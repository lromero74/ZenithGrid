"""
Tests for backend/app/routers/chat_router.py

Covers REST endpoints for chat channels, messages, membership,
read tracking, and unread counts. Uses httpx AsyncClient with
dependency overrides for auth and database.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.models import User
from app.models.social import Friendship


# =============================================================================
# Helpers
# =============================================================================


async def create_user(db, email, display_name=None):
    """Create a test user (superuser to bypass RBAC)."""
    user = User(
        email=email,
        hashed_password="fakehash",
        display_name=display_name or email.split("@")[0],
        is_active=True,
        is_superuser=True,
    )
    db.add(user)
    await db.flush()
    return user


async def make_friends(db, user_a, user_b):
    """Create bidirectional friendship."""
    db.add(Friendship(user_id=user_a.id, friend_id=user_b.id))
    db.add(Friendship(user_id=user_b.id, friend_id=user_a.id))
    await db.flush()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def app(mock_db_session):
    """Create a FastAPI app with DB dependency overridden."""
    from app.main import app as real_app
    from app.database import get_db

    real_app.dependency_overrides[get_db] = mock_db_session
    yield real_app
    real_app.dependency_overrides.clear()


@pytest.fixture
def override_current_user():
    """Factory to override get_current_user with a specific user."""
    def _override(app_instance, user):
        from app.auth.dependencies import get_current_user

        async def _fake():
            return user
        app_instance.dependency_overrides[get_current_user] = _fake
    return _override


@pytest.fixture
async def alice(db_session):
    return await create_user(db_session, "alice@test.com", "Alice")


@pytest.fixture
async def bob(db_session):
    return await create_user(db_session, "bob@test.com", "Bob")


@pytest.fixture
async def carol(db_session):
    return await create_user(db_session, "carol@test.com", "Carol")


# =============================================================================
# POST /api/chat/channels — Create Channel
# =============================================================================


class TestCreateChannel:
    """POST /api/chat/channels"""

    @pytest.mark.asyncio
    async def test_create_dm_happy_path(self, app, override_current_user, alice, bob, db_session):
        """Creating a DM between friends returns channel info."""
        await make_friends(db_session, alice, bob)
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/chat/channels", json={
                "type": "dm",
                "friend_id": bob.id,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "dm"
        assert data["name"] is None

    @pytest.mark.asyncio
    async def test_create_dm_without_friend_id_returns_400(
        self, app, override_current_user, alice
    ):
        """DM creation without friend_id returns 400."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/chat/channels", json={
                "type": "dm",
            })

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_dm_without_friendship_returns_400(
        self, app, override_current_user, alice, bob
    ):
        """DM creation without friendship returns 400."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/chat/channels", json={
                "type": "dm",
                "friend_id": bob.id,
            })

        assert resp.status_code == 400
        assert "friends" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_group_happy_path(
        self, app, override_current_user, alice, bob, db_session
    ):
        """Creating a group with friends succeeds."""
        await make_friends(db_session, alice, bob)
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/chat/channels", json={
                "type": "group",
                "name": "Test Group",
                "member_ids": [bob.id],
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "group"
        assert data["name"] == "Test Group"

    @pytest.mark.asyncio
    async def test_create_group_without_name_returns_400(
        self, app, override_current_user, alice
    ):
        """Group creation without name returns 400."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/chat/channels", json={
                "type": "group",
                "member_ids": [1],
            })

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_channel_happy_path(self, app, override_current_user, alice):
        """Creating a named channel succeeds."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/chat/channels", json={
                "type": "channel",
                "name": "General",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "channel"
        assert data["name"] == "General"

    @pytest.mark.asyncio
    async def test_create_channel_invalid_type_returns_422(
        self, app, override_current_user, alice
    ):
        """Invalid channel type is rejected by Pydantic validation."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/chat/channels", json={
                "type": "invalid_type",
                "name": "Bad",
            })

        assert resp.status_code == 422


# =============================================================================
# GET /api/chat/channels — List Channels
# =============================================================================


