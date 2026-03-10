"""
Endpoint-level tests for game_history_router.py.

Uses httpx AsyncClient with ASGITransport and dependency overrides.
"""

from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.models import User
from app.models.social import (
    Friendship,
    GameHistoryVisibility,
    GameResult,
    GameResultPlayer,
)


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


@pytest.fixture
async def game_result_with_players(db_session, alice, bob):
    """Create a game result with alice (winner) and bob."""
    gr = GameResult(
        room_id="room-1",
        game_id="chess",
        mode="vs",
        started_at=datetime(2026, 1, 1, 12, 0),
        finished_at=datetime(2026, 1, 1, 12, 30),
    )
    db_session.add(gr)
    await db_session.flush()

    p1 = GameResultPlayer(
        game_result_id=gr.id, user_id=alice.id,
        placement=1, score=100, is_winner=True,
    )
    p2 = GameResultPlayer(
        game_result_id=gr.id, user_id=bob.id,
        placement=2, score=50, is_winner=False,
    )
    db_session.add_all([p1, p2])
    await db_session.flush()
    return gr


# =============================================================================
# GET /api/game-history — own history
# =============================================================================


class TestListOwnGameHistory:
    """GET /api/game-history"""

    @pytest.mark.asyncio
    async def test_list_own_history_empty(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/game-history")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    @pytest.mark.asyncio
    async def test_list_own_history_with_results(
        self, app, override_current_user, alice, game_result_with_players,
    ):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/game-history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["game_id"] == "chess"
        # W5: Verify computed fields
        assert item["result"] == "win"  # alice is_winner=True
        assert item["score"] == 100
        assert item["opponent_names"] == ["Bob"]
        assert item["duration_seconds"] == 1800  # 30 min
        assert "page" in data
        assert "total_pages" in data

    @pytest.mark.asyncio
    async def test_list_own_history_filter_by_game_id(
        self, app, override_current_user, alice, bob, db_session, game_result_with_players,
    ):
        # Add a second game result for a different game
        gr2 = GameResult(
            room_id="room-2", game_id="checkers", mode="vs",
            started_at=datetime(2026, 1, 2, 12, 0),
        )
        db_session.add(gr2)
        await db_session.flush()
        db_session.add(GameResultPlayer(
            game_result_id=gr2.id, user_id=alice.id, placement=1, is_winner=True,
        ))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/game-history", params={"game_id": "chess"})
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["game_id"] == "chess"

    @pytest.mark.asyncio
    async def test_list_own_history_pagination(
        self, app, override_current_user, alice, db_session,
    ):
        # Create 3 game results
        for i in range(3):
            gr = GameResult(
                room_id=f"room-{i}", game_id="chess", mode="vs",
                started_at=datetime(2026, 1, i + 1, 12, 0),
            )
            db_session.add(gr)
            await db_session.flush()
            db_session.add(GameResultPlayer(
                game_result_id=gr.id, user_id=alice.id, placement=1,
            ))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/game-history", params={"limit": 2, "offset": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3


# =============================================================================
# GET /api/game-history/{game_result_id} — detail
# =============================================================================


class TestGetGameResultDetail:
    """GET /api/game-history/{game_result_id}"""

    @pytest.mark.asyncio
    async def test_get_detail_happy_path(
        self, app, override_current_user, alice, game_result_with_players,
    ):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/game-history/{game_result_with_players.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == "chess"
        assert len(data["players"]) == 2

    @pytest.mark.asyncio
    async def test_get_detail_not_found(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/game-history/9999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_detail_not_participant(
        self, app, override_current_user, carol, game_result_with_players,
    ):
        """Carol was not in the game — should get 404."""
        override_current_user(app, carol)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/game-history/{game_result_with_players.id}")
        assert resp.status_code == 404


# =============================================================================
# GET /api/game-history/user/{user_id} — view another user's history
# =============================================================================


class TestViewOtherUserHistory:
    """GET /api/game-history/user/{user_id}"""

    @pytest.mark.asyncio
    async def test_view_friend_history_all_friends(
        self, app, override_current_user, alice, bob, db_session, game_result_with_players,
    ):
        """Bob's visibility is all_friends, Alice is Bob's friend — should see history."""
        db_session.add(Friendship(user_id=alice.id, friend_id=bob.id))
        db_session.add(Friendship(user_id=bob.id, friend_id=alice.id))
        db_session.add(GameHistoryVisibility(user_id=bob.id, default_visibility="all_friends"))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/game-history/user/{bob.id}")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

    @pytest.mark.asyncio
    async def test_view_non_friend_all_friends_denied(
        self, app, override_current_user, alice, bob, db_session, game_result_with_players,
    ):
        """Bob's visibility is all_friends, Alice is NOT Bob's friend — 403."""
        db_session.add(GameHistoryVisibility(user_id=bob.id, default_visibility="all_friends"))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/game-history/user/{bob.id}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_view_private_history_denied(
        self, app, override_current_user, alice, bob, db_session, game_result_with_players,
    ):
        """Bob's visibility is private — even friends can't see."""
        db_session.add(Friendship(user_id=alice.id, friend_id=bob.id))
        db_session.add(Friendship(user_id=bob.id, friend_id=alice.id))
        db_session.add(GameHistoryVisibility(user_id=bob.id, default_visibility="private"))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/game-history/user/{bob.id}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_view_opponents_only_as_opponent(
        self, app, override_current_user, alice, bob, db_session, game_result_with_players,
    ):
        """Bob's visibility is opponents_only, Alice played against Bob — should see."""
        db_session.add(GameHistoryVisibility(user_id=bob.id, default_visibility="opponents_only"))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/game-history/user/{bob.id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_view_opponents_only_not_opponent(
        self, app, override_current_user, carol, bob, db_session, game_result_with_players,
    ):
        """Bob's visibility is opponents_only, Carol never played Bob — 403."""
        db_session.add(GameHistoryVisibility(user_id=bob.id, default_visibility="opponents_only"))
        await db_session.flush()

        override_current_user(app, carol)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/game-history/user/{bob.id}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_view_default_visibility_is_all_friends(
        self, app, override_current_user, alice, bob, db_session, game_result_with_players,
    ):
        """No visibility row — defaults to all_friends. Friend can see."""
        db_session.add(Friendship(user_id=alice.id, friend_id=bob.id))
        db_session.add(Friendship(user_id=bob.id, friend_id=alice.id))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/game-history/user/{bob.id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_view_nonexistent_user(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/game-history/user/9999")
        assert resp.status_code == 404


# =============================================================================
# PUT /api/game-history/visibility
# =============================================================================


class TestUpdateVisibility:
    """PUT /api/game-history/visibility"""

    @pytest.mark.asyncio
    async def test_set_visibility_creates_new(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put(
                "/api/game-history/visibility",
                json={"default_visibility": "private"},
            )
        assert resp.status_code == 200
        assert resp.json()["default_visibility"] == "private"

    @pytest.mark.asyncio
    async def test_set_visibility_updates_existing(self, app, override_current_user, alice, db_session):
        db_session.add(GameHistoryVisibility(user_id=alice.id, default_visibility="all_friends"))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put(
                "/api/game-history/visibility",
                json={"default_visibility": "opponents_only"},
            )
        assert resp.status_code == 200
        assert resp.json()["default_visibility"] == "opponents_only"

    @pytest.mark.asyncio
    async def test_set_visibility_invalid_value(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put(
                "/api/game-history/visibility",
                json={"default_visibility": "invalid_value"},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_set_visibility_with_game_overrides(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put(
                "/api/game-history/visibility",
                json={
                    "default_visibility": "all_friends",
                    "game_overrides": {"chess": "private"},
                },
            )
        assert resp.status_code == 200
        assert resp.json()["game_overrides"] == {"chess": "private"}
