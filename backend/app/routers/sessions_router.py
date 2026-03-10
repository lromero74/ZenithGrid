"""
Sessions API Router

Endpoints for managing user login sessions (view active, terminate).
Used by multiplayer games to ensure single session before joining,
and by Settings page for session management.

Permission: settings:write — observers cannot see or manage sessions.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    Perm,
    decode_token,
    require_permission,
    security,
)
from app.database import get_db
from app.models import User
from app.services.session_service import (
    end_session,
    expire_stale_sessions_for_user,
    get_user_sessions,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# ---------------------------------------------------------------------------
# Dependency: extract session ID (sid) from JWT
# ---------------------------------------------------------------------------

async def get_current_session_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[str]:
    """Extract the 'sid' claim from the current JWT token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    return payload.get("sid")


class TerminateRequest(BaseModel):
    session_ids: list[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/active")
async def list_other_active_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.SETTINGS_WRITE)),
    current_sid: Optional[str] = Depends(get_current_session_id),
) -> list[dict]:
    """
    Return all OTHER active sessions for the current user.

    Excludes the caller's own session (identified by the 'sid' JWT claim).
    Cleans up expired sessions first.
    Requires settings:write — observers cannot access this.
    """
    await expire_stale_sessions_for_user(current_user.id, db)
    await db.flush()

    sessions = await get_user_sessions(current_user.id, db)

    return [
        {
            "session_id": s.session_id,
            "ip_address": s.ip_address,
            "user_agent": s.user_agent,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in sessions
        if s.session_id != current_sid
    ]


@router.post("/terminate")
async def terminate_sessions(
    body: TerminateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.SETTINGS_WRITE)),
    current_sid: Optional[str] = Depends(get_current_session_id),
) -> dict:
    """
    Terminate specific sessions by ID.

    Supports individual, multi-select, or bulk termination.
    The caller's own session cannot be terminated (silently skipped).
    Requires settings:write — observers cannot manage sessions.
    """
    terminated = 0
    for sid in body.session_ids:
        if sid == current_sid:
            continue  # Never terminate own session
        ended = await end_session(sid, db)
        if ended:
            terminated += 1

    await db.commit()
    logger.info(
        "User %s terminated %d session(s)", current_user.id, terminated
    )
    return {"terminated": terminated}


@router.post("/terminate-others")
async def terminate_other_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.SETTINGS_WRITE)),
    current_sid: Optional[str] = Depends(get_current_session_id),
) -> dict:
    """
    Terminate ALL other active sessions for the current user.

    The caller's own session (identified by 'sid') is preserved.
    Requires settings:write — observers cannot manage sessions.
    """
    await expire_stale_sessions_for_user(current_user.id, db)
    await db.flush()

    sessions = await get_user_sessions(current_user.id, db)

    terminated = 0
    for session in sessions:
        if session.session_id != current_sid:
            ended = await end_session(session.session_id, db)
            if ended:
                terminated += 1

    await db.commit()
    logger.info(
        "User %s terminated %d other session(s)", current_user.id, terminated
    )
    return {"terminated": terminated}