class TestListChannels:
    """GET /api/chat/channels"""

    @pytest.mark.asyncio
    async def test_list_channels_returns_user_channels(
        self, app, override_current_user, alice
    ):
        """User sees their own channels."""
        override_current_user(app, alice)

        # Create a channel first
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/chat/channels", json={
                "type": "channel",
                "name": "General",
            })
            resp = await client.get("/api/chat/channels")

        assert resp.status_code == 200
        channels = resp.json()
        assert len(channels) >= 1
        assert any(c["name"] == "General" for c in channels)

    @pytest.mark.asyncio
    async def test_list_channels_empty_for_new_user(
        self, app, override_current_user, alice
    ):
        """New user with no memberships gets empty list."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/chat/channels")

        assert resp.status_code == 200
        assert resp.json() == []


# =============================================================================
# POST /api/chat/channels/{id}/messages — Send Message
# =============================================================================


class TestSendMessageEndpoint:
    """POST /api/chat/channels/{id}/messages"""

    @pytest.mark.asyncio
    async def test_send_message_happy_path(self, app, override_current_user, alice):
        """Sending a message returns the message data."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Create channel
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "channel",
                "name": "Test",
            })
            channel_id = ch_resp.json()["id"]

            resp = await client.post(
                f"/api/chat/channels/{channel_id}/messages",
                json={"content": "Hello world!"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "Hello world!"
        assert data["sender_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_send_empty_message_returns_422(self, app, override_current_user, alice):
        """Empty message content is rejected by Pydantic (min_length=1)."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "channel",
                "name": "Test",
            })
            channel_id = ch_resp.json()["id"]

            resp = await client.post(
                f"/api/chat/channels/{channel_id}/messages",
                json={"content": ""},
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_send_message_exceeds_2000_chars_returns_422(
        self, app, override_current_user, alice
    ):
        """Message over 2000 chars is rejected by Pydantic."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "channel",
                "name": "Test",
            })
            channel_id = ch_resp.json()["id"]

            resp = await client.post(
                f"/api/chat/channels/{channel_id}/messages",
                json={"content": "x" * 2001},
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_send_message_non_member_returns_400(
        self, app, override_current_user, alice, bob, db_session
    ):
        """Non-member sending a message gets 400."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "channel",
                "name": "Private",
            })
            channel_id = ch_resp.json()["id"]

        # Switch to bob
        override_current_user(app, bob)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/api/chat/channels/{channel_id}/messages",
                json={"content": "Intruder!"},
            )

        assert resp.status_code == 400


# =============================================================================
# GET /api/chat/channels/{id}/messages — Get Messages
# =============================================================================


class TestGetMessagesEndpoint:
    """GET /api/chat/channels/{id}/messages"""

    @pytest.mark.asyncio
    async def test_get_messages_happy_path(self, app, override_current_user, alice):
        """Retrieve messages from a channel."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "channel",
                "name": "Test",
            })
            channel_id = ch_resp.json()["id"]

            await client.post(
                f"/api/chat/channels/{channel_id}/messages",
                json={"content": "msg1"},
            )
            await client.post(
                f"/api/chat/channels/{channel_id}/messages",
                json={"content": "msg2"},
            )

            resp = await client.get(f"/api/chat/channels/{channel_id}/messages")

        assert resp.status_code == 200
        messages = resp.json()
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_get_messages_non_member_returns_403(
        self, app, override_current_user, alice, bob
    ):
        """Non-member cannot retrieve messages (403)."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "channel",
                "name": "Secret",
            })
            channel_id = ch_resp.json()["id"]

        override_current_user(app, bob)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/chat/channels/{channel_id}/messages")

        assert resp.status_code == 403


# =============================================================================
# PATCH /api/chat/messages/{id} — Edit Message
# =============================================================================


class TestEditMessageEndpoint:
    """PATCH /api/chat/messages/{id}"""

    @pytest.mark.asyncio
    async def test_edit_message_happy_path(self, app, override_current_user, alice):
        """Sender can edit their own message."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "channel",
                "name": "Test",
            })
            channel_id = ch_resp.json()["id"]

            msg_resp = await client.post(
                f"/api/chat/channels/{channel_id}/messages",
                json={"content": "original"},
            )
            message_id = msg_resp.json()["id"]

            resp = await client.patch(
                f"/api/chat/messages/{message_id}",
                json={"content": "edited"},
            )

        assert resp.status_code == 200
        assert resp.json()["content"] == "edited"
        assert resp.json()["edited_at"] is not None

    @pytest.mark.asyncio
    async def test_edit_message_by_other_user_returns_400(
        self, app, override_current_user, alice, bob, db_session
    ):
        """Non-sender cannot edit a message."""
        await make_friends(db_session, alice, bob)
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "dm",
                "friend_id": bob.id,
            })
            channel_id = ch_resp.json()["id"]

            msg_resp = await client.post(
                f"/api/chat/channels/{channel_id}/messages",
                json={"content": "Alice's msg"},
            )
            message_id = msg_resp.json()["id"]

        override_current_user(app, bob)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(
                f"/api/chat/messages/{message_id}",
                json={"content": "hacked"},
            )

        assert resp.status_code == 400
        assert "own" in resp.json()["detail"].lower()


