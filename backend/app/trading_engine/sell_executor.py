"""
Sell order execution for trading engine
Handles market and limit sell orders
"""

import asyncio
import logging
import math
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.currency_utils import get_quote_currency
from app.exchange_clients.base import ExchangeClient
from app.models import Bot, PendingOrder, Position, Trade
from app.product_precision import get_base_precision
from app.services.shutdown_manager import shutdown_manager
from app.services.websocket_manager import ws_manager
from app.trading_client import TradingClient
from app.trading_engine.order_logger import log_order_to_history

logger = logging.getLogger(__name__)


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

    # Check if this is a safety order that should use limit orders
    is_safety_order = trade_type.startswith("safety_order")
    config: Dict = position.strategy_config_snapshot or {}
    safety_order_type = config.get("safety_order_type", "market")

    if is_safety_order and safety_order_type == "limit":
        # Place limit sell order for short safety order
        limit_price = current_price

        logger.info(f"  📋 Placing limit short sell order: {base_amount:.8f} BTC @ {limit_price:.8f}")

        # TODO: Short safety orders use market orders only; limit logic not yet implemented
        # For now, fall through to market order
        logger.warning("  ⚠️ Limit short safety orders not yet implemented - using market order")

    # Execute market sell order (immediate execution)
    logger.info(f"  💱 Executing SHORT SELL: {base_amount:.8f} BTC @ {current_price:.8f}")

    # Round base_amount down to proper precision (floor to avoid INSUFFICIENT_FUND)
    precision = get_base_precision(product_id)
    base_amount_rounded = math.floor(base_amount * (10 ** precision)) / (10 ** precision)

    # Validate order size meets exchange minimums
    is_valid, error_msg = await validate_order_size(
        exchange, product_id, base_amount=base_amount_rounded
    )
    if not is_valid:
        error = f"Order validation failed: {error_msg}"
        logger.error(f"  ❌ {error}")
        if commit_on_error:
            position.last_error_message = error
            position.last_error_timestamp = datetime.utcnow()
            await db.commit()
        raise ValueError(error)

    # Execute order via TradingClient
    order_id = None
    await shutdown_manager.increment_in_flight()
    try:
        order_response = await trading_client.sell(product_id=product_id, base_amount=base_amount_rounded)

        logger.info(f"Exchange short sell order response: {order_response}")

        # Check for PropGuard safety block
        if order_response.get("blocked_by") == "propguard":
            raise ValueError(
                f"PropGuard blocked: {order_response.get('error', 'Safety check failed')}"
            )

        # Check success flag
        if not order_response.get("success", False):
            error_response = order_response.get("error_response", {})
            if error_response:
                error_msg = error_response.get("message", "Unknown error")
                error_details = error_response.get("error_details", "")
                error_code = error_response.get("error", "UNKNOWN")
                raise ValueError(f"Short sell failed [{error_code}]: {error_msg}. Details: {error_details}")
            else:
                raise ValueError(f"Short sell failed. Full response: {order_response}")

        # Extract order_id
        success_response = order_response.get("success_response", {})
        order_id = success_response.get("order_id", "") or order_response.get("order_id", "")

        if not order_id:
            logger.error(f"Full exchange response: {order_response}")
            raise ValueError("No order_id in successful exchange response")

        # Fetch actual fill data from exchange with retry
        logger.info(f"Fetching fill data for short sell order {order_id}")
        actual_base_sold = base_amount_rounded
        quote_received = base_amount_rounded * current_price
        actual_price = current_price

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

                if filled_size > 0 and filled_value > 0:
                    actual_base_sold = filled_size
                    quote_received = filled_value
                    actual_price = avg_price if avg_price > 0 else current_price
                    logger.info(
                        f"Short sell filled: {actual_base_sold:.8f} @ "
                        f"{actual_price:.8f} = {quote_received:.2f}"
                    )
                    break

                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries}: "
                    f"Short sell not yet filled"
                )
            except Exception as fill_err:
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries}: "
                    f"Failed to get fill data: {fill_err}"
                )

            if attempt == max_retries - 1:
                logger.warning(
                    f"Could not fetch fill data for {order_id} after "
                    f"{max_retries} attempts. Using estimates."
                )

    except Exception as e:
        logger.error(f"Error executing short sell order: {e}")
        if commit_on_error:
            position.last_error_message = f"Short sell failed: {str(e)}"
            position.last_error_timestamp = datetime.utcnow()
            await db.commit()
        raise
    finally:
        await shutdown_manager.decrement_in_flight()

    # Create Trade record using actual fill data
    trade = Trade(
        position_id=position.id,
        timestamp=datetime.utcnow(),
        side="sell",  # Selling BTC to open/add to short
        base_amount=actual_base_sold,  # Base currency sold (actual)
        quote_amount=quote_received,  # Quote currency received (actual)
        price=actual_price,  # Execution price (actual)
        trade_type=trade_type,
        order_id=order_id,
    )

    db.add(trade)

    # Update position's short tracking fields
    is_first_short = position.short_entry_price is None

    if is_first_short:
        # First short order - initialize fields
        position.short_entry_price = actual_price
        position.short_average_sell_price = actual_price
        position.short_total_sold_base = actual_base_sold
        position.short_total_sold_quote = quote_received
        logger.info(
            f"  SHORT POSITION OPENED: Entry={actual_price:.8f}, "
            f"BTC sold={actual_base_sold:.8f}, USD received={quote_received:.2f}"
        )
    else:
        # Adding to existing short position (safety order)
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

    # Log to order history (best-effort)
    try:
        await log_order_to_history(
            db=db,
            bot=bot,
            product_id=product_id,
            position=position,
            side="SELL",
            order_type="MARKET",
            trade_type=trade_type,
            quote_amount=quote_received,
            price=actual_price,
            status="success",
            order_id=order_id,
            base_amount=actual_base_sold,
        )
    except Exception as e:
        logger.warning(f"Failed to log short sell to history: {e}")

    # Send WebSocket update
    await ws_manager.broadcast_position_update(position)

    logger.info(
        f"  SHORT SELL EXECUTED: {actual_base_sold:.8f} BTC @ {actual_price:.8f} "
        f"= ${quote_received:.2f} (Order: {order_id})"
    )

    return trade


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
        created_at=datetime.utcnow(),
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
        f"✅ Placed limit sell order: {base_amount:.8f} {base_currency} @ {limit_price:.8f} (Order ID: {order_id})"
    )

    return pending_order


