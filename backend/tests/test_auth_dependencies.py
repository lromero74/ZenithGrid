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


# ---------------------------------------------------------------------------
# RBAC helpers
# ---------------------------------------------------------------------------


def _make_permission(name: str):
    """Create a mock Permission object."""
    perm = MagicMock()
    perm.name = name
    return perm


def _make_role(name: str, permissions: list, requires_mfa: bool = False):
    """Create a mock Role object."""
    role = MagicMock()
    role.name = name
    role.permissions = [_make_permission(p) for p in permissions]
    role.requires_mfa = requires_mfa
    return role


def _make_group(name: str, roles: list):
    """Create a mock Group object."""
    group = MagicMock()
    group.name = name
    group.roles = roles
    return group


def _make_rbac_user(user_id=10, is_superuser=False, groups=None):
    """Create a mock user with RBAC groups."""
    user = _make_user(user_id=user_id, is_superuser=is_superuser)
    user.groups = groups or []
    return user


# ---------------------------------------------------------------------------
# Perm enum
# ---------------------------------------------------------------------------


class TestPermEnum:
    """Tests for the Perm StrEnum."""

    def test_perm_values_follow_resource_action_pattern(self):
        from app.auth.dependencies import Perm
        for perm in Perm:
            assert ":" in perm.value, f"Perm {perm.name} must use resource:action format"

    def test_perm_string_equality(self):
        from app.auth.dependencies import Perm
        assert Perm.BOTS_READ == "bots:read"
        assert Perm.ADMIN_USERS == "admin:users"

    def test_perm_has_expected_members(self):
        from app.auth.dependencies import Perm
        expected = {"BOTS_READ", "BOTS_WRITE", "BOTS_DELETE",
                    "ADMIN_USERS", "ADMIN_GROUPS", "ADMIN_ROLES",
                    "SETTINGS_READ", "SETTINGS_WRITE", "GAMES_PLAY"}
        for name in expected:
            assert hasattr(Perm, name), f"Perm missing member: {name}"


# ---------------------------------------------------------------------------
# _get_user_permissions
# ---------------------------------------------------------------------------


class TestGetUserPermissions:
    """Tests for _get_user_permissions helper."""

    def test_happy_path_trader_permissions(self):
        """Trader user should have all trader permissions."""
        from app.auth.dependencies import _get_user_permissions
        trader_role = _make_role("trader", ["bots:read", "bots:write", "positions:read"])
        trader_group = _make_group("Traders", [trader_role])
        user = _make_rbac_user(groups=[trader_group])
        perms = _get_user_permissions(user)
        assert "bots:read" in perms
        assert "bots:write" in perms
        assert "positions:read" in perms

    def test_no_groups_returns_empty(self):
        """User with no groups should have no permissions."""
        from app.auth.dependencies import _get_user_permissions
        user = _make_rbac_user(groups=[])
        perms = _get_user_permissions(user)
        assert perms == set()

    def test_viewer_has_read_only(self):
        """Viewer should only have read permissions."""
        from app.auth.dependencies import _get_user_permissions
        viewer_role = _make_role("viewer", ["bots:read", "positions:read"])
        observer_group = _make_group("Observers", [viewer_role])
        user = _make_rbac_user(groups=[observer_group])
        perms = _get_user_permissions(user)
        assert "bots:read" in perms
        assert "bots:write" not in perms

    def test_multiple_groups_union_permissions(self):
        """User in multiple groups gets union of all permissions."""
        from app.auth.dependencies import _get_user_permissions
        role_a = _make_role("role_a", ["bots:read"])
        role_b = _make_role("role_b", ["settings:write"])
        group_a = _make_group("GroupA", [role_a])
        group_b = _make_group("GroupB", [role_b])
        user = _make_rbac_user(groups=[group_a, group_b])
        perms = _get_user_permissions(user)
        assert perms == {"bots:read", "settings:write"}

    def test_duplicate_permissions_deduplicated(self):
        """Same permission in multiple roles should appear only once."""
        from app.auth.dependencies import _get_user_permissions
        role_a = _make_role("role_a", ["bots:read", "bots:write"])
        role_b = _make_role("role_b", ["bots:read", "news:read"])
        group = _make_group("TestGroup", [role_a, role_b])
        user = _make_rbac_user(groups=[group])
        perms = _get_user_permissions(user)
        assert perms == {"bots:read", "bots:write", "news:read"}


# ---------------------------------------------------------------------------
# require_permission factory
# ---------------------------------------------------------------------------


