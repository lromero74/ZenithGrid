"""
Limit Order Monitoring Service

Monitors pending limit orders and updates positions when they fill.
Runs as a background task to check order status periodically.
"""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Position, PendingOrder, Trade
from app.coinbase_unified_client import CoinbaseClient

logger = logging.getLogger(__name__)


class LimitOrderMonitor:
    """Monitors limit orders and processes fills"""

    def __init__(self, db: AsyncSession, coinbase_client: CoinbaseClient):
        self.db = db
        self.coinbase = coinbase_client

    async def check_limit_close_orders(self):
        """Check all pending limit close orders for fills"""
        try:
            # Get all positions with pending limit close orders
            query = select(Position).where(Position.closing_via_limit, Position.status == "open")
            result = await self.db.execute(query)
            positions = result.scalars().all()

            logger.info(f"Checking {len(positions)} positions with pending limit close orders")

            for position in positions:
                await self._check_position_limit_order(position)

        except Exception as e:
            logger.error(f"Error checking limit close orders: {e}")

    async def _check_position_limit_order(self, position: Position):
        """Check a single position's limit order status"""
        try:
            if not position.limit_close_order_id:
                logger.warning(f"Position {position.id} marked as closing_via_limit but has no order ID")
                return

            # Get the pending order record
            pending_order_query = select(PendingOrder).where(PendingOrder.order_id == position.limit_close_order_id)
            pending_order_result = await self.db.execute(pending_order_query)
            pending_order = pending_order_result.scalars().first()

            if not pending_order:
                logger.warning(
                    f"No pending order found for position {position.id}, order ID {position.limit_close_order_id}"
                )
                return

            # Fetch order status from Coinbase
            order_data = await self.coinbase.get_order(position.limit_close_order_id)

            if not order_data:
                logger.warning(f"Could not fetch order data for {position.limit_close_order_id}")
                return

            order_status = order_data.get("status", "UNKNOWN")
            logger.info(f"Position {position.id} limit order {position.limit_close_order_id} status: {order_status}")

            # Handle different order statuses
            if order_status in ["FILLED", "CANCELLED", "EXPIRED", "FAILED"]:
                await self._process_order_completion(position, pending_order, order_data, order_status)
            elif order_status in ["OPEN", "PENDING"]:
                # Check for partial fills
                await self._process_partial_fills(position, pending_order, order_data)

                # Check if order has been pending too long and should fallback to bid
                await self._check_bid_fallback(position, pending_order, order_data)

        except Exception as e:
            logger.error(f"Error checking limit order for position {position.id}: {e}")

    async def _process_partial_fills(self, position: Position, pending_order: PendingOrder, order_data: dict):
        """Process partial fills for a limit order"""
        try:
            # Extract fill information from order data
            filled_size = float(order_data.get("filled_size", 0))
            filled_value = float(order_data.get("filled_value", 0))

            if filled_size > 0:
                # Check if there are NEW fills since last check
                previous_filled = pending_order.filled_base_amount or 0
                new_fill_size = filled_size - previous_filled

                if new_fill_size > 0:
                    # Calculate new fill value (proportional to new fill size)
                    avg_fill_price = filled_value / filled_size if filled_size > 0 else 0
                    new_fill_value = new_fill_size * avg_fill_price

                    logger.info(
                        f"Position {position.id} NEW partial fill detected: "
                        f"{new_fill_size} @ {avg_fill_price} BTC "
                        f"(total filled: {filled_size}/{pending_order.base_amount})"
                    )

                    # Create sell trade for the NEW partial fill
                    trade = Trade(
                        position_id=position.id,
                        timestamp=datetime.utcnow(),
                        side="sell",
                        quote_amount=new_fill_value,
                        base_amount=new_fill_size,
                        price=avg_fill_price,
                        trade_type="limit_close_partial",
                        order_id=position.limit_close_order_id,
                    )
                    self.db.add(trade)

                    # Update position totals (reduce remaining base, add quote received)
                    if not position.total_quote_received:
                        position.total_quote_received = 0
                    position.total_quote_received += new_fill_value

                    # Recalculate profit based on what's been sold so far
                    position.profit_quote = position.total_quote_received - position.total_quote_spent
                    position.profit_percentage = (
                        (position.profit_quote / position.total_quote_spent * 100)
                        if position.total_quote_spent > 0 else 0
                    )

                # Update pending order with current fill information
                pending_order.filled_base_amount = filled_size
                pending_order.filled_quote_amount = filled_value
                pending_order.remaining_base_amount = pending_order.base_amount - filled_size
                pending_order.filled_price = filled_value / filled_size if filled_size > 0 else 0

                # Update status to partially_filled if not fully filled
                if filled_size < pending_order.base_amount:
                    pending_order.status = "partially_filled"
                    logger.info(
                        f"Position {position.id} partial fill status: "
                        f"{filled_size}/{pending_order.base_amount} filled, "
                        f"{pending_order.remaining_base_amount} remaining"
                    )

                await self.db.commit()

        except Exception as e:
            logger.error(f"Error processing partial fills for position {position.id}: {e}")
            await self.db.rollback()

    async def _check_bid_fallback(self, position: Position, pending_order: PendingOrder, order_data: dict):
        """
        Check if limit order has been pending too long and should fall back to bid price

        If order has been open for > 60 seconds without filling, cancel and replace
        at bid price (more aggressive) if bid still meets profit threshold.
        """
        try:
            # Get bot configuration for timeout and profit threshold
            from app.models import Bot
            from sqlalchemy import select

            bot_query = select(Bot).where(Bot.id == position.bot_id)
            bot_result = await self.db.execute(bot_query)
            bot = bot_result.scalars().first()

            if not bot:
                return

            # Get config parameters with defaults
            config = bot.strategy_config or {}
            fallback_enabled = config.get("limit_order_fallback_enabled", True)
            timeout_seconds = config.get("limit_order_timeout_seconds", 60)
            min_profit_threshold_pct = config.get("min_profit_threshold_pct", 0.5)

            if not fallback_enabled:
                return

            # Check if order has been pending long enough
            time_elapsed = (datetime.utcnow() - pending_order.created_at).total_seconds()
            if time_elapsed < timeout_seconds:
                return  # Not yet time to fallback

            # Check if already partially filled (don't adjust if partially filled)
            filled_size = float(order_data.get("filled_size", 0))
            if filled_size > 0:
                logger.info(f"Position {position.id}: Order partially filled ({filled_size}), skipping bid fallback")
                return

            logger.info(
                f"⏰ Position {position.id}: Limit order pending for {time_elapsed:.0f}s "
                f"(threshold: {timeout_seconds}s) - checking bid price..."
            )

            # Get current ticker for bid price
            ticker = await self.coinbase.get_ticker(position.product_id)
            best_bid = float(ticker.get("best_bid", 0))

            if best_bid <= 0:
                logger.warning(f"Position {position.id}: No valid bid price available")
                return

            # Calculate profit at bid price
            btc_received_at_bid = position.total_base_acquired * best_bid
            btc_profit = btc_received_at_bid - position.total_quote_spent
            profit_pct = (btc_profit / position.total_quote_spent) * 100 if position.total_quote_spent > 0 else 0

            logger.info(
                f"📊 Position {position.id}: Current bid: {best_bid:.8f} "
                f"(profit: {profit_pct:.2f}% vs threshold: {min_profit_threshold_pct}%)"
            )

            # Check if bid price still meets profit threshold
            if profit_pct < min_profit_threshold_pct:
                logger.info(
                    f"⏳ Position {position.id}: Bid price profit ({profit_pct:.2f}%) "
                    f"below threshold ({min_profit_threshold_pct}%) - keeping mark order"
                )
                return

            # Profit threshold met - cancel old order and place new one at bid
            logger.info(
                f"🔄 Position {position.id}: Cancelling mark order, placing new limit @ bid price {best_bid:.8f}"
            )

            # Cancel old order
            from app.trading_client import TradingClient
            trading_client = TradingClient(self.coinbase)

            try:
                cancel_result = await trading_client.cancel_order(pending_order.order_id)
                logger.info(f"✅ Position {position.id}: Old order cancelled successfully")
            except Exception as e:
                logger.error(f"❌ Position {position.id}: Failed to cancel old order: {e}")
                return

            # Place new limit order at bid price
            try:
                import math
                from app.product_precision import get_base_precision

                # Round base amount to proper precision
                precision = get_base_precision(position.product_id)
                base_amount_rounded = math.floor(position.total_base_acquired * (10 ** precision)) / (10 ** precision)

                new_order_response = await trading_client.sell_limit(
                    product_id=position.product_id,
                    limit_price=best_bid,
                    base_amount=base_amount_rounded
                )

                if not new_order_response.get("success", False):
                    raise ValueError(f"Order placement failed: {new_order_response.get('error_response')}")

                new_order_id = new_order_response.get("success_response", {}).get("order_id")
                if not new_order_id:
                    raise ValueError("No order_id in response")

                logger.info(f"✅ Position {position.id}: New limit order placed @ bid {best_bid:.8f} (Order ID: {new_order_id})")

                # Update pending order record with new details
                pending_order.order_id = new_order_id
                pending_order.limit_price = best_bid
                pending_order.status = "pending"
                pending_order.created_at = datetime.utcnow()  # Reset timer for new order

                # Update position's limit_close_order_id
                position.limit_close_order_id = new_order_id

                await self.db.commit()

                logger.info(f"🎉 Position {position.id}: Successfully adjusted to bid price - should fill immediately")

            except Exception as e:
                logger.error(f"❌ Position {position.id}: Failed to place new limit order: {e}")
                # Position is now in limbo - old order cancelled but new order failed
                # Reset closing_via_limit flag so user can manually intervene
                position.closing_via_limit = False
                position.limit_close_order_id = None
                pending_order.status = "failed"
                await self.db.commit()
                return

        except Exception as e:
            logger.error(f"Error in bid fallback check for position {position.id}: {e}")

    async def _process_order_completion(
        self, position: Position, pending_order: PendingOrder, order_data: dict, order_status: str
    ):
        """Process completed (filled/cancelled/expired) limit order"""
        try:
            if order_status == "FILLED":
                # Order fully filled - close the position
                filled_size = float(order_data.get("filled_size", 0))
                filled_value = float(order_data.get("filled_value", 0))
                avg_fill_price = filled_value / filled_size if filled_size > 0 else 0

                logger.info(f"Position {position.id} limit order FILLED at avg price {avg_fill_price}")

                # Check if there are NEW fills since last partial fill check
                previous_filled = pending_order.filled_base_amount or 0
                new_fill_size = filled_size - previous_filled

                if new_fill_size > 0:
                    # There's a final partial fill that hasn't been recorded yet
                    new_fill_value = new_fill_size * avg_fill_price

                    logger.info(
                        f"Position {position.id} FINAL fill: {new_fill_size} @ {avg_fill_price} BTC "
                        f"(completing full {filled_size})"
                    )

                    # Create sell trade for the final partial fill
                    trade = Trade(
                        position_id=position.id,
                        timestamp=datetime.utcnow(),
                        side="sell",
                        quote_amount=new_fill_value,
                        base_amount=new_fill_size,
                        price=avg_fill_price,
                        trade_type="limit_close_final",
                        order_id=position.limit_close_order_id,
                    )
                    self.db.add(trade)

                    # Update position totals with final fill
                    if not position.total_quote_received:
                        position.total_quote_received = 0
                    position.total_quote_received += new_fill_value

                # Close the position
                position.status = "closed"
                position.closed_at = datetime.utcnow()
                position.sell_price = avg_fill_price

                # Use accumulated total_quote_received (includes partial fills)
                # If no partial fills occurred, this will be set to filled_value
                if not position.total_quote_received:
                    position.total_quote_received = filled_value

                position.profit_quote = position.total_quote_received - position.total_quote_spent
                position.profit_percentage = (
                    (position.profit_quote / position.total_quote_spent * 100) if position.total_quote_spent > 0 else 0
                )

                # Calculate USD profit if BTC pair
                quote_currency = position.get_quote_currency()
                if quote_currency == "BTC":
                    btc_usd_price = await self.coinbase.get_btc_usd_price()
                    position.btc_usd_price_at_close = btc_usd_price
                    position.profit_usd = position.profit_quote * btc_usd_price

                # Update pending order
                pending_order.status = "filled"
                pending_order.filled_at = datetime.utcnow()
                pending_order.filled_base_amount = filled_size
                pending_order.filled_quote_amount = filled_value
                pending_order.filled_price = avg_fill_price
                pending_order.remaining_base_amount = 0

                # Clear limit close flags
                position.closing_via_limit = False
                position.limit_close_order_id = None

                # Return reserved balance to bot if position has a bot
                if position.bot_id:
                    from app.models import Bot

                    bot_query = select(Bot).where(Bot.id == position.bot_id)
                    bot_result = await self.db.execute(bot_query)
                    bot = bot_result.scalars().first()

                    if bot:
                        quote_currency = position.get_quote_currency()
                        if quote_currency == "BTC":
                            bot.reserved_btc_balance = max(0, bot.reserved_btc_balance - position.initial_quote_balance)
                        else:
                            bot.reserved_usd_balance = max(0, bot.reserved_usd_balance - position.initial_quote_balance)

                await self.db.commit()
                logger.info(f"Position {position.id} closed successfully via limit order")

            elif order_status in ["CANCELLED", "EXPIRED", "FAILED"]:
                # Order cancelled/expired - reset position flags
                logger.info(f"Position {position.id} limit order {order_status}")

                pending_order.status = order_status.lower()
                if order_status == "CANCELLED":
                    pending_order.canceled_at = datetime.utcnow()

                position.closing_via_limit = False
                position.limit_close_order_id = None

                await self.db.commit()

        except Exception as e:
            logger.error(f"Error processing order completion for position {position.id}: {e}")
            await self.db.rollback()


async def run_limit_order_monitor(db: AsyncSession, coinbase_client: CoinbaseClient):
    """Main loop for limit order monitoring"""
    monitor = LimitOrderMonitor(db, coinbase_client)

    while True:
        try:
            await monitor.check_limit_close_orders()
        except Exception as e:
            logger.error(f"Error in limit order monitor loop: {e}")

        # Check every 10 seconds (fast response without hitting rate limits)
        await asyncio.sleep(10)
