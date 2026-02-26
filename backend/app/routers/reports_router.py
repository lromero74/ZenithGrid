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
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import (
    ExpenseItem,
    GoalProgressSnapshot,
    Report,
    ReportGoal,
    ReportSchedule,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


# ----- Pydantic Schemas -----

class GoalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    target_type: str = Field(..., pattern="^(balance|profit|both|income|expenses)$")
    target_currency: str = Field("USD", pattern="^(USD|BTC)$")
    target_value: float = Field(..., gt=0)
    target_balance_value: Optional[float] = None
    target_profit_value: Optional[float] = None
    income_period: Optional[str] = Field(
        None, pattern="^(daily|weekly|monthly|yearly)$"
    )
    expense_period: Optional[str] = Field(
        None, pattern="^(weekly|monthly|quarterly|yearly)$"
    )
    tax_withholding_pct: Optional[float] = Field(None, ge=0, le=100)
    expense_sort_mode: Optional[str] = Field(
        None, pattern="^(amount_asc|amount_desc|custom)$"
    )
    time_horizon_months: int = Field(..., ge=1, le=120)
    target_date: Optional[datetime] = None
    account_id: Optional[int] = None
    chart_horizon: Optional[str] = Field("auto", pattern=r"^(auto|elapsed|full|[0-9]+)$")
    show_minimap: Optional[bool] = True
    minimap_threshold_days: Optional[int] = Field(90, ge=7, le=3650)

    @model_validator(mode="after")
    def validate_goal_fields(self):
        if self.target_type == "income" and not self.income_period:
            raise ValueError("income_period is required when target_type is 'income'")
        if self.target_type == "expenses" and not self.expense_period:
            raise ValueError("expense_period is required when target_type is 'expenses'")
        return self


class GoalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    target_type: Optional[str] = Field(None, pattern="^(balance|profit|both|income|expenses)$")
    target_currency: Optional[str] = Field(None, pattern="^(USD|BTC)$")
    target_value: Optional[float] = Field(None, gt=0)
    target_balance_value: Optional[float] = None
    target_profit_value: Optional[float] = None
    income_period: Optional[str] = Field(
        None, pattern="^(daily|weekly|monthly|yearly)$"
    )
    expense_period: Optional[str] = Field(
        None, pattern="^(weekly|monthly|quarterly|yearly)$"
    )
    tax_withholding_pct: Optional[float] = Field(None, ge=0, le=100)
    expense_sort_mode: Optional[str] = Field(
        None, pattern="^(amount_asc|amount_desc|custom)$"
    )
    time_horizon_months: Optional[int] = Field(None, ge=1, le=120)
    target_date: Optional[datetime] = None
    is_active: Optional[bool] = None
    chart_horizon: Optional[str] = Field(None, pattern=r"^(auto|elapsed|full|[0-9]+)$")
    show_minimap: Optional[bool] = None
    minimap_threshold_days: Optional[int] = Field(None, ge=7, le=3650)


class RecipientItem(BaseModel):
    email: str = Field(..., min_length=5)
    color_scheme: str = Field(
        "dark", pattern="^(dark|clean)$",
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
    force_standard_days: Optional[List[int]] = None
    # Legacy periodicity — auto-generated if not provided
    periodicity: Optional[str] = None
    account_id: Optional[int] = None
    recipients: List[RecipientItem] = Field(default_factory=list)
    ai_provider: Optional[str] = Field(
        None, pattern="^(claude|openai|gemini)$"
    )
    generate_ai_summary: bool = True
    goal_ids: List[int] = Field(default_factory=list)
    is_enabled: bool = True
    show_expense_lookahead: bool = True
    chart_horizon: Optional[str] = Field("auto", pattern=r"^(auto|elapsed|full|[0-9]+)$")
    chart_lookahead_multiplier: Optional[float] = Field(1.0, ge=0.1, le=10.0)

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
    force_standard_days: Optional[List[int]] = None
    periodicity: Optional[str] = None
    account_id: Optional[int] = None
    recipients: Optional[List[RecipientItem]] = None
    ai_provider: Optional[str] = None
    generate_ai_summary: Optional[bool] = None
    goal_ids: Optional[List[int]] = None
    is_enabled: Optional[bool] = None
    show_expense_lookahead: Optional[bool] = None
    chart_horizon: Optional[str] = Field(None, pattern=r"^(auto|elapsed|full|[0-9]+)$")
    chart_lookahead_multiplier: Optional[float] = Field(None, ge=0.1, le=10.0)


class GenerateRequest(BaseModel):
    schedule_id: int


class PreviewRequest(BaseModel):
    schedule_id: int


class ExpenseItemCreate(BaseModel):
    category: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    amount: float = Field(..., ge=0)
    frequency: str = Field(
        ...,
        pattern="^(daily|weekly|biweekly|every_n_days|semi_monthly|monthly|quarterly|semi_annual|yearly)$",
    )
    frequency_n: Optional[int] = Field(None, ge=1)
    frequency_anchor: Optional[str] = None
    due_day: Optional[int] = Field(None, ge=-1, le=31)
    due_month: Optional[int] = Field(None, ge=1, le=12)
    login_url: Optional[str] = Field(None, max_length=500)
    amount_mode: Optional[str] = Field(
        "fixed", pattern="^(fixed|percent_of_income)$"
    )
    percent_of_income: Optional[float] = Field(None, gt=0, le=100)
    percent_basis: Optional[str] = Field(
        None, pattern="^(pre_tax|post_tax)$"
    )

    @model_validator(mode="after")
    def validate_frequency_n(self):
        if self.frequency == "every_n_days" and not self.frequency_n:
            raise ValueError("frequency_n is required when frequency is 'every_n_days'")
        if self.due_day is not None and self.due_day == 0:
            raise ValueError("due_day must be -1 (last day) or 1-31")
        if self.amount_mode == "percent_of_income" and not self.percent_of_income:
            raise ValueError(
                "percent_of_income is required when amount_mode is 'percent_of_income'"
            )
        return self


class ExpenseItemUpdate(BaseModel):
    category: Optional[str] = Field(None, min_length=1, max_length=100)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    amount: Optional[float] = Field(None, ge=0)
    frequency: Optional[str] = Field(
        None,
        pattern="^(daily|weekly|biweekly|every_n_days|semi_monthly|monthly|quarterly|semi_annual|yearly)$",
    )
    frequency_n: Optional[int] = Field(None, ge=1)
    frequency_anchor: Optional[str] = None
    due_day: Optional[int] = Field(None, ge=-1, le=31)
    due_month: Optional[int] = Field(None, ge=1, le=12)
    login_url: Optional[str] = Field(None, max_length=500)
    amount_mode: Optional[str] = Field(
        None, pattern="^(fixed|percent_of_income)$"
    )
    percent_of_income: Optional[float] = Field(None, gt=0, le=100)
    percent_basis: Optional[str] = Field(
        None, pattern="^(pre_tax|post_tax)$"
    )
    is_active: Optional[bool] = None


# ----- Helper Functions -----

def _normalize_recipient_for_api(item) -> dict:
    """
    Normalize a stored recipient to {email, color_scheme} dict.

    Handles legacy plain string format and old object format.
    """
    if isinstance(item, dict) and "email" in item:
        return {
            "email": item["email"],
            "color_scheme": item.get("color_scheme", "dark"),
        }
    return {"email": str(item), "color_scheme": "dark"}


def _goal_to_dict(goal: ReportGoal) -> dict:
    d = {
        "id": goal.id,
        "account_id": goal.account_id,
        "name": goal.name,
        "target_type": goal.target_type,
        "target_currency": goal.target_currency,
        "target_value": goal.target_value,
        "target_balance_value": goal.target_balance_value,
        "target_profit_value": goal.target_profit_value,
        "income_period": goal.income_period,
        "expense_period": goal.expense_period,
        "tax_withholding_pct": goal.tax_withholding_pct or 0,
        "expense_sort_mode": goal.expense_sort_mode or "amount_asc",
        "time_horizon_months": goal.time_horizon_months,
        "start_date": goal.start_date.isoformat() if goal.start_date else None,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "is_active": goal.is_active,
        "achieved_at": goal.achieved_at.isoformat() if goal.achieved_at else None,
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
        "chart_horizon": goal.chart_horizon or "auto",
        "show_minimap": goal.show_minimap if goal.show_minimap is not None else True,
        "minimap_threshold_days": goal.minimap_threshold_days or 90,
    }
    # Include expense item count (only if relationship is already loaded)
    if goal.target_type == "expenses":
        state = sa_inspect(goal)
        if "expense_items" not in state.unloaded:
            items = goal.expense_items
            d["expense_item_count"] = len(items) if items else 0
        else:
            d["expense_item_count"] = 0
    else:
        d["expense_item_count"] = 0
    return d


def _parse_json_list(raw: Optional[str]) -> Optional[list]:
    """Parse a JSON string to a list, or return None."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _schedule_to_dict(schedule: ReportSchedule) -> dict:
    goal_ids = (
        [link.goal_id for link in schedule.goal_links]
        if schedule.goal_links else []
    )
    # Normalize recipients to object format
    raw_recipients = schedule.recipients or []
    recipients = [_normalize_recipient_for_api(r) for r in raw_recipients]
    schedule_days = _parse_json_list(schedule.schedule_days)
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
        "force_standard_days": _parse_json_list(
            schedule.force_standard_days
        ),
        "account_id": schedule.account_id,
        "is_enabled": schedule.is_enabled,
        "recipients": recipients,
        "ai_provider": schedule.ai_provider,
        "generate_ai_summary": (
            schedule.generate_ai_summary
            if schedule.generate_ai_summary is not None else True
        ),
        "show_expense_lookahead": (
            schedule.show_expense_lookahead
            if schedule.show_expense_lookahead is not None else True
        ),
        "chart_horizon": schedule.chart_horizon or "auto",
        "chart_lookahead_multiplier": (
            schedule.chart_lookahead_multiplier
            if schedule.chart_lookahead_multiplier is not None else 1.0
        ),
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
        "has_pdf": report.pdf_content is not None,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }
    if include_html:
        result["html_content"] = report.html_content
    return result


# ----- Goals CRUD -----

@router.get("/goals")
async def list_goals(
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """List all goals for the current user, optionally filtered by account."""
    filters = [ReportGoal.user_id == current_user.id]
    if account_id:
        filters.append(ReportGoal.account_id == account_id)
    result = await db.execute(
        select(ReportGoal)
        .where(and_(*filters))
        .options(selectinload(ReportGoal.expense_items))
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

    # For expenses goals, target_value starts at 0 (auto-computed from items)
    target_value = body.target_value
    if body.target_type == "expenses":
        target_value = body.target_value  # Will be recalculated when items are added

    goal = ReportGoal(
        user_id=current_user.id,
        account_id=body.account_id,
        name=body.name,
        target_type=body.target_type,
        target_currency=body.target_currency,
        target_value=target_value,
        target_balance_value=body.target_balance_value,
        target_profit_value=body.target_profit_value,
        income_period=body.income_period,
        expense_period=body.expense_period,
        tax_withholding_pct=body.tax_withholding_pct or 0,
        expense_sort_mode=body.expense_sort_mode or "amount_asc",
        time_horizon_months=body.time_horizon_months,
        start_date=start_date,
        target_date=target_date,
        chart_horizon=body.chart_horizon or "auto",
        show_minimap=body.show_minimap if body.show_minimap is not None else True,
        minimap_threshold_days=body.minimap_threshold_days or 90,
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


# ----- Goal Trend -----

@router.get("/goals/{goal_id}/trend")
async def get_goal_trend(
    goal_id: int,
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get trend line data for a specific goal."""
    from app.services.goal_snapshot_service import (
        backfill_goal_snapshots,
        get_goal_trend_data,
    )
    from sqlalchemy import func as sa_func

    result = await db.execute(
        select(ReportGoal).where(
            ReportGoal.id == goal_id,
            ReportGoal.user_id == current_user.id,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    if goal.target_type == "income":
        raise HTTPException(
            status_code=400,
            detail="Trend charts are not supported for income goals"
        )

    # Auto-backfill if no snapshots exist yet
    count_result = await db.execute(
        select(sa_func.count(GoalProgressSnapshot.id)).where(
            GoalProgressSnapshot.goal_id == goal_id
        )
    )
    snapshot_count = count_result.scalar() or 0

    if snapshot_count == 0:
        backfill_count = await backfill_goal_snapshots(db, goal)
        if backfill_count > 0:
            await db.commit()

    # Parse optional date filters
    parsed_from = None
    parsed_to = None
    if from_date:
        try:
            parsed_from = datetime.strptime(from_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid from_date format")
    if to_date:
        try:
            parsed_to = datetime.strptime(to_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid to_date format")

    trend_data = await get_goal_trend_data(db, goal, parsed_from, parsed_to)

    # Include chart display settings for frontend clipping/minimap
    trend_data["chart_settings"] = {
        "chart_horizon": goal.chart_horizon or "auto",
        "show_minimap": goal.show_minimap if goal.show_minimap is not None else True,
        "minimap_threshold_days": goal.minimap_threshold_days or 90,
    }

    return trend_data


# ----- Expense Items CRUD -----

@router.get("/expense-categories")
async def get_expense_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[str]:
    """Get default + user-defined expense categories."""
    from app.services.expense_service import get_user_expense_categories
    return await get_user_expense_categories(db, current_user.id)


@router.get("/goals/{goal_id}/expenses")
async def list_expense_items(
    goal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """List all expense items for a goal."""
    goal = await _get_user_goal(db, goal_id, current_user.id)
    result = await db.execute(
        select(ExpenseItem)
        .where(ExpenseItem.goal_id == goal.id)
        .order_by(ExpenseItem.sort_order, ExpenseItem.created_at)
    )
    items = result.scalars().all()
    return [_expense_item_to_dict(i, goal.expense_period) for i in items]


@router.post("/goals/{goal_id}/expenses")
async def create_expense_item(
    goal_id: int,
    body: ExpenseItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Add an expense item to a goal."""
    from app.services.expense_service import recalculate_goal_target

    goal = await _get_user_goal(db, goal_id, current_user.id)
    if goal.target_type != "expenses":
        raise HTTPException(
            status_code=400, detail="Can only add expense items to expenses goals"
        )

    item = ExpenseItem(
        goal_id=goal.id,
        user_id=current_user.id,
        category=body.category,
        name=body.name,
        amount=body.amount,
        frequency=body.frequency,
        frequency_n=body.frequency_n,
        frequency_anchor=body.frequency_anchor,
        due_day=body.due_day,
        due_month=body.due_month,
        login_url=body.login_url,
        amount_mode=body.amount_mode or "fixed",
        percent_of_income=body.percent_of_income,
        percent_basis=body.percent_basis,
    )
    db.add(item)
    await db.flush()

    await recalculate_goal_target(db, goal)
    await db.commit()
    await db.refresh(item)
    return _expense_item_to_dict(item, goal.expense_period)


class ExpenseReorderRequest(BaseModel):
    item_ids: List[int] = Field(..., min_length=1)


@router.put("/goals/{goal_id}/expenses/reorder")
async def reorder_expense_items(
    goal_id: int,
    body: ExpenseReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Set sort_order for expense items based on provided ID order."""
    goal = await _get_user_goal(db, goal_id, current_user.id)

    # Fetch all items for this goal owned by this user
    result = await db.execute(
        select(ExpenseItem).where(
            ExpenseItem.goal_id == goal.id,
            ExpenseItem.user_id == current_user.id,
        )
    )
    items_by_id = {item.id: item for item in result.scalars().all()}

    # Validate all IDs belong to this goal
    invalid = set(body.item_ids) - set(items_by_id.keys())
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid item IDs: {list(invalid)}",
        )

    # Set sort_order based on position in the list
    for idx, item_id in enumerate(body.item_ids):
        items_by_id[item_id].sort_order = idx

    await db.commit()
    return {"detail": "Expense items reordered", "count": len(body.item_ids)}


@router.put("/goals/{goal_id}/expenses/{item_id}")
async def update_expense_item(
    goal_id: int,
    item_id: int,
    body: ExpenseItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Update an expense item."""
    from app.services.expense_service import recalculate_goal_target

    goal = await _get_user_goal(db, goal_id, current_user.id)
    result = await db.execute(
        select(ExpenseItem).where(
            ExpenseItem.id == item_id,
            ExpenseItem.goal_id == goal.id,
            ExpenseItem.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Expense item not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(item, key, value)
    item.updated_at = datetime.utcnow()

    await recalculate_goal_target(db, goal)
    await db.commit()
    await db.refresh(item)
    return _expense_item_to_dict(item, goal.expense_period)


@router.delete("/goals/{goal_id}/expenses/{item_id}")
async def delete_expense_item(
    goal_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Delete an expense item."""
    from app.services.expense_service import recalculate_goal_target

    goal = await _get_user_goal(db, goal_id, current_user.id)
    result = await db.execute(
        select(ExpenseItem).where(
            ExpenseItem.id == item_id,
            ExpenseItem.goal_id == goal.id,
            ExpenseItem.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Expense item not found")

    await db.delete(item)
    await recalculate_goal_target(db, goal)
    await db.commit()
    return {"detail": "Expense item deleted"}


async def _get_user_goal(
    db: AsyncSession, goal_id: int, user_id: int,
) -> ReportGoal:
    """Helper to fetch and validate goal ownership."""
    result = await db.execute(
        select(ReportGoal).where(
            ReportGoal.id == goal_id,
            ReportGoal.user_id == user_id,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


def _expense_item_to_dict(item: ExpenseItem, period: str = None) -> dict:
    """Convert an ExpenseItem to a dict for API responses."""
    from app.services.expense_service import normalize_item_to_period

    d = {
        "id": item.id,
        "goal_id": item.goal_id,
        "category": item.category,
        "name": item.name,
        "amount": item.amount,
        "frequency": item.frequency,
        "frequency_n": item.frequency_n,
        "frequency_anchor": item.frequency_anchor,
        "due_day": item.due_day,
        "due_month": item.due_month,
        "login_url": item.login_url,
        "amount_mode": getattr(item, "amount_mode", "fixed") or "fixed",
        "percent_of_income": getattr(item, "percent_of_income", None),
        "percent_basis": getattr(item, "percent_basis", None),
        "is_active": item.is_active,
        "sort_order": item.sort_order or 0,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }
    if period:
        d["normalized_amount"] = round(normalize_item_to_period(item, period), 2)
    return d


# ----- Schedules CRUD -----

@router.get("/schedules")
async def list_schedules(
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """List all report schedules for the current user, optionally filtered by account."""
    filters = [ReportSchedule.user_id == current_user.id]
    if account_id:
        filters.append(ReportSchedule.account_id == account_id)
    result = await db.execute(
        select(ReportSchedule)
        .where(and_(*filters))
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
    from app.services.report_schedule_service import create_schedule_record
    schedule = await create_schedule_record(db, current_user.id, body)
    return _schedule_to_dict(schedule)


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    body: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Update an existing report schedule."""
    from app.services.report_schedule_service import update_schedule_record
    schedule = await update_schedule_record(db, current_user.id, schedule_id, body)
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
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """List generated reports (paginated), optionally filtered by account."""
    filters = [Report.user_id == current_user.id]
    if schedule_id:
        filters.append(Report.schedule_id == schedule_id)
    if account_id:
        filters.append(Report.account_id == account_id)

    # Get total count
    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count(Report.id)).where(and_(*filters))
    )
    total = count_result.scalar()

    # Get page (eager-load schedule for name)
    result = await db.execute(
        select(Report)
        .where(and_(*filters))
        .options(selectinload(Report.schedule))
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
        ).options(selectinload(Report.schedule))
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


class BulkDeleteRequest(BaseModel):
    report_ids: List[int] = Field(..., min_length=1, max_length=100)


@router.post("/bulk-delete")
async def bulk_delete_reports(
    body: BulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Delete multiple reports at once."""
    result = await db.execute(
        select(Report).where(
            Report.id.in_(body.report_ids),
            Report.user_id == current_user.id,
        )
    )
    reports = list(result.scalars().all())
    if not reports:
        raise HTTPException(status_code=404, detail="No matching reports found")
    for report in reports:
        await db.delete(report)
    await db.commit()
    return {"deleted": len(reports)}


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
