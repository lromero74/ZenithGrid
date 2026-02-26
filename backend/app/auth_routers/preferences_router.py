"""
User preference endpoints: accept-terms, last-seen-history.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import User

from app.auth_routers.helpers import _build_user_response
from app.auth_routers.schemas import (
    LastSeenHistoryRequest,
    LastSeenHistoryResponse,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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
