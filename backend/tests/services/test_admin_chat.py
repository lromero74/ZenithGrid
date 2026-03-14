"""
Tests for admin chat functionality (admin_dm channels, admin display names).
"""

import pytest
from datetime import datetime

from app.models import User
from app.models.social import ChatChannel, ChatChannelMember, ChatMessage, Friendship
from app.services.chat_service import (
    get_or_create_admin_dm,
    send_message,
    get_channel_members,
)
from sqlalchemy import select


@pytest.fixture
async def admin_user(db_session):
    """Create an admin user with admin display name."""
    user = User(
        id=1, email="admin@test.com", display_name="AdminFull",
        admin_display_name="Louis", hashed_password="x",
        is_active=True, is_superuser=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def regular_user(db_session):
    """Create a regular user."""
    user = User(
        id=2, email="user@test.com", display_name="RegularUser",
        hashed_password="x", is_active=True, is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    return user


class TestGetOrCreateAdminDm:
    """Tests for admin DM channel creation."""

    @pytest.mark.asyncio
    async def test_creates_admin_dm_no_friendship_required(
        self, db_session, admin_user, regular_user
    ):
        """Admin can create DM with any user without friendship."""
        channel = await get_or_create_admin_dm(db_session, admin_user.id, regular_user.id)

        assert channel.type == "admin_dm"
        assert channel.created_by == admin_user.id

        # Check members
        result = await db_session.execute(
            select(ChatChannelMember).where(
                ChatChannelMember.channel_id == channel.id
            )
        )
        members = result.scalars().all()
        assert len(members) == 2

        admin_member = next(m for m in members if m.user_id == admin_user.id)
        user_member = next(m for m in members if m.user_id == regular_user.id)
        assert admin_member.role == "owner"
        assert user_member.role == "member"

    @pytest.mark.asyncio
    async def test_admin_dm_channel_not_duplicated(
        self, db_session, admin_user, regular_user
    ):
        """Calling get_or_create_admin_dm twice returns same channel."""
        ch1 = await get_or_create_admin_dm(db_session, admin_user.id, regular_user.id)
        ch2 = await get_or_create_admin_dm(db_session, admin_user.id, regular_user.id)

        assert ch1.id == ch2.id

    @pytest.mark.asyncio
    async def test_admin_dm_sender_name_uses_admin_display_name(
        self, db_session, admin_user, regular_user
    ):
        """Messages in admin_dm use admin_display_name (Admin) format."""
        channel = await get_or_create_admin_dm(db_session, admin_user.id, regular_user.id)

        msg_data = await send_message(
            db_session, channel.id, admin_user.id, "Hello from admin"
        )

        assert msg_data["sender_name"] == "Louis (Admin)"
        assert msg_data["is_admin"] is True

    @pytest.mark.asyncio
    async def test_regular_user_message_in_admin_dm(
        self, db_session, admin_user, regular_user
    ):
        """Regular user's messages in admin_dm use their display_name, not admin format."""
        channel = await get_or_create_admin_dm(db_session, admin_user.id, regular_user.id)

        msg_data = await send_message(
            db_session, channel.id, regular_user.id, "Hello admin"
        )

        assert msg_data["sender_name"] == "RegularUser"
        assert msg_data["is_admin"] is False

    @pytest.mark.asyncio
    async def test_admin_badge_flag_on_members(
        self, db_session, admin_user, regular_user
    ):
        """Channel members include is_admin flag."""
        channel = await get_or_create_admin_dm(db_session, admin_user.id, regular_user.id)

        members = await get_channel_members(db_session, channel.id)

        admin_member = next(m for m in members if m["user_id"] == admin_user.id)
        user_member = next(m for m in members if m["user_id"] == regular_user.id)

        assert admin_member["is_admin"] is True
        assert user_member["is_admin"] is False

    @pytest.mark.asyncio
    async def test_admin_dm_falls_back_to_display_name(self, db_session, regular_user):
        """If admin_display_name not set, falls back to display_name."""
        admin_no_alias = User(
            id=3, email="admin2@test.com", display_name="Admin2",
            admin_display_name=None, hashed_password="x",
            is_active=True, is_superuser=True,
        )
        db_session.add(admin_no_alias)
        await db_session.commit()

        channel = await get_or_create_admin_dm(db_session, admin_no_alias.id, regular_user.id)
        msg = await send_message(db_session, channel.id, admin_no_alias.id, "Hi")

        assert msg["sender_name"] == "Admin2 (Admin)"
