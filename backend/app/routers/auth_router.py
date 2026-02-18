"""
Authentication API routes

Handles user authentication:
- Login (email/password) -> JWT tokens (with optional MFA challenge)
- Token refresh
- Logout (optional - client-side token removal)
- Password change
- User registration (admin only in production)
- TOTP MFA setup, verification, and disable
"""

import base64
import io
import json
import logging
import random
import re
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Optional

import httpx

import bcrypt
import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (  # noqa: F401
    decode_token,
    get_current_user,
    get_user_by_id,
)
from app.config import settings
from app.database import get_db
from app.encryption import decrypt_value, encrypt_value
from app.models import EmailVerificationToken, TrustedDevice, User
from app.services.brand_service import get_brand

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Security scheme for JWT bearer tokens
security = HTTPBearer(auto_error=False)

# =============================================================================
# Rate Limiting (in-memory, per-IP)
# =============================================================================

# {ip: [(timestamp, ...)] }
_login_attempts: dict = defaultdict(list)
_RATE_LIMIT_MAX = 5  # max attempts
_RATE_LIMIT_WINDOW = 900  # 15 minutes in seconds


def _check_rate_limit(ip: str):
    """Check if IP has exceeded login rate limit. Raises 429 if exceeded."""
    now = time.time()
    # Clean old entries
    _login_attempts[ip] = [
        t for t in _login_attempts[ip]
        if now - t < _RATE_LIMIT_WINDOW
    ]
    if len(_login_attempts[ip]) >= _RATE_LIMIT_MAX:
        oldest = min(_login_attempts[ip])
        retry_after = int(oldest + _RATE_LIMIT_WINDOW - now)
        minutes = (retry_after + 59) // 60  # round up
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many login attempts. "
                f"Try again in {minutes} minute{'s' if minutes != 1 else ''}."
            ),
            headers={"Retry-After": str(retry_after)},
        )


def _record_attempt(ip: str):
    """Record a login attempt for rate limiting."""
    _login_attempts[ip].append(time.time())


# Signup rate limiting: 3 per IP per hour
_signup_attempts: dict = defaultdict(list)
_SIGNUP_RATE_LIMIT_MAX = 3
_SIGNUP_RATE_LIMIT_WINDOW = 3600  # 1 hour


def _check_signup_rate_limit(ip: str):
    """Check if IP has exceeded signup rate limit."""
    now = time.time()
    _signup_attempts[ip] = [
        t for t in _signup_attempts[ip]
        if now - t < _SIGNUP_RATE_LIMIT_WINDOW
    ]
    if len(_signup_attempts[ip]) >= _SIGNUP_RATE_LIMIT_MAX:
        oldest = min(_signup_attempts[ip])
        retry_after = int(oldest + _SIGNUP_RATE_LIMIT_WINDOW - now)
        minutes = (retry_after + 59) // 60
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many signup attempts. "
                f"Try again in {minutes} minute{'s' if minutes != 1 else ''}."
            ),
            headers={"Retry-After": str(retry_after)},
        )


def _record_signup_attempt(ip: str):
    """Record a signup attempt for rate limiting."""
    _signup_attempts[ip].append(time.time())


# Forgot-password rate limiting: 3 per IP per hour
_forgot_pw_attempts: dict = defaultdict(list)
_FORGOT_PW_RATE_LIMIT_MAX = 3
_FORGOT_PW_RATE_LIMIT_WINDOW = 3600


def _check_forgot_pw_rate_limit(ip: str):
    """Check if IP has exceeded forgot-password rate limit."""
    now = time.time()
    _forgot_pw_attempts[ip] = [
        t for t in _forgot_pw_attempts[ip]
        if now - t < _FORGOT_PW_RATE_LIMIT_WINDOW
    ]
    if len(_forgot_pw_attempts[ip]) >= _FORGOT_PW_RATE_LIMIT_MAX:
        oldest = min(_forgot_pw_attempts[ip])
        retry_after = int(
            oldest + _FORGOT_PW_RATE_LIMIT_WINDOW - now
        )
        minutes = (retry_after + 59) // 60
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many requests. "
                f"Try again in {minutes} minute{'s' if minutes != 1 else ''}."
            ),
            headers={"Retry-After": str(retry_after)},
        )


