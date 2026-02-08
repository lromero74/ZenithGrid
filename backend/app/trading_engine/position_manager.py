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
    Calculate the expected total budget for a position including base order + safety orders.

    This handles both manual sizing mode AND fixed base orders with safety orders enabled.
    When using fixed base orders with safety orders, the total budget must include room
    for all potential safety orders to prevent over-allocation.

    Args:
        config: Bot strategy config with order sizing parameters
        aggregate_value: Total account liquidation value (for percentage calculations)

    Returns:
        Expected total budget for this position (base + all safety orders), or 0.0 if using percentage-based sizing
    """
    # CRITICAL: If auto-calculate is enabled, return 0 to use quote_balance as max_quote_allowed
    # Auto-calculate dynamically sizes orders based on available budget, not config values
    if config.get("auto_calculate_order_sizes", False):
        return 0.0

    # Handle manual sizing mode (original logic)
    if config.get("use_manual_sizing", False) and aggregate_value > 0:
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

    # Handle fixed base orders with safety orders (MACD Bot, etc.)
    base_order_type = config.get("base_order_type", "percentage")
    max_safety_orders = config.get("max_safety_orders", 0)

    # Only calculate total budget for fixed orders with safety orders enabled
    if base_order_type in ["fixed", "fixed_btc"] and max_safety_orders > 0:
        total_expected = 0.0

        # Get base order size (minimum 0.0001 BTC for Coinbase)
        # IMPORTANT: Match the logic in calculate_base_order_size() - prioritize base_order_btc over base_order_fixed
        base_order_btc = config.get("base_order_btc", 0.0001)
        base_order_fixed = config.get("base_order_fixed", 0.001)

        # Use base_order_btc if it's explicitly set (not default) or if order_type is "fixed_btc"
        if base_order_type == "fixed_btc" or (base_order_btc != 0.0001 and base_order_btc < base_order_fixed):
            base_order_size = base_order_btc
        else:
            base_order_size = base_order_fixed

        base_order_size = max(base_order_size, 0.0001)  # Enforce Coinbase minimum
        total_expected += base_order_size

        # Calculate safety orders with volume scaling
        safety_order_type = config.get("safety_order_type", "percentage_of_base")
        volume_scale = config.get("safety_order_volume_scale", 1.0)

        for order_num in range(1, max_safety_orders + 1):
            # Calculate base safety order size
            # IMPORTANT: Match the logic in calculate_safety_order_size()
            if safety_order_type == "percentage_of_base":
                base_safety_size = base_order_size * (config.get("safety_order_percentage", 50.0) / 100.0)
            elif safety_order_type in ["fixed", "fixed_btc"]:
                # Prioritize safety_order_btc over safety_order_fixed (match execution logic)
                base_safety_size = config.get("safety_order_btc", 0.0001)
            else:
                # Fallback for legacy configs
                base_safety_size = config.get("safety_order_fixed", 0.0005)

            # Apply volume scaling (each subsequent order scales up)
            safety_order_size = base_safety_size * (volume_scale ** (order_num - 1))
            total_expected += safety_order_size

        return total_expected

    # For percentage-based orders or no safety orders, return 0 (use default per-position budget)
    return 0.0


def calculate_max_deal_cost(config: dict, base_order_size: float) -> float:
    """
    Calculate the true max cost of a deal: base order + all safety orders with volume scaling.

    Use this when calculate_expected_position_budget() returns 0 (percentage-based or auto-calc modes)
    and we need to derive the max cost from the position's actual first buy size.

    Args:
        config: Bot strategy config with safety order parameters
        base_order_size: The actual base order size (e.g. from the position's first trade)

    Returns:
        Total max cost (base + all safety orders)
    """
    if base_order_size <= 0:
        return 0.0

    total = base_order_size
    max_safety_orders = config.get("max_safety_orders", 0)

    if max_safety_orders <= 0:
        return total

    # Check for manual sizing mode (DCA orders)
    if config.get("use_manual_sizing", False):
        dca_order_type = config.get("dca_order_type", "percentage")
        dca_order_value = config.get("dca_order_value", 0.0)
        dca_multiplier = config.get("dca_order_multiplier", 1.0)
        max_dca_orders = config.get("manual_max_dca_orders", max_safety_orders)

        for i in range(max_dca_orders):
            order_size = dca_order_value * (dca_multiplier ** i)
            if dca_order_type == "percentage":
                # percentage of base order
                total += base_order_size * (order_size / 100.0)
            else:
                total += order_size
        return total

    # Standard safety order calculation (matches lines 92-109 logic)
    safety_order_type = config.get("safety_order_type", "percentage_of_base")
    volume_scale = config.get("safety_order_volume_scale", 1.0)

    for order_num in range(1, max_safety_orders + 1):
        if safety_order_type == "percentage_of_base":
            base_safety_size = base_order_size * (config.get("safety_order_percentage", 50.0) / 100.0)
        elif safety_order_type in ["fixed", "fixed_btc"]:
            base_safety_size = config.get("safety_order_btc", 0.0001)
        else:
            base_safety_size = config.get("safety_order_fixed", 0.0005)

        safety_order_size = base_safety_size * (volume_scale ** (order_num - 1))
        total += safety_order_size

    return total


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


async def get_next_user_attempt_number(db: AsyncSession, user_id: int) -> int:
    """Get the next attempt number for a user (max + 1, or 1 if no positions exist)"""
    query = select(func.max(Position.user_attempt_number)).where(Position.user_id == user_id)
    result = await db.execute(query)
    max_attempt_number = result.scalar()
    return (max_attempt_number or 0) + 1


async def get_next_user_deal_number(db: AsyncSession, user_id: int) -> int:
    """Get the next deal number for a user (max + 1, or 1 if no positions exist)

    Note: Deal numbers are only for SUCCESSFUL deals (where base order executed).
    Failed position attempts get an attempt_number but not a deal_number.
    """
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
    direction: str = "long",
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
        direction: Position direction - "long" (buy) or "short" (sell)
    """
    # Get BTC/USD price for USD tracking
    try:
        btc_usd_price = await exchange.get_btc_usd_price()
    except Exception:
        btc_usd_price = None

    # Get next user-specific attempt number (assigned BEFORE base order attempt)
    # Deal number will be assigned AFTER successful base order execution
    user_id = bot.user_id
    user_attempt_number = await get_next_user_attempt_number(db, user_id) if user_id else None

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
        user_id=user_id,  # Owner (for user-specific numbers)
        user_attempt_number=user_attempt_number,  # Sequential attempt number (ALL attempts: success + failed)
        user_deal_number=None,  # Will be assigned AFTER successful base order execution
        product_id=product_id,  # Use the engine's product_id (specific pair being traded)
        status="open",
        direction=direction,  # "long" or "short" for bidirectional DCA
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
