"""
Indicator Log Service

Logs indicator condition evaluations to the database for non-AI bots.
This allows users to see which conditions matched and why.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IndicatorLog

logger = logging.getLogger(__name__)


async def log_indicator_evaluation(
    db: AsyncSession,
    bot_id: int,
    product_id: str,
    phase: str,
    conditions_met: bool,
    conditions_detail: List[Dict[str, Any]],
    indicators_snapshot: Optional[Dict[str, Any]] = None,
    current_price: Optional[float] = None,
) -> Optional[IndicatorLog]:
    """
    Log an indicator condition evaluation to the database.

    Args:
        db: Database session
        bot_id: Bot ID that ran the evaluation
        product_id: Trading pair (e.g., "ETH-BTC")
        phase: Phase being evaluated ("base_order", "safety_order", "take_profit")
        conditions_met: Whether all conditions passed
        conditions_detail: List of condition evaluation details
        indicators_snapshot: All indicator values at evaluation time
        current_price: Current price at evaluation time

    Returns:
        IndicatorLog record if created, None on error
    """
    try:
        # Only log if there are actual conditions to evaluate
        if not conditions_detail:
            return None

        log_entry = IndicatorLog(
            bot_id=bot_id,
            timestamp=datetime.utcnow(),
            product_id=product_id,
            phase=phase,
            conditions_met=conditions_met,
            conditions_detail=conditions_detail,
            indicators_snapshot=indicators_snapshot,
            current_price=current_price,
        )

        db.add(log_entry)
        # Don't commit here — let the caller batch-commit.
        # Each individual commit acquires SQLite's write lock,
        # causing "database is locked" storms when many pairs
        # are processed concurrently.

        logger.debug(
            f"Logged indicator evaluation: bot={bot_id}, pair={product_id}, "
            f"phase={phase}, met={conditions_met}, conditions={len(conditions_detail)}"
        )

        return log_entry

    except Exception as e:
        logger.error(f"Failed to log indicator evaluation: {e}")
        return None


async def get_indicator_logs(
    db: AsyncSession,
    bot_id: int,
    limit: int = 100,
    offset: int = 0,
    product_id: Optional[str] = None,
    phase: Optional[str] = None,
) -> List[IndicatorLog]:
    """
    Get indicator logs for a bot.

    Args:
        db: Database session
        bot_id: Bot ID to get logs for
        limit: Maximum number of logs to return
        offset: Offset for pagination
        product_id: Filter by product ID (optional)
        phase: Filter by phase (optional)

    Returns:
        List of IndicatorLog records
    """
    from sqlalchemy import select, desc

    query = select(IndicatorLog).where(IndicatorLog.bot_id == bot_id)

    if product_id:
        query = query.where(IndicatorLog.product_id == product_id)

    if phase:
        query = query.where(IndicatorLog.phase == phase)

    query = query.order_by(desc(IndicatorLog.timestamp)).offset(offset).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def cleanup_old_indicator_logs(
    db: AsyncSession,
    bot_id: int,
    keep_count: int = 1000,
) -> int:
    """
    Clean up old indicator logs to prevent database bloat.
    Keeps the most recent `keep_count` logs per bot.

    Args:
        db: Database session
        bot_id: Bot ID to clean logs for
        keep_count: Number of recent logs to keep

    Returns:
        Number of logs deleted
    """
    from sqlalchemy import select, delete

    try:
        # Get the timestamp of the Nth most recent log
        subquery = (
            select(IndicatorLog.timestamp)
            .where(IndicatorLog.bot_id == bot_id)
            .order_by(IndicatorLog.timestamp.desc())
            .offset(keep_count)
            .limit(1)
        )
        result = await db.execute(subquery)
        cutoff_row = result.scalar_one_or_none()

        if cutoff_row is None:
            # Not enough logs to cleanup
            return 0

        # Delete logs older than the cutoff
        delete_stmt = (
            delete(IndicatorLog)
            .where(IndicatorLog.bot_id == bot_id)
            .where(IndicatorLog.timestamp < cutoff_row)
        )
        result = await db.execute(delete_stmt)
        await db.commit()

        deleted_count = result.rowcount
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old indicator logs for bot {bot_id}")

        return deleted_count

    except Exception as e:
        logger.error(f"Failed to cleanup indicator logs: {e}")
        return 0
