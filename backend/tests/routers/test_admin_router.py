"""
Tests for backend/app/routers/admin_router.py

Covers CRUD endpoints for users, groups, roles, and permissions
in the admin management panel.
"""

import pytest
from unittest.mock import MagicMock
from sqlalchemy import select

from app.models import Group, Permission, Role, User, user_groups, group_roles, role_permissions


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def admin_user(db_session):
    """A superuser with admin access."""
    user = User(
        id=1, email="admin@test.com",
        hashed_password="hashed", is_active=True, is_superuser=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def regular_user(db_session):
    """A non-admin user."""
    user = User(
        id=2, email="user@test.com",
        hashed_password="hashed", is_active=True, is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def test_group(db_session):
    """A test group."""
    group = Group(id=1, name="Test Group", description="A test group", is_system=False)
    db_session.add(group)
    await db_session.flush()
    return group


@pytest.fixture
async def system_group(db_session):
    """A system group (cannot be deleted)."""
    group = Group(id=2, name="System Owners", description="System group", is_system=True)
    db_session.add(group)
    await db_session.flush()
    return group


@pytest.fixture
async def test_role(db_session):
    """A test role."""
    role = Role(id=1, name="test_role", description="A test role", is_system=False)
    db_session.add(role)
    await db_session.flush()
    return role


@pytest.fixture
async def system_role(db_session):
    """A system role (cannot be deleted)."""
    role = Role(id=2, name="super_admin", description="System role", is_system=True, requires_mfa=True)
    db_session.add(role)
    await db_session.flush()
    return role


@pytest.fixture
async def test_permission(db_session):
    """A test permission."""
    perm = Permission(id=1, name="bots:read", description="View bots")
    db_session.add(perm)
    await db_session.flush()
    return perm


# =============================================================================
# Import the admin router functions
# =============================================================================


class TestListUsers:
    """Tests for GET /api/admin/users"""

    @pytest.mark.asyncio
    async def test_list_users_returns_all(self, db_session, admin_user, regular_user):
        from app.routers.admin_router import list_users
        result = await list_users(db=db_session, current_user=admin_user)
        emails = [u["email"] for u in result]
        assert "admin@test.com" in emails
        assert "user@test.com" in emails

    @pytest.mark.asyncio
    async def test_list_users_includes_group_info(self, db_session, admin_user, test_group):
        # Assign admin to test group
        await db_session.execute(user_groups.insert().values(user_id=admin_user.id, group_id=test_group.id))
        await db_session.flush()
        from app.routers.admin_router import list_users
        result = await list_users(db=db_session, current_user=admin_user)
        admin_data = next(u for u in result if u["email"] == "admin@test.com")
        assert len(admin_data["groups"]) >= 1


class TestUpdateUserGroups:
    """Tests for PUT /api/admin/users/{id}/groups"""

    @pytest.mark.asyncio
    async def test_assign_group_to_user(self, db_session, admin_user, regular_user, test_group):
        from app.routers.admin_router import update_user_groups, UserGroupsRequest
        request = UserGroupsRequest(group_ids=[test_group.id])
        result = await update_user_groups(
            user_id=regular_user.id, request=request,
            db=db_session, current_user=admin_user,
        )
        assert len(result["groups"]) == 1
        assert result["groups"][0]["name"] == "Test Group"

    @pytest.mark.asyncio
    async def test_assign_mfa_group_without_mfa_fails(self, db_session, admin_user, regular_user, system_group,
                                                       system_role):
        # Assign the MFA-requiring role to the system group
        await db_session.execute(group_roles.insert().values(group_id=system_group.id, role_id=system_role.id))
        await db_session.flush()
        from app.routers.admin_router import update_user_groups, UserGroupsRequest
        from fastapi import HTTPException
        request = UserGroupsRequest(group_ids=[system_group.id])
        with pytest.raises(HTTPException) as exc_info:
            await update_user_groups(
                user_id=regular_user.id, request=request,
                db=db_session, current_user=admin_user,
            )
        assert exc_info.value.status_code == 400
        assert "MFA" in exc_info.value.detail


class TestUpdateUserStatus:
    """Tests for PUT /api/admin/users/{id}/status"""

    @pytest.mark.asyncio
    async def test_disable_user(self, db_session, admin_user, regular_user):
        from app.routers.admin_router import update_user_status, UserStatusRequest
        request = UserStatusRequest(is_active=False)
        result = await update_user_status(
            user_id=regular_user.id, request=request,
            db=db_session, current_user=admin_user,
        )
        assert result["is_active"] is False

    @pytest.mark.asyncio
    async def test_cannot_disable_self(self, db_session, admin_user):
        from app.routers.admin_router import update_user_status, UserStatusRequest
        from fastapi import HTTPException
        request = UserStatusRequest(is_active=False)
        with pytest.raises(HTTPException) as exc_info:
            await update_user_status(
                user_id=admin_user.id, request=request,
                db=db_session, current_user=admin_user,
            )
        assert exc_info.value.status_code == 400


class TestListGroups:
    """Tests for GET /api/admin/groups"""

    @pytest.mark.asyncio
    async def test_list_groups(self, db_session, admin_user, test_group, system_group):
        from app.routers.admin_router import list_groups
        result = await list_groups(db=db_session, current_user=admin_user)
        names = [g["name"] for g in result]
        assert "Test Group" in names
        assert "System Owners" in names


class TestCreateGroup:
    """Tests for POST /api/admin/groups"""

    @pytest.mark.asyncio
    async def test_create_group(self, db_session, admin_user):
        from app.routers.admin_router import create_group, GroupCreateRequest
        request = GroupCreateRequest(name="New Group", description="A new group")
        result = await create_group(request=request, db=db_session, current_user=admin_user)
        assert result["name"] == "New Group"
        assert result["is_system"] is False

    @pytest.mark.asyncio
    async def test_create_duplicate_group_fails(self, db_session, admin_user, test_group):
        from app.routers.admin_router import create_group, GroupCreateRequest
        from fastapi import HTTPException
        request = GroupCreateRequest(name="Test Group")
        with pytest.raises(HTTPException) as exc_info:
            await create_group(request=request, db=db_session, current_user=admin_user)
        assert exc_info.value.status_code == 400


class TestDeleteGroup:
    """Tests for DELETE /api/admin/groups/{id}"""

    @pytest.mark.asyncio
    async def test_delete_custom_group(self, db_session, admin_user, test_group):
        from app.routers.admin_router import delete_group
        result = await delete_group(group_id=test_group.id, db=db_session, current_user=admin_user)
        assert "deleted" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_system_group_fails(self, db_session, admin_user, system_group):
        from app.routers.admin_router import delete_group
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await delete_group(group_id=system_group.id, db=db_session, current_user=admin_user)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_group_with_members_fails(self, db_session, admin_user, regular_user, test_group):
        await db_session.execute(user_groups.insert().values(user_id=regular_user.id, group_id=test_group.id))
        await db_session.flush()
        from app.routers.admin_router import delete_group
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await delete_group(group_id=test_group.id, db=db_session, current_user=admin_user)
        assert exc_info.value.status_code == 400
        assert "members" in exc_info.value.detail.lower()


class TestDeleteRole:
    """Tests for DELETE /api/admin/roles/{id}"""

    @pytest.mark.asyncio
    async def test_delete_custom_role(self, db_session, admin_user, test_role):
        from app.routers.admin_router import delete_role
        result = await delete_role(role_id=test_role.id, db=db_session, current_user=admin_user)
        assert "deleted" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_system_role_fails(self, db_session, admin_user, system_role):
        from app.routers.admin_router import delete_role
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await delete_role(role_id=system_role.id, db=db_session, current_user=admin_user)
        assert exc_info.value.status_code == 400


class TestListPermissions:
    """Tests for GET /api/admin/permissions"""

    @pytest.mark.asyncio
    async def test_list_permissions(self, db_session, admin_user, test_permission):
        from app.routers.admin_router import list_permissions
        result = await list_permissions(db=db_session, current_user=admin_user)
        names = [p["name"] for p in result]
        assert "bots:read" in names
