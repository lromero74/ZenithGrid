"""
Tests for RBAC enforcement on account-related router endpoints.

Verifies that:
- Observer users (no accounts:write / settings:write) get 403 on write endpoints
- Users with accounts:write can perform account write operations
- Users with settings:write can manage AI credentials
- Superusers bypass all permission checks
- Read endpoints do NOT require write permissions

Covers:
- accounts_router (6 write + 7 read endpoints)
- paper_trading_router (3 write + 1 read)
- ai_credentials_router (3 write + 3 read)
"""

import inspect

import pytest
from fastapi import HTTPException

from app.auth.dependencies import (
    Perm,
    require_permission,
)
from app.models import (
    Group,
    Permission,
    Role,
    User,
)


# =============================================================================
# Helpers: Create RBAC chain in the database
# =============================================================================


async def _create_permission(db_session, name: str) -> Permission:
    perm = Permission(name=name)
    db_session.add(perm)
    await db_session.flush()
    return perm


async def _create_role(db_session, name: str, permissions: list[Permission]) -> Role:
    role = Role(name=name, is_system=True)
    role.permissions = permissions
    db_session.add(role)
    await db_session.flush()
    return role


async def _create_group(db_session, name: str, roles: list[Role]) -> Group:
    group = Group(name=name, is_system=True)
    group.roles = roles
    db_session.add(group)
    await db_session.flush()
    return group


async def _create_user(db_session, email: str, groups: list[Group], is_superuser=False) -> User:
    from datetime import datetime
    user = User(
        email=email,
        hashed_password="hashed",
        is_active=True,
        is_superuser=is_superuser,
        created_at=datetime.utcnow(),
    )
    user.groups = groups
    db_session.add(user)
    await db_session.flush()
    return user


async def _create_observer_user(db_session, email="observer@example.com") -> User:
    """Create a user with only read permissions (no write)."""
    read_perm = await _create_permission(db_session, "accounts:read")
    settings_read = await _create_permission(db_session, "settings:read")
    viewer_role = await _create_role(db_session, "viewer", [read_perm, settings_read])
    observers_group = await _create_group(db_session, "Observers", [viewer_role])
    return await _create_user(db_session, email, [observers_group])


async def _create_account_writer_user(db_session, email="writer@example.com") -> User:
    """Create a user with accounts:write + settings:write permissions."""
    acct_read = await _create_permission(db_session, "accounts:read")
    acct_write = await _create_permission(db_session, "accounts:write")
    settings_read = await _create_permission(db_session, "settings:read")
    settings_write = await _create_permission(db_session, "settings:write")
    writer_role = await _create_role(
        db_session, "writer",
        [acct_read, acct_write, settings_read, settings_write],
    )
    writers_group = await _create_group(db_session, "Writers", [writer_role])
    return await _create_user(db_session, email, [writers_group])


async def _create_superuser(db_session, email="admin@example.com") -> User:
    """Create a superuser (bypasses all RBAC checks)."""
    return await _create_user(db_session, email, [], is_superuser=True)


# =============================================================================
# Helpers: Inspect endpoint dependency annotations
# =============================================================================


def _assert_endpoint_requires_permission(endpoint_func, permission_name: str):
    """Check that a FastAPI endpoint's current_user param uses require_permission."""
    sig = inspect.signature(endpoint_func)
    param = sig.parameters.get("current_user")
    assert param is not None, f"Endpoint {endpoint_func.__name__} has no current_user parameter"

    dep = param.default
    assert hasattr(dep, "dependency"), (
        f"current_user param on {endpoint_func.__name__} is not a Depends"
    )
    inner = dep.dependency

    assert "require_permission" in inner.__qualname__, (
        f"{endpoint_func.__name__}: current_user uses {inner.__qualname__}, "
        f"expected require_permission.<locals>._check"
    )

    closure_vars = inspect.getclosurevars(inner)
    perms_tuple = closure_vars.nonlocals.get("permissions")
    assert perms_tuple is not None, f"Could not find permissions closure in {endpoint_func.__name__}"
    perm_names = [str(p) for p in perms_tuple]
    assert permission_name in perm_names, (
        f"{endpoint_func.__name__} requires {perm_names}, expected {permission_name}"
    )


