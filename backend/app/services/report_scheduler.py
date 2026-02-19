"""
Report Scheduler Service

Background task that checks for due report schedules and generates reports.
Also provides the generate_report_for_schedule function used by manual triggers.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session_maker
from app.models import (
    Report,
    ReportGoal,
    ReportSchedule,
    User,
)

logger = logging.getLogger(__name__)


async def run_report_scheduler():
    """
    Background task that checks for due report schedules.

    Runs every 15 minutes after an initial 10-minute startup delay.
    """
    # Wait 10 minutes after startup
    await asyncio.sleep(600)

    while True:
        try:
            async with async_session_maker() as db:
                now = datetime.utcnow()

                # Find enabled schedules that are due
                result = await db.execute(
                    select(ReportSchedule)
                    .where(
                        and_(
                            ReportSchedule.is_enabled.is_(True),
                            ReportSchedule.next_run_at <= now,
                        )
                    )
                    .options(selectinload(ReportSchedule.goal_links))
                )
                due_schedules = result.scalars().all()

                for schedule in due_schedules:
                    try:
                        # Get the user for this schedule
                        user_result = await db.execute(
                            select(User).where(User.id == schedule.user_id)
                        )
                        user = user_result.scalar_one_or_none()
                        if not user or not user.is_active:
                            logger.warning(
                                f"Skipping schedule {schedule.id}: user "
                                f"{schedule.user_id} inactive or missing"
                            )
                            continue

                        logger.info(
                            f"Generating report for schedule {schedule.id} "
                            f"({schedule.name}, {schedule.periodicity})"
                        )
                        await generate_report_for_schedule(db, schedule, user)
                        logger.info(
                            f"Report generated for schedule {schedule.id}"
                        )

                    except Exception as e:
                        logger.error(
                            f"Failed to generate report for schedule "
                            f"{schedule.id}: {e}",
                            exc_info=True,
                        )

        except Exception as e:
            logger.error(f"Error in report scheduler loop: {e}", exc_info=True)

        # Check every 15 minutes
        await asyncio.sleep(900)


def _normalize_recipient(item) -> dict:
    """
    Normalize a recipient to {"email": ..., "level": ...}.

    Handles both new object format and legacy plain string format.
    """
    if isinstance(item, dict) and "email" in item:
        level = item.get("level", "comfortable")
        if level not in ("beginner", "comfortable", "experienced"):
            level = "comfortable"
        return {"email": item["email"], "level": level}
    if isinstance(item, str):
        return {"email": item, "level": "comfortable"}
    return {"email": str(item), "level": "comfortable"}


async def generate_report_for_schedule(
    db: AsyncSession,
    schedule: ReportSchedule,
    user: User,
    save: bool = True,
    send_email: bool = True,
) -> Report:
    """
    Generate a report for a given schedule.

    Args:
        db: Database session
        schedule: The schedule to generate for
        user: The user who owns the schedule
        save: Whether to save the report to the database
        send_email: Whether to send the email

    Returns:
        The generated Report object (may not be persisted if save=False)
    """
    from app.services.report_ai_service import generate_report_summary
    from app.services.report_data_service import (
        gather_report_data,
        get_prior_period_data,
    )
    from app.services.report_generator_service import (
        build_report_html,
        generate_pdf,
    )

    # Compute period bounds
    period_start, period_end = compute_period_bounds(
        schedule.periodicity, datetime.utcnow()
    )
    period_label = _format_period_label(period_start, period_end)

    # Get linked goals
    goals = []
    if schedule.goal_links:
        goal_ids = [link.goal_id for link in schedule.goal_links]
        if goal_ids:
            result = await db.execute(
                select(ReportGoal).where(
                    ReportGoal.id.in_(goal_ids),
                    ReportGoal.user_id == user.id,
                )
            )
            goals = list(result.scalars().all())

    # Gather report data
    report_data = await gather_report_data(
        db, user.id, schedule.account_id, period_start, period_end, goals
    )
    period_days = (period_end - period_start).days
    report_data["period_days"] = period_days

    # Get prior period data for comparison
    if schedule.id:
        prior_data = await get_prior_period_data(db, schedule.id, period_start)
        if prior_data:
            report_data["prior_period"] = prior_data

    # Generate AI summary (returns dict of tiers or None)
    ai_summary, ai_provider_used = await generate_report_summary(
        db, user.id, report_data, period_label, schedule.ai_provider
    )

    # Build canonical HTML (comfortable is the default for stored report)
    user_name = user.display_name or user.email
    html_content = build_report_html(
        report_data, ai_summary, user_name, period_label,
        default_level="comfortable",
    )

    # Generate PDF (includes all three tiers with no emphasis)
    pdf_data = dict(report_data)
    if ai_summary:
        pdf_data["_ai_summary"] = ai_summary
    pdf_content = generate_pdf(html_content, report_data=pdf_data)

    # Store ai_summary as JSON string for the DB
    ai_summary_str = None
    if ai_summary is not None:
        ai_summary_str = json.dumps(ai_summary) if isinstance(ai_summary, dict) else ai_summary

    # Create report object
    report = Report(
        user_id=user.id,
        schedule_id=schedule.id,
        period_start=period_start,
        period_end=period_end,
        periodicity=schedule.periodicity,
        report_data=report_data,
        html_content=html_content,
        pdf_content=pdf_content,
        ai_summary=ai_summary_str,
        ai_provider_used=ai_provider_used,
        delivery_status="pending" if send_email else "manual",
    )

    if save:
        db.add(report)
        await db.flush()  # Get the report.id

    # Send email — per-recipient with level-specific HTML
    if send_email and save and schedule.recipients:
        recipients = [_normalize_recipient(r) for r in schedule.recipients]
        email_sent = await _deliver_report(
            report, recipients, ai_summary, report_data, user_name,
            period_label, pdf_content,
        )
        if email_sent:
            report.delivery_status = "sent"
            report.delivered_at = datetime.utcnow()
            report.delivery_recipients = schedule.recipients
        else:
            report.delivery_status = "failed"
            report.delivery_error = "Email delivery failed"

    if save:
        # Update schedule's last_run_at and next_run_at
        schedule.last_run_at = datetime.utcnow()
        schedule.next_run_at = compute_next_run_at(
            schedule.periodicity, schedule.last_run_at
        )
        await db.commit()
        await db.refresh(report)

    return report


async def _deliver_report(
    report: Report,
    recipients: list,
    ai_summary: Optional[dict],
    report_data: dict,
    user_name: str,
    period_label: str,
    pdf_content: Optional[bytes],
) -> bool:
    """
    Send the report email to each recipient individually with their
    experience-level-specific HTML.

    Caches HTML per level to avoid redundant builds (at most 3 variants).
    Returns True if at least one email was sent successfully.
    """
    from app.services.brand_service import get_brand
    from app.services.email_service import send_report_email
    from app.services.report_generator_service import build_report_html

    b = get_brand()

    if not recipients:
        return False

    subject = f"{b['shortName']} Performance Report \u2014 {period_label}"

    # Plain text fallback (same for all recipients)
    data = report.report_data or report_data or {}
    pd = data.get("period_days")
    trades_suffix = f" (last {pd}d)" if pd else ""
    text_body = (
        f"{b['shortName']} Performance Report\n"
        f"Period: {period_label}\n\n"
        f"Account Value: ${data.get('account_value_usd', 0):,.2f}\n"
        f"Period Profit: ${data.get('period_profit_usd', 0):,.2f}\n"
        f"Total Trades{trades_suffix}: {data.get('total_trades', 0)}\n"
        f"Win Rate: {data.get('win_rate', 0):.1f}%\n"
    )

    pdf_filename = (
        f"performance_report_{report.period_end.strftime('%Y-%m-%d')}.pdf"
        if report.period_end else "performance_report.pdf"
    )

    # Cache HTML per level
    html_cache: dict = {}
    any_sent = False

    for recipient in recipients:
        email = recipient["email"]
        level = recipient.get("level", "comfortable")

        # Build level-specific HTML (cached)
        if level not in html_cache:
            html_cache[level] = build_report_html(
                report_data, ai_summary, user_name, period_label,
                default_level=level,
            )

        try:
            sent = send_report_email(
                to=email,
                cc=[],
                subject=subject,
                html_body=html_cache[level],
                text_body=text_body,
                pdf_attachment=pdf_content,
                pdf_filename=pdf_filename,
            )
            if sent:
                any_sent = True
                logger.info(
                    f"Report email sent to {email} (level={level})"
                )
            else:
                logger.warning(
                    f"Failed to send report email to {email}"
                )
        except Exception as e:
            logger.error(
                f"Error sending report email to {email}: {e}"
            )

    return any_sent


def compute_next_run_at(periodicity: str, last_run_at: datetime) -> datetime:
    """Calculate the next run time based on periodicity."""
    if periodicity == "daily":
        return (last_run_at + timedelta(days=1)).replace(
            hour=6, minute=0, second=0, microsecond=0
        )
    elif periodicity == "weekly":
        days_ahead = 7 - last_run_at.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return (last_run_at + timedelta(days=days_ahead)).replace(
            hour=6, minute=0, second=0, microsecond=0
        )
    elif periodicity == "biweekly":
        days_ahead = 14 - last_run_at.weekday()
        if days_ahead <= 0:
            days_ahead += 14
        return (last_run_at + timedelta(days=days_ahead)).replace(
            hour=6, minute=0, second=0, microsecond=0
        )
    elif periodicity == "monthly":
        if last_run_at.month == 12:
            return last_run_at.replace(
                year=last_run_at.year + 1, month=1, day=1,
                hour=6, minute=0, second=0, microsecond=0,
            )
        return last_run_at.replace(
            month=last_run_at.month + 1, day=1,
            hour=6, minute=0, second=0, microsecond=0,
        )
    elif periodicity == "quarterly":
        quarter_months = [1, 4, 7, 10]
        next_q = None
        for m in quarter_months:
            if m > last_run_at.month:
                next_q = m
                break
        if next_q is None:
            return last_run_at.replace(
                year=last_run_at.year + 1, month=1, day=1,
                hour=6, minute=0, second=0, microsecond=0,
            )
        return last_run_at.replace(
            month=next_q, day=1,
            hour=6, minute=0, second=0, microsecond=0,
        )
    elif periodicity == "yearly":
        return last_run_at.replace(
            year=last_run_at.year + 1, month=1, day=1,
            hour=6, minute=0, second=0, microsecond=0,
        )
    else:
        return last_run_at + timedelta(days=7)


def compute_period_bounds(periodicity: str, run_at: datetime):
    """Compute the period start and end for a given run time."""
    if periodicity == "daily":
        period_end = run_at.replace(hour=0, minute=0, second=0, microsecond=0)
        period_start = period_end - timedelta(days=1)
    elif periodicity == "weekly":
        period_end = run_at.replace(hour=0, minute=0, second=0, microsecond=0)
        period_start = period_end - timedelta(days=7)
    elif periodicity == "biweekly":
        period_end = run_at.replace(hour=0, minute=0, second=0, microsecond=0)
        period_start = period_end - timedelta(days=14)
    elif periodicity == "monthly":
        # Previous month
        period_end = run_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_start = (period_end - timedelta(days=1)).replace(day=1)
    elif periodicity == "quarterly":
        # Previous quarter
        period_end = run_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Go back 3 months
        if period_end.month <= 3:
            period_start = period_end.replace(year=period_end.year - 1, month=period_end.month + 9)
        else:
            period_start = period_end.replace(month=period_end.month - 3)
    elif periodicity == "yearly":
        period_end = run_at.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        period_start = period_end.replace(year=period_end.year - 1)
    else:
        period_end = run_at
        period_start = run_at - timedelta(days=7)

    return period_start, period_end


def _format_period_label(start: datetime, end: datetime) -> str:
    """Format a human-readable period label."""
    if start.year == end.year:
        if start.month == end.month:
            return f"{start.strftime('%B %d')} - {end.strftime('%d, %Y')}"
        return f"{start.strftime('%B %d')} - {end.strftime('%B %d, %Y')}"
    return f"{start.strftime('%B %d, %Y')} - {end.strftime('%B %d, %Y')}"
