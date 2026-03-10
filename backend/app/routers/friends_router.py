"""
Friends & Social API Router

Endpoints for managing friendships, friend requests, blocking, and user search.
All social interactions are scoped by authenticated user.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import User
from app.models.social import BlockedUser, FriendRequest, Friendship

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/friends", tags=["friends"])


# ----- Pydantic Schemas -----

class FriendRequestCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=50)


class BlockUserRequest(BaseModel):
    user_id: int


class FriendOut(BaseModel):
    id: int
    display_name: str


class FriendRequestOut(BaseModel):
    id: int
    from_user_id: int
    from_display_name: str
    created_at: str


class BlockedUserOut(BaseModel):
    user_id: int
    display_name: str


class UserSearchResult(BaseModel):
    id: int
    display_name: str


# ----- Endpoints -----

@router.get("")
async def list_friends(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """List all friends of the current user."""
    result = await db.execute(
        select(Friendship, User)
        .join(User, Friendship.friend_id == User.id)
        .where(Friendship.user_id == current_user.id)
        .order_by(User.display_name)
    )
    rows = result.all()
    return [
        {"id": user.id, "display_name": user.display_name}
        for _, user in rows
    ]


@router.post("/request")
async def send_friend_request(
    body: FriendRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Send a friend request by display name."""
    # Find target user
    result = await db.execute(
        select(User).where(
            User.display_name.ilike(body.display_name),
            User.is_active.is_(True),
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Cannot friend yourself
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot send friend request to yourself")

    # Check if already friends
    existing_friendship = await db.execute(
        select(Friendship.id).where(
            Friendship.user_id == current_user.id,
            Friendship.friend_id == target.id,
        )
    )
    if existing_friendship.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Already friends")

    # Check if blocked (either direction)
    block_check = await db.execute(
        select(BlockedUser.id).where(
            or_(
                and_(BlockedUser.blocker_id == current_user.id, BlockedUser.blocked_id == target.id),
                and_(BlockedUser.blocker_id == target.id, BlockedUser.blocked_id == current_user.id),
            )
        )
    )
    if block_check.scalar_one_or_none() is not None:
        raise HTTPException(status_code=403, detail="Cannot send friend request")

    # Check for existing pending request (either direction)
    pending = await db.execute(
        select(FriendRequest.id).where(
            or_(
                and_(FriendRequest.from_user_id == current_user.id, FriendRequest.to_user_id == target.id),
                and_(FriendRequest.from_user_id == target.id, FriendRequest.to_user_id == current_user.id),
            )
        )
    )
    if pending.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Friend request already pending")

    req = FriendRequest(from_user_id=current_user.id, to_user_id=target.id)
    db.add(req)
    await db.flush()
    return {"id": req.id, "to_user_id": target.id, "to_display_name": target.display_name}


@router.get("/requests")
async def list_friend_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """List pending incoming friend requests."""
    result = await db.execute(
        select(FriendRequest, User)
        .join(User, FriendRequest.from_user_id == User.id)
        .where(FriendRequest.to_user_id == current_user.id)
        .order_by(FriendRequest.created_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": req.id,
            "from_user_id": req.from_user_id,
            "from_display_name": user.display_name,
            "created_at": req.created_at.isoformat() if req.created_at else None,
        }
        for req, user in rows
    ]


@router.get("/requests/sent")
async def list_sent_friend_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """List pending outgoing friend requests sent by the current user."""
    result = await db.execute(
        select(FriendRequest, User)
        .join(User, FriendRequest.to_user_id == User.id)
        .where(FriendRequest.from_user_id == current_user.id)
        .order_by(FriendRequest.created_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": req.id,
            "to_user_id": req.to_user_id,
            "to_display_name": user.display_name,
            "created_at": req.created_at.isoformat() if req.created_at else None,
        }
        for req, user in rows
    ]


@router.delete("/requests/sent/{request_id}")
async def cancel_sent_friend_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Cancel a friend request you sent."""
    result = await db.execute(
        select(FriendRequest).where(
            FriendRequest.id == request_id,
            FriendRequest.from_user_id == current_user.id,
        )
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Sent request not found")

    await db.delete(req)
    await db.flush()
    return {"status": "cancelled"}


@router.post("/requests/{request_id}/accept")
async def accept_friend_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Accept a pending friend request — creates bidirectional friendship."""
    result = await db.execute(
        select(FriendRequest).where(
            FriendRequest.id == request_id,
            FriendRequest.to_user_id == current_user.id,
        )
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Friend request not found")

    # Create bidirectional friendship
    db.add(Friendship(user_id=current_user.id, friend_id=req.from_user_id))
    db.add(Friendship(user_id=req.from_user_id, friend_id=current_user.id))

    # Delete the request
    await db.delete(req)
    await db.flush()
    return {"friend_id": req.from_user_id, "status": "accepted"}


@router.delete("/requests/{request_id}")
async def reject_friend_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Reject/dismiss a friend request (silent — no block)."""
    result = await db.execute(
        select(FriendRequest).where(
            FriendRequest.id == request_id,
            FriendRequest.to_user_id == current_user.id,
        )
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Friend request not found")

    await db.delete(req)
    await db.flush()
    return {"status": "rejected"}


@router.delete("/{friend_id}")
async def remove_friend(
    friend_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Remove a friend — deletes both direction rows."""
    # Delete both directions
    await db.execute(
        delete(Friendship).where(
            or_(
                and_(Friendship.user_id == current_user.id, Friendship.friend_id == friend_id),
                and_(Friendship.user_id == friend_id, Friendship.friend_id == current_user.id),
            )
        )
    )
    await db.flush()
    return {"status": "removed"}


@router.post("/block")
async def block_user(
    body: BlockUserRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Block a user. Also removes any existing friendship."""
    if body.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot block yourself")

    # Check user exists
    target = await db.execute(select(User.id).where(User.id == body.user_id))
    if target.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if already blocked
    existing = await db.execute(
        select(BlockedUser.id).where(
            BlockedUser.blocker_id == current_user.id,
            BlockedUser.blocked_id == body.user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="User already blocked")

    # Remove any friendship
    await db.execute(
        delete(Friendship).where(
            or_(
                and_(Friendship.user_id == current_user.id, Friendship.friend_id == body.user_id),
                and_(Friendship.user_id == body.user_id, Friendship.friend_id == current_user.id),
            )
        )
    )

    # Remove any pending requests (both directions)
    await db.execute(
        delete(FriendRequest).where(
            or_(
                and_(FriendRequest.from_user_id == current_user.id, FriendRequest.to_user_id == body.user_id),
                and_(FriendRequest.from_user_id == body.user_id, FriendRequest.to_user_id == current_user.id),
            )
        )
    )

    db.add(BlockedUser(blocker_id=current_user.id, blocked_id=body.user_id))
    await db.flush()
    return {"status": "blocked"}


@router.delete("/block/{user_id}")
async def unblock_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Unblock a user."""
    result = await db.execute(
        select(BlockedUser).where(
            BlockedUser.blocker_id == current_user.id,
            BlockedUser.blocked_id == user_id,
        )
    )
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")

    await db.delete(block)
    await db.flush()
    return {"status": "unblocked"}


@router.get("/blocked")
async def list_blocked_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """List all blocked users."""
    result = await db.execute(
        select(BlockedUser, User)
        .join(User, BlockedUser.blocked_id == User.id)
        .where(BlockedUser.blocker_id == current_user.id)
        .order_by(User.display_name)
    )
    rows = result.all()
    return [
        {"user_id": user.id, "display_name": user.display_name}
        for _, user in rows
    ]


# ----- User Search (mounted under /api/users) -----

search_router = APIRouter(prefix="/api/users", tags=["users"])


@search_router.get("/search")
async def search_users(
    q: str = Query(..., min_length=1, max_length=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Search for users by display name. Excludes inactive, self, and blocked users."""
    # Escape LIKE wildcards to prevent pattern injection
    q_safe = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    # Subquery: user IDs blocked by me or who blocked me
    blocked_ids = select(BlockedUser.blocked_id).where(
        BlockedUser.blocker_id == current_user.id
    ).union(
        select(BlockedUser.blocker_id).where(
            BlockedUser.blocked_id == current_user.id
        )
    ).subquery()

    result = await db.execute(
        select(User)
        .where(
            User.display_name.ilike(f"%{q_safe}%"),
            User.is_active.is_(True),
            User.id != current_user.id,
            User.id.not_in(select(blocked_ids)),
        )
        .limit(20)
    )
    users = result.scalars().all()
    return [{"id": u.id, "display_name": u.display_name} for u in users]
