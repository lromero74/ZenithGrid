"""
Tests for backend/app/services/chat_service.py

Covers channel creation (DM, group, channel), message CRUD with permission
checks, membership management, read tracking, unread counts, and retention cleanup.
"""

import pytest
from datetime import datetime, timedelta

from app.models import User
from app.models.social import (
    BlockedUser, ChatChannelMember, ChatMessage, ChatMessageReaction, Friendship,
)
from app.services import chat_service


# =============================================================================
# Helpers
# =============================================================================


async def create_user(db, email, display_name=None):
    """Create a test user."""
    user = User(
        email=email,
        hashed_password="fakehash",
        display_name=display_name or email.split("@")[0],
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def make_friends(db, user_a, user_b):
    """Create bidirectional friendship between two users."""
    db.add(Friendship(user_id=user_a.id, friend_id=user_b.id))
    db.add(Friendship(user_id=user_b.id, friend_id=user_a.id))
    await db.flush()


# =============================================================================
# DM Creation — get_or_create_dm
# =============================================================================


class TestGetOrCreateDM:
    """Tests for get_or_create_dm()"""

    @pytest.mark.asyncio
    async def test_create_dm_with_friend(self, db_session):
        """Happy path: DM channel created between two friends."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)

        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)

        assert channel is not None
        assert channel.type == "dm"
        assert channel.name is None
        assert channel.created_by == alice.id

    @pytest.mark.asyncio
    async def test_create_dm_adds_both_members(self, db_session):
        """Both users are added as owners of the DM channel."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)

        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        member_ids = await chat_service.get_channel_member_ids(db_session, channel.id)

        assert set(member_ids) == {alice.id, bob.id}

    @pytest.mark.asyncio
    async def test_get_existing_dm_returns_same_channel(self, db_session):
        """Calling get_or_create_dm twice returns the same channel (idempotent)."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)

        ch1 = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        ch2 = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)

        assert ch1.id == ch2.id

    @pytest.mark.asyncio
    async def test_create_dm_without_friendship_raises(self, db_session):
        """DM creation requires an existing friendship."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")

        with pytest.raises(ValueError, match="accepted friends"):
            await chat_service.get_or_create_dm(db_session, alice.id, bob.id)

    @pytest.mark.asyncio
    async def test_create_dm_when_blocked_raises(self, db_session):
        """DM creation fails when the target user has blocked the requester."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)

        # Bob blocks Alice
        db_session.add(BlockedUser(blocker_id=bob.id, blocked_id=alice.id))
        await db_session.flush()

        with pytest.raises(ValueError, match="Cannot message this user"):
            await chat_service.get_or_create_dm(db_session, alice.id, bob.id)


# =============================================================================
# Group Creation — create_group
# =============================================================================


class TestCreateGroup:
    """Tests for create_group()"""

    @pytest.mark.asyncio
    async def test_create_group_happy_path(self, db_session):
        """Happy path: group created with creator as owner and members added."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        carol = await create_user(db_session, "carol@test.com", "Carol")
        await make_friends(db_session, alice, bob)
        await make_friends(db_session, alice, carol)

        channel = await chat_service.create_group(
            db_session, alice.id, "Test Group", [bob.id, carol.id]
        )

        assert channel.type == "group"
        assert channel.name == "Test Group"
        member_ids = await chat_service.get_channel_member_ids(db_session, channel.id)
        assert set(member_ids) == {alice.id, bob.id, carol.id}

    @pytest.mark.asyncio
    async def test_create_group_creator_is_owner(self, db_session):
        """Creator has owner role, members have member role."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)

        channel = await chat_service.create_group(
            db_session, alice.id, "My Group", [bob.id]
        )
        members = await chat_service.get_channel_members(db_session, channel.id)
        roles = {m["user_id"]: m["role"] for m in members}

        assert roles[alice.id] == "owner"
        assert roles[bob.id] == "member"

    @pytest.mark.asyncio
    async def test_create_group_empty_name_raises(self, db_session):
        """Group name is required."""
        alice = await create_user(db_session, "alice@test.com", "Alice")

        with pytest.raises(ValueError, match="Group name is required"):
            await chat_service.create_group(db_session, alice.id, "", [1])

    @pytest.mark.asyncio
    async def test_create_group_whitespace_name_raises(self, db_session):
        """Whitespace-only name is treated as empty."""
        alice = await create_user(db_session, "alice@test.com", "Alice")

        with pytest.raises(ValueError, match="Group name is required"):
            await chat_service.create_group(db_session, alice.id, "   ", [1])

    @pytest.mark.asyncio
    async def test_create_group_no_members_creates_group_of_one(self, db_session):
        """A group with no additional members creates a group of one (just the creator)."""
        alice = await create_user(db_session, "alice@test.com", "Alice")

        channel = await chat_service.create_group(db_session, alice.id, "Solo Group", [])
        assert channel.type == "group"
        assert channel.name == "Solo Group"

        members = await chat_service.get_channel_members(db_session, channel.id)
        assert len(members) == 1
        assert members[0]["user_id"] == alice.id
        assert members[0]["role"] == "owner"

    @pytest.mark.asyncio
    async def test_create_group_non_friend_member_raises(self, db_session):
        """All members must be friends of the creator."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        # No friendship

        with pytest.raises(ValueError, match="not your friend"):
            await chat_service.create_group(
                db_session, alice.id, "Group", [bob.id]
            )

    @pytest.mark.asyncio
    async def test_create_group_name_is_stripped(self, db_session):
        """Group name should be trimmed of whitespace."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)

        channel = await chat_service.create_group(
            db_session, alice.id, "  Padded Name  ", [bob.id]
        )
        assert channel.name == "Padded Name"

    @pytest.mark.asyncio
    async def test_create_group_skips_creator_in_member_list(self, db_session):
        """If creator ID appears in member_ids, it should not create duplicate membership."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)

        channel = await chat_service.create_group(
            db_session, alice.id, "Group", [alice.id, bob.id]
        )
        member_ids = await chat_service.get_channel_member_ids(db_session, channel.id)
        assert len(member_ids) == 2
        assert set(member_ids) == {alice.id, bob.id}


