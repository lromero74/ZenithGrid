"""
Report Scheduler Service

Background task that checks for due report schedules and generates reports.
Also provides the generate_report_for_schedule function used by manual triggers.
"""

import asyncio
from app.utils.timeutil import utcnow
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session_maker as _default_session_maker
from app.models import (
    Account,
    GoalProgressSnapshot,
    Report,
    ReportGoal,
    ReportSchedule,
    User,
)

from app.services.report_schedule_timing import (
    compute_next_run_flexible,
    compute_period_bounds_flexible,
    _compute_next_run_legacy,
    _compute_period_bounds_legacy,
    _format_period_label,
    _should_auto_prior,
)

logger = logging.getLogger(__name__)


async def run_report_scheduler_once(session_maker=None):
    """
    Check for due report schedules and generate them. Called by APScheduler every 15 minutes.
    """
    sm = session_maker or _default_session_maker
    try:
        async with sm() as db:
            now = utcnow()

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
            f"Error in report scheduler: {e}", exc_info=True
        )


def _normalize_recipient(item) -> str:
    """
    Extract email string from a recipient entry.

    Handles both legacy object format {"email": ..., "level": ...}
    and plain string format.
    """
    if isinstance(item, dict) and "email" in item:
        return item["email"]
    return str(item)


async def _fetch_schedule_goals(
    db: AsyncSession, schedule: "ReportSchedule", user_id: int,
) -> list:
    """Resolve the ReportGoal ORM rows linked to this schedule (user-scoped)."""
    if not schedule.goal_links:
        return []
    goal_ids = [link.goal_id for link in schedule.goal_links]
    if not goal_ids:
        return []
    result = await db.execute(
        select(ReportGoal).where(
            ReportGoal.id.in_(goal_ids),
            ReportGoal.user_id == user_id,
        )
    )
    return list(result.scalars().all())


async def _attach_goal_trend_data(
    db: AsyncSession,
    schedule: "ReportSchedule",
    goals: list,
    report_data: dict,
    period_days: int,
) -> None:
    """For each non-income goal, attach trend_data + chart_settings in-place."""
    from app.services.goal_snapshot_service import (
        backfill_goal_snapshots,
        clip_trend_data,
        compute_horizon_date,
        get_goal_trend_data,
    )

    goal_orm_map = {g.id: g for g in goals}
    sched_horizon = getattr(schedule, "chart_horizon", "auto") or "auto"
    sched_mult = getattr(schedule, "chart_lookahead_multiplier", 1.0) or 1.0
    show_minimap_default = getattr(schedule, "show_minimap", True)
    if show_minimap_default is None:
        show_minimap_default = True

    for goal_dict in report_data.get("goals", []):
        if goal_dict.get("target_type") in ("income",):
            continue
        gid = goal_dict.get("goal_id")
        if not gid or gid not in goal_orm_map:
            continue
        try:
            goal_orm = goal_orm_map[gid]
            snap_count = await db.execute(
                select(func.count(GoalProgressSnapshot.id))
                .where(GoalProgressSnapshot.goal_id == gid)
            )
            if snap_count.scalar() == 0:
                await backfill_goal_snapshots(db, goal_orm)
            trend = await get_goal_trend_data(db, goal_orm)
            goal_dict["trend_data"] = trend

            target_date_str = goal_orm.target_date.strftime("%Y-%m-%d")
            horizon_date = compute_horizon_date(
                trend["data_points"], target_date_str, sched_horizon,
                schedule_period_days=period_days,
                lookahead_multiplier=sched_mult,
            )

            goal_dict["chart_settings"] = {
                "horizon_date": horizon_date,
                "show_minimap": show_minimap_default and horizon_date < target_date_str,
                "target_date": target_date_str,
                "full_data_points": trend["data_points"],
            }

            goal_dict["trend_data"] = clip_trend_data(trend, horizon_date)
        except Exception as e:
            logger.warning(f"Failed to fetch trend data for goal {gid}: {e}")


async def _fetch_account_name(db: AsyncSession, account_id: Optional[int]) -> Optional[str]:
    """Resolve account display name, or None if unset/missing."""
    if not account_id:
        return None
    acct_result = await db.execute(
        select(Account).where(Account.id == account_id)
    )
    acct = acct_result.scalar_one_or_none()
    return acct.name if acct else None


