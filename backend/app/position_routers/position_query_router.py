"""
Position Query Router

Handles position listing, details, trades, AI logs, and P&L timeseries.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Response
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Account, AIBotLog, BlacklistedCoin, Bot, PendingOrder, Position, Trade, User
from app.schemas import AIBotLogResponse, PositionResponse, TradeResponse
from app.schemas.position import LimitOrderDetails, LimitOrderFill
from app.coinbase_unified_client import CoinbaseClient
from app.position_routers.dependencies import get_coinbase
from app.routers.auth_dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=List[PositionResponse])
async def get_positions(
    response: Response,
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase),
    current_user: User = Depends(get_current_user),
):
    """Get positions with optional status filter"""
    # Prevent browser HTTP caching of position data (force fresh data on every request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    # Use eager loading to avoid N+1 queries
    query = select(Position).options(
        selectinload(Position.trades),
        selectinload(Position.pending_orders)
    )

    # Get user's account IDs
    accounts_query = select(Account.id).where(Account.user_id == current_user.id)
    accounts_result = await db.execute(accounts_query)
    user_account_ids = [row[0] for row in accounts_result.fetchall()]
    if user_account_ids:
        query = query.where(Position.account_id.in_(user_account_ids))
    else:
        # User has no accounts, return empty
        return []

    if status:
        query = query.where(Position.status == status)
        # Sort closed positions by close date (most recent first), others by opened_at
        if status == "closed":
            query = query.order_by(desc(Position.closed_at)).limit(limit)
        else:
            query = query.order_by(desc(Position.opened_at)).limit(limit)
    else:
        query = query.order_by(desc(Position.opened_at)).limit(limit)

    result = await db.execute(query)
    positions = result.scalars().all()

    # Fetch all blacklisted coins once for efficiency
    blacklist_query = select(BlacklistedCoin)
    blacklist_result = await db.execute(blacklist_query)
    blacklisted_coins = blacklist_result.scalars().all()
    blacklist_map = {coin.symbol: coin.reason for coin in blacklisted_coins}

    # Pre-load bots for open positions (needed for computed_max_budget)
    from app.position_routers.position_actions_router import _compute_resize_budget
    open_bot_ids = {pos.bot_id for pos in positions if pos.bot_id and pos.status == "open"}
    bots_map = {}
    if open_bot_ids:
        bots_result = await db.execute(select(Bot).where(Bot.id.in_(open_bot_ids)))
        bots_map = {b.id: b for b in bots_result.scalars().all()}

    response = []
    for pos in positions:
        # Use eager-loaded data instead of separate queries
        # Count trades (already loaded via selectinload)
        trade_count = len(pos.trades)

        # Count pending orders (already loaded via selectinload)
        pending_count = len([o for o in pos.pending_orders if o.status == "pending"])

        # Get buy trades for first/last buy prices (already loaded)
        buy_trades = [t for t in pos.trades if t.side == "buy"]
        buy_trades.sort(key=lambda t: t.timestamp)

        pos_response = PositionResponse.model_validate(pos)
        pos_response.trade_count = trade_count
        pos_response.pending_orders_count = pending_count

        # Set first/last buy prices for DCA reference
        if buy_trades:
            pos_response.first_buy_price = buy_trades[0].price
            pos_response.last_buy_price = buy_trades[-1].price

        # Check if position's coin is blacklisted
        base_symbol = pos.product_id.split("-")[0]  # "ETH-BTC" -> "ETH"
        if base_symbol in blacklist_map:
            pos_response.is_blacklisted = True
            pos_response.blacklist_reason = blacklist_map[base_symbol]

        # Compute resize budget for open positions
        if pos.status == "open":
            bot = bots_map.get(pos.bot_id) if pos.bot_id else None
            computed = _compute_resize_budget(pos, bot)
            if computed > 0:
                pos_response.computed_max_budget = computed

        # If position is closing via limit, fetch order details (already loaded)
        if pos.closing_via_limit and pos.limit_close_order_id:
            # Find the limit order from already-loaded pending_orders
            limit_order = next(
                (o for o in pos.pending_orders if o.order_id == pos.limit_close_order_id),
                None
            )

            if limit_order:
                fills_data: List = (
                    json.loads(limit_order.fills) if isinstance(limit_order.fills, str) else (limit_order.fills or [])
                )
                fills = [LimitOrderFill(**fill) for fill in fills_data]
                filled_amount = limit_order.base_amount - (limit_order.remaining_base_amount or limit_order.base_amount)
                fill_percentage = (filled_amount / limit_order.base_amount * 100) if limit_order.base_amount > 0 else 0

                pos_response.limit_order_details = LimitOrderDetails(
                    limit_price=limit_order.limit_price,
                    remaining_amount=limit_order.remaining_base_amount or limit_order.base_amount,
                    filled_amount=filled_amount,
                    fill_percentage=fill_percentage,
                    fills=fills,
                    status=limit_order.status,
                )

        response.append(pos_response)

    return response


@router.get("/pnl-timeseries")
async def get_pnl_timeseries(
    account_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get P&L time series data for cumulative profit chart (3Commas-style).

    Returns cumulative profit over time from closed positions.
    If account_id is provided, only returns data for that account.
    """
    # Get closed positions ordered by close date
    query = select(Position).where(
        Position.status == "closed",
        Position.closed_at is not None,
        Position.profit_usd is not None
    )

    accounts_query = select(Account.id).where(Account.user_id == current_user.id)
    accounts_result = await db.execute(accounts_query)
    user_account_ids = [row[0] for row in accounts_result.fetchall()]
    if user_account_ids:
        query = query.where(Position.account_id.in_(user_account_ids))
    else:
        return {"summary": [], "by_day": [], "by_pair": [], "active_trades": 0, "most_profitable_bot": None}

    # Filter by account_id if provided (must be owned by user)
    if account_id is not None:
        query = query.where(Position.account_id == account_id)

    query = query.order_by(Position.closed_at)

    result = await db.execute(query)
    positions = result.scalars().all()

    if not positions:
        # No data yet
        return {"summary": [], "by_day": [], "by_pair": []}

    # Pre-fetch bot names for all positions to avoid N+1 queries
    bot_ids = list(set(pos.bot_id for pos in positions if pos.bot_id))
    bot_name_map: Dict[int, str] = {}
    if bot_ids:
        bots_query = select(Bot).where(Bot.id.in_(bot_ids))
        bots_result = await db.execute(bots_query)
        for bot in bots_result.scalars().all():
            bot_name_map[bot.id] = bot.name

    # Build cumulative P&L over time
    cumulative_pnl_usd = 0.0
    cumulative_pnl_btc = 0.0
    summary_data = []
    daily_pnl_usd: Dict[str, float] = defaultdict(float)
    daily_pnl_btc: Dict[str, float] = defaultdict(float)
    pair_pnl_usd: Dict[str, float] = defaultdict(float)
    pair_pnl_btc: Dict[str, float] = defaultdict(float)

    for pos in positions:
        profit_usd = pos.profit_usd or 0.0

        # Calculate profit_btc based on pair type
        if pos.product_id and "-BTC" in pos.product_id:
            # BTC pair: profit_quote IS the BTC profit
            profit_btc = pos.profit_quote or 0.0
        else:
            # USD/USDC/USDT pair: convert USD profit to BTC
            btc_price = pos.btc_usd_price_at_close or pos.btc_usd_price_at_open or 100000.0
            if btc_price > 0:
                profit_btc = profit_usd / btc_price
            else:
                profit_btc = 0.0

        cumulative_pnl_usd += profit_usd
        cumulative_pnl_btc += profit_btc

        # Add to summary timeline
        summary_data.append(
            {
                "timestamp": pos.closed_at.isoformat(),
                "date": pos.closed_at.strftime("%Y-%m-%d"),
                "cumulative_pnl_usd": round(cumulative_pnl_usd, 2),
                "cumulative_pnl_btc": round(cumulative_pnl_btc, 8),
                "profit_usd": round(profit_usd, 2),
                "profit_btc": round(profit_btc, 8),
                "product_id": pos.product_id,  # Include pair for frontend filtering
                "bot_id": pos.bot_id,  # Include bot_id for frontend filtering
                "bot_name": bot_name_map.get(pos.bot_id, "Unknown"),  # Include bot name for display
            }
        )

        # Aggregate by day
        day_key = pos.closed_at.date().isoformat()
        daily_pnl_usd[day_key] += profit_usd
        daily_pnl_btc[day_key] += profit_btc

        # Aggregate by pair
        pair_pnl_usd[pos.product_id] += profit_usd
        pair_pnl_btc[pos.product_id] += profit_btc

    # Convert daily P&L to cumulative
    by_day_data = []
    cumulative_usd = 0.0
    cumulative_btc = 0.0
    all_days = sorted(set(daily_pnl_usd.keys()) | set(daily_pnl_btc.keys()))
    for day in all_days:
        cumulative_usd += daily_pnl_usd[day]
        cumulative_btc += daily_pnl_btc[day]
        by_day_data.append({
            "date": day,
            "daily_pnl_usd": round(daily_pnl_usd[day], 2),
            "daily_pnl_btc": round(daily_pnl_btc[day], 8),
            "cumulative_pnl_usd": round(cumulative_usd, 2),
            "cumulative_pnl_btc": round(cumulative_btc, 8)
        })

    # Convert pair P&L to list
    all_pairs = sorted(set(pair_pnl_usd.keys()) | set(pair_pnl_btc.keys()))
    by_pair_data = [
        {
            "pair": pair,
            "total_pnl_usd": round(pair_pnl_usd[pair], 2),
            "total_pnl_btc": round(pair_pnl_btc[pair], 8)
        }
        for pair in all_pairs
    ]
    # Sort by USD profit (descending)
    by_pair_data.sort(key=lambda x: x["total_pnl_usd"], reverse=True)

    # Get active trades count (filtered by account if specified)
    active_count_query = select(func.count(Position.id)).where(Position.status == "open")
    if account_id is not None:
        active_count_query = active_count_query.where(Position.account_id == account_id)
    active_count_result = await db.execute(active_count_query)
    active_trades = active_count_result.scalar() or 0

    # Calculate bot-level P&L from already-fetched positions
    bot_pnl_map: Dict[int, dict] = {}
    for pos in positions:
        if pos.bot_id:
            profit_usd = pos.profit_usd or 0.0

            # Calculate profit_btc based on pair type
            if pos.product_id and "-BTC" in pos.product_id:
                profit_btc = pos.profit_quote or 0.0
            else:
                btc_price = pos.btc_usd_price_at_close or pos.btc_usd_price_at_open or 100000.0
                profit_btc = profit_usd / btc_price if btc_price > 0 else 0.0

            if pos.bot_id not in bot_pnl_map:
                bot_pnl_map[pos.bot_id] = {"total_pnl_usd": 0.0, "total_pnl_btc": 0.0}
            bot_pnl_map[pos.bot_id]["total_pnl_usd"] += profit_usd
            bot_pnl_map[pos.bot_id]["total_pnl_btc"] += profit_btc

    most_profitable_bot = None
    if bot_pnl_map:
        # Find bot with highest USD profit
        top_bot_id = max(bot_pnl_map.keys(), key=lambda k: bot_pnl_map[k]["total_pnl_usd"])
        top_bot_data = bot_pnl_map[top_bot_id]

        # Get bot name
        if top_bot_id in bot_name_map:
            most_profitable_bot = {
                "bot_id": top_bot_id,
                "bot_name": bot_name_map[top_bot_id],
                "total_pnl_usd": round(top_bot_data["total_pnl_usd"], 2),
                "total_pnl_btc": round(top_bot_data["total_pnl_btc"], 8)
            }

    return {
        "summary": summary_data,
        "by_day": by_day_data,
        "by_pair": by_pair_data,
        "active_trades": active_trades,
        "most_profitable_bot": most_profitable_bot,
    }


