"""
Sell order execution for trading engine
Handles market and limit sell orders
"""

from app.utils.timeutil import utcnow
import logging
import math
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.currency_utils import get_quote_currency
from app.exchange_clients.base import ExchangeClient
from app.models import Bot, PendingOrder, Position, Trade
from app.product_precision import ensure_product_precision, get_base_precision
from app.services.shutdown_manager import shutdown_manager
from app.services.websocket_manager import OrderFillEvent
from app.services.broadcast_backend import broadcast_backend
from app.trading_client import TradingClient
from app.trading_engine.fill_reconciler import reconcile_order_fill
from app.services.pnl_service import calculate_realized_spot_profit, fee_adjusted_tp_floor
from app.services.exit_provenance import record_exit_provenance
from app.trading_engine.order_logger import log_order_to_history, OrderLogEntry

logger = logging.getLogger(__name__)

# Tiny haircut applied when clamping a sell to the wallet's available balance.
# Mirrors the dust sweeper's 0.999 — leaves rounding/hold-timing slack so the
# exchange never rejects the order for being a hair over the true free balance.
SELL_BALANCE_HAIRCUT = 0.999


def clamp_sell_base_amount(
    recorded: float, available: float, precision: int,
) -> Tuple[float, bool]:
    """Resolve how much base to sell without exceeding the wallet balance.

    A position's recorded ``total_base_acquired`` can drift ABOVE the coins
    actually held on the exchange — fees, prior rebalance/dust sweeps, or
    partial fills shave the wallet while the position record stays whole.
    Selling the full recorded amount then fails with INSUFFICIENT_FUND and the
    position is stuck forever, retried every cycle. When the wallet is short,
    sell the available balance minus a tiny haircut; otherwise sell the full
    recorded amount. Both are floored to the exchange's base precision so we
    never submit more than we can cover.

    Returns ``(base_amount, clamped)`` where ``clamped`` is True when the wallet
    balance forced a reduction below the recorded size.
    """
    clamped = available < recorded
    target = (available * SELL_BALANCE_HAIRCUT) if clamped else recorded
    if target < 0:
        target = 0.0
    factor = 10 ** precision
    base_amount = math.floor(target * factor) / factor
    return base_amount, clamped


async def _resolve_real_close_amount(
    exchange: ExchangeClient,
    product_id: str,
    position: Position,
    raw_amount: float,
    precision: int,
) -> Tuple[float, bool]:
    """Clamp a real (non-paper) close to the wallet's live available balance.

    Fetches the current available base balance and defers to
    ``clamp_sell_base_amount``. If the balance lookup fails, falls back to the
    recorded amount (floored) so a transient API hiccup never blocks a close.
    """
    base_currency = product_id.split("-")[0]
    try:
        try:
            bal_info = await exchange.get_balance(base_currency, force_fresh=True)
        except TypeError:
            # Exchange clients whose get_balance has no force_fresh kwarg.
            bal_info = await exchange.get_balance(base_currency)
        available = float(bal_info.get("available", bal_info.get("balance", 0)) or 0)
    except Exception as e:
        logger.warning(
            f"  Could not fetch {base_currency} balance to clamp sell "
            f"({e}); proceeding with recorded amount."
        )
        factor = 10 ** precision
        return math.floor(raw_amount * factor) / factor, False

    base_amount, clamped = clamp_sell_base_amount(raw_amount, available, precision)
    if clamped:
        logger.warning(
            f"  Wallet short for {product_id}: position holds {raw_amount:.8f} "
            f"{base_currency} on record but only {available:.8f} is available. "
            f"Clamping close to {base_amount:.8f} (booking the real, smaller "
            f"proceeds)."
        )
        # Audit the drift so this class of issue is greppable after the fact.
        try:
            from app.services.realmoney_audit import record_event
            record_event(
                "sell_clamped",
                account_id=getattr(position, "account_id", None),
                position_id=getattr(position, "id", None),
                product_id=product_id,
                recorded=raw_amount,
                available=available,
                clamped_to=base_amount,
            )
        except Exception:
            logger.debug("clamp audit failed", exc_info=True)
    return base_amount, clamped


