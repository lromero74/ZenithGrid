"""
Short-position sell execution for the trading engine.

Extracted from sell_executor.py: opening/adding short positions (sell-to-open),
their fill reconciliation and trade recording, and the limit safety-order path
used only by shorts. Shares low-level helpers with sell_executor (imported
one-way; sell_executor does not depend on this module).
"""

import asyncio
import logging
import math
from app.utils.timeutil import utcnow
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.exchange_clients.base import ExchangeClient
from app.models import Bot, PendingOrder, Position, Trade
from app.product_precision import ensure_product_precision, get_base_precision
from app.services.shutdown_manager import shutdown_manager
from app.services.websocket_manager import OrderFillEvent
from app.services.broadcast_backend import broadcast_backend
from app.trading_client import TradingClient
from app.trading_engine.fill_reconciler import _TERMINAL_ORDER_STATUSES
from app.trading_engine.order_logger import log_order_to_history, OrderLogEntry
from app.trading_engine.sell_executor import sell_fill_is_complete

logger = logging.getLogger(__name__)


async def _reconcile_short_sell_fill(
    exchange: ExchangeClient,
    order_id: str,
    fallback_price: float,
) -> tuple:
    """
    Fetch actual short sell fill data from exchange with retry logic.

    CRITICAL: like the long-close path, this NEVER fabricates a fill. If the
    exchange doesn't confirm a fill after all retries, it returns zero amounts
    with ``reconciled=False`` — booking the requested size as "sold" would inflate
    the short position's tracking (sold_base / sold_quote / average price) with
    base that never left the wallet. ``fallback_price`` only labels the price of
    the (zero-amount) unconfirmed result.

    Args:
        exchange: Exchange client instance
        order_id: The exchange order ID to check
        fallback_price: Price used only for the price field when no fill data

    Returns:
        Tuple of (actual_base_sold, quote_received, actual_price, fee_quote,
        reconciled) — reconciled is True only for a real exchange fill.
    """
    logger.info(f"Fetching fill data for short sell order {order_id}")

    max_retries = 10
    for attempt in range(max_retries):
        if attempt > 0:
            delay = min(0.5 * (2 ** (attempt - 1)), 5.0)
            await asyncio.sleep(delay)

        try:
            order_details = await exchange.get_order(order_id)
            filled_size = float(order_details.get("filled_size", "0"))
            filled_value = float(order_details.get("filled_value", "0"))
            avg_price = float(order_details.get("average_filled_price", "0"))
            fee_quote = float(order_details.get("total_fees", "0") or 0)
            status = str(order_details.get("status", "")).upper()
            # Only accept the fill once the order is terminal — a market short-open
            # read mid-fill would book a partial as the complete sale, stranding the
            # rest (the v3.11.6 mid-fill bug, on the short-open side). Clients with
            # no status field (paper/some adapters) are treated terminal.
            order_is_terminal = (not status) or (status in _TERMINAL_ORDER_STATUSES)

            if filled_size > 0 and filled_value > 0 and order_is_terminal:
                actual_price = avg_price if avg_price > 0 else fallback_price
                logger.info(
                    f"Short sell filled: {filled_size:.8f} @ "
                    f"{actual_price:.8f} = {filled_value:.2f}"
                )
                return filled_size, filled_value, actual_price, fee_quote, True

            logger.warning(
                f"Attempt {attempt + 1}/{max_retries}: "
                f"Short sell not yet filled or not terminal (status={status or 'n/a'})"
            )
        except Exception as fill_err:
            logger.warning(
                f"Attempt {attempt + 1}/{max_retries}: "
                f"Failed to get fill data: {fill_err}"
            )

        if attempt == max_retries - 1:
            logger.error(
                f"Short sell order {order_id} did not confirm a fill after "
                f"{max_retries} attempts. Refusing to fabricate — not booking."
            )

    return 0.0, 0.0, fallback_price, 0.0, False


