"""
Tests for backend/app/auth_routers/password_router.py

Covers the /forgot-password and /reset-password endpoints:
- Happy path
- Non-existent email returns generic success (no user enumeration)
- Expired / already-used / forged reset tokens
- Cross-user token isolation (user A's token cannot reset user B)
- tokens_valid_after is bumped on reset so old JWTs stop working (v2.26.3)
"""

from datetime import timedelta
from app.utils.timeutil import utcnow
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.auth_routers.helpers import verify_password
from app.auth_routers.rate_limiters import _CATEGORY_STORE, _warmed
from app.auth_routers.schemas import ForgotPasswordRequest, ResetPasswordRequest
from app.models import EmailVerificationToken, User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state():
    """Clear the auth rate-limit in-memory buckets between tests."""
    for store in _CATEGORY_STORE.values():
        store.clear()
    _warmed.clear()
    yield


def _mock_http_request(ip: str = "127.0.0.1"):
    """Build a minimal Request-like mock with the headers the router reads."""
    req = MagicMock()
    req.headers = {"X-Forwarded-For": ip}
    req.client = MagicMock()
    req.client.host = ip
    return req


async def _mk_user(db_session, email: str = "alice@example.com") -> User:
    user = User(
        email=email,
        hashed_password="$2b$12$fakefakefakefakefakeufakefakefakefakefakefakefakefa",
        is_active=True,
        is_superuser=False,
        created_at=utcnow(),
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _mk_reset_token(
    db_session, user_id: int, *, used: bool = False, expires_in_hours: float = 1
) -> EmailVerificationToken:
    token = EmailVerificationToken(
        user_id=user_id,
        token=f"reset-{user_id}-{int(utcnow().timestamp())}",
        token_type="password_reset",
        expires_at=utcnow() + timedelta(hours=expires_in_hours),
        used_at=utcnow() if used else None,
    )
    db_session.add(token)
    await db_session.flush()
    return token


# ---------------------------------------------------------------------------
# POST /forgot-password
# ---------------------------------------------------------------------------


class TestForgotPassword:
    @pytest.mark.asyncio
    @patch("app.auth_routers.password_router.send_password_reset_email", create=True)
    async def test_existing_user_creates_reset_token(self, _mock_send, db_session):
        """Happy path: known email creates a password_reset token row."""
        # Patch the email sender at the import site inside the function.
        with patch("app.services.email_service.send_password_reset_email"):
            from app.auth_routers.password_router import forgot_password
            user = await _mk_user(db_session, "known@example.com")

            result = await forgot_password(
                request=ForgotPasswordRequest(email=user.email),
                http_request=_mock_http_request(),
                db=db_session,
            )
        assert "sent a password reset link" in result["message"]

        tokens = (await db_session.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.user_id == user.id,
                EmailVerificationToken.token_type == "password_reset",
            )
        )).scalars().all()
        assert len(tokens) == 1
        assert tokens[0].used_at is None
        assert tokens[0].expires_at > utcnow()

    @pytest.mark.asyncio
    async def test_unknown_email_returns_generic_success(self, db_session):
        """No-such-email returns the same success message (no enumeration)."""
        from app.auth_routers.password_router import forgot_password

        result = await forgot_password(
            request=ForgotPasswordRequest(email="nobody@example.com"),
            http_request=_mock_http_request(),
            db=db_session,
        )
        assert "sent a password reset link" in result["message"]
        # And no token was created.
        tokens = (await db_session.execute(
            select(EmailVerificationToken)
        )).scalars().all()
        assert tokens == []

    @pytest.mark.asyncio
    async def test_repeat_requests_clear_old_unused_tokens(self, db_session):
        """Second request deletes the first unused token (prevents stockpiling)."""
        with patch("app.services.email_service.send_password_reset_email"):
            from app.auth_routers.password_router import forgot_password
            user = await _mk_user(db_session, "repeater@example.com")
            await _mk_reset_token(db_session, user.id)

            await forgot_password(
                request=ForgotPasswordRequest(email=user.email),
                http_request=_mock_http_request(),
                db=db_session,
            )

        tokens = (await db_session.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.user_id == user.id,
                EmailVerificationToken.token_type == "password_reset",
                EmailVerificationToken.used_at.is_(None),
            )
        )).scalars().all()
        # Only the newly-created token should remain.
        assert len(tokens) == 1


