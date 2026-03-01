"""
Session lifecycle management service.

Handles creating, validating, ending, and enforcing session limits.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActiveSession

logger = logging.getLogger(__name__)


async def create_session(
    user_id: int,
    session_id: str,
    ip_address: Optional[str],
    user_agent: Optional[str],
    expires_at: Optional[datetime],
    db: AsyncSession,
) -> ActiveSession:
    """Create a new active session record."""
    session = ActiveSession(
        user_id=user_id,
        session_id=session_id,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=expires_at,
        is_active=True,
    )
    db.add(session)
    await db.flush()
    return session


async def check_session_limits(
    user_id: int,
    ip_address: Optional[str],
    policy: dict,
    db: AsyncSession,
):
    """
    Check session limits before allowing a new login.

    Raises HTTPException if any limit is exceeded.
    Strategy: DENY new login (never evict existing sessions).
    """
    # Step 1: expire stale sessions first (reclaim slots)
    await expire_stale_sessions_for_user(user_id, db)
    await db.flush()  # Ensure expired sessions are visible to subsequent count queries

    # Step 2: relogin cooldown
    cooldown_minutes = policy.get("relogin_cooldown_minutes")
    if cooldown_minutes and ip_address:
        result = await db.execute(
            select(func.max(ActiveSession.ended_at)).where(
                and_(
                    ActiveSession.user_id == user_id,
                    ActiveSession.ip_address == ip_address,
                    ActiveSession.ended_at.isnot(None),
                )
            )
        )
        last_ended = result.scalar()
        if last_ended:
            cooldown_until = last_ended + timedelta(minutes=cooldown_minutes)
            if datetime.utcnow() < cooldown_until:
                retry_after = int((cooldown_until - datetime.utcnow()).total_seconds())
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Please wait {retry_after} seconds before logging in again",
                    headers={"Retry-After": str(retry_after)},
                )

    # Step 3: max simultaneous sessions
    max_simultaneous = policy.get("max_simultaneous_sessions")
    if max_simultaneous:
        result = await db.execute(
            select(func.count()).where(
                and_(
                    ActiveSession.user_id == user_id,
                    ActiveSession.is_active.is_(True),
                )
            )
        )
        active_count = result.scalar() or 0
        if active_count >= max_simultaneous:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Maximum {max_simultaneous} simultaneous sessions reached",
            )

    # Step 4: max sessions per IP
    max_per_ip = policy.get("max_sessions_per_ip")
    if max_per_ip and ip_address:
        result = await db.execute(
            select(func.count()).where(
                and_(
                    ActiveSession.user_id == user_id,
                    ActiveSession.ip_address == ip_address,
                    ActiveSession.is_active.is_(True),
                )
            )
        )
        ip_count = result.scalar() or 0
        if ip_count >= max_per_ip:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Maximum {max_per_ip} sessions from this IP address",
            )


async def end_session(session_id: str, db: AsyncSession) -> bool:
    """End a session (mark inactive, record ended_at for cooldown)."""
    result = await db.execute(
        select(ActiveSession).where(
            and_(
                ActiveSession.session_id == session_id,
                ActiveSession.is_active.is_(True),
            )
        )
    )
    session = result.scalar_one_or_none()
    if session:
        session.is_active = False
        session.ended_at = datetime.utcnow()
        return True
    return False


async def check_session_valid(session_id: str, db: AsyncSession) -> bool:
    """Check if a session is still active and not expired."""
    result = await db.execute(
        select(ActiveSession).where(
            and_(
                ActiveSession.session_id == session_id,
                ActiveSession.is_active.is_(True),
            )
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        return False

    # Check expiry
    if session.expires_at and datetime.utcnow() > session.expires_at:
        session.is_active = False
        session.ended_at = datetime.utcnow()
        return False

    return True


async def expire_stale_sessions_for_user(user_id: int, db: AsyncSession):
    """Mark expired sessions as inactive for a specific user."""
    now = datetime.utcnow()
    result = await db.execute(
        select(ActiveSession).where(
            and_(
                ActiveSession.user_id == user_id,
                ActiveSession.is_active.is_(True),
                ActiveSession.expires_at.isnot(None),
                ActiveSession.expires_at < now,
            )
        )
    )
    for session in result.scalars().all():
        session.is_active = False
        # Use the actual expiry time, not now — otherwise cooldown triggers
        # against the cleanup time instead of when the session really ended.
        session.ended_at = session.expires_at


async def expire_all_stale_sessions(db: AsyncSession) -> int:
    """Bulk cleanup: mark all expired active sessions as inactive."""
    now = datetime.utcnow()
    result = await db.execute(
        select(ActiveSession).where(
            and_(
                ActiveSession.is_active.is_(True),
                ActiveSession.expires_at.isnot(None),
                ActiveSession.expires_at < now,
            )
        )
    )
    count = 0
    for session in result.scalars().all():
        session.is_active = False
        session.ended_at = session.expires_at
        count += 1
    return count


async def get_user_sessions(user_id: int, db: AsyncSession) -> list:
    """Get all active sessions for a user (for admin view)."""
    result = await db.execute(
        select(ActiveSession).where(
            and_(
                ActiveSession.user_id == user_id,
                ActiveSession.is_active.is_(True),
            )
        ).order_by(ActiveSession.created_at.desc())
    )
    return result.scalars().all()
