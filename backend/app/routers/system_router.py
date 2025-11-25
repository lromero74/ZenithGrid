"""
System and general API routes

Handles system-level endpoints:
- Root/health check
- System status
- AI provider information
- Dashboard statistics
- Monitor control (start/stop)
- Recent trades and signals
- Market data history
"""

import logging
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_unified_client import CoinbaseClient
from app.config import settings
from app.database import get_db
from app.models import MarketData, Position, Signal, Trade
from app.multi_bot_monitor import MultiBotMonitor
from app.schemas import (
    DashboardStats,
    MarketDataResponse,
    PositionResponse,
    SignalResponse,
    TradeResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


# Dependencies - will be injected from main.py
def get_coinbase() -> CoinbaseClient:
    """Get coinbase client - will be overridden in main.py"""
    raise NotImplementedError("Must override coinbase dependency")


def get_price_monitor() -> MultiBotMonitor:
    """Get price monitor - will be overridden in main.py"""
    raise NotImplementedError("Must override price_monitor dependency")


@router.get("/")
async def root():
    return {"message": "ETH/BTC Trading Bot API", "status": "running"}


@router.get("/api/ai-providers")
async def get_ai_provider_info():
    """Get information about AI providers and their billing URLs"""
    return {
        "providers": {
            "anthropic": {
                "name": "Anthropic (Claude)",
                "billing_url": "https://console.anthropic.com/settings/usage",
                "has_api_key": bool(settings.anthropic_api_key),
            },
            "gemini": {
                "name": "Google Gemini",
                "billing_url": "https://aistudio.google.com/app/apikey",
                "has_api_key": bool(settings.gemini_api_key),
            },
            "openai": {
                "name": "OpenAI (GPT)",
                "billing_url": "https://platform.openai.com/usage",
                "has_api_key": False,  # Not currently configured
            },
        }
    }


@router.get("/api/status")
async def get_status(
    coinbase: CoinbaseClient = Depends(get_coinbase), price_monitor: MultiBotMonitor = Depends(get_price_monitor)
):
    """Get overall system status"""
    try:
        connection_ok = await coinbase.test_connection()
        monitor_status = await price_monitor.get_status()

        return {"api_connected": connection_ok, "monitor": monitor_status, "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/dashboard", response_model=DashboardStats)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase),
    price_monitor: MultiBotMonitor = Depends(get_price_monitor),
):
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
        current_price = await coinbase.get_current_price()

        # Balances
        btc_balance = await coinbase.get_btc_balance()
        eth_balance = await coinbase.get_eth_balance()

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
            monitor_running=monitor_status["running"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/monitor/start")
async def start_monitor(price_monitor: MultiBotMonitor = Depends(get_price_monitor)):
    """Start the price monitor"""
    if not price_monitor.running:
        price_monitor.start()
        return {"message": "Monitor started"}
    return {"message": "Monitor already running"}


@router.post("/api/monitor/stop")
async def stop_monitor(price_monitor: MultiBotMonitor = Depends(get_price_monitor)):
    """Stop the price monitor"""
    if price_monitor.running:
        await price_monitor.stop()
        return {"message": "Monitor stopped"}
    return {"message": "Monitor not running"}


@router.get("/api/trades", response_model=List[TradeResponse])
async def get_trades(limit: int = 100, db: AsyncSession = Depends(get_db)):
    """Get recent trades"""
    query = select(Trade).order_by(desc(Trade.timestamp)).limit(limit)
    result = await db.execute(query)
    trades = result.scalars().all()

    return [TradeResponse.model_validate(t) for t in trades]


@router.get("/api/signals", response_model=List[SignalResponse])
async def get_signals(limit: int = 100, db: AsyncSession = Depends(get_db)):
    """Get recent signals"""
    query = select(Signal).order_by(desc(Signal.timestamp)).limit(limit)
    result = await db.execute(query)
    signals = result.scalars().all()

    return [SignalResponse.model_validate(s) for s in signals]


@router.get("/api/market-data", response_model=List[MarketDataResponse])
async def get_market_data(hours: int = 24, db: AsyncSession = Depends(get_db)):
    """Get market data for charting"""
    start_time = datetime.utcnow() - timedelta(hours=hours)
    query = select(MarketData).where(MarketData.timestamp >= start_time).order_by(MarketData.timestamp)
    result = await db.execute(query)
    data = result.scalars().all()

    return [MarketDataResponse.model_validate(d) for d in data]
