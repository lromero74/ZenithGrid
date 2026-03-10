"""
Endpoint-level tests for tournament_router.py.

Uses httpx AsyncClient with ASGITransport and dependency overrides.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models import User
from app.models.social import (
    Tournament,
    TournamentDeleteVote,
    TournamentPlayer,
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
def override_multiplayer_perm():
    """Factory to override require_permission(Perm.GAMES_MULTIPLAYER) with a specific user."""
    def _override(app_instance, user):
        from app.auth.dependencies import require_permission, Perm

        perm_dep = require_permission(Perm.GAMES_MULTIPLAYER)

        async def _fake():
            return user
        app_instance.dependency_overrides[perm_dep] = _fake
    return _override


@pytest.fixture
async def alice(db_session):
    user = User(
        email="alice@test.com", hashed_password="fake",
        display_name="Alice", is_active=True, is_superuser=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def bob(db_session):
    user = User(
        email="bob@test.com", hashed_password="fake",
        display_name="Bob", is_active=True, is_superuser=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def carol(db_session):
    user = User(
        email="carol@test.com", hashed_password="fake",
        display_name="Carol", is_active=True, is_superuser=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def tournament(db_session, alice):
    """Create a pending tournament owned by Alice."""
    t = Tournament(
        name="Chess Championship",
        creator_id=alice.id,
        game_ids=["chess"],
        status="pending",
    )
    db_session.add(t)
    await db_session.flush()
    # Creator auto-joins
    db_session.add(TournamentPlayer(tournament_id=t.id, user_id=alice.id))
    await db_session.flush()
    return t


# =============================================================================
# POST /api/tournaments — create
# =============================================================================


class TestCreateTournament:
    """POST /api/tournaments"""

    @pytest.mark.asyncio
    async def test_create_tournament_happy_path(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/tournaments", json={
                "name": "My Tournament",
                "game_ids": ["chess", "checkers"],
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "My Tournament"
        assert data["status"] == "pending"
        assert data["creator_id"] == alice.id

    @pytest.mark.asyncio
    async def test_create_tournament_missing_name(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/tournaments", json={
                "game_ids": ["chess"],
            })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_tournament_empty_game_ids(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/tournaments", json={
                "name": "Empty Games",
                "game_ids": [],
            })
        assert resp.status_code == 422


# =============================================================================
# GET /api/tournaments — list
# =============================================================================


class TestListTournaments:
    """GET /api/tournaments"""

    @pytest.mark.asyncio
    async def test_list_empty(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/tournaments")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_shows_joined_tournaments(self, app, override_current_user, alice, tournament):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/tournaments")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Chess Championship"
        # W6: Verify computed fields
        assert data[0]["creator_name"] == "Alice"
        assert data[0]["player_count"] == 1

    @pytest.mark.asyncio
    async def test_list_excludes_archived(self, app, override_current_user, alice, tournament, db_session):
        # Archive alice's tournament player entry
        result = await db_session.execute(
            select(TournamentPlayer).where(
                TournamentPlayer.tournament_id == tournament.id,
                TournamentPlayer.user_id == alice.id,
            )
        )
        tp = result.scalar_one()
        tp.archived = True
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/tournaments")
        assert resp.status_code == 200
        assert len(resp.json()) == 0


# =============================================================================
# GET /api/tournaments/{id} — detail
# =============================================================================


class TestGetTournamentDetail:
    """GET /api/tournaments/{id}"""

    @pytest.mark.asyncio
    async def test_get_detail_happy_path(self, app, override_current_user, alice, tournament):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/tournaments/{tournament.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Chess Championship"
        assert len(data["players"]) == 1

    @pytest.mark.asyncio
    async def test_get_detail_not_found(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/tournaments/9999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_detail_non_participant_denied(self, app, override_current_user, bob, tournament):
        """Bob is not in the tournament — W8: should get 403."""
        override_current_user(app, bob)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/tournaments/{tournament.id}")
        assert resp.status_code == 403


# =============================================================================
# POST /api/tournaments/{id}/join
# =============================================================================


class TestJoinTournament:
    """POST /api/tournaments/{id}/join"""

    @pytest.mark.asyncio
    async def test_join_happy_path(self, app, override_current_user, bob, tournament):
        override_current_user(app, bob)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tournaments/{tournament.id}/join")
        assert resp.status_code == 200
        assert resp.json()["status"] == "joined"

    @pytest.mark.asyncio
    async def test_join_already_joined(self, app, override_current_user, alice, tournament):
        """Alice is already in the tournament."""
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tournaments/{tournament.id}/join")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_join_active_tournament_rejected(
        self, app, override_current_user, bob, tournament, db_session,
    ):
        """Cannot join a tournament that's already started."""
        tournament.status = "active"
        await db_session.flush()

        override_current_user(app, bob)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tournaments/{tournament.id}/join")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_join_nonexistent_tournament(self, app, override_current_user, bob):
        override_current_user(app, bob)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/tournaments/9999/join")
        assert resp.status_code == 404


# =============================================================================
# POST /api/tournaments/{id}/leave
# =============================================================================