async def _try_limit_sell(
    db: AsyncSession,
    exchange: ExchangeClient,
    trading_client: TradingClient,
    bot: Bot,
    product_id: str,
    position: Position,
    current_price: float,
    signal_data: Optional[Dict[str, Any]],
) -> Tuple[bool, Optional[Tuple[None, float, float]]]:
    """
    Attempt to place a limit sell order at mark price.

    Gets the ticker to calculate the mark price (mid between bid/ask) and
    places a limit sell order. If successful, returns early result. If the
    limit order placement fails, returns False so the caller can attempt
    a market order fallback.

    Args:
        db: Database session
        exchange: Exchange client instance
        trading_client: TradingClient instance
        bot: Bot instance
        product_id: Trading pair
        position: Current position to close
        current_price: Current market price (fallback)
        signal_data: Optional signal metadata

    Returns:
        Tuple of (handled, result). If handled is True, result contains the
        return value (None, 0.0, 0.0). If handled is False, result is None
        and the caller should fall back to market order.
    """
    try:
        # Get ticker to calculate mark price
        ticker = await exchange.get_ticker(product_id)
        best_bid = float(
            ticker.get("best_bid", 0) or ticker.get("bid", 0)
        )
        best_ask = float(
            ticker.get("best_ask", 0) or ticker.get("ask", 0)
        )

        # Use mark price (mid-point) as limit price
        if best_bid > 0 and best_ask > 0:
            limit_price = (best_bid + best_ask) / 2
        else:
            # Fallback to current price if bid/ask not available
            limit_price = current_price

        # Use full position amount (execute_limit_sell will handle precision rounding)
        base_amount = position.total_base_acquired

        logger.info(f"  Placing LIMIT close order @ {limit_price:.8f} (mark price)")

        # Place limit order and return - position stays open until filled
        # Limit order placed; fill tracking handled by limit_order_monitor service
        await execute_limit_sell(
            db=db,
            exchange=exchange,
            trading_client=trading_client,
            bot=bot,
            product_id=product_id,
            position=position,
            base_amount=base_amount,
            limit_price=limit_price,
            signal_data=signal_data,
        )

        # Return None trade since order is pending
        # Actual Trade record will be created when limit order fills
        return True, (None, 0.0, 0.0)

    except Exception as e:
        logger.warning(f"Failed to place limit close order: {e}. Checking if market order is viable...")
        return False, None


async def _validate_market_fallback(
    position: Position,
    current_price: float,
    config: Dict,
) -> bool:
    """
    Validate that profit is sufficient before falling back to a market order.

    When a limit sell order fails, this checks whether the current profit
    still meets the minimum take_profit_percentage threshold. If profit has
    dropped below the target, the sell is aborted to prevent selling below
    the desired profit level.

    Args:
        position: Current position
        current_price: Current market price
        config: Strategy config snapshot

    Returns:
        True if market fallback is approved (profit sufficient), False to abort.
    """
    current_value = position.total_base_acquired * current_price
    profit_amount = current_value - position.total_quote_spent
    profit_pct = (profit_amount / position.total_quote_spent * 100) if position.total_quote_spent > 0 else 0.0

    # Get minimum profit threshold from config, raised so the configured target is
    # honored NET of round-trip fees (gross profit_pct never subtracted them).
    min_profit = fee_adjusted_tp_floor(position, config.get("take_profit_percentage", 3.0))

    if profit_pct < min_profit:
        logger.warning(
            f"Aborting market order fallback - current profit {profit_pct:.2f}% is below "
            f"minimum target {min_profit:.2f}%. Will retry on next check cycle."
        )
        return False

    logger.info(
        f"Market order fallback approved - current profit {profit_pct:.2f}% >= "
        f"minimum {min_profit:.2f}%. Proceeding with market order."
    )
    return True


async def _reconcile_sell_fill(
    exchange: ExchangeClient,
    order_id: str,
    product_id: str,
    fallback_price: float,
) -> tuple:
    """
    Fetch actual sell fill data from exchange with retry logic.

    CRITICAL: unlike the buy path, the sell path does NOT pass a ``fallback_base``
    to the reconciler. A close must be booked only from a confirmed fill — if the
    exchange never reports a fill, fabricating one would mark the position closed
    while the coins are still in the wallet (the stranded-balance bug). When the
    fill is unconfirmed the reconciler returns zeros with ``reconciled=False`` and
    the caller leaves the position open to retry. ``fallback_price`` is used only
    to label the (zero-amount) result's price, never to invent a quantity.

    Args:
        exchange: Exchange client instance
        order_id: The exchange order ID to check
        product_id: Trading pair
        fallback_price: Price used only for the price field when no fill data

    Returns:
        Tuple of (actual_base_sold, quote_received, actual_price, total_fees,
        reconciled) where ``reconciled`` is True only for a real exchange fill.
    """
    logger.info(f"Fetching fill data for sell order {order_id}")

    fill_data = await reconcile_order_fill(
        exchange=exchange,
        order_id=order_id,
        product_id=product_id,
        max_retries=10,
        adjust_btc_fees=False,
        round_base_to_precision=False,
        fallback_base=None,
        fallback_price=None,
    )

    actual_price = fill_data.average_price if fill_data.average_price > 0 else fallback_price
    return (
        fill_data.filled_size,
        fill_data.filled_value,
        actual_price,
        fill_data.total_fees,
        fill_data.reconciled,
    )


