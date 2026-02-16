"""
Limit Order Monitoring Service

Monitors pending limit orders and updates positions when they fill.
Runs as a background task to check order status periodically.

Exchange-agnostic: works with any ExchangeClient implementation
(Coinbase, ByBit, MT5, PropGuard wrapper).
"""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exchange_clients.base import ExchangeClient
from app.models import Position, PendingOrder, Trade
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)


class LimitOrderMonitor:
    """Monitors limit orders and processes fills"""

    def __init__(self, db: AsyncSession, exchange: ExchangeClient):
        self.db = db
        self.exchange = exchange

    async def startup_reconciliation(self):
        """
        Reconcile all pending limit orders on startup.

        Checks ALL positions with limit_close_order_id set (even if closing_via_limit is False)
        to catch any orders that filled during downtime or got orphaned due to flag sync issues.
        """
        try:
            # Get all open positions with a limit_close_order_id (regardless of closing_via_limit flag)
            # This catches both active limit orders AND orphaned orders where the flag wasn't set
            query = select(Position).where(
                Position.status == "open",
                Position.limit_close_order_id.isnot(None)
            )
            result = await self.db.execute(query)
            positions = result.scalars().all()

            if not positions:
                logger.info("✅ Startup reconciliation: No pending limit orders to check")
                return

            logger.info(f"🔄 Startup reconciliation: Checking {len(positions)} positions with limit order IDs")

            for position in positions:
                # Ensure closing_via_limit flag is set (fix orphaned orders)
                if not position.closing_via_limit:
                    logger.warning(
                        f"⚠️ Position {position.id} has limit_close_order_id but closing_via_limit is False. "
                        f"Fixing flag and checking order status..."
                    )
                    position.closing_via_limit = True

                await self.check_single_position_limit_order(position)

            await self.db.commit()
            logger.info(f"✅ Startup reconciliation complete: Checked {len(positions)} orders")

        except Exception as e:
            logger.error(f"❌ Error in startup reconciliation: {e}")
            await self.db.rollback()

    async def check_limit_close_orders(self):
        """Check all pending limit close orders for fills"""
        try:
            # Get all positions with pending limit close orders
            query = select(Position).where(Position.closing_via_limit, Position.status == "open")
            result = await self.db.execute(query)
            positions = result.scalars().all()

            logger.info(f"Checking {len(positions)} positions with pending limit close orders")

            for position in positions:
                await self.check_single_position_limit_order(position)

        except Exception as e:
            logger.error(f"Error checking limit close orders: {e}")

    async def check_single_position_limit_order(self, position: Position):
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

            # Fetch order status from exchange
            order_data = await self.exchange.get_order(position.limit_close_order_id)

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

                    # Broadcast partial fill notification
                    await ws_manager.broadcast_order_fill(
                        fill_type="partial_fill",
                        product_id=position.product_id,
                        base_amount=new_fill_size,
                        quote_amount=new_fill_value,
                        price=avg_fill_price,
                        position_id=position.id,
                    )

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

        IMPORTANT: Manual orders (is_manual=True) are NEVER auto-adjusted.
        User's GTC/GTD preference must be honored.
        """
        try:
            # CRITICAL: Skip bid fallback for manual orders
            # Manual orders are placed by user through UI - respect their time_in_force choice
            if pending_order.is_manual:
                logger.debug(
                    f"Position {position.id}: Skipping bid fallback for manual order "
                    f"(time_in_force={pending_order.time_in_force})"
                )
                return
            # Get bot configuration for timeout and profit threshold
            from app.models import Bot
            from sqlalchemy import select

            bot_query = select(Bot).where(Bot.id == position.bot_id)
            bot_result = await self.db.execute(bot_query)
            bot = bot_result.scalars().first()

            if not bot:
                return

            # Get config parameters - use POSITION's frozen config for profit threshold
            # This ensures we respect the min_profit_for_conditions that was set when position opened
            bot_config = bot.strategy_config or {}
            position_config = position.strategy_config_snapshot or {}

            fallback_enabled = bot_config.get("limit_order_fallback_enabled", True)
            timeout_seconds = bot_config.get("limit_order_timeout_seconds", 60)

            # CRITICAL: Use min_profit_for_conditions from position's frozen config
            # This prevents selling below the profit threshold the user set
            min_profit_threshold_pct = position_config.get("min_profit_for_conditions")
            if min_profit_threshold_pct is None:
                # Fall back to take_profit_percentage, then bot's min_profit_threshold_pct, then default
                min_profit_threshold_pct = position_config.get(
                    "take_profit_percentage",
                    bot_config.get("min_profit_threshold_pct", 0.5)
                )

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
            ticker = await self.exchange.get_ticker(position.product_id)
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

            # Profit threshold met - adjust limit order price to bid
            logger.info(
                f"🔄 Position {position.id}: Adjusting limit order price "
                f"from {pending_order.limit_price:.8f} to bid {best_bid:.8f}"
            )

            try:
                # Format bid price with product-specific precision
                from app.product_precision import format_quote_amount_for_product
                formatted_bid = format_quote_amount_for_product(best_bid, position.product_id)

                try:
                    # Try native edit_order API (atomic, preserves queue position)
                    edit_result = await self.exchange.edit_order(
                        order_id=pending_order.order_id,
                        price=formatted_bid
                    )

                    # Check if edit was successful
                    if edit_result.get("error_response"):
                        error_response = edit_result.get("error_response", {})
                        error_msg = error_response.get("message", "Unknown error")
                        raise Exception(f"Edit order failed: {error_msg}")

                    logger.info(
                        f"✅ Position {position.id}: Order price edited to bid "
                        f"{best_bid:.8f} (Order ID: {pending_order.order_id})"
                    )

                    # Update pending order with new price (same order_id)
                    pending_order.limit_price = best_bid
                    pending_order.created_at = datetime.utcnow()
                    await self.db.commit()

                except NotImplementedError:
                    # Exchange doesn't support edit — cancel + new order
                    logger.info(
                        f"Position {position.id}: Exchange doesn't support "
                        f"edit_order, using cancel+replace"
                    )
                    await self._cancel_and_replace_order(
                        position, pending_order, formatted_bid, best_bid
                    )

                logger.info(
                    f"🎉 Position {position.id}: Successfully adjusted to "
                    f"bid price - should fill quickly"
                )

            except Exception as e:
                logger.error(f"❌ Position {position.id}: Failed to adjust limit order: {e}")
                logger.warning(
                    f"⚠️ Position {position.id}: Order remains at original price {pending_order.limit_price:.8f}"
                )
                # Order is still valid at original price, so don't mark as failed
                # Just log the error and continue monitoring
                await self.db.rollback()
                return

        except Exception as e:
            logger.error(f"Error in bid fallback check for position {position.id}: {e}")

    async def _cancel_and_replace_order(
        self,
        position: Position,
        pending_order: PendingOrder,
        formatted_bid: str,
        best_bid: float,
    ):
        """Cancel existing order and place a new one at the bid price.

        Used as fallback when the exchange doesn't support edit_order().

        Handles edge cases:
        - If the cancelled order filled between our last check and
          cancel, we detect it and skip replacement.
        - If the replacement order fails, we clear closing_via_limit
          so the position returns to normal monitoring on the next
          cycle (or after restart).
        - Uses pending_order remaining amount, not position total,
          to handle partially-filled orders correctly.
        """
        old_order_id = pending_order.order_id

        # Cancel the old order
        cancel_result = await self.exchange.cancel_order(old_order_id)
        if not cancel_result.get("success", False):
            raise Exception(
                f"Cancel failed: {cancel_result.get('error', 'unknown')}"
            )

        # Check if the cancelled order filled between our last check
        # and the cancel. This prevents double-selling.
        try:
            cancelled_order = await self.exchange.get_order(old_order_id)
            if cancelled_order:
                filled_size = float(
                    cancelled_order.get("filled_size", "0")
                )
                if filled_size > 0:
                    status = cancelled_order.get("status", "")
                    if status == "FILLED":
                        logger.info(
                            f"Position {position.id}: Cancelled order "
                            f"was actually FILLED — processing as fill"
                        )
                        await self._process_order_completion(
                            position, pending_order,
                            cancelled_order, "FILLED"
                        )
                        return
                    # Partial fill on cancel — update pending_order
                    # and use remaining amount for replacement
                    filled_value = float(
                        cancelled_order.get("filled_value", "0")
                    )
                    avg_price = (
                        filled_value / filled_size
                        if filled_size > 0 else 0
                    )
                    await self._process_partial_fills(
                        position, pending_order, cancelled_order
                    )
                    logger.info(
                        f"Position {position.id}: Cancelled order had "
                        f"partial fill: {filled_size} @ {avg_price:.8f}"
                    )
        except Exception as e:
            logger.warning(
                f"Position {position.id}: Could not check "
                f"cancelled order fill state: {e}"
            )

        # Use remaining amount (handles partial fills correctly)
        remaining = pending_order.remaining_base_amount
        if remaining is None or remaining <= 0:
            remaining = pending_order.base_amount or (
                position.total_base_acquired
            )

        # Place new limit sell at bid price
        try:
            new_order_resp = await self.exchange.create_limit_order(
                product_id=position.product_id,
                side="SELL",
                limit_price=float(formatted_bid),
                size=str(remaining),
            )
        except Exception as replace_err:
            # Replacement failed — clear closing flags so the
            # position re-enters normal monitoring.  On restart,
            # startup_reconciliation will find it has no order_id
            # and will leave it as a normal open position.
            logger.error(
                f"Position {position.id}: Replacement order "
                f"failed: {replace_err} — clearing limit close "
                f"flags for re-evaluation"
            )
            position.closing_via_limit = False
            position.limit_close_order_id = None
            pending_order.status = "cancelled"
            pending_order.canceled_at = datetime.utcnow()
            await self.db.commit()
            raise

        # Extract new order_id
        success_resp = new_order_resp.get("success_response", {})
        new_order_id = (
            success_resp.get("order_id", "")
            or new_order_resp.get("order_id", "")
        )

        if not new_order_id:
            # No order_id — same recovery as replacement failure
            position.closing_via_limit = False
            position.limit_close_order_id = None
            pending_order.status = "cancelled"
            pending_order.canceled_at = datetime.utcnow()
            await self.db.commit()
            raise Exception("No order_id in replacement order response")

        # Update tracking
        pending_order.order_id = new_order_id
        pending_order.limit_price = best_bid
        pending_order.created_at = datetime.utcnow()
        pending_order.status = "pending"
        position.limit_close_order_id = new_order_id

        await self.db.commit()
        logger.info(
            f"✅ Position {position.id}: Replaced order with "
            f"new order {new_order_id} @ {best_bid:.8f} "
            f"(size: {remaining})"
        )

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
                    btc_usd_price = await self.exchange.get_btc_usd_price()
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

                # Broadcast sell order fill notification
                await ws_manager.broadcast_order_fill(
                    fill_type="sell_order",
                    product_id=position.product_id,
                    base_amount=filled_size,
                    quote_amount=filled_value,
                    price=avg_fill_price,
                    position_id=position.id,
                    profit=position.profit_quote,
                    profit_percentage=position.profit_percentage,
                )

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


async def run_limit_order_monitor(db: AsyncSession, exchange: ExchangeClient):
    """Main loop for limit order monitoring"""
    monitor = LimitOrderMonitor(db, exchange)

    # Run startup reconciliation to catch orders that filled during downtime
    logger.info("🚀 Starting limit order monitor with startup reconciliation...")
    await monitor.startup_reconciliation()

    while True:
        try:
            await monitor.check_limit_close_orders()
        except Exception as e:
            logger.error(f"Error in limit order monitor loop: {e}")

        # Check every 10 seconds (fast response without hitting rate limits)
        await asyncio.sleep(10)
