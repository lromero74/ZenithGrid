"""Tests for pure helpers in app/services/portfolio_calculations.py."""

import pytest

from app.services.portfolio_calculations import compute_untracked_usd


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
