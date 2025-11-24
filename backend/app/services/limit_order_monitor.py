"""
Limit Order Monitoring Service

Monitors pending limit orders and updates positions when they fill.
Runs as a background task to check order status periodically.
"""

import asyncio
import logging
from datetime import datetime
from typing import List
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Position, PendingOrder, Trade
from app.coinbase_unified_client import CoinbaseUnifiedClient

logger = logging.getLogger(__name__)


class LimitOrderMonitor:
    """Monitors limit orders and processes fills"""

    def __init__(self, db: AsyncSession, coinbase_client: CoinbaseUnifiedClient):
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

        except Exception as e:
            logger.error(f"Error checking limit order for position {position.id}: {e}")

    async def _process_partial_fills(self, position: Position, pending_order: PendingOrder, order_data: dict):
        """Process partial fills for a limit order"""
        try:
            # Extract fill information from order data
            filled_size = float(order_data.get("filled_size", 0))
            filled_value = float(order_data.get("filled_value", 0))

            if filled_size > 0:
                # Update pending order with fill information
                pending_order.filled_base_amount = filled_size
                pending_order.filled_quote_amount = filled_value
                pending_order.remaining_base_amount = pending_order.base_amount - filled_size

                # Calculate average fill price
                if filled_size > 0:
                    pending_order.filled_price = filled_value / filled_size

                # Update status to partially_filled if not fully filled
                if filled_size < pending_order.base_amount:
                    pending_order.status = "partially_filled"
                    logger.info(
                        f"Position {position.id} limit order partially filled: {filled_size}/{pending_order.base_amount}"
                    )

                await self.db.commit()

        except Exception as e:
            logger.error(f"Error processing partial fills for position {position.id}: {e}")
            await self.db.rollback()

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

                # Create sell trade record
                trade = Trade(
                    position_id=position.id,
                    timestamp=datetime.utcnow(),
                    side="sell",
                    quote_amount=filled_value,
                    base_amount=filled_size,
                    price=avg_fill_price,
                    trade_type="limit_close",
                    order_id=position.limit_close_order_id,
                )
                self.db.add(trade)

                # Close the position
                position.status = "closed"
                position.closed_at = datetime.utcnow()
                position.sell_price = avg_fill_price
                position.total_quote_received = filled_value
                position.profit_quote = filled_value - position.total_quote_spent
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


async def run_limit_order_monitor(db: AsyncSession, coinbase_client: CoinbaseUnifiedClient):
    """Main loop for limit order monitoring"""
    monitor = LimitOrderMonitor(db, coinbase_client)

    while True:
        try:
            await monitor.check_limit_close_orders()
        except Exception as e:
            logger.error(f"Error in limit order monitor loop: {e}")

        # Check every 30 seconds
        await asyncio.sleep(30)
