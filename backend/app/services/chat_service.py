"""
Chat service — business logic for DMs, group chats, and channels.

Handles channel creation, membership, messages, read tracking, and retention.
All queries are scoped by user_id to ensure data isolation.
"""

import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import User
from app.models.social import (
    BlockedUser, ChatChannel, ChatChannelMember, ChatMessage,
    ChatMessageReaction, Friendship,
)

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 2000

# Must match EMOJI_LIST in frontend MessageBubble.tsx
ALLOWED_EMOJIS = {
    "👍", "👎", "❤️", "😂", "😮", "😢", "😡", "🎉",
    "🔥", "👀", "💯", "🙏", "👏", "🤔", "😍", "🎮",
}


# ----- Private Helpers -----

async def _validate_membership(
    db: AsyncSession, channel_id: int, user_id: int
) -> ChatChannelMember:
    """Validate user is a member of a channel. Returns the membership row.

    Raises ValueError if not a member.
    """
    result = await db.execute(
        select(ChatChannelMember).where(
            ChatChannelMember.channel_id == channel_id,
            ChatChannelMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise ValueError("You are not a member of this channel")
    return member


async def _aggregate_reactions(db: AsyncSession, message_id: int) -> list[dict]:
    """Load and aggregate reactions for a single message."""
    reactions_q = await db.execute(
        select(ChatMessageReaction).where(
            ChatMessageReaction.message_id == message_id
        )
    )
    all_reactions = reactions_q.scalars().all()
    emoji_map: dict[str, list[int]] = {}
    for r in all_reactions:
        emoji_map.setdefault(r.emoji, []).append(r.user_id)
    return [
        {"emoji": emoji, "count": len(uids), "user_ids": uids}
        for emoji, uids in emoji_map.items()
    ]


async def _batch_aggregate_reactions(
    db: AsyncSession, message_ids: list[int]
) -> dict[int, list[dict]]:
    """Batch-load reactions for multiple messages in a single query.

    Returns {message_id: [{emoji, count, user_ids}, ...]}
    """
    if not message_ids:
        return {}

    reactions_q = await db.execute(
        select(ChatMessageReaction).where(
            ChatMessageReaction.message_id.in_(message_ids)
        )
    )
    all_reactions = reactions_q.scalars().all()

    # Group by message_id then by emoji
    msg_emoji_map: dict[int, dict[str, list[int]]] = {}
    for r in all_reactions:
        emoji_map = msg_emoji_map.setdefault(r.message_id, {})
        emoji_map.setdefault(r.emoji, []).append(r.user_id)

    return {
        mid: [
            {"emoji": emoji, "count": len(uids), "user_ids": uids}
            for emoji, uids in emojis.items()
        ]
        for mid, emojis in msg_emoji_map.items()
    }


async def _build_message_dict(
    db: AsyncSession, msg: ChatMessage, sender_name: str,
    reactions_cache: dict[int, list[dict]] | None = None,
    reply_cache: dict[int, dict | None] | None = None,
) -> dict:
    """Build the full message response dict including reactions and reply-to.

    Optional caches avoid N+1 queries when building multiple messages.
    """
    result = {
        "id": msg.id,
        "channel_id": msg.channel_id,
        "sender_id": msg.sender_id,
        "sender_name": sender_name,
        "content": msg.content if msg.deleted_at is None else None,
        "media_url": msg.media_url if msg.deleted_at is None else None,
        "is_deleted": msg.deleted_at is not None,
        "edited_at": msg.edited_at.isoformat() if msg.edited_at else None,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "is_pinned": bool(msg.is_pinned),
        "reply_to": None,
        "reactions": [],
    }

    # Load reply-to preview
    if msg.reply_to_id and msg.deleted_at is None:
        if reply_cache is not None and msg.reply_to_id in reply_cache:
            result["reply_to"] = reply_cache[msg.reply_to_id]
        else:
            reply_msg = await db.get(ChatMessage, msg.reply_to_id)
            if reply_msg:
                reply_sender = await db.get(User, reply_msg.sender_id)
                result["reply_to"] = {
                    "id": reply_msg.id,
                    "sender_name": (reply_sender.display_name
                                    if reply_sender else "Unknown"),
                    "content": (reply_msg.content[:100]
                                if reply_msg.deleted_at is None else None),
                    "is_deleted": reply_msg.deleted_at is not None,
                }

    # Load reactions (aggregated)
    if msg.deleted_at is None:
        if reactions_cache is not None:
            result["reactions"] = reactions_cache.get(msg.id, [])
        else:
            result["reactions"] = await _aggregate_reactions(db, msg.id)

    return result


async def _batch_build_message_dicts(
    db: AsyncSession, rows: list[tuple[ChatMessage, User]]
) -> list[dict]:
    """Batch-build message dicts for multiple (message, sender) rows.

    Loads all reactions and reply-to data in bulk to avoid N+1 queries.
    """
    if not rows:
        return []

    # Collect IDs for batch loading
    active_msg_ids = [msg.id for msg, _ in rows if msg.deleted_at is None]
    reply_to_ids = [
        msg.reply_to_id for msg, _ in rows
        if msg.reply_to_id and msg.deleted_at is None
    ]

    # Batch load reactions
    reactions_cache = await _batch_aggregate_reactions(db, active_msg_ids)

    # Batch load reply-to messages and senders
    reply_cache: dict[int, dict | None] = {}
    if reply_to_ids:
        unique_reply_ids = list(set(reply_to_ids))
        reply_msgs_q = await db.execute(
            select(ChatMessage, User)
            .join(User, ChatMessage.sender_id == User.id)
            .where(ChatMessage.id.in_(unique_reply_ids))
        )
        for reply_msg, reply_sender in reply_msgs_q.all():
            reply_cache[reply_msg.id] = {
                "id": reply_msg.id,
                "sender_name": (reply_sender.display_name
                                if reply_sender else "Unknown"),
                "content": (reply_msg.content[:100]
                            if reply_msg.deleted_at is None else None),
                "is_deleted": reply_msg.deleted_at is not None,
            }

    return [
        await _build_message_dict(
            db, msg, sender.display_name,
            reactions_cache=reactions_cache,
            reply_cache=reply_cache,
        )
        for msg, sender in rows
    ]


# ----- Channel Creation -----

async def get_or_create_dm(
    db: AsyncSession, user_id: int, friend_id: int
) -> ChatChannel:
    """Get existing DM channel between two users, or create one.

    Validates friendship before creating. Returns the channel.
    """
    # Check friendship
    friendship = await db.execute(
        select(Friendship.id).where(
            Friendship.user_id == user_id,
            Friendship.friend_id == friend_id,
        )
    )
    if friendship.scalar_one_or_none() is None:
        raise ValueError("You can only message accepted friends")

    # Check not blocked
    block = await db.execute(
        select(BlockedUser.id).where(
            BlockedUser.blocker_id == friend_id,
            BlockedUser.blocked_id == user_id,
        )
    )
    if block.scalar_one_or_none() is not None:
        raise ValueError("Cannot message this user")

    # Find existing DM where both users are members (single query)
    my_member = aliased(ChatChannelMember)
    friend_member = aliased(ChatChannelMember)
    existing = await db.execute(
        select(ChatChannel)
        .join(my_member, ChatChannel.id == my_member.channel_id)
        .join(friend_member, ChatChannel.id == friend_member.channel_id)
        .where(
            ChatChannel.type == "dm",
            my_member.user_id == user_id,
            friend_member.user_id == friend_id,
        )
    )
    dm_channel = existing.scalar_one_or_none()
    if dm_channel:
        return dm_channel

    # Create new DM channel
    channel = ChatChannel(type="dm", name=None, created_by=user_id)
    db.add(channel)
    await db.flush()

    db.add(ChatChannelMember(
        channel_id=channel.id, user_id=user_id, role="owner",
    ))
    db.add(ChatChannelMember(
        channel_id=channel.id, user_id=friend_id, role="owner",
    ))
    await db.commit()
    await db.refresh(channel)
    return channel


async def create_group(
    db: AsyncSession, user_id: int, name: str, member_ids: list[int]
) -> ChatChannel:
    """Create a group chat. All members must be friends of the creator."""
    if not name or not name.strip():
        raise ValueError("Group name is required")

    # Validate all members are friends
    for mid in member_ids:
        if mid == user_id:
            continue
        friendship = await db.execute(
            select(Friendship.id).where(
                Friendship.user_id == user_id,
                Friendship.friend_id == mid,
            )
        )
        if friendship.scalar_one_or_none() is None:
            raise ValueError(f"User {mid} is not your friend")

    channel = ChatChannel(type="group", name=name.strip(), created_by=user_id)
    db.add(channel)
    await db.flush()

    # Add creator as owner
    db.add(ChatChannelMember(
        channel_id=channel.id, user_id=user_id, role="owner",
    ))
    # Add members
    for mid in member_ids:
        if mid == user_id:
            continue
        db.add(ChatChannelMember(
            channel_id=channel.id, user_id=mid, role="member",
        ))

    await db.commit()
    await db.refresh(channel)
    return channel


async def create_channel(
    db: AsyncSession, user_id: int, name: str
) -> ChatChannel:
    """Create a named channel. Creator becomes owner."""
    if not name or not name.strip():
        raise ValueError("Channel name is required")

    channel = ChatChannel(type="channel", name=name.strip(), created_by=user_id)
    db.add(channel)
    await db.flush()

    db.add(ChatChannelMember(
        channel_id=channel.id, user_id=user_id, role="owner",
    ))
    await db.commit()
    await db.refresh(channel)
    return channel


# ----- Channel Queries -----

async def get_user_channels(db: AsyncSession, user_id: int) -> list[dict]:
    """Get all channels the user belongs to, with last message and unread count.

    Uses batch queries to avoid N+1 pattern.
    """
    # Get all channel memberships
    memberships = await db.execute(
        select(ChatChannelMember, ChatChannel)
        .join(ChatChannel, ChatChannelMember.channel_id == ChatChannel.id)
        .where(ChatChannelMember.user_id == user_id)
        .order_by(ChatChannel.updated_at.desc())
    )
    rows = memberships.all()

    if not rows:
        return []

    channel_ids = [channel.id for _, channel in rows]

    # Batch: member counts per channel
    member_counts_q = await db.execute(
        select(
            ChatChannelMember.channel_id,
            func.count(ChatChannelMember.id)
        ).where(
            ChatChannelMember.channel_id.in_(channel_ids)
        ).group_by(ChatChannelMember.channel_id)
    )
    member_counts = dict(member_counts_q.all())

    # Batch: DM partner names (for DM channels only)
    dm_channel_ids = [ch.id for _, ch in rows if ch.type == "dm"]
    dm_names: dict[int, str] = {}
    if dm_channel_ids:
        dm_partners_q = await db.execute(
            select(ChatChannelMember.channel_id, User.display_name)
            .join(User, ChatChannelMember.user_id == User.id)
            .where(
                ChatChannelMember.channel_id.in_(dm_channel_ids),
                ChatChannelMember.user_id != user_id,
            )
        )
        for ch_id, name in dm_partners_q.all():
            dm_names[ch_id] = name

    # Batch: last message per channel (latest message ID per channel)
    latest_msg_ids_q = await db.execute(
        select(
            ChatMessage.channel_id,
            func.max(ChatMessage.id).label("max_id"),
        ).where(
            ChatMessage.channel_id.in_(channel_ids),
            ChatMessage.deleted_at.is_(None),
        ).group_by(ChatMessage.channel_id)
    )
    latest_msg_map = {row[0]: row[1] for row in latest_msg_ids_q.all()}

    last_messages: dict[int, dict] = {}
    if latest_msg_map:
        msg_ids = list(latest_msg_map.values())
        msgs_q = await db.execute(
            select(ChatMessage, User)
            .join(User, ChatMessage.sender_id == User.id)
            .where(ChatMessage.id.in_(msg_ids))
        )
        for msg, sender in msgs_q.all():
            last_messages[msg.channel_id] = {
                "id": msg.id,
                "sender_id": msg.sender_id,
                "sender_name": sender.display_name,
                "content": msg.content[:100] if msg.content else "",
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }

    # Batch: unread counts — single query using LEFT JOIN with per-channel filter
    unread_q = await db.execute(
        select(
            ChatChannelMember.channel_id,
            func.count(ChatMessage.id),
        )
        .outerjoin(
            ChatMessage,
            (ChatMessage.channel_id == ChatChannelMember.channel_id)
            & (ChatMessage.deleted_at.is_(None))
            & (
                (ChatChannelMember.last_read_at.is_(None))
                | (ChatMessage.created_at > ChatChannelMember.last_read_at)
            ),
        )
        .where(
            ChatChannelMember.user_id == user_id,
            ChatChannelMember.channel_id.in_(channel_ids),
        )
        .group_by(ChatChannelMember.channel_id)
    )
    unread_counts = dict(unread_q.all())

    channels = []
    for membership, channel in rows:
        channels.append({
            "id": channel.id,
            "type": channel.type,
            "name": dm_names.get(channel.id) if channel.type == "dm" else channel.name,
            "member_count": member_counts.get(channel.id, 0),
            "unread_count": unread_counts.get(channel.id, 0),
            "last_message": last_messages.get(channel.id),
            "my_role": membership.role,
            "updated_at": channel.updated_at.isoformat() if channel.updated_at else None,
        })

    return channels


# ----- Messages -----

async def get_messages(
    db: AsyncSession, channel_id: int, user_id: int,
    before_id: int | None = None, limit: int = 50
) -> list[dict]:
    """Get paginated messages for a channel. Validates membership."""
    await _validate_membership(db, channel_id, user_id)

    query = (
        select(ChatMessage, User)
        .join(User, ChatMessage.sender_id == User.id)
        .where(ChatMessage.channel_id == channel_id)
    )
    if before_id is not None:
        query = query.where(ChatMessage.id < before_id)
    query = query.order_by(ChatMessage.created_at.desc()).limit(min(limit, 100))

    result = await db.execute(query)
    rows = list(reversed(result.all()))  # reverse to chronological order

    return await _batch_build_message_dicts(db, rows)


async def send_message(
    db: AsyncSession, channel_id: int, user_id: int, content: str,
    reply_to_id: int | None = None, media_url: str | None = None,
) -> dict:
    """Send a message to a channel. Validates membership and friends-only for DMs."""
    content = content.strip()
    if not content and not media_url:
        raise ValueError("Message cannot be empty")
    if len(content) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Message exceeds {MAX_MESSAGE_LENGTH} character limit")

    await _validate_membership(db, channel_id, user_id)

    # For DMs, verify still friends
    channel = await db.get(ChatChannel, channel_id)
    if channel and channel.type == "dm":
        other_member = await db.execute(
            select(ChatChannelMember.user_id).where(
                ChatChannelMember.channel_id == channel_id,
                ChatChannelMember.user_id != user_id,
            )
        )
        other_id = other_member.scalar_one_or_none()
        if other_id:
            friendship = await db.execute(
                select(Friendship.id).where(
                    Friendship.user_id == user_id,
                    Friendship.friend_id == other_id,
                )
            )
            if friendship.scalar_one_or_none() is None:
                raise ValueError("You can only message accepted friends")

    # Validate reply_to_id if provided
    if reply_to_id is not None:
        reply_msg = await db.get(ChatMessage, reply_to_id)
        if not reply_msg or reply_msg.channel_id != channel_id:
            raise ValueError("Invalid reply target")

    # Validate media_url — only allow Giphy URLs
    if media_url:
        if not media_url.startswith("https://media") or "giphy.com/" not in media_url:
            raise ValueError("Only Giphy URLs are allowed for media")
        if len(media_url) > 500:
            raise ValueError("Media URL too long")

    msg = ChatMessage(
        channel_id=channel_id, sender_id=user_id,
        content=content or "", media_url=media_url,
        reply_to_id=reply_to_id,
    )
    db.add(msg)

    # Touch channel updated_at
    if channel:
        channel.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(msg)

    # Get sender display name
    sender = await db.get(User, user_id)
    sender_name = sender.display_name if sender else f"User {user_id}"

    return await _build_message_dict(db, msg, sender_name)


async def edit_message(
    db: AsyncSession, message_id: int, user_id: int, new_content: str
) -> dict:
    """Edit a message. Only the sender can edit their own messages."""
    new_content = new_content.strip()
    if not new_content:
        raise ValueError("Message cannot be empty")
    if len(new_content) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Message exceeds {MAX_MESSAGE_LENGTH} character limit")

    msg = await db.get(ChatMessage, message_id)
    if not msg:
        raise ValueError("Message not found")
    if msg.sender_id != user_id:
        raise ValueError("You can only edit your own messages")
    if msg.deleted_at is not None:
        raise ValueError("Cannot edit a deleted message")

    msg.content = new_content
    msg.edited_at = datetime.utcnow()
    await db.commit()
    await db.refresh(msg)

    sender = await db.get(User, user_id)
    sender_name = sender.display_name if sender else f"User {user_id}"

    return await _build_message_dict(db, msg, sender_name)


async def delete_message(
    db: AsyncSession, message_id: int, user_id: int
) -> dict:
    """Soft-delete a message. Sender can delete own; admins/owners can delete any in channel."""
    msg = await db.get(ChatMessage, message_id)
    if not msg:
        raise ValueError("Message not found")
    if msg.deleted_at is not None:
        raise ValueError("Message already deleted")

    if msg.sender_id != user_id:
        # Check if user is admin/owner of the channel
        member = await _validate_membership(db, msg.channel_id, user_id)
        if member.role not in ("owner", "admin"):
            raise ValueError("You can only delete your own messages")

    msg.deleted_at = datetime.utcnow()
    await db.commit()

    return {"id": msg.id, "channel_id": msg.channel_id}


# ----- Read Tracking -----

async def mark_read(db: AsyncSession, channel_id: int, user_id: int) -> None:
    """Mark all messages in a channel as read for this user."""
    member = await _validate_membership(db, channel_id, user_id)
    member.last_read_at = datetime.utcnow()
    await db.commit()


# ----- Membership Management -----

async def add_member(
    db: AsyncSession, channel_id: int, user_id: int, target_id: int
) -> dict:
    """Add a member to a group/channel. Must be admin/owner. Target must be friend of adder."""
    channel = await db.get(ChatChannel, channel_id)
    if not channel:
        raise ValueError("Channel not found")
    if channel.type == "dm":
        raise ValueError("Cannot add members to a DM")

    # Check requester is admin/owner
    member = await _validate_membership(db, channel_id, user_id)
    if member.role not in ("owner", "admin"):
        raise ValueError("Only admins and owners can add members")

    # Check target is friend of adder
    friendship = await db.execute(
        select(Friendship.id).where(
            Friendship.user_id == user_id,
            Friendship.friend_id == target_id,
        )
    )
    if friendship.scalar_one_or_none() is None:
        raise ValueError("You can only add friends to the chat")

    # Check not already a member
    existing = await db.execute(
        select(ChatChannelMember.id).where(
            ChatChannelMember.channel_id == channel_id,
            ChatChannelMember.user_id == target_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("User is already a member")

    db.add(ChatChannelMember(
        channel_id=channel_id, user_id=target_id, role="member",
    ))
    await db.commit()

    target_user = await db.get(User, target_id)
    return {
        "user_id": target_id,
        "display_name": target_user.display_name if target_user else f"User {target_id}",
    }


async def remove_member(
    db: AsyncSession, channel_id: int, user_id: int, target_id: int
) -> None:
    """Remove a member from a group/channel. Admin/owner can remove others. Anyone can leave."""
    from sqlalchemy import delete

    channel = await db.get(ChatChannel, channel_id)
    if not channel:
        raise ValueError("Channel not found")
    if channel.type == "dm":
        raise ValueError("Cannot remove members from a DM")

    if user_id == target_id:
        # Self-leave
        await db.execute(
            delete(ChatChannelMember).where(
                ChatChannelMember.channel_id == channel_id,
                ChatChannelMember.user_id == user_id,
            )
        )
        await db.commit()
        return

    # Check requester is admin/owner
    member = await _validate_membership(db, channel_id, user_id)
    if member.role not in ("owner", "admin"):
        raise ValueError("Only admins and owners can remove members")

    await db.execute(
        delete(ChatChannelMember).where(
            ChatChannelMember.channel_id == channel_id,
            ChatChannelMember.user_id == target_id,
        )
    )
    await db.commit()


async def get_channel_member_ids(db: AsyncSession, channel_id: int) -> list[int]:
    """Get all member user IDs for a channel."""
    result = await db.execute(
        select(ChatChannelMember.user_id).where(
            ChatChannelMember.channel_id == channel_id
        )
    )
    return [row[0] for row in result.all()]


async def get_channel_member_ids_excluding_blockers(
    db: AsyncSession, channel_id: int, sender_id: int
) -> list[int]:
    """Get member IDs for a channel, excluding members who have blocked the sender.

    Used for message delivery: members who blocked the sender won't receive
    their messages in group channels (W5 — blocked user filtering).
    DMs already enforce friendship; this handles group/channel contexts.
    """
    # Subquery: user IDs that have blocked the sender
    blocker_ids = select(BlockedUser.blocker_id).where(
        BlockedUser.blocked_id == sender_id
    ).scalar_subquery()

    result = await db.execute(
        select(ChatChannelMember.user_id).where(
            ChatChannelMember.channel_id == channel_id,
            ChatChannelMember.user_id.not_in(blocker_ids),
        )
    )
    return [row[0] for row in result.all()]


async def get_channel_members(db: AsyncSession, channel_id: int) -> list[dict]:
    """Get all members with display names for a channel."""
    result = await db.execute(
        select(ChatChannelMember, User)
        .join(User, ChatChannelMember.user_id == User.id)
        .where(ChatChannelMember.channel_id == channel_id)
        .order_by(User.display_name)
    )
    return [
        {
            "user_id": member.user_id,
            "display_name": user.display_name,
            "role": member.role,
            "joined_at": member.joined_at.isoformat() if member.joined_at else None,
        }
        for member, user in result.all()
    ]


async def rename_channel(
    db: AsyncSession, channel_id: int, user_id: int, new_name: str
) -> None:
    """Rename a group/channel. Only owner/admin can rename."""
    channel = await db.get(ChatChannel, channel_id)
    if not channel:
        raise ValueError("Channel not found")
    if channel.type == "dm":
        raise ValueError("Cannot rename a DM")

    member = await _validate_membership(db, channel_id, user_id)
    if member.role not in ("owner", "admin"):
        raise ValueError("Only admins and owners can rename")

    new_name = new_name.strip()
    if not new_name:
        raise ValueError("Name cannot be empty")

    channel.name = new_name
    channel.updated_at = datetime.utcnow()
    await db.commit()


async def delete_channel(db: AsyncSession, channel_id: int, user_id: int) -> None:
    """Delete a group/channel entirely. Only the owner can delete."""
    channel = await db.get(ChatChannel, channel_id)
    if not channel:
        raise ValueError("Channel not found")
    if channel.type == "dm":
        raise ValueError("Cannot delete a DM")

    member = await _validate_membership(db, channel_id, user_id)
    if member.role != "owner":
        raise ValueError("Only the owner can delete a group")

    await db.delete(channel)  # cascades to members and messages
    await db.commit()


async def update_member_role(
    db: AsyncSession, channel_id: int, user_id: int, target_id: int, new_role: str
) -> dict:
    """Promote or demote a channel member. Only the owner can change roles."""
    if new_role not in ("admin", "member"):
        raise ValueError("Role must be 'admin' or 'member'")

    channel = await db.get(ChatChannel, channel_id)
    if not channel:
        raise ValueError("Channel not found")
    if channel.type == "dm":
        raise ValueError("Cannot change roles in a DM")

    # Only owner can change roles
    req_member = await _validate_membership(db, channel_id, user_id)
    if req_member.role != "owner":
        raise ValueError("Only the owner can change member roles")

    if target_id == user_id:
        raise ValueError("Cannot change your own role")

    # Find target membership
    target_q = await db.execute(
        select(ChatChannelMember).where(
            ChatChannelMember.channel_id == channel_id,
            ChatChannelMember.user_id == target_id,
        )
    )
    target_member = target_q.scalar_one_or_none()
    if not target_member:
        raise ValueError("User is not a member of this channel")

    target_member.role = new_role
    await db.commit()

    target_user = await db.get(User, target_id)
    return {
        "user_id": target_id,
        "display_name": target_user.display_name if target_user else f"User {target_id}",
        "role": new_role,
    }


# ----- Unread Counts -----

async def get_unread_counts(db: AsyncSession, user_id: int) -> dict[int, int]:
    """Get unread message counts for all channels the user belongs to.

    Uses a single joined query instead of per-channel COUNT queries.
    """
    result = await db.execute(
        select(
            ChatChannelMember.channel_id,
            func.count(ChatMessage.id),
        )
        .outerjoin(
            ChatMessage,
            (ChatMessage.channel_id == ChatChannelMember.channel_id)
            & (ChatMessage.deleted_at.is_(None))
            & (
                (ChatChannelMember.last_read_at.is_(None))
                | (ChatMessage.created_at > ChatChannelMember.last_read_at)
            ),
        )
        .where(ChatChannelMember.user_id == user_id)
        .group_by(ChatChannelMember.channel_id)
    )
    return {ch_id: count for ch_id, count in result.all() if count > 0}


# ----- Reactions -----

async def toggle_reaction(
    db: AsyncSession, message_id: int, user_id: int, emoji: str
) -> dict:
    """Toggle an emoji reaction on a message. Returns action taken and updated reactions."""
    if emoji not in ALLOWED_EMOJIS:
        raise ValueError("Invalid emoji")

    msg = await db.get(ChatMessage, message_id)
    if not msg:
        raise ValueError("Message not found")
    if msg.deleted_at is not None:
        raise ValueError("Cannot react to a deleted message")

    await _validate_membership(db, msg.channel_id, user_id)

    # Check if already reacted with this emoji
    existing = await db.execute(
        select(ChatMessageReaction).where(
            ChatMessageReaction.message_id == message_id,
            ChatMessageReaction.user_id == user_id,
            ChatMessageReaction.emoji == emoji,
        )
    )
    reaction = existing.scalar_one_or_none()

    if reaction:
        await db.delete(reaction)
        action = "removed"
    else:
        db.add(ChatMessageReaction(
            message_id=message_id, user_id=user_id, emoji=emoji
        ))
        action = "added"

    await db.commit()

    return {
        "message_id": message_id,
        "channel_id": msg.channel_id,
        "action": action,
        "emoji": emoji,
        "user_id": user_id,
        "reactions": await _aggregate_reactions(db, message_id),
    }


# ----- Pinned Messages -----

async def toggle_pin(
    db: AsyncSession, message_id: int, user_id: int
) -> dict:
    """Toggle pin on a message. Only admin/owner can pin."""
    msg = await db.get(ChatMessage, message_id)
    if not msg:
        raise ValueError("Message not found")
    if msg.deleted_at is not None:
        raise ValueError("Cannot pin a deleted message")

    # Check requester is admin/owner
    member = await _validate_membership(db, msg.channel_id, user_id)
    if member.role not in ("owner", "admin"):
        raise ValueError("Only admins and owners can pin messages")

    msg.is_pinned = not msg.is_pinned
    await db.commit()

    return {
        "message_id": message_id,
        "channel_id": msg.channel_id,
        "is_pinned": msg.is_pinned,
    }


async def get_pinned_messages(
    db: AsyncSession, channel_id: int, user_id: int
) -> list[dict]:
    """Get all pinned messages in a channel."""
    await _validate_membership(db, channel_id, user_id)

    result = await db.execute(
        select(ChatMessage, User)
        .join(User, ChatMessage.sender_id == User.id)
        .where(
            ChatMessage.channel_id == channel_id,
            ChatMessage.is_pinned.is_(True),
            ChatMessage.deleted_at.is_(None),
        )
        .order_by(ChatMessage.created_at.desc())
    )
    rows = result.all()
    return await _batch_build_message_dicts(db, rows)


# ----- Search -----

async def search_messages(
    db: AsyncSession, user_id: int, query: str,
    channel_id: int | None = None, limit: int = 30
) -> list[dict]:
    """Search messages across user's channels (or a specific channel)."""
    query_text = query.strip()
    if not query_text or len(query_text) < 2:
        raise ValueError("Search query must be at least 2 characters")

    # Escape ILIKE wildcards in user input
    query_text = query_text.replace('%', '\\%').replace('_', '\\_')

    # Get user's channel IDs
    if channel_id:
        await _validate_membership(db, channel_id, user_id)
        channel_ids = [channel_id]
    else:
        memberships = await db.execute(
            select(ChatChannelMember.channel_id).where(
                ChatChannelMember.user_id == user_id
            )
        )
        channel_ids = [row[0] for row in memberships.all()]

    if not channel_ids:
        return []

    # Search using ILIKE (works for both PostgreSQL and SQLite)
    stmt = (
        select(ChatMessage, User)
        .join(User, ChatMessage.sender_id == User.id)
        .where(
            ChatMessage.channel_id.in_(channel_ids),
            ChatMessage.deleted_at.is_(None),
            ChatMessage.content.ilike(f"%{query_text}%"),
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(min(limit, 50))
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Batch-build message dicts (reactions + replies in bulk)
    messages = await _batch_build_message_dicts(db, rows)

    # Batch-load channel names for cross-channel search results
    unique_ch_ids = list({msg.channel_id for msg, _ in rows})
    if unique_ch_ids:
        channels_q = await db.execute(
            select(ChatChannel).where(ChatChannel.id.in_(unique_ch_ids))
        )
        ch_map = {ch.id: ch for ch in channels_q.scalars().all()}
    else:
        ch_map = {}

    for msg_dict, (msg, _) in zip(messages, rows):
        ch = ch_map.get(msg.channel_id)
        msg_dict["channel_name"] = ch.name if ch else None
        msg_dict["channel_type"] = ch.type if ch else None

    return messages
