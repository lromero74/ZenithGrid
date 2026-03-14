"""
Friend presence and social notifications via WebSocket.

Broadcasts events when friends come online or friend requests are accepted.
"""

import logging
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.social import Friendship

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
            await ws_manager.send_to_user(fid, message)
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
        await ws_manager.send_to_user(requester_id, message)
    except Exception as e:
        logger.debug(f"Failed to notify user {requester_id} of accepted request: {e}")