# ---------------------------------------------------------------------------
# POST /reset-password
# ---------------------------------------------------------------------------


class TestResetPassword:
    @pytest.mark.asyncio
    async def test_valid_token_resets_password(self, db_session):
        """Happy path: valid token resets password, bumps tokens_valid_after, marks token used."""
        from app.auth_routers.password_router import reset_password

        user = await _mk_user(db_session, "reset-happy@example.com")
        token = await _mk_reset_token(db_session, user.id)

        before_ts = utcnow() - timedelta(seconds=1)
        result = await reset_password(
            request=ResetPasswordRequest(token=token.token, new_password="NewP@ssword1"),
            db=db_session,
        )
        assert "reset successfully" in result["message"].lower()

        await db_session.refresh(user)
        await db_session.refresh(token)
        assert verify_password("NewP@ssword1", user.hashed_password)
        # tokens_valid_after must be bumped so any prior JWT stops validating.
        assert user.tokens_valid_after is not None
        assert user.tokens_valid_after >= before_ts
        # The token row is single-use — must now be marked used.
        assert token.used_at is not None

    @pytest.mark.asyncio
    async def test_forged_token_returns_400(self, db_session):
        """A token that doesn't exist in the DB is rejected."""
        from app.auth_routers.password_router import reset_password

        with pytest.raises(HTTPException) as exc:
            await reset_password(
                request=ResetPasswordRequest(token="not-a-real-token", new_password="NewP@ssword1"),
                db=db_session,
            )
        assert exc.value.status_code == 400
        assert "invalid" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_expired_token_returns_400(self, db_session):
        """Tokens past expires_at are rejected with a dedicated message."""
        from app.auth_routers.password_router import reset_password

        user = await _mk_user(db_session, "expired@example.com")
        token = await _mk_reset_token(db_session, user.id, expires_in_hours=-1)

        with pytest.raises(HTTPException) as exc:
            await reset_password(
                request=ResetPasswordRequest(token=token.token, new_password="NewP@ssword1"),
                db=db_session,
            )
        assert exc.value.status_code == 400
        assert "expired" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_reused_token_returns_400(self, db_session):
        """A token that has already been consumed is rejected."""
        from app.auth_routers.password_router import reset_password

        user = await _mk_user(db_session, "reused@example.com")
        token = await _mk_reset_token(db_session, user.id, used=True)

        with pytest.raises(HTTPException) as exc:
            await reset_password(
                request=ResetPasswordRequest(token=token.token, new_password="NewP@ssword1"),
                db=db_session,
            )
        assert exc.value.status_code == 400
        assert "already been used" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_user_a_token_only_resets_user_a(self, db_session):
        """Cross-user isolation: User A's reset token resets A, never B."""
        from app.auth_routers.password_router import reset_password

        user_a = await _mk_user(db_session, "a@example.com")
        user_b = await _mk_user(db_session, "b@example.com")
        original_b_hash = user_b.hashed_password
        token_a = await _mk_reset_token(db_session, user_a.id)

        await reset_password(
            request=ResetPasswordRequest(token=token_a.token, new_password="NewP@ssword1"),
            db=db_session,
        )
        await db_session.refresh(user_a)
        await db_session.refresh(user_b)

        assert verify_password("NewP@ssword1", user_a.hashed_password)
        # User B's hash must be untouched.
        assert user_b.hashed_password == original_b_hash
        assert user_b.tokens_valid_after is None
