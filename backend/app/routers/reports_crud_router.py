"""
Reports CRUD Router

CRUD endpoints for financial goals, report schedules,
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
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user, require_permission, Perm
from app.database import get_db, get_read_db
from app.models import (
    Account,
    Report,
    ReportGoal,
    ReportSchedule,
    User,
)
from app.services.account_access import accessible_accounts_filter, manager_account_ids, manager_accounts_filter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


async def _resolve_report_user_id(
    db: AsyncSession, current_user_id: int, account_id: Optional[int]
) -> int:
    """
    Return the user_id to use when querying report rows.

    Goals, schedules, and history are stored with the account OWNER's user_id.
    When a member (observer/manager) requests data for a specific account, we
    resolve the owner's user_id so the query returns the correct rows.

    When no account_id is given, returns current_user_id (observer sees only
    their own records, which is the correct behaviour for unscoped requests).
    """
    if account_id is None:
        return current_user_id

    result = await db.execute(
        select(Account.user_id).where(
            Account.id == account_id,
            accessible_accounts_filter(current_user_id),
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found or not accessible")
    return row[0]


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
    show_minimap: Optional[bool] = True  # Legacy; minimap now controlled per schedule
    minimap_threshold_days: Optional[int] = Field(90, ge=1)

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
    show_minimap: Optional[bool] = None  # Legacy; minimap now controlled per schedule
    minimap_threshold_days: Optional[int] = Field(None, ge=1)


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
    chart_lookahead_multiplier: Optional[float] = Field(1.0, ge=0.01, le=10.0)
    show_minimap: Optional[bool] = True
    retention_count: Optional[int] = Field(None, ge=1)
    retention_days: Optional[int] = Field(None, ge=1)

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
    chart_lookahead_multiplier: Optional[float] = Field(None, ge=0.01, le=10.0)
    show_minimap: Optional[bool] = None
    retention_count: Optional[int] = Field(None, ge=1)
    retention_days: Optional[int] = Field(None, ge=1)


class BulkDeleteRequest(BaseModel):
    report_ids: List[int] = Field(..., min_length=1, max_length=100)


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
    # Include expense item count split (only if relationship is already loaded)
    if goal.target_type == "expenses":
        state = sa_inspect(goal)
        if "expense_items" not in state.unloaded:
            items = goal.expense_items or []
            active_items = [i for i in items if getattr(i, "is_active", True)]
            d["expense_item_count"] = len(active_items)
            d["savings_target_count"] = sum(
                1 for i in active_items if getattr(i, "item_type", "expense") == "savings_target"
            )
            # Recompute target_value from items instead of trusting stale cached value.
            # Only fixed-amount expense items contribute; savings targets (amount=0)
            # and percent_of_income items are excluded from this total.
            from app.services.expense_service import normalize_to_monthly, normalize_monthly_to_period
            period = goal.expense_period or "monthly"
            total_monthly = sum(
                normalize_to_monthly(i.amount, i.frequency, getattr(i, "frequency_n", None))
                for i in active_items
                if (getattr(i, "amount_mode", "fixed") or "fixed") == "fixed"
                and (getattr(i, "item_type", "expense") or "expense") == "expense"
                and i.amount > 0
            )
            if total_monthly > 0:
                d["target_value"] = round(normalize_monthly_to_period(total_monthly, period), 2)
        else:
            d["expense_item_count"] = 0
            d["savings_target_count"] = 0
    else:
        d["expense_item_count"] = 0
        d["savings_target_count"] = 0
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
        "show_minimap": (
            schedule.show_minimap
            if schedule.show_minimap is not None else True
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
        "retention_count": schedule.retention_count,
        "retention_days": schedule.retention_days,
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


async def _get_user_goal(
    db: AsyncSession, goal_id: int, user_id: int,
) -> ReportGoal:
    """Helper to fetch and validate goal ownership (write paths only)."""
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


async def _get_accessible_goal(
    db: AsyncSession, goal_id: int, current_user_id: int,
) -> ReportGoal:
    """Fetch a goal the user can read: owner OR observer/manager of owner's account."""
    from sqlalchemy import or_
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


