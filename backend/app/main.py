import logging
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db, get_db
from app.exchange_clients.factory import create_exchange_client
from app.multi_bot_monitor import MultiBotMonitor
from app.services.limit_order_monitor import LimitOrderMonitor
from app.routers import bots_router, order_history_router, templates_router
from app.routers import positions_router
from app.routers import account_router
from app.routers import accounts_router  # Multi-account management (CEX + DEX)
from app.routers.accounts_router import set_coinbase_client
from app.routers import market_data_router
from app.routers import settings_router
from app.routers import system_router
from app.routers import blacklist_router
import asyncio

# Import dependency functions for override
from app.position_routers.dependencies import get_coinbase as position_get_coinbase
from app.routers.account_router import get_coinbase as account_get_coinbase
from app.routers.market_data_router import get_coinbase as market_data_get_coinbase
from app.routers.settings_router import get_coinbase as settings_get_coinbase
from app.routers.system_router import get_coinbase as system_get_coinbase, get_price_monitor as system_get_price_monitor

logger = logging.getLogger(__name__)

app = FastAPI(title="ETH/BTC Trading Bot")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances - Create exchange client using factory (CEX for now, DEX in future)
# Factory creates CoinbaseAdapter wrapping CoinbaseClient (auto-detects CDP vs HMAC auth)
exchange_client = create_exchange_client(
    exchange_type="cex",  # Centralized exchange (Coinbase)
    coinbase_key_name=settings.coinbase_cdp_key_name,
    coinbase_private_key=settings.coinbase_cdp_private_key,
)

# Multi-bot monitor - monitors all active bots with their strategies
# Monitor loop runs every 10s to check if any bots need processing
# Bots can override with their own check_interval_seconds (set in database)
price_monitor = MultiBotMonitor(exchange_client, interval_seconds=10)

# Limit order monitor - tracks pending limit orders and processes fills
# Runs every 10 seconds to check order status
limit_order_monitor_task = None

# Order reconciliation monitor - auto-fixes positions with missing fill data
# Runs every 60 seconds to detect and reconcile orphaned orders
order_reconciliation_monitor_task = None


# Dependency overrides for router injection
def override_get_coinbase():
    return exchange_client


def override_get_price_monitor():
    return price_monitor


# Override dependencies with global instances
app.dependency_overrides[position_get_coinbase] = override_get_coinbase
app.dependency_overrides[account_get_coinbase] = override_get_coinbase
app.dependency_overrides[market_data_get_coinbase] = override_get_coinbase
app.dependency_overrides[settings_get_coinbase] = override_get_coinbase
app.dependency_overrides[system_get_coinbase] = override_get_coinbase
app.dependency_overrides[system_get_price_monitor] = override_get_price_monitor

# Set coinbase client for accounts router (uses global instead of dependency injection)
set_coinbase_client(exchange_client)

# Include all routers
app.include_router(bots_router)  # Existing routers
app.include_router(order_history_router)
app.include_router(templates_router)
app.include_router(positions_router.router)  # New routers
app.include_router(account_router.router)
app.include_router(accounts_router.router)  # Multi-account management (CEX + DEX)
app.include_router(market_data_router.router)
app.include_router(settings_router.router)
app.include_router(system_router.router)
app.include_router(blacklist_router.router)


# Background task for limit order monitoring
async def run_limit_order_monitor():
    """Background task that monitors pending limit orders"""
    from app.database import async_session_maker

    while True:
        try:
            async with async_session_maker() as db:
                monitor = LimitOrderMonitor(db, exchange_client)
                await monitor.check_limit_close_orders()
        except Exception as e:
            logger.error(f"Error in limit order monitor loop: {e}")

        # Check every 10 seconds
        await asyncio.sleep(10)


# Background task for order reconciliation
async def run_order_reconciliation_monitor():
    """Background task that auto-fixes positions with missing fill data"""
    from app.database import async_session_maker
    from app.services.order_reconciliation_monitor import OrderReconciliationMonitor

    while True:
        try:
            async with async_session_maker() as db:
                monitor = OrderReconciliationMonitor(db, exchange_client)
                await monitor.check_and_fix_orphaned_positions()
        except Exception as e:
            logger.error(f"Error in order reconciliation monitor loop: {e}")

        # Check every 60 seconds (less frequent than limit orders)
        await asyncio.sleep(60)


# Startup/Shutdown events
@app.on_event("startup")
async def startup_event():
    global limit_order_monitor_task, order_reconciliation_monitor_task

    print("🚀 ========================================")
    print("🚀 FastAPI startup event triggered")
    print("🚀 Initializing database...")
    await init_db()
    print("🚀 Database initialized successfully")
    print("🚀 Starting multi-bot monitor...")
    # Start price monitor
    await price_monitor.start_async()
    print("🚀 Multi-bot monitor started - bot monitoring active")
    print("🚀 Starting limit order monitor...")
    # Start limit order monitor as background task
    limit_order_monitor_task = asyncio.create_task(run_limit_order_monitor())
    print("🚀 Limit order monitor started - checking every 10 seconds")
    print("🚀 Starting order reconciliation monitor...")
    # Start order reconciliation monitor as background task
    order_reconciliation_monitor_task = asyncio.create_task(run_order_reconciliation_monitor())
    print("🚀 Order reconciliation monitor started - auto-fixing orphaned positions every 60 seconds")
    print("🚀 Startup complete!")
    print("🚀 ========================================")


@app.on_event("shutdown")
async def shutdown_event():
    global limit_order_monitor_task, order_reconciliation_monitor_task

    logger.info("🛑 Shutting down - stopping monitors...")
    await price_monitor.stop()

    if limit_order_monitor_task:
        limit_order_monitor_task.cancel()
        try:
            await limit_order_monitor_task
        except asyncio.CancelledError:
            pass

    if order_reconciliation_monitor_task:
        order_reconciliation_monitor_task.cancel()
        try:
            await order_reconciliation_monitor_task
        except asyncio.CancelledError:
            pass

    logger.info("🛑 Monitors stopped - shutdown complete")


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
