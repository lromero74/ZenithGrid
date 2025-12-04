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
from app.models import AIBotLog, Bot, User
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
