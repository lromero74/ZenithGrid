"""
Buy order execution for trading engine
Handles market and limit buy orders
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.exchange_clients.base import ExchangeClient
from app.models import Bot, PendingOrder, Position, Trade
from app.trading_client import TradingClient
from app.order_validation import validate_order_size
from app.currency_utils import get_quote_currency
from app.trading_engine.order_logger import log_order_to_history
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)


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

    # Check if this is a safety order that should use limit orders
    is_safety_order = trade_type.startswith("safety_order")
    config: Dict = position.strategy_config_snapshot or {}
    safety_order_type = config.get("safety_order_type", "market")

    if is_safety_order and safety_order_type == "limit":
        # Place limit order instead of market order
        # Calculate limit price (use current price as-is for now)
        # Note: In the future, this could apply a discount or use strategy-specific logic
        limit_price = current_price

        logger.info(f"  📋 Placing limit buy order: {quote_amount:.8f} {quote_currency} @ {limit_price:.8f}")

        # TODO: pending_order is currently unused but reserved for future limit order tracking/monitoring
        pending_order = await execute_limit_buy(
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

        # Return None for limit orders (no Trade created yet)
        # The order monitoring service will create the Trade when filled
        return None

    # Execute market order (immediate execution)
    # Validate order meets minimum size requirements
    is_valid, error_msg = await validate_order_size(exchange, product_id, quote_amount=quote_amount)

    if not is_valid:
        logger.warning(f"Order validation failed: {error_msg}")

        # Log failed order to history
        await log_order_to_history(
            db=db,
            bot=bot,
            product_id=product_id,
            position=position,
            side="BUY",
            order_type="MARKET",
            trade_type=trade_type,
            quote_amount=quote_amount,
            price=current_price,
            status="failed",
            error_message=error_msg,
        )

        # Save error to position for UI display (only for DCA orders)
        if commit_on_error:
            position.last_error_message = error_msg
            position.last_error_timestamp = datetime.utcnow()
            await db.commit()
        raise ValueError(error_msg)

    # Execute order via TradingClient (currency-agnostic)
    # Actual fill amounts will be fetched from Coinbase after order executes
    order_id = None
    try:
        order_response = await trading_client.buy(product_id=product_id, quote_amount=quote_amount)
        success_response = order_response.get("success_response", {})
        error_response = order_response.get("error_response", {})
        order_id = success_response.get("order_id", "")

        # CRITICAL: Validate order_id is present
        if not order_id:
            # Log the full Coinbase response to understand why order failed
            logger.error(f"Coinbase order failed - Full response: {order_response}")

            # Save error to position for UI display (like 3Commas)
            if error_response:
                # Try multiple possible error field names from Coinbase
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

                    full_error = f"Coinbase error: {json.dumps(error_response)}"

                logger.error(f"Coinbase error details: {full_error}")
            else:
                full_error = "No order_id returned from Coinbase (no error_response provided)"

            # Log failed order to history
            await log_order_to_history(
                db=db,
                bot=bot,
                product_id=product_id,
                position=position,
                side="BUY",
                order_type="MARKET",
                trade_type=trade_type,
                quote_amount=quote_amount,
                price=current_price,
                status="failed",
                error_message=full_error,
            )

            # Record error on position (only for DCA orders)
            if commit_on_error:
                position.last_error_message = full_error
                position.last_error_timestamp = datetime.utcnow()
                await db.commit()

            raise ValueError(f"Coinbase order failed: {full_error}")

        # Fetch actual fill data from Coinbase with retry logic
        # Market orders can take time to fill on illiquid pairs - retry up to 10 times over ~30s
        logger.info(f"Fetching order details for order_id: {order_id}")

        actual_base_amount = 0.0
        actual_quote_amount = 0.0
        actual_price = 0.0

        max_retries = 10  # Increased from 5 to handle slow fills
        for attempt in range(max_retries):
            if attempt > 0:
                # Wait before retrying (exponential backoff: 0.5s, 1s, 2s, 4s, 8s, then 5s intervals)
                import asyncio

                if attempt < 5:
                    delay = 0.5 * (2 ** (attempt - 1))
                else:
                    delay = 5.0  # Cap at 5s for remaining attempts
                logger.info(f"Waiting {delay}s before retry {attempt + 1}/{max_retries}...")
                await asyncio.sleep(delay)

            order_details = await exchange.get_order(order_id)

            # get_order() already unwraps the "order" key - access fields directly
            # See app/coinbase_api/order_api.py:118-135
            filled_size_str = order_details.get("filled_size", "0")
            filled_value_str = order_details.get("filled_value", "0")
            avg_price_str = order_details.get("average_filled_price", "0")
            total_fees_str = order_details.get("total_fees", "0")

            # Convert to floats
            gross_base_amount = float(filled_size_str)
            actual_quote_amount = float(filled_value_str)
            actual_price = float(avg_price_str)
            total_fees = float(total_fees_str)

            # For BTC pair buy orders, fees are charged IN the base currency (the crypto you buy)
            # So filled_size is GROSS, and you actually receive filled_size - fee_in_base
            # For USD pairs, fees are charged in USD (quote currency), so filled_size is NET
            # Fee calculation: fee_in_base = total_fees_in_usd / avg_price
            # Or we can estimate: fee ~= gross_base * fee_rate (typically 0.5-0.8% for taker)
            #
            # Since total_fees is in USD, we need to convert to base currency for BTC pairs
            is_btc_pair = product_id.endswith("-BTC")
            if is_btc_pair and actual_price > 0 and total_fees > 0:
                # Fee is returned in USD, convert to base currency
                # fee_in_base = total_fees_usd / (base_price_in_usd)
                # base_price_in_usd = avg_btc_price * avg_price_btc_pair
                # For simplicity, estimate fee % from filled_value ratio
                # Coinbase Advanced Trade taker fee is ~0.5-0.8%
                # Net base = gross_base * (1 - fee_rate)
                # We can derive fee_rate = total_fees / filled_value
                if actual_quote_amount > 0:
                    fee_rate = total_fees / actual_quote_amount  # This gives us fee as % of trade
                    fee_in_base = gross_base_amount * fee_rate
                    actual_base_amount = gross_base_amount - fee_in_base
                    logger.info(
                        f"BTC pair fee adjustment: gross={gross_base_amount:.8f}, "
                        f"fee_rate={fee_rate:.4%}, fee_in_base={fee_in_base:.8f}, "
                        f"net={actual_base_amount:.8f}"
                    )
                else:
                    actual_base_amount = gross_base_amount
            else:
                actual_base_amount = gross_base_amount

            # Check if order has filled (non-zero amounts)
            if actual_base_amount > 0 and actual_quote_amount > 0:
                logger.info(
                    f"Order filled - Base: {actual_base_amount}, Quote: {actual_quote_amount}, Avg Price: {actual_price}"
                )
                break
            else:
                logger.warning(f"Attempt {attempt + 1}/{max_retries}: Order not yet filled (amounts still zero)")
                if attempt == max_retries - 1:
                    logger.error(
                        f"Order {order_id} did not fill after {max_retries} attempts (~30s) - recording with zero amounts. "
                        f"This position will need manual reconciliation."
                    )

        # Final validation check
        if actual_base_amount == 0 or actual_quote_amount == 0:
            logger.error(
                f"WARNING: Order {order_id} has zero fill amounts after all retries! "
                f"Position #{position.id} will show 0% filled. Manual fix required using scripts/fix_position.py"
            )

    except Exception as e:
        logger.error(f"Error executing buy order: {e}")

        # Log failed order to history (only if not already logged)
        # ValueError exceptions were already logged above, so skip those
        if not isinstance(e, ValueError):
            await log_order_to_history(
                db=db,
                bot=bot,
                product_id=product_id,
                position=position,
                side="BUY",
                order_type="MARKET",
                trade_type=trade_type,
                quote_amount=quote_amount,
                price=current_price,
                status="failed",
                error_message=str(e),
            )

        # Record error on position if it's not already recorded (only for DCA orders)
        if commit_on_error and position and not position.last_error_message:
            position.last_error_message = str(e)
            position.last_error_timestamp = datetime.utcnow()
            await db.commit()
        raise

    # Record trade with ACTUAL filled amounts from Coinbase
    trade = Trade(
        position_id=position.id,
        timestamp=datetime.utcnow(),
        side="buy",
        quote_amount=actual_quote_amount,  # Use actual filled value
        base_amount=actual_base_amount,  # Use actual filled size
        price=actual_price,  # Use actual average price
        trade_type=trade_type,
        order_id=order_id,
        macd_value=signal_data.get("macd_value") if signal_data else None,
        macd_signal=signal_data.get("macd_signal") if signal_data else None,
        macd_histogram=signal_data.get("macd_histogram") if signal_data else None,
    )

    db.add(trade)

    # Log successful order to history
    await log_order_to_history(
        db=db,
        bot=bot,
        product_id=product_id,
        position=position,
        side="BUY",
        order_type="MARKET",
        trade_type=trade_type,
        quote_amount=actual_quote_amount,
        price=actual_price,
        status="success",
        order_id=order_id,
        base_amount=actual_base_amount,
    )

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

    await db.commit()
    await db.refresh(trade)

    # Broadcast order fill notification via WebSocket
    # Determine fill type based on trade_type
    fill_type = "base_order" if trade_type == "initial" else "dca_order"
    await ws_manager.broadcast_order_fill(
        fill_type=fill_type,
        product_id=product_id,
        base_amount=actual_base_amount,
        quote_amount=actual_quote_amount,
        price=actual_price,
        position_id=position.id,
    )

    # Invalidate balance cache after trade
    await trading_client.invalidate_balance_cache()

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
        success_response = order_response.get("success_response", {})
        order_id = success_response.get("order_id", "")

        if not order_id:
            raise ValueError("No order_id returned from Coinbase")

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
        f"✅ Placed limit buy order: {quote_amount:.8f} {quote_currency} @ {limit_price:.8f} (Order ID: {order_id})"
    )

    return pending_order
