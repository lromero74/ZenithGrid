import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.cleanup_jobs import (
    cleanup_expired_revoked_tokens,
    cleanup_expired_sessions,
    cleanup_failed_condition_logs,
    cleanup_old_decision_logs,
    cleanup_old_failed_orders,
    cleanup_old_reports,
)
from app.services.coin_review_service import run_coin_review_scheduler
from app.services.report_scheduler import run_report_scheduler
from app.config import settings
from app.database import init_db
from app.multi_bot_monitor import MultiBotMonitor
from app.position_routers import perps_router
from app.routers import account_value_router  # Account value history tracking
from app.routers import accounts_router  # Multi-account management (CEX + DEX)
from app.routers import ai_credentials_router  # Per-user AI provider keys
from app.routers import auth_router  # User authentication
from app.routers import coin_icons_router  # Proxied coin icons to avoid CORS
from app.routers import paper_trading_router  # Paper trading account management
from app.routers import seasonality_router  # Seasonality-based bot management
from app.routers import sources_router  # Content source subscriptions
from app.routers import trading_router  # Manual trading operations
from app.routers import (
    account_router,
    blacklist_router,
    market_data_router,
    news_router,
    positions_router,
    settings_router,
    strategies_router,
    system_router,
)
from app.routers.order_history import router as order_history_router
from app.routers.templates import router as templates_router
from app.routers import admin_router  # RBAC admin management
from app.routers import prop_guard_router
from app.routers import reports_router  # Reporting & goals
from app.routers import transfers_router  # Deposit/withdrawal tracking
from app.routers import friends_router  # Friends & social
from app.routers import game_history_router  # Game history & privacy
from app.routers import tournament_router  # Multiplayer tournaments
from app.routers import display_name_router  # Display name management
from app.routers import sessions_router  # Session management for multiplayer
from app.routers import chat_router  # Chat (DMs, groups, channels)
from app.routers.bots import router as bots_router
from app.routers.system_router import build_changelog_cache, set_trading_pair_monitor
from app.services.auto_buy_monitor import AutoBuyMonitor
from app.services.rebalance_monitor import RebalanceMonitor
from app.services.content_refresh_service import content_refresh_service
from app.services.debt_ceiling_monitor import debt_ceiling_monitor
from app.services.delisted_pair_monitor import TradingPairMonitor
from app.services.domain_blacklist_service import domain_blacklist_service
from app.services.limit_order_monitor import LimitOrderMonitor
from app.services.perps_monitor import PerpsMonitor
from app.services.prop_guard_monitor import start_prop_guard_monitor, stop_prop_guard_monitor
from app.services.shutdown_manager import shutdown_manager
from app.services.brand_service import get_brand
from app.services.websocket_manager import ws_manager

logger = logging.getLogger(__name__)

_brand = get_brand()
app = FastAPI(title=f"{_brand['shortName']} Trading Platform")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)


# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(SecurityHeadersMiddleware)


# Global exception handler for domain exceptions raised by service layer
from app.exceptions import AppError  # noqa: E402


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    headers = {}
    if hasattr(exc, "retry_after") and exc.retry_after is not None:
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message}, headers=headers or None)


# Multi-bot monitor - monitors all active bots with their strategies
# Each bot gets its exchange client from its associated account in the database
# Monitor loop runs every 10s to check if any bots need processing
price_monitor = MultiBotMonitor(interval_seconds=10)

# Trading pair monitor - daily job to remove delisted pairs, add new ones
trading_pair_monitor = TradingPairMonitor(check_interval_seconds=86400)  # 24 hours
set_trading_pair_monitor(trading_pair_monitor)  # Make accessible via API

# Auto-buy BTC monitor - converts stablecoins to BTC based on account settings
auto_buy_monitor = AutoBuyMonitor()

# Portfolio rebalance monitor - maintains target USD/BTC/ETH allocations per account
rebalance_monitor = RebalanceMonitor()

# Perpetual futures position monitor - syncs open perps positions with exchange
perps_monitor = PerpsMonitor(interval_seconds=60)

