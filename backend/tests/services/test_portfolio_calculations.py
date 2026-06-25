"""Tests for pure helpers in app/services/portfolio_calculations.py."""

import pytest
from types import SimpleNamespace

from app.services.portfolio_calculations import compute_untracked_usd, _compute_position_pnl


def _pos(product_id, direction="long", **kw):
    base, quote = product_id.split("-")
    p = SimpleNamespace(
        direction=direction,
        total_base_acquired=kw.get("total_base_acquired", 0.0),
        total_quote_spent=kw.get("total_quote_spent", 0.0),
        short_total_sold_base=kw.get("short_total_sold_base", 0.0),
        short_total_sold_quote=kw.get("short_total_sold_quote", 0.0),
    )
    p.get_base_currency = lambda: base
    p.get_quote_currency = lambda: quote
    return p


class TestComputePositionPnl:
    """_compute_position_pnl must handle shorts (own cost basis) and USDC pairs."""

    def test_usdc_pair_included(self):
        # USDC-quoted long: bought 1 SOL for $100, now worth $150 → +$50 USD.
        pos = _pos("SOL-USDC", total_base_acquired=1.0, total_quote_spent=100.0)
        result = _compute_position_pnl([pos], {"SOL": 150.0}, btc_usd_price=60000.0)
        assert result["SOL"]["pnl_usd"] == pytest.approx(50.0)
        assert result["SOL"]["cost_usd"] == pytest.approx(100.0)

    def test_short_uses_short_cost_basis(self):
        # Short: sold 1 ETH for $2000; price fell to $1800 → +$200 profit.
        pos = _pos("ETH-USD", direction="short",
                   short_total_sold_base=1.0, short_total_sold_quote=2000.0)
        result = _compute_position_pnl([pos], {"ETH": 1800.0}, btc_usd_price=60000.0)
        assert result["ETH"]["pnl_usd"] == pytest.approx(200.0)
        assert result["ETH"]["cost_usd"] == pytest.approx(2000.0)

    def test_long_usd_unchanged(self):
        pos = _pos("BTC-USD", total_base_acquired=0.01, total_quote_spent=600.0)
        result = _compute_position_pnl([pos], {"BTC": 65000.0}, btc_usd_price=65000.0)
        assert result["BTC"]["pnl_usd"] == pytest.approx(0.01 * 65000.0 - 600.0)


class TestComputeUntrackedUsd:
    """compute_untracked_usd: USD value of wallet coins not backed by a position."""

    def test_fully_orphaned_coin_counts_in_full(self):
        """A coin with no open-position backing contributes its full USD value."""
        holdings = [{"asset": "ERA", "total_balance": 38.81, "in_positions": 0.0, "usd_value": 3.33}]
        assert compute_untracked_usd(holdings) == pytest.approx(3.33)

    def test_partial_surplus_is_prorated(self):
        """Only the unbacked fraction of a coin counts."""
        # wallet 30, 19.7 backs an open position -> 10.3/30 of $5.30 is untracked
        holdings = [{"asset": "FET", "total_balance": 30.0, "in_positions": 19.7, "usd_value": 5.30}]
        assert compute_untracked_usd(holdings) == pytest.approx(5.30 * (10.3 / 30.0))

    def test_fully_backed_coin_contributes_nothing(self):
        """A coin entirely backing open positions is not untracked."""
        holdings = [{"asset": "UNI", "total_balance": 0.337, "in_positions": 0.337, "usd_value": 0.99}]
        assert compute_untracked_usd(holdings) == pytest.approx(0.0)

    def test_balance_table_rows_excluded(self):
        """BTC/ETH/stablecoins have their own rows and never count as untracked."""
        holdings = [
            {"asset": "BTC", "total_balance": 0.01, "in_positions": 0.0, "usd_value": 600.0},
            {"asset": "ETH", "total_balance": 1.0, "in_positions": 0.0, "usd_value": 1600.0},
            {"asset": "USD", "total_balance": 50.0, "in_positions": 0.0, "usd_value": 50.0},
            {"asset": "USDC", "total_balance": 5.0, "in_positions": 0.0, "usd_value": 5.0},
            {"asset": "USDT", "total_balance": 1.0, "in_positions": 0.0, "usd_value": 1.0},
        ]
        assert compute_untracked_usd(holdings) == pytest.approx(0.0)

    def test_mixed_portfolio_sums_only_unbacked_alts(self):
        holdings = [
            {"asset": "BTC", "total_balance": 0.01, "in_positions": 0.0, "usd_value": 600.0},   # excluded
            {"asset": "ERA", "total_balance": 38.81, "in_positions": 0.0, "usd_value": 3.33},    # full
            {"asset": "FET", "total_balance": 30.0, "in_positions": 30.0, "usd_value": 5.30},    # fully backed
            {"asset": "CRV", "total_balance": 10.0, "in_positions": 5.0, "usd_value": 2.00},     # half
        ]
        assert compute_untracked_usd(holdings) == pytest.approx(3.33 + 1.00)

    def test_empty_holdings(self):
        assert compute_untracked_usd([]) == 0.0

    def test_zero_balance_skipped_no_divide_by_zero(self):
        """A zero-balance holding must not raise (no divide-by-zero)."""
        holdings = [{"asset": "FOO", "total_balance": 0.0, "in_positions": 0.0, "usd_value": 0.0}]
        assert compute_untracked_usd(holdings) == 0.0

    def test_missing_fields_default_safely(self):
        """Missing in_positions/usd_value default to 0 without raising."""
        holdings = [{"asset": "BAR", "total_balance": 10.0}]
        assert compute_untracked_usd(holdings) == 0.0
