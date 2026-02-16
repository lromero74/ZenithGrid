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
import logging
import re
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Optional, Union

import httpx

import bcrypt
import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.encryption import decrypt_value, encrypt_value
from app.models import TrustedDevice, User

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
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < _RATE_LIMIT_WINDOW]
    if len(_login_attempts[ip]) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later."
        )


def _record_attempt(ip: str):
    """Record a login attempt for rate limiting."""
    _login_attempts[ip].append(time.time())


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
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        terms_accepted_at=user.terms_accepted_at,
    )


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token"""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError as e:
        logger.warning(f"JWT decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Get a user by email address"""
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """Get a user by ID"""
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.

    Usage in routes:
        @router.get("/protected")
        async def protected_route(current_user: User = Depends(get_current_user)):
            ...
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = int(payload.get("sub"))
    user = await get_user_by_id(db, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


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

    # If MFA is enabled, check for trusted device token before requiring MFA
    if user.mfa_enabled:
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
            logger.info(f"MFA challenge issued for user: {user.email}")
            return LoginResponse(
                mfa_required=True,
                mfa_token=mfa_token,
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

    # Create new user
    new_user = User(
        email=request.email.lower(),
        hashed_password=hash_password(request.password),
        display_name=request.display_name,
        is_active=True,
        is_superuser=False,
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Create default paper trading account for new user
    from app.models import Account
    import json

    default_paper_account = Account(
        user_id=new_user.id,
        name="Paper Trading Account",
        type="cex",
        exchange="coinbase",
        is_default=True,
        is_active=True,
        is_paper_trading=True,
        paper_balances=json.dumps({
            "BTC": 0.01,      # Start with 0.01 BTC
            "ETH": 0.0,
            "USD": 1000.0,    # Start with $1000 USD
            "USDC": 0.0,
            "USDT": 0.0
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
    db: AsyncSession = Depends(get_db)
):
    """
    Public user registration endpoint.

    Creates a new user account and returns JWT tokens for immediate login.
    """
    # Public registration is disabled for security
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Public registration is currently disabled. Contact an administrator.",
    )

    # Check if email already exists
    existing_user = await get_user_by_email(db, request.email.lower())
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user
    new_user = User(
        email=request.email.lower(),
        hashed_password=hash_password(request.password),
        display_name=request.display_name,
        is_active=True,
        is_superuser=False,
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Create default paper trading account for new user
    from app.models import Account
    import json

    default_paper_account = Account(
        user_id=new_user.id,
        name="Paper Trading Account",
        type="cex",
        exchange="coinbase",
        is_default=True,
        is_active=True,
        is_paper_trading=True,
        paper_balances=json.dumps({
            "BTC": 0.01,      # Start with 0.01 BTC
            "ETH": 0.0,
            "USD": 1000.0,    # Start with $1000 USD
            "USDC": 0.0,
            "USDT": 0.0
        })
    )

    db.add(default_paper_account)
    await db.commit()
    await db.refresh(default_paper_account)

    logger.info(f"Created default paper trading account for new user: {new_user.email}")

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
        issuer_name="Zenith Grid",
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

    # Disable MFA and clear secret
    current_user.mfa_enabled = False
    current_user.totp_secret = None
    current_user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(current_user)

    logger.info(f"MFA disabled for user: {current_user.email}")

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

    # Optionally create a device trust token (30 days) and store in DB
    device_trust = None
    if request.remember_device:
        device_uuid = str(uuid.uuid4())
        expires = datetime.utcnow() + timedelta(days=30)
        device_trust = create_device_trust_token(user.id, device_uuid)

        # Parse device info from request
        user_agent = http_request.headers.get("user-agent", "")
        client_ip = http_request.client.host if http_request.client else "unknown"

        # Resolve IP to location (city, state, country)
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

    logger.info(f"MFA verified, user logged in: {user.email}")

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=_build_user_response(user),
        device_trust_token=device_trust,
    )


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