async def _create_short_sell_trade_record(
    db: AsyncSession,
    position: Position,
    order_id: str,
    actual_base_sold: float,
    quote_received: float,
    actual_price: float,
    trade_type: str,
    fee_quote: float = 0.0,
) -> Trade:
    """
    Create Trade record and update position's short tracking fields.

    Initializes short fields on first order, or updates running averages
    for safety orders. Clears error status and commits immediately.

    Args:
        db: Database session
        position: Current short position
        order_id: Exchange order ID
        actual_base_sold: Actual base currency sold
        quote_received: Actual quote currency received
        actual_price: Actual average fill price
        trade_type: Order type identifier

    Returns:
        Committed Trade record
    """
    trade = Trade(
        position_id=position.id,
        timestamp=utcnow(),
        side="sell",
        base_amount=actual_base_sold,
        quote_amount=quote_received,
        price=actual_price,
        trade_type=trade_type,
        order_id=order_id,
        fee_quote=fee_quote,
    )

    db.add(trade)
    position.entry_fees_quote = (getattr(position, "entry_fees_quote", 0.0) or 0.0) + fee_quote

    # Update position's short tracking fields
    is_first_short = position.short_entry_price is None

    if is_first_short:
        position.short_entry_price = actual_price
        position.short_average_sell_price = actual_price
        position.short_total_sold_base = actual_base_sold
        position.short_total_sold_quote = quote_received
        logger.info(
            f"  SHORT POSITION OPENED: Entry={actual_price:.8f}, "
            f"BTC sold={actual_base_sold:.8f}, USD received={quote_received:.2f}"
        )
    else:
        prev_sold_base = position.short_total_sold_base or 0.0
        prev_sold_quote = position.short_total_sold_quote or 0.0

        new_total_sold_base = prev_sold_base + actual_base_sold
        new_total_sold_quote = prev_sold_quote + quote_received

        position.short_total_sold_base = new_total_sold_base
        position.short_total_sold_quote = new_total_sold_quote
        if new_total_sold_base > 0:
            position.short_average_sell_price = (
                new_total_sold_quote / new_total_sold_base
            )
        else:
            position.short_average_sell_price = actual_price

        logger.info(
            f"  SHORT POSITION UPDATED: Avg={position.short_average_sell_price:.8f}, "
            f"Total BTC sold={new_total_sold_base:.8f}, Total USD={new_total_sold_quote:.2f}"
        )

    # Clear any error status
    position.last_error_message = None
    position.last_error_timestamp = None

    await db.commit()
    await db.refresh(trade)

    return trade


async def _post_short_sell_operations(
    db: AsyncSession,
    exchange: ExchangeClient,
    bot: Bot,
    product_id: str,
    position: Position,
    order_id: str,
    actual_base_sold: float,
    quote_received: float,
    actual_price: float,
    trade_type: str,
) -> None:
    """
    Non-critical post-short-sell operations: logging and WebSocket notifications.

    All operations are best-effort and will not raise exceptions if they fail.

    Args:
        db: Database session
        exchange: Exchange client instance
        bot: Bot instance
        product_id: Trading pair
        position: Current position
        order_id: Exchange order ID
        actual_base_sold: Actual base currency sold
        quote_received: Actual quote currency received
        actual_price: Actual average fill price
        trade_type: Order type identifier
    """
    # Log to order history (best-effort)
    try:
        await log_order_to_history(
            db=db, bot=bot, position=position,
            entry=OrderLogEntry(
                product_id=product_id, side="SELL", order_type="MARKET",
                trade_type=trade_type, quote_amount=quote_received,
                price=actual_price, status="success",
                order_id=order_id, base_amount=actual_base_sold,
            ),
        )
    except Exception as e:
        logger.warning(f"Failed to log short sell to history: {e}")

    # Broadcast short sell notification via WebSocket (best-effort)
    try:
        is_paper = (hasattr(exchange, 'is_paper_trading')
                    and callable(exchange.is_paper_trading)
                    and exchange.is_paper_trading())
        await broadcast_backend.broadcast_order_fill(OrderFillEvent(
            fill_type="short_sell",
            product_id=product_id,
            bot_name=bot.name,
            base_amount=actual_base_sold,
            quote_amount=quote_received,
            price=actual_price,
            position_id=position.id,
            user_id=position.user_id,
            is_paper_trading=is_paper,
        ))
    except Exception as e:
        logger.warning(f"Failed to broadcast short sell WebSocket notification: {e}")


