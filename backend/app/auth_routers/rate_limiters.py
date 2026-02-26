"""
Rate limiting logic for authentication endpoints.

In-memory rate limiting dicts and check/record functions for:
- Login (per IP + per username)
- Signup (per IP)
- Forgot password (per IP + per email)
- Resend verification (per user)
- MFA verification (per token)
"""

import logging
import time
from collections import defaultdict

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# =============================================================================
# Login rate limiting
# =============================================================================

# {ip: [(timestamp, ...)] }
_login_attempts: dict = defaultdict(list)
_login_attempts_by_username: dict = defaultdict(list)
_RATE_LIMIT_MAX = 5  # max attempts
_RATE_LIMIT_WINDOW = 900  # 15 minutes in seconds

# =============================================================================
# MFA verification rate limiting
# =============================================================================

# MFA verification rate limiting (S2/S3): keyed by mfa_token
_mfa_attempts: dict = defaultdict(list)
_MFA_RATE_LIMIT_MAX = 5  # max attempts per token
_MFA_RATE_LIMIT_WINDOW = 300  # 5 minutes

# =============================================================================
# Signup rate limiting
# =============================================================================

# Signup rate limiting: 3 per IP per hour
_signup_attempts: dict = defaultdict(list)
_SIGNUP_RATE_LIMIT_MAX = 3
_SIGNUP_RATE_LIMIT_WINDOW = 3600  # 1 hour

# =============================================================================
# Forgot-password rate limiting
# =============================================================================

# Forgot-password rate limiting: 3 per IP per hour + 3 per email per hour
_forgot_pw_attempts: dict = defaultdict(list)
_forgot_pw_by_email: dict = defaultdict(list)
_FORGOT_PW_RATE_LIMIT_MAX = 3
_FORGOT_PW_RATE_LIMIT_WINDOW = 3600

# =============================================================================
# Resend verification rate limiting
# =============================================================================

# Resend verification rate limiting: 3 per user per hour
_resend_attempts: dict = defaultdict(list)
_RESEND_RATE_LIMIT_MAX = 3
_RESEND_RATE_LIMIT_WINDOW = 3600

# =============================================================================
# Global prune
# =============================================================================

# Track last global prune time (shared across all rate limiters)
_last_prune_time: float = 0.0
_PRUNE_INTERVAL = 3600  # Prune stale entries every hour


def _prune_all_rate_limiters():
    """Periodically remove stale IPs/keys from all rate limiter dicts."""
    global _last_prune_time
    now = time.time()
    if now - _last_prune_time < _PRUNE_INTERVAL:
        return
    _last_prune_time = now

    total_pruned = 0
    for store, window in [
        (_login_attempts, _RATE_LIMIT_WINDOW),
        (_login_attempts_by_username, _RATE_LIMIT_WINDOW),
        (_signup_attempts, _SIGNUP_RATE_LIMIT_WINDOW),
        (_forgot_pw_attempts, _FORGOT_PW_RATE_LIMIT_WINDOW),
        (_forgot_pw_by_email, _FORGOT_PW_RATE_LIMIT_WINDOW),
        (_resend_attempts, _RESEND_RATE_LIMIT_WINDOW),
        (_mfa_attempts, _MFA_RATE_LIMIT_WINDOW),
    ]:
        stale_keys = [
            k for k, timestamps in store.items()
            if not any(now - t < window for t in timestamps)
        ]
        for k in stale_keys:
            del store[k]
        total_pruned += len(stale_keys)
    if total_pruned:
        logger.debug("Pruned %d stale rate limiter entries", total_pruned)


# =============================================================================
# Login rate limit functions
# =============================================================================


def _check_rate_limit(ip: str, username=None):
    """Check if IP or username has exceeded login rate limit. Raises 429."""
    _prune_all_rate_limiters()
    now = time.time()
    # Clean old entries for IP
    _login_attempts[ip] = [
        t for t in _login_attempts[ip]
        if now - t < _RATE_LIMIT_WINDOW
    ]
    exceeded = len(_login_attempts[ip]) >= _RATE_LIMIT_MAX
    timestamps = _login_attempts[ip]

    # Also check per-username (S11)
    if username and not exceeded:
        _login_attempts_by_username[username] = [
            t for t in _login_attempts_by_username[username]
            if now - t < _RATE_LIMIT_WINDOW
        ]
        if len(_login_attempts_by_username[username]) >= _RATE_LIMIT_MAX:
            exceeded = True
            timestamps = _login_attempts_by_username[username]

    if exceeded:
        oldest = min(timestamps)
        retry_after = int(oldest + _RATE_LIMIT_WINDOW - now)
        minutes = (retry_after + 59) // 60  # round up
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many login attempts. "
                f"Try again in {minutes} minute{'s' if minutes != 1 else ''}."
            ),
            headers={"Retry-After": str(retry_after)},
        )


