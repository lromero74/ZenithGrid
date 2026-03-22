# PRP: Phase 1.3 — Separate Read Connection Pool for Analytics

**Feature**: Create a dedicated async connection pool for analytics/read-only queries, routing report and account-value reads away from the shared write pool
**Created**: 2026-03-21
**One-Pass Confidence Score**: 9/10

---

## Context & Goal

### Problem

The production PostgreSQL pool is configured at `pool_size=8, max_overflow=4` (12 max connections) on a t2.micro with `max_connections=25`. Heavy aggregate queries from report generation, goal snapshots, and market metrics compete with order-fill writes for these same 12 slots. When the multi-bot monitor runs many pairs simultaneously, DB pool exhaustion has already caused HTTP timeouts (the root cause of the 30-second pool timeout added in the current `database.py`).

The SCALABILITY_ROADMAP.md section 1.3 documents this precisely: "Report generation, goal snapshots, and market metrics do heavy aggregate queries (SUM, GROUP BY, window functions) against the same connection pool that handles order fills."

### Solution

Introduce a second `async_session_maker` — `read_async_session_maker` — backed by a separate SQLAlchemy engine (`read_engine`) pointing at the same `settings.database_url` but configured with:
- `execution_options={"postgresql_readonly": True}` — signals read-intent to the DB driver
- `pool_size=4, max_overflow=2` — 6 max connections, a separate budget from the write pool
- Same `pool_pre_ping`, `pool_recycle`, `pool_timeout` settings as the write engine

Expose a `get_read_db()` dependency in `database.py`. Route the following analytics consumers to `get_read_db()` instead of `get_db()`:
- All **GET endpoints** in `reports_router.py` (goals list, schedules list, reports list, goal trends, snapshot history, preview, etc.)
- All **GET endpoints** in `account_value_router.py` (history, latest, activity)
- `market_metrics_service.py` — already uses `async_session_maker` directly; switch to `read_async_session_maker`
- `report_data_service.py` — its `gather_report_data()` receives a session as a parameter; callers (`report_scheduler.py`) will pass a read session

**Write endpoints** (`POST /goals`, `PUT /goals/:id`, `DELETE`, `POST /capture`, etc.) continue using `get_db()` — they need write access.

### What This Is Not

This is a zero-infrastructure change. It does **not** require:
- A PostgreSQL streaming replica
- New EC2 instances
- Any migration
- Any schema change

### Medium-Term Note (Document, Don't Implement)

The next step after this is a true PostgreSQL streaming replica:
1. Set up `pg_basebackup` + replication slot on the primary
2. Change `settings.read_database_url` to point at the replica
3. `read_engine` already uses that URL — no application code change needed beyond adding the config field

---

## Existing Code Patterns (Reference)

### Current engine/session setup (`database.py`)

```python
engine = create_async_engine(settings.database_url, **_engine_kwargs)

async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)

async def get_db():
    async with async_session_maker() as session:
        yield session
```

The write pool kwargs for PostgreSQL:
```python
_engine_kwargs = {
    "echo": False,
    "pool_pre_ping": True,
    "pool_recycle": 3600,
    "pool_size": 8,
    "max_overflow": 4,
    "pool_timeout": 10,
}
```

### How consumers currently use sessions

**Routers** receive sessions via FastAPI `Depends(get_db)`:
```python
# reports_router.py, account_value_router.py
from app.database import get_db
...
db: AsyncSession = Depends(get_db),
```

**Background services** create sessions directly via `async_session_maker`:
```python
# market_metrics_service.py
from app.database import async_session_maker
...
async with async_session_maker() as db:
    ...

# report_scheduler.py
from app.database import async_session_maker
...
async with async_session_maker() as db:
    ...
```

**Report data service** receives a session as an injected parameter — the session is created by the scheduler:
```python
# report_data_service.py
async def gather_report_data(db: AsyncSession, ...) -> Dict[str, Any]:
```

### Read vs write endpoint classification in `reports_router.py`

