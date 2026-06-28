"""Tests for PnL service — extracted from Position.calculate_profit model method."""
import pytest
from unittest.mock import MagicMock
from types import SimpleNamespace
from app.constants import FALLBACK_BTC_USD_PRICE
from app.services.pnl_service import (
    DEFAULT_TAKER_FEE_RATE,
    calculate_profit,
    calculate_realized_short_profit,
    calculate_realized_spot_profit,
    fee_adjusted_tp_floor,
    position_exit_fee_rate,
    resolve_btc_usd_price,
)


class TestResolveBtcUsdPrice:
    def test_prefers_close_price(self):
        pos = SimpleNamespace(btc_usd_price_at_close=120000.0, btc_usd_price_at_open=90000.0)
        assert resolve_btc_usd_price(pos) == 120000.0

    def test_falls_back_to_open_when_close_missing(self):
        pos = SimpleNamespace(btc_usd_price_at_close=None, btc_usd_price_at_open=90000.0)
        assert resolve_btc_usd_price(pos) == 90000.0

    def test_zero_close_falls_through_to_open(self):
        pos = SimpleNamespace(btc_usd_price_at_close=0.0, btc_usd_price_at_open=90000.0)
        assert resolve_btc_usd_price(pos) == 90000.0

    def test_uses_constant_when_both_missing(self):
        pos = SimpleNamespace(btc_usd_price_at_close=None, btc_usd_price_at_open=None)
        assert resolve_btc_usd_price(pos) == FALLBACK_BTC_USD_PRICE


class TestCalculateProfit:
    """Characterization tests for calculate_profit logic."""

    def _make_position(self, direction="long", **kwargs):
        """Create a mock position with given attributes."""
        pos = MagicMock()
        pos.direction = direction
        pos.total_base_acquired = kwargs.get("total_base_acquired", 0.0)
        pos.total_quote_spent = kwargs.get("total_quote_spent", 0.0)
        pos.short_total_sold_base = kwargs.get("short_total_sold_base", None)
        pos.short_total_sold_quote = kwargs.get("short_total_sold_quote", None)
        return pos

    # --- Long positions ---

    def test_long_profit_when_price_rises(self):
        """Long position should show profit when price goes up."""
        pos = self._make_position(
            direction="long",
            total_base_acquired=1.0,
            total_quote_spent=100.0,
        )
        result = calculate_profit(pos, current_price=150.0)
        assert result["profit_quote"] == pytest.approx(50.0)
        assert result["profit_pct"] == pytest.approx(50.0)
        assert result["unrealized_value"] == pytest.approx(150.0)

    def test_long_loss_when_price_drops(self):
        """Long position should show loss when price goes down."""
        from app.services.pnl_service import calculate_profit
        pos = self._make_position(
            direction="long",
            total_base_acquired=2.0,
            total_quote_spent=200.0,
        )
        result = calculate_profit(pos, current_price=80.0)
        assert result["profit_quote"] == pytest.approx(-40.0)
        assert result["profit_pct"] == pytest.approx(-20.0)
        assert result["unrealized_value"] == pytest.approx(160.0)

    def test_long_zero_quote_spent_returns_zero_pct(self):
        """Edge case: zero quote spent should yield 0% profit."""
        from app.services.pnl_service import calculate_profit
        pos = self._make_position(
            direction="long",
            total_base_acquired=1.0,
            total_quote_spent=0.0,
        )
        result = calculate_profit(pos, current_price=50.0)
        assert result["profit_pct"] == pytest.approx(0.0)
        assert result["unrealized_value"] == pytest.approx(50.0)

    # --- Short positions ---

    def test_short_profit_when_price_drops(self):
        """Short position should show profit when price goes down."""
        from app.services.pnl_service import calculate_profit
        pos = self._make_position(
            direction="short",
            short_total_sold_base=1.0,
            short_total_sold_quote=100.0,
        )
        result = calculate_profit(pos, current_price=80.0)
        assert result["profit_quote"] == pytest.approx(20.0)
        assert result["profit_pct"] == pytest.approx(20.0)
        assert result["unrealized_value"] == pytest.approx(80.0)

    def test_short_loss_when_price_rises(self):
        """Short position should show loss when price goes up."""
        from app.services.pnl_service import calculate_profit
        pos = self._make_position(
            direction="short",
            short_total_sold_base=1.0,
            short_total_sold_quote=100.0,
        )
        result = calculate_profit(pos, current_price=120.0)
        assert result["profit_quote"] == pytest.approx(-20.0)
        assert result["profit_pct"] == pytest.approx(-20.0)
        assert result["unrealized_value"] == pytest.approx(120.0)

    def test_short_none_fields_default_to_zero(self):
        """Short position with None sold fields should not crash."""
        from app.services.pnl_service import calculate_profit
        pos = self._make_position(
            direction="short",
            short_total_sold_base=None,
            short_total_sold_quote=None,
        )
        result = calculate_profit(pos, current_price=100.0)
        assert result["profit_quote"] == pytest.approx(0.0)
        assert result["profit_pct"] == pytest.approx(0.0)
        assert result["unrealized_value"] == pytest.approx(0.0)


