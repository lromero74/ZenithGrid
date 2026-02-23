"""
Tests for backend/app/services/perps_monitor.py

Tests the PerpsMonitor service that syncs open perpetual futures
positions with exchange state, detects TP/SL bracket fills, and
updates unrealized PnL.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.perps_monitor import PerpsMonitor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_position(**overrides):
    """Create a mock Position with sensible defaults for perps."""
    pos = MagicMock()
    pos.id = overrides.get("id", 1)
    pos.account_id = overrides.get("account_id", 1)
    pos.user_id = overrides.get("user_id", 1)
    pos.product_id = overrides.get("product_id", "BTC-PERP-INTX")
    pos.product_type = overrides.get("product_type", "future")
    pos.status = overrides.get("status", "open")
    pos.direction = overrides.get("direction", "long")
    pos.total_base_acquired = overrides.get("total_base_acquired", 0.1)
    pos.total_quote_spent = overrides.get("total_quote_spent", 5000.0)
    pos.average_buy_price = overrides.get("average_buy_price", 50000.0)
    pos.short_total_sold_base = overrides.get("short_total_sold_base", None)
    pos.short_total_sold_quote = overrides.get("short_total_sold_quote", None)
    pos.short_average_sell_price = overrides.get("short_average_sell_price", None)
    pos.funding_fees_total = overrides.get("funding_fees_total", 0.0)
    pos.tp_order_id = overrides.get("tp_order_id", "tp-order-1")
    pos.sl_order_id = overrides.get("sl_order_id", "sl-order-1")
    pos.unrealized_pnl = overrides.get("unrealized_pnl", None)
    pos.liquidation_price = overrides.get("liquidation_price", None)
    pos.bot = overrides.get("bot", MagicMock())
    return pos


def _make_account(**overrides):
    """Create a mock Account."""
    acct = MagicMock()
    acct.id = overrides.get("id", 1)
    acct.perps_portfolio_uuid = overrides.get("perps_portfolio_uuid", "portfolio-uuid-1")
    return acct


# ---------------------------------------------------------------------------
# PerpsMonitor.__init__ / lifecycle tests
# ---------------------------------------------------------------------------

class TestPerpsMonitorInit:
    """Tests for PerpsMonitor initialization and lifecycle."""

    def test_init_defaults(self):
        """Happy path: monitor initializes with expected defaults."""
        monitor = PerpsMonitor()
        assert monitor.interval_seconds == 60
        assert monitor.running is False
        assert monitor.task is None

    def test_init_custom_interval(self):
        """Happy path: custom interval."""
        monitor = PerpsMonitor(interval_seconds=30)
        assert monitor.interval_seconds == 30

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        """Edge case: calling start when already running does nothing."""
        monitor = PerpsMonitor()
        monitor.running = True
        old_task = monitor.task
        await monitor.start()
        assert monitor.task is old_task  # Should not have changed


# ---------------------------------------------------------------------------
# _sync_single_position tests
# ---------------------------------------------------------------------------

class TestSyncSinglePosition:
    """Tests for PerpsMonitor._sync_single_position()."""

    @pytest.mark.asyncio
    async def test_position_on_exchange_updates_metrics(self):
        """Happy path: position found on exchange, metrics updated."""
        monitor = PerpsMonitor()
        db = AsyncMock()
        coinbase_client = AsyncMock()

        position = _make_position()
        exchange_pos_map = {
            "BTC-PERP-INTX": {
                "unrealized_pnl": 150.0,
                "liquidation_price": 42000.0,
            }
        }

        await monitor._sync_single_position(db, position, exchange_pos_map, coinbase_client)

        assert position.unrealized_pnl == pytest.approx(150.0)
        assert position.liquidation_price == pytest.approx(42000.0)

    @pytest.mark.asyncio
    async def test_position_on_exchange_no_liquidation_price(self):
        """Edge case: exchange returns no liquidation_price."""
        monitor = PerpsMonitor()
        db = AsyncMock()
        coinbase_client = AsyncMock()

        position = _make_position(liquidation_price=45000.0)
        exchange_pos_map = {
            "BTC-PERP-INTX": {
                "unrealized_pnl": -50.0,
                "liquidation_price": None,
            }
        }

        await monitor._sync_single_position(db, position, exchange_pos_map, coinbase_client)

        assert position.unrealized_pnl == pytest.approx(-50.0)
        # liquidation_price should not be updated when None
        assert position.liquidation_price == pytest.approx(45000.0)

    @pytest.mark.asyncio
    async def test_position_not_on_exchange_checks_bracket_fill(self):
        """Happy path: position not on exchange, checks for bracket fills."""
        monitor = PerpsMonitor()
        db = AsyncMock()
        coinbase_client = AsyncMock()

        position = _make_position()
        exchange_pos_map = {}  # Position not on exchange

        with patch.object(monitor, '_check_bracket_fill', new_callable=AsyncMock) as mock_check:
            await monitor._sync_single_position(db, position, exchange_pos_map, coinbase_client)
            mock_check.assert_awaited_once_with(db, position, coinbase_client)


# ---------------------------------------------------------------------------
# _check_bracket_fill tests
# ---------------------------------------------------------------------------

class TestCheckBracketFill:
    """Tests for PerpsMonitor._check_bracket_fill()."""

    @pytest.mark.asyncio
    @patch('app.services.perps_monitor.ws_manager', create=True)
    async def test_tp_filled_closes_long_position(self, mock_ws):
        """Happy path: TP order filled, long position closed with profit."""
        monitor = PerpsMonitor()
        db = AsyncMock()
        coinbase_client = AsyncMock()
        coinbase_client.get_order = AsyncMock(return_value={
            "status": "FILLED",
            "average_filled_price": "55000.00",
        })

        position = _make_position(
            direction="long",
            total_base_acquired=0.1,
            total_quote_spent=5000.0,
            average_buy_price=50000.0,
            funding_fees_total=10.0,
            tp_order_id="tp-order-1",
            sl_order_id="sl-order-1",
        )

        with patch('app.services.perps_monitor.ws_manager', create=True) as mock_ws_mod:
            mock_ws_mod.broadcast = AsyncMock()
            await monitor._check_bracket_fill(db, position, coinbase_client)

        assert position.status == "closed"
        assert position.exit_reason == "tp_hit"
        assert position.sell_price == pytest.approx(55000.0)
        # Profit: (55000 - 50000) * 0.1 - 10 = 500 - 10 = 490
        assert position.profit_quote == pytest.approx(490.0)
        assert position.tp_order_id is None
        assert position.sl_order_id is None
        assert position.unrealized_pnl is None

    @pytest.mark.asyncio
    @patch('app.services.perps_monitor.ws_manager', create=True)
    async def test_sl_filled_closes_short_position(self, mock_ws):
        """Happy path: SL order filled on short position."""
        monitor = PerpsMonitor()
        db = AsyncMock()
        coinbase_client = AsyncMock()

        # TP not filled, SL is filled
        coinbase_client.get_order = AsyncMock(side_effect=[
            {"status": "OPEN", "average_filled_price": "0"},  # TP not filled
            {"status": "FILLED", "average_filled_price": "52000.00"},  # SL filled
        ])

        position = _make_position(
            direction="short",
            short_total_sold_base=0.1,
            short_total_sold_quote=5500.0,
            short_average_sell_price=55000.0,
            funding_fees_total=5.0,
            tp_order_id="tp-order-short",
            sl_order_id="sl-order-short",
        )

        with patch('app.services.perps_monitor.ws_manager', create=True) as mock_ws_mod:
            mock_ws_mod.broadcast = AsyncMock()
            await monitor._check_bracket_fill(db, position, coinbase_client)

        assert position.status == "closed"
        assert position.exit_reason == "sl_hit"
        assert position.sell_price == pytest.approx(52000.0)
        # Short profit: (55000 - 52000) * 0.1 - 5 = 300 - 5 = 295
        assert position.profit_quote == pytest.approx(295.0)

    @pytest.mark.asyncio
    async def test_no_bracket_orders_logs_warning(self):
        """Edge case: position has no TP/SL order IDs."""
        monitor = PerpsMonitor()
        db = AsyncMock()
        coinbase_client = AsyncMock()

        position = _make_position(tp_order_id=None, sl_order_id=None)

        await monitor._check_bracket_fill(db, position, coinbase_client)

        # Should not call get_order
        coinbase_client.get_order.assert_not_awaited()
        # Position should remain open
        assert position.status == "open"

    @pytest.mark.asyncio
    async def test_no_bracket_fill_detected(self):
        """Edge case: neither TP nor SL are filled yet."""
        monitor = PerpsMonitor()
        db = AsyncMock()
        coinbase_client = AsyncMock()
        coinbase_client.get_order = AsyncMock(return_value={
            "status": "OPEN",
            "average_filled_price": "0",
        })

        position = _make_position()

        await monitor._check_bracket_fill(db, position, coinbase_client)

        # Position should remain open
        assert position.status == "open"

    @pytest.mark.asyncio
    async def test_bracket_check_handles_api_error(self):
        """Failure: API error when checking bracket order."""
        monitor = PerpsMonitor()
        db = AsyncMock()
        coinbase_client = AsyncMock()
        coinbase_client.get_order = AsyncMock(side_effect=Exception("API timeout"))

        position = _make_position()

        # Should not raise
        await monitor._check_bracket_fill(db, position, coinbase_client)
        assert position.status == "open"


# ---------------------------------------------------------------------------
# _sync_account_positions tests
# ---------------------------------------------------------------------------

class TestSyncAccountPositions:
    """Tests for PerpsMonitor._sync_account_positions()."""

    @pytest.mark.asyncio
    @patch('app.services.exchange_service.get_exchange_client_for_account')
    async def test_no_portfolio_uuid_skips(self, mock_get_client):
        """Edge case: account has no perps_portfolio_uuid."""
        monitor = PerpsMonitor()
        db = AsyncMock()

        account = _make_account(perps_portfolio_uuid=None)
        db.get = AsyncMock(return_value=account)

        positions = [_make_position()]

        await monitor._sync_account_positions(db, 1, positions)

        mock_get_client.assert_not_awaited()

    @pytest.mark.asyncio
    @patch('app.services.exchange_service.get_exchange_client_for_account')
    async def test_no_exchange_client_returns(self, mock_get_client):
        """Failure: exchange client not available."""
        monitor = PerpsMonitor()
        db = AsyncMock()

        account = _make_account()
        db.get = AsyncMock(return_value=account)
        mock_get_client.return_value = None

        positions = [_make_position()]

        # Should not raise
        await monitor._sync_account_positions(db, 1, positions)

    @pytest.mark.asyncio
    @patch('app.services.exchange_service.get_exchange_client_for_account')
    async def test_successful_sync(self, mock_get_client):
        """Happy path: positions synced with exchange data."""
        monitor = PerpsMonitor()
        db = AsyncMock()

        account = _make_account()
        db.get = AsyncMock(return_value=account)

        # Mock exchange client with _client attribute
        mock_coinbase = AsyncMock()
        mock_coinbase.list_perps_positions = AsyncMock(return_value=[
            {"symbol": "BTC-PERP-INTX", "unrealized_pnl": 200.0, "liquidation_price": 40000.0},
        ])
        mock_exchange = MagicMock()
        mock_exchange._client = mock_coinbase
        mock_get_client.return_value = mock_exchange

        position = _make_position()
        positions = [position]

        with patch.object(monitor, '_sync_single_position', new_callable=AsyncMock) as mock_sync:
            await monitor._sync_account_positions(db, 1, positions)
            mock_sync.assert_awaited_once()
