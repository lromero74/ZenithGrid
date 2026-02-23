"""
Tests for backend/app/routers/system_router.py

Covers system-level endpoints: root/health, version, brand,
changelog, AI providers, shutdown management, and trading pair monitor.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.models import MarketData, User


# =============================================================================
# Helper functions
# =============================================================================


class TestGetRepoRoot:
    """Tests for get_repo_root()"""

    def test_returns_path(self):
        """Happy path: returns a Path object that exists."""
        from app.routers.system_router import get_repo_root
        root = get_repo_root()
        assert root.exists()


class TestGetGitVersion:
    """Tests for get_git_version()"""

    def test_returns_cached_version(self):
        """Happy path: returns the cached version string."""
        from app.routers.system_router import get_git_version
        version = get_git_version()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_does_not_change_between_calls(self):
        """Edge case: version is cached at import time, multiple calls return same value."""
        from app.routers.system_router import get_git_version
        v1 = get_git_version()
        v2 = get_git_version()
        assert v1 == v2


class TestGetSortedTags:
    """Tests for get_sorted_tags()"""

    def test_returns_list(self):
        """Happy path: returns a list of tags."""
        from app.routers.system_router import get_sorted_tags
        tags = get_sorted_tags()
        assert isinstance(tags, list)


# =============================================================================
# Public endpoints (no auth required)
# =============================================================================


class TestRootEndpoint:
    """Tests for GET /api/"""

    @pytest.mark.asyncio
    async def test_root_returns_status(self):
        """Happy path: root endpoint returns running status."""
        from app.routers.system_router import root
        result = await root()
        assert result["status"] == "running"
        assert "version" in result
        assert "message" in result

    @pytest.mark.asyncio
    async def test_root_contains_version_info(self):
        """Happy path: root includes version and latest_version."""
        from app.routers.system_router import root
        result = await root()
        assert "version" in result
        assert "latest_version" in result
        assert "update_available" in result


class TestVersionEndpoint:
    """Tests for GET /api/version"""

    @pytest.mark.asyncio
    async def test_version_returns_string(self):
        """Happy path: returns version as string."""
        from app.routers.system_router import get_version
        result = await get_version()
        assert "version" in result
        assert isinstance(result["version"], str)


class TestBrandEndpoint:
    """Tests for GET /api/brand"""

    @pytest.mark.asyncio
    async def test_brand_returns_config(self):
        """Happy path: returns brand configuration dict."""
        from app.routers.system_router import get_brand_config
        result = await get_brand_config()
        assert isinstance(result, dict)


class TestBrandImageEndpoint:
    """Tests for GET /api/brand/images/{filename}"""

    @pytest.mark.asyncio
    async def test_invalid_filename_returns_400(self):
        """Failure: path traversal in filename returns 400."""
        from fastapi import HTTPException
        from app.routers.system_router import get_brand_image

        with pytest.raises(HTTPException) as exc_info:
            await get_brand_image("../../etc/passwd")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_nonexistent_image_returns_404(self):
        """Failure: non-existent image file returns 404."""
        from fastapi import HTTPException
        from app.routers.system_router import get_brand_image

        with pytest.raises(HTTPException) as exc_info:
            await get_brand_image("nonexistent-image.png")
        assert exc_info.value.status_code == 404


# =============================================================================
# AI Provider Info
# =============================================================================


class TestAiProviderInfo:
    """Tests for GET /api/ai-providers"""

    @pytest.mark.asyncio
    async def test_returns_provider_dict(self):
        """Happy path: returns dict with provider information."""
        from app.routers.system_router import get_ai_provider_info

        user = MagicMock(spec=User)
        result = await get_ai_provider_info(current_user=user)
        assert "providers" in result
        assert "anthropic" in result["providers"]
        assert "gemini" in result["providers"]
        assert "grok" in result["providers"]
        assert "groq" in result["providers"]
        assert "openai" in result["providers"]

    @pytest.mark.asyncio
    async def test_provider_has_required_fields(self):
        """Edge case: each provider has name, billing_url, has_api_key."""
        from app.routers.system_router import get_ai_provider_info

        user = MagicMock(spec=User)
        result = await get_ai_provider_info(current_user=user)
        for name, provider in result["providers"].items():
            assert "name" in provider, f"Provider {name} missing 'name'"
            assert "billing_url" in provider, f"Provider {name} missing 'billing_url'"
            assert "has_api_key" in provider, f"Provider {name} missing 'has_api_key'"


# =============================================================================
# Changelog endpoint
# =============================================================================


class TestChangelogEndpoint:
    """Tests for GET /api/changelog"""

    @pytest.mark.asyncio
    async def test_changelog_returns_structure(self):
        """Happy path: returns pagination structure."""
        from app.routers.system_router import get_changelog

        user = MagicMock(spec=User)
        result = await get_changelog(limit=5, offset=0, refresh=False, current_user=user)
        assert "current_version" in result
        assert "versions" in result
        assert "total_versions" in result
        assert "has_more" in result

    @pytest.mark.asyncio
    async def test_changelog_pagination(self):
        """Edge case: offset and limit work for pagination."""
        from app.routers.system_router import get_changelog

        user = MagicMock(spec=User)
        # Get first 2
        result1 = await get_changelog(limit=2, offset=0, refresh=False, current_user=user)
        # Get next 2
        result2 = await get_changelog(limit=2, offset=2, refresh=False, current_user=user)

        # They should be from the same total
        assert result1["total_versions"] == result2["total_versions"]

    @pytest.mark.asyncio
    async def test_changelog_refresh_rebuilds_cache(self):
        """Edge case: refresh=True rebuilds the cache without error."""
        from app.routers.system_router import get_changelog

        user = MagicMock(spec=User)
        # Should not raise
        result = await get_changelog(limit=5, offset=0, refresh=True, current_user=user)
        assert "versions" in result


# =============================================================================
# Trades endpoint
# =============================================================================


class TestTradesEndpoint:
    """Tests for GET /api/trades"""

    @pytest.mark.asyncio
    async def test_trades_empty_for_new_user(self, db_session):
        """Happy path: new user with no trades returns empty list."""
        from app.routers.system_router import get_trades

        user = User(
            email="trades@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        result = await get_trades(limit=100, db=db_session, current_user=user)
        assert result == []


# =============================================================================
# Signals endpoint
# =============================================================================


class TestSignalsEndpoint:
    """Tests for GET /api/signals"""

    @pytest.mark.asyncio
    async def test_signals_empty_for_new_user(self, db_session):
        """Happy path: new user with no signals returns empty list."""
        from app.routers.system_router import get_signals

        user = User(
            email="signals@example.com",
            hashed_password="hashed",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(user)
        await db_session.flush()

        result = await get_signals(limit=100, db=db_session, current_user=user)
        assert result == []


# =============================================================================
# Market data endpoint
# =============================================================================


class TestMarketDataEndpoint:
    """Tests for GET /api/market-data"""

    @pytest.mark.asyncio
    async def test_market_data_empty_returns_empty(self, db_session):
        """Happy path: no market data returns empty list."""
        from app.routers.system_router import get_market_data

        user = MagicMock(spec=User)
        result = await get_market_data(hours=24, db=db_session, current_user=user)
        assert result == []

    @pytest.mark.asyncio
    async def test_market_data_returns_recent_data(self, db_session):
        """Happy path: returns market data within the time window."""
        from app.routers.system_router import get_market_data

        # Insert some market data
        md = MarketData(
            timestamp=datetime.utcnow() - timedelta(hours=1),
            price=50000.0,
        )
        db_session.add(md)
        await db_session.flush()

        user = MagicMock(spec=User)
        result = await get_market_data(hours=24, db=db_session, current_user=user)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_market_data_excludes_old_data(self, db_session):
        """Edge case: data older than the window is excluded."""
        from app.routers.system_router import get_market_data

        old_md = MarketData(
            timestamp=datetime.utcnow() - timedelta(hours=48),
            price=45000.0,
        )
        db_session.add(old_md)
        await db_session.flush()

        user = MagicMock(spec=User)
        result = await get_market_data(hours=24, db=db_session, current_user=user)
        assert len(result) == 0


# =============================================================================
# Shutdown management
# =============================================================================


class TestShutdownStatus:
    """Tests for GET /api/system/shutdown-status"""

    @pytest.mark.asyncio
    async def test_returns_status_dict(self):
        """Happy path: returns shutdown manager status."""
        from app.routers.system_router import get_shutdown_status

        user = MagicMock(spec=User)
        result = await get_shutdown_status(current_user=user)
        assert isinstance(result, dict)


class TestCancelShutdown:
    """Tests for POST /api/system/cancel-shutdown"""

    @pytest.mark.asyncio
    async def test_cancel_shutdown(self):
        """Happy path: cancelling shutdown returns success message."""
        from app.routers.system_router import cancel_shutdown

        user = MagicMock(spec=User)
        result = await cancel_shutdown(current_user=user)
        assert "message" in result
        assert "cancelled" in result["message"].lower()


# =============================================================================
# Trading pair monitor
# =============================================================================


class TestPairMonitorStatus:
    """Tests for GET /api/system/pair-monitor/status"""

    @pytest.mark.asyncio
    async def test_no_monitor_returns_503(self):
        """Failure: returns 503 when monitor not initialized."""
        from fastapi import HTTPException
        from app.routers.system_router import get_pair_monitor_status
        import app.routers.system_router as sm

        # Ensure monitor is None
        original = sm._trading_pair_monitor
        sm._trading_pair_monitor = None
        try:
            user = MagicMock(spec=User)
            with pytest.raises(HTTPException) as exc_info:
                await get_pair_monitor_status(current_user=user)
            assert exc_info.value.status_code == 503
        finally:
            sm._trading_pair_monitor = original

    @pytest.mark.asyncio
    async def test_returns_monitor_status(self):
        """Happy path: returns status when monitor is initialized."""
        from app.routers.system_router import get_pair_monitor_status
        import app.routers.system_router as sm

        original = sm._trading_pair_monitor
        mock_monitor = MagicMock()
        mock_monitor.get_status.return_value = {"running": True, "last_check": "2024-01-01"}
        sm._trading_pair_monitor = mock_monitor
        try:
            user = MagicMock(spec=User)
            result = await get_pair_monitor_status(current_user=user)
            assert result["running"] is True
        finally:
            sm._trading_pair_monitor = original


class TestTriggerPairSync:
    """Tests for POST /api/system/pair-monitor/sync"""

    @pytest.mark.asyncio
    async def test_no_monitor_returns_503(self):
        """Failure: returns 503 when monitor not initialized."""
        from fastapi import HTTPException
        from app.routers.system_router import trigger_pair_sync
        import app.routers.system_router as sm

        original = sm._trading_pair_monitor
        sm._trading_pair_monitor = None
        try:
            user = MagicMock(spec=User)
            with pytest.raises(HTTPException) as exc_info:
                await trigger_pair_sync(current_user=user)
            assert exc_info.value.status_code == 503
        finally:
            sm._trading_pair_monitor = original

    @pytest.mark.asyncio
    async def test_trigger_sync_calls_run_once(self):
        """Happy path: triggering sync calls run_once on the monitor."""
        from app.routers.system_router import trigger_pair_sync
        import app.routers.system_router as sm

        original = sm._trading_pair_monitor
        mock_monitor = MagicMock()
        mock_monitor.run_once = AsyncMock(return_value={
            "checked_at": "2024-01-01",
            "bots_checked": 5,
            "pairs_removed": 0,
            "pairs_added": 2,
        })
        sm._trading_pair_monitor = mock_monitor
        try:
            user = MagicMock(spec=User)
            result = await trigger_pair_sync(current_user=user)
            assert result["bots_checked"] == 5
            mock_monitor.run_once.assert_awaited_once()
        finally:
            sm._trading_pair_monitor = original


# =============================================================================
# Monitor start/stop
# =============================================================================


class TestMonitorStartStop:
    """Tests for POST /api/monitor/start and /api/monitor/stop"""

    @pytest.mark.asyncio
    async def test_start_monitor_when_not_running(self):
        """Happy path: starts the monitor."""
        from app.routers.system_router import start_monitor

        mock_monitor = MagicMock()
        mock_monitor.running = False

        user = MagicMock(spec=User)
        result = await start_monitor(price_monitor=mock_monitor, current_user=user)
        mock_monitor.start.assert_called_once()
        assert "started" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_start_monitor_already_running(self):
        """Edge case: returns already running message."""
        from app.routers.system_router import start_monitor

        mock_monitor = MagicMock()
        mock_monitor.running = True

        user = MagicMock(spec=User)
        result = await start_monitor(price_monitor=mock_monitor, current_user=user)
        mock_monitor.start.assert_not_called()
        assert "already running" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_stop_monitor_when_running(self):
        """Happy path: stops the monitor."""
        from app.routers.system_router import stop_monitor

        mock_monitor = MagicMock()
        mock_monitor.running = True
        mock_monitor.stop = AsyncMock()

        user = MagicMock(spec=User)
        result = await stop_monitor(price_monitor=mock_monitor, current_user=user)
        mock_monitor.stop.assert_awaited_once()
        assert "stopped" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_stop_monitor_not_running(self):
        """Edge case: returns not running message."""
        from app.routers.system_router import stop_monitor

        mock_monitor = MagicMock()
        mock_monitor.running = False

        user = MagicMock(spec=User)
        result = await stop_monitor(price_monitor=mock_monitor, current_user=user)
        assert "not running" in result["message"].lower()


# =============================================================================
# set_trading_pair_monitor
# =============================================================================


class TestSetTradingPairMonitor:
    """Tests for set_trading_pair_monitor()"""

    def test_sets_global_monitor(self):
        """Happy path: sets the global monitor reference."""
        from app.routers.system_router import set_trading_pair_monitor
        import app.routers.system_router as sm

        original = sm._trading_pair_monitor
        try:
            mock = MagicMock()
            set_trading_pair_monitor(mock)
            assert sm._trading_pair_monitor is mock
        finally:
            sm._trading_pair_monitor = original
