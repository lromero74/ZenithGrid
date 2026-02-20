"""
Report Scheduler Service

Background task that checks for due report schedules and generates reports.
Also provides the generate_report_for_schedule function used by manual triggers.
"""

import asyncio
import calendar
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from dateutil.relativedelta import relativedelta
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

RUN_HOUR = 6  # All scheduled reports run at 06:00 UTC


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
            logger.error(
                f"Error in report scheduler loop: {e}", exc_info=True
            )

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
    advance_schedule: bool = True,
) -> Report:
    """
    Generate a report for a given schedule.

    Args:
        advance_schedule: If True, update last_run_at and next_run_at.
            Set to False for ad-hoc/manual runs so they don't affect
            the scheduled cadence.
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

    now = datetime.utcnow()

    # Compute period bounds using new flexible logic
    if schedule.schedule_type:
        period_start, period_end = compute_period_bounds_flexible(
            schedule, now
        )
    else:
        # Legacy fallback for unmigrated schedules
        period_start, period_end = _compute_period_bounds_legacy(
            schedule.periodicity, now
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
        prior_data = await get_prior_period_data(
            db, schedule.id, period_start
        )
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
        ai_summary_str = (
            json.dumps(ai_summary)
            if isinstance(ai_summary, dict) else ai_summary
        )

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
        # Only advance schedule timing for automated runs,
        # not ad-hoc/manual triggers
        if advance_schedule:
            schedule.last_run_at = datetime.utcnow()
            if schedule.schedule_type:
                schedule.next_run_at = compute_next_run_flexible(
                    schedule, schedule.last_run_at
                )
            else:
                schedule.next_run_at = _compute_next_run_legacy(
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


# ---- Flexible scheduling helpers ----

def _parse_schedule_days(schedule: ReportSchedule) -> Optional[List[int]]:
    """Parse schedule_days JSON string to list of ints."""
    if not schedule.schedule_days:
        return None
    try:
        days = json.loads(schedule.schedule_days)
        if isinstance(days, list):
            return [int(d) for d in days]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _at_run_time(dt: datetime) -> datetime:
    """Set time to the standard run hour (06:00 UTC)."""
    return dt.replace(hour=RUN_HOUR, minute=0, second=0, microsecond=0)


def _last_day_of_month(year: int, month: int) -> int:
    """Return the last day of the given month."""
    return calendar.monthrange(year, month)[1]


def _resolve_day_of_month(day: int, year: int, month: int) -> int:
    """Resolve day-of-month, handling -1 (last day) and clamping."""
    last = _last_day_of_month(year, month)
    if day == -1:
        return last
    return min(day, last)


def compute_next_run_flexible(
    schedule: ReportSchedule,
    after: datetime,
) -> datetime:
    """
    Compute the next run datetime based on flexible schedule fields.

    Args:
        schedule: The schedule with schedule_type, schedule_days, etc.
        after: Find the next run strictly after this datetime.
    """
    stype = schedule.schedule_type or "weekly"
    days = _parse_schedule_days(schedule)

    if stype == "daily":
        # Next day at run hour
        nxt = _at_run_time(after + timedelta(days=1))
        return nxt

    elif stype == "weekly":
        # days = list of weekday ints (0=Mon, 6=Sun)
        run_days = sorted(days) if days else [0]  # default Monday
        # Scan next 7 days starting from tomorrow
        for offset in range(1, 8):
            candidate = after + timedelta(days=offset)
            if candidate.weekday() in run_days:
                return _at_run_time(candidate)
        # Fallback (shouldn't reach here)
        return _at_run_time(after + timedelta(days=7))

    elif stype == "monthly":
        # days = list of day-of-month ints, e.g. [1, 15] or [-1]
        run_days = sorted(days) if days else [1]
        # Check remaining days in current month, then next month
        for month_offset in range(0, 3):
            check_date = after + relativedelta(months=month_offset)
            y, m = check_date.year, check_date.month
            for d in run_days:
                resolved = _resolve_day_of_month(d, y, m)
                candidate = _at_run_time(
                    datetime(y, m, resolved)
                )
                if candidate > after:
                    return candidate
        # Fallback: 1st of next month
        return _at_run_time(
            (after.replace(day=1) + relativedelta(months=1))
        )

    elif stype == "quarterly":
        # days = [day_of_month], quarter_start_month defines cycle
        qstart = schedule.quarter_start_month or 1
        run_day = days[0] if days else 1
        # Build quarter start months from qstart
        q_months = [(qstart + 3 * i - 1) % 12 + 1 for i in range(4)]
        q_months_sorted = sorted(q_months)

        # Check this year and next year
        for year_offset in range(0, 2):
            y = after.year + year_offset
            for m in q_months_sorted:
                resolved = _resolve_day_of_month(run_day, y, m)
                candidate = _at_run_time(datetime(y, m, resolved))
                if candidate > after:
                    return candidate
        # Fallback
        return _at_run_time(
            datetime(after.year + 1, q_months_sorted[0], run_day)
        )

    elif stype == "yearly":
        # days = [month, day_of_month], e.g. [6, 15] = June 15
        run_month = days[0] if days and len(days) >= 1 else 1
        run_day = days[1] if days and len(days) >= 2 else 1
        # Try this year, then next year
        for year_offset in range(0, 2):
            y = after.year + year_offset
            resolved = _resolve_day_of_month(run_day, y, run_month)
            candidate = _at_run_time(
                datetime(y, run_month, resolved)
            )
            if candidate > after:
                return candidate
        return _at_run_time(
            datetime(after.year + 2, run_month, run_day)
        )

    # Unknown type fallback
    return _at_run_time(after + timedelta(days=7))


def compute_period_bounds_flexible(
    schedule: ReportSchedule,
    run_at: datetime,
) -> Tuple[datetime, datetime]:
    """
    Compute period bounds based on flexible schedule fields.

    Period window options:
    - full_prior: Complete previous period (week/month/quarter/year)
    - wtd: Week to date (Monday through run_at)
    - mtd: Month to date (1st through run_at)
    - qtd: Quarter to date (quarter start through run_at)
    - ytd: Year to date (Jan 1 through run_at)
    - trailing: Rolling lookback of N units (days/weeks/months/years)
    """
    window = schedule.period_window or "full_prior"
    period_end = run_at.replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    if window == "trailing":
        val = schedule.lookback_value or 7
        unit = schedule.lookback_unit or "days"
        if unit == "days":
            period_start = period_end - timedelta(days=val)
        elif unit == "weeks":
            period_start = period_end - timedelta(weeks=val)
        elif unit == "months":
            period_start = period_end - relativedelta(months=val)
        elif unit == "years":
            period_start = period_end - relativedelta(years=val)
        else:
            period_start = period_end - timedelta(days=val)
        return period_start, period_end

    if window == "wtd":
        # Monday of current week through run_at
        weekday = period_end.weekday()  # 0=Mon
        period_start = period_end - timedelta(days=weekday)
        return period_start, period_end

    if window == "mtd":
        period_start = period_end.replace(day=1)
        return period_start, period_end

    if window == "qtd":
        qstart = schedule.quarter_start_month or 1
        q_months = sorted(
            [(qstart + 3 * i - 1) % 12 + 1 for i in range(4)]
        )
        # Find the most recent quarter start <= run_at month
        quarter_month = q_months[0]
        for m in q_months:
            if m <= period_end.month:
                quarter_month = m
        period_start = period_end.replace(
            month=quarter_month, day=1
        )
        # If quarter_month is after current month, it started last year
        if quarter_month > period_end.month:
            period_start = period_start.replace(
                year=period_end.year - 1
            )
        return period_start, period_end

    if window == "ytd":
        period_start = period_end.replace(month=1, day=1)
        return period_start, period_end

    # full_prior (default) — complete previous period based on schedule_type
    stype = schedule.schedule_type or "weekly"
    return _compute_full_prior_bounds(stype, period_end, schedule)


def _compute_full_prior_bounds(
    stype: str,
    period_end: datetime,
    schedule: ReportSchedule,
) -> Tuple[datetime, datetime]:
    """Compute full prior period bounds based on schedule type."""
    if stype == "daily":
        end = period_end
        start = end - timedelta(days=1)
        return start, end

    if stype == "weekly":
        # Full prior week: last Monday through last Sunday
        weekday = period_end.weekday()
        last_monday = period_end - timedelta(days=weekday + 7)
        last_sunday = last_monday + timedelta(days=7)
        return last_monday, last_sunday

    if stype == "monthly":
        # Full prior month
        first_of_this_month = period_end.replace(day=1)
        end = first_of_this_month
        start = (first_of_this_month - timedelta(days=1)).replace(day=1)
        return start, end

    if stype == "quarterly":
        # Full prior quarter
        qstart = schedule.quarter_start_month or 1
        q_months = sorted(
            [(qstart + 3 * i - 1) % 12 + 1 for i in range(4)]
        )
        # Find the most recent quarter start <= current month
        current_q_start = q_months[0]
        for m in q_months:
            if m <= period_end.month:
                current_q_start = m
        # The prior quarter ends at current_q_start
        q_end = period_end.replace(month=current_q_start, day=1)
        if current_q_start > period_end.month:
            q_end = q_end.replace(year=period_end.year - 1)
        q_start = q_end - relativedelta(months=3)
        return q_start, q_end

    if stype == "yearly":
        # Full prior year
        end = period_end.replace(month=1, day=1)
        start = end.replace(year=end.year - 1)
        return start, end

    # Unknown type fallback
    return period_end - timedelta(days=7), period_end


# ---- Legacy functions (for unmigrated schedules) ----

def _compute_next_run_legacy(
    periodicity: str, last_run_at: datetime,
) -> datetime:
    """Legacy: Calculate next run time based on old periodicity field."""
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


def _compute_period_bounds_legacy(
    periodicity: str, run_at: datetime,
) -> Tuple[datetime, datetime]:
    """Legacy: Compute period bounds based on old periodicity field."""
    if periodicity == "daily":
        period_end = run_at.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        period_start = period_end - timedelta(days=1)
    elif periodicity == "weekly":
        period_end = run_at.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        period_start = period_end - timedelta(days=7)
    elif periodicity == "biweekly":
        period_end = run_at.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        period_start = period_end - timedelta(days=14)
    elif periodicity == "monthly":
        period_end = run_at.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        period_start = (period_end - timedelta(days=1)).replace(day=1)
    elif periodicity == "quarterly":
        period_end = run_at.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        if period_end.month <= 3:
            period_start = period_end.replace(
                year=period_end.year - 1, month=period_end.month + 9
            )
        else:
            period_start = period_end.replace(
                month=period_end.month - 3
            )
    elif periodicity == "yearly":
        period_end = run_at.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        period_start = period_end.replace(year=period_end.year - 1)
    else:
        period_end = run_at
        period_start = run_at - timedelta(days=7)

    return period_start, period_end


# ---- Public aliases for backward compatibility ----
# These are used by the router's _compute_next_run helper

def compute_next_run_at(
    periodicity: str, last_run_at: datetime,
) -> datetime:
    """Public alias — delegates to legacy logic."""
    return _compute_next_run_legacy(periodicity, last_run_at)


def compute_period_bounds(
    periodicity: str, run_at: datetime,
) -> Tuple[datetime, datetime]:
    """Public alias — delegates to legacy logic."""
    return _compute_period_bounds_legacy(periodicity, run_at)


# ---- Human-readable label generation ----

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_NAMES = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

WINDOW_LABELS = {
    "full_prior": "full prior period",
    "wtd": "WTD",
    "mtd": "MTD",
    "qtd": "QTD",
    "ytd": "YTD",
    "trailing": None,  # built dynamically
}


def build_periodicity_label(
    schedule_type: str,
    schedule_days: Optional[str],
    quarter_start_month: Optional[int],
    period_window: str,
    lookback_value: Optional[int],
    lookback_unit: Optional[str],
) -> str:
    """
    Build a human-readable periodicity label from flexible schedule fields.

    Examples:
    - "Every Mon, Wed - full prior period"
    - "Monthly on 1st & 15th - MTD"
    - "Quarterly from Feb, day 1 - full prior period"
    - "Yearly on Jun 15 - trailing 30d"
    - "Daily - YTD"
    """
    days = None
    if schedule_days:
        try:
            days = json.loads(schedule_days)
        except (json.JSONDecodeError, TypeError):
            pass

    # Schedule part
    if schedule_type == "daily":
        sched_part = "Daily"
    elif schedule_type == "weekly":
        if days:
            day_names = [
                WEEKDAY_NAMES[d] for d in sorted(days)
                if 0 <= d <= 6
            ]
            sched_part = f"Every {', '.join(day_names)}"
        else:
            sched_part = "Weekly"
    elif schedule_type == "monthly":
        if days:
            day_strs = []
            for d in sorted(days):
                if d == -1:
                    day_strs.append("last")
                else:
                    day_strs.append(_ordinal(d))
            sched_part = f"Monthly on {' & '.join(day_strs)}"
        else:
            sched_part = "Monthly"
    elif schedule_type == "quarterly":
        qm = quarter_start_month or 1
        run_day = days[0] if days else 1
        sched_part = (
            f"Quarterly from {MONTH_NAMES[qm]}, day {run_day}"
        )
    elif schedule_type == "yearly":
        if days and len(days) >= 2:
            m, d = days[0], days[1]
            sched_part = f"Yearly on {MONTH_NAMES[m]} {d}"
        else:
            sched_part = "Yearly"
    else:
        sched_part = schedule_type.capitalize() if schedule_type else "Custom"

    # Window part
    window = period_window or "full_prior"
    if window == "trailing" and lookback_value:
        unit = lookback_unit or "days"
        unit_abbrev = {
            "days": "d", "weeks": "w", "months": "mo", "years": "y",
        }
        window_part = (
            f"trailing {lookback_value}{unit_abbrev.get(unit, unit)}"
        )
    else:
        window_part = WINDOW_LABELS.get(window, window)

    return f"{sched_part} - {window_part}"


def _ordinal(n: int) -> str:
    """Return ordinal string for a number (1st, 2nd, 3rd, ...)."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _format_period_label(start: datetime, end: datetime) -> str:
    """Format a human-readable period label."""
    if start.year == end.year:
        if start.month == end.month:
            return (
                f"{start.strftime('%B %d')} - "
                f"{end.strftime('%d, %Y')}"
            )
        return (
            f"{start.strftime('%B %d')} - "
            f"{end.strftime('%B %d, %Y')}"
        )
    return (
        f"{start.strftime('%B %d, %Y')} - "
        f"{end.strftime('%B %d, %Y')}"
    )
