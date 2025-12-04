"""
Authentication dependencies for routers

Provides easy-to-use dependencies for protecting routes with authentication.
Supports both required and optional authentication modes.
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.routers.auth_router import decode_token, get_user_by_id

# Security scheme - auto_error=False allows optional auth
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
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


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Optional authentication - returns current user or None.

    This is useful during the transition period when the frontend
    may not have authentication implemented yet. Routes can work
    for both authenticated and unauthenticated users.

    Usage:
        @router.get("/data")
        async def get_data(current_user: Optional[User] = Depends(get_current_user_optional)):
            if current_user:
                # Filter by user
                query = query.where(Model.user_id == current_user.id)
            # else return all data (backwards compatible)
    """
    if credentials is None:
        return None

    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


async def require_superuser(
    current_user: User = Depends(get_current_user)
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
