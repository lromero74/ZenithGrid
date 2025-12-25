import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.multi_bot_monitor import MultiBotMonitor
from app.services.limit_order_monitor import LimitOrderMonitor
from app.services.delisted_pair_monitor import TradingPairMonitor
from app.routers import bots_router, order_history_router, templates_router
from app.routers import positions_router
from app.routers import account_router
from app.routers import accounts_router  # Multi-account management (CEX + DEX)
from app.routers import market_data_router
from app.routers import settings_router
from app.routers import system_router
from app.routers.system_router import set_trading_pair_monitor, build_changelog_cache
from app.routers import blacklist_router
from app.routers import news_router
from app.routers import sources_router  # Content source subscriptions
from app.routers import auth_router  # User authentication
from app.routers import ai_credentials_router  # Per-user AI provider keys
from app.routers import coin_icons_router  # Proxied coin icons to avoid CORS
from app.services.websocket_manager import ws_manager
from app.services.shutdown_manager import shutdown_manager
from app.services.content_refresh_service import content_refresh_service
import asyncio

logger = logging.getLogger(__name__)

app = FastAPI(title="Zenith Grid Trading Bot")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Multi-bot monitor - monitors all active bots with their strategies
# Each bot gets its exchange client from its associated account in the database
# Monitor loop runs every 10s to check if any bots need processing
price_monitor = MultiBotMonitor(interval_seconds=10)

# Trading pair monitor - daily job to remove delisted pairs, add new ones
trading_pair_monitor = TradingPairMonitor(check_interval_seconds=86400)  # 24 hours
set_trading_pair_monitor(trading_pair_monitor)  # Make accessible via API

# Background task handles
limit_order_monitor_task = None
order_reconciliation_monitor_task = None
missing_order_detector_task = None


def override_get_price_monitor():
    return price_monitor


# Include all routers
app.include_router(auth_router.router)  # Authentication (login, register, etc.)
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
app.include_router(news_router.router)  # Crypto news with 24h caching
app.include_router(sources_router.router)  # Content source subscriptions
app.include_router(ai_credentials_router.router)  # Per-user AI provider keys
app.include_router(coin_icons_router.router)  # Proxied coin icons to avoid CORS

# Mount static files for cached news images
# Images are stored in backend/static/news_images/ and served at /static/news_images/
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# Background task for limit order monitoring
# Now works with per-position exchange clients from accounts
async def run_limit_order_monitor():
    """Background task that monitors pending limit orders"""
    from app.database import async_session_maker
    from app.services.exchange_service import get_exchange_client_for_account
    from app.models import Position
    from sqlalchemy import select

    while True:
        try:
            async with async_session_maker() as db:
                # Get positions with pending limit close orders
                result = await db.execute(
                    select(Position).where(
                        Position.closing_via_limit.is_(True),
                        Position.limit_close_order_id.isnot(None),
                        Position.status == "open"
                    )
                )
                positions = result.scalars().all()

                for position in positions:
                    # Get exchange client for this position's account
                    if position.account_id:
                        exchange = await get_exchange_client_for_account(db, position.account_id)
                        if exchange:
                            monitor = LimitOrderMonitor(db, exchange)
                            await monitor.check_single_position_limit_order(position)
        except Exception as e:
            logger.error(f"Error in limit order monitor loop: {e}")

        # Check every 10 seconds
        await asyncio.sleep(10)


# Background task for order reconciliation
async def run_order_reconciliation_monitor():
    """Background task that auto-fixes positions with missing fill data"""
    from app.database import async_session_maker
    from app.services.order_reconciliation_monitor import OrderReconciliationMonitor
    from app.services.exchange_service import get_exchange_client_for_account
    from app.models import Position
    from sqlalchemy import select

    while True:
        try:
            async with async_session_maker() as db:
                # Get positions that might need reconciliation (open positions)
                result = await db.execute(
                    select(Position).where(Position.status == "open")
                )
                positions = result.scalars().all()

                # Group by account_id to minimize exchange client creation
                positions_by_account = {}
                for pos in positions:
                    account_id = pos.account_id or 0
                    if account_id not in positions_by_account:
                        positions_by_account[account_id] = []
                    positions_by_account[account_id].append(pos)

                for account_id, account_positions in positions_by_account.items():
                    if account_id > 0:
                        exchange = await get_exchange_client_for_account(db, account_id)
                        if exchange:
                            monitor = OrderReconciliationMonitor(db, exchange)
                            await monitor.check_and_fix_orphaned_positions()
        except Exception as e:
            logger.error(f"Error in order reconciliation monitor loop: {e}")

        # Check every 60 seconds (less frequent than limit orders)
        await asyncio.sleep(60)


