"""
Goal Progress Snapshot Service

Captures daily progress snapshots for active goals.
Also provides backfill logic from existing AccountValueSnapshot data
and trend data retrieval for charting.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Account,
    AccountValueSnapshot,
    ExpenseItem,
    GoalProgressSnapshot,
    Position,
    ReportGoal,
)

logger = logging.getLogger(__name__)


async def capture_goal_snapshots(
    db: AsyncSession,
    user_id: int,
    current_usd: float,
    current_btc: float,
) -> int:
    """
    Capture daily progress snapshots for all active goals of a user.

    Called during the daily account snapshot cycle.
    Returns the number of snapshots created/updated.
    """
    snapshot_date = datetime.utcnow().replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Get all active goals that support snapshots (not income)
    result = await db.execute(
        select(ReportGoal).where(
            ReportGoal.user_id == user_id,
            ReportGoal.is_active.is_(True),
            ReportGoal.target_type.notin_(["income"]),
        )
    )
    goals = result.scalars().all()

    if not goals:
        return 0

    # Group goals by account_id for efficient profit queries
    account_ids = {g.account_id for g in goals}

    # Pre-compute profits per account_id (None = all accounts)
    profit_cache: dict = {}
    for acct_id in account_ids:
        usd_filters = [
            Position.user_id == user_id,
            Position.status == "closed",
        ]
        btc_filters = [
            Position.user_id == user_id,
            Position.status == "closed",
            Position.product_id.like("%-BTC"),
        ]
        if acct_id is not None:
            usd_filters.append(Position.account_id == acct_id)
            btc_filters.append(Position.account_id == acct_id)

        profit_result = await db.execute(
            select(func.sum(Position.profit_usd)).where(*usd_filters)
        )
        row = profit_result.one_or_none()
        p_usd = (row[0] or 0.0) if row else 0.0

        btc_profit_result = await db.execute(
            select(func.sum(Position.profit_quote)).where(*btc_filters)
        )
        btc_row = btc_profit_result.one_or_none()
        p_btc = (btc_row[0] or 0.0) if btc_row else 0.0

        profit_cache[acct_id] = {"usd": p_usd, "btc": p_btc}

    count = 0
    for goal in goals:
        profits = profit_cache.get(goal.account_id, {"usd": 0.0, "btc": 0.0})
        profit_usd = profits["usd"]
        profit_btc = profits["btc"]

        if goal.target_type == "expenses":
            current_value, target = await _get_expense_snapshot_values(
                db, goal,
            )
        else:
            current_value = _get_current_value_for_goal(
                goal, current_usd, current_btc, profit_usd, profit_btc
            )
            target = _get_target_for_goal(goal)

        progress_pct = (current_value / target * 100) if target > 0 else 0.0
        progress_pct = min(progress_pct, 100.0)

        # Determine on_track
        total_duration = (goal.target_date - goal.start_date).total_seconds()
        elapsed = (datetime.utcnow() - goal.start_date).total_seconds()
        time_pct = (elapsed / total_duration * 100) if total_duration > 0 else 100
        on_track = progress_pct >= time_pct

        # Upsert snapshot
        existing = await db.execute(
            select(GoalProgressSnapshot).where(
                GoalProgressSnapshot.goal_id == goal.id,
                GoalProgressSnapshot.snapshot_date == snapshot_date,
            )
        )
        snap = existing.scalar_one_or_none()

        if snap:
            snap.current_value = current_value
            snap.target_value = target
            snap.progress_pct = round(progress_pct, 2)
            snap.on_track = on_track
        else:
            snap = GoalProgressSnapshot(
                goal_id=goal.id,
                user_id=user_id,
                snapshot_date=snapshot_date,
                current_value=current_value,
                target_value=target,
                progress_pct=round(progress_pct, 2),
                on_track=on_track,
            )
            db.add(snap)

        count += 1

    return count


def _get_current_value_for_goal(
    goal: ReportGoal,
    current_usd: float,
    current_btc: float,
    profit_usd: float,
    profit_btc: float,
) -> float:
    """Get the current value relevant to this goal type."""
    is_btc = goal.target_currency == "BTC"

    if goal.target_type == "balance":
        return current_btc if is_btc else current_usd
    elif goal.target_type == "profit":
        return profit_btc if is_btc else profit_usd
    else:
        # "both" -- use balance as primary
        return current_btc if is_btc else current_usd


def _get_target_for_goal(goal: ReportGoal) -> float:
    """Get the target value for this goal."""
    if goal.target_type == "both":
        return goal.target_balance_value or goal.target_value
    return goal.target_value


async def _get_expense_snapshot_values(
    db: AsyncSession,
    goal: ReportGoal,
) -> tuple:
    """
    Compute snapshot values for an expense-type goal.

    Returns (income_after_tax, total_expenses).
    """
    from app.services.expense_service import compute_expense_coverage

    expense_period = goal.expense_period or "monthly"
    tax_pct = goal.tax_withholding_pct or 0
    period_multipliers = {
        "weekly": 7, "monthly": 30, "quarterly": 91, "yearly": 365,
    }
    period_days = period_multipliers.get(expense_period, 30)

    # Compute daily income from closed positions since goal start
    now = datetime.utcnow()
    days_elapsed = max((now - goal.start_date).days, 1)

    profit_filters = [
        Position.user_id == goal.user_id,
        Position.status == "closed",
        Position.closed_at >= goal.start_date,
        Position.closed_at <= now,
    ]
    if goal.account_id is not None:
        profit_filters.append(Position.account_id == goal.account_id)

    profit_result = await db.execute(
        select(func.sum(Position.profit_usd)).where(*profit_filters)
    )
    row = profit_result.one_or_none()
    total_profit = (row[0] or 0.0) if row else 0.0

    daily_income = total_profit / days_elapsed
    projected_income = daily_income * period_days

    # Load active expense items
    items_result = await db.execute(
        select(ExpenseItem).where(
            ExpenseItem.goal_id == goal.id,
            ExpenseItem.is_active.is_(True),
        ).order_by(ExpenseItem.sort_order, ExpenseItem.created_at)
    )
    expense_items = items_result.scalars().all()

    coverage = compute_expense_coverage(
        expense_items, expense_period, projected_income, tax_pct,
        sort_mode="custom",
    )

    return (coverage["income_after_tax"], coverage["total_expenses"])


async def backfill_goal_snapshots(
    db: AsyncSession,
    goal: ReportGoal,
) -> int:
    """
    Backfill goal progress snapshots from existing AccountValueSnapshot data.

    Creates one snapshot per day from goal.start_date to today,
    using the closest AccountValueSnapshot for each day.

    Returns the number of snapshots created.
    """
    if goal.target_type == "income":
        logger.info(f"Skipping backfill for income goal {goal.id}")
        return 0

    if goal.target_type == "expenses":
        return await _backfill_expense_goal_snapshots(db, goal)

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    start = goal.start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    if start > today:
        return 0

    # Get all account value snapshots for this user from start to today
    snap_result = await db.execute(
        select(AccountValueSnapshot)
        .join(Account, AccountValueSnapshot.account_id == Account.id)
        .where(
            AccountValueSnapshot.user_id == goal.user_id,
            AccountValueSnapshot.snapshot_date >= start,
            AccountValueSnapshot.snapshot_date <= today,
            Account.is_paper_trading.is_(False),
            Account.is_active.is_(True),
        )
        .order_by(AccountValueSnapshot.snapshot_date)
    )
    all_snapshots = snap_result.scalars().all()

    if not all_snapshots:
        logger.info(f"No account snapshots found for goal {goal.id} backfill")
        return 0

    # Group snapshots by date, summing across accounts
    daily_values: Dict[str, Dict[str, float]] = {}
    for snap in all_snapshots:
        date_key = snap.snapshot_date.replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        if date_key not in daily_values:
            daily_values[date_key] = {"usd": 0.0, "btc": 0.0}
        daily_values[date_key]["usd"] += snap.total_value_usd
        daily_values[date_key]["btc"] += snap.total_value_btc

    # For profit goals, get cumulative closed-position profit up to each date
    profit_by_date: Dict[str, Dict[str, float]] = {}
    if goal.target_type in ("profit", "both"):
        bf_pos_filters = [
            Position.user_id == goal.user_id,
            Position.status == "closed",
            Position.closed_at >= start,
            Position.closed_at <= today + timedelta(days=1),
        ]
        if goal.account_id is not None:
            bf_pos_filters.append(Position.account_id == goal.account_id)

        pos_result = await db.execute(
            select(Position)
            .where(*bf_pos_filters)
            .order_by(Position.closed_at)
        )
        positions = pos_result.scalars().all()

        # Pre-start cumulative profit
        bf_pre_filters = [
            Position.user_id == goal.user_id,
            Position.status == "closed",
            Position.closed_at < start,
        ]
        if goal.account_id is not None:
            bf_pre_filters.append(Position.account_id == goal.account_id)

        pre_result = await db.execute(
            select(func.sum(Position.profit_usd))
            .where(*bf_pre_filters)
        )
        pre_row = pre_result.one_or_none()
        cumulative_usd = (pre_row[0] or 0.0) if pre_row else 0.0
        cumulative_btc = 0.0

        current_date = start
        pos_idx = 0
        while current_date <= today:
            while pos_idx < len(positions):
                pos_date = positions[pos_idx].closed_at.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                if pos_date <= current_date:
                    cumulative_usd += positions[pos_idx].profit_usd or 0
                    if (positions[pos_idx].product_id or "").endswith("-BTC"):
                        cumulative_btc += positions[pos_idx].profit_quote or 0
                    pos_idx += 1
                else:
                    break

            date_key = current_date.isoformat()
            profit_by_date[date_key] = {
                "usd": cumulative_usd,
                "btc": cumulative_btc,
            }
            current_date += timedelta(days=1)

    target = _get_target_for_goal(goal)
    is_btc = goal.target_currency == "BTC"

    # Check which dates already have snapshots
    existing_result = await db.execute(
        select(GoalProgressSnapshot.snapshot_date).where(
            GoalProgressSnapshot.goal_id == goal.id,
        )
    )
    existing_dates = {
        row[0].replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        for row in existing_result.fetchall()
    }

    count = 0
    last_known_value = {"usd": 0.0, "btc": 0.0}
    current_date = start

    while current_date <= today:
        date_key = current_date.isoformat()

        # Skip if already exists
        if date_key in existing_dates:
            if date_key in daily_values:
                last_known_value = daily_values[date_key]
            current_date += timedelta(days=1)
            continue

        # Get value for this date
        if date_key in daily_values:
            last_known_value = daily_values[date_key]

        if goal.target_type == "profit":
            if date_key in profit_by_date:
                current_value = (
                    profit_by_date[date_key]["btc"] if is_btc
                    else profit_by_date[date_key]["usd"]
                )
            else:
                current_date += timedelta(days=1)
                continue
        else:
            # balance or both — use account value
            current_value = (
                last_known_value["btc"] if is_btc
                else last_known_value["usd"]
            )

        # Only create if we have a non-zero value
        if current_value == 0.0 and date_key not in daily_values:
            current_date += timedelta(days=1)
            continue

        progress_pct = (current_value / target * 100) if target > 0 else 0.0
        progress_pct = min(progress_pct, 100.0)

        total_duration = (goal.target_date - goal.start_date).total_seconds()
        elapsed = (current_date - goal.start_date).total_seconds()
        time_pct = (elapsed / total_duration * 100) if total_duration > 0 else 100
        on_track = progress_pct >= time_pct

        snap = GoalProgressSnapshot(
            goal_id=goal.id,
            user_id=goal.user_id,
            snapshot_date=current_date,
            current_value=round(current_value, 8 if is_btc else 2),
            target_value=target,
            progress_pct=round(progress_pct, 2),
            on_track=on_track,
        )
        db.add(snap)
        count += 1
        current_date += timedelta(days=1)

    if count > 0:
        await db.flush()
        logger.info(
            f"Backfilled {count} snapshots for goal {goal.id} ({goal.name})"
        )

    return count


async def _backfill_expense_goal_snapshots(
    db: AsyncSession,
    goal: ReportGoal,
) -> int:
    """
    Backfill goal progress snapshots for an expense-type goal.

    For each day from start_date to today, computes income_after_tax
    (from cumulative closed-position profit) vs total_expenses.
    """
    from app.services.expense_service import compute_expense_coverage

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    start = goal.start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    if start > today:
        return 0

    expense_period = goal.expense_period or "monthly"
    tax_pct = goal.tax_withholding_pct or 0
    period_multipliers = {
        "weekly": 7, "monthly": 30, "quarterly": 91, "yearly": 365,
    }
    period_days = period_multipliers.get(expense_period, 30)

    # Load active expense items once (current state)
    items_result = await db.execute(
        select(ExpenseItem).where(
            ExpenseItem.goal_id == goal.id,
            ExpenseItem.is_active.is_(True),
        ).order_by(ExpenseItem.sort_order, ExpenseItem.created_at)
    )
    expense_items = items_result.scalars().all()

    if not expense_items:
        logger.info(f"No expense items for goal {goal.id}, skipping backfill")
        return 0

    # Get all closed positions from start to today for cumulative profit
    pos_filters = [
        Position.user_id == goal.user_id,
        Position.status == "closed",
        Position.closed_at >= start,
        Position.closed_at <= today + timedelta(days=1),
    ]
    if goal.account_id is not None:
        pos_filters.append(Position.account_id == goal.account_id)

    pos_result = await db.execute(
        select(Position)
        .where(*pos_filters)
        .order_by(Position.closed_at)
    )
    positions = pos_result.scalars().all()

    # Pre-start cumulative profit
    pre_filters = [
        Position.user_id == goal.user_id,
        Position.status == "closed",
        Position.closed_at < start,
    ]
    if goal.account_id is not None:
        pre_filters.append(Position.account_id == goal.account_id)

    pre_result = await db.execute(
        select(func.sum(Position.profit_usd)).where(*pre_filters)
    )
    pre_row = pre_result.one_or_none()
    cumulative_profit = (pre_row[0] or 0.0) if pre_row else 0.0

    # Build cumulative profit by date
    profit_by_date: Dict[str, float] = {}
    pos_idx = 0
    current_date = start
    while current_date <= today:
        while pos_idx < len(positions):
            pos_date = positions[pos_idx].closed_at.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            if pos_date <= current_date:
                cumulative_profit += positions[pos_idx].profit_usd or 0
                pos_idx += 1
            else:
                break
        profit_by_date[current_date.isoformat()] = cumulative_profit
        current_date += timedelta(days=1)

    # Check which dates already have snapshots
    existing_result = await db.execute(
        select(GoalProgressSnapshot.snapshot_date).where(
            GoalProgressSnapshot.goal_id == goal.id,
        )
    )
    existing_dates = {
        row[0].replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        for row in existing_result.fetchall()
    }

    total_duration = (goal.target_date - goal.start_date).total_seconds()

    count = 0
    current_date = start
    while current_date <= today:
        date_key = current_date.isoformat()

        if date_key in existing_dates:
            current_date += timedelta(days=1)
            continue

        cum_profit = profit_by_date.get(date_key, 0.0)
        days_elapsed = max((current_date - start).days, 1)
        daily_income = cum_profit / days_elapsed
        projected_income = daily_income * period_days

        coverage = compute_expense_coverage(
            expense_items, expense_period, projected_income, tax_pct,
            sort_mode="custom",
        )

        income_after_tax = coverage["income_after_tax"]
        total_expenses = coverage["total_expenses"]
        coverage_pct = coverage["coverage_pct"]

        elapsed = (current_date - goal.start_date).total_seconds()
        time_pct = (elapsed / total_duration * 100) if total_duration > 0 else 100
        on_track = coverage_pct >= time_pct

        snap = GoalProgressSnapshot(
            goal_id=goal.id,
            user_id=goal.user_id,
            snapshot_date=current_date,
            current_value=round(income_after_tax, 2),
            target_value=round(total_expenses, 2),
            progress_pct=round(min(coverage_pct, 100.0), 2),
            on_track=on_track,
        )
        db.add(snap)
        count += 1
        current_date += timedelta(days=1)

    if count > 0:
        await db.flush()
        logger.info(
            f"Backfilled {count} expense snapshots for goal {goal.id} "
            f"({goal.name})"
        )

    return count


async def get_goal_trend_data(
    db: AsyncSession,
    goal: ReportGoal,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Get trend data for a goal, suitable for charting.

    Returns dict with goal metadata, ideal start/end values,
    and an array of data points for recharts.
    """
    start = from_date or goal.start_date
    end = to_date or min(datetime.utcnow(), goal.target_date)

    # Query snapshots
    filters = [
        GoalProgressSnapshot.goal_id == goal.id,
        GoalProgressSnapshot.snapshot_date >= start,
        GoalProgressSnapshot.snapshot_date <= end,
    ]
    result = await db.execute(
        select(GoalProgressSnapshot)
        .where(and_(*filters))
        .order_by(GoalProgressSnapshot.snapshot_date)
    )
    snapshots = result.scalars().all()

    # Compute ideal start value
    if goal.target_type in ("profit", "expenses"):
        ideal_start = 0.0
    else:
        ideal_start = snapshots[0].current_value if snapshots else 0.0

    target = _get_target_for_goal(goal)
    total_duration = (goal.target_date - goal.start_date).total_seconds()

    is_btc = goal.target_currency == "BTC"
    precision = 8 if is_btc else 2

    data_points = []
    for snap in snapshots:
        elapsed = (snap.snapshot_date - goal.start_date).total_seconds()
        if total_duration > 0:
            fraction = elapsed / total_duration
        else:
            fraction = 1.0
        fraction = min(max(fraction, 0.0), 1.0)
        ideal_value = ideal_start + (target - ideal_start) * fraction

        data_points.append({
            "date": snap.snapshot_date.strftime("%Y-%m-%d"),
            "current_value": round(snap.current_value, precision),
            "ideal_value": round(ideal_value, precision),
            "progress_pct": snap.progress_pct,
            "on_track": snap.on_track,
        })

    # Add target endpoint so the ideal line shows the full trajectory
    target_date_str = goal.target_date.strftime("%Y-%m-%d")
    if data_points and data_points[-1]["date"] != target_date_str:
        data_points.append({
            "date": target_date_str,
            "current_value": None,
            "ideal_value": round(target, precision),
            "progress_pct": None,
            "on_track": None,
        })

    return {
        "goal": {
            "id": goal.id,
            "name": goal.name,
            "target_type": goal.target_type,
            "target_currency": goal.target_currency,
            "target_value": target,
            "start_date": goal.start_date.strftime("%Y-%m-%d"),
            "target_date": goal.target_date.strftime("%Y-%m-%d"),
        },
        "ideal_start_value": round(ideal_start, precision),
        "ideal_end_value": target,
        "data_points": data_points,
    }