class TestRequirePermission:
    """Tests for require_permission dependency factory."""

    @pytest.mark.asyncio
    async def test_superuser_bypasses_all_checks(self):
        """Superusers should bypass permission checks."""
        from app.auth.dependencies import require_permission, Perm
        user = _make_rbac_user(is_superuser=True)
        check_fn = require_permission(Perm.ADMIN_USERS)
        result = await check_fn(current_user=user)
        assert result == user

    @pytest.mark.asyncio
    async def test_user_with_permission_succeeds(self):
        """User with the required permission should pass."""
        from app.auth.dependencies import require_permission, Perm
        trader_role = _make_role("trader", ["bots:read", "bots:write"])
        trader_group = _make_group("Traders", [trader_role])
        user = _make_rbac_user(groups=[trader_group])
        check_fn = require_permission(Perm.BOTS_READ)
        result = await check_fn(current_user=user)
        assert result == user

    @pytest.mark.asyncio
    async def test_user_without_permission_raises_403(self):
        """User missing the required permission should get 403."""
        from app.auth.dependencies import require_permission, Perm
        trader_role = _make_role("trader", ["bots:read", "bots:write"])
        trader_group = _make_group("Traders", [trader_role])
        user = _make_rbac_user(groups=[trader_group])
        check_fn = require_permission(Perm.ADMIN_USERS)
        with pytest.raises(HTTPException) as exc_info:
            await check_fn(current_user=user)
        assert exc_info.value.status_code == 403
        assert "admin:users" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_multiple_permissions_all_required(self):
        """All specified permissions must be present."""
        from app.auth.dependencies import require_permission, Perm
        trader_role = _make_role("trader", ["bots:read", "bots:write"])
        trader_group = _make_group("Traders", [trader_role])
        user = _make_rbac_user(groups=[trader_group])
        check_fn = require_permission(Perm.BOTS_READ, Perm.BOTS_WRITE)
        result = await check_fn(current_user=user)
        assert result == user

    @pytest.mark.asyncio
    async def test_multiple_permissions_one_missing_raises_403(self):
        """If any of the specified permissions is missing, 403."""
        from app.auth.dependencies import require_permission, Perm
        trader_role = _make_role("trader", ["bots:read", "bots:write"])
        trader_group = _make_group("Traders", [trader_role])
        user = _make_rbac_user(groups=[trader_group])
        check_fn = require_permission(Perm.BOTS_READ, Perm.ADMIN_USERS)
        with pytest.raises(HTTPException) as exc_info:
            await check_fn(current_user=user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_no_groups_user_raises_403(self):
        """User with no groups should be denied any permission."""
        from app.auth.dependencies import require_permission, Perm
        user = _make_rbac_user(groups=[])
        check_fn = require_permission(Perm.BOTS_READ)
        with pytest.raises(HTTPException) as exc_info:
            await check_fn(current_user=user)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# require_role factory
# ---------------------------------------------------------------------------


class TestRequireRole:
    """Tests for require_role dependency factory."""

    @pytest.mark.asyncio
    async def test_superuser_bypasses_role_check(self):
        """Superusers bypass role checks."""
        from app.auth.dependencies import require_role
        user = _make_rbac_user(is_superuser=True)
        check_fn = require_role("admin")
        result = await check_fn(current_user=user)
        assert result == user

    @pytest.mark.asyncio
    async def test_user_with_role_succeeds(self):
        """User with the required role should pass."""
        from app.auth.dependencies import require_role
        trader_role = _make_role("trader", ["bots:read"])
        trader_group = _make_group("Traders", [trader_role])
        user = _make_rbac_user(groups=[trader_group])
        check_fn = require_role("trader")
        result = await check_fn(current_user=user)
        assert result == user

    @pytest.mark.asyncio
    async def test_user_without_role_raises_403(self):
        """User without the required role should get 403."""
        from app.auth.dependencies import require_role
        trader_role = _make_role("trader", ["bots:read"])
        trader_group = _make_group("Traders", [trader_role])
        user = _make_rbac_user(groups=[trader_group])
        check_fn = require_role("admin")
        with pytest.raises(HTTPException) as exc_info:
            await check_fn(current_user=user)
        assert exc_info.value.status_code == 403
        assert "admin" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_no_groups_user_raises_403(self):
        """User with no groups has no roles."""
        from app.auth.dependencies import require_role
        user = _make_rbac_user(groups=[])
        check_fn = require_role("viewer")
        with pytest.raises(HTTPException) as exc_info:
            await check_fn(current_user=user)
        assert exc_info.value.status_code == 403
