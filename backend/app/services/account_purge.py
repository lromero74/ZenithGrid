"""Authoritative account-history purge.

Single source of truth for wiping an account's trading history — trades, order
history, signals, AI-opinion log, pending orders, account-value snapshots, and
positions. The trading record tables intentionally use RESTRICT foreign keys (a
stray account/position delete must never silently cascade away financial
history), so children are deleted explicitly here, in FK-safe order, inside one
transaction.

This replaces ad-hoc reset scripts: any reset/purge — CLI, endpoint, or test —
goes through purge_account_history so the deletion order stays correct in one
place. It does NOT sell holdings or touch the exchange; liquidate first if you
want the wallet flat (see scripts/), then purge the records.
"""
import logging
from typing import Dict

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Bot, Position, Trade, Signal, PendingOrder, OrderHistory, AIOpinionLog,
)
from app.models.reporting import AccountValueSnapshot

logger = logging.getLogger(__name__)


async def count_account_history(db: AsyncSession, account_id: int) -> Dict[str, int]:
    """Return the row counts that purge_account_history would delete. Read-only."""
    bot_ids = select(Bot.id).where(Bot.account_id == account_id).scalar_subquery()
    pos_ids = select(Position.id).where(Position.account_id == account_id).scalar_subquery()

    selects = {
        "trades": select(func.count()).select_from(Trade).where(Trade.position_id.in_(pos_ids)),
        "signals": select(func.count()).select_from(Signal).where(Signal.position_id.in_(pos_ids)),
        "pending_orders": select(func.count()).select_from(PendingOrder).where(
            PendingOrder.position_id.in_(pos_ids)),
        "order_history": select(func.count()).select_from(OrderHistory).where(
            or_(OrderHistory.bot_id.in_(bot_ids), OrderHistory.position_id.in_(pos_ids))),
        "ai_opinion_log": select(func.count()).select_from(AIOpinionLog).where(or_(
            AIOpinionLog.account_id == account_id,
            AIOpinionLog.bot_id.in_(bot_ids),
            AIOpinionLog.position_id.in_(pos_ids))),
        "account_value_snapshots": select(func.count()).select_from(AccountValueSnapshot).where(
            AccountValueSnapshot.account_id == account_id),
        "positions": select(func.count()).select_from(Position).where(
            Position.account_id == account_id),
    }
    return {name: (await db.execute(stmt)).scalar() or 0 for name, stmt in selects.items()}


async def purge_account_history(db: AsyncSession, account_id: int) -> Dict[str, int]:
    """Delete all trading history for ``account_id`` and commit.

    Returns the per-table counts deleted. Children are removed before the
    positions they reference so the RESTRICT foreign keys are satisfied. Bots and
    the account itself are NOT deleted — only their history — so the account can
    immediately start fresh.
    """
    counts = await count_account_history(db, account_id)

    bot_ids = select(Bot.id).where(Bot.account_id == account_id).scalar_subquery()
    pos_ids = select(Position.id).where(Position.account_id == account_id).scalar_subquery()

    # Children → parents (single transaction).
    await db.execute(delete(Trade).where(Trade.position_id.in_(pos_ids)))
    await db.execute(delete(Signal).where(Signal.position_id.in_(pos_ids)))
    await db.execute(delete(PendingOrder).where(PendingOrder.position_id.in_(pos_ids)))
    await db.execute(delete(OrderHistory).where(
        or_(OrderHistory.bot_id.in_(bot_ids), OrderHistory.position_id.in_(pos_ids))))
    await db.execute(delete(AIOpinionLog).where(or_(
        AIOpinionLog.account_id == account_id,
        AIOpinionLog.bot_id.in_(bot_ids),
        AIOpinionLog.position_id.in_(pos_ids))))
    await db.execute(delete(AccountValueSnapshot).where(
        AccountValueSnapshot.account_id == account_id))
    await db.execute(delete(Position).where(Position.account_id == account_id))
    await db.commit()

    logger.info("Purged account %s history: %s", account_id, counts)
    return counts
