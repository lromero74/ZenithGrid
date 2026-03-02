"""
Core authentication endpoints: login, refresh, logout, register, signup, /me, change-password.
"""

import json
import logging
import random
import uuid
from datetime import datetime, timedelta

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    check_token_revocation,
    decode_token,
    get_current_user,
    get_user_by_id,
    require_superuser,
)
from app.config import settings
from app.database import get_db
from app.models import EmailVerificationToken, Group, RevokedToken, TrustedDevice, User

from app.auth_routers.helpers import (
    _DUMMY_HASH,
    _build_user_response,
    create_access_token,
    create_mfa_token,
    create_refresh_token,
    decode_device_trust_token,
    get_user_by_email,
    hash_password,
    verify_password,
)
from app.auth_routers.rate_limiters import (
    _check_rate_limit,
    _check_signup_rate_limit,
    _record_attempt,
    _record_signup_attempt,
)
from app.auth_routers.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate user and return JWT tokens.

    If MFA is enabled, returns mfa_required=True with a short-lived mfa_token.
    The client must then call POST /api/auth/mfa/verify with the mfa_token + TOTP code.
    """
    # Rate limiting by IP + username (S11)
    client_ip = http_request.client.host if http_request.client else "unknown"
    email_lower = request.email.lower()
    _check_rate_limit(client_ip, username=email_lower)

    # Find user by email (also matches plain usernames stored as email)
    user = await get_user_by_email(db, email_lower)

    # Record attempt AFTER lookup so we can skip per-username for shared accounts
    # (Observers group = shared demo accounts accessed from many IPs)
    is_shared = user and any(g.name == "Observers" for g in (user.groups or []))
    _record_attempt(client_ip, username=None if is_shared else email_lower)

    if not user:
        # S1: Timing equalization — run bcrypt on dummy hash so response
        # time is indistinguishable from a real password check.
        bcrypt.checkpw(request.password.encode('utf-8'), _DUMMY_HASH.encode())
        logger.warning(f"Login attempt for unknown email: {request.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Verify password
    if not verify_password(request.password, user.hashed_password):
        logger.warning(f"Invalid password for user: {request.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # If any MFA method is enabled, check for trusted device token before requiring MFA
    any_mfa_enabled = user.mfa_enabled or user.mfa_email_enabled
    if any_mfa_enabled:
        trusted = False
        if request.device_trust_token:
            payload = decode_device_trust_token(request.device_trust_token)
            if payload and int(payload.get("sub")) == user.id:
                # Verify device still exists in DB (not revoked)
                device_id = payload.get("device_id")
                result = await db.execute(
                    select(TrustedDevice).where(
                        TrustedDevice.device_id == device_id,
                        TrustedDevice.user_id == user.id,
                    )
                )
                device = result.scalar_one_or_none()
                if device and device.expires_at > datetime.utcnow():
                    trusted = True
                    logger.info(f"MFA skipped via trusted device for user: {user.email}")

        if not trusted:
            mfa_token = create_mfa_token(user.id)

            # Build list of available MFA methods
            mfa_methods = []
            if user.mfa_enabled:
                mfa_methods.append("totp")
            if user.mfa_email_enabled:
                mfa_methods.append("email_code")
                mfa_methods.append("email_link")

                # Create email verification token and send MFA email
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

                # Send MFA verification email
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
                    logger.error(f"Failed to send MFA email to {user.email}: {e}")

            logger.info(f"MFA challenge issued for user: {user.email} (methods: {mfa_methods})")
            return LoginResponse(
                mfa_required=True,
                mfa_token=mfa_token,
                mfa_methods=mfa_methods,
            )

    # No MFA (or trusted device) - issue full tokens
    # Update last_login_at (non-critical — don't block login if DB is locked)
    try:
        user.last_login_at = datetime.utcnow()
        await db.commit()
        await db.refresh(user)
    except Exception as e:
        logger.warning(f"Non-critical: failed to update last_login_at for {user.email}: {e}")
        await db.rollback()

    # Resolve session policy
    from app.services.session_policy_service import resolve_session_policy, has_any_limits
    from app.services.session_service import check_session_limits, create_session

    policy = resolve_session_policy(user)
    session_id_str = None
    session_expires_at = None

    if has_any_limits(policy):
        try:
            await check_session_limits(user.id, client_ip, policy, db)
            session_id_str = str(uuid.uuid4())
            timeout = policy.get("session_timeout_minutes")
            if timeout:
                session_expires_at = datetime.utcnow() + timedelta(minutes=timeout)
            await create_session(
                user_id=user.id,
                session_id=session_id_str,
                ip_address=client_ip,
                user_agent=http_request.headers.get("user-agent", ""),
                expires_at=session_expires_at,
                db=db,
            )
            await db.commit()
        except Exception as e:
            logger.warning(f"Non-critical: failed to create session for {user.email}: {e}")
            await db.rollback()
            session_id_str = None
            session_expires_at = None

    access_token = create_access_token(user.id, user.email, session_id=session_id_str)
    refresh_token = create_refresh_token(user.id, session_id=session_id_str)

    logger.info(f"User logged in: {user.email}")

    response = LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=_build_user_response(user),
    )
    if has_any_limits(policy):
        response.session_policy = policy
        response.session_expires_at = (
            session_expires_at.isoformat() if session_expires_at else None
        )

    return response


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a new access token using a refresh token.

    Call this when the access token expires to get a new one without re-entering credentials.
    """
    payload = decode_token(request.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    # Check individual token revocation (JTI)
    await check_token_revocation(payload, db)

    user_id = int(payload.get("sub"))
    user = await get_user_by_id(db, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # Check bulk revocation (password change)
    iat = payload.get("iat")
    if user.tokens_valid_after and iat:
        token_issued = datetime.utcfromtimestamp(iat)
        if token_issued < user.tokens_valid_after:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired — please log in again",
            )

    # Check session validity if sid present
    sid = payload.get("sid")
    if sid:
        from app.services.session_service import check_session_valid
        if not await check_session_valid(sid, db):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired — please log in again",
            )

    # Generate new tokens (pass sid through)
    access_token = create_access_token(user.id, user.email, session_id=sid)
    new_refresh_token = create_refresh_token(user.id, session_id=sid)

    logger.debug(f"Token refreshed for user: {user.email}")

    response = TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=_build_user_response(user),
    )

    if sid:
        from app.models import ActiveSession
        from sqlalchemy import select as sa_select
        sess_result = await db.execute(
            sa_select(ActiveSession.expires_at).where(ActiveSession.session_id == sid)
        )
        sess_row = sess_result.first()
        if sess_row and sess_row[0]:
            response.session_expires_at = sess_row[0].isoformat()

    return response


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Change the current user's password.

    Requires authentication and the current password for verification.
    Demo accounts (no valid email) are blocked from changing passwords.
    """
    # Block demo accounts from changing password
    if "@" not in (current_user.email or ""):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo accounts cannot change passwords",
        )

    # Verify current password
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Hash and save new password
    current_user.hashed_password = hash_password(request.new_password)
    current_user.updated_at = datetime.utcnow()

    # Invalidate all existing sessions by setting tokens_valid_after
    # Any token with iat < this timestamp will be rejected by decode_token()
    current_user.tokens_valid_after = datetime.utcnow()

    await db.commit()

    logger.info(f"Password changed for user: {current_user.email} — all sessions invalidated")

    return {"message": "Password changed successfully. Please log in again."}


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new user.

    Only superusers can create new accounts (for security in a trading application).
    """
    # Check if email already exists
    existing_user = await get_user_by_email(db, request.email.lower())
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user (admin-created users are auto-verified)
    new_user = User(
        email=request.email.lower(),
        hashed_password=hash_password(request.password),
        display_name=request.display_name,
        is_active=True,
        is_superuser=False,
        email_verified=True,
        email_verified_at=datetime.utcnow(),
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Create default paper trading account for new user
    from app.models import Account

    default_paper_account = Account(
        user_id=new_user.id,
        name="Paper Trading Account",
        type="cex",
        exchange="coinbase",
        is_default=True,
        is_active=True,
        is_paper_trading=True,
        paper_balances=json.dumps({
            "BTC": 0.01,
            "ETH": 0.0,
            "USD": 1000.0,
            "USDC": 0.0,
            "USDT": 0.0,
        })
    )

    db.add(default_paper_account)
    await db.commit()
    await db.refresh(default_paper_account)

    logger.info(f"Created default paper trading account for new user: {new_user.email}")

    # Assign to Paper Traders group by default
    paper_traders = (await db.execute(
        select(Group).where(Group.name == "Paper Traders")
    )).scalar_one_or_none()
    if paper_traders:
        new_user.groups.append(paper_traders)
        await db.commit()
        await db.refresh(new_user)
        logger.info(f"Assigned {new_user.email} to Paper Traders group")

    logger.info(f"New user registered: {new_user.email} (by {current_user.email})")

    return _build_user_response(new_user)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get information about the currently authenticated user.
    """
    return _build_user_response(current_user)


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Logout the current user and revoke the current access token server-side.

    The token's JTI is added to the revoked_tokens table so it cannot be reused.
    The client should also discard both access and refresh tokens after calling this.
    """
    # Extract JTI from the current token
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token_str = auth_header[7:]
        try:
            payload = jwt.decode(
                token_str,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                revoked = RevokedToken(
                    jti=jti,
                    user_id=current_user.id,
                    expires_at=datetime.utcfromtimestamp(exp),
                )
                db.add(revoked)

            # End active session if sid present
            sid = payload.get("sid")
            if sid:
                from app.services.session_service import end_session
                await end_session(sid, db)

            await db.commit()
            logger.info(f"Token revoked for user: {current_user.email}")
        except JWTError:
            pass  # Token already invalid — nothing to revoke

    return {"message": "Logged out successfully"}


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    request: RegisterRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Public user registration endpoint.

    Creates a new user account with email_verified=False,
    sends a verification email, and returns JWT tokens for immediate login.
    The frontend gates unverified users from the dashboard.
    """
    if not settings.public_signup_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration is currently disabled. Contact an administrator.",
        )

    # Rate limit by IP
    client_ip = http_request.client.host if http_request.client else "unknown"
    _check_signup_rate_limit(client_ip)
    _record_signup_attempt(client_ip)

    # Check if email already exists
    existing_user = await get_user_by_email(db, request.email.lower())
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user (unverified)
    new_user = User(
        email=request.email.lower(),
        hashed_password=hash_password(request.password),
        display_name=request.display_name,
        is_active=True,
        is_superuser=False,
        email_verified=False,
        last_login_at=datetime.utcnow(),
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Create default paper trading account for new user
    from app.models import Account

    default_paper_account = Account(
        user_id=new_user.id,
        name="Paper Trading Account",
        type="cex",
        exchange="coinbase",
        is_default=True,
        is_active=True,
        is_paper_trading=True,
        paper_balances=json.dumps({
            "BTC": 0.01,
            "ETH": 0.0,
            "USD": 1000.0,
            "USDC": 0.0,
            "USDT": 0.0,
        })
    )

    db.add(default_paper_account)
    await db.commit()
    await db.refresh(default_paper_account)

    logger.info(f"Created default paper trading account for new user: {new_user.email}")

    # Assign to Paper Traders group by default
    paper_traders = (await db.execute(
        select(Group).where(Group.name == "Paper Traders")
    )).scalar_one_or_none()
    if paper_traders:
        new_user.groups.append(paper_traders)
        await db.commit()
        await db.refresh(new_user)
        logger.info(f"Assigned {new_user.email} to Paper Traders group")

    # Generate verification token + 6-digit code and send email
    token_str = uuid.uuid4().hex
    verify_code = f"{random.randint(0, 999999):06d}"
    verification_token = EmailVerificationToken(
        user_id=new_user.id,
        token=token_str,
        verification_code=verify_code,
        token_type="email_verify",
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.add(verification_token)
    await db.commit()

    # Send verification email (fire and forget — don't block signup on email failure)
    try:
        from app.services.email_service import send_verification_email
        verification_url = f"{settings.frontend_url}/verify-email?token={token_str}"
        send_verification_email(
            to=new_user.email,
            verification_url=verification_url,
            display_name=new_user.display_name or "",
            verification_code=verify_code,
        )
    except Exception as e:
        logger.error(f"Failed to send verification email to {new_user.email}: {e}")

    # Generate tokens for immediate login
    access_token = create_access_token(new_user.id, new_user.email)
    refresh_token = create_refresh_token(new_user.id)

    logger.info(f"New user signed up: {new_user.email}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=_build_user_response(new_user),
    )
