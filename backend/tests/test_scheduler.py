"""
Tests for APScheduler configuration.

TDD: Written before implementing app/scheduler.py
"""

import logging
from datetime import datetime, timedelta
from unittest import mock

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR


class TestSchedulerSetup:
    """Tests for basic scheduler lifecycle."""

    @pytest.mark.asyncio
    async def test_scheduler_starts(self):
        """Happy path: scheduler can be started within a running event loop."""
        sched = AsyncIOScheduler()
        assert not sched.running
        sched.start()
        assert sched.running
        sched.shutdown(wait=False)

    def test_register_jobs_adds_expected_job_count(self):
        """register_jobs() registers the expected number of jobs."""
        from app.scheduler import register_jobs

        sched = AsyncIOScheduler()
        startup_time = datetime.utcnow()
        register_jobs(startup_time, scheduler=sched)

        # We expect exactly 22 jobs:
        # Tier 2: auto_buy, rebalance, transfer_sync, account_snapshot, ban_monitor, report_scheduler (6)
        # Tier 3: content_news, content_videos, domain_blacklist, debt_ceiling, coin_review,
        #          trading_pair (6)
        # Cleanup: decision_logs, failed_condition_logs, failed_orders, revoked_tokens,
        #           old_reports, sessions, rate_limit_attempts, memory_caches (8)
        # Total: 20 jobs
        # (May vary by 1-2 based on final design)
        jobs = sched.get_jobs()
        assert len(jobs) >= 18, f"Expected at least 18 jobs, got {len(jobs)}: {[j.id for j in jobs]}"

    def test_job_ids_are_unique(self):
        """All registered job IDs are unique strings."""
        from app.scheduler import register_jobs

        sched = AsyncIOScheduler()
        startup_time = datetime.utcnow()
        register_jobs(startup_time, scheduler=sched)

        job_ids = [j.id for j in sched.get_jobs()]
        assert len(job_ids) == len(set(job_ids)), f"Duplicate job IDs: {job_ids}"

    def test_interval_trigger_seconds_for_auto_buy(self):
        """auto_buy_monitor job uses IntervalTrigger with seconds=10."""
        from app.scheduler import register_jobs

        sched = AsyncIOScheduler()
        startup_time = datetime.utcnow()
        register_jobs(startup_time, scheduler=sched)

        job = sched.get_job("auto_buy_monitor")
        assert job is not None, "auto_buy_monitor job not found"
        assert isinstance(job.trigger, IntervalTrigger)
        assert job.trigger.interval.total_seconds() == 10

    def test_interval_trigger_seconds_for_rebalance(self):
        """rebalance_monitor job uses IntervalTrigger with seconds=30."""
        from app.scheduler import register_jobs

        sched = AsyncIOScheduler()
        startup_time = datetime.utcnow()
        register_jobs(startup_time, scheduler=sched)

        job = sched.get_job("rebalance_monitor")
        assert job is not None, "rebalance_monitor job not found"
        assert isinstance(job.trigger, IntervalTrigger)
        assert job.trigger.interval.total_seconds() == 30

    def test_cleanup_jobs_have_max_instances_1(self):
        """All cleanup jobs have max_instances=1 to prevent overlapping."""
        from app.scheduler import register_jobs

        sched = AsyncIOScheduler()
        startup_time = datetime.utcnow()
        register_jobs(startup_time, scheduler=sched)

        cleanup_job_ids = [
            "cleanup_decision_logs", "cleanup_failed_condition_logs",
            "cleanup_failed_orders", "cleanup_revoked_tokens",
            "cleanup_old_reports", "cleanup_sessions",
            "cleanup_rate_limit_attempts", "cleanup_memory_caches",
        ]
        for job_id in cleanup_job_ids:
            job = sched.get_job(job_id)
            assert job is not None, f"Job {job_id} not found"
            assert job.max_instances == 1, f"Job {job_id} should have max_instances=1"

    def test_startup_delay_applied_for_snapshot_job(self):
        """account_snapshot job fires at startup + 5 minutes (not immediately)."""
        from app.scheduler import register_jobs

        sched = AsyncIOScheduler()
        startup_time = datetime.utcnow()
        register_jobs(startup_time, scheduler=sched)

        job = sched.get_job("account_snapshot")
        assert job is not None
        # next_run_time should be ~5 minutes after startup_time
        expected_min = startup_time + timedelta(minutes=4, seconds=50)
        expected_max = startup_time + timedelta(minutes=5, seconds=10)
        nrt = job.next_run_time
        # Strip timezone for comparison (job uses UTC, startup_time is naive)
        if nrt.tzinfo is not None:
            nrt = nrt.replace(tzinfo=None)
        assert expected_min <= nrt <= expected_max, (
            f"account_snapshot next_run_time {nrt} not in expected range"
        )

    def test_register_jobs_single_call_produces_unique_ids(self):
        """A single register_jobs() call produces no duplicate job IDs."""
        from app.scheduler import register_jobs

        sched = AsyncIOScheduler()
        startup_time = datetime.utcnow()
        register_jobs(startup_time, scheduler=sched)
        job_ids = [j.id for j in sched.get_jobs()]
        assert len(job_ids) == len(set(job_ids)), (
            f"Duplicate job IDs found: {[jid for jid in job_ids if job_ids.count(jid) > 1]}"
        )


class TestErrorListener:
    """Tests for the error listener behavior."""

    def test_error_listener_logs_on_job_exception(self):
        """Error listener logs to logger.error when a job raises."""
        from app.scheduler import _job_error_handler

        mock_event = mock.MagicMock()
        mock_event.exception = ValueError("test error")
        mock_event.job_id = "test_job"
        mock_event.traceback = None

        with mock.patch("app.scheduler.logger") as mock_logger:
            _job_error_handler(mock_event)
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args[0][0]
            assert "test_job" in call_args
            assert "ValueError" in call_args

    def test_error_listener_silent_when_no_exception(self):
        """Error listener does nothing when event.exception is None/falsy."""
        from app.scheduler import _job_error_handler

        mock_event = mock.MagicMock()
        mock_event.exception = None

        with mock.patch("app.scheduler.logger") as mock_logger:
            _job_error_handler(mock_event)
            mock_logger.error.assert_not_called()
