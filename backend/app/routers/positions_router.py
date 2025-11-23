"""
Position management API routes

Handles all position-related endpoints:
- List positions
- Position details
- Position trades and AI logs
- Position actions (cancel, force-close, limit-close, add-funds, notes)
- P&L time series data
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_unified_client import CoinbaseClient
from app.database import get_db
from app.models import AIBotLog, Bot, PendingOrder, Position, Trade
from app.schemas import AIBotLogResponse, PositionResponse, TradeResponse
from app.schemas.position import LimitOrderDetails, LimitOrderFill
from app.trading_client import TradingClient
from app.trading_engine_v2 import StrategyTradingEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/positions", tags=["positions"])


# Request Models
class AddFundsRequest(BaseModel):
    btc_amount: float


class UpdateNotesRequest(BaseModel):
    notes: str


class LimitCloseRequest(BaseModel):
    limit_price: float


class UpdateLimitCloseRequest(BaseModel):
    new_limit_price: float


# Dependency - these will be injected from main.py
def get_coinbase() -> CoinbaseClient:
    """Get coinbase client - will be overridden in main.py"""
    raise NotImplementedError("Must override coinbase dependency")


@router.get("", response_model=List[PositionResponse])
async def get_positions(
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase)
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
            PendingOrder.position_id == pos.id,
            PendingOrder.status == "pending"
        )
        pending_count_result = await db.execute(pending_count_query)
        pending_count = pending_count_result.scalar()

        pos_response = PositionResponse.model_validate(pos)
        pos_response.trade_count = trade_count
        pos_response.pending_orders_count = pending_count

        # If position is closing via limit, fetch order details
        if pos.closing_via_limit and pos.limit_close_order_id:
            limit_order_query = select(PendingOrder).where(
                PendingOrder.order_id == pos.limit_close_order_id
            )
            limit_order_result = await db.execute(limit_order_query)
            limit_order = limit_order_result.scalars().first()

            if limit_order:
                fills_data = json.loads(limit_order.fills) if isinstance(limit_order.fills, str) else (limit_order.fills or [])
                fills = [LimitOrderFill(**fill) for fill in fills_data]
                filled_amount = limit_order.base_amount - (limit_order.remaining_base_amount or limit_order.base_amount)
                fill_percentage = (filled_amount / limit_order.base_amount * 100) if limit_order.base_amount > 0 else 0

                pos_response.limit_order_details = LimitOrderDetails(
                    limit_price=limit_order.limit_price,
                    remaining_amount=limit_order.remaining_base_amount or limit_order.base_amount,
                    filled_amount=filled_amount,
                    fill_percentage=fill_percentage,
                    fills=fills,
                    status=limit_order.status
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
    query = select(Position).where(
        Position.status == "closed",
        Position.closed_at != None,
        Position.profit_usd != None
    ).order_by(Position.closed_at)

    result = await db.execute(query)
    positions = result.scalars().all()

    if not positions:
        # No data yet
        return {
            "summary": [],
            "by_day": [],
            "by_pair": []
        }

    # Build cumulative P&L over time
    cumulative_pnl = 0.0
    summary_data = []
    daily_pnl = defaultdict(float)
    pair_pnl = defaultdict(float)

    for pos in positions:
        profit = pos.profit_usd or 0.0
        cumulative_pnl += profit

        # Add to summary timeline
        summary_data.append({
            "timestamp": pos.closed_at.isoformat(),
            "date": pos.closed_at.strftime("%Y-%m-%d"),
            "cumulative_pnl": round(cumulative_pnl, 2),
            "profit": round(profit, 2)
        })

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
        by_day_data.append({
            "date": day,
            "daily_pnl": round(daily_pnl[day], 2),
            "cumulative_pnl": round(cumulative, 2)
        })

    # Convert pair P&L to list
    by_pair_data = [
        {
            "pair": pair,
            "total_pnl": round(pnl, 2)
        }
        for pair, pnl in sorted(pair_pnl.items(), key=lambda x: x[1], reverse=True)
    ]

    # Get active trades count
    active_count_query = select(func.count(Position.id)).where(Position.status == "open")
    active_count_result = await db.execute(active_count_query)
    active_trades = active_count_result.scalar() or 0

    # Get bot-level P&L for most profitable bot
    bot_pnl_query = select(
        Position.bot_id,
        func.sum(Position.profit_usd).label('total_pnl')
    ).where(
        Position.status == "closed",
        Position.profit_usd != None
    ).group_by(Position.bot_id).order_by(func.sum(Position.profit_usd).desc())

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
            most_profitable_bot = {
                "bot_id": top_bot_id,
                "bot_name": bot.name,
                "total_pnl": round(top_bot_pnl, 2)
            }

    return {
        "summary": summary_data,
        "by_day": by_day_data,
        "by_pair": by_pair_data,
        "active_trades": active_trades,
        "most_profitable_bot": most_profitable_bot
    }


@router.get("/{position_id}", response_model=PositionResponse)
async def get_position(position_id: int, db: AsyncSession = Depends(get_db)):
    """Get specific position details"""
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
        PendingOrder.position_id == position.id,
        PendingOrder.status == "pending"
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
async def get_position_ai_logs(
    position_id: int,
    include_before_open: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """
    Get AI reasoning logs for a position.

    By default, includes logs from 30 seconds before position opened and
    30 seconds after position closed. This captures the AI's complete
    decision-making process including what led to opening and closing.
    """
    # Get the position to know when it was opened/closed
    pos_query = select(Position).where(Position.id == position_id)
    pos_result = await db.execute(pos_query)
    position = pos_result.scalars().first()

    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    # Build query for AI logs
    query = select(AIBotLog).where(
        AIBotLog.position_id == position_id
    )

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
            (AIBotLog.position_id == position_id) |
            (
                (AIBotLog.bot_id == position.bot_id) &
                (AIBotLog.product_id == position.product_id) &
                (AIBotLog.timestamp >= time_before) &
                (AIBotLog.timestamp <= time_after) &
                (AIBotLog.position_id == None)
            )
        )

    query = query.order_by(AIBotLog.timestamp)

    result = await db.execute(query)
    logs = result.scalars().all()

    return [AIBotLogResponse.model_validate(log) for log in logs]


@router.post("/{position_id}/cancel")
async def cancel_position(position_id: int, db: AsyncSession = Depends(get_db)):
    """Cancel a position without selling (leave balances as-is)"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if position.status != "open":
            raise HTTPException(status_code=400, detail="Position is not open")

        # Mark position as cancelled
        position.status = "cancelled"
        position.closed_at = datetime.utcnow()

        await db.commit()

        return {"message": f"Position {position_id} cancelled successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{position_id}/force-close")
