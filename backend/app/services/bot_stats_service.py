"""
Bot Stats Service

Calculates PnL, win rate, trades/day, budget utilization, and daily PnL
projections for bot listings. Extracted from bot_crud_router.list_bots().
"""

import asyncio
from app.utils.timeutil import utcnow
import logging
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Position
from app.services.pnl_service import resolve_btc_usd_price

logger = logging.getLogger(__name__)


async def fetch_aggregate_values(coinbase) -> Tuple[Optional[float], Optional[float]]:
    """Fetch BTC and USD aggregate budget values for bot budget allocation.

    Uses calculate_market_budget (free currency + positions in that
    currency's pairs) — NOT calculate_aggregate_usd_value which returns the
    total portfolio value including all assets converted to USD.
    """
    async def fetch_btc():
        try:
            return await coinbase.calculate_market_budget("BTC")
        except Exception as e:
            logger.warning(f"Could not calculate aggregate BTC value: {e}")
            return None

    async def fetch_usd():
        try:
            return await coinbase.calculate_market_budget("USD")
        except Exception as e:
            logger.warning(f"Could not calculate aggregate USD value: {e}")
            return None

    return await asyncio.gather(fetch_btc(), fetch_usd())


async def fetch_position_prices(
    coinbase, unique_products: List[str], batch_size: int = 15
) -> Dict[str, float]:
    """Batch-fetch current prices for a list of product IDs.

    Prefers one bulk-cached fetch over N serial per-product ticker calls
    (the latter pays a ~150ms auth rate-limit lock per call, which
    dominates cold-path latency when the list grows past ~20 products).
    Falls back to the per-product path for any IDs the bulk call didn't
    cover (delisted coins, bulk endpoint failure).
    """
    if not unique_products:
        return {}

    from app.coinbase_api.public_market_data import bulk_prices_for_products
    position_prices: Dict[str, float] = await bulk_prices_for_products(unique_products)

    missing = [pid for pid in unique_products if pid not in position_prices]
    if not missing:
        return position_prices

    async def fetch_price(product_id: str):
        try:
            price = await coinbase.get_current_price(product_id)
            return (product_id, price)
        except Exception:
            return (product_id, None)

    for i in range(0, len(missing), batch_size):
        batch = missing[i:i + batch_size]
        batch_results = await asyncio.gather(*[fetch_price(pid) for pid in batch])
        for pid, price in batch_results:
            if price is not None:
                position_prices[pid] = price
        if i + batch_size < len(missing):
            await asyncio.sleep(0.2)

    return position_prices


def calculate_bot_pnl(
    bot,
    closed_positions: List,
    open_positions: List,
    projection_timeframe: Optional[str] = "all",
) -> dict:
    """
    Calculate PnL metrics for a single bot.

    Returns dict with: total_pnl_usd, total_pnl_btc, total_pnl_percentage,
    avg_daily_pnl_usd, avg_daily_pnl_btc, trades_per_day, win_rate.
    """
    # Determine timeframe cutoff for recent PnL
    timeframe_days_map = {
        '7d': 7, '14d': 14, '30d': 30,
        '3m': 90, '6m': 180, '1y': 365,
        'all': None,
    }
    timeframe_days = timeframe_days_map.get(projection_timeframe, None)
    cutoff_date = (
        utcnow() - timedelta(days=timeframe_days) if timeframe_days else None
    )

    # Single pass over closed_positions: accumulate all metrics at once
    total_pnl_usd = 0.0
    total_pnl_btc = 0.0
    recent_pnl_usd = 0.0
    recent_pnl_btc = 0.0
    winning_count = 0
    total_capital_deployed_usd = 0.0

    for pos in closed_positions:
        profit_usd = pos.profit_usd or 0.0
        is_btc_pair = pos.product_id and "-BTC" in pos.product_id

        # BTC profit conversion
        if is_btc_pair:
            profit_btc = pos.profit_quote or 0.0
        else:
            btc_price = resolve_btc_usd_price(pos)
            profit_btc = profit_usd / btc_price if btc_price > 0 else 0.0

        total_pnl_usd += profit_usd
        total_pnl_btc += profit_btc

        # Recent PnL (within timeframe)
        is_recent = cutoff_date is None or (pos.closed_at and pos.closed_at >= cutoff_date)
        if is_recent:
            recent_pnl_usd += profit_usd
            recent_pnl_btc += profit_btc

        # Win count: only bot-driven closes with positive profit
        if pos.exit_reason != "manual" and pos.profit_usd is not None and pos.profit_usd > 0:
            winning_count += 1

        # Capital deployed
        quote_spent = pos.total_quote_spent or 0.0
        if is_btc_pair:
            deploy_btc_price = resolve_btc_usd_price(pos)
            total_capital_deployed_usd += quote_spent * deploy_btc_price
        else:
            total_capital_deployed_usd += quote_spent

    # Calculate derived metrics
    if timeframe_days is None:
        days_in_recent_period = max(1, (utcnow() - bot.created_at).total_seconds() / 86400)
    else:
        days_in_recent_period = timeframe_days

    avg_daily_pnl_usd = recent_pnl_usd / days_in_recent_period
    avg_daily_pnl_btc = recent_pnl_btc / days_in_recent_period

    # Trades per day (all-time)
    days_active = (utcnow() - bot.created_at).total_seconds() / 86400
    trades_per_day = len(closed_positions) / days_active if days_active > 0 else 0.0

    # Win rate: exclude manual closes (user intervention) from denominator
    bot_driven_positions = [p for p in closed_positions if p.exit_reason != "manual"]
    win_rate = (winning_count / len(bot_driven_positions) * 100) if bot_driven_positions else 0.0

    # PnL percentage
    total_pnl_percentage = (
        (total_pnl_usd / total_capital_deployed_usd * 100)
        if total_capital_deployed_usd > 0 else 0.0
    )

    # Aggregate running days: stored seconds + current session (if active)
    running_secs = bot.total_running_seconds or 0.0
    if bot.is_active and bot.last_started_at is not None:
        running_secs += (utcnow() - bot.last_started_at).total_seconds()
    aggregate_running_days = running_secs / 86400.0

    # Calendar days since creation
    calendar_days = (utcnow() - bot.created_at).total_seconds() / 86400.0

    # PnL per active day (only when bot has meaningful running time; else same as avg_daily)
    if aggregate_running_days >= 0.01:
        avg_daily_pnl_usd_active = recent_pnl_usd / aggregate_running_days
        avg_daily_pnl_btc_active = recent_pnl_btc / aggregate_running_days
    else:
        avg_daily_pnl_usd_active = avg_daily_pnl_usd
        avg_daily_pnl_btc_active = avg_daily_pnl_btc

    return {
        "total_pnl_usd": total_pnl_usd,
        "total_pnl_btc": total_pnl_btc,
        "total_pnl_percentage": total_pnl_percentage,
        "avg_daily_pnl_usd": avg_daily_pnl_usd,
        "avg_daily_pnl_btc": avg_daily_pnl_btc,
        "avg_daily_pnl_usd_active": avg_daily_pnl_usd_active,
        "avg_daily_pnl_btc_active": avg_daily_pnl_btc_active,
        "trades_per_day": trades_per_day,
        "win_rate": win_rate,
        "aggregate_running_days": aggregate_running_days,
        "calendar_days": calendar_days,
    }