Read (safe to route to read pool — 22 endpoints):
- `GET /goals`, `GET /goals/{id}`, `GET /goals/{id}/trend`
- `GET /schedules`, `GET /schedules/{id}`
- `GET /history`, `GET /history/{id}`, `GET /history/{id}/html`, `GET /history/{id}/pdf`
- `GET /expense-items/{goal_id}`, `GET /expense-items/{goal_id}/categories`
- `GET /snapshot-history/{goal_id}`, `GET /backfill-history/{goal_id}`
- `GET /preview/{schedule_id}` (read-heavy: fetches goals, reports, snapshots)

Write (must stay on write pool — 9 endpoints):
- `POST /goals`, `PUT /goals/{id}`, `DELETE /goals/{id}`
- `POST /schedules`, `PUT /schedules/{id}`, `DELETE /schedules/{id}`
- `POST /expense-items/{goal_id}`, `PUT /expense-items/{goal_id}/{item_id}`, `DELETE /expense-items/{goal_id}/{item_id}`
- `POST /generate` (creates a Report row, runs the scheduler)

Read endpoints in `account_value_router.py`:
- `GET /history`, `GET /latest`, `GET /activity`

Write endpoints in `account_value_router.py`:
- `POST /capture` (writes AccountValueSnapshot rows)
- `GET /reservations` (reads but also calls exchange API — keep on write pool to avoid holding read connections during external I/O)

---

## Implementation Blueprint

### TDD Order: Tests First

**Step 0 must be writing failing tests.** Implementation begins at Step 5.

---

### Step 1 — Write `test_database_read_pool.py` (failing)

Create `backend/tests/test_database_read_pool.py`. All tests fail until Step 5 implements the code.

```python
"""
Tests for the separate read connection pool introduced in Phase 1.3.

Verifies:
1. read_engine and engine are distinct objects
2. read_async_session_maker and async_session_maker are distinct objects
3. get_read_db() yields a session backed by the read engine
4. get_db() yields a session backed by the write engine
5. The read engine has postgresql_readonly execution option set (PostgreSQL only)
6. The read engine pool is smaller than the write engine pool
"""
import pytest
from unittest.mock import patch, MagicMock

from app.database import (
    async_session_maker,
    engine,
    get_db,
    get_read_db,
    read_async_session_maker,
    read_engine,
)


class TestReadEngineIsDistinct:
    """read_engine must be a separate engine object from the write engine."""

    def test_read_engine_is_not_write_engine(self):
        """Happy path: read_engine and engine are different objects."""
        assert read_engine is not engine

    def test_read_session_maker_is_not_write_session_maker(self):
        """Happy path: read_async_session_maker differs from async_session_maker."""
        assert read_async_session_maker is not async_session_maker


class TestReadEnginePoolConfig:
    """Read pool is sized smaller than the write pool (PostgreSQL only)."""

    def test_read_pool_size_is_smaller_than_write_pool(self):
        """Happy path: read pool_size <= write pool_size."""
        from app.config import settings

        if not settings.is_postgres:
            pytest.skip("Pool size check only applies to PostgreSQL")

        write_pool = engine.pool
        read_pool = read_engine.pool

        assert read_pool.size() <= write_pool.size()

    def test_read_pool_max_overflow_is_smaller_than_write(self):
        """Edge case: read max_overflow <= write max_overflow."""
        from app.config import settings

        if not settings.is_postgres:
            pytest.skip("Pool overflow check only applies to PostgreSQL")

        write_pool = engine.pool
        read_pool = read_engine.pool

        assert read_pool._max_overflow <= write_pool._max_overflow


class TestGetReadDbDependency:
    """get_read_db() must yield an AsyncSession from the read pool."""

    @pytest.mark.asyncio
    async def test_get_read_db_yields_session(self):
        """Happy path: get_read_db() yields an AsyncSession."""
        from sqlalchemy.ext.asyncio import AsyncSession

        gen = get_read_db()
        session = await gen.__anext__()
        assert isinstance(session, AsyncSession)
        try:
            await gen.aclose()
        except StopAsyncIteration:
            pass

    @pytest.mark.asyncio
    async def test_get_db_and_get_read_db_yield_different_sessions(self):
        """Happy path: get_db() and get_read_db() yield sessions from different pools."""
        write_gen = get_db()
        read_gen = get_read_db()

        write_session = await write_gen.__anext__()
        read_session = await read_gen.__anext__()

        # They must be distinct session objects
        assert write_session is not read_session

        # They must be bound to different engines
        assert write_session.bind is not read_session.bind

        try:
            await write_gen.aclose()
            await read_gen.aclose()
        except StopAsyncIteration:
            pass

    @pytest.mark.asyncio
    async def test_get_read_db_session_is_bound_to_read_engine(self):
        """Edge case: read session's engine is read_engine, not engine."""
        gen = get_read_db()
        session = await gen.__anext__()

        # The session's bind should trace back to read_engine
        assert session.get_bind() is read_engine.sync_engine or \
               session.sync_session.bind is read_engine.sync_engine

        try:
            await gen.aclose()
        except StopAsyncIteration:
            pass


class TestReadOnlyExecutionOption:
    """The read engine has postgresql_readonly set (PostgreSQL only)."""

    def test_read_engine_has_readonly_execution_option(self):
        """Happy path: read_engine carries postgresql_readonly=True."""
        from app.config import settings

        if not settings.is_postgres:
            pytest.skip("postgresql_readonly only applies to PostgreSQL")

        opts = read_engine.get_execution_options()
        assert opts.get("postgresql_readonly") is True

    def test_write_engine_does_not_have_readonly_option(self):
        """Edge case: the write engine must NOT have postgresql_readonly set."""
        opts = engine.get_execution_options()
        assert opts.get("postgresql_readonly") is not True
```

