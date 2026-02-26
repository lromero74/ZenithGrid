"""
Order logging utilities for trading engine

Handles logging of:
- Order history (complete audit trail)
- AI bot decision logs
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIBotLog, Bot, OrderHistory, Position

logger = logging.getLogger(__name__)


def _bot_uses_ai_indicators(bot: Bot) -> bool:
    """Check if bot uses AI indicators in its conditions."""
    # Legacy support for ai_autonomous strategy type
    if bot.strategy_type == "ai_autonomous":
        return True

    # Check for AI indicators in strategy_config conditions
    config = bot.strategy_config
    if not config:
        return False

    # Check all condition arrays for ai_buy or ai_sell
    condition_arrays = [
        config.get("base_order_conditions", []),
        config.get("safety_order_conditions", []),
        config.get("take_profit_conditions", []),
    ]

    for conditions in condition_arrays:
        if isinstance(conditions, list):
            for cond in conditions:
                indicator = cond.get("type") or cond.get("indicator")
                if indicator in ("ai_buy", "ai_sell"):
                    return True
    return False


async def save_ai_log(
    db: AsyncSession,
    bot: Bot,
    product_id: str,
    signal_data: Dict[str, Any],
    decision: str,
    current_price: float,
    position: Optional[Position],
):
    """Save AI bot reasoning log if this bot uses AI indicators"""
    # Only save logs for bots using AI indicators
    if not _bot_uses_ai_indicators(bot):
        return

    # Extract AI thinking/reasoning from signal_data
    thinking = signal_data.get("reasoning", "No reasoning provided")
    confidence = signal_data.get("confidence", None)

    # Determine position status
    position_status = "none"
    if position:
        position_status = position.status

    # Save log (don't commit - let caller handle transaction)
    ai_log = AIBotLog(
        bot_id=bot.id,
        position_id=position.id if position else None,  # Link to position for historical review
        thinking=thinking,
        decision=decision,
        confidence=confidence,
        current_price=current_price,
        position_status=position_status,
        product_id=product_id,  # Track which pair this analysis is for
        context=signal_data,  # Store full signal data for reference
        timestamp=datetime.utcnow(),
    )

    db.add(ai_log)
    # Don't commit here - let the main process_signal flow commit everything together


@dataclass
class OrderLogEntry:
    """Data for a single order history log entry.

    Groups the order-specific fields (side, type, amounts, status)
    into a single object, reducing the parameter count of
    log_order_to_history from 12 to 5.
    """
    product_id: str
    side: str
    order_type: str
    trade_type: str
    quote_amount: float
    price: float
    status: str
    order_id: Optional[str] = None
    base_amount: Optional[float] = None
    error_message: Optional[str] = None


async def log_order_to_history(
    db: AsyncSession,
    bot: Bot,
    position: Optional[Position],
    entry: OrderLogEntry,
):
    """
    Log order attempt to order_history table for audit trail.
    Complete order history for audit trail.

    Args:
        db: Database session
        bot: Bot instance
        position: Position (None for failed base orders)
        entry: OrderLogEntry with order details (product_id, side, order_type,
               trade_type, quote_amount, price, status, order_id, base_amount,
               error_message)
    """
    try:
        order_history = OrderHistory(
            timestamp=datetime.utcnow(),
            bot_id=bot.id,
            position_id=position.id if position else None,
            product_id=entry.product_id,
            side=entry.side,
            order_type=entry.order_type,
            trade_type=entry.trade_type,
            quote_amount=entry.quote_amount,
            base_amount=entry.base_amount,
            price=entry.price,
            status=entry.status,
            order_id=entry.order_id,
            error_message=entry.error_message,
        )
        db.add(order_history)
        # Note: Don't commit here - let caller handle commits
    except Exception as e:
        logger.error(f"Failed to log order to history: {e}")
        # Don't fail the entire operation if logging fails
