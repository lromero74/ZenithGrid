"""
Bot Stats Service

Calculates PnL, win rate, trades/day, budget utilization, and daily PnL
projections for bot listings. Extracted from bot_crud_router.list_bots().
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Position

logger = logging.getLogger(__name__)


async def fetch_aggregate_values(coinbase) -> Tuple[Optional[float], Optional[float]]:
    """Fetch BTC and USD aggregate portfolio values in parallel."""
    async def fetch_btc():
        try:
            return await coinbase.calculate_aggregate_btc_value()
        except Exception as e:
            logger.warning(f"Could not calculate aggregate BTC value: {e}")
            return None

    async def fetch_usd():
        try:
            return await coinbase.calculate_aggregate_usd_value()
        except Exception as e:
            logger.warning(f"Could not calculate aggregate USD value: {e}")
            return None

    return await asyncio.gather(fetch_btc(), fetch_usd())


async def fetch_position_prices(
    coinbase, unique_products: List[str], batch_size: int = 15
) -> Dict[str, float]:
    """Batch-fetch current prices for a list of product IDs."""
    position_prices = {}

    async def fetch_price(product_id: str):
        try:
            price = await coinbase.get_current_price(product_id)
            return (product_id, price)
        except Exception:
            return (product_id, None)

    for i in range(0, len(unique_products), batch_size):
        batch = unique_products[i:i + batch_size]
        batch_results = await asyncio.gather(*[fetch_price(pid) for pid in batch])
        for pid, price in batch_results:
            if price is not None:
                position_prices[pid] = price
        if i + batch_size < len(unique_products):
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
    # Total PnL (closed positions only)
    total_pnl_usd = 0.0
    total_pnl_btc = 0.0
    for pos in closed_positions:
        profit_usd = pos.profit_usd or 0.0
        total_pnl_usd += profit_usd

        if pos.product_id and "-BTC" in pos.product_id:
            profit_btc = pos.profit_quote or 0.0
        else:
            btc_price = pos.btc_usd_price_at_close or pos.btc_usd_price_at_open or 100000.0
            profit_btc = profit_usd / btc_price if btc_price > 0 else 0.0
        total_pnl_btc += profit_btc

    # Filter positions by projection timeframe
    timeframe_days_map = {
        '7d': 7, '14d': 14, '30d': 30,
        '3m': 90, '6m': 180, '1y': 365,
        'all': None,
    }
    timeframe_days = timeframe_days_map.get(projection_timeframe, None)

    if timeframe_days is None:
        recent_closed = closed_positions
    else:
        cutoff_date = datetime.utcnow() - timedelta(days=timeframe_days)
        recent_closed = [
            p for p in closed_positions
            if p.closed_at and p.closed_at >= cutoff_date
        ]

    recent_pnl_usd = sum(p.profit_usd for p in recent_closed if p.profit_usd)

    recent_pnl_btc = 0.0
    for pos in recent_closed:
        profit_usd = pos.profit_usd or 0.0
        if pos.product_id and "-BTC" in pos.product_id:
            profit_btc = pos.profit_quote or 0.0
        else:
            btc_price = pos.btc_usd_price_at_close or pos.btc_usd_price_at_open or 100000.0
            profit_btc = profit_usd / btc_price if btc_price > 0 else 0.0
        recent_pnl_btc += profit_btc

    # Calculate days in period
    if timeframe_days is None:
        days_in_recent_period = max(1, (datetime.utcnow() - bot.created_at).total_seconds() / 86400)
    else:
        days_in_recent_period = timeframe_days

    avg_daily_pnl_usd = recent_pnl_usd / days_in_recent_period
    avg_daily_pnl_btc = recent_pnl_btc / days_in_recent_period

    # Trades per day (all-time)
    days_active = (datetime.utcnow() - bot.created_at).total_seconds() / 86400
    trades_per_day = len(closed_positions) / days_active if days_active > 0 else 0.0

    # Win rate
    winning = [p for p in closed_positions if p.profit_usd is not None and p.profit_usd > 0]
    win_rate = (len(winning) / len(closed_positions) * 100) if closed_positions else 0.0

    # PnL percentage (total_pnl_usd / total capital deployed)
    total_capital_deployed_usd = 0.0
    for pos in closed_positions:
        quote_spent = pos.total_quote_spent or 0.0
        if pos.product_id and "-BTC" in pos.product_id:
            btc_price = pos.btc_usd_price_at_close or pos.btc_usd_price_at_open or 100000.0
            total_capital_deployed_usd += quote_spent * btc_price
        else:
            total_capital_deployed_usd += quote_spent
    total_pnl_percentage = (
        (total_pnl_usd / total_capital_deployed_usd * 100)
        if total_capital_deployed_usd > 0 else 0.0
    )

    return {
        "total_pnl_usd": total_pnl_usd,
        "total_pnl_btc": total_pnl_btc,
        "total_pnl_percentage": total_pnl_percentage,
        "avg_daily_pnl_usd": avg_daily_pnl_usd,
        "avg_daily_pnl_btc": avg_daily_pnl_btc,
        "trades_per_day": trades_per_day,
        "win_rate": win_rate,
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
    user_accounts_q = select(Account.id).where(Account.user_id == user_id)
    user_accounts_r = await db.execute(user_accounts_q)
    user_account_ids = [row[0] for row in user_accounts_r.fetchall()]

    all_open_query = select(Position).where(
        Position.status == "open",
        Position.account_id.in_(user_account_ids) if user_account_ids else Position.id < 0,
    )
    all_open_result = await db.execute(all_open_query)
    all_open_positions = all_open_result.scalars().all()

    unique_products = list({p.product_id for p in all_open_positions})
    return all_open_positions, unique_products
