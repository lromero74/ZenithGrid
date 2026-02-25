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

from app.models import (
    Account, AccountTransfer, AccountValueSnapshot, Bot, Position, Report,
    ReportGoal,
)

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

    # Collect bot strategy context for AI analysis
    bot_ids = list({p.bot_id for p in closed_positions if p.bot_id})
    bot_strategies = []
    if bot_ids:
        bot_result = await db.execute(
            select(Bot).where(Bot.id.in_(bot_ids))
        )
        bots = {b.id: b for b in bot_result.scalars().all()}
        for bid in bot_ids:
            bot = bots.get(bid)
            if not bot:
                continue
            cfg = bot.strategy_config or {}
            pairs = bot.product_ids or ([bot.product_id] if bot.product_id else [])
            # Count trades per bot in this period
            bot_trades = sum(1 for p in closed_positions if p.bot_id == bid)
            bot_wins = sum(
                1 for p in closed_positions
                if p.bot_id == bid and (p.profit_usd or 0) > 0
            )
            bot_strategies.append({
                "name": bot.name,
                "strategy_type": bot.strategy_type,
                "pairs": pairs,
                "config": cfg,
                "trades_in_period": bot_trades,
                "wins_in_period": bot_wins,
            })

    # Compute goal progress — use the report's period bounds for lookback
    goal_data = []
    for goal in goals:
        goal_progress = await compute_goal_progress(
            db,
            goal,
            current_usd=end_value["usd"],
            current_btc=end_value["btc"],
            period_profit_usd=period_profit_usd,
            period_profit_btc=period_profit_btc,
            period_start=period_start,
            period_end=period_end,
            account_id=account_id,
        )
        goal_data.append(goal_progress)

    # Query deposits/withdrawals in this period
    transfer_filters = [
        AccountTransfer.user_id == user_id,
        AccountTransfer.occurred_at >= period_start,
        AccountTransfer.occurred_at <= period_end,
    ]
    if account_id:
        transfer_filters.append(AccountTransfer.account_id == account_id)

    transfer_result = await db.execute(
        select(AccountTransfer).where(and_(*transfer_filters))
    )
    all_transfers = transfer_result.scalars().all()

    # Serialize individual transfer records (most recent first)
    sorted_transfers = sorted(
        all_transfers,
        key=lambda t: t.occurred_at or datetime.min,
        reverse=True,
    )
    transfer_records = [
        {
            "date": t.occurred_at.strftime("%Y-%m-%d") if t.occurred_at else "",
            "type": t.transfer_type,
            "amount_usd": round(t.amount_usd or 0, 2),
            "currency": t.currency or "USD",
            "source": t.source or "unknown",
            "original_type": t.original_type,
        }
        for t in sorted_transfers
    ]

    total_deposits_usd = sum(
        t.amount_usd or 0 for t in all_transfers
        if t.transfer_type == "deposit"
    )
    total_withdrawals_usd = sum(
        t.amount_usd or 0 for t in all_transfers
        if t.transfer_type == "withdrawal"
    )
    net_deposits_usd = round(total_deposits_usd - total_withdrawals_usd, 2)

    # Native-currency accounting: compute implied net deposits per currency
    # in native units, then combine. BTC price movements cancel out in
    # BTC terms, preventing phantom deposits/withdrawals.
    account_growth_usd = end_value["usd"] - start_value["usd"]

    # Realized profit from USD-pair positions only
    realized_profit_usd_pairs = sum(
        p.profit_usd or 0 for p in closed_positions
        if p.get_quote_currency() != "BTC"
    )

    # Extract portion data from start/end snapshots
    start_btc = start_value.get("btc_portion_btc")
    end_btc = end_value.get("btc_portion_btc")
    start_usd_portion = start_value.get("usd_portion_usd")
    end_usd_portion = end_value.get("usd_portion_usd")
    end_btc_price = end_value.get("btc_usd_price")
    start_btc_price = start_value.get("btc_usd_price")

    market_value_effect_usd = None
    unrealized_pnl_change_usd = None

    if (start_btc is not None and end_btc is not None
            and start_usd_portion is not None and end_usd_portion is not None
            and end_btc_price is not None):
        # Native-currency accounting per currency
        btc_implied_deposit = (end_btc - start_btc) - period_profit_btc
        usd_implied_deposit = (end_usd_portion - start_usd_portion) - realized_profit_usd_pairs

        # Subtract unrealized PnL changes if available (isolate actual deposits)
        start_upnl_usd = start_value.get("unrealized_pnl_usd")
        end_upnl_usd = end_value.get("unrealized_pnl_usd")
        start_upnl_btc = start_value.get("unrealized_pnl_btc")
        end_upnl_btc = end_value.get("unrealized_pnl_btc")

        if (start_upnl_usd is not None and end_upnl_usd is not None):
            usd_upnl_delta = end_upnl_usd - start_upnl_usd
            usd_implied_deposit -= usd_upnl_delta
            # Track total unrealized PnL change in USD
            unrealized_pnl_change_usd = round(usd_upnl_delta, 2)
        if (start_upnl_btc is not None and end_upnl_btc is not None):
            btc_upnl_delta = end_upnl_btc - start_upnl_btc
            btc_implied_deposit -= btc_upnl_delta
            # Add BTC unrealized PnL change converted to USD
            btc_upnl_usd = round(btc_upnl_delta * end_btc_price, 2)
            if unrealized_pnl_change_usd is not None:
                unrealized_pnl_change_usd = round(
                    unrealized_pnl_change_usd + btc_upnl_usd, 2
                )
            else:
                unrealized_pnl_change_usd = btc_upnl_usd

        # Combine: BTC deposits valued at end-of-period price
        implied_net_deposits = round(
            btc_implied_deposit * end_btc_price + usd_implied_deposit, 2
        )

        # Market Value Effect: how much USD value changed from BTC price alone
        if start_btc_price is not None:
            market_value_effect_usd = round(
                start_btc * (end_btc_price - start_btc_price), 2
            )
    else:
        # Fallback for old snapshots without portion data
        implied_net_deposits = round(account_growth_usd - period_profit_usd, 2)

    if not all_transfers and abs(implied_net_deposits) >= 0.01:
        # No transfer records — use the implied value
        net_deposits_usd = implied_net_deposits
        deposits_source = "implied"
    else:
        deposits_source = "transfers"

    # True trading-driven account growth = (end - start) - net deposits
    adjusted_growth_usd = round(account_growth_usd - net_deposits_usd, 2)

    # Trading summary for Capital Movements section
    trade_summary = {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "net_profit_usd": round(period_profit_usd, 2),
    }

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
        # Deposit/withdrawal data
        "net_deposits_usd": net_deposits_usd,
        "total_deposits_usd": round(total_deposits_usd, 2),
        "total_withdrawals_usd": round(total_withdrawals_usd, 2),
        "adjusted_account_growth_usd": adjusted_growth_usd,
        "transfer_count": len(all_transfers),
        "deposits_source": deposits_source,
        "transfer_records": transfer_records,
        "trade_summary": trade_summary,
        "bot_strategies": bot_strategies,
        "market_value_effect_usd": market_value_effect_usd,
        "unrealized_pnl_change_usd": unrealized_pnl_change_usd,
        "start_btc_usd_price": start_btc_price,
        "end_btc_usd_price": end_btc_price,
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