def compute_horizon_date(
    data_points: list,
    target_date_str: str,
    chart_horizon: str = "auto",
) -> str:
    """Compute the chart's visible end date based on horizon setting.

    Returns a date string (YYYY-MM-DD) for the rightmost point of the chart.
    """
    if not data_points:
        return target_date_str

    target_date = datetime.strptime(target_date_str, "%Y-%m-%d")

    # Find last real data date
    real_dates = [
        datetime.strptime(p["date"], "%Y-%m-%d")
        for p in data_points if p.get("current_value") is not None
    ]
    if not real_dates:
        # All points are ideal-only projections; use last point date
        real_dates = [datetime.strptime(data_points[-1]["date"], "%Y-%m-%d")]

    last_data_date = max(real_dates)
    first_date = datetime.strptime(data_points[0]["date"], "%Y-%m-%d")

    if chart_horizon == "full":
        return target_date_str

    if chart_horizon != "auto":
        # Custom integer days
        try:
            days = int(chart_horizon)
            horizon = last_data_date + timedelta(days=days)
            return min(horizon, target_date).strftime("%Y-%m-%d")
        except ValueError:
            pass  # Fall through to auto

    # Auto: 1/3 rule
    data_span = (last_data_date - first_date).days
    look_ahead = max(data_span / 2, 7)
    horizon = last_data_date + timedelta(days=int(look_ahead))
    return min(horizon, target_date).strftime("%Y-%m-%d")


