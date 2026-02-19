"""
Reports & Goals API Router

Endpoints for managing financial goals, report schedules,
and viewing/downloading generated reports.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
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
    target_type: str = Field(..., pattern="^(balance|profit|both)$")
    target_currency: str = Field("USD", pattern="^(USD|BTC)$")
    target_value: float = Field(..., gt=0)
    target_balance_value: Optional[float] = None
    target_profit_value: Optional[float] = None
    time_horizon_months: int = Field(..., ge=1, le=120)


class GoalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    target_type: Optional[str] = Field(None, pattern="^(balance|profit|both)$")
    target_currency: Optional[str] = Field(None, pattern="^(USD|BTC)$")
    target_value: Optional[float] = Field(None, gt=0)
    target_balance_value: Optional[float] = None
    target_profit_value: Optional[float] = None
    time_horizon_months: Optional[int] = Field(None, ge=1, le=120)
    is_active: Optional[bool] = None


class ScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    periodicity: str = Field(
        ..., pattern="^(daily|weekly|biweekly|monthly|quarterly|yearly)$"
    )
    account_id: Optional[int] = None
    recipients: List[str] = Field(default_factory=list)
    ai_provider: Optional[str] = Field(None, pattern="^(claude|openai|gemini)$")
    goal_ids: List[int] = Field(default_factory=list)
    is_enabled: bool = True


class ScheduleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    periodicity: Optional[str] = Field(
        None, pattern="^(daily|weekly|biweekly|monthly|quarterly|yearly)$"
    )
    account_id: Optional[int] = None
    recipients: Optional[List[str]] = None
    ai_provider: Optional[str] = None
    goal_ids: Optional[List[int]] = None
    is_enabled: Optional[bool] = None


class GenerateRequest(BaseModel):
    schedule_id: int


class PreviewRequest(BaseModel):
    schedule_id: int


# ----- Helper Functions -----

def _goal_to_dict(goal: ReportGoal) -> dict:
    return {
        "id": goal.id,
        "name": goal.name,
        "target_type": goal.target_type,
        "target_currency": goal.target_currency,
        "target_value": goal.target_value,
        "target_balance_value": goal.target_balance_value,
        "target_profit_value": goal.target_profit_value,
        "time_horizon_months": goal.time_horizon_months,
        "start_date": goal.start_date.isoformat() if goal.start_date else None,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "is_active": goal.is_active,
        "achieved_at": goal.achieved_at.isoformat() if goal.achieved_at else None,
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
    }


def _schedule_to_dict(schedule: ReportSchedule) -> dict:
    goal_ids = [link.goal_id for link in schedule.goal_links] if schedule.goal_links else []
    return {
        "id": schedule.id,
        "name": schedule.name,
        "periodicity": schedule.periodicity,
        "account_id": schedule.account_id,
        "is_enabled": schedule.is_enabled,
        "recipients": schedule.recipients or [],
        "ai_provider": schedule.ai_provider,
        "goal_ids": goal_ids,
        "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
        "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
        "created_at": schedule.created_at.isoformat() if schedule.created_at else None,
    }


def _report_to_dict(report: Report, include_html: bool = False) -> dict:
    result = {
        "id": report.id,
        "schedule_id": report.schedule_id,
        "period_start": report.period_start.isoformat() if report.period_start else None,
        "period_end": report.period_end.isoformat() if report.period_end else None,
        "periodicity": report.periodicity,
        "report_data": report.report_data,
        "ai_summary": report.ai_summary,
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


def _compute_next_run(periodicity: str, from_dt: Optional[datetime] = None) -> datetime:
    """Compute the next run time for a schedule."""
    now = from_dt or datetime.utcnow()

    if periodicity == "daily":
        # Next day at 06:00 UTC
        next_dt = (now + timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
    elif periodicity == "weekly":
        # Next Monday at 06:00 UTC
        days_ahead = 7 - now.weekday()  # Monday = 0
        if days_ahead == 0:
            days_ahead = 7
        next_dt = (now + timedelta(days=days_ahead)).replace(hour=6, minute=0, second=0, microsecond=0)
    elif periodicity == "biweekly":
        days_ahead = 14 - now.weekday()
        if days_ahead <= 0:
            days_ahead += 14
        next_dt = (now + timedelta(days=days_ahead)).replace(hour=6, minute=0, second=0, microsecond=0)
    elif periodicity == "monthly":
        # 1st of next month at 06:00 UTC
        if now.month == 12:
            next_dt = now.replace(year=now.year + 1, month=1, day=1, hour=6, minute=0, second=0, microsecond=0)
        else:
            next_dt = now.replace(month=now.month + 1, day=1, hour=6, minute=0, second=0, microsecond=0)
    elif periodicity == "quarterly":
        # 1st of next quarter at 06:00 UTC
        quarter_months = [1, 4, 7, 10]
        next_q = None
        for m in quarter_months:
            if m > now.month:
                next_q = m
                break
        if next_q is None:
            next_q = 1
            next_dt = now.replace(year=now.year + 1, month=next_q, day=1, hour=6, minute=0, second=0, microsecond=0)
        else:
            next_dt = now.replace(month=next_q, day=1, hour=6, minute=0, second=0, microsecond=0)
    elif periodicity == "yearly":
        # Jan 1 next year at 06:00 UTC
        next_dt = now.replace(year=now.year + 1, month=1, day=1, hour=6, minute=0, second=0, microsecond=0)
    else:
        next_dt = now + timedelta(days=7)

    return next_dt


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
    target_date = start_date + relativedelta(months=body.time_horizon_months)

    goal = ReportGoal(
        user_id=current_user.id,
        name=body.name,
        target_type=body.target_type,
        target_currency=body.target_currency,
        target_value=body.target_value,
        target_balance_value=body.target_balance_value,
        target_profit_value=body.target_profit_value,
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

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(goal, key, value)

    # Recompute target_date if horizon changed
    if "time_horizon_months" in update_data:
        from dateutil.relativedelta import relativedelta
        goal.target_date = goal.start_date + relativedelta(months=goal.time_horizon_months)

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

    next_run = _compute_next_run(body.periodicity)
    schedule = ReportSchedule(
        user_id=current_user.id,
        account_id=body.account_id,
        name=body.name,
        periodicity=body.periodicity,
        is_enabled=body.is_enabled,
        recipients=body.recipients,
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

    update_data = body.model_dump(exclude_unset=True)
    goal_ids = update_data.pop("goal_ids", None)

    for key, value in update_data.items():
        setattr(schedule, key, value)

    # Recompute next_run if periodicity changed
    if "periodicity" in update_data:
        schedule.next_run_at = _compute_next_run(schedule.periodicity)

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

    # Generate the report
    from app.services.report_scheduler import generate_report_for_schedule
    report = await generate_report_for_schedule(db, schedule, current_user)

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
