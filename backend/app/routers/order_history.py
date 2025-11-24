"""
Order History API Router

Provides endpoints for viewing order history (successful and failed orders).
Similar to 3Commas order history page.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Bot, OrderHistory

router = APIRouter(prefix="/api/order-history", tags=["order-history"])


class OrderHistoryResponse(BaseModel):
    """Order history record for API response"""

    id: int
    timestamp: datetime
    bot_id: int
    bot_name: str
    position_id: Optional[int]
    product_id: str
    side: str
    order_type: str
    trade_type: str
    quote_amount: float
    base_amount: Optional[float]
    price: Optional[float]
    status: str
    order_id: Optional[str]
    error_message: Optional[str]

    class Config:
        from_attributes = True


@router.get("/", response_model=List[OrderHistoryResponse])
async def get_order_history(
    db: AsyncSession = Depends(get_db),
    bot_id: Optional[int] = Query(None, description="Filter by bot ID"),
    status: Optional[str] = Query(None, description="Filter by status (success, failed, canceled)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
):
    """
    Get order history with optional filtering.

    Returns all order attempts (successful and failed) in reverse chronological order.
    Similar to 3Commas order history.
    """
    # Build query
    query = (
        select(OrderHistory, Bot.name.label("bot_name"))
        .join(Bot, OrderHistory.bot_id == Bot.id)
        .order_by(desc(OrderHistory.timestamp))
    )

    # Apply filters
    if bot_id is not None:
        query = query.where(OrderHistory.bot_id == bot_id)

    if status is not None:
        query = query.where(OrderHistory.status == status)

    # Apply pagination
    query = query.limit(limit).offset(offset)

    # Execute query
    result = await db.execute(query)
    rows = result.all()

    # Format response
    history = []
    for order_history, bot_name in rows:
        history.append(
            OrderHistoryResponse(
                id=order_history.id,
                timestamp=order_history.timestamp,
                bot_id=order_history.bot_id,
                bot_name=bot_name,
                position_id=order_history.position_id,
                product_id=order_history.product_id,
                side=order_history.side,
                order_type=order_history.order_type,
                trade_type=order_history.trade_type,
                quote_amount=order_history.quote_amount,
                base_amount=order_history.base_amount,
                price=order_history.price,
                status=order_history.status,
                order_id=order_history.order_id,
                error_message=order_history.error_message,
            )
        )

    return history


@router.get("/failed", response_model=List[OrderHistoryResponse])
async def get_failed_orders(
    db: AsyncSession = Depends(get_db),
    bot_id: Optional[int] = Query(None, description="Filter by bot ID"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of records to return"),
):
    """
    Get recent failed orders.

    Useful for debugging and troubleshooting.
    """
    return await get_order_history(db=db, bot_id=bot_id, status="failed", limit=limit, offset=0)


@router.get("/stats")
async def get_order_stats(
    db: AsyncSession = Depends(get_db), bot_id: Optional[int] = Query(None, description="Filter by bot ID")
):
    """
    Get order statistics (success rate, failure rate, etc.)
    """
    # Build base query
    query = select(OrderHistory)

    if bot_id is not None:
        query = query.where(OrderHistory.bot_id == bot_id)

    result = await db.execute(query)
    all_orders = result.scalars().all()

    total_orders = len(all_orders)
    successful_orders = len([o for o in all_orders if o.status == "success"])
    failed_orders = len([o for o in all_orders if o.status == "failed"])
    canceled_orders = len([o for o in all_orders if o.status == "canceled"])

    return {
        "total_orders": total_orders,
        "successful_orders": successful_orders,
        "failed_orders": failed_orders,
        "canceled_orders": canceled_orders,
        "success_rate": (successful_orders / total_orders * 100) if total_orders > 0 else 0,
        "failure_rate": (failed_orders / total_orders * 100) if total_orders > 0 else 0,
    }