async def _advance_schedule_timing(
    schedule: "ReportSchedule", db: AsyncSession,
) -> None:
    """Update last_run_at/next_run_at for an automated run."""
    schedule.last_run_at = utcnow()
    if schedule.schedule_type:
        schedule.next_run_at = compute_next_run_flexible(
            schedule, schedule.last_run_at,
        )
    else:
        schedule.next_run_at = _compute_next_run_legacy(
            schedule.periodicity, schedule.last_run_at,
        )


def _compute_report_period(schedule: ReportSchedule, now: datetime) -> Tuple[datetime, datetime, str]:
    """Resolve a schedule's period bounds + human label (fast, no I/O)."""
    if schedule.schedule_type:
        period_start, period_end = compute_period_bounds_flexible(schedule, now)
    else:
        # Legacy fallback for unmigrated schedules
        period_start, period_end = _compute_period_bounds_legacy(
            schedule.periodicity, now
        )
    period_label = _format_period_label(period_start, period_end)
    return period_start, period_end, period_label


async def generate_report_for_schedule(
    db: AsyncSession,
    schedule: ReportSchedule,
    user: User,
    save: bool = True,
    send_email: bool = True,
    advance_schedule: bool = True,
    report: Optional[Report] = None,
) -> Report:
    """
    Generate a report for a given schedule.

    Args:
        advance_schedule: If True, update last_run_at and next_run_at.
            Set to False for ad-hoc/manual runs so they don't affect
            the scheduled cadence.
        report: If provided, fill in this existing (e.g. ``pending``) row in
            place instead of creating a new one — used by async manual
            generation so the row that was returned to the client becomes the
            finished report. The row is flipped to ``generation_status='complete'``.
    """
    from app.services.report_ai_service import generate_report_summary
    from app.services.report_data_service import (
        gather_report_data,
        get_prior_period_data,
    )
    from app.services.report_generator_service import (
        BuildReportHtmlParams,
        build_report_html,
        generate_pdf,
    )

    now = utcnow()

    # Compute period bounds (flexible logic, with legacy fallback)
    period_start, period_end, period_label = _compute_report_period(schedule, now)

    # Get linked goals
    goals = await _fetch_schedule_goals(db, schedule, user.id)

    # Gather report data
    report_data = await gather_report_data(
        db, user.id, schedule.account_id, period_start, period_end, goals
    )
    period_days = (period_end - period_start).days
    report_data["period_days"] = period_days

    # Pass schedule metadata for features that need period context
    _pw = schedule.period_window or "full_prior"
    _is_auto_prior = (
        _pw in ("mtd", "wtd")
        and _should_auto_prior(schedule, _pw, now)
    )
    report_data["_schedule_meta"] = {
        "period_window": _pw,
        "show_expense_lookahead": bool(
            getattr(schedule, "show_expense_lookahead", True)
        ) and not _is_auto_prior,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
    }

    # Fetch trend data for non-income goals (for chart embedding)
    await _attach_goal_trend_data(db, schedule, goals, report_data, period_days)

    # Get prior period data for comparison
    if schedule.id:
        prior_data = await get_prior_period_data(
            db, schedule.id, period_start
        )
        if prior_data:
            report_data["prior_period"] = prior_data
            _compute_expense_changes(report_data, prior_data)

    # Generate AI summary (returns dict of tiers or None)
    if schedule.generate_ai_summary is not False:
        ai_summary, ai_provider_used = await generate_report_summary(
            db, user.id, report_data, period_label, schedule.ai_provider
        )
    else:
        ai_summary, ai_provider_used = None, None

    # Build canonical HTML (simple is the default tab for stored report)
    user_name = user.display_name or user.email

    # Fetch account name for display in report header
    account_name = await _fetch_account_name(db, schedule.account_id)

    sched_name = schedule.name if schedule else None
    html_content = build_report_html(BuildReportHtmlParams(
        report_data=report_data, ai_summary=ai_summary, user_name=user_name,
        period_label=period_label, default_level="simple",
        schedule_name=sched_name, account_name=account_name,
    ))

    # Generate PDF (includes all three tiers with no emphasis)
    pdf_data = dict(report_data)
    if ai_summary:
        pdf_data["_ai_summary"] = ai_summary
    pdf_content = generate_pdf(
        html_content, report_data=pdf_data, schedule_name=sched_name,
        account_name=account_name,
    )

    # Store ai_summary as JSON string for the DB
    ai_summary_str = None
    if ai_summary is not None:
        ai_summary_str = (
            json.dumps(ai_summary)
            if isinstance(ai_summary, dict) else ai_summary
        )

    initial_delivery_status = "pending" if (send_email and schedule.recipients) else "manual"

    # Create a new row, or fill in an existing (pending) one in place.
    if report is None:
        report = Report(
            user_id=user.id,
            account_id=schedule.account_id,
            schedule_id=schedule.id,
            period_start=period_start,
            period_end=period_end,
            periodicity=schedule.periodicity,
            report_data=report_data,
            html_content=html_content,
            pdf_content=pdf_content,
            ai_summary=ai_summary_str,
            ai_provider_used=ai_provider_used,
            delivery_status=initial_delivery_status,
            generation_status="complete",
        )
    else:
        report.period_start = period_start
        report.period_end = period_end
        report.periodicity = schedule.periodicity
        report.report_data = report_data
        report.html_content = html_content
        report.pdf_content = pdf_content
        report.ai_summary = ai_summary_str
        report.ai_provider_used = ai_provider_used
        report.delivery_status = initial_delivery_status
        report.generation_status = "complete"
        report.generation_error = None

    if save:
        db.add(report)
        await db.flush()  # Get the report.id (no-op if it already has one)

    # Send email to all recipients (same report for everyone)
    if send_email and save and schedule.recipients:
        recipients = [_normalize_recipient(r) for r in schedule.recipients]
        email_sent, delivery_error = await _deliver_report(DeliverReportParams(
            report=report, recipients=recipients, ai_summary=ai_summary,
            report_data=report_data, user_name=user_name,
            period_label=period_label, pdf_content=pdf_content,
            schedule_name=sched_name, account_name=account_name,
        ))
        if email_sent:
            report.delivery_status = "sent"
            report.delivered_at = utcnow()
            report.delivery_recipients = schedule.recipients
        else:
            report.delivery_status = "failed"
            report.delivery_error = (delivery_error or "Email delivery failed")[:500]

    if save:
        # Only advance schedule timing for automated runs,
        # not ad-hoc/manual triggers
        if advance_schedule:
            await _advance_schedule_timing(schedule, db)
        await db.commit()
        await db.refresh(report)

        # Apply retention policy — delete old reports that exceed the schedule's limits
        if save and schedule.id and (
            schedule.retention_count is not None or schedule.retention_days is not None
        ):
            from app.services.report_schedule_service import apply_retention
            deleted = await apply_retention(schedule, db)
            if deleted:
                logger.info(
                    f"Retention cleanup: deleted {deleted} old report(s) "
                    f"for schedule {schedule.id} ({schedule.name})"
                )

    return report


