"""
Background cleanup jobs for database maintenance
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import (
    ActiveSession, AIBotLog, IndicatorLog, OrderHistory, Position, Report,
    RevokedToken, Settings,
)

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

            # Clean up expired entries from the API cache
            try:
                from app.cache import api_cache
                await api_cache.cleanup_expired()
            except Exception as cache_err:
                logger.debug(f"Cache cleanup: {cache_err}")

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


async def cleanup_old_reports():
    """
    Clean up generated reports older than 730 days (2 years).

    Removes report rows including HTML and PDF content to reclaim space.
    Runs weekly.
    """
    # Wait 45 minutes after startup
    await asyncio.sleep(2700)

    while True:
        try:
            async with async_session_maker() as db:
                cutoff_date = datetime.utcnow() - timedelta(days=730)

                result = await db.execute(
                    delete(Report).where(Report.created_at < cutoff_date)
                )
                deleted_count = result.rowcount
                await db.commit()

                if deleted_count > 0:
                    logger.info(
                        f"🧹 Cleaned up {deleted_count} reports older than 2 years"
                    )
                else:
                    logger.debug("No old reports to clean up")

        except Exception as e:
            logger.error(f"Error in report cleanup job: {e}", exc_info=True)

        # Run weekly (7 days)
        await asyncio.sleep(604800)


async def cleanup_expired_sessions():
    """
    Clean up expired sessions and old inactive session records.

    1. Mark expired active sessions as inactive
    2. Delete inactive sessions older than 30 days

    Runs daily.
    """
    # Wait 35 minutes after startup
    await asyncio.sleep(2100)

    while True:
        try:
            async with async_session_maker() as db:
                from app.services.session_service import expire_all_stale_sessions

                expired_count = await expire_all_stale_sessions(db)

                # Delete old inactive sessions (>30 days)
                cutoff = datetime.utcnow() - timedelta(days=30)
                result = await db.execute(
                    delete(ActiveSession).where(
                        and_(
                            ActiveSession.is_active.is_(False),
                            ActiveSession.ended_at < cutoff,
                        )
                    )
                )
                deleted_count = result.rowcount

                await db.commit()

                if expired_count > 0 or deleted_count > 0:
                    logger.info(
                        f"Session cleanup: expired {expired_count} stale sessions, "
                        f"deleted {deleted_count} old inactive sessions"
                    )

        except Exception as e:
            logger.error(f"Error in session cleanup job: {e}", exc_info=True)

        await asyncio.sleep(86400)  # Daily


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


async def cleanup_old_rate_limit_attempts():
    """
    Periodically remove expired rate limit attempts.

    Rows older than 1 hour are no longer relevant to any rate-limit window.
    Runs every hour.
    """
    # Wait 10 minutes after startup
    await asyncio.sleep(600)

    while True:
        try:
            async with async_session_maker() as db:
                cutoff = datetime.utcnow() - timedelta(hours=1)
                from app.models import RateLimitAttempt
                result = await db.execute(
                    delete(RateLimitAttempt).where(
                        RateLimitAttempt.attempted_at < cutoff
                    )
                )
                await db.commit()
                deleted = result.rowcount
                if deleted:
                    logger.info(f'Cleaned up {deleted} expired rate limit attempts')
        except Exception as e:
            logger.error(f'Rate limit cleanup error: {e}')

        await asyncio.sleep(3600)  # Run every hour


async def cleanup_in_memory_caches():
    """
    Periodically sweep all in-memory caches to prevent unbounded growth.

    On a 1GB t2.micro, unchecked caches (price data, candle data, WebSocket tracking,
    chat rate-limit dicts, game rooms) can exhaust RAM within hours.
    Runs every 5 minutes.
    """
    import resource
    # Let the app warm up before first sweep
    await asyncio.sleep(120)

    while True:
        try:
            # --- Price cache (dex_wallet_service) ---
            from app.services.dex_wallet_service import prune_price_cache, _price_cache
            price_evicted = prune_price_cache()

            # --- Chat rate-limit dicts ---
            from app.services.chat_ws_handler import prune_all_stale
            prune_all_stale()

            # --- Game rooms (already has cleanup_stale_rooms) ---
            from app.services.game_room_manager import game_room_manager
            rooms_cleaned = game_room_manager.cleanup_stale_rooms()

            # --- Multi-bot monitor caches ---
            from app.multi_bot_monitor import MultiBotMonitor
            # Access the singleton via the main module (avoid circular import)
            from app import main as main_module
            monitor = getattr(main_module, 'price_monitor', None)
            monitor_stats = {}
            if monitor and isinstance(monitor, MultiBotMonitor):
                monitor_stats = monitor.cleanup_caches()

            # --- WebSocket stale connections ---
            from app.services.websocket_manager import ws_manager
            ws_stale = await ws_manager.sweep_stale_connections()

            # Log RSS and cache stats
            rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
            logger.info(
                f"Memory sweep: RSS={rss_mb:.0f}MB | "
                f"price_cache={len(_price_cache)}(-{price_evicted}) | "
                f"rooms_cleaned={rooms_cleaned} | "
                f"monitor={monitor_stats} | "
                f"ws_stale={ws_stale}"
            )
        except Exception as e:
            logger.error(f"In-memory cache cleanup error: {e}", exc_info=True)

        await asyncio.sleep(300)  # Run every 5 minutes