@router.get("/completed/stats")
async def get_completed_trades_stats(
    account_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get completed trades profit statistics.

    Returns statistics for closed positions including:
    - Total profit (BTC and USD)
    - Win rate
    - Total completed trades count
    - Average profit per trade
    """
    # Get closed positions
    query = select(Position).where(
        Position.status == "closed",
        Position.closed_at is not None
    )

    accounts_query = select(Account.id).where(Account.user_id == current_user.id)
    accounts_result = await db.execute(accounts_query)
    user_account_ids = [row[0] for row in accounts_result.fetchall()]
    if user_account_ids:
        query = query.where(Position.account_id.in_(user_account_ids))
    else:
        return {
    "total_profit_btc": 0.0,
    "total_profit_usd": 0.0,
    "win_rate": 0.0,
    "total_trades": 0,
    "winning_trades": 0,
    "losing_trades": 0,
    "average_profit_usd": 0.0,
    }

    # Filter by account_id if provided
    if account_id is not None:
        query = query.where(Position.account_id == account_id)

    result = await db.execute(query)
    positions = result.scalars().all()

    if not positions:
        return {
            "total_profit_btc": 0.0,
            "total_profit_usd": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "average_profit_usd": 0.0,
        }

    # Calculate statistics
    total_trades = len(positions)
    total_profit_btc = 0.0
    total_profit_usd = 0.0
    winning_trades = 0
    losing_trades = 0

    for pos in positions:
        # BTC profit calculation
        if pos.product_id and '-BTC' in pos.product_id:
            # For BTC pairs, profit_quote is already in BTC
            if pos.profit_quote is not None:
                total_profit_btc += pos.profit_quote
        else:
            # For USD pairs, convert USD profit to BTC
            if pos.profit_usd is not None and pos.btc_usd_price_at_close:
                # profit_usd / btc_price = profit_btc
                total_profit_btc += pos.profit_usd / pos.btc_usd_price_at_close

        # USD profit
        if pos.profit_usd is not None:
            total_profit_usd += pos.profit_usd
            if pos.profit_usd > 0:
                winning_trades += 1
            elif pos.profit_usd < 0:
                losing_trades += 1

    # Calculate win rate
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

    # Calculate average profit
    average_profit_usd = total_profit_usd / total_trades if total_trades > 0 else 0.0

    return {
        "total_profit_btc": round(total_profit_btc, 8),
        "total_profit_usd": round(total_profit_usd, 2),
        "win_rate": round(win_rate, 2),
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "average_profit_usd": round(average_profit_usd, 2),
    }


@router.get("/realized-pnl")
async def get_realized_pnl(
    account_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get realized PnL for multiple time periods.

    Returns realized profit/loss for positions closed:
    - Today (since midnight UTC)
    - Yesterday (previous day)
    - Last week (previous calendar week, Monday to Sunday)
    - Last month (previous calendar month)
    - Last quarter (previous calendar quarter)
    - Last year (previous calendar year)
    - WTD (week to date - since Monday of current week)
    - MTD (month to date - since 1st of current month)
    - QTD (quarter to date - since 1st of current quarter)
    - YTD (year to date - since January 1st of current year)
    """
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    # Start of today (midnight UTC)
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Yesterday (previous day, full 24 hours)
    start_of_yesterday = start_of_today - timedelta(days=1)
    end_of_yesterday = start_of_today - timedelta(microseconds=1)
    # Last week (previous calendar week: Monday to Sunday)
    # Find start of this week (Monday)
    days_since_monday = now.weekday()  # Monday=0, Sunday=6
    start_of_this_week = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    # Last week starts 7 days before this week starts
    start_of_last_week = start_of_this_week - timedelta(days=7)
    # Last week ends just before this week starts
    end_of_last_week = start_of_this_week - timedelta(microseconds=1)
    # Last month (previous month's first and last day)
    first_of_current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day_of_prev_month = first_of_current_month - timedelta(days=1)
    start_of_last_month = last_day_of_prev_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_of_last_month = last_day_of_prev_month.replace(hour=23, minute=59, second=59, microsecond=999999)
    # Start of month (1st of current month)
    start_of_month = first_of_current_month
    # Week to date (since Monday of current week - same as Last Week definition)
    start_of_wtd = start_of_this_week
    # Start of quarter (1st of current quarter)
    current_quarter = (now.month - 1) // 3 + 1
    start_month_of_quarter = (current_quarter - 1) * 3 + 1
    start_of_quarter = now.replace(month=start_month_of_quarter, day=1, hour=0, minute=0, second=0, microsecond=0)
    # Last quarter (previous calendar quarter)
    previous_quarter = current_quarter - 1 if current_quarter > 1 else 4
    previous_quarter_year = now.year if current_quarter > 1 else now.year - 1
    start_month_of_prev_quarter = (previous_quarter - 1) * 3 + 1
    start_of_last_quarter = datetime(previous_quarter_year, start_month_of_prev_quarter, 1, 0, 0, 0)
    # Last day of previous quarter is day before current quarter starts
    end_of_last_quarter = start_of_quarter - timedelta(microseconds=1)
    # Last year (previous calendar year)
    start_of_last_year = datetime(now.year - 1, 1, 1, 0, 0, 0)
    end_of_last_year = datetime(now.year - 1, 12, 31, 23, 59, 59, 999999)
    # Start of year (January 1st of current year)
    start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    # Get closed positions
    query = select(Position).where(
        Position.status == "closed",
        Position.closed_at is not None
    )

    accounts_query = select(Account.id).where(Account.user_id == current_user.id)
    accounts_result = await db.execute(accounts_query)
    user_account_ids = [row[0] for row in accounts_result.fetchall()]
    if user_account_ids:
        query = query.where(Position.account_id.in_(user_account_ids))
    else:
        return {
    "daily_profit_btc": 0.0,
    "daily_profit_usd": 0.0,
    "yesterday_profit_btc": 0.0,
    "yesterday_profit_usd": 0.0,
    "last_week_profit_btc": 0.0,
    "last_week_profit_usd": 0.0,
    "last_month_profit_btc": 0.0,
    "last_month_profit_usd": 0.0,
    "last_quarter_profit_btc": 0.0,
    "last_quarter_profit_usd": 0.0,
    "last_year_profit_btc": 0.0,
    "last_year_profit_usd": 0.0,
    "wtd_profit_btc": 0.0,
    "wtd_profit_usd": 0.0,
    "mtd_profit_btc": 0.0,
    "mtd_profit_usd": 0.0,
    "qtd_profit_btc": 0.0,
    "qtd_profit_usd": 0.0,
    "ytd_profit_btc": 0.0,
    "ytd_profit_usd": 0.0,
    "alltime_profit_btc": 0.0,
    "alltime_profit_usd": 0.0,
    }

    # Filter by account_id if provided
    if account_id is not None:
        query = query.where(Position.account_id == account_id)

    result = await db.execute(query)
    positions = result.scalars().all()

    # Calculate PnL for all time periods
    daily_profit_btc = 0.0
    daily_profit_usd = 0.0
    yesterday_profit_btc = 0.0
    yesterday_profit_usd = 0.0
    last_week_profit_btc = 0.0
    last_week_profit_usd = 0.0
    last_month_profit_btc = 0.0
    last_month_profit_usd = 0.0
    last_quarter_profit_btc = 0.0
    last_quarter_profit_usd = 0.0
    last_year_profit_btc = 0.0
    last_year_profit_usd = 0.0
    wtd_profit_btc = 0.0
    wtd_profit_usd = 0.0
    mtd_profit_btc = 0.0
    mtd_profit_usd = 0.0
    qtd_profit_btc = 0.0
    qtd_profit_usd = 0.0
    ytd_profit_btc = 0.0
    ytd_profit_usd = 0.0
    alltime_profit_btc = 0.0
    alltime_profit_usd = 0.0

    for pos in positions:
        if not pos.closed_at:
            continue

        # Calculate BTC profit
        profit_btc = 0.0
        if pos.product_id and '-BTC' in pos.product_id:
            # For BTC pairs, profit_quote is already in BTC
            if pos.profit_quote is not None:
                profit_btc = pos.profit_quote
        else:
            # For USD pairs, convert USD profit to BTC
            if pos.profit_usd is not None and pos.btc_usd_price_at_close:
                profit_btc = pos.profit_usd / pos.btc_usd_price_at_close

        profit_usd = pos.profit_usd if pos.profit_usd is not None else 0.0

        # All-time (every closed position)
        alltime_profit_btc += profit_btc
        alltime_profit_usd += profit_usd

        # Check if closed today
        if pos.closed_at >= start_of_today:
            daily_profit_btc += profit_btc
            daily_profit_usd += profit_usd

        # Check if closed yesterday (previous day)
        if start_of_yesterday <= pos.closed_at <= end_of_yesterday:
            yesterday_profit_btc += profit_btc
            yesterday_profit_usd += profit_usd

        # Check if closed last week (previous calendar week)
        if start_of_last_week <= pos.closed_at <= end_of_last_week:
            last_week_profit_btc += profit_btc
            last_week_profit_usd += profit_usd

        # Check if closed last month (previous calendar month)
        if start_of_last_month <= pos.closed_at <= end_of_last_month:
            last_month_profit_btc += profit_btc
            last_month_profit_usd += profit_usd

        # Check if closed last quarter (previous calendar quarter)
        if start_of_last_quarter <= pos.closed_at <= end_of_last_quarter:
            last_quarter_profit_btc += profit_btc
            last_quarter_profit_usd += profit_usd

        # Check if closed last year (previous calendar year)
        if start_of_last_year <= pos.closed_at <= end_of_last_year:
            last_year_profit_btc += profit_btc
            last_year_profit_usd += profit_usd

        # Check if closed this week (week to date)
        if pos.closed_at >= start_of_wtd:
            wtd_profit_btc += profit_btc
            wtd_profit_usd += profit_usd

        # Check if closed this month
        if pos.closed_at >= start_of_month:
            mtd_profit_btc += profit_btc
            mtd_profit_usd += profit_usd

        # Check if closed this quarter
        if pos.closed_at >= start_of_quarter:
            qtd_profit_btc += profit_btc
            qtd_profit_usd += profit_usd

        # Check if closed this year
        if pos.closed_at >= start_of_year:
            ytd_profit_btc += profit_btc
            ytd_profit_usd += profit_usd

    return {
        "daily_profit_btc": round(daily_profit_btc, 8),
        "daily_profit_usd": round(daily_profit_usd, 2),
        "yesterday_profit_btc": round(yesterday_profit_btc, 8),
        "yesterday_profit_usd": round(yesterday_profit_usd, 2),
        "last_week_profit_btc": round(last_week_profit_btc, 8),
        "last_week_profit_usd": round(last_week_profit_usd, 2),
        "last_month_profit_btc": round(last_month_profit_btc, 8),
        "last_month_profit_usd": round(last_month_profit_usd, 2),
        "last_quarter_profit_btc": round(last_quarter_profit_btc, 8),
        "last_quarter_profit_usd": round(last_quarter_profit_usd, 2),
        "last_year_profit_btc": round(last_year_profit_btc, 8),
        "last_year_profit_usd": round(last_year_profit_usd, 2),
        "wtd_profit_btc": round(wtd_profit_btc, 8),
        "wtd_profit_usd": round(wtd_profit_usd, 2),
        "mtd_profit_btc": round(mtd_profit_btc, 8),
        "mtd_profit_usd": round(mtd_profit_usd, 2),
        "qtd_profit_btc": round(qtd_profit_btc, 8),
        "qtd_profit_usd": round(qtd_profit_usd, 2),
        "ytd_profit_btc": round(ytd_profit_btc, 8),
        "ytd_profit_usd": round(ytd_profit_usd, 2),
        "alltime_profit_btc": round(alltime_profit_btc, 8),
        "alltime_profit_usd": round(alltime_profit_usd, 2),
    }


@router.get("/{position_id}", response_model=PositionResponse)
async def get_position(
    position_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific position details"""
    from fastapi import HTTPException

    query = select(Position).where(Position.id == position_id)

    accounts_query = select(Account.id).where(Account.user_id == current_user.id)
    accounts_result = await db.execute(accounts_query)
    user_account_ids = [row[0] for row in accounts_result.fetchall()]
    if user_account_ids:
        query = query.where(Position.account_id.in_(user_account_ids))
    else:
        raise HTTPException(status_code=404, detail="Position not found")

    result = await db.execute(query)
    position = result.scalars().first()

    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    # Count trades
    trade_count_query = select(func.count(Trade.id)).where(Trade.position_id == position.id)
    trade_count_result = await db.execute(trade_count_query)
    trade_count = trade_count_result.scalar()

    # Count pending orders
    pending_count_query = select(func.count(PendingOrder.id)).where(
        PendingOrder.position_id == position.id, PendingOrder.status == "pending"
    )
    pending_count_result = await db.execute(pending_count_query)
    pending_count = pending_count_result.scalar()

    # Get buy trades for first/last buy prices (needed for DCA tick marks)
    buy_trades_query = (
        select(Trade)
        .where(Trade.position_id == position.id, Trade.side == "buy")
        .order_by(Trade.timestamp)
    )
    buy_trades_result = await db.execute(buy_trades_query)
    buy_trades = buy_trades_result.scalars().all()

    pos_response = PositionResponse.model_validate(position)
    pos_response.trade_count = trade_count
    pos_response.pending_orders_count = pending_count

    # Set first/last buy prices for DCA reference
    if buy_trades:
        pos_response.first_buy_price = buy_trades[0].price
        pos_response.last_buy_price = buy_trades[-1].price

    # Check if position's coin is blacklisted
    base_symbol = position.product_id.split("-")[0]  # "ETH-BTC" -> "ETH"
    blacklist_query = select(BlacklistedCoin).where(BlacklistedCoin.symbol == base_symbol)
    blacklist_result = await db.execute(blacklist_query)
    blacklisted_coin = blacklist_result.scalars().first()
    if blacklisted_coin:
        pos_response.is_blacklisted = True
        pos_response.blacklist_reason = blacklisted_coin.reason

    return pos_response


@router.get("/{position_id}/trades", response_model=List[TradeResponse])
async def get_position_trades(position_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get all trades for a position"""
    query = select(Trade).where(Trade.position_id == position_id).order_by(Trade.timestamp)
    result = await db.execute(query)
    trades = result.scalars().all()

    return [TradeResponse.model_validate(t) for t in trades]


@router.get("/{position_id}/ai-logs", response_model=List[AIBotLogResponse])
async def get_position_ai_logs(position_id: int, include_before_open: bool = True, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get AI reasoning logs for a position.

    By default, includes logs from 30 seconds before position opened and
    30 seconds after position closed. This captures the AI's complete
    decision-making process including what led to opening and closing.
    """
    from fastapi import HTTPException

    # Get the position to know when it was opened/closed
    pos_query = select(Position).where(Position.id == position_id)
    pos_result = await db.execute(pos_query)
    position = pos_result.scalars().first()

    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    # Build query for AI logs
    query = select(AIBotLog).where(AIBotLog.position_id == position_id)

    # If include_before_open is True, also get logs from 30s before open and 30s after close
    # that belong to the same bot and product
    if include_before_open and position.opened_at:
        time_before = position.opened_at - timedelta(seconds=30)

        # Calculate time after (30s after close, or far future if still open)
        if position.closed_at:
            time_after = position.closed_at + timedelta(seconds=30)
        else:
            time_after = datetime.utcnow() + timedelta(days=365)

        query = select(AIBotLog).where(
            (AIBotLog.position_id == position_id)
            | (
                (AIBotLog.bot_id == position.bot_id)
                & (AIBotLog.product_id == position.product_id)
                & (AIBotLog.timestamp >= time_before)
                & (AIBotLog.timestamp <= time_after)
                & (AIBotLog.position_id is None)
            )
        )

    query = query.order_by(AIBotLog.timestamp)

    result = await db.execute(query)
    logs = result.scalars().all()

    return [AIBotLogResponse.model_validate(log) for log in logs]