# =============================================================================
# DELETE /api/chat/messages/{id} — Delete Message
# =============================================================================


class TestDeleteMessageEndpoint:
    """DELETE /api/chat/messages/{id}"""

    @pytest.mark.asyncio
    async def test_delete_message_happy_path(self, app, override_current_user, alice):
        """Sender can delete their own message."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "channel",
                "name": "Test",
            })
            channel_id = ch_resp.json()["id"]

            msg_resp = await client.post(
                f"/api/chat/channels/{channel_id}/messages",
                json={"content": "delete me"},
            )
            message_id = msg_resp.json()["id"]

            resp = await client.delete(f"/api/chat/messages/{message_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == message_id

    @pytest.mark.asyncio
    async def test_delete_nonexistent_message_returns_400(
        self, app, override_current_user, alice
    ):
        """Deleting a non-existent message returns 400."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete("/api/chat/messages/99999")

        assert resp.status_code == 400


# =============================================================================
# POST /api/chat/channels/{id}/read — Mark Read
# =============================================================================


class TestMarkReadEndpoint:
    """POST /api/chat/channels/{id}/read"""

    @pytest.mark.asyncio
    async def test_mark_read_happy_path(self, app, override_current_user, alice):
        """Marking read returns success status."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "channel",
                "name": "Test",
            })
            channel_id = ch_resp.json()["id"]

            resp = await client.post(f"/api/chat/channels/{channel_id}/read")

        assert resp.status_code == 200
        assert resp.json()["status"] == "read"

    @pytest.mark.asyncio
    async def test_mark_read_non_member_returns_400(
        self, app, override_current_user, alice, bob
    ):
        """Non-member cannot mark read."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "channel",
                "name": "Test",
            })
            channel_id = ch_resp.json()["id"]

        override_current_user(app, bob)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/chat/channels/{channel_id}/read")

        assert resp.status_code == 400


# =============================================================================
# GET /api/chat/unread — Unread Counts
# =============================================================================


