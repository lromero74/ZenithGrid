"""
Bot Indicator Logs Router

Handles indicator condition evaluation log retrieval.
Shows which indicators matched, at what values, for non-AI bots.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Bot, IndicatorLog, User
from app.bot_routers.schemas import IndicatorLogResponse
from app.routers.auth_dependencies import get_current_user_optional

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{bot_id}/indicator-logs", response_model=List[IndicatorLogResponse])
async def get_indicator_logs(
    bot_id: int,
    limit: int = 50,
    offset: int = 0,
    product_id: Optional[str] = None,
    phase: Optional[str] = None,
    conditions_met: Optional[bool] = None,
    since: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Get indicator condition evaluation logs (most recent first)

    Args:
        bot_id: Bot ID to get logs for
        limit: Maximum number of logs to return
        offset: Pagination offset
        product_id: Optional filter by trading pair (e.g., "ETH-BTC")
        phase: Optional filter by phase ("base_order", "safety_order", "take_profit")
        conditions_met: Optional filter by whether conditions were met
        since: Optional filter for logs since this timestamp
    """
    # Verify bot exists and belongs to user
    bot_query = select(Bot).where(Bot.id == bot_id)
    # Filter by user if authenticated
    if current_user:
        bot_query = bot_query.where(Bot.user_id == current_user.id)
    bot_result = await db.execute(bot_query)
    bot = bot_result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Build query with optional filters
    logs_query = select(IndicatorLog).where(IndicatorLog.bot_id == bot_id)

    if product_id:
        logs_query = logs_query.where(IndicatorLog.product_id == product_id)

    if phase:
        logs_query = logs_query.where(IndicatorLog.phase == phase)

    if conditions_met is not None:
        logs_query = logs_query.where(IndicatorLog.conditions_met == conditions_met)

    if since:
        logs_query = logs_query.where(IndicatorLog.timestamp >= since)

    logs_query = logs_query.order_by(desc(IndicatorLog.timestamp)).limit(limit).offset(offset)

    logs_result = await db.execute(logs_query)
    logs = logs_result.scalars().all()

    return [IndicatorLogResponse.model_validate(log) for log in logs]


@router.get("/{bot_id}/indicator-logs/summary")
async def get_indicator_logs_summary(
    bot_id: int,
    product_id: Optional[str] = None,
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Get a summary of indicator evaluations over a time period.

    Returns counts of conditions met vs not met by phase.
    """
    from datetime import timedelta

    # Verify bot exists and belongs to user
    bot_query = select(Bot).where(Bot.id == bot_id)
    if current_user:
        bot_query = bot_query.where(Bot.user_id == current_user.id)
    bot_result = await db.execute(bot_query)
    bot = bot_result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    since = datetime.utcnow() - timedelta(hours=hours)

    # Build base query
    base_query = select(IndicatorLog).where(
        IndicatorLog.bot_id == bot_id,
        IndicatorLog.timestamp >= since
    )

    if product_id:
        base_query = base_query.where(IndicatorLog.product_id == product_id)

    result = await db.execute(base_query)
    logs = list(result.scalars().all())

    # Aggregate by phase
    summary = {
        "total_evaluations": len(logs),
        "time_period_hours": hours,
        "by_phase": {},
        "by_product": {},
    }

    for log in logs:
        # By phase
        if log.phase not in summary["by_phase"]:
            summary["by_phase"][log.phase] = {"total": 0, "met": 0, "not_met": 0}
        summary["by_phase"][log.phase]["total"] += 1
        if log.conditions_met:
            summary["by_phase"][log.phase]["met"] += 1
        else:
            summary["by_phase"][log.phase]["not_met"] += 1

        # By product
        if log.product_id not in summary["by_product"]:
            summary["by_product"][log.product_id] = {"total": 0, "met": 0, "not_met": 0}
        summary["by_product"][log.product_id]["total"] += 1
        if log.conditions_met:
            summary["by_product"][log.product_id]["met"] += 1
        else:
            summary["by_product"][log.product_id]["not_met"] += 1

    return summary