async def _create_sell_trade_record(
    db: AsyncSession,
    exchange: ExchangeClient,
    position: Position,
    order_id: str,
    product_id: str,
    actual_base_sold: float,
    quote_received: float,
    actual_price: float,
    fee_quote: float,
    signal_data: Optional[Dict[str, Any]],
) -> Tuple[Trade, float, float]:
    """
    Create Trade record, compute profit, and close the position.

    Calculates profit in both quote currency and USD, creates the Trade
    record, updates position status to closed, and commits immediately.

    Args:
        db: Database session
        exchange: Exchange client instance (for BTC/USD price)
        position: Current position to close
        order_id: Exchange order ID
        product_id: Trading pair
        actual_base_sold: Actual base currency sold
        quote_received: Actual quote currency received
        actual_price: Actual average fill price
        signal_data: Optional signal metadata

    Returns:
        Tuple of (trade, profit_quote, profit_percentage)
    """
    quote_currency = get_quote_currency(product_id)

    # Calculate profit using actual fill data
    exit_fees_quote = (position.exit_fees_quote or 0.0) + fee_quote
    profit_quote, profit_percentage = calculate_realized_spot_profit(
        position.total_quote_spent,
        quote_received,
        position.entry_fees_quote or 0.0,
        exit_fees_quote,
    )

    # Get BTC/USD price for USD profit tracking
    try:
        btc_usd_price_at_close = await exchange.get_btc_usd_price()
        # Convert profit to USD if quote is BTC
        if quote_currency == "BTC":
            profit_usd = profit_quote * btc_usd_price_at_close
        else:  # quote is USD
            profit_usd = profit_quote
    except Exception:
        logger.warning("Failed to get BTC/USD price for profit calculation", exc_info=True)
        btc_usd_price_at_close = None
        profit_usd = None

    # Record trade with actual fill data
    trade = Trade(
        position_id=position.id,
        timestamp=utcnow(),
        side="sell",
        quote_amount=quote_received,
        base_amount=actual_base_sold,
        price=actual_price,
        trade_type="sell",
        order_id=order_id,
        fee_quote=fee_quote,
        macd_value=signal_data.get("macd_value") if signal_data else None,
        macd_signal=signal_data.get("macd_signal") if signal_data else None,
        macd_histogram=signal_data.get("macd_histogram") if signal_data else None,
    )

    db.add(trade)

    # Close position using actual fill data
    position.status = "closed"
    position.closed_at = utcnow()
    position.sell_price = actual_price
    position.total_quote_received = quote_received
    position.exit_fees_quote = exit_fees_quote
    position.profit_quote = profit_quote
    position.profit_percentage = profit_percentage
    position.btc_usd_price_at_close = btc_usd_price_at_close
    position.profit_usd = profit_usd
    trigger_reason = (signal_data or {}).get("exit_trigger_reason") or position.exit_reason or "Automated exit"
    record_exit_provenance(position, trigger_reason, order_id)

    # CRITICAL: Commit trade and position close IMMEDIATELY
    # This ensures we never lose a sell record even if subsequent operations fail
    await db.commit()
    await db.refresh(trade)

    return trade, profit_quote, profit_percentage


