"""
Position Query Router

Handles position listing, details, trades, AI logs, and P&L timeseries.
"""

import logging
from app.utils.timeutil import utcnow
from collections import defaultdict
from datetime import datetime, timedelta
import time
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AIBotLog, AIOpinionLog, BlacklistedCoin, Bot, PendingOrder, Position, Trade, User
from app.auth.dependencies import get_current_user
from app.services.account_access import accessible_account_ids
from app.services.portfolio_service import get_account_balances
from app.schemas import AIBotLogResponse, AIOpinionLogResponse, PositionResponse, TradeResponse
from app.schemas.position import LimitOrderDetails
from app.constants import VALID_CATEGORIES

logger = logging.getLogger(__name__)
router = APIRouter()

POSITIONS_SUMMARY_CACHE_TTL_SECONDS = 20.0
_positions_summary_cache: Dict[tuple[int, int], tuple[float, dict]] = {}


def _get_page_summary_cache_key(user_id: int, account_id: int) -> tuple[int, int]:
    return user_id, account_id


def clear_positions_summary_cache() -> None:
    _positions_summary_cache.clear()

LIST_SAFE_STRATEGY_CONFIG_KEYS = {
    "take_profit_percentage",
    "take_profit_percent",
    "min_profit_percentage",
    "price_deviation",
    "safety_order_step_scale",
    "max_safety_orders",
    "grace_safety_orders",
    "dca_target_reference",
    "base_order_size",
    "trailing_take_profit",
    "trailing_tp_deviation",
    "stop_loss_enabled",
    "stop_loss_percentage",
}

OPEN_LIST_UNUSED_OPTIONAL_FIELDS = (
    "account_id",
    "user_attempt_number",
    "sell_price",
    "total_quote_received",
    "profit_quote",
    "btc_usd_price_at_close",
    "profit_usd",
    "limit_close_order_id",
)


def _trim_strategy_snapshot_for_list(strategy_config_snapshot: Optional[dict]) -> Optional[dict]:
    """Keep only the strategy config fields used by the hot open-positions UI."""
    if not isinstance(strategy_config_snapshot, dict):
        return strategy_config_snapshot

    return {
        key: value
        for key, value in strategy_config_snapshot.items()
        if key in LIST_SAFE_STRATEGY_CONFIG_KEYS
    }


def _trim_open_list_optional_fields(pos_response: PositionResponse) -> None:
    """Clear optional fields the open-positions list view never reads."""
    for field_name in OPEN_LIST_UNUSED_OPTIONAL_FIELDS:
        setattr(pos_response, field_name, None)


