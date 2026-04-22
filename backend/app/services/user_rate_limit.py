"""
Per-user sliding-window rate limiter.

In-memory limiter keyed by (user_id, bucket). Designed for authenticated
endpoints that need defensive throttling on top of the IP-based public
limiter in app.middleware.public_rate_limit.

Typical use:
    from app.services.user_rate_limit import check_user_rate_limit

    check_user_rate_limit(
        user_id=current_user.id,
        bucket="invitation_action",
        max_requests=30,
        window_seconds=3600,
    )  # raises HTTPException(429) when exceeded

State lives in a module-level dict; one process only. For multi-process
deployments, swap the backing store for Redis without changing callers.
"""

import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException

_buckets: dict[tuple[int, str], list[float]] = defaultdict(list)
_lock = Lock()

# Entries older than this are eligible for pruning.
_STALE_SECONDS = 7200.0


def check_user_rate_limit(
    *,
    user_id: int,
    bucket: str,
    max_requests: int,
    window_seconds: float,
    message: str = "Too many requests. Please try again later.",
) -> None:
    """
    Raise HTTPException(429) if user_id has exceeded max_requests in the window.

    Records a successful request (adds timestamp to bucket) when under the
    limit — do not call this on code paths you don't want to count.
    """
    key = (user_id, bucket)
    now = time.time()
    cutoff = now - window_seconds

    with _lock:
        timestamps = _buckets[key]
        # Drop expired entries in-place
        timestamps[:] = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= max_requests:
            retry_after = int(window_seconds - (now - timestamps[0])) + 1
            raise HTTPException(
                status_code=429,
                detail=message,
                headers={"Retry-After": str(max(1, retry_after))},
            )

        timestamps.append(now)


def record_user_failure(
    *,
    user_id: int,
    bucket: str,
    max_failures: int,
    window_seconds: float,
    message: str = "Too many failed attempts. Please try again later.",
) -> None:
    """
    Record a failure for user_id and raise HTTPException(429) once max_failures
    is reached within window_seconds. Unlike check_user_rate_limit, this is
    meant to be called only on failed attempts (e.g., bad MFA code) so
    successful requests don't count toward the limit.
    """
    key = (user_id, f"fail:{bucket}")
    now = time.time()
    cutoff = now - window_seconds

    with _lock:
        timestamps = _buckets[key]
        timestamps[:] = [t for t in timestamps if t > cutoff]
        timestamps.append(now)

        if len(timestamps) >= max_failures:
            retry_after = int(window_seconds - (now - timestamps[0])) + 1
            raise HTTPException(
                status_code=429,
                detail=message,
                headers={"Retry-After": str(max(1, retry_after))},
            )


def clear_user_failures(*, user_id: int, bucket: str) -> None:
    """Clear failure count for user_id in bucket. Call after a successful attempt."""
    key = (user_id, f"fail:{bucket}")
    with _lock:
        _buckets.pop(key, None)


def prune_stale() -> int:
    """Remove buckets that haven't been touched recently. Returns count pruned."""
    now = time.time()
    with _lock:
        stale = [
            key for key, ts in _buckets.items()
            if not ts or (now - max(ts)) > _STALE_SECONDS
        ]
        for key in stale:
            del _buckets[key]
    return len(stale)
