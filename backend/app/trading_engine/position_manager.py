"""
Position management utilities for trading engine

Handles position CRUD operations:
- Getting active positions
- Counting open positions
- Creating new positions
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.coinbase_unified_client import CoinbaseClient
from app.models import Bot, Position


async def get_active_position(
    db: AsyncSession,
    bot: Bot,
    product_id: str
) -> Optional[Position]:
    """Get currently active position for this bot/pair combination"""
    query = select(Position).options(
        selectinload(Position.trades)  # Eager load trades to avoid greenlet errors in should_buy()
    ).where(
        Position.bot_id == bot.id,
        Position.product_id == product_id,  # Filter by pair for multi-pair support
        Position.status == "open"
    ).order_by(desc(Position.opened_at))

    result = await db.execute(query)
    return result.scalars().first()


async def get_open_positions_count(
    db: AsyncSession,
    bot: Bot
) -> int:
    """Get count of all open positions for this bot (across all pairs)"""
    query = select(func.count(Position.id)).where(
        Position.bot_id == bot.id,
        Position.status == "open"
    )
    result = await db.execute(query)
    return result.scalar() or 0


async def create_position(
    db: AsyncSession,
    coinbase: CoinbaseClient,
    bot: Bot,
    product_id: str,
    quote_balance: float,
    quote_amount: float
) -> Position:
    """
    Create a new position for this bot

    Args:
        db: Database session
        coinbase: Coinbase client
        bot: Bot instance
        product_id: Trading pair
        quote_balance: Current total quote currency balance (BTC or USD)
        quote_amount: Amount of quote currency being spent on initial buy
    """
    # Get BTC/USD price for USD tracking
    try:
        btc_usd_price = await coinbase.get_btc_usd_price()
    except Exception:
        btc_usd_price = None

    position = Position(
        bot_id=bot.id,
        product_id=product_id,  # Use the engine's product_id (specific pair being traded)
        status="open",
        opened_at=datetime.utcnow(),
        initial_quote_balance=quote_balance,
        max_quote_allowed=quote_balance,  # Strategy determines actual limits
        total_quote_spent=0.0,
        total_base_acquired=0.0,
        average_buy_price=0.0,
        btc_usd_price_at_open=btc_usd_price,
        strategy_config_snapshot=bot.strategy_config  # Freeze config at position creation (like 3Commas)
    )

    db.add(position)
    # Don't commit here - let caller commit after trade succeeds
    # This ensures position only persists if trade is successful
    await db.flush()  # Flush to get position.id but don't commit

    return position
