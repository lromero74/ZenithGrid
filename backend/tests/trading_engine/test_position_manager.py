"""Tests for trading_engine/position_manager.py"""

import pytest
from unittest.mock import MagicMock

from app.trading_engine.position_manager import (
    all_positions_exhausted_safety_orders,
    calculate_expected_position_budget,
    calculate_max_deal_cost,
    compute_grace_expanded_budget,
)


# ---------------------------------------------------------------------------
# compute_grace_expanded_budget (just-in-time grace budget)
# ---------------------------------------------------------------------------


class TestFixedUsdBudget:
    """fixed_usd is a real base_order_type — it must get a per-deal budget cap, not 0
    (0 made max_quote_allowed fall back to the whole balance)."""

    def test_fixed_usd_returns_nonzero_budget(self):
        cfg = {
            "base_order_type": "fixed_usd", "base_order_fixed": 100.0,
            "max_safety_orders": 2, "safety_order_type": "fixed_usd",
            "safety_order_fixed": 50.0, "safety_order_volume_scale": 1.0,
        }
        budget = calculate_expected_position_budget(cfg, 0.0)
        # base 100 + 2 SOs * 50 = 200
        assert budget == pytest.approx(200.0)

    def test_fixed_usd_matches_fixed_btc_structure(self):
        """fixed_usd budget must be > 0 (was 0 before the fix)."""
        cfg = {"base_order_type": "fixed_usd", "base_order_fixed": 25.0,
               "max_safety_orders": 1, "safety_order_type": "fixed_usd",
               "safety_order_fixed": 25.0, "safety_order_volume_scale": 1.0}
        assert calculate_expected_position_budget(cfg, 0.0) > 0


class TestComputeGraceExpandedBudget:
    """Grace expands a deal's budget only after configured SOs are spent, using the
    same deal-cost formula a manual bump would (rule 13)."""

    def _cfg(self, **o):
        base = {
            "base_order_type": "fixed", "base_order_fixed": 0.001,
            "max_safety_orders": 3, "safety_order_type": "percentage_of_base",
            "safety_order_percentage": 50.0, "safety_order_volume_scale": 1.0,
        }
        base.update(o)
        return base

    def test_zero_when_no_grace(self):
        cfg = self._cfg(grace_safety_orders=0)
        assert compute_grace_expanded_budget(cfg, deployed_safety_orders=3,
                                             base_order_size=0.001, aggregate_value=0.0) == 0.0

    def test_zero_before_configured_exhausted(self):
        cfg = self._cfg(grace_safety_orders=2)
        # only 2 of 3 configured deployed → grace not active yet
        assert compute_grace_expanded_budget(cfg, 2, 0.001, 0.0) == 0.0

    def test_expands_to_manual_bump_value_once_exhausted(self):
        cfg = self._cfg(grace_safety_orders=2)
        # Grace budget must equal the deal cost for configured+grace = 5 SOs —
        # i.e. exactly what editing Max Safety Orders to 5 would compute.
        expected = calculate_expected_position_budget({**cfg, "max_safety_orders": 5}, 0.0)
        assert compute_grace_expanded_budget(cfg, 3, 0.001, 0.0) == pytest.approx(expected)
        # ...and strictly greater than the configured-only budget.
        assert expected > calculate_expected_position_budget(cfg, 0.0)

    def test_zero_when_safety_orders_disabled(self):
        cfg = self._cfg(max_safety_orders=0, grace_safety_orders=2)
        assert compute_grace_expanded_budget(cfg, 0, 0.001, 0.0) == 0.0


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

def _pos(*trades, direction="long"):
    """A mock position with the given entry trades (default long)."""
    pos = MagicMock()
    pos.direction = direction
    pos.trades = list(trades)
    return pos


def _t(side="buy", dca_levels=1):
    """A mock trade carrying a real int dca_levels (count_deployed sums these)."""
    return MagicMock(side=side, dca_levels=dca_levels)


class TestAllPositionsExhaustedSafetyOrders:
    def test_empty_positions_returns_true(self):
        assert all_positions_exhausted_safety_orders([], 3) is True

    def test_position_with_all_safety_orders_used(self):
        # 1 initial buy + 3 safety orders = 4 buy trades
        pos = _pos(*[_t("buy") for _ in range(4)])
        assert all_positions_exhausted_safety_orders([pos], 3) is True

    def test_position_with_safety_orders_remaining(self):
        pos = _pos(_t("buy"))  # 1 initial buy only, 0 safety orders used
        assert all_positions_exhausted_safety_orders([pos], 3) is False

    def test_multiple_positions_mixed(self):
        """Returns False if ANY position hasn't exhausted safety orders"""
        pos1 = _pos(*[_t("buy") for _ in range(4)])  # 3 safety = exhausted
        pos2 = _pos(_t("buy"))                        # 0 safety = NOT exhausted
        assert all_positions_exhausted_safety_orders([pos1, pos2], 3) is False

    def test_position_with_no_trades(self):
        pos = MagicMock()
        pos.direction = "long"
        pos.trades = None
        assert all_positions_exhausted_safety_orders([pos], 3) is False

    def test_sell_trades_not_counted(self):
        # 2 buys: 1 initial + 1 safety = 1/3 safety used
        pos = _pos(_t("buy"), _t("sell"), _t("buy"))
        assert all_positions_exhausted_safety_orders([pos], 3) is False

    def test_cascade_levels_counted_not_trade_rows(self):
        """A single cascade trade deploying 3 SO levels counts as 3 (not 1) — the old
        buy_count-1 form undercounted and let a new deal open prematurely."""
        # base order (1 level) + one cascade trade that filled 3 SO levels
        pos = _pos(_t("buy", dca_levels=1), _t("buy", dca_levels=3))
        assert all_positions_exhausted_safety_orders([pos], 3) is True   # 3 >= 3
        assert all_positions_exhausted_safety_orders([pos], 4) is False  # 3 < 4

    def test_short_position_entry_trades_are_sells(self):
        """For shorts, entry trades are sells — they must be counted as safety orders."""
        pos = _pos(_t("sell"), _t("sell"), _t("sell"), _t("sell"), direction="short")
        assert all_positions_exhausted_safety_orders([pos], 3) is True