---

### Step 2 — Write `test_reports_router_uses_read_db.py` (failing)

Create `backend/tests/routers/test_reports_router_uses_read_db.py`.

```python
"""
Tests that analytics GET endpoints in reports_router use get_read_db,
and that write endpoints continue to use get_db.

We verify this by inspecting the FastAPI dependency overrides that are
registered on each endpoint's dependant tree — if get_read_db is in
the dependency set for a GET endpoint, the routing is correct.
"""
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.database import get_db, get_read_db


def _get_dependency_callables(route: APIRoute) -> set:
    """Collect all dependency callables from a route's dependant tree."""
    callables = set()
    stack = [route.dependant]
    while stack:
        dep = stack.pop()
        for d in dep.dependencies:
            if d.call is not None:
                callables.add(d.call)
            stack.append(d.dependant)
    return callables


def _find_route(app: FastAPI, method: str, path: str) -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and method in route.methods and route.path == path:
            return route
    raise AssertionError(f"Route {method} {path} not found")


@pytest.fixture
def app():
    """Import the FastAPI app for dependency inspection."""
    from app.main import app as _app
    return _app


class TestReportsRouterReadEndpointsUseReadDb:
    """GET endpoints that are read-only must use get_read_db, not get_db."""

    @pytest.mark.parametrize("path", [
        "/api/reports/goals",
        "/api/reports/schedules",
        "/api/reports/history",
    ])
    def test_get_endpoint_uses_get_read_db(self, app, path):
        """Happy path: GET list endpoints declare get_read_db as a dependency."""
        route = _find_route(app, "GET", path)
        deps = _get_dependency_callables(route)
        assert get_read_db in deps, (
            f"GET {path} should use get_read_db but found: {deps}"
        )
        assert get_db not in deps, (
            f"GET {path} should NOT use get_db but it does"
        )

    @pytest.mark.parametrize("path", [
        "/api/reports/goals",
        "/api/reports/schedules",
    ])
    def test_post_endpoint_uses_get_db(self, app, path):
        """Edge case: POST write endpoints must still use get_db."""
        route = _find_route(app, "POST", path)
        deps = _get_dependency_callables(route)
        assert get_db in deps, (
            f"POST {path} should use get_db but found: {deps}"
        )
        assert get_read_db not in deps, (
            f"POST {path} should NOT use get_read_db but it does"
        )


class TestAccountValueRouterReadEndpointsUseReadDb:
    """GET endpoints in account_value_router must use get_read_db."""

    @pytest.mark.parametrize("path", [
        "/api/account-value/history",
        "/api/account-value/latest",
        "/api/account-value/activity",
    ])
    def test_get_endpoint_uses_get_read_db(self, app, path):
        """Happy path: read GET endpoints use get_read_db."""
        route = _find_route(app, "GET", path)
        deps = _get_dependency_callables(route)
        assert get_read_db in deps, (
            f"GET {path} should use get_read_db but found: {deps}"
        )

    def test_capture_post_endpoint_uses_get_db(self, app):
        """Failure case: POST /capture is a write endpoint and must use get_db."""
        route = _find_route(app, "POST", "/api/account-value/capture")
        deps = _get_dependency_callables(route)
        assert get_db in deps
        assert get_read_db not in deps
```

