"""
Reports & Goals API Router

Endpoints for managing financial goals, report schedules,
and viewing/downloading generated reports.
"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import (
    Report,
    ReportGoal,
    ReportSchedule,
    ReportScheduleGoal,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


# ----- Pydantic Schemas -----

class GoalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    target_type: str = Field(..., pattern="^(balance|profit|both|income)$")
    target_currency: str = Field("USD", pattern="^(USD|BTC)$")
    target_value: float = Field(..., gt=0)
    target_balance_value: Optional[float] = None
    target_profit_value: Optional[float] = None
    income_period: Optional[str] = Field(
        None, pattern="^(daily|weekly|monthly|yearly)$"
    )
    lookback_days: Optional[int] = Field(None, ge=7, le=365)
    time_horizon_months: int = Field(..., ge=1, le=120)
    target_date: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_income_fields(self):
        if self.target_type == "income" and not self.income_period:
            raise ValueError("income_period is required when target_type is 'income'")
        return self


class GoalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    target_type: Optional[str] = Field(None, pattern="^(balance|profit|both|income)$")
    target_currency: Optional[str] = Field(None, pattern="^(USD|BTC)$")
    target_value: Optional[float] = Field(None, gt=0)
    target_balance_value: Optional[float] = None
    target_profit_value: Optional[float] = None
    income_period: Optional[str] = Field(
        None, pattern="^(daily|weekly|monthly|yearly)$"
    )
    lookback_days: Optional[int] = Field(None, ge=7, le=365)
    time_horizon_months: Optional[int] = Field(None, ge=1, le=120)
    target_date: Optional[datetime] = None
    is_active: Optional[bool] = None


class RecipientItem(BaseModel):
    email: str = Field(..., min_length=5)
    level: str = Field(
        "comfortable",
        pattern="^(beginner|comfortable|experienced)$",
    )


class ScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    # New flexible schedule fields (primary)
    schedule_type: str = Field(
        ..., pattern="^(daily|weekly|monthly|quarterly|yearly)$"
    )
    schedule_days: Optional[List[int]] = None
    quarter_start_month: Optional[int] = Field(None, ge=1, le=12)
    period_window: str = Field(
        "full_prior",
        pattern="^(full_prior|wtd|mtd|qtd|ytd|trailing)$",
    )
    lookback_value: Optional[int] = Field(None, ge=1)
    lookback_unit: Optional[str] = Field(
        None, pattern="^(days|weeks|months|years)$"
    )
    # Legacy periodicity — auto-generated if not provided
    periodicity: Optional[str] = None
    account_id: Optional[int] = None
    recipients: List[RecipientItem] = Field(default_factory=list)
    ai_provider: Optional[str] = Field(
        None, pattern="^(claude|openai|gemini)$"
    )
    goal_ids: List[int] = Field(default_factory=list)
    is_enabled: bool = True

    @model_validator(mode="after")
    def validate_schedule_fields(self):
        if (
            self.schedule_type == "quarterly"
            and self.quarter_start_month is None
        ):
            self.quarter_start_month = 1
        if self.period_window == "trailing":
            if not self.lookback_value:
                raise ValueError(
                    "lookback_value is required when "
                    "period_window is 'trailing'"
                )
            if not self.lookback_unit:
                self.lookback_unit = "days"
        return self


class ScheduleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    schedule_type: Optional[str] = Field(
        None, pattern="^(daily|weekly|monthly|quarterly|yearly)$"
    )
    schedule_days: Optional[List[int]] = None
    quarter_start_month: Optional[int] = Field(None, ge=1, le=12)
    period_window: Optional[str] = Field(
        None,
        pattern="^(full_prior|wtd|mtd|qtd|ytd|trailing)$",
    )
    lookback_value: Optional[int] = Field(None, ge=1)
    lookback_unit: Optional[str] = Field(
        None, pattern="^(days|weeks|months|years)$"
    )
    periodicity: Optional[str] = None
    account_id: Optional[int] = None
    recipients: Optional[List[RecipientItem]] = None
    ai_provider: Optional[str] = None
    goal_ids: Optional[List[int]] = None
    is_enabled: Optional[bool] = None


class GenerateRequest(BaseModel):
    schedule_id: int


class PreviewRequest(BaseModel):
    schedule_id: int


# ----- Helper Functions -----

def _normalize_recipient_for_api(item) -> dict:
    """
    Normalize a stored recipient to object format for API responses.

    Handles both new object format and legacy plain string format.
    """
    if isinstance(item, dict) and "email" in item:
        return {
            "email": item["email"],
            "level": item.get("level", "comfortable"),
        }
    if isinstance(item, str):
        return {"email": item, "level": "comfortable"}
    return {"email": str(item), "level": "comfortable"}


def _goal_to_dict(goal: ReportGoal) -> dict:
    return {
        "id": goal.id,
        "name": goal.name,
        "target_type": goal.target_type,
        "target_currency": goal.target_currency,
        "target_value": goal.target_value,
        "target_balance_value": goal.target_balance_value,
        "target_profit_value": goal.target_profit_value,
        "income_period": goal.income_period,
        "lookback_days": goal.lookback_days,
        "time_horizon_months": goal.time_horizon_months,
        "start_date": goal.start_date.isoformat() if goal.start_date else None,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "is_active": goal.is_active,
        "achieved_at": goal.achieved_at.isoformat() if goal.achieved_at else None,
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
    }


def _schedule_to_dict(schedule: ReportSchedule) -> dict:
    goal_ids = (
        [link.goal_id for link in schedule.goal_links]
        if schedule.goal_links else []
    )
    # Normalize recipients to object format
    raw_recipients = schedule.recipients or []
    recipients = [_normalize_recipient_for_api(r) for r in raw_recipients]
    # Parse schedule_days JSON to list for API response
    schedule_days = None
    if schedule.schedule_days:
        try:
            schedule_days = json.loads(schedule.schedule_days)
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "id": schedule.id,
        "name": schedule.name,
        "periodicity": schedule.periodicity,
        "schedule_type": schedule.schedule_type,
        "schedule_days": schedule_days,
        "quarter_start_month": schedule.quarter_start_month,
        "period_window": schedule.period_window or "full_prior",
        "lookback_value": schedule.lookback_value,
        "lookback_unit": schedule.lookback_unit,
        "account_id": schedule.account_id,
        "is_enabled": schedule.is_enabled,
        "recipients": recipients,
        "ai_provider": schedule.ai_provider,
        "goal_ids": goal_ids,
        "last_run_at": (
            schedule.last_run_at.isoformat()
            if schedule.last_run_at else None
        ),
        "next_run_at": (
            schedule.next_run_at.isoformat()
            if schedule.next_run_at else None
        ),
        "created_at": (
            schedule.created_at.isoformat()
            if schedule.created_at else None
        ),
    }


def _report_to_dict(report: Report, include_html: bool = False) -> dict:
    # Parse ai_summary — return as dict if it's tiered JSON, else as-is
    ai_summary = report.ai_summary
    if ai_summary and isinstance(ai_summary, str):
        try:
            parsed = json.loads(ai_summary)
            if isinstance(parsed, dict) and "comfortable" in parsed:
                ai_summary = parsed
        except (json.JSONDecodeError, TypeError):
            pass

    result = {
        "id": report.id,
        "schedule_id": report.schedule_id,
        "period_start": report.period_start.isoformat() if report.period_start else None,
        "period_end": report.period_end.isoformat() if report.period_end else None,
        "periodicity": report.periodicity,
        "report_data": report.report_data,
        "ai_summary": ai_summary,
        "ai_provider_used": report.ai_provider_used,
        "delivery_status": report.delivery_status,
        "delivered_at": report.delivered_at.isoformat() if report.delivered_at else None,
        "delivery_recipients": report.delivery_recipients,
        "has_pdf": report.pdf_content is not None,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }
    if include_html:
        result["html_content"] = report.html_content
    return result


def _compute_next_run_for_new_schedule(body) -> datetime:
    """Compute the first next_run_at for a newly created schedule."""
    from app.services.report_scheduler import compute_next_run_flexible

    # Build a lightweight object with the schedule fields
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


# ----- Goals CRUD -----

@router.get("/goals")
async def list_goals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """List all goals for the current user."""
    result = await db.execute(
        select(ReportGoal)
        .where(ReportGoal.user_id == current_user.id)
        .order_by(ReportGoal.created_at.desc())
    )
    goals = result.scalars().all()
    return [_goal_to_dict(g) for g in goals]


@router.post("/goals")
async def create_goal(
    body: GoalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Create a new financial goal."""
    from dateutil.relativedelta import relativedelta

    start_date = datetime.utcnow()

    if body.target_date:
        # Custom date provided — use it, back-compute horizon
        if body.target_date <= start_date:
            raise HTTPException(
                status_code=400, detail="target_date must be in the future"
            )
        target_date = body.target_date
        delta = relativedelta(target_date, start_date)
        body.time_horizon_months = max(delta.years * 12 + delta.months, 1)
    else:
        target_date = start_date + relativedelta(months=body.time_horizon_months)

    goal = ReportGoal(
        user_id=current_user.id,
        name=body.name,
        target_type=body.target_type,
        target_currency=body.target_currency,
        target_value=body.target_value,
        target_balance_value=body.target_balance_value,
        target_profit_value=body.target_profit_value,
        income_period=body.income_period,
        lookback_days=body.lookback_days,
        time_horizon_months=body.time_horizon_months,
        start_date=start_date,
        target_date=target_date,
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    return _goal_to_dict(goal)


@router.put("/goals/{goal_id}")
async def update_goal(
    goal_id: int,
    body: GoalUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Update an existing goal."""
    result = await db.execute(
        select(ReportGoal).where(
            ReportGoal.id == goal_id,
            ReportGoal.user_id == current_user.id,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    from dateutil.relativedelta import relativedelta

    update_data = body.model_dump(exclude_unset=True)

    # Handle target_date vs time_horizon_months
    custom_target_date = update_data.pop("target_date", None)
    if custom_target_date is not None:
        if custom_target_date <= datetime.utcnow():
            raise HTTPException(
                status_code=400, detail="target_date must be in the future"
            )
        # Set target_date directly, back-compute horizon
        goal.target_date = custom_target_date
        delta = relativedelta(custom_target_date, goal.start_date)
        goal.time_horizon_months = max(delta.years * 12 + delta.months, 1)
        update_data.pop("time_horizon_months", None)

    for key, value in update_data.items():
        setattr(goal, key, value)

    # Recompute target_date if horizon changed (and no custom date)
    if custom_target_date is None and "time_horizon_months" in update_data:
        goal.target_date = goal.start_date + relativedelta(
            months=goal.time_horizon_months
        )

    goal.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(goal)
    return _goal_to_dict(goal)


@router.delete("/goals/{goal_id}")
async def delete_goal(
    goal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Delete a goal."""
    result = await db.execute(
        select(ReportGoal).where(
            ReportGoal.id == goal_id,
            ReportGoal.user_id == current_user.id,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    await db.delete(goal)
    await db.commit()
    return {"detail": "Goal deleted"}


# ----- Schedules CRUD -----

@router.get("/schedules")
async def list_schedules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """List all report schedules for the current user."""
    result = await db.execute(
        select(ReportSchedule)
        .where(ReportSchedule.user_id == current_user.id)
        .options(selectinload(ReportSchedule.goal_links))
        .order_by(ReportSchedule.created_at.desc())
    )
    schedules = result.scalars().all()
    return [_schedule_to_dict(s) for s in schedules]


@router.post("/schedules")
async def create_schedule(
    body: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Create a new report schedule."""
    # Validate goal IDs belong to this user
    if body.goal_ids:
        result = await db.execute(
            select(ReportGoal.id).where(
                ReportGoal.id.in_(body.goal_ids),
                ReportGoal.user_id == current_user.id,
            )
        )
        valid_ids = {row[0] for row in result.fetchall()}
        invalid = set(body.goal_ids) - valid_ids
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid goal IDs: {list(invalid)}",
            )

    from app.services.report_scheduler import build_periodicity_label

    next_run = _compute_next_run_for_new_schedule(body)
    # Serialize recipients to dicts for JSON storage
    recipients_data = [r.model_dump() for r in body.recipients]
    # Build human-readable periodicity label
    schedule_days_json = (
        json.dumps(body.schedule_days) if body.schedule_days else None
    )
    periodicity_label = body.periodicity or build_periodicity_label(
        body.schedule_type,
        schedule_days_json,
        body.quarter_start_month,
        body.period_window,
        body.lookback_value,
        body.lookback_unit,
    )
    schedule = ReportSchedule(
        user_id=current_user.id,
        account_id=body.account_id,
        name=body.name,
        periodicity=periodicity_label,
        schedule_type=body.schedule_type,
        schedule_days=schedule_days_json,
        quarter_start_month=body.quarter_start_month,
        period_window=body.period_window,
        lookback_value=body.lookback_value,
        lookback_unit=body.lookback_unit,
        is_enabled=body.is_enabled,
        recipients=recipients_data,
        ai_provider=body.ai_provider,
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
    schedule = result.scalar_one()
    return _schedule_to_dict(schedule)


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    body: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Update an existing report schedule."""
    result = await db.execute(
        select(ReportSchedule)
        .where(
            ReportSchedule.id == schedule_id,
            ReportSchedule.user_id == current_user.id,
        )
        .options(selectinload(ReportSchedule.goal_links))
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    from app.services.report_scheduler import (
        build_periodicity_label,
        compute_next_run_flexible,
    )

    update_data = body.model_dump(exclude_unset=True)
    goal_ids = update_data.pop("goal_ids", None)

    # Serialize recipients if present
    if "recipients" in update_data and update_data["recipients"] is not None:
        update_data["recipients"] = [
            r.model_dump() if hasattr(r, "model_dump") else r
            for r in update_data["recipients"]
        ]

    # Convert schedule_days list to JSON string for DB storage
    if "schedule_days" in update_data:
        sd = update_data["schedule_days"]
        update_data["schedule_days"] = (
            json.dumps(sd) if sd is not None else None
        )

    # Track whether schedule config changed (for recompute)
    schedule_fields = {
        "schedule_type", "schedule_days", "quarter_start_month",
        "period_window", "lookback_value", "lookback_unit",
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
                    ReportGoal.user_id == current_user.id,
                )
            )
            valid_ids = {row[0] for row in result.fetchall()}
            invalid = set(goal_ids) - valid_ids
            if invalid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid goal IDs: {list(invalid)}",
                )

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
    schedule = result.scalar_one()
    return _schedule_to_dict(schedule)


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Delete a report schedule."""
    result = await db.execute(
        select(ReportSchedule).where(
            ReportSchedule.id == schedule_id,
            ReportSchedule.user_id == current_user.id,
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    await db.delete(schedule)
    await db.commit()
    return {"detail": "Schedule deleted"}


# ----- Reports -----

@router.get("/history")
async def list_reports(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    schedule_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """List generated reports (paginated)."""
    filters = [Report.user_id == current_user.id]
    if schedule_id:
        filters.append(Report.schedule_id == schedule_id)

    # Get total count
    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count(Report.id)).where(and_(*filters))
    )
    total = count_result.scalar()

    # Get page
    result = await db.execute(
        select(Report)
        .where(and_(*filters))
        .order_by(Report.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    reports = result.scalars().all()

    return {
        "total": total,
        "reports": [_report_to_dict(r) for r in reports],
    }


@router.get("/{report_id}")
async def get_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get a single report with HTML content for in-app viewing."""
    result = await db.execute(
        select(Report).where(
            Report.id == report_id,
            Report.user_id == current_user.id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return _report_to_dict(report, include_html=True)


@router.delete("/{report_id}")
async def delete_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Delete a report from history."""
    result = await db.execute(
        select(Report).where(
            Report.id == report_id,
            Report.user_id == current_user.id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    await db.delete(report)
    await db.commit()
    return {"detail": "Report deleted"}


@router.get("/{report_id}/pdf")
async def download_report_pdf(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download a report as PDF."""
    result = await db.execute(
        select(Report).where(
            Report.id == report_id,
            Report.user_id == current_user.id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if not report.pdf_content:
        raise HTTPException(status_code=404, detail="PDF not available for this report")

    period_str = ""
    if report.period_end:
        period_str = report.period_end.strftime("%Y-%m-%d")
    filename = f"report_{period_str}_{report.periodicity}.pdf"

    return Response(
        content=report.pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/generate")
async def generate_report(
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Manually trigger report generation for a schedule."""
    result = await db.execute(
        select(ReportSchedule)
        .where(
            ReportSchedule.id == body.schedule_id,
            ReportSchedule.user_id == current_user.id,
        )
        .options(selectinload(ReportSchedule.goal_links))
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Generate the report (ad-hoc — don't advance schedule timing)
    from app.services.report_scheduler import generate_report_for_schedule
    report = await generate_report_for_schedule(
        db, schedule, current_user, advance_schedule=False,
    )

    return _report_to_dict(report, include_html=True)


@router.post("/preview")
async def preview_report(
    body: PreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Preview a report without saving or emailing."""
    result = await db.execute(
        select(ReportSchedule)
        .where(
            ReportSchedule.id == body.schedule_id,
            ReportSchedule.user_id == current_user.id,
        )
        .options(selectinload(ReportSchedule.goal_links))
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    from app.services.report_scheduler import generate_report_for_schedule
    report = await generate_report_for_schedule(
        db, schedule, current_user, save=False, send_email=False
    )

    return _report_to_dict(report, include_html=True)
