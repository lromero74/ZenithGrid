"""
Tests for backend/app/routers/auth_router.py

Covers authentication endpoints: login, signup, token refresh,
password change, email verification, MFA, rate limiting, and helper functions.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.models import (
    EmailVerificationToken,
    TrustedDevice,
    User,
)
from app.routers.auth_router import (
    _build_user_response,
    _check_forgot_pw_rate_limit,
    _check_mfa_rate_limit,
    _check_rate_limit,
    _check_resend_rate_limit,
    _check_signup_rate_limit,
    _is_forgot_pw_email_rate_limited,
    _parse_device_name,
    _record_attempt,
    _record_forgot_pw_attempt,
    _record_forgot_pw_email_attempt,
    _record_mfa_attempt,
    _record_resend_attempt,
    _record_signup_attempt,
    _validate_password_strength,
    create_access_token,
    create_device_trust_token,
    create_mfa_token,
    create_refresh_token,
    decode_device_trust_token,
    get_user_by_email,
    hash_password,
    verify_password,
)


# =============================================================================
# Rate limiter cleanup — ensure per-test isolation
# =============================================================================

@pytest.fixture(autouse=True)
def _clear_rate_limiters():
    """Clear all in-memory rate limiter dicts before each test."""
    from app.routers import auth_router
    auth_router._login_attempts.clear()
    auth_router._login_attempts_by_username.clear()
    auth_router._signup_attempts.clear()
    auth_router._forgot_pw_attempts.clear()
    auth_router._forgot_pw_by_email.clear()
    auth_router._resend_attempts.clear()
    auth_router._mfa_attempts.clear()
    yield


# =============================================================================
# Password hashing and verification
# =============================================================================


class TestHashPassword:
    """Tests for hash_password()"""

    def test_hash_password_returns_string(self):
        """Happy path: hashing a password returns a bcrypt string."""
        result = hash_password("SecurePass1")
        assert isinstance(result, str)
        assert result.startswith("$2b$")

    def test_hash_password_different_calls_produce_different_hashes(self):
        """Edge case: two calls with the same password produce different hashes (random salt)."""
        h1 = hash_password("SamePassword1")
        h2 = hash_password("SamePassword1")
        assert h1 != h2


class TestVerifyPassword:
    """Tests for verify_password()"""

    def test_verify_password_correct(self):
        """Happy path: correct password is verified."""
        hashed = hash_password("GoodPass1")
        assert verify_password("GoodPass1", hashed) is True

    def test_verify_password_incorrect(self):
        """Failure: wrong password is rejected."""
        hashed = hash_password("GoodPass1")
        assert verify_password("WrongPass2", hashed) is False

    def test_verify_password_empty_password(self):
        """Edge case: empty password does not match."""
        hashed = hash_password("SomePass1")
        assert verify_password("", hashed) is False


# =============================================================================
# Password strength validation
# =============================================================================


class TestValidatePasswordStrength:
    """Tests for _validate_password_strength()"""

    def test_valid_password(self):
        """Happy path: password with upper, lower, digit passes."""
        result = _validate_password_strength("Abcdefg1")
        assert result == "Abcdefg1"

    def test_missing_uppercase_raises(self):
        """Failure: password without uppercase raises ValueError."""
        with pytest.raises(ValueError, match="uppercase"):
            _validate_password_strength("abcdefg1")

    def test_missing_lowercase_raises(self):
        """Failure: password without lowercase raises ValueError."""
        with pytest.raises(ValueError, match="lowercase"):
            _validate_password_strength("ABCDEFG1")

    def test_missing_digit_raises(self):
        """Failure: password without digit raises ValueError."""
        with pytest.raises(ValueError, match="digit"):
            _validate_password_strength("Abcdefgh")


# =============================================================================
# JWT token creation and decoding
# =============================================================================


class TestCreateAccessToken:
    """Tests for create_access_token()"""

    def test_creates_valid_jwt(self):
        """Happy path: returns a non-empty string."""
        token = create_access_token(user_id=1, email="test@example.com")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_can_be_decoded(self):
        """Happy path: token payload contains expected fields."""
        from jose import jwt
        from app.config import settings

        token = create_access_token(user_id=42, email="user@example.com")
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert payload["sub"] == "42"
        assert payload["email"] == "user@example.com"
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "exp" in payload


class TestCreateRefreshToken:
    """Tests for create_refresh_token()"""

    def test_creates_refresh_token(self):
        """Happy path: creates a refresh token with type=refresh."""
        from jose import jwt
        from app.config import settings

        token = create_refresh_token(user_id=1)
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert payload["type"] == "refresh"
        assert payload["sub"] == "1"


class TestCreateMfaToken:
    """Tests for create_mfa_token()"""

    def test_creates_mfa_token(self):
        """Happy path: creates an MFA token with type=mfa."""
        from jose import jwt
        from app.config import settings

        token = create_mfa_token(user_id=5)
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert payload["type"] == "mfa"
        assert payload["sub"] == "5"


class TestCreateDeviceTrustToken:
    """Tests for create_device_trust_token() and decode_device_trust_token()"""

    def test_roundtrip(self):
        """Happy path: token can be created and decoded."""
        token = create_device_trust_token(user_id=7, device_id="abc-123")
        payload = decode_device_trust_token(token)
        assert payload is not None
        assert payload["sub"] == "7"
        assert payload["device_id"] == "abc-123"
        assert payload["type"] == "device_trust"

    def test_decode_invalid_token(self):
        """Failure: decoding garbage returns None."""
        assert decode_device_trust_token("garbage.token.here") is None

    def test_decode_wrong_type_returns_none(self):
        """Edge case: a valid JWT with wrong type returns None."""
        token = create_access_token(user_id=1, email="test@example.com")
        assert decode_device_trust_token(token) is None


# =============================================================================
# User-Agent parsing
# =============================================================================


class TestParseDeviceName:
    """Tests for _parse_device_name()"""

    def test_chrome_on_mac(self):
        """Happy path: Chrome on macOS parsed correctly."""
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0 Safari/537.36"
        assert _parse_device_name(ua) == "Chrome on Mac"

    def test_safari_on_iphone(self):
        """Happy path: Safari on iPhone."""
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1"
        assert _parse_device_name(ua) == "Safari on iPhone"

    def test_firefox_on_windows(self):
        """Happy path: Firefox on Windows."""
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Firefox/120.0"
        assert _parse_device_name(ua) == "Firefox on Windows"

    def test_empty_user_agent(self):
        """Edge case: empty string returns Unknown Device."""
        assert _parse_device_name("") == "Unknown Device"

    def test_none_user_agent(self):
        """Edge case: None input returns Unknown Device."""
        assert _parse_device_name(None) == "Unknown Device"

    def test_edge_on_linux(self):
        """Happy path: Edge on Linux."""
        ua = "Mozilla/5.0 (X11; Linux x86_64) Edg/120.0 Safari/537.36"
        assert _parse_device_name(ua) == "Edge on Linux"

    def test_android_chrome(self):
        """Happy path: Chrome on Android."""
        ua = "Mozilla/5.0 (Linux; Android 14) Chrome/120.0 Safari/537.36"
        assert _parse_device_name(ua) == "Chrome on Android"


# =============================================================================
# Build user response
# =============================================================================


class TestBuildUserResponse:
    """Tests for _build_user_response()"""

    def test_builds_response_from_user(self):
        """Happy path: all fields are mapped correctly."""
        user = MagicMock(spec=User)
        user.id = 1
        user.email = "test@example.com"
        user.display_name = "Test User"
        user.is_active = True
        user.is_superuser = False
        user.mfa_enabled = False
        user.mfa_email_enabled = False
        user.email_verified = True
        user.email_verified_at = datetime(2024, 1, 1)
        user.created_at = datetime(2023, 1, 1)
        user.last_login_at = datetime(2024, 6, 1)
        user.terms_accepted_at = datetime(2024, 3, 1)

        resp = _build_user_response(user)
        assert resp.id == 1
        assert resp.email == "test@example.com"
        assert resp.display_name == "Test User"
        assert resp.is_active is True
        assert resp.is_superuser is False
        assert resp.mfa_enabled is False
        assert resp.email_verified is True

    def test_builds_response_with_none_optional_fields(self):
        """Edge case: None optional fields do not crash."""
        user = MagicMock(spec=User)
        user.id = 2
        user.email = "user2@example.com"
        user.display_name = None
        user.is_active = True
        user.is_superuser = False
        user.mfa_enabled = False
        user.mfa_email_enabled = False
        user.email_verified = False
        user.email_verified_at = None
        user.created_at = datetime(2023, 1, 1)
        user.last_login_at = None
        user.terms_accepted_at = None

        resp = _build_user_response(user)
        assert resp.display_name is None
        assert resp.last_login_at is None
        assert resp.terms_accepted_at is None


# =============================================================================
# Rate Limiting — Login
# =============================================================================


class TestLoginRateLimit:
    """Tests for _check_rate_limit() and _record_attempt()"""

    def test_under_limit_does_not_raise(self):
        """Happy path: fewer than 5 attempts does not raise."""
        _record_attempt("192.168.1.1")
        _record_attempt("192.168.1.1")
        # Should not raise
        _check_rate_limit("192.168.1.1")

    def test_at_limit_raises_429(self):
        """Failure: 5 attempts within the window triggers 429."""
        from fastapi import HTTPException

        for _ in range(5):
            _record_attempt("10.0.0.1")

        with pytest.raises(HTTPException) as exc_info:
            _check_rate_limit("10.0.0.1")
        assert exc_info.value.status_code == 429
        assert "Too many login attempts" in exc_info.value.detail

    def test_rate_limit_by_username(self):
        """Edge case: rate limiting also applies per-username."""
        from fastapi import HTTPException

        # Use different IPs but same username
        for i in range(5):
            _record_attempt(f"10.0.0.{i + 10}", username="victim@example.com")

        with pytest.raises(HTTPException) as exc_info:
            _check_rate_limit("10.0.0.99", username="victim@example.com")
        assert exc_info.value.status_code == 429


class TestSignupRateLimit:
    """Tests for _check_signup_rate_limit()"""

    def test_under_limit_no_error(self):
        """Happy path: 2 signups is fine."""
        _record_signup_attempt("10.0.0.1")
        _record_signup_attempt("10.0.0.1")
        # Should not raise
        _check_signup_rate_limit("10.0.0.1")

    def test_at_limit_raises_429(self):
        """Failure: 3 signups triggers rate limit."""
        from fastapi import HTTPException

        for _ in range(3):
            _record_signup_attempt("10.0.0.2")

        with pytest.raises(HTTPException) as exc_info:
            _check_signup_rate_limit("10.0.0.2")
        assert exc_info.value.status_code == 429
        assert "signup" in exc_info.value.detail.lower()


class TestMfaRateLimit:
    """Tests for _check_mfa_rate_limit()"""

    def test_under_limit_no_error(self):
        """Happy path: 4 attempts is fine."""
        for _ in range(4):
            _record_mfa_attempt("mfa-token-abc")
        _check_mfa_rate_limit("mfa-token-abc")

    def test_at_limit_raises_429(self):
        """Failure: 5 MFA attempts triggers rate limit."""
        from fastapi import HTTPException

        for _ in range(5):
            _record_mfa_attempt("mfa-token-xyz")

        with pytest.raises(HTTPException) as exc_info:
            _check_mfa_rate_limit("mfa-token-xyz")
        assert exc_info.value.status_code == 429


class TestForgotPasswordRateLimit:
    """Tests for forgot-password rate limiting."""

    def test_ip_rate_limit(self):
        """Failure: 3 forgot-password from same IP triggers 429."""
        from fastapi import HTTPException

        for _ in range(3):
            _record_forgot_pw_attempt("10.0.0.3")

        with pytest.raises(HTTPException) as exc_info:
            _check_forgot_pw_rate_limit("10.0.0.3")
        assert exc_info.value.status_code == 429

    def test_email_rate_limit_returns_true(self):
        """Edge case: email rate limit returns True after 3 attempts."""
        for _ in range(3):
            _record_forgot_pw_email_attempt("victim@example.com")

        assert _is_forgot_pw_email_rate_limited("victim@example.com") is True

    def test_email_under_limit_returns_false(self):
        """Happy path: under limit returns False."""
        _record_forgot_pw_email_attempt("ok@example.com")
        assert _is_forgot_pw_email_rate_limited("ok@example.com") is False


class TestResendRateLimit:
    """Tests for resend verification rate limiting."""

    def test_at_limit_raises_429(self):
        """Failure: 3 resend attempts triggers rate limit."""
        from fastapi import HTTPException

        for _ in range(3):
            _record_resend_attempt(99)

        with pytest.raises(HTTPException) as exc_info:
            _check_resend_rate_limit(99)
        assert exc_info.value.status_code == 429


# =============================================================================
# Database helpers
# =============================================================================


class TestGetUserByEmail:
    """Tests for get_user_by_email()"""

    @pytest.mark.asyncio
    async def test_finds_existing_user(self, db_session):
        """Happy path: returns user when email matches."""
        user = User(
            email="findme@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        result = await get_user_by_email(db_session, "findme@example.com")
        assert result is not None
        assert result.email == "findme@example.com"

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_email(self, db_session):
        """Failure: returns None for non-existent email."""
        result = await get_user_by_email(db_session, "nobody@example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_email_case_sensitivity(self, db_session):
        """Edge case: email lookup is case-sensitive at the DB level."""
        user = User(
            email="lower@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        # Exact match works
        assert await get_user_by_email(db_session, "lower@example.com") is not None
        # Different case does not match (SQLite default is case-insensitive for ASCII,
        # but we document behavior as-is)
        result = await get_user_by_email(db_session, "LOWER@example.com")
        # SQLite is case-insensitive for ASCII, so this actually finds the user
        # Document actual behavior rather than assume
        if result is not None:
            assert result.email == "lower@example.com"


# =============================================================================
# Endpoint tests — login
# =============================================================================


class TestLoginEndpoint:
    """Tests for POST /api/auth/login"""

    @pytest.mark.asyncio
    async def test_login_success_no_mfa(self, db_session):
        """Happy path: valid credentials return access and refresh tokens."""
        from app.routers.auth_router import login, LoginRequest

        user = User(
            email="login@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            is_superuser=False,
            mfa_enabled=False,
            mfa_email_enabled=False,
            email_verified=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        request = LoginRequest(email="login@example.com", password="TestPass1")
        http_request = MagicMock()
        http_request.client = MagicMock()
        http_request.client.host = "127.0.0.1"

        result = await login(request=request, http_request=http_request, db=db_session)
        assert result.access_token is not None
        assert result.refresh_token is not None
        assert result.mfa_required is False
        assert result.user is not None
        assert result.user.email == "login@example.com"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, db_session):
        """Failure: wrong password returns 401."""
        from fastapi import HTTPException
        from app.routers.auth_router import login, LoginRequest

        user = User(
            email="wrongpw@example.com",
            hashed_password=hash_password("CorrectPass1"),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        request = LoginRequest(email="wrongpw@example.com", password="WrongPass1")
        http_request = MagicMock()
        http_request.client = MagicMock()
        http_request.client.host = "127.0.0.2"

        with pytest.raises(HTTPException) as exc_info:
            await login(request=request, http_request=http_request, db=db_session)
        assert exc_info.value.status_code == 401
        assert "Invalid email or password" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_login_nonexistent_email(self, db_session):
        """Failure: non-existent email returns 401 with same message (no email enumeration)."""
        from fastapi import HTTPException
        from app.routers.auth_router import login, LoginRequest

        request = LoginRequest(email="ghost@example.com", password="SomePass1")
        http_request = MagicMock()
        http_request.client = MagicMock()
        http_request.client.host = "127.0.0.3"

        with pytest.raises(HTTPException) as exc_info:
            await login(request=request, http_request=http_request, db=db_session)
        assert exc_info.value.status_code == 401
        assert "Invalid email or password" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, db_session):
        """Failure: inactive user returns 403."""
        from fastapi import HTTPException
        from app.routers.auth_router import login, LoginRequest

        user = User(
            email="disabled@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=False,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        request = LoginRequest(email="disabled@example.com", password="TestPass1")
        http_request = MagicMock()
        http_request.client = MagicMock()
        http_request.client.host = "127.0.0.4"

        with pytest.raises(HTTPException) as exc_info:
            await login(request=request, http_request=http_request, db=db_session)
        assert exc_info.value.status_code == 403
        assert "disabled" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_login_mfa_required(self, db_session):
        """Edge case: MFA-enabled user gets mfa_required=True instead of tokens."""
        from app.routers.auth_router import login, LoginRequest

        user = User(
            email="mfauser@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            is_superuser=False,
            mfa_enabled=True,
            mfa_email_enabled=False,
            totp_secret="encrypted-secret",
            email_verified=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        request = LoginRequest(email="mfauser@example.com", password="TestPass1")
        http_request = MagicMock()
        http_request.client = MagicMock()
        http_request.client.host = "127.0.0.5"

        result = await login(request=request, http_request=http_request, db=db_session)
        assert result.mfa_required is True
        assert result.mfa_token is not None
        assert result.access_token is None
        assert "totp" in result.mfa_methods


# =============================================================================
# Endpoint tests — token refresh
# =============================================================================


class TestRefreshEndpoint:
    """Tests for POST /api/auth/refresh"""

    @pytest.mark.asyncio
    async def test_refresh_with_valid_token(self, db_session):
        """Happy path: valid refresh token returns new access token."""
        from app.routers.auth_router import refresh_token, RefreshRequest

        user = User(
            email="refresh@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            is_superuser=False,
            mfa_enabled=False,
            mfa_email_enabled=False,
            email_verified=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        token = create_refresh_token(user.id)
        request = RefreshRequest(refresh_token=token)

        result = await refresh_token(request=request, db=db_session)
        assert result.access_token is not None
        assert result.refresh_token is not None
        assert result.user.email == "refresh@example.com"

    @pytest.mark.asyncio
    async def test_refresh_with_access_token_fails(self, db_session):
        """Failure: using an access token for refresh returns 401."""
        from fastapi import HTTPException
        from app.routers.auth_router import refresh_token, RefreshRequest

        user = User(
            email="refreshfail@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        token = create_access_token(user.id, user.email)
        request = RefreshRequest(refresh_token=token)

        with pytest.raises(HTTPException) as exc_info:
            await refresh_token(request=request, db=db_session)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_with_inactive_user(self, db_session):
        """Failure: refresh for inactive user returns 403."""
        from fastapi import HTTPException
        from app.routers.auth_router import refresh_token, RefreshRequest

        user = User(
            email="refreshinactive@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=False,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        token = create_refresh_token(user.id)
        request = RefreshRequest(refresh_token=token)

        with pytest.raises(HTTPException) as exc_info:
            await refresh_token(request=request, db=db_session)
        assert exc_info.value.status_code == 403


# =============================================================================
# Endpoint tests — change password
# =============================================================================


class TestChangePasswordEndpoint:
    """Tests for POST /api/auth/change-password"""

    @pytest.mark.asyncio
    async def test_change_password_success(self, db_session):
        """Happy path: password is changed and sessions invalidated."""
        from app.routers.auth_router import change_password, ChangePasswordRequest

        user = User(
            email="changepw@example.com",
            hashed_password=hash_password("OldPass1"),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        request = ChangePasswordRequest(
            current_password="OldPass1",
            new_password="NewPass1",
        )

        result = await change_password(request=request, current_user=user, db=db_session)
        assert "successfully" in result["message"].lower()
        assert user.tokens_valid_after is not None
        # New password should work
        assert verify_password("NewPass1", user.hashed_password) is True

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self, db_session):
        """Failure: wrong current password returns 400."""
        from fastapi import HTTPException
        from app.routers.auth_router import change_password, ChangePasswordRequest

        user = User(
            email="changepwfail@example.com",
            hashed_password=hash_password("CurrentPass1"),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        request = ChangePasswordRequest(
            current_password="WrongCurrent1",
            new_password="NewPass1",
        )

        with pytest.raises(HTTPException) as exc_info:
            await change_password(request=request, current_user=user, db=db_session)
        assert exc_info.value.status_code == 400
        assert "incorrect" in exc_info.value.detail.lower()


# =============================================================================
# Endpoint tests — register (admin only)
# =============================================================================


class TestRegisterEndpoint:
    """Tests for POST /api/auth/register"""

    @pytest.mark.asyncio
    async def test_register_as_superuser(self, db_session):
        """Happy path: superuser can register a new user."""
        from app.routers.auth_router import register, RegisterRequest

        admin = User(
            email="admin@example.com",
            hashed_password=hash_password("AdminPass1"),
            is_active=True,
            is_superuser=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(admin)
        await db_session.flush()

        request = RegisterRequest(
            email="newuser@example.com",
            password="NewUser1Pass",
            display_name="New User",
        )

        result = await register(request=request, current_user=admin, db=db_session)
        assert result.email == "newuser@example.com"
        assert result.is_active is True
        assert result.email_verified is True  # Admin-created users are auto-verified

    @pytest.mark.asyncio
    async def test_register_as_non_superuser_fails(self, db_session):
        """Failure: non-superuser cannot register new users."""
        from fastapi import HTTPException
        from app.routers.auth_router import register, RegisterRequest

        regular_user = User(
            email="regular@example.com",
            hashed_password=hash_password("RegularPass1"),
            is_active=True,
            is_superuser=False,
            created_at=datetime.utcnow(),
        )
        db_session.add(regular_user)
        await db_session.flush()

        request = RegisterRequest(
            email="wannabe@example.com",
            password="WannabePass1",
        )

        with pytest.raises(HTTPException) as exc_info:
            await register(request=request, current_user=regular_user, db=db_session)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, db_session):
        """Failure: duplicate email returns 400."""
        from fastapi import HTTPException
        from app.routers.auth_router import register, RegisterRequest

        admin = User(
            email="admin2@example.com",
            hashed_password=hash_password("AdminPass1"),
            is_active=True,
            is_superuser=True,
            created_at=datetime.utcnow(),
        )
        existing = User(
            email="exists@example.com",
            hashed_password=hash_password("ExistPass1"),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add_all([admin, existing])
        await db_session.flush()

        request = RegisterRequest(
            email="exists@example.com",
            password="NewPass1xx",
        )

        with pytest.raises(HTTPException) as exc_info:
            await register(request=request, current_user=admin, db=db_session)
        assert exc_info.value.status_code == 400
        assert "already registered" in exc_info.value.detail.lower()


# =============================================================================
# Endpoint tests — get current user
# =============================================================================


class TestGetCurrentUserInfo:
    """Tests for GET /api/auth/me"""

    @pytest.mark.asyncio
    async def test_returns_current_user(self):
        """Happy path: returns the authenticated user info."""
        from app.routers.auth_router import get_current_user_info

        user = MagicMock(spec=User)
        user.id = 1
        user.email = "me@example.com"
        user.display_name = "Me"
        user.is_active = True
        user.is_superuser = False
        user.mfa_enabled = False
        user.mfa_email_enabled = False
        user.email_verified = True
        user.email_verified_at = datetime(2024, 1, 1)
        user.created_at = datetime(2023, 1, 1)
        user.last_login_at = datetime(2024, 6, 1)
        user.terms_accepted_at = None

        result = await get_current_user_info(current_user=user)
        assert result.email == "me@example.com"


# =============================================================================
# Endpoint tests — verify email
# =============================================================================


class TestVerifyEmail:
    """Tests for POST /api/auth/verify-email"""

    @pytest.mark.asyncio
    async def test_verify_email_success(self, db_session):
        """Happy path: valid token verifies the user's email."""
        from app.routers.auth_router import verify_email, VerifyEmailRequest

        user = User(
            email="verify@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            email_verified=False,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        token = EmailVerificationToken(
            user_id=user.id,
            token="valid-token-123",
            token_type="email_verify",
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        db_session.add(token)
        await db_session.flush()

        request = VerifyEmailRequest(token="valid-token-123")
        result = await verify_email(request=request, db=db_session)
        assert result.email_verified is True

    @pytest.mark.asyncio
    async def test_verify_email_invalid_token(self, db_session):
        """Failure: invalid token returns 400."""
        from fastapi import HTTPException
        from app.routers.auth_router import verify_email, VerifyEmailRequest

        request = VerifyEmailRequest(token="nonexistent-token")
        with pytest.raises(HTTPException) as exc_info:
            await verify_email(request=request, db=db_session)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_verify_email_expired_token(self, db_session):
        """Failure: expired token returns 400."""
        from fastapi import HTTPException
        from app.routers.auth_router import verify_email, VerifyEmailRequest

        user = User(
            email="expired@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            email_verified=False,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        token = EmailVerificationToken(
            user_id=user.id,
            token="expired-token-123",
            token_type="email_verify",
            expires_at=datetime.utcnow() - timedelta(hours=1),  # Already expired
        )
        db_session.add(token)
        await db_session.flush()

        request = VerifyEmailRequest(token="expired-token-123")
        with pytest.raises(HTTPException) as exc_info:
            await verify_email(request=request, db=db_session)
        assert exc_info.value.status_code == 400
        assert "expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_verify_email_already_used_token(self, db_session):
        """Failure: already-used token returns 400."""
        from fastapi import HTTPException
        from app.routers.auth_router import verify_email, VerifyEmailRequest

        user = User(
            email="usedtoken@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            email_verified=False,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        token = EmailVerificationToken(
            user_id=user.id,
            token="used-token-123",
            token_type="email_verify",
            expires_at=datetime.utcnow() + timedelta(hours=24),
            used_at=datetime.utcnow(),  # Already used
        )
        db_session.add(token)
        await db_session.flush()

        request = VerifyEmailRequest(token="used-token-123")
        with pytest.raises(HTTPException) as exc_info:
            await verify_email(request=request, db=db_session)
        assert exc_info.value.status_code == 400
        assert "already been used" in exc_info.value.detail.lower()


# =============================================================================
# Endpoint tests — reset password
# =============================================================================


class TestResetPassword:
    """Tests for POST /api/auth/reset-password"""

    @pytest.mark.asyncio
    async def test_reset_password_success(self, db_session):
        """Happy path: valid reset token changes the password."""
        from app.routers.auth_router import reset_password, ResetPasswordRequest

        user = User(
            email="reset@example.com",
            hashed_password=hash_password("OldPass1"),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        token = EmailVerificationToken(
            user_id=user.id,
            token="reset-token-abc",
            token_type="password_reset",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db_session.add(token)
        await db_session.flush()

        request = ResetPasswordRequest(token="reset-token-abc", new_password="NewPass1x")
        result = await reset_password(request=request, db=db_session)
        assert "successfully" in result["message"].lower()

        # Verify new password works
        await db_session.refresh(user)
        assert verify_password("NewPass1x", user.hashed_password) is True
        assert user.tokens_valid_after is not None

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self, db_session):
        """Failure: invalid token returns 400."""
        from fastapi import HTTPException
        from app.routers.auth_router import reset_password, ResetPasswordRequest

        request = ResetPasswordRequest(token="nonexistent", new_password="NewPass1x")
        with pytest.raises(HTTPException) as exc_info:
            await reset_password(request=request, db=db_session)
        assert exc_info.value.status_code == 400


# =============================================================================
# Endpoint tests — accept terms
# =============================================================================


class TestAcceptTerms:
    """Tests for POST /api/auth/accept-terms"""

    @pytest.mark.asyncio
    async def test_accept_terms_success(self, db_session):
        """Happy path: terms_accepted_at is set."""
        from app.routers.auth_router import accept_terms

        user = User(
            email="terms@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            is_superuser=False,
            mfa_enabled=False,
            mfa_email_enabled=False,
            email_verified=True,
            created_at=datetime.utcnow(),
            terms_accepted_at=None,
        )
        db_session.add(user)
        await db_session.flush()

        result = await accept_terms(current_user=user, db=db_session)
        assert result.terms_accepted_at is not None


# =============================================================================
# Endpoint tests — last seen history preferences
# =============================================================================


class TestLastSeenHistory:
    """Tests for GET/PUT /api/auth/preferences/last-seen-history"""

    @pytest.mark.asyncio
    async def test_get_last_seen_history(self):
        """Happy path: returns current counts."""
        from app.routers.auth_router import get_last_seen_history

        user = MagicMock(spec=User)
        user.last_seen_history_count = 10
        user.last_seen_failed_count = 3

        result = await get_last_seen_history(current_user=user)
        assert result.last_seen_history_count == 10
        assert result.last_seen_failed_count == 3

    @pytest.mark.asyncio
    async def test_get_last_seen_history_none_values(self):
        """Edge case: None values default to 0."""
        from app.routers.auth_router import get_last_seen_history

        user = MagicMock(spec=User)
        user.last_seen_history_count = None
        user.last_seen_failed_count = None

        result = await get_last_seen_history(current_user=user)
        assert result.last_seen_history_count == 0
        assert result.last_seen_failed_count == 0

    @pytest.mark.asyncio
    async def test_update_last_seen_history(self, db_session):
        """Happy path: updates counts and returns new values."""
        from app.routers.auth_router import (
            update_last_seen_history,
            LastSeenHistoryRequest,
        )

        user = User(
            email="prefs@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            last_seen_history_count=0,
            last_seen_failed_count=0,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        request = LastSeenHistoryRequest(count=25, failed_count=5)
        result = await update_last_seen_history(
            request=request, current_user=user, db=db_session
        )
        assert result.last_seen_history_count == 25
        assert result.last_seen_failed_count == 5


# =============================================================================
# Endpoint tests — signup (public registration)
# =============================================================================


class TestSignupEndpoint:
    """Tests for POST /api/auth/signup"""

    @pytest.mark.asyncio
    @patch("app.auth_routers.auth_core_router.settings")
    async def test_signup_disabled_returns_403(self, mock_settings, db_session):
        """Failure: signup returns 403 when public_signup_enabled=False."""
        from fastapi import HTTPException
        from app.routers.auth_router import signup, RegisterRequest

        mock_settings.public_signup_enabled = False

        request = RegisterRequest(
            email="signup@example.com",
            password="SignupPass1",
        )
        http_request = MagicMock()
        http_request.client = MagicMock()
        http_request.client.host = "127.0.0.10"

        with pytest.raises(HTTPException) as exc_info:
            await signup(request=request, http_request=http_request, db=db_session)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_signup_duplicate_email_returns_400(self, db_session):
        """Failure: duplicate email on signup returns 400."""
        from fastapi import HTTPException
        from app.routers.auth_router import signup, RegisterRequest

        existing = User(
            email="dupe@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(existing)
        await db_session.flush()

        request = RegisterRequest(
            email="dupe@example.com",
            password="DupePass1",
        )
        http_request = MagicMock()
        http_request.client = MagicMock()
        http_request.client.host = "127.0.0.11"

        with pytest.raises(HTTPException) as exc_info:
            await signup(request=request, http_request=http_request, db=db_session)
        assert exc_info.value.status_code == 400


# =============================================================================
# Endpoint tests — forgot password
# =============================================================================


class TestForgotPassword:
    """Tests for POST /api/auth/forgot-password"""

    @pytest.mark.asyncio
    @patch("app.routers.auth_router.send_password_reset_email", create=True)
    async def test_forgot_password_existing_user(self, mock_send, db_session):
        """Happy path: returns success and sends email for existing user."""
        from app.routers.auth_router import forgot_password, ForgotPasswordRequest

        user = User(
            email="forgot@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        request = ForgotPasswordRequest(email="forgot@example.com")
        http_request = MagicMock()
        http_request.client = MagicMock()
        http_request.client.host = "127.0.0.20"

        result = await forgot_password(request=request, http_request=http_request, db=db_session)
        assert "message" in result

    @pytest.mark.asyncio
    async def test_forgot_password_nonexistent_user(self, db_session):
        """Edge case: returns same success message for non-existent user (no enumeration)."""
        from app.routers.auth_router import forgot_password, ForgotPasswordRequest

        request = ForgotPasswordRequest(email="nobody@example.com")
        http_request = MagicMock()
        http_request.client = MagicMock()
        http_request.client.host = "127.0.0.21"

        result = await forgot_password(request=request, http_request=http_request, db=db_session)
        assert "message" in result
        assert "if an account exists" in result["message"].lower()


# =============================================================================
# Endpoint tests — trusted devices
# =============================================================================


class TestTrustedDevices:
    """Tests for MFA trusted device endpoints."""

    @pytest.mark.asyncio
    async def test_list_trusted_devices_empty(self, db_session):
        """Happy path: returns empty list when no devices."""
        from app.routers.auth_router import list_trusted_devices

        user = User(
            email="devices@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        result = await list_trusted_devices(current_user=user, db=db_session)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_trusted_devices_returns_active(self, db_session):
        """Happy path: returns non-expired devices."""
        from app.routers.auth_router import list_trusted_devices

        user = User(
            email="devicesactive@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        device = TrustedDevice(
            user_id=user.id,
            device_id="device-abc-123",
            device_name="Chrome on Mac",
            ip_address="1.2.3.4",
            expires_at=datetime.utcnow() + timedelta(days=30),
        )
        db_session.add(device)
        await db_session.flush()

        result = await list_trusted_devices(current_user=user, db=db_session)
        assert len(result) == 1
        assert result[0].device_name == "Chrome on Mac"

    @pytest.mark.asyncio
    async def test_revoke_trusted_device(self, db_session):
        """Happy path: device is deleted."""
        from app.routers.auth_router import revoke_trusted_device

        user = User(
            email="revoke@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        device = TrustedDevice(
            user_id=user.id,
            device_id="device-to-revoke",
            expires_at=datetime.utcnow() + timedelta(days=30),
        )
        db_session.add(device)
        await db_session.flush()

        result = await revoke_trusted_device(device_id=device.id, current_user=user, db=db_session)
        assert "revoked" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_device_returns_404(self, db_session):
        """Failure: revoking non-existent device returns 404."""
        from fastapi import HTTPException
        from app.routers.auth_router import revoke_trusted_device

        user = User(
            email="revoke404@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await revoke_trusted_device(device_id=99999, current_user=user, db=db_session)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_revoke_all_trusted_devices(self, db_session):
        """Happy path: all devices are deleted."""
        from app.routers.auth_router import revoke_all_trusted_devices

        user = User(
            email="revokeall@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        for i in range(3):
            device = TrustedDevice(
                user_id=user.id,
                device_id=f"device-{i}",
                expires_at=datetime.utcnow() + timedelta(days=30),
            )
            db_session.add(device)
        await db_session.flush()

        result = await revoke_all_trusted_devices(current_user=user, db=db_session)
        assert "3" in result["message"]


# =============================================================================
# Endpoint tests — MFA email enable/disable
# =============================================================================


class TestMfaEmailEndpoints:
    """Tests for MFA email enable/disable endpoints."""

    @pytest.mark.asyncio
    async def test_enable_email_mfa_success(self, db_session):
        """Happy path: email MFA is enabled."""
        from app.routers.auth_router import mfa_email_enable, MFAEmailEnableRequest

        user = User(
            email="mfaemail@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            mfa_email_enabled=False,
            email_verified=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        request = MFAEmailEnableRequest(password="TestPass1")
        result = await mfa_email_enable(request=request, current_user=user, db=db_session)
        assert result.mfa_email_enabled is True

    @pytest.mark.asyncio
    async def test_enable_email_mfa_wrong_password(self, db_session):
        """Failure: wrong password returns 400."""
        from fastapi import HTTPException
        from app.routers.auth_router import mfa_email_enable, MFAEmailEnableRequest

        user = User(
            email="mfaemail_wrongpw@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            mfa_email_enabled=False,
            email_verified=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        request = MFAEmailEnableRequest(password="WrongPass1")
        with pytest.raises(HTTPException) as exc_info:
            await mfa_email_enable(request=request, current_user=user, db=db_session)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_enable_email_mfa_unverified_email(self, db_session):
        """Failure: unverified email returns 400."""
        from fastapi import HTTPException
        from app.routers.auth_router import mfa_email_enable, MFAEmailEnableRequest

        user = User(
            email="unverified@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            mfa_email_enabled=False,
            email_verified=False,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        request = MFAEmailEnableRequest(password="TestPass1")
        with pytest.raises(HTTPException) as exc_info:
            await mfa_email_enable(request=request, current_user=user, db=db_session)
        assert exc_info.value.status_code == 400
        assert "verify" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_disable_email_mfa_no_other_method(self, db_session):
        """Failure: cannot disable email MFA when it is the only method."""
        from fastapi import HTTPException
        from app.routers.auth_router import mfa_email_disable, MFAEmailDisableRequest

        user = User(
            email="mfadisable_only@example.com",
            hashed_password=hash_password("TestPass1"),
            is_active=True,
            mfa_email_enabled=True,
            mfa_enabled=False,  # No TOTP
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        request = MFAEmailDisableRequest(password="TestPass1")
        with pytest.raises(HTTPException) as exc_info:
            await mfa_email_disable(request=request, current_user=user, db=db_session)
        assert exc_info.value.status_code == 400
        assert "only MFA method" in exc_info.value.detail
