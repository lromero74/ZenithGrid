"""
Admin Management Router

Handles RBAC administration:
- User management (list, status, group assignments)
- Group management (CRUD, role assignments)
- Role management (CRUD, permission assignments)
- Permission listing (read-only)
"""

import ipaddress
import logging
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
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


class SessionPolicyRequest(BaseModel):
    max_sessions: Optional[int] = Field(None, ge=1, le=100)
    session_duration_hours: Optional[int] = Field(None, ge=1, le=8760)
    require_mfa: Optional[bool] = None
    trusted_device_days: Optional[int] = Field(None, ge=0, le=365)


# ---------------------------------------------------------------------------
# Module-level state

_last_ban_refresh: float = 0.0


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
):
    """List all users with group memberships, MFA status, and online indicator."""
    from app.services.websocket_manager import ws_manager
    from app.models.auth import ActiveSession
    from app.services.ban_monitor import _lookup_ip_geo
    import asyncio

    query = (
        select(User)
        .options(selectinload(User.groups))
        .order_by(User.id)
    )
    result = await db.execute(query)
    users = result.scalars().all()

    online_ids = ws_manager.get_connected_user_ids()

    # Get all active session IPs for Observers (shared accounts) for geo tracking
    observer_ids = [u.id for u in users if any(g.name == "Observers" for g in u.groups)]
    observer_locations: dict[int, list[dict]] = {}
    if observer_ids:
        session_result = await db.execute(
            select(ActiveSession.user_id, ActiveSession.ip_address)
            .where(
                ActiveSession.user_id.in_(observer_ids),
                ActiveSession.is_active.is_(True),
            )
            .order_by(ActiveSession.created_at.desc())
        )
        # Collect unique IPs per user
        user_ips: dict[int, list[str]] = {}
        for uid, ip in session_result.all():
            if ip:
                user_ips.setdefault(uid, [])
                if ip not in user_ips[uid]:
                    user_ips[uid].append(ip)

        # Geo lookups in thread pool (deduplicated across all users)
        all_unique_ips = set()
        for ips in user_ips.values():
            all_unique_ips.update(ips)

        if all_unique_ips:
            loop = asyncio.get_event_loop()
            unique_ip_list = list(all_unique_ips)
            geo_results = await asyncio.gather(
                *[loop.run_in_executor(None, _lookup_ip_geo, ip) for ip in unique_ip_list]
            )
            ip_geo_cache: dict[str, dict] = dict(zip(unique_ip_list, geo_results))

            for uid, ips in user_ips.items():
                observer_locations[uid] = [
                    {"ip": ip, **ip_geo_cache.get(ip, {})}
                    for ip in ips
                ]

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
            "is_online": u.id in online_ids,
            "admin_display_name": u.admin_display_name,
            "login_locations": observer_locations.get(u.id),
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
    policy: Optional[SessionPolicyRequest] = None,
    current_user: User = Depends(require_permission(Perm.ADMIN_GROUPS)),
    db: AsyncSession = Depends(get_db),
):
    """Set or clear session policy for a group."""
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    policy_dict = policy.model_dump(exclude_none=True) if policy else None
    group.session_policy = policy_dict
    await db.commit()

    return {"message": f"Session policy updated for group '{group.name}'", "policy": policy_dict}