# Background task for detecting missing orders
async def run_missing_order_detector():
    """Background task that detects orders on Coinbase not recorded in our DB"""
    from app.database import async_session_maker
    from app.services.order_reconciliation_monitor import MissingOrderDetector
    from app.services.exchange_service import get_exchange_client_for_account
    from app.models import Account
    from sqlalchemy import select

    # Wait 2 minutes after startup before first check
    await asyncio.sleep(120)

    while True:
        try:
            async with async_session_maker() as db:
                # Get primary account (account_id=1 for now, could be extended)
                result = await db.execute(select(Account).where(Account.id == 1))
                account = result.scalars().first()

                if account:
                    exchange = await get_exchange_client_for_account(db, account.id)
                    if exchange:
                        detector = MissingOrderDetector(db, exchange)
                        await detector.check_for_missing_orders()
        except Exception as e:
            logger.error(f"Error in missing order detector loop: {e}")

        # Check every 5 minutes
        await asyncio.sleep(300)


# Startup/Shutdown events
@app.on_event("startup")
async def startup_event():
    global limit_order_monitor_task, order_reconciliation_monitor_task, missing_order_detector_task

    print("🚀 ========================================")
    print("🚀 FastAPI startup event triggered")
    print("🚀 Initializing database...")
    await init_db()
    print("🚀 Database initialized successfully")

    # Start multi-bot monitor (gets exchange clients per-bot from accounts)
    print("🚀 Starting multi-bot monitor...")
    await price_monitor.start_async()
    print("🚀 Multi-bot monitor started - bot monitoring active")

    print("🚀 Starting limit order monitor...")
    limit_order_monitor_task = asyncio.create_task(run_limit_order_monitor())
    print("🚀 Limit order monitor started - checking every 10 seconds")

    print("🚀 Starting order reconciliation monitor...")
    order_reconciliation_monitor_task = asyncio.create_task(run_order_reconciliation_monitor())
    print("🚀 Order reconciliation monitor started - auto-fixing orphaned positions every 60 seconds")

    print("🚀 Starting missing order detector...")
    missing_order_detector_task = asyncio.create_task(run_missing_order_detector())
    print("🚀 Missing order detector started - checking for unrecorded orders every 5 minutes")

    print("🚀 Starting trading pair monitor...")
    await trading_pair_monitor.start()
    print("🚀 Trading pair monitor started - syncing pairs daily (first check in 5 minutes)")

    print("🚀 Starting content refresh service...")
    await content_refresh_service.start()
    print("🚀 Content refresh service started - news every 30min, videos every 60min")

    print("🚀 Building changelog cache...")
    build_changelog_cache()
    print("🚀 Changelog cache built")

    print("🚀 Startup complete!")
    print("🚀 ========================================")


@app.on_event("shutdown")
async def shutdown_event():
    global limit_order_monitor_task, order_reconciliation_monitor_task, missing_order_detector_task

    logger.info("🛑 Shutting down - waiting for in-flight orders...")

    # Wait for any in-flight orders to complete (up to 60 seconds)
    shutdown_result = await shutdown_manager.prepare_shutdown(timeout=60.0)
    if shutdown_result["ready"]:
        logger.info(f"✅ {shutdown_result['message']}")
    else:
        logger.warning(f"⚠️ {shutdown_result['message']}")

    logger.info("🛑 Stopping monitors...")
    if price_monitor:
        await price_monitor.stop()

    if content_refresh_service:
        await content_refresh_service.stop()

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

    if missing_order_detector_task:
        missing_order_detector_task.cancel()
        try:
            await missing_order_detector_task
        except asyncio.CancelledError:
            pass

    if trading_pair_monitor:
        await trading_pair_monitor.stop()

    logger.info("🛑 Monitors stopped - shutdown complete")


# WebSocket for real-time updates (order fill notifications)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and wait for messages
            data = await websocket.receive_text()
            # Echo back for debugging
            await websocket.send_json({"type": "echo", "message": f"Received: {data}"})
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
