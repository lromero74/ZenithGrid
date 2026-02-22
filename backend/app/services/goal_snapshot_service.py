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

    # Get all active goals that support snapshots (not income/expenses)
    result = await db.execute(
        select(ReportGoal).where(
            ReportGoal.user_id == user_id,
            ReportGoal.is_active.is_(True),
            ReportGoal.target_type.notin_(["income", "expenses"]),
        )
    )
    goals = result.scalars().all()

    if not goals:
        return 0

    # Calculate cumulative profit for profit-type goals
    profit_usd = 0.0
    profit_btc = 0.0

    profit_result = await db.execute(
        select(func.sum(Position.profit_usd)).where(
            Position.user_id == user_id,
            Position.status == "closed",
        )
    )
    row = profit_result.one_or_none()
    if row and row[0] is not None:
        profit_usd = row[0]

    btc_profit_result = await db.execute(
        select(func.sum(Position.profit_quote)).where(
            Position.user_id == user_id,
            Position.status == "closed",
            Position.product_id.like("%-BTC"),
        )
    )
    btc_row = btc_profit_result.one_or_none()
    if btc_row and btc_row[0] is not None:
        profit_btc = btc_row[0]

    count = 0
    for goal in goals:
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
    if goal.target_type in ("income", "expenses"):
        logger.info(f"Skipping backfill for {goal.target_type} goal {goal.id}")
        return 0

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
        pos_result = await db.execute(
            select(Position)
            .where(
                Position.user_id == goal.user_id,
                Position.status == "closed",
                Position.closed_at >= start,
                Position.closed_at <= today + timedelta(days=1),
            )
            .order_by(Position.closed_at)
        )
        positions = pos_result.scalars().all()

        # Pre-start cumulative profit
        pre_result = await db.execute(
            select(func.sum(Position.profit_usd))
            .where(
                Position.user_id == goal.user_id,
                Position.status == "closed",
                Position.closed_at < start,
            )
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
    if goal.target_type == "profit":
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
