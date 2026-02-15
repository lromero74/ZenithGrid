"""
Authentication API routes

Handles user authentication:
- Login (email/password) -> JWT tokens
- Token refresh
- Logout (optional - client-side token removal)
- Password change
- User registration (admin only in production)
"""

import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User

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
    created_at: datetime
    last_login_at: Optional[datetime]
    terms_accepted_at: Optional[datetime] = None  # NULL = must accept terms

    class Config:
        from_attributes = True


# Allow forward reference
TokenResponse.model_rebuild()


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


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate user and return JWT tokens.

    The access token is short-lived (30 minutes by default) and used for API requests.
    The refresh token is long-lived (7 days by default) and used to get new access tokens.
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

    # Update last login timestamp
    user.last_login_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)

    # Generate tokens
    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)

    logger.info(f"User logged in: {user.email}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            terms_accepted_at=user.terms_accepted_at,
        ),
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
        user=UserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            terms_accepted_at=user.terms_accepted_at,
        ),
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

    return UserResponse(
        id=new_user.id,
        email=new_user.email,
        display_name=new_user.display_name,
        is_active=new_user.is_active,
        is_superuser=new_user.is_superuser,
        created_at=new_user.created_at,
        last_login_at=new_user.last_login_at,
        terms_accepted_at=new_user.terms_accepted_at,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get information about the currently authenticated user.
    """
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
        terms_accepted_at=current_user.terms_accepted_at,
    )


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
        user=UserResponse(
            id=new_user.id,
            email=new_user.email,
            display_name=new_user.display_name,
            is_active=new_user.is_active,
            is_superuser=new_user.is_superuser,
            created_at=new_user.created_at,
            last_login_at=new_user.last_login_at,
            terms_accepted_at=new_user.terms_accepted_at,
        ),
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

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
        terms_accepted_at=current_user.terms_accepted_at,
    )


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
