"""
Perpetual futures order execution for trading engine
Handles opening and closing INTX perpetual futures positions with bracket TP/SL
"""

import logging
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_unified_client import CoinbaseClient
from app.models import Bot, Position, Trade
from app.services.shutdown_manager import shutdown_manager

logger = logging.getLogger(__name__)


async def execute_perps_open(
    db: AsyncSession,
    client: CoinbaseClient,
    bot: Bot,
    product_id: str,
    side: str,
    size_usdc: float,
    current_price: float,
    leverage: int = 1,
    margin_type: str = "CROSS",
    tp_pct: Optional[float] = None,
    sl_pct: Optional[float] = None,
    user_id: Optional[int] = None,
) -> Tuple[Optional[Position], Optional[Trade]]:
    """
    Open a perpetual futures position with optional bracket TP/SL.

    Args:
        db: Database session
        client: CoinbaseClient instance
        bot: Bot that generated the signal
        product_id: Perpetual product (e.g., "BTC-PERP-INTX")
        side: "BUY" (long) or "SELL" (short)
        size_usdc: Notional size in USDC
        current_price: Current market price for size calculation
        leverage: Leverage multiplier (1-10)
        margin_type: "CROSS" or "ISOLATED"
        tp_pct: Take profit percentage from entry (e.g., 5.0 = 5%)
        sl_pct: Stop loss percentage from entry (e.g., 3.0 = 3%)
        user_id: Owner user ID

    Returns:
        Tuple of (Position, Trade) or (None, None) on failure
    """
    if shutdown_manager.is_shutting_down:
        logger.warning(f"Rejecting perps order for {product_id} - shutdown in progress")
        return None, None

    # Calculate base size from USDC amount and current price
    base_size = size_usdc / current_price
    base_size_str = f"{base_size:.8f}"

    # Calculate TP/SL prices
    tp_price_str = None
    sl_price_str = None
    tp_price_val = None
    sl_price_val = None

    if side == "BUY":  # Long
        if tp_pct:
            tp_price_val = current_price * (1 + tp_pct / 100)
            tp_price_str = f"{tp_price_val:.2f}"
        if sl_pct:
            sl_price_val = current_price * (1 - sl_pct / 100)
            sl_price_str = f"{sl_price_val:.2f}"
    else:  # Short
        if tp_pct:
            tp_price_val = current_price * (1 - tp_pct / 100)
            tp_price_str = f"{tp_price_val:.2f}"
        if sl_pct:
            sl_price_val = current_price * (1 + sl_pct / 100)
            sl_price_str = f"{sl_price_val:.2f}"

    # Validate minimum notional (10 USDC for INTX)
    if size_usdc < 10.0:
        logger.warning(
            f"Perps order rejected: notional {size_usdc:.2f} USDC below 10 USDC minimum"
        )
        return None, None

    logger.info(
        f"Opening perps position: {product_id} {side} {base_size_str} "
        f"@ ~{current_price:.2f} ({leverage}x {margin_type}) "
        f"TP={tp_price_str} SL={sl_price_str}"
    )

    try:
        result = await client.create_perps_order(
            product_id=product_id,
            side=side,
            base_size=base_size_str,
            leverage=str(leverage),
            margin_type=margin_type,
            tp_price=tp_price_str,
            sl_price=sl_price_str,
        )

        # Extract order details
        success_response = result.get("success_response", result.get("order", {}))
        order_id = success_response.get("order_id", "")

        if not order_id:
            error_response = result.get("error_response", {})
            error_msg = error_response.get("message", str(result))
            logger.error(f"Perps order failed: {error_msg}")
            return None, None

        direction = "long" if side == "BUY" else "short"

        # Create Position record
        position = Position(
            bot_id=bot.id,
            account_id=bot.account_id,
            user_id=user_id or bot.user_id,
            product_id=product_id,
            status="open",
            direction=direction,
            product_type="future",
            leverage=leverage,
            perps_margin_type=margin_type,
            tp_price=tp_price_val,
            sl_price=sl_price_val,
            entry_price=current_price,
            initial_quote_balance=size_usdc,
            max_quote_allowed=size_usdc,
            strategy_config_snapshot=bot.strategy_config,
        )

        if direction == "long":
            position.total_quote_spent = size_usdc
            position.total_base_acquired = base_size
            position.average_buy_price = current_price
        else:
            position.short_entry_price = current_price
            position.short_average_sell_price = current_price
            position.short_total_sold_quote = size_usdc
            position.short_total_sold_base = base_size

        db.add(position)
        await db.flush()

        # Create Trade record
        trade = Trade(
            position_id=position.id,
            side=side.lower(),
            quote_amount=size_usdc,
            base_amount=base_size,
            price=current_price,
            trade_type="initial",
            order_id=order_id,
        )
        db.add(trade)
        await db.commit()

        logger.info(
            f"Perps position opened: #{position.id} {product_id} {direction} "
            f"{base_size_str} @ {current_price:.2f} ({leverage}x)"
        )

        return position, trade

    except Exception as e:
        logger.error(f"Failed to open perps position {product_id}: {e}", exc_info=True)
        await db.rollback()
        return None, None