---

### Step 3 — Write `test_market_metrics_read_pool.py` (failing)

Create `backend/tests/services/test_market_metrics_read_pool.py`.

```python
"""
Tests that market_metrics_service uses the read session maker for its
DB operations (snapshot recording and pruning).
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestMarketMetricsUsesReadSessionMaker:
    """market_metrics_service must import and use read_async_session_maker."""

    def test_module_imports_read_async_session_maker(self):
        """Happy path: the service imports read_async_session_maker from app.database."""
        import importlib, inspect
        import app.services.market_metrics_service as mod

        src = inspect.getsource(mod)
        assert "read_async_session_maker" in src, (
            "market_metrics_service.py must import and use read_async_session_maker"
        )

    def test_module_does_not_import_write_session_maker_for_reads(self):
        """Edge case: async_session_maker should not be used for snapshot reads."""
        import inspect
        import app.services.market_metrics_service as mod

        src = inspect.getsource(mod)
        # async_session_maker should not appear in service-level db opens
        # (it may still appear in imports to satisfy IDE/linting, but must not
        # be called as a context manager for reads)
        assert "async with async_session_maker" not in src, (
            "market_metrics_service must not use write async_session_maker for reads"
        )


class TestMarketMetricsSnapshotUsesReadDb:
    """Snapshot recording uses the read session via read_async_session_maker."""

    @pytest.mark.asyncio
    @patch("app.services.market_metrics_service.read_async_session_maker")
    async def test_record_snapshot_opens_read_session(self, mock_session_maker):
        """Happy path: record_metric_snapshot opens a session via read_async_session_maker."""
        from app.services.market_metrics_service import record_metric_snapshot

        mock_session = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(
            return_value=MagicMock(first=MagicMock(return_value=None))
        )))
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        await record_metric_snapshot("fear_greed_index", 55.0)

        mock_session_maker.assert_called_once()
```

---

### Step 4 — Confirm all three test files FAIL

```bash
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -m pytest tests/test_database_read_pool.py \
    tests/routers/test_reports_router_uses_read_db.py \
    tests/services/test_market_metrics_read_pool.py -v 2>&1 | tail -30
```

Expected: `ImportError: cannot import name 'get_read_db' from 'app.database'` and similar failures. This confirms the tests are genuinely testing the unimplemented behavior.

---

### Step 5 — Implement `read_engine` and `get_read_db()` in `database.py`

Add after the existing `engine` and `async_session_maker` block:

```python
# Read-only connection pool for analytics queries.
# Separate pool budget (size=4, overflow=2) so aggregate queries in
# reports/account-value never compete with trading writes for connections.
# Points at the SAME database — zero-infrastructure change.
# Medium-term: change settings.database_url here to a replica URL.
_read_engine_kwargs = {
    "echo": False,
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}

if settings.is_postgres:
    _read_engine_kwargs["pool_size"] = 4
    _read_engine_kwargs["max_overflow"] = 2
    _read_engine_kwargs["pool_timeout"] = 10
    _read_engine_kwargs["execution_options"] = {"postgresql_readonly": True}
else:
    _read_engine_kwargs["connect_args"] = {"check_same_thread": False}

read_engine = create_async_engine(settings.database_url, **_read_engine_kwargs)

read_async_session_maker = async_sessionmaker(
    read_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_read_db():
    """Read-only DB session dependency for analytics endpoints.

    Routes to the separate read connection pool (size=4, overflow=2).
    On PostgreSQL, sessions carry the postgresql_readonly execution option.
    On SQLite (tests), same database — no-op distinction from get_db().
    """
    async with read_async_session_maker() as session:
        yield session
```