# Background task handles
limit_order_monitor_task = None
order_reconciliation_monitor_task = None
missing_order_detector_task = None
decision_log_cleanup_task = None
failed_condition_cleanup_task = None
failed_order_cleanup_task = None
account_snapshot_task = None
revoked_token_cleanup_task = None
report_scheduler_task = None
report_cleanup_task = None
session_cleanup_task = None
transfer_sync_task = None


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
app.include_router(strategies_router.router)  # Trading strategy definitions
app.include_router(blacklist_router.router)
app.include_router(news_router.router)  # Crypto news with 24h caching
app.include_router(sources_router.router)  # Content source subscriptions
app.include_router(ai_credentials_router.router)  # Per-user AI provider keys
app.include_router(coin_icons_router.router)  # Proxied coin icons to avoid CORS
app.include_router(paper_trading_router.router)  # Paper trading account management
app.include_router(account_value_router.router)  # Account value history tracking
app.include_router(trading_router.router)  # Manual trading operations
app.include_router(seasonality_router.router)  # Seasonality-based bot management
app.include_router(perps_router.router)  # Perpetual futures (INTX) management

app.include_router(admin_router.router)  # RBAC admin management
app.include_router(prop_guard_router.router)  # PropGuard safety monitoring
app.include_router(reports_router.router)  # Reporting & goals
app.include_router(transfers_router.router)  # Deposit/withdrawal tracking
app.include_router(friends_router.router)  # Friends & social
app.include_router(friends_router.search_router)  # User search
app.include_router(game_history_router.router)  # Game history & privacy
app.include_router(tournament_router.router)  # Multiplayer tournaments
app.include_router(display_name_router.router)  # Display name management
app.include_router(sessions_router.router)  # Session management for multiplayer
app.include_router(chat_router.router)  # Chat (DMs, groups, channels)

# Mount static files for cached news images
# Images are stored in backend/static/news_images/ and served at /static/news_images/
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# Background task for limit order monitoring
# Now works with per-position exchange clients from accounts
async def run_limit_order_monitor():
    """Background task that monitors pending limit orders"""
    from sqlalchemy import select

    from app.database import async_session_maker
    from app.models import Position
    from app.services.exchange_service import get_exchange_client_for_account
    from app.services.limit_order_monitor import sweep_orphaned_pending_orders

    # Run startup reconciliation once
    logger.info("Running startup reconciliation for limit orders...")
    try:
        async with async_session_maker() as db:
            # Check ALL positions with limit_close_order_id (regardless of closing_via_limit flag)
            # This catches orphaned orders where the flag wasn't set
            result = await db.execute(
                select(Position).where(
                    Position.status == "open",
                    Position.limit_close_order_id.isnot(None)
                )
            )
            positions = result.scalars().all()

            if positions:
                logger.info(f"Found {len(positions)} positions with limit order IDs - checking each...")

                for position in positions:
                    # Ensure closing_via_limit flag is set (fix orphaned orders)
                    if not position.closing_via_limit:
                        logger.warning(
                            f"Position {position.id} has order ID but closing_via_limit is False - fixing..."
                        )
                        position.closing_via_limit = True

                    # Get exchange client and check order status
                    if position.account_id:
                        exchange = await get_exchange_client_for_account(db, position.account_id)
                        if exchange:
                            monitor = LimitOrderMonitor(db, exchange)
                            await monitor.check_single_position_limit_order(position)

                await db.commit()
                logger.info(f"Startup reconciliation complete: Checked {len(positions)} orders")
            else:
                logger.info("No pending limit orders to check")

            # Fix orphaned positions: closing_via_limit=True but no order ID
            # This can happen if a cancel+replace failed midway before restart
            orphaned = await db.execute(
                select(Position).where(
                    Position.status == "open",
                    Position.closing_via_limit.is_(True),
                    Position.limit_close_order_id.is_(None)
                )
            )
            orphaned_positions = orphaned.scalars().all()
            if orphaned_positions:
                logger.warning(
                    f"Found {len(orphaned_positions)} orphaned positions "
                    f"(closing_via_limit=True but no order ID) - clearing flags..."
                )
                for pos in orphaned_positions:
                    pos.closing_via_limit = False
                    logger.info(f"Fixed position {pos.id}: cleared closing_via_limit")
                await db.commit()
    except Exception as e:
        logger.error(f"Error in startup reconciliation: {e}")

    # Main monitoring loop
    sweep_counter = 0
    SWEEP_INTERVAL = 30  # Every 30 iterations (5 minutes at 10s interval)

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

                # Periodic orphaned record sweep (every ~5 minutes)
                sweep_counter += 1
                if sweep_counter >= SWEEP_INTERVAL:
                    sweep_counter = 0
                    await sweep_orphaned_pending_orders(db)
        except Exception as e:
            logger.error(f"Error in limit order monitor loop: {e}")

        # Check every 10 seconds
        await asyncio.sleep(10)