class TestLeaveTournament:
    """POST /api/tournaments/{id}/leave"""

    @pytest.mark.asyncio
    async def test_leave_pending_tournament(self, app, override_current_user, bob, tournament, db_session):
        db_session.add(TournamentPlayer(tournament_id=tournament.id, user_id=bob.id))
        await db_session.flush()

        override_current_user(app, bob)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tournaments/{tournament.id}/leave")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_leave_active_tournament_rejected(
        self, app, override_current_user, alice, tournament, db_session,
    ):
        tournament.status = "active"
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tournaments/{tournament.id}/leave")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_leave_not_joined(self, app, override_current_user, carol, tournament):
        override_current_user(app, carol)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tournaments/{tournament.id}/leave")
        assert resp.status_code == 404


# =============================================================================
# POST /api/tournaments/{id}/start
# =============================================================================


class TestStartTournament:
    """POST /api/tournaments/{id}/start"""

    @pytest.mark.asyncio
    async def test_start_happy_path(
        self, app, override_current_user, alice, bob, tournament, db_session,
    ):
        db_session.add(TournamentPlayer(tournament_id=tournament.id, user_id=bob.id))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tournaments/{tournament.id}/start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    @pytest.mark.asyncio
    async def test_start_not_creator(self, app, override_current_user, bob, tournament, db_session):
        db_session.add(TournamentPlayer(tournament_id=tournament.id, user_id=bob.id))
        await db_session.flush()

        override_current_user(app, bob)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tournaments/{tournament.id}/start")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_start_already_active(self, app, override_current_user, alice, tournament, db_session):
        tournament.status = "active"
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tournaments/{tournament.id}/start")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_start_needs_at_least_two_players(
        self, app, override_current_user, alice, tournament,
    ):
        """Tournament with only one player should not start."""
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tournaments/{tournament.id}/start")
        assert resp.status_code == 400


# =============================================================================
# POST /api/tournaments/{id}/archive
# =============================================================================


class TestArchiveTournament:
    """POST /api/tournaments/{id}/archive"""

    @pytest.mark.asyncio
    async def test_archive_happy_path(self, app, override_current_user, alice, tournament):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tournaments/{tournament.id}/archive")
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    @pytest.mark.asyncio
    async def test_archive_not_participant(self, app, override_current_user, carol, tournament):
        override_current_user(app, carol)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tournaments/{tournament.id}/archive")
        assert resp.status_code == 404


# =============================================================================
# POST /api/tournaments/{id}/vote-delete
# =============================================================================


class TestVoteDelete:
    """POST /api/tournaments/{id}/vote-delete"""

    @pytest.mark.asyncio
    async def test_vote_delete_single_vote(self, app, override_current_user, alice, bob, tournament, db_session):
        db_session.add(TournamentPlayer(tournament_id=tournament.id, user_id=bob.id))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tournaments/{tournament.id}/vote-delete")
        assert resp.status_code == 200
        data = resp.json()
        assert data["votes"] == 1
        assert data["deleted"] is False

    @pytest.mark.asyncio
    async def test_vote_delete_majority_deletes(
        self, app, override_current_user, alice, bob, tournament, db_session,
    ):
        """With 2 players, both must vote to delete (majority = > half)."""
        db_session.add(TournamentPlayer(tournament_id=tournament.id, user_id=bob.id))
        db_session.add(TournamentDeleteVote(tournament_id=tournament.id, user_id=alice.id))
        await db_session.flush()

        override_current_user(app, bob)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tournaments/{tournament.id}/vote-delete")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    @pytest.mark.asyncio
    async def test_vote_delete_duplicate_vote(self, app, override_current_user, alice, tournament, db_session):
        db_session.add(TournamentDeleteVote(tournament_id=tournament.id, user_id=alice.id))
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tournaments/{tournament.id}/vote-delete")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_vote_delete_not_participant(self, app, override_current_user, carol, tournament):
        override_current_user(app, carol)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/tournaments/{tournament.id}/vote-delete")
        assert resp.status_code == 404


# =============================================================================
# GET /api/tournaments/{id}/standings
# =============================================================================


class TestTournamentStandings:
    """GET /api/tournaments/{id}/standings"""

    @pytest.mark.asyncio
    async def test_standings_happy_path(self, app, override_current_user, alice, bob, tournament, db_session):
        db_session.add(TournamentPlayer(tournament_id=tournament.id, user_id=bob.id, total_score=50))
        await db_session.flush()

        # Update alice's score
        result = await db_session.execute(
            select(TournamentPlayer).where(
                TournamentPlayer.tournament_id == tournament.id,
                TournamentPlayer.user_id == alice.id,
            )
        )
        alice_tp = result.scalar_one()
        alice_tp.total_score = 100
        await db_session.flush()

        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/tournaments/{tournament.id}/standings")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Highest score first
        assert data[0]["total_score"] == 100
        assert data[0]["rank"] == 1
        assert data[1]["rank"] == 2

    @pytest.mark.asyncio
    async def test_standings_not_found(self, app, override_current_user, alice):
        override_current_user(app, alice)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/tournaments/9999/standings")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_standings_non_participant_denied(self, app, override_current_user, carol, tournament):
        """W8: Non-participants cannot view standings."""
        override_current_user(app, carol)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/tournaments/{tournament.id}/standings")
        assert resp.status_code == 403
