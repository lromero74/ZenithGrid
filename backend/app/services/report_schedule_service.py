"""
Report Schedule Service

Business logic for creating and updating report schedules.
Separated from the router to keep router endpoints thin.
"""

import json
import logging
from datetime import datetime

from app.exceptions import NotFoundError, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ReportGoal, ReportSchedule, ReportScheduleGoal
from app.services.report_scheduler import build_periodicity_label, compute_next_run_flexible

logger = logging.getLogger(__name__)


def compute_next_run_for_new_schedule(body) -> datetime:
    """Compute the first next_run_at for a newly created schedule."""
    class _Sched:
        pass

    sched = _Sched()
    sched.schedule_type = body.schedule_type
    sched.schedule_days = (
        json.dumps(body.schedule_days) if body.schedule_days else None
    )
    sched.quarter_start_month = body.quarter_start_month
    sched.period_window = body.period_window
    sched.lookback_value = body.lookback_value
    sched.lookback_unit = body.lookback_unit

    return compute_next_run_flexible(sched, datetime.utcnow())


async def create_schedule_record(
    db: AsyncSession,
    user_id: int,
    body,
) -> ReportSchedule:
    """
    Create a new report schedule with goal links.

    Validates goal IDs, computes next_run_at and periodicity label,
    creates the schedule record and goal links, and returns the
    fully-loaded schedule.
    """
    # Validate goal IDs belong to this user
    if body.goal_ids:
        result = await db.execute(
            select(ReportGoal.id).where(
                ReportGoal.id.in_(body.goal_ids),
                ReportGoal.user_id == user_id,
            )
        )
        valid_ids = {row[0] for row in result.fetchall()}
        invalid = set(body.goal_ids) - valid_ids
        if invalid:
            raise ValidationError(f"Invalid goal IDs: {list(invalid)}")

    next_run = compute_next_run_for_new_schedule(body)
    # Serialize recipients as dicts with email + color_scheme
    recipients_data = [
        {"email": r.email, "color_scheme": r.color_scheme}
        for r in body.recipients
    ]
    # Build human-readable periodicity label
    schedule_days_json = (
        json.dumps(body.schedule_days) if body.schedule_days else None
    )
    force_standard_json = (
        json.dumps(body.force_standard_days)
        if body.force_standard_days else None
    )
    periodicity_label = body.periodicity or build_periodicity_label(
        body.schedule_type,
        schedule_days_json,
        body.quarter_start_month,
        body.period_window,
        body.lookback_value,
        body.lookback_unit,
        force_standard_json,
    )
    schedule = ReportSchedule(
        user_id=user_id,
        account_id=body.account_id,
        name=body.name,
        periodicity=periodicity_label,
        schedule_type=body.schedule_type,
        schedule_days=schedule_days_json,
        quarter_start_month=body.quarter_start_month,
        period_window=body.period_window,
        lookback_value=body.lookback_value,
        lookback_unit=body.lookback_unit,
        force_standard_days=force_standard_json,
        is_enabled=body.is_enabled,
        show_expense_lookahead=body.show_expense_lookahead,
        chart_horizon=getattr(body, "chart_horizon", "auto") or "auto",
        chart_lookahead_multiplier=getattr(body, "chart_lookahead_multiplier", 1.0) or 1.0,
        show_minimap=getattr(body, "show_minimap", True) if getattr(body, "show_minimap", True) is not None else True,
        recipients=recipients_data,
        ai_provider=body.ai_provider,
        generate_ai_summary=body.generate_ai_summary,
        next_run_at=next_run,
    )
    db.add(schedule)
    await db.flush()  # Get the schedule.id

    # Create goal links
    for gid in body.goal_ids:
        db.add(ReportScheduleGoal(schedule_id=schedule.id, goal_id=gid))

    await db.commit()

    # Refresh with goal_links loaded
    result = await db.execute(
        select(ReportSchedule)
        .where(ReportSchedule.id == schedule.id)
        .options(selectinload(ReportSchedule.goal_links))
    )
    return result.scalar_one()


