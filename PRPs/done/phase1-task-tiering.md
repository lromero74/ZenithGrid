# PRP: Phase 1.1 — Tier the 27 Background Tasks by Priority

**Feature**: Separate the 27 asyncio background tasks into priority tiers so trading monitors get
CPU and DB pool priority over slow batch jobs
**Created**: 2026-03-21
**One-Pass Confidence Score**: 7/10

> Medium-complexity infrastructure change. The logic is simple (move tasks to a second event loop).
> The gotcha is asyncpg's event-loop binding — DB connections are tied to the loop that created the
> engine. The secondary loop needs its own engine. The PRP spells this out in full detail.

---

## Context & Goal

### Problem

All 27 asyncio background tasks share the FastAPI/uvicorn main event loop. A slow news fetch
(30-min content refresh) or a weekly coin review competes with bot monitoring and order fills for:

1. **CPU time** — the event loop is single-threaded; a long synchronous block in any task stalls all others
2. **DB pool connections** — PostgreSQL pool is `size=8, max_overflow=4` (12 total); slow batch tasks
   can exhaust all 12 connections, causing `pool_timeout=10s` exceptions during order fill processing

The 30-second DB pool timeout that appeared when saving a bot is a direct symptom. The scalability
roadmap (docs/SCALABILITY_ROADMAP.md, section 1.1) identifies this as the highest-priority fix.

### Solution

Assign every task to one of three priority tiers:

