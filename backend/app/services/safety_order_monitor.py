"""Reconciles filled limit DCA *safety* orders into their positions as ADDS.

This is the counterpart to ``limit_order_monitor`` (which handles position
CLOSES via ``Position.closing_via_limit``). A safety-order limit fill must GROW
the position — increase the running base/quote totals and recompute the average
entry — and must NEVER mark the position closed or book realized P&L.

Both directions are handled by dispatching on ``PendingOrder.side``:
  - SELL → adds to a SHORT (``_create_short_sell_trade_record``)
  - BUY  → adds to a LONG  (``_create_buy_trade_record``)

Fills are applied by *delta* (only the newly-filled base since the last check),
keyed off ``PendingOrder.filled_base_amount``, so partial fills accumulate
correctly and re-runs never double-apply.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PendingOrder, Position
from app.services.exchange_service import get_exchange_client_for_account
from app.utils.timeutil import utcnow

logger = logging.getLogger(__name__)
_PREFETCH_NOT_PROVIDED = object()

# trade_type prefix that marks a PendingOrder as a DCA safety ADD (not a close).
SAFETY_TRADE_TYPE_PREFIX = "safety_order"

_TERMINAL_CANCEL_STATUSES = {"CANCELLED", "CANCELED", "EXPIRED", "FAILED"}
_FILL_PROGRESS_STATUSES = {"FILLED", "OPEN", "PENDING", "PARTIALLY_FILLED"}


@dataclass(frozen=True)
class PendingSafetyOrderSnapshot:
    pending_order_id: int
    position_id: int
    account_id: int
    order_id: str
    base_amount: float
    limit_price: float


async def _snapshot_pending_safety_orders(db: AsyncSession) -> list[PendingSafetyOrderSnapshot]:
    result = await db.execute(
        select(
            PendingOrder.id,
            Position.id,
            Position.account_id,
            PendingOrder.order_id,
            PendingOrder.base_amount,
            PendingOrder.limit_price,
        )
        .join(Position, PendingOrder.position_id == Position.id)
        .where(
            PendingOrder.status.in_(["pending", "partially_filled"]),
            PendingOrder.trade_type.like(f"{SAFETY_TRADE_TYPE_PREFIX}%"),
            Position.status == "open",
        )
    )
    snapshots: list[PendingSafetyOrderSnapshot] = []
    for pending_id, position_id, account_id, order_id, base_amount, limit_price in result.all():
        if account_id and order_id:
            snapshots.append(PendingSafetyOrderSnapshot(
                pending_order_id=pending_id,
                position_id=position_id,
                account_id=account_id,
                order_id=order_id,
                base_amount=base_amount or 0.0,
                limit_price=limit_price or 0.0,
            ))
    return snapshots


async def _poll_safety_order_without_db(exchange, snapshot: PendingSafetyOrderSnapshot) -> dict:
    if snapshot.order_id.startswith("paper-"):
        fill_size = snapshot.base_amount or 0.0
        return {
            "status": "FILLED",
            "filled_size": str(fill_size),
            "filled_value": str((snapshot.limit_price or 0.0) * fill_size),
        }
    return await exchange.get_order(snapshot.order_id)


async def _apply_polled_safety_order(session_maker, snapshot: PendingSafetyOrderSnapshot, exchange, order_data) -> None:
    async with session_maker() as db:
        result = await db.execute(
            select(PendingOrder, Position)
            .join(Position, PendingOrder.position_id == Position.id)
            .where(
                PendingOrder.id == snapshot.pending_order_id,
                PendingOrder.status.in_(["pending", "partially_filled"]),
                Position.id == snapshot.position_id,
                Position.status == "open",
            )
        )
        row = result.first()
        if not row:
            logger.info(
                "Safety order %s no longer needs monitoring; skipping",
                snapshot.order_id,
            )
            return
        pending_order, position = row
        apply_exchange = exchange
        is_paper = False
        if hasattr(exchange, "is_paper_trading") and callable(exchange.is_paper_trading):
            is_paper = exchange.is_paper_trading() is True
        if is_paper:
            refreshed = await get_exchange_client_for_account(db, snapshot.account_id)
            if refreshed:
                apply_exchange = refreshed
        monitor = SafetyOrderMonitor(db, apply_exchange)
        await monitor.process_pending_safety_order(pending_order, position, pre_fetched_order_data=order_data)


async def _check_all_pending_safety_orders_scoped(session_maker) -> None:
    async with session_maker() as db:
        snapshots = await _snapshot_pending_safety_orders(db)

    by_account: Dict[int, List[PendingSafetyOrderSnapshot]] = {}
    for snapshot in snapshots:
        by_account.setdefault(snapshot.account_id, []).append(snapshot)

    for account_id, items in by_account.items():
        try:
            async with session_maker() as db:
                exchange = await get_exchange_client_for_account(db, account_id)
            if not exchange:
                logger.warning(
                    f"No exchange client for account {account_id}; "
                    f"skipping {len(items)} pending safety order(s) this cycle"
                )
                continue
            for snapshot in items:
                try:
                    order_data = await _poll_safety_order_without_db(exchange, snapshot)
                    await _apply_polled_safety_order(session_maker, snapshot, exchange, order_data)
                except Exception as e:
                    logger.error(
                        f"Error reconciling safety order {snapshot.order_id} "
                        f"for account {account_id}: {e}",
                        exc_info=True,
                    )
        except Exception as e:
            logger.error(f"Error reconciling safety orders for account {account_id}: {e}")


async def check_all_pending_safety_orders(db: AsyncSession = None, *, session_maker=None) -> None:
    """Find open positions with pending/partially-filled safety limit orders and
    reconcile any new fills into the position. Resolves the exchange client once
    per account (mirrors ``check_all_pending_limit_orders``)."""
    if session_maker is not None:
        await _check_all_pending_safety_orders_scoped(session_maker)
        return
    if db is None:
        from app.database import async_session_maker
        await _check_all_pending_safety_orders_scoped(async_session_maker)
        return

    result = await db.execute(
        select(PendingOrder, Position)
        .join(Position, PendingOrder.position_id == Position.id)
        .where(
            PendingOrder.status.in_(["pending", "partially_filled"]),
            PendingOrder.trade_type.like(f"{SAFETY_TRADE_TYPE_PREFIX}%"),
            Position.status == "open",
        )
    )
    rows = result.all()

    by_account: Dict[int, List[Tuple[PendingOrder, Position]]] = {}
    for pending_order, position in rows:
        if position.account_id:
            by_account.setdefault(position.account_id, []).append((pending_order, position))

    for account_id, items in by_account.items():
        # Isolate per-account failures so one account's client-resolution error
        # can't abort the others (or skip the caller's later orphan sweep).
        try:
            exchange = await get_exchange_client_for_account(db, account_id)
            if not exchange:
                logger.warning(
                    f"No exchange client for account {account_id}; "
                    f"skipping {len(items)} pending safety order(s) this cycle"
                )
                continue
            monitor = SafetyOrderMonitor(db, exchange)
            for pending_order, position in items:
                try:
                    await monitor.process_pending_safety_order(pending_order, position)
                except Exception as e:
                    logger.error(
                        f"Error reconciling safety order {pending_order.order_id} "
                        f"for account {account_id}: {e}"
                    )
        except Exception as e:
            logger.error(f"Error reconciling safety orders for account {account_id}: {e}")


class SafetyOrderMonitor:
    """Applies filled safety limit orders to their positions as adds."""

    def __init__(self, db: AsyncSession, exchange):
        self.db = db
        self.exchange = exchange

    async def process_pending_safety_order(
        self, pending_order: PendingOrder, position: Position, pre_fetched_order_data: Any = _PREFETCH_NOT_PROVIDED,
    ) -> None:
        try:
            # Paper orders fill instantly; synthesize fill data rather than
            # querying the exchange (mirrors limit_order_monitor's handling).
            if pre_fetched_order_data is _PREFETCH_NOT_PROVIDED:
                order_data = None
            else:
                order_data = pre_fetched_order_data

            if order_data is None and pending_order.order_id and pending_order.order_id.startswith("paper-"):
                fill_size = pending_order.base_amount or 0.0
                order_data = {
                    "status": "FILLED",
                    "filled_size": str(fill_size),
                    "filled_value": str((pending_order.limit_price or 0.0) * fill_size),
                }
            elif order_data is None and pre_fetched_order_data is _PREFETCH_NOT_PROVIDED:
                order_data = await self.exchange.get_order(pending_order.order_id)

            if not order_data:
                logger.warning(
                    f"Safety order {pending_order.order_id}: no order data from exchange"
                )
                return

            status = order_data.get("status", "UNKNOWN").upper()

            if status in _TERMINAL_CANCEL_STATUSES:
                pending_order.status = "cancelled"
                pending_order.canceled_at = utcnow()
                await self.db.commit()
                logger.info(
                    f"Safety order {pending_order.order_id} {status}; "
                    f"position {position.id} left unchanged"
                )
            elif status in _FILL_PROGRESS_STATUSES:
                await self._apply_new_fill(pending_order, position, order_data, status)
            else:
                logger.warning(
                    f"Safety order {pending_order.order_id}: unrecognized status '{status}'"
                )
        except Exception as e:
            logger.error(f"Error reconciling safety order {pending_order.order_id}: {e}", exc_info=True)
            await self.db.rollback()
            # Re-raise so the caller knows the fill wasn't applied.
            # Without this, DCA levels aren't counted, average entry price
            # stays stale, and PendingOrder status never updates to "filled".
            raise

    async def _apply_new_fill(
        self, pending_order: PendingOrder, position: Position, order_data: dict, status: str
    ) -> None:
        filled_size = float(order_data.get("filled_size", 0) or 0)
        filled_value = float(order_data.get("filled_value", 0) or 0)
        total_fees = float(order_data.get("total_fees", 0) or 0)

        if filled_size <= 0:
            return  # nothing has filled yet

        prev_filled = pending_order.filled_base_amount or 0.0
        new_base = filled_size - prev_filled

        if new_base <= 0:
            # Idempotent: this fill (or more) was already applied. Only finalize
            # the PendingOrder status if the exchange now reports a full fill.
            if status == "FILLED" and pending_order.status != "filled":
                pending_order.status = "filled"
                pending_order.filled_at = utcnow()
                await self.db.commit()
            return

        avg_price = (filled_value / filled_size) if filled_size > 0 else (pending_order.limit_price or 0.0)
        new_quote = new_base * avg_price
        previous_quote = pending_order.filled_quote_amount or 0.0
        previous_fee = total_fees * (previous_quote / filled_value) if filled_value > 0 else 0.0
        new_fee = max(0.0, total_fees - previous_fee)

        # Apply the ADD via the canonical accounting helpers. These grow the
        # position's running totals and recompute the average entry. They NEVER
        # set status="closed" or compute realized P&L.
        if pending_order.side == "SELL":
            from app.trading_engine.sell_executor_short import _create_short_sell_trade_record
            await _create_short_sell_trade_record(
                db=self.db,
                position=position,
                order_id=pending_order.order_id,
                actual_base_sold=new_base,
                quote_received=new_quote,
                actual_price=avg_price,
                trade_type=pending_order.trade_type,
                fee_quote=new_fee,
            )
        else:  # BUY → long add
            from app.trading_engine.buy_executor import _create_buy_trade_record
            await _create_buy_trade_record(
                db=self.db,
                position=position,
                order_id=pending_order.order_id,
                actual_base_amount=new_base,
                actual_quote_amount=new_quote,
                actual_price=avg_price,
                trade_type=pending_order.trade_type,
                signal_data=None,
                fee_quote=new_fee,
            )

        # Update PendingOrder fill tracking (cumulative).
        pending_order.filled_base_amount = filled_size
        pending_order.filled_quote_amount = filled_value
        pending_order.filled_price = avg_price
        if status == "FILLED":
            pending_order.status = "filled"
            pending_order.filled_at = utcnow()
        else:
            pending_order.status = "partially_filled"

        await self.db.commit()

        # Best-effort post-fill ops (order-history log + WS fill notification,
        # plus balance-cache/event-bus for buys) — the same observability the
        # market execution path runs. Without this, limit safety fills would be
        # invisible in order history and push no notification.
        await self._run_post_fill_ops(pending_order, position, new_base, new_quote, avg_price)

    async def _run_post_fill_ops(
        self, pending_order: PendingOrder, position: Position,
        base_amount: float, quote_amount: float, avg_price: float,
    ) -> None:
        """Run the non-critical post-fill operations (history + notifications)
        for a reconciled safety-order fill, mirroring the market path."""
        from app.models import Bot
        bot = (
            await self.db.execute(select(Bot).where(Bot.id == position.bot_id))
        ).scalar_one_or_none()
        if bot is None:
            logger.warning(
                f"Safety order {pending_order.order_id}: bot {position.bot_id} not found; "
                f"skipping post-fill notifications"
            )
            return

        if pending_order.side == "SELL":
            from app.trading_engine.sell_executor_short import _post_short_sell_operations
            await _post_short_sell_operations(
                db=self.db, exchange=self.exchange, bot=bot,
                product_id=pending_order.product_id, position=position,
                order_id=pending_order.order_id, actual_base_sold=base_amount,
                quote_received=quote_amount, actual_price=avg_price,
                trade_type=pending_order.trade_type,
            )
        else:  # BUY → long add
            from app.trading_client import TradingClient
            from app.trading_engine.buy_executor import _post_buy_operations
            await _post_buy_operations(
                db=self.db, exchange=self.exchange,
                trading_client=TradingClient(self.exchange), bot=bot,
                product_id=pending_order.product_id, position=position,
                order_id=pending_order.order_id, actual_base_amount=base_amount,
                actual_quote_amount=quote_amount, actual_price=avg_price,
                trade_type=pending_order.trade_type,
            )
