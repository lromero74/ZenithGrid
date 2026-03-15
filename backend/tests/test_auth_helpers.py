"""
Tests for backend/app/auth_routers/helpers.py

Covers password hashing/verification, JWT token creation/decoding,
device name parsing, IP geolocation, user response building, and
MFA token decoding.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from jose import jwt

from app.auth_routers.helpers import (
    _build_user_response,
    _decode_mfa_token,
    _geolocate_ip,
    _parse_device_name,
    create_access_token,
    create_device_trust_token,
    create_mfa_token,
    create_refresh_token,
    decode_device_trust_token,
    get_user_by_email,
    hash_password,
    verify_password,
)
from app.config import settings


# =============================================================================
# Password hashing and verification
# =============================================================================


class TestHashPassword:
    """Tests for hash_password()"""

    def test_hash_password_returns_bcrypt_string(self):
        """Happy path: hashing a password returns a bcrypt-formatted string."""
        result = hash_password("SecurePass1")
        assert isinstance(result, str)
        assert result.startswith("$2b$")

    def test_hash_password_different_salts(self):
        """Edge case: same password produces different hashes (random salt)."""
        h1 = hash_password("SamePass1")
        h2 = hash_password("SamePass1")
        assert h1 != h2

    def test_hash_password_empty_string(self):
        """Edge case: empty string can be hashed without error."""
        result = hash_password("")
        assert result.startswith("$2b$")


class TestVerifyPassword:
    """Tests for verify_password()"""

    def test_verify_password_correct(self):
        """Happy path: correct password verifies successfully."""
        hashed = hash_password("MyPassword123")
        assert verify_password("MyPassword123", hashed) is True

    def test_verify_password_incorrect(self):
        """Failure: wrong password fails verification."""
        hashed = hash_password("MyPassword123")
        assert verify_password("WrongPassword", hashed) is False

    def test_verify_password_unicode(self):
        """Edge case: unicode passwords hash and verify correctly."""
        hashed = hash_password("p@ssw0rd!")
        assert verify_password("p@ssw0rd!", hashed) is True


# =============================================================================
# JWT token creation
# =============================================================================


class TestCreateAccessToken:
    """Tests for create_access_token()"""

    def test_create_access_token_valid_jwt(self):
        """Happy path: creates a decodable JWT with correct claims."""
        token = create_access_token(user_id=1, email="test@example.com")
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert payload["sub"] == "1"
        assert payload["email"] == "test@example.com"
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "exp" in payload

    def test_create_access_token_with_session_id(self):
        """Happy path: session_id is included when provided."""
        token = create_access_token(user_id=1, email="a@b.com", session_id="sess-123")
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert payload["sid"] == "sess-123"

    def test_create_access_token_without_session_id(self):
        """Edge case: no session_id means no 'sid' claim in the token."""
        token = create_access_token(user_id=1, email="a@b.com")
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert "sid" not in payload

    def test_create_access_token_unique_jti(self):
        """Edge case: each token has a unique JTI for revocation support."""
        t1 = create_access_token(user_id=1, email="a@b.com")
        t2 = create_access_token(user_id=1, email="a@b.com")
        p1 = jwt.decode(t1, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        p2 = jwt.decode(t2, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert p1["jti"] != p2["jti"]


class TestCreateRefreshToken:
    """Tests for create_refresh_token()"""

    def test_create_refresh_token_valid_jwt(self):
        """Happy path: creates a refresh token with correct type claim."""
        token = create_refresh_token(user_id=42)
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert payload["sub"] == "42"
        assert payload["type"] == "refresh"
        assert "jti" in payload

    def test_create_refresh_token_with_session_id(self):
        """Happy path: session_id is included when provided."""
        token = create_refresh_token(user_id=42, session_id="s-abc")
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert payload["sid"] == "s-abc"

    def test_create_refresh_token_longer_expiry_than_access(self):
        """Edge case: refresh token expires later than access token."""
        access = create_access_token(user_id=1, email="a@b.com")
        refresh = create_refresh_token(user_id=1)
        a_payload = jwt.decode(access, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        r_payload = jwt.decode(refresh, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert r_payload["exp"] > a_payload["exp"]


class TestCreateMfaToken:
    """Tests for create_mfa_token()"""

    def test_create_mfa_token_valid(self):
        """Happy path: creates a short-lived MFA token."""
        token = create_mfa_token(user_id=5)
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert payload["sub"] == "5"
        assert payload["type"] == "mfa"

    def test_create_mfa_token_short_expiry(self):
        """Edge case: MFA token expires within ~5 minutes."""
        token = create_mfa_token(user_id=5)
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        # exp should be within 5 minutes + a few seconds tolerance
        now_ts = datetime.utcnow().timestamp()
        assert payload["exp"] - now_ts <= 305  # 5 min + 5 sec tolerance
        assert payload["exp"] - now_ts > 200  # At least ~3 min


# =============================================================================
# Device trust tokens
# =============================================================================


class TestDeviceTrustToken:
    """Tests for create_device_trust_token() and decode_device_trust_token()"""

    def test_create_and_decode_round_trip(self):
        """Happy path: token can be created and decoded successfully."""
        token = create_device_trust_token(user_id=1, device_id="dev-abc")
        payload = decode_device_trust_token(token)
        assert payload is not None
        assert int(payload["sub"]) == 1
        assert payload["device_id"] == "dev-abc"
        assert payload["type"] == "device_trust"

    def test_decode_invalid_token_returns_none(self):
        """Failure: garbage token returns None."""
        result = decode_device_trust_token("not.a.valid.token")
        assert result is None

    def test_decode_wrong_type_returns_none(self):
        """Failure: a valid JWT with wrong type returns None."""
        # Create an access token (type='access') and try to decode as device_trust
        access = create_access_token(user_id=1, email="a@b.com")
        result = decode_device_trust_token(access)
        assert result is None

    def test_decode_expired_token_returns_none(self):
        """Failure: expired device trust token returns None."""
        payload = {
            "sub": 1,
            "type": "device_trust",
            "device_id": "dev-old",
            "exp": datetime.utcnow() - timedelta(days=1),
            "iat": datetime.utcnow() - timedelta(days=31),
        }
        expired_token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        result = decode_device_trust_token(expired_token)
        assert result is None


# =============================================================================
# _parse_device_name
# =============================================================================


class TestParseDeviceName:
    """Tests for _parse_device_name() — user-agent parsing."""

    def test_parse_chrome_on_mac(self):
        """Happy path: Chrome on macOS."""
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"
        assert _parse_device_name(ua) == "Chrome on Mac"

    def test_parse_safari_on_iphone(self):
        """Happy path: Safari on iPhone."""
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15 Safari/604.1"
        assert _parse_device_name(ua) == "Safari on iPhone"

    def test_parse_firefox_on_windows(self):
        """Happy path: Firefox on Windows."""
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
        assert _parse_device_name(ua) == "Firefox on Windows"

    def test_parse_edge_on_windows(self):
        """Happy path: Edge on Windows."""
        ua = "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/120 Safari/537.36 Edg/120.0"
        assert _parse_device_name(ua) == "Edge on Windows"

    def test_parse_chrome_on_android(self):
        """Happy path: Chrome on Android."""
        ua = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Safari/537.36"
        assert _parse_device_name(ua) == "Chrome on Android"

    def test_parse_chrome_on_linux(self):
        """Happy path: Chrome on Linux."""
        ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
        assert _parse_device_name(ua) == "Chrome on Linux"

    def test_parse_ipad(self):
        """Happy path: Safari on iPad."""
        ua = "Mozilla/5.0 (iPad; CPU OS 17_0) AppleWebKit/605.1.15 Safari/604.1"
        assert _parse_device_name(ua) == "Safari on iPad"

    def test_parse_empty_user_agent(self):
        """Edge case: empty string returns 'Unknown Device'."""
        assert _parse_device_name("") == "Unknown Device"

    def test_parse_none_user_agent(self):
        """Edge case: None returns 'Unknown Device'."""
        assert _parse_device_name(None) == "Unknown Device"

    def test_parse_unknown_browser_and_os(self):
        """Edge case: unrecognizable UA returns generic labels."""
        assert _parse_device_name("curl/7.88.1") == "Browser on Unknown OS"


# =============================================================================
# _geolocate_ip
# =============================================================================


class TestGeolocateIp:
    """Tests for _geolocate_ip() — IP geolocation via external API."""

    @pytest.mark.asyncio
    async def test_geolocate_localhost_returns_none(self):
        """Edge case: localhost IPs are skipped."""
        assert await _geolocate_ip("127.0.0.1") is None
        assert await _geolocate_ip("::1") is None
        assert await _geolocate_ip("localhost") is None

    @pytest.mark.asyncio
    async def test_geolocate_unknown_returns_none(self):
        """Edge case: 'unknown' IP returns None."""
        assert await _geolocate_ip("unknown") is None

    @pytest.mark.asyncio
    async def test_geolocate_empty_returns_none(self):
        """Edge case: empty/None IP returns None."""
        assert await _geolocate_ip("") is None
        assert await _geolocate_ip(None) is None

    @pytest.mark.asyncio
    @patch("app.auth_routers.helpers.httpx.AsyncClient")
    async def test_geolocate_success(self, mock_client_cls):
        """Happy path: successful API response returns location string."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "success",
            "city": "Austin",
            "regionName": "Texas",
            "country": "United States",
        }
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await _geolocate_ip("8.8.8.8")
        assert result == "Austin, Texas, United States"

    @pytest.mark.asyncio
    @patch("app.auth_routers.helpers.httpx.AsyncClient")
    async def test_geolocate_api_failure_returns_none(self, mock_client_cls):
        """Failure: API error returns None gracefully."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await _geolocate_ip("8.8.8.8")
        assert result is None

    @pytest.mark.asyncio
    @patch("app.auth_routers.helpers.httpx.AsyncClient")
    async def test_geolocate_api_fail_status(self, mock_client_cls):
        """Failure: API returns fail status, result is None."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "fail"}
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await _geolocate_ip("10.0.0.1")
        assert result is None