async def update_schedule_record(
    db: AsyncSession,
    user_id: int,
    schedule_id: int,
    body,
) -> ReportSchedule:
    """
    Update an existing report schedule.

    Handles field serialization, periodicity recomputation,
    goal link updates, and returns the fully-loaded schedule.
    """
    result = await db.execute(
        select(ReportSchedule)
        .where(
            ReportSchedule.id == schedule_id,
            ReportSchedule.user_id == user_id,
        )
        .options(selectinload(ReportSchedule.goal_links))
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise NotFoundError("Schedule not found")

    update_data = body.model_dump(exclude_unset=True)
    goal_ids = update_data.pop("goal_ids", None)

    # Serialize recipients as dicts with email + color_scheme
    # Note: model_dump() converts RecipientItem to dicts, so handle both
    if "recipients" in update_data and update_data["recipients"] is not None:
        serialized = []
        for r in update_data["recipients"]:
            if isinstance(r, dict):
                serialized.append({
                    "email": r["email"],
                    "color_scheme": r.get("color_scheme", "dark"),
                })
            elif hasattr(r, "email"):
                serialized.append({
                    "email": r.email,
                    "color_scheme": r.color_scheme,
                })
            else:
                serialized.append({"email": str(r), "color_scheme": "dark"})
        update_data["recipients"] = serialized

    # Convert list fields to JSON strings for DB storage
    if "schedule_days" in update_data:
        sd = update_data["schedule_days"]
        update_data["schedule_days"] = (
            json.dumps(sd) if sd is not None else None
        )
    if "force_standard_days" in update_data:
        fsd = update_data["force_standard_days"]
        update_data["force_standard_days"] = (
            json.dumps(fsd) if fsd is not None else None
        )

    # Track whether schedule config changed (for recompute)
    schedule_fields = {
        "schedule_type", "schedule_days", "quarter_start_month",
        "period_window", "lookback_value", "lookback_unit",
        "force_standard_days",
    }
    schedule_changed = bool(schedule_fields & set(update_data.keys()))

    # Don't write a user-supplied periodicity — it's auto-generated
    update_data.pop("periodicity", None)

    for key, value in update_data.items():
        setattr(schedule, key, value)

    # Recompute next_run_at and periodicity label if schedule changed
    if schedule_changed:
        schedule.periodicity = build_periodicity_label(
            schedule.schedule_type,
            schedule.schedule_days,
            schedule.quarter_start_month,
            schedule.period_window or "full_prior",
            schedule.lookback_value,
            schedule.lookback_unit,
            schedule.force_standard_days,
        )
        schedule.next_run_at = compute_next_run_flexible(
            schedule, datetime.utcnow()
        )

    # Update goal links if provided
    if goal_ids is not None:
        # Validate goal IDs
        if goal_ids:
            result = await db.execute(
                select(ReportGoal.id).where(
                    ReportGoal.id.in_(goal_ids),
                    ReportGoal.user_id == user_id,
                )
            )
            valid_ids = {row[0] for row in result.fetchall()}
            invalid = set(goal_ids) - valid_ids
            if invalid:
                raise ValidationError(f"Invalid goal IDs: {list(invalid)}")

        # Remove existing links
        await db.execute(
            delete(ReportScheduleGoal).where(
                ReportScheduleGoal.schedule_id == schedule.id
            )
        )
        # Add new links
        for gid in goal_ids:
            db.add(ReportScheduleGoal(schedule_id=schedule.id, goal_id=gid))

    schedule.updated_at = datetime.utcnow()
    await db.commit()

    # Refresh with goal_links
    result = await db.execute(
        select(ReportSchedule)
        .where(ReportSchedule.id == schedule.id)
        .options(selectinload(ReportSchedule.goal_links))
    )
    return result.scalar_one()
