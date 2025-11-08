from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime, timedelta
import asyncio
import json
import os

from app.database import get_db, init_db
from app.config import settings
from app.models import Position, Trade, Signal, MarketData, Settings as SettingsModel
from app.coinbase_client import CoinbaseClient
from app.price_monitor import PriceMonitor
from app.trading_engine import TradingEngine
from app.indicators import MACDCalculator

app = FastAPI(title="ETH/BTC Trading Bot")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
coinbase_client = CoinbaseClient()
price_monitor = PriceMonitor(coinbase_client, interval_seconds=60)


# Pydantic schemas
from pydantic import BaseModel


class PositionResponse(BaseModel):
    id: int
    status: str
    opened_at: datetime
    closed_at: Optional[datetime]
    initial_btc_balance: float
    max_btc_allowed: float
    total_btc_spent: float
    total_eth_acquired: float
    average_buy_price: float
    sell_price: Optional[float]
    total_btc_received: Optional[float]
    profit_btc: Optional[float]
    profit_percentage: Optional[float]
    btc_usd_price_at_open: Optional[float]
    btc_usd_price_at_close: Optional[float]
    profit_usd: Optional[float]
    trade_count: int = 0

    class Config:
        from_attributes = True


class TradeResponse(BaseModel):
    id: int
    position_id: int
    timestamp: datetime
    side: str
    btc_amount: float
    eth_amount: float
    price: float
    trade_type: str
    order_id: Optional[str]

    class Config:
        from_attributes = True


class SignalResponse(BaseModel):
    id: int
    timestamp: datetime
    signal_type: str
    macd_value: float
    macd_signal: float
    macd_histogram: float
    price: float
    action_taken: Optional[str]
    reason: Optional[str]

    class Config:
        from_attributes = True


class MarketDataResponse(BaseModel):
    id: int
    timestamp: datetime
    price: float
    macd_value: Optional[float]
    macd_signal: Optional[float]
    macd_histogram: Optional[float]

    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    coinbase_api_key: Optional[str] = None
    coinbase_api_secret: Optional[str] = None
    initial_btc_percentage: Optional[float] = None
    dca_percentage: Optional[float] = None
    max_btc_usage_percentage: Optional[float] = None
    min_profit_percentage: Optional[float] = None
    macd_fast_period: Optional[int] = None
    macd_slow_period: Optional[int] = None
    macd_signal_period: Optional[int] = None
    candle_interval: Optional[str] = None


class TestConnectionRequest(BaseModel):
    coinbase_api_key: str
    coinbase_api_secret: str


class DashboardStats(BaseModel):
    current_position: Optional[PositionResponse]
    total_positions: int
    total_profit_btc: float
    win_rate: float
    current_price: float
    btc_balance: float
    eth_balance: float
    monitor_running: bool


# Startup/Shutdown events
@app.on_event("startup")
async def startup_event():
    await init_db()
    # Start price monitor
    price_monitor.start()


@app.on_event("shutdown")
async def shutdown_event():
    await price_monitor.stop()


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

        pos_response = PositionResponse.model_validate(pos)
        pos_response.trade_count = trade_count
        response.append(pos_response)

    return response


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

    pos_response = PositionResponse.model_validate(position)
    pos_response.trade_count = trade_count

    return pos_response


@app.get("/api/positions/{position_id}/trades", response_model=List[TradeResponse])
async def get_position_trades(position_id: int, db: AsyncSession = Depends(get_db)):
    """Get all trades for a position"""
    query = select(Trade).where(Trade.position_id == position_id).order_by(Trade.timestamp)
    result = await db.execute(query)
    trades = result.scalars().all()

    return [TradeResponse.model_validate(t) for t in trades]


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

        # Get current price
        current_price = await coinbase_client.get_current_price()

        # Execute sell
        engine = TradingEngine(db, coinbase_client)
        trade, profit_btc, profit_percentage = await engine.execute_sell(
            position=position,
            current_price=current_price,
            macd_data=None
        )

        return {
            "message": f"Position {position_id} closed successfully",
            "profit_btc": profit_btc,
            "profit_percentage": profit_percentage
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
            except:
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