async def execute_limit_sell(
    db: AsyncSession,
    exchange: ExchangeClient,
    trading_client: TradingClient,
    bot: Bot,
    product_id: str,
    position: Position,
    base_amount: float,
    limit_price: float,
    signal_data: Optional[Dict[str, Any]] = None,
) -> PendingOrder:
    """
    Place a limit sell order to close position and track it in pending_orders table

    Args:
        db: Database session
        exchange: Exchange client instance (CEX or DEX)
        trading_client: TradingClient instance
        bot: Bot instance
        product_id: Trading pair (e.g., 'ETH-BTC')
        position: Current position to close
        base_amount: Amount of base currency to sell
        limit_price: Target price for the limit order (mark price)
        signal_data: Optional signal metadata

    Returns:
        PendingOrder record
    """
    # Ensure precision data is cached for this product (fetches from API if missing)
    await ensure_product_precision(product_id)

    # Round base_amount down to proper precision (floor to avoid INSUFFICIENT_FUND)
    precision = get_base_precision(product_id)
    base_amount_rounded = math.floor(base_amount * (10 ** precision)) / (10 ** precision)

    logger.info(
        f"Limit sell precision: raw={base_amount:.8f}, "
        f"precision={precision} decimals, rounded_down={base_amount_rounded:.8f}"
    )

    # Calculate expected quote amount at limit price
    expected_quote_amount = base_amount_rounded * limit_price

    # Place limit order via TradingClient
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
        logger.error(f"Error placing limit sell order: {e}")
        raise

    # Create PendingOrder record
    pending_order = PendingOrder(
        position_id=position.id,
        bot_id=bot.id,
        order_id=order_id,
        product_id=product_id,
        side="SELL",
        order_type="LIMIT",
        limit_price=limit_price,
        quote_amount=expected_quote_amount,
        base_amount=base_amount,
        trade_type="limit_close",
        status="pending",
        created_at=utcnow(),
    )

    db.add(pending_order)

    # Mark position as closing via limit
    position.closing_via_limit = True
    position.limit_close_order_id = order_id

    await db.commit()
    await db.refresh(pending_order)

    # Get base currency name from product_id
    base_currency = product_id.split("-")[0]
    logger.info(
        f"Placed limit sell order: {base_amount:.8f} {base_currency} @ {limit_price:.8f} (Order ID: {order_id})"
    )

    return pending_order


async def _post_sell_operations(
    db: AsyncSession,
    exchange: ExchangeClient,
    trading_client: TradingClient,
    bot: Bot,
    product_id: str,
    position: Position,
    order_id: str,
    actual_base_sold: float,
    quote_received: float,
    actual_price: float,
    profit_quote: float,
    profit_percentage: float,
) -> None:
    """
    Non-critical post-sell operations: logging, WebSocket, event bus, cache, re-analysis.

    All operations are best-effort and will not raise exceptions if they fail.
    The trade record has already been committed before this is called.

    Args:
        db: Database session
        exchange: Exchange client instance
        trading_client: TradingClient instance
        bot: Bot instance
        product_id: Trading pair
        position: Current position
        order_id: Exchange order ID
        actual_base_sold: Actual base currency sold
        quote_received: Actual quote currency received
        actual_price: Actual average fill price
        profit_quote: Profit in quote currency
        profit_percentage: Profit percentage
    """
    # Log successful sell to order history (best-effort)
    try:
        await log_order_to_history(
            db=db, bot=bot, position=position,
            entry=OrderLogEntry(
                product_id=product_id, side="SELL", order_type="MARKET",
                trade_type="sell", quote_amount=quote_received,
                price=actual_price, status="success",
                order_id=order_id, base_amount=actual_base_sold,
            ),
        )
    except Exception as e:
        logger.warning(f"Failed to log sell order to history (trade was recorded): {e}")

    # Broadcast sell order fill notification via WebSocket (best-effort)
    try:
        is_paper = (hasattr(exchange, 'is_paper_trading')
                    and callable(exchange.is_paper_trading)
                    and exchange.is_paper_trading())
        await broadcast_backend.broadcast_order_fill(OrderFillEvent(
            fill_type="sell_order",
            product_id=product_id,
            bot_name=bot.name,
            base_amount=actual_base_sold,
            quote_amount=quote_received,
            price=actual_price,
            position_id=position.id,
            profit=profit_quote,
            profit_percentage=profit_percentage,
            user_id=position.user_id,
            is_paper_trading=is_paper,
            exit_source=position.exit_source,
            exit_trigger_reason=position.exit_trigger_reason,
            exit_process_role=position.exit_process_role,
            exit_hostname=position.exit_hostname,
            exit_order_id=position.exit_order_id,
            unexpected_exit=getattr(position, "exit_was_unexpected", False),
        ))
    except Exception as e:
        logger.warning(f"Failed to broadcast WebSocket notification (trade was recorded): {e}")

    # Publish domain event (best-effort — polling fallback handles misses)
    try:
        from app.event_bus import (
            event_bus, ORDER_FILLED, OrderFilledPayload,
            POSITION_CLOSED, PositionClosedPayload,
        )
        await event_bus.publish(ORDER_FILLED, OrderFilledPayload(
            position_id=position.id,
            user_id=position.user_id,
            product_id=product_id,
            fill_type="sell_order",
            quote_amount=quote_received,
            base_amount=actual_base_sold,
            price=actual_price,
            profit=profit_quote,
            profit_percentage=profit_percentage,
            is_paper_trading=is_paper,
        ))
        await event_bus.publish(POSITION_CLOSED, PositionClosedPayload(
            position_id=position.id,
            user_id=position.user_id,
            product_id=product_id,
            bot_id=bot.id,
            profit_quote=profit_quote,
            profit_percentage=profit_percentage,
        ))
    except Exception as e:
        logger.warning(f"Event bus publish failed (non-critical): {e}")

    # Invalidate balance cache after trade (best-effort)
    try:
        await trading_client.invalidate_balance_cache()
    except Exception as e:
        logger.warning(f"Failed to invalidate balance cache (trade was recorded): {e}")

    # Trigger immediate re-analysis to find replacement position (best-effort)
    try:
        logger.info("Position closed - triggering immediate re-analysis to find replacement")
        bot.last_signal_check = None
        await db.commit()
    except Exception as e:
        logger.warning(f"Failed to trigger re-analysis (trade was recorded): {e}")


