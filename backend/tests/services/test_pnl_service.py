"""Tests for PnL service — extracted from Position.calculate_profit model method."""
import pytest
from unittest.mock import MagicMock
from app.services.pnl_service import (
    calculate_profit,
    calculate_realized_short_profit,
    calculate_realized_spot_profit,
)


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
