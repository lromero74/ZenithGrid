"""
Tests for backend/app/auth_routers/mfa_totp_router.py

Covers:
- POST /mfa/setup: generate TOTP secret and QR code
- POST /mfa/verify-setup: confirm MFA setup with TOTP code
- POST /mfa/disable: disable MFA with password + TOTP verification
- POST /mfa/verify: verify TOTP during login (MFA challenge)

Tests call endpoint functions directly with mocked dependencies.
"""

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
    return user


# =============================================================================
# POST /mfa/setup
# =============================================================================


class TestMfaSetup:
    """Tests for mfa_setup endpoint."""

    @pytest.mark.asyncio
    async def test_setup_returns_qr_and_secret(self):
        """Happy path: generates TOTP secret and QR code for unenrolled user."""
        from app.auth_routers.mfa_totp_router import mfa_setup

        user = _make_user(mfa_enabled=False)

        with patch(
            "app.auth_routers.mfa_totp_router.get_brand",
            return_value={"shortName": "BTC-Bot"},
        ):
            result = await mfa_setup(current_user=user)

        assert result.qr_code_base64  # Non-empty base64 string
        assert result.secret_key  # Non-empty secret
        assert result.provisioning_uri  # Contains otpauth://
        assert "otpauth://" in result.provisioning_uri

    @pytest.mark.asyncio
    async def test_setup_already_enabled_raises_400(self):
        """Failure: MFA already enabled raises 400."""
        from app.auth_routers.mfa_totp_router import mfa_setup

        user = _make_user(mfa_enabled=True)

        with pytest.raises(HTTPException) as exc_info:
            await mfa_setup(current_user=user)

        assert exc_info.value.status_code == 400
        assert "already enabled" in exc_info.value.detail


# =============================================================================
# POST /mfa/verify-setup
# =============================================================================


class TestMfaVerifySetup:
    """Tests for mfa_verify_setup endpoint."""

    @pytest.mark.asyncio
    async def test_verify_setup_enables_mfa(self):
        """Happy path: valid TOTP code enables MFA and stores encrypted secret."""
        from app.auth_routers.mfa_totp_router import mfa_verify_setup

        user = _make_user(mfa_enabled=False)
        db = AsyncMock()

        import pyotp
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        valid_code = totp.now()

        request = MagicMock()
        request.secret_key = secret
        request.totp_code = valid_code

        with patch(
            "app.auth_routers.mfa_totp_router.encrypt_value",
            return_value="encrypted_secret",
        ), patch(
            "app.auth_routers.mfa_totp_router._build_user_response",
            return_value=MagicMock(),
        ):
            await mfa_verify_setup(
                request=request,
                current_user=user,
                db=db,
            )

        assert user.mfa_enabled is True
        assert user.totp_secret == "encrypted_secret"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_setup_invalid_code_raises_400(self):
        """Failure: invalid TOTP code raises 400."""
        from app.auth_routers.mfa_totp_router import mfa_verify_setup

        user = _make_user(mfa_enabled=False)
        db = AsyncMock()

        import pyotp
        secret = pyotp.random_base32()

        request = MagicMock()
        request.secret_key = secret
        request.totp_code = "000000"  # Invalid code

        with pytest.raises(HTTPException) as exc_info:
            await mfa_verify_setup(
                request=request,
                current_user=user,
                db=db,
            )

        assert exc_info.value.status_code == 400
        assert "Invalid TOTP" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_setup_already_enabled_raises_400(self):
        """Failure: MFA already enabled raises 400."""
        from app.auth_routers.mfa_totp_router import mfa_verify_setup

        user = _make_user(mfa_enabled=True)
        db = AsyncMock()

        request = MagicMock()
        request.secret_key = "SOME_SECRET"
        request.totp_code = "123456"

        with pytest.raises(HTTPException) as exc_info:
            await mfa_verify_setup(
                request=request,
                current_user=user,
                db=db,
            )

        assert exc_info.value.status_code == 400
        assert "already enabled" in exc_info.value.detail


# =============================================================================
# POST /mfa/disable
# =============================================================================


