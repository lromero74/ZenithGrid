"""
TOTP MFA endpoints: setup, verify-setup, disable, verify (during login).
"""

import base64
import io
import logging
from datetime import datetime

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_user_by_id
from app.config import settings
from app.database import get_db
from app.encryption import decrypt_value, encrypt_value
from app.models import User
from app.services.brand_service import get_brand

from app.auth_routers.helpers import (
    _build_user_response,
    _create_device_trust,
    create_access_token,
    create_refresh_token,
    verify_password,
)
from app.auth_routers.rate_limiters import _check_mfa_rate_limit, _record_mfa_attempt
from app.auth_routers.schemas import (
    LoginResponse,
    MFAConfirmSetupRequest,
    MFADisableRequest,
    MFASetupResponse,
    MFAVerifyLoginRequest,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def mfa_setup(
    current_user: User = Depends(get_current_user),
):
    """
    Generate a TOTP secret and QR code for MFA setup.

    Does NOT enable MFA yet — user must verify with a TOTP code first
    via POST /api/auth/mfa/verify-setup.
    """
    if current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled. Disable it first to re-setup.",
        )

    # Generate a new TOTP secret
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)

    # Build the provisioning URI for authenticator apps
    provisioning_uri = totp.provisioning_uri(
        name=current_user.email,
        issuer_name=get_brand()["shortName"],
    )

    # Generate QR code as base64 PNG
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    logger.info(f"MFA setup initiated for user: {current_user.email}")

    return MFASetupResponse(
        qr_code_base64=qr_base64,
        secret_key=secret,
        provisioning_uri=provisioning_uri,
    )


@router.post("/mfa/verify-setup", response_model=UserResponse)
async def mfa_verify_setup(
    request: MFAConfirmSetupRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify a TOTP code to complete MFA setup.

    The client sends the secret_key from /mfa/setup along with the first
    TOTP code from their authenticator app. On success, MFA is enabled
    and the secret is stored (encrypted) in the database.
    """
    if current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled.",
        )

    # Verify the TOTP code against the provided secret
    totp = pyotp.TOTP(request.secret_key)
    if not totp.verify(request.totp_code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code. Please try again.",
        )

    # Store the encrypted secret and enable MFA
    current_user.totp_secret = encrypt_value(request.secret_key)
    current_user.mfa_enabled = True
    current_user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(current_user)

    logger.info(f"MFA enabled for user: {current_user.email}")

    return _build_user_response(current_user)


@router.post("/mfa/disable", response_model=UserResponse)
async def mfa_disable(
    request: MFADisableRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Disable MFA for the current user.

    Requires current password and a valid TOTP code for security.
    """
    if not current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled.",
        )

    # Verify password
    if not verify_password(request.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password.",
        )

    # Verify TOTP code
    secret = decrypt_value(current_user.totp_secret)
    totp = pyotp.TOTP(secret)
    if not totp.verify(request.totp_code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code.",
        )

    # Check that at least one MFA method will remain (if email MFA is enabled)
    if current_user.mfa_email_enabled:
        # OK to disable TOTP - email MFA will still be active
        pass
    # If no other MFA method, allow disabling (user wants no MFA at all)

    # Disable MFA and clear secret
    current_user.mfa_enabled = False
    current_user.totp_secret = None
    current_user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(current_user)

    logger.info(f"TOTP MFA disabled for user: {current_user.email}")

    return _build_user_response(current_user)


@router.post("/mfa/verify", response_model=LoginResponse)
async def mfa_verify(
    request: MFAVerifyLoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Verify TOTP code during login to complete MFA challenge.

    Called after /login returns mfa_required=true with an mfa_token.
    On success, returns full access and refresh tokens.
    """
    # S2: Rate limit MFA attempts per token
    _check_mfa_rate_limit(request.mfa_token)
    _record_mfa_attempt(request.mfa_token)

    # Decode the MFA token
    try:
        payload = jwt.decode(
            request.mfa_token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired MFA token. Please login again.",
        )

    if payload.get("type") != "mfa":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type.",
        )

    user_id = int(payload.get("sub"))
    user = await get_user_by_id(db, user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled.",
        )

    if not user.mfa_enabled or not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not configured for this user.",
        )

    # Verify TOTP code
    secret = decrypt_value(user.totp_secret)
    totp = pyotp.TOTP(secret)
    if not totp.verify(request.totp_code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid TOTP code.",
        )

    # MFA verified — issue full tokens
    user.last_login_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)

    # Optionally create a device trust token (30 days)
    device_trust = None
    if request.remember_device:
        device_trust = await _create_device_trust(user, http_request, db)

    logger.info(f"MFA verified, user logged in: {user.email}")

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=_build_user_response(user),
        device_trust_token=device_trust,
    )
