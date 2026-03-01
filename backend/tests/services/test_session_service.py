"""
Tests for session lifecycle service.

Covers:
- create_session: creates record
- end_session: marks inactive + sets ended_at
- check_session_valid: active, inactive, expired
- check_session_limits: max simultaneous, max per IP, relogin cooldown
- expire_stale_sessions_for_user / expire_all_stale_sessions
- get_user_sessions
"""
import pytest
from datetime import datetime, timedelta

from fastapi import HTTPException

from app.models import ActiveSession, User
from app.services.session_service import (
    check_session_limits,
    check_session_valid,
    create_session,
    end_session,
    expire_all_stale_sessions,
    expire_stale_sessions_for_user,
    get_user_sessions,
)


@pytest.fixture
async def test_user(db_session):
    """Create a test user for session tests."""
    user = User(
        email="session-test@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


# ---------------------------------------------------------------------------
# create_session
# ---------------------------------------------------------------------------


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_creates_record(self, db_session, test_user):
        session = await create_session(
            user_id=test_user.id,
            session_id="sess-001",
            ip_address="1.2.3.4",
            user_agent="TestBrowser/1.0",
            expires_at=datetime.utcnow() + timedelta(minutes=30),
            db=db_session,
        )
        assert session.id is not None
        assert session.session_id == "sess-001"
        assert session.user_id == test_user.id
        assert session.ip_address == "1.2.3.4"
        assert session.is_active is True

    @pytest.mark.asyncio
    async def test_creates_without_expiry(self, db_session, test_user):
        session = await create_session(
            user_id=test_user.id,
            session_id="sess-no-exp",
            ip_address=None,
            user_agent=None,
            expires_at=None,
            db=db_session,
        )
        assert session.expires_at is None
        assert session.is_active is True


# ---------------------------------------------------------------------------
# end_session
# ---------------------------------------------------------------------------


class TestEndSession:
    @pytest.mark.asyncio
    async def test_marks_inactive_and_sets_ended_at(self, db_session, test_user):
        await create_session(
            user_id=test_user.id, session_id="sess-end-1",
            ip_address="1.2.3.4", user_agent=None, expires_at=None, db=db_session,
        )
        ended = await end_session("sess-end-1", db_session)
        assert ended is True

        # Verify state
        from sqlalchemy import select
        result = await db_session.execute(
            select(ActiveSession).where(ActiveSession.session_id == "sess-end-1")
        )
        s = result.scalar_one()
        assert s.is_active is False
        assert s.ended_at is not None

    @pytest.mark.asyncio
    async def test_returns_false_for_nonexistent(self, db_session):
        ended = await end_session("nonexistent-id", db_session)
        assert ended is False

    @pytest.mark.asyncio
    async def test_returns_false_for_already_ended(self, db_session, test_user):
        await create_session(
            user_id=test_user.id, session_id="sess-end-2",
            ip_address="1.2.3.4", user_agent=None, expires_at=None, db=db_session,
        )
        await end_session("sess-end-2", db_session)
        # Try ending again
        ended = await end_session("sess-end-2", db_session)
        assert ended is False


# ---------------------------------------------------------------------------
# check_session_valid
# ---------------------------------------------------------------------------


class TestCheckSessionValid:
    @pytest.mark.asyncio
    async def test_active_session_is_valid(self, db_session, test_user):
        await create_session(
            user_id=test_user.id, session_id="sess-valid-1",
            ip_address="1.2.3.4", user_agent=None,
            expires_at=datetime.utcnow() + timedelta(hours=1),
            db=db_session,
        )
        valid = await check_session_valid("sess-valid-1", db_session)
        assert valid is True

    @pytest.mark.asyncio
    async def test_inactive_session_is_invalid(self, db_session, test_user):
        await create_session(
            user_id=test_user.id, session_id="sess-valid-2",
            ip_address="1.2.3.4", user_agent=None, expires_at=None, db=db_session,
        )
        await end_session("sess-valid-2", db_session)
        valid = await check_session_valid("sess-valid-2", db_session)
        assert valid is False

    @pytest.mark.asyncio
    async def test_expired_session_is_invalid(self, db_session, test_user):
        await create_session(
            user_id=test_user.id, session_id="sess-valid-3",
            ip_address="1.2.3.4", user_agent=None,
            expires_at=datetime.utcnow() - timedelta(minutes=1),
            db=db_session,
        )
        valid = await check_session_valid("sess-valid-3", db_session)
        assert valid is False

    @pytest.mark.asyncio
    async def test_nonexistent_session_is_invalid(self, db_session):
        valid = await check_session_valid("does-not-exist", db_session)
        assert valid is False

    @pytest.mark.asyncio
    async def test_session_without_expiry_is_valid(self, db_session, test_user):
        await create_session(
            user_id=test_user.id, session_id="sess-valid-4",
            ip_address="1.2.3.4", user_agent=None,
            expires_at=None, db=db_session,
        )
        valid = await check_session_valid("sess-valid-4", db_session)
        assert valid is True


# ---------------------------------------------------------------------------
# check_session_limits
# ---------------------------------------------------------------------------


class TestCheckSessionLimits:
    @pytest.mark.asyncio
    async def test_max_simultaneous_exceeded_raises_403(self, db_session, test_user):
        # Create 2 active sessions
        await create_session(
            user_id=test_user.id, session_id="lim-1",
            ip_address="1.2.3.4", user_agent=None, expires_at=None, db=db_session,
        )
        await create_session(
            user_id=test_user.id, session_id="lim-2",
            ip_address="5.6.7.8", user_agent=None, expires_at=None, db=db_session,
        )

        policy = {"max_simultaneous_sessions": 2}
        with pytest.raises(HTTPException) as exc_info:
            await check_session_limits(test_user.id, "9.10.11.12", policy, db_session)
        assert exc_info.value.status_code == 403
        assert "Maximum 2 simultaneous sessions" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_max_simultaneous_not_exceeded(self, db_session, test_user):
        await create_session(
            user_id=test_user.id, session_id="lim-ok-1",
            ip_address="1.2.3.4", user_agent=None, expires_at=None, db=db_session,
        )
        policy = {"max_simultaneous_sessions": 5}
        # Should not raise
        await check_session_limits(test_user.id, "1.2.3.4", policy, db_session)

    @pytest.mark.asyncio
    async def test_max_per_ip_exceeded_raises_403(self, db_session, test_user):
        await create_session(
            user_id=test_user.id, session_id="ip-1",
            ip_address="1.2.3.4", user_agent=None, expires_at=None, db=db_session,
        )
        await create_session(
            user_id=test_user.id, session_id="ip-2",
            ip_address="1.2.3.4", user_agent=None, expires_at=None, db=db_session,
        )

        policy = {"max_sessions_per_ip": 2}
        with pytest.raises(HTTPException) as exc_info:
            await check_session_limits(test_user.id, "1.2.3.4", policy, db_session)
        assert exc_info.value.status_code == 403
        assert "Maximum 2 sessions from this IP" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_max_per_ip_different_ip_ok(self, db_session, test_user):
        await create_session(
            user_id=test_user.id, session_id="ip-diff-1",
            ip_address="1.2.3.4", user_agent=None, expires_at=None, db=db_session,
        )

        policy = {"max_sessions_per_ip": 1}
        # Different IP — should not raise
        await check_session_limits(test_user.id, "5.6.7.8", policy, db_session)

    @pytest.mark.asyncio
    async def test_relogin_cooldown_raises_429(self, db_session, test_user):
        # Create and immediately end a session
        await create_session(
            user_id=test_user.id, session_id="cool-1",
            ip_address="1.2.3.4", user_agent=None, expires_at=None, db=db_session,
        )
        await end_session("cool-1", db_session)

        policy = {"relogin_cooldown_minutes": 10}
        with pytest.raises(HTTPException) as exc_info:
            await check_session_limits(test_user.id, "1.2.3.4", policy, db_session)
        assert exc_info.value.status_code == 429
        assert "wait" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_relogin_cooldown_expired_ok(self, db_session, test_user):
        # Create a session and manually set ended_at in the past
        session = await create_session(
            user_id=test_user.id, session_id="cool-past-1",
            ip_address="1.2.3.4", user_agent=None, expires_at=None, db=db_session,
        )
        session.is_active = False
        session.ended_at = datetime.utcnow() - timedelta(minutes=20)

        policy = {"relogin_cooldown_minutes": 10}
        # Should not raise — cooldown has passed
        await check_session_limits(test_user.id, "1.2.3.4", policy, db_session)

    @pytest.mark.asyncio
    async def test_max_per_ip_includes_expiry_hint(self, db_session, test_user):
        """When sessions have expiry times, the error should tell the user when a slot frees up."""
        await create_session(
            user_id=test_user.id, session_id="ip-hint-1",
            ip_address="1.2.3.4", user_agent=None,
            expires_at=datetime.utcnow() + timedelta(minutes=10),
            db=db_session,
        )

        policy = {"max_sessions_per_ip": 1}
        with pytest.raises(HTTPException) as exc_info:
            await check_session_limits(test_user.id, "1.2.3.4", policy, db_session)
        assert exc_info.value.status_code == 403
        assert "session slot will free up" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_max_simultaneous_includes_expiry_hint(self, db_session, test_user):
        """When sessions have expiry times, the error should tell the user when a slot frees up."""
        await create_session(
            user_id=test_user.id, session_id="sim-hint-1",
            ip_address="1.2.3.4", user_agent=None,
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            db=db_session,
        )

        policy = {"max_simultaneous_sessions": 1}
        with pytest.raises(HTTPException) as exc_info:
            await check_session_limits(test_user.id, "5.6.7.8", policy, db_session)
        assert exc_info.value.status_code == 403
        assert "session slot will free up" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_empty_policy_allows_all(self, db_session, test_user):
        # Empty policy = no limits
        await check_session_limits(test_user.id, "1.2.3.4", {}, db_session)

    @pytest.mark.asyncio
    async def test_expired_sessions_reclaimed(self, db_session, test_user):
        """Expired sessions should be cleaned up, freeing slots."""
        await create_session(
            user_id=test_user.id, session_id="exp-1",
            ip_address="1.2.3.4", user_agent=None,
            expires_at=datetime.utcnow() - timedelta(minutes=5),
            db=db_session,
        )
        policy = {"max_simultaneous_sessions": 1}
        # The expired session should be reclaimed, allowing a new one
        await check_session_limits(test_user.id, "1.2.3.4", policy, db_session)


# ---------------------------------------------------------------------------
# expire_stale_sessions_for_user
# ---------------------------------------------------------------------------


class TestExpireStaleSessionsForUser:
    @pytest.mark.asyncio
    async def test_expires_stale_sessions(self, db_session, test_user):
        await create_session(
            user_id=test_user.id, session_id="stale-1",
            ip_address="1.2.3.4", user_agent=None,
            expires_at=datetime.utcnow() - timedelta(minutes=5),
            db=db_session,
        )
        await create_session(
            user_id=test_user.id, session_id="fresh-1",
            ip_address="1.2.3.4", user_agent=None,
            expires_at=datetime.utcnow() + timedelta(hours=1),
            db=db_session,
        )

        await expire_stale_sessions_for_user(test_user.id, db_session)

        from sqlalchemy import select
        result = await db_session.execute(
            select(ActiveSession).where(ActiveSession.session_id == "stale-1")
        )
        stale = result.scalar_one()
        assert stale.is_active is False

        result = await db_session.execute(
            select(ActiveSession).where(ActiveSession.session_id == "fresh-1")
        )
        fresh = result.scalar_one()
        assert fresh.is_active is True


# ---------------------------------------------------------------------------
# expire_all_stale_sessions
# ---------------------------------------------------------------------------


class TestExpireAllStaleSessions:
    @pytest.mark.asyncio
    async def test_bulk_expire(self, db_session, test_user):
        await create_session(
            user_id=test_user.id, session_id="bulk-stale-1",
            ip_address="1.2.3.4", user_agent=None,
            expires_at=datetime.utcnow() - timedelta(minutes=10),
            db=db_session,
        )
        await create_session(
            user_id=test_user.id, session_id="bulk-stale-2",
            ip_address="5.6.7.8", user_agent=None,
            expires_at=datetime.utcnow() - timedelta(minutes=1),
            db=db_session,
        )
        count = await expire_all_stale_sessions(db_session)
        assert count == 2


# ---------------------------------------------------------------------------
# get_user_sessions
# ---------------------------------------------------------------------------


class TestGetUserSessions:
    @pytest.mark.asyncio
    async def test_returns_active_sessions(self, db_session, test_user):
        await create_session(
            user_id=test_user.id, session_id="list-1",
            ip_address="1.2.3.4", user_agent=None, expires_at=None, db=db_session,
        )
        await create_session(
            user_id=test_user.id, session_id="list-2",
            ip_address="5.6.7.8", user_agent=None, expires_at=None, db=db_session,
        )
        # End one
        await end_session("list-1", db_session)

        sessions = await get_user_sessions(test_user.id, db_session)
        assert len(sessions) == 1
        assert sessions[0].session_id == "list-2"
