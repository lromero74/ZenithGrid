import logging
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.coinbase_unified_client import CoinbaseClient
from app.config import settings
from app.database import init_db
from app.multi_bot_monitor import MultiBotMonitor
from app.routers import bots_router, order_history_router, templates_router
from app.routers import positions_router
from app.routers import account_router
from app.routers import market_data_router
from app.routers import settings_router
from app.routers import system_router
# Import dependency functions for override
from app.position_routers.dependencies import get_coinbase as position_get_coinbase
from app.routers.account_router import get_coinbase as account_get_coinbase
from app.routers.market_data_router import get_coinbase as market_data_get_coinbase
from app.routers.settings_router import get_coinbase as settings_get_coinbase
from app.routers.system_router import get_coinbase as system_get_coinbase, get_price_monitor as system_get_price_monitor

logger = logging.getLogger(__name__)

app = FastAPI(
    title="ETH/BTC Trading Bot"
)

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


# Dependency overrides for router injection
def override_get_coinbase():
    return coinbase_client


def override_get_price_monitor():
    return price_monitor


# Override dependencies with global instances
app.dependency_overrides[position_get_coinbase] = override_get_coinbase
app.dependency_overrides[account_get_coinbase] = override_get_coinbase
app.dependency_overrides[market_data_get_coinbase] = override_get_coinbase
app.dependency_overrides[settings_get_coinbase] = override_get_coinbase
app.dependency_overrides[system_get_coinbase] = override_get_coinbase
app.dependency_overrides[system_get_price_monitor] = override_get_price_monitor

# Include all routers
app.include_router(bots_router)  # Existing routers
app.include_router(order_history_router)
app.include_router(templates_router)
app.include_router(positions_router.router)  # New routers
app.include_router(account_router.router)
app.include_router(market_data_router.router)
app.include_router(settings_router.router)
app.include_router(system_router.router)


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
