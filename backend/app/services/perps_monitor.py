"""
Perpetual futures position monitor

Periodically syncs open perps positions with Coinbase INTX exchange state:
- Updates unrealized PnL, liquidation price
- Detects TP/SL bracket order fills (auto-close)
- Accumulates funding fees
- Broadcasts WebSocket updates
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session_maker
from app.models import Account, Position

logger = logging.getLogger(__name__)


class PerpsMonitor:
    """Monitor open perpetual futures positions and sync with exchange state."""

    def __init__(self, interval_seconds: int = 60):
        self.interval_seconds = interval_seconds
        self.running = False
        self.task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the perps monitoring loop"""
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._monitor_loop())
        logger.info(f"Perps monitor started (interval: {self.interval_seconds}s)")

    async def stop(self):
        """Stop the perps monitoring loop"""
        self.running = False
        if self.task:
            await self.task
            logger.info("Perps monitor stopped")

    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                await self._sync_positions()
            except Exception as e:
                logger.error(f"Perps monitor error: {e}", exc_info=True)

            await asyncio.sleep(self.interval_seconds)

    async def _sync_positions(self):
        """Sync all open perps positions with exchange state"""
        async with async_session_maker() as db:
            # Get all open futures positions
            result = await db.execute(
                select(Position)
                .where(Position.product_type == "future")
                .where(Position.status == "open")
                .options(selectinload(Position.bot))
            )
            positions = result.scalars().all()

            if not positions:
                return

            # Group positions by account to minimize API calls
            positions_by_account: dict[int, list[Position]] = {}
            for pos in positions:
                acct_id = pos.account_id
                if acct_id:
                    positions_by_account.setdefault(acct_id, []).append(pos)

            for account_id, acct_positions in positions_by_account.items():
                await self._sync_account_positions(db, account_id, acct_positions)

            await db.commit()

    async def _sync_account_positions(
        self, db: AsyncSession, account_id: int, positions: list[Position]
    ):
        """Sync positions for a single account"""
        from app.services.exchange_service import get_exchange_client_for_account

        try:
            # Get account to find portfolio UUID
            account = await db.get(Account, account_id)
            if not account or not account.perps_portfolio_uuid:
                logger.debug(
                    f"Account {account_id} has no perps portfolio UUID, skipping sync"
                )
                return

            portfolio_uuid = account.perps_portfolio_uuid

            # Get exchange client
            exchange_client = await get_exchange_client_for_account(db, account_id)
            if not exchange_client:
                return

            # Get the underlying CoinbaseClient
            coinbase_client = getattr(exchange_client, '_client', None) or getattr(exchange_client, 'client', None)
            if coinbase_client is None:
                return

            # Fetch all exchange positions for this portfolio
            try:
                exchange_positions = await coinbase_client.list_perps_positions(portfolio_uuid)
            except Exception as e:
                logger.warning(f"Failed to fetch perps positions for account {account_id}: {e}")
                return

            # Build lookup by product_id
            exchange_pos_map = {
                ep.get("symbol", ep.get("product_id", "")): ep
                for ep in exchange_positions
            }

            for position in positions:
                await self._sync_single_position(
                    db, position, exchange_pos_map, coinbase_client
                )

        except Exception as e:
            logger.error(
                f"Error syncing perps positions for account {account_id}: {e}",
                exc_info=True,
            )

    async def _sync_single_position(
        self,
        db: AsyncSession,
        position: Position,
        exchange_pos_map: dict,
        coinbase_client,
    ):
        """Sync a single position with exchange state"""
        product_id = position.product_id
        exchange_pos = exchange_pos_map.get(product_id)

        if exchange_pos:
            # Position exists on exchange — update metrics
            unrealized_pnl = float(exchange_pos.get("unrealized_pnl", 0))
            liquidation_price = exchange_pos.get("liquidation_price")

            position.unrealized_pnl = unrealized_pnl
            if liquidation_price:
                position.liquidation_price = float(liquidation_price)

            logger.debug(
                f"Position #{position.id} {product_id}: "
                f"uPnL={unrealized_pnl:+.2f} USDC, "
                f"liq={position.liquidation_price}"
            )
        else:
            # Position not on exchange — likely TP/SL filled
            # Check if TP or SL bracket orders were filled
            await self._check_bracket_fill(db, position, coinbase_client)

    async def _check_bracket_fill(
        self, db: AsyncSession, position: Position, coinbase_client
    ):
        """Check if a position was closed by TP/SL bracket order"""
        filled_by = None
        fill_price = None

        for order_id, order_type in [
            (position.tp_order_id, "tp_hit"),
            (position.sl_order_id, "sl_hit"),
        ]:
            if not order_id:
                continue
            try:
                order = await coinbase_client.get_order(order_id)
                status = order.get("status", "")
                if status == "FILLED":
                    filled_by = order_type
                    fill_price = float(order.get("average_filled_price", 0))
                    break
            except Exception as e:
                logger.warning(f"Failed to check bracket order {order_id}: {e}")

        if filled_by and fill_price:
            # Position was auto-closed by exchange bracket order
            logger.info(
                f"Position #{position.id} {position.product_id} auto-closed by {filled_by} @ {fill_price:.2f}"
            )

            # Calculate PnL
            if position.direction == "long":
                base_size = position.total_base_acquired or 0
                cost_basis = position.total_quote_spent or 0
                profit = (fill_price - position.average_buy_price) * base_size
            else:
                base_size = position.short_total_sold_base or 0
                cost_basis = position.short_total_sold_quote or 0
                profit = (position.short_average_sell_price - fill_price) * base_size

            profit -= position.funding_fees_total or 0
            profit_pct = (profit / cost_basis * 100) if cost_basis > 0 else 0

            position.status = "closed"
            position.closed_at = datetime.utcnow()
            position.sell_price = fill_price
            position.profit_quote = profit
            position.profit_percentage = profit_pct
            position.profit_usd = profit
            position.exit_reason = filled_by
            position.tp_order_id = None
            position.sl_order_id = None
            position.unrealized_pnl = None

            logger.info(
                f"Position #{position.id} closed via {filled_by}: "
                f"PnL {profit:+.2f} USDC ({profit_pct:+.2f}%)"
            )

            # Broadcast via WebSocket (scoped to position owner)
            try:
                from app.services.websocket_manager import ws_manager
                await ws_manager.broadcast({
                    "type": "perps_position_closed",
                    "position_id": position.id,
                    "product_id": position.product_id,
                    "exit_reason": filled_by,
                    "profit_usdc": profit,
                    "profit_pct": profit_pct,
                }, user_id=position.user_id)
            except Exception:
                pass
        else:
            # Position gone from exchange but no bracket fill detected
            logger.warning(
                f"Position #{position.id} {position.product_id} not found on exchange "
                f"and no bracket fill detected — may need manual reconciliation"
            )