async def _submit_short_sell_market_order(
    db: AsyncSession,
    exchange: ExchangeClient,
    trading_client: TradingClient,
    position: Position,
    product_id: str,
    base_amount_rounded: float,
    current_price: float,
    commit_on_error: bool,
) -> Tuple[str, float, float, float, float, bool]:
    """Submit a market short-sell order and reconcile the fill.

    Mirrors _submit_sell_market_order but uses the short-sell reconciler
    and the short-specific error message. Re-raises on failure after
    optionally recording the error on the position. The trailing ``reconciled``
    flag is True only when the returned amounts came from a real exchange fill.
    """
    await shutdown_manager.increment_in_flight()
    try:
        order_response = await trading_client.sell(
            product_id=product_id, base_amount=base_amount_rounded,
        )
        logger.info(f"Exchange short sell order response: {order_response}")

        if order_response.get("blocked_by") == "propguard":
            raise ValueError(
                f"PropGuard blocked: {order_response.get('error', 'Safety check failed')}"
            )

        if not order_response.get("success", False):
            error_response = order_response.get("error_response", {})
            if error_response:
                error_msg = error_response.get("message", "Unknown error")
                error_details = error_response.get("error_details", "")
                error_code = error_response.get("error", "UNKNOWN")
                raise ValueError(
                    f"Short sell failed [{error_code}]: {error_msg}. Details: {error_details}"
                )
            raise ValueError(f"Short sell failed. Full response: {order_response}")

        success_response = order_response.get("success_response", {})
        order_id = success_response.get("order_id", "") or order_response.get("order_id", "")

        if not order_id:
            logger.error(f"Full exchange response: {order_response}")
            raise ValueError("No order_id in successful exchange response")

        actual_base_sold, quote_received, actual_price, fee_quote, reconciled = await _reconcile_short_sell_fill(
            exchange=exchange,
            order_id=order_id,
            fallback_price=current_price,
        )
        return order_id, actual_base_sold, quote_received, actual_price, fee_quote, reconciled

    except Exception as e:
        logger.error(f"Error executing short sell order: {e}")
        if commit_on_error:
            position.last_error_message = f"Short sell failed: {str(e)}"
            position.last_error_timestamp = utcnow()
            await db.commit()
        raise
    finally:
        await shutdown_manager.decrement_in_flight()