class TestMfaDisable:
    """Tests for mfa_disable endpoint."""

    @pytest.mark.asyncio
    async def test_disable_mfa_successfully(self):
        """Happy path: correct password + TOTP disables MFA."""
        from app.auth_routers.mfa_totp_router import mfa_disable

        import pyotp
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        valid_code = totp.now()

        user = _make_user(
            mfa_enabled=True,
            totp_secret="encrypted_secret",
        )
        db = AsyncMock()

        request = MagicMock()
        request.password = "correct_password"
        request.totp_code = valid_code

        with patch(
            "app.auth_routers.mfa_totp_router.verify_password",
            return_value=True,
        ), patch(
            "app.auth_routers.mfa_totp_router.decrypt_value",
            return_value=secret,
        ), patch(
            "app.auth_routers.mfa_totp_router._build_user_response",
            return_value=MagicMock(),
        ):
            await mfa_disable(
                request=request,
                current_user=user,
                db=db,
            )

        assert user.mfa_enabled is False
        assert user.totp_secret is None
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_disable_mfa_not_enabled_raises_400(self):
        """Failure: MFA not enabled raises 400."""
        from app.auth_routers.mfa_totp_router import mfa_disable

        user = _make_user(mfa_enabled=False)
        db = AsyncMock()

        request = MagicMock()
        request.password = "pw"
        request.totp_code = "123456"

        with pytest.raises(HTTPException) as exc_info:
            await mfa_disable(
                request=request,
                current_user=user,
                db=db,
            )

        assert exc_info.value.status_code == 400
        assert "not enabled" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_disable_mfa_wrong_password_raises_400(self):
        """Failure: wrong password raises 400."""
        from app.auth_routers.mfa_totp_router import mfa_disable

        user = _make_user(mfa_enabled=True)
        db = AsyncMock()

        request = MagicMock()
        request.password = "wrong_password"
        request.totp_code = "123456"

        with patch(
            "app.auth_routers.mfa_totp_router.verify_password",
            return_value=False,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await mfa_disable(
                    request=request,
                    current_user=user,
                    db=db,
                )

        assert exc_info.value.status_code == 400
        assert "Invalid password" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_disable_mfa_wrong_totp_raises_400(self):
        """Failure: wrong TOTP code raises 400."""
        from app.auth_routers.mfa_totp_router import mfa_disable

        import pyotp
        secret = pyotp.random_base32()

        user = _make_user(
            mfa_enabled=True,
            totp_secret="encrypted_secret",
        )
        db = AsyncMock()

        request = MagicMock()
        request.password = "correct_pw"
        request.totp_code = "000000"

        with patch(
            "app.auth_routers.mfa_totp_router.verify_password",
            return_value=True,
        ), patch(
            "app.auth_routers.mfa_totp_router.decrypt_value",
            return_value=secret,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await mfa_disable(
                    request=request,
                    current_user=user,
                    db=db,
                )

        assert exc_info.value.status_code == 400
        assert "Invalid TOTP" in exc_info.value.detail


# =============================================================================
# POST /mfa/verify (login MFA challenge)
# =============================================================================


class TestMfaVerify:
    """Tests for mfa_verify endpoint (login flow)."""

    @pytest.mark.asyncio
    async def test_verify_login_succeeds(self):
        """Happy path: valid MFA token + TOTP code returns tokens."""
        from app.auth_routers.mfa_totp_router import mfa_verify

        import pyotp
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        valid_code = totp.now()

        user = _make_user(
            mfa_enabled=True,
            totp_secret="encrypted_secret",
        )

        db = AsyncMock()
        http_request = MagicMock()

        request = MagicMock()
        request.mfa_token = "valid_mfa_token"
        request.totp_code = valid_code
        request.remember_device = False

        with patch(
            "app.auth_routers.mfa_totp_router._check_mfa_rate_limit",
        ), patch(
            "app.auth_routers.mfa_totp_router._record_mfa_attempt",
        ), patch(
            "app.auth_routers.mfa_totp_router.jwt.decode",
            return_value={"type": "mfa", "sub": "1"},
        ), patch(
            "app.auth_routers.mfa_totp_router.get_user_by_id",
            new_callable=AsyncMock,
            return_value=user,
        ), patch(
            "app.auth_routers.mfa_totp_router.decrypt_value",
            return_value=secret,
        ), patch(
            "app.auth_routers.mfa_totp_router.create_access_token",
            return_value="access_token_123",
        ), patch(
            "app.auth_routers.mfa_totp_router.create_refresh_token",
            return_value="refresh_token_456",
        ), patch(
            "app.auth_routers.mfa_totp_router._build_user_response",
            return_value={
                "id": 1, "email": "test@example.com", "display_name": "Test User",
                "is_active": True, "is_superuser": False,
                "mfa_enabled": True, "mfa_email_enabled": False,
                "email_verified": True,
                "created_at": datetime.utcnow().isoformat(),
                "last_login_at": datetime.utcnow().isoformat(),
            },
        ), patch(
            "app.auth_routers.mfa_totp_router.settings",
            MagicMock(
                jwt_secret_key="secret",
                jwt_algorithm="HS256",
                jwt_access_token_expire_minutes=30,
            ),
        ):
            result = await mfa_verify(
                request=request,
                http_request=http_request,
                db=db,
            )

        assert result.access_token == "access_token_123"
        assert result.refresh_token == "refresh_token_456"

    @pytest.mark.asyncio
    async def test_verify_login_invalid_token_raises_401(self):
        """Failure: invalid JWT MFA token raises 401."""
        from app.auth_routers.mfa_totp_router import mfa_verify
        from jose import JWTError

        request = MagicMock()
        request.mfa_token = "invalid_token"
        request.totp_code = "123456"

        db = AsyncMock()
        http_request = MagicMock()

        with patch(
            "app.auth_routers.mfa_totp_router._check_mfa_rate_limit",
        ), patch(
            "app.auth_routers.mfa_totp_router._record_mfa_attempt",
        ), patch(
            "app.auth_routers.mfa_totp_router.jwt.decode",
            side_effect=JWTError("expired"),
        ), patch(
            "app.auth_routers.mfa_totp_router.settings",
            MagicMock(jwt_secret_key="secret", jwt_algorithm="HS256"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await mfa_verify(
                    request=request,
                    http_request=http_request,
                    db=db,
                )

        assert exc_info.value.status_code == 401
        assert "Invalid or expired" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_login_wrong_token_type_raises_401(self):
        """Failure: token with wrong type raises 401."""
        from app.auth_routers.mfa_totp_router import mfa_verify

        request = MagicMock()
        request.mfa_token = "token"
        request.totp_code = "123456"

        db = AsyncMock()
        http_request = MagicMock()

        with patch(
            "app.auth_routers.mfa_totp_router._check_mfa_rate_limit",
        ), patch(
            "app.auth_routers.mfa_totp_router._record_mfa_attempt",
        ), patch(
            "app.auth_routers.mfa_totp_router.jwt.decode",
            return_value={"type": "access", "sub": "1"},
        ), patch(
            "app.auth_routers.mfa_totp_router.settings",
            MagicMock(jwt_secret_key="secret", jwt_algorithm="HS256"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await mfa_verify(
                    request=request,
                    http_request=http_request,
                    db=db,
                )

        assert exc_info.value.status_code == 401
        assert "Invalid token type" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_login_user_not_found_raises_401(self):
        """Failure: user not found from token raises 401."""
        from app.auth_routers.mfa_totp_router import mfa_verify

        request = MagicMock()
        request.mfa_token = "token"
        request.totp_code = "123456"

        db = AsyncMock()
        http_request = MagicMock()

        with patch(
            "app.auth_routers.mfa_totp_router._check_mfa_rate_limit",
        ), patch(
            "app.auth_routers.mfa_totp_router._record_mfa_attempt",
        ), patch(
            "app.auth_routers.mfa_totp_router.jwt.decode",
            return_value={"type": "mfa", "sub": "1"},
        ), patch(
            "app.auth_routers.mfa_totp_router.get_user_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.auth_routers.mfa_totp_router.settings",
            MagicMock(jwt_secret_key="secret", jwt_algorithm="HS256"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await mfa_verify(
                    request=request,
                    http_request=http_request,
                    db=db,
                )

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_login_mfa_not_configured_raises_400(self):
        """Failure: user without MFA configured raises 400."""
        from app.auth_routers.mfa_totp_router import mfa_verify

        user = _make_user(mfa_enabled=False, totp_secret=None)

        request = MagicMock()
        request.mfa_token = "token"
        request.totp_code = "123456"

        db = AsyncMock()
        http_request = MagicMock()

        with patch(
            "app.auth_routers.mfa_totp_router._check_mfa_rate_limit",
        ), patch(
            "app.auth_routers.mfa_totp_router._record_mfa_attempt",
        ), patch(
            "app.auth_routers.mfa_totp_router.jwt.decode",
            return_value={"type": "mfa", "sub": "1"},
        ), patch(
            "app.auth_routers.mfa_totp_router.get_user_by_id",
            new_callable=AsyncMock,
            return_value=user,
        ), patch(
            "app.auth_routers.mfa_totp_router.settings",
            MagicMock(jwt_secret_key="secret", jwt_algorithm="HS256"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await mfa_verify(
                    request=request,
                    http_request=http_request,
                    db=db,
                )

        assert exc_info.value.status_code == 400
        assert "not configured" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_login_wrong_totp_code_raises_401(self):
        """Failure: wrong TOTP code during login raises 401."""
        from app.auth_routers.mfa_totp_router import mfa_verify

        import pyotp
        secret = pyotp.random_base32()

        user = _make_user(
            mfa_enabled=True,
            totp_secret="encrypted_secret",
        )

        request = MagicMock()
        request.mfa_token = "token"
        request.totp_code = "000000"
        request.remember_device = False

        db = AsyncMock()
        http_request = MagicMock()

        with patch(
            "app.auth_routers.mfa_totp_router._check_mfa_rate_limit",
        ), patch(
            "app.auth_routers.mfa_totp_router._record_mfa_attempt",
        ), patch(
            "app.auth_routers.mfa_totp_router.jwt.decode",
            return_value={"type": "mfa", "sub": "1"},
        ), patch(
            "app.auth_routers.mfa_totp_router.get_user_by_id",
            new_callable=AsyncMock,
            return_value=user,
        ), patch(
            "app.auth_routers.mfa_totp_router.decrypt_value",
            return_value=secret,
        ), patch(
            "app.auth_routers.mfa_totp_router.settings",
            MagicMock(jwt_secret_key="secret", jwt_algorithm="HS256"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await mfa_verify(
                    request=request,
                    http_request=http_request,
                    db=db,
                )

        assert exc_info.value.status_code == 401
        assert "Invalid TOTP" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_login_with_remember_device(self):
        """Happy path: remember_device=True creates device trust token."""
        from app.auth_routers.mfa_totp_router import mfa_verify

        import pyotp
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        valid_code = totp.now()

        user = _make_user(
            mfa_enabled=True,
            totp_secret="encrypted_secret",
        )

        request = MagicMock()
        request.mfa_token = "token"
        request.totp_code = valid_code
        request.remember_device = True

        db = AsyncMock()
        http_request = MagicMock()

        with patch(
            "app.auth_routers.mfa_totp_router._check_mfa_rate_limit",
        ), patch(
            "app.auth_routers.mfa_totp_router._record_mfa_attempt",
        ), patch(
            "app.auth_routers.mfa_totp_router.jwt.decode",
            return_value={"type": "mfa", "sub": "1"},
        ), patch(
            "app.auth_routers.mfa_totp_router.get_user_by_id",
            new_callable=AsyncMock,
            return_value=user,
        ), patch(
            "app.auth_routers.mfa_totp_router.decrypt_value",
            return_value=secret,
        ), patch(
            "app.auth_routers.mfa_totp_router.create_access_token",
            return_value="access",
        ), patch(
            "app.auth_routers.mfa_totp_router.create_refresh_token",
            return_value="refresh",
        ), patch(
            "app.auth_routers.mfa_totp_router._create_device_trust",
            new_callable=AsyncMock,
            return_value="device_trust_token_abc",
        ) as mock_trust, patch(
            "app.auth_routers.mfa_totp_router._build_user_response",
            return_value={
                "id": 1, "email": "test@example.com", "display_name": "Test User",
                "is_active": True, "is_superuser": False,
                "mfa_enabled": True, "mfa_email_enabled": False,
                "email_verified": True,
                "created_at": datetime.utcnow().isoformat(),
                "last_login_at": datetime.utcnow().isoformat(),
            },
        ), patch(
            "app.auth_routers.mfa_totp_router.settings",
            MagicMock(
                jwt_secret_key="secret",
                jwt_algorithm="HS256",
                jwt_access_token_expire_minutes=30,
            ),
        ):
            result = await mfa_verify(
                request=request,
                http_request=http_request,
                db=db,
            )

        mock_trust.assert_called_once()
        assert result.device_trust_token == "device_trust_token_abc"
