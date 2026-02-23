"""
Tests for backend/app/services/delisted_pair_monitor.py

Tests the TradingPairMonitor service that syncs trading pairs
with the exchange, removing delisted pairs and adding new ones.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.delisted_pair_monitor import (
    TradingPairMonitor,
    EXCLUDED_PAIRS,
)


# ---------------------------------------------------------------------------
# TradingPairMonitor.__init__ / lifecycle tests
# ---------------------------------------------------------------------------

class TestTradingPairMonitorInit:
    """Tests for TradingPairMonitor initialization and lifecycle."""

    def test_init_defaults(self):
        """Happy path: monitor initializes with expected defaults."""
        monitor = TradingPairMonitor()
        assert monitor.check_interval_seconds == 86400  # 24 hours
        assert monitor.running is False
        assert monitor.task is None
        assert monitor._last_check is None
        assert monitor._available_products == set()
        assert monitor._btc_pairs == set()
        assert monitor._usd_pairs == set()

    def test_init_custom_interval(self):
        """Happy path: custom check interval."""
        monitor = TradingPairMonitor(check_interval_seconds=3600)
        assert monitor.check_interval_seconds == 3600


# ---------------------------------------------------------------------------
# _get_quote_currency tests
# ---------------------------------------------------------------------------

class TestGetQuoteCurrency:
    """Tests for TradingPairMonitor._get_quote_currency()."""

    def test_btc_pairs(self):
        """Happy path: identifies BTC quote currency."""
        monitor = TradingPairMonitor()
        result = monitor._get_quote_currency(["ETH-BTC", "SOL-BTC"])
        assert result == "BTC"

    def test_usd_pairs(self):
        """Happy path: identifies USD quote currency."""
        monitor = TradingPairMonitor()
        result = monitor._get_quote_currency(["ETH-USD", "SOL-USD"])
        assert result == "USD"

    def test_empty_list_returns_none(self):
        """Edge case: empty list returns None."""
        monitor = TradingPairMonitor()
        result = monitor._get_quote_currency([])
        assert result is None

    def test_unknown_quote_returns_none(self):
        """Edge case: pair with unknown quote currency."""
        monitor = TradingPairMonitor()
        result = monitor._get_quote_currency(["ETH-EUR"])
        assert result is None


# ---------------------------------------------------------------------------
# get_available_products tests
# ---------------------------------------------------------------------------

class TestGetAvailableProducts:
    """Tests for TradingPairMonitor.get_available_products()."""

    @pytest.mark.asyncio
    @patch('app.services.delisted_pair_monitor.get_exchange_client_for_account')
    async def test_fetches_and_categorizes_products(self, mock_get_client, db_session):
        """Happy path: fetches products and categorizes by quote currency."""
        mock_exchange = AsyncMock()
        mock_exchange.list_products = AsyncMock(return_value=[
            {"product_id": "ETH-BTC", "trading_disabled": False, "status": "online"},
            {"product_id": "SOL-BTC", "trading_disabled": False, "status": "online"},
            {"product_id": "BTC-USD", "trading_disabled": False, "status": "online"},
            {"product_id": "ETH-USD", "trading_disabled": False, "status": "online"},
        ])
        mock_get_client.return_value = mock_exchange

        # Mock account query
        mock_account = MagicMock()
        mock_account.id = 1
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_account
        db_session.execute = AsyncMock(return_value=mock_result)

        monitor = TradingPairMonitor()
        products = await monitor.get_available_products(db_session)

        assert "ETH-BTC" in products
        assert "SOL-BTC" in products
        assert "BTC-USD" in products
        assert "ETH-USD" in products
        assert "ETH-BTC" in monitor._btc_pairs
        assert "BTC-USD" in monitor._usd_pairs

    @pytest.mark.asyncio
    @patch('app.services.delisted_pair_monitor.get_exchange_client_for_account')
    async def test_excluded_pairs_filtered_out(self, mock_get_client, db_session):
        """Edge case: excluded pairs (stablecoins) are filtered out."""
        mock_exchange = AsyncMock()
        mock_exchange.list_products = AsyncMock(return_value=[
            {"product_id": "USDC-USD", "trading_disabled": False, "status": "online"},
            {"product_id": "ETH-BTC", "trading_disabled": False, "status": "online"},
        ])
        mock_get_client.return_value = mock_exchange

        mock_account = MagicMock()
        mock_account.id = 1
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_account
        db_session.execute = AsyncMock(return_value=mock_result)

        monitor = TradingPairMonitor()
        products = await monitor.get_available_products(db_session)

        assert "USDC-USD" not in products  # Excluded
        assert "ETH-BTC" in products

    @pytest.mark.asyncio
    @patch('app.services.delisted_pair_monitor.get_exchange_client_for_account')
    async def test_trading_disabled_pairs_filtered_out(self, mock_get_client, db_session):
        """Edge case: pairs with trading_disabled=True are filtered."""
        mock_exchange = AsyncMock()
        mock_exchange.list_products = AsyncMock(return_value=[
            {"product_id": "DEAD-BTC", "trading_disabled": True, "status": "online"},
            {"product_id": "ETH-BTC", "trading_disabled": False, "status": "online"},
        ])
        mock_get_client.return_value = mock_exchange

        mock_account = MagicMock()
        mock_account.id = 1
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_account
        db_session.execute = AsyncMock(return_value=mock_result)

        monitor = TradingPairMonitor()
        products = await monitor.get_available_products(db_session)

        assert "DEAD-BTC" not in products
        assert "ETH-BTC" in products

    @pytest.mark.asyncio
    async def test_no_active_account_returns_empty(self, db_session):
        """Failure: no active CEX account, returns empty set."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        db_session.execute = AsyncMock(return_value=mock_result)

        monitor = TradingPairMonitor()
        products = await monitor.get_available_products(db_session)

        assert products == set()

    @pytest.mark.asyncio
    @patch('app.services.delisted_pair_monitor.get_exchange_client_for_account')
    async def test_no_exchange_client_returns_empty(self, mock_get_client, db_session):
        """Failure: exchange client creation fails, returns empty set."""
        mock_get_client.return_value = None

        mock_account = MagicMock()
        mock_account.id = 1
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_account
        db_session.execute = AsyncMock(return_value=mock_result)

        monitor = TradingPairMonitor()
        products = await monitor.get_available_products(db_session)

        assert products == set()


