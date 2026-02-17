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
import subprocess
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_unified_client import CoinbaseClient
from app.config import settings
from app.database import get_db
from app.encryption import decrypt_value, is_encrypted
from app.exchange_clients.factory import create_exchange_client
from app.models import Account, MarketData, Position, Signal, Trade, User
from app.multi_bot_monitor import MultiBotMonitor
from app.routers.auth_dependencies import get_current_user, require_superuser
from app.schemas import (
    DashboardStats,
    MarketDataResponse,
    PositionResponse,
    SignalResponse,
    TradeResponse,
)
from app.services.shutdown_manager import shutdown_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


def get_repo_root():
    """Get the repository root path"""
    from pathlib import Path
    current_file = Path(__file__).resolve()
    return current_file.parent.parent.parent.parent  # routers -> app -> backend -> repo root


def get_git_version() -> str:
    """Get the current git version tag (what we're running)"""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True,
            text=True,
            cwd=str(get_repo_root()),
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return "dev"


def get_latest_git_tag() -> str:
    """Get the latest git tag available (may be newer than running version)"""
    try:
        # Fetch latest tags from origin (silent, quick timeout)
        subprocess.run(
            ["git", "fetch", "--tags", "--quiet"],
            capture_output=True,
            cwd=str(get_repo_root()),
            timeout=10
        )
        # Get the latest tag sorted by version
        result = subprocess.run(
            ["git", "tag", "--sort=-version:refname"],
            capture_output=True,
            text=True,
            cwd=str(get_repo_root()),
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            # Return the first (latest) tag
            return result.stdout.strip().split('\n')[0]
    except Exception:
        pass

    return get_git_version()  # Fallback to current version


@router.get("/api/version")
async def get_version():
    """Get the current application version from git tags"""
    return {"version": get_git_version()}


def get_sorted_tags() -> list:
    """Get all git tags sorted by version (newest first)"""
    try:
        result = subprocess.run(
            ["git", "tag", "--sort=-version:refname"],
            capture_output=True,
            text=True,
            cwd=str(get_repo_root()),
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split('\n')
    except Exception:
        pass
    return []


# Cache for changelog data - invalidated when latest tag changes
_changelog_cache: dict = {
    "latest_tag": None,
    "versions": [],  # All versions with commits and dates
    "current_version": None,
}


def build_changelog_cache() -> None:
    """Build the full changelog cache. Called at startup and when cache is invalid."""
    global _changelog_cache
    repo_root = str(get_repo_root())

    # Fetch latest tags from origin (only done when rebuilding cache)
    try:
        subprocess.run(
            ["git", "fetch", "--tags", "--quiet"],
            capture_output=True,
            cwd=repo_root,
            timeout=10
        )
    except Exception:
        pass

    tags = get_sorted_tags()
    current_version = get_git_version()

    if len(tags) < 2:
        _changelog_cache = {
            "latest_tag": tags[0] if tags else None,
            "versions": [],
            "current_version": current_version
        }
        return

    versions = []

    for i in range(len(tags) - 1):
        curr_tag = tags[i]
        prev_tag = tags[i + 1]

        # Get commits between these tags
        try:
            result = subprocess.run(
                ["git", "log", "--format=%s", f"{prev_tag}..{curr_tag}"],
                capture_output=True,
                text=True,
                cwd=repo_root,
                timeout=5
            )
            commits = []
            if result.returncode == 0 and result.stdout.strip():
                commits = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
        except Exception:
            commits = []

        # Get tag date
        try:
            date_result = subprocess.run(
                ["git", "log", "-1", "--format=%ai", curr_tag],
                capture_output=True,
                text=True,
                cwd=repo_root,
                timeout=5
            )
            tag_date = date_result.stdout.strip()[:16] if date_result.stdout else ""
        except Exception:
            tag_date = ""

        versions.append({
            "version": curr_tag,
            "date": tag_date,
            "commits": commits,
            "is_installed": curr_tag == current_version
        })

    _changelog_cache = {
        "latest_tag": tags[0] if tags else None,
        "versions": versions,
        "current_version": current_version
    }


@router.get("/api/changelog")
async def get_changelog(limit: int = Query(20, ge=1, le=100), offset: int = 0, refresh: bool = False, current_user: User = Depends(get_current_user)):
    """
    Get changelog showing commits between version tags.
    Similar to 'python3 update.py --changelog' output.
    Supports pagination with limit and offset.
    Uses caching - rebuilds cache only on first call, when refresh=true, or when new tags detected.
    """
    # Check if cache needs rebuilding
    needs_rebuild = not _changelog_cache["versions"] or refresh

    # Auto-invalidate cache if new tags are available
    if not needs_rebuild:
        actual_latest = get_latest_git_tag()
        cached_latest = _changelog_cache["latest_tag"]
        if actual_latest != cached_latest:
            logger.info(f"New tag detected: {actual_latest} (cached: {cached_latest}), rebuilding changelog cache")
            needs_rebuild = True

    if needs_rebuild:
        build_changelog_cache()

    current_version = get_git_version()
    latest_tag = _changelog_cache["latest_tag"]
    all_versions = _changelog_cache["versions"]
    total_versions = len(all_versions)

    if total_versions == 0:
        return {
            "current_version": current_version,
            "latest_version": latest_tag or current_version,
            "versions": [],
            "total_versions": 0,
            "has_more": False
        }

    # Apply pagination
    start_idx = offset
    end_idx = min(offset + limit, total_versions)
    paginated_versions = all_versions[start_idx:end_idx]

    # Update is_installed flag based on current version (might change after update)
    for v in paginated_versions:
        v["is_installed"] = v["version"] == current_version

    return {
        "current_version": current_version,
        "latest_version": latest_tag or current_version,
        "update_available": latest_tag != current_version and current_version != "dev",
        "versions": paginated_versions,
        "total_versions": total_versions,
        "has_more": end_idx < total_versions
    }


async def get_coinbase(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CoinbaseClient:
    """
    Get Coinbase client for the authenticated user's active CEX account.
    """
    # Get user's active CEX account
    result = await db.execute(
        select(Account).where(
            Account.user_id == current_user.id,
            Account.type == "cex",
            Account.is_active.is_(True),
        ).order_by(Account.is_default.desc(), Account.created_at)
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=503,
            detail="No Coinbase account configured. Please add your API credentials in Settings."
        )

    if not account.api_key_name or not account.api_private_key:
        raise HTTPException(
            status_code=503,
            detail="Coinbase account missing API credentials. Please update in Settings."
        )

    # Decrypt private key if encrypted
    private_key = account.api_private_key
    if private_key and is_encrypted(private_key):
        private_key = decrypt_value(private_key)

    # Create and return the client
    client = create_exchange_client(
        exchange_type="cex",
        coinbase_key_name=account.api_key_name,
        coinbase_private_key=private_key,
    )

    if not client:
        raise HTTPException(
            status_code=503,
            detail="Failed to create Coinbase client. Please check your API credentials."
        )

    return client


def get_price_monitor() -> MultiBotMonitor:
    """Get price monitor - will be overridden in main.py"""
    raise NotImplementedError("Must override price_monitor dependency")


@router.get("/api/")
async def root():
    current_version = get_git_version()
    latest_version = get_latest_git_tag()
    return {
        "message": "ETH/BTC Trading Bot API",
        "status": "running",
        "version": current_version,
        "latest_version": latest_version,
        "update_available": latest_version != current_version and current_version != "dev"
    }


@router.get("/api/ai-providers")
async def get_ai_provider_info(current_user: User = Depends(get_current_user)):
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
            "grok": {
                "name": "xAI (Grok)",
                "billing_url": "https://console.x.ai/",
                "has_api_key": bool(settings.grok_api_key),
            },
            "groq": {
                "name": "Groq (Llama 3.1 70B)",
                "billing_url": "https://console.groq.com/keys",
                "has_api_key": bool(settings.groq_api_key),
                "free_tier": "14,400 RPD",
            },
            "openai": {
                "name": "OpenAI (GPT)",
                "billing_url": "https://platform.openai.com/usage",
                "has_api_key": bool(settings.openai_api_key),
            },
        }
    }


@router.get("/api/status")
async def get_status(
    coinbase: CoinbaseClient = Depends(get_coinbase), price_monitor: MultiBotMonitor = Depends(get_price_monitor),
    current_user: User = Depends(get_current_user)
):
    """Get overall system status"""
    try:
        connection_ok = await coinbase.test_connection()
        monitor_status = await price_monitor.get_status()

        return {"api_connected": connection_ok, "monitor": monitor_status, "timestamp": datetime.utcnow().isoformat()}
    except Exception:
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/api/dashboard", response_model=DashboardStats)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    coinbase: CoinbaseClient = Depends(get_coinbase),
    price_monitor: MultiBotMonitor = Depends(get_price_monitor),
    current_user: User = Depends(get_current_user),
):
    """Get dashboard statistics"""
    try:
        # Get current user's account IDs for scoping queries
        user_accounts_q = select(Account.id).where(Account.user_id == current_user.id)
        user_accounts_r = await db.execute(user_accounts_q)
        user_account_ids = [row[0] for row in user_accounts_r.fetchall()]

        # Get current position (scoped to user)
        current_position = None
        query = select(Position).where(
            Position.status == "open",
            Position.account_id.in_(user_account_ids) if user_account_ids else Position.id < 0,
        ).order_by(desc(Position.opened_at))
        result = await db.execute(query)
        pos = result.scalars().first()

        if pos:
            # Count trades for this position
            trade_count_query = select(func.count(Trade.id)).where(Trade.position_id == pos.id)
            trade_count_result = await db.execute(trade_count_query)
            trade_count = trade_count_result.scalar()

            current_position = PositionResponse.model_validate(pos)
            current_position.trade_count = trade_count

        # Total positions (scoped to user)
        total_positions_query = select(func.count(Position.id)).where(
            Position.account_id.in_(user_account_ids) if user_account_ids else Position.id < 0,
        )
        total_positions_result = await db.execute(total_positions_query)
        total_positions = total_positions_result.scalar() or 0

        # Total profit (closed positions only, scoped to user)
        profit_query = select(func.sum(Position.profit_btc)).where(
            Position.status == "closed",
            Position.account_id.in_(user_account_ids) if user_account_ids else Position.id < 0,
        )
        profit_result = await db.execute(profit_query)
        total_profit_btc = profit_result.scalar() or 0.0

        # Win rate (scoped to user)
        closed_positions_query = select(Position).where(
            Position.status == "closed",
            Position.account_id.in_(user_account_ids) if user_account_ids else Position.id < 0,
        )
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

    except Exception:
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.post("/api/monitor/start")
async def start_monitor(price_monitor: MultiBotMonitor = Depends(get_price_monitor), current_user: User = Depends(require_superuser)):
    """Start the price monitor (admin only)"""
    if not price_monitor.running:
        price_monitor.start()
        return {"message": "Monitor started"}
    return {"message": "Monitor already running"}


