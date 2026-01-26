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
from app.routers.auth_dependencies import get_current_user_optional

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=List[PositionResponse])
async def get_positions(
    response: Response,
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase),
    current_user: Optional[User] = Depends(get_current_user_optional),
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

    # Filter by user's accounts if authenticated
    if current_user:
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
    current_user: Optional[User] = Depends(get_current_user_optional)
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

    # Filter by user's accounts if authenticated
    if current_user:
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
    cumulative_pnl = 0.0
    summary_data = []
    daily_pnl: Dict[str, float] = defaultdict(float)
    pair_pnl: Dict[str, float] = defaultdict(float)

    for pos in positions:
        profit = pos.profit_usd or 0.0
        cumulative_pnl += profit

        # Add to summary timeline
        summary_data.append(
            {
                "timestamp": pos.closed_at.isoformat(),
                "date": pos.closed_at.strftime("%Y-%m-%d"),
                "cumulative_pnl": round(cumulative_pnl, 2),
                "profit": round(profit, 2),
                "product_id": pos.product_id,  # Include pair for frontend filtering
                "bot_id": pos.bot_id,  # Include bot_id for frontend filtering
                "bot_name": bot_name_map.get(pos.bot_id, "Unknown"),  # Include bot name for display
            }
        )

        # Aggregate by day
        day_key = pos.closed_at.date().isoformat()
        daily_pnl[day_key] += profit

        # Aggregate by pair
        pair_pnl[pos.product_id] += profit

    # Convert daily P&L to cumulative
    by_day_data = []
    cumulative = 0.0
    for day in sorted(daily_pnl.keys()):
        cumulative += daily_pnl[day]
        by_day_data.append({"date": day, "daily_pnl": round(daily_pnl[day], 2), "cumulative_pnl": round(cumulative, 2)})

    # Convert pair P&L to list
    by_pair_data = [
        {"pair": pair, "total_pnl": round(pnl, 2)}
        for pair, pnl in sorted(pair_pnl.items(), key=lambda x: x[1], reverse=True)
    ]

    # Get active trades count (filtered by account if specified)
    active_count_query = select(func.count(Position.id)).where(Position.status == "open")
    if account_id is not None:
        active_count_query = active_count_query.where(Position.account_id == account_id)
    active_count_result = await db.execute(active_count_query)
    active_trades = active_count_result.scalar() or 0

    # Get bot-level P&L for most profitable bot (filtered by account if specified)
    bot_pnl_query = (
        select(Position.bot_id, func.sum(Position.profit_usd).label("total_pnl"))
        .where(Position.status == "closed", Position.profit_usd is not None)
    )
    if account_id is not None:
        bot_pnl_query = bot_pnl_query.where(Position.account_id == account_id)
    bot_pnl_query = (
        bot_pnl_query
        .group_by(Position.bot_id)
        .order_by(func.sum(Position.profit_usd).desc())
    )

    bot_pnl_result = await db.execute(bot_pnl_query)
    bot_pnls = bot_pnl_result.all()

    most_profitable_bot = None
    if bot_pnls:
        top_bot_id, top_bot_pnl = bot_pnls[0]
        # Get bot name
        bot_query = select(Bot).where(Bot.id == top_bot_id)
        bot_result = await db.execute(bot_query)
        bot = bot_result.scalars().first()
        if bot:
            most_profitable_bot = {"bot_id": top_bot_id, "bot_name": bot.name, "total_pnl": round(top_bot_pnl, 2)}

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
    current_user: Optional[User] = Depends(get_current_user_optional)
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

    # Filter by user's accounts if authenticated
    if current_user:
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
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Get realized PnL for multiple time periods.

    Returns realized profit/loss for positions closed:
    - Today (since midnight UTC)
    - This week (last 7 days)
    - 4 weeks (last 28 days)
    - YTD (year to date - since January 1st of current year)
    """
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    # Start of today (midnight UTC)
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Start of week (7 days ago)
    start_of_week = now - timedelta(days=7)
    # Start of 4 weeks (28 days ago)
    start_of_4_weeks = now - timedelta(days=28)
    # Start of year (January 1st of current year)
    start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    # Get closed positions
    query = select(Position).where(
        Position.status == "closed",
        Position.closed_at is not None
    )

    # Filter by user's accounts if authenticated
    if current_user:
        accounts_query = select(Account.id).where(Account.user_id == current_user.id)
        accounts_result = await db.execute(accounts_query)
        user_account_ids = [row[0] for row in accounts_result.fetchall()]
        if user_account_ids:
            query = query.where(Position.account_id.in_(user_account_ids))
        else:
            return {
                "daily_profit_btc": 0.0,
                "daily_profit_usd": 0.0,
                "weekly_profit_btc": 0.0,
                "weekly_profit_usd": 0.0,
                "four_weeks_profit_btc": 0.0,
                "four_weeks_profit_usd": 0.0,
                "ytd_profit_btc": 0.0,
                "ytd_profit_usd": 0.0,
            }

    # Filter by account_id if provided
    if account_id is not None:
        query = query.where(Position.account_id == account_id)

    result = await db.execute(query)
    positions = result.scalars().all()

    # Calculate PnL for all time periods
    daily_profit_btc = 0.0
    daily_profit_usd = 0.0
    weekly_profit_btc = 0.0
    weekly_profit_usd = 0.0
    four_weeks_profit_btc = 0.0
    four_weeks_profit_usd = 0.0
    ytd_profit_btc = 0.0
    ytd_profit_usd = 0.0

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

        # Check if closed today
        if pos.closed_at >= start_of_today:
            daily_profit_btc += profit_btc
            daily_profit_usd += profit_usd

        # Check if closed this week
        if pos.closed_at >= start_of_week:
            weekly_profit_btc += profit_btc
            weekly_profit_usd += profit_usd

        # Check if closed in last 4 weeks
        if pos.closed_at >= start_of_4_weeks:
            four_weeks_profit_btc += profit_btc
            four_weeks_profit_usd += profit_usd

        # Check if closed this year
        if pos.closed_at >= start_of_year:
            ytd_profit_btc += profit_btc
            ytd_profit_usd += profit_usd

    return {
        "daily_profit_btc": round(daily_profit_btc, 8),
        "daily_profit_usd": round(daily_profit_usd, 2),
        "weekly_profit_btc": round(weekly_profit_btc, 8),
        "weekly_profit_usd": round(weekly_profit_usd, 2),
        "four_weeks_profit_btc": round(four_weeks_profit_btc, 8),
        "four_weeks_profit_usd": round(four_weeks_profit_usd, 2),
        "ytd_profit_btc": round(ytd_profit_btc, 8),
        "ytd_profit_usd": round(ytd_profit_usd, 2),
    }


@router.get("/{position_id}", response_model=PositionResponse)
async def get_position(
    position_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Get specific position details"""
    from fastapi import HTTPException

    query = select(Position).where(Position.id == position_id)

    # Filter by user's accounts if authenticated
    if current_user:
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
async def get_position_trades(position_id: int, db: AsyncSession = Depends(get_db)):
    """Get all trades for a position"""
    query = select(Trade).where(Trade.position_id == position_id).order_by(Trade.timestamp)
    result = await db.execute(query)
    trades = result.scalars().all()

    return [TradeResponse.model_validate(t) for t in trades]


@router.get("/{position_id}/ai-logs", response_model=List[AIBotLogResponse])
async def get_position_ai_logs(position_id: int, include_before_open: bool = True, db: AsyncSession = Depends(get_db)):
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
