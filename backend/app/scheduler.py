"""
APScheduler configuration for ZenithGrid background jobs.

Tier 2 (near-real-time) and Tier 3 (batch) tasks are registered here.
Tier 1 tasks (trading monitors) remain as asyncio.create_task() in main.py.

Jobs are registered via register_jobs(startup_time) called from startup_event().
The scheduler uses AsyncIOScheduler so it shares the FastAPI event loop.
"""

import logging
from datetime import datetime, timedelta

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _job_error_handler(event):
    if event.exception:
        logger.error(
            f"APScheduler job '{event.job_id}' raised {type(event.exception).__name__}: {event.exception}",
            exc_info=(type(event.exception), event.exception, event.traceback),
        )


def register_jobs(startup_time: datetime, scheduler: AsyncIOScheduler = scheduler) -> None:
    """Register all Tier 2 and Tier 3 jobs. Call once from startup_event()."""
    scheduler.add_listener(_job_error_handler, EVENT_JOB_ERROR)

    # --- Tier 2: Near-real-time ---

    from app.services.auto_buy_monitor import auto_buy_monitor
    scheduler.add_job(
        auto_buy_monitor.run_once,
        IntervalTrigger(seconds=10),
        id="auto_buy_monitor",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    from app.services.rebalance_monitor import rebalance_monitor
    scheduler.add_job(
        rebalance_monitor.run_once,
        IntervalTrigger(seconds=30),
        id="rebalance_monitor",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    from app.services.transfer_sync_service import run_transfer_sync_once
    scheduler.add_job(
        run_transfer_sync_once,
        IntervalTrigger(hours=24),
        id="transfer_sync",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=startup_time + timedelta(minutes=20),
    )

    from app.services.account_snapshot_service import run_account_snapshot_once
    scheduler.add_job(
        run_account_snapshot_once,
        IntervalTrigger(hours=24),
        id="account_snapshot",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=startup_time + timedelta(minutes=5),
    )

    from app.services.ban_monitor import run_ban_monitor_once
    scheduler.add_job(
        run_ban_monitor_once,
        IntervalTrigger(hours=24),
        id="ban_monitor",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=startup_time + timedelta(seconds=30),
    )

    from app.services.report_scheduler import run_report_scheduler_once
    scheduler.add_job(
        run_report_scheduler_once,
        IntervalTrigger(minutes=15),
        id="report_scheduler",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    # --- Tier 3: Batch ---

    from app.services.content_refresh_service import content_refresh_service
    scheduler.add_job(
        content_refresh_service.refresh_news,
        IntervalTrigger(minutes=30),
        id="content_refresh_news",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        content_refresh_service.refresh_videos,
        IntervalTrigger(hours=1),
        id="content_refresh_videos",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    from app.services.domain_blacklist_service import domain_blacklist_service
    scheduler.add_job(
        domain_blacklist_service.run_once,
        IntervalTrigger(weeks=1),
        id="domain_blacklist",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    from app.services.debt_ceiling_monitor import debt_ceiling_monitor
    scheduler.add_job(
        debt_ceiling_monitor.run_once,
        IntervalTrigger(weeks=1),
        id="debt_ceiling_monitor",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    from app.services.coin_review_service import run_coin_review_once
    scheduler.add_job(
        run_coin_review_once,
        IntervalTrigger(days=7),
        id="coin_review",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=startup_time + timedelta(minutes=30),
    )

    from app.services.delisted_pair_monitor import trading_pair_monitor
    scheduler.add_job(
        trading_pair_monitor.run_once,
        IntervalTrigger(hours=24),
        id="trading_pair_monitor",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    # --- Cleanup jobs ---

    from app.cleanup_jobs import (
        cleanup_expired_revoked_tokens,
        cleanup_expired_sessions,
        cleanup_failed_condition_logs,
        cleanup_in_memory_caches,
        cleanup_old_decision_logs,
        cleanup_old_failed_orders,
        cleanup_old_rate_limit_attempts,
        cleanup_old_reports,
    )

    scheduler.add_job(
        cleanup_old_decision_logs,
        IntervalTrigger(hours=24),
        id="cleanup_decision_logs",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=startup_time + timedelta(minutes=10),
    )
    scheduler.add_job(
        cleanup_failed_condition_logs,
        IntervalTrigger(hours=6),
        id="cleanup_failed_condition_logs",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=startup_time + timedelta(minutes=15),
    )
    scheduler.add_job(
        cleanup_old_failed_orders,
        IntervalTrigger(hours=6),
        id="cleanup_failed_orders",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=startup_time + timedelta(minutes=20),
    )
    scheduler.add_job(
        cleanup_expired_revoked_tokens,
        IntervalTrigger(hours=24),
        id="cleanup_revoked_tokens",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=startup_time + timedelta(minutes=30),
    )
    scheduler.add_job(
        cleanup_old_reports,
        IntervalTrigger(weeks=1),
        id="cleanup_old_reports",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=startup_time + timedelta(minutes=45),
    )
    scheduler.add_job(
        cleanup_expired_sessions,
        IntervalTrigger(hours=24),
        id="cleanup_sessions",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=startup_time + timedelta(minutes=35),
    )
    scheduler.add_job(
        cleanup_old_rate_limit_attempts,
        IntervalTrigger(hours=1),
        id="cleanup_rate_limit_attempts",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        cleanup_in_memory_caches,
        IntervalTrigger(minutes=5),
        id="cleanup_memory_caches",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=startup_time + timedelta(minutes=2),
    )

    logger.info(f"APScheduler: registered {len(scheduler.get_jobs())} jobs")
