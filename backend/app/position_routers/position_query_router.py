"""
Position Query Router

Handles position listing, details, trades, AI logs, and P&L timeseries.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AIBotLog, Bot, PendingOrder, Position, Trade
from app.schemas import AIBotLogResponse, PositionResponse, TradeResponse
from app.schemas.position import LimitOrderDetails, LimitOrderFill
from app.coinbase_unified_client import CoinbaseClient
from app.position_routers.dependencies import get_coinbase

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=List[PositionResponse])
async def get_positions(
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase),
):
    """Get positions with optional status filter"""
    query = select(Position)
    if status:
        query = query.where(Position.status == status)
    query = query.order_by(desc(Position.opened_at)).limit(limit)

    result = await db.execute(query)
    positions = result.scalars().all()

    response = []
    for pos in positions:
        # Count trades
        trade_count_query = select(func.count(Trade.id)).where(Trade.position_id == pos.id)
        trade_count_result = await db.execute(trade_count_query)
        trade_count = trade_count_result.scalar()

        # Count pending orders
        pending_count_query = select(func.count(PendingOrder.id)).where(
            PendingOrder.position_id == pos.id, PendingOrder.status == "pending"
        )
        pending_count_result = await db.execute(pending_count_query)
        pending_count = pending_count_result.scalar()

        pos_response = PositionResponse.model_validate(pos)
        pos_response.trade_count = trade_count
        pos_response.pending_orders_count = pending_count

        # If position is closing via limit, fetch order details
        if pos.closing_via_limit and pos.limit_close_order_id:
            limit_order_query = select(PendingOrder).where(PendingOrder.order_id == pos.limit_close_order_id)
            limit_order_result = await db.execute(limit_order_query)
            limit_order = limit_order_result.scalars().first()

            if limit_order:
                fills_data = (
                    json.loads(limit_order.fills) if isinstance(limit_order.fills, str) else (limit_order.fills or [])
                )
                fills = [LimitOrderFill(**fill) for fill in fills_data]
                filled_amount = limit_order.base_amount - (limit_order.remaining_base_amount or limit_order.base_amount)
                fill_percentage = (filled_amount / limit_order.base_amount * 100) if limit_order.base_amount > 0 else 0

                pos_response.limit_order_details = LimitOrderDetails(
                    limit_price=limit_order.limit_price,
                    remaining_amount=limit_order.remaining_base_amount or limit_order.base_amount,
                    filled_amount=filled_amount,
                    fill_percentage=fill_percentage,
                    fills=fills,
                    status=limit_order.status,
                )

        response.append(pos_response)

    return response


@router.get("/pnl-timeseries")
async def get_pnl_timeseries(db: AsyncSession = Depends(get_db)):
    """
    Get P&L time series data for cumulative profit chart (3Commas-style).

    Returns cumulative profit over time from all closed positions.
    """
    # Get all closed positions ordered by close date
    query = (
        select(Position)
        .where(Position.status == "closed", Position.closed_at != None, Position.profit_usd != None)
        .order_by(Position.closed_at)
    )

    result = await db.execute(query)
    positions = result.scalars().all()

    if not positions:
        # No data yet
        return {"summary": [], "by_day": [], "by_pair": []}

    # Build cumulative P&L over time
    cumulative_pnl = 0.0
    summary_data = []
    daily_pnl = defaultdict(float)
    pair_pnl = defaultdict(float)

    for pos in positions:
        profit = pos.profit_usd or 0.0
        cumulative_pnl += profit

        # Add to summary timeline
        summary_data.append(
            {
                "timestamp": pos.closed_at.isoformat(),
                "date": pos.closed_at.strftime("%Y-%m-%d"),
                "cumulative_pnl": round(cumulative_pnl, 2),
                "profit": round(profit, 2),
            }
        )

        # Aggregate by day
        day_key = pos.closed_at.date().isoformat()
        daily_pnl[day_key] += profit

        # Aggregate by pair
        pair_pnl[pos.product_id] += profit

    # Convert daily P&L to cumulative
    by_day_data = []
    cumulative = 0.0
    for day in sorted(daily_pnl.keys()):
        cumulative += daily_pnl[day]
        by_day_data.append({"date": day, "daily_pnl": round(daily_pnl[day], 2), "cumulative_pnl": round(cumulative, 2)})

    # Convert pair P&L to list
    by_pair_data = [
        {"pair": pair, "total_pnl": round(pnl, 2)}
        for pair, pnl in sorted(pair_pnl.items(), key=lambda x: x[1], reverse=True)
    ]

    # Get active trades count
    active_count_query = select(func.count(Position.id)).where(Position.status == "open")
    active_count_result = await db.execute(active_count_query)
    active_trades = active_count_result.scalar() or 0

    # Get bot-level P&L for most profitable bot
    bot_pnl_query = (
        select(Position.bot_id, func.sum(Position.profit_usd).label("total_pnl"))
        .where(Position.status == "closed", Position.profit_usd != None)
        .group_by(Position.bot_id)
        .order_by(func.sum(Position.profit_usd).desc())
    )

    bot_pnl_result = await db.execute(bot_pnl_query)
    bot_pnls = bot_pnl_result.all()

    most_profitable_bot = None
    if bot_pnls:
        top_bot_id, top_bot_pnl = bot_pnls[0]
        # Get bot name
        bot_query = select(Bot).where(Bot.id == top_bot_id)
        bot_result = await db.execute(bot_query)
        bot = bot_result.scalars().first()
        if bot:
            most_profitable_bot = {"bot_id": top_bot_id, "bot_name": bot.name, "total_pnl": round(top_bot_pnl, 2)}

    return {
        "summary": summary_data,
        "by_day": by_day_data,
        "by_pair": by_pair_data,
        "active_trades": active_trades,
        "most_profitable_bot": most_profitable_bot,
    }


@router.get("/{position_id}", response_model=PositionResponse)
async def get_position(position_id: int, db: AsyncSession = Depends(get_db)):
    """Get specific position details"""
    from fastapi import HTTPException

    query = select(Position).where(Position.id == position_id)
    result = await db.execute(query)
    position = result.scalars().first()

    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    # Count trades
    trade_count_query = select(func.count(Trade.id)).where(Trade.position_id == position.id)
    trade_count_result = await db.execute(trade_count_query)
    trade_count = trade_count_result.scalar()

    # Count pending orders
    pending_count_query = select(func.count(PendingOrder.id)).where(
        PendingOrder.position_id == position.id, PendingOrder.status == "pending"
    )
    pending_count_result = await db.execute(pending_count_query)
    pending_count = pending_count_result.scalar()

    pos_response = PositionResponse.model_validate(position)
    pos_response.trade_count = trade_count
    pos_response.pending_orders_count = pending_count

    return pos_response


@router.get("/{position_id}/trades", response_model=List[TradeResponse])
async def get_position_trades(position_id: int, db: AsyncSession = Depends(get_db)):
    """Get all trades for a position"""
    query = select(Trade).where(Trade.position_id == position_id).order_by(Trade.timestamp)
    result = await db.execute(query)
    trades = result.scalars().all()

    return [TradeResponse.model_validate(t) for t in trades]


@router.get("/{position_id}/ai-logs", response_model=List[AIBotLogResponse])
async def get_position_ai_logs(position_id: int, include_before_open: bool = True, db: AsyncSession = Depends(get_db)):
    """
    Get AI reasoning logs for a position.

    By default, includes logs from 30 seconds before position opened and
    30 seconds after position closed. This captures the AI's complete
    decision-making process including what led to opening and closing.
    """
    from fastapi import HTTPException

    # Get the position to know when it was opened/closed
    pos_query = select(Position).where(Position.id == position_id)
    pos_result = await db.execute(pos_query)
    position = pos_result.scalars().first()

    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    # Build query for AI logs
    query = select(AIBotLog).where(AIBotLog.position_id == position_id)

    # If include_before_open is True, also get logs from 30s before open and 30s after close
    # that belong to the same bot and product
    if include_before_open and position.opened_at:
        time_before = position.opened_at - timedelta(seconds=30)

        # Calculate time after (30s after close, or far future if still open)
        if position.closed_at:
            time_after = position.closed_at + timedelta(seconds=30)
        else:
            time_after = datetime.utcnow() + timedelta(days=365)

        query = select(AIBotLog).where(
            (AIBotLog.position_id == position_id)
            | (
                (AIBotLog.bot_id == position.bot_id)
                & (AIBotLog.product_id == position.product_id)
                & (AIBotLog.timestamp >= time_before)
                & (AIBotLog.timestamp <= time_after)
                & (AIBotLog.position_id == None)
            )
        )

    query = query.order_by(AIBotLog.timestamp)

    result = await db.execute(query)
    logs = result.scalars().all()

    return [AIBotLogResponse.model_validate(log) for log in logs]
