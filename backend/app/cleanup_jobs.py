"""
Background cleanup jobs for database maintenance
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import AIBotLog, IndicatorLog, OrderHistory, Position, RevokedToken, Settings

logger = logging.getLogger(__name__)


async def cleanup_old_decision_logs():
    """
    Periodically clean up old AI and indicator logs for closed positions.
    Runs daily and deletes logs older than the configured retention period.
    """
    # Wait 10 minutes after startup before first cleanup
    await asyncio.sleep(600)

    while True:
        try:
            async with async_session_maker() as db:
                # Get retention period from settings
                retention_days = await get_log_retention_days(db)

                if retention_days > 0:
                    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

                    # Find closed positions older than retention period
                    closed_positions_query = select(Position.id).where(
                        and_(
                            Position.status == 'closed',
                            Position.closed_at < cutoff_date
                        )
                    )
                    result = await db.execute(closed_positions_query)
                    closed_position_ids = [row[0] for row in result.fetchall()]

                    if closed_position_ids:
                        # Delete AI logs for these positions
                        ai_delete_query = delete(AIBotLog).where(
                            AIBotLog.position_id.in_(closed_position_ids)
                        )
                        ai_result = await db.execute(ai_delete_query)
                        ai_deleted = ai_result.rowcount

                        # Delete indicator logs for these positions
                        # Note: IndicatorLog doesn't have position_id, so we delete by bot_id and age
                        # Get bot IDs for the closed positions
                        bot_ids_query = select(Position.bot_id).where(
                            Position.id.in_(closed_position_ids)
                        ).distinct()
                        bot_result = await db.execute(bot_ids_query)
                        bot_ids = [row[0] for row in bot_result.fetchall()]

                        if bot_ids:
                            indicator_delete_query = delete(IndicatorLog).where(
                                and_(
                                    IndicatorLog.bot_id.in_(bot_ids),
                                    IndicatorLog.timestamp < cutoff_date
                                )
                            )
                            indicator_result = await db.execute(indicator_delete_query)
                            indicator_deleted = indicator_result.rowcount
                        else:
                            indicator_deleted = 0

                        await db.commit()

                        logger.info(
                            f"🧹 Cleaned up {ai_deleted} AI logs and {indicator_deleted} indicator logs "
                            f"for {len(closed_position_ids)} closed positions older than {retention_days} days"
                        )
                    else:
                        logger.debug(f"No old closed positions to clean up (retention: {retention_days} days)")

        except Exception as e:
            logger.error(f"Error in decision log cleanup job: {e}", exc_info=True)

        # Run daily
        await asyncio.sleep(86400)  # 24 hours


async def cleanup_failed_condition_logs():
    """
    Clean up indicator and AI logs where conditions didn't match.

    Keeps logs where conditions were met (potential trades) indefinitely,
    but removes "noise" logs where conditions failed after 24 hours.
    This prevents the database from filling up with informational logs.

    Runs every 6 hours.
    """
    # Wait 15 minutes after startup before first cleanup
    await asyncio.sleep(900)

    while True:
        try:
            async with async_session_maker() as db:
                cutoff_time = datetime.utcnow() - timedelta(hours=24)

                # Delete indicator logs where conditions were NOT met (conditions_met = False or 0)
                # Keep logs where conditions_met = True as they represent successful matches
                indicator_delete_query = delete(IndicatorLog).where(
                    and_(
                        IndicatorLog.timestamp < cutoff_time,
                        IndicatorLog.conditions_met.is_(False)
                    )
                )
                indicator_result = await db.execute(indicator_delete_query)
                indicator_deleted = indicator_result.rowcount

                # Delete AI logs with low confidence (<30%) older than 24h
                # Keep high-confidence AI signals as they're valuable for analysis
                ai_delete_query = delete(AIBotLog).where(
                    and_(
                        AIBotLog.timestamp < cutoff_time,
                        AIBotLog.confidence < 30
                    )
                )
                ai_result = await db.execute(ai_delete_query)
                ai_deleted = ai_result.rowcount

                await db.commit()

                if indicator_deleted > 0 or ai_deleted > 0:
                    logger.info(
                        f"🧹 Cleaned up failed condition logs: "
                        f"{indicator_deleted} indicator logs (conditions not met), "
                        f"{ai_deleted} AI logs (confidence <30%) older than 24h"
                    )
                else:
                    logger.debug("No failed condition logs to clean up")

        except Exception as e:
            logger.error(f"Error in failed condition log cleanup job: {e}", exc_info=True)

        # Run every 6 hours
        await asyncio.sleep(21600)


async def cleanup_old_failed_orders():
    """
    Clean up failed order records older than 24 hours.

    Failed orders are useful for immediate debugging but don't need to be
    kept indefinitely. This prevents the order_history table from filling
    up with old failed order attempts.

    Keeps successful orders indefinitely for audit trail.
    Runs every 6 hours.
    """
    # Wait 20 minutes after startup before first cleanup
    await asyncio.sleep(1200)

    while True:
        try:
            async with async_session_maker() as db:
                cutoff_time = datetime.utcnow() - timedelta(hours=24)

                # Delete failed orders older than 24 hours
                # Keep successful and canceled orders for audit trail
                failed_delete_query = delete(OrderHistory).where(
                    and_(
                        OrderHistory.timestamp < cutoff_time,
                        OrderHistory.status == 'failed'
                    )
                )
                result = await db.execute(failed_delete_query)
                deleted_count = result.rowcount

                await db.commit()

                if deleted_count > 0:
                    logger.info(
                        f"🧹 Cleaned up {deleted_count} failed order records older than 24 hours"
                    )
                else:
                    logger.debug("No old failed orders to clean up")

        except Exception as e:
            logger.error(f"Error in failed order cleanup job: {e}", exc_info=True)

        # Run every 6 hours
        await asyncio.sleep(21600)


async def cleanup_expired_revoked_tokens():
    """
    Periodically remove expired entries from revoked_tokens table.

    Once a JWT's original expiry time has passed, keeping the revocation
    record is unnecessary — the token can't be used anyway.
    Runs daily.
    """
    # Wait 30 minutes after startup
    await asyncio.sleep(1800)

    while True:
        try:
            async with async_session_maker() as db:
                now = datetime.utcnow()
                result = await db.execute(
                    delete(RevokedToken).where(RevokedToken.expires_at < now)
                )
                deleted_count = result.rowcount
                await db.commit()

                if deleted_count > 0:
                    logger.info(
                        f"🧹 Cleaned up {deleted_count} expired revoked token records"
                    )
                else:
                    logger.debug("No expired revoked tokens to clean up")

        except Exception as e:
            logger.error(f"Error in revoked token cleanup job: {e}", exc_info=True)

        # Run daily
        await asyncio.sleep(86400)


async def get_log_retention_days(db: AsyncSession) -> int:
    """Get the configured log retention period from settings"""
    try:
        query = select(Settings).where(Settings.key == 'decision_log_retention_days')
        result = await db.execute(query)
        setting = result.scalars().first()

        if setting:
            return int(setting.value)
        else:
            # Default to 14 days if setting doesn't exist
            return 14
    except Exception as e:
        logger.error(f"Error getting log retention setting: {e}")
        return 14  # Default fallback