# =============================================================================
# _build_user_response
# =============================================================================


class TestBuildUserResponse:
    """Tests for _build_user_response() — User model to UserResponse."""

    def _make_user(self, **overrides):
        """Create a mock User object with default values."""
        user = MagicMock()
        user.id = overrides.get("id", 1)
        user.email = overrides.get("email", "test@example.com")
        user.display_name = overrides.get("display_name", "Test User")
        user.is_active = overrides.get("is_active", True)
        user.is_superuser = overrides.get("is_superuser", False)
        user.mfa_enabled = overrides.get("mfa_enabled", False)
        user.mfa_email_enabled = overrides.get("mfa_email_enabled", False)
        user.email_verified = overrides.get("email_verified", True)
        user.email_verified_at = overrides.get("email_verified_at", datetime(2024, 1, 1))
        user.created_at = overrides.get("created_at", datetime(2024, 1, 1))
        user.last_login_at = overrides.get("last_login_at", datetime(2024, 6, 1))
        user.terms_accepted_at = overrides.get("terms_accepted_at", datetime(2024, 1, 1))
        user.last_seen_history_count = overrides.get("last_seen_history_count", 5)
        user.last_seen_failed_count = overrides.get("last_seen_failed_count", 2)
        user.groups = overrides.get("groups", [])
        return user

    def test_build_user_response_basic(self):
        """Happy path: builds a UserResponse from a User object."""
        user = self._make_user()
        response = _build_user_response(user)
        assert response.id == 1
        assert response.email == "test@example.com"
        assert response.display_name == "Test User"
        assert response.is_active is True
        assert response.mfa_enabled is False

    def test_build_user_response_with_groups_and_permissions(self):
        """Happy path: permissions are flattened from groups -> roles -> permissions."""
        perm1 = MagicMock()
        perm1.name = "manage_bots"
        perm2 = MagicMock()
        perm2.name = "view_reports"
        role = MagicMock()
        role.permissions = [perm1, perm2]
        group = MagicMock()
        group.id = 1
        group.name = "Admins"
        group.description = "Admin group"
        group.roles = [role]
        user = self._make_user(groups=[group])

        response = _build_user_response(user)
        assert set(response.permissions) == {"manage_bots", "view_reports"}
        assert len(response.groups) == 1

    def test_build_user_response_no_groups(self):
        """Edge case: user with no groups has empty permissions."""
        user = self._make_user(groups=[])
        response = _build_user_response(user)
        assert response.permissions == []
        assert response.groups == []

    def test_build_user_response_none_groups(self):
        """Edge case: user.groups is None (not loaded)."""
        user = self._make_user()
        user.groups = None
        response = _build_user_response(user)
        assert response.permissions == []

    def test_build_user_response_null_last_seen_count(self):
        """Edge case: None last_seen_history_count defaults to 0."""
        user = self._make_user(last_seen_history_count=None)
        response = _build_user_response(user)
        assert response.last_seen_history_count == 0

    def test_build_user_response_deduplicates_permissions(self):
        """Edge case: duplicate permissions across roles are deduplicated."""
        perm = MagicMock()
        perm.name = "view_reports"
        role1 = MagicMock()
        role1.permissions = [perm]
        role2 = MagicMock()
        role2.permissions = [perm]
        group = MagicMock()
        group.id = 1
        group.name = "G"
        group.description = None
        group.roles = [role1, role2]
        user = self._make_user(groups=[group])

        response = _build_user_response(user)
        assert response.permissions == ["view_reports"]


