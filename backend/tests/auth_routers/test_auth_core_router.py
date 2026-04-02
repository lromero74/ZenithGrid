"""
Tests for rate limiting on /auth/refresh and /auth/change-password endpoints.

TDD: These tests are written BEFORE the rate limiting implementation.
They verify that repeated requests trigger 429 Too Many Requests.
"""

import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models import User


# =============================================================================
# Fixtures
# =============================================================================


def _make_user(**overrides):
    """Create a mock User object."""
    user = MagicMock(spec=User)
    user.id = overrides.get("id", 1)
    user.email = overrides.get("email", "test@example.com")
    user.hashed_password = overrides.get("hashed_password", "hashed_pw")
    user.is_active = overrides.get("is_active", True)
    user.mfa_enabled = overrides.get("mfa_enabled", False)
    user.mfa_email_enabled = overrides.get("mfa_email_enabled", False)
    user.totp_secret = overrides.get("totp_secret", None)
    user.last_login_at = overrides.get("last_login_at", None)
    user.updated_at = overrides.get("updated_at", None)
    user.display_name = overrides.get("display_name", None)
    user.email_verified = overrides.get("email_verified", True)
    user.terms_accepted_at = overrides.get("terms_accepted_at", datetime.utcnow())
    user.tokens_valid_after = overrides.get("tokens_valid_after", None)
    return user


def _mock_db():
    """Create a mock async DB session."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _clear_rate_limit_state():
    """Clear in-memory rate limiter state between tests."""
    from app.auth_routers import rate_limiters
    for store in rate_limiters._CATEGORY_STORE.values():
        store.clear()
    rate_limiters._warmed.clear()


# =============================================================================
# POST /auth/refresh — rate limit tests
# =============================================================================


class TestRefreshRateLimit:
    """Rate limiting on /auth/refresh endpoint."""

    @pytest.mark.asyncio
    async def test_refresh_rate_limit_blocks_after_max_attempts(self):
        """Hitting /auth/refresh more than 60 times in an hour should return 429."""
        from app.auth_routers.rate_limiters import _check, _record

        _clear_rate_limit_state()

        # Record 60 attempts (the limit)
        for _ in range(60):
            await _record("refresh", "refresh:1")

        # The 61st check should raise 429
        with pytest.raises(HTTPException) as exc_info:
            await _check("refresh", "refresh:1", "Too many token refresh attempts.")

        assert exc_info.value.status_code == 429
        assert "Too many token refresh attempts" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_refresh_rate_limit_allows_under_threshold(self):
        """Under 60 refreshes in an hour should succeed."""
        from app.auth_routers.rate_limiters import _check, _record

        _clear_rate_limit_state()

        # Record 59 attempts (under the limit)
        for _ in range(59):
            await _record("refresh", "refresh:1")

        # Should NOT raise
        await _check("refresh", "refresh:1", "Too many token refresh attempts.")

    @pytest.mark.asyncio
    async def test_refresh_rate_limit_per_user_isolation(self):
        """Rate limits are per-user — user 2 unaffected by user 1's usage."""
        from app.auth_routers.rate_limiters import _check, _record

        _clear_rate_limit_state()

        # Exhaust user 1's limit
        for _ in range(60):
            await _record("refresh", "refresh:1")

        # User 2 should still be fine
        await _check("refresh", "refresh:2", "Too many token refresh attempts.")


# =============================================================================
# POST /auth/change-password — rate limit tests
# =============================================================================


class TestChangePasswordRateLimit:
    """Rate limiting on /auth/change-password endpoint."""

    @pytest.mark.asyncio
    async def test_change_password_rate_limit_blocks_after_max_attempts(self):
        """Hitting /auth/change-password more than 5 times in 15 min should return 429."""
        from app.auth_routers.rate_limiters import _check, _record

        _clear_rate_limit_state()

        # Record 5 attempts (the limit)
        for _ in range(5):
            await _record("change_pw", "change_pw:1")

        # The 6th check should raise 429
        with pytest.raises(HTTPException) as exc_info:
            await _check("change_pw", "change_pw:1", "Too many password change attempts.")

        assert exc_info.value.status_code == 429
        assert "Too many password change attempts" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_change_password_rate_limit_allows_under_threshold(self):
        """Under 5 changes in 15 min should succeed."""
        from app.auth_routers.rate_limiters import _check, _record

        _clear_rate_limit_state()

        # Record 4 attempts (under the limit)
        for _ in range(4):
            await _record("change_pw", "change_pw:1")

        # Should NOT raise
        await _check("change_pw", "change_pw:1", "Too many password change attempts.")

    @pytest.mark.asyncio
    async def test_change_password_rate_limit_per_user_isolation(self):
        """Rate limits are per-user — user 2 unaffected by user 1's usage."""
        from app.auth_routers.rate_limiters import _check, _record

        _clear_rate_limit_state()

        # Exhaust user 1's limit
        for _ in range(5):
            await _record("change_pw", "change_pw:1")

        # User 2 should still be fine
        await _check("change_pw", "change_pw:2", "Too many password change attempts.")
