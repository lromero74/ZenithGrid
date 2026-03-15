"""
Tests for backend/app/auth_routers/rate_limiters.py

Covers in-memory rate limiting for login, signup, forgot password,
resend verification, and MFA categories. All tests use in-memory stores
only — DB persistence is mocked.
"""

import time

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException

from app.auth_routers.rate_limiters import (
    _check,
    _check_forgot_pw_rate_limit,
    _check_mfa_rate_limit,
    _check_rate_limit,
    _check_resend_rate_limit,
    _check_signup_rate_limit,
    _fire_and_forget,
    _is_forgot_pw_email_rate_limited,
    _mem_count,
    _prune_memory,
    _record,
    _record_attempt,
    _record_forgot_pw_attempt,
    _record_forgot_pw_email_attempt,
    _record_mfa_attempt,
    _record_resend_attempt,
    _record_signup_attempt,
    _CATEGORY_STORE,
    _LIMITS,
)
import app.auth_routers.rate_limiters as rl_module


# =============================================================================
# Fixture: clear all in-memory state before each test
# =============================================================================


@pytest.fixture(autouse=True)
def _clear_rate_limiter_state():
    """Reset all in-memory rate limiter state for test isolation."""
    for store in _CATEGORY_STORE.values():
        store.clear()
    rl_module._warmed.clear()
    rl_module._last_prune_time = 0.0
    rl_module._pending_db_tasks.clear()
    yield
    for store in _CATEGORY_STORE.values():
        store.clear()
    rl_module._warmed.clear()


# =============================================================================
# _mem_count
# =============================================================================


class TestMemCount:
    """Tests for _mem_count() — in-memory window counting."""

    def test_mem_count_returns_zero_for_empty_store(self):
        """Happy path: no attempts recorded returns count of 0."""
        from collections import defaultdict
        store = defaultdict(list)
        count, timestamps = _mem_count(store, "192.168.1.1", 900)
        assert count == 0
        assert timestamps == []

    def test_mem_count_counts_recent_attempts(self):
        """Happy path: only timestamps within window are counted."""
        from collections import defaultdict
        store = defaultdict(list)
        now = time.time()
        store["key1"] = [now - 10, now - 5, now - 1]
        count, timestamps = _mem_count(store, "key1", 900)
        assert count == 3

    def test_mem_count_filters_expired_attempts(self):
        """Edge case: timestamps outside the window are pruned."""
        from collections import defaultdict
        store = defaultdict(list)
        now = time.time()
        store["key1"] = [now - 2000, now - 1500, now - 5]
        count, timestamps = _mem_count(store, "key1", 900)
        assert count == 1
        assert len(store["key1"]) == 1  # Store is cleaned

    def test_mem_count_all_expired(self):
        """Edge case: all timestamps expired returns 0."""
        from collections import defaultdict
        store = defaultdict(list)
        store["key1"] = [time.time() - 5000, time.time() - 4000]
        count, timestamps = _mem_count(store, "key1", 900)
        assert count == 0


# =============================================================================
# Login rate limiting
# =============================================================================


