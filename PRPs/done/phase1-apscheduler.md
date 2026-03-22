# PRP: Phase 1.2 — Move Tier 2 & 3 Background Tasks to APScheduler

**Feature**: Replace hand-rolled `asyncio.sleep()` loops for Tier 2 and Tier 3 background tasks with APScheduler's `AsyncIOScheduler`
**Created**: 2026-03-21
**One-Pass Confidence Score**: 8/10
**Depends on**: Phase 1.1 (task tiering) must be complete first

> Confidence is 8 (not 9) because several tasks have class-based start/stop patterns with internal state (`ContentRefreshService`, `AutoBuyMonitor`, `RebalanceMonitor`, `DebtCeilingMonitor`, `DomainBlacklistService`, `TradingPairMonitor`). These require more thought than a plain function-to-job swap. The cleanup functions in `cleanup_jobs.py` and the standalone async functions in `main.py` are straightforward drop-ins.

---

## Context & Goal

### Problem

All 27 background tasks in ZenithGrid are hand-rolled `asyncio.sleep()` loops started with `asyncio.create_task()` at app startup. Every single one shares the same event loop with trading monitors, WebSocket handlers, and API requests. This has three concrete problems:

1. **No error isolation** — a crash in a cleanup loop silently kills that loop forever (no restart, no alert)
2. **Clock drift** — `asyncio.sleep(86400)` does not mean "run at midnight daily"; it means "run 24 hours after the last run ended, plus however long the job body took." Over days this drifts noticeably.
3. **No visibility** — there is no way to see when the next report cleanup will run, or when the last coin review happened, without tailing logs.

The roadmap (Section 1.2) targets Tier 2 and Tier 3 tasks specifically. Tier 1 (trading monitors) stay on the main asyncio event loop — they need sub-second latency, not scheduled intervals.

### Solution

Install APScheduler and replace Tier 2 and Tier 3 sleep loops with `AsyncIOScheduler` jobs. The scheduler:
- Runs on the same event loop as FastAPI (no separate thread needed)
- Gives each job an independent try/except with a per-job error handler
- Fires at the configured interval regardless of how long the job took (no drift)
- Exposes `scheduler.get_jobs()` for an admin endpoint showing next-run times

### Who Benefits

- **Operators**: Visibility into next-run times without tailing logs. Silent death of cleanup jobs becomes a logged error.
- **Users**: Reports, coin reviews, and cleanup jobs fire reliably. No more "why haven't new coins been reviewed in a month?" because the task crashed silently.
- **Future developers**: Adding a new periodic job is 3 lines, not 15.

### Scope

- **In**: All Tier 2 and Tier 3 tasks (exact list below)
- **Out**: Tier 1 tasks (MultiBotMonitor, LimitOrderMonitor, OrderReconciliationMonitor, PropGuardMonitor, PerpsMonitor, MissingOrderDetector) — these stay as asyncio tasks
- **Out**: Job persistence / SQLAlchemy job store — use in-memory store only for now (Redis store is a Phase 2 option per the roadmap)
- **Out**: Admin UI for job management — adding an endpoint to expose `get_jobs()` is a follow-on, not part of this PRP

---

## Current State Inventory

### Tasks to Migrate (Tier 2 — Near-real-time)

| Task | Current location | Current interval | New APScheduler trigger |
|------|-----------------|-----------------|------------------------|
| `AutoBuyMonitor` | `auto_buy_monitor.py` — class with `start()/stop()`, inner loop sleeps 10s | 10 seconds | `IntervalTrigger(seconds=10)` |
| `RebalanceMonitor` | `rebalance_monitor.py` — class with `start()/stop()`, inner loop sleeps 30s | 30 seconds | `IntervalTrigger(seconds=30)` |
| `run_transfer_sync()` | `main.py` inline function, sleeps 86400s, 1200s initial delay | daily | `IntervalTrigger(hours=24, start_date=startup+20min)` |
| `run_account_snapshot_capture()` | `main.py` inline function, sleeps 86400s, 300s initial delay | daily | `IntervalTrigger(hours=24, start_date=startup+5min)` |
| `ban_monitor_loop()` | `ban_monitor.py`, sleeps 86400s, 30s initial delay | daily | `IntervalTrigger(hours=24, start_date=startup+30s)` |
| `run_report_scheduler()` | `report_scheduler.py` standalone async function, sleeps 900s | 15 minutes | `IntervalTrigger(minutes=15)` |

