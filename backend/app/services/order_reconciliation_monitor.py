"""
Order Reconciliation Monitor Service

Automatically detects and fixes positions with missing fill data.
Runs as a background task to check for positions showing 0% filled
but with orders that are actually filled on Coinbase.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Position, Trade
from app.coinbase_unified_client import CoinbaseClient

logger = logging.getLogger(__name__)


class OrderReconciliationMonitor:
    """Monitors and auto-fixes positions with missing fill data"""

    def __init__(self, db: AsyncSession, coinbase_client: CoinbaseClient):
        self.db = db
        self.coinbase = coinbase_client

    async def check_and_fix_orphaned_positions(self):
        """
        Check for positions with zero fill data but existing order_id in trades.
        These are positions where the initial order succeeded but fill data wasn't captured.
        """
        try:
            # Find open positions with zero base acquired (orphaned orders)
            # Only check positions opened within last 24 hours to avoid re-checking old issues
            twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)

            query = select(Position).where(
                and_(
                    Position.status == "open",
                    Position.total_base_acquired == 0,
                    Position.opened_at >= twenty_four_hours_ago
                )
            )
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
        """Attempt to reconcile a single position by fetching fill data from Coinbase"""
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

            # Fetch order details from Coinbase
            order_data = await self.coinbase.get_order(order_id)

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
                f"✅ Position #{position.id}: Auto-reconciling with Coinbase data - "
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


async def run_order_reconciliation_monitor(db: AsyncSession, coinbase_client: CoinbaseClient):
    """Main loop for order reconciliation monitoring"""
    monitor = OrderReconciliationMonitor(db, coinbase_client)

    while True:
        try:
            await monitor.check_and_fix_orphaned_positions()
        except Exception as e:
            logger.error(f"Error in order reconciliation monitor loop: {e}")

        # Check every 60 seconds (no need to check as frequently as limit orders)
        await asyncio.sleep(60)


class MissingOrderDetector:
    """
    Detects orders that exist on Coinbase but are not recorded in our database.
    Runs periodically to catch any orders that were placed but not committed due to errors.
    Enhanced to check both BUY and SELL orders, and recently closed positions.
    """

    def __init__(self, db: AsyncSession, coinbase_client: CoinbaseClient):
        self.db = db
        self.coinbase = coinbase_client
        # Threshold for alerting (in BTC equivalent)
        self.alert_threshold_btc = 0.0001  # Alert if missing order is >= 0.0001 BTC

    async def check_for_missing_orders(self):
        """
        Compare Coinbase orders with recorded trades for both open and recently closed positions.
        Alert if any orders are found that weren't recorded.
        Enhanced to check BOTH buy and sell orders.
        """
        try:
            from app.models import PendingOrder

            # Get all open positions + recently closed positions (last 7 days)
            seven_days_ago = datetime.utcnow() - timedelta(days=7)

            query = select(Position).where(
                (Position.status == "open") |
                ((Position.status == "closed") & (Position.closed_at >= seven_days_ago))
            )
            result = await self.db.execute(query)
            positions = result.scalars().all()

            if not positions:
                return

            # Group positions by product_id for efficient Coinbase queries
            positions_by_product = {}
            for pos in positions:
                if pos.product_id not in positions_by_product:
                    positions_by_product[pos.product_id] = []
                positions_by_product[pos.product_id].append(pos)

            missing_buys = []
            missing_sells = []
            stuck_pending_orders = []

            for product_id, product_positions in positions_by_product.items():
                # Find the earliest position open date
                earliest_open = min(p.opened_at for p in product_positions)

                # Get all recorded order_ids for these positions from trades table
                position_ids = [p.id for p in product_positions]
                trade_query = select(Trade.order_id).where(
                    Trade.position_id.in_(position_ids)
                )
                trade_result = await self.db.execute(trade_query)
                recorded_order_ids = set(t[0] for t in trade_result.fetchall() if t[0])

                # Also get order_ids from pending_orders table
                pending_query = select(PendingOrder.order_id, PendingOrder.status).where(
                    PendingOrder.position_id.in_(position_ids)
                )
                pending_result = await self.db.execute(pending_query)
                pending_orders = {row[0]: row[1] for row in pending_result.fetchall() if row[0]}

                # Get orders from Coinbase since earliest position opened
                start_date = earliest_open.strftime("%Y-%m-%dT%H:%M:%SZ")
                try:
                    coinbase_orders = await self.coinbase.list_orders(
                        product_id=product_id,
                        order_status=["FILLED"],
                        start_date=start_date,
                        limit=200,
                    )
                except Exception as e:
                    logger.warning(f"Could not fetch orders for {product_id}: {e}")
                    continue

                # Check for missing orders (both BUY and SELL)
                for order in coinbase_orders.get("orders", []):
                    order_id = order.get("order_id", "")
                    filled_size = float(order.get("filled_size", 0) or 0)
                    filled_value = float(order.get("filled_value", 0) or 0)
                    side = order.get("side", "")

                    # Skip orders with no fills
                    if filled_size == 0:
                        continue

                    # Check if order is recorded in trades table
                    if order_id and order_id not in recorded_order_ids:
                        # Check if it's in pending_orders with status='pending' (stuck order)
                        if order_id in pending_orders and pending_orders[order_id] == "pending":
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
                        f"filled on Coinbase but stuck with status='pending'"
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


async def run_missing_order_detector(db: AsyncSession, coinbase_client: CoinbaseClient):
    """Background task to detect missing orders every 5 minutes"""
    detector = MissingOrderDetector(db, coinbase_client)

    # Wait 2 minutes after startup before first check
    await asyncio.sleep(120)

    while True:
        try:
            await detector.check_for_missing_orders()
        except Exception as e:
            logger.error(f"Error in missing order detector loop: {e}")

        # Check every 5 minutes
        await asyncio.sleep(300)