async def execute_perps_close(
    db: AsyncSession,
    client: CoinbaseClient,
    position: Position,
    current_price: float,
    reason: str = "manual",
) -> Tuple[bool, float, float]:
    """
    Close a perpetual futures position with a market order.
    Cancels any remaining TP/SL bracket orders.

    Args:
        db: Database session
        client: CoinbaseClient instance
        position: Position to close
        current_price: Current market price
        reason: Exit reason (e.g., "manual", "tp_hit", "sl_hit", "signal")

    Returns:
        Tuple of (success, profit_usdc, profit_pct)
    """
    if shutdown_manager.is_shutting_down:
        logger.warning(f"Rejecting perps close for position #{position.id} - shutdown in progress")
        return False, 0.0, 0.0

    # Determine close side (opposite of position direction)
    if position.direction == "long":
        close_side = "SELL"
        base_size = position.total_base_acquired or 0.0
        profit_usdc = (current_price - position.average_buy_price) * base_size
        cost_basis = position.total_quote_spent or 0.0
    else:
        close_side = "BUY"
        base_size = position.short_total_sold_base or 0.0
        profit_usdc = (position.short_average_sell_price - current_price) * base_size
        cost_basis = position.short_total_sold_quote or 0.0

    # Subtract accumulated funding fees
    profit_usdc -= position.funding_fees_total or 0.0

    profit_pct = (profit_usdc / cost_basis * 100) if cost_basis > 0 else 0.0

    base_size_str = f"{base_size:.8f}"

    logger.info(
        f"Closing perps position #{position.id}: {position.product_id} "
        f"{close_side} {base_size_str} @ ~{current_price:.2f} "
        f"(PnL: {profit_usdc:+.2f} USDC / {profit_pct:+.2f}%)"
    )

    try:
        # Cancel TP/SL bracket orders first
        for order_id in [position.tp_order_id, position.sl_order_id]:
            if order_id:
                try:
                    await client.cancel_order(order_id)
                    logger.info(f"  Cancelled bracket order {order_id}")
                except Exception as e:
                    logger.warning(f"  Failed to cancel bracket order {order_id}: {e}")

        # Place closing market order
        result = await client.close_perps_position(
            product_id=position.product_id,
            base_size=base_size_str,
            side=close_side,
        )

        success_response = result.get("success_response", result.get("order", {}))
        order_id = success_response.get("order_id", "")

        if not order_id:
            error_response = result.get("error_response", {})
            error_msg = error_response.get("message", str(result))
            logger.error(f"Perps close order failed: {error_msg}")
            return False, 0.0, 0.0

        # Create closing trade record
        trade = Trade(
            position_id=position.id,
            side=close_side.lower(),
            quote_amount=base_size * current_price,
            base_amount=base_size,
            price=current_price,
            trade_type="sell",
            order_id=order_id,
        )
        db.add(trade)

        # Update position
        position.status = "closed"
        position.closed_at = datetime.utcnow()
        position.sell_price = current_price
        position.profit_quote = profit_usdc
        position.profit_percentage = profit_pct
        position.profit_usd = profit_usdc  # USDC-denominated perps
        position.exit_reason = reason
        position.tp_order_id = None
        position.sl_order_id = None

        await db.commit()

        logger.info(
            f"Perps position #{position.id} closed: "
            f"PnL {profit_usdc:+.2f} USDC ({profit_pct:+.2f}%)"
        )

        return True, profit_usdc, profit_pct

    except Exception as e:
        logger.error(
            f"Failed to close perps position #{position.id}: {e}", exc_info=True
        )
        await db.rollback()
        return False, 0.0, 0.0
