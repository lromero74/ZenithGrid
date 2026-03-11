"""
Chat service — business logic for DMs, group chats, and channels.

Handles channel creation, membership, messages, read tracking, and retention.
All queries are scoped by user_id to ensure data isolation.
"""

import logging
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.social import (
    BlockedUser, ChatChannel, ChatChannelMember, ChatMessage,
    ChatMessageReaction, Friendship,
)

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 2000

# Common emojis allowed for reactions
ALLOWED_EMOJIS = {
    "👍", "👎", "❤️", "😂", "😮", "😢", "😡", "🎉",
    "🔥", "👀", "💯", "🙏", "👏", "🤔", "😍", "🎮",
}


async def _build_message_dict(
    db: AsyncSession, msg: ChatMessage, sender_name: str
) -> dict:
    """Build the full message response dict including reactions and reply-to."""
    result = {
        "id": msg.id,
        "channel_id": msg.channel_id,
        "sender_id": msg.sender_id,
        "sender_name": sender_name,
        "content": msg.content if msg.deleted_at is None else None,
        "is_deleted": msg.deleted_at is not None,
        "edited_at": msg.edited_at.isoformat() if msg.edited_at else None,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "is_pinned": bool(msg.is_pinned),
        "reply_to": None,
        "reactions": [],
    }

    # Load reply-to preview
    if msg.reply_to_id and msg.deleted_at is None:
        reply_msg = await db.get(ChatMessage, msg.reply_to_id)
        if reply_msg:
            reply_sender = await db.get(User, reply_msg.sender_id)
            result["reply_to"] = {
                "id": reply_msg.id,
                "sender_name": reply_sender.display_name if reply_sender else "Unknown",
                "content": (reply_msg.content[:100] if reply_msg.deleted_at is None
                            else None),
                "is_deleted": reply_msg.deleted_at is not None,
            }

    # Load reactions (aggregated)
    if msg.deleted_at is None:
        reactions_q = await db.execute(
            select(ChatMessageReaction).where(
                ChatMessageReaction.message_id == msg.id
            )
        )
        all_reactions = reactions_q.scalars().all()
        emoji_map: dict[str, list[int]] = {}
        for r in all_reactions:
            emoji_map.setdefault(r.emoji, []).append(r.user_id)
        result["reactions"] = [
            {"emoji": emoji, "count": len(uids), "user_ids": uids}
            for emoji, uids in emoji_map.items()
        ]

    return result


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

    # Look for existing DM between these two users
    existing = await db.execute(
        select(ChatChannel).where(
            ChatChannel.type == "dm",
        ).join(
            ChatChannelMember, ChatChannel.id == ChatChannelMember.channel_id
        ).where(
            ChatChannelMember.user_id == user_id,
        )
    )
    my_dm_channels = existing.scalars().all()

    for ch in my_dm_channels:
        # Check if friend is also a member
        member_check = await db.execute(
            select(ChatChannelMember.id).where(
                ChatChannelMember.channel_id == ch.id,
                ChatChannelMember.user_id == friend_id,
            )
        )
        if member_check.scalar_one_or_none() is not None:
            return ch

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