def _record_forgot_pw_attempt(ip: str):
    """Record a forgot-password attempt for rate limiting."""
    _forgot_pw_attempts[ip].append(time.time())


# Resend verification rate limiting: 3 per user per hour
_resend_attempts: dict = defaultdict(list)
_RESEND_RATE_LIMIT_MAX = 3
_RESEND_RATE_LIMIT_WINDOW = 3600


def _check_resend_rate_limit(user_id: int):
    """Check if user has exceeded resend verification rate limit."""
    now = time.time()
    key = str(user_id)
    _resend_attempts[key] = [
        t for t in _resend_attempts[key]
        if now - t < _RESEND_RATE_LIMIT_WINDOW
    ]
    if len(_resend_attempts[key]) >= _RESEND_RATE_LIMIT_MAX:
        oldest = min(_resend_attempts[key])
        retry_after = int(
            oldest + _RESEND_RATE_LIMIT_WINDOW - now
        )
        minutes = (retry_after + 59) // 60
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many resend attempts. "
                f"Try again in {minutes} minute{'s' if minutes != 1 else ''}."
            ),
            headers={"Retry-After": str(retry_after)},
        )


def _record_resend_attempt(user_id: int):
    """Record a resend verification attempt for rate limiting."""
    _resend_attempts[str(user_id)].append(time.time())


# =============================================================================
# Pydantic Models
# =============================================================================


class LoginRequest(BaseModel):
    """Login request with email and password"""
    email: EmailStr
    password: str = Field(..., min_length=1)
    device_trust_token: Optional[str] = None  # Skip MFA if valid trusted device


class TokenResponse(BaseModel):
    """Response containing JWT tokens"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires
    user: "UserResponse"


class RefreshRequest(BaseModel):
    """Request to refresh access token"""
    refresh_token: str


def _validate_password_strength(password: str) -> str:
    """Validate password has uppercase, lowercase, and digit."""
    if not re.search(r'[A-Z]', password):
        raise ValueError('Password must contain at least one uppercase letter')
    if not re.search(r'[a-z]', password):
        raise ValueError('Password must contain at least one lowercase letter')
    if not re.search(r'[0-9]', password):
        raise ValueError('Password must contain at least one digit')
    return password


class ChangePasswordRequest(BaseModel):
    """Request to change password"""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, description="New password (min 8 chars, 1 upper, 1 lower, 1 digit)")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_password_strength(v)


class RegisterRequest(BaseModel):
    """Request to register a new user"""
    email: EmailStr
    password: str = Field(..., min_length=8)
    display_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_strength(v)


class UserResponse(BaseModel):
    """User information (without sensitive data)"""
    id: int
    email: str
    display_name: Optional[str]
    is_active: bool
    is_superuser: bool
    mfa_enabled: bool = False
    mfa_email_enabled: bool = False
    email_verified: bool = False
    email_verified_at: Optional[datetime] = None
    created_at: datetime
    last_login_at: Optional[datetime]
    terms_accepted_at: Optional[datetime] = None  # NULL = must accept terms

    class Config:
        from_attributes = True


class MFAChallengeResponse(BaseModel):
    """Response when MFA is required during login"""
    mfa_required: bool = True
    mfa_token: str  # Short-lived JWT for MFA verification


class LoginResponse(BaseModel):
    """Union response for login: either full tokens or MFA challenge"""
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: Optional[int] = None
    user: Optional[UserResponse] = None
    mfa_required: bool = False
    mfa_token: Optional[str] = None
    mfa_methods: Optional[List[str]] = None  # e.g. ["totp", "email_code", "email_link"]
    device_trust_token: Optional[str] = None  # 30-day device trust token


class MFASetupResponse(BaseModel):
    """Response with QR code and secret for MFA setup"""
    qr_code_base64: str  # Base64 PNG of QR code
    secret_key: str  # Base32 secret for manual entry
    provisioning_uri: str  # otpauth:// URI


class MFAVerifyRequest(BaseModel):
    """Request to verify a TOTP code"""
    totp_code: str = Field(..., min_length=6, max_length=6, pattern=r'^\d{6}$')


class MFAVerifyLoginRequest(BaseModel):
    """Request to verify MFA during login"""
    mfa_token: str
    totp_code: str = Field(..., min_length=6, max_length=6, pattern=r'^\d{6}$')
    remember_device: bool = False  # If true, returns a 30-day device trust token


class MFADisableRequest(BaseModel):
    """Request to disable MFA (requires password + TOTP code)"""
    password: str = Field(..., min_length=1)
    totp_code: str = Field(..., min_length=6, max_length=6, pattern=r'^\d{6}$')


# Allow forward reference
TokenResponse.model_rebuild()
LoginResponse.model_rebuild()


# =============================================================================
# Helper Functions
# =============================================================================


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(user_id: int, email: str) -> str:
    """Create a JWT access token"""
    expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes)
    expire = datetime.utcnow() + expires_delta

    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "exp": expire,
        "iat": datetime.utcnow(),
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: int) -> str:
    """Create a JWT refresh token (longer-lived)"""
    expires_delta = timedelta(days=settings.jwt_refresh_token_expire_days)
    expire = datetime.utcnow() + expires_delta

    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
        "iat": datetime.utcnow(),
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_mfa_token(user_id: int) -> str:
    """Create a short-lived JWT for MFA verification (5 minutes)"""
    expire = datetime.utcnow() + timedelta(minutes=5)

    payload = {
        "sub": str(user_id),
        "type": "mfa",
        "exp": expire,
        "iat": datetime.utcnow(),
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_device_trust_token(user_id: int, device_id: str) -> str:
    """Create a 30-day device trust token to skip MFA on trusted devices."""
    expire = datetime.utcnow() + timedelta(days=30)

    payload = {
        "sub": str(user_id),
        "type": "device_trust",
        "device_id": device_id,
        "exp": expire,
        "iat": datetime.utcnow(),
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_device_trust_token(token: str) -> Optional[dict]:
    """Decode a device trust token. Returns payload or None if invalid."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        if payload.get("type") != "device_trust":
            return None
        return payload
    except JWTError:
        return None


