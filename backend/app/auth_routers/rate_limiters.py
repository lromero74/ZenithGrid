"""
Rate limiting logic for authentication endpoints.

Hybrid approach: in-memory dict for fast lookups + DB persistence so
rate-limit state survives application restarts.  On startup the in-memory
cache is cold; the first check for any key falls through to a DB count
query and warms the cache.

Categories: login, signup, forgot_pw, resend, mfa
"""

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import delete, func, select

from app.database import async_session_maker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_LIMITS = {
    #  category           max   window_seconds
    "login":             (5,    900),    # 5 per 15 min
    "login_user":        (5,    900),    # per-username
    "signup":            (3,    3600),   # 3 per hour
    "forgot_pw":         (3,    3600),
    "forgot_pw_email":   (3,    3600),
    "resend":            (3,    3600),
    "mfa":               (5,    300),    # 5 per 5 min
}

# ---------------------------------------------------------------------------
# In-memory cache (fast path — identical to the original implementation)
# ---------------------------------------------------------------------------

_login_attempts: dict = defaultdict(list)
_login_attempts_by_username: dict = defaultdict(list)
_signup_attempts: dict = defaultdict(list)
_forgot_pw_attempts: dict = defaultdict(list)
_forgot_pw_by_email: dict = defaultdict(list)
_resend_attempts: dict = defaultdict(list)
_mfa_attempts: dict = defaultdict(list)

_CATEGORY_STORE = {
    "login":           _login_attempts,
    "login_user":      _login_attempts_by_username,
    "signup":          _signup_attempts,
    "forgot_pw":       _forgot_pw_attempts,
    "forgot_pw_email": _forgot_pw_by_email,
    "resend":          _resend_attempts,
    "mfa":             _mfa_attempts,
}

# Track whether a key has been warmed from DB
_warmed: set = set()
_MAX_WARMED_SIZE = 10000  # Hard cap — rebuilds on demand if cleared

# Prune
_last_prune_time: float = 0.0
_PRUNE_INTERVAL = 3600

# Bounded fire-and-forget task tracking (prevents pile-up under slow DB)
_pending_db_tasks: set = set()
_MAX_PENDING_DB_TASKS = 100

# ---------------------------------------------------------------------------
# DB helpers (fire-and-forget writes, blocking reads only on cold cache)
# ---------------------------------------------------------------------------


async def _db_record(category: str, key: str):
    """Persist an attempt to the database (non-blocking best-effort)."""
    try:
        from app.models.auth import RateLimitAttempt
        async with async_session_maker() as db:
            db.add(RateLimitAttempt(
                category=category, key=key, attempted_at=datetime.utcnow(),
            ))
            await db.commit()
    except Exception as e:
        logger.warning(f"rate_limiter: failed to persist attempt ({category}/{key}): {e}")


async def _db_count(category: str, key: str, window_seconds: int) -> int:
    """Count recent attempts from DB for a key (used to warm cold cache)."""
    try:
        from app.models.auth import RateLimitAttempt
        cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
        async with async_session_maker() as db:
            result = await db.execute(
                select(func.count()).where(
                    RateLimitAttempt.category == category,
                    RateLimitAttempt.key == key,
                    RateLimitAttempt.attempted_at >= cutoff,
                )
            )
            return result.scalar() or 0
    except Exception as e:
        logger.warning(f"rate_limiter: DB count failed ({category}/{key}): {e}")
        return 0


