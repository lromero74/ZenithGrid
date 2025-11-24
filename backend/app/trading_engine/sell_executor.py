"""
Sell order execution for trading engine
Handles market and limit sell orders
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_unified_client import CoinbaseClient
from app.models import Bot, PendingOrder, Position, Trade
from app.trading_client import TradingClient
from app.currency_utils import get_quote_currency
from app.order_validation import get_product_minimums

logger = logging.getLogger(__name__)


async def execute_limit_sell(
    db: AsyncSession,
    coinbase: CoinbaseClient,
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
        coinbase: CoinbaseClient instance
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
    # Round base_amount to proper precision using product precision data
    minimums = await get_product_minimums(coinbase, product_id)
    base_increment = Decimal(minimums.get('base_increment', '0.00000001'))
    base_decimal = Decimal(str(base_amount))

    # Floor division to round down to nearest increment (avoid INSUFFICIENT_FUND)
    rounded_base = (base_decimal // base_increment) * base_increment
    base_amount_rounded = float(rounded_base)

    logger.info(
        f"Limit sell precision: raw={base_amount:.8f}, "
        f"increment={base_increment}, rounded={base_amount_rounded:.8f}"
    )

    # Calculate expected quote amount at limit price
    expected_quote_amount = base_amount_rounded * limit_price

    # Place limit order via TradingClient
    order_id = None
    try:
        order_response = await trading_client.sell_limit(
            product_id=product_id, limit_price=limit_price, base_amount=base_amount_rounded
        )
        success_response = order_response.get("success_response", {})
        order_id = success_response.get("order_id", "")

        if not order_id:
            raise ValueError("No order_id returned from Coinbase")

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
    coinbase: CoinbaseClient,
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
        coinbase: CoinbaseClient instance
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

    # Check if we should use a limit order for closing
    config: Dict = position.strategy_config_snapshot or {}
    take_profit_order_type = config.get("take_profit_order_type", "limit")

    if take_profit_order_type == "limit":
        # Use limit order at mark price (mid between bid/ask)
        try:
            # Get ticker to calculate mark price
            ticker = await coinbase.get_ticker(product_id)
            best_bid = float(ticker.get("best_bid", 0))
            best_ask = float(ticker.get("best_ask", 0))

            # Use mark price (mid-point) as limit price
            if best_bid > 0 and best_ask > 0:
                limit_price = (best_bid + best_ask) / 2
            else:
                # Fallback to current price if bid/ask not available
                limit_price = current_price

            # Sell 99% to prevent precision/rounding rejections
            base_amount = position.total_base_acquired * 0.99

            logger.info(f"  📊 Placing LIMIT close order @ {limit_price:.8f} (mark price)")

            # Place limit order and return - position stays open until filled
            # TODO: pending_order is currently unused but reserved for future limit order tracking/monitoring
            pending_order = await execute_limit_sell(
                db=db,
                coinbase=coinbase,
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
            logger.warning(f"Failed to place limit close order: {e}. Falling back to market order.")
            # Fall through to market order execution below

    # Execute market order (default behavior or fallback)
    logger.info(f"  💱 Executing MARKET close order @ {current_price:.8f}")

    # Sell 99% to prevent precision/rounding rejections from Coinbase
    # Leaves 1% "dust" amount but ensures sell executes successfully
    # The 1% dust can be cleaned up later
    # Using 0.99 instead of 0.9999 because our tracked amounts may be slightly
    # higher than actual Coinbase balances due to calculation vs actual fills
    base_amount = position.total_base_acquired * 0.99
    quote_received = base_amount * current_price

    # Log the dust amount
    dust_amount = position.total_base_acquired - base_amount
    logger.info(f"  💰 Selling {base_amount:.8f} {product_id.split('-')[0]} (leaving {dust_amount:.8f} dust)")

    # Execute order via TradingClient (currency-agnostic)
    order_id = None
    try:
        order_response = await trading_client.sell(product_id=product_id, base_amount=base_amount)

        # Log the full response for debugging
        logger.info(f"Coinbase sell order response: {order_response}")

        # Check success flag first
        if not order_response.get("success", False):
            # Order failed - check error response
            error_response = order_response.get("error_response", {})
            if error_response:
                error_msg = error_response.get("message", "Unknown error")
                error_details = error_response.get("error_details", "")
                error_code = error_response.get("error", "UNKNOWN")
                raise ValueError(f"Coinbase sell order failed [{error_code}]: {error_msg}. Details: {error_details}")
            else:
                raise ValueError(f"Coinbase sell order failed with no error details. Full response: {order_response}")

        # Extract order_id from success_response (documented format)
        success_response = order_response.get("success_response", {})
        order_id = success_response.get("order_id", "")

        # Fallback: try top-level order_id
        if not order_id:
            order_id = order_response.get("order_id", "")

        # CRITICAL: Validate order_id is present
        if not order_id:
            logger.error(f"Full Coinbase response: {order_response}")
            raise ValueError(
                f"No order_id found in successful Coinbase response. Response keys: {list(order_response.keys())}"
            )

    except Exception as e:
        logger.error(f"Error executing sell order: {e}")
        raise

    # Calculate profit
    profit_quote = quote_received - position.total_quote_spent
    profit_percentage = (profit_quote / position.total_quote_spent) * 100

    # Get BTC/USD price for USD profit tracking
    try:
        btc_usd_price_at_close = await coinbase.get_btc_usd_price()
        # Convert profit to USD if quote is BTC
        if quote_currency == "BTC":
            profit_usd = profit_quote * btc_usd_price_at_close
        else:  # quote is USD
            profit_usd = profit_quote
    except Exception:
        btc_usd_price_at_close = None
        profit_usd = None

    # Record trade
    trade = Trade(
        position_id=position.id,
        timestamp=datetime.utcnow(),
        side="sell",
        quote_amount=quote_received,
        base_amount=base_amount,
        price=current_price,
        trade_type="sell",
        order_id=order_id,
        macd_value=signal_data.get("macd_value") if signal_data else None,
        macd_signal=signal_data.get("macd_signal") if signal_data else None,
        macd_histogram=signal_data.get("macd_histogram") if signal_data else None,
    )

    db.add(trade)

    # Close position
    position.status = "closed"
    position.closed_at = datetime.utcnow()
    position.sell_price = current_price
    position.total_quote_received = quote_received
    position.profit_quote = profit_quote
    position.profit_percentage = profit_percentage
    position.btc_usd_price_at_close = btc_usd_price_at_close
    position.profit_usd = profit_usd

    await db.commit()
    await db.refresh(trade)

    # Invalidate balance cache after trade
    await trading_client.invalidate_balance_cache()

    # Trigger immediate re-analysis to find replacement position
    # By resetting last_signal_check, the bot will run on the next monitor cycle
    # This is like 3Commas - when a deal closes, immediately look for new opportunities
    logger.info("🔄 Position closed - triggering immediate re-analysis to find replacement")
    bot.last_signal_check = None
    await db.commit()

    return trade, profit_quote, profit_percentage