# Background task for order reconciliation
async def run_order_reconciliation_monitor():
    """Background task that auto-fixes positions with missing fill data.

    Runs immediately on startup (catch crash-orphaned orders), then
    checks every 60 seconds.
    """
    from sqlalchemy import select

    from app.database import async_session_maker
    from app.models import Position
    from app.services.exchange_service import get_exchange_client_for_account
    from app.services.order_reconciliation_monitor import OrderReconciliationMonitor

    first_run = True
    while True:
        try:
            if first_run:
                logger.info("Running startup reconciliation for orphaned orders...")

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
                            monitor = OrderReconciliationMonitor(db, exchange, account_id=account_id)
                            await monitor.check_and_fix_orphaned_positions()

            if first_run:
                logger.info("Startup order reconciliation complete")
                first_run = False

        except Exception as e:
            logger.error(f"Error in order reconciliation monitor loop: {e}")
            if first_run:
                logger.error(f"Startup order reconciliation error: {e}")
                first_run = False

        # Check every 60 seconds (less frequent than limit orders)
        await asyncio.sleep(60)


# Background task for detecting missing orders
async def run_missing_order_detector():
    """Background task that detects orders on exchanges not recorded in our DB"""
    from sqlalchemy import select

    from app.database import async_session_maker
    from app.models import Account
    from app.services.exchange_service import get_exchange_client_for_account
    from app.services.order_reconciliation_monitor import MissingOrderDetector

    # Wait 2 minutes after startup before first check
    await asyncio.sleep(120)

    while True:
        try:
            async with async_session_maker() as db:
                # Check all active accounts (not just account_id=1)
                result = await db.execute(
                    select(Account).where(Account.is_active.is_(True))
                )
                accounts = result.scalars().all()

                for account in accounts:
                    try:
                        exchange = await get_exchange_client_for_account(
                            db, account.id
                        )
                        if exchange:
                            detector = MissingOrderDetector(db, exchange, account_id=account.id)
                            await detector.check_for_missing_orders()
                    except Exception as e:
                        logger.error(
                            f"Error checking missing orders for account "
                            f"{account.id}: {e}"
                        )
        except Exception as e:
            logger.error(f"Error in missing order detector loop: {e}")

        # Check every 5 minutes
        await asyncio.sleep(300)


# Background task for capturing daily account value snapshots
async def run_account_snapshot_capture():
    """Background task that captures account value snapshots once per day"""
    from sqlalchemy import select

    from app.database import async_session_maker
    from app.models import User
    from app.services import account_snapshot_service

    # Wait 5 minutes after startup before first check
    await asyncio.sleep(300)

    while True:
        try:
            async with async_session_maker() as db:
                # Get all active users
                result = await db.execute(select(User).where(User.is_active.is_(True)))
                users = result.scalars().all()

                for user in users:
                    try:
                        logger.info(f"Capturing account snapshots for user {user.id}")
                        result = await account_snapshot_service.capture_all_account_snapshots(
                            db, user.id
                        )
                        logger.info(
                            f"User {user.id}: {result['success_count']}/"
                            f"{result['total_accounts']} snapshots captured"
                        )
                        if result['errors']:
                            for error in result['errors']:
                                logger.warning(f"Snapshot error: {error}")
                    except Exception as e:
                        logger.error(f"Failed to capture snapshots for user {user.id}: {e}")

        except Exception as e:
            logger.error(f"Error in account snapshot capture loop: {e}")

        # Run once per day (24 hours)
        await asyncio.sleep(86400)