async def _close_sell_position_as_dust(
    db: AsyncSession,
    exchange: ExchangeClient,
    bot: Bot,
    product_id: str,
    position: Position,
    current_price: float,
    available_base: Optional[float] = None,
) -> Tuple[None, float, float]:
    """Close a long position as dust (rounds to zero base) with no exchange order.

    Calculates profit at current price, finalizes the Position row, and
    publishes a POSITION_CLOSED event (best-effort). Writes the same fields the
    normal market close does (``sell_price``, BTC→USD-converted ``profit_usd``) so
    dust closes aren't inconsistent — ``sell_price`` is the persisted column
    (``close_price`` is not a column), and ``profit_usd`` must be converted for
    BTC-quoted pairs rather than booking the BTC amount as USD.
    """
    # Value the retained dust at the ACTUAL base on hand. The round-to-zero caller
    # leaves available_base=None (the recorded amount IS what's held, just too small
    # to sell). The clamped caller passes the clamped wallet balance — there the
    # recorded total_base_acquired exceeds what's actually in the wallet, so booking
    # the recorded amount would over-book proceeds the position never received.
    effective_base = available_base if available_base is not None else position.total_base_acquired
    quote_value = effective_base * current_price
    spent = position.total_quote_spent or 0
    dust_profit = quote_value - spent
    dust_pct = (dust_profit / spent * 100) if spent > 0 else -100.0
    position.status = "closed"
    position.closed_at = utcnow()
    position.sell_price = current_price
    position.profit_quote = dust_profit
    position.profit_percentage = dust_pct
    position.total_quote_received = quote_value

    # Convert profit to USD using the quote currency (matches _create_sell_trade_record).
    if get_quote_currency(product_id) == "BTC":
        try:
            btc_usd_price_at_close = await exchange.get_btc_usd_price()
            position.btc_usd_price_at_close = btc_usd_price_at_close
            position.profit_usd = dust_profit * btc_usd_price_at_close
        except Exception:
            logger.warning("Dust close: failed to fetch BTC/USD for profit_usd", exc_info=True)
            position.profit_usd = None
    else:  # USD/USDC/USDT-quoted
        position.profit_usd = dust_profit

    record_exit_provenance(position, position.exit_reason or "Dust position close", None)
    await db.commit()
    try:
        from app.event_bus import event_bus, POSITION_CLOSED, PositionClosedPayload
        await event_bus.publish(POSITION_CLOSED, PositionClosedPayload(
            position_id=position.id,
            user_id=position.user_id,
            product_id=product_id,
            bot_id=bot.id,
            profit_quote=dust_profit,
            profit_percentage=dust_pct,
        ))
    except Exception as e:
        logger.warning(f"Event bus publish failed (non-critical): {e}")
    return None, dust_profit, dust_pct