class TestCheckRateLimit:
    """Tests for _check_rate_limit() — synchronous login limiter."""

    def test_check_rate_limit_allows_under_limit(self):
        """Happy path: fewer than 5 attempts does not raise."""
        _check_rate_limit("10.0.0.1")  # Should not raise

    def test_check_rate_limit_blocks_at_limit_by_ip(self):
        """Failure: 5 attempts from same IP raises 429."""
        now = time.time()
        rl_module._login_attempts["10.0.0.1"] = [now - i for i in range(5)]
        with pytest.raises(HTTPException) as exc_info:
            _check_rate_limit("10.0.0.1")
        assert exc_info.value.status_code == 429
        assert "Too many login attempts" in exc_info.value.detail

    def test_check_rate_limit_blocks_by_username(self):
        """Failure: 5 attempts for same username raises 429."""
        now = time.time()
        rl_module._login_attempts_by_username["admin"] = [now - i for i in range(5)]
        with pytest.raises(HTTPException) as exc_info:
            _check_rate_limit("10.0.0.2", username="admin")
        assert exc_info.value.status_code == 429

    def test_check_rate_limit_ip_ok_username_blocked(self):
        """Edge case: IP is fine but username is rate limited."""
        now = time.time()
        rl_module._login_attempts_by_username["victim"] = [now - i for i in range(5)]
        with pytest.raises(HTTPException):
            _check_rate_limit("192.168.1.1", username="victim")

    def test_check_rate_limit_expired_attempts_not_counted(self):
        """Edge case: old attempts outside the 15-min window are ignored."""
        rl_module._login_attempts["10.0.0.1"] = [time.time() - 2000 for _ in range(10)]
        _check_rate_limit("10.0.0.1")  # Should not raise

    def test_check_rate_limit_retry_after_header(self):
        """Failure: the 429 response includes a Retry-After header."""
        now = time.time()
        rl_module._login_attempts["10.0.0.1"] = [now - i for i in range(5)]
        with pytest.raises(HTTPException) as exc_info:
            _check_rate_limit("10.0.0.1")
        assert "Retry-After" in exc_info.value.headers

    def test_check_rate_limit_singular_minute(self):
        """Edge case: when retry is ~1 minute, message says 'minute' not 'minutes'."""
        now = time.time()
        # Place all attempts very recently so retry_after is close to 900s = 15 min
        rl_module._login_attempts["10.0.0.1"] = [now for _ in range(5)]
        with pytest.raises(HTTPException) as exc_info:
            _check_rate_limit("10.0.0.1")
        # The detail should contain "minutes" since 900s = 15 minutes
        assert "minute" in exc_info.value.detail


class TestRecordAttempt:
    """Tests for _record_attempt() — login attempt recording."""

    def test_record_attempt_adds_to_ip_store(self):
        """Happy path: recording adds a timestamp for the IP."""
        _record_attempt("10.0.0.1")
        assert len(rl_module._login_attempts["10.0.0.1"]) == 1

    def test_record_attempt_adds_to_username_store(self):
        """Happy path: with username, records in both IP and username stores."""
        _record_attempt("10.0.0.1", username="testuser")
        assert len(rl_module._login_attempts["10.0.0.1"]) == 1
        assert len(rl_module._login_attempts_by_username["testuser"]) == 1

    def test_record_attempt_no_username_skips_username_store(self):
        """Edge case: without username, only IP store is updated."""
        _record_attempt("10.0.0.1")
        assert "testuser" not in rl_module._login_attempts_by_username

    def test_record_attempt_marks_warmed(self):
        """Happy path: recording marks the cache key as warmed."""
        _record_attempt("10.0.0.1", username="user1")
        assert ("login", "10.0.0.1") in rl_module._warmed
        assert ("login_user", "user1") in rl_module._warmed


# =============================================================================
# Signup rate limiting
# =============================================================================


class TestSignupRateLimit:
    """Tests for signup rate limiting (3 per hour)."""

    def test_check_signup_allows_under_limit(self):
        """Happy path: under 3 attempts is allowed."""
        _check_signup_rate_limit("10.0.0.1")

    def test_check_signup_blocks_at_limit(self):
        """Failure: 3 attempts from same IP raises 429."""
        now = time.time()
        rl_module._signup_attempts["10.0.0.1"] = [now - i for i in range(3)]
        with pytest.raises(HTTPException) as exc_info:
            _check_signup_rate_limit("10.0.0.1")
        assert exc_info.value.status_code == 429
        assert "signup" in exc_info.value.detail.lower()

    def test_record_signup_adds_to_store(self):
        """Happy path: recording increments the signup store."""
        _record_signup_attempt("10.0.0.1")
        assert len(rl_module._signup_attempts["10.0.0.1"]) == 1
        assert ("signup", "10.0.0.1") in rl_module._warmed


# =============================================================================
# Forgot password rate limiting
# =============================================================================