**Important**: On SQLite (tests), `execution_options={"postgresql_readonly": True}` is silently ignored by aiosqlite — no special handling needed.

---

### Step 6 — Update `reports_router.py`

Change the import line and swap `get_db` → `get_read_db` on all read-only endpoints.

**Import change** (line 22):
```python
# Before:
from app.database import get_db

# After:
from app.database import get_db, get_read_db
```

**Endpoint changes** — swap `Depends(get_db)` → `Depends(get_read_db)` for every `@router.get` endpoint. Write endpoints (`@router.post`, `@router.put`, `@router.delete`) keep `Depends(get_db)`.

Read endpoints to update (use `get_read_db`):
- `GET /goals` (`list_goals`)
- `GET /goals/{goal_id}` (`get_goal`)
- `GET /goals/{goal_id}/trend` (`get_goal_trend`)
- `GET /schedules` (`list_schedules`)
- `GET /schedules/{schedule_id}` (`get_schedule`)
- `GET /history` (`list_reports`)
- `GET /history/{report_id}` (`get_report`)
- `GET /history/{report_id}/html` (`get_report_html`)
- `GET /history/{report_id}/pdf` (`download_report_pdf`)
- `GET /expense-items/{goal_id}` (`list_expense_items`)
- `GET /expense-items/{goal_id}/categories` (`list_expense_categories`)
- `GET /snapshot-history/{goal_id}` (`get_snapshot_history`)
- `GET /backfill-history/{goal_id}` (`get_backfill_history`)
- `GET /preview/{schedule_id}` (`preview_report`)

Write endpoints that keep `get_db` (no change):
- `POST /goals`, `PUT /goals/{goal_id}`, `DELETE /goals/{goal_id}`
- `POST /schedules`, `PUT /schedules/{schedule_id}`, `DELETE /schedules/{schedule_id}`
- `POST /expense-items/{goal_id}`, `PUT /.../{item_id}`, `DELETE /.../{item_id}`
- `POST /generate`

---

### Step 7 — Update `account_value_router.py`

```python
# Before:
from app.database import get_db

# After:
from app.database import get_db, get_read_db
```

Swap `Depends(get_db)` → `Depends(get_read_db)` on:
- `GET /history` (`get_account_value_history`)
- `GET /latest` (`get_latest_snapshot`)
- `GET /activity` (`get_daily_activity`)

Keep `Depends(get_db)` on:
- `POST /capture` (`capture_snapshots`) — writes AccountValueSnapshot rows
- `GET /reservations` (`get_bidirectional_reservations`) — calls exchange API during the session; keep on write pool to avoid holding read connections during external I/O

---

### Step 8 — Update `market_metrics_service.py`

```python
# Before:
from app.database import async_session_maker

# After:
from app.database import read_async_session_maker
```

Replace all `async with async_session_maker() as db:` calls with `async with read_async_session_maker() as db:`.

There are 3 call sites (lines 93, 113, 804 in the current file). All of them are reads or snapshot inserts that belong on the analytics pool.

---

### Step 9 — Update `report_scheduler.py`

The scheduler creates its own sessions via `async_session_maker`. For the data-gathering phase (reading positions, snapshots, goals for report generation) it should use `read_async_session_maker`. For writing the resulting `Report` row it continues to use the write pool.

```python
# Before:
from app.database import async_session_maker

# After:
from app.database import async_session_maker, read_async_session_maker
```

In `_run_schedule()` (or equivalent), open two sessions:
- `async with read_async_session_maker() as read_db:` — passed to `gather_report_data()`
- `async with async_session_maker() as write_db:` — used to `db.add(report)` and `commit()`

If the scheduler currently uses a single session for both reading and writing, split it. The `gather_report_data()` signature accepts a session argument — no service-layer change needed.

---

### Step 10 — Run the failing tests; confirm they now pass

```bash
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -m pytest \
    tests/test_database_read_pool.py \
    tests/routers/test_reports_router_uses_read_db.py \
    tests/services/test_market_metrics_read_pool.py \
    -v
```