# =============================================================================
# Channel Creation — create_channel
# =============================================================================


class TestCreateChannel:
    """Tests for create_channel()"""

    @pytest.mark.asyncio
    async def test_create_channel_happy_path(self, db_session):
        """Happy path: channel created with creator as owner."""
        alice = await create_user(db_session, "alice@test.com", "Alice")

        channel = await chat_service.create_channel(db_session, alice.id, "General")

        assert channel.type == "channel"
        assert channel.name == "General"
        assert channel.created_by == alice.id

    @pytest.mark.asyncio
    async def test_create_channel_empty_name_raises(self, db_session):
        """Channel name is required."""
        alice = await create_user(db_session, "alice@test.com", "Alice")

        with pytest.raises(ValueError, match="Channel name is required"):
            await chat_service.create_channel(db_session, alice.id, "")


# =============================================================================
# Send Message — send_message
# =============================================================================


class TestSendMessage:
    """Tests for send_message()"""

    @pytest.mark.asyncio
    async def test_send_message_happy_path(self, db_session):
        """Happy path: message sent and returned with correct fields."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)

        result = await chat_service.send_message(
            db_session, channel.id, alice.id, "Hello Bob!"
        )

        assert result["content"] == "Hello Bob!"
        assert result["sender_id"] == alice.id
        assert result["sender_name"] == "Alice"
        assert result["channel_id"] == channel.id
        assert result["is_deleted"] is False

    @pytest.mark.asyncio
    async def test_send_message_strips_whitespace(self, db_session):
        """Message content is stripped of leading/trailing whitespace."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")

        result = await chat_service.send_message(
            db_session, channel.id, alice.id, "  hello  "
        )
        assert result["content"] == "hello"

    @pytest.mark.asyncio
    async def test_send_empty_message_raises(self, db_session):
        """Empty messages are rejected."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")

        with pytest.raises(ValueError, match="cannot be empty"):
            await chat_service.send_message(db_session, channel.id, alice.id, "")

    @pytest.mark.asyncio
    async def test_send_whitespace_only_message_raises(self, db_session):
        """Whitespace-only messages are treated as empty."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")

        with pytest.raises(ValueError, match="cannot be empty"):
            await chat_service.send_message(db_session, channel.id, alice.id, "   ")

    @pytest.mark.asyncio
    async def test_send_message_exceeds_limit_raises(self, db_session):
        """Messages over 2000 characters are rejected."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")

        long_msg = "x" * 2001
        with pytest.raises(ValueError, match="2000 character limit"):
            await chat_service.send_message(
                db_session, channel.id, alice.id, long_msg
            )

    @pytest.mark.asyncio
    async def test_send_message_exactly_at_limit_succeeds(self, db_session):
        """Message exactly at 2000 characters should succeed."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")

        msg_2000 = "x" * 2000
        result = await chat_service.send_message(
            db_session, channel.id, alice.id, msg_2000
        )
        assert len(result["content"]) == 2000

    @pytest.mark.asyncio
    async def test_send_message_non_member_raises(self, db_session):
        """Non-members cannot send messages."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")

        with pytest.raises(ValueError, match="not a member"):
            await chat_service.send_message(
                db_session, channel.id, bob.id, "Intruder!"
            )

    @pytest.mark.asyncio
    async def test_send_dm_after_unfriend_raises(self, db_session):
        """Sending a DM after friendship is removed should fail."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)

        # Remove friendship (alice -> bob direction)
        from sqlalchemy import delete
        await db_session.execute(
            delete(Friendship).where(
                Friendship.user_id == alice.id,
                Friendship.friend_id == bob.id,
            )
        )
        await db_session.flush()

        with pytest.raises(ValueError, match="accepted friends"):
            await chat_service.send_message(
                db_session, channel.id, alice.id, "Are you there?"
            )


# =============================================================================
# Edit Message — edit_message
# =============================================================================


