"""Tests for trading_engine/position_manager.py"""

import pytest
from unittest.mock import MagicMock

from app.trading_engine.position_manager import (
    all_positions_exhausted_safety_orders,
    calculate_expected_position_budget,
    calculate_max_deal_cost,
)


# ---------------------------------------------------------------------------
# calculate_expected_position_budget
# ---------------------------------------------------------------------------

class TestCalculateExpectedPositionBudget:
    def test_auto_calculate_returns_zero(self):
        config = {"auto_calculate_order_sizes": True}
        assert calculate_expected_position_budget(config, 1.0) == 0.0

    def test_manual_sizing_percentage_orders(self):
        """Manual sizing with percentage-based orders"""
        config = {
            "use_manual_sizing": True,
            "base_order_type": "percentage",
            "base_order_value": 10.0,  # 10% of aggregate
            "dca_order_type": "percentage",
            "dca_order_value": 5.0,  # 5% of aggregate per DCA
            "dca_order_multiplier": 1.0,
            "manual_max_dca_orders": 2,
        }
        aggregate = 1.0  # 1 BTC

        result = calculate_expected_position_budget(config, aggregate)

        # base = 1.0 * 10% = 0.1
        # dca1 = 1.0 * 5% = 0.05
        # dca2 = 1.0 * 5% = 0.05
        assert result == pytest.approx(0.2)

    def test_manual_sizing_fixed_orders(self):
        config = {
            "use_manual_sizing": True,
            "base_order_type": "fixed",
            "base_order_value": 0.01,
            "dca_order_type": "fixed",
            "dca_order_value": 0.005,
            "dca_order_multiplier": 2.0,
            "manual_max_dca_orders": 3,
        }

        result = calculate_expected_position_budget(config, 1.0)

        # base = 0.01
        # dca1 = 0.005 * 2^0 = 0.005
        # dca2 = 0.005 * 2^1 = 0.01
        # dca3 = 0.005 * 2^2 = 0.02
        assert result == pytest.approx(0.045)

    def test_fixed_base_with_safety_orders(self):
        config = {
            "base_order_type": "fixed",
            "base_order_btc": 0.001,
            "base_order_fixed": 0.001,
            "max_safety_orders": 2,
            "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 50.0,
            "safety_order_volume_scale": 1.0,
        }

        result = calculate_expected_position_budget(config, 1.0)

        # base = 0.001
        # safety1 = 0.001 * 50% = 0.0005
        # safety2 = 0.001 * 50% = 0.0005
        assert result == pytest.approx(0.002)

    def test_percentage_base_no_safety_returns_zero(self):
        config = {
            "base_order_type": "percentage",
            "max_safety_orders": 0,
        }
        assert calculate_expected_position_budget(config, 1.0) == 0.0

    def test_fixed_base_no_safety_returns_zero(self):
        config = {
            "base_order_type": "fixed",
            "max_safety_orders": 0,
        }
        assert calculate_expected_position_budget(config, 1.0) == 0.0

    def test_volume_scale_applied_to_safety_orders(self):
        config = {
            "base_order_type": "fixed_btc",
            "base_order_btc": 0.001,
            "base_order_fixed": 0.001,
            "max_safety_orders": 3,
            "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 100.0,
            "safety_order_volume_scale": 2.0,
        }

        result = calculate_expected_position_budget(config, 1.0)

        # base = 0.001
        # safety1 = 0.001 * 100% * 2^0 = 0.001
        # safety2 = 0.001 * 100% * 2^1 = 0.002
        # safety3 = 0.001 * 100% * 2^2 = 0.004
        assert result == pytest.approx(0.008)


# ---------------------------------------------------------------------------
# calculate_max_deal_cost
# ---------------------------------------------------------------------------

