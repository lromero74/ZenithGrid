"""
Expense Service

Handles expense item normalization and coverage waterfall calculations
for the expenses goal type, including savings targets with PMT-based
monthly contribution calculations.
"""

import logging
import math
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Average days per month (365.25 / 12)
_DAYS_PER_MONTH = 30.4375

DEFAULT_EXPENSE_CATEGORIES = [
    "Housing", "Utilities", "Transportation", "Food",
    "Insurance", "Healthcare", "Subscriptions", "Entertainment",
    "Education", "Debt", "Donations", "Personal", "Other",
]


def normalize_to_monthly(
    amount: float,
    frequency: str,
    frequency_n: Optional[int] = None,
) -> float:
    """
    Convert an expense amount from its native frequency to a monthly equivalent.

    Raises ValueError for unknown frequencies or missing frequency_n.
    """
    if frequency == "daily":
        return amount * _DAYS_PER_MONTH
    elif frequency == "weekly":
        return amount * 52 / 12
    elif frequency == "biweekly":
        return amount * 26 / 12
    elif frequency == "every_n_days":
        if not frequency_n or frequency_n <= 0:
            raise ValueError("frequency_n is required and must be > 0 for every_n_days")
        return amount * _DAYS_PER_MONTH / frequency_n
    elif frequency == "semi_monthly":
        return amount * 2
    elif frequency == "monthly":
        return amount
    elif frequency == "quarterly":
        return amount / 3
    elif frequency == "semi_annual":
        return amount / 6
    elif frequency == "yearly":
        return amount / 12
    else:
        raise ValueError(f"Unknown frequency: {frequency}")


def normalize_monthly_to_period(monthly: float, period: str) -> float:
    """Convert a monthly amount to a target period."""
    if period == "weekly":
        return monthly * 12 / 52
    elif period == "monthly":
        return monthly
    elif period == "quarterly":
        return monthly * 3
    elif period == "yearly":
        return monthly * 12
    else:
        raise ValueError(f"Unknown period: {period}")


def normalize_item_to_period(item, period: str) -> float:
    """Normalize a single expense item to the goal's period."""
    monthly = normalize_to_monthly(item.amount, item.frequency, item.frequency_n)
    return normalize_monthly_to_period(monthly, period)


def compute_monthly_savings_contribution(
    target_amount: float,
    target_date: date,
    current_balance: float,
    annual_growth_rate_pct: float,
    tax_pct: float,
) -> float:
    """
    Calculate the required monthly contribution to reach target_amount by target_date,
    given current_balance growing at annual_growth_rate_pct.

    Uses the standard PMT formula:
        PMT = r * (FV - PV*(1+r)^n) / ((1+r)^n - 1)
    where r = monthly rate, n = months remaining, PV = current_balance, FV = gross target.

    Returns 0.0 if:
    - target_date is in the past (can't contribute retroactively)
    - current_balance already meets or exceeds the gross target
    """
    today = date.today()
    if target_date <= today:
        return 0.0

    # Gross up target for tax withholding (if proceeds are taxed)
    gross_target = target_amount / (1 - tax_pct / 100) if tax_pct > 0 else target_amount

    if current_balance >= gross_target:
        return 0.0

    # Months remaining (fractional)
    days_remaining = (target_date - today).days
    n = days_remaining / 30.4375  # average days per month

    if n <= 0:
        return 0.0

    r = annual_growth_rate_pct / 100.0 / 12.0  # monthly rate

    if r == 0.0:
        # Simple linear: no growth
        return (gross_target - current_balance) / n

    # Standard PMT for future value with existing present value:
    # PMT = r * (FV - PV*(1+r)^n) / ((1+r)^n - 1)
    factor = math.pow(1 + r, n)
    numerator = r * (gross_target - current_balance * factor)
    denominator = factor - 1
    if denominator <= 0:
        return 0.0

    return max(0.0, numerator / denominator)