@router.post("/api/monitor/stop")
async def stop_monitor(price_monitor: MultiBotMonitor = Depends(get_price_monitor), current_user: User = Depends(require_superuser)):
    """Stop the price monitor (admin only)"""
    if price_monitor.running:
        await price_monitor.stop()
        return {"message": "Monitor stopped"}
    return {"message": "Monitor not running"}


@router.get("/api/trades", response_model=List[TradeResponse])
async def get_trades(limit: int = Query(100, ge=1, le=1000), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get recent trades (scoped to current user)"""
    # Get user's account IDs to scope trades via positions
    user_accounts_q = select(Account.id).where(Account.user_id == current_user.id)
    user_accounts_r = await db.execute(user_accounts_q)
    user_account_ids = [row[0] for row in user_accounts_r.fetchall()]

    # Get position IDs for user's accounts
    user_position_ids_q = select(Position.id).where(
        Position.account_id.in_(user_account_ids) if user_account_ids else Position.id < 0,
    )

    query = select(Trade).where(
        Trade.position_id.in_(user_position_ids_q)
    ).order_by(desc(Trade.timestamp)).limit(limit)
    result = await db.execute(query)
    trades = result.scalars().all()

    return [TradeResponse.model_validate(t) for t in trades]


@router.get("/api/signals", response_model=List[SignalResponse])
async def get_signals(limit: int = Query(100, ge=1, le=1000), db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get recent signals (scoped to current user)"""
    # Get user's account IDs to scope signals via positions
    user_accounts_q = select(Account.id).where(Account.user_id == current_user.id)
    user_accounts_r = await db.execute(user_accounts_q)
    user_account_ids = [row[0] for row in user_accounts_r.fetchall()]

    # Get position IDs for user's accounts
    user_position_ids_q = select(Position.id).where(
        Position.account_id.in_(user_account_ids) if user_account_ids else Position.id < 0,
    )

    query = select(Signal).where(
        Signal.position_id.in_(user_position_ids_q)
    ).order_by(desc(Signal.timestamp)).limit(limit)
    result = await db.execute(query)
    signals = result.scalars().all()

    return [SignalResponse.model_validate(s) for s in signals]


@router.get("/api/market-data", response_model=List[MarketDataResponse])
async def get_market_data(hours: int = 24, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get market data for charting (global — price/indicator data is not user-specific)"""
    start_time = datetime.utcnow() - timedelta(hours=hours)
    query = select(MarketData).where(MarketData.timestamp >= start_time).order_by(MarketData.timestamp)
    result = await db.execute(query)
    data = result.scalars().all()

    return [MarketDataResponse.model_validate(d) for d in data]


# === Graceful Shutdown Endpoints ===

@router.get("/api/system/shutdown-status")
async def get_shutdown_status(current_user: User = Depends(get_current_user)):
    """Get current shutdown manager status"""
    return shutdown_manager.get_status()


@router.post("/api/system/prepare-shutdown")
async def prepare_shutdown(timeout: int = 60, current_user: User = Depends(require_superuser)):
    """
    Prepare for graceful shutdown.

    This endpoint:
    1. Prevents new orders from being placed
    2. Waits for any in-flight orders to complete (up to timeout seconds)
    3. Returns when safe to stop the service

    Args:
        timeout: Maximum seconds to wait for in-flight orders (default: 60)

    Returns:
        - ready: True if safe to shutdown
        - in_flight_count: Orders still executing (if not ready)
        - waited_seconds: How long we waited
        - message: Human-readable status

    Usage from shell:
        curl -X POST http://localhost:8100/api/system/prepare-shutdown?timeout=60
    """
    logger.info(f"Prepare-shutdown requested with timeout={timeout}s")
    result = await shutdown_manager.prepare_shutdown(timeout=float(timeout))
    return result


@router.post("/api/system/cancel-shutdown")
async def cancel_shutdown(current_user: User = Depends(require_superuser)):
    """
    Cancel a pending shutdown request.

    This allows new orders to be placed again.
    """
    await shutdown_manager.cancel_shutdown()
    return {"message": "Shutdown cancelled", "status": shutdown_manager.get_status()}


# === Trading Pair Monitor Endpoints ===

# Reference to the trading pair monitor (set from main.py)
_trading_pair_monitor = None


def set_trading_pair_monitor(monitor):
    """Called from main.py to inject the trading pair monitor instance"""
    global _trading_pair_monitor
    _trading_pair_monitor = monitor


@router.get("/api/system/pair-monitor/status")
async def get_pair_monitor_status(current_user: User = Depends(require_superuser)):
    """Get status of the trading pair monitor"""
    if not _trading_pair_monitor:
        raise HTTPException(status_code=503, detail="Trading pair monitor not initialized")
    return _trading_pair_monitor.get_status()


@router.post("/api/system/pair-monitor/sync")
async def trigger_pair_sync(current_user: User = Depends(require_superuser)):
    """
    Manually trigger a trading pair sync.

    This will:
    1. Fetch all available products from Coinbase
    2. Remove delisted pairs from all bots
    3. Add newly listed pairs to bots with auto_add_new_pairs enabled

    Returns:
        - checked_at: Timestamp of the check
        - bots_checked: Number of bots checked
        - pairs_removed: Total pairs removed
        - pairs_added: Total pairs added
        - affected_bots: List of bots that were modified
        - new_pairs_available: New pairs that exist but aren't in any bot
        - errors: Any errors encountered
    """
    if not _trading_pair_monitor:
        raise HTTPException(status_code=503, detail="Trading pair monitor not initialized")

    logger.info("Manual pair sync triggered via API")
    result = await _trading_pair_monitor.run_once()
    return result
