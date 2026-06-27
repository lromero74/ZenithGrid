"""Shared access-control helpers for report goals, schedules, and reports.

Used by reports_crud_router and reports_generation_router. Moved here from
reports_crud_router to stop generation_router from reaching into another
router's private helpers.
"""
import json
from typing import Tuple

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Account, Report, ReportGoal, ReportSchedule, User
from app.services.account_access import accessible_accounts_filter, manager_account_ids


async def get_accessible_goal(
    db: AsyncSession, goal_id: int, current_user_id: int,
) -> ReportGoal:
    """Fetch a goal the user can read: owner OR observer/manager of owner's account."""
    result = await db.execute(
        select(ReportGoal).where(
            ReportGoal.id == goal_id,
            or_(
                ReportGoal.user_id == current_user_id,
                ReportGoal.user_id.in_(
                    select(Account.user_id).where(
                        accessible_accounts_filter(current_user_id),
                        Account.user_id != current_user_id,
                    )
                ),
            ),
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


async def get_writable_goal(
    db: AsyncSession, goal_id: int, current_user: User,
) -> ReportGoal:
    """Fetch a goal the user can write to.

    Grants write access when the user owns the goal OR holds manager/owner
    membership on the goal's account.  Raises 404 if not readable at all,
    403 if readable but not writable.
    """
    goal = await get_accessible_goal(db, goal_id, current_user.id)
    if goal.user_id == current_user.id:
        return goal
    mgr_ids = await manager_account_ids(db, current_user.id)
    if goal.account_id not in mgr_ids:
        raise HTTPException(status_code=403, detail="Insufficient access to modify this goal")
    return goal


async def get_writable_schedule(
    db: AsyncSession, schedule_id: int, current_user: User,
) -> Tuple[ReportSchedule, int]:
    """Fetch a schedule the user can write to.

    Returns (schedule, effective_user_id) where effective_user_id is the
    schedule owner's user_id — pass it to service functions that accept
    user_id to look up records.

    Grants write access when the user owns the schedule OR holds manager/owner
    membership on the schedule's account.  Raises 404 / 403 accordingly.
    """
    result = await db.execute(
        select(ReportSchedule)
        .where(ReportSchedule.id == schedule_id)
        .options(selectinload(ReportSchedule.goal_links))
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if schedule.user_id == current_user.id:
        return schedule, current_user.id

    mgr_ids = await manager_account_ids(db, current_user.id)
    if schedule.account_id not in mgr_ids:
        raise HTTPException(status_code=403, detail="Insufficient access to schedule")

    return schedule, schedule.user_id


def report_to_dict(report: Report, include_html: bool = False) -> dict:
    """Serialize a Report row for JSON response; optionally include html_content."""
    ai_summary = report.ai_summary
    if ai_summary and isinstance(ai_summary, str):
        try:
            parsed = json.loads(ai_summary)
            if isinstance(parsed, dict) and ("simple" in parsed or "comfortable" in parsed):
                ai_summary = parsed
        except (json.JSONDecodeError, TypeError):
            pass

    schedule_name = None
    if report.schedule_id and hasattr(report, "schedule") and report.schedule:
        schedule_name = report.schedule.name

    result = {
        "id": report.id,
        "account_id": report.account_id,
        "schedule_id": report.schedule_id,
        "schedule_name": schedule_name,
        "period_start": report.period_start.isoformat() if report.period_start else None,
        "period_end": report.period_end.isoformat() if report.period_end else None,
        "periodicity": report.periodicity,
        "report_data": report.report_data,
        "ai_summary": ai_summary,
        "ai_provider_used": report.ai_provider_used,
        "delivery_status": report.delivery_status,
        "delivered_at": report.delivered_at.isoformat() if report.delivered_at else None,
        "delivery_recipients": report.delivery_recipients,
        "generation_status": getattr(report, "generation_status", "complete"),
        "generation_error": getattr(report, "generation_error", None),
        "has_pdf": report.pdf_content is not None,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }
    if include_html:
        result["html_content"] = report.html_content
    return result