async def _submit_sell_market_order(
    db: AsyncSession,
    exchange: ExchangeClient,
    trading_client: TradingClient,
    bot: Bot,
    product_id: str,
    position: Position,
    base_amount: float,
    current_price: float,
) -> Tuple[str, float, float, float, float, bool]:
    """Submit a market sell order and reconcile the fill.

    Wraps exchange-submission bookkeeping (shutdown-manager counters,
    PropGuard gate, error-path position + order-history logging) and returns
    (order_id, actual_base_sold, quote_received, actual_price, fee_quote,
    reconciled). ``reconciled`` is True only when the returned amounts came from
    a real exchange fill — the caller must not close the position on a False.

    Re-raises the original exception on failure after logging.
    """
    await shutdown_manager.increment_in_flight()
    try:
        order_response = await trading_client.sell(product_id=product_id, base_amount=base_amount)
        logger.info(f"Exchange sell order response: {order_response}")

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
                    f"Sell order failed [{error_code}]: {error_msg}. Details: {error_details}"
                )
            raise ValueError(f"Sell order failed with no error details. Full response: {order_response}")

        success_response = order_response.get("success_response", {})
        order_id = success_response.get("order_id", "") or order_response.get("order_id", "")

        if not order_id:
            logger.error(f"Full exchange response: {order_response}")
            raise ValueError(
                f"No order_id found in successful exchange response. "
                f"Response keys: {list(order_response.keys())}"
            )

        actual_base_sold, quote_received, actual_price, fee_quote, reconciled = await _reconcile_sell_fill(
            exchange=exchange,
            order_id=order_id,
            product_id=product_id,
            fallback_price=current_price,
        )
        return order_id, actual_base_sold, quote_received, actual_price, fee_quote, reconciled

    except Exception as e:
        logger.error(f"Error executing sell order: {e}")

        try:
            position.last_error_message = f"Sell failed: {str(e)[:200]}"
            position.last_error_timestamp = utcnow()
            await db.commit()
        except Exception:
            logger.warning(
                "Could not persist last_error on position %s after sell failure",
                position.id, exc_info=True,
            )  # Don't mask the original error — log and move on

        try:
            await log_order_to_history(
                db=db, bot=bot, position=position,
                entry=OrderLogEntry(
                    product_id=product_id, side="SELL", order_type="MARKET",
                    trade_type="sell", quote_amount=base_amount * current_price,
                    price=current_price, status="failed",
                    error_message=str(e)[:200],
                ),
            )
            await db.commit()
        except Exception:
            pass

        raise

    finally:
        await shutdown_manager.decrement_in_flight()


# A close is only booked when the exchange confirms a substantially complete
# fill. The slack (1%) absorbs precision/fee rounding on the filled size; below
# it the order did not (fully) execute, so the position must stay OPEN rather
# than be marked closed with proceeds that never arrived.
SELL_COMPLETE_FILL_RATIO = 0.99


def sell_fill_is_complete(
    reconciled: bool,
    actual_base_sold: float,
    quote_received: float,
    requested_base: float,
) -> bool:
    """Decide whether a sell fill is safe to book as a position close.

    Returns True ONLY for a confirmed (``reconciled``) fill whose size covers at
    least ``SELL_COMPLETE_FILL_RATIO`` of the submitted amount and that received
    quote currency. An unconfirmed, zero, or partial fill returns False so the
    caller leaves the position open to retry — never fabricating a sale.
    """
    if not reconciled or actual_base_sold <= 0 or quote_received <= 0:
        return False
    if requested_base <= 0:
        return False
    return actual_base_sold >= requested_base * SELL_COMPLETE_FILL_RATIO