def _parse_device_name(user_agent: str) -> str:
    """Parse a human-readable device name from User-Agent string."""
    if not user_agent:
        return "Unknown Device"

    ua = user_agent.lower()

    # Detect OS
    if "iphone" in ua:
        os_name = "iPhone"
    elif "ipad" in ua:
        os_name = "iPad"
    elif "android" in ua:
        os_name = "Android"
    elif "macintosh" in ua or "mac os" in ua:
        os_name = "Mac"
    elif "windows" in ua:
        os_name = "Windows"
    elif "linux" in ua:
        os_name = "Linux"
    else:
        os_name = "Unknown OS"

    # Detect browser
    if "firefox" in ua:
        browser = "Firefox"
    elif "edg/" in ua or "edge" in ua:
        browser = "Edge"
    elif "chrome" in ua and "safari" in ua:
        browser = "Chrome"
    elif "safari" in ua:
        browser = "Safari"
    else:
        browser = "Browser"

    return f"{browser} on {os_name}"


async def _geolocate_ip(ip: str) -> Optional[str]:
    """Resolve IP address to city, state, country using free geolocation API."""
    if not ip or ip in ("unknown", "127.0.0.1", "::1", "localhost"):
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"http://ip-api.com/json/{ip}?fields=city,regionName,country,status")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    parts = [p for p in [data.get("city"), data.get("regionName"), data.get("country")] if p]
                    return ", ".join(parts) if parts else None
    except Exception as e:
        logger.debug(f"IP geolocation failed for {ip}: {e}")
    return None


def _build_user_response(user: User) -> UserResponse:
    """Build a UserResponse from a User model instance."""
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        mfa_enabled=bool(user.mfa_enabled),
        mfa_email_enabled=bool(user.mfa_email_enabled),
        email_verified=bool(user.email_verified),
        email_verified_at=user.email_verified_at,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        terms_accepted_at=user.terms_accepted_at,
    )