All tests must be green.

---

### Step 11 — Run related existing tests to confirm no regressions

```bash
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -m pytest \
    tests/routers/test_reports_router.py \
    tests/routers/test_account_value_router.py \
    tests/services/test_goal_snapshot_service.py \
    tests/services/test_market_metrics_service.py \
    -v
```

---

### Step 12 — Lint

```bash
cd /home/ec2-user/ZenithGrid/backend
./venv/bin/python3 -m flake8 --max-line-length=120 \
    app/database.py \
    app/routers/reports_router.py \
    app/routers/account_value_router.py \
    app/services/market_metrics_service.py \
    app/services/report_scheduler.py \
    tests/test_database_read_pool.py \
    tests/routers/test_reports_router_uses_read_db.py \
    tests/services/test_market_metrics_read_pool.py
```

---

### Step 13 — Update `docs/architecture.json`

Add `read_engine` and `get_read_db` to the `database` section of the architecture document.

---

## Files to Modify

| File | Change |
|------|--------|
| `backend/app/database.py` | Add `read_engine`, `read_async_session_maker`, `get_read_db()` |
| `backend/app/routers/reports_router.py` | Import `get_read_db`; swap all GET endpoints to `Depends(get_read_db)` |
| `backend/app/routers/account_value_router.py` | Import `get_read_db`; swap 3 GET endpoints to `Depends(get_read_db)` |
| `backend/app/services/market_metrics_service.py` | Import `read_async_session_maker`; replace 3 `async_session_maker` call sites |
| `backend/app/services/report_scheduler.py` | Import `read_async_session_maker`; use it for data-gathering phase |
| `docs/architecture.json` | Add `read_engine`, `get_read_db` to database section |
| `CHANGELOG.md` | Add entry under new version |

## New Test Files

| File | What It Tests |
|------|---------------|
| `backend/tests/test_database_read_pool.py` | `read_engine` distinctness, pool sizing, `get_read_db()` session isolation, `postgresql_readonly` execution option |
| `backend/tests/routers/test_reports_router_uses_read_db.py` | GET endpoints use `get_read_db`, POST/PUT/DELETE endpoints use `get_db` |
| `backend/tests/services/test_market_metrics_read_pool.py` | `market_metrics_service` uses `read_async_session_maker` |

---

## Edge Cases & Gotchas

### 1. SQLite in tests — `postgresql_readonly` is silently ignored

aiosqlite does not implement `postgresql_readonly`. The execution option is passed but has no effect. This is fine — test sessions get all the isolation benefits (separate engine, separate pool) while running on SQLite. The `TestReadOnlyExecutionOption` tests skip themselves if `not settings.is_postgres`.

### 2. Read sessions must NOT be used for writes

Any attempt to write via a `get_read_db()` session on PostgreSQL will fail at the server level with `ERROR: cannot execute INSERT in a read-only transaction`. This is the desired behavior — it prevents analytics paths from accidentally writing. In tests (SQLite), writes would succeed because SQLite ignores the flag, so don't accidentally write in analytics endpoint tests.

### 3. `GET /reservations` stays on write pool

The `/api/account-value/reservations` endpoint calls `get_exchange_client_for_account()`, which may do additional DB lookups during external I/O. Holding a read connection open during HTTP requests to Coinbase is wasteful and burns the small read pool. Keep it on `get_db()`.

### 4. `report_scheduler.py` session split

The scheduler's `_run_schedule()` currently opens a single session for read + write. After this change it uses two sessions. The `gather_report_data()` call receives the read session; the final `db.add(report); await db.commit()` uses the write session. The two sessions must NOT share a transaction. This is straightforward — they are completely independent `async with` blocks.

### 5. Pool sizing rationale

Write pool: `size=8, overflow=4` = 12 max connections
Read pool: `size=4, overflow=2` = 6 max connections
Total theoretical max: 18 connections against `max_connections=25`. Leaves 7 for:
- 1 sync engine (`get_sync_engine()`) — used by balance API
- psql admin connections
- Future migration tooling

This is comfortably within limits.

### 6. `pool_recycle` and `pool_pre_ping` on read engine

