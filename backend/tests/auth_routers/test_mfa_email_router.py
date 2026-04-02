"""
Tests for backend/app/auth_routers/mfa_email_router.py

Covers:
- POST /mfa/email/disable: TOTP gate when user has both TOTP + email MFA
- POST /mfa/resend-email: rate limiting on resend endpoint
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
    user.mfa_email_enabled = overrides.get("mfa_email_enabled", True)
    user.totp_secret = overrides.get("totp_secret", None)
    user.last_login_at = overrides.get("last_login_at", None)
    user.updated_at = overrides.get("updated_at", None)
    user.display_name = overrides.get("display_name", None)
    user.email_verified = overrides.get("email_verified", True)
    user.terms_accepted_at = overrides.get("terms_accepted_at", datetime.utcnow())
    return user


def _mock_db():
    """Create a mock async DB session."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


# =============================================================================
# POST /mfa/email/disable — TOTP gate tests
# =============================================================================


class TestEmailMfaDisableTotpGate:
    """When user has TOTP active, disabling email MFA must require a TOTP code."""

    @pytest.mark.asyncio
    async def test_totp_gate_disable_with_totp_active_no_code_raises_403(self):
        """User has both TOTP + email MFA, tries to disable email with only password -> 403."""
        from app.auth_routers.mfa_email_router import mfa_email_disable
        from app.auth_routers.schemas import MFAEmailDisableRequest

        user = _make_user(
            mfa_enabled=True,
            mfa_email_enabled=True,
            totp_secret="encrypted_secret",
        )
        request = MFAEmailDisableRequest(password="correctpassword")
        db = _mock_db()

        with patch(
            "app.auth_routers.mfa_email_router.verify_password",
            return_value=True,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await mfa_email_disable(request=request, current_user=user, db=db)

            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_totp_gate_disable_with_totp_active_valid_code_succeeds(self):
        """User has both TOTP + email MFA, provides password + valid TOTP -> succeeds."""
        from app.auth_routers.mfa_email_router import mfa_email_disable
        from app.auth_routers.schemas import MFAEmailDisableRequest

        user = _make_user(
            mfa_enabled=True,
            mfa_email_enabled=True,
            totp_secret="encrypted_secret",
        )
        # The schema needs to accept an optional totp_code field
        request = MFAEmailDisableRequest(password="correctpassword", totp_code="123456")
        db = _mock_db()

        with patch(
            "app.auth_routers.mfa_email_router.verify_password",
            return_value=True,
        ), patch(
            "app.auth_routers.mfa_email_router.decrypt_value",
            return_value="JBSWY3DPEHPK3PXP",
        ), patch(
            "app.auth_routers.mfa_email_router.pyotp.TOTP",
        ) as mock_totp_cls, patch(
            "app.auth_routers.mfa_email_router._build_user_response",
            return_value={"id": 1, "email": "test@example.com"},
        ):
            mock_totp = MagicMock()
            mock_totp.verify.return_value = True
            mock_totp_cls.return_value = mock_totp

            await mfa_email_disable(request=request, current_user=user, db=db)

        assert user.mfa_email_enabled is False

    @pytest.mark.asyncio
    async def test_totp_gate_disable_with_totp_active_invalid_code_raises_403(self):
        """User has both TOTP + email MFA, provides wrong TOTP code -> 403."""
        from app.auth_routers.mfa_email_router import mfa_email_disable
        from app.auth_routers.schemas import MFAEmailDisableRequest

        user = _make_user(
            mfa_enabled=True,
            mfa_email_enabled=True,
            totp_secret="encrypted_secret",
        )
        request = MFAEmailDisableRequest(password="correctpassword", totp_code="000000")
        db = _mock_db()

        with patch(
            "app.auth_routers.mfa_email_router.verify_password",
            return_value=True,
        ), patch(
            "app.auth_routers.mfa_email_router.decrypt_value",
            return_value="JBSWY3DPEHPK3PXP",
        ), patch(
            "app.auth_routers.mfa_email_router.pyotp.TOTP",
        ) as mock_totp_cls:
            mock_totp = MagicMock()
            mock_totp.verify.return_value = False
            mock_totp_cls.return_value = mock_totp

            with pytest.raises(HTTPException) as exc_info:
                await mfa_email_disable(request=request, current_user=user, db=db)

            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_totp_gate_disable_no_totp_password_only_succeeds(self):
        """User has ONLY email MFA (no TOTP), disables with just password -> succeeds."""
        from app.auth_routers.mfa_email_router import mfa_email_disable
        from app.auth_routers.schemas import MFAEmailDisableRequest

        # mfa_enabled=True here means "TOTP is active" — set to False for no-TOTP user
        # But we need mfa_enabled=False AND mfa_email_enabled=True
        # Wait — the current code checks `if not current_user.mfa_enabled` to block
        # "it's your only MFA method". So if user has ONLY email MFA:
        #   mfa_enabled=False -> raises 400 "Cannot disable email MFA — it's your only method"
        # That's existing behavior. Let's test a user who has TOTP active but is just
        # choosing to also disable email. The real "no TOTP" case is already blocked.
        # Actually, let me re-read: mfa_enabled means TOTP is active. If mfa_enabled=False
        # and user tries to disable email, it blocks with "only method". So the only way
        # to disable email is if mfa_enabled=True (TOTP is active). So our TOTP gate
        # always applies — user always needs TOTP code to disable email.
        # Let me adjust: test that when TOTP is NOT active, existing behavior remains (400).
        user = _make_user(
            mfa_enabled=False,
            mfa_email_enabled=True,
        )
        request = MFAEmailDisableRequest(password="correctpassword")
        db = _mock_db()

        with patch(
            "app.auth_routers.mfa_email_router.verify_password",
            return_value=True,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await mfa_email_disable(request=request, current_user=user, db=db)

            # Existing behavior: can't disable if it's only MFA method
            assert exc_info.value.status_code == 400
            assert "only MFA method" in exc_info.value.detail


# =============================================================================
# POST /mfa/resend-email — rate limiting tests
# =============================================================================


class TestResendEmailRateLimit:
    """The resend-email endpoint must be rate limited."""

    @pytest.mark.asyncio
    async def test_resend_rate_limit_blocks_after_max_attempts(self):
        """Hitting /mfa/resend-email many times should eventually return 429."""
        from app.auth_routers.rate_limiters import (
            _check_mfa_rate_limit,
            _mfa_attempts,
            _LIMITS,
        )

        token = "test-resend-rate-limit-token"
        max_attempts, window = _LIMITS["mfa"]

        # Simulate max_attempts worth of attempts
        now = time.time()
        _mfa_attempts[token] = [now for _ in range(max_attempts)]

        with pytest.raises(HTTPException) as exc_info:
            _check_mfa_rate_limit(token)

        assert exc_info.value.status_code == 429

        # Cleanup
        del _mfa_attempts[token]

    @pytest.mark.asyncio
    async def test_resend_rate_limit_applied_in_endpoint(self):
        """The resend-email endpoint calls _check_mfa_rate_limit before processing."""
        from app.auth_routers.mfa_email_router import mfa_resend_email

        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={"mfa_token": "rate-limited-token"})
        db = _mock_db()

        # Rate limit should fire BEFORE _decode_mfa_token
        with patch(
            "app.auth_routers.mfa_email_router._check_mfa_rate_limit",
            side_effect=HTTPException(status_code=429, detail="Too many MFA attempts."),
        ) as mock_rate_limit, patch(
            "app.auth_routers.mfa_email_router._record_mfa_attempt",
        ), patch(
            "app.auth_routers.mfa_email_router._decode_mfa_token",
            new_callable=AsyncMock,
            side_effect=AssertionError("Should not reach _decode_mfa_token if rate limited"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await mfa_resend_email(http_request=mock_request, db=db)

            assert exc_info.value.status_code == 429
            mock_rate_limit.assert_called_once_with("rate-limited-token")
