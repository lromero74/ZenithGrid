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


# ---------------------------------------------------------------------------
# Protocol — the interface any backend must satisfy
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Postgres implementation — delegates to existing rate_limiters DB helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Redis stub — documented seam for Phase 3 multi-process deployment
# ---------------------------------------------------------------------------

class RedisRateLimitBackend:
    """RateLimitBackend backed by Redis.

    Uses atomic INCR + EXPIRE (fixed window) per (category, key) pair.
    TTL is set only on the first increment so the window isn't reset by
    subsequent attempts within the same window.

    Key pattern: rl:{category}:{key}
    DB: 0 (shared with general cache)
    """

    async def record_attempt(self, category: str, key: str) -> None:
        from app.redis_client import get_redis
        from app.auth_routers.rate_limiters import _LIMITS
        redis = await get_redis()
        rkey = f"rl:{category}:{key}"
        _, window = _LIMITS.get(category, (5, 900))
        count = await redis.incr(rkey)
        if count == 1:
            # First attempt — set TTL so the key expires after the window
            await redis.expire(rkey, window)

    async def count_recent(self, category: str, key: str, window_seconds: int) -> int:
        from app.redis_client import get_redis
        redis = await get_redis()
        val = await redis.get(f"rl:{category}:{key}")
        return int(val) if val else 0

    async def cleanup(self) -> None:
        pass  # Redis TTL handles expiry automatically


# ---------------------------------------------------------------------------
# Module-level singleton — same pattern as broadcast_backend and event_bus
# ---------------------------------------------------------------------------

rate_limit_backend: RateLimitBackend = PostgresRateLimitBackend()
