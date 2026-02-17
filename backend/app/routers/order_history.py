"""
Order History API Router

Provides endpoints for viewing order history (successful and failed orders).
Similar to 3Commas order history page.
"""

from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Bot, OrderHistory, User
from app.routers.auth_dependencies import get_current_user

T = TypeVar("T")

router = APIRouter(prefix="/api/order-history", tags=["order-history"])


class OrderHistoryResponse(BaseModel):
    """Order history record for API response"""

    id: int
    timestamp: datetime
    bot_id: int
    bot_name: str
    account_id: Optional[int]
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


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper"""

    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int


@router.get("/", response_model=List[OrderHistoryResponse])
async def get_order_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    bot_id: Optional[int] = Query(None, description="Filter by bot ID"),
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    status: Optional[str] = Query(None, description="Filter by status (success, failed, canceled)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
):
    """
    Get order history with optional filtering.

    Returns all order attempts (successful and failed) in reverse chronological order.
    Similar to 3Commas order history.
    """
    # Build query - include account_id from Bot for filtering
    # CRITICAL: Always filter by current user's bots for multi-user isolation
    query = (
        select(OrderHistory, Bot.name.label("bot_name"), Bot.account_id.label("account_id"))
        .join(Bot, OrderHistory.bot_id == Bot.id)
        .where(Bot.user_id == current_user.id)
        .order_by(desc(OrderHistory.timestamp))
    )

    # Apply filters
    if bot_id is not None:
        query = query.where(OrderHistory.bot_id == bot_id)

    if account_id is not None:
        query = query.where(Bot.account_id == account_id)

    if status is not None:
        query = query.where(OrderHistory.status == status)

    # Apply pagination
    query = query.limit(limit).offset(offset)

    # Execute query
    result = await db.execute(query)
    rows = result.all()

    # Format response
    history = []
    for order_history, bot_name, account_id in rows:
        history.append(
            OrderHistoryResponse(
                id=order_history.id,
                timestamp=order_history.timestamp,
                bot_id=order_history.bot_id,
                bot_name=bot_name,
                account_id=account_id,
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
    current_user: User = Depends(get_current_user),
    bot_id: Optional[int] = Query(None, description="Filter by bot ID"),
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of records to return"),
):
    """
    Get recent failed orders.

    Useful for debugging and troubleshooting.
    """
    return await get_order_history(db=db, current_user=current_user, bot_id=bot_id, account_id=account_id, status="failed", limit=limit, offset=0)


@router.get("/failed/paginated")
async def get_failed_orders_paginated(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    bot_id: Optional[int] = Query(None, description="Filter by bot ID"),
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
):
    """
    Get paginated failed orders with total count.

    Returns items plus pagination metadata for UI controls.
    """
    # Build base query for counting - always filter by current user's bots
    count_query = (
        select(func.count())
        .select_from(OrderHistory)
        .join(Bot, OrderHistory.bot_id == Bot.id)
        .where(OrderHistory.status == "failed")
        .where(Bot.user_id == current_user.id)
    )

    if account_id is not None:
        count_query = count_query.where(Bot.account_id == account_id)

    if bot_id is not None:
        count_query = count_query.where(OrderHistory.bot_id == bot_id)

    # Get total count
    result = await db.execute(count_query)
    total = result.scalar() or 0

    # Calculate offset
    offset = (page - 1) * page_size
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    # Get paginated items
    items = await get_order_history(db=db, current_user=current_user, bot_id=bot_id, account_id=account_id, status="failed", limit=page_size, offset=offset)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/stats")
async def get_order_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    bot_id: Optional[int] = Query(None, description="Filter by bot ID"),
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
):
    """
    Get order statistics (success rate, failure rate, etc.)
    """
    # Build base query - always filter by current user's bots
    query = (
        select(OrderHistory)
        .join(Bot, OrderHistory.bot_id == Bot.id)
        .where(Bot.user_id == current_user.id)
    )

    if account_id is not None:
        query = query.where(Bot.account_id == account_id)

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
