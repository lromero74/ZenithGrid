"""
Buy order execution for trading engine
Handles market and limit buy orders
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.currency_utils import get_quote_currency
from app.exchange_clients.base import ExchangeClient
from app.models import Bot, PendingOrder, Position, Trade
from app.order_validation import validate_order_size
from app.services.shutdown_manager import shutdown_manager
from app.services.websocket_manager import ws_manager, OrderFillEvent
from app.trading_client import TradingClient
from app.trading_engine.fill_reconciler import reconcile_order_fill
from app.trading_engine.order_logger import log_order_to_history, OrderLogEntry

logger = logging.getLogger(__name__)


async def _validate_and_reject(
    db: AsyncSession,
    bot: Bot,
    product_id: str,
    position: Position,
    quote_amount: float,
    current_price: float,
    trade_type: str,
    commit_on_error: bool,
    exchange: ExchangeClient,
) -> None:
    """
    Validate order meets minimum size requirements and reject if invalid.

    Logs the failed order to history, records error on position (for DCA orders),
    and raises ValueError if validation fails.

    Args:
        db: Database session
        bot: Bot instance
        product_id: Trading pair
        position: Current position
        quote_amount: Amount of quote currency to spend
        current_price: Current market price
        trade_type: Order type identifier
        commit_on_error: Whether to commit errors to DB
        exchange: Exchange client for validation

    Raises:
        ValueError: If order does not meet minimum size requirements
    """
    is_valid, error_msg = await validate_order_size(exchange, product_id, quote_amount=quote_amount)

    if not is_valid:
        logger.warning(f"Order validation failed: {error_msg}")

        # Log failed order to history
        await log_order_to_history(
            db=db, bot=bot, position=position,
            entry=OrderLogEntry(
                product_id=product_id, side="BUY", order_type="MARKET",
                trade_type=trade_type, quote_amount=quote_amount,
                price=current_price, status="failed", error_message=error_msg,
            ),
        )

        # Save error to position for UI display (only for DCA orders)
        if commit_on_error:
            position.last_error_message = error_msg
            position.last_error_timestamp = datetime.utcnow()
            await db.commit()
        raise ValueError(error_msg)


async def _reconcile_buy_fill(
    exchange: ExchangeClient,
    order_id: str,
    product_id: str,
) -> tuple:
    """
    Fetch actual fill data from exchange with retry logic.

    Uses the shared fill reconciler with BTC fee adjustment and precision
    rounding enabled (specific to buy orders).

    Args:
        exchange: Exchange client instance
        order_id: The exchange order ID to check
        product_id: Trading pair

    Returns:
        Tuple of (actual_base_amount, actual_quote_amount, actual_price)
    """
    logger.info(f"Fetching order details for order_id: {order_id}")

    fill_data = await reconcile_order_fill(
        exchange=exchange,
        order_id=order_id,
        product_id=product_id,
        max_retries=10,
        adjust_btc_fees=True,
        round_base_to_precision=True,
    )

    return fill_data.filled_size, fill_data.filled_value, fill_data.average_price


async def _create_buy_trade_record(
    db: AsyncSession,
    position: Position,
    order_id: str,
    actual_base_amount: float,
    actual_quote_amount: float,
    actual_price: float,
    trade_type: str,
    signal_data: Optional[Dict[str, Any]],
) -> Trade:
    """
    Create Trade record and update Position with actual filled amounts.

    Clears previous errors, updates position totals, assigns deal number
    on first successful trade, and commits immediately.

    Args:
        db: Database session
        position: Current position to update
        order_id: Exchange order ID
        actual_base_amount: Actual base currency filled
        actual_quote_amount: Actual quote currency filled
        actual_price: Actual average fill price
        trade_type: Order type identifier
        signal_data: Optional signal metadata

    Returns:
        Committed Trade record
    """
    trade = Trade(
        position_id=position.id,
        timestamp=datetime.utcnow(),
        side="buy",
        quote_amount=actual_quote_amount,
        base_amount=actual_base_amount,
        price=actual_price,
        trade_type=trade_type,
        order_id=order_id,
        macd_value=signal_data.get("macd_value") if signal_data else None,
        macd_signal=signal_data.get("macd_signal") if signal_data else None,
        macd_histogram=signal_data.get("macd_histogram") if signal_data else None,
    )

    db.add(trade)

    # Clear any previous errors on successful trade
    position.last_error_message = None
    position.last_error_timestamp = None

    # Update position totals with ACTUAL filled amounts
    position.total_quote_spent += actual_quote_amount
    position.total_base_acquired += actual_base_amount
    # Update average buy price manually (don't use update_averages() - it triggers lazy loading)
    if position.total_base_acquired > 0:
        position.average_buy_price = position.total_quote_spent / position.total_base_acquired
    else:
        position.average_buy_price = 0.0

    # Assign deal number on FIRST successful trade (base order success)
    # This ensures only successfully opened positions get deal numbers
    if position.user_deal_number is None and position.user_id:
        from app.trading_engine.position_manager import get_next_user_deal_number
        position.user_deal_number = await get_next_user_deal_number(db, position.user_id)
        logger.info(f"  Assigned deal #{position.user_deal_number} (attempt #{position.user_attempt_number})")

    # CRITICAL: Commit trade and position update IMMEDIATELY
    # This ensures we never lose a trade record even if subsequent operations fail
    await db.commit()
    await db.refresh(trade)

    return trade


async def _post_buy_operations(
    db: AsyncSession,
    exchange: ExchangeClient,
    trading_client: TradingClient,
    bot: Bot,
    product_id: str,
    position: Position,
    order_id: str,
    actual_base_amount: float,
    actual_quote_amount: float,
    actual_price: float,
    trade_type: str,
) -> None:
    """
    Non-critical post-buy operations: logging, WebSocket notifications, cache invalidation.

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
        actual_base_amount: Actual base currency filled
        actual_quote_amount: Actual quote currency filled
        actual_price: Actual average fill price
        trade_type: Order type identifier
    """
    # Log successful order to history (best-effort)
    try:
        await log_order_to_history(
            db=db, bot=bot, position=position,
            entry=OrderLogEntry(
                product_id=product_id, side="BUY", order_type="MARKET",
                trade_type=trade_type, quote_amount=actual_quote_amount,
                price=actual_price, status="success",
                order_id=order_id, base_amount=actual_base_amount,
            ),
        )
    except Exception as e:
        logger.warning(f"Failed to log order to history (trade was recorded): {e}")

    # Broadcast order fill notification via WebSocket (best-effort)
    try:
        fill_type = "base_order" if trade_type == "initial" else "dca_order"
        is_paper = (hasattr(exchange, 'is_paper_trading')
                    and callable(exchange.is_paper_trading)
                    and exchange.is_paper_trading())
        await ws_manager.broadcast_order_fill(OrderFillEvent(
            fill_type=fill_type,
            product_id=product_id,
            base_amount=actual_base_amount,
            quote_amount=actual_quote_amount,
            price=actual_price,
            position_id=position.id,
            user_id=position.user_id,
            is_paper_trading=is_paper,
        ))
    except Exception as e:
        logger.warning(f"Failed to broadcast WebSocket notification (trade was recorded): {e}")

    # Invalidate balance cache after trade (best-effort)
    try:
        await trading_client.invalidate_balance_cache()
    except Exception as e:
        logger.warning(f"Failed to invalidate balance cache (trade was recorded): {e}")


async def execute_buy(
    db: AsyncSession,
    exchange: ExchangeClient,
    trading_client: TradingClient,
    bot: Bot,
    product_id: str,
    position: Position,
    quote_amount: float,
    current_price: float,
    trade_type: str,
    signal_data: Optional[Dict[str, Any]] = None,
    commit_on_error: bool = True,
) -> Optional[Trade]:
    """
    Execute a buy order (market or limit based on configuration)

    For safety orders, checks position's strategy_config_snapshot for safety_order_type.
    If "limit", places a limit order instead of executing immediately.

    Args:
        db: Database session
        exchange: Exchange client instance (CEX or DEX)
        trading_client: TradingClient instance
        bot: Bot instance
        product_id: Trading pair (e.g., 'ETH-BTC')
        position: Current position
        quote_amount: Amount of quote currency to spend (BTC or USD)
        current_price: Current market price
        trade_type: 'initial' or 'dca' or strategy-specific type
        signal_data: Optional signal metadata
        commit_on_error: If True, commit errors to DB (for DCA orders).
                       If False, don't commit errors (for base orders - let rollback work)

    Returns:
        Trade record (for market orders only; limit orders return None)
    """
    quote_currency = get_quote_currency(product_id)

    # Check if shutdown is in progress - reject new orders
    if shutdown_manager.is_shutting_down:
        logger.warning(f"Rejecting order for {product_id} - shutdown in progress")
        raise RuntimeError("Cannot place orders - shutdown in progress")

    config: Dict = position.strategy_config_snapshot or {}

    # Check if this is a base order that should use limit orders
    is_base_order = trade_type == "initial"
    if is_base_order and config.get("base_execution_type") == "limit":
        limit_price = current_price
        logger.info(f"  Placing limit base buy: {quote_amount:.8f} {quote_currency} @ {limit_price:.8f}")
        _pending_order = await execute_limit_buy(  # noqa: F841
            db=db,
            exchange=exchange,
            trading_client=trading_client,
            bot=bot,
            product_id=product_id,
            position=position,
            quote_amount=quote_amount,
            limit_price=limit_price,
            trade_type=trade_type,
            signal_data=signal_data,
        )
        return None

    # Check if this is a safety order that should use limit orders
    is_safety_order = trade_type.startswith("safety_order")
    dca_execution_type = config.get("dca_execution_type", "market")

    if is_safety_order and dca_execution_type == "limit":
        limit_price = current_price
        logger.info(f"  Placing limit DCA buy: {quote_amount:.8f} {quote_currency} @ {limit_price:.8f}")
        _pending_order = await execute_limit_buy(  # noqa: F841
            db=db,
            exchange=exchange,
            trading_client=trading_client,
            bot=bot,
            product_id=product_id,
            position=position,
            quote_amount=quote_amount,
            limit_price=limit_price,
            trade_type=trade_type,
            signal_data=signal_data,
        )
        return None

    # Execute market order (immediate execution)
    # Validate order meets minimum size requirements
    await _validate_and_reject(
        db=db,
        bot=bot,
        product_id=product_id,
        position=position,
        quote_amount=quote_amount,
        current_price=current_price,
        trade_type=trade_type,
        commit_on_error=commit_on_error,
        exchange=exchange,
    )

    # Execute order via TradingClient (currency-agnostic)
    # Actual fill amounts will be fetched from exchange after order executes
    # Track this as an in-flight order for graceful shutdown
    order_id = None
    await shutdown_manager.increment_in_flight()
    try:
        order_response = await trading_client.buy(product_id=product_id, quote_amount=quote_amount)

        # Check for PropGuard safety block before normal error handling
        if order_response.get("blocked_by") == "propguard":
            error_msg = f"PropGuard blocked: {order_response.get('error', 'Safety check failed')}"
            logger.warning(f"  PropGuard blocked buy order for {product_id}: {error_msg}")
            await log_order_to_history(
                db=db, bot=bot, position=position,
                entry=OrderLogEntry(
                    product_id=product_id, side="BUY", order_type="MARKET",
                    trade_type=trade_type, quote_amount=quote_amount,
                    price=current_price, status="failed", error_message=error_msg,
                ),
            )
            if commit_on_error:
                position.last_error_message = error_msg
                position.last_error_timestamp = datetime.utcnow()
                await db.commit()
            raise ValueError(error_msg)

        success_response = order_response.get("success_response", {})
        error_response = order_response.get("error_response", {})
        order_id = success_response.get("order_id", "")

        # CRITICAL: Validate order_id is present
        if not order_id:
            # Log the full exchange response to understand why order failed
            logger.error(f"Exchange order failed - Full response: {order_response}")

            # Save error to position for UI display
            if error_response:
                # Try multiple possible error field names from exchange
                error_msg = error_response.get("message") or error_response.get("error") or "Unknown error"
                error_details = error_response.get("error_details", "")
                failure_reason = error_response.get("failure_reason", "")
                preview_failure_reason = error_response.get("preview_failure_reason", "")

                # Build comprehensive error message
                error_parts = [error_msg]
                if error_details:
                    error_parts.append(error_details)
                if failure_reason:
                    error_parts.append(f"Reason: {failure_reason}")
                if preview_failure_reason:
                    error_parts.append(f"Preview: {preview_failure_reason}")

                full_error = " - ".join(error_parts)

                # If still no useful error, show the entire error_response as JSON
                if full_error == "Unknown error":
                    import json

                    full_error = f"Exchange error: {json.dumps(error_response)}"

                logger.error(f"Exchange error details: {full_error}")
            else:
                full_error = "No order_id returned from exchange (no error_response provided)"

            # Log failed order to history
            await log_order_to_history(
                db=db, bot=bot, position=position,
                entry=OrderLogEntry(
                    product_id=product_id, side="BUY", order_type="MARKET",
                    trade_type=trade_type, quote_amount=quote_amount,
                    price=current_price, status="failed", error_message=full_error,
                ),
            )

            # Record error on position (only for DCA orders)
            if commit_on_error:
                position.last_error_message = full_error
                position.last_error_timestamp = datetime.utcnow()
                await db.commit()

            raise ValueError(f"Exchange order failed: {full_error}")

        # Fetch actual fill data from exchange with retry logic
        actual_base_amount, actual_quote_amount, actual_price = await _reconcile_buy_fill(
            exchange=exchange,
            order_id=order_id,
            product_id=product_id,
        )

        # Final validation check
        if actual_base_amount == 0 or actual_quote_amount == 0:
            logger.error(
                f"WARNING: Order {order_id} has zero fill amounts after all retries! "
                f"Position #{position.id} will show 0% filled. "
                f"Manual fix required using scripts/fix_position.py"
            )

    except Exception as e:
        logger.error(f"Error executing buy order: {e}")

        # Log failed order to history (only if not already logged)
        # ValueError exceptions were already logged above, so skip those
        if not isinstance(e, ValueError):
            await log_order_to_history(
                db=db, bot=bot, position=position,
                entry=OrderLogEntry(
                    product_id=product_id, side="BUY", order_type="MARKET",
                    trade_type=trade_type, quote_amount=quote_amount,
                    price=current_price, status="failed", error_message=str(e),
                ),
            )

        # Record error on position for UI display and commit order history
        if position:
            if not position.last_error_message:
                position.last_error_message = str(e)
                position.last_error_timestamp = datetime.utcnow()
            try:
                await db.commit()
            except Exception:
                pass  # Don't mask the original error
        raise

    finally:
        await shutdown_manager.decrement_in_flight()

    # Record trade with ACTUAL filled amounts from exchange
    trade = await _create_buy_trade_record(
        db=db,
        position=position,
        order_id=order_id,
        actual_base_amount=actual_base_amount,
        actual_quote_amount=actual_quote_amount,
        actual_price=actual_price,
        trade_type=trade_type,
        signal_data=signal_data,
    )

    # === NON-CRITICAL OPERATIONS BELOW ===
    # These can fail without losing the trade record
    await _post_buy_operations(
        db=db,
        exchange=exchange,
        trading_client=trading_client,
        bot=bot,
        product_id=product_id,
        position=position,
        order_id=order_id,
        actual_base_amount=actual_base_amount,
        actual_quote_amount=actual_quote_amount,
        actual_price=actual_price,
        trade_type=trade_type,
    )

    return trade


async def execute_limit_buy(
    db: AsyncSession,
    exchange: ExchangeClient,
    trading_client: TradingClient,
    bot: Bot,
    product_id: str,
    position: Position,
    quote_amount: float,
    limit_price: float,
    trade_type: str,
    signal_data: Optional[Dict[str, Any]] = None,
) -> PendingOrder:
    """
    Place a limit buy order and track it in pending_orders table

    Args:
        db: Database session
        exchange: Exchange client instance (CEX or DEX)
        trading_client: TradingClient instance
        bot: Bot instance
        product_id: Trading pair (e.g., 'ETH-BTC')
        position: Current position
        quote_amount: Amount of quote currency to spend (BTC or USD)
        limit_price: Target price for the limit order
        trade_type: 'safety_order_1', 'safety_order_2', etc.
        signal_data: Optional signal metadata

    Returns:
        PendingOrder record
    """
    quote_currency = get_quote_currency(product_id)

    # Calculate base amount at limit price
    base_amount = quote_amount / limit_price

    # Place limit order via TradingClient
    order_id = None
    try:
        order_response = await trading_client.buy_limit(
            product_id=product_id, limit_price=limit_price, quote_amount=quote_amount
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
        logger.error(f"Error placing limit buy order: {e}")
        raise

    # Create PendingOrder record
    pending_order = PendingOrder(
        position_id=position.id,
        bot_id=bot.id,
        order_id=order_id,
        product_id=product_id,
        side="BUY",
        order_type="LIMIT",
        limit_price=limit_price,
        quote_amount=quote_amount,
        base_amount=base_amount,
        trade_type=trade_type,
        status="pending",
        created_at=datetime.utcnow(),
    )

    db.add(pending_order)
    await db.commit()
    await db.refresh(pending_order)

    logger.info(
        f"Placed limit buy order: {quote_amount:.8f} {quote_currency} @ {limit_price:.8f} (Order ID: {order_id})"
    )

    return pending_order


async def execute_buy_close_short(
    db: AsyncSession,
    exchange: ExchangeClient,
    trading_client: TradingClient,
    bot: Bot,
    product_id: str,
    position: Position,
    current_price: float,
    signal_data: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[Trade], float, float]:
    """
    Execute a buy order to CLOSE a SHORT position (bidirectional DCA)

    For short positions:
    - We sold BTC at short_average_sell_price
    - We need to buy it back now at current_price
    - Profit if current_price < short_average_sell_price (bought back cheaper)
    - Loss if current_price > short_average_sell_price (bought back more expensive)

    Args:
        db: Database session
        exchange: Exchange client instance (CEX or DEX)
        trading_client: TradingClient instance
        bot: Bot instance
        product_id: Trading pair (e.g., 'BTC-USD')
        position: Current short position to close
        current_price: Current market price
        signal_data: Optional signal metadata

    Returns:
        Tuple of (trade, profit_quote, profit_percentage)
    """
    quote_currency = get_quote_currency(product_id)

    # Check if shutdown is in progress - reject new orders
    if shutdown_manager.is_shutting_down:
        logger.warning(f"Rejecting close-short buy order for {product_id} - shutdown in progress")
        raise RuntimeError("Cannot place orders - shutdown in progress")

    # For short positions, we need to buy back the BTC we sold
    btc_to_buy_back = position.short_total_sold_base or 0.0

    if btc_to_buy_back <= 0:
        raise ValueError(
            f"Position #{position.id} has no BTC to buy back "
            f"(short_total_sold_base = {btc_to_buy_back})"
        )

    # Calculate how much USD we need to buy back the BTC
    quote_amount_needed = btc_to_buy_back * current_price

    logger.info(
        f"  CLOSING SHORT: Buying back {btc_to_buy_back:.8f} BTC "
        f"@ ${current_price:.2f} (need ${quote_amount_needed:.2f})"
    )

    # Check if we should use a limit order for closing
    config: Dict = position.strategy_config_snapshot or {}
    take_profit_order_type = config.get("take_profit_order_type", "limit")

    if take_profit_order_type == "limit":
        # TODO: Short close currently uses market orders only; limit close not yet implemented
        logger.warning("  Limit close orders for shorts not yet implemented - using market order")

    # Execute market buy order to close short
    logger.info(f"  Executing MARKET close (buy back) @ {current_price:.8f}")

    # Execute order via TradingClient
    order_id = None
    await shutdown_manager.increment_in_flight()
    try:
        order_response = await trading_client.buy(product_id=product_id, quote_amount=quote_amount_needed)

        # Check for PropGuard safety block
        if order_response.get("blocked_by") == "propguard":
            raise ValueError(
                f"PropGuard blocked: {order_response.get('error', 'Safety check failed')}"
            )

        success_response = order_response.get("success_response", {})
        error_response = order_response.get("error_response", {})
        order_id = success_response.get("order_id", "")

        if not order_id:
            logger.error(f"Exchange close-short buy failed - Full response: {order_response}")
            if error_response:
                error_msg = error_response.get("message", "Unknown error")
                error_details = error_response.get("error_details", "")
                raise ValueError(f"Close-short buy failed: {error_msg}. Details: {error_details}")
            else:
                raise ValueError(f"Close-short buy failed. Full response: {order_response}")

    except Exception as e:
        logger.error(f"Error executing close-short buy order: {e}")
        raise
    finally:
        await shutdown_manager.decrement_in_flight()

    # Fetch actual fill data from exchange
    logger.info(f"Fetching order details for close-short order_id: {order_id}")
    max_retries = 10
    retry_delay = 3.0  # seconds
    filled_size = None
    average_filled_price = None

    for attempt in range(max_retries):
        try:
            order_details = await trading_client.get_order(order_id)
            filled_size = float(order_details.get("filled_size", 0))
            average_filled_price = float(order_details.get("average_filled_price", 0))

            if filled_size > 0 and average_filled_price > 0:
                logger.info(f"Order filled: {filled_size:.8f} BTC @ ${average_filled_price:.8f}")
                break

            if attempt < max_retries - 1:
                logger.warning(
                    f"Order {order_id} not fully filled yet "
                    f"(attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s..."
                )
                await asyncio.sleep(retry_delay)

        except Exception as e:
            logger.error(
                f"Error fetching order details (attempt {attempt + 1}/{max_retries}): {e}"
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)

    if not filled_size or not average_filled_price:
        raise ValueError(f"Failed to fetch fill data for order {order_id} after {max_retries} attempts")

    # Calculate profit for short position
    # Profit = (average sell price - buy back price) * BTC amount
    # We received short_total_sold_quote USD when we sold
    # We spent filled_size * average_filled_price USD to buy back
    usd_spent_to_close = filled_size * average_filled_price
    usd_received_from_short = position.short_total_sold_quote or 0.0

    profit_quote = usd_received_from_short - usd_spent_to_close
    profit_percentage = (profit_quote / usd_received_from_short) * 100 if usd_received_from_short > 0 else 0.0

    logger.info(
        f"  SHORT CLOSED: Sold @ avg ${position.short_average_sell_price:.2f}, "
        f"bought back @ ${average_filled_price:.2f}"
    )
    logger.info(f"  P&L: ${profit_quote:.2f} ({profit_percentage:.2f}%)")

    # Get BTC/USD price for USD profit tracking
    try:
        btc_usd_price_at_close = await exchange.get_btc_usd_price()
        if quote_currency == "BTC":
            profit_usd = profit_quote * btc_usd_price_at_close
        else:
            profit_usd = profit_quote
    except Exception:
        btc_usd_price_at_close = None
        profit_usd = profit_quote if quote_currency == "USD" else None

    # Create Trade record for closing short
    trade = Trade(
        position_id=position.id,
        timestamp=datetime.utcnow(),
        side="buy",  # Buying back BTC to close short
        base_amount=filled_size,  # Base currency bought back
        quote_amount=usd_spent_to_close,  # Quote currency spent
        price=average_filled_price,  # Average buy-back price
        trade_type="close_short",
        order_id=order_id,
    )

    db.add(trade)

    # Close position and record profit
    position.status = "closed"
    position.closed_at = datetime.utcnow()
    position.profit_quote = profit_quote
    position.profit_percentage = profit_percentage
    position.profit_usd = profit_usd

    await db.commit()
    await db.refresh(trade)

    # Log to order history (best-effort)
    try:
        await log_order_to_history(
            db=db, bot=bot, position=position,
            entry=OrderLogEntry(
                product_id=product_id, side="BUY", order_type="MARKET",
                trade_type="close_short", quote_amount=usd_spent_to_close,
                price=average_filled_price, status="success",
                order_id=order_id, base_amount=filled_size,
            ),
        )
    except Exception as e:
        logger.warning(f"Failed to log close-short to history: {e}")

    # Broadcast short close notification via WebSocket (best-effort)
    try:
        is_paper = (hasattr(exchange, 'is_paper_trading')
                    and callable(exchange.is_paper_trading)
                    and exchange.is_paper_trading())
        await ws_manager.broadcast_order_fill(OrderFillEvent(
            fill_type="close_short",
            product_id=product_id,
            base_amount=filled_size,
            quote_amount=usd_spent_to_close,
            price=average_filled_price,
            position_id=position.id,
            profit=profit_quote,
            profit_percentage=profit_percentage,
            user_id=position.user_id,
            is_paper_trading=is_paper,
        ))
    except Exception as e:
        logger.warning(f"Failed to broadcast short close WebSocket notification: {e}")

    logger.info(f"  SHORT POSITION CLOSED: Profit ${profit_quote:.2f} ({profit_percentage:.2f}%)")

    return trade, profit_quote, profit_percentage