def calculate_budget_utilization(
    bot,
    open_positions: List,
    position_prices: Dict[str, float],
    aggregate_btc_value: Optional[float],
    aggregate_usd_value: Optional[float],
) -> dict:
    """
    Calculate budget utilization % and insufficient_funds flag for a bot.

    Returns dict with: budget_utilization_percentage, insufficient_funds.
    """
    insufficient_funds = False
    budget_utilization_percentage = 0.0
    max_concurrent_deals = (
        bot.strategy_config.get("max_concurrent_deals")
        or bot.strategy_config.get("max_concurrent_positions")
        or 1
    )

    try:
        quote_currency = bot.get_quote_currency()

        if quote_currency == "BTC":
            aggregate_value = aggregate_btc_value
        else:
            aggregate_value = aggregate_usd_value

        if aggregate_value is None:
            raise ValueError(f"No aggregate {quote_currency} value available")

        reserved_balance = bot.get_reserved_balance(aggregate_value)

        total_in_positions_value = 0.0
        for position in open_positions:
            current_price = position_prices.get(position.product_id)
            if current_price is not None:
                total_in_positions_value += position.total_base_acquired * current_price
            else:
                total_in_positions_value += position.total_quote_spent

        if reserved_balance > 0:
            budget_utilization_percentage = (total_in_positions_value / reserved_balance) * 100

        if len(open_positions) < max_concurrent_deals:
            available_budget = reserved_balance - total_in_positions_value
            min_per_position = reserved_balance / max(max_concurrent_deals, 1)
            insufficient_funds = available_budget < min_per_position

    except Exception as e:
        logger.error(f"Error calculating budget for bot {bot.id}: {e}")
        insufficient_funds = False
        budget_utilization_percentage = 0.0

    return {
        "budget_utilization_percentage": budget_utilization_percentage,
        "insufficient_funds": insufficient_funds,
    }


async def get_open_position_products(
    db: AsyncSession, user_id: int
) -> Tuple[List, List[str]]:
    """
    Get all open positions for a user and return unique product IDs.

    Returns (all_open_positions, unique_product_ids).
    """
    # All accounts the user can access (owned + shared/managed) — not just owned,
    # so positions on shared accounts also get their prices prefetched.
    from app.services.account_access import accessible_account_ids
    user_account_ids = await accessible_account_ids(db, user_id)

    all_open_query = select(Position).where(
        Position.status == "open",
        Position.account_id.in_(user_account_ids) if user_account_ids else Position.id < 0,
    )
    all_open_result = await db.execute(all_open_query)
    all_open_positions = all_open_result.scalars().all()

    unique_products = list({p.product_id for p in all_open_positions})
    return all_open_positions, unique_products
