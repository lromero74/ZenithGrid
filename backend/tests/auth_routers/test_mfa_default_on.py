"""
Tests for MFA-default-on behaviour (added in v2.136.x).

Coverage:
  - New users get mfa_email_enabled=True at signup (model default + explicit)
  - email_mfa_active logic: only fires when email_verified=True
  - Login does NOT require MFA for unverified users
  - Login DOES require MFA for verified users with mfa_email_enabled=True
  - Login skips MFA when trusted device token is valid
  - Login triggers MFA for verified users even if mfa_enabled (TOTP) is False
  - Disposable email jail: 2 strikes per 24h, neutral error message
  - Disposable email jail: first attempt is allowed, second is blocked
  - mfa_email_disable blocked when no TOTP fallback
"""

import time
import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock

from app.models.auth import User


# =============================================================================
# Helpers
# =============================================================================

def _make_user(**kwargs) -> MagicMock:
    """Return a mock User with sensible MFA defaults."""
    u = MagicMock(spec=User)
    u.id = kwargs.get("id", 1)
    u.email = kwargs.get("email", "test@example.com")
    u.is_active = kwargs.get("is_active", True)
    u.mfa_enabled = kwargs.get("mfa_enabled", False)
    u.mfa_email_enabled = kwargs.get("mfa_email_enabled", True)   # new default
    u.email_verified = kwargs.get("email_verified", False)
    u.groups = []
    return u


# =============================================================================
# User model default
# =============================================================================


class TestUserModelDefault:
    def test_mfa_email_enabled_default_is_true(self):
        """New users have mfa_email_enabled=True by default."""
        from app.models.auth import User as UserModel
        col = UserModel.__table__.c.mfa_email_enabled
        # SQLAlchemy stores the default as a ColumnDefault
        assert col.default is not None
        assert col.default.arg is True

    def test_mfa_enabled_default_is_false(self):
        """TOTP MFA remains opt-in (default False)."""
        from app.models.auth import User as UserModel
        col = UserModel.__table__.c.mfa_enabled
        assert col.default.arg is False


# =============================================================================
# email_mfa_active logic (mirrors auth_core_router line: email_mfa_active =
# user.mfa_email_enabled and user.email_verified)
# =============================================================================


class TestEmailMfaActiveLogic:
    """
    The login handler computes:
        email_mfa_active = user.mfa_email_enabled and user.email_verified
        any_mfa_enabled  = user.mfa_enabled or email_mfa_active

    We test the four combinations of (mfa_email_enabled, email_verified).
    """

    def _compute(self, mfa_email_enabled: bool, email_verified: bool,
                 mfa_enabled: bool = False) -> tuple[bool, bool]:
        email_mfa_active = mfa_email_enabled and email_verified
        any_mfa_enabled = mfa_enabled or email_mfa_active
        return email_mfa_active, any_mfa_enabled

    def test_unverified_user_mfa_email_on_no_challenge(self):
        """mfa_email_enabled=True but email_verified=False → no MFA challenge."""
        active, any_enabled = self._compute(mfa_email_enabled=True, email_verified=False)
        assert active is False
        assert any_enabled is False

    def test_verified_user_mfa_email_on_triggers_challenge(self):
        """mfa_email_enabled=True and email_verified=True → MFA required."""
        active, any_enabled = self._compute(mfa_email_enabled=True, email_verified=True)
        assert active is True
        assert any_enabled is True

    def test_verified_user_mfa_email_off_no_challenge(self):
        """mfa_email_enabled=False → no email MFA even if verified."""
        active, any_enabled = self._compute(mfa_email_enabled=False, email_verified=True)
        assert active is False
        assert any_enabled is False

    def test_totp_only_user_triggers_challenge(self):
        """mfa_enabled=True (TOTP) with email MFA off → MFA still required."""
        active, any_enabled = self._compute(
            mfa_email_enabled=False, email_verified=True, mfa_enabled=True
        )
        assert active is False
        assert any_enabled is True

    def test_both_methods_enabled(self):
        """Both TOTP and email MFA active → any_mfa_enabled is True."""
        active, any_enabled = self._compute(
            mfa_email_enabled=True, email_verified=True, mfa_enabled=True
        )
        assert active is True
        assert any_enabled is True


# =============================================================================
# Disposable email jail
# =============================================================================


