"""
Friend presence and social notifications via WebSocket.

Broadcasts events when friends come online or friend requests are accepted.
"""

import logging
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.auth import user_groups, group_roles, role_permissions, Permission
from app.models.social import Friendship
from app.services.broadcast_backend import broadcast_backend

logger = logging.getLogger(__name__)


async def _get_friend_ids(db: AsyncSession, user_id: int) -> set[int]:
    """Get all friend IDs for a user (bidirectional)."""
    result = await db.execute(
        select(Friendship).where(
            or_(
                Friendship.user_id == user_id,
                Friendship.friend_id == user_id,
            )
        )
    )
    friendships = result.scalars().all()
    return {
        f.friend_id if f.user_id == user_id else f.user_id
        for f in friendships
    }


async def broadcast_friend_online(ws_manager, db: AsyncSession, user_id: int) -> None:
    """Notify online friends that this user came online."""
    friend_ids = await _get_friend_ids(db, user_id)
    if not friend_ids:
        return

    # Only notify friends who are currently connected
    online_friend_ids = friend_ids & ws_manager.get_connected_user_ids()
    if not online_friend_ids:
        return

    # Get user's display name
    result = await db.execute(
        select(User.display_name).where(User.id == user_id)
    )
    display_name = result.scalar_one_or_none() or f"Player {user_id}"

    message = {
        "type": "friend:online",
        "user_id": user_id,
        "display_name": display_name,
    }

    for fid in online_friend_ids:
        try:
            await broadcast_backend.send_to_user(fid, message)
        except Exception as e:
            logger.debug(f"Failed to notify user {fid} of friend online: {e}")


async def notify_friend_request_accepted(
    ws_manager, db: AsyncSession, acceptor_id: int, requester_id: int
) -> None:
    """Notify the original requester that their friend request was accepted."""
    # Get acceptor's display name
    result = await db.execute(
        select(User.display_name).where(User.id == acceptor_id)
    )
    display_name = result.scalar_one_or_none() or f"Player {acceptor_id}"

    message = {
        "type": "friend:request_accepted",
        "user_id": acceptor_id,
        "display_name": display_name,
    }

    try:
        await broadcast_backend.send_to_user(requester_id, message)
    except Exception as e:
        logger.debug(f"Failed to notify user {requester_id} of accepted request: {e}")


async def broadcast_user_presence(
    ws_manager, db: AsyncSession, user_id: int, is_online: bool
) -> None:
    """Broadcast user online/offline status to users with admin:users permission (RBAC)."""
    message = {
        "type": "admin:user_presence",
        "user_id": user_id,
        "is_online": is_online,
    }

    connected_ids = ws_manager.get_connected_user_ids() - {user_id}
    if not connected_ids:
        return

    # Single query: find connected users who are superuser OR have admin:users
    # via the RBAC chain (user → groups → roles → permissions).
    has_admin_perm = (
        select(Permission.id)
        .join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .join(group_roles, group_roles.c.role_id == role_permissions.c.role_id)
        .join(user_groups, user_groups.c.group_id == group_roles.c.group_id)
        .where(
            user_groups.c.user_id == User.id,
            Permission.name == "admin:users",
        )
        .correlate(User)
        .exists()
    )

    result = await db.execute(
        select(User.id).where(
            User.id.in_(connected_ids),
            or_(User.is_superuser.is_(True), has_admin_perm),
        )
    )
    admin_ids = {row[0] for row in result.all()}

    for uid in admin_ids:
        try:
            await broadcast_backend.send_to_user(uid, message)
        except Exception:
            pass