class TestEditMessage:
    """Tests for edit_message()"""

    @pytest.mark.asyncio
    async def test_edit_own_message(self, db_session):
        """Happy path: sender can edit their own message."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")
        msg = await chat_service.send_message(
            db_session, channel.id, alice.id, "original"
        )

        result = await chat_service.edit_message(
            db_session, msg["id"], alice.id, "edited"
        )

        assert result["content"] == "edited"
        assert result["edited_at"] is not None

    @pytest.mark.asyncio
    async def test_edit_other_user_message_raises(self, db_session):
        """Users cannot edit messages sent by others."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        msg = await chat_service.send_message(
            db_session, channel.id, alice.id, "Alice's msg"
        )

        with pytest.raises(ValueError, match="only edit your own"):
            await chat_service.edit_message(
                db_session, msg["id"], bob.id, "hacked"
            )

    @pytest.mark.asyncio
    async def test_edit_deleted_message_raises(self, db_session):
        """Deleted messages cannot be edited."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")
        msg = await chat_service.send_message(
            db_session, channel.id, alice.id, "to be deleted"
        )
        await chat_service.delete_message(db_session, msg["id"], alice.id)

        with pytest.raises(ValueError, match="Cannot edit a deleted"):
            await chat_service.edit_message(
                db_session, msg["id"], alice.id, "revived"
            )

    @pytest.mark.asyncio
    async def test_edit_nonexistent_message_raises(self, db_session):
        """Editing a non-existent message raises."""
        alice = await create_user(db_session, "alice@test.com", "Alice")

        with pytest.raises(ValueError, match="Message not found"):
            await chat_service.edit_message(db_session, 99999, alice.id, "ghost")

    @pytest.mark.asyncio
    async def test_edit_message_empty_content_raises(self, db_session):
        """Edit content cannot be empty."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")
        msg = await chat_service.send_message(
            db_session, channel.id, alice.id, "original"
        )

        with pytest.raises(ValueError, match="cannot be empty"):
            await chat_service.edit_message(db_session, msg["id"], alice.id, "")

    @pytest.mark.asyncio
    async def test_edit_message_exceeds_limit_raises(self, db_session):
        """Edit content over 2000 chars is rejected."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")
        msg = await chat_service.send_message(
            db_session, channel.id, alice.id, "original"
        )

        with pytest.raises(ValueError, match="2000 character limit"):
            await chat_service.edit_message(
                db_session, msg["id"], alice.id, "x" * 2001
            )


# =============================================================================
# Delete Message — delete_message
# =============================================================================


class TestDeleteMessage:
    """Tests for delete_message()"""

    @pytest.mark.asyncio
    async def test_delete_own_message(self, db_session):
        """Happy path: sender can delete their own message."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")
        msg = await chat_service.send_message(
            db_session, channel.id, alice.id, "delete me"
        )

        result = await chat_service.delete_message(db_session, msg["id"], alice.id)

        assert result["id"] == msg["id"]
        assert result["channel_id"] == channel.id

    @pytest.mark.asyncio
    async def test_admin_can_delete_any_message(self, db_session):
        """Admin/owner of a channel can delete any member's message."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.create_group(
            db_session, alice.id, "Group", [bob.id]
        )
        # Bob sends a message
        msg = await chat_service.send_message(
            db_session, channel.id, bob.id, "Bob's message"
        )

        # Alice (owner) deletes Bob's message
        result = await chat_service.delete_message(db_session, msg["id"], alice.id)
        assert result["id"] == msg["id"]

    @pytest.mark.asyncio
    async def test_regular_member_cannot_delete_others_message(self, db_session):
        """Regular members cannot delete messages from other users."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.create_group(
            db_session, alice.id, "Group", [bob.id]
        )
        msg = await chat_service.send_message(
            db_session, channel.id, alice.id, "Alice's message"
        )

        # Bob (member) tries to delete Alice's message
        with pytest.raises(ValueError, match="only delete your own"):
            await chat_service.delete_message(db_session, msg["id"], bob.id)

    @pytest.mark.asyncio
    async def test_delete_already_deleted_raises(self, db_session):
        """Cannot delete an already deleted message."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")
        msg = await chat_service.send_message(
            db_session, channel.id, alice.id, "delete twice"
        )
        await chat_service.delete_message(db_session, msg["id"], alice.id)

        with pytest.raises(ValueError, match="already deleted"):
            await chat_service.delete_message(db_session, msg["id"], alice.id)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_message_raises(self, db_session):
        """Deleting a non-existent message raises."""
        alice = await create_user(db_session, "alice@test.com", "Alice")

        with pytest.raises(ValueError, match="Message not found"):
            await chat_service.delete_message(db_session, 99999, alice.id)


# =============================================================================
# Get Messages — get_messages (soft delete behavior)
# =============================================================================


class TestGetMessages:
    """Tests for get_messages()"""

    @pytest.mark.asyncio
    async def test_get_messages_happy_path(self, db_session):
        """Happy path: retrieve messages from a channel."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")
        await chat_service.send_message(db_session, channel.id, alice.id, "msg1")
        await chat_service.send_message(db_session, channel.id, alice.id, "msg2")

        messages = await chat_service.get_messages(db_session, channel.id, alice.id)

        assert len(messages) == 2
        assert messages[0]["content"] == "msg1"
        assert messages[1]["content"] == "msg2"

    @pytest.mark.asyncio
    async def test_deleted_message_returns_null_content(self, db_session):
        """Soft-deleted messages show null content and is_deleted=True."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")
        msg = await chat_service.send_message(
            db_session, channel.id, alice.id, "secret"
        )
        await chat_service.delete_message(db_session, msg["id"], alice.id)

        messages = await chat_service.get_messages(db_session, channel.id, alice.id)

        assert len(messages) == 1
        assert messages[0]["content"] is None
        assert messages[0]["is_deleted"] is True

    @pytest.mark.asyncio
    async def test_get_messages_non_member_raises(self, db_session):
        """Non-members cannot retrieve messages."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")

        with pytest.raises(ValueError, match="not a member"):
            await chat_service.get_messages(db_session, channel.id, bob.id)

    @pytest.mark.asyncio
    async def test_get_messages_respects_limit(self, db_session):
        """Limit parameter restricts how many messages are returned."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")
        for i in range(5):
            await chat_service.send_message(
                db_session, channel.id, alice.id, f"msg{i}"
            )

        messages = await chat_service.get_messages(
            db_session, channel.id, alice.id, limit=3
        )
        assert len(messages) == 3

    @pytest.mark.asyncio
    async def test_get_messages_limit_capped_at_100(self, db_session):
        """Limit is capped at 100 even if higher value is requested."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")

        # Just verify it doesn't error with a high limit
        messages = await chat_service.get_messages(
            db_session, channel.id, alice.id, limit=500
        )
        assert isinstance(messages, list)