- **Tier 1** (real-time trading) — stays on the main FastAPI event loop, current behavior
- **Tier 2** (near-real-time) — moves to a secondary `asyncio` event loop in a dedicated daemon thread
- **Tier 3** (batch) — also moves to the secondary loop (same loop as Tier 2 is fine; they have long
  intervals and don't compete with each other)

The secondary loop gets its **own SQLAlchemy engine** with a smaller connection pool (size=3,
max_overflow=2 → 5 connections max), leaving the main pool's 12 connections exclusively for
Tier 1 tasks and API request handlers.

### What This Is Not

This is **not** APScheduler (that's Phase 1.2). This is a targeted structural fix with minimal
moving parts — one new thread, one new engine, relocate task startup calls. The tasks themselves
are not rewritten.

---

## Exact Task Tier Assignment

### Tier 1 — Main Event Loop (unchanged)

| Task | Start mechanism | Interval |
|------|----------------|----------|
| `MultiBotMonitor` (`price_monitor`) | `price_monitor.start_async()` | 10s |
| `LimitOrderMonitor` (`run_limit_order_monitor`) | `asyncio.create_task(...)` | 10s + 5m sweep |
| `OrderReconciliationMonitor` (`run_order_reconciliation_monitor`) | `asyncio.create_task(...)` | 60s |
| `PropGuardMonitor` (`start_prop_guard_monitor()`) | module function | 30s |
| `PerpsMonitor` (`perps_monitor`) | `perps_monitor.start()` | 60s |
| `MissingOrderDetector` (`run_missing_order_detector`) | `asyncio.create_task(...)` | 5m |

### Tier 2 — Secondary Loop (moved)

| Task | Current start mechanism | Interval |
|------|------------------------|----------|
| `AutoBuyMonitor` (`auto_buy_monitor`) | `auto_buy_monitor.start()` | continuous |
| `RebalanceMonitor` (`rebalance_monitor`) | `rebalance_monitor.start()` | continuous |
| `TransferSync` (`run_transfer_sync`) | `asyncio.create_task(...)` | daily (20m startup delay) |
| `AccountSnapshotService` (`run_account_snapshot_capture`) | `asyncio.create_task(...)` | daily (5m startup delay) |
| `BanMonitor` (`ban_monitor_loop`) | `asyncio.create_task(...)` | daily (30s startup delay) |
| `ReportScheduler` (`run_report_scheduler`) | `asyncio.create_task(...)` | 15m |

### Tier 3 — Secondary Loop (moved)

| Task | Current start mechanism | Interval |
|------|------------------------|----------|
| `ContentRefreshService` (`content_refresh_service`) | `content_refresh_service.start()` | 30m/60m |
| `DomainBlacklistService` (`domain_blacklist_service`) | `domain_blacklist_service.start()` | weekly |
| `DebtCeilingMonitor` (`debt_ceiling_monitor`) | `debt_ceiling_monitor.start()` | weekly |
| `TradingPairMonitor` (`trading_pair_monitor`) | `trading_pair_monitor.start()` | daily |
| `CoinReviewScheduler` (`run_coin_review_scheduler`) | `asyncio.create_task(...)` | 7 days |
| `DecisionLogCleanup` (`cleanup_old_decision_logs`) | `asyncio.create_task(...)` | daily (10m startup delay) |
| `FailedConditionCleanup` (`cleanup_failed_condition_logs`) | `asyncio.create_task(...)` | 6h |
| `FailedOrderCleanup` (`cleanup_old_failed_orders`) | `asyncio.create_task(...)` | 6h |
| `RevokedTokenCleanup` (`cleanup_expired_revoked_tokens`) | `asyncio.create_task(...)` | daily |
| `SessionCleanup` (`cleanup_expired_sessions`) | `asyncio.create_task(...)` | daily |
| `RateLimitCleanup` (`cleanup_old_rate_limit_attempts`) | `asyncio.create_task(...)` | unknown interval |
| `MemoryCacheCleanup` (`cleanup_in_memory_caches`) | `asyncio.create_task(...)` | 5m |
| `ReportCleanup` (`cleanup_old_reports`) | `asyncio.create_task(...)` | weekly |
| `ChangelogCacheRebuild` (`build_changelog_cache`) | synchronous call | startup only |

**Note on `ChangelogCacheRebuild`**: `build_changelog_cache()` is a synchronous function (`system_router.py`).
It should run in the secondary loop at startup via `loop.run_in_executor(None, build_changelog_cache)`
so it doesn't block the main loop during startup. Currently it runs synchronously on the main loop.

**Note on `TradingPairMonitor`**: Despite a 24h interval, it interacts with exchange APIs and can
take a long time on first run. Moving it to the secondary loop is the right call.

---

## Critical Architecture Gotcha: asyncpg Is Event-Loop Bound

**This is the most important implementation detail.** Do not skip it.

`asyncpg` (the async PostgreSQL driver) binds connections to the event loop that was active when
`create_async_engine()` was called. If a secondary event loop tries to use connections from an
engine created on the main loop, it raises:

```
asyncpg.exceptions._base.InterfaceError: cannot perform operation: another operation is in progress
# or
RuntimeError: Task attached to a different loop
```

**Solution**: Create a **second `create_async_engine`** instance inside the secondary thread, after
`asyncio.set_event_loop(secondary_loop)` is called. This second engine points to the same database
URL but has its own smaller connection pool and is bound to the secondary loop.

```python
# In the secondary thread's setup function (runs inside the secondary loop):
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings

_secondary_engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=3,          # Small — batch tasks don't need many connections
    max_overflow=2,        # 5 total max connections for all Tier 2/3 tasks
    pool_timeout=30,       # Batch tasks can wait longer
)
_secondary_session_maker = async_sessionmaker(
    _secondary_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)
```

The existing tasks use `app.database.async_session_maker` (imported from `app.database`). Tasks
running on the secondary loop must use `_secondary_session_maker` instead.

**Two approaches** to thread this through:

**Option A — Patch the module-level reference inside the thread (hacky, not recommended)**
Override `app.database.async_session_maker` after `asyncio.set_event_loop()`. Fragile.

**Option B — Dependency injection via a module-level secondary session accessor (recommended)**
Add a module-level variable in `app/database.py`:

```python
# app/database.py — new addition
_secondary_session_maker = None  # Set by secondary_loop.py on startup

def get_secondary_session_maker():
    """Return the secondary loop's session maker, or the primary if not yet initialized."""
    return _secondary_session_maker or async_session_maker

def set_secondary_session_maker(sm):
    global _secondary_session_maker
    _secondary_session_maker = sm
```

Tasks that move to the secondary loop import `get_secondary_session_maker()` and call it at
runtime (not at import time), so they always get the right session maker for their loop context.

**Option C — Simplest: create a new module `app/secondary_loop.py`**
The secondary loop module creates its own engine and session maker. Tasks running on the secondary
loop are passed the session maker as a parameter, OR the secondary loop module exposes a
`secondary_session_maker` that tasks import when they're on that loop.

**Recommendation**: Use Option C. Keep everything in a new `app/secondary_loop.py` file. The
tasks that move to the secondary loop need minimal changes — they just need to use the secondary
session maker.

---

## SQLite Note

On SQLite (not PostgreSQL), there is no connection pool and no asyncpg. `aiosqlite` does not have
the same event-loop binding restriction. However, this app runs PostgreSQL in production
(`settings.is_postgres`). The implementation should handle both:

```python
if settings.is_postgres:
    _secondary_engine_kwargs = {"pool_size": 3, "max_overflow": 2, "pool_timeout": 30}
else:
    _secondary_engine_kwargs = {"connect_args": {"check_same_thread": False}}
```

---

## Implementation Tasks

Complete these **in order**. Each task is independently testable.

### Task 1: Create `backend/app/secondary_loop.py`

New module that owns the secondary event loop and session maker.

```python
"""
secondary_loop.py — Dedicated asyncio event loop for Tier 2/3 background tasks.

Tier 2/3 tasks run here so they cannot exhaust the main loop's DB connection
pool or block order fill processing during heavy batch operations.
"""
import asyncio
import logging
import threading
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

logger = logging.getLogger(__name__)

_loop: Optional[asyncio.AbstractEventLoop] = None
_thread: Optional[threading.Thread] = None
_session_maker: Optional[async_sessionmaker] = None


def get_secondary_session_maker() -> async_sessionmaker:
    """Return the secondary loop's session maker. Must be called after loop is started."""
    if _session_maker is None:
        raise RuntimeError("Secondary loop not started — call start_secondary_loop() first")
    return _session_maker


def get_secondary_loop() -> asyncio.AbstractEventLoop:
    """Return the secondary event loop. Must be called after loop is started."""
    if _loop is None:
        raise RuntimeError("Secondary loop not started")
    return _loop


def schedule(coro) -> asyncio.Future:
    """Schedule a coroutine on the secondary event loop from the main thread."""
    if _loop is None:
        raise RuntimeError("Secondary loop not started")
    return asyncio.run_coroutine_threadsafe(coro, _loop)


def _run_loop(loop: asyncio.AbstractEventLoop):
    """Thread target: run the secondary event loop forever."""
    asyncio.set_event_loop(loop)
    loop.run_forever()


def start_secondary_loop():
    """
    Create and start the secondary event loop in a daemon thread.
    Also creates the secondary DB engine bound to that loop.
    Must be called from the main thread during FastAPI startup.
    """
    global _loop, _thread, _session_maker

    _loop = asyncio.new_event_loop()
    _thread = threading.Thread(target=_run_loop, args=(_loop,), daemon=True, name="secondary-loop")
    _thread.start()

    # Create engine + session maker bound to the secondary loop.
    # Must run inside the secondary loop so asyncpg binds to it.
    future = asyncio.run_coroutine_threadsafe(_init_secondary_engine(), _loop)
    future.result(timeout=30)  # Block until engine is ready
    logger.info("Secondary event loop started (Tier 2/3 tasks)")


async def _init_secondary_engine():
    """Initialize the DB engine on the secondary loop. Runs inside the secondary loop."""
    global _session_maker

    kwargs = {
        "echo": False,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }
    if settings.is_postgres:
        # Small pool — batch tasks don't need many connections.
        # Main pool (size=8, overflow=4) stays exclusively for Tier 1 + API handlers.
        kwargs["pool_size"] = 3
        kwargs["max_overflow"] = 2
        kwargs["pool_timeout"] = 30  # Batch tasks can wait longer
    else:
        kwargs["connect_args"] = {"check_same_thread": False}

    engine = create_async_engine(settings.database_url, **kwargs)
    _session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


def stop_secondary_loop():
    """Stop the secondary event loop. Called during FastAPI shutdown."""
    global _loop, _thread
    if _loop and _loop.is_running():
        _loop.call_soon_threadsafe(_loop.stop)
    if _thread:
        _thread.join(timeout=10)
    logger.info("Secondary event loop stopped")
```

### Task 2: Update task functions to accept an optional `session_maker` parameter

The tasks that move to the secondary loop currently hardcode `from app.database import async_session_maker`.
They need to be parameterized to accept an injected session maker.

**Pattern to use** (minimal change — add a `session_maker` parameter with a default):

```python
# Before (in cleanup_jobs.py, ban_monitor.py, etc.):
from app.database import async_session_maker
async with async_session_maker() as db:
    ...

# After:
from app.database import async_session_maker as _default_session_maker

async def cleanup_old_decision_logs(session_maker=None):
    sm = session_maker or _default_session_maker
    await asyncio.sleep(600)
    while True:
        try:
            async with sm() as db:
                ...
```

**Which files need this change:**
- `backend/app/cleanup_jobs.py` — all 8 cleanup functions
- `backend/app/services/ban_monitor.py` — `ban_monitor_loop()`
- `backend/app/services/report_scheduler.py` — `run_report_scheduler()`
- `backend/app/services/coin_review_service.py` — `run_coin_review_scheduler()`
- The `run_account_snapshot_capture()` and `run_transfer_sync()` coroutines in `main.py` — these can
  be extracted to their own module or updated in-place in `main.py`

**For class-based monitors** (AutoBuyMonitor, RebalanceMonitor, ContentRefreshService, etc.) that
call `async_session_maker` internally: pass the session maker to their `__init__` or add a
`set_session_maker(sm)` method. Check each class for where `async_session_maker` is used.

Files to inspect for `async_session_maker` usage:
- `backend/app/services/auto_buy_monitor.py`
- `backend/app/services/rebalance_monitor.py`
- `backend/app/services/content_refresh_service.py`
- `backend/app/services/domain_blacklist_service.py`
- `backend/app/services/debt_ceiling_monitor.py`
- `backend/app/services/delisted_pair_monitor.py`

### Task 3: Modify `startup_event()` in `main.py`

Split the startup block into Tier 1 (main loop) and Tier 2+3 (secondary loop).

```python
@app.on_event("startup")
async def startup_event():
    # ... existing boilerplate (JWT check, VACUUM, init_db) unchanged ...

    # ── TIER 1: Start on main event loop ──────────────────────────────────
    logger.info("Starting Tier 1 monitors (main event loop)...")

    await price_monitor.start_async()
    limit_order_monitor_task = asyncio.create_task(run_limit_order_monitor())
    order_reconciliation_monitor_task = asyncio.create_task(run_order_reconciliation_monitor())
    missing_order_detector_task = asyncio.create_task(run_missing_order_detector())
    await start_prop_guard_monitor()
    await perps_monitor.start()

    logger.info("Tier 1 monitors started")

    # ── Start secondary event loop ────────────────────────────────────────
    from app.secondary_loop import start_secondary_loop, schedule, get_secondary_session_maker
    start_secondary_loop()
    sm = get_secondary_session_maker()

    # ── TIER 2: Schedule on secondary loop ───────────────────────────────
    logger.info("Starting Tier 2 monitors (secondary event loop)...")

    # Class-based monitors: set secondary session maker, then schedule start()
    auto_buy_monitor.set_session_maker(sm)
    schedule(auto_buy_monitor.start())

    rebalance_monitor.set_session_maker(sm)
    schedule(rebalance_monitor.start())

    # Coroutine-based tasks: schedule with sm injected
    schedule(run_transfer_sync(session_maker=sm))
    schedule(run_account_snapshot_capture(session_maker=sm))
    schedule(ban_monitor_loop(session_maker=sm))
    schedule(run_report_scheduler(session_maker=sm))

    logger.info("Tier 2 monitors started on secondary loop")

    # ── TIER 3: Schedule on secondary loop ───────────────────────────────
    logger.info("Starting Tier 3 jobs (secondary event loop)...")

    content_refresh_service.set_session_maker(sm)
    schedule(content_refresh_service.start())

    domain_blacklist_service.set_session_maker(sm)
    schedule(domain_blacklist_service.start())

    debt_ceiling_monitor.set_session_maker(sm)
    schedule(debt_ceiling_monitor.start())

    trading_pair_monitor.set_session_maker(sm)
    schedule(trading_pair_monitor.start())

    schedule(run_coin_review_scheduler(session_maker=sm))
    schedule(cleanup_old_decision_logs(session_maker=sm))
    schedule(cleanup_failed_condition_logs(session_maker=sm))
    schedule(cleanup_old_failed_orders(session_maker=sm))
    schedule(cleanup_expired_revoked_tokens(session_maker=sm))
    schedule(cleanup_expired_sessions(session_maker=sm))
    schedule(cleanup_old_rate_limit_attempts(session_maker=sm))
    schedule(cleanup_in_memory_caches(session_maker=sm))
    schedule(cleanup_old_reports(session_maker=sm))

    # ChangelogCacheRebuild: synchronous call, run in thread pool on secondary loop
    import asyncio as _asyncio
    secondary_loop = get_secondary_loop()
    secondary_loop.call_soon_threadsafe(
        lambda: _asyncio.run_coroutine_threadsafe(
            asyncio.get_event_loop().run_in_executor(None, build_changelog_cache),
            secondary_loop
        )
    )
    # Simpler alternative: just keep build_changelog_cache() synchronous on main loop at startup
    # since it's startup-only and fast (git log is < 1s). Leave it on main loop.
    build_changelog_cache()  # Keep as-is: startup-only, fast, not a loop

    logger.info("Tier 3 jobs started on secondary loop")
    logger.info("Startup complete!")
```

**Note on `build_changelog_cache()`**: It's startup-only and runs `git log` (< 1 second). No need
to move it — leave it synchronous on the main startup path.

### Task 4: Update `shutdown_event()` in `main.py`

Add secondary loop teardown after stopping Tier 1 tasks.

```python
@app.on_event("shutdown")
async def shutdown_event():
    # ... existing shutdown logic (shutdown_manager, Tier 1 stops) ...

    # After all Tier 1 tasks are cancelled:
    from app.secondary_loop import stop_secondary_loop
    stop_secondary_loop()

    logger.info("Secondary event loop stopped - shutdown complete")
```

### Task 5: Handle tasks stored in module-level globals (shutdown cleanup)

Several Tier 2/3 tasks are assigned to module-level variables:
`decision_log_cleanup_task`, `failed_condition_cleanup_task`, etc. These are cancelled in
`shutdown_event()` via `_cancel_task()`.

When tasks run on the secondary loop, they are `asyncio.Future` objects (from
`run_coroutine_threadsafe`), not `asyncio.Task` objects. `Future.cancel()` works differently —
it sends a cancel signal but does not cooperate with `CancelledError` the same way.

**Recommended**: For Tier 2/3 tasks, stop them by stopping the loop (`stop_secondary_loop()`),
which cancels all running tasks on that loop. Remove the individual `_cancel_task()` calls for
Tier 2/3 from `shutdown_event()`. Only keep `_cancel_task()` for Tier 1 tasks.

Clean up the module-level task handles in `main.py`: remove handles for Tier 2/3 tasks since
they're now managed by the secondary loop, not by individual `asyncio.Task` references.

---

## Class-Based Monitor Changes

The class-based monitors that move to Tier 2/3 all call `async_session_maker` internally.
Add a `set_session_maker()` method to each:

### AutoBuyMonitor (Tier 2)

```python
# backend/app/services/auto_buy_monitor.py

class AutoBuyMonitor:
    def __init__(self):
        self.running = False
        self.task = None
        self._session_maker = None  # injected by secondary_loop startup
        ...

    def set_session_maker(self, sm):
        self._session_maker = sm

    def _get_sm(self):
        from app.database import async_session_maker as _default
        return self._session_maker or _default

    async def _some_method(self):
        sm = self._get_sm()
        async with sm() as db:
            ...
```

Apply the same pattern to: `RebalanceMonitor`, `ContentRefreshService`, `DomainBlacklistService`,
`DebtCeilingMonitor`, `TradingPairMonitor`.

**Note**: `start()` in these classes calls `asyncio.create_task(self._monitor_loop())`. When
`start()` is called from the secondary loop (via `schedule(auto_buy_monitor.start())`), the task
is created on the secondary loop — which is correct. No change needed to the `create_task` call.

---

## Files to Modify

| File | Change |
|------|--------|
| `backend/app/main.py` | Split startup into Tier 1/2/3 sections; call `start_secondary_loop()`; update shutdown |
| `backend/app/secondary_loop.py` | **New file** — secondary loop, engine, session maker |
| `backend/app/cleanup_jobs.py` | Add `session_maker=None` param to all 8 functions |
| `backend/app/services/auto_buy_monitor.py` | Add `set_session_maker()` / `_get_sm()` |
| `backend/app/services/rebalance_monitor.py` | Add `set_session_maker()` / `_get_sm()` |
| `backend/app/services/content_refresh_service.py` | Add `set_session_maker()` / `_get_sm()` |
| `backend/app/services/domain_blacklist_service.py` | Add `set_session_maker()` / `_get_sm()` |
| `backend/app/services/debt_ceiling_monitor.py` | Add `set_session_maker()` / `_get_sm()` |
| `backend/app/services/delisted_pair_monitor.py` | Add `set_session_maker()` / `_get_sm()` |
| `backend/app/services/ban_monitor.py` | Add `session_maker=None` to `ban_monitor_loop()` |
| `backend/app/services/report_scheduler.py` | Add `session_maker=None` to `run_report_scheduler()` |
| `backend/app/services/coin_review_service.py` | Add `session_maker=None` to `run_coin_review_scheduler()` |

The `run_account_snapshot_capture()` and `run_transfer_sync()` coroutines live inline in `main.py`.
Extract them to `backend/app/services/snapshot_service_runner.py` and
`backend/app/services/transfer_sync_runner.py`, or add `session_maker=None` params directly in `main.py`.

---

## Test Plan

### Before writing any implementation code: write these tests first (TDD)

#### Test 1: `tests/test_secondary_loop.py` — secondary loop lifecycle

```python
def test_secondary_loop_starts_and_stops():
    """Start and stop the secondary loop without error."""
    from app.secondary_loop import start_secondary_loop, stop_secondary_loop, get_secondary_loop
    start_secondary_loop()
    loop = get_secondary_loop()
    assert loop.is_running()
    stop_secondary_loop()
    # Loop should stop within 10s (daemon thread)

def test_secondary_loop_session_maker_is_distinct():
    """Secondary session maker must differ from the primary session maker."""
    from app.database import async_session_maker as primary
    from app.secondary_loop import start_secondary_loop, get_secondary_session_maker, stop_secondary_loop
    start_secondary_loop()
    secondary = get_secondary_session_maker()
    assert secondary is not primary, "Secondary must have its own engine and session maker"
    stop_secondary_loop()

def test_schedule_runs_coroutine_on_secondary_loop():
    """schedule() executes a coroutine on the secondary loop."""
    import asyncio
    from app.secondary_loop import start_secondary_loop, schedule, stop_secondary_loop
    start_secondary_loop()
    results = []

    async def _work():
        results.append(asyncio.get_event_loop())

    future = schedule(_work())
    future.result(timeout=5)
    assert len(results) == 1
    stop_secondary_loop()

def test_get_secondary_session_maker_before_start_raises():
    """Calling get_secondary_session_maker() before start raises RuntimeError."""
    import importlib
    import app.secondary_loop as sl
    sl._session_maker = None  # force uninitialized state
    with pytest.raises(RuntimeError, match="Secondary loop not started"):
        sl.get_secondary_session_maker()
```

#### Test 2: Cleanup job `session_maker` parameter injection

```python
# tests/test_cleanup_jobs.py (add to existing or create)

async def test_cleanup_decision_logs_uses_injected_session_maker():
    """cleanup_old_decision_logs() uses the provided session_maker, not the default."""
    calls = []

    class MockSM:
        def __call__(self):
            calls.append(1)
            return MockCtxMgr()

    # Run one iteration with short sleep and cancel
    import asyncio
    task = asyncio.create_task(cleanup_old_decision_logs(session_maker=MockSM()))
    await asyncio.sleep(0.1)
    task.cancel()
    assert len(calls) > 0, "MockSM was never called — injection failed"
```

#### Test 3: Monitor session maker injection

```python
def test_auto_buy_monitor_uses_injected_session_maker():
    """AutoBuyMonitor.set_session_maker() is used in _get_sm()."""
    from app.services.auto_buy_monitor import AutoBuyMonitor

    mock_sm = object()
    monitor = AutoBuyMonitor()
    monitor.set_session_maker(mock_sm)
    assert monitor._get_sm() is mock_sm

def test_auto_buy_monitor_falls_back_to_default_session_maker():
    """AutoBuyMonitor._get_sm() returns default when no injected SM."""
    from app.database import async_session_maker
    from app.services.auto_buy_monitor import AutoBuyMonitor

    monitor = AutoBuyMonitor()
    assert monitor._get_sm() is async_session_maker
```

#### Test 4: `main.py` startup smoke test

This is an integration test that verifies the secondary loop is started and Tier 1 tasks are
not moved. Use the existing `TestClient` fixture from `conftest.py`.

```python
async def test_secondary_loop_started_during_startup(test_client):
    """After startup, secondary loop must be running."""
    from app.secondary_loop import get_secondary_loop
    loop = get_secondary_loop()
    assert loop.is_running()
```

### Validation Gates

```bash
# 1. Lint all modified files
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m flake8 \
  --max-line-length=120 \
  app/secondary_loop.py \
  app/main.py \
  app/cleanup_jobs.py \
  app/services/auto_buy_monitor.py \
  app/services/rebalance_monitor.py \
  app/services/content_refresh_service.py \
  app/services/domain_blacklist_service.py \
  app/services/debt_ceiling_monitor.py \
  app/services/delisted_pair_monitor.py \
  app/services/ban_monitor.py \
  app/services/report_scheduler.py \
  app/services/coin_review_service.py

# 2. Type check
./venv/bin/python3 -m mypy app/secondary_loop.py --ignore-missing-imports

# 3. Run new secondary loop tests
./venv/bin/python3 -m pytest tests/test_secondary_loop.py -v

# 4. Run cleanup job tests
./venv/bin/python3 -m pytest tests/test_cleanup_jobs.py -v

# 5. Run full monitor tests to confirm nothing broken
./venv/bin/python3 -m pytest tests/services/test_auto_buy_monitor.py \
  tests/services/test_rebalance_monitor.py -v

# 6. Startup smoke test
./venv/bin/python3 -m pytest tests/test_main_startup.py -v

# 7. Full test suite (focused on changed modules)
./venv/bin/python3 -m pytest tests/ -k "secondary_loop or cleanup or auto_buy or rebalance or ban_monitor" -v
```

---

## Rollback Plan

This change is fully reversible. The rollback steps are:

1. Revert `main.py` to start all tasks with `asyncio.create_task()` on the main loop (original startup block)
2. Delete `backend/app/secondary_loop.py`
3. The `session_maker=None` default parameters added to cleanup functions are backwards compatible —
   they default to the original `async_session_maker`, so they do not need to be reverted immediately
4. The `set_session_maker()` methods added to monitor classes are also backwards compatible (no-op
   unless called)

The change is safe to deploy because:
- Tier 1 tasks are untouched — same loop, same behavior
- Tier 2/3 tasks do the same work, just on a different loop with a different DB pool
- The secondary DB pool is additive — total DB connections go from 12 to 17 (main 12 + secondary 5)
  which is still within PostgreSQL's `max_connections=25` headroom

**To verify after deploy:**
```bash
# Check secondary loop thread is running
ps aux | grep python  # look for main process
# Or add a /api/system/loop-status endpoint (optional, admin-only)

# Check DB connection count
psql -U zenithgrid_app -d zenithgrid -c \
  "SELECT count(*), state FROM pg_stat_activity WHERE datname='zenithgrid' GROUP BY state;"
# Should show ~12 main pool + up to 5 secondary pool connections under load

# Watch logs for pool timeout errors (should disappear)
sudo journalctl -u zenithgrid-backend -f | grep -i "pool\|timeout\|exhausted"
```

---

## Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| asyncpg loop-binding error if engine created on wrong loop | High | Create engine inside `_init_secondary_engine()` coroutine running on secondary loop |
| Secondary loop thread crash silently kills Tier 2/3 tasks | Medium | Daemon thread exits with the process; add `thread.is_alive()` health check to `/api/system/status` |
| `asyncio.run_coroutine_threadsafe` futures swallowing exceptions | Medium | Wrap `schedule()` calls in try/except; log `future.exception()` if set |
| Total DB connections exceed `max_connections=25` | Low | secondary pool size=3, max_overflow=2 → 5 max. Main pool=12. Total=17. Well within 25. |
| Shutdown race: secondary loop stops before in-flight batch work completes | Low | `stop_secondary_loop()` joins thread with 10s timeout; batch tasks handle interruption gracefully via existing exception handlers |
| SQLite (dev mode) has no pool exhaustion issue; this adds complexity for no gain | Low | The secondary loop still works on SQLite — no pool kwargs; adds minor overhead but is harmless |

---

## Connection Pool Budget (After Change)

| Pool | Engine | Size | Max Overflow | Max Connections |
|------|--------|------|--------------|-----------------|
| Main | `app.database.engine` | 8 | 4 | **12** |
| Secondary | `secondary_loop._secondary_engine` | 3 | 2 | **5** |
| Sync (migrations, balance API) | `app.database._sync_engine` | default | default | ~5 |
| **PostgreSQL total** | | | | **~22** (within max_connections=25) |

---

## Implementation Order (Summary)

1. Write tests first (`tests/test_secondary_loop.py`, add to `tests/test_cleanup_jobs.py`)
2. Create `backend/app/secondary_loop.py`
3. Add `session_maker=None` to all 8 cleanup functions in `cleanup_jobs.py`
4. Add `session_maker=None` to `ban_monitor_loop`, `run_report_scheduler`, `run_coin_review_scheduler`
5. Add `set_session_maker()` / `_get_sm()` to all 6 class-based monitors
6. Add `session_maker` param to `run_account_snapshot_capture` and `run_transfer_sync` in `main.py`
7. Refactor `startup_event()` in `main.py` — Tier 1 block, then secondary loop start, then Tier 2/3 block
8. Refactor `shutdown_event()` in `main.py` — add `stop_secondary_loop()`; remove Tier 2/3 `_cancel_task()` calls
9. Run all validation gates
10. Deploy: `./bot.sh restart --prod` (backend change)
11. Verify DB connection counts and absence of pool timeout errors in logs

---

## References

- Roadmap: `docs/SCALABILITY_ROADMAP.md` section 1.1
- Main loop: `backend/app/main.py` lines 491–633 (startup_event)
- DB pool config: `backend/app/database.py` lines 17–34
- asyncpg event-loop binding: https://magicstack.github.io/asyncpg/current/usage.html#connection-pools
- Python threading + asyncio: https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.run_coroutine_threadsafe
- SQLAlchemy async engine: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html

---

## Quality Checklist

- [x] All necessary context included (asyncpg loop-binding gotcha fully documented)
- [x] Validation gates are executable by AI
- [x] References existing patterns (class-based monitor pattern, `async_session_maker` usage)
- [x] Clear implementation path (10-step ordered task list)
- [x] Error handling documented (risks table, rollback plan, pool budget math)
- [x] TDD: tests listed before implementation tasks
- [x] Backwards compatible: `session_maker=None` defaults preserve existing behavior