async def execute_sell(
    db: AsyncSession,
    exchange: ExchangeClient,
    trading_client: TradingClient,
    bot: Bot,
    product_id: str,
    position: Position,
    current_price: float,
    signal_data: Optional[Dict[str, Any]] = None,
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
    quote_currency = get_quote_currency(product_id)

    # Check if shutdown is in progress - reject new orders
    if shutdown_manager.is_shutting_down:
        logger.warning(f"Rejecting sell order for {product_id} - shutdown in progress")
        raise RuntimeError("Cannot place orders - shutdown in progress")

    # CRITICAL: Prevent duplicate limit sell orders
    # If position is already closing via limit order, don't place another one
    if position.closing_via_limit:
        logger.warning(
            f"⚠️ Position #{position.id} already has a pending limit close order "
            f"(order_id: {position.limit_close_order_id}). Skipping duplicate sell."
        )
        return None, 0.0, 0.0

    # Check if we should use a limit order for closing
    config: Dict = position.strategy_config_snapshot or {}
    take_profit_order_type = config.get("take_profit_order_type", "limit")

    if take_profit_order_type == "limit":
        # Use limit order at mark price (mid between bid/ask)
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

            logger.info(f"  📊 Placing LIMIT close order @ {limit_price:.8f} (mark price)")

            # Place limit order and return - position stays open until filled
            # Limit order placed; fill tracking handled by limit_order_monitor service
            _pending_order = await execute_limit_sell(  # noqa: F841
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
            return None, 0.0, 0.0

        except Exception as e:
            logger.warning(f"Failed to place limit close order: {e}. Checking if market order is viable...")

            # SAFETY CHECK: Re-validate profit before falling back to market order
            # If price dropped significantly during the limit order attempt, abort instead of selling below target
            current_value = position.total_base_acquired * current_price
            profit_amount = current_value - position.total_quote_spent
            profit_pct = (profit_amount / position.total_quote_spent) * 100

            # Get minimum profit threshold from config
            # Use same logic as should_sell() to determine minimum profit requirement
            min_profit_override = config.get("min_profit_for_conditions")
            if min_profit_override is not None:
                min_profit = min_profit_override
            else:
                min_profit = config.get("take_profit_percentage", 3.0)

            if profit_pct < min_profit:
                logger.warning(
                    f"⚠️ Aborting market order fallback - current profit {profit_pct:.2f}% is below "
                    f"minimum target {min_profit:.2f}%. Will retry on next check cycle."
                )
                return None, 0.0, 0.0

            logger.info(
                f"✅ Market order fallback approved - current profit {profit_pct:.2f}% >= "
                f"minimum {min_profit:.2f}%. Proceeding with market order."
            )
            # Fall through to market order execution below

    # Execute market order (default behavior or fallback)
    logger.info(f"  💱 Executing MARKET close order @ {current_price:.8f}")

    # Round base_amount down to proper precision (floor to avoid INSUFFICIENT_FUND)
    precision = get_base_precision(product_id)
    base_amount = math.floor(position.total_base_acquired * (10 ** precision)) / (10 ** precision)

    logger.info(
        f"  💰 Selling {base_amount:.8f} {product_id.split('-')[0]} "
        f"(raw: {position.total_base_acquired:.8f}, precision: {precision} decimals)"
    )

    # Execute order via TradingClient (currency-agnostic)
    # Track this as an in-flight order for graceful shutdown
    order_id = None
    actual_base_sold = base_amount
    actual_price = current_price
    quote_received = base_amount * current_price

    await shutdown_manager.increment_in_flight()
    try:
        order_response = await trading_client.sell(product_id=product_id, base_amount=base_amount)

        # Log the full response for debugging
        logger.info(f"Exchange sell order response: {order_response}")

        # Check for PropGuard safety block
        if order_response.get("blocked_by") == "propguard":
            raise ValueError(
                f"PropGuard blocked: {order_response.get('error', 'Safety check failed')}"
            )

        # Check success flag first
        if not order_response.get("success", False):
            # Order failed - check error response
            error_response = order_response.get("error_response", {})
            if error_response:
                error_msg = error_response.get("message", "Unknown error")
                error_details = error_response.get("error_details", "")
                error_code = error_response.get("error", "UNKNOWN")
                raise ValueError(f"Sell order failed [{error_code}]: {error_msg}. Details: {error_details}")
            else:
                raise ValueError(f"Sell order failed with no error details. Full response: {order_response}")

        # Extract order_id from success_response (documented format)
        success_response = order_response.get("success_response", {})
        order_id = success_response.get("order_id", "")

        # Fallback: try top-level order_id
        if not order_id:
            order_id = order_response.get("order_id", "")

        # CRITICAL: Validate order_id is present
        if not order_id:
            logger.error(f"Full exchange response: {order_response}")
            raise ValueError(
                f"No order_id found in successful exchange response. Response keys: {list(order_response.keys())}"
            )

        # Fetch actual fill data from exchange with retry
        logger.info(f"Fetching fill data for sell order {order_id}")
        max_retries = 10
        for attempt in range(max_retries):
            if attempt > 0:
                delay = min(0.5 * (2 ** (attempt - 1)), 5.0)
                await asyncio.sleep(delay)

            try:
                order_details = await exchange.get_order(order_id)
                filled_size = float(order_details.get("filled_size", "0"))
                filled_value = float(order_details.get("filled_value", "0"))
                avg_price = float(
                    order_details.get("average_filled_price", "0")
                )

                if filled_size > 0 and filled_value > 0:
                    actual_base_sold = filled_size
                    quote_received = filled_value
                    actual_price = avg_price if avg_price > 0 else current_price
                    logger.info(
                        f"Sell order filled: {actual_base_sold:.8f} @ "
                        f"{actual_price:.8f} = {quote_received:.8f}"
                    )
                    break

                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries}: "
                    f"Sell order not yet filled"
                )
            except Exception as fill_err:
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries}: "
                    f"Failed to get fill data: {fill_err}"
                )

            if attempt == max_retries - 1:
                logger.warning(
                    f"Could not fetch fill data for {order_id} after "
                    f"{max_retries} attempts. Using estimate: "
                    f"{base_amount} @ {current_price}"
                )

    except Exception as e:
        logger.error(f"Error executing sell order: {e}")

        # Record error on position for UI visibility
        try:
            position.last_error_message = f"Sell failed: {str(e)[:200]}"
            position.last_error_timestamp = datetime.utcnow()
            await db.commit()
        except Exception:
            pass  # Don't mask the original error

        # Log failed sell to order history (best-effort)
        try:
            await log_order_to_history(
                db=db,
                bot=bot,
                product_id=product_id,
                position=position,
                side="SELL",
                order_type="MARKET",
                trade_type="sell",
                quote_amount=base_amount * current_price,
                price=current_price,
                status="failed",
                error_message=str(e)[:200],
            )
        except Exception:
            pass

        raise

    finally:
        await shutdown_manager.decrement_in_flight()

    # Calculate profit using actual fill data
    profit_quote = quote_received - position.total_quote_spent
    profit_percentage = (profit_quote / position.total_quote_spent) * 100

    # Get BTC/USD price for USD profit tracking
    try:
        btc_usd_price_at_close = await exchange.get_btc_usd_price()
        # Convert profit to USD if quote is BTC
        if quote_currency == "BTC":
            profit_usd = profit_quote * btc_usd_price_at_close
        else:  # quote is USD
            profit_usd = profit_quote
    except Exception:
        btc_usd_price_at_close = None
        profit_usd = None

    # Record trade with actual fill data
    trade = Trade(
        position_id=position.id,
        timestamp=datetime.utcnow(),
        side="sell",
        quote_amount=quote_received,
        base_amount=actual_base_sold,
        price=actual_price,
        trade_type="sell",
        order_id=order_id,
        macd_value=signal_data.get("macd_value") if signal_data else None,
        macd_signal=signal_data.get("macd_signal") if signal_data else None,
        macd_histogram=signal_data.get("macd_histogram") if signal_data else None,
    )

    db.add(trade)

    # Close position using actual fill data
    position.status = "closed"
    position.closed_at = datetime.utcnow()
    position.sell_price = actual_price
    position.total_quote_received = quote_received
    position.profit_quote = profit_quote
    position.profit_percentage = profit_percentage
    position.btc_usd_price_at_close = btc_usd_price_at_close
    position.profit_usd = profit_usd

    # CRITICAL: Commit trade and position close IMMEDIATELY
    # This ensures we never lose a sell record even if subsequent operations fail
    await db.commit()
    await db.refresh(trade)

    # === NON-CRITICAL OPERATIONS BELOW ===
    # These can fail without losing the trade record

    # Log successful sell to order history (best-effort)
    try:
        await log_order_to_history(
            db=db,
            bot=bot,
            product_id=product_id,
            position=position,
            side="SELL",
            order_type="MARKET",
            trade_type="sell",
            quote_amount=quote_received,
            price=actual_price,
            status="success",
            order_id=order_id,
            base_amount=actual_base_sold,
        )
    except Exception as e:
        logger.warning(f"Failed to log sell order to history (trade was recorded): {e}")

    # Broadcast sell order fill notification via WebSocket (best-effort)
    try:
        await ws_manager.broadcast_order_fill(
            fill_type="sell_order",
            product_id=product_id,
            base_amount=actual_base_sold,
            quote_amount=quote_received,
            price=actual_price,
            position_id=position.id,
            profit=profit_quote,
            profit_percentage=profit_percentage,
        )
    except Exception as e:
        logger.warning(f"Failed to broadcast WebSocket notification (trade was recorded): {e}")

    # Invalidate balance cache after trade (best-effort)
    try:
        await trading_client.invalidate_balance_cache()
    except Exception as e:
        logger.warning(f"Failed to invalidate balance cache (trade was recorded): {e}")

    # Trigger immediate re-analysis to find replacement position (best-effort)
    # By resetting last_signal_check, the bot will run on the next monitor cycle
    # This is like 3Commas - when a deal closes, immediately look for new opportunities
    try:
        logger.info("🔄 Position closed - triggering immediate re-analysis to find replacement")
        bot.last_signal_check = None
        await db.commit()
    except Exception as e:
        logger.warning(f"Failed to trigger re-analysis (trade was recorded): {e}")

    return trade, profit_quote, profit_percentage