async def _get_accessible_report(
    db: AsyncSession, report_id: int, current_user_id: int,
) -> Report:
    """Fetch a report the user can read: owner OR observer/manager of owner's account."""
    from sqlalchemy import or_
    result = await db.execute(
        select(Report).where(
            Report.id == report_id,
            or_(
                Report.user_id == current_user_id,
                Report.user_id.in_(
                    select(Account.user_id).where(
                        accessible_accounts_filter(current_user_id),
                        Account.user_id != current_user_id,
                    )
                ),
            ),
        ).options(selectinload(Report.schedule))
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


async def _resolve_write_user_id(
    db: AsyncSession, current_user: User, account_id: Optional[int],
) -> int:
    """
    Return the user_id to store on report objects created for a shared account.

    When a manager creates goals, schedules, or expense items on another user's
    account, the record is attributed to the account OWNER so that the owner
    (and other members) see it via _resolve_report_user_id.

    - Own account or no account_id → returns current_user.id
    - Manager on another account    → returns account.user_id (the owner)
    - No write access               → raises 403
    """
    if account_id is None:
        return current_user.id
    result = await db.execute(
        select(Account.user_id).where(
            Account.id == account_id,
            manager_accounts_filter(current_user.id),
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=403, detail="Insufficient access to account")
    return row[0]


async def _get_writable_goal(
    db: AsyncSession, goal_id: int, current_user: User,
) -> ReportGoal:
    """
    Fetch a goal the user can write to.

    Grants write access when the user owns the goal OR holds manager/owner
    membership on the goal's account.  Raises 404 if not readable at all,
    403 if readable but not writable.
    """
    goal = await _get_accessible_goal(db, goal_id, current_user.id)
    if goal.user_id == current_user.id:
        return goal
    mgr_ids = await manager_account_ids(db, current_user.id)
    if goal.account_id not in mgr_ids:
        raise HTTPException(status_code=403, detail="Insufficient access to modify this goal")
    return goal


async def _get_writable_schedule(
    db: AsyncSession, schedule_id: int, current_user: User,
) -> tuple:
    """
    Fetch a schedule the user can write to.

    Returns (schedule, effective_user_id) where effective_user_id is the
    schedule owner's user_id — pass it to service functions that accept user_id
    to look up records.

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


# ----- Goals CRUD -----

@router.get("/goals")
async def list_goals(
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    db: AsyncSession = Depends(get_read_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """List all goals for the current user, optionally filtered by account."""
    uid = await _resolve_report_user_id(db, current_user.id, account_id)
    filters = [ReportGoal.user_id == uid]
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
    current_user: User = Depends(require_permission(Perm.REPORTS_WRITE)),
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

    write_uid = await _resolve_write_user_id(db, current_user, body.account_id)

    goal = ReportGoal(
        user_id=write_uid,
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
    current_user: User = Depends(require_permission(Perm.REPORTS_WRITE)),
) -> dict:
    """Update an existing goal."""
    goal = await _get_writable_goal(db, goal_id, current_user)

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
    current_user: User = Depends(require_permission(Perm.REPORTS_DELETE)),
) -> dict:
    """Delete a goal."""
    goal = await _get_writable_goal(db, goal_id, current_user)

    await db.delete(goal)
    await db.commit()
    return {"detail": "Goal deleted"}


# ----- Schedules CRUD -----

@router.get("/schedules")
async def list_schedules(
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    db: AsyncSession = Depends(get_read_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """List all report schedules for the current user, optionally filtered by account."""
    uid = await _resolve_report_user_id(db, current_user.id, account_id)
    filters = [ReportSchedule.user_id == uid]
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
    current_user: User = Depends(require_permission(Perm.REPORTS_WRITE)),
) -> dict:
    """Create a new report schedule."""
    from app.services.report_schedule_service import create_schedule_record
    write_uid = await _resolve_write_user_id(db, current_user, body.account_id)
    schedule = await create_schedule_record(db, write_uid, body)
    return _schedule_to_dict(schedule)


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    body: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.REPORTS_WRITE)),
) -> dict:
    """Update an existing report schedule."""
    from app.services.report_schedule_service import update_schedule_record
    _schedule, effective_uid = await _get_writable_schedule(db, schedule_id, current_user)
    schedule = await update_schedule_record(db, effective_uid, schedule_id, body)
    return _schedule_to_dict(schedule)


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.REPORTS_DELETE)),
) -> dict:
    """Delete a report schedule."""
    schedule, _uid = await _get_writable_schedule(db, schedule_id, current_user)
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
    db: AsyncSession = Depends(get_read_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """List generated reports (paginated), optionally filtered by account."""
    uid = await _resolve_report_user_id(db, current_user.id, account_id)
    filters = [Report.user_id == uid]
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
    db: AsyncSession = Depends(get_read_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get a single report with HTML content for in-app viewing."""
    report = await _get_accessible_report(db, report_id, current_user.id)
    return _report_to_dict(report, include_html=True)


@router.delete("/{report_id}")
async def delete_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.REPORTS_DELETE)),
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


@router.post("/bulk-delete")
async def bulk_delete_reports(
    body: BulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.REPORTS_DELETE)),
) -> dict:
    """Delete multiple reports at once."""
    # Use bulk DELETE instead of individual db.delete() per report
    del_result = await db.execute(
        delete(Report).where(
            Report.id.in_(body.report_ids),
            Report.user_id == current_user.id,
        )
    )
    deleted_count = del_result.rowcount
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="No matching reports found")
    await db.commit()
    return {"deleted": deleted_count}


@router.get("/{report_id}/pdf")
async def download_report_pdf(
    report_id: int,
    db: AsyncSession = Depends(get_read_db),
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
