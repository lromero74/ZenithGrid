"""
Bot AI Logs Router

Handles AI bot reasoning/thinking log creation and retrieval.
"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select, union_all, literal
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

    Uses SQL UNION ALL to merge both log tables at database level with proper
    pagination. Database handles sorting and limiting for optimal performance.

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

    # Build AI logs subquery with discriminator column
    ai_logs_stmt = select(
        literal('ai').label('log_type'),
        AIBotLog.id,
        AIBotLog.bot_id,
        AIBotLog.timestamp,
        AIBotLog.product_id,
        AIBotLog.thinking,
        AIBotLog.decision,
        AIBotLog.confidence,
        AIBotLog.current_price,
        AIBotLog.position_status,
        AIBotLog.position_id,
        AIBotLog.context,
        literal(None).label('phase'),
        literal(None).label('conditions_met'),
        literal(None).label('conditions_detail'),
        literal(None).label('indicators_snapshot'),
    ).where(AIBotLog.bot_id == bot_id)

    # Apply optional filters to AI logs
    if product_id:
        ai_logs_stmt = ai_logs_stmt.where(AIBotLog.product_id == product_id)
    if since:
        ai_logs_stmt = ai_logs_stmt.where(AIBotLog.timestamp >= since)

    # Build Indicator logs subquery with discriminator column
    indicator_logs_stmt = select(
        literal('indicator').label('log_type'),
        IndicatorLog.id,
        IndicatorLog.bot_id,
        IndicatorLog.timestamp,
        IndicatorLog.product_id,
        literal(None).label('thinking'),
        literal(None).label('decision'),
        literal(None).label('confidence'),
        IndicatorLog.current_price,
        literal(None).label('position_status'),
        literal(None).label('position_id'),
        literal(None).label('context'),
        IndicatorLog.phase,
        IndicatorLog.conditions_met,
        IndicatorLog.conditions_detail,
        IndicatorLog.indicators_snapshot,
    ).where(IndicatorLog.bot_id == bot_id)

    # Apply optional filters to Indicator logs
    if product_id:
        indicator_logs_stmt = indicator_logs_stmt.where(
            IndicatorLog.product_id == product_id
        )
    if since:
        indicator_logs_stmt = indicator_logs_stmt.where(
            IndicatorLog.timestamp >= since
        )

    # UNION ALL both queries
    union_stmt = union_all(ai_logs_stmt, indicator_logs_stmt)

    # Apply ORDER BY and pagination at SQL level
    final_query = (
        select(union_stmt.c)  # Select all columns from union result
        .order_by(desc(union_stmt.c.timestamp))
        .limit(limit)
        .offset(offset)
    )

    # Execute query
    result = await db.execute(final_query)
    rows = result.fetchall()

    # Convert rows to response dictionaries
    unified_logs = []
    for row in rows:
        log_dict = {
            'log_type': row.log_type,
            'id': row.id,
            'bot_id': row.bot_id,
            'timestamp': row.timestamp,
            'product_id': row.product_id,
            'current_price': row.current_price,
        }

        # Add AI-specific fields if this is an AI log
        if row.log_type == 'ai':
            # Parse JSON context if it's a string
            context = row.context
            if isinstance(context, str):
                try:
                    context = json.loads(context)
                except (json.JSONDecodeError, TypeError):
                    pass

            log_dict.update({
                'thinking': row.thinking,
                'decision': row.decision,
                'confidence': row.confidence,
                'position_status': row.position_status,
                'position_id': row.position_id,
                'context': context,
            })

        # Add Indicator-specific fields if this is an indicator log
        if row.log_type == 'indicator':
            # Parse JSON fields if they're strings
            conditions_detail = row.conditions_detail
            if isinstance(conditions_detail, str):
                try:
                    conditions_detail = json.loads(conditions_detail)
                except (json.JSONDecodeError, TypeError):
                    pass

            indicators_snapshot = row.indicators_snapshot
            if isinstance(indicators_snapshot, str):
                try:
                    indicators_snapshot = json.loads(indicators_snapshot)
                except (json.JSONDecodeError, TypeError):
                    pass

            log_dict.update({
                'phase': row.phase,
                'conditions_met': row.conditions_met,
                'conditions_detail': conditions_detail,
                'indicators_snapshot': indicators_snapshot,
            })

        unified_logs.append(log_dict)

    return unified_logs