def _build_savings_target_entry(item, period: str, income_after_tax: float, tax_pct: float) -> Dict[str, Any]:
    """Build a savings target entry with contribution + progress fields."""
    target_amount = getattr(item, "savings_target_amount", 0.0) or 0.0
    target_date = getattr(item, "savings_target_date", None)
    current_balance = getattr(item, "savings_current_balance", 0.0) or 0.0
    growth_rate = getattr(item, "assumed_growth_rate_pct", 0.0) or 0.0
    is_recurring = getattr(item, "savings_is_recurring", False)
    recurrence_months = getattr(item, "savings_recurrence_months", None)

    today = date.today()
    months_remaining = 0
    if target_date and target_date > today:
        months_remaining = round((target_date - today).days / 30.4375)

    # Required monthly contribution (PMT, no tax gross-up here — tax applied at goal level)
    monthly_contribution = compute_monthly_savings_contribution(
        target_amount=target_amount,
        target_date=target_date or today,
        current_balance=current_balance,
        annual_growth_rate_pct=growth_rate,
        tax_pct=0.0,  # tax gross-up is a report-level concern, not per-item
    )

    # Normalize monthly contribution to the goal period
    monthly_in_period = normalize_monthly_to_period(monthly_contribution, period)

    savings_pct = min((current_balance / target_amount * 100) if target_amount > 0 else 0.0, 100.0)

    # On-track: compare current_balance to what FV should be by now (compound growth)
    # Expected = FV of starting balance ($0 assumed) + contributions made
    # Simplified: if savings_pct >= linear time fraction, call it on track
    savings_on_track = False
    if target_date and target_date > today and target_amount > 0:
        # We don't know start_date here, so use savings_pct as a proxy.
        savings_on_track = current_balance >= target_amount or savings_pct >= 50.0

    # Determine status based on past due / funded / progress
    if target_date and target_date <= today:
        if current_balance >= target_amount:
            status = "funded"
        else:
            status = "past_due"
    elif current_balance >= target_amount:
        status = "funded"
    else:
        status = "pending"  # will be overridden by waterfall coverage check

    return {
        "id": getattr(item, "id", None),
        "name": item.name,
        "category": getattr(item, "category", "Savings"),
        "target_amount": round(target_amount, 2),
        "target_date": target_date.isoformat() if target_date else None,
        "current_balance": round(current_balance, 2),
        "savings_pct": round(savings_pct, 1),
        "months_remaining": months_remaining,
        "monthly_contribution": round(monthly_contribution, 2),
        "normalized_amount": round(monthly_in_period, 2),  # period-normalized contribution
        "assumed_growth_rate_pct": growth_rate,
        "is_recurring": is_recurring,
        "recurrence_months": recurrence_months,
        "savings_on_track": savings_on_track,
        "sort_order": getattr(item, "sort_order", 0),
        "status": status,
        "coverage_pct": 0.0,  # set by waterfall pass below
    }


