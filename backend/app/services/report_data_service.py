"""
Report Data Service

Gathers metrics for report generation:
- Account value from snapshots
- Closed positions and profit calculations
- Goal progress computation
- Prior period data for comparisons
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccountValueSnapshot, Position, Report, ReportGoal

logger = logging.getLogger(__name__)


async def gather_report_data(
    db: AsyncSession,
    user_id: int,
    account_id: Optional[int],
    period_start: datetime,
    period_end: datetime,
    goals: List[ReportGoal],
) -> Dict[str, Any]:
    """
    Gather all metrics for a report period.

    Args:
        db: Database session
        user_id: User ID
        account_id: Specific account ID, or None for all accounts
        period_start: Start of the report period
        period_end: End of the report period
        goals: Goals to include in the report

    Returns:
        Dictionary of all report metrics
    """
    # Get account value at period end (latest snapshot <= period_end)
    end_value = await _get_account_value_at(db, user_id, account_id, period_end)
    # Get account value at period start (latest snapshot <= period_start)
    start_value = await _get_account_value_at(db, user_id, account_id, period_start)

    # Get closed positions in this period
    pos_filters = [
        Position.user_id == user_id,
        Position.status == "closed",
        Position.closed_at >= period_start,
        Position.closed_at <= period_end,
    ]
    if account_id:
        pos_filters.append(Position.account_id == account_id)

    result = await db.execute(select(Position).where(and_(*pos_filters)))
    closed_positions = result.scalars().all()

    # Calculate trade stats
    total_trades = len(closed_positions)
    winning_trades = sum(1 for p in closed_positions if (p.profit_usd or 0) > 0)
    losing_trades = sum(1 for p in closed_positions if (p.profit_usd or 0) < 0)
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

    # Calculate period profit
    period_profit_usd = sum(p.profit_usd or 0 for p in closed_positions)
    period_profit_btc = sum(
        p.profit_quote or 0 for p in closed_positions
        if p.get_quote_currency() == "BTC"
    )

    # Compute goal progress
    goal_data = []
    for goal in goals:
        goal_progress = compute_goal_progress(
            goal,
            current_usd=end_value["usd"],
            current_btc=end_value["btc"],
            period_profit_usd=period_profit_usd,
            period_profit_btc=period_profit_btc,
        )
        goal_data.append(goal_progress)

    return {
        "account_value_usd": end_value["usd"],
        "account_value_btc": end_value["btc"],
        "period_start_value_usd": start_value["usd"],
        "period_start_value_btc": start_value["btc"],
        "period_profit_usd": round(period_profit_usd, 2),
        "period_profit_btc": round(period_profit_btc, 8),
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": round(win_rate, 1),
        "goals": goal_data,
        "prior_period": None,  # Filled in by caller if prior report exists
    }


async def get_prior_period_data(
    db: AsyncSession,
    schedule_id: int,
    current_period_start: datetime,
) -> Optional[Dict[str, Any]]:
    """
    Get report_data from the most recent prior report for the same schedule.

    Returns None if no prior report exists.
    """
    result = await db.execute(
        select(Report)
        .where(
            and_(
                Report.schedule_id == schedule_id,
                Report.period_end < current_period_start,
            )
        )
        .order_by(Report.period_end.desc())
        .limit(1)
    )
    prior_report = result.scalar_one_or_none()

    if prior_report and prior_report.report_data:
        return prior_report.report_data
    return None


def compute_goal_progress(
    goal: ReportGoal,
    current_usd: float,
    current_btc: float,
    period_profit_usd: float,
    period_profit_btc: float,
) -> Dict[str, Any]:
    """
    Compute progress towards a goal.

    Returns dict with goal_id, name, target_value, current_value, progress_pct, on_track.
    """
    is_btc = goal.target_currency == "BTC"
    current_value = current_btc if is_btc else current_usd

    if goal.target_type == "balance":
        target = goal.target_value
        progress = (current_value / target * 100) if target > 0 else 0
    elif goal.target_type == "profit":
        target = goal.target_value
        profit = period_profit_btc if is_btc else period_profit_usd
        progress = (profit / target * 100) if target > 0 else 0
        current_value = profit
    else:
        # "both" — use balance as primary progress indicator
        target = goal.target_balance_value or goal.target_value
        progress = (current_value / target * 100) if target > 0 else 0

    # Check if on track based on time elapsed
    now = datetime.utcnow()
    total_duration = (goal.target_date - goal.start_date).total_seconds()
    elapsed = (now - goal.start_date).total_seconds()
    time_pct = (elapsed / total_duration * 100) if total_duration > 0 else 100
    on_track = progress >= time_pct  # Progress % >= Time elapsed %

    return {
        "goal_id": goal.id,
        "name": goal.name,
        "target_type": goal.target_type,
        "target_currency": goal.target_currency,
        "target_value": goal.target_value,
        "current_value": round(current_value, 8 if is_btc else 2),
        "progress_pct": round(min(progress, 100), 1),
        "on_track": on_track,
        "time_elapsed_pct": round(min(time_pct, 100), 1),
    }


async def _get_account_value_at(
    db: AsyncSession,
    user_id: int,
    account_id: Optional[int],
    at_date: datetime,
) -> Dict[str, float]:
    """Get the closest account value snapshot on or before at_date."""
    filters = [
        AccountValueSnapshot.user_id == user_id,
        AccountValueSnapshot.snapshot_date <= at_date,
    ]
    if account_id:
        filters.append(AccountValueSnapshot.account_id == account_id)

    if account_id:
        # Single account — get latest snapshot
        result = await db.execute(
            select(AccountValueSnapshot)
            .where(and_(*filters))
            .order_by(AccountValueSnapshot.snapshot_date.desc())
            .limit(1)
        )
        snapshot = result.scalar_one_or_none()
        if snapshot:
            return {"usd": snapshot.total_value_usd, "btc": snapshot.total_value_btc}
    else:
        # All accounts — sum the latest snapshot per account
        # Get the max snapshot_date per account that's <= at_date
        subq = (
            select(
                AccountValueSnapshot.account_id,
                func.max(AccountValueSnapshot.snapshot_date).label("max_date"),
            )
            .where(
                AccountValueSnapshot.user_id == user_id,
                AccountValueSnapshot.snapshot_date <= at_date,
            )
            .group_by(AccountValueSnapshot.account_id)
            .subquery()
        )
        result = await db.execute(
            select(
                func.sum(AccountValueSnapshot.total_value_usd),
                func.sum(AccountValueSnapshot.total_value_btc),
            )
            .join(
                subq,
                and_(
                    AccountValueSnapshot.account_id == subq.c.account_id,
                    AccountValueSnapshot.snapshot_date == subq.c.max_date,
                ),
            )
            .where(AccountValueSnapshot.user_id == user_id)
        )
        row = result.one_or_none()
        if row and row[0] is not None:
            return {"usd": row[0], "btc": row[1]}

    return {"usd": 0.0, "btc": 0.0}
