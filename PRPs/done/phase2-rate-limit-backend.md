# PRP: Phase 2.6 — Rate Limit Backend Abstraction

## Feature Summary

Add a `RateLimitBackend` protocol in front of the three PostgreSQL DB helper functions
in `app/auth_routers/rate_limiters.py`. Zero behavior change today — `PostgresRateLimitBackend`
delegates to the existing internal DB helpers. `RedisRateLimitBackend` stub documents
the Phase 3 multi-process architecture and raises `NotImplementedError`.

- `rate_limiters.py` stays **completely unchanged**
- Single new file: `app/auth_routers/rate_limit_backend.py`
- Single new test file: `tests/test_rate_limit_backend.py` (TDD — written first)

**Motivation** (from `docs/SCALABILITY_ROADMAP.md` Phase 2.6): Rate limit state
is currently written to `RateLimitAttempt` rows in PostgreSQL. In a multi-process
deployment each worker writes independently, but the in-memory cache means a request
hitting Process A doesn't see Process B's recent attempts. Redis `INCR` + `EXPIRE`
solves this atomically per key. By introducing the backend seam now, the swap is
a one-line singleton reassignment at startup.

---

## Architecture

```
Auth router (login, signup, mfa, etc.)
        │
        ▼ (today — unchanged)
rate_limiters._check()/_record()
        │
        ├── memory dict (fast path — always in-process, never abstracted)
        │
        └── DB helpers (_db_record, _db_count, _db_cleanup)
                │
                ▼ (abstraction lives here)
        RateLimitBackend protocol
                │
        PostgresRateLimitBackend  →  _db_record / _db_count / _db_cleanup (today)
        RedisRateLimitBackend     →  INCR/GET/TTL on Redis (Phase 3)
```

**Key constraint**: The in-memory `_login_attempts` / `_signup_attempts` etc. dicts
stay untouched. The `RateLimitBackend` abstracts **only the persistence layer** (the
DB operations that provide cross-restart durability and cold-cache warming).

---

## What the Three DB Helpers Do (from `app/auth_routers/rate_limiters.py`)

```python
async def _db_record(category: str, key: str):
    """Persist an attempt to the database (non-blocking best-effort)."""
    # Writes one RateLimitAttempt(category=category, key=key, attempted_at=utcnow())

async def _db_count(category: str, key: str, window_seconds: int) -> int:
    """Count recent attempts from DB for a key (used to warm cold cache)."""
    # SELECT count(*) WHERE category=? AND key=? AND attempted_at >= cutoff

async def _db_cleanup():
    """Delete attempts older than the largest window (1 hour)."""
    # DELETE WHERE attempted_at < utcnow() - 1 hour
    # NOTE: hardcoded to 1-hour max window — no parameter
```

These become the three protocol methods:
- `record_attempt(category, key)` — delegates to `_db_record`
- `count_recent(category, key, window_seconds)` — delegates to `_db_count`
- `cleanup()` — delegates to `_db_cleanup` (no-arg; Redis impl is a no-op since TTL handles it)

---

## Reference Files

| File | Purpose |
|------|---------|
| `backend/app/auth_routers/rate_limiters.py` | The existing rate limiter — `PostgresRateLimitBackend` wraps its internal DB helpers |
| `backend/app/services/broadcast_backend.py` | **Primary pattern to follow** — Protocol + InProcess + Redis stub + module singleton |
| `backend/app/event_bus.py` | Secondary pattern — module singleton, deferred imports in methods |
| `backend/tests/test_rate_limiters.py` | Existing test file — test conventions, import patterns |
| `backend/tests/services/test_broadcast_backend.py` | **TDD test pattern to mirror** |

### Pattern from `broadcast_backend.py` to follow exactly

```python
@runtime_checkable
class BroadcastBackend(Protocol):
    async def method(self, ...) -> None: ...

class InProcessBroadcast:
    def __init__(self, manager: WebSocketManager) -> None:
        self._manager = manager
    async def method(self, ...) -> None:
        await self._manager.method(...)

class RedisBroadcast:
    """Raises NotImplementedError with Phase 3 architecture doc."""
    async def method(self, ...) -> None:
        raise NotImplementedError("RedisBroadcast not yet implemented (Phase 3)")

broadcast_backend: BroadcastBackend = InProcessBroadcast(ws_manager)
```

For `rate_limit_backend.py`, `PostgresRateLimitBackend` takes **no constructor args** (unlike `InProcessBroadcast` which takes `manager`). Instead it uses deferred imports inside methods to avoid circular imports and to stay testable via `patch()`.

---

## Implementation Blueprint

### File: `backend/app/auth_routers/rate_limit_backend.py`

