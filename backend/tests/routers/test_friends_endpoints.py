"""
Endpoint-level tests for friends_router.py and display_name_router.py.

Uses FastAPI TestClient with dependency overrides to exercise HTTP layer
including validation, status codes, and response schemas.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models import User
from app.models.social import BlockedUser, FriendRequest, Friendship


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
    user = User(email="alice@test.com", hashed_password="fake", display_name="Alice", is_active=True)
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def bob(db_session):
    user = User(email="bob@test.com", hashed_password="fake", display_name="Bob", is_active=True)
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def carol(db_session):
    user = User(email="carol@test.com", hashed_password="fake", display_name="Carol", is_active=True)
    db_session.add(user)
    await db_session.flush()
    return user


# =============================================================================
# Friend Request Endpoints
# =============================================================================


class TestSendFriendRequest:
    """POST /api/friends/request"""

    @pytest.mark.asyncio
    async def test_send_request_happy_path(self, app, override_current_user, alice, bob, db_session):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/friends/request", json={"display_name": "Bob"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["to_user_id"] == bob.id
        assert data["to_display_name"] == "Bob"

    @pytest.mark.asyncio
    async def test_send_request_user_not_found(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/friends/request", json={"display_name": "Nobody"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_send_request_to_self(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/friends/request", json={"display_name": "Alice"})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_send_request_already_friends(self, app, override_current_user, alice, bob, db_session):
        db_session.add(Friendship(user_id=alice.id, friend_id=bob.id))
        db_session.add(Friendship(user_id=bob.id, friend_id=alice.id))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/friends/request", json={"display_name": "Bob"})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_send_request_blocked_by_target(self, app, override_current_user, alice, bob, db_session):
        db_session.add(BlockedUser(blocker_id=bob.id, blocked_id=alice.id))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/friends/request", json={"display_name": "Bob"})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_send_request_duplicate_pending(self, app, override_current_user, alice, bob, db_session):
        db_session.add(FriendRequest(from_user_id=alice.id, to_user_id=bob.id))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/friends/request", json={"display_name": "Bob"})
        assert resp.status_code == 409


# =============================================================================
# Accept / Reject Friend Requests
# =============================================================================


class TestAcceptRejectRequest:
    """POST /api/friends/requests/{id}/accept, DELETE /api/friends/requests/{id}"""

    @pytest.mark.asyncio
    async def test_accept_creates_bidirectional_friendship(self, app, override_current_user, alice, bob, db_session):
        req = FriendRequest(from_user_id=alice.id, to_user_id=bob.id)
        db_session.add(req)
        await db_session.flush()

        override_current_user(app, bob)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/friends/requests/{req.id}/accept")
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

        # Verify bidirectional friendship
        result = await db_session.execute(
            select(Friendship).where(Friendship.user_id == bob.id, Friendship.friend_id == alice.id)
        )
        assert result.scalar_one_or_none() is not None
        result = await db_session.execute(
            select(Friendship).where(Friendship.user_id == alice.id, Friendship.friend_id == bob.id)
        )
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_accept_nonexistent_request(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/friends/requests/9999/accept")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reject_deletes_request(self, app, override_current_user, alice, bob, db_session):
        req = FriendRequest(from_user_id=alice.id, to_user_id=bob.id)
        db_session.add(req)
        await db_session.flush()
        req_id = req.id

        override_current_user(app, bob)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete(f"/api/friends/requests/{req_id}")
        assert resp.status_code == 200

        # Request is gone
        result = await db_session.execute(select(FriendRequest).where(FriendRequest.id == req_id))
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_cannot_accept_others_request(self, app, override_current_user, alice, bob, carol, db_session):
        """Alice sends to Bob, Carol tries to accept — should fail."""
        req = FriendRequest(from_user_id=alice.id, to_user_id=bob.id)
        db_session.add(req)
        await db_session.flush()

        override_current_user(app, carol)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/friends/requests/{req.id}/accept")
        assert resp.status_code == 404  # Not found for Carol


# =============================================================================
# List Friends
# =============================================================================


class TestListFriends:
    """GET /api/friends"""

    @pytest.mark.asyncio
    async def test_list_friends_empty(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/friends")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_friends_with_data(self, app, override_current_user, alice, bob, carol, db_session):
        for f in [bob, carol]:
            db_session.add(Friendship(user_id=alice.id, friend_id=f.id))
            db_session.add(Friendship(user_id=f.id, friend_id=alice.id))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/friends")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {f["display_name"] for f in data}
        assert names == {"Bob", "Carol"}


# =============================================================================
# Remove Friend
# =============================================================================


class TestRemoveFriend:
    """DELETE /api/friends/{friend_id}"""

    @pytest.mark.asyncio
    async def test_remove_friend_deletes_both_directions(self, app, override_current_user, alice, bob, db_session):
        db_session.add(Friendship(user_id=alice.id, friend_id=bob.id))
        db_session.add(Friendship(user_id=bob.id, friend_id=alice.id))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete(f"/api/friends/{bob.id}")
        assert resp.status_code == 200

        result = await db_session.execute(
            select(Friendship).where(Friendship.user_id == alice.id, Friendship.friend_id == bob.id)
        )
        assert result.scalar_one_or_none() is None


# =============================================================================
# Block / Unblock
# =============================================================================


class TestBlockUnblock:
    """POST /api/friends/block, DELETE /api/friends/block/{user_id}, GET /api/friends/blocked"""

    @pytest.mark.asyncio
    async def test_block_user(self, app, override_current_user, alice, bob, db_session):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/friends/block", json={"user_id": bob.id})
        assert resp.status_code == 200
        assert resp.json()["status"] == "blocked"

    @pytest.mark.asyncio
    async def test_block_removes_friendship(self, app, override_current_user, alice, bob, db_session):
        db_session.add(Friendship(user_id=alice.id, friend_id=bob.id))
        db_session.add(Friendship(user_id=bob.id, friend_id=alice.id))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/friends/block", json={"user_id": bob.id})

        result = await db_session.execute(
            select(Friendship).where(Friendship.user_id == alice.id, Friendship.friend_id == bob.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_block_self_rejected(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/friends/block", json={"user_id": alice.id})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_unblock_user(self, app, override_current_user, alice, bob, db_session):
        db_session.add(BlockedUser(blocker_id=alice.id, blocked_id=bob.id))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete(f"/api/friends/block/{bob.id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unblock_nonexistent(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete("/api/friends/block/9999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_blocked(self, app, override_current_user, alice, bob, db_session):
        db_session.add(BlockedUser(blocker_id=alice.id, blocked_id=bob.id))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/friends/blocked")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["display_name"] == "Bob"


# =============================================================================
# User Search
# =============================================================================


class TestUserSearch:
    """GET /api/users/search"""

    @pytest.mark.asyncio
    async def test_search_returns_matches(self, app, override_current_user, alice, bob, carol):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/users/search", params={"q": "Bob"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["display_name"] == "Bob"

    @pytest.mark.asyncio
    async def test_search_excludes_self(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/users/search", params={"q": "Alice"})
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, app, override_current_user, alice, bob):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/users/search", params={"q": "bob"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_search_empty_query_rejected(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/users/search", params={"q": ""})
        assert resp.status_code == 422  # Validation error


# =============================================================================
# Display Name
# =============================================================================


class TestDisplayName:
    """PUT /api/users/display-name, GET /api/users/display-name/check"""

    @pytest.mark.asyncio
    async def test_set_display_name(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/users/display-name", json={"display_name": "NewAlice"})
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "NewAlice"

    @pytest.mark.asyncio
    async def test_set_display_name_taken(self, app, override_current_user, alice, bob):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/users/display-name", json={"display_name": "Bob"})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_set_display_name_case_insensitive_conflict(self, app, override_current_user, alice, bob):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/users/display-name", json={"display_name": "bob"})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_set_display_name_invalid_chars(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/users/display-name", json={"display_name": "Bad Name!"})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_set_display_name_too_short(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/users/display-name", json={"display_name": "AB"})
        assert resp.status_code == 422  # Pydantic validation

    @pytest.mark.asyncio
    async def test_check_available_name(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/users/display-name/check", params={"name": "FreshName"})
        assert resp.status_code == 200
        assert resp.json()["available"] is True

    @pytest.mark.asyncio
    async def test_check_taken_name(self, app, override_current_user, alice, bob):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/users/display-name/check", params={"name": "Bob"})
        assert resp.status_code == 200
        assert resp.json()["available"] is False

    @pytest.mark.asyncio
    async def test_can_keep_own_name(self, app, override_current_user, alice):
        """Setting display name to your current name should succeed."""
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put("/api/users/display-name", json={"display_name": "Alice"})
        assert resp.status_code == 200
