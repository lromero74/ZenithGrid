"""
Bot AI Logs Router

Handles AI bot reasoning/thinking log creation and retrieval.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AIBotLog, IndicatorLog, Bot, User
from app.bot_routers.schemas import AIBotLogCreate, AIBotLogResponse
from app.routers.auth_dependencies import get_current_user_optional

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{bot_id}/logs", response_model=AIBotLogResponse, status_code=201)
async def create_ai_bot_log(
    bot_id: int,
    log_data: AIBotLogCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Save AI bot reasoning/thinking log"""
    # Verify bot exists and belongs to user
    bot_query = select(Bot).where(Bot.id == bot_id)
    # Filter by user if authenticated
    if current_user:
        bot_query = bot_query.where(Bot.user_id == current_user.id)
    bot_result = await db.execute(bot_query)
    bot = bot_result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Create log entry
    log_entry = AIBotLog(
        bot_id=bot_id,
        thinking=log_data.thinking,
        decision=log_data.decision,
        confidence=log_data.confidence,
        current_price=log_data.current_price,
        position_status=log_data.position_status,
        context=log_data.context,
        timestamp=datetime.utcnow(),
    )

    db.add(log_entry)
    await db.commit()
    await db.refresh(log_entry)

    return AIBotLogResponse.model_validate(log_entry)


@router.get("/{bot_id}/logs", response_model=List[AIBotLogResponse])
async def get_ai_bot_logs(
    bot_id: int,
    limit: int = 50,
    offset: int = 0,
    product_id: Optional[str] = None,
    position_id: Optional[int] = None,
    since: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Get AI bot reasoning logs (most recent first)

    Args:
        bot_id: Bot ID to get logs for
        limit: Maximum number of logs to return
        offset: Pagination offset
        product_id: Optional filter by trading pair (e.g., "ETH-BTC")
        position_id: Optional filter by position ID
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
    logs_query = select(AIBotLog).where(AIBotLog.bot_id == bot_id)

    if product_id:
        logs_query = logs_query.where(AIBotLog.product_id == product_id)

    if position_id is not None:
        logs_query = logs_query.where(AIBotLog.position_id == position_id)

    if since:
        logs_query = logs_query.where(AIBotLog.timestamp >= since)

    logs_query = logs_query.order_by(desc(AIBotLog.timestamp)).limit(limit).offset(offset)

    logs_result = await db.execute(logs_query)
    logs = logs_result.scalars().all()

    return [AIBotLogResponse.model_validate(log) for log in logs]


@router.get("/{bot_id}/decision-logs")
async def get_unified_decision_logs(
    bot_id: int,
    limit: int = 50,
    offset: int = 0,
    product_id: Optional[str] = None,
    since: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Get unified decision logs (AI + Indicator) in chronological order.

    Returns both AI reasoning logs and indicator evaluation logs merged by timestamp.
    Each entry has a 'log_type' field indicating 'ai' or 'indicator'.

    Args:
        bot_id: Bot ID to get logs for
        limit: Maximum number of logs to return
        offset: Pagination offset
        product_id: Optional filter by trading pair
        since: Optional filter for logs since this timestamp
    """
    # Verify bot exists and belongs to user
    bot_query = select(Bot).where(Bot.id == bot_id)
    if current_user:
        bot_query = bot_query.where(Bot.user_id == current_user.id)
    bot_result = await db.execute(bot_query)
    bot = bot_result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Query AI logs
    ai_logs_query = select(AIBotLog).where(AIBotLog.bot_id == bot_id)
    if product_id:
        ai_logs_query = ai_logs_query.where(AIBotLog.product_id == product_id)
    if since:
        ai_logs_query = ai_logs_query.where(AIBotLog.timestamp >= since)

    ai_logs_result = await db.execute(ai_logs_query)
    ai_logs = ai_logs_result.scalars().all()

    # Query Indicator logs
    indicator_logs_query = select(IndicatorLog).where(IndicatorLog.bot_id == bot_id)
    if product_id:
        indicator_logs_query = indicator_logs_query.where(IndicatorLog.product_id == product_id)
    if since:
        indicator_logs_query = indicator_logs_query.where(IndicatorLog.timestamp >= since)

    indicator_logs_result = await db.execute(indicator_logs_query)
    indicator_logs = indicator_logs_result.scalars().all()

    # Convert to unified format
    unified_logs = []

    # Add AI logs
    for log in ai_logs:
        unified_logs.append({
            "log_type": "ai",
            "id": log.id,
            "timestamp": log.timestamp,
            "product_id": log.product_id,
            "decision": log.decision,
            "confidence": log.confidence,
            "thinking": log.thinking,
            "current_price": log.current_price,
            "position_status": log.position_status,
            "context": log.context,
            "position_id": log.position_id,
        })

    # Add Indicator logs
    for log in indicator_logs:
        unified_logs.append({
            "log_type": "indicator",
            "id": log.id,
            "timestamp": log.timestamp,
            "product_id": log.product_id,
            "phase": log.phase,
            "conditions_met": log.conditions_met,
            "conditions_detail": log.conditions_detail,
            "indicators_snapshot": log.indicators_snapshot,
            "current_price": log.current_price,
        })

    # Sort by timestamp descending (most recent first)
    unified_logs.sort(key=lambda x: x["timestamp"], reverse=True)

    # Apply pagination
    paginated_logs = unified_logs[offset:offset + limit]

    return paginated_logs
