"""
Tests for session limits auth integration.

Covers:
- Login with session limits -> response includes session_policy
- Login without limits -> no session_policy
- Refresh with expired session -> 401
- Max sessions exceeded -> 403
- Cooldown active -> 429
"""
import pytest
from datetime import datetime, timedelta

from app.models import Group, User
from app.auth_routers.helpers import (
    create_access_token,
    create_refresh_token,
    hash_password,
)
from app.services.session_service import create_session, end_session


@pytest.fixture
async def limited_user(db_session):
    """Create a user in a group with session limits."""
    # Create group with session policy
    group = Group(
        name="LimitedGroup",
        description="Group with session limits",
        is_system=False,
        session_policy={
            "session_timeout_minutes": 30,
            "max_simultaneous_sessions": 2,
            "max_sessions_per_ip": 1,
            "relogin_cooldown_minutes": 5,
            "auto_logout": True,
        },
    )
    db_session.add(group)
    await db_session.flush()

    user = User(
        email="limited@test.com",
        hashed_password=hash_password("Password1"),
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()

    # Add user to group
    from app.models import user_groups
    await db_session.execute(
        user_groups.insert().values(user_id=user.id, group_id=group.id)
    )
    await db_session.flush()

    # Refresh to load relationships
    await db_session.refresh(user)
    return user


@pytest.fixture
async def unlimited_user(db_session):
    """Create a user with no session limits."""
    user = User(
        email="unlimited@test.com",
        hashed_password=hash_password("Password1"),
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    # Eagerly load groups relationship to avoid lazy load in async context
    await db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Session policy resolution in auth context
# ---------------------------------------------------------------------------


class TestSessionPolicyResolution:
    @pytest.mark.asyncio
    async def test_user_with_limits_resolves_policy(self, db_session, limited_user):
        from app.services.session_policy_service import resolve_session_policy, has_any_limits
        policy = resolve_session_policy(limited_user)
        assert has_any_limits(policy) is True
        assert policy["session_timeout_minutes"] == 30
        assert policy["max_simultaneous_sessions"] == 2

    @pytest.mark.asyncio
    async def test_user_without_limits_resolves_empty(self, db_session, unlimited_user):
        from app.services.session_policy_service import resolve_session_policy, has_any_limits
        policy = resolve_session_policy(unlimited_user)
        assert has_any_limits(policy) is False

    @pytest.mark.asyncio
    async def test_user_override_masks_group(self, db_session, limited_user):
        limited_user.session_policy_override = {"session_timeout_minutes": 120}
        from app.services.session_policy_service import resolve_session_policy
        policy = resolve_session_policy(limited_user)
        assert policy["session_timeout_minutes"] == 120
        assert policy["max_simultaneous_sessions"] == 2


# ---------------------------------------------------------------------------
# Token creation with session_id
# ---------------------------------------------------------------------------


class TestTokenSessionId:
    def test_access_token_includes_sid(self):
        from jose import jwt
        from app.config import settings
        token = create_access_token(1, "test@test.com", session_id="test-sid-123")
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        assert payload["sid"] == "test-sid-123"

    def test_access_token_without_sid(self):
        from jose import jwt
        from app.config import settings
        token = create_access_token(1, "test@test.com")
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        assert "sid" not in payload

    def test_refresh_token_includes_sid(self):
        from jose import jwt
        from app.config import settings
        token = create_refresh_token(1, session_id="test-sid-456")
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        assert payload["sid"] == "test-sid-456"

    def test_refresh_token_without_sid(self):
        from jose import jwt
        from app.config import settings
        token = create_refresh_token(1)
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        assert "sid" not in payload


# ---------------------------------------------------------------------------
# Session check during token refresh
# ---------------------------------------------------------------------------


class TestRefreshSessionCheck:
    @pytest.mark.asyncio
    async def test_refresh_with_expired_session_rejects(self, db_session, limited_user):
        """A refresh token with an expired/ended session should fail validation."""
        # Create and end a session
        await create_session(
            user_id=limited_user.id,
            session_id="refresh-test-1",
            ip_address="1.2.3.4",
            user_agent=None,
            expires_at=None,
            db=db_session,
        )
        await end_session("refresh-test-1", db_session)

        from app.services.session_service import check_session_valid
        valid = await check_session_valid("refresh-test-1", db_session)
        assert valid is False

    @pytest.mark.asyncio
    async def test_refresh_with_active_session_succeeds(self, db_session, limited_user):
        """A refresh token with an active session should succeed."""
        await create_session(
            user_id=limited_user.id,
            session_id="refresh-test-2",
            ip_address="1.2.3.4",
            user_agent=None,
            expires_at=datetime.utcnow() + timedelta(hours=1),
            db=db_session,
        )

        from app.services.session_service import check_session_valid
        valid = await check_session_valid("refresh-test-2", db_session)
        assert valid is True


# ---------------------------------------------------------------------------
# Session limits enforcement
# ---------------------------------------------------------------------------


class TestSessionLimitsEnforcement:
    @pytest.mark.asyncio
    async def test_max_sessions_exceeded_blocks_login(self, db_session, limited_user):
        """When max_simultaneous_sessions is reached, new login is denied."""
        from app.services.session_service import check_session_limits
        from fastapi import HTTPException

        # Create 2 sessions (the limit)
        await create_session(
            user_id=limited_user.id, session_id="max-1",
            ip_address="1.2.3.4", user_agent=None, expires_at=None, db=db_session,
        )
        await create_session(
            user_id=limited_user.id, session_id="max-2",
            ip_address="5.6.7.8", user_agent=None, expires_at=None, db=db_session,
        )

        policy = {"max_simultaneous_sessions": 2}
        with pytest.raises(HTTPException) as exc_info:
            await check_session_limits(limited_user.id, "9.10.11.12", policy, db_session)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_cooldown_blocks_relogin(self, db_session, limited_user):
        """Relogin cooldown blocks login from same IP after recent logout."""
        from app.services.session_service import check_session_limits
        from fastapi import HTTPException

        await create_session(
            user_id=limited_user.id, session_id="cd-1",
            ip_address="1.2.3.4", user_agent=None, expires_at=None, db=db_session,
        )
        await end_session("cd-1", db_session)

        policy = {"relogin_cooldown_minutes": 10}
        with pytest.raises(HTTPException) as exc_info:
            await check_session_limits(limited_user.id, "1.2.3.4", policy, db_session)
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_ip_limit_blocks_same_ip(self, db_session, limited_user):
        """Max sessions per IP blocks additional logins from same IP."""
        from app.services.session_service import check_session_limits
        from fastapi import HTTPException

        await create_session(
            user_id=limited_user.id, session_id="ip-limit-1",
            ip_address="1.2.3.4", user_agent=None, expires_at=None, db=db_session,
        )

        policy = {"max_sessions_per_ip": 1}
        with pytest.raises(HTTPException) as exc_info:
            await check_session_limits(limited_user.id, "1.2.3.4", policy, db_session)
        assert exc_info.value.status_code == 403