async def execute_sell_short(
    db: AsyncSession,
    exchange: ExchangeClient,
    trading_client: TradingClient,
    bot: Bot,
    product_id: str,
    position: Position,
    base_amount: float,
    current_price: float,
    trade_type: str,
    signal_data: Optional[Dict[str, Any]] = None,
    commit_on_error: bool = True,
) -> Optional[Trade]:
    """
    Execute a sell order to OPEN or ADD TO a SHORT position (bidirectional DCA)

    This is different from execute_sell() which CLOSES long positions.
    This function sells BTC to enter/add to a short position.

    Pipeline: validate → place order → reconcile fill → record trade → notify

    Args:
        db: Database session
        exchange: Exchange client instance (CEX or DEX)
        trading_client: TradingClient instance
        bot: Bot instance
        product_id: Trading pair (e.g., 'BTC-USD')
        position: Current short position
        base_amount: Amount of base currency to sell (BTC)
        current_price: Current market price
        trade_type: 'initial' or 'safety_order_X'
        signal_data: Optional signal metadata
        commit_on_error: If True, commit errors to DB (for safety orders).
                       If False, don't commit errors (for base orders - let rollback work)

    Returns:
        Trade record (for market orders only; limit orders return None)
    """
    from app.order_validation import validate_order_size

    # Check if shutdown is in progress - reject new orders
    if shutdown_manager.is_shutting_down:
        logger.warning(f"Rejecting short sell order for {product_id} - shutdown in progress")
        raise RuntimeError("Cannot place orders - shutdown in progress")

    config: Dict = position.strategy_config_snapshot or {}

    # Check if this is a safety order that should use limit orders
    is_safety_order = trade_type.startswith("safety_order")
    dca_execution_type = config.get("dca_execution_type", "market")

    if is_safety_order and dca_execution_type == "limit":
        limit_price = current_price
        logger.info(f"  Placing limit short safety sell: {base_amount:.8f} @ {limit_price:.8f}")
        await execute_limit_sell_safety(
            db=db,
            exchange=exchange,
            trading_client=trading_client,
            bot=bot,
            product_id=product_id,
            position=position,
            base_amount=base_amount,
            limit_price=limit_price,
            trade_type=trade_type,
            signal_data=signal_data,
        )
        # Position is mutated only when the fill is reconciled (safety-order
        # reconciler) — never at placement, and never via the close path.
        return None

    # Execute market sell order (immediate execution)
    logger.info(f"  Executing SHORT SELL: {base_amount:.8f} BTC @ {current_price:.8f}")

    # Ensure precision data is cached for this product (fetches from API if missing)
    await ensure_product_precision(product_id)

    # Round base_amount down to proper precision (floor to avoid INSUFFICIENT_FUND)
    precision = get_base_precision(product_id)
    base_amount_rounded = math.floor(base_amount * (10 ** precision)) / (10 ** precision)

    # Validate order size meets exchange minimums
    is_valid, error_msg = await validate_order_size(
        exchange, product_id, base_amount=base_amount_rounded
    )
    if not is_valid:
        error = f"Order validation failed: {error_msg}"
        logger.error(f"  {error}")
        if commit_on_error:
            position.last_error_message = error
            position.last_error_timestamp = utcnow()
            await db.commit()
        raise ValueError(error)

    order_id, actual_base_sold, quote_received, actual_price, fee_quote, reconciled = (
        await _submit_short_sell_market_order(
            db=db,
            exchange=exchange,
            trading_client=trading_client,
            position=position,
            product_id=product_id,
            base_amount_rounded=base_amount_rounded,
            current_price=current_price,
            commit_on_error=commit_on_error,
        )
    )

    # Only update the short position from a confirmed, (substantially) complete
    # fill. An unconfirmed/partial short sell must NOT inflate the position's
    # short tracking with base that never left the wallet — leave the position
    # untouched and flag it (mirrors the long-close guard).
    if not sell_fill_is_complete(reconciled, actual_base_sold, quote_received, base_amount_rounded):
        await _handle_unconfirmed_short(
            db=db, exchange=exchange, bot=bot, product_id=product_id,
            position=position, order_id=order_id, trade_type=trade_type,
            requested_base=base_amount_rounded, actual_base_sold=actual_base_sold,
            quote_received=quote_received, reconciled=reconciled,
        )
        # Raise (don't silently return) so the caller's existing handling runs:
        # a NEW short position gets marked "failed" / cleaned up, while a DCA add
        # to an existing short is logged and the bot cycle continues. Returning a
        # Trade or None here would leave a phantom/empty short on the books.
        raise ValueError(
            f"Short sell for {product_id} (order {order_id}) did not confirm a "
            f"complete fill — not booking."
        )

    # Record trade and update position
    trade = await _create_short_sell_trade_record(
        db=db,
        position=position,
        order_id=order_id,
        actual_base_sold=actual_base_sold,
        quote_received=quote_received,
        actual_price=actual_price,
        trade_type=trade_type,
        fee_quote=fee_quote,
    )

    # === NON-CRITICAL OPERATIONS BELOW ===
    await _post_short_sell_operations(
        db=db,
        exchange=exchange,
        bot=bot,
        product_id=product_id,
        position=position,
        order_id=order_id,
        actual_base_sold=actual_base_sold,
        quote_received=quote_received,
        actual_price=actual_price,
        trade_type=trade_type,
    )

    logger.info(
        f"  SHORT SELL EXECUTED: {actual_base_sold:.8f} BTC @ {actual_price:.8f} "
        f"= ${quote_received:.2f} (Order: {order_id})"
    )

    return trade


