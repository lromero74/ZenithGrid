"""
Tests for RBAC enforcement on bot CRUD and control endpoints.

Verifies that:
- Observer users (viewer role, bots:read only) get 403 on write endpoints
- Observer users get 200 on read endpoints
- Users with bots:write can perform write operations
- Users with bots:delete can delete bots
- Superusers bypass all permission checks
"""

import pytest
from datetime import datetime
from fastapi import HTTPException

from app.auth.dependencies import (
    Perm,
    require_permission,
    _get_user_permissions,
)
from app.models import (
    Account,
    Bot,
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
    """Create a user with only read permissions (viewer role in Observers group)."""
    read_perm = await _create_permission(db_session, "bots:read")
    pos_read = await _create_permission(db_session, "positions:read")
    viewer_role = await _create_role(db_session, "viewer", [read_perm, pos_read])
    observers_group = await _create_group(db_session, "Observers", [viewer_role])
    return await _create_user(db_session, email, [observers_group])


async def _create_trader_user(db_session, email="trader@example.com") -> User:
    """Create a user with full bot read/write/delete permissions."""
    read_perm = await _create_permission(db_session, "bots:read")
    write_perm = await _create_permission(db_session, "bots:write")
    delete_perm = await _create_permission(db_session, "bots:delete")
    trader_role = await _create_role(db_session, "trader", [read_perm, write_perm, delete_perm])
    traders_group = await _create_group(db_session, "Traders", [trader_role])
    return await _create_user(db_session, email, [traders_group])


async def _create_superuser(db_session, email="admin@example.com") -> User:
    """Create a superuser (bypasses all RBAC checks)."""
    return await _create_user(db_session, email, [], is_superuser=True)


async def _create_account_and_bot(db_session, user: User) -> tuple[Account, Bot]:
    """Create an account and bot owned by the given user."""
    account = Account(
        user_id=user.id,
        name="Test Account",
        type="cex",
        exchange="coinbase",
        is_active=True,
    )
    db_session.add(account)
    await db_session.flush()

    bot = Bot(
        user_id=user.id,
        account_id=account.id,
        name="Test Bot",
        strategy_type="macd_dca",
        strategy_config={"base_order_fixed": 0.01},
        product_id="ETH-BTC",
        product_ids=["ETH-BTC"],
        is_active=False,
    )
    db_session.add(bot)
    await db_session.flush()
    return account, bot


# =============================================================================
# Test: Permission resolution
# =============================================================================


class TestPermissionResolution:
    """Verify _get_user_permissions resolves the RBAC chain correctly."""

    @pytest.mark.asyncio
    async def test_observer_has_read_only(self, db_session):
        """Observer user resolves to only read permissions."""
        user = await _create_observer_user(db_session)
        perms = _get_user_permissions(user)
        assert "bots:read" in perms
        assert "positions:read" in perms
        assert "bots:write" not in perms
        assert "bots:delete" not in perms

    @pytest.mark.asyncio
    async def test_trader_has_full_bot_perms(self, db_session):
        """Trader user resolves to read + write + delete permissions."""
        user = await _create_trader_user(db_session)
        perms = _get_user_permissions(user)
        assert "bots:read" in perms
        assert "bots:write" in perms
        assert "bots:delete" in perms


# =============================================================================
# Test: require_permission dependency for BOTS_WRITE
# =============================================================================


class TestRequireBotsWrite:
    """Test require_permission(Perm.BOTS_WRITE) enforcement."""

    @pytest.mark.asyncio
    async def test_observer_denied_bots_write(self, db_session):
        """Observer (bots:read only) is denied bots:write — expect 403."""
        user = await _create_observer_user(db_session)
        checker = require_permission(Perm.BOTS_WRITE)
        with pytest.raises(HTTPException) as exc_info:
            await checker(current_user=user)
        assert exc_info.value.status_code == 403
        assert "bots:write" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_trader_allowed_bots_write(self, db_session):
        """Trader (bots:write) passes the check."""
        user = await _create_trader_user(db_session)
        checker = require_permission(Perm.BOTS_WRITE)
        result = await checker(current_user=user)
        assert result.id == user.id

    @pytest.mark.asyncio
    async def test_superuser_bypasses_bots_write(self, db_session):
        """Superuser bypasses all permission checks."""
        user = await _create_superuser(db_session)
        checker = require_permission(Perm.BOTS_WRITE)
        result = await checker(current_user=user)
        assert result.id == user.id


# =============================================================================
# Test: require_permission dependency for BOTS_DELETE
# =============================================================================


class TestRequireBotsDelete:
    """Test require_permission(Perm.BOTS_DELETE) enforcement."""

    @pytest.mark.asyncio
    async def test_observer_denied_bots_delete(self, db_session):
        """Observer cannot delete bots — expect 403."""
        user = await _create_observer_user(db_session)
        checker = require_permission(Perm.BOTS_DELETE)
        with pytest.raises(HTTPException) as exc_info:
            await checker(current_user=user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_trader_allowed_bots_delete(self, db_session):
        """Trader with bots:delete can delete bots."""
        user = await _create_trader_user(db_session)
        checker = require_permission(Perm.BOTS_DELETE)
        result = await checker(current_user=user)
        assert result.id == user.id

    @pytest.mark.asyncio
    async def test_superuser_bypasses_bots_delete(self, db_session):
        """Superuser bypasses delete permission check."""
        user = await _create_superuser(db_session)
        checker = require_permission(Perm.BOTS_DELETE)
        result = await checker(current_user=user)
        assert result.id == user.id


# =============================================================================
# Test: require_permission dependency for BOTS_READ
# =============================================================================


class TestRequireBotsRead:
    """Test that observer users CAN access read endpoints."""

    @pytest.mark.asyncio
    async def test_observer_allowed_bots_read(self, db_session):
        """Observer with bots:read can list/view bots — expect pass."""
        user = await _create_observer_user(db_session)
        checker = require_permission(Perm.BOTS_READ)
        result = await checker(current_user=user)
        assert result.id == user.id


# =============================================================================
# Test: Bot CRUD router endpoints use correct permission dependencies
# =============================================================================


class TestBotCrudRouterDependencies:
    """Verify bot_crud_router write endpoints use require_permission."""

    def test_create_bot_requires_bots_write(self):
        """POST /bots/ should require bots:write."""
        from app.bot_routers.bot_crud_router import create_bot
        _assert_endpoint_requires_permission(create_bot, "bots:write")

    def test_update_bot_requires_bots_write(self):
        """PUT /bots/{bot_id} should require bots:write."""
        from app.bot_routers.bot_crud_router import update_bot
        _assert_endpoint_requires_permission(update_bot, "bots:write")

    def test_delete_bot_requires_bots_delete(self):
        """DELETE /bots/{bot_id} should require bots:delete."""
        from app.bot_routers.bot_crud_router import delete_bot
        _assert_endpoint_requires_permission(delete_bot, "bots:delete")

    def test_clone_bot_requires_bots_write(self):
        """POST /bots/{bot_id}/clone should require bots:write."""
        from app.bot_routers.bot_crud_router import clone_bot
        _assert_endpoint_requires_permission(clone_bot, "bots:write")

    def test_copy_to_account_requires_bots_write(self):
        """POST /bots/{bot_id}/copy-to-account should require bots:write."""
        from app.bot_routers.bot_crud_router import copy_bot_to_account
        _assert_endpoint_requires_permission(copy_bot_to_account, "bots:write")

    def test_list_bots_does_not_require_write(self):
        """GET /bots/ should NOT require bots:write (read-only)."""
        from app.bot_routers.bot_crud_router import list_bots
        _assert_endpoint_does_not_require_permission(list_bots, "bots:write")

    def test_get_bot_does_not_require_write(self):
        """GET /bots/{bot_id} should NOT require bots:write (read-only)."""
        from app.bot_routers.bot_crud_router import get_bot
        _assert_endpoint_does_not_require_permission(get_bot, "bots:write")


class TestBotControlRouterDependencies:
    """Verify bot_control_router endpoints use require_permission."""

    def test_start_bot_requires_bots_write(self):
        """POST /bots/{bot_id}/start should require bots:write."""
        from app.bot_routers.bot_control_router import start_bot
        _assert_endpoint_requires_permission(start_bot, "bots:write")

    def test_stop_bot_requires_bots_write(self):
        """POST /bots/{bot_id}/stop should require bots:write."""
        from app.bot_routers.bot_control_router import stop_bot
        _assert_endpoint_requires_permission(stop_bot, "bots:write")

    def test_force_run_requires_bots_write(self):
        """POST /bots/{bot_id}/force-run should require bots:write."""
        from app.bot_routers.bot_control_router import force_run_bot
        _assert_endpoint_requires_permission(force_run_bot, "bots:write")

    def test_cancel_all_requires_bots_write(self):
        """POST /bots/{bot_id}/cancel-all-positions should require bots:write."""
        from app.bot_routers.bot_control_router import cancel_all_positions
        _assert_endpoint_requires_permission(cancel_all_positions, "bots:write")

    def test_sell_all_requires_bots_write(self):
        """POST /bots/{bot_id}/sell-all-positions should require bots:write."""
        from app.bot_routers.bot_control_router import sell_all_positions
        _assert_endpoint_requires_permission(sell_all_positions, "bots:write")


# =============================================================================
# Helper: Inspect FastAPI endpoint dependency annotations
# =============================================================================


def _assert_endpoint_requires_permission(endpoint_func, permission_name: str):
    """Check that a FastAPI endpoint's `current_user` param uses require_permission."""
    import inspect
    sig = inspect.signature(endpoint_func)
    param = sig.parameters.get("current_user")
    assert param is not None, f"Endpoint {endpoint_func.__name__} has no current_user parameter"

    dep = param.default
    # The Depends wraps the inner _check function from require_permission
    assert hasattr(dep, "dependency"), (
        f"current_user param on {endpoint_func.__name__} is not a Depends"
    )
    inner = dep.dependency

    # The inner function should have a __qualname__ containing require_permission
    assert "require_permission" in inner.__qualname__, (
        f"{endpoint_func.__name__}: current_user uses {inner.__qualname__}, "
        f"expected require_permission.<locals>._check"
    )

    # Verify the specific permission by checking closures
    closure_vars = inspect.getclosurevars(inner)
    perms_tuple = closure_vars.nonlocals.get("permissions")
    assert perms_tuple is not None, f"Could not find permissions closure in {endpoint_func.__name__}"
    perm_names = [str(p) for p in perms_tuple]
    assert permission_name in perm_names, (
        f"{endpoint_func.__name__} requires {perm_names}, expected {permission_name}"
    )


def _assert_endpoint_does_not_require_permission(endpoint_func, permission_name: str):
    """Check that a FastAPI endpoint does NOT require a specific permission."""
    import inspect
    sig = inspect.signature(endpoint_func)
    param = sig.parameters.get("current_user")
    if param is None:
        return  # No auth at all — fine for public endpoints

    dep = param.default
    if not hasattr(dep, "dependency"):
        return  # Not a Depends — shouldn't happen but not requiring permission

    inner = dep.dependency
    if "require_permission" not in inner.__qualname__:
        return  # Uses plain get_current_user — no permission required

    # If it does use require_permission, verify it doesn't check the specific one
    closure_vars = inspect.getclosurevars(inner)
    perms_tuple = closure_vars.nonlocals.get("permissions", ())
    perm_names = [str(p) for p in perms_tuple]
    assert permission_name not in perm_names, (
        f"{endpoint_func.__name__} should NOT require {permission_name} but does"
    )
