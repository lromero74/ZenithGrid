"""
Authentication dependencies for routers.

Provides easy-to-use dependencies for protecting routes with authentication.
This module lives at the auth-utility layer (no router imports) so that
routers, services, strategies, and indicators can all import it without
creating circular dependencies.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import RevokedToken, User

logger = logging.getLogger(__name__)

# Security scheme - auto_error=False allows optional auth
security = HTTPBearer(auto_error=False)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token (signature + expiry only)."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError as e:
        logger.warning(f"JWT decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def check_token_revocation(payload: dict, db: AsyncSession) -> None:
    """
    Check if a token has been revoked. Raises 401 if revoked.

    Two revocation mechanisms:
    1. Individual JTI revocation (logout) — exact match in revoked_tokens table
    2. Bulk revocation (password change) — user.tokens_valid_after > token.iat
    """
    jti = payload.get("jti")
    if jti:
        result = await db.execute(
            select(RevokedToken.id).where(RevokedToken.jti == jti)
        )
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """Get a user by ID."""
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Require authentication - returns current user or raises 401.

    Usage:
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

    # Check individual token revocation (JTI)
    await check_token_revocation(payload, db)

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

    # Check bulk revocation (password change sets tokens_valid_after)
    iat = payload.get("iat")
    if user.tokens_valid_after and iat:
        token_issued = datetime.utcfromtimestamp(iat)
        if token_issued < user.tokens_valid_after:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired — please log in again",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return user


async def require_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Require superuser (admin) authentication.

    Usage:
        @router.post("/admin-only")
        async def admin_route(admin: User = Depends(require_superuser)):
            ...
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required",
        )
    return current_user
