"""
Password reset endpoints: forgot-password, reset-password.
"""

import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_user_by_id
from app.config import settings
from app.database import get_db
from app.models import EmailVerificationToken

from app.auth_routers.helpers import get_user_by_email, hash_password
from app.auth_routers.rate_limiters import (
    _check_forgot_pw_rate_limit,
    _is_forgot_pw_email_rate_limited,
    _record_forgot_pw_attempt,
    _record_forgot_pw_email_attempt,
)
from app.auth_routers.schemas import ForgotPasswordRequest, ResetPasswordRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Send password reset email. Always returns success to avoid leaking email existence.
    """
    client_ip = http_request.client.host if http_request.client else "unknown"
    _check_forgot_pw_rate_limit(client_ip)
    _record_forgot_pw_attempt(client_ip)

    # Always return the same message regardless of whether email exists
    success_message = {"message": "If an account exists with that email, we've sent a password reset link."}

    # S15: Per-email rate limiting — silently return success to avoid leaking
    email_lower = request.email.lower()
    if _is_forgot_pw_email_rate_limited(email_lower):
        return success_message
    _record_forgot_pw_email_attempt(email_lower)

    user = await get_user_by_email(db, email_lower)
    if not user:
        return success_message

    # Delete old unused reset tokens for this user
    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.token_type == "password_reset",
            EmailVerificationToken.used_at.is_(None),
        )
    )
    old_tokens = result.scalars().all()
    for old_token in old_tokens:
        await db.delete(old_token)

    # Generate reset token (1 hour expiry)
    token_str = uuid.uuid4().hex
    reset_token = EmailVerificationToken(
        user_id=user.id,
        token=token_str,
        token_type="password_reset",
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    db.add(reset_token)
    await db.commit()

    # Send reset email
    try:
        from app.services.email_service import send_password_reset_email
        reset_url = f"{settings.frontend_url}/reset-password?token={token_str}"
        send_password_reset_email(
            to=user.email,
            reset_url=reset_url,
            display_name=user.display_name or "",
        )
    except Exception as e:
        logger.error(f"Failed to send password reset email to {user.email}: {e}")

    return success_message


@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Reset password using a token from the reset email.
    Invalidates all existing sessions by updating updated_at.
    """
    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token == request.token,
            EmailVerificationToken.token_type == "password_reset",
        )
    )
    token_record = result.scalar_one_or_none()

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    if token_record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has already been used.",
        )

    if token_record.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has expired. Please request a new one.",
        )

    user = await get_user_by_id(db, token_record.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    # Update password and invalidate all existing sessions
    user.hashed_password = hash_password(request.new_password)
    user.updated_at = datetime.utcnow()
    user.tokens_valid_after = datetime.utcnow()
    token_record.used_at = datetime.utcnow()

    await db.commit()

    logger.info(f"Password reset for user: {user.email} — all sessions invalidated")

    return {"message": "Password reset successfully. Please log in with your new password."}
