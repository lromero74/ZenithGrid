"""Tests for app/auth/dependencies.py"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from jose import jwt

from app.auth.dependencies import (
    check_token_revocation,
    decode_token,
    get_current_user,
    get_user_by_id,
    require_superuser,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_SECRET = "test-secret-key-for-unit-tests"
TEST_ALGORITHM = "HS256"


def _make_token(payload: dict, secret: str = TEST_SECRET) -> str:
    return jwt.encode(payload, secret, algorithm=TEST_ALGORITHM)


def _make_user(user_id=1, is_active=True, is_superuser=False, tokens_valid_after=None):
    user = MagicMock()
    user.id = user_id
    user.is_active = is_active
    user.is_superuser = is_superuser
    user.tokens_valid_after = tokens_valid_after
    return user


@pytest.fixture
def mock_settings():
    with patch("app.auth.dependencies.settings") as mock:
        mock.jwt_secret_key = TEST_SECRET
        mock.jwt_algorithm = TEST_ALGORITHM
        yield mock


# ---------------------------------------------------------------------------
# decode_token
# ---------------------------------------------------------------------------

class TestDecodeToken:
    def test_valid_token_decoded(self, mock_settings):
        payload = {"sub": "1", "type": "access", "exp": datetime.utcnow() + timedelta(hours=1)}
        token = _make_token(payload)

        result = decode_token(token)

        assert result["sub"] == "1"
        assert result["type"] == "access"

    def test_expired_token_raises_401(self, mock_settings):
        payload = {"sub": "1", "type": "access", "exp": datetime.utcnow() - timedelta(hours=1)}
        token = _make_token(payload)

        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401

    def test_invalid_signature_raises_401(self, mock_settings):
        payload = {"sub": "1", "type": "access", "exp": datetime.utcnow() + timedelta(hours=1)}
        token = _make_token(payload, secret="wrong-secret")

        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401

    def test_malformed_token_raises_401(self, mock_settings):
        with pytest.raises(HTTPException) as exc_info:
            decode_token("not.a.valid.jwt")
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# check_token_revocation
# ---------------------------------------------------------------------------

class TestCheckTokenRevocation:
    @pytest.mark.asyncio
    async def test_non_revoked_token_passes(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        # Should not raise
        await check_token_revocation({"jti": "abc-123"}, db)

    @pytest.mark.asyncio
    async def test_revoked_token_raises_401(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = 1  # Token found in revoked table
        db.execute.return_value = result_mock

        with pytest.raises(HTTPException) as exc_info:
            await check_token_revocation({"jti": "abc-123"}, db)
        assert exc_info.value.status_code == 401
        assert "revoked" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_no_jti_skips_check(self):
        db = AsyncMock()

        # Should not raise, and should not call db
        await check_token_revocation({}, db)
        db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# get_user_by_id
# ---------------------------------------------------------------------------

class TestGetUserById:
    @pytest.mark.asyncio
    async def test_returns_user(self):
        user = _make_user(user_id=42)
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = user
        db.execute.return_value = result_mock

        result = await get_user_by_id(db, 42)
        assert result.id == 42

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_user(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        result = await get_user_by_id(db, 999)
        assert result is None


# ---------------------------------------------------------------------------
# get_current_user
# ---------------------------------------------------------------------------

class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_no_credentials_raises_401(self):
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=None, db=db)
        assert exc_info.value.status_code == 401
        assert "Not authenticated" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_wrong_token_type_raises_401(self, mock_settings):
        payload = {
            "sub": "1", "type": "refresh",
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        token = _make_token(payload)

        creds = MagicMock()
        creds.credentials = token
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=creds, db=db)
        assert exc_info.value.status_code == 401
        assert "Invalid token type" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_user_not_found_raises_401(self, mock_settings):
        payload = {
            "sub": "999", "type": "access", "jti": "test-jti",
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        token = _make_token(payload)

        creds = MagicMock()
        creds.credentials = token
        db = AsyncMock()

        # Mock revocation check (not revoked)
        revoke_result = MagicMock()
        revoke_result.scalar_one_or_none.return_value = None
        # Mock user lookup (not found)
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None

        db.execute.side_effect = [revoke_result, user_result]

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=creds, db=db)
        assert exc_info.value.status_code == 401
        assert "User not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_inactive_user_raises_403(self, mock_settings):
        payload = {
            "sub": "1", "type": "access", "jti": "test-jti",
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        token = _make_token(payload)

        creds = MagicMock()
        creds.credentials = token
        db = AsyncMock()

        user = _make_user(user_id=1, is_active=False)

        revoke_result = MagicMock()
        revoke_result.scalar_one_or_none.return_value = None
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        db.execute.side_effect = [revoke_result, user_result]

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=creds, db=db)
        assert exc_info.value.status_code == 403
        assert "disabled" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_bulk_revocation_raises_401(self, mock_settings):
        """Token issued before password change is rejected"""
        old_iat = datetime.utcnow() - timedelta(hours=2)
        password_change_time = datetime.utcnow() - timedelta(hours=1)

        payload = {
            "sub": "1", "type": "access", "jti": "test-jti",
            "iat": int(old_iat.timestamp()),
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        token = _make_token(payload)

        creds = MagicMock()
        creds.credentials = token
        db = AsyncMock()

        user = _make_user(user_id=1, tokens_valid_after=password_change_time)

        revoke_result = MagicMock()
        revoke_result.scalar_one_or_none.return_value = None
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        db.execute.side_effect = [revoke_result, user_result]

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=creds, db=db)
        assert exc_info.value.status_code == 401
        assert "Session expired" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self, mock_settings):
        payload = {
            "sub": "1", "type": "access", "jti": "test-jti",
            "iat": int(datetime.utcnow().timestamp()),
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        token = _make_token(payload)

        creds = MagicMock()
        creds.credentials = token
        db = AsyncMock()

        user = _make_user(user_id=1)

        revoke_result = MagicMock()
        revoke_result.scalar_one_or_none.return_value = None
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        db.execute.side_effect = [revoke_result, user_result]

        result = await get_current_user(credentials=creds, db=db)
        assert result.id == 1


# ---------------------------------------------------------------------------
# require_superuser
# ---------------------------------------------------------------------------

class TestRequireSuperuser:
    @pytest.mark.asyncio
    async def test_superuser_passes(self):
        user = _make_user(is_superuser=True)
        result = await require_superuser(current_user=user)
        assert result.is_superuser is True

    @pytest.mark.asyncio
    async def test_non_superuser_raises_403(self):
        user = _make_user(is_superuser=False)
        with pytest.raises(HTTPException) as exc_info:
            await require_superuser(current_user=user)
        assert exc_info.value.status_code == 403
        assert "Superuser" in exc_info.value.detail
