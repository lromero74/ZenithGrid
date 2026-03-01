"""
Helper functions for authentication.

Includes password hashing, JWT token creation/decoding, device trust,
IP geolocation, and shared MFA login completion logic.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import httpx
from fastapi import HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import TrustedDevice, User

from app.auth_routers.schemas import GroupResponse, LoginResponse, UserResponse

logger = logging.getLogger(__name__)

# Pre-computed dummy bcrypt hash for timing-safe login (S1)
_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(user_id: int, email: str) -> str:
    """Create a JWT access token with unique JTI for revocation support"""
    expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes)
    expire = datetime.utcnow() + expires_delta

    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "exp": expire,
        "iat": datetime.utcnow(),
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: int) -> str:
    """Create a JWT refresh token (longer-lived) with unique JTI for revocation support"""
    expires_delta = timedelta(days=settings.jwt_refresh_token_expire_days)
    expire = datetime.utcnow() + expires_delta

    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": str(uuid.uuid4()),
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
    # Flatten permissions from groups -> roles -> permissions chain
    groups = getattr(user, 'groups', None) or []
    permissions = list({
        p.name
        for g in groups
        for r in g.roles
        for p in r.permissions
    })

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
        groups=[GroupResponse.model_validate(g) for g in groups],
        permissions=permissions,
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
