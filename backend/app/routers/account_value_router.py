"""
Account Value History API Router

Endpoints for fetching and managing account value snapshots over time.
"""

import logging
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.services import account_snapshot_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account-value", tags=["account-value"])


@router.get("/history")
async def get_account_value_history(
    days: int = Query(365, ge=1, le=1825, description="Number of days to fetch (max 5 years)"),
    include_paper_trading: bool = Query(False, description="Include paper trading accounts (default: false)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Get historical account value snapshots aggregated across all user accounts.

    Returns daily snapshots with total BTC and USD values.
    By default, excludes paper trading accounts (virtual money).
    """
    try:
        history = await account_snapshot_service.get_account_value_history(
            db, current_user.id, days, include_paper_trading
        )
        return history
    except Exception as e:
        logger.error(f"Failed to fetch account value history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest")
async def get_latest_snapshot(
    include_paper_trading: bool = Query(False, description="Include paper trading accounts (default: false)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get the most recent account value snapshot.
    By default, excludes paper trading accounts (virtual money).
    """
    try:
        snapshot = await account_snapshot_service.get_latest_snapshot(db, current_user.id, include_paper_trading)
        return snapshot
    except Exception as e:
        logger.error(f"Failed to fetch latest snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/capture")
async def capture_snapshots(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Manually trigger snapshot capture for all user accounts.

    Useful for testing or if daily capture fails.
    """
    try:
        result = await account_snapshot_service.capture_all_account_snapshots(db, current_user.id)
        return result
    except Exception as e:
        logger.error(f"Failed to capture snapshots: {e}")
        raise HTTPException(status_code=500, detail=str(e))