def compute_expense_coverage(
    items: list,
    period: str,
    projected_income: float,
    tax_pct: float,
    sort_mode: str = "amount_asc",
) -> Dict[str, Any]:
    """
    Compute coverage waterfall for expense items and savings targets.

    Pass 1 — Regular expenses:
        1. Normalize all expense items (item_type='expense') to the goal period
        2. Sort by sort_mode: amount_asc (default), amount_desc, or custom
        3. Walk through deducting from income after tax
        4. Return coverage status for each item

    Pass 2 — Savings targets (item_type='savings_target'):
        5. Calculate required monthly contribution (PMT) per target
        6. Walk through remaining income after expenses
        7. Return coverage status per target + progress tracking fields
    """
    income_after_tax = projected_income * (1 - tax_pct / 100)

    # Split items into expenses and savings targets
    expense_items = [i for i in items if getattr(i, "item_type", "expense") != "savings_target"]
    savings_items = [i for i in items if getattr(i, "item_type", "expense") == "savings_target"]

    # --- Pass 1: Expense waterfall ---
    normalized = []
    for item in expense_items:
        amount_mode = getattr(item, "amount_mode", "fixed") or "fixed"
        pct_of_income = getattr(item, "percent_of_income", None)
        pct_basis = getattr(item, "percent_basis", None)

        if amount_mode == "percent_of_income" and pct_of_income:
            # Calculate dollar amount from percentage of income
            basis = (projected_income if pct_basis == "pre_tax"
                     else income_after_tax)
            dollar_amount = pct_of_income / 100.0 * basis
            # Already in the goal period — no frequency normalization needed
            norm_amount = round(dollar_amount, 2)
        else:
            norm_amount = normalize_item_to_period(item, period)

        entry = {
            "id": getattr(item, "id", None),
            "name": item.name,
            "category": item.category,
            "amount": item.amount,
            "frequency": item.frequency,
            "due_day": getattr(item, "due_day", None),
            "due_month": getattr(item, "due_month", None),
            "frequency_anchor": getattr(item, "frequency_anchor", None),
            "frequency_n": getattr(item, "frequency_n", None),
            "login_url": getattr(item, "login_url", None),
            "sort_order": getattr(item, "sort_order", 0),
            "normalized_amount": round(norm_amount, 2),
            "amount_mode": amount_mode,
        }
        if amount_mode == "percent_of_income":
            entry["percent_of_income"] = pct_of_income
            entry["percent_basis"] = pct_basis
        normalized.append(entry)

    if sort_mode == "amount_desc":
        normalized.sort(key=lambda x: x["normalized_amount"], reverse=True)
    elif sort_mode == "custom":
        normalized.sort(key=lambda x: x.get("sort_order", 0))
    else:  # amount_asc (default)
        normalized.sort(key=lambda x: x["normalized_amount"])

    total_expenses = sum(i["normalized_amount"] for i in normalized)

    # Walk through the waterfall
    remaining = income_after_tax
    covered_count = 0
    partial_item = None  # The item that's partially covered
    next_uncovered_item = None  # The first fully uncovered item after partial
    for item in normalized:
        amt = item["normalized_amount"]
        if remaining >= amt:
            item["status"] = "covered"
            item["coverage_pct"] = 100.0
            remaining -= amt
            covered_count += 1
        elif remaining > 0:
            item["status"] = "partial"
            item["coverage_pct"] = round(remaining / amt * 100, 1)
            item["shortfall"] = round(amt - remaining, 2)
            partial_item = item
            remaining = 0
        else:
            item["status"] = "uncovered"
            item["coverage_pct"] = 0.0
            if next_uncovered_item is None and partial_item is not None:
                next_uncovered_item = item

    # If no partial item, the first uncovered is the "next" to cover
    if partial_item is None:
        for item in normalized:
            if item["status"] == "uncovered":
                next_uncovered_item = item
                break

    shortfall = max(total_expenses - income_after_tax, 0)
    coverage_pct = (
        min(income_after_tax / total_expenses * 100, 100.0)
        if total_expenses > 0 else 100.0
    )

    # --- Pass 2: Savings target waterfall ---
    # Run against income remaining after expenses
    savings_remaining = max(income_after_tax - total_expenses, 0.0)
    savings_entries = []
    total_savings_contributions = 0.0

    for item in savings_items:
        entry = _build_savings_target_entry(item, period, income_after_tax, tax_pct)
        contrib = entry["normalized_amount"]
        total_savings_contributions += contrib

        # Override status from waterfall coverage
        if entry["status"] in ("funded", "past_due"):
            pass  # keep computed status
        elif contrib <= 0:
            entry["status"] = "funded"
            entry["coverage_pct"] = 100.0
        elif savings_remaining >= contrib:
            entry["status"] = "covered"
            entry["coverage_pct"] = 100.0
            savings_remaining -= contrib
        elif savings_remaining > 0:
            entry["status"] = "partial"
            entry["coverage_pct"] = round(savings_remaining / contrib * 100, 1)
            entry["shortfall"] = round(contrib - savings_remaining, 2)
            savings_remaining = 0.0
        else:
            entry["status"] = "uncovered"
            entry["coverage_pct"] = 0.0

        savings_entries.append(entry)

    total_claims = round(total_expenses + total_savings_contributions, 2)
    savings_coverage_pct = (
        min(max(income_after_tax - total_expenses, 0.0) / total_savings_contributions * 100, 100.0)
        if total_savings_contributions > 0 else 100.0
    )

    result = {
        "total_expenses": round(total_expenses, 2),
        "total_savings_contributions": round(total_savings_contributions, 2),
        "total_claims": total_claims,
        "income_after_tax": round(income_after_tax, 2),
        "coverage_pct": round(coverage_pct, 1),
        "savings_coverage_pct": round(savings_coverage_pct, 1),
        "shortfall": round(shortfall, 2),
        "covered_count": covered_count,
        "total_count": len(normalized),
        "items": normalized,
        "savings_targets": savings_entries,
    }

    # Add granular deposit targets
    if partial_item:
        result["partial_item_name"] = partial_item["name"]
        result["partial_item_shortfall"] = partial_item["shortfall"]
    if next_uncovered_item:
        result["next_uncovered_name"] = next_uncovered_item["name"]
        result["next_uncovered_amount"] = next_uncovered_item["normalized_amount"]

    return result


async def get_user_expense_categories(
    db: AsyncSession, user_id: int,
) -> List[str]:
    """Return default categories plus any user-defined ones."""
    from app.models import ExpenseItem

    result = await db.execute(
        select(ExpenseItem.category)
        .where(ExpenseItem.user_id == user_id)
        .distinct()
    )
    user_cats = {row[0] for row in result.fetchall()}
    all_cats = set(DEFAULT_EXPENSE_CATEGORIES) | user_cats
    return sorted(all_cats)


async def recalculate_goal_target(db: AsyncSession, goal) -> float:
    """
    Recalculate target_value for an expenses goal from its active items.

    Updates goal.target_value in place and returns the new value.
    """
    from app.models import ExpenseItem

    result = await db.execute(
        select(ExpenseItem).where(
            ExpenseItem.goal_id == goal.id,
            ExpenseItem.is_active.is_(True),
        )
    )
    items = result.scalars().all()

    total_monthly = sum(
        normalize_to_monthly(item.amount, item.frequency, item.frequency_n)
        for item in items
        if (getattr(item, "amount_mode", "fixed") or "fixed") == "fixed"
    )
    period = goal.expense_period or "monthly"
    total_period = normalize_monthly_to_period(total_monthly, period)
    goal.target_value = round(total_period, 2)
    return goal.target_value