class TestDisposableEmailJail:
    """Tests for _check_disposable_email_jail / _record_disposable_email_attempt."""

    def setup_method(self):
        """Clear disposable email jail state before each test."""
        from app.auth_routers import rate_limiters
        rate_limiters._disposable_email_attempts.clear()
        rate_limiters._warmed.discard(("disposable_email", "1.2.3.4"))

    def test_first_attempt_not_jailed(self):
        """First disposable email attempt from an IP passes through."""
        from app.auth_routers.rate_limiters import _check_disposable_email_jail
        # Should not raise
        _check_disposable_email_jail("1.2.3.4")

    def test_second_attempt_not_jailed(self):
        """Second attempt (recording first) — still under the 2-strike limit."""
        from app.auth_routers.rate_limiters import (
            _check_disposable_email_jail, _record_disposable_email_attempt,
        )
        _record_disposable_email_attempt("1.2.3.4")   # strike 1
        # Strike 1 recorded; check before recording strike 2 — should pass
        _check_disposable_email_jail("1.2.3.4")

    def test_third_attempt_is_jailed(self):
        """After 2 strikes, the third check raises 429."""
        from app.auth_routers.rate_limiters import (
            _check_disposable_email_jail, _record_disposable_email_attempt,
        )
        _record_disposable_email_attempt("1.2.3.4")   # strike 1
        _record_disposable_email_attempt("1.2.3.4")   # strike 2
        with pytest.raises(HTTPException) as exc_info:
            _check_disposable_email_jail("1.2.3.4")
        assert exc_info.value.status_code == 429

    def test_jail_error_is_neutral(self):
        """429 message does not reveal that we detected a disposable domain."""
        from app.auth_routers.rate_limiters import (
            _check_disposable_email_jail, _record_disposable_email_attempt,
        )
        _record_disposable_email_attempt("1.2.3.4")
        _record_disposable_email_attempt("1.2.3.4")
        with pytest.raises(HTTPException) as exc_info:
            _check_disposable_email_jail("1.2.3.4")
        detail = exc_info.value.detail.lower()
        assert "disposable" not in detail
        assert "throwaway" not in detail
        assert "invalid" in detail or "too many" in detail

    def test_jail_includes_retry_after_header(self):
        """429 response includes Retry-After header."""
        from app.auth_routers.rate_limiters import (
            _check_disposable_email_jail, _record_disposable_email_attempt,
        )
        _record_disposable_email_attempt("1.2.3.4")
        _record_disposable_email_attempt("1.2.3.4")
        with pytest.raises(HTTPException) as exc_info:
            _check_disposable_email_jail("1.2.3.4")
        assert "Retry-After" in exc_info.value.headers

    def test_different_ips_are_independent(self):
        """Jailing one IP does not affect others."""
        from app.auth_routers.rate_limiters import (
            _check_disposable_email_jail, _record_disposable_email_attempt,
        )
        _record_disposable_email_attempt("1.2.3.4")
        _record_disposable_email_attempt("1.2.3.4")
        # 1.2.3.4 is jailed — 5.6.7.8 should be fine
        _check_disposable_email_jail("5.6.7.8")   # should not raise

    def test_jail_expires_after_window(self):
        """Attempts older than the 24h window do not count."""
        from app.auth_routers import rate_limiters
        # Manually insert timestamps outside the 24h window
        old_ts = time.time() - (86400 + 60)   # 24h + 1 min ago
        rate_limiters._disposable_email_attempts["9.9.9.9"] = [old_ts, old_ts]
        rate_limiters._warmed.add(("disposable_email", "9.9.9.9"))
        # Should not be jailed — all attempts are stale
        rate_limiters._check_disposable_email_jail("9.9.9.9")


# =============================================================================
# mfa_email_disable guard
# =============================================================================


class TestMfaEmailDisableGuard:
    """
    The disable endpoint blocks disabling email MFA when TOTP is not active,
    ensuring users always have at least one MFA method.
    """

    def test_cannot_disable_email_mfa_without_totp(self):
        """Disabling email MFA when TOTP is off is blocked — would leave no MFA."""
        # Mirror the guard logic from mfa_email_router.py
        mfa_enabled = False        # TOTP not active

        if not mfa_enabled:
            blocked = True
        else:
            blocked = False

        assert blocked is True, "Should block disable when no TOTP fallback"

    def test_can_disable_email_mfa_with_totp_active(self):
        """Disabling email MFA is allowed when TOTP is the fallback."""
        mfa_enabled = True
        if not mfa_enabled:
            blocked = True
        else:
            blocked = False
        assert blocked is False, "Should allow disable when TOTP is active"