# =============================================================================
# Mark Read & Unread Counts
# =============================================================================


class TestReadTracking:
    """Tests for mark_read() and get_unread_counts()"""

    @pytest.mark.asyncio
    async def test_mark_read_updates_timestamp(self, db_session):
        """Marking a channel as read updates last_read_at."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")

        await chat_service.mark_read(db_session, channel.id, alice.id)

        # Verify the member's last_read_at is set
        from sqlalchemy import select
        result = await db_session.execute(
            select(ChatChannelMember).where(
                ChatChannelMember.channel_id == channel.id,
                ChatChannelMember.user_id == alice.id,
            )
        )
        member = result.scalar_one()
        assert member.last_read_at is not None

    @pytest.mark.asyncio
    async def test_mark_read_non_member_raises(self, db_session):
        """Non-members cannot mark read."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")

        with pytest.raises(ValueError, match="not a member"):
            await chat_service.mark_read(db_session, channel.id, bob.id)

    @pytest.mark.asyncio
    async def test_unread_count_with_no_messages(self, db_session):
        """Empty channel has zero unread count (or not in counts dict)."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        await chat_service.create_channel(db_session, alice.id, "Test")

        counts = await chat_service.get_unread_counts(db_session, alice.id)
        # Should be empty — no messages to be unread
        assert len(counts) == 0

    @pytest.mark.asyncio
    async def test_unread_count_increments_with_messages(self, db_session):
        """Unread count reflects messages sent after last_read_at."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)

        # Mark read first
        await chat_service.mark_read(db_session, channel.id, bob.id)

        # Alice sends 3 messages after Bob's last read
        for i in range(3):
            await chat_service.send_message(
                db_session, channel.id, alice.id, f"msg {i}"
            )

        counts = await chat_service.get_unread_counts(db_session, bob.id)
        assert counts.get(channel.id) == 3

    @pytest.mark.asyncio
    async def test_unread_count_resets_after_mark_read(self, db_session):
        """After marking read, unread count should be zero."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)

        await chat_service.send_message(
            db_session, channel.id, alice.id, "hello"
        )
        # Bob marks read
        await chat_service.mark_read(db_session, channel.id, bob.id)

        counts = await chat_service.get_unread_counts(db_session, bob.id)
        assert counts.get(channel.id) is None  # 0 = not in dict


# =============================================================================
# Membership — add_member / remove_member
# =============================================================================


class TestMembership:
    """Tests for add_member() and remove_member()"""

    @pytest.mark.asyncio
    async def test_add_member_happy_path(self, db_session):
        """Owner can add a friend to the group."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        carol = await create_user(db_session, "carol@test.com", "Carol")
        await make_friends(db_session, alice, bob)
        await make_friends(db_session, alice, carol)
        channel = await chat_service.create_group(
            db_session, alice.id, "Group", [bob.id]
        )

        result = await chat_service.add_member(
            db_session, channel.id, alice.id, carol.id
        )

        assert result["user_id"] == carol.id
        assert result["display_name"] == "Carol"

    @pytest.mark.asyncio
    async def test_add_member_to_dm_raises(self, db_session):
        """Cannot add members to DM channels."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        carol = await create_user(db_session, "carol@test.com", "Carol")
        await make_friends(db_session, alice, bob)
        await make_friends(db_session, alice, carol)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)

        with pytest.raises(ValueError, match="Cannot add members to a DM"):
            await chat_service.add_member(
                db_session, channel.id, alice.id, carol.id
            )

    @pytest.mark.asyncio
    async def test_add_member_by_regular_member_raises(self, db_session):
        """Regular members cannot add people."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        carol = await create_user(db_session, "carol@test.com", "Carol")
        await make_friends(db_session, alice, bob)
        await make_friends(db_session, bob, carol)
        channel = await chat_service.create_group(
            db_session, alice.id, "Group", [bob.id]
        )

        # Bob (member) tries to add Carol
        with pytest.raises(ValueError, match="Only admins and owners"):
            await chat_service.add_member(
                db_session, channel.id, bob.id, carol.id
            )

    @pytest.mark.asyncio
    async def test_add_non_friend_raises(self, db_session):
        """Can only add friends to the chat."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        carol = await create_user(db_session, "carol@test.com", "Carol")
        await make_friends(db_session, alice, bob)
        # alice and carol are NOT friends
        channel = await chat_service.create_group(
            db_session, alice.id, "Group", [bob.id]
        )

        with pytest.raises(ValueError, match="only add friends"):
            await chat_service.add_member(
                db_session, channel.id, alice.id, carol.id
            )

    @pytest.mark.asyncio
    async def test_add_existing_member_raises(self, db_session):
        """Cannot add someone who is already a member."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.create_group(
            db_session, alice.id, "Group", [bob.id]
        )

        with pytest.raises(ValueError, match="already a member"):
            await chat_service.add_member(
                db_session, channel.id, alice.id, bob.id
            )

    @pytest.mark.asyncio
    async def test_remove_member_by_owner(self, db_session):
        """Owner can remove a member from the group."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.create_group(
            db_session, alice.id, "Group", [bob.id]
        )

        await chat_service.remove_member(
            db_session, channel.id, alice.id, bob.id
        )

        member_ids = await chat_service.get_channel_member_ids(
            db_session, channel.id
        )
        assert bob.id not in member_ids

    @pytest.mark.asyncio
    async def test_self_leave(self, db_session):
        """Any member can leave a group by removing themselves."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.create_group(
            db_session, alice.id, "Group", [bob.id]
        )

        # Bob leaves
        await chat_service.remove_member(
            db_session, channel.id, bob.id, bob.id
        )

        member_ids = await chat_service.get_channel_member_ids(
            db_session, channel.id
        )
        assert bob.id not in member_ids
        assert alice.id in member_ids

    @pytest.mark.asyncio
    async def test_regular_member_cannot_remove_others(self, db_session):
        """Regular members cannot remove other members."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        carol = await create_user(db_session, "carol@test.com", "Carol")
        await make_friends(db_session, alice, bob)
        await make_friends(db_session, alice, carol)
        channel = await chat_service.create_group(
            db_session, alice.id, "Group", [bob.id, carol.id]
        )

        # Bob (member) tries to remove Carol
        with pytest.raises(ValueError, match="Only admins and owners"):
            await chat_service.remove_member(
                db_session, channel.id, bob.id, carol.id
            )

    @pytest.mark.asyncio
    async def test_remove_member_from_dm_raises(self, db_session):
        """Cannot remove members from DM channels."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)

        with pytest.raises(ValueError, match="Cannot remove members from a DM"):
            await chat_service.remove_member(
                db_session, channel.id, alice.id, bob.id
            )

    @pytest.mark.asyncio
    async def test_add_member_to_nonexistent_channel_raises(self, db_session):
        """Adding to a non-existent channel raises."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")

        with pytest.raises(ValueError, match="Channel not found"):
            await chat_service.add_member(db_session, 99999, alice.id, bob.id)


# =============================================================================
# Rename Channel — rename_channel
# =============================================================================


class TestRenameChannel:
    """Tests for rename_channel()"""

    @pytest.mark.asyncio
    async def test_rename_group_happy_path(self, db_session):
        """Owner can rename a group."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.create_group(
            db_session, alice.id, "Old Name", [bob.id]
        )

        await chat_service.rename_channel(
            db_session, channel.id, alice.id, "New Name"
        )
        await db_session.refresh(channel)
        assert channel.name == "New Name"

    @pytest.mark.asyncio
    async def test_rename_dm_raises(self, db_session):
        """DMs cannot be renamed."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)

        with pytest.raises(ValueError, match="Cannot rename a DM"):
            await chat_service.rename_channel(
                db_session, channel.id, alice.id, "Named DM"
            )

    @pytest.mark.asyncio
    async def test_rename_by_regular_member_raises(self, db_session):
        """Regular members cannot rename."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.create_group(
            db_session, alice.id, "Group", [bob.id]
        )

        with pytest.raises(ValueError, match="Only admins and owners"):
            await chat_service.rename_channel(
                db_session, channel.id, bob.id, "Bob's Group"
            )

    @pytest.mark.asyncio
    async def test_rename_empty_name_raises(self, db_session):
        """Empty name is rejected."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.create_group(
            db_session, alice.id, "Group", [bob.id]
        )

        with pytest.raises(ValueError, match="Name cannot be empty"):
            await chat_service.rename_channel(
                db_session, channel.id, alice.id, "   "
            )


# =============================================================================
# Get User Channels — get_user_channels
# =============================================================================


class TestGetUserChannels:
    """Tests for get_user_channels()"""

    @pytest.mark.asyncio
    async def test_returns_channels_user_belongs_to(self, db_session):
        """User sees only channels they are a member of."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)

        dm = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        ch = await chat_service.create_channel(db_session, alice.id, "General")

        channels = await chat_service.get_user_channels(db_session, alice.id)

        channel_ids = [c["id"] for c in channels]
        assert dm.id in channel_ids
        assert ch.id in channel_ids

    @pytest.mark.asyncio
    async def test_dm_channel_shows_other_user_name(self, db_session):
        """DM channels display the other user's name, not the channel name."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        await chat_service.get_or_create_dm(db_session, alice.id, bob.id)

        channels = await chat_service.get_user_channels(db_session, alice.id)
        dm = [c for c in channels if c["type"] == "dm"][0]
        assert dm["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_channel_includes_unread_count(self, db_session):
        """Channel listing includes unread message count."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)

        # Mark read for bob, then alice sends a message
        await chat_service.mark_read(db_session, channel.id, bob.id)
        await chat_service.send_message(
            db_session, channel.id, alice.id, "new message"
        )

        channels = await chat_service.get_user_channels(db_session, bob.id)
        dm = [c for c in channels if c["id"] == channel.id][0]
        assert dm["unread_count"] == 1

    @pytest.mark.asyncio
    async def test_user_with_no_channels_returns_empty(self, db_session):
        """User with no channel memberships gets empty list."""
        alice = await create_user(db_session, "alice@test.com", "Alice")

        channels = await chat_service.get_user_channels(db_session, alice.id)
        assert channels == []


