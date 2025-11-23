import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_unified_client import CoinbaseClient
from app.config import settings
from app.database import get_db, init_db
from app.models import AIBotLog, Bot, MarketData, PendingOrder, Position, Signal, Trade
from app.multi_bot_monitor import MultiBotMonitor
from app.routers import bots_router, order_history_router, templates_router
from app.schemas import (
    AIBotLogResponse,
    DashboardStats,
    MarketDataResponse,
    PositionResponse,
    SettingsUpdate,
    SignalResponse,
    TestConnectionRequest,
    TradeResponse,
)
from app.trading_client import TradingClient
from app.trading_engine_v2 import StrategyTradingEngine

logger = logging.getLogger(__name__)




app = FastAPI(
    title="ETH/BTC Trading Bot"
)

# Import custom middleware

# Temporarily disabled - causing API hangs
# app.add_middleware(DatetimeTimezoneMiddleware)

# Include routers
app.include_router(bots_router)
app.include_router(order_history_router)
app.include_router(templates_router)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances - Unified client auto-detects CDP vs HMAC authentication
coinbase_client = CoinbaseClient()  # Auto-detects auth from settings

# Multi-bot monitor - monitors all active bots with their strategies
# Monitor loop runs every 10s to check if any bots need processing
# Bots can override with their own check_interval_seconds (set in database)
# Order monitor is integrated within MultiBotMonitor (checks pending limit orders)
price_monitor = MultiBotMonitor(coinbase_client, interval_seconds=10)


# Startup/Shutdown events
@app.on_event("startup")
async def startup_event():
    print("🚀 ========================================")
    print("🚀 FastAPI startup event triggered")
    print("🚀 Initializing database...")
    await init_db()
    print("🚀 Database initialized successfully")
    print("🚀 Starting multi-bot monitor (includes order monitor)...")
    # Start price monitor (which includes order monitor)
    await price_monitor.start_async()
    print("🚀 Multi-bot monitor started - bot monitoring & order tracking active")
    print("🚀 Startup complete!")
    print("🚀 ========================================")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Shutting down - stopping monitors...")
    await price_monitor.stop()
    logger.info("🛑 Monitors stopped - shutdown complete")


# API Endpoints
@app.get("/")
async def root():
    return {"message": "ETH/BTC Trading Bot API", "status": "running"}