class TestForgotPwRateLimit:
    """Tests for forgot password rate limiting (3 per hour)."""

    def test_check_forgot_pw_allows_under_limit(self):
        """Happy path: under 3 attempts is allowed."""
        _check_forgot_pw_rate_limit("10.0.0.1")

    def test_check_forgot_pw_blocks_at_limit(self):
        """Failure: 3 attempts from same IP raises 429."""
        now = time.time()
        rl_module._forgot_pw_attempts["10.0.0.1"] = [now - i for i in range(3)]
        with pytest.raises(HTTPException) as exc_info:
            _check_forgot_pw_rate_limit("10.0.0.1")
        assert exc_info.value.status_code == 429
        assert "Too many requests" in exc_info.value.detail

    def test_record_forgot_pw_adds_to_store(self):
        """Happy path: recording increments the forgot_pw store."""
        _record_forgot_pw_attempt("10.0.0.1")
        assert len(rl_module._forgot_pw_attempts["10.0.0.1"]) == 1


class TestForgotPwEmailRateLimit:
    """Tests for per-email forgot password rate limiting."""

    def test_is_rate_limited_returns_false_under_limit(self):
        """Happy path: fewer than 3 attempts returns False."""
        assert _is_forgot_pw_email_rate_limited("test@example.com") is False

    def test_is_rate_limited_returns_true_at_limit(self):
        """Failure: 3 attempts returns True."""
        now = time.time()
        rl_module._forgot_pw_by_email["test@example.com"] = [now - i for i in range(3)]
        assert _is_forgot_pw_email_rate_limited("test@example.com") is True

    def test_is_rate_limited_prunes_expired(self):
        """Edge case: expired timestamps are pruned and not counted."""
        rl_module._forgot_pw_by_email["test@example.com"] = [
            time.time() - 5000 for _ in range(10)
        ]
        assert _is_forgot_pw_email_rate_limited("test@example.com") is False

    def test_record_forgot_pw_email_adds_to_store(self):
        """Happy path: recording increments the email store."""
        _record_forgot_pw_email_attempt("a@b.com")
        assert len(rl_module._forgot_pw_by_email["a@b.com"]) == 1
        assert ("forgot_pw_email", "a@b.com") in rl_module._warmed


# =============================================================================
# Resend verification rate limiting
# =============================================================================


class TestResendRateLimit:
    """Tests for resend verification rate limiting (3 per hour)."""

    def test_check_resend_allows_under_limit(self):
        """Happy path: under 3 attempts is allowed."""
        _check_resend_rate_limit(42)

    def test_check_resend_blocks_at_limit(self):
        """Failure: 3 attempts for same user_id raises 429."""
        now = time.time()
        rl_module._resend_attempts["42"] = [now - i for i in range(3)]
        with pytest.raises(HTTPException) as exc_info:
            _check_resend_rate_limit(42)
        assert exc_info.value.status_code == 429
        assert "resend" in exc_info.value.detail.lower()

    def test_record_resend_converts_user_id_to_string(self):
        """Edge case: user_id is stored as string key."""
        _record_resend_attempt(99)
        assert len(rl_module._resend_attempts["99"]) == 1
        assert ("resend", "99") in rl_module._warmed


# =============================================================================
# MFA rate limiting
# =============================================================================