async def _db_cleanup():
    """Delete attempts older than the largest window (1 hour)."""
    try:
        from app.models.auth import RateLimitAttempt
        cutoff = datetime.utcnow() - timedelta(hours=1)
        async with async_session_maker() as db:
            await db.execute(
                delete(RateLimitAttempt).where(
                    RateLimitAttempt.attempted_at < cutoff
                )
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"rate_limiter: DB cleanup failed: {e}")


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _fire_and_forget(coro):
    """Schedule a coroutine as a tracked task. Drops under backpressure."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        if len(_pending_db_tasks) >= _MAX_PENDING_DB_TASKS:
            return  # Drop under backpressure — prevents unbounded task pile-up
        task = loop.create_task(coro)
        _pending_db_tasks.add(task)
        task.add_done_callback(_pending_db_tasks.discard)
    except RuntimeError:
        pass  # No event loop (test context)


def _prune_memory():
    """Periodically prune stale in-memory entries."""
    global _last_prune_time
    now = time.time()
    if now - _last_prune_time < _PRUNE_INTERVAL:
        return
    _last_prune_time = now
    total = 0
    for cat, store in _CATEGORY_STORE.items():
        _, window = _LIMITS[cat]
        stale = [k for k, ts in store.items() if not any(now - t < window for t in ts)]
        for k in stale:
            del store[k]
            _warmed.discard((cat, k))
        total += len(stale)
    # Cap _warmed set — it's a "have I loaded from DB" tracker that rebuilds on demand
    if len(_warmed) > _MAX_WARMED_SIZE:
        _warmed.clear()
        total += 1
    if total:
        logger.debug("Pruned %d stale rate limiter entries", total)


def _mem_count(store: dict, key: str, window: int) -> tuple[int, list]:
    """Count recent in-memory attempts and return cleaned list."""
    now = time.time()
    cleaned = [t for t in store[key] if now - t < window]
    store[key] = cleaned
    return len(cleaned), cleaned


def _get_rate_limit_backend():
    """Return the current rate_limit_backend singleton (always reads the live module attr)."""
    from app.auth_routers.rate_limit_backend import rate_limit_backend as _backend
    return _backend


async def _check(category: str, key: str, error_msg: str):
    """Unified rate limit check: memory first, DB fallback on cold cache."""
    _prune_memory()
    max_attempts, window = _LIMITS[category]
    store = _CATEGORY_STORE[category]
    cache_key = (category, key)

    # Warm from backend on first access after restart
    if cache_key not in _warmed:
        db_count = await _get_rate_limit_backend().count_recent(category, key, window)
        if db_count > 0:
            # Backfill memory with synthetic timestamps spread across the window
            now = time.time()
            store[key] = [now - (window * i / max(db_count, 1)) for i in range(db_count)]
        _warmed.add(cache_key)

    count, timestamps = _mem_count(store, key, window)
    if count >= max_attempts:
        oldest = min(timestamps)
        retry_after = int(oldest + window - time.time())
        minutes = (retry_after + 59) // 60
        raise HTTPException(
            status_code=429,
            detail=f"{error_msg} Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
            headers={"Retry-After": str(max(retry_after, 1))},
        )


async def _record(category: str, key: str):
    """Record an attempt in both memory and backend."""
    _CATEGORY_STORE[category][key].append(time.time())
    _warmed.add((category, key))
    await _get_rate_limit_backend().record_attempt(category, key)


# ---------------------------------------------------------------------------
# Public API (same signatures as before for backward compat)
# ---------------------------------------------------------------------------

# -- Login --

def _check_rate_limit(ip: str, username=None):
    """Synchronous check (called from sync login endpoint).
    Falls back to memory-only on first call; DB warming happens on next async check.
    """
    _prune_memory()
    max_attempts, window = _LIMITS["login"]

    count, timestamps = _mem_count(_login_attempts, ip, window)
    exceeded = count >= max_attempts

    if username and not exceeded:
        count, timestamps = _mem_count(_login_attempts_by_username, username, window)
        exceeded = count >= max_attempts

    if exceeded:
        oldest = min(timestamps)
        retry_after = int(oldest + window - time.time())
        minutes = (retry_after + 59) // 60
        raise HTTPException(
            status_code=429,
            detail=f"Too many login attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
            headers={"Retry-After": str(max(retry_after, 1))},
        )


def _record_attempt(ip: str, username=None):
    """Record failed login attempt (sync wrapper — DB write is best-effort)."""
    _login_attempts[ip].append(time.time())
    _warmed.add(("login", ip))
    if username:
        _login_attempts_by_username[username].append(time.time())
        _warmed.add(("login_user", username))
    # Fire-and-forget backend persistence (bounded task tracking)
    _fire_and_forget(_get_rate_limit_backend().record_attempt("login", ip))
    if username:
        _fire_and_forget(_get_rate_limit_backend().record_attempt("login_user", username))


# -- Signup --

def _check_signup_rate_limit(ip: str):
    _prune_memory()
    max_attempts, window = _LIMITS["signup"]
    count, timestamps = _mem_count(_signup_attempts, ip, window)
    if count >= max_attempts:
        oldest = min(timestamps)
        retry_after = int(oldest + window - time.time())
        minutes = (retry_after + 59) // 60
        raise HTTPException(
            status_code=429,
            detail=f"Too many signup attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
            headers={"Retry-After": str(max(retry_after, 1))},
        )


def _record_signup_attempt(ip: str):
    _signup_attempts[ip].append(time.time())
    _warmed.add(("signup", ip))
    _fire_and_forget(_get_rate_limit_backend().record_attempt("signup", ip))


# -- Forgot password --

def _check_forgot_pw_rate_limit(ip: str):
    _prune_memory()
    max_attempts, window = _LIMITS["forgot_pw"]
    count, timestamps = _mem_count(_forgot_pw_attempts, ip, window)
    if count >= max_attempts:
        oldest = min(timestamps)
        retry_after = int(oldest + window - time.time())
        minutes = (retry_after + 59) // 60
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
            headers={"Retry-After": str(max(retry_after, 1))},
        )


def _record_forgot_pw_attempt(ip: str):
    _forgot_pw_attempts[ip].append(time.time())
    _warmed.add(("forgot_pw", ip))
    _fire_and_forget(_get_rate_limit_backend().record_attempt("forgot_pw", ip))


def _is_forgot_pw_email_rate_limited(email: str) -> bool:
    now = time.time()
    _, window = _LIMITS["forgot_pw_email"]
    max_attempts = _LIMITS["forgot_pw_email"][0]
    _forgot_pw_by_email[email] = [
        t for t in _forgot_pw_by_email[email] if now - t < window
    ]
    return len(_forgot_pw_by_email[email]) >= max_attempts


def _record_forgot_pw_email_attempt(email: str):
    _forgot_pw_by_email[email].append(time.time())
    _warmed.add(("forgot_pw_email", email))
    _fire_and_forget(_get_rate_limit_backend().record_attempt("forgot_pw_email", email))


# -- Resend verification --

def _check_resend_rate_limit(user_id: int):
    _prune_memory()
    key = str(user_id)
    max_attempts, window = _LIMITS["resend"]
    count, timestamps = _mem_count(_resend_attempts, key, window)
    if count >= max_attempts:
        oldest = min(timestamps)
        retry_after = int(oldest + window - time.time())
        minutes = (retry_after + 59) // 60
        raise HTTPException(
            status_code=429,
            detail=f"Too many resend attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
            headers={"Retry-After": str(max(retry_after, 1))},
        )


def _record_resend_attempt(user_id: int):
    key = str(user_id)
    _resend_attempts[key].append(time.time())
    _warmed.add(("resend", key))
    _fire_and_forget(_get_rate_limit_backend().record_attempt("resend", key))


# -- MFA --

def _check_mfa_rate_limit(mfa_token: str):
    _prune_memory()
    max_attempts, window = _LIMITS["mfa"]
    count, _ = _mem_count(_mfa_attempts, mfa_token, window)
    if count >= max_attempts:
        raise HTTPException(
            status_code=429,
            detail="Too many MFA attempts. Please login again.",
        )


def _record_mfa_attempt(mfa_token: str):
    _mfa_attempts[mfa_token].append(time.time())
    _warmed.add(("mfa", mfa_token))
    _fire_and_forget(_get_rate_limit_backend().record_attempt("mfa", mfa_token))