# =============================================================================
# Get Channel Members — get_channel_members
# =============================================================================


class TestGetChannelMembers:
    """Tests for get_channel_members()"""

    @pytest.mark.asyncio
    async def test_returns_all_members_with_roles(self, db_session):
        """All members returned with display name and role."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.create_group(
            db_session, alice.id, "Group", [bob.id]
        )

        members = await chat_service.get_channel_members(db_session, channel.id)

        assert len(members) == 2
        names = {m["display_name"] for m in members}
        assert names == {"Alice", "Bob"}


# =============================================================================
# Cleanup — cleanup_old_messages
# =============================================================================


class TestCleanupOldMessages:
    """Tests for cleanup_old_messages()"""

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_messages(self, db_session):
        """Messages older than retention period are deleted."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        channel = await chat_service.create_channel(db_session, alice.id, "Test")

        # Create an old message directly
        old_msg = ChatMessage(
            channel_id=channel.id,
            sender_id=alice.id,
            content="old",
            created_at=datetime.utcnow() - timedelta(days=100),
        )
        db_session.add(old_msg)
        await db_session.flush()

        # Create a recent message
        await chat_service.send_message(
            db_session, channel.id, alice.id, "recent"
        )

        deleted = await chat_service.cleanup_old_messages(db_session, 30)
        assert deleted == 1

    @pytest.mark.asyncio
    async def test_cleanup_zero_days_does_nothing(self, db_session):
        """Retention of 0 days means no cleanup."""
        deleted = await chat_service.cleanup_old_messages(db_session, 0)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_cleanup_negative_days_does_nothing(self, db_session):
        """Negative retention days does nothing."""
        deleted = await chat_service.cleanup_old_messages(db_session, -5)
        assert deleted == 0


