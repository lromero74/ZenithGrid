"""
Admin Management Router

Handles RBAC administration:
- User management (list, status, group assignments)
- Group management (CRUD, role assignments)
- Role management (CRUD, permission assignments)
- Permission listing (read-only)
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import (
    Group, Permission, Role, User,
    group_roles, role_permissions, user_groups,
)
from app.auth.dependencies import require_permission, Perm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Request/Response schemas
# ---------------------------------------------------------------------------

class UserStatusRequest(BaseModel):
    is_active: bool


class UserGroupsRequest(BaseModel):
    group_ids: List[int]


class GroupCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    role_ids: Optional[List[int]] = None


class GroupUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    role_ids: Optional[List[int]] = None


class RoleCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    requires_mfa: bool = False
    permission_ids: Optional[List[int]] = None


class RoleUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    requires_mfa: Optional[bool] = None
    permission_ids: Optional[List[int]] = None


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
):
    """List all users with group memberships and MFA status."""
    query = (
        select(User)
        .options(selectinload(User.groups))
        .order_by(User.id)
    )
    result = await db.execute(query)
    users = result.scalars().all()

    return [
        {
            "id": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "is_active": u.is_active,
            "is_superuser": u.is_superuser,
            "mfa_enabled": bool(u.mfa_enabled),
            "mfa_email_enabled": bool(u.mfa_email_enabled),
            "groups": [{"id": g.id, "name": g.name} for g in u.groups],
            "session_policy_override": u.session_policy_override,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.put("/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    request: UserStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
):
    """Enable or disable a user account."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own account status")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = request.is_active
    await db.commit()
    await db.refresh(user)

    action = "enabled" if request.is_active else "disabled"
    logger.info(f"Admin {current_user.email} {action} user {user.email}")

    return {"id": user.id, "email": user.email, "is_active": user.is_active}


