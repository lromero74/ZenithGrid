"""
Tests for backend/app/services/auto_buy_monitor.py

Tests the AutoBuyMonitor service that automatically converts stablecoins
to BTC when balances exceed configured minimums.
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.auto_buy_monitor import AutoBuyMonitor, AutoBuyPendingOrder


# ---------------------------------------------------------------------------
# AutoBuyPendingOrder dataclass tests
# ---------------------------------------------------------------------------

class TestAutoBuyPendingOrder:
    """Tests for AutoBuyPendingOrder dataclass."""

    def test_create_pending_order_with_valid_fields(self):
        """Happy path: dataclass stores all fields correctly."""
        now = datetime.utcnow()
        order = AutoBuyPendingOrder(
            order_id="order-123",
            account_id=1,
            product_id="BTC-USD",
            side="BUY",
            size=0.001,
            price=50000.0,
            placed_at=now,
        )
        assert order.order_id == "order-123"
        assert order.account_id == 1
        assert order.product_id == "BTC-USD"
        assert order.side == "BUY"
        assert order.size == pytest.approx(0.001)
        assert order.price == pytest.approx(50000.0)
        assert order.placed_at == now


# ---------------------------------------------------------------------------
# AutoBuyMonitor.__init__ and start/stop tests
# ---------------------------------------------------------------------------

class TestAutoBuyMonitorInit:
    """Tests for AutoBuyMonitor initialization and lifecycle."""

    def test_init_defaults(self):
        """Happy path: monitor initializes with expected defaults."""
        monitor = AutoBuyMonitor()
        assert monitor.running is False
        assert monitor.task is None
        assert monitor._account_timers == {}
        assert monitor._pending_orders == {}

    @pytest.mark.asyncio
    async def test_start_sets_running(self):
        """Happy path: start sets running flag and creates task."""
        monitor = AutoBuyMonitor()
        with patch.object(monitor, '_monitor_loop', new_callable=AsyncMock):
            await monitor.start()
            assert monitor.running is True
            assert monitor.task is not None
            # Clean up
            monitor.running = False
            monitor.task.cancel()
            try:
                await monitor.task
            except (Exception, asyncio.CancelledError):
                pass

    @pytest.mark.asyncio
    async def test_start_idempotent_when_already_running(self):
        """Edge case: calling start when already running does not create a second task."""
        monitor = AutoBuyMonitor()
        monitor.running = True
        monitor.task = MagicMock()
        await monitor.start()
        # Should not have replaced the existing task
        assert isinstance(monitor.task, MagicMock)


# ---------------------------------------------------------------------------
# _should_check_account tests
# ---------------------------------------------------------------------------

class TestShouldCheckAccount:
    """Tests for AutoBuyMonitor._should_check_account()."""

    def test_returns_true_for_never_checked_account(self):
        """Happy path: account never checked before returns True."""
        monitor = AutoBuyMonitor()
        account = MagicMock()
        account.id = 1
        account.auto_buy_check_interval_minutes = 5

        result = monitor._should_check_account(account)
        assert result is True

    def test_returns_false_when_interval_not_elapsed(self):
        """Edge case: account checked recently, interval not elapsed."""
        monitor = AutoBuyMonitor()
        account = MagicMock()
        account.id = 1
        account.auto_buy_check_interval_minutes = 5

        # Set last check to 1 minute ago
        monitor._account_timers[1] = datetime.utcnow() - timedelta(minutes=1)

        result = monitor._should_check_account(account)
        assert result is False

    def test_returns_true_when_interval_elapsed(self):
        """Happy path: interval has passed, should check again."""
        monitor = AutoBuyMonitor()
        account = MagicMock()
        account.id = 1
        account.auto_buy_check_interval_minutes = 5

        # Set last check to 6 minutes ago
        monitor._account_timers[1] = datetime.utcnow() - timedelta(minutes=6)

        result = monitor._should_check_account(account)
        assert result is True

    def test_defaults_to_5_minute_interval_when_none(self):
        """Edge case: auto_buy_check_interval_minutes is None, defaults to 5."""
        monitor = AutoBuyMonitor()
        account = MagicMock()
        account.id = 1
        account.auto_buy_check_interval_minutes = None

        # Set last check to 4 minutes ago (less than default 5)
        monitor._account_timers[1] = datetime.utcnow() - timedelta(minutes=4)

        result = monitor._should_check_account(account)
        assert result is False


# ---------------------------------------------------------------------------
# _check_and_buy tests
# ---------------------------------------------------------------------------

class TestCheckAndBuy:
    """Tests for AutoBuyMonitor._check_and_buy()."""

    @pytest.mark.asyncio
    async def test_market_buy_when_balance_exceeds_minimum(self, db_session):
        """Happy path: market buy triggered when available > min after reservations."""
        monitor = AutoBuyMonitor()

        client = AsyncMock()
        client.get_balance = AsyncMock(return_value={"available": "500.00"})
        client.buy_with_usd = AsyncMock(return_value={
            "success_response": {"order_id": "mkt-order-1"},
            "error_response": {},
        })

        account = MagicMock()
        account.id = 1
        account.name = "TestAcct"
        account.auto_buy_order_type = "market"

        with patch.object(monitor, '_calculate_reserved_usd', new_callable=AsyncMock, return_value=0.0):
            await monitor._check_and_buy(client, account, "USD", 10.0, "BTC-USD", db_session)

        client.buy_with_usd.assert_awaited_once()
        # Spend amount should be 99% of available = 500 * 0.99 = 495.0
        args = client.buy_with_usd.call_args
        assert args[0][0] == pytest.approx(495.0)
        assert args[0][1] == "BTC-USD"

    @pytest.mark.asyncio
    async def test_no_buy_when_available_below_minimum(self, db_session):
        """Edge case: balance below minimum after reservations, no order placed."""
        monitor = AutoBuyMonitor()

        client = AsyncMock()
        client.get_balance = AsyncMock(return_value={"available": "100.00"})

        account = MagicMock()
        account.id = 1
        account.name = "TestAcct"
        account.auto_buy_order_type = "market"

        # Reserve 95 of the 100, leaving only 5 which is below min of 10
        with patch.object(monitor, '_calculate_reserved_usd', new_callable=AsyncMock, return_value=95.0):
            await monitor._check_and_buy(client, account, "USD", 10.0, "BTC-USD", db_session)

        client.buy_with_usd.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_limit_buy_when_order_type_is_limit(self, db_session):
        """Happy path: limit order placed at current market price."""
        monitor = AutoBuyMonitor()

        client = AsyncMock()
        client.get_balance = AsyncMock(return_value={"available": "1000.00"})
        client.get_product = AsyncMock(return_value={"price": "50000.00"})
        client.create_limit_order = AsyncMock(return_value={
            "success_response": {"order_id": "lmt-order-1"},
            "error_response": {},
        })

        account = MagicMock()
        account.id = 1
        account.name = "TestAcct"
        account.auto_buy_order_type = "limit"

        with patch.object(monitor, '_calculate_reserved_usd', new_callable=AsyncMock, return_value=0.0):
            await monitor._check_and_buy(client, account, "USD", 10.0, "BTC-USD", db_session)

        client.create_limit_order.assert_awaited_once()
        # Verify pending order tracked
        assert len(monitor._pending_orders) == 1
        pending = list(monitor._pending_orders.values())[0]
        assert pending.product_id == "BTC-USD"
        assert pending.price == pytest.approx(50000.0)

    @pytest.mark.asyncio
    async def test_market_buy_failure_logs_error(self, db_session):
        """Failure: market order returns no order_id, should not raise."""
        monitor = AutoBuyMonitor()

        client = AsyncMock()
        client.get_balance = AsyncMock(return_value={"available": "500.00"})
        client.buy_with_usd = AsyncMock(return_value={
            "success_response": {},
            "error_response": {"message": "Insufficient funds"},
        })

        account = MagicMock()
        account.id = 1
        account.name = "TestAcct"
        account.auto_buy_order_type = "market"

        with patch.object(monitor, '_calculate_reserved_usd', new_callable=AsyncMock, return_value=0.0):
            # Should not raise - errors are caught and logged
            await monitor._check_and_buy(client, account, "USD", 10.0, "BTC-USD", db_session)

    @pytest.mark.asyncio
    async def test_limit_buy_zero_price_returns_early(self, db_session):
        """Edge case: exchange returns 0 price for product, should skip order."""
        monitor = AutoBuyMonitor()

        client = AsyncMock()
        client.get_balance = AsyncMock(return_value={"available": "500.00"})
        client.get_product = AsyncMock(return_value={"price": "0"})

        account = MagicMock()
        account.id = 1
        account.name = "TestAcct"
        account.auto_buy_order_type = "limit"

        with patch.object(monitor, '_calculate_reserved_usd', new_callable=AsyncMock, return_value=0.0):
            await monitor._check_and_buy(client, account, "USD", 10.0, "BTC-USD", db_session)

        client.create_limit_order.assert_not_awaited()


# ---------------------------------------------------------------------------
# _check_pending_orders / _reprice_order tests
# ---------------------------------------------------------------------------

class TestCheckPendingOrders:
    """Tests for AutoBuyMonitor._check_pending_orders()."""

    @pytest.mark.asyncio
    async def test_no_pending_orders_returns_immediately(self):
        """Edge case: no pending orders, should return without DB access."""
        monitor = AutoBuyMonitor()
        # Should not raise or access DB
        await monitor._check_pending_orders()

    @pytest.mark.asyncio
    @patch('app.services.auto_buy_monitor.async_session_maker')
    @patch('app.services.auto_buy_monitor.get_exchange_client_for_account')
    async def test_reprice_order_after_timeout(self, mock_get_client, mock_session_maker):
        """Happy path: order older than 2 minutes gets cancelled and replaced."""
        monitor = AutoBuyMonitor()

        # Add a pending order that was placed 3 minutes ago
        old_order = AutoBuyPendingOrder(
            order_id="old-order-1",
            account_id=1,
            product_id="BTC-USD",
            side="BUY",
            size=0.01,
            price=49000.0,
            placed_at=datetime.utcnow() - timedelta(minutes=3),
        )
        monitor._pending_orders["old-order-1"] = old_order

        # Mock exchange client
        mock_client = AsyncMock()
        mock_client.get_order = AsyncMock(return_value={"status": "OPEN"})
        mock_client.cancel_order = AsyncMock(return_value=True)
        mock_client.get_product = AsyncMock(return_value={"price": "51000.00"})
        mock_client.create_limit_order = AsyncMock(return_value={
            "success_response": {"order_id": "new-order-1"},
            "error_response": {},
        })
        mock_get_client.return_value = mock_client

        # Mock DB session
        mock_db = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        await monitor._check_pending_orders()

        # Old order should be removed
        assert "old-order-1" not in monitor._pending_orders
        # New order should be tracked
        assert "new-order-1" in monitor._pending_orders
        new_pending = monitor._pending_orders["new-order-1"]
        assert new_pending.price == pytest.approx(51000.0)

    @pytest.mark.asyncio
    @patch('app.services.auto_buy_monitor.async_session_maker')
    @patch('app.services.auto_buy_monitor.get_exchange_client_for_account')
    async def test_reprice_skipped_for_already_filled_order(self, mock_get_client, mock_session_maker):
        """Edge case: order already filled on exchange, skip repricing."""
        monitor = AutoBuyMonitor()

        old_order = AutoBuyPendingOrder(
            order_id="filled-order",
            account_id=1,
            product_id="BTC-USD",
            side="BUY",
            size=0.01,
            price=49000.0,
            placed_at=datetime.utcnow() - timedelta(minutes=3),
        )
        monitor._pending_orders["filled-order"] = old_order

        mock_client = AsyncMock()
        mock_client.get_order = AsyncMock(return_value={"status": "FILLED"})
        mock_get_client.return_value = mock_client

        mock_db = AsyncMock()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)

        await monitor._check_pending_orders()

        # Order should be removed (processed) but cancel should NOT have been called
        assert "filled-order" not in monitor._pending_orders
        mock_client.cancel_order.assert_not_awaited()


# ---------------------------------------------------------------------------
# _process_account tests
# ---------------------------------------------------------------------------

class TestProcessAccount:
    """Tests for AutoBuyMonitor._process_account()."""

    @pytest.mark.asyncio
    @patch('app.services.auto_buy_monitor.get_exchange_client_for_account')
    async def test_no_client_returns_early(self, mock_get_client, db_session):
        """Failure: no exchange client available, should return without error."""
        monitor = AutoBuyMonitor()
        mock_get_client.return_value = None

        account = MagicMock()
        account.id = 1
        account.name = "TestAcct"
        account.auto_buy_usd_enabled = True
        account.auto_buy_usd_min = 10.0
        account.auto_buy_usdc_enabled = False
        account.auto_buy_usdt_enabled = False

        await monitor._process_account(account, db_session)

        # Timer should NOT be updated when client is missing
        assert 1 not in monitor._account_timers

    @pytest.mark.asyncio
    @patch('app.services.auto_buy_monitor.get_exchange_client_for_account')
    async def test_processes_enabled_stablecoins_only(self, mock_get_client, db_session):
        """Happy path: only processes stablecoins that are enabled."""
        monitor = AutoBuyMonitor()
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        account = MagicMock()
        account.id = 2
        account.name = "TestAcct"
        account.auto_buy_usd_enabled = True
        account.auto_buy_usd_min = 10.0
        account.auto_buy_usdc_enabled = False
        account.auto_buy_usdt_enabled = True
        account.auto_buy_usdt_min = 20.0

        with patch.object(monitor, '_check_and_buy', new_callable=AsyncMock) as mock_check:
            await monitor._process_account(account, db_session)

        # Should have been called for USD and USDT but not USDC
        assert mock_check.await_count == 2
        calls = mock_check.call_args_list
        # First call: USD
        assert calls[0][1].get('currency') or calls[0][0][2] == "USD"
        # Second call: USDT
        assert calls[1][1].get('currency') or calls[1][0][2] == "USDT"

        # Timer should be updated
        assert 2 in monitor._account_timers

    @pytest.mark.asyncio
    @patch('app.services.auto_buy_monitor.get_exchange_client_for_account')
    async def test_exception_in_process_does_not_propagate(self, mock_get_client, db_session):
        """Failure: exception during processing is caught and logged."""
        monitor = AutoBuyMonitor()
        mock_get_client.side_effect = Exception("API connection failed")

        account = MagicMock()
        account.id = 3
        account.name = "TestAcct"

        # Should not raise
        await monitor._process_account(account, db_session)
