"""
Grid Trading Service

Handles grid bot lifecycle:
- Grid initialization (place all limit orders)
- Order fill detection and response
- Grid rebalancing on breakouts
- Capital reservation management
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bot, PendingOrder, Position
from app.exchange_clients.base import ExchangeClient

logger = logging.getLogger(__name__)


async def initialize_grid(
    bot: Bot,
    position: Position,
    exchange_client: ExchangeClient,
    db: AsyncSession,
    grid_config: Dict[str, Any],
    current_price: float,
) -> Dict[str, Any]:
    """
    Initialize a new grid by placing all limit orders.

    This function:
    1. Calculates order size per level
    2. Places buy orders below current price
    3. Places sell orders above current price (if neutral mode)
    4. Sets reserved_amount_quote/base on each order
    5. Updates grid_state in bot config

    Args:
        bot: Bot instance
        position: Position to track grid
        exchange_client: Exchange client for placing orders
        db: Database session
        grid_config: Grid configuration from analyze_signal
        current_price: Current market price

    Returns:
        Dict with grid_state including placed order IDs
    """
    grid_mode = grid_config.get("grid_mode", "neutral")
    levels = grid_config["levels"]
    total_investment = bot.bot_config.get("total_investment_quote", 0)
    product_id = bot.product_id

    logger.info(f"🌐 Initializing {grid_mode} grid for {product_id} with {len(levels)} levels")
    logger.info(f"   Current price: {current_price:.8f}, Investment: {total_investment:.8f}")

    # Calculate order size per level
    if grid_mode == "neutral":
        # Neutral grid: split investment across buy orders (sell side uses existing base currency)
        buy_levels = [level for level in levels if level < current_price]
        num_buy_orders = len(buy_levels)

        if num_buy_orders == 0:
            raise ValueError(f"No buy levels below current price {current_price:.8f}")

        order_size_quote = total_investment / num_buy_orders

        logger.info(f"   Neutral mode: {num_buy_orders} buy orders @ {order_size_quote:.8f} each")

    elif grid_mode == "long":
        # Long grid: all investment goes into buy orders
        num_buy_orders = len(levels)
        order_size_quote = total_investment / num_buy_orders

        logger.info(f"   Long mode: {num_buy_orders} buy orders @ {order_size_quote:.8f} each")

    else:
        raise ValueError(f"Unsupported grid_mode: {grid_mode}")

    # Track placed orders
    placed_orders = []
    buy_orders_placed = 0
    sell_orders_placed = 0

    # Place buy orders (below current price for neutral, all levels for long)
    for i, level_price in enumerate(levels):
        # Skip levels above current price in neutral mode
        if grid_mode == "neutral" and level_price >= current_price:
            continue

        # Calculate base amount for this buy order
        base_amount = order_size_quote / level_price

        try:
            # Place limit buy order on exchange
            logger.debug(f"   Placing buy order: price={level_price:.8f}, size={base_amount:.8f}")

            order_response = await exchange_client.create_limit_order(
                product_id=product_id,
                side="BUY",
                limit_price=level_price,
                size=str(base_amount),
                time_in_force="gtc",
            )

            order_id = order_response.get("order_id") or order_response.get("success_response", {}).get("order_id")

            if not order_id:
                logger.error(f"No order_id in response: {order_response}")
                continue

            # Create PendingOrder record with capital reservation
            pending_order = PendingOrder(
                position_id=position.id,
                bot_id=bot.id,
                order_id=order_id,
                product_id=product_id,
                side="BUY",
                order_type="LIMIT",
                limit_price=level_price,
                quote_amount=order_size_quote,
                base_amount=base_amount,
                trade_type=f"grid_buy_{i}",
                status="pending",
                reserved_amount_quote=order_size_quote,  # Reserve quote currency
                reserved_amount_base=0.0,
                time_in_force="gtc",
                is_manual=False,
            )

            db.add(pending_order)
            buy_orders_placed += 1

            placed_orders.append({
                "level_index": i,
                "price": level_price,
                "order_type": "buy",
                "order_id": order_id,
                "status": "pending",
                "size": base_amount,
                "reserved_quote": order_size_quote,
            })

            logger.info(f"   ✅ Buy order placed at {level_price:.8f} (order_id: {order_id[:8]}...)")

        except Exception as e:
            logger.error(f"Failed to place buy order at {level_price:.8f}: {e}")
            # Continue with other orders

    # Place sell orders (only in neutral mode, above current price)
    if grid_mode == "neutral":
        sell_levels = [level for level in levels if level > current_price]

        # For sell orders, we need base currency
        # Calculate how much base currency to sell at each level
        # This assumes user has existing base currency inventory
        # TODO: Add validation that user has enough base currency

        for i, level_price in enumerate(sell_levels):
            # Calculate size for sell order
            # For now, use same quote value as buy orders
            base_amount = order_size_quote / level_price

            try:
                logger.debug(f"   Placing sell order: price={level_price:.8f}, size={base_amount:.8f}")

                order_response = await exchange_client.create_limit_order(
                    product_id=product_id,
                    side="SELL",
                    limit_price=level_price,
                    size=str(base_amount),
                    time_in_force="gtc",
                )

                order_id = order_response.get("order_id") or order_response.get("success_response", {}).get("order_id")

                if not order_id:
                    logger.error(f"No order_id in sell response: {order_response}")
                    continue

                # Create PendingOrder record with base currency reservation
                pending_order = PendingOrder(
                    position_id=position.id,
                    bot_id=bot.id,
                    order_id=order_id,
                    product_id=product_id,
                    side="SELL",
                    order_type="LIMIT",
                    limit_price=level_price,
                    quote_amount=order_size_quote,
                    base_amount=base_amount,
                    trade_type=f"grid_sell_{i}",
                    status="pending",
                    reserved_amount_quote=0.0,
                    reserved_amount_base=base_amount,  # Reserve base currency
                    time_in_force="gtc",
                    is_manual=False,
                )

                db.add(pending_order)
                sell_orders_placed += 1

                placed_orders.append({
                    "level_index": len(levels) - len(sell_levels) + i,
                    "price": level_price,
                    "order_type": "sell",
                    "order_id": order_id,
                    "status": "pending",
                    "size": base_amount,
                    "reserved_base": base_amount,
                })

                logger.info(f"   ✅ Sell order placed at {level_price:.8f} (order_id: {order_id[:8]}...)")

            except Exception as e:
                logger.error(f"Failed to place sell order at {level_price:.8f}: {e}")

    # Commit all pending orders to database
    await db.commit()

    # Create grid state
    grid_state = {
        "initialized_at": datetime.utcnow().isoformat(),
        "current_range_upper": grid_config["upper_limit"],
        "current_range_lower": grid_config["lower_limit"],
        "grid_levels": placed_orders,
        "total_buy_orders": buy_orders_placed,
        "total_sell_orders": sell_orders_placed,
        "last_rebalance": datetime.utcnow().isoformat(),
        "total_profit_quote": 0.0,
        "breakout_count": 0,
        "grid_type": grid_config["grid_type"],
        "grid_mode": grid_mode,
    }

    logger.info(f"🎉 Grid initialized: {buy_orders_placed} buy orders, {sell_orders_placed} sell orders")

    return grid_state


async def cancel_grid_orders(
    bot: Bot,
    position: Position,
    exchange_client: ExchangeClient,
    db: AsyncSession,
    reason: str = "grid_rebalance",
) -> int:
    """
    Cancel all pending grid orders and release reserved capital.

    Used during:
    - Grid rebalancing (breakout)
    - Bot stop/delete
    - Grid rotation

    Args:
        bot: Bot instance
        position: Position with pending orders
        exchange_client: Exchange client
        db: Database session
        reason: Why orders are being cancelled

    Returns:
        Number of orders cancelled
    """
    logger.info(f"🛑 Cancelling grid orders for bot {bot.id}, reason: {reason}")

    # Get all pending orders for this position
    result = await db.execute(
        select(PendingOrder).where(
            PendingOrder.position_id == position.id,
            PendingOrder.status == "pending"
        )
    )
    pending_orders = result.scalars().all()

    cancelled_count = 0

    for order in pending_orders:
        try:
            # Cancel on exchange
            logger.debug(f"   Cancelling order {order.order_id[:8]}...")
            await exchange_client.cancel_order(order.order_id)

            # Update status and release reserved capital
            order.status = "cancelled"
            order.canceled_at = datetime.utcnow()
            order.reserved_amount_quote = 0.0
            order.reserved_amount_base = 0.0

            cancelled_count += 1

        except Exception as e:
            logger.error(f"Failed to cancel order {order.order_id}: {e}")
            # Mark as cancelled in DB anyway to release capital
            order.status = "cancelled"
            order.reserved_amount_quote = 0.0
            order.reserved_amount_base = 0.0

    await db.commit()

    logger.info(f"✅ Cancelled {cancelled_count}/{len(pending_orders)} orders")

    return cancelled_count


async def handle_grid_order_fill(
    pending_order: PendingOrder,
    bot: Bot,
    position: Position,
    exchange_client: ExchangeClient,
    db: AsyncSession,
) -> Optional[str]:
    """
    Handle a grid order fill and potentially place opposite order.

    For neutral grids:
    - Buy order fills → place sell order at next level up
    - Sell order fills → place buy order at next level down

    For long grids:
    - Buy order fills → accumulate position
    - No automatic sell (wait for take profit)

    Args:
        pending_order: The order that just filled
        bot: Bot instance
        position: Position
        exchange_client: Exchange client
        db: Database session

    Returns:
        Order ID of new opposite order (if placed)
    """
    grid_state = bot.bot_config.get("grid_state", {})
    grid_mode = grid_state.get("grid_mode", "neutral")
    filled_price = pending_order.filled_price
    filled_side = pending_order.side

    logger.info(f"📊 Grid order filled: {filled_side} @ {filled_price:.8f}")

    # Release reserved capital (it's now in the position)
    pending_order.reserved_amount_quote = 0.0
    pending_order.reserved_amount_base = 0.0

    if grid_mode == "neutral":
        # For neutral grids, place opposite order
        if filled_side == "BUY":
            # Buy filled → place sell order above
            # Find next sell level from grid_state
            levels = grid_state.get("grid_levels", [])
            sell_levels = [l for l in levels if l["order_type"] == "sell" and l["price"] > filled_price and l["status"] == "pending"]

            if sell_levels:
                # Place sell at next available level
                target_level = min(sell_levels, key=lambda x: x["price"])
                sell_price = target_level["price"]
                sell_size = pending_order.filled_base_amount  # Sell what we just bought

                try:
                    logger.info(f"   Placing corresponding sell order at {sell_price:.8f}")

                    order_response = await exchange_client.create_limit_order(
                        product_id=bot.product_id,
                        side="SELL",
                        limit_price=sell_price,
                        size=str(sell_size),
                        time_in_force="gtc",
                    )

                    order_id = order_response.get("order_id") or order_response.get("success_response", {}).get("order_id")

                    if order_id:
                        # Create new pending order
                        new_sell_order = PendingOrder(
                            position_id=position.id,
                            bot_id=bot.id,
                            order_id=order_id,
                            product_id=bot.product_id,
                            side="SELL",
                            order_type="LIMIT",
                            limit_price=sell_price,
                            quote_amount=sell_size * sell_price,
                            base_amount=sell_size,
                            trade_type="grid_sell_response",
                            status="pending",
                            reserved_amount_quote=0.0,
                            reserved_amount_base=sell_size,
                            time_in_force="gtc",
                            is_manual=False,
                        )

                        db.add(new_sell_order)
                        await db.commit()

                        logger.info(f"   ✅ Sell order placed at {sell_price:.8f}")
                        return order_id

                except Exception as e:
                    logger.error(f"Failed to place sell response order: {e}")

        elif filled_side == "SELL":
            # Sell filled → place buy order below
            levels = grid_state.get("grid_levels", [])
            buy_levels = [l for l in levels if l["order_type"] == "buy" and l["price"] < filled_price and l["status"] == "pending"]

            if buy_levels:
                target_level = max(buy_levels, key=lambda x: x["price"])
                buy_price = target_level["price"]
                buy_size = pending_order.filled_base_amount

                try:
                    logger.info(f"   Placing corresponding buy order at {buy_price:.8f}")

                    order_response = await exchange_client.create_limit_order(
                        product_id=bot.product_id,
                        side="BUY",
                        limit_price=buy_price,
                        size=str(buy_size),
                        time_in_force="gtc",
                    )

                    order_id = order_response.get("order_id") or order_response.get("success_response", {}).get("order_id")

                    if order_id:
                        new_buy_order = PendingOrder(
                            position_id=position.id,
                            bot_id=bot.id,
                            order_id=order_id,
                            product_id=bot.product_id,
                            side="BUY",
                            order_type="LIMIT",
                            limit_price=buy_price,
                            quote_amount=buy_size * buy_price,
                            base_amount=buy_size,
                            trade_type="grid_buy_response",
                            status="pending",
                            reserved_amount_quote=buy_size * buy_price,
                            reserved_amount_base=0.0,
                            time_in_force="gtc",
                            is_manual=False,
                        )

                        db.add(new_buy_order)
                        await db.commit()

                        logger.info(f"   ✅ Buy order placed at {buy_price:.8f}")
                        return order_id

                except Exception as e:
                    logger.error(f"Failed to place buy response order: {e}")

    elif grid_mode == "long":
        # Long mode: just accumulate, no opposite orders
        logger.info("   Long mode: accumulating position, no opposite order")

    return None


async def rebalance_grid_on_breakout(
    bot: Bot,
    position: Position,
    exchange_client: ExchangeClient,
    db: AsyncSession,
    breakout_direction: str,
    current_price: float,
    new_levels: List[float],
    new_upper: float,
    new_lower: float,
) -> Dict[str, Any]:
    """
    Rebalance grid after price breakout.

    This function:
    1. Cancels all unfilled orders in old range
    2. Updates grid range to new bounds
    3. Places new orders in new range
    4. Updates grid_state with breakout info

    Args:
        bot: Bot instance
        position: Position with grid state
        exchange_client: Exchange client
        db: Database session
        breakout_direction: "upward" or "downward"
        current_price: Current market price
        new_levels: New grid price levels
        new_upper: New upper range limit
        new_lower: New lower range limit

    Returns:
        Updated grid_state dict
    """
    logger.warning(f"🔄 REBALANCING GRID: {breakout_direction} breakout detected")
    logger.info(f"   Old range: {bot.bot_config['grid_state']['current_range_lower']:.8f} - {bot.bot_config['grid_state']['current_range_upper']:.8f}")
    logger.info(f"   New range: {new_lower:.8f} - {new_upper:.8f}")
    logger.info(f"   Current price: {current_price:.8f}")

    # Step 1: Cancel all unfilled orders in old range
    cancelled_count = await cancel_grid_orders(
        bot=bot,
        position=position,
        exchange_client=exchange_client,
        db=db,
        reason=f"{breakout_direction}_breakout"
    )

    logger.info(f"   Cancelled {cancelled_count} old orders")

    # Step 2: Calculate new grid configuration
    grid_mode = bot.bot_config.get("grid_mode", "neutral")
    grid_type = bot.bot_config.get("grid_type", "arithmetic")

    # Keep same investment amount
    total_investment = bot.bot_config.get("total_investment_quote", 0)

    # Build new grid config
    new_grid_config = {
        "grid_mode": grid_mode,
        "grid_type": grid_type,
        "upper_limit": new_upper,
        "lower_limit": new_lower,
        "levels": new_levels,
    }

    # Step 3: Place new grid orders in new range
    logger.info(f"   Placing {len(new_levels)} new grid levels...")

    new_grid_state = await initialize_grid(
        bot=bot,
        position=position,
        exchange_client=exchange_client,
        db=db,
        grid_config=new_grid_config,
        current_price=current_price,
    )

    # Step 4: Update grid state with rebalance info
    old_grid_state = bot.bot_config.get("grid_state", {})
    new_grid_state["breakout_count"] = old_grid_state.get("breakout_count", 0) + 1
    new_grid_state["last_breakout_direction"] = breakout_direction
    new_grid_state["last_breakout_time"] = datetime.utcnow().isoformat()
    new_grid_state["previous_range_upper"] = old_grid_state.get("current_range_upper")
    new_grid_state["previous_range_lower"] = old_grid_state.get("current_range_lower")

    # Update bot config with new grid state
    bot.bot_config["grid_state"] = new_grid_state

    # Commit bot config update
    await db.commit()

    logger.info(f"✅ Grid rebalanced successfully! Breakout count: {new_grid_state['breakout_count']}")

    return new_grid_state


def calculate_new_range_after_breakout(
    old_upper: float,
    old_lower: float,
    current_price: float,
    breakout_direction: str,
    range_expansion_factor: float = 1.2,
) -> Tuple[float, float]:
    """
    Calculate new grid range after a breakout.

    Strategy:
    - Upward breakout: Shift range upward, maintain width
    - Downward breakout: Shift range downward, maintain width
    - Optionally expand range by factor to reduce future breakouts

    Args:
        old_upper: Previous upper limit
        old_lower: Previous lower limit
        current_price: Current market price
        breakout_direction: "upward" or "downward"
        range_expansion_factor: Multiplier for range width (default 1.2 = 20% wider)

    Returns:
        Tuple of (new_upper, new_lower)

    Example:
        Old range: 45-55 (width=10)
        Current price: 58 (upward breakout)
        Expansion: 1.2
        New width: 10 * 1.2 = 12
        New range: Center around 58 ± 6 = 52-64
    """
    old_width = old_upper - old_lower
    new_width = old_width * range_expansion_factor

    if breakout_direction == "upward":
        # Shift range upward, centered on current price
        new_upper = current_price + (new_width / 2)
        new_lower = current_price - (new_width / 2)

    elif breakout_direction == "downward":
        # Shift range downward, centered on current price
        new_upper = current_price + (new_width / 2)
        new_lower = current_price - (new_width / 2)

    else:
        raise ValueError(f"Invalid breakout_direction: {breakout_direction}")

    # Ensure lower bound is positive
    new_lower = max(new_lower, current_price * 0.3)

    logger.debug(f"Range calculation: {old_lower:.8f}-{old_upper:.8f} → {new_lower:.8f}-{new_upper:.8f}")

    return (new_upper, new_lower)


async def detect_and_handle_breakout(
    bot: Bot,
    position: Position,
    exchange_client: ExchangeClient,
    db: AsyncSession,
    current_price: float,
) -> bool:
    """
    Check for breakout and rebalance grid if needed.

    This should be called periodically during bot execution to monitor for breakouts.

    Args:
        bot: Bot instance with grid_state
        position: Position tracking the grid
        exchange_client: Exchange client
        db: Database session
        current_price: Current market price

    Returns:
        True if breakout detected and handled, False otherwise
    """
    if not bot.bot_config.get("enable_dynamic_adjustment", True):
        return False

    grid_state = bot.bot_config.get("grid_state", {})
    if not grid_state:
        # Grid not initialized yet
        return False

    current_upper = grid_state.get("current_range_upper")
    current_lower = grid_state.get("current_range_lower")

    if not current_upper or not current_lower:
        return False

    # Check breakout threshold
    threshold_pct = bot.bot_config.get("breakout_threshold_percent", 5.0)
    threshold = threshold_pct / 100

    breakout_direction = None

    if current_price > current_upper * (1 + threshold):
        breakout_direction = "upward"
    elif current_price < current_lower * (1 - threshold):
        breakout_direction = "downward"

    if not breakout_direction:
        return False  # No breakout

    # Breakout detected - rebalance grid
    logger.warning(f"⚠️  BREAKOUT DETECTED: {breakout_direction}")

    # Calculate new range
    new_upper, new_lower = calculate_new_range_after_breakout(
        old_upper=current_upper,
        old_lower=current_lower,
        current_price=current_price,
        breakout_direction=breakout_direction,
        range_expansion_factor=1.2,  # 20% wider to reduce future breakouts
    )

    # Recalculate grid levels with same spacing type
    grid_type = bot.bot_config.get("grid_type", "arithmetic")
    num_levels = bot.bot_config.get("num_grid_levels", 20)

    if grid_type == "arithmetic":
        from app.strategies.grid_trading import calculate_arithmetic_levels
        new_levels = calculate_arithmetic_levels(new_lower, new_upper, num_levels)
    else:
        from app.strategies.grid_trading import calculate_geometric_levels
        new_levels = calculate_geometric_levels(new_lower, new_upper, num_levels)

    # Rebalance the grid
    await rebalance_grid_on_breakout(
        bot=bot,
        position=position,
        exchange_client=exchange_client,
        db=db,
        breakout_direction=breakout_direction,
        current_price=current_price,
        new_levels=new_levels,
        new_upper=new_upper,
        new_lower=new_lower,
    )

    return True


__all__ = [
    "initialize_grid",
    "cancel_grid_orders",
    "handle_grid_order_fill",
    "rebalance_grid_on_breakout",
    "calculate_new_range_after_breakout",
    "detect_and_handle_breakout",
]