# =============================================================================
# Emoji Reactions — toggle_reaction
# =============================================================================


class TestToggleReaction:
    """Tests for toggle_reaction()"""

    @pytest.mark.asyncio
    async def test_add_reaction_happy_path(self, db_session):
        """Happy path: add a reaction to a message."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        msg = await chat_service.send_message(db_session, channel.id, alice.id, "Hello!")

        result = await chat_service.toggle_reaction(db_session, msg["id"], bob.id, "👍")
        assert result["action"] == "added"
        assert result["emoji"] == "👍"
        assert len(result["reactions"]) == 1
        assert result["reactions"][0]["count"] == 1
        assert bob.id in result["reactions"][0]["user_ids"]

    @pytest.mark.asyncio
    async def test_remove_reaction(self, db_session):
        """Toggling an existing reaction removes it."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        msg = await chat_service.send_message(db_session, channel.id, alice.id, "Hello!")

        await chat_service.toggle_reaction(db_session, msg["id"], bob.id, "👍")
        result = await chat_service.toggle_reaction(db_session, msg["id"], bob.id, "👍")
        assert result["action"] == "removed"
        assert len(result["reactions"]) == 0

    @pytest.mark.asyncio
    async def test_reaction_invalid_emoji_raises(self, db_session):
        """Invalid emojis are rejected."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        msg = await chat_service.send_message(db_session, channel.id, alice.id, "Hello!")

        with pytest.raises(ValueError, match="Invalid emoji"):
            await chat_service.toggle_reaction(db_session, msg["id"], bob.id, "NOTANEMOJI")

    @pytest.mark.asyncio
    async def test_reaction_nonmember_raises(self, db_session):
        """Non-members cannot react."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        charlie = await create_user(db_session, "charlie@test.com", "Charlie")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        msg = await chat_service.send_message(db_session, channel.id, alice.id, "Hello!")

        with pytest.raises(ValueError, match="not a member"):
            await chat_service.toggle_reaction(db_session, msg["id"], charlie.id, "👍")

    @pytest.mark.asyncio
    async def test_reaction_on_deleted_message_raises(self, db_session):
        """Cannot react to a deleted message."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        msg = await chat_service.send_message(db_session, channel.id, alice.id, "Hello!")
        await chat_service.delete_message(db_session, msg["id"], alice.id)

        with pytest.raises(ValueError, match="deleted"):
            await chat_service.toggle_reaction(db_session, msg["id"], bob.id, "👍")

    @pytest.mark.asyncio
    async def test_multiple_users_same_emoji(self, db_session):
        """Multiple users can react with the same emoji."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        msg = await chat_service.send_message(db_session, channel.id, alice.id, "Hello!")

        await chat_service.toggle_reaction(db_session, msg["id"], alice.id, "❤️")
        result = await chat_service.toggle_reaction(db_session, msg["id"], bob.id, "❤️")
        assert result["reactions"][0]["count"] == 2
        assert set(result["reactions"][0]["user_ids"]) == {alice.id, bob.id}


