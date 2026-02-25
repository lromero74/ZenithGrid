"""
Expense Service

Handles expense item normalization and coverage waterfall calculations
for the expenses goal type.
"""

import logging
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


def compute_expense_coverage(
    items: list,
    period: str,
    projected_income: float,
    tax_pct: float,
    sort_mode: str = "amount_asc",
) -> Dict[str, Any]:
    """
    Compute coverage waterfall for expense items.

    1. Normalize all items to the goal period
    2. Sort by sort_mode: amount_asc (default), amount_desc, or custom
    3. Walk through deducting from income after tax
    4. Return coverage status for each item
    """
    income_after_tax = projected_income * (1 - tax_pct / 100)

    # Normalize and sort items
    normalized = []
    for item in items:
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

    result = {
        "total_expenses": round(total_expenses, 2),
        "income_after_tax": round(income_after_tax, 2),
        "coverage_pct": round(coverage_pct, 1),
        "shortfall": round(shortfall, 2),
        "covered_count": covered_count,
        "total_count": len(normalized),
        "items": normalized,
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
