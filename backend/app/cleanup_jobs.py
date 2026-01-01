"""
Background cleanup jobs for database maintenance
"""

import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import AIBotLog, IndicatorLog, Position, Settings

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
