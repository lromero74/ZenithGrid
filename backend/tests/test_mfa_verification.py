"""Tests for app.auth.mfa_verification.verify_mfa lockout behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pyotp
import pytest
from fastapi import HTTPException

from app.auth.mfa_verification import verify_mfa
from app.services import user_rate_limit


@pytest.fixture(autouse=True)
def clear_rate_limit_state():
    user_rate_limit._buckets.clear()
    yield
    user_rate_limit._buckets.clear()


def _make_totp_user(secret: str, user_id: int = 42):
    user = MagicMock()
    user.id = user_id
    user.mfa_enabled = True
    user.mfa_email_enabled = False
    user.totp_secret = "encrypted:" + secret  # decrypt_value is patched
    return user


class TestTotpMfaLockout:
    @pytest.mark.asyncio
    async def test_valid_code_passes_and_clears_failure_count(self):
        secret = pyotp.random_base32()
        user = _make_totp_user(secret)
        db = AsyncMock()

        # Seed 4 prior failures
        for _ in range(4):
            user_rate_limit.record_user_failure(
                user_id=user.id,
                bucket="mfa_verify",
                max_failures=10,
                window_seconds=900,
            )

        code = pyotp.TOTP(secret).now()
        with patch("app.auth.mfa_verification.decrypt_value", return_value=secret):
            await verify_mfa(db, user, code)

        # Success should have cleared the failure bucket
        assert ((user.id, "fail:mfa_verify") not in user_rate_limit._buckets
                or not user_rate_limit._buckets[(user.id, "fail:mfa_verify")])

    @pytest.mark.asyncio
    async def test_missing_code_raises_403(self):
        user = _make_totp_user("JBSWY3DPEHPK3PXP")
        db = AsyncMock()
        with pytest.raises(HTTPException) as exc:
            await verify_mfa(db, user, None)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_invalid_code_raises_403_and_counts_failure(self):
        secret = pyotp.random_base32()
        user = _make_totp_user(secret)
        db = AsyncMock()

        with patch("app.auth.mfa_verification.decrypt_value", return_value=secret):
            with pytest.raises(HTTPException) as exc:
                await verify_mfa(db, user, "000000")

        assert exc.value.status_code == 403
        # A failure should now be recorded
        assert len(user_rate_limit._buckets[(user.id, "fail:mfa_verify")]) == 1

    @pytest.mark.asyncio
    async def test_fifth_invalid_attempt_returns_429(self):
        secret = pyotp.random_base32()
        user = _make_totp_user(secret)
        db = AsyncMock()

        with patch("app.auth.mfa_verification.decrypt_value", return_value=secret):
            # First 4 invalid attempts: 403s
            for _ in range(4):
                with pytest.raises(HTTPException) as exc:
                    await verify_mfa(db, user, "000000")
                assert exc.value.status_code == 403

            # 5th invalid attempt trips the lockout
            with pytest.raises(HTTPException) as exc:
                await verify_mfa(db, user, "000000")

        assert exc.value.status_code == 429
        assert "Too many" in exc.value.detail


class TestNoMfaConfigured:
    @pytest.mark.asyncio
    async def test_no_mfa_is_noop(self):
        user = MagicMock()
        user.mfa_enabled = False
        user.mfa_email_enabled = False
        user.totp_secret = None
        db = AsyncMock()
        # Should not raise even with no code provided
        await verify_mfa(db, user, None)