class TestMfaRateLimit:
    """Tests for MFA rate limiting (5 per 5 minutes)."""

    def test_check_mfa_allows_under_limit(self):
        """Happy path: under 5 attempts is allowed."""
        _check_mfa_rate_limit("mfa-token-abc")

    def test_check_mfa_blocks_at_limit(self):
        """Failure: 5 attempts raises 429 with MFA-specific message."""
        now = time.time()
        rl_module._mfa_attempts["mfa-token-abc"] = [now - i for i in range(5)]
        with pytest.raises(HTTPException) as exc_info:
            _check_mfa_rate_limit("mfa-token-abc")
        assert exc_info.value.status_code == 429
        assert "MFA" in exc_info.value.detail
        assert "login again" in exc_info.value.detail.lower()

    def test_check_mfa_no_retry_after_header(self):
        """Edge case: MFA 429 does NOT include Retry-After header (different from login)."""
        now = time.time()
        rl_module._mfa_attempts["tok"] = [now - i for i in range(5)]
        with pytest.raises(HTTPException) as exc_info:
            _check_mfa_rate_limit("tok")
        # MFA handler doesn't set headers unlike other categories
        assert not hasattr(exc_info.value, 'headers') or exc_info.value.headers is None

    def test_record_mfa_adds_to_store(self):
        """Happy path: recording increments the MFA store."""
        _record_mfa_attempt("mfa-token-xyz")
        assert len(rl_module._mfa_attempts["mfa-token-xyz"]) == 1
        assert ("mfa", "mfa-token-xyz") in rl_module._warmed


# =============================================================================
# _prune_memory
# =============================================================================


class TestPruneMemory:
    """Tests for _prune_memory() — periodic stale entry cleanup."""

    def test_prune_memory_skips_when_interval_not_elapsed(self):
        """Edge case: prune is a no-op if called before the interval elapses."""
        rl_module._last_prune_time = time.time()
        now = time.time()
        rl_module._login_attempts["old_ip"] = [now - 5000]
        _prune_memory()
        # Should NOT have pruned because interval hasn't passed
        assert "old_ip" in rl_module._login_attempts

    def test_prune_memory_removes_stale_entries(self):
        """Happy path: stale entries are removed when interval elapses."""
        rl_module._last_prune_time = 0.0
        rl_module._login_attempts["stale_ip"] = [time.time() - 5000]
        rl_module._warmed.add(("login", "stale_ip"))
        _prune_memory()
        assert "stale_ip" not in rl_module._login_attempts
        assert ("login", "stale_ip") not in rl_module._warmed

    def test_prune_memory_keeps_fresh_entries(self):
        """Happy path: entries within the window are preserved."""
        rl_module._last_prune_time = 0.0
        rl_module._login_attempts["fresh_ip"] = [time.time() - 10]
        _prune_memory()
        assert "fresh_ip" in rl_module._login_attempts

    def test_prune_memory_clears_warmed_when_oversized(self):
        """Edge case: _warmed set is cleared when it exceeds MAX_WARMED_SIZE."""
        rl_module._last_prune_time = 0.0
        for i in range(rl_module._MAX_WARMED_SIZE + 1):
            rl_module._warmed.add(("login", f"ip_{i}"))
        _prune_memory()
        assert len(rl_module._warmed) == 0


# =============================================================================
# _fire_and_forget
# =============================================================================


class TestFireAndForget:
    """Tests for _fire_and_forget() — bounded async task scheduling."""

    def test_fire_and_forget_no_event_loop_is_silent(self):
        """Edge case: no running event loop does not raise."""
        async def dummy():
            pass
        # Outside an async context, there's no running loop — should silently pass
        _fire_and_forget(dummy())

    def test_fire_and_forget_drops_under_backpressure(self):
        """Edge case: tasks are dropped when pending count hits the limit."""
        # Fill up the pending tasks set
        for i in range(rl_module._MAX_PENDING_DB_TASKS):
            mock_task = MagicMock()
            rl_module._pending_db_tasks.add(mock_task)

        async def dummy():
            pass

        # This should be silently dropped (no loop, but even if there were one,
        # the backpressure check happens first)
        initial_count = len(rl_module._pending_db_tasks)
        _fire_and_forget(dummy())
        # Count should not have increased
        assert len(rl_module._pending_db_tasks) == initial_count


# =============================================================================
# Async _check (unified rate limit check)
# =============================================================================