# =============================================================================
# _decode_mfa_token
# =============================================================================


class TestDecodeMfaToken:
    """Tests for _decode_mfa_token() — MFA JWT decoding."""

    @pytest.mark.asyncio
    async def test_decode_valid_mfa_token(self):
        """Happy path: valid MFA token returns user_id."""
        token = create_mfa_token(user_id=42)
        user_id = await _decode_mfa_token(token)
        assert user_id == 42

    @pytest.mark.asyncio
    async def test_decode_invalid_token_raises(self):
        """Failure: garbage token raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            await _decode_mfa_token("invalid.token.here")
        assert exc_info.value.status_code == 401
        assert "Invalid or expired" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_decode_wrong_type_raises(self):
        """Failure: non-MFA token type raises 401."""
        access_token = create_access_token(user_id=1, email="a@b.com")
        with pytest.raises(HTTPException) as exc_info:
            await _decode_mfa_token(access_token)
        assert exc_info.value.status_code == 401
        assert "Invalid token type" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_decode_expired_mfa_token_raises(self):
        """Failure: expired MFA token raises 401."""
        payload = {
            "sub": "99",
            "type": "mfa",
            "exp": datetime.utcnow() - timedelta(minutes=10),
            "iat": datetime.utcnow() - timedelta(minutes=15),
        }
        expired_token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        with pytest.raises(HTTPException) as exc_info:
            await _decode_mfa_token(expired_token)
        assert exc_info.value.status_code == 401


# =============================================================================
# get_user_by_email (requires DB session)
# =============================================================================


class TestGetUserByEmail:
    """Tests for get_user_by_email() — database lookup."""

    @pytest.mark.asyncio
    async def test_get_user_by_email_found(self, db_session):
        """Happy path: existing user is returned."""
        from app.models import User
        user = User(
            email="found@example.com",
            hashed_password=hash_password("Test1234"),
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()

        result = await get_user_by_email(db_session, "found@example.com")
        assert result is not None
        assert result.email == "found@example.com"

    @pytest.mark.asyncio
    async def test_get_user_by_email_not_found(self, db_session):
        """Failure: nonexistent email returns None."""
        result = await get_user_by_email(db_session, "nonexistent@example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_by_email_case_sensitive(self, db_session):
        """Edge case: email lookup is case-sensitive at the DB level."""
        from app.models import User
        user = User(
            email="CaseSensitive@Example.com",
            hashed_password=hash_password("Test1234"),
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()

        # Exact case match should work
        result = await get_user_by_email(db_session, "CaseSensitive@Example.com")
        assert result is not None
