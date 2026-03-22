"""
Background cleanup jobs for database maintenance.

Each function runs once per call. APScheduler fires them on their configured intervals.
Functions log errors and return cleanly (never re-raise) so APScheduler reschedules normally.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker as _default_session_maker
from app.models import (
    Account, ActiveSession, AIBotLog, IndicatorLog, OrderHistory, Position,
    Report, RevokedToken, Settings,
)
from app.services.session_service import expire_all_stale_sessions

logger = logging.getLogger(__name__)


async def cleanup_old_decision_logs(session_maker=None):
    """
    Clean up old AI and indicator logs for closed positions.
    Deletes logs older than the configured retention period.
    """
    sm = session_maker or _default_session_maker
    try:
        async with sm() as db:
            retention_days = await get_log_retention_days(db)

            if retention_days > 0:
                cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

                closed_positions_query = select(Position.id).where(
                    and_(
                        Position.status == 'closed',
                        Position.closed_at < cutoff_date
                    )
                )
                result = await db.execute(closed_positions_query)
                closed_position_ids = [row[0] for row in result.fetchall()]

                if closed_position_ids:
                    ai_delete_query = delete(AIBotLog).where(
                        AIBotLog.position_id.in_(closed_position_ids)
                    )
                    ai_result = await db.execute(ai_delete_query)
                    ai_deleted = ai_result.rowcount

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


async def cleanup_failed_condition_logs(session_maker=None):
    """
    Clean up indicator and AI logs where conditions didn't match.
    Removes logs older than 24 hours where conditions failed or confidence was low.
    """
    sm = session_maker or _default_session_maker
    try:
        async with sm() as db:
            cutoff_time = datetime.utcnow() - timedelta(hours=24)

            indicator_delete_query = delete(IndicatorLog).where(
                and_(
                    IndicatorLog.timestamp < cutoff_time,
                    IndicatorLog.conditions_met.is_(False)
                )
            )
            indicator_result = await db.execute(indicator_delete_query)
            indicator_deleted = indicator_result.rowcount

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


async def cleanup_old_failed_orders(session_maker=None):
    """
    Clean up failed order records older than 24 hours.
    Keeps successful orders indefinitely for audit trail.
    """
    sm = session_maker or _default_session_maker
    try:
        async with sm() as db:
            cutoff_time = datetime.utcnow() - timedelta(hours=24)

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
                logger.info(f"🧹 Cleaned up {deleted_count} failed order records older than 24 hours")
            else:
                logger.debug("No old failed orders to clean up")

    except Exception as e:
        logger.error(f"Error in failed order cleanup job: {e}", exc_info=True)


async def cleanup_expired_revoked_tokens(session_maker=None):
    """
    Remove expired entries from revoked_tokens table.
    Once a JWT's original expiry has passed, the revocation record is unnecessary.
    """
    sm = session_maker or _default_session_maker
    try:
        async with sm() as db:
            now = datetime.utcnow()
            result = await db.execute(
                delete(RevokedToken).where(RevokedToken.expires_at < now)
            )
            deleted_count = result.rowcount
            await db.commit()

            if deleted_count > 0:
                logger.info(f"🧹 Cleaned up {deleted_count} expired revoked token records")
            else:
                logger.debug("No expired revoked tokens to clean up")

    except Exception as e:
        logger.error(f"Error in revoked token cleanup job: {e}", exc_info=True)


async def cleanup_old_reports(session_maker=None):
    """
    Clean up generated reports older than 730 days (2 years).
    """
    sm = session_maker or _default_session_maker
    try:
        async with sm() as db:
            cutoff_date = datetime.utcnow() - timedelta(days=730)

            result = await db.execute(
                delete(Report).where(Report.created_at < cutoff_date)
            )
            deleted_count = result.rowcount
            await db.commit()

            if deleted_count > 0:
                logger.info(f"🧹 Cleaned up {deleted_count} reports older than 2 years")
            else:
                logger.debug("No old reports to clean up")

    except Exception as e:
        logger.error(f"Error in report cleanup job: {e}", exc_info=True)


async def cleanup_expired_sessions(session_maker=None):
    """
    Clean up expired sessions and old inactive session records.
    Marks expired active sessions inactive, deletes inactive sessions older than 30 days.
    """
    sm = session_maker or _default_session_maker
    try:
        async with sm() as db:
            expired_count = await expire_all_stale_sessions(db)

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


async def get_log_retention_days(db: AsyncSession) -> int:
    """Get the configured log retention period from settings"""
    try:
        query = select(Settings).where(Settings.key == 'decision_log_retention_days')
        result = await db.execute(query)
        setting = result.scalars().first()

        if setting:
            return int(setting.value)
        else:
            return 14  # Default to 14 days if setting doesn't exist
    except Exception as e:
        logger.error(f"Error getting log retention setting: {e}")
        return 14  # Default fallback


async def cleanup_old_rate_limit_attempts(session_maker=None):
    """
    Remove expired rate limit attempts.
    Rows older than 1 hour are no longer relevant to any rate-limit window.
    """
    sm = session_maker or _default_session_maker
    try:
        async with sm() as db:
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


async def cleanup_in_memory_caches():
    """
    Sweep all in-memory caches to prevent unbounded growth.
    Called every 5 minutes via APScheduler.
    """
    import resource
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
        from app import main as main_module
        monitor = getattr(main_module, 'price_monitor', None)
        monitor_stats = {}
        if monitor and isinstance(monitor, MultiBotMonitor):
            monitor_stats = monitor.cleanup_caches()

        # --- Rate limiter in-memory pruning ---
        import app.auth_routers.rate_limiters as _rl
        _rl._last_prune_time = 0.0
        _rl._prune_memory()

        # --- Friend request rate limiter ---
        from app.routers.friends_router import prune_friend_request_attempts
        prune_friend_request_attempts()

        # --- Portfolio conversion tasks ---
        from app.services.portfolio_conversion_service import cleanup_old_tasks
        cleanup_old_tasks()

        # --- Auto-buy & rebalance monitor timers ---
        auto_buy = getattr(main_module, 'auto_buy_monitor', None)
        rebalance = getattr(main_module, 'rebalance_monitor', None)
        monitor_cleanup = {}
        if auto_buy or rebalance:
            async with _default_session_maker() as _db:
                _res = await _db.execute(
                    select(Account.id).where(Account.is_active.is_(True))
                )
                active_ids = {row[0] for row in _res.fetchall()}
            if auto_buy:
                monitor_cleanup['auto_buy'] = auto_buy.cleanup_stale_entries(active_ids)
            if rebalance:
                monitor_cleanup['rebalance'] = rebalance.cleanup_stale_entries(active_ids)

        # --- Game WS rate-limit dicts ---
        from app.services.game_ws_handler import prune_game_rate_timestamps
        prune_game_rate_timestamps()

        # --- Public endpoint rate limiter ---
        from app.middleware.public_rate_limit import PublicEndpointRateLimiter
        PublicEndpointRateLimiter.prune_stale()

        # --- Intrusion detection stale entries ---
        from app.middleware.intrusion_detect import IntrusionDetector
        IntrusionDetector.prune_stale()

        # --- WebSocket stale connections ---
        from app.services.websocket_manager import ws_manager
        ws_stale = await ws_manager.sweep_stale_connections()

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