async def _create_device_trust(
    user: User, request: Request, db: AsyncSession
) -> Optional[str]:
    """Create a trusted device record and return the device trust JWT token."""
    device_uuid = str(uuid.uuid4())
    expires = datetime.utcnow() + timedelta(days=30)
    device_trust = create_device_trust_token(user.id, device_uuid)

    user_agent = request.headers.get("user-agent", "")
    client_ip = request.client.host if request.client else "unknown"
    location = await _geolocate_ip(client_ip)

    trusted_device = TrustedDevice(
        user_id=user.id,
        device_id=device_uuid,
        device_name=_parse_device_name(user_agent),
        ip_address=client_ip,
        location=location,
        expires_at=expires,
    )
    db.add(trusted_device)
    await db.commit()
    logger.info(f"Device trust token issued for user: {user.email} (device: {device_uuid[:8]}...)")
    return device_trust


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Get a user by email address"""
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    return result.scalar_one_or_none()


# =============================================================================
# API Endpoints
# =============================================================================


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
    # Rate limiting by IP
    client_ip = http_request.client.host if http_request.client else "unknown"
    _check_rate_limit(client_ip)
    _record_attempt(client_ip)

    # Find user by email
    user = await get_user_by_email(db, request.email.lower())

    if not user:
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
    user.last_login_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)

    logger.info(f"User logged in: {user.email}")

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=_build_user_response(user),
    )


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

    # Generate new tokens
    access_token = create_access_token(user.id, user.email)
    new_refresh_token = create_refresh_token(user.id)

    logger.debug(f"Token refreshed for user: {user.email}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=_build_user_response(user),
    )


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Change the current user's password.

    Requires authentication and the current password for verification.
    """
    # Verify current password
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Hash and save new password
    current_user.hashed_password = hash_password(request.new_password)
    current_user.updated_at = datetime.utcnow()

    await db.commit()

    logger.info(f"Password changed for user: {current_user.email}")

    return {"message": "Password changed successfully"}


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Register a new user.

    Only superusers can create new accounts (for security in a trading application).
    """
    # Only superusers can register new users
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create new users",
        )

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
async def logout():
    """
    Logout the current user.

    Note: JWT tokens are stateless, so this endpoint is mainly for client-side
    confirmation. The client should discard the tokens after calling this.
    For true token invalidation, implement a token blacklist (not included here).
    """
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


# =============================================================================
# Email Verification Endpoints
# =============================================================================


class VerifyEmailRequest(BaseModel):
    """Request to verify email with token"""
    token: str = Field(..., min_length=1)


class ForgotPasswordRequest(BaseModel):
    """Request to send password reset email"""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Request to reset password with token"""
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_password_strength(v)


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


class VerifyEmailCodeRequest(BaseModel):
    """Request to verify email with 6-digit code (authenticated user)"""
    code: str = Field(..., min_length=6, max_length=6, pattern=r'^\d{6}$')


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

    user = await get_user_by_email(db, request.email.lower())
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

    # Update password
    user.hashed_password = hash_password(request.new_password)
    user.updated_at = datetime.utcnow()
    token_record.used_at = datetime.utcnow()

    await db.commit()

    logger.info(f"Password reset for user: {user.email}")

    return {"message": "Password reset successfully. Please log in with your new password."}


# =============================================================================
# Terms and Conditions Endpoints
# =============================================================================