@router.put("/users/{user_id}/session-policy")
async def update_user_session_policy(
    user_id: int,
    policy: Optional[SessionPolicyRequest] = None,
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
    db: AsyncSession = Depends(get_db),
):
    """Set or clear session policy override for a user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    policy_dict = policy.model_dump(exclude_none=True) if policy else None
    user.session_policy_override = policy_dict
    await db.commit()

    return {"message": f"Session policy override updated for user '{user.email}'", "policy": policy_dict}


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


# ---------------------------------------------------------------------------
# Security / Bans
# ---------------------------------------------------------------------------


@router.get("/bans")
async def get_banned_ips(
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
):
    """Return cached fail2ban ban snapshot (updated daily)."""
    from app.services.ban_monitor import get_ban_snapshot

    snapshot = get_ban_snapshot()
    return _format_ban_snapshot(snapshot)


@router.post("/bans/refresh")
async def refresh_bans(
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
):
    """Force-refresh the fail2ban ban snapshot (queries fail2ban now)."""
    global _last_ban_refresh
    if time.time() - _last_ban_refresh < 10:
        raise HTTPException(status_code=429, detail="Refresh rate limited — wait 10 seconds between refreshes")

    from app.services.ban_monitor import refresh_ban_snapshot

    snapshot = await refresh_ban_snapshot()
    _last_ban_refresh = time.time()
    return _format_ban_snapshot(snapshot)


class UnbanRequest(BaseModel):
    ip: str


@router.post("/bans/unban")
async def unban_ip(
    data: UnbanRequest,
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
):
    """Unban an IP from all fail2ban jails and firewalld."""
    import subprocess

    ip = data.ip.strip()
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid IP address format")

    unbanned_jails = []

    # Get jail list
    try:
        result = subprocess.run(
            ["sudo", "fail2ban-client", "status"],
            capture_output=True, text=True, timeout=10,
        )
        jails = []
        for line in result.stdout.splitlines():
            if "Jail list:" in line:
                jails = [j.strip() for j in line.split(":", 1)[1].split(",") if j.strip()]

        for jail in jails:
            unban_result = subprocess.run(
                ["sudo", "fail2ban-client", "set", jail, "unbanip", ip],
                capture_output=True, text=True, timeout=10,
            )
            if unban_result.returncode == 0:
                unbanned_jails.append(jail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unban failed: {e}")

    # Also remove firewalld rich rule if present
    try:
        subprocess.run(
            ["sudo", "firewall-cmd",
             f"--remove-rich-rule=rule family='ipv4' source address='{ip}' drop"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        pass

    # Refresh the cached snapshot
    from app.services.ban_monitor import refresh_ban_snapshot
    await refresh_ban_snapshot()

    logger.info(f"Admin {current_user.email} unbanned IP {ip} from jails: {unbanned_jails}")

    return {
        "ip": ip,
        "unbanned_from": unbanned_jails,
        "message": f"IP {ip} unbanned" if unbanned_jails else f"IP {ip} was not found in any jail",
    }


@router.get("/bans/{ip}/details")
async def get_ban_details(
    ip: str,
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
):
    """Get attack patterns that led to an IP ban. Greps nginx + intrusion logs."""
    import subprocess
    import asyncio

    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid IP address format")

    patterns: list[dict] = []

    async def _grep_log(log_path: str, source: str):
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["grep", "-F", ip, log_path],
                    capture_output=True, text=True, timeout=10,
                )
            )
            if result.returncode != 0:
                return
            for line in result.stdout.strip().split("\n")[:50]:
                if not line.strip():
                    continue
                patterns.append({"source": source, "line": line.strip()[:500]})
        except Exception:
            pass

    async def _zgrep_log(log_path: str, source: str):
        """Search gzipped rotated logs."""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["zgrep", "-F", ip, log_path],
                    capture_output=True, text=True, timeout=10,
                )
            )
            if result.returncode != 0:
                return
            for line in result.stdout.strip().split("\n")[:50]:
                if not line.strip():
                    continue
                patterns.append({"source": source, "line": line.strip()[:500]})
        except Exception:
            pass

    # Search current + rotated logs (plain text and gzipped)
    import glob
    nginx_rotated = sorted(glob.glob("/var/log/nginx/access.log-*"))
    # Only search the 3 most recent rotated logs to keep it fast
    nginx_rotated = nginx_rotated[-3:]

    tasks = [_grep_log("/var/log/nginx/access.log", "nginx")]
    for rotated in nginx_rotated:
        if rotated.endswith(".gz"):
            tasks.append(_zgrep_log(rotated, "nginx"))
        else:
            tasks.append(_grep_log(rotated, "nginx"))
    tasks.append(_grep_log("/var/log/zenithgrid/intrusion.log", "intrusion"))

    await asyncio.gather(*tasks)

    # Categorize patterns
    categories: dict[str, int] = {}
    for p in patterns:
        line = p["line"].lower()
        if ".php" in line or "wp-" in line or "xmlrpc" in line:
            cat = "WordPress/PHP scan"
        elif ".env" in line:
            cat = "Env file enumeration"
        elif "cgi-bin" in line or "/bin/sh" in line or "/bin/bash" in line:
            cat = "Shell injection"
        elif "../" in line or "%2e" in line:
            cat = "Path traversal"
        elif "swagger" in line or "actuator" in line or "graphql" in line:
            cat = "API framework scan"
        elif "console" in line or "login" in line or "admin" in line:
            cat = "Admin panel probe"
        elif ".bak" in line or ".old" in line or "debug.log" in line:
            cat = "Backup file scan"
        elif "[INTRUSION]" in p["line"]:
            cat = "POST body injection"
        else:
            cat = "Other"
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "ip": ip,
        "total_hits": len(patterns),
        "categories": categories,
        "sample_requests": [p["line"] for p in patterns[:20]],
    }


def _format_ban_snapshot(snapshot):
    from datetime import datetime
    return {
        "currently_banned": snapshot.currently_banned,
        "total_banned": snapshot.total_banned,
        "total_failed": snapshot.total_failed,
        "last_updated": datetime.utcfromtimestamp(snapshot.last_updated).isoformat()
        if snapshot.last_updated > 0 else None,
        "banned_ips": [
            {
                "ip": b.ip,
                "jail": b.jail,
                "city": b.city,
                "region": b.region,
                "country": b.country,
                "country_name": b.country_name,
                "org": b.org,
                "hostname": b.hostname,
            }
            for b in snapshot.banned_ips
        ],
    }