# =============================================================================
# Reply-to Messages
# =============================================================================


class TestReplyTo:
    """Tests for reply_to_id in send_message()"""

    @pytest.mark.asyncio
    async def test_reply_to_message(self, db_session):
        """Happy path: reply to a specific message."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        original = await chat_service.send_message(db_session, channel.id, alice.id, "Hi Bob!")

        reply = await chat_service.send_message(
            db_session, channel.id, bob.id, "Hi Alice!",
            reply_to_id=original["id"]
        )
        assert reply["reply_to"] is not None
        assert reply["reply_to"]["id"] == original["id"]
        assert reply["reply_to"]["sender_name"] == "Alice"
        assert reply["reply_to"]["content"] == "Hi Bob!"

    @pytest.mark.asyncio
    async def test_reply_to_invalid_message_raises(self, db_session):
        """Reply to a message in a different channel raises error."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        charlie = await create_user(db_session, "charlie@test.com", "Charlie")
        await make_friends(db_session, alice, bob)
        await make_friends(db_session, alice, charlie)

        ch1 = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        ch2 = await chat_service.get_or_create_dm(db_session, alice.id, charlie.id)
        msg_in_ch1 = await chat_service.send_message(db_session, ch1.id, alice.id, "In ch1")

        with pytest.raises(ValueError, match="Invalid reply target"):
            await chat_service.send_message(
                db_session, ch2.id, alice.id, "Reply",
                reply_to_id=msg_in_ch1["id"]
            )

    @pytest.mark.asyncio
    async def test_reply_to_nonexistent_message_raises(self, db_session):
        """Reply to a nonexistent message raises error."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)

        with pytest.raises(ValueError, match="Invalid reply target"):
            await chat_service.send_message(
                db_session, channel.id, alice.id, "Reply",
                reply_to_id=99999
            )

    @pytest.mark.asyncio
    async def test_messages_include_reply_to_data(self, db_session):
        """get_messages returns reply_to data in message dicts."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        original = await chat_service.send_message(db_session, channel.id, alice.id, "Original")
        await chat_service.send_message(
            db_session, channel.id, bob.id, "Reply",
            reply_to_id=original["id"]
        )

        messages = await chat_service.get_messages(db_session, channel.id, alice.id)
        reply_msg = [m for m in messages if m["content"] == "Reply"][0]
        assert reply_msg["reply_to"]["id"] == original["id"]
        assert reply_msg["reply_to"]["sender_name"] == "Alice"


# =============================================================================
# Pinned Messages — toggle_pin, get_pinned_messages
# =============================================================================