async def get_user_channels(db: AsyncSession, user_id: int) -> list[dict]:
    """Get all channels the user belongs to, with last message and unread count."""
    # Get all channel memberships
    memberships = await db.execute(
        select(ChatChannelMember, ChatChannel)
        .join(ChatChannel, ChatChannelMember.channel_id == ChatChannel.id)
        .where(ChatChannelMember.user_id == user_id)
        .order_by(ChatChannel.updated_at.desc())
    )
    rows = memberships.all()

    channels = []
    for membership, channel in rows:
        # Get last message
        last_msg_q = await db.execute(
            select(ChatMessage, User)
            .join(User, ChatMessage.sender_id == User.id)
            .where(
                ChatMessage.channel_id == channel.id,
                ChatMessage.deleted_at.is_(None),
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        )
        last_msg_row = last_msg_q.first()

        # Count unread
        unread_filter = [
            ChatMessage.channel_id == channel.id,
            ChatMessage.deleted_at.is_(None),
        ]
        if membership.last_read_at is not None:
            unread_filter.append(ChatMessage.created_at > membership.last_read_at)
        unread_q = await db.execute(
            select(func.count(ChatMessage.id)).where(*unread_filter)
        )
        unread_count = unread_q.scalar() or 0

        # For DMs, resolve the other member's name
        dm_name = None
        if channel.type == "dm":
            other_member = await db.execute(
                select(User.display_name)
                .join(ChatChannelMember, ChatChannelMember.user_id == User.id)
                .where(
                    ChatChannelMember.channel_id == channel.id,
                    ChatChannelMember.user_id != user_id,
                )
            )
            dm_name = other_member.scalar_one_or_none()

        # Get member count
        member_count_q = await db.execute(
            select(func.count(ChatChannelMember.id)).where(
                ChatChannelMember.channel_id == channel.id
            )
        )
        member_count = member_count_q.scalar() or 0

        last_message = None
        if last_msg_row:
            msg, sender = last_msg_row
            last_message = {
                "id": msg.id,
                "sender_id": msg.sender_id,
                "sender_name": sender.display_name,
                "content": msg.content[:100],  # preview
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }

        channels.append({
            "id": channel.id,
            "type": channel.type,
            "name": dm_name if channel.type == "dm" else channel.name,
            "member_count": member_count,
            "unread_count": unread_count,
            "last_message": last_message,
            "my_role": membership.role,
            "updated_at": channel.updated_at.isoformat() if channel.updated_at else None,
        })

    return channels


async def get_messages(
    db: AsyncSession, channel_id: int, user_id: int,
    before_id: int | None = None, limit: int = 50
) -> list[dict]:
    """Get paginated messages for a channel. Validates membership."""
    # Validate membership
    membership = await db.execute(
        select(ChatChannelMember.id).where(
            ChatChannelMember.channel_id == channel_id,
            ChatChannelMember.user_id == user_id,
        )
    )
    if membership.scalar_one_or_none() is None:
        raise ValueError("You are not a member of this channel")

    query = (
        select(ChatMessage, User)
        .join(User, ChatMessage.sender_id == User.id)
        .where(ChatMessage.channel_id == channel_id)
    )
    if before_id is not None:
        query = query.where(ChatMessage.id < before_id)
    query = query.order_by(ChatMessage.created_at.desc()).limit(min(limit, 100))

    result = await db.execute(query)
    rows = result.all()

    messages = []
    for msg, sender in reversed(rows):  # reverse to get chronological order
        messages.append(await _build_message_dict(db, msg, sender.display_name))

    return messages


async def send_message(
    db: AsyncSession, channel_id: int, user_id: int, content: str,
    reply_to_id: int | None = None,
) -> dict:
    """Send a message to a channel. Validates membership and friends-only for DMs."""
    content = content.strip()
    if not content:
        raise ValueError("Message cannot be empty")
    if len(content) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Message exceeds {MAX_MESSAGE_LENGTH} character limit")

    # Validate membership
    membership = await db.execute(
        select(ChatChannelMember.id).where(
            ChatChannelMember.channel_id == channel_id,
            ChatChannelMember.user_id == user_id,
        )
    )
    if membership.scalar_one_or_none() is None:
        raise ValueError("You are not a member of this channel")

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

    msg = ChatMessage(
        channel_id=channel_id, sender_id=user_id, content=content,
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
        membership = await db.execute(
            select(ChatChannelMember).where(
                ChatChannelMember.channel_id == msg.channel_id,
                ChatChannelMember.user_id == user_id,
            )
        )
        member = membership.scalar_one_or_none()
        if not member or member.role not in ("owner", "admin"):
            raise ValueError("You can only delete your own messages")

    msg.deleted_at = datetime.utcnow()
    await db.commit()

    return {"id": msg.id, "channel_id": msg.channel_id}


async def mark_read(db: AsyncSession, channel_id: int, user_id: int) -> None:
    """Mark all messages in a channel as read for this user."""
    membership = await db.execute(
        select(ChatChannelMember).where(
            ChatChannelMember.channel_id == channel_id,
            ChatChannelMember.user_id == user_id,
        )
    )
    member = membership.scalar_one_or_none()
    if not member:
        raise ValueError("You are not a member of this channel")

    member.last_read_at = datetime.utcnow()
    await db.commit()


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
    membership = await db.execute(
        select(ChatChannelMember).where(
            ChatChannelMember.channel_id == channel_id,
            ChatChannelMember.user_id == user_id,
        )
    )
    member = membership.scalar_one_or_none()
    if not member or member.role not in ("owner", "admin"):
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
    membership = await db.execute(
        select(ChatChannelMember).where(
            ChatChannelMember.channel_id == channel_id,
            ChatChannelMember.user_id == user_id,
        )
    )
    member = membership.scalar_one_or_none()
    if not member or member.role not in ("owner", "admin"):
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

    membership = await db.execute(
        select(ChatChannelMember).where(
            ChatChannelMember.channel_id == channel_id,
            ChatChannelMember.user_id == user_id,
        )
    )
    member = membership.scalar_one_or_none()
    if not member or member.role not in ("owner", "admin"):
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

    membership = await db.execute(
        select(ChatChannelMember).where(
            ChatChannelMember.channel_id == channel_id,
            ChatChannelMember.user_id == user_id,
        )
    )
    member = membership.scalar_one_or_none()
    if not member or member.role != "owner":
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
    requester = await db.execute(
        select(ChatChannelMember).where(
            ChatChannelMember.channel_id == channel_id,
            ChatChannelMember.user_id == user_id,
        )
    )
    req_member = requester.scalar_one_or_none()
    if not req_member or req_member.role != "owner":
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


async def get_unread_counts(db: AsyncSession, user_id: int) -> dict[int, int]:
    """Get unread message counts for all channels the user belongs to."""
    memberships = await db.execute(
        select(ChatChannelMember).where(ChatChannelMember.user_id == user_id)
    )
    members = memberships.scalars().all()

    counts = {}
    for m in members:
        filters = [
            ChatMessage.channel_id == m.channel_id,
            ChatMessage.deleted_at.is_(None),
        ]
        if m.last_read_at is not None:
            filters.append(ChatMessage.created_at > m.last_read_at)
        result = await db.execute(
            select(func.count(ChatMessage.id)).where(*filters)
        )
        count = result.scalar() or 0
        if count > 0:
            counts[m.channel_id] = count

    return counts


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

    # Check membership
    membership = await db.execute(
        select(ChatChannelMember.id).where(
            ChatChannelMember.channel_id == msg.channel_id,
            ChatChannelMember.user_id == user_id,
        )
    )
    if membership.scalar_one_or_none() is None:
        raise ValueError("You are not a member of this channel")

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

    # Return updated reactions for this message
    reactions_q = await db.execute(
        select(ChatMessageReaction).where(
            ChatMessageReaction.message_id == message_id
        )
    )
    all_reactions = reactions_q.scalars().all()
    emoji_map: dict[str, list[int]] = {}
    for r in all_reactions:
        emoji_map.setdefault(r.emoji, []).append(r.user_id)

    return {
        "message_id": message_id,
        "channel_id": msg.channel_id,
        "action": action,
        "emoji": emoji,
        "user_id": user_id,
        "reactions": [
            {"emoji": e, "count": len(uids), "user_ids": uids}
            for e, uids in emoji_map.items()
        ],
    }


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
    membership = await db.execute(
        select(ChatChannelMember).where(
            ChatChannelMember.channel_id == msg.channel_id,
            ChatChannelMember.user_id == user_id,
        )
    )
    member = membership.scalar_one_or_none()
    if not member or member.role not in ("owner", "admin"):
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
    # Validate membership
    membership = await db.execute(
        select(ChatChannelMember.id).where(
            ChatChannelMember.channel_id == channel_id,
            ChatChannelMember.user_id == user_id,
        )
    )
    if membership.scalar_one_or_none() is None:
        raise ValueError("You are not a member of this channel")

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
    return [await _build_message_dict(db, msg, sender.display_name)
            for msg, sender in rows]


async def search_messages(
    db: AsyncSession, user_id: int, query: str,
    channel_id: int | None = None, limit: int = 30
) -> list[dict]:
    """Search messages across user's channels (or a specific channel)."""
    query_text = query.strip()
    if not query_text or len(query_text) < 2:
        raise ValueError("Search query must be at least 2 characters")

    # Get user's channel IDs
    if channel_id:
        # Validate membership
        membership = await db.execute(
            select(ChatChannelMember.id).where(
                ChatChannelMember.channel_id == channel_id,
                ChatChannelMember.user_id == user_id,
            )
        )
        if membership.scalar_one_or_none() is None:
            raise ValueError("You are not a member of this channel")
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

    messages = []
    for msg, sender in rows:
        msg_dict = await _build_message_dict(db, msg, sender.display_name)
        # Include channel name for cross-channel search
        channel = await db.get(ChatChannel, msg.channel_id)
        msg_dict["channel_name"] = channel.name if channel else None
        msg_dict["channel_type"] = channel.type if channel else None
        messages.append(msg_dict)

    return messages


async def cleanup_old_messages(db: AsyncSession, retention_days: int) -> int:
    """Delete messages older than retention_days. Returns count deleted. 0 days = no cleanup."""
    if retention_days <= 0:
        return 0

    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=retention_days)

    result = await db.execute(
        delete(ChatMessage).where(ChatMessage.created_at < cutoff)
    )
    await db.commit()
    return result.rowcount or 0