@router.post("/accept-terms", response_model=UserResponse)
async def accept_terms(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Accept the terms of service and risk disclaimer.

    Users must accept terms before accessing the dashboard.
    This only needs to be done once per user.
    """
    current_user.terms_accepted_at = datetime.utcnow()
    await db.commit()
    await db.refresh(current_user)

    logger.info(f"User accepted terms: {current_user.email}")

    return _build_user_response(current_user)


# =============================================================================
# User Preferences Endpoints
# =============================================================================


class LastSeenHistoryRequest(BaseModel):
    """Request to update last seen history count"""
    count: Optional[int] = Field(None, ge=0)  # Closed positions count
    failed_count: Optional[int] = Field(None, ge=0)  # Failed orders count


class LastSeenHistoryResponse(BaseModel):
    """Response with last seen history count"""
    last_seen_history_count: int
    last_seen_failed_count: int = 0


@router.get("/preferences/last-seen-history", response_model=LastSeenHistoryResponse)
async def get_last_seen_history(
    current_user: User = Depends(get_current_user)
):
    """
    Get the user's last seen history counts.
    Used for the "new items" badge in the History tab (closed + failed).
    """
    return LastSeenHistoryResponse(
        last_seen_history_count=current_user.last_seen_history_count or 0,
        last_seen_failed_count=current_user.last_seen_failed_count or 0
    )


@router.put("/preferences/last-seen-history", response_model=LastSeenHistoryResponse)
async def update_last_seen_history(
    request: LastSeenHistoryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update the user's last seen history counts.
    Called when the user views the History tab (closed or failed).
    Both counts are optional - only update what's provided.
    """
    if request.count is not None:
        current_user.last_seen_history_count = request.count
    if request.failed_count is not None:
        current_user.last_seen_failed_count = request.failed_count
    await db.commit()

    return LastSeenHistoryResponse(
        last_seen_history_count=current_user.last_seen_history_count or 0,
        last_seen_failed_count=current_user.last_seen_failed_count or 0
    )


# =============================================================================
# MFA (Two-Factor Authentication) Endpoints
# =============================================================================


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


class MFAConfirmSetupRequest(BaseModel):
    """Request to confirm MFA setup with secret and first TOTP code"""
    secret_key: str = Field(..., min_length=16, max_length=64)
    totp_code: str = Field(..., min_length=6, max_length=6, pattern=r'^\d{6}$')


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


# =============================================================================
# Email MFA Verification Endpoints
# =============================================================================


class MFAEmailCodeRequest(BaseModel):
    """Request to verify MFA with email code"""
    mfa_token: str
    email_code: str = Field(..., min_length=6, max_length=6, pattern=r'^\d{6}$')
    remember_device: bool = False


class MFAEmailLinkRequest(BaseModel):
    """Request to verify MFA with email link token"""
    token: str
    remember_device: bool = False


class MFAEmailEnableRequest(BaseModel):
    """Request to enable email MFA"""
    password: str = Field(..., min_length=1)


class MFAEmailDisableRequest(BaseModel):
    """Request to disable email MFA"""
    password: str = Field(..., min_length=1)


async def _decode_mfa_token(mfa_token: str) -> int:
    """Decode MFA JWT token and return user_id. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(
            mfa_token,
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

    return int(payload.get("sub"))


async def _complete_mfa_login(
    user: User, remember_device: bool, http_request: Request, db: AsyncSession
) -> LoginResponse:
    """Common logic to complete MFA login after any verification method succeeds."""
    user.last_login_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)

    device_trust = None
    if remember_device:
        device_trust = await _create_device_trust(user, http_request, db)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=_build_user_response(user),
        device_trust_token=device_trust,
    )


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


# =============================================================================
# Trusted Devices Management Endpoints
# =============================================================================


class TrustedDeviceResponse(BaseModel):
    """Response for a single trusted device"""
    id: int
    device_name: Optional[str]
    ip_address: Optional[str]
    location: Optional[str]
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


@router.get("/mfa/devices", response_model=List[TrustedDeviceResponse])
async def list_trusted_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all trusted devices for the current user.

    Returns active (non-expired) trusted devices that can bypass MFA.
    """
    result = await db.execute(
        select(TrustedDevice)
        .where(
            TrustedDevice.user_id == current_user.id,
            TrustedDevice.expires_at > datetime.utcnow(),
        )
        .order_by(TrustedDevice.created_at.desc())
    )
    devices = result.scalars().all()

    return [
        TrustedDeviceResponse(
            id=d.id,
            device_name=d.device_name,
            ip_address=d.ip_address,
            location=d.location,
            created_at=d.created_at,
            expires_at=d.expires_at,
        )
        for d in devices
    ]


@router.delete("/mfa/devices/{device_id}")
async def revoke_trusted_device(
    device_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoke a specific trusted device.

    The device will need to complete MFA again on next login.
    """
    result = await db.execute(
        select(TrustedDevice).where(
            TrustedDevice.id == device_id,
            TrustedDevice.user_id == current_user.id,
        )
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trusted device not found.",
        )

    await db.delete(device)
    await db.commit()

    logger.info(f"Trusted device revoked for user: {current_user.email} (device ID: {device_id})")

    return {"message": "Device trust revoked successfully"}


@router.delete("/mfa/devices")
async def revoke_all_trusted_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoke all trusted devices for the current user.

    All devices will need to complete MFA again on next login.
    """
    result = await db.execute(
        select(TrustedDevice).where(TrustedDevice.user_id == current_user.id)
    )
    devices = result.scalars().all()

    for device in devices:
        await db.delete(device)

    await db.commit()

    logger.info(f"All trusted devices revoked for user: {current_user.email} ({len(devices)} devices)")

    return {"message": f"All {len(devices)} trusted device(s) revoked"}