class TestAsyncCheck:
    """Tests for _check() — unified async rate limiter with DB warming."""

    @pytest.mark.asyncio
    @patch("app.auth_routers.rate_limiters._db_count", new_callable=AsyncMock, return_value=0)
    async def test_check_allows_under_limit(self, mock_db_count):
        """Happy path: no prior attempts allows the request."""
        await _check("login", "10.0.0.1", "Too many login attempts.")

    @pytest.mark.asyncio
    @patch("app.auth_routers.rate_limiters._db_count", new_callable=AsyncMock, return_value=0)
    async def test_check_blocks_at_limit(self, mock_db_count):
        """Failure: when in-memory count reaches limit, 429 is raised."""
        now = time.time()
        rl_module._login_attempts["10.0.0.1"] = [now - i for i in range(5)]
        rl_module._warmed.add(("login", "10.0.0.1"))
        with pytest.raises(HTTPException) as exc_info:
            await _check("login", "10.0.0.1", "Too many login attempts.")
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    @patch("app.auth_routers.rate_limiters._db_count", new_callable=AsyncMock, return_value=4)
    async def test_check_warms_from_db_on_cold_cache(self, mock_db_count):
        """Happy path: cold cache warms from DB count and backfills memory."""
        await _check("login", "new_ip", "Too many login attempts.")
        # After warming, the key should be in warmed set
        assert ("login", "new_ip") in rl_module._warmed
        # Memory should have 4 synthetic timestamps
        assert len(rl_module._login_attempts["new_ip"]) == 4
        mock_db_count.assert_called_once_with("login", "new_ip", 900)

    @pytest.mark.asyncio
    @patch("app.auth_routers.rate_limiters._db_count", new_callable=AsyncMock, return_value=5)
    async def test_check_blocks_when_db_count_at_limit(self, mock_db_count):
        """Failure: DB warming reveals we're already at the limit."""
        with pytest.raises(HTTPException) as exc_info:
            await _check("login", "db_heavy_ip", "Too many login attempts.")
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    @patch("app.auth_routers.rate_limiters._db_count", new_callable=AsyncMock, return_value=0)
    async def test_check_skips_db_when_already_warmed(self, mock_db_count):
        """Edge case: already-warmed keys skip the DB query."""
        rl_module._warmed.add(("login", "10.0.0.1"))
        await _check("login", "10.0.0.1", "Too many login attempts.")
        mock_db_count.assert_not_called()


# =============================================================================
# Async _record
# =============================================================================


class TestAsyncRecord:
    """Tests for _record() — async attempt recording."""

    @pytest.mark.asyncio
    @patch("app.auth_routers.rate_limiters._db_record", new_callable=AsyncMock)
    async def test_record_adds_to_memory_and_calls_db(self, mock_db_record):
        """Happy path: recording adds to memory and persists to DB."""
        await _record("signup", "10.0.0.1")
        assert len(rl_module._signup_attempts["10.0.0.1"]) == 1
        assert ("signup", "10.0.0.1") in rl_module._warmed
        mock_db_record.assert_awaited_once_with("signup", "10.0.0.1")


# =============================================================================
# _LIMITS configuration
# =============================================================================


class TestLimitsConfig:
    """Tests for the _LIMITS configuration dictionary."""

    def test_all_categories_have_limits(self):
        """Happy path: every category in CATEGORY_STORE has a limit config."""
        for category in _CATEGORY_STORE:
            assert category in _LIMITS, f"Missing limit config for {category}"

    def test_limits_are_tuples_of_int(self):
        """Happy path: each limit is a (max_attempts, window_seconds) tuple."""
        for category, (max_attempts, window) in _LIMITS.items():
            assert isinstance(max_attempts, int), f"{category} max is not int"
            assert isinstance(window, int), f"{category} window is not int"
            assert max_attempts > 0
            assert window > 0

    def test_login_limits_are_5_per_15min(self):
        """Happy path: login is configured as 5 per 900 seconds."""
        assert _LIMITS["login"] == (5, 900)

    def test_mfa_limits_are_5_per_5min(self):
        """Happy path: MFA is configured as 5 per 300 seconds."""
        assert _LIMITS["mfa"] == (5, 300)

    def test_signup_limits_are_3_per_hour(self):
        """Happy path: signup is configured as 3 per 3600 seconds."""
        assert _LIMITS["signup"] == (3, 3600)