@router.get("/", response_model=List[PositionResponse])
async def get_positions(
    response: Response,
    status: Optional[str] = None,
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    account_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get positions with optional status and account_id filters."""
    # Prevent browser HTTP caching of position data (force fresh data on every request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    trade_count = (
        select(func.count(Trade.id))
        .where(Trade.position_id == Position.id)
        .correlate(Position)
        .scalar_subquery()
    )
    safety_orders_deployed = (
        select(func.coalesce(func.sum(Trade.dca_levels), 0))
        .where(Trade.position_id == Position.id, Trade.trade_type == "dca")
        .correlate(Position)
        .scalar_subquery()
    )
    first_buy_price = (
        select(Trade.price)
        .where(Trade.position_id == Position.id, Trade.side == "buy")
        .order_by(Trade.timestamp.asc(), Trade.id.asc())
        .limit(1)
        .correlate(Position)
        .scalar_subquery()
    )
    last_buy_price = (
        select(Trade.price)
        .where(Trade.position_id == Position.id, Trade.side == "buy")
        .order_by(Trade.timestamp.desc(), Trade.id.desc())
        .limit(1)
        .correlate(Position)
        .scalar_subquery()
    )
    first_buy_quote_amount = (
        select(Trade.quote_amount)
        .where(Trade.position_id == Position.id, Trade.side == "buy")
        .order_by(Trade.timestamp.asc(), Trade.id.asc())
        .limit(1)
        .correlate(Position)
        .scalar_subquery()
    )
    pending_order_count = (
        select(func.count(PendingOrder.id))
        .where(PendingOrder.position_id == Position.id, PendingOrder.status == "pending")
        .correlate(Position)
        .scalar_subquery()
    )
    query = select(
        Position,
        trade_count.label("trade_count"),
        safety_orders_deployed.label("safety_orders_deployed"),
        first_buy_price.label("first_buy_price"),
        last_buy_price.label("last_buy_price"),
        first_buy_quote_amount.label("first_buy_quote_amount"),
        pending_order_count.label("pending_order_count"),
    )

    # Get user's account IDs (owned + shared)
    user_account_ids = await accessible_account_ids(db, current_user.id)
    if not user_account_ids:
        return []

    if account_id is not None:
        # Caller requested a specific account — verify access first
        if account_id not in user_account_ids:
            raise HTTPException(status_code=403, detail="Access to this account is not permitted")
        query = query.where(Position.account_id == account_id)
    else:
        query = query.where(Position.account_id.in_(user_account_ids))

    if status:
        query = query.where(Position.status == status)
        if status == "closed":
            query = query.order_by(desc(Position.closed_at)).offset(offset).limit(limit)
        else:
            query = query.order_by(desc(Position.opened_at)).offset(offset).limit(limit)
    else:
        query = query.order_by(desc(Position.opened_at)).offset(offset).limit(limit)

    result = await db.execute(query)
    position_rows = result.all()
    positions = [row[0] for row in position_rows]
    if not positions:
        return []

    base_symbols = {pos.product_id.split("-")[0] for pos in positions if pos.product_id}

    # Fetch blacklisted coins: global entries + current user's overrides
    from sqlalchemy import or_
    blacklist_query = select(BlacklistedCoin).where(
        BlacklistedCoin.symbol.in_(base_symbols),
        or_(
            BlacklistedCoin.user_id.is_(None),
            BlacklistedCoin.user_id == current_user.id,
        )
    )
    blacklist_result = await db.execute(blacklist_query)
    blacklisted_coins = blacklist_result.scalars().all()
    blacklist_map = {coin.symbol: coin.reason for coin in blacklisted_coins}

    trade_count_map = {
        row[0].id: row.trade_count
        for row in position_rows
    }

    # Safety orders DEPLOYED = sum of dca_levels over DCA trades (a cascade fills
    # several SO levels in one trade), not the number of DCA trade rows. Covers
    # both long (buy) and short (sell) DCA trades.
    so_deployed_map = {
        row[0].id: int(row.safety_orders_deployed or 0)
        for row in position_rows
    }
    buy_price_map = {
        row[0].id: (row.first_buy_price, row.last_buy_price, row.first_buy_quote_amount)
        for row in position_rows
    }
    pending_count_map = {
        row[0].id: row.pending_order_count
        for row in position_rows
    }

    limit_order_ids = [
        pos.limit_close_order_id
        for pos in positions
        if pos.closing_via_limit and pos.limit_close_order_id
    ]
    limit_order_map = {}
    if limit_order_ids:
        limit_order_result = await db.execute(
            select(PendingOrder).where(PendingOrder.order_id.in_(limit_order_ids))
        )
        limit_order_map = {
            order.order_id: order
            for order in limit_order_result.scalars().all()
        }

    # Pre-load bots for open positions (needed for computed_max_budget)
    from app.position_routers.helpers import compute_resize_budget
    open_bot_ids = {
        pos.bot_id
        for pos in positions
        if pos.bot_id and pos.status == "open" and not pos.strategy_config_snapshot
    }
    bots_map = {}
    if open_bot_ids:
        bots_result = await db.execute(select(Bot).where(Bot.id.in_(open_bot_ids)))
        bots_map = {b.id: b for b in bots_result.scalars().all()}

    response = []
    for pos in positions:
        pos_response = PositionResponse.model_validate(pos)
        if status == "open":
            pos_response.strategy_config_snapshot = _trim_strategy_snapshot_for_list(
                pos_response.strategy_config_snapshot
            )
            _trim_open_list_optional_fields(pos_response)
        pos_response.trade_count = trade_count_map.get(pos.id, 0)
        pos_response.safety_orders_deployed = so_deployed_map.get(pos.id, 0)
        pos_response.pending_orders_count = pending_count_map.get(pos.id, 0)

        # Set first/last buy prices for DCA reference
        first_buy_price, last_buy_price, first_buy_quote_amount = buy_price_map.get(pos.id, (None, None, None))
        pos_response.first_buy_price = first_buy_price
        pos_response.last_buy_price = last_buy_price

        # Attach coin category from blacklist (category is embedded in reason prefix)
        base_symbol = pos.product_id.split("-")[0]  # "ETH-BTC" -> "ETH"
        if base_symbol in blacklist_map:
            reason = blacklist_map[base_symbol]
            pos_response.is_blacklisted = True
            pos_response.blacklist_reason = reason
            # Extract category tag from reason prefix (e.g., "[APPROVED] good coin" → "APPROVED")
            for cat in VALID_CATEGORIES:
                if reason and reason.startswith(f"[{cat}]"):
                    pos_response.coin_category = cat
                    break
            else:
                pos_response.coin_category = "BLACKLISTED"

        # Compute resize budget for open positions
        if pos.status == "open":
            bot = bots_map.get(pos.bot_id) if pos.bot_id else None
            computed = compute_resize_budget(pos, bot, base_order_size=first_buy_quote_amount)
            if computed > 0:
                pos_response.computed_max_budget = computed

        # If position is closing via limit, fetch order details (already loaded)
        if pos.closing_via_limit and pos.limit_close_order_id:
            limit_order = limit_order_map.get(pos.limit_close_order_id)

            if limit_order:
                filled_amount = limit_order.base_amount - (limit_order.remaining_base_amount or limit_order.base_amount)
                fill_percentage = (filled_amount / limit_order.base_amount * 100) if limit_order.base_amount > 0 else 0

                pos_response.limit_order_details = LimitOrderDetails(
                    limit_price=limit_order.limit_price,
                    remaining_amount=limit_order.remaining_base_amount or limit_order.base_amount,
                    filled_amount=filled_amount,
                    fill_percentage=fill_percentage,
                    fills=[],
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
    Get P&L time series data for cumulative profit chart.

    Returns cumulative profit over time from closed positions.
    If account_id is provided, only returns data for that account.
    """
    # Get closed positions ordered by close date.
    # NB: .isnot(None) — not Python `is not None`, which evaluates at
    # construction time to the Column object's Python identity (always
    # True) and never reaches the SQL layer. Fixed in v2.166.6 per the
    # multiuser-security audit's Low finding.
    query = select(Position).where(
        Position.status == "closed",
        Position.closed_at.isnot(None),
        Position.profit_usd.isnot(None),
    )

    user_account_ids = await accessible_account_ids(db, current_user.id)
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

    # Get active trades count (scoped to current user's accounts)
    active_count_query = select(func.count(Position.id)).where(
        Position.status == "open",
        Position.account_id.in_(user_account_ids) if user_account_ids else Position.id < 0,
    )
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
    empty_stats = {
        "total_profit_btc": 0.0,
        "total_profit_usd": 0.0,
        "win_rate": 0.0,
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "average_profit_usd": 0.0,
    }

    user_account_ids = await accessible_account_ids(db, current_user.id)
    if not user_account_ids:
        return empty_stats

    # Build conditions for closed positions — exclude manual closes from win rate stats
    conditions = [
        Position.status == "closed",
        Position.account_id.in_(user_account_ids),
        or_(Position.exit_reason.is_(None), Position.exit_reason != "manual"),
    ]
    if account_id is not None:
        conditions.append(Position.account_id == account_id)

    # Use SQL aggregation instead of materializing all rows
    # BTC profit: profit_quote for BTC pairs, profit_usd/btc_usd_price_at_close for others
    btc_profit_expr = func.coalesce(func.sum(
        case(
            (Position.product_id.like('%-BTC'), Position.profit_quote),
            else_=case(
                (Position.btc_usd_price_at_close > 0,
                 Position.profit_usd / Position.btc_usd_price_at_close),
                else_=0.0,
            ),
        )
    ), 0.0)

    agg_query = select(
        func.count(Position.id),
        func.coalesce(func.sum(Position.profit_usd), 0.0),
        func.count(case((Position.profit_usd > 0, 1))),
        func.count(case((Position.profit_usd < 0, 1))),
        btc_profit_expr,
    ).where(*conditions)

    result = await db.execute(agg_query)
    row = result.one()
    total_trades, total_profit_usd, winning_trades, losing_trades, total_profit_btc = row

    if total_trades == 0:
        return empty_stats

    win_rate = (winning_trades / total_trades * 100)
    average_profit_usd = total_profit_usd / total_trades

    return {
        "total_profit_btc": round(float(total_profit_btc), 8),
        "total_profit_usd": round(float(total_profit_usd), 2),
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
    now = utcnow()
    # Pre-compute all period boundaries
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_yesterday = start_of_today - timedelta(days=1)
    end_of_yesterday = start_of_today - timedelta(microseconds=1)
    days_since_monday = now.weekday()
    start_of_this_week = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_last_week = start_of_this_week - timedelta(days=7)
    end_of_last_week = start_of_this_week - timedelta(microseconds=1)
    first_of_current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day_of_prev_month = first_of_current_month - timedelta(days=1)
    start_of_last_month = last_day_of_prev_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_of_last_month = last_day_of_prev_month.replace(hour=23, minute=59, second=59, microsecond=999999)
    start_of_month = first_of_current_month
    start_of_wtd = start_of_this_week
    current_quarter = (now.month - 1) // 3 + 1
    start_month_of_quarter = (current_quarter - 1) * 3 + 1
    start_of_quarter = now.replace(month=start_month_of_quarter, day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_quarter = current_quarter - 1 if current_quarter > 1 else 4
    previous_quarter_year = now.year if current_quarter > 1 else now.year - 1
    start_month_of_prev_quarter = (previous_quarter - 1) * 3 + 1
    start_of_last_quarter = datetime(previous_quarter_year, start_month_of_prev_quarter, 1, 0, 0, 0)
    end_of_last_quarter = start_of_quarter - timedelta(microseconds=1)
    start_of_last_year = datetime(now.year - 1, 1, 1, 0, 0, 0)
    end_of_last_year = datetime(now.year - 1, 12, 31, 23, 59, 59, 999999)
    start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    periods = [
        'daily', 'yesterday', 'last_week', 'last_month', 'last_quarter',
        'last_year', 'wtd', 'mtd', 'qtd', 'ytd', 'alltime']

    user_account_ids = await accessible_account_ids(db, current_user.id)
    if not user_account_ids:
        empty = {}
        for p in periods:
            empty[f"{p}_profit_btc"] = 0.0
            empty[f"{p}_profit_usd"] = 0.0
            empty[f"{p}_profit_by_quote"] = {}
        return empty

    base_where = [
        Position.status == "closed",
        Position.closed_at.isnot(None),
        Position.account_id.in_(user_account_ids),
    ]
    if account_id is not None:
        base_where.append(Position.account_id == account_id)

    period_bounds = {
        "daily": (start_of_today, None),
        "yesterday": (start_of_yesterday, end_of_yesterday),
        "last_week": (start_of_last_week, end_of_last_week),
        "last_month": (start_of_last_month, end_of_last_month),
        "last_quarter": (start_of_last_quarter, end_of_last_quarter),
        "last_year": (start_of_last_year, end_of_last_year),
        "wtd": (start_of_wtd, None),
        "mtd": (start_of_month, None),
        "qtd": (start_of_quarter, None),
        "ytd": (start_of_year, None),
        "alltime": (None, None),
    }

    # One grouped SQL query returns one row per product rather than one row per
    # closed position. Both USD totals and native quote totals are aggregated in
    # the database; Python only maps the small product result set into currencies.
    usd_value = func.coalesce(Position.profit_usd, 0.0)
    stable_quote = or_(
        Position.product_id.like('%-USD'),
        Position.product_id.like('%-USDC'),
        Position.product_id.like('%-USDT'),
    )
    quote_value = func.coalesce(
        Position.profit_quote,
        case((stable_quote, usd_value), else_=0.0),
        0.0,
    )
    aggregate_columns = [Position.product_id.label("product_id")]
    for period_name, (start, end) in period_bounds.items():
        if start is None:
            aggregate_columns.extend([
                func.coalesce(func.sum(usd_value), 0.0).label(f"{period_name}_usd"),
                func.coalesce(func.sum(quote_value), 0.0).label(f"{period_name}_quote"),
            ])
            continue
        condition = Position.closed_at >= start if end is None else Position.closed_at.between(start, end)
        aggregate_columns.extend([
            func.coalesce(func.sum(case((condition, usd_value), else_=0.0)), 0.0).label(f"{period_name}_usd"),
            func.coalesce(func.sum(case((condition, quote_value), else_=0.0)), 0.0).label(f"{period_name}_quote"),
        ])

    grouped_result = await db.execute(
        select(*aggregate_columns).where(*base_where).group_by(Position.product_id)
    )
    grouped_rows = grouped_result.mappings().all()

    usd_map = {p: 0.0 for p in periods}
    by_quote = {p: {} for p in periods}
    for row in grouped_rows:
        product_id = row["product_id"]
        quote_currency = product_id.split('-')[1] if product_id and '-' in product_id else 'BTC'
        for period_name in periods:
            usd_map[period_name] += float(row[f"{period_name}_usd"] or 0.0)
            quote_total = float(row[f"{period_name}_quote"] or 0.0)
            if quote_total:
                by_quote[period_name][quote_currency] = (
                    by_quote[period_name].get(quote_currency, 0.0) + quote_total
                )

    # Build response
    resp: dict = {}
    for p in periods:
        resp[f"{p}_profit_usd"] = round(float(usd_map[p] or 0.0), 2)
        resp[f"{p}_profit_btc"] = round(by_quote[p].get('BTC', 0.0), 8)
        resp[f"{p}_profit_by_quote"] = {k: round(v, 8) for k, v in by_quote[p].items()}
    return resp


@router.get("/page-summary")
async def get_positions_summary(
    account_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the three account-scoped summary panels in one HTTP response."""
    user_account_ids = await accessible_account_ids(db, current_user.id)
    if account_id not in user_account_ids:
        raise HTTPException(status_code=404, detail="Account not found")

    cache_key = _get_page_summary_cache_key(current_user.id, account_id)
    now = time.monotonic()
    cached = _positions_summary_cache.get(cache_key)
    if cached and now - cached[0] < POSITIONS_SUMMARY_CACHE_TTL_SECONDS:
        return cached[1]

    completed_stats = await get_completed_trades_stats(account_id, db, current_user)
    realized_pnl = await get_realized_pnl(account_id, db, current_user)
    balances = await get_account_balances(db, current_user, account_id)
    summary = {
        "completed_stats": completed_stats,
        "realized_pnl": realized_pnl,
        "balances": balances,
    }
    _positions_summary_cache[cache_key] = (now, summary)
    return summary


@router.get("/ai-opinions", response_model=Dict[int, Optional[AIOpinionLogResponse]])
async def get_position_ai_opinions(
    position_ids: List[int] = Query(..., min_length=1, max_length=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the latest AI opinion for each authorized position in one query batch."""
    deduped_ids = list(dict.fromkeys(position_ids))
    if len(deduped_ids) > 200:
        raise HTTPException(status_code=400, detail="At most 200 position_ids are allowed")

    user_account_ids = await accessible_account_ids(db, current_user.id)
    if not user_account_ids:
        return {}

    positions_query = select(Position.id).where(
        Position.id.in_(deduped_ids),
        Position.account_id.in_(user_account_ids),
    )
    authorized_ids = list((await db.execute(positions_query)).scalars().all())
    if not authorized_ids:
        return {}

    opinions_by_position: Dict[int, Optional[AIOpinionLogResponse]] = {
        position_id: None for position_id in authorized_ids
    }
    opinions_query = (
        select(AIOpinionLog)
        .where(AIOpinionLog.position_id.in_(authorized_ids))
        .order_by(AIOpinionLog.position_id, desc(AIOpinionLog.created_at))
    )
    opinions = (await db.execute(opinions_query)).scalars().all()
    for opinion in opinions:
        position_id = opinion.position_id
        if position_id is not None and opinions_by_position.get(position_id) is None:
            opinions_by_position[position_id] = AIOpinionLogResponse.model_validate(opinion)

    return opinions_by_position


@router.get("/{position_id}", response_model=PositionResponse)
async def get_position(
    position_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific position details"""
    from fastapi import HTTPException

    query = select(Position).where(Position.id == position_id)

    user_account_ids = await accessible_account_ids(db, current_user.id)
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

    # First/last buy prices (needed for DCA tick marks) — two LIMIT-1 lookups
    # instead of materializing every buy trade. Tie-break on id so trades with
    # identical timestamps keep their insertion order.
    first_buy_query = (
        select(Trade.price)
        .where(Trade.position_id == position.id, Trade.side == "buy")
        .order_by(Trade.timestamp.asc(), Trade.id.asc())
        .limit(1)
    )
    last_buy_query = (
        select(Trade.price)
        .where(Trade.position_id == position.id, Trade.side == "buy")
        .order_by(Trade.timestamp.desc(), Trade.id.desc())
        .limit(1)
    )
    first_buy_price = (await db.execute(first_buy_query)).scalar_one_or_none()
    last_buy_price = (await db.execute(last_buy_query)).scalar_one_or_none()

    # SO levels deployed = sum of dca_levels over DCA trades (cascades fill >1).
    so_deployed_query = select(func.coalesce(func.sum(Trade.dca_levels), 0)).where(
        Trade.position_id == position.id, Trade.trade_type == "dca"
    )
    safety_orders_deployed = int((await db.execute(so_deployed_query)).scalar() or 0)

    pos_response = PositionResponse.model_validate(position)
    pos_response.trade_count = trade_count
    pos_response.safety_orders_deployed = safety_orders_deployed
    pos_response.pending_orders_count = pending_count

    # Set first/last buy prices for DCA reference
    if first_buy_price is not None:
        pos_response.first_buy_price = first_buy_price
        pos_response.last_buy_price = last_buy_price

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
async def get_position_trades(
    position_id: int, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all trades for a position (verifies ownership)"""
    # Verify position belongs to current user
    user_account_ids = await accessible_account_ids(db, current_user.id)

    pos_query = select(Position).where(
        Position.id == position_id,
        Position.account_id.in_(user_account_ids) if user_account_ids else Position.id < 0,
    )
    pos_result = await db.execute(pos_query)
    if not pos_result.scalars().first():
        raise HTTPException(status_code=404, detail="Position not found")

    query = select(Trade).where(Trade.position_id == position_id).order_by(Trade.timestamp)
    result = await db.execute(query)
    trades = result.scalars().all()

    return [TradeResponse.model_validate(t) for t in trades]


@router.get("/{position_id}/ai-logs", response_model=List[AIBotLogResponse])
async def get_position_ai_logs(
    position_id: int, include_before_open: bool = True,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    Get AI reasoning logs for a position.

    By default, includes logs from 30 seconds before position opened and
    30 seconds after position closed. This captures the AI's complete
    decision-making process including what led to opening and closing.
    """
    # Verify position belongs to current user
    user_account_ids = await accessible_account_ids(db, current_user.id)

    pos_query = select(Position).where(
        Position.id == position_id,
        Position.account_id.in_(user_account_ids) if user_account_ids else Position.id < 0,
    )
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
            time_after = utcnow() + timedelta(days=365)

        query = select(AIBotLog).where(
            (AIBotLog.position_id == position_id)
            | (
                (AIBotLog.bot_id == position.bot_id)
                & (AIBotLog.product_id == position.product_id)
                & (AIBotLog.timestamp >= time_before)
                & (AIBotLog.timestamp <= time_after)
                & (AIBotLog.position_id.is_(None))  # SQL IS NULL (not Python `is None`)
            )
        )

    query = query.order_by(AIBotLog.timestamp)

    result = await db.execute(query)
    logs = result.scalars().all()

    return [AIBotLogResponse.model_validate(log) for log in logs]


@router.get("/{position_id}/ai-opinion", response_model=Optional[AIOpinionLogResponse])
async def get_position_ai_opinion(
    position_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the most recent AI opinion log for a position, including any
    tool_calls the model issued (Phase E — tool-use transparency UI).

    Returns `null` when the position has no opinion logged yet — the Positions
    page renders this widget for every row, so a missing opinion is the
    expected common case and should not surface as a 404 in the browser.
    """
    user_account_ids = await accessible_account_ids(db, current_user.id)

    pos_query = select(Position).where(
        Position.id == position_id,
        Position.account_id.in_(user_account_ids) if user_account_ids else Position.id < 0,
    )
    position = (await db.execute(pos_query)).scalars().first()
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    opinion_query = (
        select(AIOpinionLog)
        .where(AIOpinionLog.position_id == position_id)
        .order_by(desc(AIOpinionLog.created_at))
        .limit(1)
    )
    opinion = (await db.execute(opinion_query)).scalars().first()
    if not opinion:
        return None

    return AIOpinionLogResponse.model_validate(opinion)
