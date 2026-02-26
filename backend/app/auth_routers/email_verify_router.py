"""
Email verification endpoints: verify-email, resend-verification, verify-email-code.
"""

import logging
import random
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_user_by_id
from app.config import settings
from app.database import get_db
from app.models import EmailVerificationToken, User

from app.auth_routers.helpers import _build_user_response
from app.auth_routers.rate_limiters import _check_resend_rate_limit, _record_resend_attempt
from app.auth_routers.schemas import UserResponse, VerifyEmailCodeRequest, VerifyEmailRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/verify-email", response_model=UserResponse)
async def verify_email(
    request: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify a user's email address using a token from the verification email.

    No auth required — user clicks link from email (may be in a different browser tab).
    """
    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token == request.token,
            EmailVerificationToken.token_type == "email_verify",
        )
    )
    token_record = result.scalar_one_or_none()

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification token.",
        )

    if token_record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link has already been used.",
        )

    if token_record.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link has expired. Please request a new one.",
        )

    # Mark token as used and verify user
    token_record.used_at = datetime.utcnow()
    user = await get_user_by_id(db, token_record.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    user.email_verified = True
    user.email_verified_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)

    logger.info(f"Email verified for user: {user.email}")

    return _build_user_response(user)


@router.post("/resend-verification")
async def resend_verification(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Resend email verification link. Rate limited to 3 per user per hour.
    """
    if current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified.",
        )

    _check_resend_rate_limit(current_user.id)
    _record_resend_attempt(current_user.id)

    # Delete old unused tokens for this user
    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == current_user.id,
            EmailVerificationToken.token_type == "email_verify",
            EmailVerificationToken.used_at.is_(None),
        )
    )
    old_tokens = result.scalars().all()
    for old_token in old_tokens:
        await db.delete(old_token)

    # Generate new token + 6-digit code
    token_str = uuid.uuid4().hex
    verify_code = f"{random.randint(0, 999999):06d}"
    verification_token = EmailVerificationToken(
        user_id=current_user.id,
        token=token_str,
        verification_code=verify_code,
        token_type="email_verify",
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.add(verification_token)
    await db.commit()

    # Send email
    try:
        from app.services.email_service import send_verification_email
        verification_url = f"{settings.frontend_url}/verify-email?token={token_str}"
        send_verification_email(
            to=current_user.email,
            verification_url=verification_url,
            display_name=current_user.display_name or "",
            verification_code=verify_code,
        )
    except Exception as e:
        logger.error(f"Failed to resend verification email to {current_user.email}: {e}")

    return {"message": "Verification email sent. Please check your inbox."}


@router.post("/verify-email-code", response_model=UserResponse)
async def verify_email_code(
    request: VerifyEmailCodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Verify email using a 6-digit code (entered by authenticated user).

    Alternative to clicking the email link — user can type the code
    shown in the verification email directly in the app.
    """
    if current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified.",
        )

    # Find an unused verification token with matching code for this user
    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == current_user.id,
            EmailVerificationToken.token_type == "email_verify",
            EmailVerificationToken.verification_code == request.code,
            EmailVerificationToken.used_at.is_(None),
        )
    )
    token_record = result.scalar_one_or_none()

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code.",
        )

    if token_record.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This code has expired. Please request a new one.",
        )

    # Mark token as used and verify user
    token_record.used_at = datetime.utcnow()
    current_user.email_verified = True
    current_user.email_verified_at = datetime.utcnow()
    await db.commit()
    await db.refresh(current_user)

    logger.info(f"Email verified via code for user: {current_user.email}")

    return _build_user_response(current_user)
