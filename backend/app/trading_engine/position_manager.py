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

from app.exchange_clients.base import ExchangeClient
from app.models import Bot, Position


def calculate_expected_position_budget(config: dict, aggregate_value: float) -> float:
    """
    Calculate the expected total budget for a position based on manual sizing config.

    When using manual sizing with percentage-based orders, the budget should equal
    the sum of all expected orders (base + DCAs), not the per-position allocation.

    Args:
        config: Bot strategy config with manual sizing parameters
        aggregate_value: Total account liquidation value (for percentage calculations)

    Returns:
        Expected total budget for this position based on configured order sizes
    """
    if not config.get("use_manual_sizing", False) or aggregate_value <= 0:
        return 0.0  # Caller should use default per-position budget

    # Get order sizing config
    base_order_type = config.get("base_order_type", "percentage")
    base_order_value = config.get("base_order_value", 0.0)
    dca_order_type = config.get("dca_order_type", "percentage")
    dca_order_value = config.get("dca_order_value", 0.0)
    dca_multiplier = config.get("dca_order_multiplier", 1.0)
    max_dca_orders = config.get("manual_max_dca_orders", config.get("max_safety_orders", 3))

    total_expected = 0.0

    # Calculate base order amount
    if base_order_type == "percentage":
        total_expected += aggregate_value * (base_order_value / 100.0)
    else:
        total_expected += base_order_value

    # Calculate DCA orders amount (each can have multiplier)
    for i in range(max_dca_orders):
        order_size = dca_order_value * (dca_multiplier ** i)
        if dca_order_type == "percentage":
            total_expected += aggregate_value * (order_size / 100.0)
        else:
            total_expected += order_size

    return total_expected


async def get_active_position(db: AsyncSession, bot: Bot, product_id: str) -> Optional[Position]:
    """Get currently active position for this bot/pair combination"""
    query = (
        select(Position)
        .options(selectinload(Position.trades))  # Eager load trades to avoid greenlet errors in should_buy()
        .where(
            Position.bot_id == bot.id,
            Position.product_id == product_id,  # Filter by pair for multi-pair support
            Position.status == "open",
        )
        .order_by(desc(Position.opened_at))
    )

    result = await db.execute(query)
    return result.scalars().first()


async def get_open_positions_count(db: AsyncSession, bot: Bot) -> int:
    """Get count of all open positions for this bot (across all pairs)"""
    query = select(func.count(Position.id)).where(Position.bot_id == bot.id, Position.status == "open")
    result = await db.execute(query)
    return result.scalar() or 0


async def get_next_user_deal_number(db: AsyncSession, user_id: int) -> int:
    """Get the next deal number for a user (max + 1, or 1 if no positions exist)"""
    query = select(func.max(Position.user_deal_number)).where(Position.user_id == user_id)
    result = await db.execute(query)
    max_deal_number = result.scalar()
    return (max_deal_number or 0) + 1


async def create_position(
    db: AsyncSession,
    exchange: ExchangeClient,
    bot: Bot,
    product_id: str,
    quote_balance: float,
    quote_amount: float,
    aggregate_value: float = None,
    pattern_data: dict = None,
) -> Position:
    """
    Create a new position for this bot

    Args:
        db: Database session
        exchange: Exchange client instance (CEX or DEX)
        bot: Bot instance
        product_id: Trading pair
        quote_balance: Current per-position budget (BTC or USD)
        quote_amount: Amount of quote currency being spent on initial buy
        aggregate_value: Total account liquidation value (for manual sizing budget calc)
        pattern_data: Optional pattern data (bull_flag targets: entry, stop_loss, take_profit_target)
    """
    # Get BTC/USD price for USD tracking
    try:
        btc_usd_price = await exchange.get_btc_usd_price()
    except Exception:
        btc_usd_price = None

    # Get next user-specific deal number
    user_id = bot.user_id
    user_deal_number = await get_next_user_deal_number(db, user_id) if user_id else None

    # Calculate max_quote_allowed based on sizing mode
    # For manual sizing with percentage orders, use expected order totals
    # For AI mode or fixed orders, use the per-position budget
    config = bot.strategy_config or {}
    expected_budget = calculate_expected_position_budget(config, aggregate_value or 0)
    if expected_budget > 0:
        max_quote = expected_budget
    else:
        max_quote = quote_balance

    position = Position(
        bot_id=bot.id,
        account_id=bot.account_id,  # Copy account_id from bot for filtering
        user_id=user_id,  # Owner (for user-specific deal numbers)
        user_deal_number=user_deal_number,  # User-specific sequential deal number
        product_id=product_id,  # Use the engine's product_id (specific pair being traded)
        status="open",
        opened_at=datetime.utcnow(),
        initial_quote_balance=quote_balance,
        max_quote_allowed=max_quote,  # Expected total based on order sizes
        total_quote_spent=0.0,
        total_base_acquired=0.0,
        average_buy_price=0.0,
        btc_usd_price_at_open=btc_usd_price,
        strategy_config_snapshot=bot.strategy_config,  # Freeze config at position creation (like 3Commas)
    )

    # If pattern data provided (e.g., bull_flag), set up trailing stops
    if pattern_data:
        import json
        position.entry_stop_loss = pattern_data.get("stop_loss")
        position.entry_take_profit_target = pattern_data.get("take_profit_target")
        position.trailing_stop_loss_price = position.entry_stop_loss
        position.trailing_stop_loss_active = True
        position.trailing_tp_active = False
        position.pattern_data = json.dumps(pattern_data)

    db.add(position)
    # Don't commit here - let caller commit after trade succeeds
    # This ensures position only persists if trade is successful
    await db.flush()  # Flush to get position.id but don't commit

    return position
