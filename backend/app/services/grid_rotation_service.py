"""
Time-Based Grid Rotation Service

Periodically locks in profits from winning positions and refreshes the grid.
Keeps losing positions to wait for recovery.
"""

import logging
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exchange_clients.base import ExchangeClient
from app.models import Bot, Position, Trade

logger = logging.getLogger(__name__)


async def evaluate_grid_rotation(
    bot: Bot,
    position: Position,
    exchange_client: ExchangeClient,
    db: AsyncSession
) -> bool:
    """
    Evaluate if grid should be rotated based on time and profit conditions.

    Args:
        bot: Bot instance
        position: Current position
        exchange_client: Exchange client
        db: Database session

    Returns:
        True if rotation is needed
    """
    if not bot.strategy_config.get("enable_time_rotation", False):
        return False

    grid_state = bot.strategy_config.get("grid_state", {})

    # Check time condition
    rotation_interval_hours = bot.strategy_config.get("rotation_interval_hours", 48)

    # Get last rotation time (or initialization time if never rotated)
    last_rotation = grid_state.get("last_rotation")
    if not last_rotation:
        # Use initialization time
        initialized_at = grid_state.get("initialized_at")
        if not initialized_at:
            logger.warning(f"Grid not initialized for bot {bot.id}, skipping rotation check")
            return False
        last_rotation = initialized_at

    last_rotation_time = datetime.fromisoformat(last_rotation)
    hours_elapsed = (datetime.utcnow() - last_rotation_time).total_seconds() / 3600

    if hours_elapsed < rotation_interval_hours:
        # Not yet time to rotate
        return False

    logger.info(f"Grid rotation interval reached for bot {bot.id} ({hours_elapsed:.1f} hours elapsed)")

    # Check profit condition
    min_profit_threshold = bot.strategy_config.get("min_profit_to_rotate", 0.0)

    # Calculate total unrealized profit
    # For grid bots, we need to look at the grid_state profit or calculate from trades
    total_profit = grid_state.get("total_profit_quote", 0.0)

    if total_profit < min_profit_threshold:
        logger.info(f"Insufficient profit for rotation: {total_profit:.8f} < {min_profit_threshold:.8f}")
        return False

    logger.info(f"✅ Grid rotation conditions met for bot {bot.id} (profit: {total_profit:.8f})")
    return True


