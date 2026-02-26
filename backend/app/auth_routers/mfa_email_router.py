"""
Email MFA endpoints: verify-email-code, verify-email-link, email/enable, email/disable, resend-email.
"""

import logging
import random
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_user_by_id
from app.config import settings
from app.database import get_db
from app.models import EmailVerificationToken, User

from app.auth_routers.helpers import (
    _build_user_response,
    _complete_mfa_login,
    _decode_mfa_token,
    verify_password,
)
from app.auth_routers.rate_limiters import _check_mfa_rate_limit, _record_mfa_attempt
from app.auth_routers.schemas import (
    LoginResponse,
    MFAEmailCodeRequest,
    MFAEmailDisableRequest,
    MFAEmailEnableRequest,
    MFAEmailLinkRequest,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/mfa/verify-email-code", response_model=LoginResponse)
async def mfa_verify_email_code(
    request: MFAEmailCodeRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify email code during login to complete MFA challenge.

    Called after /login returns mfa_required=true with "email_code" in mfa_methods.
    User enters the 6-digit code from their email.
    """
    # S3: Rate limit MFA attempts per token
    _check_mfa_rate_limit(request.mfa_token)
    _record_mfa_attempt(request.mfa_token)

    user_id = await _decode_mfa_token(request.mfa_token)
    user = await get_user_by_id(db, user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled.",
        )

    # Find matching unused MFA email token with this code
    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user_id,
            EmailVerificationToken.token_type == "mfa_email",
            EmailVerificationToken.verification_code == request.email_code,
            EmailVerificationToken.used_at.is_(None),
        )
    )
    token_record = result.scalar_one_or_none()

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification code.",
        )

    if token_record.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verification code has expired. Please login again.",
        )

    # Mark token as used
    token_record.used_at = datetime.utcnow()
    await db.commit()

    logger.info(f"MFA email code verified, user logged in: {user.email}")

    return await _complete_mfa_login(user, request.remember_device, http_request, db)


@router.post("/mfa/verify-email-link", response_model=LoginResponse)
async def mfa_verify_email_link(
    request: MFAEmailLinkRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify MFA via email link click.

    No mfa_token needed — user clicked a link from their email.
    The token in the URL identifies the user and MFA session.
    """
    # Find the token record
    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token == request.token,
            EmailVerificationToken.token_type == "mfa_email",
        )
    )
    token_record = result.scalar_one_or_none()

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification link.",
        )

    if token_record.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link has already been used.",
        )

    if token_record.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This verification link has expired. Please login again.",
        )

    user = await get_user_by_id(db, token_record.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled.",
        )

    # Mark token as used
    token_record.used_at = datetime.utcnow()
    await db.commit()

    logger.info(f"MFA email link verified, user logged in: {user.email}")

    return await _complete_mfa_login(user, request.remember_device, http_request, db)


@router.post("/mfa/email/enable", response_model=UserResponse)
async def mfa_email_enable(
    request: MFAEmailEnableRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Enable email-based MFA for the current user.

    Requires password confirmation. User must have a verified email address.
    """
    if current_user.mfa_email_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email MFA is already enabled.",
        )

    if not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must verify your email address before enabling email MFA.",
        )

    # Verify password
    if not verify_password(request.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password.",
        )

    current_user.mfa_email_enabled = True
    current_user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(current_user)

    logger.info(f"Email MFA enabled for user: {current_user.email}")

    return _build_user_response(current_user)


@router.post("/mfa/email/disable", response_model=UserResponse)
async def mfa_email_disable(
    request: MFAEmailDisableRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Disable email-based MFA for the current user.

    Requires password confirmation. Cannot disable if it would leave no MFA methods.
    """
    if not current_user.mfa_email_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email MFA is not enabled.",
        )

    # Verify password
    if not verify_password(request.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password.",
        )

    # Check that at least one MFA method will remain
    if not current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot disable email MFA — it's your only MFA method. "
                   "Enable authenticator app (TOTP) first.",
        )

    current_user.mfa_email_enabled = False
    current_user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(current_user)

    logger.info(f"Email MFA disabled for user: {current_user.email}")

    return _build_user_response(current_user)


@router.post("/mfa/resend-email")
async def mfa_resend_email(
    http_request: Request,
    mfa_token: str = "",
    db: AsyncSession = Depends(get_db),
):
    """
    Resend MFA verification email during login.

    Invalidates old MFA email tokens and creates a new one.
    Accepts mfa_token in body as JSON or query param.
    """
    # Parse body for mfa_token
    try:
        body = await http_request.json()
        mfa_token = body.get("mfa_token", mfa_token)
    except Exception:
        pass

    if not mfa_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA token is required.",
        )

    user_id = await _decode_mfa_token(mfa_token)
    user = await get_user_by_id(db, user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled.",
        )

    # Invalidate old unused MFA email tokens
    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.token_type == "mfa_email",
            EmailVerificationToken.used_at.is_(None),
        )
    )
    old_tokens = result.scalars().all()
    for old_token in old_tokens:
        old_token.used_at = datetime.utcnow()

    # Create new token
    token_str = uuid.uuid4().hex
    verify_code = f"{random.randint(0, 999999):06d}"
    mfa_email_token = EmailVerificationToken(
        user_id=user.id,
        token=token_str,
        verification_code=verify_code,
        token_type="mfa_email",
        expires_at=datetime.utcnow() + timedelta(
            minutes=settings.mfa_email_code_lifetime_minutes
        ),
    )
    db.add(mfa_email_token)
    await db.commit()

    # Send email
    try:
        from app.services.email_service import send_mfa_verification_email
        link_url = f"{settings.frontend_url}/mfa-email-verify?token={token_str}"
        send_mfa_verification_email(
            to=user.email,
            code=verify_code,
            link_url=link_url,
            display_name=user.display_name or "",
        )
    except Exception as e:
        logger.error(f"Failed to resend MFA email to {user.email}: {e}")

    logger.info(f"MFA email resent for user: {user.email}")

    return {"message": "Verification email sent. Please check your inbox."}
