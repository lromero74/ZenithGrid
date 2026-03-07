"""
Tests for backend/app/services/rebalance_monitor.py

Tests allocation calculation, drift detection, trade planning,
and the rebalance monitor lifecycle.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# calculate_current_allocations
# ---------------------------------------------------------------------------


class TestCalculateCurrentAllocations:
    """Tests for calculate_current_allocations()."""

    def test_happy_path_three_currencies(self):
        """Happy path: USD/BTC/ETH balances converted to allocation percentages."""
        from app.services.rebalance_monitor import calculate_current_allocations

        # free_balances: {currency: amount}, prices: {pair: price}
        free_balances = {"USD": 5000.0, "BTC": 0.05, "ETH": 2.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0}

        result = calculate_current_allocations(free_balances, prices)

        # USD: 5000, BTC: 0.05 * 100000 = 5000, ETH: 2 * 2500 = 5000
        # Total = 15000
        assert result["usd_pct"] == pytest.approx(33.33, rel=0.01)
        assert result["btc_pct"] == pytest.approx(33.33, rel=0.01)
        assert result["eth_pct"] == pytest.approx(33.33, rel=0.01)
        assert result["total_value_usd"] == pytest.approx(15000.0)

    def test_zero_total_returns_zero_pcts(self):
        """Edge case: all zero balances returns 0% for each."""
        from app.services.rebalance_monitor import calculate_current_allocations

        free_balances = {"USD": 0.0, "BTC": 0.0, "ETH": 0.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0}

        result = calculate_current_allocations(free_balances, prices)

        assert result["usd_pct"] == 0.0
        assert result["btc_pct"] == 0.0
        assert result["eth_pct"] == 0.0
        assert result["total_value_usd"] == 0.0

    def test_single_currency_100_pct(self):
        """Edge case: only USD held returns 100% USD."""
        from app.services.rebalance_monitor import calculate_current_allocations

        free_balances = {"USD": 10000.0, "BTC": 0.0, "ETH": 0.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0}

        result = calculate_current_allocations(free_balances, prices)

        assert result["usd_pct"] == pytest.approx(100.0)
        assert result["btc_pct"] == 0.0
        assert result["eth_pct"] == 0.0


# ---------------------------------------------------------------------------
# needs_rebalance
# ---------------------------------------------------------------------------


class TestNeedsRebalance:
    """Tests for needs_rebalance()."""

    def test_within_threshold_returns_false(self):
        """Happy path: all currencies within ±5% drift — no rebalance needed."""
        from app.services.rebalance_monitor import needs_rebalance

        current = {"usd_pct": 36.0, "btc_pct": 31.0, "eth_pct": 33.0}
        targets = {"usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0}

        assert needs_rebalance(current, targets, threshold=5.0) is False

    def test_exceeds_threshold_returns_true(self):
        """Happy path: one currency drifts beyond ±5% — rebalance needed."""
        from app.services.rebalance_monitor import needs_rebalance

        current = {"usd_pct": 45.0, "btc_pct": 30.0, "eth_pct": 25.0}
        targets = {"usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0}

        assert needs_rebalance(current, targets, threshold=5.0) is True

    def test_exact_match_returns_false(self):
        """Edge case: allocations exactly match targets."""
        from app.services.rebalance_monitor import needs_rebalance

        current = {"usd_pct": 50.0, "btc_pct": 30.0, "eth_pct": 20.0}
        targets = {"usd_pct": 50.0, "btc_pct": 30.0, "eth_pct": 20.0}

        assert needs_rebalance(current, targets, threshold=5.0) is False

    def test_boundary_at_threshold_returns_false(self):
        """Edge case: drift exactly at threshold — no rebalance (must exceed)."""
        from app.services.rebalance_monitor import needs_rebalance

        current = {"usd_pct": 39.0, "btc_pct": 33.0, "eth_pct": 28.0}
        targets = {"usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0}

        # USD drift = 5.0 exactly, ETH drift = -5.0 exactly
        assert needs_rebalance(current, targets, threshold=5.0) is False


# ---------------------------------------------------------------------------
# plan_trades
# ---------------------------------------------------------------------------


class TestPlanTrades:
    """Tests for plan_trades()."""

    def test_sell_overweight_buy_underweight(self):
        """Happy path: sells overweight currency and buys underweight."""
        from app.services.rebalance_monitor import plan_trades

        free_balances = {"USD": 10000.0, "BTC": 0.0, "ETH": 0.0}
        targets = {"usd_pct": 50.0, "btc_pct": 30.0, "eth_pct": 20.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0}

        trades = plan_trades(free_balances, targets, prices)

        # Total = $10000. Target: USD=5000, BTC=3000, ETH=2000
        # Need to sell $5000 USD and buy $3000 BTC + $2000 ETH
        assert len(trades) == 2

        # Find BTC and ETH trades
        btc_trade = next(t for t in trades if t["to_currency"] == "BTC")
        eth_trade = next(t for t in trades if t["to_currency"] == "ETH")

        assert btc_trade["from_currency"] == "USD"
        assert btc_trade["usd_amount"] == pytest.approx(3000.0)
        assert eth_trade["from_currency"] == "USD"
        assert eth_trade["usd_amount"] == pytest.approx(2000.0)

    def test_respects_min_trade_size(self):
        """Edge case: trades below $10 minimum are skipped."""
        from app.services.rebalance_monitor import plan_trades

        # Small imbalance that would produce < $10 trades
        free_balances = {"USD": 100.0, "BTC": 0.00045, "ETH": 0.018}
        targets = {"usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0}

        # USD: 100, BTC: 45, ETH: 45 => total=190
        # Target: USD=64.6, BTC=62.7, ETH=62.7
        # USD overweight by 35.4, BTC underweight by 17.7, ETH underweight by 17.7
        trades = plan_trades(free_balances, targets, prices)

        # All trades >= $10
        for trade in trades:
            assert trade["usd_amount"] >= 10.0

    def test_skips_when_no_free_balance(self):
        """Edge case: zero free balances produces no trades."""
        from app.services.rebalance_monitor import plan_trades

        free_balances = {"USD": 0.0, "BTC": 0.0, "ETH": 0.0}
        targets = {"usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0}

        trades = plan_trades(free_balances, targets, prices)
        assert trades == []

    def test_three_way_rebalance(self):
        """Happy path: rebalance among all three currencies."""
        from app.services.rebalance_monitor import plan_trades

        # Heavy BTC, light USD and ETH
        free_balances = {"USD": 1000.0, "BTC": 0.08, "ETH": 0.4}
        targets = {"usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0}

        # USD: 1000, BTC: 8000, ETH: 1000 => total=10000
        # Target: USD=3400, BTC=3300, ETH=3300
        # BTC overweight by 4700
        # USD underweight by 2400
        # ETH underweight by 2300
        trades = plan_trades(free_balances, targets, prices)

        # Should sell BTC and buy USD + ETH
        assert len(trades) >= 1
        btc_sells = [t for t in trades if t["from_currency"] == "BTC"]
        assert len(btc_sells) > 0


# ---------------------------------------------------------------------------
# RebalanceMonitor._process_account (integration-level)
# ---------------------------------------------------------------------------


class TestRebalanceMonitorProcess:
    """Tests for the monitor's account processing logic."""

    @pytest.mark.asyncio
    async def test_disabled_account_skipped(self):
        """Failure: account with rebalance_enabled=False is not processed."""
        from app.services.rebalance_monitor import RebalanceMonitor

        monitor = RebalanceMonitor()

        account = MagicMock()
        account.id = 1
        account.rebalance_enabled = False

        db = AsyncMock()

        # Mock the query to return an account with rebalance disabled
        with patch(
            "app.services.rebalance_monitor.get_exchange_client_for_account"
        ) as mock_get_client:
            await monitor._process_account(account, db)
            # Should not attempt to get exchange client
            mock_get_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_account_executes_trades(self):
        """Happy path: processes account and executes planned trades."""
        from app.services.rebalance_monitor import RebalanceMonitor

        monitor = RebalanceMonitor()

        account = MagicMock()
        account.id = 1
        account.name = "Test Account"
        account.rebalance_enabled = True
        account.rebalance_target_usd_pct = 50.0
        account.rebalance_target_btc_pct = 30.0
        account.rebalance_target_eth_pct = 20.0
        account.rebalance_drift_threshold_pct = 5.0

        db = AsyncMock()

        mock_client = AsyncMock()
        # Aggregate values: all USD (drift detected via aggregate)
        mock_client.calculate_aggregate_quote_value = AsyncMock(
            side_effect=lambda c: 10000.0 if c == "USD" else 0.0
        )
        # Free balances: all USD (used for trade planning)
        mock_client.get_usd_balance = AsyncMock(return_value=10000.0)
        mock_client.get_btc_balance = AsyncMock(return_value=0.0)
        mock_client.get_eth_balance = AsyncMock(return_value=0.0)
        mock_client.get_current_price = AsyncMock(
            side_effect=lambda p: 100000.0 if p == "BTC-USD" else 2500.0
        )
        mock_client.buy_with_usd = AsyncMock(return_value={
            "success_response": {"order_id": "test-123"}
        })

        with patch(
            "app.services.rebalance_monitor.get_exchange_client_for_account",
            return_value=mock_client
        ):
            await monitor._process_account(account, db)

        # Should have placed orders (buy BTC and/or ETH)
        assert mock_client.buy_with_usd.call_count >= 1

    @pytest.mark.asyncio
    async def test_no_trades_within_threshold(self):
        """Edge case: balanced account within threshold triggers no trades."""
        from app.services.rebalance_monitor import RebalanceMonitor

        monitor = RebalanceMonitor()

        account = MagicMock()
        account.id = 1
        account.name = "Balanced Account"
        account.rebalance_enabled = True
        account.rebalance_target_usd_pct = 34.0
        account.rebalance_target_btc_pct = 33.0
        account.rebalance_target_eth_pct = 33.0
        account.rebalance_drift_threshold_pct = 5.0

        db = AsyncMock()

        mock_client = AsyncMock()
        # Aggregate values roughly balanced
        mock_client.calculate_aggregate_quote_value = AsyncMock(
            side_effect=lambda c: (
                3400.0 if c == "USD"
                else 0.033 if c == "BTC"
                else 1.32
            )
        )
        mock_client.get_current_price = AsyncMock(
            side_effect=lambda p: 100000.0 if p == "BTC-USD" else 2500.0
        )

        with patch(
            "app.services.rebalance_monitor.get_exchange_client_for_account",
            return_value=mock_client
        ):
            await monitor._process_account(account, db)

        # No orders should be placed (within threshold, so free balances
        # are never even fetched)
        mock_client.buy_with_usd.assert_not_called()
        mock_client.create_market_order.assert_not_called()