### Tasks to Migrate (Tier 3 — Batch)

| Task | Current location | Current interval | New APScheduler trigger |
|------|-----------------|-----------------|------------------------|
| `ContentRefreshService` (news) | `content_refresh_service.py` — class, news every 30m | 30 minutes | `IntervalTrigger(minutes=30)` |
| `ContentRefreshService` (videos) | same class, videos every 60m | 60 minutes | `IntervalTrigger(hours=1)` |
| `DomainBlacklistService` | `domain_blacklist_service.py` — class with `start()/stop()`, weekly | weekly | `IntervalTrigger(weeks=1)` |
| `DebtCeilingMonitor` | `debt_ceiling_monitor.py` — class with `start()/stop()`, weekly | weekly | `IntervalTrigger(weeks=1)` |
| `run_coin_review_scheduler()` | `coin_review_service.py` standalone function, 7-day interval | 7 days | `IntervalTrigger(days=7)` |
| `cleanup_old_decision_logs()` | `cleanup_jobs.py`, 24h sleep, 600s initial delay | daily | `IntervalTrigger(hours=24, start_date=startup+10min)` |
| `cleanup_failed_condition_logs()` | `cleanup_jobs.py`, 6h sleep, 900s initial delay | 6 hours | `IntervalTrigger(hours=6, start_date=startup+15min)` |
| `cleanup_old_failed_orders()` | `cleanup_jobs.py`, 6h sleep, 1200s initial delay | 6 hours | `IntervalTrigger(hours=6, start_date=startup+20min)` |
| `cleanup_expired_revoked_tokens()` | `cleanup_jobs.py`, 24h sleep, 1800s initial delay | daily | `IntervalTrigger(hours=24, start_date=startup+30min)` |
| `cleanup_old_reports()` | `cleanup_jobs.py`, 7-day sleep, 2700s initial delay | weekly | `IntervalTrigger(weeks=1, start_date=startup+45min)` |
| `cleanup_expired_sessions()` | `cleanup_jobs.py`, 24h sleep, 2100s initial delay | daily | `IntervalTrigger(hours=24, start_date=startup+35min)` |
| `cleanup_old_rate_limit_attempts()` | `cleanup_jobs.py`, 3600s sleep | hourly | `IntervalTrigger(hours=1)` |
| `cleanup_in_memory_caches()` | `cleanup_jobs.py`, 300s sleep, 120s initial delay | 5 minutes | `IntervalTrigger(minutes=5, start_date=startup+2min)` |
| `TradingPairMonitor` | `delisted_pair_monitor.py` — class with `start()/stop()`, 86400s | daily | `IntervalTrigger(hours=24)` |

### Tasks That Stay as asyncio.create_task() (Tier 1 — Do NOT migrate)

- `MultiBotMonitor` (10s) — order execution path
- `run_limit_order_monitor()` (10s) — limit order fill detection
- `run_order_reconciliation_monitor()` (60s) — orphaned position repair
- `run_missing_order_detector()` (5m) — exchange-side order audit
- `PropGuardMonitor` (30s) — prop firm drawdown enforcement
- `PerpsMonitor` (60s) — futures position sync

---

## Pre-existing: APScheduler in requirements.txt

APScheduler is **not currently in `backend/requirements.txt`**. It must be added. The correct package is `APScheduler>=3.10.0` (the 3.x line; the 4.x beta has breaking API changes and is not production-ready as of 2026-03).

---

## Implementation Approach

### Architecture Decision: One Scheduler, Module `app/scheduler.py`

Create a single `app/scheduler.py` module that:
1. Instantiates `AsyncIOScheduler` as a module-level singleton
2. Exposes a `scheduler` object that `main.py` starts and stops via `scheduler.start()` / `scheduler.shutdown(wait=False)`
3. Provides `register_jobs(startup_time: datetime)` called once from `startup_event()`

This follows the existing singleton pattern used for `ws_manager`, `content_refresh_service`, `domain_blacklist_service`, etc.

### Pattern: Wrapping Class-Based Services

Several Tier 2/3 services use the class pattern `start()/stop()` with an inner `_loop()` that contains the real business logic. The migration approach:

- **Extract the business logic** from the `_loop()` method into a standalone `async def run_once()` method on the class (or a top-level function if simpler)
- **APScheduler calls `run_once()`** on its interval
- **Remove `start()/stop()` and the sleep loop** from the class — APScheduler owns the scheduling now
- **`stop()` becomes a no-op or removed** — APScheduler's `scheduler.shutdown()` stops all jobs cleanly

For services whose `start()/stop()` are called in `shutdown_event()`, the shutdown block in `main.py` must be updated to remove those calls (APScheduler's `shutdown()` replaces them).

### Pattern: Wrapping Standalone Async Functions

The `cleanup_jobs.py` functions and inline `main.py` functions (like `run_account_snapshot_capture`, `run_transfer_sync`) currently embed their own `while True` + `asyncio.sleep()` loop. The migration:

- **Remove the `while True` loop and `asyncio.sleep()` calls** from each function — keep only the body logic
- **Remove the initial `asyncio.sleep(N)` startup delay** — replace with `start_date` parameter in the trigger
- **The function becomes a plain async job function** that APScheduler calls on schedule
- **No changes to the DB query logic, error handling, or logging** — only the scheduling wrapper changes

### Error Handler

Register a per-scheduler error listener that logs the job ID, exception type, and traceback. This replaces the current "task crashes silently" behavior:

```python
def _job_error_handler(event):
    if event.exception:
        logger.error(
            f"APScheduler job {event.job_id} raised an exception: {event.exception}",
            exc_info=(type(event.exception), event.exception, event.traceback),
        )
```

Use `scheduler.add_listener(_job_error_handler, EVENT_JOB_ERROR)`.

---

## Implementation Tasks (in order)

### Step 1: Add APScheduler to requirements.txt (TDD: do this before tests)

**File**: `backend/requirements.txt`

Add after the existing dependencies block, before `# Development & testing tools`:

```
APScheduler>=3.10.0
```

Then install it:

```bash
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m pip install "APScheduler>=3.10.0"
```

Verify the install:
```bash
./venv/bin/python3 -c "import apscheduler; print(apscheduler.__version__)"
```

---

### Step 2: Write tests FIRST (TDD)

**New file**: `backend/tests/test_scheduler.py`

Write these tests before writing `app/scheduler.py`:

**Happy path**:
- `test_scheduler_starts_and_stops` — create an `AsyncIOScheduler`, add a mock job, start it, assert it is running, shut it down, assert not running
- `test_register_jobs_adds_expected_job_count` — call `register_jobs()`, assert the scheduler has the expected number of jobs (one per task above, counting ContentRefreshService as 2)
- `test_job_ids_are_unique` — assert all registered job IDs are unique strings
- `test_interval_trigger_seconds_for_auto_buy` — assert the `auto_buy` job has an `IntervalTrigger` with `seconds=10`

**Edge case**:
- `test_register_jobs_idempotent` — calling `register_jobs()` twice should not double-add jobs (APScheduler raises `ConflictingIdError` if IDs collide; verify this is caught or prevented)

**Failure case**:
- `test_error_listener_logs_on_job_exception` — inject a job that raises, fire it, assert `logger.error` was called with the job ID

**File**: `backend/tests/services/test_cleanup_jobs_as_functions.py`

For each cleanup function that previously had a `while True` loop (after the refactor removes the loop), write:
- `test_cleanup_<name>_runs_without_error` — mock the DB session, verify no exceptions raised
- `test_cleanup_<name>_handles_db_error` — make the session raise, verify the function does NOT reraise (it should log and return cleanly, so APScheduler can retry next interval)

---

### Step 3: Create `backend/app/scheduler.py`

**New file**: `backend/app/scheduler.py`

```python
"""
APScheduler configuration for ZenithGrid background jobs.

Tier 2 (near-real-time) and Tier 3 (batch) tasks are registered here.
Tier 1 tasks (trading monitors) remain as asyncio.create_task() in main.py.

Jobs are registered via register_jobs(startup_time) called from startup_event().
The scheduler uses AsyncIOScheduler so it shares the FastAPI event loop.
"""

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _job_error_handler(event):
    if event.exception:
        logger.error(
            f"APScheduler job '{event.job_id}' raised {type(event.exception).__name__}: {event.exception}",
            exc_info=(type(event.exception), event.exception, event.traceback),
        )


def register_jobs(startup_time: datetime) -> None:
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
    )

    from app.services.rebalance_monitor import rebalance_monitor
    scheduler.add_job(
        rebalance_monitor.run_once,
        IntervalTrigger(seconds=30),
        id="rebalance_monitor",
        max_instances=1,
        coalesce=True,
    )

    from app.services.transfer_sync_service import run_transfer_sync_once
    scheduler.add_job(
        run_transfer_sync_once,
        IntervalTrigger(hours=24),
        id="transfer_sync",
        max_instances=1,
        coalesce=True,
        next_run_time=startup_time + timedelta(minutes=20),
    )

    from app.services.account_snapshot_service import run_account_snapshot_once
    scheduler.add_job(
        run_account_snapshot_once,
        IntervalTrigger(hours=24),
        id="account_snapshot",
        max_instances=1,
        coalesce=True,
        next_run_time=startup_time + timedelta(minutes=5),
    )

    from app.services.ban_monitor import run_ban_monitor_once
    scheduler.add_job(
        run_ban_monitor_once,
        IntervalTrigger(hours=24),
        id="ban_monitor",
        max_instances=1,
        coalesce=True,
        next_run_time=startup_time + timedelta(seconds=30),
    )

    from app.services.report_scheduler import run_report_scheduler_once
    scheduler.add_job(
        run_report_scheduler_once,
        IntervalTrigger(minutes=15),
        id="report_scheduler",
        max_instances=1,
        coalesce=True,
    )

    # --- Tier 3: Batch ---

    from app.services.content_refresh_service import content_refresh_service
    scheduler.add_job(
        content_refresh_service.refresh_news,
        IntervalTrigger(minutes=30),
        id="content_refresh_news",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        content_refresh_service.refresh_videos,
        IntervalTrigger(hours=1),
        id="content_refresh_videos",
        max_instances=1,
        coalesce=True,
    )

    from app.services.domain_blacklist_service import domain_blacklist_service
    scheduler.add_job(
        domain_blacklist_service.run_once,
        IntervalTrigger(weeks=1),
        id="domain_blacklist",
        max_instances=1,
        coalesce=True,
    )

    from app.services.debt_ceiling_monitor import debt_ceiling_monitor
    scheduler.add_job(
        debt_ceiling_monitor.run_once,
        IntervalTrigger(weeks=1),
        id="debt_ceiling_monitor",
        max_instances=1,
        coalesce=True,
    )

    from app.services.coin_review_service import run_coin_review_once
    scheduler.add_job(
        run_coin_review_once,
        IntervalTrigger(days=7),
        id="coin_review",
        max_instances=1,
        coalesce=True,
        next_run_time=startup_time + timedelta(minutes=30),
    )

    from app.services.delisted_pair_monitor import trading_pair_monitor
    scheduler.add_job(
        trading_pair_monitor.run_once,
        IntervalTrigger(hours=24),
        id="trading_pair_monitor",
        max_instances=1,
        coalesce=True,
    )

    # --- Cleanup jobs ---

    from app.cleanup_jobs import (
        cleanup_old_decision_logs,
        cleanup_failed_condition_logs,
        cleanup_old_failed_orders,
        cleanup_expired_revoked_tokens,
        cleanup_old_reports,
        cleanup_expired_sessions,
        cleanup_old_rate_limit_attempts,
        cleanup_in_memory_caches,
    )

    scheduler.add_job(
        cleanup_old_decision_logs,
        IntervalTrigger(hours=24),
        id="cleanup_decision_logs",
        max_instances=1,
        coalesce=True,
        next_run_time=startup_time + timedelta(minutes=10),
    )
    scheduler.add_job(
        cleanup_failed_condition_logs,
        IntervalTrigger(hours=6),
        id="cleanup_failed_condition_logs",
        max_instances=1,
        coalesce=True,
        next_run_time=startup_time + timedelta(minutes=15),
    )
    scheduler.add_job(
        cleanup_old_failed_orders,
        IntervalTrigger(hours=6),
        id="cleanup_failed_orders",
        max_instances=1,
        coalesce=True,
        next_run_time=startup_time + timedelta(minutes=20),
    )
    scheduler.add_job(
        cleanup_expired_revoked_tokens,
        IntervalTrigger(hours=24),
        id="cleanup_revoked_tokens",
        max_instances=1,
        coalesce=True,
        next_run_time=startup_time + timedelta(minutes=30),
    )
    scheduler.add_job(
        cleanup_old_reports,
        IntervalTrigger(weeks=1),
        id="cleanup_old_reports",
        max_instances=1,
        coalesce=True,
        next_run_time=startup_time + timedelta(minutes=45),
    )
    scheduler.add_job(
        cleanup_expired_sessions,
        IntervalTrigger(hours=24),
        id="cleanup_sessions",
        max_instances=1,
        coalesce=True,
        next_run_time=startup_time + timedelta(minutes=35),
    )
    scheduler.add_job(
        cleanup_old_rate_limit_attempts,
        IntervalTrigger(hours=1),
        id="cleanup_rate_limit_attempts",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        cleanup_in_memory_caches,
        IntervalTrigger(minutes=5),
        id="cleanup_memory_caches",
        max_instances=1,
        coalesce=True,
        next_run_time=startup_time + timedelta(minutes=2),
    )

    logger.info(f"APScheduler: registered {len(scheduler.get_jobs())} jobs")
```

Key design notes:
- `max_instances=1` prevents overlapping runs if a job takes longer than its interval
- `coalesce=True` collapses missed runs (e.g., after a long shutdown) into a single execution
- `next_run_time=startup_time + timedelta(...)` replaces the `await asyncio.sleep(N)` startup delays
- All imports are inside `register_jobs()` to avoid circular imports at module load time

---

### Step 4: Refactor service classes to expose `run_once()`

Each class-based service needs a `run_once()` async method extracted from its current inner loop. The `start()/stop()` methods and the `asyncio.create_task()` call are deleted.

#### 4a: `AutoBuyMonitor` (`auto_buy_monitor.py`)

- Rename the body of the inner loop to `async def run_once(self)`
- Delete `start()`, `stop()`, `_task` attribute, the `while True` loop
- The module-level singleton `auto_buy_monitor = AutoBuyMonitor()` stays

#### 4b: `RebalanceMonitor` (`rebalance_monitor.py`)

- Same pattern as `AutoBuyMonitor`
- Expose `async def run_once(self)`
- Delete `start()`, `stop()`, task management

#### 4c: `ContentRefreshService` (`content_refresh_service.py`)

- Split the existing `_refresh_loop()` into two methods: `async def refresh_news(self)` and `async def refresh_videos(self)`
- These are the APScheduler job functions (called separately, no internal loop)
- Delete `start()`, `stop()`, `_task`, `_running`, `_refresh_loop()`
- Keep `_last_news_refresh` and `_last_video_refresh` timestamps (they are used in logging)

#### 4d: `DomainBlacklistService` (`domain_blacklist_service.py`)

- Extract inner loop body to `async def run_once(self)`
- Delete `start()`, `stop()`, `_task`, `_running`

#### 4e: `DebtCeilingMonitor` (`debt_ceiling_monitor.py`)

- Same pattern
- Extract to `async def run_once(self)`
- Delete `start()`, `stop()`, `_task`, `_running`

#### 4f: `TradingPairMonitor` (`delisted_pair_monitor.py`)

- Extract the check body to `async def run_once(self)`
- Delete `start()`, `stop()`, `_task`, `_running`
- Note: `trading_pair_monitor` is referenced in `system_router.py` via `set_trading_pair_monitor()` for manual force-refresh — this call path does not use `start()/stop()` so it is unaffected

---

### Step 5: Refactor standalone async functions

These functions in `cleanup_jobs.py` and `main.py` currently contain their own `while True` + `asyncio.sleep()` loops. Remove the loops; keep only the body.

#### Cleanup functions in `cleanup_jobs.py`:

For each of `cleanup_old_decision_logs`, `cleanup_failed_condition_logs`, `cleanup_old_failed_orders`, `cleanup_expired_revoked_tokens`, `cleanup_old_reports`, `cleanup_expired_sessions`, `cleanup_old_rate_limit_attempts`, `cleanup_in_memory_caches`:

- Remove `await asyncio.sleep(INITIAL_DELAY)` at the top
- Remove `while True:` wrapper
- Remove `await asyncio.sleep(INTERVAL)` at the bottom
- The function becomes: open DB session → do work → log → return
- Keep the `try/except Exception` block — APScheduler calls the error handler on exception, but explicit logging before re-raise (or swallowing the exception) is still good practice. **Do NOT re-raise** — a re-raised exception from a job function stops that job from ever running again. Log and return.

#### Inline functions in `main.py`:

`run_transfer_sync()` and `run_account_snapshot_capture()` are defined inline in `main.py`. Move their business logic to proper service modules:

- `run_account_snapshot_capture()` → extract to `backend/app/services/account_snapshot_service.py` as `async def run_account_snapshot_once()`
- `run_transfer_sync()` → extract to `backend/app/services/transfer_sync_service.py` as `async def run_transfer_sync_once()`

These inline functions in `main.py` are deleted entirely after extraction.

#### Standalone functions in service modules:

- `ban_monitor.py`: `ban_monitor_loop()` → extract body to `async def run_ban_monitor_once()`, delete the loop
- `report_scheduler.py`: `run_report_scheduler()` → extract body to `async def run_report_scheduler_once()`, delete the loop
- `coin_review_service.py`: `run_coin_review_scheduler()` → extract body to `async def run_coin_review_once()`, delete the loop

---

### Step 6: Update `main.py`

After the refactors above, `main.py` changes are:

**Imports — remove**:
```python
from app.cleanup_jobs import (
    cleanup_in_memory_caches,
    cleanup_old_rate_limit_attempts,
    cleanup_expired_revoked_tokens,
    cleanup_expired_sessions,
    cleanup_failed_condition_logs,
    cleanup_old_decision_logs,
    cleanup_old_failed_orders,
    cleanup_old_reports,
)
from app.services.coin_review_service import run_coin_review_scheduler
from app.services.report_scheduler import run_report_scheduler
from app.services.content_refresh_service import content_refresh_service
from app.services.debt_ceiling_monitor import debt_ceiling_monitor
from app.services.domain_blacklist_service import domain_blacklist_service
from app.services.auto_buy_monitor import AutoBuyMonitor
from app.services.rebalance_monitor import RebalanceMonitor
```

**Imports — add**:
```python
from app.scheduler import scheduler, register_jobs
```

**Global task handles — remove** (all of these become APScheduler-managed):
```python
decision_log_cleanup_task = None
failed_condition_cleanup_task = None
failed_order_cleanup_task = None
account_snapshot_task = None
revoked_token_cleanup_task = None
report_scheduler_task = None
report_cleanup_task = None
session_cleanup_task = None
rate_limit_cleanup_task = None
memory_cache_cleanup_task = None
transfer_sync_task = None
```

**`startup_event()` — replace all Tier 2/3 task creation** with:
```python
startup_time = datetime.utcnow()
register_jobs(startup_time)
scheduler.start()
logger.info(f"APScheduler started — {len(scheduler.get_jobs())} jobs registered")
```

Remove individual `asyncio.create_task()` calls for all Tier 2/3 tasks and the class `.start()` calls for `content_refresh_service`, `domain_blacklist_service`, `debt_ceiling_monitor`, `auto_buy_monitor`, `rebalance_monitor`, `trading_pair_monitor`, `perps_monitor` (if it was moved — confirm tier first).

**`shutdown_event()` — replace Tier 2/3 stop calls**:

Remove from the stop loop:
```python
content_refresh_service, domain_blacklist_service,
debt_ceiling_monitor, auto_buy_monitor, rebalance_monitor,
```

Add APScheduler shutdown:
```python
scheduler.shutdown(wait=False)
```

Remove all `_cancel_task()` calls for the task handles being deleted.

**Tier 1 tasks stay unchanged**:
- `price_monitor.start_async()` — keep
- `limit_order_monitor_task = asyncio.create_task(run_limit_order_monitor())` — keep
- `order_reconciliation_monitor_task` — keep
- `missing_order_detector_task` — keep
- `start_prop_guard_monitor()` — keep
- `perps_monitor.start()` — keep (confirm it's Tier 1; 60s interval puts it in Tier 1 per roadmap)

---

### Step 7: Remove dead `run_limit_order_monitor` / `run_order_reconciliation_monitor` inline functions from main.py

These are Tier 1 tasks and stay as `asyncio.create_task()`. They are NOT migrated. Only the Tier 2/3 inline functions (`run_account_snapshot_capture`, `run_transfer_sync`) are deleted.

---

## Files Modified

| File | Change |
|------|--------|
| `backend/requirements.txt` | Add `APScheduler>=3.10.0` |
| `backend/app/scheduler.py` | **New file** — scheduler singleton + `register_jobs()` |
| `backend/app/main.py` | Remove Tier 2/3 task creation; add `register_jobs()` + `scheduler.start/stop` |
| `backend/app/cleanup_jobs.py` | Remove `while True` + `asyncio.sleep()` from all 8 cleanup functions |
| `backend/app/services/auto_buy_monitor.py` | Extract `run_once()`, delete `start()/stop()` |
| `backend/app/services/rebalance_monitor.py` | Extract `run_once()`, delete `start()/stop()` |
| `backend/app/services/content_refresh_service.py` | Extract `refresh_news()` / `refresh_videos()`, delete class loop infrastructure |
| `backend/app/services/domain_blacklist_service.py` | Extract `run_once()`, delete `start()/stop()` |
| `backend/app/services/debt_ceiling_monitor.py` | Extract `run_once()`, delete `start()/stop()` |
| `backend/app/services/delisted_pair_monitor.py` | Extract `run_once()`, delete `start()/stop()` |
| `backend/app/services/ban_monitor.py` | Extract `run_ban_monitor_once()`, delete `ban_monitor_loop()` sleep loop |
| `backend/app/services/report_scheduler.py` | Extract `run_report_scheduler_once()`, delete sleep loop |
| `backend/app/services/coin_review_service.py` | Extract `run_coin_review_once()`, delete sleep loop |
| `backend/app/services/account_snapshot_service.py` | Add `run_account_snapshot_once()` (extracted from `main.py`) |
| `backend/app/services/transfer_sync_service.py` | Add `run_transfer_sync_once()` (extracted from `main.py`) |

---

## Test Plan

### Write tests before implementation (TDD)

1. **`backend/tests/test_scheduler.py`** — test `register_jobs()`, job count, job IDs, error listener behavior. Use `AsyncIOScheduler` in tests but do NOT call `scheduler.start()` — just inspect the registered jobs.

2. **`backend/tests/services/test_cleanup_jobs_as_functions.py`** — for each refactored cleanup function, test the happy path (job runs without error with mocked DB) and failure case (DB raises → function logs error → does NOT re-raise).

3. **Update existing tests** for any service that changes its interface (e.g., `test_auto_buy_monitor.py`, `test_rebalance_monitor.py`, `test_debt_ceiling_monitor.py`) — if they test `start()/stop()`, update to test `run_once()`.

### Validation commands

```bash
# Install dependency
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -m pip install "APScheduler>=3.10.0"
./venv/bin/python3 -c "import apscheduler; print(apscheduler.__version__)"

# Lint all changed files
./venv/bin/python3 -m flake8 app/scheduler.py app/cleanup_jobs.py app/main.py \
  app/services/auto_buy_monitor.py app/services/rebalance_monitor.py \
  app/services/content_refresh_service.py app/services/domain_blacklist_service.py \
  app/services/debt_ceiling_monitor.py app/services/delisted_pair_monitor.py \
  app/services/ban_monitor.py app/services/report_scheduler.py \
  app/services/coin_review_service.py app/services/account_snapshot_service.py \
  app/services/transfer_sync_service.py \
  --max-line-length=120

# Run affected tests
./venv/bin/python3 -m pytest tests/test_scheduler.py \
  tests/services/test_cleanup_jobs_as_functions.py \
  tests/services/test_auto_buy_monitor.py \
  tests/services/test_rebalance_monitor.py \
  tests/services/test_debt_ceiling_monitor.py \
  tests/services/test_ban_monitor.py \
  tests/test_cleanup_jobs.py \
  -v --timeout=30

# Import smoke test (catches circular imports and missing attributes)
./venv/bin/python3 -c "
from app.scheduler import scheduler, register_jobs
from datetime import datetime
register_jobs(datetime.utcnow())
jobs = scheduler.get_jobs()
print(f'Registered {len(jobs)} jobs:')
for j in jobs:
    print(f'  {j.id}: next_run={j.next_run_time}')
"
```

### Post-deploy verification

After `./bot.sh restart --dev --back-end`, check that:
1. Log output shows "APScheduler started — N jobs registered" (expect ~21 jobs)
2. No "APScheduler job X raised" errors appear in the first 5 minutes
3. Memory cache cleanup fires at startup+2m (check logs around that time)
4. The `ban_monitor` fires at startup+30s (check logs)
5. No `asyncio.CancelledError` on shutdown — APScheduler `shutdown(wait=False)` should be clean

---

## Rollback Plan

This is a code-only change (no migrations, no DB schema changes). Rollback is `git revert`.

If the deployed version shows job failures or startup errors:

1. `./bot.sh stop`
2. `git revert HEAD` (or `git checkout main -- backend/app/`)
3. `./bot.sh restart --dev --back-end`

The `asyncio.sleep()` sleep loops, while inferior, are known-working. APScheduler can be removed from `requirements.txt` if the revert is permanent. The venv package (`pip uninstall APScheduler`) is optional since unused imports don't cause runtime errors.

---

## Gotchas & Considerations

1. **`coalesce=True` behavior**: If the app is down for 2 hours and a 6-hour cleanup job was missed, APScheduler fires it once on startup (coalesced), not multiple times. This is correct behavior.

2. **`max_instances=1` is critical for cleanup jobs**: Without it, if a `cleanup_old_decision_logs` run takes longer than 24 hours (pathological case), APScheduler would start a second instance. With `max_instances=1` it skips the next scheduled run instead.

3. **Do NOT re-raise exceptions in job functions**: If a job function raises an unhandled exception, APScheduler logs it via the error listener but keeps the job scheduled. If the job re-raises after logging, APScheduler still catches it. But if you return `None` from the function (swallow the exception after logging), the job reschedules normally. All current cleanup functions already have `try/except Exception: logger.error(...)` — keep that pattern and ensure the except block does NOT re-raise.

4. **`TradingPairMonitor.set_trading_pair_monitor()`**: `system_router.py` holds a reference to the `TradingPairMonitor` instance for admin-triggered force-refresh. The APScheduler migration does not remove this reference — APScheduler just calls `trading_pair_monitor.run_once()` on schedule. Manual force-refresh via the admin endpoint continues to work unchanged.

5. **`ContentRefreshService` internal timestamps**: The `_last_news_refresh` and `_last_video_refresh` timestamps are used for logging ("last refreshed X minutes ago"). Keep these on the class. APScheduler replaces the scheduling, not the state.

6. **`auto_buy_monitor` and `rebalance_monitor` are imported as singletons in main.py**: After refactoring, `main.py` no longer needs to import or instantiate them. The `scheduler.py` module imports them directly via `from app.services.auto_buy_monitor import auto_buy_monitor`. Verify no double-import issues.

7. **Startup delay replacement**: The old code used `await asyncio.sleep(N)` at the top of each function to stagger startup. APScheduler's `next_run_time` parameter replaces this — pass `startup_time + timedelta(seconds=N)` when registering. The `startup_time` variable is captured once in `startup_event()` and passed to `register_jobs()`.

8. **APScheduler timezone**: `AsyncIOScheduler` defaults to UTC. All existing code uses `datetime.utcnow()`. No timezone conversion needed.

9. **Phase 1.1 dependency**: Phase 1.1 (task tiering) moves Tier 2/3 tasks to a secondary event loop / thread pool. If Phase 1.1 is not done yet, this PRP runs all jobs on the main event loop — which is still better than the status quo (no error isolation, clock drift) but doesn't achieve CPU separation. Run Phase 1.1 first if event loop contention is the primary driver.

10. **APScheduler 4.x vs 3.x**: The `APScheduler>=3.10.0` pin is intentional. APScheduler 4.x was released in beta in 2024 and has breaking API changes (different import paths, different trigger names). Stay on 3.x until 4.x is stable.

---

## References

- APScheduler docs: https://apscheduler.readthedocs.io/en/3.x/
- APScheduler `AsyncIOScheduler`: https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/asyncio.html
- APScheduler `IntervalTrigger`: https://apscheduler.readthedocs.io/en/3.x/modules/triggers/interval.html
- Scalability roadmap section 1.2: `/home/ec2-user/ZenithGrid/docs/SCALABILITY_ROADMAP.md`
- Existing cleanup job patterns: `/home/ec2-user/ZenithGrid/backend/app/cleanup_jobs.py`
- Existing singleton pattern: `/home/ec2-user/ZenithGrid/backend/app/services/websocket_manager.py`
- Current startup block: `/home/ec2-user/ZenithGrid/backend/app/main.py` lines 490–633