# ── Async manual generation ──────────────────────────────────────────────────
# Strong refs to in-flight background tasks so they aren't garbage-collected
# mid-run (asyncio only holds a weak ref to a bare create_task result).
_BG_TASKS: set = set()

# A pending report older than this is assumed orphaned (process died mid-run).
_PENDING_ORPHAN_MINUTES = 15


def _spawn_bg(coro) -> None:
    """Fire-and-forget a coroutine, keeping a strong ref until it completes."""
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


async def _reap_orphaned_pending_reports(
    db: AsyncSession, older_than_minutes: int = _PENDING_ORPHAN_MINUTES
) -> int:
    """Mark long-stuck ``pending`` reports as ``failed`` (self-heal after a crash/restart)."""
    cutoff = utcnow() - timedelta(minutes=older_than_minutes)
    result = await db.execute(
        update(Report)
        .where(Report.generation_status == "pending", Report.created_at < cutoff)
        .values(
            generation_status="failed",
            generation_error="Generation did not finish (the server restarted). Please try again.",
        )
    )
    if result.rowcount:
        await db.commit()
        logger.info("Reaped %d orphaned pending report(s)", result.rowcount)
    return result.rowcount or 0


async def start_manual_report_generation(
    db: AsyncSession,
    schedule: ReportSchedule,
    user: User,
    send_email: bool = True,
    session_maker=None,
) -> Report:
    """
    Create a ``pending`` report row and kick off generation in the background,
    returning the pending row immediately.

    The heavy work (data gather + AI summary + PDF render) routinely takes longer
    than a client/proxy request window; doing it synchronously made the request
    time out while the report finished server-side, leaving the UI stuck. The
    pending row appears in history as "Generating…" and the client polls until it
    flips to ``complete``/``failed``.
    """
    await _reap_orphaned_pending_reports(db)

    period_start, period_end, _ = _compute_report_period(schedule, utcnow())
    report = Report(
        user_id=user.id,
        account_id=schedule.account_id,
        schedule_id=schedule.id,
        period_start=period_start,
        period_end=period_end,
        periodicity=schedule.periodicity,
        generation_status="pending",
        delivery_status="pending" if (send_email and schedule.recipients) else "manual",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    _spawn_bg(_run_manual_generation_bg(
        report.id, schedule.id, user.id, send_email, session_maker=session_maker
    ))
    return report


async def _run_manual_generation_bg(
    report_id: int, schedule_id: int, user_id: int, send_email: bool,
    session_maker=None,
) -> None:
    """Background worker: render the pending report and flip it to complete/failed."""
    sm = session_maker or _default_session_maker
    try:
        async with sm() as bg_db:
            report = await bg_db.get(Report, report_id)
            schedule = await bg_db.get(ReportSchedule, schedule_id)
            user = await bg_db.get(User, user_id)
            if not (report and schedule and user):
                logger.warning(
                    "Manual report generation: row/schedule/user missing (report %s)", report_id
                )
                return
            await generate_report_for_schedule(
                bg_db, schedule, user,
                save=True, send_email=send_email, advance_schedule=False,
                report=report,
            )
        logger.info("Manual report %s generated", report_id)
    except Exception as e:  # noqa: BLE001 — any failure must mark the row failed
        logger.error(
            "Manual report generation failed (report %s): %s", report_id, e, exc_info=True
        )
        await _mark_report_failed(report_id, str(e), session_maker=sm)


async def _mark_report_failed(report_id: int, error: str, session_maker=None) -> None:
    """Flip a report row to ``failed`` from a fresh session (the worker's may be poisoned)."""
    sm = session_maker or _default_session_maker
    try:
        async with sm() as db:
            report = await db.get(Report, report_id)
            if report and report.generation_status != "complete":
                report.generation_status = "failed"
                report.generation_error = (error or "Generation failed")[:500]
                await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.error("Could not mark report %s failed: %s", report_id, e)


@dataclass
class DeliverReportParams:
    """Parameters for delivering a report email."""
    report: Report
    recipients: list
    ai_summary: Optional[dict]
    report_data: dict
    user_name: str
    period_label: str
    pdf_content: Optional[bytes]
    schedule_name: Optional[str] = None
    account_name: Optional[str] = None


async def _deliver_report(params: DeliverReportParams) -> tuple[bool, str | None]:
    """
    Send the report email to all recipients.

    All recipients get the same email-mode HTML (Summary tier as default).
    Returns ``(any_sent, last_error)``: ``any_sent`` is True if at least one
    email was sent successfully; ``last_error`` is the most recent failure
    reason (None on full success) so the caller can record it on the report.
    """
    from botocore.exceptions import ClientError

    from app.services.brand_service import get_brand
    from app.services.email_service import send_report_email
    from app.services.report_generator_service import BuildReportHtmlParams, build_report_html

    b = get_brand()

    if not params.recipients:
        return False, "No recipients configured"

    report_title = params.schedule_name or "Performance Report"
    subject = f"{b['shortName']} {report_title} \u2014 {params.period_label}"

    # Plain text fallback
    data = params.report.report_data or params.report_data or {}
    pd = data.get("period_days")
    trades_suffix = f" (last {pd}d)" if pd else ""
    text_body = (
        f"{b['shortName']} {report_title}\n"
        f"Period: {params.period_label}\n\n"
        f"Account Value: ${data.get('account_value_usd', 0):,.2f}\n"
        f"Period Profit: ${data.get('period_profit_usd', 0):,.2f}\n"
        f"Total Trades{trades_suffix}: {data.get('total_trades', 0)}\n"
        f"Win Rate: {data.get('win_rate', 0):.1f}%\n"
    )

    pdf_filename = (
        f"performance_report_{params.report.period_end.strftime('%Y-%m-%d')}.pdf"
        if params.report.period_end else "performance_report.pdf"
    )

    # Build HTML per color scheme (cache to avoid re-generating)
    html_cache: dict = {}  # color_scheme → (html, inline_images)
    any_sent = False
    last_error: str | None = None

    for recipient in params.recipients:
        if isinstance(recipient, dict):
            email = recipient.get("email", "")
            scheme = recipient.get("color_scheme", "dark")
        else:
            email = str(recipient)
            scheme = "dark"

        if scheme not in html_cache:
            imgs: list = []
            html = build_report_html(BuildReportHtmlParams(
                report_data=params.report_data, ai_summary=params.ai_summary,
                user_name=params.user_name, period_label=params.period_label,
                default_level="simple", schedule_name=params.schedule_name,
                email_mode=True, account_name=params.account_name,
                inline_images=imgs, color_scheme=scheme,
            ))
            html_cache[scheme] = (html, imgs)

        email_html, inline_images = html_cache[scheme]

        try:
            sent = send_report_email(
                to=email,
                cc=[],
                subject=subject,
                html_body=email_html,
                text_body=text_body,
                pdf_attachment=params.pdf_content,
                pdf_filename=pdf_filename,
                inline_images=inline_images,
            )
            if sent:
                any_sent = True
                logger.info(
                    f"Report email sent to {email} (scheme={scheme})"
                )
            else:
                # send_report_email returns False only when SES is disabled.
                last_error = "Email sending is disabled (SES_ENABLED is false)"
                logger.warning(
                    f"Failed to send report email to {email}: {last_error}"
                )
        except ClientError as e:
            err = e.response.get("Error", {})
            last_error = f"{err.get('Code', 'ClientError')}: {err.get('Message', str(e))}"
            logger.error(
                f"Error sending report email to {email}: {last_error}"
            )
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            logger.error(
                f"Error sending report email to {email}: {last_error}"
            )

    return any_sent, last_error


def _compute_expense_changes(report_data: dict, prior_data: dict) -> None:
    """
    Compare expense items between current and prior report, annotating changes.

    For each expense goal in report_data, finds the matching prior goal by
    goal_id and compares items by their DB primary key (id). Classifies items
    as increased, decreased, added, or removed. Stores result as
    g["expense_changes"] dict on each matching goal.
    """
    prior_goals = {
        g.get("goal_id"): g
        for g in prior_data.get("goals", [])
        if g.get("target_type") == "expenses"
    }

    for g in report_data.get("goals", []):
        if g.get("target_type") != "expenses":
            continue

        prior_g = prior_goals.get(g.get("goal_id"))
        if not prior_g:
            continue

        current_items = {
            item["id"]: item
            for item in g.get("expense_coverage", {}).get("items", [])
            if item.get("id") is not None
        }
        prior_items = {
            item["id"]: item
            for item in prior_g.get("expense_coverage", {}).get("items", [])
            if item.get("id") is not None
        }

        increased = []
        decreased = []
        added = []
        removed = []

        # Items in both: compare normalized_amount
        for item_id, cur in current_items.items():
            prior = prior_items.get(item_id)
            if prior is None:
                added.append({
                    "name": cur.get("name", ""),
                    "amount": cur.get("normalized_amount", 0),
                })
                continue

            cur_amt = cur.get("normalized_amount", 0)
            prior_amt = prior.get("normalized_amount", 0)
            delta = round(cur_amt - prior_amt, 2)

            if abs(delta) < 0.01:
                continue

            pct_delta = (
                round(delta / prior_amt * 100, 1) if prior_amt else 0
            )

            entry = {
                "name": cur.get("name", ""),
                "amount": cur_amt,
                "delta": delta,
                "pct_delta": pct_delta,
            }
            if delta > 0:
                increased.append(entry)
            else:
                decreased.append(entry)

        # Items only in prior: removed
        for item_id, prior in prior_items.items():
            if item_id not in current_items:
                removed.append({
                    "name": prior.get("name", ""),
                    "amount": prior.get("normalized_amount", 0),
                })

        changes = {}
        if increased:
            changes["increased"] = increased
        if decreased:
            changes["decreased"] = decreased
        if added:
            changes["added"] = added
        if removed:
            changes["removed"] = removed

        if changes:
            g["expense_changes"] = changes


# ---- Flexible scheduling helpers ----