class TestCalculateMaxDealCost:
    def test_zero_base_order_returns_zero(self):
        assert calculate_max_deal_cost({}, 0) == 0.0
        assert calculate_max_deal_cost({}, -1) == 0.0

    def test_no_safety_orders(self):
        config = {"max_safety_orders": 0}
        assert calculate_max_deal_cost(config, 0.001) == pytest.approx(0.001)

    def test_percentage_of_base_safety_orders(self):
        config = {
            "max_safety_orders": 2,
            "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 50.0,
            "safety_order_volume_scale": 1.0,
        }

        result = calculate_max_deal_cost(config, 0.01)

        # base = 0.01
        # safety1 = 0.01 * 50% = 0.005
        # safety2 = 0.01 * 50% = 0.005
        assert result == pytest.approx(0.02)

    def test_volume_scaling(self):
        config = {
            "max_safety_orders": 3,
            "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 100.0,
            "safety_order_volume_scale": 2.0,
        }

        result = calculate_max_deal_cost(config, 0.01)

        # base = 0.01
        # safety1 = 0.01 * 1 = 0.01
        # safety2 = 0.01 * 2 = 0.02
        # safety3 = 0.01 * 4 = 0.04
        assert result == pytest.approx(0.08)

    def test_manual_sizing_dca_orders(self):
        config = {
            "use_manual_sizing": True,
            "dca_order_type": "fixed",
            "dca_order_value": 0.005,
            "dca_order_multiplier": 1.5,
            "manual_max_dca_orders": 2,
            "max_safety_orders": 2,
        }

        result = calculate_max_deal_cost(config, 0.01)

        # base = 0.01
        # dca1 = 0.005 * 1.5^0 = 0.005
        # dca2 = 0.005 * 1.5^1 = 0.0075
        assert result == pytest.approx(0.0225)

    def test_auto_calc_safety_equals_base(self):
        config = {
            "max_safety_orders": 2,
            "safety_order_type": "fixed_btc",
            "auto_calculate_order_sizes": True,
            "safety_order_volume_scale": 1.0,
        }

        result = calculate_max_deal_cost(config, 0.01)

        # base = 0.01
        # safety1 = 0.01 * 1 = 0.01 (auto-calc: safety = base)
        # safety2 = 0.01 * 1 = 0.01
        assert result == pytest.approx(0.03)


# ---------------------------------------------------------------------------
# all_positions_exhausted_safety_orders
# ---------------------------------------------------------------------------

class TestAllPositionsExhaustedSafetyOrders:
    def test_empty_positions_returns_true(self):
        assert all_positions_exhausted_safety_orders([], 3) is True

    def test_position_with_all_safety_orders_used(self):
        pos = MagicMock()
        # 1 initial buy + 3 safety orders = 4 buy trades
        buy_trades = [MagicMock(side="buy") for _ in range(4)]
        pos.trades = buy_trades

        assert all_positions_exhausted_safety_orders([pos], 3) is True

    def test_position_with_safety_orders_remaining(self):
        pos = MagicMock()
        # 1 initial buy only, 0 safety orders used
        pos.trades = [MagicMock(side="buy")]

        assert all_positions_exhausted_safety_orders([pos], 3) is False

    def test_multiple_positions_mixed(self):
        """Returns False if ANY position hasn't exhausted safety orders"""
        pos1 = MagicMock()
        pos1.trades = [MagicMock(side="buy") for _ in range(4)]  # 3 safety = exhausted

        pos2 = MagicMock()
        pos2.trades = [MagicMock(side="buy")]  # 0 safety = NOT exhausted

        assert all_positions_exhausted_safety_orders([pos1, pos2], 3) is False

    def test_position_with_no_trades(self):
        pos = MagicMock()
        pos.trades = None

        assert all_positions_exhausted_safety_orders([pos], 3) is False

    def test_sell_trades_not_counted(self):
        pos = MagicMock()
        pos.trades = [
            MagicMock(side="buy"),
            MagicMock(side="sell"),
            MagicMock(side="buy"),
        ]
        # 2 buys: 1 initial + 1 safety = 1/3 safety used

        assert all_positions_exhausted_safety_orders([pos], 3) is False