def _assert_endpoint_uses_get_current_user(endpoint_func):
    """Check that a FastAPI endpoint uses get_current_user (not require_permission)."""
    sig = inspect.signature(endpoint_func)
    param = sig.parameters.get("current_user")
    assert param is not None, f"Endpoint {endpoint_func.__name__} has no current_user parameter"

    dep = param.default
    assert hasattr(dep, "dependency"), (
        f"current_user param on {endpoint_func.__name__} is not a Depends"
    )
    inner = dep.dependency

    assert "require_permission" not in inner.__qualname__, (
        f"{endpoint_func.__name__}: uses require_permission but should use get_current_user"
    )


# =============================================================================
# Test: Permission resolution for ACCOUNTS_WRITE
# =============================================================================


class TestAccountsPermissionResolution:
    """Verify require_permission works for accounts:write."""

    @pytest.mark.asyncio
    async def test_observer_denied_accounts_write(self, db_session):
        """Observer (accounts:read only) is denied accounts:write."""
        user = await _create_observer_user(db_session)
        checker = require_permission(Perm.ACCOUNTS_WRITE)
        with pytest.raises(HTTPException) as exc_info:
            await checker(current_user=user)
        assert exc_info.value.status_code == 403
        assert "accounts:write" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_writer_allowed_accounts_write(self, db_session):
        """User with accounts:write passes the check."""
        user = await _create_account_writer_user(db_session)
        checker = require_permission(Perm.ACCOUNTS_WRITE)
        result = await checker(current_user=user)
        assert result.id == user.id

    @pytest.mark.asyncio
    async def test_superuser_bypasses_accounts_write(self, db_session):
        """Superuser bypasses all permission checks."""
        user = await _create_superuser(db_session)
        checker = require_permission(Perm.ACCOUNTS_WRITE)
        result = await checker(current_user=user)
        assert result.id == user.id


# =============================================================================
# Test: Permission resolution for SETTINGS_WRITE
# =============================================================================


class TestSettingsPermissionResolution:
    """Verify require_permission works for settings:write."""

    @pytest.mark.asyncio
    async def test_observer_denied_settings_write(self, db_session):
        """Observer (settings:read only) is denied settings:write."""
        user = await _create_observer_user(db_session, "obs2@example.com")
        checker = require_permission(Perm.SETTINGS_WRITE)
        with pytest.raises(HTTPException) as exc_info:
            await checker(current_user=user)
        assert exc_info.value.status_code == 403
        assert "settings:write" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_writer_allowed_settings_write(self, db_session):
        """User with settings:write passes the check."""
        user = await _create_account_writer_user(db_session, "writer2@example.com")
        checker = require_permission(Perm.SETTINGS_WRITE)
        result = await checker(current_user=user)
        assert result.id == user.id


# =============================================================================
# Test: accounts_router write endpoints
# =============================================================================


class TestAccountsRouterWriteDependencies:
    """Verify accounts_router write endpoints use require_permission(ACCOUNTS_WRITE)."""

    def test_create_account_requires_accounts_write(self):
        from app.routers.accounts_router import create_account
        _assert_endpoint_requires_permission(create_account, "accounts:write")

    def test_update_account_requires_accounts_write(self):
        from app.routers.accounts_router import update_account
        _assert_endpoint_requires_permission(update_account, "accounts:write")

    def test_delete_account_requires_accounts_write(self):
        from app.routers.accounts_router import delete_account
        _assert_endpoint_requires_permission(delete_account, "accounts:write")

    def test_set_default_requires_accounts_write(self):
        from app.routers.accounts_router import set_default_account
        _assert_endpoint_requires_permission(set_default_account, "accounts:write")

    def test_link_perps_portfolio_requires_accounts_write(self):
        from app.routers.accounts_router import link_perps_portfolio
        _assert_endpoint_requires_permission(link_perps_portfolio, "accounts:write")

    def test_update_auto_buy_requires_accounts_write(self):
        from app.routers.accounts_router import update_auto_buy_settings
        _assert_endpoint_requires_permission(update_auto_buy_settings, "accounts:write")


# =============================================================================
# Test: accounts_router read endpoints (should NOT require write)
# =============================================================================


