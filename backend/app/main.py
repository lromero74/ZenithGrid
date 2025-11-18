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

from app.coinbase_cdp_client import CoinbaseCDPClient
from app.coinbase_client import CoinbaseClient
from app.config import settings
from app.database import get_db, init_db
from app.models import Bot, MarketData, PendingOrder, Position, Signal, Trade
from app.multi_bot_monitor import MultiBotMonitor
from app.routers import bots_router, templates_router
from app.schemas import (
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
app.include_router(templates_router)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances - Auto-detect CDP vs Legacy API
if settings.coinbase_cdp_key_name and settings.coinbase_cdp_private_key:
    print("🔑 Using CDP API authentication (EC private key)")
    coinbase_client = CoinbaseCDPClient(
        key_name=settings.coinbase_cdp_key_name,
        private_key=settings.coinbase_cdp_private_key
    )
elif settings.coinbase_api_key and settings.coinbase_api_secret:
    print("🔑 Using legacy HMAC API authentication")
    coinbase_client = CoinbaseClient()
else:
    print("⚠️  No API credentials configured")
    coinbase_client = CoinbaseClient()  # Will fail on actual calls

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
    price_monitor.start()
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

        # Execute sell using new trading engine
        trading_client = TradingClient(coinbase_client)
        engine = StrategyTradingEngine(
            db=db,
            trading_client=trading_client,
            bot=None,  # Manual operation, no bot
            product_id=position.product_id
        )
        trade, profit_btc, profit_percentage = await engine.execute_sell(
            position=position,
            current_price=current_price,
            signal_data=None
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


class AddFundsRequest(BaseModel):
    btc_amount: float


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


@app.get("/api/account/portfolio")
async def get_portfolio(db: AsyncSession = Depends(get_db)):
    """Get full portfolio breakdown (all coins like 3Commas)"""
    try:
        # Get portfolio breakdown with all holdings
        breakdown = await coinbase_client.get_portfolio_breakdown()
        spot_positions = breakdown.get("spot_positions", [])

        # Get BTC/USD price for valuations
        btc_usd_price = await coinbase_client.get_btc_usd_price()

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
                # Try to get price for other assets (with timeout protection)
                try:
                    # First try ASSET-USD pair
                    try:
                        asset_usd_price = await coinbase_client.get_current_price(f"{asset}-USD")
                        usd_value = total_balance * asset_usd_price
                        current_price_usd = asset_usd_price
                    except Exception:
                        # Try ASSET-BTC pair and convert to USD
                        try:
                            asset_btc_price = await coinbase_client.get_current_price(f"{asset}-BTC")
                            btc_value = total_balance * asset_btc_price
                            usd_value = btc_value * btc_usd_price
                            current_price_usd = asset_btc_price * btc_usd_price
                        except Exception:
                            # Can't get price for this asset, skip it
                            print(f"Could not get price for {asset}, skipping")
                            continue

                    # Calculate BTC value if not already set
                    if btc_value == 0 and btc_usd_price > 0:
                        btc_value = usd_value / btc_usd_price
                except Exception as e:
                    # If we can't get price, skip this asset
                    print(f"Error pricing {asset}: {e}")
                    continue

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

        # Get all open positions and sum their balances
        positions_query = select(Position).where(Position.status == "open")
        positions_result = await db.execute(positions_query)
        open_positions = positions_result.scalars().all()

        total_in_positions_btc = 0.0
        total_in_positions_usd = 0.0

        for position in open_positions:
            quote = position.get_quote_currency()
            if quote == "USD":
                total_in_positions_usd += position.total_quote_spent
            else:
                total_in_positions_btc += position.total_quote_spent

        # Get total portfolio balances from Coinbase
        total_portfolio_btc = 0.0
        total_portfolio_usd = 0.0

        for position in spot_positions:
            asset = position.get("asset", "")
            total_balance = float(position.get("total_balance_crypto", 0))

            if asset == "BTC":
                total_portfolio_btc = total_balance
            elif asset in ["USD", "USDC"]:
                total_portfolio_usd += total_balance

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
