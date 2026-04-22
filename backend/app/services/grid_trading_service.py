"""
Grid Trading Service

Handles grid bot lifecycle:
- Grid initialization (place all limit orders)
- Order fill detection and response
- Grid rebalancing on breakouts
- Capital reservation management
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exchange_clients.base import ExchangeClient
from app.models import Bot, PendingOrder, Position
from app.order_validation import validate_order_size

logger = logging.getLogger(__name__)


async def _place_grid_limit_order(
    exchange_client: ExchangeClient,
    db: AsyncSession,
    bot: Bot,
    position: Position,
    side: str,
    limit_price: float,
    base_amount: float,
    quote_amount: float,
    trade_type: str,
) -> Optional[str]:
    """Place a single grid limit order and persist its PendingOrder row.

    Reservation rules: BUY reserves quote currency, SELL reserves base
    currency. Returns the exchange order_id on success, None on failure.

    Does not commit — caller is expected to commit at a batch boundary.
    """
    product_id = bot.product_id
    order_response = await exchange_client.create_limit_order(
        product_id=product_id,
        side=side,
        limit_price=limit_price,
        size=str(base_amount),
        time_in_force="gtc",
    )

    order_id = (
        order_response.get("order_id")
        or order_response.get("success_response", {}).get("order_id")
    )
    if not order_id:
        logger.error(f"No order_id in response: {order_response}")
        return None

    reserved_quote = quote_amount if side == "BUY" else 0.0
    reserved_base = 0.0 if side == "BUY" else base_amount

    pending_order = PendingOrder(
        position_id=position.id,
        bot_id=bot.id,
        order_id=order_id,
        product_id=product_id,
        side=side,
        order_type="LIMIT",
        limit_price=limit_price,
        quote_amount=quote_amount,
        base_amount=base_amount,
        trade_type=trade_type,
        status="pending",
        reserved_amount_quote=reserved_quote,
        reserved_amount_base=reserved_base,
        time_in_force="gtc",
        is_manual=False,
    )
    db.add(pending_order)
    return order_id


def _compute_grid_order_size(
    levels: List[float], current_price: float, total_investment: float, grid_mode: str,
) -> Tuple[float, int]:
    """Determine per-level quote size and buy-order count for the given mode."""
    if grid_mode == "neutral":
        buy_levels = [lvl for lvl in levels if lvl < current_price]
        num_buy_orders = len(buy_levels)
        if num_buy_orders == 0:
            raise ValueError(f"No buy levels below current price {current_price:.8f}")
        return total_investment / num_buy_orders, num_buy_orders
    if grid_mode == "long":
        num_buy_orders = len(levels)
        return total_investment / num_buy_orders, num_buy_orders
    raise ValueError(f"Unsupported grid_mode: {grid_mode}")


async def _place_grid_buy_orders(
    bot: Bot, position: Position, exchange_client: ExchangeClient, db: AsyncSession,
    levels: List[float], current_price: float, order_size_quote: float, grid_mode: str,
) -> Tuple[int, List[Dict[str, Any]]]:
    """Place the buy-side orders for a grid. Returns (count, placed_summaries)."""
    product_id = bot.product_id
    placed: List[Dict[str, Any]] = []
    buy_count = 0

    for i, level_price in enumerate(levels):
        if grid_mode == "neutral" and level_price >= current_price:
            continue
        base_amount = order_size_quote / level_price

        try:
            is_valid, error_msg = await validate_order_size(
                exchange_client, product_id,
                quote_amount=order_size_quote, base_amount=base_amount,
            )
            if not is_valid:
                logger.warning(f"   ⚠️  Skipping grid level {i} at {level_price:.8f}: {error_msg}")
                continue

            logger.debug(f"   Placing buy order: price={level_price:.8f}, size={base_amount:.8f}")
            order_id = await _place_grid_limit_order(
                exchange_client, db, bot, position,
                side="BUY", limit_price=level_price,
                base_amount=base_amount, quote_amount=order_size_quote,
                trade_type=f"grid_buy_{i}",
            )
            if not order_id:
                continue

            buy_count += 1
            placed.append({
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

    return buy_count, placed


async def _place_grid_sell_orders(
    bot: Bot, position: Position, exchange_client: ExchangeClient, db: AsyncSession,
    levels: List[float], current_price: float, order_size_quote: float,
) -> Tuple[int, List[Dict[str, Any]]]:
    """Place the sell-side orders for a neutral grid above current_price."""
    product_id = bot.product_id
    placed: List[Dict[str, Any]] = []
    sell_count = 0

    sell_levels = [lvl for lvl in levels if lvl > current_price]
    for i, level_price in enumerate(sell_levels):
        base_amount = order_size_quote / level_price

        try:
            is_valid, error_msg = await validate_order_size(
                exchange_client, product_id,
                quote_amount=order_size_quote, base_amount=base_amount,
            )
            if not is_valid:
                logger.warning(f"   ⚠️  Skipping sell level at {level_price:.8f}: {error_msg}")
                continue

            logger.debug(f"   Placing sell order: price={level_price:.8f}, size={base_amount:.8f}")
            order_id = await _place_grid_limit_order(
                exchange_client, db, bot, position,
                side="SELL", limit_price=level_price,
                base_amount=base_amount, quote_amount=order_size_quote,
                trade_type=f"grid_sell_{i}",
            )
            if not order_id:
                continue

            sell_count += 1
            placed.append({
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

    return sell_count, placed


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

    order_size_quote, num_buy_orders = _compute_grid_order_size(
        levels, current_price, total_investment, grid_mode,
    )
    logger.info(f"   {grid_mode.title()} mode: {num_buy_orders} buy orders @ {order_size_quote:.8f} each")

    buy_orders_placed, buy_placed = await _place_grid_buy_orders(
        bot, position, exchange_client, db,
        levels, current_price, order_size_quote, grid_mode,
    )
    sell_orders_placed = 0
    sell_placed: List[Dict[str, Any]] = []
    if grid_mode == "neutral":
        sell_orders_placed, sell_placed = await _place_grid_sell_orders(
            bot, position, exchange_client, db,
            levels, current_price, order_size_quote,
        )
    placed_orders = buy_placed + sell_placed

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

    # Warn if some orders were skipped due to size requirements
    expected_buy_orders = len([level for level in levels if grid_mode == "long" or level < current_price])
    expected_sell_orders = len([level for level in levels if grid_mode == "neutral" and level > current_price])
    skipped_orders = (expected_buy_orders - buy_orders_placed) + (expected_sell_orders - sell_orders_placed)

    if skipped_orders > 0:
        logger.warning(
            f"⚠️  {skipped_orders} grid order(s) were skipped because they were below exchange minimum order size. "
            f"Consider increasing total_investment_quote or reducing num_grid_levels."
        )

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

    # Batch cancel all orders in a single API call instead of one-by-one
    order_ids = [order.order_id for order in pending_orders if order.order_id]
    cancelled_count = 0

    if order_ids:
        try:
            await exchange_client.cancel_orders(order_ids)
            cancelled_count = len(order_ids)
        except Exception as e:
            logger.error(f"Batch cancel failed: {e}, falling back to individual cancels")
            for order in pending_orders:
                try:
                    await exchange_client.cancel_order(order.order_id)
                    cancelled_count += 1
                except Exception as e2:
                    logger.error(f"Failed to cancel order {order.order_id}: {e2}")

    # Update all pending orders in DB regardless of exchange result
    now = datetime.utcnow()
    for order in pending_orders:
        order.status = "cancelled"
        order.canceled_at = now
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
            sell_levels = (
                level for level in levels
                if level["order_type"] == "sell"
                and level["price"] > filled_price
                and level["status"] == "pending"
            )
            target_level = min(sell_levels, key=lambda x: x["price"], default=None)

            if target_level:
                sell_price = target_level["price"]
                sell_size = pending_order.filled_base_amount  # Sell what we just bought

                try:
                    logger.info(f"   Placing corresponding sell order at {sell_price:.8f}")
                    order_id = await _place_grid_limit_order(
                        exchange_client, db, bot, position,
                        side="SELL", limit_price=sell_price,
                        base_amount=sell_size, quote_amount=sell_size * sell_price,
                        trade_type="grid_sell_response",
                    )
                    if order_id:
                        await db.commit()
                        logger.info(f"   ✅ Sell order placed at {sell_price:.8f}")
                        return order_id

                except Exception as e:
                    logger.error(f"Failed to place sell response order: {e}")

        elif filled_side == "SELL":
            # Sell filled → place buy order below
            levels = grid_state.get("grid_levels", [])
            buy_levels = (
                level for level in levels
                if level["order_type"] == "buy"
                and level["price"] < filled_price
                and level["status"] == "pending"
            )
            target_level = max(buy_levels, key=lambda x: x["price"], default=None)

            if target_level:
                buy_price = target_level["price"]
                buy_size = pending_order.filled_base_amount

                try:
                    logger.info(f"   Placing corresponding buy order at {buy_price:.8f}")
                    order_id = await _place_grid_limit_order(
                        exchange_client, db, bot, position,
                        side="BUY", limit_price=buy_price,
                        base_amount=buy_size, quote_amount=buy_size * buy_price,
                        trade_type="grid_buy_response",
                    )
                    if order_id:
                        await db.commit()
                        logger.info(f"   ✅ Buy order placed at {buy_price:.8f}")
                        return order_id

                except Exception as e:
                    logger.error(f"Failed to place buy response order: {e}")

    elif grid_mode == "long":
        # Long mode: just accumulate, no opposite orders
        logger.info("   Long mode: accumulating position, no opposite order")

    return None


@dataclass
class GridRebalanceParams:
    """Parameters for grid rebalancing on breakout."""
    bot: Bot
    position: Position
    exchange_client: ExchangeClient
    db: AsyncSession
    breakout_direction: str
    current_price: float
    new_levels: List[float]
    new_upper: float
    new_lower: float


async def rebalance_grid_on_breakout(params: GridRebalanceParams) -> Dict[str, Any]:
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
    logger.warning(f"🔄 REBALANCING GRID: {params.breakout_direction} breakout detected")
    old_lower = params.bot.bot_config['grid_state']['current_range_lower']
    old_upper = params.bot.bot_config['grid_state']['current_range_upper']
    logger.info(f"   Old range: {old_lower:.8f} - {old_upper:.8f}")
    logger.info(f"   New range: {params.new_lower:.8f} - {params.new_upper:.8f}")
    logger.info(f"   Current price: {params.current_price:.8f}")

    # Step 1: Cancel all unfilled orders in old range
    cancelled_count = await cancel_grid_orders(
        bot=params.bot,
        position=params.position,
        exchange_client=params.exchange_client,
        db=params.db,
        reason=f"{params.breakout_direction}_breakout"
    )

    logger.info(f"   Cancelled {cancelled_count} old orders")

    # Step 2: Calculate new grid configuration
    grid_mode = params.bot.bot_config.get("grid_mode", "neutral")
    grid_type = params.bot.bot_config.get("grid_type", "arithmetic")

    # Build new grid config (investment amount is preserved upstream)
    new_grid_config = {
        "grid_mode": grid_mode,
        "grid_type": grid_type,
        "upper_limit": params.new_upper,
        "lower_limit": params.new_lower,
        "levels": params.new_levels,
    }

    # Step 3: Place new grid orders in new range
    logger.info(f"   Placing {len(params.new_levels)} new grid levels...")

    new_grid_state = await initialize_grid(
        bot=params.bot,
        position=params.position,
        exchange_client=params.exchange_client,
        db=params.db,
        grid_config=new_grid_config,
        current_price=params.current_price,
    )

    # Step 4: Update grid state with rebalance info
    old_grid_state = params.bot.bot_config.get("grid_state", {})
    new_grid_state["breakout_count"] = old_grid_state.get("breakout_count", 0) + 1
    new_grid_state["last_breakout_direction"] = params.breakout_direction
    new_grid_state["last_breakout_time"] = datetime.utcnow().isoformat()
    new_grid_state["previous_range_upper"] = old_grid_state.get("current_range_upper")
    new_grid_state["previous_range_lower"] = old_grid_state.get("current_range_lower")

    # Update bot config with new grid state
    params.bot.bot_config["grid_state"] = new_grid_state

    # Commit bot config update
    await params.db.commit()

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
    await rebalance_grid_on_breakout(GridRebalanceParams(
        bot=bot, position=position, exchange_client=exchange_client,
        db=db, breakout_direction=breakout_direction,
        current_price=current_price, new_levels=new_levels,
        new_upper=new_upper, new_lower=new_lower,
    ))

    return True


async def check_and_run_ai_optimization(
    bot: Bot,
    position: Position,
    exchange_client: ExchangeClient,
    db: AsyncSession,
    signal_data: Dict[str, Any],
) -> bool:
    """
    Check if AI optimization is due and run it if needed.

    Called from bot monitoring loop when signal indicates AI optimization is due.

    Args:
        bot: Bot instance
        position: Current position
        exchange_client: Exchange client
        db: Database session
        signal_data: Signal from analyze_signal (contains ai_optimization_due flag)

    Returns:
        True if AI optimization ran and made adjustments
    """
    if not signal_data.get("ai_optimization_due"):
        return False

    if not bot.strategy_config.get("enable_ai_optimization", False):
        return False

    logger.info(f"🤖 Running AI optimization for grid bot {bot.id}...")

    try:
        from app.services.ai_grid_optimizer import run_ai_grid_optimization

        recommendations = await run_ai_grid_optimization(
            bot=bot,
            position=position,
            exchange_client=exchange_client,
            db=db
        )

        if recommendations:
            logger.info(f"✅ AI optimization applied for bot {bot.id}")
            return True
        else:
            logger.info(f"No AI adjustments made for bot {bot.id}")
            return False

    except Exception as e:
        logger.error(f"Error running AI optimization for bot {bot.id}: {e}", exc_info=True)
        return False


async def check_and_run_rotation(
    bot: Bot,
    position: Position,
    exchange_client: ExchangeClient,
    db: AsyncSession,
    current_price: float
) -> bool:
    """
    Check if time-based rotation is due and execute if needed.

    Wrapper that calls the grid_rotation_service.

    Args:
        bot: Bot instance
        position: Current position
        exchange_client: Exchange client
        db: Database session
        current_price: Current market price

    Returns:
        True if rotation was executed
    """
    try:
        from app.services.grid_rotation_service import check_and_run_rotation as execute_rotation

        result = await execute_rotation(bot, position, exchange_client, db, current_price)

        if result:
            logger.info(f"✅ Time-based rotation executed for bot {bot.id}")

        return result

    except Exception as e:
        logger.error(f"Error running rotation for bot {bot.id}: {e}", exc_info=True)
        return False


__all__ = [
    "initialize_grid",
    "cancel_grid_orders",
    "handle_grid_order_fill",
    "rebalance_grid_on_breakout",
    "calculate_new_range_after_breakout",
    "detect_and_handle_breakout",
    "check_and_run_ai_optimization",
    "check_and_run_rotation",
]
