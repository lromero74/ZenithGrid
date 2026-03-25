"""
Expense Service

Handles expense item normalization and coverage waterfall calculations
for the expenses goal type, including savings targets with capital-reservation
tracking. Savings targets show how much capital must be held in the account
today (Present Value) so it compounds to the target by the deadline — not
a monthly cash outflow.
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


def compute_savings_capital_required(
    target_amount: float,
    target_date: date,
    annual_growth_rate_pct: float,
    tax_pct: float = 0.0,
    is_recurring: bool = False,
    current_balance: float = 0.0,
) -> float:
    """
    Calculate the Present Value (capital) that must be reserved in the account
    TODAY for it to compound to the target by target_date.

    PV = gross_target / (1 + monthly_rate)^n

    For recurring targets with tax: gross_target includes tax + principal preservation.
    Returns 0.0 if target_date is in the past or already funded.
    """
    today = date.today()
    if target_date <= today:
        return 0.0

    days_remaining = (target_date - today).days
    n = days_remaining / _DAYS_PER_MONTH
    if n <= 0:
        return 0.0

    gross_target = _compute_gross_target(target_amount, tax_pct, is_recurring, current_balance)
    r = annual_growth_rate_pct / 100.0 / 12.0

    if r == 0.0:
        return gross_target

    # PV = FV / (1 + r)^n
    return gross_target / math.pow(1 + r, n)


def _compute_gross_target(
    target_amount: float,
    tax_pct: float,
    is_recurring: bool,
    current_balance: float,
) -> float:
    """
    Compute the gross FV target that the account balance must reach.

    - Non-recurring, no tax: just target_amount
    - Non-recurring, with tax: target_amount / (1 - tax_pct/100) so after-tax = target
    - Recurring, no tax: target_amount + current_balance (preserve principal for next cycle)
    - Recurring, with tax: (target_amount / (1 - tax_pct/100)) + current_balance
    """
    gross_withdrawal = target_amount / (1 - tax_pct / 100) if tax_pct > 0 else target_amount
    if is_recurring:
        return gross_withdrawal + current_balance
    return gross_withdrawal


def compute_monthly_savings_contribution(
    target_amount: float,
    target_date: date,
    current_balance: float,
    annual_growth_rate_pct: float,
    tax_pct: float,
    is_recurring: bool = False,
) -> float:
    """
    Calculate the required monthly contribution from income to bridge any gap
    between current_balance and the capital needed to reach the target.

    If current_balance already compounds to the gross target by target_date,
    returns 0.0 — no income contribution needed, growth alone is sufficient.

    For recurring targets: gross target includes tax gross-up and principal
    preservation so the cycle can restart after withdrawal.

    Uses the standard PMT formula:
        PMT = r * (FV - PV*(1+r)^n) / ((1+r)^n - 1)
    where r = monthly rate, n = months remaining, PV = current_balance, FV = gross target.
    """
    today = date.today()
    if target_date <= today:
        return 0.0

    gross_target = _compute_gross_target(target_amount, tax_pct, is_recurring, current_balance)

    if current_balance >= gross_target:
        return 0.0

    # Months remaining (fractional)
    days_remaining = (target_date - today).days
    n = days_remaining / _DAYS_PER_MONTH

    if n <= 0:
        return 0.0

    r = annual_growth_rate_pct / 100.0 / 12.0  # monthly rate

    if r == 0.0:
        # Simple linear: no growth
        return (gross_target - current_balance) / n

    # PMT = r * (FV - PV*(1+r)^n) / ((1+r)^n - 1)
    factor = math.pow(1 + r, n)
    numerator = r * (gross_target - current_balance * factor)
    denominator = factor - 1
    if denominator <= 0:
        return 0.0

    return max(0.0, numerator / denominator)


def _build_savings_target_entry(
    item,
    period: str,
    income_after_tax: float,
    tax_pct: float,
    account_annual_return_pct: float = 0.0,
) -> Dict[str, Any]:
    """Build a savings target entry with capital-reservation framing.

    The key metric is `capital_required` — the Present Value that must be held
    in the account TODAY for compound growth to reach the target by the deadline.
    If current_balance >= capital_required, the goal is on track and no income
    contribution is needed. monthly_contribution is only non-zero when the
    current balance is insufficient and income needs to bridge the gap.

    growth_rate priority: item.assumed_growth_rate_pct (explicit override) →
    account_annual_return_pct (derived from live trading returns) → 0.
    """
    target_amount = getattr(item, "savings_target_amount", 0.0) or 0.0
    target_date = getattr(item, "savings_target_date", None)
    current_balance = getattr(item, "savings_current_balance", 0.0) or 0.0
    item_rate = getattr(item, "assumed_growth_rate_pct", None)
    # Use item override if explicitly set; otherwise use live account return
    growth_rate = item_rate if (item_rate is not None and item_rate > 0) else account_annual_return_pct
    effective_rate_source = "override" if (item_rate is not None and item_rate > 0) else "account"
    is_recurring = getattr(item, "savings_is_recurring", False)
    recurrence_months = getattr(item, "savings_recurrence_months", None)

    today = date.today()
    months_remaining = 0
    if target_date and target_date > today:
        months_remaining = round((target_date - today).days / _DAYS_PER_MONTH)

    # Capital required TODAY (PV) for compound growth to reach gross target by deadline.
    capital_required = compute_savings_capital_required(
        target_amount=target_amount,
        target_date=target_date or today,
        annual_growth_rate_pct=growth_rate,
        tax_pct=tax_pct,
        is_recurring=is_recurring,
        current_balance=current_balance,
    )
    capital_gap = max(0.0, capital_required - current_balance)

    # Monthly income contribution needed ONLY if current balance is insufficient.
    # Accounts for tax gross-up and principal preservation (recurring).
    monthly_contribution = compute_monthly_savings_contribution(
        target_amount=target_amount,
        target_date=target_date or today,
        current_balance=current_balance,
        annual_growth_rate_pct=growth_rate,
        tax_pct=tax_pct,
        is_recurring=is_recurring,
    )

    # Normalize monthly contribution to the goal period
    monthly_in_period = normalize_monthly_to_period(monthly_contribution, period)

    savings_pct = min((current_balance / target_amount * 100) if target_amount > 0 else 0.0, 100.0)
    # On-track = current balance already covers the required capital (PV)
    savings_on_track = capital_gap <= 0

    # Determine status based on past due / funded / capital sufficiency
    if target_date and target_date <= today:
        if current_balance >= target_amount:
            status = "funded"
        else:
            status = "past_due"
    elif savings_on_track:
        status = "funded"  # will be "on_track" if not fully funded yet but growing to target
    else:
        status = "pending"  # will be overridden by waterfall coverage check

    return {
        "id": getattr(item, "id", None),
        "name": item.name,
        "category": getattr(item, "category", "Savings"),
        "target_amount": round(target_amount, 2),
        "target_date": target_date.isoformat() if target_date else None,
        "current_balance": round(current_balance, 2),
        "capital_required": round(capital_required, 2),
        "capital_gap": round(capital_gap, 2),
        "savings_pct": round(savings_pct, 1),
        "months_remaining": months_remaining,
        "monthly_contribution": round(monthly_contribution, 2),
        "normalized_amount": round(monthly_in_period, 2),  # period-normalized contribution
        "assumed_growth_rate_pct": growth_rate,
        "growth_rate_source": effective_rate_source,
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
    account_annual_return_pct: float = 0.0,
    account_balance: float = 0.0,
) -> Dict[str, Any]:
    """
    Compute a unified coverage waterfall for expense items and savings targets.

    Items are processed in sort_order (when sort_mode='custom'), so position
    determines priority. Savings targets reserve from the account balance pool;
    expenses consume from the income pool generated by the remaining free capital.

    SAVINGS TARGET model:
        - capital_required = PV(target, growth_rate, n): must be held in account TODAY
        - dynamic_reserved  = min(capital_required, remaining_balance at this position)
        - Items above a savings target have already consumed some balance/income
        - The income generated by the reserved capital is earmarked (not available for expenses)
        - If dynamic_reserved < capital_required → capital_gap > 0 → nothing passes to items below

    EXPENSE model:
        - Consumes from current_income at its position in the waterfall
        - current_income decreases as savings targets above earmark their income portion
    """
    income_after_tax = projected_income * (1 - tax_pct / 100)

    # Income rate: post-tax income per unit of account balance
    # Used to compute how much income is earmarked by each savings reservation
    income_rate = (income_after_tax / account_balance) if account_balance > 0 else 0.0

    # Normalise and sort all items together in a single pass
    all_entries = []
    for item in items:
        item_type = getattr(item, "item_type", "expense") or "expense"
        sort_key = getattr(item, "sort_order", 0) or 0

        if item_type == "savings_target":
            # Savings targets are built later during the waterfall pass (need dynamic_balance)
            all_entries.append({
                "_type": "savings_target",
                "_item": item,
                "sort_order": sort_key,
            })
        else:
            amount_mode = getattr(item, "amount_mode", "fixed") or "fixed"
            pct_of_income = getattr(item, "percent_of_income", None)
            pct_basis = getattr(item, "percent_basis", None)

            if amount_mode == "percent_of_income" and pct_of_income:
                basis = projected_income if pct_basis == "pre_tax" else income_after_tax
                norm_amount = round(pct_of_income / 100.0 * basis, 2)
            else:
                norm_amount = normalize_item_to_period(item, period)

            entry = {
                "_type": "expense",
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
                "sort_order": sort_key,
                "normalized_amount": round(norm_amount, 2),
                "amount_mode": amount_mode,
            }
            if amount_mode == "percent_of_income":
                entry["percent_of_income"] = pct_of_income
                entry["percent_basis"] = pct_basis
            all_entries.append(entry)

    # Sort: custom (sort_order) interleaves savings+expenses by priority.
    # Amount-based sorts keep the original two-pass ordering (expenses first, savings after),
    # since savings targets don't have a meaningful "amount" until the waterfall runs.
    if sort_mode == "custom":
        all_entries.sort(key=lambda x: x.get("sort_order", 0))
    elif sort_mode == "amount_desc":
        # Expenses sorted descending, savings appended after
        all_entries.sort(
            key=lambda x: (1 if x["_type"] == "savings_target" else 0,
                           -x.get("normalized_amount", 0))
        )
    else:  # amount_asc (default)
        all_entries.sort(
            key=lambda x: (1 if x["_type"] == "savings_target" else 0,
                           x.get("normalized_amount", 0))
        )

    # ── Unified waterfall pass ──────────────────────────────────────────────
    # remaining_balance: account capital not yet reserved by savings targets
    # current_income:    post-tax income from the non-reserved capital
    remaining_balance = account_balance
    current_income = income_after_tax
    blocked = False  # True when a savings target is underfunded — nothing passes below
    # True once any expense above is partial or uncovered (income exhausted).
    # A savings target should not reserve capital when higher-priority expenses
    # cannot be covered — those expenses have first claim on all resources.
    has_uncovered_expense_above = False

    normalized = []  # final expense entries
    savings_entries = []  # final savings target entries
    total_expenses = 0.0
    total_savings_contributions = 0.0
    covered_count = 0
    partial_item = None
    next_uncovered_item = None

    for raw in all_entries:
        if raw["_type"] == "savings_target":
            item = raw["_item"]
            entry = _build_savings_target_entry(
                item, period, income_after_tax, tax_pct, account_annual_return_pct
            )
            cap_req = entry["capital_required"]

            if blocked or has_uncovered_expense_above:
                # Either a prior savings target is underfunded, OR income has been
                # exhausted by higher-priority uncovered expenses — don't reserve.
                # A savings target should not claim capital when expenses ranked
                # above it in the priority list cannot be covered.
                dynamic_reserved = 0.0
            else:
                dynamic_reserved = min(cap_req, remaining_balance)

            cap_gap = max(0.0, cap_req - dynamic_reserved)
            entry["dynamic_reserved"] = round(dynamic_reserved, 2)
            entry["capital_gap"] = round(cap_gap, 2)

            # Earmark income from the reserved capital
            income_earmarked = dynamic_reserved * income_rate
            entry["income_earmarked"] = round(income_earmarked, 2)

            remaining_balance -= dynamic_reserved
            current_income -= income_earmarked

            # Monthly contribution needed from INCOME (gap only — reserved balance handles the rest)
            if cap_gap > 0:
                # Recompute PMT against the actual dynamic balance
                from datetime import date as _date
                target_date = getattr(item, "savings_target_date", None)
                monthly_contribution = compute_monthly_savings_contribution(
                    target_amount=getattr(item, "savings_target_amount", 0.0) or 0.0,
                    target_date=target_date or _date.today(),
                    current_balance=dynamic_reserved,
                    annual_growth_rate_pct=entry["assumed_growth_rate_pct"],
                    tax_pct=tax_pct,
                    is_recurring=getattr(item, "savings_is_recurring", False),
                )
                entry["monthly_contribution"] = round(monthly_contribution, 2)
                norm_contrib = normalize_monthly_to_period(monthly_contribution, period)
                entry["normalized_amount"] = round(norm_contrib, 2)
            else:
                entry["monthly_contribution"] = 0.0
                entry["normalized_amount"] = 0.0

            entry["dynamic_on_track"] = cap_gap <= 0

            # Determine coverage status
            if entry.get("status") == "past_due":
                pass
            elif has_uncovered_expense_above or (blocked and dynamic_reserved == 0):
                # Gated by uncovered expenses above (or a prior underfunded savings target)
                entry["status"] = "blocked"
                entry["coverage_pct"] = 0.0
            elif cap_gap <= 0:
                entry["status"] = "funded"
                entry["coverage_pct"] = 100.0
            elif account_balance > 0:
                # Capital-reservation mode: capital insufficient → gate items below
                if dynamic_reserved > 0:
                    entry["status"] = "partial"
                    entry["coverage_pct"] = round(dynamic_reserved / cap_req * 100, 1)
                else:
                    entry["status"] = "uncovered"
                    entry["coverage_pct"] = 0.0
                # Gate: items below see nothing until this capital goal is met
                blocked = True
            else:
                # No account balance context: fall back to income-based coverage
                norm_contrib = entry["normalized_amount"]
                if current_income >= norm_contrib and norm_contrib > 0:
                    entry["status"] = "covered"
                    entry["coverage_pct"] = 100.0
                    current_income -= norm_contrib
                elif current_income > 0 and norm_contrib > 0:
                    entry["status"] = "partial"
                    entry["coverage_pct"] = round(current_income / norm_contrib * 100, 1)
                    entry["shortfall"] = round(norm_contrib - current_income, 2)
                    current_income = 0.0
                elif norm_contrib <= 0:
                    entry["status"] = "funded"
                    entry["coverage_pct"] = 100.0
                else:
                    entry["status"] = "uncovered"
                    entry["coverage_pct"] = 0.0

            total_savings_contributions += entry["normalized_amount"]
            savings_entries.append(entry)

        else:
            entry = {k: v for k, v in raw.items() if not k.startswith("_")}
            amt = entry["normalized_amount"]
            total_expenses += amt

            if blocked:
                entry["status"] = "blocked"
                entry["coverage_pct"] = 0.0
            elif current_income >= amt:
                entry["status"] = "covered"
                entry["coverage_pct"] = 100.0
                current_income -= amt
                covered_count += 1
            elif current_income > 0:
                entry["status"] = "partial"
                entry["coverage_pct"] = round(current_income / amt * 100, 1)
                entry["shortfall"] = round(amt - current_income, 2)
                partial_item = entry
                current_income = 0
                has_uncovered_expense_above = True  # income exhausted mid-item
            else:
                entry["status"] = "uncovered"
                entry["coverage_pct"] = 0.0
                has_uncovered_expense_above = True  # income already gone
                if next_uncovered_item is None and partial_item is not None:
                    next_uncovered_item = entry

            normalized.append(entry)

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
    savings_coverage_pct = (
        min(max(income_after_tax - total_expenses, 0.0) / total_savings_contributions * 100, 100.0)
        if total_savings_contributions > 0 else 100.0
    )
    total_claims = round(total_expenses + total_savings_contributions, 2)

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
        "account_annual_return_pct": round(account_annual_return_pct, 4),
        "free_balance": round(remaining_balance, 2),
        "income_earmarked_for_savings": round(
            sum(e.get("income_earmarked", 0) for e in savings_entries), 2
        ),
    }

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
