"""
Reports Generation Router

Endpoints for report generation, expense item management,
goal trend analytics, and financial metrics.
"""

import logging
from app.utils.timeutil import utcnow
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_permission, Perm
from app.database import get_db, get_read_db
from app.models import (
    ExpenseItem,
    GoalProgressSnapshot,
    User,
)
from app.services.report_access import (
    get_accessible_goal,
    get_writable_goal,
    get_writable_schedule,
    report_to_dict,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


# ----- Pydantic Schemas -----

class GenerateRequest(BaseModel):
    schedule_id: int


class PreviewRequest(BaseModel):
    schedule_id: int


class ExpenseItemCreate(BaseModel):
    category: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    amount: float = Field(0.0, ge=0)
    frequency: str = Field(
        "monthly",
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
    # Savings target fields
    item_type: Optional[str] = Field("expense", pattern="^(expense|savings_target)$")
    savings_target_amount: Optional[float] = Field(None, gt=0)
    savings_target_date: Optional[str] = None   # ISO date YYYY-MM-DD
    savings_is_recurring: Optional[bool] = False
    savings_recurrence_months: Optional[int] = Field(None, ge=1)
    assumed_growth_rate_pct: Optional[float] = Field(None, ge=0, le=100)
    savings_current_balance: Optional[float] = Field(None, ge=0)

    @model_validator(mode="after")
    def validate_fields(self):
        if self.frequency == "every_n_days" and not self.frequency_n:
            raise ValueError("frequency_n is required when frequency is 'every_n_days'")
        if self.due_day is not None and self.due_day == 0:
            raise ValueError("due_day must be -1 (last day) or 1-31")
        if self.amount_mode == "percent_of_income" and not self.percent_of_income:
            raise ValueError(
                "percent_of_income is required when amount_mode is 'percent_of_income'"
            )
        if self.item_type == "savings_target":
            if not self.savings_target_amount:
                raise ValueError("savings_target_amount is required for savings targets")
            if not self.savings_target_date:
                raise ValueError("savings_target_date is required for savings targets")
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
    # Savings target fields
    savings_target_amount: Optional[float] = Field(None, gt=0)
    savings_target_date: Optional[str] = None
    savings_is_recurring: Optional[bool] = None
    savings_recurrence_months: Optional[int] = Field(None, ge=1)
    assumed_growth_rate_pct: Optional[float] = Field(None, ge=0, le=100)
    savings_current_balance: Optional[float] = Field(None, ge=0)


class ExpenseReorderRequest(BaseModel):
    item_ids: List[int] = Field(..., min_length=1)


# ----- Helper Functions -----

async def _get_user_trading_metrics(
    db: AsyncSession, user_id: int, is_btc: bool = False, account_id: int = None
) -> tuple:
    """Delegate to report_data_service.get_user_trading_metrics."""
    from app.services.report_data_service import get_user_trading_metrics
    return await get_user_trading_metrics(db, user_id, is_btc=is_btc, account_id=account_id)


async def _get_user_annual_return_pct(db: AsyncSession, user_id: int, is_btc: bool = False) -> float:
    """Delegate to report_data_service.get_annual_return_pct."""
    from app.services.report_data_service import get_annual_return_pct
    return await get_annual_return_pct(db, user_id, is_btc=is_btc)


def _expense_item_to_dict(
    item: ExpenseItem,
    period: str = None,
    account_annual_return_pct: float = 0.0,
    tax_pct: float = 0.0,
) -> dict:
    """Convert an ExpenseItem to a dict for API responses.

    For savings targets, uses assumed_growth_rate_pct if set, otherwise
    falls back to account_annual_return_pct (live return from closed positions).
    Returns capital_required (PV today needed for compound growth to target) and
    capital_gap (how much more must be reserved) alongside monthly_contribution.
    """
    from app.services.expense_service import normalize_item_to_period

    item_type = getattr(item, "item_type", "expense") or "expense"
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
        # Savings target fields
        "item_type": item_type,
        "savings_target_amount": getattr(item, "savings_target_amount", None),
        "savings_target_date": (
            getattr(item, "savings_target_date", None).isoformat()
            if getattr(item, "savings_target_date", None) else None
        ),
        "savings_is_recurring": getattr(item, "savings_is_recurring", False) or False,
        "savings_recurrence_months": getattr(item, "savings_recurrence_months", None),
        "assumed_growth_rate_pct": getattr(item, "assumed_growth_rate_pct", None),
        "savings_current_balance": getattr(item, "savings_current_balance", 0.0) or 0.0,
    }
    if period:
        if item_type == "savings_target":
            from app.services.expense_service import (
                _compute_gross_target,
                compute_monthly_savings_contribution,
                compute_savings_capital_required,
                normalize_monthly_to_period,
            )
            from datetime import date as _date
            target_date = getattr(item, "savings_target_date", None)
            target_amount = getattr(item, "savings_target_amount", 0.0) or 0.0
            current_balance = getattr(item, "savings_current_balance", 0.0) or 0.0
            is_recurring = getattr(item, "savings_is_recurring", False) or False
            item_rate = getattr(item, "assumed_growth_rate_pct", None)
            # Item override wins; fall back to live account return rate
            growth_rate = item_rate if (item_rate is not None and item_rate > 0) else account_annual_return_pct
            d["effective_growth_rate_pct"] = round(growth_rate, 4)
            d["growth_rate_source"] = "override" if (item_rate is not None and item_rate > 0) else "account"
            # gross_target = total to accumulate by deadline (includes tax gross-up and
            # principal preservation). Exposed alongside target_amount (spend) so the
            # UI can show the user why the accumulation target exceeds their spend target.
            d["gross_target"] = round(
                _compute_gross_target(target_amount, tax_pct, is_recurring, current_balance), 2
            )
            capital_required = compute_savings_capital_required(
                target_amount=target_amount,
                target_date=target_date or _date.today(),
                annual_growth_rate_pct=growth_rate,
                tax_pct=tax_pct,
                is_recurring=is_recurring,
                current_balance=current_balance,
            )
            d["capital_required"] = round(capital_required, 2)
            d["capital_gap"] = round(max(0.0, capital_required - current_balance), 2)
            monthly = compute_monthly_savings_contribution(
                target_amount=target_amount,
                target_date=target_date or _date.today(),
                current_balance=current_balance,
                annual_growth_rate_pct=growth_rate,
                tax_pct=tax_pct,
                is_recurring=is_recurring,
            )
            d["monthly_contribution"] = round(monthly, 2)
            d["normalized_amount"] = round(normalize_monthly_to_period(monthly, period), 2)
        else:
            d["normalized_amount"] = round(normalize_item_to_period(item, period), 2)
    return d


# ----- Goal Trend -----

@router.get("/goals/{goal_id}/trend")
async def get_goal_trend(
    goal_id: int,
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_read_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get trend line data for a specific goal."""
    from app.services.goal_snapshot_service import (
        backfill_goal_snapshots,
        get_goal_trend_data,
    )
    from sqlalchemy import func as sa_func

    goal = await get_accessible_goal(db, goal_id, current_user.id)

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
    # Note: show_minimap is now schedule-level, but the trend endpoint
    # doesn't know which schedule is viewing. Default to True and let
    # frontend decide based on horizon vs target comparison.
    trend_data["chart_settings"] = {
        "chart_horizon": goal.chart_horizon or "auto",
    }

    return trend_data


# ----- Expense Items CRUD -----

@router.get("/expense-categories")
async def get_expense_categories(
    db: AsyncSession = Depends(get_read_db),
    current_user: User = Depends(get_current_user),
) -> List[str]:
    """Get default + user-defined expense categories."""
    from app.services.expense_service import get_user_expense_categories
    return await get_user_expense_categories(db, current_user.id)


@router.get("/goals/{goal_id}/expenses")
async def list_expense_items(
    goal_id: int,
    db: AsyncSession = Depends(get_read_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """List all expense items for a goal with live waterfall coverage.

    Runs the unified waterfall so each item shows its dynamic_reserved amount
    (what's actually available from the account balance given its sort position)
    and income_earmarked (how much monthly income the reservation consumes).
    """
    from app.services.expense_service import compute_expense_coverage

    goal = await get_accessible_goal(db, goal_id, current_user.id)
    result = await db.execute(
        select(ExpenseItem)
        .where(ExpenseItem.goal_id == goal.id)
        .order_by(ExpenseItem.sort_order, ExpenseItem.created_at)
    )
    items = result.scalars().all()
    is_btc = goal.target_currency == "BTC"
    tax_pct = goal.tax_withholding_pct or 0.0

    annual_return_pct, account_balance = await _get_user_trading_metrics(
        db, goal.user_id, is_btc=is_btc, account_id=goal.account_id or None
    )

    # Compute projected monthly income from account balance and growth rate
    from app.services.report_data_service import compute_monthly_growth_rate
    monthly_rate = compute_monthly_growth_rate(annual_return_pct)
    if account_balance > 0 and monthly_rate > 0:
        projected_monthly = account_balance * monthly_rate
    else:
        projected_monthly = 0.0

    # Run unified waterfall to get dynamic reservation fields per item
    coverage = compute_expense_coverage(
        items, goal.expense_period or "monthly", projected_monthly, tax_pct,
        sort_mode="custom",
        account_annual_return_pct=annual_return_pct,
        account_balance=account_balance,
    )

    # Build a lookup of item_id → waterfall dynamic fields
    waterfall_by_id: dict = {}
    for entry in coverage.get("items", []) + coverage.get("savings_targets", []):
        if entry.get("id"):
            waterfall_by_id[entry["id"]] = entry

    enriched = []
    for item in items:
        d = _expense_item_to_dict(item, goal.expense_period, annual_return_pct, tax_pct)
        if item.id in waterfall_by_id:
            wf = waterfall_by_id[item.id]
            # Overlay dynamic waterfall fields
            d["dynamic_reserved"] = wf.get("dynamic_reserved", 0.0)
            d["income_earmarked"] = wf.get("income_earmarked", 0.0)
            d["dynamic_on_track"] = wf.get("dynamic_on_track", False)
            d["waterfall_status"] = wf.get("status", "unknown")
            d["waterfall_coverage_pct"] = wf.get("coverage_pct", 0.0)
            # Use waterfall normalized_amount for all items — it has the correct value
            # for percent_of_income items (calculated against projected_income).
            if "normalized_amount" in wf:
                d["normalized_amount"] = wf["normalized_amount"]
            if item.item_type == "savings_target":
                # Use waterfall-computed gap (based on dynamic_reserved, not stored balance)
                d["capital_gap"] = wf.get("capital_gap", d.get("capital_gap", 0.0))
                d["capital_required"] = wf.get("capital_required", d.get("capital_required", 0.0))
                d["monthly_contribution"] = wf.get("monthly_contribution", 0.0)
        enriched.append(d)

    # Build coverage summary for frontend deposit coaching
    coverage_summary = {
        "shortfall": coverage.get("shortfall", 0.0),
        "income_after_tax": coverage.get("income_after_tax", 0.0),
        "total_expenses": coverage.get("total_expenses", 0.0),
        # Expense-path coaching
        "partial_item_name": coverage.get("partial_item_name"),
        "partial_item_shortfall": coverage.get("partial_item_shortfall"),
        "next_uncovered_name": coverage.get("next_uncovered_name"),
        "next_uncovered_amount": coverage.get("next_uncovered_amount"),
        # Savings-gap coaching
        "first_gap_savings_name": coverage.get("first_gap_savings_name"),
        "first_gap_savings_cap_gap": coverage.get("first_gap_savings_cap_gap"),
        "first_gap_savings_capital_required": coverage.get("first_gap_savings_capital_required"),
        "first_blocked_after_savings_name": coverage.get("first_blocked_after_savings_name"),
        "first_blocked_after_savings_amount": coverage.get("first_blocked_after_savings_amount"),
        # Account context for income-based deposit math
        "account_balance": account_balance,
        "annual_return_pct": annual_return_pct,
        "tax_pct": tax_pct,
        "period": goal.expense_period or "monthly",
    }

    return {"items": enriched, "coverage_summary": coverage_summary}


@router.post("/goals/{goal_id}/expenses")
async def create_expense_item(
    goal_id: int,
    body: ExpenseItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.REPORTS_WRITE)),
) -> dict:
    """Add an expense item to a goal."""
    from app.services.expense_service import recalculate_goal_target

    goal = await get_writable_goal(db, goal_id, current_user)
    if goal.target_type != "expenses":
        raise HTTPException(
            status_code=400, detail="Can only add expense items to expenses goals"
        )

    from datetime import date as _date
    savings_target_date = None
    if body.savings_target_date:
        try:
            savings_target_date = _date.fromisoformat(body.savings_target_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="savings_target_date must be YYYY-MM-DD")

    item = ExpenseItem(
        goal_id=goal.id,
        user_id=goal.user_id,  # attribute to goal owner so members see it
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
        item_type=body.item_type or "expense",
        savings_target_amount=body.savings_target_amount,
        savings_target_date=savings_target_date,
        savings_is_recurring=body.savings_is_recurring or False,
        savings_recurrence_months=body.savings_recurrence_months,
        assumed_growth_rate_pct=body.assumed_growth_rate_pct,
        savings_current_balance=body.savings_current_balance or 0.0,
    )
    db.add(item)
    await db.flush()

    await recalculate_goal_target(db, goal)
    await db.commit()
    await db.refresh(item)
    return _expense_item_to_dict(item, goal.expense_period)


@router.put("/goals/{goal_id}/expenses/reorder")
async def reorder_expense_items(
    goal_id: int,
    body: ExpenseReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.REPORTS_WRITE)),
) -> dict:
    """Set sort_order for expense items based on provided ID order."""
    goal = await get_writable_goal(db, goal_id, current_user)

    # Fetch all items for this goal
    result = await db.execute(
        select(ExpenseItem).where(
            ExpenseItem.goal_id == goal.id,
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
    current_user: User = Depends(require_permission(Perm.REPORTS_WRITE)),
) -> dict:
    """Update an expense item."""
    from app.services.expense_service import recalculate_goal_target

    goal = await get_writable_goal(db, goal_id, current_user)
    result = await db.execute(
        select(ExpenseItem).where(
            ExpenseItem.id == item_id,
            ExpenseItem.goal_id == goal.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Expense item not found")

    from datetime import date as _date
    update_data = body.model_dump(exclude_unset=True)

    # Parse savings_target_date string → date object
    if "savings_target_date" in update_data and update_data["savings_target_date"]:
        try:
            update_data["savings_target_date"] = _date.fromisoformat(
                update_data["savings_target_date"]
            )
        except ValueError:
            raise HTTPException(status_code=422, detail="savings_target_date must be YYYY-MM-DD")

    for key, value in update_data.items():
        setattr(item, key, value)
    item.updated_at = utcnow()

    await recalculate_goal_target(db, goal)
    await db.commit()
    await db.refresh(item)
    return _expense_item_to_dict(item, goal.expense_period)


@router.delete("/goals/{goal_id}/expenses/{item_id}")
async def delete_expense_item(
    goal_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.REPORTS_WRITE)),
) -> dict:
    """Delete an expense item."""
    from app.services.expense_service import recalculate_goal_target

    goal = await get_writable_goal(db, goal_id, current_user)
    result = await db.execute(
        select(ExpenseItem).where(
            ExpenseItem.id == item_id,
            ExpenseItem.goal_id == goal.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Expense item not found")

    await db.delete(item)
    await recalculate_goal_target(db, goal)
    await db.commit()
    return {"detail": "Expense item deleted"}


# ----- Report Generation -----

@router.post("/generate")
async def generate_report(
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.REPORTS_WRITE)),
) -> dict:
    """Manually trigger report generation for a schedule."""
    schedule, _uid = await get_writable_schedule(db, body.schedule_id, current_user)

    # Generate the report (ad-hoc — don't advance schedule timing)
    from app.services.report_scheduler import generate_report_for_schedule
    report = await generate_report_for_schedule(
        db, schedule, current_user, advance_schedule=False,
    )

    return report_to_dict(report, include_html=True)


@router.post("/preview")
async def preview_report(
    body: PreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Preview a report without saving or emailing."""
    schedule, _uid = await get_writable_schedule(db, body.schedule_id, current_user)

    from app.services.report_scheduler import generate_report_for_schedule
    report = await generate_report_for_schedule(
        db, schedule, current_user, save=False, send_email=False
    )

    return report_to_dict(report, include_html=True)
