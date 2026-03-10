"""
Endpoint-level tests for sessions_router.py.

Covers:
- Listing active sessions (excludes current)
- Terminating specific sessions
- Terminating all other sessions
- Current session protection
- Auth enforcement
- Edge cases (nonexistent sessions)

Uses httpx AsyncClient with ASGITransport and dependency overrides.
"""

from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.models import User
from app.services.session_service import create_session, get_user_sessions


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
async def test_user(db_session):
    """Create a superuser (bypasses permission checks)."""
    user = User(
        email="session-test@test.com",
        hashed_password="fake",
        is_active=True,
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _apply_user_and_sid_overrides(app_instance, user, sid):
    """Override get_current_user and get_current_session_id for a given user/sid."""
    from app.auth.dependencies import get_current_user
    from app.routers.sessions_router import get_current_session_id

    async def _fake_user():
        return user

    async def _fake_sid():
        return sid

    app_instance.dependency_overrides[get_current_user] = _fake_user
    app_instance.dependency_overrides[get_current_session_id] = _fake_sid


# =============================================================================
# Happy path tests
# =============================================================================


class TestListActiveSessions:
    @pytest.mark.asyncio
    async def test_list_active_sessions_empty(self, app, db_session, test_user):
        """User with no other sessions gets empty list."""
        _apply_user_and_sid_overrides(app, test_user, "my-current-sid")

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/sessions/active")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_active_sessions_excludes_current(self, app, db_session, test_user):
        """Creates 2 sessions, one matching the JWT sid; only the other is returned."""
        current_sid = "current-session-id"
        other_sid = "other-session-id"

        await create_session(
            user_id=test_user.id, session_id=current_sid,
            ip_address="10.0.0.1", user_agent="Chrome", expires_at=None, db=db_session,
        )
        await create_session(
            user_id=test_user.id, session_id=other_sid,
            ip_address="10.0.0.2", user_agent="Firefox", expires_at=None, db=db_session,
        )
        await db_session.flush()

        _apply_user_and_sid_overrides(app, test_user, current_sid)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/sessions/active")

        assert resp.status_code == 200
        sessions = resp.json()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == other_sid

    @pytest.mark.asyncio
    async def test_list_active_sessions_returns_details(self, app, db_session, test_user):
        """Verifies ip_address, user_agent, created_at are in response."""
        other_sid = "detail-session"

        await create_session(
            user_id=test_user.id, session_id=other_sid,
            ip_address="192.168.1.100", user_agent="Mozilla/5.0",
            expires_at=None, db=db_session,
        )
        await db_session.flush()

        _apply_user_and_sid_overrides(app, test_user, "my-sid")

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/sessions/active")

        assert resp.status_code == 200
        sessions = resp.json()
        assert len(sessions) == 1
        s = sessions[0]
        assert s["session_id"] == other_sid
        assert s["ip_address"] == "192.168.1.100"
        assert s["user_agent"] == "Mozilla/5.0"
        assert "created_at" in s
        assert s["created_at"] is not None


class TestTerminateSessions:
    @pytest.mark.asyncio
    async def test_terminate_specific_sessions(self, app, db_session, test_user):
        """Create 3 sessions, terminate 2 by ID, verify 1 remains."""
        current_sid = "keep-current"
        sid_a = "terminate-a"
        sid_b = "terminate-b"
        sid_keep = "keep-other"

        for sid in [current_sid, sid_a, sid_b, sid_keep]:
            await create_session(
                user_id=test_user.id, session_id=sid,
                ip_address="10.0.0.1", user_agent=None, expires_at=None, db=db_session,
            )
        await db_session.flush()

        _apply_user_and_sid_overrides(app, test_user, current_sid)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/sessions/terminate",
                json={"session_ids": [sid_a, sid_b]},
            )

        assert resp.status_code == 200
        assert resp.json()["terminated"] == 2

        # Verify remaining active sessions
        remaining = await get_user_sessions(test_user.id, db_session)
        remaining_ids = {s.session_id for s in remaining}
        assert current_sid in remaining_ids
        assert sid_keep in remaining_ids
        assert sid_a not in remaining_ids
        assert sid_b not in remaining_ids

    @pytest.mark.asyncio
    async def test_terminate_others(self, app, db_session, test_user):
        """Create 3 sessions, call terminate-others, verify only current remains."""
        current_sid = "my-session"
        other_a = "other-a"
        other_b = "other-b"

        for sid in [current_sid, other_a, other_b]:
            await create_session(
                user_id=test_user.id, session_id=sid,
                ip_address="10.0.0.1", user_agent=None, expires_at=None, db=db_session,
            )
        await db_session.flush()

        _apply_user_and_sid_overrides(app, test_user, current_sid)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/sessions/terminate-others")

        assert resp.status_code == 200
        assert resp.json()["terminated"] == 2

        remaining = await get_user_sessions(test_user.id, db_session)
        remaining_ids = [s.session_id for s in remaining]
        assert remaining_ids == [current_sid]

    @pytest.mark.asyncio
    async def test_terminate_protects_current_session(self, app, db_session, test_user):
        """Try to terminate own session ID, verify it's still active."""
        current_sid = "protected-session"

        await create_session(
            user_id=test_user.id, session_id=current_sid,
            ip_address="10.0.0.1", user_agent=None, expires_at=None, db=db_session,
        )
        await db_session.flush()

        _apply_user_and_sid_overrides(app, test_user, current_sid)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/sessions/terminate",
                json={"session_ids": [current_sid]},
            )

        assert resp.status_code == 200
        assert resp.json()["terminated"] == 0

        # Verify session is still active
        remaining = await get_user_sessions(test_user.id, db_session)
        assert any(s.session_id == current_sid for s in remaining)


# =============================================================================
# Failure tests
# =============================================================================


class TestSessionsAuthRequired:
    @pytest.mark.asyncio
    async def test_list_sessions_requires_auth(self, app):
        """Unauthenticated request to list sessions gets 401 or 403."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/sessions/active")

        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_terminate_requires_auth(self, app):
        """Unauthenticated request to terminate sessions gets 401 or 403."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/sessions/terminate",
                json={"session_ids": ["some-id"]},
            )

        assert resp.status_code in (401, 403)


class TestTerminateEdgeCases:
    @pytest.mark.asyncio
    async def test_terminate_nonexistent_session(self, app, db_session, test_user):
        """Terminate a session that doesn't exist succeeds with terminated: 0."""
        _apply_user_and_sid_overrides(app, test_user, "my-sid")

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/sessions/terminate",
                json={"session_ids": ["nonexistent-session-id"]},
            )

        assert resp.status_code == 200
        assert resp.json()["terminated"] == 0