async def _handle_unconfirmed_close(
    db: AsyncSession,
    exchange: ExchangeClient,
    bot: Bot,
    product_id: str,
    position: Position,
    order_id: str,
    requested_base: float,
    actual_base_sold: float,
    quote_received: float,
    reconciled: bool,
) -> Tuple[None, float, float]:
    """Handle a sell whose fill the exchange did not confirm as complete.

    Leaves the position OPEN (never marks it closed), best-effort cancels the
    order so a late fill can't slip through unaccounted, records the drift for
    audit, and returns the ``(None, 0.0, 0.0)`` "not closed" sentinel. The next
    monitor cycle re-attempts the close, clamping to the live wallet balance — so
    coins are never abandoned and proceeds are never fabricated.
    """
    logger.error(
        f"  Sell for {product_id} (order {order_id}) did NOT confirm a complete "
        f"fill: requested {requested_base:.8f}, exchange reported "
        f"{actual_base_sold:.8f} sold (reconciled={reconciled}). Leaving position "
        f"#{position.id} OPEN to retry — refusing to book a phantom close."
    )

    # Best-effort cancel: a market order showing no fill after ~30s has almost
    # certainly failed, but cancel defensively so a stray resting order can't
    # fill later without the position being open to record it.
    try:
        if hasattr(exchange, "cancel_order"):
            await exchange.cancel_order(order_id)
    except Exception:
        logger.debug(f"cancel_order({order_id}) failed (best-effort)", exc_info=True)

    position.last_error_message = (
        f"Sell not confirmed: exchange reported {actual_base_sold:.8f}/"
        f"{requested_base:.8f} sold. Position left open to retry."
    )
    position.last_error_timestamp = utcnow()

    try:
        from app.services.realmoney_audit import record_event
        record_event(
            "sell_unconfirmed",
            account_id=getattr(position, "account_id", None),
            position_id=getattr(position, "id", None),
            product_id=product_id,
            order_id=order_id,
            requested=requested_base,
            actual_sold=actual_base_sold,
            quote_received=quote_received,
            reconciled=reconciled,
        )
    except Exception:
        logger.debug("sell_unconfirmed audit failed", exc_info=True)

    try:
        await log_order_to_history(
            db=db, bot=bot, position=position,
            entry=OrderLogEntry(
                product_id=product_id, side="SELL", order_type="MARKET",
                trade_type="sell", quote_amount=quote_received,
                price=0.0, status="failed", order_id=order_id,
                base_amount=actual_base_sold,
                error_message="Sell did not confirm a complete fill",
            ),
        )
    except Exception:
        logger.debug("order-history log for unconfirmed sell failed", exc_info=True)

    try:
        await db.commit()
    except Exception:
        logger.warning(
            "Could not persist unconfirmed-sell state on position %s",
            position.id, exc_info=True,
        )

    return None, 0.0, 0.0