class TestAccountsRouterReadDependencies:
    """Verify accounts_router read endpoints use get_current_user."""

    def test_list_accounts_uses_get_current_user(self):
        from app.routers.accounts_router import list_accounts
        _assert_endpoint_uses_get_current_user(list_accounts)

    def test_get_account_uses_get_current_user(self):
        from app.routers.accounts_router import get_account
        _assert_endpoint_uses_get_current_user(get_account)

    def test_get_account_bots_uses_get_current_user(self):
        from app.routers.accounts_router import get_account_bots
        _assert_endpoint_uses_get_current_user(get_account_bots)

    def test_get_default_account_uses_get_current_user(self):
        from app.routers.accounts_router import get_default_account
        _assert_endpoint_uses_get_current_user(get_default_account)

    def test_get_account_portfolio_uses_get_current_user(self):
        from app.routers.accounts_router import get_account_portfolio
        _assert_endpoint_uses_get_current_user(get_account_portfolio)

    def test_get_auto_buy_settings_uses_get_current_user(self):
        from app.routers.accounts_router import get_auto_buy_settings
        _assert_endpoint_uses_get_current_user(get_auto_buy_settings)

    def test_get_perps_portfolio_status_uses_get_current_user(self):
        from app.routers.accounts_router import get_perps_portfolio_status
        _assert_endpoint_uses_get_current_user(get_perps_portfolio_status)


# =============================================================================
# Test: paper_trading_router write endpoints
# =============================================================================


class TestPaperTradingRouterWriteDependencies:
    """Verify paper_trading_router write endpoints use require_permission(ACCOUNTS_WRITE)."""

    def test_deposit_requires_accounts_write(self):
        from app.routers.paper_trading_router import deposit_to_paper_account
        _assert_endpoint_requires_permission(deposit_to_paper_account, "accounts:write")

    def test_withdraw_requires_accounts_write(self):
        from app.routers.paper_trading_router import withdraw_from_paper_account
        _assert_endpoint_requires_permission(withdraw_from_paper_account, "accounts:write")

    def test_reset_requires_accounts_write(self):
        from app.routers.paper_trading_router import reset_paper_account
        _assert_endpoint_requires_permission(reset_paper_account, "accounts:write")


# =============================================================================
# Test: paper_trading_router read endpoints
# =============================================================================


class TestPaperTradingRouterReadDependencies:
    """Verify paper_trading_router read endpoints use get_current_user."""

    def test_get_paper_balance_uses_get_current_user(self):
        from app.routers.paper_trading_router import get_paper_balance
        _assert_endpoint_uses_get_current_user(get_paper_balance)


# =============================================================================
# Test: ai_credentials_router write endpoints
# =============================================================================


class TestAICredentialsRouterWriteDependencies:
    """Verify ai_credentials_router write endpoints use require_permission(SETTINGS_WRITE)."""

    def test_create_ai_credential_requires_settings_write(self):
        from app.routers.ai_credentials_router import create_or_update_ai_credential
        _assert_endpoint_requires_permission(create_or_update_ai_credential, "settings:write")

    def test_update_ai_credential_requires_settings_write(self):
        from app.routers.ai_credentials_router import update_ai_credential
        _assert_endpoint_requires_permission(update_ai_credential, "settings:write")

    def test_delete_ai_credential_requires_settings_write(self):
        from app.routers.ai_credentials_router import delete_ai_credential
        _assert_endpoint_requires_permission(delete_ai_credential, "settings:write")


# =============================================================================
# Test: ai_credentials_router read endpoints
# =============================================================================


class TestAICredentialsRouterReadDependencies:
    """Verify ai_credentials_router read endpoints use get_current_user."""

    def test_list_ai_credentials_uses_get_current_user(self):
        from app.routers.ai_credentials_router import list_ai_credentials
        _assert_endpoint_uses_get_current_user(list_ai_credentials)

    def test_get_ai_providers_status_uses_get_current_user(self):
        from app.routers.ai_credentials_router import get_ai_providers_status
        _assert_endpoint_uses_get_current_user(get_ai_providers_status)

    def test_get_ai_credential_uses_get_current_user(self):
        from app.routers.ai_credentials_router import get_ai_credential
        _assert_endpoint_uses_get_current_user(get_ai_credential)