```python
"""
RateLimitBackend abstraction — Phase 2.6 of the scalability roadmap.

Wraps the three DB helper functions in rate_limiters.py behind a protocol so
that Phase 3 (multi-process) can swap PostgresRateLimitBackend for
RedisRateLimitBackend without touching any call-site code.

The in-memory rate limit state (fast path) is NOT abstracted — it stays
in rate_limiters.py and is always in-process.

Usage (when migrating call sites in Phase 3):
    from app.auth_routers.rate_limit_backend import rate_limit_backend
    await rate_limit_backend.record_attempt("login", ip)
    count = await rate_limit_backend.count_recent("login", ip, window_seconds=900)
    await rate_limit_backend.cleanup()
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class RateLimitBackend(Protocol):
    """Persistence backend for rate limit attempt tracking.

    Implementations:
    - PostgresRateLimitBackend: delegates to RateLimitAttempt table (today)
    - RedisRateLimitBackend:    INCR/GET with TTL per key (Phase 3, multi-process)
    """

    async def record_attempt(self, category: str, key: str) -> None:
        """Persist one rate limit attempt for (category, key)."""
        ...

    async def count_recent(self, category: str, key: str, window_seconds: int) -> int:
        """Return the count of attempts in the last window_seconds for (category, key)."""
        ...

    async def cleanup(self) -> None:
        """Remove expired attempt records. Redis impl is a no-op (TTL handles it)."""
        ...


class PostgresRateLimitBackend:
    """RateLimitBackend backed by the PostgreSQL RateLimitAttempt table.

    Delegates to the existing internal DB helpers in rate_limiters.py.
    Zero behavior change — this is a pure delegation wrapper.

    Deferred imports avoid circular imports at module load time
    (rate_limit_backend.py lives in the same package as rate_limiters.py).
    """

    async def record_attempt(self, category: str, key: str) -> None:
        from app.auth_routers.rate_limiters import _db_record
        await _db_record(category, key)

    async def count_recent(self, category: str, key: str, window_seconds: int) -> int:
        from app.auth_routers.rate_limiters import _db_count
        return await _db_count(category, key, window_seconds)

    async def cleanup(self) -> None:
        from app.auth_routers.rate_limiters import _db_cleanup
        await _db_cleanup()


class RedisRateLimitBackend:
    """RateLimitBackend backed by Redis (Phase 3, multi-process deployments).

    In a multi-process deployment, each worker process has its own in-memory
    rate limit dict. A request hitting Process A does not see attempts recorded
    by Process B. Redis solves this with atomic INCR + EXPIRE per key.

    Architecture (Phase 3):
        record_attempt  → INCR rl:{category}:{key}  (atomic, with EXPIRE = window)
        count_recent    → GET  rl:{category}:{key}  (returns current INCR value)
        cleanup         → no-op (Redis TTL handles expiry automatically)

    When implementing:
        - Use `aioredis` or `redis.asyncio` client
        - Key pattern: f"rl:{category}:{key}"
        - Set TTL to window_seconds on first INCR (use MULTI/EXEC or SET NX + EXPIRE)
        - count_recent returns int(GET(...)) or 0 if key missing

    NOT IMPLEMENTED — raises NotImplementedError. Swap this in when Phase 3
    deploys multi-process uvicorn workers.
    """

    async def record_attempt(self, category: str, key: str) -> None:
        raise NotImplementedError("RedisRateLimitBackend not yet implemented (Phase 3)")

    async def count_recent(self, category: str, key: str, window_seconds: int) -> int:
        raise NotImplementedError("RedisRateLimitBackend not yet implemented (Phase 3)")

    async def cleanup(self) -> None:
        raise NotImplementedError("RedisRateLimitBackend not yet implemented (Phase 3)")


# ---------------------------------------------------------------------------
# Module-level singleton — same pattern as broadcast_backend and event_bus
# ---------------------------------------------------------------------------

rate_limit_backend: RateLimitBackend = PostgresRateLimitBackend()
```

---

## TDD Test File: `backend/tests/test_rate_limit_backend.py`

Write FIRST — all tests must initially fail with `ModuleNotFoundError`.

```
Tests to cover:
1.  PostgresRateLimitBackend.record_attempt delegates to _db_record(category, key)
2.  PostgresRateLimitBackend.count_recent delegates to _db_count(category, key, window)
    and returns its result
3.  PostgresRateLimitBackend.cleanup delegates to _db_cleanup()
4.  Module-level singleton exists and is PostgresRateLimitBackend
5.  rate_limit_backend satisfies RateLimitBackend Protocol (isinstance)
6.  RedisRateLimitBackend is importable
7.  RedisRateLimitBackend.record_attempt raises NotImplementedError
8.  RedisRateLimitBackend.count_recent raises NotImplementedError
9.  RedisRateLimitBackend.cleanup raises NotImplementedError
10. RedisRateLimitBackend satisfies RateLimitBackend Protocol (isinstance)
```

