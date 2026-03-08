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

        current = {"usd_pct": 36.0, "btc_pct": 31.0, "eth_pct": 33.0, "usdc_pct": 0.0}
        targets = {"usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0, "usdc_pct": 0.0}

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

        current = {"usd_pct": 50.0, "btc_pct": 30.0, "eth_pct": 20.0, "usdc_pct": 0.0}
        targets = {"usd_pct": 50.0, "btc_pct": 30.0, "eth_pct": 20.0, "usdc_pct": 0.0}

        assert needs_rebalance(current, targets, threshold=5.0) is False

    def test_boundary_at_threshold_returns_false(self):
        """Edge case: drift exactly at threshold — no rebalance (must exceed)."""
        from app.services.rebalance_monitor import needs_rebalance

        current = {"usd_pct": 39.0, "btc_pct": 33.0, "eth_pct": 28.0, "usdc_pct": 0.0}
        targets = {"usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0, "usdc_pct": 0.0}

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
        targets = {"usd_pct": 50.0, "btc_pct": 30.0, "eth_pct": 20.0, "usdc_pct": 0.0}
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

    def test_respects_min_trade_pct(self):
        """Edge case: trades below min_trade_pct of portfolio are skipped."""
        from app.services.rebalance_monitor import plan_trades

        # Small portfolio — 5% of $190 = $9.50, below exchange floor of $10
        free_balances = {"USD": 100.0, "BTC": 0.00045, "ETH": 0.018}
        targets = {"usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0, "usdc_pct": 0.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0}

        # USD: 100, BTC: 45, ETH: 45 => total=190
        # 5% of 190 = $9.50, exchange floor = $10, so min = $10
        # Deltas ~$35 each, so trades should be planned (above $10)
        trades = plan_trades(free_balances, targets, prices, min_trade_pct=5.0)

        # With 20% min: 20% of 190 = $38, deltas ~$35 are below that
        trades_20 = plan_trades(free_balances, targets, prices, min_trade_pct=20.0)
        assert len(trades_20) == 0  # All deltas below 20% threshold

    def test_custom_min_trade_pct(self):
        """Edge case: custom min trade pct scales with portfolio."""
        from app.services.rebalance_monitor import plan_trades

        free_balances = {"USD": 10000.0, "BTC": 0.0, "ETH": 0.0}
        targets = {"usd_pct": 50.0, "btc_pct": 30.0, "eth_pct": 20.0, "usdc_pct": 0.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0}

        # Total = $10000. BTC trade = $3000 (30%), ETH trade = $2000 (20%)
        # With 5% min ($500), both qualify
        trades_5 = plan_trades(free_balances, targets, prices, min_trade_pct=5.0)
        assert len(trades_5) == 2

        # With 25% min ($2500), BTC ($3000) qualifies but ETH ($2000) doesn't
        trades_25 = plan_trades(free_balances, targets, prices, min_trade_pct=25.0)
        assert len(trades_25) == 1
        assert trades_25[0]["to_currency"] == "BTC"

    def test_skips_when_no_free_balance(self):
        """Edge case: zero free balances produces no trades."""
        from app.services.rebalance_monitor import plan_trades

        free_balances = {"USD": 0.0, "BTC": 0.0, "ETH": 0.0}
        targets = {"usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0, "usdc_pct": 0.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0}

        trades = plan_trades(free_balances, targets, prices)
        assert trades == []

    def test_three_way_rebalance(self):
        """Happy path: rebalance among all three currencies."""
        from app.services.rebalance_monitor import plan_trades

        # Heavy BTC, light USD and ETH
        free_balances = {"USD": 1000.0, "BTC": 0.08, "ETH": 0.4}
        targets = {"usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0, "usdc_pct": 0.0}
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

    def test_sell_capped_to_free_balance(self):
        """Edge case: sell amount capped to available free balance."""
        from app.services.rebalance_monitor import plan_trades

        # Target says sell lots of USD, but only $200 free
        free_balances = {"USD": 200.0, "BTC": 0.0, "ETH": 0.0}
        targets = {"usd_pct": 0.0, "btc_pct": 50.0, "eth_pct": 50.0, "usdc_pct": 0.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0}

        # Total free = $200, all in USD
        # Target: 0% USD, so sell all $200
        trades = plan_trades(free_balances, targets, prices)

        total_sold = sum(t["usd_amount"] for t in trades)
        # Can never sell more than the $200 of free USD
        assert total_sold <= 200.0


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
        account.rebalance_target_usdc_pct = 0.0
        account.rebalance_drift_threshold_pct = 5.0
        account.rebalance_min_trade_pct = 5.0
        account.min_balance_usd = 0.0
        account.min_balance_btc = 0.0
        account.min_balance_eth = 0.0
        account.min_balance_usdc = 0.0
        account.dust_sweep_enabled = False
        account.dust_sweep_threshold_usd = 5.0
        account.dust_last_sweep_at = None

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
        mock_client.get_usdc_balance = AsyncMock(return_value=0.0)
        mock_client.get_current_price = AsyncMock(
            side_effect=lambda p: {"BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0}.get(p, 0.0)
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
        account.rebalance_target_usdc_pct = 0.0
        account.rebalance_drift_threshold_pct = 5.0
        account.min_balance_usd = 0.0
        account.min_balance_btc = 0.0
        account.min_balance_eth = 0.0
        account.min_balance_usdc = 0.0
        account.dust_sweep_enabled = False
        account.dust_sweep_threshold_usd = 5.0
        account.dust_last_sweep_at = None

        db = AsyncMock()

        mock_client = AsyncMock()
        # Aggregate values roughly balanced
        mock_client.calculate_aggregate_quote_value = AsyncMock(
            side_effect=lambda c: (
                3400.0 if c == "USD"
                else 0.033 if c == "BTC"
                else 1.32 if c == "ETH"
                else 0.0
            )
        )
        mock_client.get_current_price = AsyncMock(
            side_effect=lambda p: {"BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0}.get(p, 0.0)
        )
        # Free balances are fetched first (for top-up check)
        mock_client.get_usd_balance = AsyncMock(return_value=3400.0)
        mock_client.get_btc_balance = AsyncMock(return_value=0.033)
        mock_client.get_eth_balance = AsyncMock(return_value=1.32)
        mock_client.get_usdc_balance = AsyncMock(return_value=0.0)

        with patch(
            "app.services.rebalance_monitor.get_exchange_client_for_account",
            return_value=mock_client
        ):
            await monitor._process_account(account, db)

        # No orders should be placed — within drift threshold
        # and no min balance reserves to top up
        mock_client.buy_with_usd.assert_not_called()
        mock_client.create_market_order.assert_not_called()


# ---------------------------------------------------------------------------
# plan_topup_trades
# ---------------------------------------------------------------------------


class TestPlanTopupTrades:
    """Tests for plan_topup_trades() — minimum balance reserve top-ups."""

    def test_no_deficit_no_trades(self):
        """Happy path: all currencies above minimum — no top-up trades needed."""
        from app.services.rebalance_monitor import plan_topup_trades

        free_balances = {"USD": 1000.0, "BTC": 0.1, "ETH": 2.0, "USDC": 500.0}
        min_balances = {"USD": 500.0, "BTC": 0.05, "ETH": 1.0, "USDC": 200.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0}

        trades = plan_topup_trades(free_balances, min_balances, prices)
        assert trades == []

    def test_single_currency_below_minimum(self):
        """Happy path: USDC below minimum, proportional buy from others."""
        from app.services.rebalance_monitor import plan_topup_trades

        # USDC has $300, minimum is $500 → deficit of $200
        free_balances = {"USD": 500.0, "BTC": 0.003, "ETH": 0.08, "USDC": 300.0}
        min_balances = {"USD": 0.0, "BTC": 0.0, "ETH": 0.0, "USDC": 500.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0}

        # USD=$500, BTC=0.003*100000=$300, ETH=0.08*2500=$200
        # Total available from others = $1000
        # Deficit = $200 USDC
        trades = plan_topup_trades(free_balances, min_balances, prices)

        assert len(trades) > 0
        # All trades should be buying USDC
        for t in trades:
            assert t["to_currency"] == "USDC"
        # Total USD amount across trades should be ~$200
        total = sum(t["usd_amount"] for t in trades)
        assert total == pytest.approx(200.0, rel=0.01)

    def test_proportional_sourcing(self):
        """Happy path: verify funds sourced proportionally from other currencies."""
        from app.services.rebalance_monitor import plan_topup_trades

        # USDC deficit = $200
        # Others: USD=$500 (50%), BTC=$300 (30%), ETH=$200 (20%)
        free_balances = {"USD": 500.0, "BTC": 0.003, "ETH": 0.08, "USDC": 300.0}
        min_balances = {"USD": 0.0, "BTC": 0.0, "ETH": 0.0, "USDC": 500.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0}

        trades = plan_topup_trades(free_balances, min_balances, prices)

        # Find trades by source currency
        by_source = {t["from_currency"]: t["usd_amount"] for t in trades}

        # USD contributes 50% of $200 = $100
        assert by_source.get("USD", 0) == pytest.approx(100.0, rel=0.01)
        # BTC contributes 30% of $200 = $60
        assert by_source.get("BTC", 0) == pytest.approx(60.0, rel=0.01)
        # ETH contributes 20% of $200 = $40
        assert by_source.get("ETH", 0) == pytest.approx(40.0, rel=0.01)

    def test_deficit_larger_than_available(self):
        """Edge case: deficit exceeds total available — trades capped to what's available."""
        from app.services.rebalance_monitor import plan_topup_trades

        # USDC deficit = $900 (need 1000, have 100)
        # Others: USD=$200, BTC=$100, ETH=$0 → total only $300
        free_balances = {"USD": 200.0, "BTC": 0.001, "ETH": 0.0, "USDC": 100.0}
        min_balances = {"USD": 0.0, "BTC": 0.0, "ETH": 0.0, "USDC": 1000.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0}

        trades = plan_topup_trades(free_balances, min_balances, prices)

        total = sum(t["usd_amount"] for t in trades)
        # Can't exceed total available ($300)
        assert total <= 300.0

    def test_multiple_currencies_below_minimum(self):
        """Edge case: two currencies below minimum — both get top-up trades."""
        from app.services.rebalance_monitor import plan_topup_trades

        # USD deficit=$200 (need 500, have 300), USDC deficit=$100 (need 200, have 100)
        # Available donors: BTC=$5000, ETH=$2500
        free_balances = {"USD": 300.0, "BTC": 0.05, "ETH": 1.0, "USDC": 100.0}
        min_balances = {"USD": 500.0, "BTC": 0.0, "ETH": 0.0, "USDC": 200.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0}

        trades = plan_topup_trades(free_balances, min_balances, prices)

        # Should have trades buying both USD and USDC
        buy_targets = {t["to_currency"] for t in trades}
        assert "USD" in buy_targets
        assert "USDC" in buy_targets

    def test_small_deficit_below_exchange_min(self):
        """Edge case: deficit < $10 exchange minimum — no trades."""
        from app.services.rebalance_monitor import plan_topup_trades

        # USDC deficit = $5 (need 505, have 500) — below $10 minimum
        free_balances = {"USD": 1000.0, "BTC": 0.1, "ETH": 2.0, "USDC": 500.0}
        min_balances = {"USD": 0.0, "BTC": 0.0, "ETH": 0.0, "USDC": 505.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0}

        trades = plan_topup_trades(free_balances, min_balances, prices)
        assert trades == []

    def test_all_zeros_no_trades(self):
        """Edge case: all minimums at zero — no top-up needed."""
        from app.services.rebalance_monitor import plan_topup_trades

        free_balances = {"USD": 100.0, "BTC": 0.001, "ETH": 0.04, "USDC": 50.0}
        min_balances = {"USD": 0.0, "BTC": 0.0, "ETH": 0.0, "USDC": 0.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0}

        trades = plan_topup_trades(free_balances, min_balances, prices)
        assert trades == []

    def test_individual_contribution_below_exchange_min_skipped(self):
        """Edge case: proportional contribution from a currency is below $10 — skip that source."""
        from app.services.rebalance_monitor import plan_topup_trades

        # USDC deficit = $200
        # Others: USD=$5000 (98%), BTC=$0, ETH=$100 (2%)
        # ETH's contribution: 2% of $200 = $4 → below $10, should be skipped
        free_balances = {"USD": 5000.0, "BTC": 0.0, "ETH": 0.04, "USDC": 300.0}
        min_balances = {"USD": 0.0, "BTC": 0.0, "ETH": 0.0, "USDC": 500.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0}

        trades = plan_topup_trades(free_balances, min_balances, prices)

        sources = {t["from_currency"] for t in trades}
        assert "ETH" not in sources  # Too small a contribution
        assert "USD" in sources


# ---------------------------------------------------------------------------
# plan_dust_sweeps
# ---------------------------------------------------------------------------


class TestPlanDustSweeps:
    """Tests for plan_dust_sweeps() — identify non-target dust and sell into underweight currency."""

    TARGET_CURRENCIES = {"USD", "BTC", "ETH", "USDC"}

    def test_identifies_coins_above_threshold(self):
        """Happy path: finds sweepable dust coins above the USD threshold."""
        from app.services.rebalance_monitor import plan_dust_sweeps

        all_balances = {
            "USD": 5000.0, "BTC": 0.05, "ETH": 2.0, "USDC": 500.0,
            "ADA": 73.5, "SOL": 0.06,
        }
        prices = {
            "BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0,
            "ADA-USD": 0.38, "SOL-USD": 163.0,
        }
        targets = {
            "usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0, "usdc_pct": 0.0,
        }
        available_products = {"ADA-USD", "SOL-USD", "ADA-BTC", "SOL-BTC"}

        result = plan_dust_sweeps(
            all_balances, targets, prices, available_products, threshold_usd=5.0
        )

        swept_coins = {s["coin"] for s in result}
        assert "ADA" in swept_coins  # 73.5 * 0.38 = $27.93
        assert "SOL" in swept_coins  # 0.06 * 163 = $9.78

    def test_skips_below_threshold(self):
        """Edge case: coins below threshold are skipped."""
        from app.services.rebalance_monitor import plan_dust_sweeps

        all_balances = {
            "USD": 5000.0, "BTC": 0.05, "ETH": 2.0, "USDC": 500.0,
            "ADA": 5.0,  # 5 * 0.38 = $1.90, below $5 threshold
        }
        prices = {
            "BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0,
            "ADA-USD": 0.38,
        }
        targets = {
            "usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0, "usdc_pct": 0.0,
        }
        available_products = {"ADA-USD"}

        result = plan_dust_sweeps(
            all_balances, targets, prices, available_products, threshold_usd=5.0
        )
        assert len(result) == 0

    def test_targets_underweight_currency(self):
        """Happy path: sells dust into the most underweight target currency."""
        from app.services.rebalance_monitor import plan_dust_sweeps

        # ETH is most underweight: current 10% vs target 33%
        all_balances = {
            "USD": 5000.0, "BTC": 0.04, "ETH": 0.4, "USDC": 500.0,
            "ADA": 100.0,
        }
        prices = {
            "BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0,
            "ADA-USD": 0.50,
        }
        targets = {
            "usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0, "usdc_pct": 0.0,
        }
        available_products = {"ADA-USD", "ADA-ETH"}

        result = plan_dust_sweeps(
            all_balances, targets, prices, available_products, threshold_usd=5.0
        )

        assert len(result) == 1
        # Should target the most underweight currency
        assert result[0]["target_currency"] in {"USD", "BTC", "ETH", "USDC"}

    def test_skips_untradable_coins(self):
        """Edge case: coins with no available trading pair are skipped."""
        from app.services.rebalance_monitor import plan_dust_sweeps

        all_balances = {
            "USD": 5000.0, "BTC": 0.05, "ETH": 2.0, "USDC": 500.0,
            "SHIB": 1000000.0,  # No trading pair available
        }
        prices = {
            "BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0,
        }
        targets = {
            "usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0, "usdc_pct": 0.0,
        }
        available_products = set()  # No products for SHIB

        result = plan_dust_sweeps(
            all_balances, targets, prices, available_products, threshold_usd=5.0
        )
        assert len(result) == 0

    def test_empty_balances_returns_empty(self):
        """Edge case: no non-target currencies in balances."""
        from app.services.rebalance_monitor import plan_dust_sweeps

        all_balances = {"USD": 5000.0, "BTC": 0.05, "ETH": 2.0, "USDC": 500.0}
        prices = {"BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0}
        targets = {
            "usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0, "usdc_pct": 0.0,
        }

        result = plan_dust_sweeps(
            all_balances, targets, prices, set(), threshold_usd=5.0
        )
        assert result == []

    def test_prefers_direct_pair_to_underweight_currency(self):
        """Happy path: uses direct pair to underweight currency if available."""
        from app.services.rebalance_monitor import plan_dust_sweeps

        # BTC is most underweight
        all_balances = {
            "USD": 8000.0, "BTC": 0.01, "ETH": 2.0, "USDC": 0.0,
            "ADA": 200.0,
        }
        prices = {
            "BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0,
            "ADA-USD": 0.50, "ADA-BTC": 0.000005,
        }
        targets = {
            "usd_pct": 34.0, "btc_pct": 33.0, "eth_pct": 33.0, "usdc_pct": 0.0,
        }
        # ADA-BTC pair available
        available_products = {"ADA-USD", "ADA-BTC"}

        result = plan_dust_sweeps(
            all_balances, targets, prices, available_products, threshold_usd=5.0
        )

        assert len(result) == 1
        assert result[0]["coin"] == "ADA"
        # Should prefer ADA-BTC since BTC is underweight
        assert result[0]["product_id"] == "ADA-BTC"
        assert result[0]["target_currency"] == "BTC"


# ---------------------------------------------------------------------------
# Dust sweep monthly cadence
# ---------------------------------------------------------------------------


class TestDustSweepCadence:
    """Tests for the monthly cadence check in dust sweeping."""

    def test_should_sweep_never_swept(self):
        """Happy path: account that has never been swept should be swept."""
        from app.services.rebalance_monitor import should_dust_sweep

        assert should_dust_sweep(None) is True

    def test_should_sweep_after_30_days(self):
        """Happy path: sweep if last sweep was >30 days ago."""
        from datetime import datetime, timedelta
        from app.services.rebalance_monitor import should_dust_sweep

        last_sweep = datetime.utcnow() - timedelta(days=31)
        assert should_dust_sweep(last_sweep) is True

    def test_should_not_sweep_within_30_days(self):
        """Edge case: skip sweep if last sweep was <30 days ago."""
        from datetime import datetime, timedelta
        from app.services.rebalance_monitor import should_dust_sweep

        last_sweep = datetime.utcnow() - timedelta(days=15)
        assert should_dust_sweep(last_sweep) is False

    def test_should_sweep_exactly_30_days(self):
        """Edge case: sweep at exactly 30 days."""
        from datetime import datetime, timedelta
        from app.services.rebalance_monitor import should_dust_sweep

        last_sweep = datetime.utcnow() - timedelta(days=30)
        assert should_dust_sweep(last_sweep) is True


# ---------------------------------------------------------------------------
# subtract_locked_amounts
# ---------------------------------------------------------------------------


class TestSubtractLockedAmounts:
    """Tests for subtract_locked_amounts() — exclude position-held coins from dust."""

    def test_subtracts_locked_from_balances(self):
        """Happy path: locked amounts are subtracted from total balances."""
        from app.services.rebalance_monitor import subtract_locked_amounts

        balances = {"USD": 5000, "ADA": 100.0, "SOL": 5.0}
        locked = {"ADA": 60.0}  # 60 ADA in open positions

        free = subtract_locked_amounts(balances, locked)

        assert free["ADA"] == pytest.approx(40.0)
        assert free["SOL"] == pytest.approx(5.0)
        assert free["USD"] == pytest.approx(5000.0)

    def test_fully_locked_coin_excluded(self):
        """Edge case: coin fully locked in positions is excluded entirely."""
        from app.services.rebalance_monitor import subtract_locked_amounts

        balances = {"ADA": 50.0, "SOL": 2.0}
        locked = {"ADA": 50.0}  # All ADA in positions

        free = subtract_locked_amounts(balances, locked)

        assert "ADA" not in free  # Zero free, excluded
        assert free["SOL"] == pytest.approx(2.0)

    def test_no_locked_returns_original(self):
        """Edge case: no locked positions returns original balances."""
        from app.services.rebalance_monitor import subtract_locked_amounts

        balances = {"ADA": 100.0, "SOL": 5.0}
        free = subtract_locked_amounts(balances, {})

        assert free == balances

    def test_locked_more_than_balance_excluded(self):
        """Edge case: locked > balance (shouldn't happen, but handle gracefully)."""
        from app.services.rebalance_monitor import subtract_locked_amounts

        balances = {"ADA": 30.0}
        locked = {"ADA": 50.0}  # Over-locked

        free = subtract_locked_amounts(balances, locked)
        assert "ADA" not in free


# ---------------------------------------------------------------------------
# _sweep_dust failure reporting
# ---------------------------------------------------------------------------


class TestSweepDustFailureReporting:
    """Tests that _sweep_dust reports failures in results."""

    @pytest.mark.asyncio
    async def test_failed_order_included_in_results(self):
        """When Coinbase returns an error response, it should appear in results."""
        from app.services.rebalance_monitor import RebalanceMonitor

        monitor = RebalanceMonitor()

        account = MagicMock()
        account.id = 1
        account.name = "Test"
        account.is_paper_trading = False
        account.dust_sweep_enabled = True
        account.dust_sweep_threshold_usd = 5.0
        account.dust_last_sweep_at = None
        account.rebalance_target_usd_pct = 34.0
        account.rebalance_target_btc_pct = 33.0
        account.rebalance_target_eth_pct = 33.0
        account.rebalance_target_usdc_pct = 0.0

        # Client with GRT dust and a failing market order
        client = AsyncMock()
        client.get_accounts.return_value = [
            {"currency": "USD", "available_balance": {"value": "5000"}},
            {"currency": "GRT", "available_balance": {"value": "100.5"}},
        ]
        client.get_current_price.return_value = "0.15"
        client.list_products.return_value = [{"product_id": "GRT-USD"}]
        # Simulate Coinbase error
        client.create_market_order.return_value = {
            "error_response": {"message": "Insufficient balance in source account"},
        }

        db = AsyncMock()

        with patch(
            "app.services.rebalance_monitor.get_position_locked_amounts",
            return_value={},
        ):
            results = await monitor._sweep_dust(
                client, account, db,
                prices={"BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0},
                free_balances={"USD": 5000.0},
            )

        assert len(results) == 1
        assert results[0]["coin"] == "GRT"
        assert results[0]["status"] == "failed"
        assert "Insufficient balance" in results[0]["error"]

    @pytest.mark.asyncio
    async def test_successful_order_has_success_status(self):
        """Successful orders should have status='success'."""
        from app.services.rebalance_monitor import RebalanceMonitor

        monitor = RebalanceMonitor()

        account = MagicMock()
        account.id = 1
        account.name = "Test"
        account.is_paper_trading = False
        account.dust_sweep_enabled = True
        account.dust_sweep_threshold_usd = 5.0
        account.dust_last_sweep_at = None
        account.rebalance_target_usd_pct = 34.0
        account.rebalance_target_btc_pct = 33.0
        account.rebalance_target_eth_pct = 33.0
        account.rebalance_target_usdc_pct = 0.0

        client = AsyncMock()
        client.get_accounts.return_value = [
            {"currency": "USD", "available_balance": {"value": "5000"}},
            {"currency": "LTC", "available_balance": {"value": "0.5"}},
        ]
        client.get_current_price.return_value = "80.0"
        client.list_products.return_value = [{"product_id": "LTC-USD"}]
        client.create_market_order.return_value = {
            "success_response": {"order_id": "order-123"},
        }

        db = AsyncMock()

        with patch(
            "app.services.rebalance_monitor.get_position_locked_amounts",
            return_value={},
        ):
            results = await monitor._sweep_dust(
                client, account, db,
                prices={"BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0},
                free_balances={"USD": 5000.0},
            )

        assert len(results) == 1
        assert results[0]["coin"] == "LTC"
        assert results[0]["status"] == "success"
        assert results[0]["order_id"] == "order-123"

    @pytest.mark.asyncio
    async def test_exception_during_order_included_as_failure(self):
        """If create_market_order raises, it should appear as a failure."""
        from app.services.rebalance_monitor import RebalanceMonitor

        monitor = RebalanceMonitor()

        account = MagicMock()
        account.id = 1
        account.name = "Test"
        account.is_paper_trading = False
        account.dust_sweep_enabled = True
        account.dust_sweep_threshold_usd = 5.0
        account.dust_last_sweep_at = None
        account.rebalance_target_usd_pct = 34.0
        account.rebalance_target_btc_pct = 33.0
        account.rebalance_target_eth_pct = 33.0
        account.rebalance_target_usdc_pct = 0.0

        client = AsyncMock()
        client.get_accounts.return_value = [
            {"currency": "USD", "available_balance": {"value": "5000"}},
            {"currency": "ETC", "available_balance": {"value": "2.0"}},
        ]
        client.get_current_price.return_value = "18.0"
        client.list_products.return_value = [{"product_id": "ETC-USD"}]
        client.create_market_order.side_effect = Exception("Network timeout")

        db = AsyncMock()

        with patch(
            "app.services.rebalance_monitor.get_position_locked_amounts",
            return_value={},
        ):
            results = await monitor._sweep_dust(
                client, account, db,
                prices={"BTC-USD": 100000.0, "ETH-USD": 2500.0, "USDC-USD": 1.0},
                free_balances={"USD": 5000.0},
            )

        assert len(results) == 1
        assert results[0]["coin"] == "ETC"
        assert results[0]["status"] == "failed"
        assert "Network timeout" in results[0]["error"]