@router.put("/users/{user_id}/groups")
async def update_user_groups(
    user_id: int,
    request: UserGroupsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
):
    """Assign/replace group memberships for a user."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Load requested groups with their roles
    groups_result = await db.execute(
        select(Group)
        .where(Group.id.in_(request.group_ids))
        .options(selectinload(Group.roles))
    )
    new_groups = groups_result.scalars().all()

    if len(new_groups) != len(request.group_ids):
        raise HTTPException(status_code=400, detail="One or more group IDs are invalid")

    # Check MFA requirement: if any role in any group requires MFA, user must have it
    for group in new_groups:
        for role in group.roles:
            if role.requires_mfa and not user.mfa_enabled:
                raise HTTPException(
                    status_code=400,
                    detail=f"MFA must be enabled before joining group '{group.name}' "
                           f"(role '{role.name}' requires MFA)",
                )

    # Replace group memberships
    await db.execute(user_groups.delete().where(user_groups.c.user_id == user_id))
    for group in new_groups:
        await db.execute(user_groups.insert().values(user_id=user_id, group_id=group.id))
    await db.commit()

    logger.info(f"Admin {current_user.email} updated groups for user {user.email}: "
                f"{[g.name for g in new_groups]}")

    return {
        "id": user.id,
        "email": user.email,
        "groups": [{"id": g.id, "name": g.name} for g in new_groups],
    }


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

@router.get("/groups")
async def list_groups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_GROUPS)),
):
    """List all groups with their roles and member count."""
    query = (
        select(Group)
        .options(selectinload(Group.roles))
        .order_by(Group.id)
    )
    result = await db.execute(query)
    groups = result.scalars().all()

    # Get member counts
    member_counts = {}
    count_query = (
        select(user_groups.c.group_id, func.count(user_groups.c.user_id))
        .group_by(user_groups.c.group_id)
    )
    count_result = await db.execute(count_query)
    for group_id, count in count_result:
        member_counts[group_id] = count

    return [
        {
            "id": g.id,
            "name": g.name,
            "description": g.description,
            "is_system": g.is_system,
            "session_policy": g.session_policy,
            "member_count": member_counts.get(g.id, 0),
            "roles": [{"id": r.id, "name": r.name} for r in g.roles],
        }
        for g in groups
    ]


@router.post("/groups", status_code=201)
async def create_group(
    request: GroupCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_GROUPS)),
):
    """Create a custom group."""
    # Check name uniqueness
    existing = await db.execute(select(Group).where(Group.name == request.name))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail=f"Group '{request.name}' already exists")

    group = Group(name=request.name, description=request.description, is_system=False)
    db.add(group)
    await db.commit()
    await db.refresh(group)

    # Assign roles if provided
    if request.role_ids:
        for role_id in request.role_ids:
            await db.execute(group_roles.insert().values(group_id=group.id, role_id=role_id))
        await db.commit()

    logger.info(f"Admin {current_user.email} created group '{group.name}'")

    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "is_system": group.is_system,
    }


@router.put("/groups/{group_id}")
async def update_group(
    group_id: int,
    request: GroupUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_GROUPS)),
):
    """Update a group's name, description, or role assignments."""
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if request.name is not None:
        # Check uniqueness
        existing = await db.execute(
            select(Group).where(Group.name == request.name, Group.id != group_id)
        )
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail=f"Group '{request.name}' already exists")
        group.name = request.name

    if request.description is not None:
        group.description = request.description

    if request.role_ids is not None:
        await db.execute(group_roles.delete().where(group_roles.c.group_id == group_id))
        for role_id in request.role_ids:
            await db.execute(group_roles.insert().values(group_id=group_id, role_id=role_id))

    await db.commit()
    await db.refresh(group)

    logger.info(f"Admin {current_user.email} updated group '{group.name}'")

    return {"id": group.id, "name": group.name, "description": group.description, "is_system": group.is_system}


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_GROUPS)),
):
    """Delete a non-system group (must have no members)."""
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if group.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system groups")

    # Check for members
    member_count = await db.execute(
        select(func.count()).select_from(user_groups).where(user_groups.c.group_id == group_id)
    )
    if member_count.scalar() > 0:
        raise HTTPException(status_code=400, detail="Group has active members. Remove all users before deleting.")

    await db.delete(group)
    await db.commit()

    logger.info(f"Admin {current_user.email} deleted group '{group.name}'")

    return {"message": f"Group '{group.name}' deleted"}


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

@router.get("/roles")
async def list_roles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_ROLES)),
):
    """List all roles with their permissions."""
    query = (
        select(Role)
        .options(selectinload(Role.permissions))
        .order_by(Role.id)
    )
    result = await db.execute(query)
    roles = result.scalars().all()

    return [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "is_system": r.is_system,
            "requires_mfa": r.requires_mfa,
            "permissions": [{"id": p.id, "name": p.name} for p in r.permissions],
        }
        for r in roles
    ]


@router.post("/roles", status_code=201)
async def create_role(
    request: RoleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_ROLES)),
):
    """Create a custom role."""
    existing = await db.execute(select(Role).where(Role.name == request.name))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail=f"Role '{request.name}' already exists")

    role = Role(
        name=request.name,
        description=request.description,
        is_system=False,
        requires_mfa=request.requires_mfa,
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)

    if request.permission_ids:
        for perm_id in request.permission_ids:
            await db.execute(role_permissions.insert().values(role_id=role.id, permission_id=perm_id))
        await db.commit()

    logger.info(f"Admin {current_user.email} created role '{role.name}'")

    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "requires_mfa": role.requires_mfa,
    }