# ---------------------------------------------------------------------------
# get_status tests
# ---------------------------------------------------------------------------

class TestGetStatus:
    """Tests for TradingPairMonitor.get_status()."""

    def test_status_before_any_check(self):
        """Happy path: status before any check runs."""
        monitor = TradingPairMonitor()
        status = monitor.get_status()
        assert status["running"] is False
        assert status["last_check"] is None
        assert status["check_interval_hours"] == pytest.approx(24.0)
        assert status["available_products_count"] == 0

    def test_status_after_products_loaded(self):
        """Happy path: status after products loaded."""
        monitor = TradingPairMonitor()
        monitor._available_products = {"ETH-BTC", "SOL-BTC", "BTC-USD"}
        monitor._btc_pairs = {"ETH-BTC", "SOL-BTC"}
        monitor._usd_pairs = {"BTC-USD"}
        monitor._last_check = datetime(2025, 1, 1, 12, 0, 0)
        monitor.running = True

        status = monitor.get_status()
        assert status["running"] is True
        assert status["available_products_count"] == 3
        assert status["btc_pairs_count"] == 2
        assert status["usd_pairs_count"] == 1


# ---------------------------------------------------------------------------
# check_and_sync_pairs tests
# ---------------------------------------------------------------------------

class TestCheckAndSyncPairs:
    """Tests for TradingPairMonitor.check_and_sync_pairs()."""

    @pytest.mark.asyncio
    @patch('app.services.delisted_pair_monitor.async_session_maker')
    async def test_no_available_products_reports_error(self, mock_session_maker):
        """Failure: could not fetch products, error reported."""
        mock_db = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        monitor = TradingPairMonitor()
        with patch.object(monitor, 'get_available_products', new_callable=AsyncMock, return_value=set()):
            results = await monitor.check_and_sync_pairs()

        assert "Could not fetch available products" in results["errors"]

    @pytest.mark.asyncio
    @patch('app.services.delisted_pair_monitor.async_session_maker')
    async def test_delisted_pair_removed_from_bot(self, mock_session_maker):
        """Happy path: delisted pair removed from bot configuration."""
        mock_db = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        # Bot with a delisted pair
        mock_bot = MagicMock()
        mock_bot.id = 1
        mock_bot.name = "TestBot"
        mock_bot.product_ids = ["ETH-BTC", "DELISTED-BTC", "SOL-BTC"]
        mock_bot.strategy_config = {"auto_add_new_pairs": False}
        bot_result = MagicMock()
        bot_result.scalars.return_value.all.return_value = [mock_bot]
        mock_db.execute = AsyncMock(return_value=bot_result)

        monitor = TradingPairMonitor()
        # Only ETH-BTC and SOL-BTC are available
        available = {"ETH-BTC", "SOL-BTC"}
        monitor._btc_pairs = {"ETH-BTC", "SOL-BTC"}
        monitor._usd_pairs = set()

        with patch.object(monitor, 'get_available_products', new_callable=AsyncMock, return_value=available):
            results = await monitor.check_and_sync_pairs()

        assert results["pairs_removed"] == 1
        assert "DELISTED-BTC" not in mock_bot.product_ids
        assert "ETH-BTC" in mock_bot.product_ids
        assert "SOL-BTC" in mock_bot.product_ids
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch('app.services.delisted_pair_monitor.async_session_maker')
    async def test_new_pair_added_when_auto_add_enabled(self, mock_session_maker):
        """Happy path: new pair added when auto_add_new_pairs is enabled."""
        mock_db = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_bot = MagicMock()
        mock_bot.id = 1
        mock_bot.name = "TestBot"
        mock_bot.product_ids = ["ETH-BTC"]
        mock_bot.strategy_config = {"auto_add_new_pairs": True}
        bot_result = MagicMock()
        bot_result.scalars.return_value.all.return_value = [mock_bot]
        mock_db.execute = AsyncMock(return_value=bot_result)

        monitor = TradingPairMonitor()
        available = {"ETH-BTC", "SOL-BTC", "ADA-BTC"}
        monitor._btc_pairs = {"ETH-BTC", "SOL-BTC", "ADA-BTC"}
        monitor._usd_pairs = set()

        with patch.object(monitor, 'get_available_products', new_callable=AsyncMock, return_value=available):
            results = await monitor.check_and_sync_pairs()

        assert results["pairs_added"] == 2
        assert "SOL-BTC" in mock_bot.product_ids
        assert "ADA-BTC" in mock_bot.product_ids
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch('app.services.delisted_pair_monitor.async_session_maker')
    async def test_no_changes_needed(self, mock_session_maker):
        """Edge case: all pairs match, no changes needed."""
        mock_db = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_bot = MagicMock()
        mock_bot.id = 1
        mock_bot.name = "TestBot"
        mock_bot.product_ids = ["ETH-BTC", "SOL-BTC"]
        mock_bot.strategy_config = {"auto_add_new_pairs": False}
        bot_result = MagicMock()
        bot_result.scalars.return_value.all.return_value = [mock_bot]
        mock_db.execute = AsyncMock(return_value=bot_result)

        monitor = TradingPairMonitor()
        available = {"ETH-BTC", "SOL-BTC"}
        monitor._btc_pairs = {"ETH-BTC", "SOL-BTC"}
        monitor._usd_pairs = set()

        with patch.object(monitor, 'get_available_products', new_callable=AsyncMock, return_value=available):
            results = await monitor.check_and_sync_pairs()

        assert results["pairs_removed"] == 0
        assert results["pairs_added"] == 0
        mock_db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# EXCLUDED_PAIRS tests
# ---------------------------------------------------------------------------

class TestExcludedPairs:
    """Tests for the EXCLUDED_PAIRS constant."""

    def test_stablecoins_excluded(self):
        """Happy path: major stablecoins are in the excluded set."""
        assert "USDC-USD" in EXCLUDED_PAIRS
        assert "USDT-USD" in EXCLUDED_PAIRS
        assert "DAI-USD" in EXCLUDED_PAIRS

    def test_wrapped_tokens_excluded(self):
        """Happy path: wrapped token pairs are excluded."""
        assert "WBTC-BTC" in EXCLUDED_PAIRS
        assert "CBBTC-BTC" in EXCLUDED_PAIRS

    def test_normal_pairs_not_excluded(self):
        """Edge case: normal trading pairs should not be in excluded set."""
        assert "ETH-BTC" not in EXCLUDED_PAIRS
        assert "SOL-USD" not in EXCLUDED_PAIRS
        assert "BTC-USD" not in EXCLUDED_PAIRS
