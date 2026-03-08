"""
Order Reconciliation Monitor Service

Automatically detects and fixes positions with missing fill data.
Runs as a background task to check for positions showing 0% filled
but with orders that are actually filled on the exchange.

Exchange-agnostic: works with any ExchangeClient implementation.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exchange_clients.base import ExchangeClient
from app.models import Position, Trade

logger = logging.getLogger(__name__)


class OrderReconciliationMonitor:
    """Monitors and auto-fixes positions with missing fill data"""

    def __init__(self, db: AsyncSession, exchange: ExchangeClient, account_id: int = None):
        self.db = db
        self.exchange = exchange
        self.account_id = account_id

    async def check_and_fix_orphaned_positions(self):
        """
        Check for positions with zero fill data but existing order_id in trades.
        These are positions where the initial order succeeded but fill data wasn't captured.
        Scoped to self.account_id if set.
        """
        try:
            # Find open positions with zero base acquired (orphaned orders)
            # Only check positions opened within last 24 hours to avoid re-checking old issues
            twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)

            conditions = [
                Position.status == "open",
                Position.total_base_acquired == 0,
                Position.opened_at >= twenty_four_hours_ago,
            ]
            if self.account_id:
                conditions.append(Position.account_id == self.account_id)

            query = select(Position).where(and_(*conditions))
            result = await self.db.execute(query)
            orphaned_positions = result.scalars().all()

            if not orphaned_positions:
                logger.debug("No orphaned positions found")
                return

            logger.info(f"Found {len(orphaned_positions)} positions with zero fill data - checking for reconciliation")

            for position in orphaned_positions:
                await self._reconcile_position(position)

        except Exception as e:
            logger.error(f"Error checking orphaned positions: {e}")

    async def _reconcile_position(self, position: Position):
        """Attempt to reconcile a single position by fetching fill data from exchange"""
        try:
            # Find the initial trade record for this position
            trade_query = select(Trade).where(
                and_(
                    Trade.position_id == position.id,
                    Trade.side == "buy",
                    Trade.trade_type.in_(["initial", "base_order"])
                )
            ).order_by(Trade.timestamp.asc())

            trade_result = await self.db.execute(trade_query)
            initial_trade = trade_result.scalars().first()

            if not initial_trade or not initial_trade.order_id:
                logger.debug(f"Position #{position.id}: No initial trade with order_id found - skipping")
                return

            order_id = initial_trade.order_id

            # Check if trade already has fill data
            if initial_trade.base_amount > 0:
                logger.debug(f"Position #{position.id}: Trade already has fill data - skipping")
                return

            logger.info(f"🔄 Position #{position.id}: Attempting auto-reconciliation for order {order_id}")

            # Fetch order details from exchange
            order_data = await self.exchange.get_order(order_id)

            if not order_data:
                logger.warning(f"Position #{position.id}: Could not fetch order data for {order_id}")
                return

            # Extract fill information
            filled_size = float(order_data.get("filled_size", "0"))
            filled_value = float(order_data.get("filled_value", "0"))
            avg_price = float(order_data.get("average_filled_price", "0"))
            order_status = order_data.get("status", "UNKNOWN")

            # Only reconcile if order is actually filled
            if order_status not in ["FILLED", "CANCELLED", "EXPIRED"]:
                logger.debug(
                    f"Position #{position.id}: Order {order_id} status is {order_status} - "
                    f"not yet ready for reconciliation"
                )
                return

            # If order was cancelled/expired with zero fills, mark position as failed
            if order_status in ["CANCELLED", "EXPIRED"] and filled_size == 0:
                logger.warning(
                    f"Position #{position.id}: Order {order_id} was {order_status} with no fills - "
                    f"marking position as failed"
                )
                position.status = "failed"
                position.closed_at = datetime.utcnow()
                position.last_error_message = f"Initial order {order_status} with no fills"
                await self.db.commit()
                return

            # If order has zero fills but shows FILLED, log warning and skip
            if filled_size == 0:
                logger.warning(
                    f"Position #{position.id}: Order {order_id} shows status={order_status} "
                    f"but has zero filled_size - cannot reconcile"
                )
                return

            # Order has fills - reconcile the position!
            logger.info(
                f"✅ Position #{position.id}: Auto-reconciling with exchange data - "
                f"filled_size={filled_size}, filled_value={filled_value}, avg_price={avg_price}"
            )

            # Update trade record with actual fill data
            initial_trade.base_amount = filled_size
            initial_trade.quote_amount = filled_value
            initial_trade.price = avg_price

            # Update position totals
            position.total_base_acquired = filled_size
            position.total_quote_spent = filled_value
            position.average_buy_price = avg_price if filled_size > 0 else 0.0

            # Clear any error messages since we successfully reconciled
            position.last_error_message = None
            position.last_error_timestamp = None

            await self.db.commit()

            logger.info(
                f"🎉 Position #{position.id} successfully reconciled! "
                f"Now shows {filled_size} acquired at avg price {avg_price}"
            )

        except Exception as e:
            logger.error(f"Error reconciling position #{position.id}: {e}")
            await self.db.rollback()


async def run_order_reconciliation_monitor(db: AsyncSession, exchange: ExchangeClient):
    """Main loop for order reconciliation monitoring"""
    monitor = OrderReconciliationMonitor(db, exchange)

    while True:
        try:
            await monitor.check_and_fix_orphaned_positions()
        except Exception as e:
            logger.error(f"Error in order reconciliation monitor loop: {e}")

        # Check every 60 seconds (no need to check as frequently as limit orders)
        await asyncio.sleep(60)


class MissingOrderDetector:
    """
    Detects orders that exist on exchange but are not recorded in our database.
    Runs periodically to catch any orders that were placed but not committed due to errors.
    Enhanced to check both BUY and SELL orders, and recently closed positions.
    """

    def __init__(self, db: AsyncSession, exchange: ExchangeClient, account_id: int = None):
        self.db = db
        self.exchange = exchange
        self.account_id = account_id
        # Threshold for alerting (in BTC equivalent)
        self.alert_threshold_btc = 0.0001  # Alert if missing order is >= 0.0001 BTC

    async def check_for_missing_orders(self):
        """
        Compare exchange orders with recorded trades for both open and recently closed positions.
        Alert if any orders are found that weren't recorded.
        Scoped to self.account_id if set.
        """
        try:
            from app.models import PendingOrder

            # Get all open positions + recently closed positions (last 7 days)
            seven_days_ago = datetime.utcnow() - timedelta(days=7)

            conditions = (Position.status == "open") | (
                (Position.status == "closed") & (Position.closed_at >= seven_days_ago)
            )
            if self.account_id:
                conditions = conditions & (Position.account_id == self.account_id)

            query = select(Position).where(conditions)
            result = await self.db.execute(query)
            positions = result.scalars().all()

            if not positions:
                return

            # Group positions by product_id for efficient exchange queries
            positions_by_product = {}
            all_position_ids = []
            for pos in positions:
                if pos.product_id not in positions_by_product:
                    positions_by_product[pos.product_id] = []
                positions_by_product[pos.product_id].append(pos)
                all_position_ids.append(pos.id)

            # Bulk queries: fetch all trades and pending orders at once
            trade_query = select(Trade.order_id, Trade.position_id).where(
                Trade.position_id.in_(all_position_ids)
            )
            trade_result = await self.db.execute(trade_query)
            all_trade_rows = trade_result.fetchall()

            # Build per-position recorded order_id sets
            recorded_order_ids_by_position = {}
            for order_id, pos_id in all_trade_rows:
                if order_id:
                    recorded_order_ids_by_position.setdefault(pos_id, set()).add(order_id)

            pending_query = select(PendingOrder.order_id, PendingOrder.status, PendingOrder.position_id).where(
                PendingOrder.position_id.in_(all_position_ids)
            )
            pending_result = await self.db.execute(pending_query)
            all_pending_rows = pending_result.fetchall()

            # Build per-position pending order maps
            pending_orders_by_position = {}
            for order_id, status, pos_id in all_pending_rows:
                if order_id:
                    pending_orders_by_position.setdefault(pos_id, {})[order_id] = status

            # Build global lookup sets from bulk DB results
            all_recorded_order_ids = set()
            all_pending_orders = {}
            for pid in all_position_ids:
                all_recorded_order_ids.update(recorded_order_ids_by_position.get(pid, set()))
                all_pending_orders.update(pending_orders_by_position.get(pid, {}))

            # Fetch ALL filled orders in a single API call (no product_id filter)
            # This replaces the previous O(U) per-product loop with O(1) API call.
            # Scale the limit with the number of tracked products so we don't miss
            # orders when many products are active (old code fetched 200 per product).
            missing_buys = []
            missing_sells = []
            stuck_pending_orders = []

            num_products = len(positions_by_product)
            fetch_limit = max(200, num_products * 200)

            try:
                exchange_orders = await self.exchange.list_orders(
                    order_status=["FILLED"],
                    limit=fetch_limit,
                )
            except Exception as e:
                logger.warning(f"Could not fetch filled orders: {e}")
                return

            # Filter to only products we're tracking
            tracked_products = set(positions_by_product.keys())

            for order in exchange_orders:
                order_id = order.get("order_id", "")
                product_id = order.get("product_id", "")
                filled_size = float(order.get("filled_size", 0) or 0)
                filled_value = float(order.get("filled_value", 0) or 0)
                side = order.get("side", "")

                # Skip orders for products we're not tracking
                if product_id not in tracked_products:
                    continue

                # Skip orders with no fills
                if filled_size == 0:
                    continue

                # Check if order is recorded in trades table
                if order_id and order_id not in all_recorded_order_ids:
                    # Check if it's in pending_orders with status='pending' (stuck order)
                    if order_id in all_pending_orders and all_pending_orders[order_id] == "pending":
                        stuck_pending_orders.append({
                            "product_id": product_id,
                            "order_id": order_id,
                            "side": side,
                            "base_amount": filled_size,
                            "quote_amount": filled_value,
                            "created_time": order.get("created_time", ""),
                        })
                    else:
                        # Found a missing order!
                        order_info = {
                            "product_id": product_id,
                            "order_id": order_id,
                            "base_amount": filled_size,
                            "quote_amount": filled_value,
                            "created_time": order.get("created_time", ""),
                        }

                        if side == "BUY":
                            missing_buys.append(order_info)
                        elif side == "SELL":
                            missing_sells.append(order_info)

            # Report findings
            total_issues = len(missing_buys) + len(missing_sells) + len(stuck_pending_orders)

            if total_issues > 0:
                logger.warning(f"⚠️  ORDER DISCREPANCIES DETECTED: {total_issues} total issues found")

                if missing_buys:
                    total_buy_quote = sum(o["quote_amount"] for o in missing_buys)
                    logger.warning(
                        f"\n  📥 MISSING BUY ORDERS: {len(missing_buys)} orders "
                        f"totaling {total_buy_quote:.8f} BTC not in trades table"
                    )
                    for order in missing_buys[:5]:  # Show first 5
                        logger.warning(
                            f"    - {order['product_id']}: {order['base_amount']:.8f} "
                            f"({order['quote_amount']:.8f} BTC) order_id={order['order_id'][:12]}... "
                            f"created={order['created_time'][:19]}"
                        )
                    if len(missing_buys) > 5:
                        logger.warning(f"    ... and {len(missing_buys) - 5} more")

                if missing_sells:
                    total_sell_quote = sum(o["quote_amount"] for o in missing_sells)
                    logger.warning(
                        f"\n  📤 MISSING SELL ORDERS: {len(missing_sells)} orders "
                        f"totaling {total_sell_quote:.8f} BTC not in trades table"
                    )
                    for order in missing_sells[:5]:  # Show first 5
                        logger.warning(
                            f"    - {order['product_id']}: {order['base_amount']:.8f} "
                            f"({order['quote_amount']:.8f} BTC) order_id={order['order_id'][:12]}... "
                            f"created={order['created_time'][:19]}"
                        )
                    if len(missing_sells) > 5:
                        logger.warning(f"    ... and {len(missing_sells) - 5} more")

                if stuck_pending_orders:
                    logger.warning(
                        f"\n  🔒 STUCK PENDING ORDERS: {len(stuck_pending_orders)} orders "
                        f"filled on exchange but stuck with status='pending'"
                    )
                    for order in stuck_pending_orders[:5]:  # Show first 5
                        logger.warning(
                            f"    - {order['product_id']} {order['side']}: {order['base_amount']:.8f} "
                            f"({order['quote_amount']:.8f} BTC) order_id={order['order_id'][:12]}... "
                            f"created={order['created_time'][:19]}"
                        )
                    if len(stuck_pending_orders) > 5:
                        logger.warning(f"    ... and {len(stuck_pending_orders) - 5} more")

                logger.warning(
                    "\n  💡 Run manual reconciliation to fix these discrepancies"
                )

        except Exception as e:
            logger.error(f"Error checking for missing orders: {e}")


async def run_missing_order_detector(db: AsyncSession, exchange: ExchangeClient):
    """Background task to detect missing orders every 5 minutes"""
    detector = MissingOrderDetector(db, exchange)

    # Wait 2 minutes after startup before first check
    await asyncio.sleep(120)

    while True:
        try:
            await detector.check_for_missing_orders()
        except Exception as e:
            logger.error(f"Error in missing order detector loop: {e}")

        # Check every 5 minutes
        await asyncio.sleep(300)