def test_realized_spot_profit_subtracts_entry_and_exit_fees():
    profit, percentage = calculate_realized_spot_profit(
        2.2026774316875, 2.2539803481, 0.02643212918025, 0.02704776417719334,
    )

    assert profit == pytest.approx(-0.002176976945)
    assert percentage == pytest.approx(-0.0976612807)


def test_realized_spot_profit_handles_zero_cost():
    assert calculate_realized_spot_profit(0.0, 1.0, 0.0, 0.1) == (0.9, 0.0)


def test_realized_short_profit_subtracts_entry_and_exit_fees():
    profit, percentage = calculate_realized_short_profit(105.0, 95.0, 1.0, 2.0)

    assert profit == pytest.approx(7.0)
    assert percentage == pytest.approx(6.7307692308)


def test_realized_short_profit_handles_zero_net_proceeds():
    assert calculate_realized_short_profit(1.0, 0.0, 1.0, 0.0) == (0.0, 0.0)


class TestFeeAdjustedTakeProfit:
    """The take-profit floor must be raised so the configured target is net of fees."""

    def test_exit_fee_rate_calibrates_from_entry_leg(self):
        # Paid $0.60 entry fee on $100 spent → 0.6% per-leg rate.
        pos = SimpleNamespace(total_quote_spent=100.0, entry_fees_quote=0.60)
        assert position_exit_fee_rate(pos) == pytest.approx(0.006)

    def test_exit_fee_rate_falls_back_when_no_recorded_fee(self):
        legacy = SimpleNamespace(total_quote_spent=100.0, entry_fees_quote=0.0)
        assert position_exit_fee_rate(legacy) == pytest.approx(DEFAULT_TAKER_FEE_RATE)
        empty = SimpleNamespace(total_quote_spent=0.0, entry_fees_quote=0.0)
        assert position_exit_fee_rate(empty) == pytest.approx(DEFAULT_TAKER_FEE_RATE)

    def test_exit_fee_rate_uses_short_notional_for_shorts(self):
        # Shorts set short_total_sold_quote (not total_quote_spent); the rate must
        # calibrate from that instead of falling through to the flat default.
        short = SimpleNamespace(total_quote_spent=0.0, short_total_sold_quote=200.0,
                                entry_fees_quote=1.20)
        assert position_exit_fee_rate(short) == pytest.approx(0.006)

    def test_floor_is_strictly_above_target(self):
        pos = SimpleNamespace(total_quote_spent=100.0, entry_fees_quote=0.60)
        floor = fee_adjusted_tp_floor(pos, 1.0)
        assert floor > 1.0
        assert floor == pytest.approx(2.2186, abs=1e-3)

    def test_floor_makes_net_profit_equal_target(self):
        # At exactly the floor gross%, realized net profit% must equal the target.
        spent, entry_fee = 100.0, 0.60
        pos = SimpleNamespace(total_quote_spent=spent, entry_fees_quote=entry_fee)
        target = 1.0
        floor = fee_adjusted_tp_floor(pos, target)
        exit_value = spent * (1.0 + floor / 100.0)            # gross value at the floor
        exit_fee = exit_value * position_exit_fee_rate(pos)
        _, net_pct = calculate_realized_spot_profit(spent, exit_value, entry_fee, exit_fee)
        assert net_pct == pytest.approx(target, abs=1e-6)

    def test_zero_target_floor_covers_round_trip_fees(self):
        # A 0% target must still require enough gross profit to not lose money to fees.
        pos = SimpleNamespace(total_quote_spent=100.0, entry_fees_quote=0.60)
        assert fee_adjusted_tp_floor(pos, 0.0) == pytest.approx(1.2072, abs=1e-3)

    def test_degenerate_fee_rate_returns_target_unchanged(self):
        absurd = SimpleNamespace(total_quote_spent=1.0, entry_fees_quote=5.0)  # 500% rate
        assert fee_adjusted_tp_floor(absurd, 3.0) == 3.0