def _record_attempt(ip: str, username=None):
    """Record a login attempt for rate limiting (IP + username)."""
    _login_attempts[ip].append(time.time())
    if username:
        _login_attempts_by_username[username].append(time.time())


# =============================================================================
# Signup rate limit functions
# =============================================================================


def _check_signup_rate_limit(ip: str):
    """Check if IP has exceeded signup rate limit."""
    now = time.time()
    _signup_attempts[ip] = [
        t for t in _signup_attempts[ip]
        if now - t < _SIGNUP_RATE_LIMIT_WINDOW
    ]
    if len(_signup_attempts[ip]) >= _SIGNUP_RATE_LIMIT_MAX:
        oldest = min(_signup_attempts[ip])
        retry_after = int(oldest + _SIGNUP_RATE_LIMIT_WINDOW - now)
        minutes = (retry_after + 59) // 60
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many signup attempts. "
                f"Try again in {minutes} minute{'s' if minutes != 1 else ''}."
            ),
            headers={"Retry-After": str(retry_after)},
        )


def _record_signup_attempt(ip: str):
    """Record a signup attempt for rate limiting."""
    _signup_attempts[ip].append(time.time())


# =============================================================================
# Forgot-password rate limit functions
# =============================================================================


def _check_forgot_pw_rate_limit(ip: str):
    """Check if IP has exceeded forgot-password rate limit."""
    now = time.time()
    _forgot_pw_attempts[ip] = [
        t for t in _forgot_pw_attempts[ip]
        if now - t < _FORGOT_PW_RATE_LIMIT_WINDOW
    ]
    if len(_forgot_pw_attempts[ip]) >= _FORGOT_PW_RATE_LIMIT_MAX:
        oldest = min(_forgot_pw_attempts[ip])
        retry_after = int(
            oldest + _FORGOT_PW_RATE_LIMIT_WINDOW - now
        )
        minutes = (retry_after + 59) // 60
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many requests. "
                f"Try again in {minutes} minute{'s' if minutes != 1 else ''}."
            ),
            headers={"Retry-After": str(retry_after)},
        )


def _record_forgot_pw_attempt(ip: str):
    """Record a forgot-password attempt for rate limiting."""
    _forgot_pw_attempts[ip].append(time.time())


def _is_forgot_pw_email_rate_limited(email: str) -> bool:
    """Check if email has exceeded forgot-password rate limit (S15).
    Returns True if rate limited (caller should return generic success)."""
    now = time.time()
    _forgot_pw_by_email[email] = [
        t for t in _forgot_pw_by_email[email]
        if now - t < _FORGOT_PW_RATE_LIMIT_WINDOW
    ]
    return len(_forgot_pw_by_email[email]) >= _FORGOT_PW_RATE_LIMIT_MAX


def _record_forgot_pw_email_attempt(email: str):
    """Record a forgot-password attempt by email."""
    _forgot_pw_by_email[email].append(time.time())


# =============================================================================
# Resend verification rate limit functions
# =============================================================================


def _check_resend_rate_limit(user_id: int):
    """Check if user has exceeded resend verification rate limit."""
    now = time.time()
    key = str(user_id)
    _resend_attempts[key] = [
        t for t in _resend_attempts[key]
        if now - t < _RESEND_RATE_LIMIT_WINDOW
    ]
    if len(_resend_attempts[key]) >= _RESEND_RATE_LIMIT_MAX:
        oldest = min(_resend_attempts[key])
        retry_after = int(
            oldest + _RESEND_RATE_LIMIT_WINDOW - now
        )
        minutes = (retry_after + 59) // 60
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many resend attempts. "
                f"Try again in {minutes} minute{'s' if minutes != 1 else ''}."
            ),
            headers={"Retry-After": str(retry_after)},
        )


def _record_resend_attempt(user_id: int):
    """Record a resend verification attempt for rate limiting."""
    _resend_attempts[str(user_id)].append(time.time())


# =============================================================================
# MFA rate limit functions
# =============================================================================


def _check_mfa_rate_limit(mfa_token: str):
    """Check MFA verification attempts per token. Raises 429 after 5 attempts."""
    now = time.time()
    _mfa_attempts[mfa_token] = [
        t for t in _mfa_attempts[mfa_token]
        if now - t < _MFA_RATE_LIMIT_WINDOW
    ]
    if len(_mfa_attempts[mfa_token]) >= _MFA_RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail="Too many MFA attempts. Please login again.",
        )


def _record_mfa_attempt(mfa_token: str):
    """Record an MFA verification attempt."""
    _mfa_attempts[mfa_token].append(time.time())
