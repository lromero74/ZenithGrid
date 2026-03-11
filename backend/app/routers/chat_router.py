"""
Chat API Router

REST endpoints for chat channels, messages, and membership management.
Real-time delivery handled separately via WebSocket chat: messages.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_permission, Perm
from app.database import get_db
from app.models import User
from app.services import chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ----- Pydantic Schemas -----

class CreateChannelRequest(BaseModel):
    type: str = Field(..., pattern="^(dm|group|channel)$")
    name: Optional[str] = Field(None, max_length=100)
    member_ids: list[int] = Field(default_factory=list)
    friend_id: Optional[int] = None  # for DM creation


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class EditMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class AddMemberRequest(BaseModel):
    user_id: int


class RenameChannelRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


# ----- Channel Endpoints -----

@router.get("/channels")
async def list_channels(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> list[dict]:
    """List all chat channels the user belongs to."""
    return await chat_service.get_user_channels(db, current_user.id)


@router.post("/channels")
async def create_channel(
    body: CreateChannelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> dict:
    """Create a new chat channel (DM, group, or channel)."""
    try:
        if body.type == "dm":
            if body.friend_id is None:
                raise HTTPException(400, "friend_id required for DM")
            channel = await chat_service.get_or_create_dm(
                db, current_user.id, body.friend_id
            )
        elif body.type == "group":
            if not body.name:
                raise HTTPException(400, "name required for group")
            channel = await chat_service.create_group(
                db, current_user.id, body.name, body.member_ids
            )
        else:
            if not body.name:
                raise HTTPException(400, "name required for channel")
            channel = await chat_service.create_channel(
                db, current_user.id, body.name
            )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "id": channel.id,
        "type": channel.type,
        "name": channel.name,
    }


@router.patch("/channels/{channel_id}")
async def rename_channel(
    channel_id: int,
    body: RenameChannelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> dict:
    """Rename a group or channel."""
    try:
        await chat_service.rename_channel(db, channel_id, current_user.id, body.name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "renamed"}


# ----- Message Endpoints -----

@router.get("/channels/{channel_id}/messages")
async def get_messages(
    channel_id: int,
    before: Optional[int] = Query(None, description="Load messages before this ID"),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> list[dict]:
    """Get paginated messages for a channel."""
    try:
        return await chat_service.get_messages(
            db, channel_id, current_user.id, before, limit
        )
    except ValueError as e:
        raise HTTPException(403, str(e))


@router.post("/channels/{channel_id}/messages")
async def send_message(
    channel_id: int,
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> dict:
    """Send a message to a channel. Also broadcasts via WebSocket."""
    try:
        return await chat_service.send_message(
            db, channel_id, current_user.id, body.content
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.patch("/messages/{message_id}")
async def edit_message(
    message_id: int,
    body: EditMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> dict:
    """Edit a message. Only the sender can edit."""
    try:
        return await chat_service.edit_message(
            db, message_id, current_user.id, body.content
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> dict:
    """Soft-delete a message."""
    try:
        return await chat_service.delete_message(
            db, message_id, current_user.id
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


# ----- Read Tracking -----

@router.post("/channels/{channel_id}/read")
async def mark_read(
    channel_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> dict:
    """Mark all messages in a channel as read."""
    try:
        await chat_service.mark_read(db, channel_id, current_user.id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "read"}


@router.get("/unread")
async def get_unread_counts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> dict:
    """Get unread message counts per channel."""
    counts = await chat_service.get_unread_counts(db, current_user.id)
    return {"counts": counts}


# ----- Membership -----

@router.get("/channels/{channel_id}/members")
async def get_members(
    channel_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> list[dict]:
    """Get members of a channel."""
    # Validate membership first
    member_ids = await chat_service.get_channel_member_ids(db, channel_id)
    if current_user.id not in member_ids:
        raise HTTPException(403, "You are not a member of this channel")
    return await chat_service.get_channel_members(db, channel_id)


@router.post("/channels/{channel_id}/members")
async def add_member(
    channel_id: int,
    body: AddMemberRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> dict:
    """Add a friend to a group/channel."""
    try:
        return await chat_service.add_member(
            db, channel_id, current_user.id, body.user_id
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/channels/{channel_id}/members/{user_id}")
async def remove_member(
    channel_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.GAMES_MULTIPLAYER)),
) -> dict:
    """Remove a member from a group/channel, or leave."""
    try:
        await chat_service.remove_member(
            db, channel_id, current_user.id, user_id
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "removed"}
