"""
Tests for RBAC enforcement on position router endpoints.

Verifies that:
- Observer users (positions:read only) get 403 on write endpoints
- Users with positions:write can perform write operations
- Superusers bypass all permission checks
- Read endpoints do NOT require write permissions

Covers all 4 position sub-routers:
- position_actions_router (5 endpoints)
- position_manual_ops_router (2 endpoints)
- position_limit_orders_router (3 write + 2 read endpoints)
- perps_router (2 write + 3 read endpoints)
"""

import inspect

import pytest
from fastapi import HTTPException

from app.auth.dependencies import (
    Perm,
    require_permission,
    _get_user_permissions,
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
    """Create a user with only read permissions (no positions:write)."""
    read_perm = await _create_permission(db_session, "positions:read")
    viewer_role = await _create_role(db_session, "viewer", [read_perm])
    observers_group = await _create_group(db_session, "Observers", [viewer_role])
    return await _create_user(db_session, email, [observers_group])


async def _create_trader_user(db_session, email="trader@example.com") -> User:
    """Create a user with positions:read + positions:write permissions."""
    read_perm = await _create_permission(db_session, "positions:read")
    write_perm = await _create_permission(db_session, "positions:write")
    trader_role = await _create_role(db_session, "trader", [read_perm, write_perm])
    traders_group = await _create_group(db_session, "Traders", [trader_role])
    return await _create_user(db_session, email, [traders_group])


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

    # Should be get_current_user, NOT require_permission._check
    assert "require_permission" not in inner.__qualname__, (
        f"{endpoint_func.__name__}: uses require_permission but should use get_current_user"
    )


# =============================================================================
# Test: Permission resolution for POSITIONS_WRITE
# =============================================================================


class TestPositionsPermissionResolution:
    """Verify require_permission(Perm.POSITIONS_WRITE) works correctly."""

    @pytest.mark.asyncio
    async def test_observer_denied_positions_write(self, db_session):
        """Observer (positions:read only) is denied positions:write."""
        user = await _create_observer_user(db_session)
        checker = require_permission(Perm.POSITIONS_WRITE)
        with pytest.raises(HTTPException) as exc_info:
            await checker(current_user=user)
        assert exc_info.value.status_code == 403
        assert "positions:write" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_trader_allowed_positions_write(self, db_session):
        """Trader (positions:write) passes the check."""
        user = await _create_trader_user(db_session)
        checker = require_permission(Perm.POSITIONS_WRITE)
        result = await checker(current_user=user)
        assert result.id == user.id

    @pytest.mark.asyncio
    async def test_superuser_bypasses_positions_write(self, db_session):
        """Superuser bypasses all permission checks."""
        user = await _create_superuser(db_session)
        checker = require_permission(Perm.POSITIONS_WRITE)
        result = await checker(current_user=user)
        assert result.id == user.id

    @pytest.mark.asyncio
    async def test_observer_has_read_only(self, db_session):
        """Observer resolves to only positions:read."""
        user = await _create_observer_user(db_session, "obs2@example.com")
        perms = _get_user_permissions(user)
        assert "positions:read" in perms
        assert "positions:write" not in perms


# =============================================================================
# Test: position_actions_router dependencies
# =============================================================================


class TestPositionActionsRouterDependencies:
    """Verify all 5 endpoints in position_actions_router use require_permission."""

    def test_cancel_position_requires_positions_write(self):
        from app.position_routers.position_actions_router import cancel_position
        _assert_endpoint_requires_permission(cancel_position, "positions:write")

    def test_force_close_requires_positions_write(self):
        from app.position_routers.position_actions_router import force_close_position
        _assert_endpoint_requires_permission(force_close_position, "positions:write")

    def test_update_settings_requires_positions_write(self):
        from app.position_routers.position_actions_router import update_position_settings
        _assert_endpoint_requires_permission(update_position_settings, "positions:write")

    def test_resize_budget_requires_positions_write(self):
        from app.position_routers.position_actions_router import resize_position_budget
        _assert_endpoint_requires_permission(resize_position_budget, "positions:write")

    def test_resize_all_budgets_requires_positions_write(self):
        from app.position_routers.position_actions_router import resize_all_budgets
        _assert_endpoint_requires_permission(resize_all_budgets, "positions:write")


# =============================================================================
# Test: position_manual_ops_router dependencies
# =============================================================================


class TestPositionManualOpsRouterDependencies:
    """Verify both endpoints in position_manual_ops_router use require_permission."""

    def test_add_funds_requires_positions_write(self):
        from app.position_routers.position_manual_ops_router import add_funds_to_position
        _assert_endpoint_requires_permission(add_funds_to_position, "positions:write")

    def test_update_notes_requires_positions_write(self):
        from app.position_routers.position_manual_ops_router import update_position_notes
        _assert_endpoint_requires_permission(update_position_notes, "positions:write")


# =============================================================================
# Test: position_limit_orders_router dependencies
# =============================================================================


class TestPositionLimitOrdersRouterDependencies:
    """Verify limit orders router: write endpoints gated, read endpoints open."""

    def test_limit_close_requires_positions_write(self):
        from app.position_routers.position_limit_orders_router import limit_close_position
        _assert_endpoint_requires_permission(limit_close_position, "positions:write")

    def test_cancel_limit_close_requires_positions_write(self):
        from app.position_routers.position_limit_orders_router import cancel_limit_close
        _assert_endpoint_requires_permission(cancel_limit_close, "positions:write")

    def test_update_limit_close_requires_positions_write(self):
        from app.position_routers.position_limit_orders_router import update_limit_close
        _assert_endpoint_requires_permission(update_limit_close, "positions:write")

    def test_get_ticker_uses_get_current_user(self):
        """GET ticker should NOT require write permission."""
        from app.position_routers.position_limit_orders_router import get_position_ticker
        _assert_endpoint_uses_get_current_user(get_position_ticker)

    def test_slippage_check_uses_get_current_user(self):
        """GET slippage-check should NOT require write permission."""
        from app.position_routers.position_limit_orders_router import check_market_close_slippage
        _assert_endpoint_uses_get_current_user(check_market_close_slippage)


# =============================================================================
# Test: perps_router dependencies
# =============================================================================


class TestPerpsRouterDependencies:
    """Verify perps router: write endpoints gated, read endpoints open."""

    def test_modify_tp_sl_requires_positions_write(self):
        from app.position_routers.perps_router import modify_tp_sl
        _assert_endpoint_requires_permission(modify_tp_sl, "positions:write")

    def test_close_perps_requires_positions_write(self):
        from app.position_routers.perps_router import close_perps_position
        _assert_endpoint_requires_permission(close_perps_position, "positions:write")

    def test_list_perps_products_uses_get_current_user(self):
        """GET /perps/products should NOT require write permission."""
        from app.position_routers.perps_router import list_perps_products
        _assert_endpoint_uses_get_current_user(list_perps_products)

    def test_get_perps_portfolio_uses_get_current_user(self):
        """GET /perps/portfolio should NOT require write permission."""
        from app.position_routers.perps_router import get_perps_portfolio
        _assert_endpoint_uses_get_current_user(get_perps_portfolio)

    def test_list_perps_positions_uses_get_current_user(self):
        """GET /perps/positions should NOT require write permission."""
        from app.position_routers.perps_router import list_perps_positions
        _assert_endpoint_uses_get_current_user(list_perps_positions)