def clip_trend_data(trend_data: dict, horizon_date_str: str) -> dict:
    """Return a copy of trend_data with data_points clipped to horizon_date.

    Keeps one ideal-only point at or after the horizon for line continuity.
    """
    data_points = trend_data.get("data_points", [])
    if not data_points:
        return {**trend_data, "data_points": []}

    horizon = datetime.strptime(horizon_date_str, "%Y-%m-%d")

    # Separate real points (with current_value) and ideal-only endpoints
    clipped = []
    for p in data_points:
        p_date = datetime.strptime(p["date"], "%Y-%m-%d")
        if p_date <= horizon:
            clipped.append(p)
        elif p.get("current_value") is None:
            # Keep the first ideal-only point beyond horizon for line continuity
            if not clipped or clipped[-1].get("current_value") is not None:
                clipped.append(p)
            break  # Only keep one
        # Skip real data points beyond horizon

    # If the last point is a real data point, add an ideal endpoint at horizon
    # for line continuity (interpolated from original ideal trajectory)
    if clipped and clipped[-1].get("current_value") is not None:
        # Find the target endpoint from original data
        ideal_endpoints = [p for p in data_points if p.get("current_value") is None]
        if ideal_endpoints:
            clipped.append(ideal_endpoints[-1])

    result = {**trend_data, "data_points": list(clipped)}
    return result