async def execute_grid_rotation(
    bot: Bot,
    position: Position,
    exchange_client: ExchangeClient,
    db: AsyncSession,
    current_price: float
) -> Dict[str, Any]:
    """
    Execute grid rotation: lock profits from winning positions, keep losers.

    Args:
        bot: Bot instance
        position: Current position
        exchange_client: Exchange client
        db: Database session
        current_price: Current market price

    Returns:
        Dictionary with rotation statistics
    """
    logger.info(f"🔄 Executing grid rotation for bot {bot.id}...")

    grid_state = bot.strategy_config.get("grid_state", {})
    profit_lock_percent = bot.strategy_config.get("profit_lock_percent", 70.0)

    # Get all trades for this position to calculate per-level profit
    trades_query = select(Trade).where(Trade.position_id == position.id)
    trades_result = await db.execute(trades_query)
    _trades = trades_result.scalars().all()  # noqa: F841

    # Group trades by grid level to calculate profit
    # For simplicity, we'll close all filled grid levels that are currently in profit

    # Get grid levels from state
    grid_levels = grid_state.get("grid_levels", [])

    profitable_levels = []
    losing_levels = []

    for level_data in grid_levels:
        if level_data.get("status") != "filled":
            continue

        # Calculate profit for this level
        # Buy price = level price
        # Current value = current_price * base_amount
        level_price = level_data.get("price", 0)
        base_amount = level_data.get("filled_base_amount", 0)

        if base_amount == 0:
            continue

        buy_cost = level_price * base_amount
        current_value = current_price * base_amount
        profit = current_value - buy_cost
        profit_percent = (profit / buy_cost) * 100 if buy_cost > 0 else 0

        level_info = {
            "level_index": level_data.get("level_index"),
            "price": level_price,
            "base_amount": base_amount,
            "profit": profit,
            "profit_percent": profit_percent,
        }

        if profit > 0:
            profitable_levels.append(level_info)
        else:
            losing_levels.append(level_info)

    # Sort profitable levels by profit (highest first)
    profitable_levels.sort(key=lambda x: x["profit"], reverse=True)

    # Determine how many positions to close
    lock_count = int(len(profitable_levels) * profit_lock_percent / 100)
    if lock_count == 0 and len(profitable_levels) > 0:
        lock_count = 1  # Close at least one if any are profitable

    levels_to_close = profitable_levels[:lock_count]

    logger.info(f"Profitable levels: {len(profitable_levels)}, Losing levels: {len(losing_levels)}")
    logger.info(f"Closing top {lock_count} profitable levels ({profit_lock_percent}%)")

    # Close profitable levels (sell the base currency)
    total_locked_profit = 0.0
    closed_count = 0

    for level_info in levels_to_close:
        try:
            # Place market sell order for this level's base amount
            base_amount = level_info["base_amount"]

            logger.info(f"Closing level {level_info['level_index']}: selling {base_amount:.8f} @ current price")

            # Create market sell order
            sell_result = await exchange_client.create_market_order(
                product_id=bot.product_id,
                side="SELL",
                size=str(base_amount)
            )

            if sell_result.get("success") or sell_result.get("success_response", {}).get("order_id"):
                total_locked_profit += level_info["profit"]
                closed_count += 1

                # Mark level as rotated in grid state
                for level_data in grid_levels:
                    if level_data.get("level_index") == level_info["level_index"]:
                        level_data["status"] = "rotated"
                        level_data["rotated_at"] = datetime.utcnow().isoformat()
                        level_data["locked_profit"] = level_info["profit"]
                        break

                logger.info(f"✅ Locked profit: {level_info['profit']:.8f} from level {level_info['level_index']}")

        except Exception as e:
            logger.error(f"Error closing level {level_info['level_index']}: {e}")

    # Update grid state
    grid_state["last_rotation"] = datetime.utcnow().isoformat()
    grid_state["total_rotations"] = grid_state.get("total_rotations", 0) + 1
    grid_state["grid_levels"] = grid_levels

    # Track rotation history
    if "rotation_history" not in grid_state:
        grid_state["rotation_history"] = []

    grid_state["rotation_history"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "levels_closed": closed_count,
        "total_locked_profit": total_locked_profit,
        "profitable_levels": len(profitable_levels),
        "losing_levels_kept": len(losing_levels),
    })

    # Keep only last 10 rotation records
    grid_state["rotation_history"] = grid_state["rotation_history"][-10:]

    bot.strategy_config["grid_state"] = grid_state

    await db.commit()

    logger.info(f"🔄 Grid rotation complete: closed {closed_count} levels, locked {total_locked_profit:.8f} profit")

    return {
        "rotated": True,
        "levels_closed": closed_count,
        "total_locked_profit": total_locked_profit,
        "profitable_levels_total": len(profitable_levels),
        "losing_levels_kept": len(losing_levels),
    }


async def check_and_run_rotation(
    bot: Bot,
    position: Position,
    exchange_client: ExchangeClient,
    db: AsyncSession,
    current_price: float
) -> bool:
    """
    Check if rotation is due and execute if needed.

    Called periodically from bot monitoring loop.

    Args:
        bot: Bot instance
        position: Current position
        exchange_client: Exchange client
        db: Database session
        current_price: Current market price

    Returns:
        True if rotation was executed
    """
    # Check if rotation is needed
    should_rotate = await evaluate_grid_rotation(bot, position, exchange_client, db)

    if not should_rotate:
        return False

    # Execute rotation
    result = await execute_grid_rotation(bot, position, exchange_client, db, current_price)

    return result.get("rotated", False)