async def compute_goal_progress(
    db: AsyncSession,
    goal: ReportGoal,
    current_usd: float,
    current_btc: float,
    period_profit_usd: float,
    period_profit_btc: float,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
    account_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Compute progress towards a goal.

    For income goals, queries closed positions to calculate income rate.
    The lookback window comes from the schedule's period bounds
    (period_start/period_end), not from goal.lookback_days.
    """
    if goal.target_type == "income":
        return await _compute_income_goal_progress(
            db, goal, current_usd, current_btc,
            period_start, period_end, account_id,
        )

    if goal.target_type == "expenses":
        return await _compute_expenses_goal_progress(
            db, goal, current_usd, current_btc,
            period_start, period_end, account_id,
        )

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


async def _compute_income_goal_progress(
    db: AsyncSession,
    goal: ReportGoal,
    current_usd: float,
    current_btc: float,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
    account_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Compute income goal progress by analyzing closed position profits.

    The lookback window is determined by the schedule's period bounds
    (period_start/period_end). Calculates daily income rate from trades
    within that window, then projects income for the goal's period.
    """
    is_btc = goal.target_currency == "BTC"
    account_value = current_btc if is_btc else current_usd
    target = goal.target_value

    period_multipliers = {
        "daily": 1,
        "weekly": 7,
        "monthly": 30,
        "yearly": 365,
    }
    period_days = period_multipliers.get(goal.income_period or "monthly", 30)

    # Use the schedule's period bounds as the lookback window
    now = datetime.utcnow()
    lookback_start = period_start or goal.start_date
    lookback_end = period_end or now

    lookback_days_actual = max((lookback_end - lookback_start).days, 1)

    # Query closed positions within the lookback window
    pos_filters = [
        Position.user_id == goal.user_id,
        Position.status == "closed",
        Position.closed_at >= lookback_start,
        Position.closed_at <= lookback_end,
    ]
    if account_id:
        pos_filters.append(Position.account_id == account_id)
    result = await db.execute(select(Position).where(and_(*pos_filters)))
    closed_positions = result.scalars().all()

    # Sum profits in the appropriate currency
    if is_btc:
        total_profit = sum(
            p.profit_quote or 0 for p in closed_positions
            if p.get_quote_currency() == "BTC"
        )
    else:
        total_profit = sum(p.profit_usd or 0 for p in closed_positions)

    sample_trades = len(closed_positions)

    # Calculate daily income rate
    daily_income = total_profit / lookback_days_actual if lookback_days_actual > 0 else 0

    # Linear projection
    projected_linear = daily_income * period_days

    # Compound projection
    projected_compound = 0.0
    deposit_needed_linear = None
    deposit_needed_compound = None

    if account_value > 0 and daily_income > 0:
        daily_return_rate = daily_income / account_value
        projected_compound = account_value * (
            (1 + daily_return_rate) ** period_days - 1
        )

        # Deposit needed (linear): extra capital so that rate * period_days >= target
        if projected_linear < target and daily_income > 0:
            # Need: (daily_income / account_value) * (account_value + deposit) * period_days = target
            # deposit = (target / (period_days * daily_return_rate)) - account_value
            needed = (target / (period_days * daily_return_rate)) - account_value
            deposit_needed_linear = round(max(needed, 0), 8 if is_btc else 2)

        # Deposit needed (compound): target / ((1+r)^n - 1) - account_value
        compound_factor = (1 + daily_return_rate) ** period_days - 1
        if compound_factor > 0 and projected_compound < target:
            needed = (target / compound_factor) - account_value
            deposit_needed_compound = round(max(needed, 0), 8 if is_btc else 2)
    elif daily_income <= 0 and target > 0:
        # No positive income — can't project, deposit_needed is N/A
        deposit_needed_linear = None
        deposit_needed_compound = None

    precision = 8 if is_btc else 2
    progress = (projected_linear / target * 100) if target > 0 else 0
    on_track = projected_linear >= target

    # Time elapsed (same as other goals)
    total_duration = (goal.target_date - goal.start_date).total_seconds()
    elapsed = (now - goal.start_date).total_seconds()
    time_pct = (elapsed / total_duration * 100) if total_duration > 0 else 100

    return {
        "goal_id": goal.id,
        "name": goal.name,
        "target_type": "income",
        "target_currency": goal.target_currency,
        "target_value": goal.target_value,
        "current_value": round(projected_linear, precision),
        "progress_pct": round(min(progress, 100), 1),
        "on_track": on_track,
        "time_elapsed_pct": round(min(time_pct, 100), 1),
        # Income-specific fields
        "income_period": goal.income_period,
        "current_daily_income": round(daily_income, precision),
        "projected_income_linear": round(projected_linear, precision),
        "projected_income_compound": round(projected_compound, precision),
        "deposit_needed_linear": deposit_needed_linear,
        "deposit_needed_compound": deposit_needed_compound,
        "lookback_days_used": lookback_days_actual,
        "sample_trades": sample_trades,
    }


async def _compute_expenses_goal_progress(
    db: AsyncSession,
    goal: ReportGoal,
    current_usd: float,
    current_btc: float,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
    account_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Compute expenses goal progress by analyzing income vs expense items.

    Reuses the same income calculation logic as income goals, then runs
    the coverage waterfall from expense_service.
    """
    from app.models import ExpenseItem
    from app.services.expense_service import compute_expense_coverage

    is_btc = goal.target_currency == "BTC"
    account_value = current_btc if is_btc else current_usd
    expense_period = goal.expense_period or "monthly"
    tax_pct = goal.tax_withholding_pct or 0

    period_multipliers = {
        "weekly": 7,
        "monthly": 30,
        "quarterly": 91,
        "yearly": 365,
    }
    period_days = period_multipliers.get(expense_period, 30)

    # Calculate income using same logic as income goals
    now = datetime.utcnow()
    lookback_start = period_start or goal.start_date
    lookback_end = period_end or now
    lookback_days_actual = max((lookback_end - lookback_start).days, 1)

    pos_filters = [
        Position.user_id == goal.user_id,
        Position.status == "closed",
        Position.closed_at >= lookback_start,
        Position.closed_at <= lookback_end,
    ]
    if account_id:
        pos_filters.append(Position.account_id == account_id)
    result = await db.execute(select(Position).where(and_(*pos_filters)))
    closed_positions = result.scalars().all()

    if is_btc:
        total_profit = sum(
            p.profit_quote or 0 for p in closed_positions
            if p.get_quote_currency() == "BTC"
        )
    else:
        total_profit = sum(p.profit_usd or 0 for p in closed_positions)

    sample_trades = len(closed_positions)
    daily_income = total_profit / lookback_days_actual if lookback_days_actual > 0 else 0
    projected_income = daily_income * period_days

    # Load active expense items (sorted by user-defined order)
    items_result = await db.execute(
        select(ExpenseItem).where(
            ExpenseItem.goal_id == goal.id,
            ExpenseItem.is_active.is_(True),
        ).order_by(ExpenseItem.sort_order, ExpenseItem.created_at)
    )
    expense_items = items_result.scalars().all()

    # Run coverage waterfall using user-defined order
    coverage = compute_expense_coverage(
        expense_items, expense_period, projected_income, tax_pct,
        sort_mode="custom",
    )

    # Compound projection (same formula as income goal)
    projected_income_compound = 0.0
    deposit_needed_compound = None
    daily_return_rate = 0.0
    if account_value > 0 and daily_income > 0:
        daily_return_rate = daily_income / account_value
        projected_income_compound = account_value * (
            (1 + daily_return_rate) ** period_days - 1
        )

    # Deposit needed: how much additional capital to generate enough
    # after-tax income to cover the shortfall, based on past return rate.
    # Formula: shortfall / ((1 - tax_pct/100) * daily_return_rate * period_days)
    deposit_needed = None
    deposit_partial = None
    deposit_next = None
    if account_value > 0 and daily_income > 0:
        after_tax_factor = (1 - tax_pct / 100) if tax_pct < 100 else 0
        denominator = daily_return_rate * period_days * after_tax_factor
        if denominator > 0:
            if coverage["shortfall"] > 0:
                deposit_needed = round(
                    coverage["shortfall"] / denominator,
                    8 if is_btc else 2,
                )
            # Per-item deposits
            partial_short = coverage.get("partial_item_shortfall")
            if partial_short:
                deposit_partial = round(partial_short / denominator, 8 if is_btc else 2)
            next_amt = coverage.get("next_uncovered_amount")
            if next_amt:
                deposit_next = round(next_amt / denominator, 8 if is_btc else 2)

        # Deposit needed (compound): target / ((1+r)^n - 1) - account_value
        compound_factor = (1 + daily_return_rate) ** period_days - 1
        total_expenses = coverage.get("total_expenses", 0)
        if compound_factor > 0 and after_tax_factor > 0 and total_expenses > 0:
            compound_income_at = projected_income_compound * after_tax_factor
            if compound_income_at < total_expenses:
                needed = (
                    total_expenses / (compound_factor * after_tax_factor)
                ) - account_value
                deposit_needed_compound = round(
                    max(needed, 0), 8 if is_btc else 2,
                )

    precision = 8 if is_btc else 2
    progress_pct = coverage["coverage_pct"]
    on_track = progress_pct >= 100.0

    return {
        "goal_id": goal.id,
        "name": goal.name,
        "target_type": "expenses",
        "target_currency": goal.target_currency,
        "target_value": goal.target_value,
        "current_value": round(coverage["income_after_tax"], precision),
        "progress_pct": round(min(progress_pct, 100), 1),
        "on_track": on_track,
        "time_elapsed_pct": 0,  # Not time-based
        # Expenses-specific fields
        "expense_period": expense_period,
        "tax_withholding_pct": tax_pct,
        "expense_coverage": coverage,
        "projected_income": round(projected_income, precision),
        "current_daily_income": round(daily_income, precision),
        "projected_income_compound": round(projected_income_compound, precision),
        "deposit_needed": deposit_needed,
        "deposit_needed_compound": deposit_needed_compound,
        "deposit_partial": deposit_partial,
        "deposit_next": deposit_next,
        "daily_return_rate": round(daily_return_rate, 6) if account_value > 0 else None,
        "lookback_days_used": lookback_days_actual,
        "sample_trades": sample_trades,
    }


async def _get_account_value_at(
    db: AsyncSession,
    user_id: int,
    account_id: Optional[int],
    at_date: datetime,
) -> Dict[str, Any]:
    """Get the closest account value snapshot on or before at_date.

    Returns dict with usd, btc, plus expanded native-currency fields:
    btc_portion_btc, usd_portion_usd, unrealized_pnl_usd,
    unrealized_pnl_btc, btc_usd_price.
    """
    default = {
        "usd": 0.0, "btc": 0.0,
        "btc_portion_btc": None, "usd_portion_usd": None,
        "unrealized_pnl_usd": None, "unrealized_pnl_btc": None,
        "btc_usd_price": None,
    }

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
            return _enrich_snapshot_data({
                "usd": snapshot.total_value_usd,
                "btc": snapshot.total_value_btc,
                "btc_portion_btc": snapshot.btc_portion_btc,
                "usd_portion_usd": snapshot.usd_portion_usd,
                "unrealized_pnl_usd": snapshot.unrealized_pnl_usd,
                "unrealized_pnl_btc": snapshot.unrealized_pnl_btc,
                "btc_usd_price": snapshot.btc_usd_price,
            })
    else:
        # All accounts — sum the latest snapshot per account
        # Exclude paper trading and inactive accounts (matches account_snapshot_service)
        subq = (
            select(
                AccountValueSnapshot.account_id,
                func.max(AccountValueSnapshot.snapshot_date).label("max_date"),
            )
            .join(Account, AccountValueSnapshot.account_id == Account.id)
            .where(
                AccountValueSnapshot.user_id == user_id,
                AccountValueSnapshot.snapshot_date <= at_date,
                Account.is_paper_trading.is_(False),
                Account.is_active.is_(True),
            )
            .group_by(AccountValueSnapshot.account_id)
            .subquery()
        )
        result = await db.execute(
            select(
                func.sum(AccountValueSnapshot.total_value_usd),
                func.sum(AccountValueSnapshot.total_value_btc),
                func.sum(AccountValueSnapshot.btc_portion_btc),
                func.sum(AccountValueSnapshot.usd_portion_usd),
                func.sum(AccountValueSnapshot.unrealized_pnl_usd),
                func.sum(AccountValueSnapshot.unrealized_pnl_btc),
                func.max(AccountValueSnapshot.btc_usd_price),
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
            return _enrich_snapshot_data({
                "usd": row[0], "btc": row[1],
                "btc_portion_btc": row[2],
                "usd_portion_usd": row[3],
                "unrealized_pnl_usd": row[4],
                "unrealized_pnl_btc": row[5],
                "btc_usd_price": row[6],
            })

    return default


def _enrich_snapshot_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Derive btc_usd_price from snapshot totals when not stored directly.

    For snapshots captured before v2.55.0, btc_usd_price is NULL.
    We can derive it: btc_price = (total_usd - usd_portion) / btc_portion.
    """
    if (data["btc_usd_price"] is None
            and data.get("btc_portion_btc") is not None
            and data.get("usd_portion_usd") is not None
            and data["btc_portion_btc"] > 0):
        btc_value_usd = data["usd"] - data["usd_portion_usd"]
        data["btc_usd_price"] = round(
            btc_value_usd / data["btc_portion_btc"], 2
        )
    return data