async def execute_sell(
    db: AsyncSession,
    exchange: ExchangeClient,
    trading_client: TradingClient,
    bot: Bot,
    product_id: str,
    position: Position,
    current_price: float,
    signal_data: Optional[Dict[str, Any]] = None,
    force_market: bool = False,
) -> Tuple[Optional[Trade], float, float]:
    """
    Execute a sell order for entire position (market or limit based on configuration)

    Args:
        db: Database session
        exchange: Exchange client instance (CEX or DEX)
        trading_client: TradingClient instance
        bot: Bot instance
        product_id: Trading pair (e.g., 'ETH-BTC')
        position: Current position to close
        current_price: Current market price
        signal_data: Optional signal metadata

    Returns:
        Tuple of (trade, profit_quote, profit_percentage)
        If limit order is placed, returns (None, 0.0, 0.0) and position remains open
    """
    # Check if shutdown is in progress - reject new orders
    if shutdown_manager.is_shutting_down:
        logger.warning(f"Rejecting sell order for {product_id} - shutdown in progress")
        raise RuntimeError("Cannot place orders - shutdown in progress")

    # CRITICAL: Prevent duplicate limit sell orders
    # If position is already closing via limit order, don't place another one
    if position.closing_via_limit:
        logger.warning(
            f"Position #{position.id} already has a pending limit close order "
            f"(order_id: {position.limit_close_order_id}). Skipping duplicate sell."
        )
        return None, 0.0, 0.0

    # Check if we should use a limit order for closing
    # Stop loss and trailing stop loss always use market orders (force_market=True)
    config: Dict = position.strategy_config_snapshot or {}
    take_profit_order_type = config.get("take_profit_order_type", "market")

    # Paper trading cannot simulate pending limit orders -- always use market
    is_paper = (
        hasattr(exchange, 'is_paper_trading')
        and callable(exchange.is_paper_trading)
        and exchange.is_paper_trading()
    )

    if take_profit_order_type == "limit" and not force_market and not is_paper:
        # Try placing a limit sell order
        handled, result = await _try_limit_sell(
            db=db,
            exchange=exchange,
            trading_client=trading_client,
            bot=bot,
            product_id=product_id,
            position=position,
            current_price=current_price,
            signal_data=signal_data,
        )

        if handled:
            return result

        # Limit order failed - validate profit before market fallback
        if not await _validate_market_fallback(position, current_price, config):
            return None, 0.0, 0.0
        # Fall through to market order execution below

    # Execute market order (default behavior or fallback)
    logger.info(f"  Executing MARKET close order @ {current_price:.8f}")

    # Ensure precision data is cached for this product (fetches from API if missing)
    await ensure_product_precision(product_id)

    # Round base_amount down to proper precision (floor to avoid INSUFFICIENT_FUND)
    precision = get_base_precision(product_id)
    raw_amount = position.total_base_acquired

    # For paper trading: ensure the wallet has enough base currency.
    # Multiple positions can share the same base currency on one account,
    # so the wallet may temporarily be short. Top up if needed to avoid
    # selling less than the position holds (which causes artificial losses).
    clamped = False
    if is_paper:
        base_currency = product_id.split("-")[0]
        try:
            bal_info = await exchange.get_balance(base_currency)
            available = float(bal_info.get("available", bal_info.get("balance", 0)))
            if available < raw_amount:
                shortfall = raw_amount - available
                logger.info(
                    f"  Paper balance top-up: position needs {raw_amount:.8f} "
                    f"{base_currency} but wallet has {available:.8f}. "
                    f"Adding {shortfall:.8f} to cover position."
                )
                await exchange.adjust_balance(base_currency, shortfall)
        except Exception as e:
            logger.warning(f"Could not check/adjust paper balance: {e}")
        base_amount = math.floor(raw_amount * (10 ** precision)) / (10 ** precision)
    else:
        # Real account: never try to sell more base than the wallet actually
        # holds. The recorded size can drift above the on-exchange balance, and
        # selling the full amount then fails with INSUFFICIENT_FUND, stranding
        # the position. Clamp to the live available balance.
        base_amount, clamped = await _resolve_real_close_amount(
            exchange, product_id, position, raw_amount, precision
        )

    logger.info(
        f"  Selling {base_amount:.8f} {product_id.split('-')[0]} "
        f"(raw: {position.total_base_acquired:.8f}, precision: {precision} decimals)"
    )

    # Dust position: if base_amount rounds to 0, close as dust (no exchange order)
    if base_amount <= 0:
        logger.warning(
            f"  Sell amount rounds to 0 for {product_id} "
            f"(raw={raw_amount:.8f}, precision={precision}). Closing as dust."
        )
        return await _close_sell_position_as_dust(
            db, exchange, bot, product_id, position, current_price,
        )

    # If the wallet balance forced a clamp, the remaining base may now sit below
    # the exchange minimum — close as dust rather than submit a doomed order.
    if clamped:
        from app.order_validation import validate_order_size
        is_valid, _vmsg = await validate_order_size(
            exchange, product_id, base_amount=base_amount
        )
        if not is_valid:
            logger.warning(
                f"  Clamped sell {base_amount:.8f} {product_id} is below the "
                f"exchange minimum ({_vmsg}). Closing as dust."
            )
            return await _close_sell_position_as_dust(
                db, exchange, bot, product_id, position, current_price,
                available_base=base_amount,
            )

    order_id, actual_base_sold, quote_received, actual_price, fee_quote, reconciled = await _submit_sell_market_order(
        db=db,
        exchange=exchange,
        trading_client=trading_client,
        bot=bot,
        product_id=product_id,
        position=position,
        base_amount=base_amount,
        current_price=current_price,
    )

    # A close may ONLY be booked from a confirmed, (substantially) complete fill.
    # If the exchange did not confirm the sale, the coins are still in the wallet
    # — marking the position closed here would fabricate proceeds and orphan the
    # coins (the v3.9.x stranded-balance bug). Leave the position open to retry.
    if not sell_fill_is_complete(reconciled, actual_base_sold, quote_received, base_amount):
        return await _handle_unconfirmed_close(
            db=db,
            exchange=exchange,
            bot=bot,
            product_id=product_id,
            position=position,
            order_id=order_id,
            requested_base=base_amount,
            actual_base_sold=actual_base_sold,
            quote_received=quote_received,
            reconciled=reconciled,
        )

    # Create trade record, compute profit, and close position
    trade, profit_quote, profit_percentage = await _create_sell_trade_record(
        db=db,
        exchange=exchange,
        position=position,
        order_id=order_id,
        product_id=product_id,
        actual_base_sold=actual_base_sold,
        quote_received=quote_received,
        actual_price=actual_price,
        fee_quote=fee_quote,
        signal_data=signal_data,
    )

    # === NON-CRITICAL OPERATIONS BELOW ===
    # These can fail without losing the trade record
    await _post_sell_operations(
        db=db,
        exchange=exchange,
        trading_client=trading_client,
        bot=bot,
        product_id=product_id,
        position=position,
        order_id=order_id,
        actual_base_sold=actual_base_sold,
        quote_received=quote_received,
        actual_price=actual_price,
        profit_quote=profit_quote,
        profit_percentage=profit_percentage,
    )

    return trade, profit_quote, profit_percentage