async def force_close_position(
    position_id: int,
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase)
):
    """Force close a position at current market price"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if position.status != "open":
            raise HTTPException(status_code=400, detail="Position is not open")

        # Get the bot associated with this position
        bot_query = select(Bot).where(Bot.id == position.bot_id)
        bot_result = await db.execute(bot_query)
        bot = bot_result.scalars().first()

        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found for this position")

        # Get current price for the position's product
        current_price = await coinbase.get_current_price(position.product_id)

        # Create strategy instance for this bot
        from app.strategies import StrategyRegistry
        strategy = StrategyRegistry.get_strategy(bot.strategy_type, bot.strategy_config)

        # Execute sell using trading engine
        engine = StrategyTradingEngine(
            db=db,
            coinbase=coinbase,
            bot=bot,
            strategy=strategy,
            product_id=position.product_id
        )
        trade, profit_quote, profit_percentage = await engine.execute_sell(
            position=position,
            current_price=current_price,
            signal_data=None
        )

        return {
            "message": f"Position {position_id} closed successfully",
            "profit_quote": profit_quote,
            "profit_percentage": profit_percentage
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{position_id}/limit-close")
async def limit_close_position(
    position_id: int,
    request: LimitCloseRequest,
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase)
):
    """Close a position via limit order"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if position.status != "open":
            raise HTTPException(status_code=400, detail="Position is not open")

        if position.closing_via_limit:
            raise HTTPException(status_code=400, detail="Position already has a pending limit close order")

        # Create limit sell order via Coinbase
        order_result = await coinbase.create_limit_order(
            product_id=position.product_id,
            side="SELL",
            limit_price=request.limit_price,
            size=str(position.total_base_acquired)  # Sell entire position
        )

        # Extract order ID from response
        order_id = order_result.get("order_id") or order_result.get("success_response", {}).get("order_id")

        if not order_id:
            raise HTTPException(status_code=500, detail="Failed to create limit order - no order ID returned")

        # Create PendingOrder record to track this limit sell
        pending_order = PendingOrder(
            position_id=position.id,
            bot_id=position.bot_id,
            order_id=order_id,
            product_id=position.product_id,
            side="SELL",
            order_type="LIMIT",
            limit_price=request.limit_price,
            quote_amount=0.0,  # Will be filled when order completes
            base_amount=position.total_base_acquired,
            trade_type="limit_close",
            status="pending",
            remaining_base_amount=position.total_base_acquired,
            fills=[]
        )
        db.add(pending_order)

        # Update position to indicate it's closing via limit
        position.closing_via_limit = True
        position.limit_close_order_id = order_id

        await db.commit()

        return {
            "message": "Limit close order placed successfully",
            "order_id": order_id,
            "limit_price": request.limit_price,
            "base_amount": position.total_base_acquired
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{position_id}/ticker")
async def get_position_ticker(
    position_id: int,
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase)
):
    """Get current bid/ask/mark prices for a position"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        # Get ticker data including bid/ask
        ticker = await coinbase.get_ticker(position.product_id)

        best_bid = float(ticker.get("best_bid", 0))
        best_ask = float(ticker.get("best_ask", 0))
        mark_price = (best_bid + best_ask) / 2 if best_bid and best_ask else float(ticker.get("price", 0))

        return {
            "product_id": position.product_id,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mark_price": mark_price,
            "last_price": float(ticker.get("price", 0))
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{position_id}/slippage-check")
async def check_market_close_slippage(
    position_id: int,
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase)
):
    """Check if closing at market would result in significant slippage"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if position.status != "open":
            raise HTTPException(status_code=400, detail="Position is not open")

        # Get ticker data including bid/ask
        ticker = await coinbase.get_ticker(position.product_id)
        best_bid = float(ticker.get("best_bid", 0))
        best_ask = float(ticker.get("best_ask", 0))
        mark_price = (best_bid + best_ask) / 2 if best_bid and best_ask else float(ticker.get("price", 0))

        # Calculate expected profit at mark price
        current_value_at_mark = position.total_base_acquired * mark_price
        expected_profit_at_mark = current_value_at_mark - position.total_quote_spent

        # Calculate actual profit when selling at best bid (market sell)
        actual_value_at_bid = position.total_base_acquired * best_bid
        actual_profit_at_bid = actual_value_at_bid - position.total_quote_spent

        # Calculate slippage
        slippage_amount = expected_profit_at_mark - actual_profit_at_bid
        slippage_percentage = 0.0

        # Calculate slippage as % of expected profit (if profitable)
        if expected_profit_at_mark > 0:
            slippage_percentage = (slippage_amount / expected_profit_at_mark) * 100

        # Determine if warning should be shown (>25% slippage)
        show_warning = slippage_percentage > 25.0

        return {
            "product_id": position.product_id,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mark_price": mark_price,
            "expected_profit_at_mark": expected_profit_at_mark,
            "actual_profit_at_bid": actual_profit_at_bid,
            "slippage_amount": slippage_amount,
            "slippage_percentage": slippage_percentage,
            "show_warning": show_warning,
            "position_value_at_bid": actual_value_at_bid,
            "position_value_at_mark": current_value_at_mark
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{position_id}/cancel-limit-close")
async def cancel_limit_close(
    position_id: int,
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase)
):
    """Cancel a pending limit close order"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if not position.closing_via_limit:
            raise HTTPException(status_code=400, detail="Position does not have a pending limit close order")

        # Cancel the order on Coinbase
        await coinbase.cancel_order(position.limit_close_order_id)

        # Update pending order status
        pending_order_query = select(PendingOrder).where(
            PendingOrder.order_id == position.limit_close_order_id
        )
        pending_order_result = await db.execute(pending_order_query)
        pending_order = pending_order_result.scalars().first()

        if pending_order:
            pending_order.status = "canceled"
            pending_order.canceled_at = datetime.utcnow()

        # Reset position limit close flags
        position.closing_via_limit = False
        position.limit_close_order_id = None

        await db.commit()

        return {"message": "Limit close order canceled successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{position_id}/update-limit-close")
async def update_limit_close(
    position_id: int,
    request: UpdateLimitCloseRequest,
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase)
):
    """Update the limit price for a pending limit close order"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if not position.closing_via_limit:
            raise HTTPException(status_code=400, detail="Position does not have a pending limit close order")

        # Get the pending order to check remaining amount
        pending_order_query = select(PendingOrder).where(
            PendingOrder.order_id == position.limit_close_order_id
        )
        pending_order_result = await db.execute(pending_order_query)
        pending_order = pending_order_result.scalars().first()

        if not pending_order:
            raise HTTPException(status_code=404, detail="Pending order not found")

        # Cancel the old order
        await coinbase.cancel_order(position.limit_close_order_id)

        # Create new limit order with updated price (for remaining amount)
        remaining_amount = pending_order.remaining_base_amount or position.total_base_acquired

        order_result = await coinbase.create_limit_order(
            product_id=position.product_id,
            side="SELL",
            limit_price=request.new_limit_price,
            size=str(remaining_amount)
        )

        # Extract new order ID
        new_order_id = order_result.get("order_id") or order_result.get("success_response", {}).get("order_id")

        if not new_order_id:
            raise HTTPException(status_code=500, detail="Failed to create updated limit order")

        # Update old pending order to canceled
        pending_order.status = "canceled"
        pending_order.canceled_at = datetime.utcnow()

        # Create new pending order
        new_pending_order = PendingOrder(
            position_id=position.id,
            bot_id=position.bot_id,
            order_id=new_order_id,
            product_id=position.product_id,
            side="SELL",
            order_type="LIMIT",
            limit_price=request.new_limit_price,
            quote_amount=0.0,
            base_amount=remaining_amount,
            trade_type="limit_close",
            status="pending",
            remaining_base_amount=remaining_amount,
            fills=pending_order.fills  # Preserve existing fills
        )
        db.add(new_pending_order)

        # Update position with new order ID
        position.limit_close_order_id = new_order_id

        await db.commit()

        return {
            "message": "Limit close order updated successfully",
            "order_id": new_order_id,
            "new_limit_price": request.new_limit_price,
            "remaining_amount": remaining_amount
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{position_id}/add-funds")
async def add_funds_to_position(
    position_id: int,
    request: AddFundsRequest,
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase)
):
    """Manually add funds to a position (manual safety order)"""
    btc_amount = request.btc_amount
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        if position.status != "open":
            raise HTTPException(status_code=400, detail="Position is not open")

        # Check if adding funds would exceed max allowed
        if position.total_btc_spent + btc_amount > position.max_btc_allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Adding {btc_amount} BTC would exceed max allowed ({position.max_btc_allowed} BTC)"
            )

        # Get current price
        current_price = await coinbase.get_current_price()

        # Execute DCA buy using new trading engine
        trading_client = TradingClient(coinbase)
        engine = StrategyTradingEngine(
            db=db,
            trading_client=trading_client,
            bot=None,  # Manual operation, no bot
            product_id=position.product_id
        )
        trade = await engine.execute_buy(
            position=position,
            quote_amount=btc_amount,  # New engine uses quote_amount (multi-currency)
            current_price=current_price,
            trade_type="manual_safety_order",
            signal_data=None
        )

        return {
            "message": f"Added {btc_amount} BTC to position {position_id}",
            "trade_id": trade.id,
            "price": current_price,
            "eth_acquired": trade.eth_amount
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{position_id}/notes")
async def update_position_notes(
    position_id: int,
    request: UpdateNotesRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update notes for a position (like 3Commas)"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        # Update notes
        position.notes = request.notes

        await db.commit()

        return {
            "message": f"Notes updated for position {position_id}",
            "notes": position.notes
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