# Background task for syncing deposit/withdrawal transfers from Coinbase
async def run_transfer_sync():
    """Background task that syncs transfers once per day, after snapshots."""
    from sqlalchemy import select

    from app.database import async_session_maker
    from app.models import User
    from app.services.transfer_sync_service import sync_all_user_transfers

    # Wait 20 minutes after startup (run after account snapshots)
    await asyncio.sleep(1200)

    while True:
        try:
            async with async_session_maker() as db:
                result = await db.execute(
                    select(User).where(User.is_active.is_(True))
                )
                users = result.scalars().all()

                for user in users:
                    try:
                        count = await sync_all_user_transfers(db, user.id)
                        if count > 0:
                            logger.info(
                                f"Synced {count} new transfers for "
                                f"user {user.id}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Transfer sync failed for user {user.id}: {e}"
                        )

        except Exception as e:
            logger.error(f"Error in transfer sync loop: {e}")

        # Run once per day
        await asyncio.sleep(86400)


# Startup/Shutdown events
@app.on_event("startup")
async def startup_event():
    global limit_order_monitor_task, order_reconciliation_monitor_task
    global missing_order_detector_task, decision_log_cleanup_task
    global failed_condition_cleanup_task, failed_order_cleanup_task
    global account_snapshot_task, revoked_token_cleanup_task
    global report_scheduler_task, report_cleanup_task
    global session_cleanup_task, transfer_sync_task

    logger.info("========================================")
    logger.info("FastAPI startup event triggered")

    # Security: Refuse to start with default JWT secret
    if settings.jwt_secret_key == "jwt-secret-key-change-in-production" or not settings.jwt_secret_key:
        logger.critical("SECURITY: JWT_SECRET_KEY is not set or still has default value!")
        logger.critical("SECURITY: Run setup.py to generate a secure JWT secret, or set JWT_SECRET_KEY in .env")
        raise RuntimeError("JWT_SECRET_KEY must be set to a secure value before starting the application")

    # Warn if email/URL config is empty (non-fatal — only needed for email features)
    if not settings.ses_sender_email:
        logger.warning("SES_SENDER_EMAIL is not set — email features (verification, MFA) will not work")
    if not settings.frontend_url:
        logger.warning("FRONTEND_URL is not set — email links will be broken")

    # VACUUM before init_db() — needs exclusive access (SQLite only)
    if not settings.is_postgres:
        try:
            import sqlite3
            db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
            conn = sqlite3.connect(db_path, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("VACUUM")
            conn.close()
            logger.info("Database VACUUM completed successfully")
        except Exception as e:
            logger.warning(f"Database VACUUM failed (non-fatal): {e}")

    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully")

    # Start multi-bot monitor (gets exchange clients per-bot from accounts)
    logger.info("Starting multi-bot monitor...")
    await price_monitor.start_async()
    logger.info("Multi-bot monitor started - bot monitoring active")

    logger.info("Starting limit order monitor...")
    limit_order_monitor_task = asyncio.create_task(run_limit_order_monitor())
    logger.info("Limit order monitor started - checking every 10 seconds")

    logger.info("Starting order reconciliation monitor...")
    order_reconciliation_monitor_task = asyncio.create_task(run_order_reconciliation_monitor())
    logger.info("Order reconciliation monitor started - auto-fixing orphaned positions every 60 seconds")

    logger.info("Starting missing order detector...")
    missing_order_detector_task = asyncio.create_task(run_missing_order_detector())
    logger.info("Missing order detector started - checking for unrecorded orders every 5 minutes")

    logger.info("Starting trading pair monitor...")
    await trading_pair_monitor.start()
    logger.info("Trading pair monitor started - syncing pairs daily (first check in 5 minutes)")

    logger.info("Starting content refresh service...")
    await content_refresh_service.start()
    logger.info("Content refresh service started - news every 30min, videos every 60min")

    logger.info("Starting domain blacklist service...")
    await domain_blacklist_service.start()
    logger.info("Domain blacklist service started - refreshing weekly")

    logger.info("Starting debt ceiling monitor...")
    await debt_ceiling_monitor.start()
    logger.info("Debt ceiling monitor started - checking for new legislation weekly")

    logger.info("Starting auto-buy BTC monitor...")
    await auto_buy_monitor.start()
    logger.info("Auto-buy BTC monitor started - converting stablecoins to BTC per account settings")

    logger.info("Starting portfolio rebalance monitor...")
    await rebalance_monitor.start()
    logger.info("Rebalance monitor started - maintaining target allocations per account")

    logger.info("Starting perps position monitor...")
    await perps_monitor.start()
    logger.info("Perps monitor started - syncing futures positions every 60s")

    logger.info("Starting PropGuard safety monitor...")
    await start_prop_guard_monitor()
    logger.info("PropGuard monitor started - checking prop firm drawdowns every 30s")

    logger.info("Building changelog cache...")
    build_changelog_cache()
    logger.info("Changelog cache built")

    logger.info("Starting decision log cleanup job...")
    decision_log_cleanup_task = asyncio.create_task(cleanup_old_decision_logs())
    logger.info("Decision log cleanup job started - cleaning old logs daily")

    logger.info("Starting failed condition log cleanup job...")
    failed_condition_cleanup_task = asyncio.create_task(cleanup_failed_condition_logs())
    logger.info("Failed condition log cleanup job started - removing noise logs every 6 hours")

    logger.info("Starting failed order cleanup job...")
    failed_order_cleanup_task = asyncio.create_task(cleanup_old_failed_orders())
    logger.info("Failed order cleanup job started - removing old failed orders every 6 hours")

    logger.info("Starting account snapshot capture job...")
    account_snapshot_task = asyncio.create_task(run_account_snapshot_capture())
    logger.info("Account snapshot capture job started - capturing daily account values")

    logger.info("Starting revoked token cleanup job...")
    revoked_token_cleanup_task = asyncio.create_task(cleanup_expired_revoked_tokens())
    logger.info("Revoked token cleanup job started - pruning expired entries daily")

    logger.info("Starting report scheduler...")
    report_scheduler_task = asyncio.create_task(run_report_scheduler())
    logger.info("Report scheduler started - checking for due reports every 15 minutes")

    logger.info("Starting report cleanup job...")
    report_cleanup_task = asyncio.create_task(cleanup_old_reports())
    logger.info("Report cleanup job started - removing reports older than 2 years weekly")

    logger.info("Starting coin review scheduler...")
    coin_review_task = asyncio.create_task(run_coin_review_scheduler())  # noqa: F841
    logger.info("Coin review scheduler started - full review every 7 days")

    logger.info("Starting session cleanup job...")
    session_cleanup_task = asyncio.create_task(cleanup_expired_sessions())
    logger.info("Session cleanup job started - expiring stale sessions daily")

    logger.info("Starting transfer sync job...")
    transfer_sync_task = asyncio.create_task(run_transfer_sync())
    logger.info("Transfer sync started - syncing deposits/withdrawals daily")

    logger.info("Startup complete!")
    logger.info("========================================")


async def _cancel_task(task: Optional[asyncio.Task]) -> None:
    """Cancel a background task and await its completion."""
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Shutting down - waiting for in-flight orders...")

    # Wait for any in-flight orders to complete (up to 60 seconds)
    shutdown_result = await shutdown_manager.prepare_shutdown(timeout=60.0)
    if shutdown_result["ready"]:
        logger.info(f"✅ {shutdown_result['message']}")
    else:
        logger.warning(f"⚠️ {shutdown_result['message']}")

    # Stop monitors that have their own .stop() method
    logger.info("🛑 Stopping monitors...")
    for monitor in [
        price_monitor, content_refresh_service, domain_blacklist_service,
        debt_ceiling_monitor, auto_buy_monitor, rebalance_monitor, perps_monitor,
    ]:
        if monitor:
            await monitor.stop()

    logger.info("🛑 Stopping PropGuard monitor...")
    await stop_prop_guard_monitor()

    # Cancel all background asyncio tasks
    for task in [
        limit_order_monitor_task, order_reconciliation_monitor_task,
        missing_order_detector_task, decision_log_cleanup_task,
        failed_condition_cleanup_task, failed_order_cleanup_task,
        account_snapshot_task, revoked_token_cleanup_task,
        report_scheduler_task, report_cleanup_task,
        session_cleanup_task, transfer_sync_task,
    ]:
        await _cancel_task(task)

    if trading_pair_monitor:
        await trading_pair_monitor.stop()

    # Close all cached exchange clients (releases httpx connections etc.)
    from app.services.exchange_service import clear_exchange_client_cache
    clear_exchange_client_cache()

    logger.info("🛑 Monitors stopped - shutdown complete")


# WebSocket for real-time updates (order fill notifications)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    # Validate JWT token before accepting WebSocket connection
    if not token:
        await websocket.close(code=4001, reason="Authentication required")
        return

    try:
        from app.database import async_session_maker
        from app.auth.dependencies import (
            check_token_revocation, decode_token, get_user_by_id,
        )

        payload = decode_token(token)
        if payload.get("type") != "access":
            await websocket.close(code=4001, reason="Invalid token type")
            return

        user_id = int(payload.get("sub"))
        async with async_session_maker() as db:
            # Check token revocation (JTI + bulk)
            await check_token_revocation(payload, db)

            user = await get_user_by_id(db, user_id)
            if not user or not user.is_active:
                await websocket.close(code=4001, reason="Invalid user")
                return

            # Check bulk revocation (password change)
            from datetime import datetime
            iat = payload.get("iat")
            if user.tokens_valid_after and iat:
                token_issued = datetime.utcfromtimestamp(iat)
                if token_issued < user.tokens_valid_after:
                    await websocket.close(code=4001, reason="Session expired")
                    return

            # Extract user permissions for game room RBAC
            from app.auth.dependencies import _get_user_permissions
            user_permissions = _get_user_permissions(user)
            display_name = user.display_name or f"Player {user_id}"
    except Exception:
        await websocket.close(code=4001, reason="Authentication failed")
        return

    from app.services.websocket_manager import MAX_MESSAGE_SIZE, RECEIVE_TIMEOUT_SECONDS

    connected = await ws_manager.connect(websocket, user_id)
    if not connected:
        return  # rejected — too many connections (4008 already sent)

    try:
        while True:
            # Receive with timeout so idle connections get cleaned up
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=RECEIVE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                await websocket.close(code=4010, reason="Idle timeout")
                break

            # Enforce message size limit
            if len(data) > MAX_MESSAGE_SIZE:
                await websocket.close(code=4009, reason="Message too large")
                break

            import json as _json
            try:
                msg = _json.loads(data)
            except _json.JSONDecodeError:
                await websocket.send_json({"type": "error", "error": "Invalid JSON"})
                continue

            msg_type = msg.get("type", "")

            # Route game messages to game room handler
            if msg_type.startswith("game:"):
                from app.services.game_ws_handler import handle_game_message
                await handle_game_message(
                    ws_manager, websocket, user_id, msg,
                    user_permissions, display_name,
                )
            elif msg_type.startswith("chat:"):
                from app.services.chat_ws_handler import handle_chat_message
                await handle_chat_message(
                    ws_manager, websocket, user_id, msg, display_name,
                )
            else:
                await websocket.send_json({"type": "echo", "message": f"Received: {data}"})
    except WebSocketDisconnect:
        pass
    finally:
        # Notify other players of disconnect (abend — not a forfeit/loss)
        from app.services.game_ws_handler import handle_player_disconnect
        await handle_player_disconnect(ws_manager, user_id)

        # Clean up game room on disconnect — but NOT if game is in progress
        # (disconnected players get a reconnect window before being removed)
        from app.services.game_room_manager import game_room_manager
        room_id = game_room_manager.get_user_room(user_id)
        if room_id:
            room = game_room_manager.get_room(room_id)
            if room:
                if room.status == "playing":
                    # Game in progress — player stays in room as "disconnected"
                    # handle_player_disconnect already marked them; they can rejoin
                    pass
                else:
                    # Waiting/finished — remove normally
                    players_before = set(room.players)
                    is_host = user_id == room.host_user_id
                    game_room_manager.leave_room(room_id, user_id)
                    if is_host:
                        await ws_manager.send_to_room(
                            players_before - {user_id},
                            {"type": "game:room_closed", "roomId": room_id,
                             "reason": "Host disconnected"},
                        )
                    elif room_id in game_room_manager._rooms:
                        await ws_manager.send_to_room(
                            room.players,
                            {"type": "game:player_left", "roomId": room_id,
                             "playerId": user_id, "players": list(room.players)},
                        )
        # Opportunistically clean up stale rooms on disconnect
        game_room_manager.cleanup_stale_rooms()
        await ws_manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Serve production frontend (built with `vite build` → frontend/dist/)
# Must be AFTER all API routes so /api/* and /ws are matched first.
# ---------------------------------------------------------------------------
_frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    # Serve JS/CSS/image assets
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="frontend-assets")

    # SPA catch-all: any non-API route returns index.html for client-side routing
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # Serve actual files from dist/ if they exist (e.g. favicon, manifest)
        file_path = _frontend_dist / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_frontend_dist / "index.html"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8100)