@app.get("/api/status")
async def get_status():
    """Get overall system status"""
    try:
        connection_ok = await coinbase_client.test_connection()
        monitor_status = await price_monitor.get_status()

        return {
            "api_connected": connection_ok,
            "monitor": monitor_status,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard", response_model=DashboardStats)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics"""
    try:
        # Get current position
        current_position = None
        query = select(Position).where(Position.status == "open").order_by(desc(Position.opened_at))
        result = await db.execute(query)
        pos = result.scalars().first()

        if pos:
            # Count trades for this position
            trade_count_query = select(func.count(Trade.id)).where(Trade.position_id == pos.id)
            trade_count_result = await db.execute(trade_count_query)
            trade_count = trade_count_result.scalar()

            current_position = PositionResponse.model_validate(pos)
            current_position.trade_count = trade_count

        # Total positions
        total_positions_query = select(func.count(Position.id))
        total_positions_result = await db.execute(total_positions_query)
        total_positions = total_positions_result.scalar() or 0

        # Total profit (closed positions only)
        profit_query = select(func.sum(Position.profit_btc)).where(Position.status == "closed")
        profit_result = await db.execute(profit_query)
        total_profit_btc = profit_result.scalar() or 0.0

        # Win rate
        closed_positions_query = select(Position).where(Position.status == "closed")
        closed_result = await db.execute(closed_positions_query)
        closed_positions = closed_result.scalars().all()

        win_count = sum(1 for p in closed_positions if p.profit_btc and p.profit_btc > 0)
        total_closed = len(closed_positions)
        win_rate = (win_count / total_closed * 100) if total_closed > 0 else 0.0

        # Current price
        current_price = await coinbase_client.get_current_price()

        # Balances
        btc_balance = await coinbase_client.get_btc_balance()
        eth_balance = await coinbase_client.get_eth_balance()

        # Monitor status
        monitor_status = await price_monitor.get_status()

        return DashboardStats(
            current_position=current_position,
            total_positions=total_positions,
            total_profit_btc=total_profit_btc,
            win_rate=win_rate,
            current_price=current_price,
            btc_balance=btc_balance,
            eth_balance=eth_balance,
            monitor_running=monitor_status["running"]
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/positions", response_model=List[PositionResponse])
async def get_positions(
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
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
                from app.schemas.position import LimitOrderDetails, LimitOrderFill
                import json

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


@app.get("/api/positions/pnl-timeseries")
async def get_pnl_timeseries(db: AsyncSession = Depends(get_db)):
    """
    Get P&L time series data for cumulative profit chart (3Commas-style).

    Returns cumulative profit over time from all closed positions.
    """
    from collections import defaultdict
    from datetime import date

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


@app.get("/api/positions/{position_id}", response_model=PositionResponse)
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


@app.get("/api/positions/{position_id}/trades", response_model=List[TradeResponse])
async def get_position_trades(position_id: int, db: AsyncSession = Depends(get_db)):
    """Get all trades for a position"""
    query = select(Trade).where(Trade.position_id == position_id).order_by(Trade.timestamp)
    result = await db.execute(query)
    trades = result.scalars().all()

    return [TradeResponse.model_validate(t) for t in trades]


@app.get("/api/positions/{position_id}/ai-logs", response_model=List[AIBotLogResponse])
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


@app.get("/api/trades", response_model=List[TradeResponse])
async def get_trades(limit: int = 100, db: AsyncSession = Depends(get_db)):
    """Get recent trades"""
    query = select(Trade).order_by(desc(Trade.timestamp)).limit(limit)
    result = await db.execute(query)
    trades = result.scalars().all()

    return [TradeResponse.model_validate(t) for t in trades]


@app.get("/api/signals", response_model=List[SignalResponse])
async def get_signals(limit: int = 100, db: AsyncSession = Depends(get_db)):
    """Get recent signals"""
    query = select(Signal).order_by(desc(Signal.timestamp)).limit(limit)
    result = await db.execute(query)
    signals = result.scalars().all()

    return [SignalResponse.model_validate(s) for s in signals]


@app.get("/api/market-data", response_model=List[MarketDataResponse])
async def get_market_data(
    hours: int = 24,
    db: AsyncSession = Depends(get_db)
):
    """Get market data for charting"""
    start_time = datetime.utcnow() - timedelta(hours=hours)
    query = select(MarketData).where(MarketData.timestamp >= start_time).order_by(MarketData.timestamp)
    result = await db.execute(query)
    data = result.scalars().all()

    return [MarketDataResponse.model_validate(d) for d in data]


@app.get("/api/settings")
async def get_settings():
    """Get current settings"""
    # Mask API credentials for security
    masked_key = ""
    masked_secret = ""
    if settings.coinbase_api_key:
        masked_key = settings.coinbase_api_key[:8] + "..." if len(settings.coinbase_api_key) > 8 else "***"
    if settings.coinbase_api_secret:
        masked_secret = "***************"

    return {
        "coinbase_api_key": masked_key,
        "coinbase_api_secret": masked_secret,
        "initial_btc_percentage": settings.initial_btc_percentage,
        "dca_percentage": settings.dca_percentage,
        "max_btc_usage_percentage": settings.max_btc_usage_percentage,
        "min_profit_percentage": settings.min_profit_percentage,
        "macd_fast_period": settings.macd_fast_period,
        "macd_slow_period": settings.macd_slow_period,
        "macd_signal_period": settings.macd_signal_period,
        "candle_interval": settings.candle_interval,
    }


def update_env_file(key: str, value: str):
    """Update a value in the .env file"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')

    # Read existing .env file
    lines = []
    key_found = False
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()

    # Update or add the key
    for i, line in enumerate(lines):
        if line.startswith(f'{key}='):
            lines[i] = f'{key}={value}\n'
            key_found = True
            break

    if not key_found:
        lines.append(f'{key}={value}\n')

    # Write back to .env file
    with open(env_path, 'w') as f:
        f.writelines(lines)


@app.post("/api/settings")
async def update_settings(settings_update: SettingsUpdate):
    """Update trading settings"""
    # Update API credentials in .env file if provided
    if settings_update.coinbase_api_key is not None:
        update_env_file('COINBASE_API_KEY', settings_update.coinbase_api_key)
        settings.coinbase_api_key = settings_update.coinbase_api_key
        # Reinitialize coinbase client with new credentials
        coinbase_client.api_key = settings_update.coinbase_api_key
        if settings_update.coinbase_api_secret is not None:
            coinbase_client.api_secret = settings_update.coinbase_api_secret

    if settings_update.coinbase_api_secret is not None:
        update_env_file('COINBASE_API_SECRET', settings_update.coinbase_api_secret)
        settings.coinbase_api_secret = settings_update.coinbase_api_secret
        coinbase_client.api_secret = settings_update.coinbase_api_secret

    # Update settings object
    if settings_update.initial_btc_percentage is not None:
        settings.initial_btc_percentage = settings_update.initial_btc_percentage
    if settings_update.dca_percentage is not None:
        settings.dca_percentage = settings_update.dca_percentage
    if settings_update.max_btc_usage_percentage is not None:
        settings.max_btc_usage_percentage = settings_update.max_btc_usage_percentage
    if settings_update.min_profit_percentage is not None:
        settings.min_profit_percentage = settings_update.min_profit_percentage
    if settings_update.macd_fast_period is not None:
        settings.macd_fast_period = settings_update.macd_fast_period
    if settings_update.macd_slow_period is not None:
        settings.macd_slow_period = settings_update.macd_slow_period
    if settings_update.macd_signal_period is not None:
        settings.macd_signal_period = settings_update.macd_signal_period
    if settings_update.candle_interval is not None:
        settings.candle_interval = settings_update.candle_interval

    return {"message": "Settings updated successfully"}


@app.post("/api/test-connection")
async def test_connection(request: TestConnectionRequest):
    """Test Coinbase API connection with provided credentials"""
    try:
        # Create a temporary client with the provided credentials
        test_client = CoinbaseClient()
        test_client.api_key = request.coinbase_api_key
        test_client.api_secret = request.coinbase_api_secret

        # Try to get account balances to test the connection
        try:
            btc_balance = await test_client.get_btc_balance()
            eth_balance = await test_client.get_eth_balance()

            return {
                "success": True,
                "message": f"Connection successful! BTC Balance: {btc_balance:.8f}, ETH Balance: {eth_balance:.8f}",
                "btc_balance": btc_balance,
                "eth_balance": eth_balance
            }
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "403" in error_msg or "unauthorized" in error_msg.lower():
                raise HTTPException(status_code=401, detail="Invalid API credentials. Please check your API key and secret.")
            elif "permission" in error_msg.lower():
                raise HTTPException(status_code=403, detail="Insufficient permissions. Make sure your API key has 'View' and 'Trade' permissions.")
            else:
                raise HTTPException(status_code=400, detail=f"Connection failed: {error_msg}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.get("/api/candles")
async def get_candles(
    product_id: str = "ETH-BTC",
    granularity: Optional[str] = None,
    limit: int = 300
):
    """
    Get historical candle data for charting

    Args:
        product_id: Trading pair (default: ETH-BTC)
        granularity: Candle interval - ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE,
                     THIRTY_MINUTE, ONE_HOUR, TWO_HOUR, SIX_HOUR, ONE_DAY
        limit: Number of candles to fetch (default: 300)
    """
    try:
        interval = granularity or settings.candle_interval

        # Calculate start time based on limit and granularity
        interval_seconds = {
            "ONE_MINUTE": 60,
            "FIVE_MINUTE": 300,
            "FIFTEEN_MINUTE": 900,
            "THIRTY_MINUTE": 1800,
            "ONE_HOUR": 3600,
            "TWO_HOUR": 7200,
            "SIX_HOUR": 21600,
            "ONE_DAY": 86400
        }

        seconds = interval_seconds.get(interval, 300)
        end_time = int(time.time())
        start_time = end_time - (seconds * limit)

        candles = await coinbase_client.get_candles(
            product_id=product_id,
            start=start_time,
            end=end_time,
            granularity=interval
        )

        # Coinbase returns candles in reverse chronological order
        # Format: {"start": timestamp, "low": str, "high": str, "open": str, "close": str, "volume": str}
        formatted_candles = []
        for candle in reversed(candles):  # Reverse to get chronological order
            formatted_candles.append({
                "time": int(candle["start"]),
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"]),
                "volume": float(candle["volume"])
            })

        return {
            "candles": formatted_candles,
            "interval": interval,
            "product_id": product_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch candles: {str(e)}")


@app.post("/api/monitor/start")
async def start_monitor():
    """Start the price monitor"""
    if not price_monitor.running:
        price_monitor.start()
        return {"message": "Monitor started"}
    return {"message": "Monitor already running"}


@app.post("/api/monitor/stop")
async def stop_monitor():
    """Stop the price monitor"""
    if price_monitor.running:
        await price_monitor.stop()
        return {"message": "Monitor stopped"}
    return {"message": "Monitor not running"}


@app.post("/api/positions/{position_id}/cancel")
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


@app.post("/api/positions/{position_id}/force-close")
async def force_close_position(position_id: int, db: AsyncSession = Depends(get_db)):
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
        current_price = await coinbase_client.get_current_price(position.product_id)

        # Create strategy instance for this bot
        from app.strategies import StrategyRegistry
        strategy = StrategyRegistry.get_strategy(bot.strategy_type, bot.strategy_config)

        # Execute sell using trading engine
        engine = StrategyTradingEngine(
            db=db,
            coinbase=coinbase_client,
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


@app.post("/api/positions/{position_id}/limit-close")
async def limit_close_position(
    position_id: int,
    request: LimitCloseRequest,
    db: AsyncSession = Depends(get_db)
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
        order_result = await coinbase_client.create_limit_order(
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


@app.get("/api/positions/{position_id}/ticker")
async def get_position_ticker(position_id: int, db: AsyncSession = Depends(get_db)):
    """Get current bid/ask/mark prices for a position"""
    try:
        query = select(Position).where(Position.id == position_id)
        result = await db.execute(query)
        position = result.scalars().first()

        if not position:
            raise HTTPException(status_code=404, detail="Position not found")

        # Get ticker data including bid/ask
        ticker = await coinbase_client.get_ticker(position.product_id)

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


@app.post("/api/positions/{position_id}/cancel-limit-close")
async def cancel_limit_close(position_id: int, db: AsyncSession = Depends(get_db)):
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
        await coinbase_client.cancel_order(position.limit_close_order_id)

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


@app.post("/api/positions/{position_id}/update-limit-close")
async def update_limit_close(
    position_id: int,
    request: UpdateLimitCloseRequest,
    db: AsyncSession = Depends(get_db)
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
        await coinbase_client.cancel_order(position.limit_close_order_id)

        # Create new limit order with updated price (for remaining amount)
        remaining_amount = pending_order.remaining_base_amount or position.total_base_acquired

        order_result = await coinbase_client.create_limit_order(
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


class AddFundsRequest(BaseModel):
    btc_amount: float


class UpdateNotesRequest(BaseModel):
    notes: str


class LimitCloseRequest(BaseModel):
    limit_price: float


class UpdateLimitCloseRequest(BaseModel):
    new_limit_price: float


@app.post("/api/positions/{position_id}/add-funds")
async def add_funds_to_position(
    position_id: int,
    request: AddFundsRequest,
    db: AsyncSession = Depends(get_db)
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
        current_price = await coinbase_client.get_current_price()

        # Execute DCA buy using new trading engine
        trading_client = TradingClient(coinbase_client)
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


@app.patch("/api/positions/{position_id}/notes")
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


@app.get("/api/account/balances")
async def get_balances():
    """Get current account balances"""
    try:
        btc_balance = await coinbase_client.get_btc_balance()
        eth_balance = await coinbase_client.get_eth_balance()
        current_price = await coinbase_client.get_current_price()
        btc_usd_price = await coinbase_client.get_btc_usd_price()

        total_btc_value = btc_balance + (eth_balance * current_price)

        return {
            "btc": btc_balance,
            "eth": eth_balance,
            "eth_value_in_btc": eth_balance * current_price,
            "total_btc_value": total_btc_value,
            "current_eth_btc_price": current_price,
            "btc_usd_price": btc_usd_price,
            "total_usd_value": total_btc_value * btc_usd_price
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/account/aggregate-value")
async def get_aggregate_value():
    """Get aggregate portfolio value (BTC + USD) for bot budgeting"""
    try:
        aggregate_btc = await coinbase_client.calculate_aggregate_btc_value()
        aggregate_usd = await coinbase_client.calculate_aggregate_usd_value()
        btc_usd_price = await coinbase_client.get_btc_usd_price()

        return {
            "aggregate_btc_value": aggregate_btc,
            "aggregate_usd_value": aggregate_usd,
            "btc_usd_price": btc_usd_price
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/account/portfolio")
async def get_portfolio(db: AsyncSession = Depends(get_db)):
    """Get full portfolio breakdown (all coins like 3Commas)"""
    try:
        # Get portfolio breakdown with all holdings
        breakdown = await coinbase_client.get_portfolio_breakdown()
        spot_positions = breakdown.get("spot_positions", [])

        # Get BTC/USD price for valuations
        btc_usd_price = await coinbase_client.get_btc_usd_price()

        # Prepare list of assets that need pricing
        assets_to_price = []
        for position in spot_positions:
            asset = position.get("asset", "")
            total_balance = float(position.get("total_balance_crypto", 0))

            # Skip if zero balance
            if total_balance == 0:
                continue

            # Skip stablecoins and BTC (we already have prices for these)
            if asset not in ["USD", "USDC", "BTC"]:
                assets_to_price.append((asset, total_balance, position))

        # Fetch all prices with rate limiting to avoid 429 errors
        async def fetch_price(asset: str, delay: float = 0):
            try:
                # Add small delay to avoid rate limiting
                if delay > 0:
                    await asyncio.sleep(delay)
                price = await coinbase_client.get_current_price(f"{asset}-USD")
                return (asset, price)
            except Exception as e:
                print(f"Could not get USD price for {asset}, skipping: {e}")
                return (asset, None)

        # Fetch prices with staggered delays (every 0.1 seconds) to avoid rate limits
        price_results = await asyncio.gather(*[
            fetch_price(asset, idx * 0.1)
            for idx, (asset, _, _) in enumerate(assets_to_price)
        ])

        # Create price lookup dict
        prices = {asset: price for asset, price in price_results if price is not None}

        # Now build portfolio with all prices available
        portfolio_holdings = []
        total_usd_value = 0.0
        total_btc_value = 0.0

        for position in spot_positions:
            asset = position.get("asset", "")
            total_balance = float(position.get("total_balance_crypto", 0))
            available = float(position.get("available_to_trade_crypto", 0))
            hold = total_balance - available

            # Skip if zero balance
            if total_balance == 0:
                continue

            # Get USD value for this asset
            usd_value = 0.0
            btc_value = 0.0
            current_price_usd = 0.0

            if asset == "USD" or asset == "USDC":
                usd_value = total_balance
                btc_value = total_balance / btc_usd_price if btc_usd_price > 0 else 0
                current_price_usd = 1.0
            elif asset == "BTC":
                usd_value = total_balance * btc_usd_price
                btc_value = total_balance
                current_price_usd = btc_usd_price
            else:
                # Use price from parallel fetch
                if asset not in prices:
                    # Skip assets we couldn't price
                    continue

                current_price_usd = prices[asset]
                usd_value = total_balance * current_price_usd
                # Calculate BTC value from USD value
                btc_value = usd_value / btc_usd_price if btc_usd_price > 0 else 0

            # Skip assets worth less than $0.01 USD
            if usd_value < 0.01:
                continue

            total_usd_value += usd_value
            total_btc_value += btc_value

            portfolio_holdings.append({
                "asset": asset,
                "total_balance": total_balance,
                "available": available,
                "hold": hold,
                "current_price_usd": current_price_usd,
                "usd_value": usd_value,
                "btc_value": btc_value,
                "percentage": 0.0  # Will calculate after we know total
            })

        # Calculate percentages
        for holding in portfolio_holdings:
            if total_usd_value > 0:
                holding["percentage"] = (holding["usd_value"] / total_usd_value) * 100

        # Sort by USD value descending
        portfolio_holdings.sort(key=lambda x: x["usd_value"], reverse=True)

        # Calculate free (unreserved) balances for BTC and USD
        # Free = Total Portfolio - (Bot Reservations + Open Position Balances)

        # Get all bots and sum their reservations
        bots_query = select(Bot)
        bots_result = await db.execute(bots_query)
        all_bots = bots_result.scalars().all()

        total_reserved_btc = sum(bot.reserved_btc_balance for bot in all_bots)
        total_reserved_usd = sum(bot.reserved_usd_balance for bot in all_bots)

        # Get all open positions and calculate their current values
        positions_query = select(Position).where(Position.status == "open")
        positions_result = await db.execute(positions_query)
        open_positions = positions_result.scalars().all()

        total_in_positions_btc = 0.0
        total_in_positions_usd = 0.0

        for position in open_positions:
            quote = position.get_quote_currency()
            base = position.get_base_currency()

            # Get current price for the position
            try:
                current_price = await coinbase_client.get_current_price(f"{base}-{quote}")
                current_value = position.amount * current_price

                if quote == "USD":
                    total_in_positions_usd += current_value
                else:  # BTC
                    total_in_positions_btc += current_value
            except Exception as e:
                # Fallback to quote spent if can't get current price
                print(f"Could not get current price for {base}-{quote}, using quote spent: {e}")
                if quote == "USD":
                    total_in_positions_usd += position.total_quote_spent
                else:
                    total_in_positions_btc += position.total_quote_spent

        # Total portfolio values should match the aggregate BTC/USD values from holdings
        # (which already include all coins converted to BTC/USD)
        total_portfolio_btc = total_btc_value
        total_portfolio_usd = total_usd_value

        # Calculate free balances
        free_btc = total_portfolio_btc - (total_reserved_btc + total_in_positions_btc)
        free_usd = total_portfolio_usd - (total_reserved_usd + total_in_positions_usd)

        # Ensure free balances don't go negative
        free_btc = max(0.0, free_btc)
        free_usd = max(0.0, free_usd)

        # Calculate realized PnL from closed positions
        # All-time PnL
        closed_positions_query = select(Position).where(Position.status == "closed")
        closed_positions_result = await db.execute(closed_positions_query)
        closed_positions = closed_positions_result.scalars().all()

        pnl_all_time_usd = 0.0
        pnl_all_time_btc = 0.0
        pnl_today_usd = 0.0
        pnl_today_btc = 0.0

        today = datetime.utcnow().date()

        for position in closed_positions:
            if position.profit_quote is not None:
                quote = position.get_quote_currency()

                # All-time PnL
                if quote == "USD":
                    pnl_all_time_usd += position.profit_quote
                else:  # BTC
                    pnl_all_time_btc += position.profit_quote

                # Today's PnL
                if position.closed_at and position.closed_at.date() == today:
                    if quote == "USD":
                        pnl_today_usd += position.profit_quote
                    else:  # BTC
                        pnl_today_btc += position.profit_quote

        return {
            "total_usd_value": total_usd_value,
            "total_btc_value": total_btc_value,
            "btc_usd_price": btc_usd_price,
            "holdings": portfolio_holdings,
            "holdings_count": len(portfolio_holdings),
            "balance_breakdown": {
                "btc": {
                    "total": total_portfolio_btc,
                    "reserved_by_bots": total_reserved_btc,
                    "in_open_positions": total_in_positions_btc,
                    "free": free_btc
                },
                "usd": {
                    "total": total_portfolio_usd,
                    "reserved_by_bots": total_reserved_usd,
                    "in_open_positions": total_in_positions_usd,
                    "free": free_usd
                }
            },
            "pnl": {
                "today": {
                    "usd": pnl_today_usd,
                    "btc": pnl_today_btc
                },
                "all_time": {
                    "usd": pnl_all_time_usd,
                    "btc": pnl_all_time_btc
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ticker/{product_id}")
async def get_ticker(product_id: str):
    """Get current ticker/price for a product"""
    try:
        # Use get_current_price() which properly calculates mid-price from best_bid/best_ask
        current_price = await coinbase_client.get_current_price(product_id)

        return {
            "product_id": product_id,
            "price": current_price,
            "time": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/prices/batch")
async def get_prices_batch(products: str):
    """
    Get current prices for multiple products in a single request

    Args:
        products: Comma-separated list of product IDs (e.g., "ETH-BTC,AAVE-BTC,ALGO-BTC")

    Returns:
        Dict mapping product_id to price
    """
    try:
        product_list = [p.strip() for p in products.split(',') if p.strip()]

        if not product_list:
            raise HTTPException(status_code=400, detail="No products specified")

        # Fetch all prices concurrently
        async def fetch_price(product_id: str):
            try:
                price = await coinbase_client.get_current_price(product_id)
                return (product_id, price)
            except Exception as e:
                logger.warning(f"Failed to fetch price for {product_id}: {e}")
                return (product_id, None)

        results = await asyncio.gather(*[fetch_price(p) for p in product_list])

        # Build response dict, filtering out failed requests
        prices = {product_id: price for product_id, price in results if price is not None}

        return {
            "prices": prices,
            "time": datetime.utcnow().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/products")
async def get_products():
    """Get all available trading products from Coinbase"""
    try:
        products = await coinbase_client.list_products()

        # Filter to only USD and BTC pairs that are tradeable
        filtered_products = []
        for product in products:
            product_id = product.get("product_id", "")
            status = product.get("status", "")

            # Only include online/active products
            if status != "online":
                continue

            # Only include USD and BTC pairs
            if product_id.endswith("-USD") or product_id.endswith("-BTC"):
                base_currency = product.get("base_currency_id", "")
                quote_currency = product.get("quote_currency_id", "")

                filtered_products.append({
                    "product_id": product_id,
                    "base_currency": base_currency,
                    "quote_currency": quote_currency,
                    "display_name": product.get("display_name", product_id),
                })

        # Sort: BTC-USD first, then alphabetically
        def sort_key(p):
            if p["product_id"] == "BTC-USD":
                return "0"
            elif p["quote_currency"] == "USD":
                return "1_" + p["product_id"]
            else:  # BTC pairs
                return "2_" + p["product_id"]

        filtered_products.sort(key=sort_key)

        return {
            "products": filtered_products,
            "count": len(filtered_products)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket for real-time updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and wait for messages
            data = await websocket.receive_text()
            # Echo back for now
            await websocket.send_text(f"Message received: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
# Test comment for auto-deploy