class TestUnreadCountsEndpoint:
    """GET /api/chat/unread"""

    @pytest.mark.asyncio
    async def test_unread_counts_happy_path(self, app, override_current_user, alice):
        """Unread counts returned in expected format."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/chat/unread")

        assert resp.status_code == 200
        assert "counts" in resp.json()


# =============================================================================
# Membership Endpoints
# =============================================================================


class TestMembershipEndpoints:
    """GET/POST/DELETE /api/chat/channels/{id}/members"""

    @pytest.mark.asyncio
    async def test_get_members_happy_path(
        self, app, override_current_user, alice, bob, db_session
    ):
        """Get members of a group channel."""
        await make_friends(db_session, alice, bob)
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "group",
                "name": "Team",
                "member_ids": [bob.id],
            })
            channel_id = ch_resp.json()["id"]

            resp = await client.get(f"/api/chat/channels/{channel_id}/members")

        assert resp.status_code == 200
        members = resp.json()
        assert len(members) == 2

    @pytest.mark.asyncio
    async def test_get_members_non_member_returns_403(
        self, app, override_current_user, alice, bob, carol, db_session
    ):
        """Non-member cannot see members."""
        await make_friends(db_session, alice, bob)
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "group",
                "name": "Private",
                "member_ids": [bob.id],
            })
            channel_id = ch_resp.json()["id"]

        override_current_user(app, carol)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/chat/channels/{channel_id}/members")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_add_member_happy_path(
        self, app, override_current_user, alice, bob, carol, db_session
    ):
        """Owner can add a friend to the group."""
        await make_friends(db_session, alice, bob)
        await make_friends(db_session, alice, carol)
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "group",
                "name": "Group",
                "member_ids": [bob.id],
            })
            channel_id = ch_resp.json()["id"]

            resp = await client.post(
                f"/api/chat/channels/{channel_id}/members",
                json={"user_id": carol.id},
            )

        assert resp.status_code == 200
        assert resp.json()["user_id"] == carol.id

    @pytest.mark.asyncio
    async def test_remove_member_happy_path(
        self, app, override_current_user, alice, bob, db_session
    ):
        """Owner can remove a member."""
        await make_friends(db_session, alice, bob)
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "group",
                "name": "Group",
                "member_ids": [bob.id],
            })
            channel_id = ch_resp.json()["id"]

            resp = await client.delete(
                f"/api/chat/channels/{channel_id}/members/{bob.id}"
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "removed"

    @pytest.mark.asyncio
    async def test_self_leave_via_endpoint(
        self, app, override_current_user, alice, bob, db_session
    ):
        """Member can leave by removing themselves via endpoint."""
        await make_friends(db_session, alice, bob)
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "group",
                "name": "Group",
                "member_ids": [bob.id],
            })
            channel_id = ch_resp.json()["id"]

        # Bob leaves
        override_current_user(app, bob)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete(
                f"/api/chat/channels/{channel_id}/members/{bob.id}"
            )

        assert resp.status_code == 200


# =============================================================================
# PATCH /api/chat/channels/{id} — Rename Channel
# =============================================================================


class TestRenameChannelEndpoint:
    """PATCH /api/chat/channels/{id}"""

    @pytest.mark.asyncio
    async def test_rename_channel_happy_path(self, app, override_current_user, alice):
        """Owner can rename a channel."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "channel",
                "name": "Old Name",
            })
            channel_id = ch_resp.json()["id"]

            resp = await client.patch(
                f"/api/chat/channels/{channel_id}",
                json={"name": "New Name"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "renamed"

    @pytest.mark.asyncio
    async def test_rename_channel_empty_name_returns_422(
        self, app, override_current_user, alice
    ):
        """Empty name is rejected by Pydantic (min_length=1)."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch_resp = await client.post("/api/chat/channels", json={
                "type": "channel",
                "name": "Test",
            })
            channel_id = ch_resp.json()["id"]

            resp = await client.patch(
                f"/api/chat/channels/{channel_id}",
                json={"name": ""},
            )

        assert resp.status_code == 422


# =============================================================================
# POST /api/chat/messages/{id}/reactions — Toggle Reaction
# =============================================================================


class TestReactions:
    """POST /api/chat/messages/{id}/reactions"""

    @pytest.mark.asyncio
    async def test_add_reaction_happy_path(self, app, override_current_user, alice, bob, db_session):
        """Adding a reaction returns updated reactions."""
        await make_friends(db_session, alice, bob)
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch = await client.post("/api/chat/channels", json={"type": "dm", "friend_id": bob.id})
            channel_id = ch.json()["id"]
            msg = await client.post(f"/api/chat/channels/{channel_id}/messages",
                                    json={"content": "React to me!"})
            msg_id = msg.json()["id"]

            resp = await client.post(f"/api/chat/messages/{msg_id}/reactions",
                                     json={"emoji": "👍"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "added"
        assert data["emoji"] == "👍"
        assert len(data["reactions"]) == 1

    @pytest.mark.asyncio
    async def test_invalid_emoji_returns_400(self, app, override_current_user, alice, bob, db_session):
        """Invalid emoji returns 400."""
        await make_friends(db_session, alice, bob)
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch = await client.post("/api/chat/channels", json={"type": "dm", "friend_id": bob.id})
            channel_id = ch.json()["id"]
            msg = await client.post(f"/api/chat/channels/{channel_id}/messages",
                                    json={"content": "React!"})
            msg_id = msg.json()["id"]

            resp = await client.post(f"/api/chat/messages/{msg_id}/reactions",
                                     json={"emoji": "INVALID"})

        assert resp.status_code == 400


# =============================================================================
# POST /api/chat/messages/{id}/pin — Toggle Pin
# =============================================================================


class TestPinMessages:
    """POST /api/chat/messages/{id}/pin"""

    @pytest.mark.asyncio
    async def test_pin_message_happy_path(self, app, override_current_user, alice, bob, db_session):
        """Owner can pin a message."""
        await make_friends(db_session, alice, bob)
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch = await client.post("/api/chat/channels", json={
                "type": "group", "name": "Test", "member_ids": [bob.id]
            })
            channel_id = ch.json()["id"]
            msg = await client.post(f"/api/chat/channels/{channel_id}/messages",
                                    json={"content": "Pin me!"})
            msg_id = msg.json()["id"]

            resp = await client.post(f"/api/chat/messages/{msg_id}/pin")

        assert resp.status_code == 200
        assert resp.json()["is_pinned"] is True

    @pytest.mark.asyncio
    async def test_get_pinned_messages(self, app, override_current_user, alice, bob, db_session):
        """GET pinned messages returns only pinned."""
        await make_friends(db_session, alice, bob)
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch = await client.post("/api/chat/channels", json={
                "type": "group", "name": "Test", "member_ids": [bob.id]
            })
            channel_id = ch.json()["id"]
            msg = await client.post(f"/api/chat/channels/{channel_id}/messages",
                                    json={"content": "Pin!"})
            await client.post(f"/api/chat/channels/{channel_id}/messages",
                              json={"content": "No pin"})
            await client.post(f"/api/chat/messages/{msg.json()['id']}/pin")

            resp = await client.get(f"/api/chat/channels/{channel_id}/pinned")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["content"] == "Pin!"


# =============================================================================
# GET /api/chat/search — Search Messages
# =============================================================================


class TestSearchEndpoint:
    """GET /api/chat/search"""

    @pytest.mark.asyncio
    async def test_search_happy_path(self, app, override_current_user, alice, bob, db_session):
        """Search finds matching messages."""
        await make_friends(db_session, alice, bob)
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch = await client.post("/api/chat/channels", json={"type": "dm", "friend_id": bob.id})
            channel_id = ch.json()["id"]
            await client.post(f"/api/chat/channels/{channel_id}/messages",
                              json={"content": "Hello world"})
            await client.post(f"/api/chat/channels/{channel_id}/messages",
                              json={"content": "Goodbye moon"})

            resp = await client.get("/api/chat/search", params={"q": "Hello"})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert "Hello" in data[0]["content"]

    @pytest.mark.asyncio
    async def test_search_query_too_short_returns_422(self, app, override_current_user, alice):
        """Query shorter than 2 chars returns 422 (validation)."""
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/chat/search", params={"q": "a"})

        assert resp.status_code == 422


# =============================================================================
# POST /api/chat/channels/{id}/messages — Reply-to
# =============================================================================


class TestReplyTo:
    """Send message with reply_to_id"""

    @pytest.mark.asyncio
    async def test_reply_to_message(self, app, override_current_user, alice, bob, db_session):
        """Replying to a message includes reply_to in response."""
        await make_friends(db_session, alice, bob)
        override_current_user(app, alice)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ch = await client.post("/api/chat/channels", json={"type": "dm", "friend_id": bob.id})
            channel_id = ch.json()["id"]
            original = await client.post(f"/api/chat/channels/{channel_id}/messages",
                                         json={"content": "Original"})
            orig_id = original.json()["id"]

            resp = await client.post(f"/api/chat/channels/{channel_id}/messages",
                                     json={"content": "Reply", "reply_to_id": orig_id})

        assert resp.status_code == 200
        data = resp.json()
        assert data["reply_to"] is not None
        assert data["reply_to"]["id"] == orig_id
        assert data["reply_to"]["content"] == "Original"
