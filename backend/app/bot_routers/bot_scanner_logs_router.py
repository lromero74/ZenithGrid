"""
Bot Scanner Logs Router

Handles scanner/monitor log creation and retrieval for non-AI strategies.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ScannerLog, Bot
from app.bot_routers.schemas import ScannerLogCreate, ScannerLogResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{bot_id}/scanner-logs", response_model=ScannerLogResponse, status_code=201)
async def create_scanner_log(bot_id: int, log_data: ScannerLogCreate, db: AsyncSession = Depends(get_db)):
    """Save scanner/monitor reasoning log"""
    # Verify bot exists
    bot_query = select(Bot).where(Bot.id == bot_id)
    bot_result = await db.execute(bot_query)
    bot = bot_result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Create log entry
    log_entry = ScannerLog(
        bot_id=bot_id,
        product_id=log_data.product_id,
        scan_type=log_data.scan_type,
        decision=log_data.decision,
        reason=log_data.reason,
        current_price=log_data.current_price,
        volume_ratio=log_data.volume_ratio,
        pattern_data=log_data.pattern_data,
        timestamp=datetime.utcnow(),
    )

    db.add(log_entry)
    await db.commit()
    await db.refresh(log_entry)

    return ScannerLogResponse.model_validate(log_entry)


@router.get("/{bot_id}/scanner-logs", response_model=List[ScannerLogResponse])
async def get_scanner_logs(
    bot_id: int,
    limit: int = 100,
    offset: int = 0,
    product_id: Optional[str] = None,
    scan_type: Optional[str] = None,
    decision: Optional[str] = None,
    since: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Get scanner/monitor logs (most recent first)

    Args:
        bot_id: Bot ID to get logs for
        limit: Maximum number of logs to return
        offset: Pagination offset
        product_id: Optional filter by trading pair
        scan_type: Optional filter by scan type (volume_check, pattern_check, etc.)
        decision: Optional filter by decision (passed, rejected, triggered, hold)
        since: Optional filter for logs since this timestamp
    """
    # Verify bot exists
    bot_query = select(Bot).where(Bot.id == bot_id)
    bot_result = await db.execute(bot_query)
    bot = bot_result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Build query
    query = select(ScannerLog).where(ScannerLog.bot_id == bot_id)

    if product_id:
        query = query.where(ScannerLog.product_id == product_id)

    if scan_type:
        query = query.where(ScannerLog.scan_type == scan_type)

    if decision:
        query = query.where(ScannerLog.decision == decision)

    if since:
        query = query.where(ScannerLog.timestamp >= since)

    query = query.order_by(desc(ScannerLog.timestamp)).offset(offset).limit(limit)

    result = await db.execute(query)
    logs = result.scalars().all()

    return [ScannerLogResponse.model_validate(log) for log in logs]


@router.delete("/{bot_id}/scanner-logs")
async def clear_scanner_logs(
    bot_id: int,
    older_than_hours: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Clear scanner logs for a bot.

    Args:
        bot_id: Bot ID to clear logs for
        older_than_hours: Only delete logs older than this many hours (optional)
    """
    from sqlalchemy import delete
    from datetime import timedelta

    # Verify bot exists
    bot_query = select(Bot).where(Bot.id == bot_id)
    bot_result = await db.execute(bot_query)
    bot = bot_result.scalars().first()

    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Build delete query
    delete_query = delete(ScannerLog).where(ScannerLog.bot_id == bot_id)

    if older_than_hours:
        cutoff = datetime.utcnow() - timedelta(hours=older_than_hours)
        delete_query = delete_query.where(ScannerLog.timestamp < cutoff)

    result = await db.execute(delete_query)
    await db.commit()

    return {"deleted": result.rowcount}
