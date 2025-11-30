"""
Trailing Stop Loss and Trailing Take Profit Management

Handles the TSL/TTP logic for bull flag positions:
- TSL: Set at pullback low, trails up as price rises, disabled when TTP activates
- TTP: Activates at 2x risk target, trails from peak price, triggers sell when price drops by risk distance
"""

import logging
from typing import Any, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def update_trailing_stop_loss(
    position: Any,
    current_price: float,
    db: AsyncSession
) -> Tuple[bool, str]:
    """
    Update trailing stop loss for a bull flag position.

    TSL Logic:
    - Set at entry (pullback low)
    - Trails up as price rises (maintains same risk distance)
    - Never trails down
    - DISABLED when TTP activates
    - Triggers sell if price <= TSL

    Args:
        position: Position model instance
        current_price: Current market price
        db: Database session

    Returns:
        Tuple of (should_sell: bool, reason: str)
    """
    # Skip if TTP is active (TTP handles exit at that point)
    if position.trailing_tp_active:
        return (False, "TSL disabled - TTP active")

    # Skip if TSL not configured
    if not position.trailing_stop_loss_active:
        return (False, "TSL not active for this position")

    entry_stop_loss = position.entry_stop_loss
    if not entry_stop_loss:
        return (False, "No entry stop loss defined")

    # Get entry price
    entry_price = position.average_buy_price
    if not entry_price or entry_price <= 0:
        return (False, "Invalid entry price")

    # Calculate risk distance (distance from entry to stop loss)
    risk_distance = entry_price - entry_stop_loss
    if risk_distance <= 0:
        return (False, "Invalid risk distance")

    # Get current TSL price
    current_tsl = position.trailing_stop_loss_price or entry_stop_loss

    # Check if price hit stop loss
    if current_price <= current_tsl:
        position.exit_reason = "trailing_stop_loss"
        await db.commit()
        return (
            True,
            f"Trailing stop loss triggered: ${current_price:.4f} <= TSL ${current_tsl:.4f}"
        )

    # Trail up if price has risen (maintain risk distance below current price)
    new_tsl = current_price - risk_distance

    # Only trail up, never down
    if new_tsl > current_tsl:
        position.trailing_stop_loss_price = new_tsl
        position.highest_price_since_entry = max(
            position.highest_price_since_entry or entry_price,
            current_price
        )
        await db.commit()
        logger.debug(
            f"TSL trailed up for position {position.id}: "
            f"${current_tsl:.4f} -> ${new_tsl:.4f} (price: ${current_price:.4f})"
        )

    return (False, f"TSL at ${current_tsl:.4f}, current price ${current_price:.4f}")


async def update_trailing_take_profit(
    position: Any,
    current_price: float,
    db: AsyncSession
) -> Tuple[bool, str]:
    """
    Update trailing take profit for a bull flag position.

    TTP Logic:
    - Target set at entry (2x risk distance above entry)
    - Activates when price >= target
    - On activation: DISABLE TSL
    - Trails from peak price
    - Triggers sell if price drops by risk distance from peak

    Args:
        position: Position model instance
        current_price: Current market price
        db: Database session

    Returns:
        Tuple of (should_sell: bool, reason: str)
    """
    # Get entry parameters
    entry_price = position.average_buy_price
    entry_stop_loss = position.entry_stop_loss
    take_profit_target = position.entry_take_profit_target

    if not all([entry_price, entry_stop_loss, take_profit_target]):
        return (False, "Missing entry parameters for TTP")

    # Calculate risk distance
    risk_distance = entry_price - entry_stop_loss
    if risk_distance <= 0:
        return (False, "Invalid risk distance")

    # Check if TTP should activate
    if not position.trailing_tp_active:
        if current_price >= take_profit_target:
            # Activate TTP
            position.trailing_tp_active = True
            position.trailing_stop_loss_active = False  # Disable TSL
            position.highest_price_since_tp = current_price
            await db.commit()

            logger.info(
                f"TTP activated for position {position.id}: "
                f"price ${current_price:.4f} >= target ${take_profit_target:.4f}. "
                f"TSL disabled."
            )
            return (False, f"TTP activated at ${current_price:.4f}")

        return (False, f"Price ${current_price:.4f} below TTP target ${take_profit_target:.4f}")

    # TTP is active - track peak and check for exit
    highest_since_tp = position.highest_price_since_tp or take_profit_target

    # Update peak if price is higher
    if current_price > highest_since_tp:
        position.highest_price_since_tp = current_price
        highest_since_tp = current_price
        await db.commit()
        logger.debug(
            f"TTP new peak for position {position.id}: ${current_price:.4f}"
        )

    # Calculate TTP trigger price (risk distance below peak)
    ttp_trigger = highest_since_tp - risk_distance

    # Check if price dropped to trigger level
    if current_price <= ttp_trigger:
        position.exit_reason = "trailing_take_profit"
        await db.commit()

        profit_pct = ((current_price - entry_price) / entry_price) * 100
        return (
            True,
            f"Trailing take profit triggered: ${current_price:.4f} <= trigger ${ttp_trigger:.4f} "
            f"(peak ${highest_since_tp:.4f}, profit {profit_pct:.2f}%)"
        )

    return (
        False,
        f"TTP tracking: peak ${highest_since_tp:.4f}, trigger ${ttp_trigger:.4f}, "
        f"current ${current_price:.4f}"
    )


async def check_bull_flag_exit_conditions(
    position: Any,
    current_price: float,
    db: AsyncSession
) -> Tuple[bool, str]:
    """
    Check all exit conditions for a bull flag position.

    Checks in order:
    1. Trailing Take Profit (if active, TTP handles exit)
    2. Trailing Stop Loss (if TTP not active)

    Args:
        position: Position model instance
        current_price: Current market price
        db: Database session

    Returns:
        Tuple of (should_sell: bool, reason: str)
    """
    # First check TTP (takes priority)
    should_sell, reason = await update_trailing_take_profit(position, current_price, db)
    if should_sell:
        return (True, reason)

    # Then check TSL (only if TTP not active)
    should_sell, reason = await update_trailing_stop_loss(position, current_price, db)
    if should_sell:
        return (True, reason)

    return (False, reason)


def setup_bull_flag_position_stops(
    position: Any,
    pattern_data: dict
) -> None:
    """
    Set up initial stop loss and take profit levels for a new bull flag position.

    Called after position entry to initialize the TSL/TTP parameters.

    Args:
        position: Position model instance
        pattern_data: Pattern data dict from bull flag detection
    """
    # Set entry-time stop loss (pullback low)
    position.entry_stop_loss = pattern_data.get("stop_loss")

    # Set take profit target
    position.entry_take_profit_target = pattern_data.get("take_profit_target")

    # Initialize trailing stop loss at entry stop loss
    position.trailing_stop_loss_price = position.entry_stop_loss
    position.trailing_stop_loss_active = True

    # TTP starts inactive
    position.trailing_tp_active = False
    position.highest_price_since_tp = None

    # Track highest price since entry
    position.highest_price_since_entry = position.average_buy_price

    # Store pattern data
    import json
    position.pattern_data = json.dumps(pattern_data)

    logger.info(
        f"Bull flag stops initialized for position {position.id}: "
        f"entry=${position.average_buy_price:.4f}, "
        f"TSL=${position.entry_stop_loss:.4f}, "
        f"TTP target=${position.entry_take_profit_target:.4f}"
    )