Both are set identically to the write engine. `pool_recycle=3600` prevents stale connections. `pool_pre_ping=True` adds one lightweight `SELECT 1` per borrowed connection to detect dropped connections. These are cheap and correct for the read pool.

### 7. No SQLite WAL listener needed on read engine

The WAL pragma listener is registered on `engine.sync_engine`. The read engine for SQLite (tests only) does not need it — SQLite WAL mode is a database-level setting, not per-connection.

### 8. `goal_snapshot_service.py` — NOT changed

`capture_goal_snapshots()` and `backfill_goal_snapshots()` receive a `db: AsyncSession` parameter injected by their callers. They write `GoalProgressSnapshot` rows — these are writes. The caller (`account_snapshot_service.py`) passes a write session from `async_session_maker`. Leave unchanged.

### 9. Dependency inspection tests require the full app to be importable

`test_reports_router_uses_read_db.py` imports `app.main` to get the FastAPI app. If test isolation is needed, ensure the app fixture doesn't start background tasks. The existing `db_session` fixture isolation in conftest.py handles this correctly.

---

## Medium-Term Path to Real Replica (Document Only)

When load justifies a streaming replica:

1. Add `READ_DATABASE_URL` to `backend/app/config.py`:
   ```python
   read_database_url: str = ""  # Falls back to database_url if empty
   ```

2. In `database.py`, use `settings.read_database_url or settings.database_url` for `read_engine`:
   ```python
   _read_db_url = getattr(settings, "read_database_url", "") or settings.database_url
   read_engine = create_async_engine(_read_db_url, **_read_engine_kwargs)
   ```

3. Set up the replica:
   ```bash
   # On primary
   pg_basebackup -h localhost -D /var/lib/postgresql/replica -P -U replicator --wal-method=stream
   # On replica, configure recovery.conf / postgresql.auto.conf
   ```

4. Set `READ_DATABASE_URL=postgresql+asyncpg://...@replica-host/zenithgrid` in `.env`.

No application code changes beyond step 2 — all analytics paths already point at `read_engine`.

---

## Validation Gates

```bash
cd /home/ec2-user/ZenithGrid/backend

# 1. New tests pass (TDD: these must be written and failing first)
./venv/bin/python3 -m pytest \
    tests/test_database_read_pool.py \
    tests/routers/test_reports_router_uses_read_db.py \
    tests/services/test_market_metrics_read_pool.py \
    -v

# 2. No regressions in affected modules
./venv/bin/python3 -m pytest \
    tests/routers/test_reports_router.py \
    tests/routers/test_account_value_router.py \
    tests/services/test_goal_snapshot_service.py \
    tests/services/test_market_metrics_service.py \
    -v

# 3. Lint all changed files
./venv/bin/python3 -m flake8 --max-line-length=120 \
    app/database.py \
    app/routers/reports_router.py \
    app/routers/account_value_router.py \
    app/services/market_metrics_service.py \
    app/services/report_scheduler.py

# 4. Import sanity check
./venv/bin/python3 -c "
from app.database import engine, read_engine, get_db, get_read_db, \
    async_session_maker, read_async_session_maker
assert read_engine is not engine
assert read_async_session_maker is not async_session_maker
print('All imports OK, engines are distinct')
"

# 5. TypeScript check (no frontend changes)
cd /home/ec2-user/ZenithGrid/frontend && npx tsc --noEmit
```

---

## Confidence Assessment

**Score: 9/10**

**Why high**: This is a well-scoped, zero-infrastructure change. The dependency injection pattern is already established — swapping `get_db` for `get_read_db` is mechanical. The read engine creation mirrors the existing write engine exactly. The test strategy is concrete and verifiable. All edge cases are well-understood (SQLite test compat, write-only endpoints, scheduler session split).

**Risk**: The one area requiring care is `report_scheduler.py` — if the scheduler uses a single session for both reading report data and writing the Report row, splitting it requires understanding the full flow of that function. The 9/10 vs 10/10 discount is for this: the exact session split in `report_scheduler.py` needs to be verified against the actual code structure before committing to the implementation approach in Step 9.
