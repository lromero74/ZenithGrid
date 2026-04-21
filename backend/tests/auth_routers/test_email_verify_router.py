"""
Tests for backend/app/auth_routers/email_verify_router.py

Covers /verify-email, /resend-verification, /verify-email-code:
- Happy path
- Expired / used / forged tokens
- Cross-user isolation: user A's verify token cannot verify user B
- verify-email-code: must only accept a code bound to the caller
- resend-verification: rate limit + already-verified short-circuit
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.auth_routers.rate_limiters import _CATEGORY_STORE, _warmed
from app.auth_routers.schemas import VerifyEmailCodeRequest, VerifyEmailRequest
from app.models import EmailVerificationToken, User


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state():
    for store in _CATEGORY_STORE.values():
        store.clear()
    _warmed.clear()
    yield


async def _mk_user(db_session, email: str, verified: bool = False) -> User:
    user = User(
        email=email,
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        email_verified=verified,
        email_verified_at=datetime.utcnow() if verified else None,
        created_at=datetime.utcnow(),
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _mk_verify_token(
    db_session,
    user_id: int,
    *,
    token: str = "verify-token-1",
    code: str = "123456",
    used: bool = False,
    expires_in_hours: float = 24,
) -> EmailVerificationToken:
    rec = EmailVerificationToken(
        user_id=user_id,
        token=token,
        verification_code=code,
        token_type="email_verify",
        expires_at=datetime.utcnow() + timedelta(hours=expires_in_hours),
        used_at=datetime.utcnow() if used else None,
    )
    db_session.add(rec)
    await db_session.flush()
    return rec


# ---------------------------------------------------------------------------
# POST /verify-email (token click from email link)
# ---------------------------------------------------------------------------


class TestVerifyEmail:
    @pytest.mark.asyncio
    async def test_valid_token_verifies_user(self, db_session):
        from app.auth_routers.email_verify_router import verify_email

        user = await _mk_user(db_session, "happy@example.com")
        token = await _mk_verify_token(db_session, user.id, token="t-happy")

        result = await verify_email(
            request=VerifyEmailRequest(token=token.token),
            db=db_session,
        )
        assert result.email_verified is True

        await db_session.refresh(user)
        await db_session.refresh(token)
        assert user.email_verified is True
        assert user.email_verified_at is not None
        assert token.used_at is not None

    @pytest.mark.asyncio
    async def test_forged_token_returns_400(self, db_session):
        from app.auth_routers.email_verify_router import verify_email

        with pytest.raises(HTTPException) as exc:
            await verify_email(
                request=VerifyEmailRequest(token="no-such-token"),
                db=db_session,
            )
        assert exc.value.status_code == 400
        assert "invalid" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_expired_token_returns_400(self, db_session):
        from app.auth_routers.email_verify_router import verify_email

        user = await _mk_user(db_session, "expired@example.com")
        token = await _mk_verify_token(db_session, user.id, token="t-exp", expires_in_hours=-1)

        with pytest.raises(HTTPException) as exc:
            await verify_email(
                request=VerifyEmailRequest(token=token.token),
                db=db_session,
            )
        assert exc.value.status_code == 400
        assert "expired" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_used_token_returns_400(self, db_session):
        from app.auth_routers.email_verify_router import verify_email

        user = await _mk_user(db_session, "used@example.com")
        token = await _mk_verify_token(db_session, user.id, token="t-used", used=True)

        with pytest.raises(HTTPException) as exc:
            await verify_email(
                request=VerifyEmailRequest(token=token.token),
                db=db_session,
            )
        assert exc.value.status_code == 400
        assert "already been used" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_user_a_token_never_verifies_user_b(self, db_session):
        """Cross-user isolation: a token bound to user A only verifies A."""
        from app.auth_routers.email_verify_router import verify_email

        user_a = await _mk_user(db_session, "a@example.com")
        user_b = await _mk_user(db_session, "b@example.com")
        token_a = await _mk_verify_token(db_session, user_a.id, token="t-a")

        await verify_email(
            request=VerifyEmailRequest(token=token_a.token),
            db=db_session,
        )
        await db_session.refresh(user_a)
        await db_session.refresh(user_b)
        assert user_a.email_verified is True
        assert user_b.email_verified is False


# ---------------------------------------------------------------------------
# POST /resend-verification (authenticated)
# ---------------------------------------------------------------------------


class TestResendVerification:
    @pytest.mark.asyncio
    async def test_already_verified_user_gets_400(self, db_session):
        from app.auth_routers.email_verify_router import resend_verification

        user = await _mk_user(db_session, "already@example.com", verified=True)
        with pytest.raises(HTTPException) as exc:
            await resend_verification(current_user=user, db=db_session)
        assert exc.value.status_code == 400
        assert "already verified" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_creates_fresh_token_and_clears_old(self, db_session):
        from app.auth_routers.email_verify_router import resend_verification

        user = await _mk_user(db_session, "resend@example.com")
        old = await _mk_verify_token(db_session, user.id, token="old-t")

        with patch("app.services.email_service.send_verification_email"):
            await resend_verification(current_user=user, db=db_session)

        tokens = (await db_session.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.user_id == user.id,
                EmailVerificationToken.token_type == "email_verify",
                EmailVerificationToken.used_at.is_(None),
            )
        )).scalars().all()
        assert len(tokens) == 1
        assert tokens[0].token != old.token  # fresh token, not the previous one

    @pytest.mark.asyncio
    async def test_rate_limit_fires_after_3_attempts(self, db_session):
        """Per-user rate limit: 3 resends / hour; 4th raises 429."""
        from app.auth_routers.email_verify_router import resend_verification

        user = await _mk_user(db_session, "ratelimit@example.com")

        with patch("app.services.email_service.send_verification_email"):
            for _ in range(3):
                await resend_verification(current_user=user, db=db_session)
            with pytest.raises(HTTPException) as exc:
                await resend_verification(current_user=user, db=db_session)
        assert exc.value.status_code == 429


# ---------------------------------------------------------------------------
# POST /verify-email-code (authenticated, 6-digit code)
# ---------------------------------------------------------------------------


class TestVerifyEmailCode:
    @pytest.mark.asyncio
    async def test_correct_code_verifies_caller(self, db_session):
        from app.auth_routers.email_verify_router import verify_email_code

        user = await _mk_user(db_session, "code@example.com")
        token = await _mk_verify_token(db_session, user.id, token="c-t", code="424242")

        result = await verify_email_code(
            request=VerifyEmailCodeRequest(code="424242"),
            current_user=user,
            db=db_session,
        )
        assert result.email_verified is True

        await db_session.refresh(user)
        await db_session.refresh(token)
        assert user.email_verified is True
        assert token.used_at is not None

    @pytest.mark.asyncio
    async def test_wrong_code_returns_400(self, db_session):
        from app.auth_routers.email_verify_router import verify_email_code

        user = await _mk_user(db_session, "wrongcode@example.com")
        await _mk_verify_token(db_session, user.id, token="c-t2", code="111111")

        with pytest.raises(HTTPException) as exc:
            await verify_email_code(
                request=VerifyEmailCodeRequest(code="222222"),
                current_user=user,
                db=db_session,
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_user_b_cannot_reuse_user_a_code(self, db_session):
        """Cross-user isolation: user B submitting user A's code is rejected."""
        from app.auth_routers.email_verify_router import verify_email_code

        user_a = await _mk_user(db_session, "a-code@example.com")
        user_b = await _mk_user(db_session, "b-code@example.com")
        await _mk_verify_token(db_session, user_a.id, token="a-code-t", code="999111")

        with pytest.raises(HTTPException) as exc:
            await verify_email_code(
                request=VerifyEmailCodeRequest(code="999111"),
                current_user=user_b,
                db=db_session,
            )
        assert exc.value.status_code == 400

        await db_session.refresh(user_b)
        assert user_b.email_verified is False