class TestPinnedMessages:
    """Tests for toggle_pin() and get_pinned_messages()"""

    @pytest.mark.asyncio
    async def test_pin_message_happy_path(self, db_session):
        """Owner can pin a message."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.create_group(db_session, alice.id, "Test", [bob.id])
        msg = await chat_service.send_message(db_session, channel.id, alice.id, "Important!")

        result = await chat_service.toggle_pin(db_session, msg["id"], alice.id)
        assert result["is_pinned"] is True
        assert result["message_id"] == msg["id"]

    @pytest.mark.asyncio
    async def test_unpin_message(self, db_session):
        """Toggling pin again unpins."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.create_group(db_session, alice.id, "Test", [bob.id])
        msg = await chat_service.send_message(db_session, channel.id, alice.id, "Pin me")

        await chat_service.toggle_pin(db_session, msg["id"], alice.id)
        result = await chat_service.toggle_pin(db_session, msg["id"], alice.id)
        assert result["is_pinned"] is False

    @pytest.mark.asyncio
    async def test_pin_member_cannot_pin(self, db_session):
        """Regular members cannot pin messages."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.create_group(db_session, alice.id, "Test", [bob.id])
        msg = await chat_service.send_message(db_session, channel.id, alice.id, "Pin?")

        with pytest.raises(ValueError, match="admins and owners"):
            await chat_service.toggle_pin(db_session, msg["id"], bob.id)

    @pytest.mark.asyncio
    async def test_get_pinned_messages(self, db_session):
        """get_pinned_messages returns only pinned messages."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.create_group(db_session, alice.id, "Test", [bob.id])

        msg1 = await chat_service.send_message(db_session, channel.id, alice.id, "Pinned!")
        await chat_service.send_message(db_session, channel.id, alice.id, "Not pinned")
        await chat_service.toggle_pin(db_session, msg1["id"], alice.id)

        pinned = await chat_service.get_pinned_messages(db_session, channel.id, alice.id)
        assert len(pinned) == 1
        assert pinned[0]["id"] == msg1["id"]
        assert pinned[0]["is_pinned"] is True

    @pytest.mark.asyncio
    async def test_pin_deleted_message_raises(self, db_session):
        """Cannot pin a deleted message."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.create_group(db_session, alice.id, "Test", [bob.id])
        msg = await chat_service.send_message(db_session, channel.id, alice.id, "Delete me")
        await chat_service.delete_message(db_session, msg["id"], alice.id)

        with pytest.raises(ValueError, match="deleted"):
            await chat_service.toggle_pin(db_session, msg["id"], alice.id)


# =============================================================================
# Message Search — search_messages
# =============================================================================


class TestSearchMessages:
    """Tests for search_messages()"""

    @pytest.mark.asyncio
    async def test_search_happy_path(self, db_session):
        """Happy path: search finds matching messages."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        await chat_service.send_message(db_session, channel.id, alice.id, "Hello world")
        await chat_service.send_message(db_session, channel.id, alice.id, "Goodbye universe")
        await chat_service.send_message(db_session, channel.id, bob.id, "Hello again")

        results = await chat_service.search_messages(db_session, alice.id, "Hello")
        assert len(results) == 2
        assert all("Hello" in r["content"] for r in results)

    @pytest.mark.asyncio
    async def test_search_specific_channel(self, db_session):
        """Search within a specific channel."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        charlie = await create_user(db_session, "charlie@test.com", "Charlie")
        await make_friends(db_session, alice, bob)
        await make_friends(db_session, alice, charlie)

        ch1 = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        ch2 = await chat_service.get_or_create_dm(db_session, alice.id, charlie.id)
        await chat_service.send_message(db_session, ch1.id, alice.id, "Hello Bob")
        await chat_service.send_message(db_session, ch2.id, alice.id, "Hello Charlie")

        results = await chat_service.search_messages(
            db_session, alice.id, "Hello", channel_id=ch1.id
        )
        assert len(results) == 1
        assert "Bob" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_search_excludes_deleted_messages(self, db_session):
        """Search excludes soft-deleted messages."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        msg = await chat_service.send_message(db_session, channel.id, alice.id, "Delete me hello")
        await chat_service.delete_message(db_session, msg["id"], alice.id)
        await chat_service.send_message(db_session, channel.id, alice.id, "Keep me hello")

        results = await chat_service.search_messages(db_session, alice.id, "hello")
        assert len(results) == 1
        assert results[0]["content"] == "Keep me hello"

    @pytest.mark.asyncio
    async def test_search_too_short_raises(self, db_session):
        """Search query too short raises error."""
        alice = await create_user(db_session, "alice@test.com", "Alice")

        with pytest.raises(ValueError, match="at least 2"):
            await chat_service.search_messages(db_session, alice.id, "a")

    @pytest.mark.asyncio
    async def test_search_nonmember_channel_raises(self, db_session):
        """Cannot search a channel you're not a member of."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        charlie = await create_user(db_session, "charlie@test.com", "Charlie")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)

        with pytest.raises(ValueError, match="not a member"):
            await chat_service.search_messages(
                db_session, charlie.id, "hello", channel_id=channel.id
            )


# =============================================================================
# Message Format — reactions and reply_to in get_messages
# =============================================================================


class TestMessageFormat:
    """Tests that messages include reactions, reply_to, and is_pinned fields."""

    @pytest.mark.asyncio
    async def test_messages_include_reactions(self, db_session):
        """get_messages returns reactions on messages."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)
        msg = await chat_service.send_message(db_session, channel.id, alice.id, "React!")
        await chat_service.toggle_reaction(db_session, msg["id"], bob.id, "👍")

        messages = await chat_service.get_messages(db_session, channel.id, alice.id)
        assert len(messages) == 1
        assert len(messages[0]["reactions"]) == 1
        assert messages[0]["reactions"][0]["emoji"] == "👍"
        assert messages[0]["reactions"][0]["count"] == 1

    @pytest.mark.asyncio
    async def test_messages_include_pin_status(self, db_session):
        """get_messages includes is_pinned field."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.create_group(db_session, alice.id, "Test", [bob.id])
        msg = await chat_service.send_message(db_session, channel.id, alice.id, "Pin me!")
        await chat_service.toggle_pin(db_session, msg["id"], alice.id)

        messages = await chat_service.get_messages(db_session, channel.id, alice.id)
        pinned = [m for m in messages if m["content"] == "Pin me!"][0]
        assert pinned["is_pinned"] is True

    @pytest.mark.asyncio
    async def test_send_message_returns_full_format(self, db_session):
        """send_message returns reactions, reply_to, and is_pinned fields."""
        alice = await create_user(db_session, "alice@test.com", "Alice")
        bob = await create_user(db_session, "bob@test.com", "Bob")
        await make_friends(db_session, alice, bob)
        channel = await chat_service.get_or_create_dm(db_session, alice.id, bob.id)

        msg = await chat_service.send_message(db_session, channel.id, alice.id, "Full format")
        assert "reactions" in msg
        assert "reply_to" in msg
        assert "is_pinned" in msg
        assert msg["reactions"] == []
        assert msg["reply_to"] is None
        assert msg["is_pinned"] is False