@router.put("/roles/{role_id}")
async def update_role(
    role_id: int,
    request: RoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_ROLES)),
):
    """Update a role's name, description, or permission assignments."""
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if request.name is not None:
        existing = await db.execute(
            select(Role).where(Role.name == request.name, Role.id != role_id)
        )
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail=f"Role '{request.name}' already exists")
        role.name = request.name

    if request.description is not None:
        role.description = request.description

    if request.requires_mfa is not None:
        role.requires_mfa = request.requires_mfa

    if request.permission_ids is not None:
        await db.execute(role_permissions.delete().where(role_permissions.c.role_id == role_id))
        for perm_id in request.permission_ids:
            await db.execute(role_permissions.insert().values(role_id=role_id, permission_id=perm_id))

    await db.commit()
    await db.refresh(role)

    logger.info(f"Admin {current_user.email} updated role '{role.name}'")

    return {
        "id": role.id, "name": role.name, "description": role.description,
        "is_system": role.is_system, "requires_mfa": role.requires_mfa,
    }


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_ROLES)),
):
    """Delete a non-system role (must not be assigned to any group)."""
    role = await db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system roles")

    # Check if assigned to any group
    assigned = await db.execute(
        select(func.count()).select_from(group_roles).where(group_roles.c.role_id == role_id)
    )
    if assigned.scalar() > 0:
        raise HTTPException(status_code=400, detail="Role is assigned to groups. Remove from all groups first.")

    await db.delete(role)
    await db.commit()

    logger.info(f"Admin {current_user.email} deleted role '{role.name}'")

    return {"message": f"Role '{role.name}' deleted"}


# ---------------------------------------------------------------------------
# Permissions (read-only)
# ---------------------------------------------------------------------------

@router.get("/permissions")
async def list_permissions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_PERMISSIONS)),
):
    """List all permissions (read-only — permissions are defined in code)."""
    result = await db.execute(select(Permission).order_by(Permission.name))
    permissions = result.scalars().all()

    return [
        {"id": p.id, "name": p.name, "description": p.description}
        for p in permissions
    ]


# ---------------------------------------------------------------------------
# Session Policy Management
# ---------------------------------------------------------------------------


@router.put("/groups/{group_id}/session-policy")
async def update_group_session_policy(
    group_id: int,
    policy: Optional[dict] = None,
    current_user: User = Depends(require_permission(Perm.ADMIN_GROUPS)),
    db: AsyncSession = Depends(get_db),
):
    """Set or clear session policy for a group."""
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    group.session_policy = policy
    await db.commit()

    return {"message": f"Session policy updated for group '{group.name}'", "policy": policy}


@router.put("/users/{user_id}/session-policy")
async def update_user_session_policy(
    user_id: int,
    policy: Optional[dict] = None,
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
    db: AsyncSession = Depends(get_db),
):
    """Set or clear session policy override for a user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.session_policy_override = policy
    await db.commit()

    return {"message": f"Session policy override updated for user '{user.email}'", "policy": policy}


@router.get("/users/{user_id}/effective-session-policy")
async def get_effective_session_policy(
    user_id: int,
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
    db: AsyncSession = Depends(get_db),
):
    """Get the resolved effective session policy for a user."""
    from app.services.session_policy_service import resolve_session_policy
    from app.auth.dependencies import get_user_by_id

    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    policy = resolve_session_policy(user)
    return {"user_id": user_id, "email": user.email, "effective_policy": policy}


@router.get("/users/{user_id}/sessions")
async def list_user_sessions(
    user_id: int,
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
    db: AsyncSession = Depends(get_db),
):
    """List active sessions for a user."""
    from app.services.session_service import get_user_sessions

    sessions = await get_user_sessions(user_id, db)
    return {
        "user_id": user_id,
        "sessions": [
            {
                "session_id": s.session_id,
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            }
            for s in sessions
        ],
    }


@router.delete("/users/{user_id}/sessions/{session_id}")
async def force_end_session(
    user_id: int,
    session_id: str,
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
    db: AsyncSession = Depends(get_db),
):
    """Force-end a specific user session."""
    from app.services.session_service import end_session

    ended = await end_session(session_id, db)
    if not ended:
        raise HTTPException(status_code=404, detail="Active session not found")

    await db.commit()
    return {"message": f"Session {session_id} ended"}