async def execute_limit_sell_safety(
    db: AsyncSession,
    exchange: ExchangeClient,
    trading_client: TradingClient,
    bot: Bot,
    product_id: str,
    position: Position,
    base_amount: float,
    limit_price: float,
    trade_type: str,
    signal_data: Optional[Dict[str, Any]] = None,
) -> PendingOrder:
    """
    Place a limit SELL that ADDS to a SHORT position (DCA safety order).

    This is the short-side analog of ``execute_limit_buy``. Critically, unlike
    ``execute_limit_sell`` (the CLOSE path), it does NOT set
    ``position.closing_via_limit`` / ``limit_close_order_id`` — those drive the
    close monitor, which would mark the position closed and book P&L on fill.
    Instead it records a ``safety_order_*`` PendingOrder and leaves the position
    untouched; the safety-order reconciler applies the fill as an add later.

    Args:
        base_amount: Base currency to sell to grow the short
        limit_price: Target price for the resting limit sell
        trade_type: 'safety_order_1', 'safety_order_2', etc.

    Returns:
        PendingOrder record (status="pending")
    """
    from app.order_validation import validate_order_size

    # Round base down to exchange precision (floor to avoid INSUFFICIENT_FUND)
    await ensure_product_precision(product_id)
    precision = get_base_precision(product_id)
    base_amount_rounded = math.floor(base_amount * (10 ** precision)) / (10 ** precision)

    # Enforce exchange minimums, same as the market short-safety path
    is_valid, error_msg = await validate_order_size(
        exchange, product_id, base_amount=base_amount_rounded
    )
    if not is_valid:
        error = f"Order validation failed: {error_msg}"
        logger.error(f"  {error}")
        position.last_error_message = error
        position.last_error_timestamp = utcnow()
        await db.commit()
        raise ValueError(error)

    expected_quote_amount = base_amount_rounded * limit_price

    order_id = None
    try:
        order_response = await trading_client.sell_limit(
            product_id=product_id, limit_price=limit_price, base_amount=base_amount_rounded
        )

        # Check for PropGuard safety block
        if order_response.get("blocked_by") == "propguard":
            raise ValueError(
                f"PropGuard blocked: {order_response.get('error', 'Safety check failed')}"
            )

        success_response = order_response.get("success_response", {})
        order_id = success_response.get("order_id", "")

        if not order_id:
            raise ValueError("No order_id returned from exchange")

    except Exception as e:
        logger.error(f"Error placing limit short safety sell order: {e}")
        raise

    pending_order = PendingOrder(
        position_id=position.id,
        bot_id=bot.id,
        order_id=order_id,
        product_id=product_id,
        side="SELL",
        order_type="LIMIT",
        limit_price=limit_price,
        quote_amount=expected_quote_amount,
        base_amount=base_amount_rounded,
        trade_type=trade_type,
        status="pending",
        created_at=utcnow(),
    )

    db.add(pending_order)
    # IMPORTANT: do NOT set closing_via_limit / limit_close_order_id — this ADDS
    # to the short. The position is mutated only when this fill is reconciled.
    await db.commit()
    await db.refresh(pending_order)

    logger.info(
        f"Placed limit short safety sell: {base_amount_rounded:.8f} @ {limit_price:.8f} "
        f"(Order ID: {order_id}, {trade_type})"
    )

    return pending_order


async def _handle_unconfirmed_short(
    db: AsyncSession,
    exchange: ExchangeClient,
    bot: Bot,
    product_id: str,
    position: Position,
    order_id: str,
    trade_type: str,
    requested_base: float,
    actual_base_sold: float,
    quote_received: float,
    reconciled: bool,
) -> None:
    """Handle a short sell whose fill the exchange did not confirm as complete.

    Mirrors ``_handle_unconfirmed_close`` for the short-open/add path: it does NOT
    create a Trade or mutate the position's short tracking (sold_base/quote/avg),
    best-effort cancels the order, records the drift for audit, and flags the
    position. Booking the requested size here would grow the short with base that
    never left the wallet.
    """
    logger.error(
        f"  Short sell for {product_id} (order {order_id}, {trade_type}) did NOT "
        f"confirm a complete fill: requested {requested_base:.8f}, exchange "
        f"reported {actual_base_sold:.8f} (reconciled={reconciled}). NOT updating "
        f"short position #{position.id} — refusing to book a phantom short."
    )

    try:
        if hasattr(exchange, "cancel_order"):
            await exchange.cancel_order(order_id)
    except Exception:
        logger.debug(f"cancel_order({order_id}) failed (best-effort)", exc_info=True)

    position.last_error_message = (
        f"Short sell not confirmed: exchange reported {actual_base_sold:.8f}/"
        f"{requested_base:.8f} sold ({trade_type}). Short tracking left unchanged."
    )
    position.last_error_timestamp = utcnow()

    try:
        from app.services.realmoney_audit import record_event
        record_event(
            "short_sell_unconfirmed",
            account_id=getattr(position, "account_id", None),
            position_id=getattr(position, "id", None),
            product_id=product_id,
            order_id=order_id,
            trade_type=trade_type,
            requested=requested_base,
            actual_sold=actual_base_sold,
            quote_received=quote_received,
            reconciled=reconciled,
        )
    except Exception:
        logger.debug("short_sell_unconfirmed audit failed", exc_info=True)

    try:
        await log_order_to_history(
            db=db, bot=bot, position=position,
            entry=OrderLogEntry(
                product_id=product_id, side="SELL", order_type="MARKET",
                trade_type=trade_type, quote_amount=quote_received,
                price=0.0, status="failed", order_id=order_id,
                base_amount=actual_base_sold,
                error_message="Short sell did not confirm a complete fill",
            ),
        )
    except Exception:
        logger.debug("order-history log for unconfirmed short sell failed", exc_info=True)

    try:
        await db.commit()
    except Exception:
        logger.warning(
            "Could not persist unconfirmed-short state on position %s",
            position.id, exc_info=True,
        )
