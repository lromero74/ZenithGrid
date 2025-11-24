"""
Order monitoring service

Periodically checks pending limit orders and creates trades when filled.
"""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_unified_client import CoinbaseClient
from app.database import get_db
from app.models import PendingOrder, Position, Trade

logger = logging.getLogger(__name__)


class OrderMonitor:
    """
    Background service to monitor pending limit orders

    Checks order status periodically and creates Trade records when filled.
    """

    def __init__(self, coinbase: CoinbaseClient, check_interval: int = 30):
        """
        Initialize order monitor

        Args:
            coinbase: CoinbaseClient instance
            check_interval: Seconds between checks (default: 30)
        """
        self.coinbase = coinbase
        self.check_interval = check_interval
        self.running = False
        self._task = None

    async def start(self):
        """Start the order monitoring service"""
        if self.running:
            logger.warning("Order monitor already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"📋 Order monitor started (check interval: {self.check_interval}s)")

    async def stop(self):
        """Stop the order monitoring service"""
        if not self.running:
            return

        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Order monitor stopped")

    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                await self._check_pending_orders()
            except Exception as e:
                logger.error(f"Error checking pending orders: {e}", exc_info=True)

            # Wait before next check
            await asyncio.sleep(self.check_interval)

    async def _check_pending_orders(self):
        """Check all pending orders and update their status"""
        async for db in get_db():
            try:
                # Get all pending orders
                query = select(PendingOrder).where(PendingOrder.status == "pending")
                result = await db.execute(query)
                pending_orders = result.scalars().all()

                if not pending_orders:
                    return

                logger.info(f"📋 Checking {len(pending_orders)} pending orders...")

                for order in pending_orders:
                    try:
                        await self._check_order(db, order)
                    except Exception as e:
                        logger.error(f"Error checking order {order.order_id}: {e}", exc_info=True)

                await db.commit()

            except Exception as e:
                logger.error(f"Error in _check_pending_orders: {e}", exc_info=True)
                await db.rollback()
            finally:
                await db.close()

    async def _check_order(self, db: AsyncSession, pending_order: PendingOrder):
        """
        Check a single pending order and update if filled

        Args:
            db: Database session
            pending_order: PendingOrder to check
        """
        # Get order status from Coinbase
        try:
            order_data = await self.coinbase.get_order(pending_order.order_id)
        except Exception as e:
            logger.error(f"Error fetching order {pending_order.order_id} from Coinbase: {e}")
            return

        # Parse order response
        order = order_data.get("order", {})
        status = order.get("status", "").upper()

        if status == "FILLED":
            # Order was filled - create Trade record
            await self._process_filled_order(db, pending_order, order)

        elif status in ["CANCELLED", "EXPIRED"]:
            # Order was cancelled or expired
            pending_order.status = status.lower()
            pending_order.canceled_at = datetime.utcnow()
            logger.info(f"❌ Order {pending_order.order_id} {status.lower()}")

        # For OPEN/PENDING status, do nothing (still waiting)

    async def _process_filled_order(self, db: AsyncSession, pending_order: PendingOrder, order_data: dict):
        """
        Process a filled order by creating a Trade and updating Position

        Args:
            db: Database session
            pending_order: PendingOrder that was filled
            order_data: Order details from Coinbase
        """
        # Extract filled details from order data
        filled_value = order_data.get("filled_value", "0")
        filled_size = order_data.get("filled_size", "0")
        average_filled_price = order_data.get("average_filled_price", "0")

        filled_quote_amount = float(filled_value)
        filled_base_amount = float(filled_size)
        filled_price = float(average_filled_price)

        # Get the position
        position_query = select(Position).where(Position.id == pending_order.position_id)
        position_result = await db.execute(position_query)
        position = position_result.scalar_one_or_none()

        if not position:
            logger.error(f"Position {pending_order.position_id} not found for order {pending_order.order_id}")
            return

        # Create Trade record
        trade = Trade(
            position_id=position.id,
            timestamp=datetime.utcnow(),
            side="buy",
            quote_amount=filled_quote_amount,
            base_amount=filled_base_amount,
            price=filled_price,
            trade_type=pending_order.trade_type,
            order_id=pending_order.order_id,
        )
        db.add(trade)

        # Update position totals
        position.total_quote_spent += filled_quote_amount
        position.total_base_acquired += filled_base_amount

        # Update average buy price
        if position.total_base_acquired > 0:
            position.average_buy_price = position.total_quote_spent / position.total_base_acquired
        else:
            position.average_buy_price = 0.0

        # Update pending order status
        pending_order.status = "filled"
        pending_order.filled_at = datetime.utcnow()
        pending_order.filled_quote_amount = filled_quote_amount
        pending_order.filled_base_amount = filled_base_amount
        pending_order.filled_price = filled_price

        logger.info(
            f"✅ Order {pending_order.order_id} filled: "
            f"{filled_base_amount:.8f} @ {filled_price:.8f} "
            f"(Position {position.id})"
        )