**How to patch the deferred imports** (critical — wrong patch target = test passes vacuously):

```python
# Correct: patch the function in its SOURCE module
@patch('app.auth_routers.rate_limiters._db_record', new_callable=AsyncMock)
async def test_record_attempt_delegates(self, mock_db_record):
    from app.auth_routers.rate_limit_backend import PostgresRateLimitBackend
    backend = PostgresRateLimitBackend()
    await backend.record_attempt("login", "1.2.3.4")
    mock_db_record.assert_awaited_once_with("login", "1.2.3.4")

# count_recent must also assert the RETURN VALUE is passed through
@patch('app.auth_routers.rate_limiters._db_count', new_callable=AsyncMock, return_value=3)
async def test_count_recent_returns_db_value(self, mock_db_count):
    backend = PostgresRateLimitBackend()
    result = await backend.count_recent("signup", "10.0.0.1", 3600)
    assert result == 3
    mock_db_count.assert_awaited_once_with("signup", "10.0.0.1", 3600)
```

---

## Gotchas

- **`@runtime_checkable` is required** on the Protocol for `isinstance(obj, RateLimitBackend)` to work without raising `TypeError`.
- **Deferred imports in `PostgresRateLimitBackend` methods** avoid circular imports at module load. `rate_limit_backend.py` is in `app/auth_routers/` — same package as `rate_limiters.py`. Top-level `from app.auth_routers.rate_limiters import _db_record` at module level would also work, but deferred is safer and matches other patterns in the codebase.
- **`_db_cleanup()` takes no arguments** — the Postgres impl's `cleanup()` just calls it directly. Redis cleanup is a no-op.
- **`PostgresRateLimitBackend` takes no constructor args** — unlike `InProcessBroadcast(manager)`, there is no injectable dependency. The DB session is obtained via `async_session_maker` inside `rate_limiters._db_*` helpers.
- **Patch target must be the SOURCE module** — when testing deferred imports, `patch('app.auth_routers.rate_limiters._db_record')` is correct. Patching `app.auth_routers.rate_limit_backend._db_record` would fail because that name doesn't exist at module level.
- **No changes to `rate_limiters.py`** — this is an addition-only PR. Existing call sites are NOT migrated. Migration happens in Phase 3 when `RedisRateLimitBackend` is implemented.
- **Test file location**: `tests/test_rate_limit_backend.py` (root of tests dir, matching `tests/test_rate_limiters.py`). No new directory needed.

---

## Tasks (in order)

1. **Write failing tests** in `backend/tests/test_rate_limit_backend.py`
2. **Run tests** — confirm all 10 fail with `ModuleNotFoundError: No module named 'app.auth_routers.rate_limit_backend'`
3. **Write implementation** in `backend/app/auth_routers/rate_limit_backend.py`
4. **Run tests** — confirm all 10 pass
5. **Lint**: `flake8 app/auth_routers/rate_limit_backend.py --max-line-length=120`
6. **Verify existing rate limiter tests unbroken**: `pytest tests/test_rate_limiters.py -q`

---

## Validation Gates

```bash
# Run from: /home/ec2-user/ZenithGrid/backend

# 1. New tests pass
./venv/bin/python3 -m pytest tests/test_rate_limit_backend.py -v

# 2. Lint
./venv/bin/python3 -m flake8 app/auth_routers/rate_limit_backend.py --max-line-length=120

# 3. Existing rate limiter tests unbroken
./venv/bin/python3 -m pytest tests/test_rate_limiters.py -q

# 4. No import errors from the new module
./venv/bin/python3 -c "from app.auth_routers.rate_limit_backend import rate_limit_backend, RateLimitBackend, PostgresRateLimitBackend, RedisRateLimitBackend; print('imports OK')"
```

---

## Quality Checklist

- [ ] Tests written before implementation (TDD)
- [ ] All 10 tests pass
- [ ] `@runtime_checkable` on Protocol
- [ ] `RedisRateLimitBackend` docstring documents Phase 3 Redis key pattern
- [ ] Module-level singleton follows `broadcast_backend` / `event_bus` pattern
- [ ] Zero changes to `rate_limiters.py` or any existing call site
- [ ] Lint passes (flake8 --max-line-length=120)
- [ ] Existing `test_rate_limiters.py` still passes

---

**Confidence score: 9/10** — Single new file, pure delegation to existing helpers, no behavior changes. The only subtlety is the patch-target for deferred imports, which is documented explicitly above. Pattern mirrors `broadcast_backend.py` exactly (just shipped in v2.128.0).
