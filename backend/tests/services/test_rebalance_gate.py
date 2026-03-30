"""
Tests for the rebalancer gate helpers in rebalance_monitor.py:
  - set_account_gate_data / get_account_gate_data (allocation cache)
  - quote_is_overweight
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch


class TestAllocationCache:
    """Tests for the per-account allocation cache."""

    def setup_method(self):
        """Clear the cache before each test."""
        from app.services import rebalance_monitor
        rebalance_monitor._allocation_cache.clear()

    def test_set_and_get_returns_data(self):
        from app.services.rebalance_monitor import set_account_gate_data, get_account_gate_data
        payload = {"agg_current": {"usd_pct": 5.0, "btc_pct": 47.5, "usdc_pct": 47.5, "eth_pct": 0.0},
                   "targets": {"usd_pct": 0.0, "btc_pct": 50.0, "usdc_pct": 50.0, "eth_pct": 0.0},
                   "threshold": 5.0}
        set_account_gate_data(1, payload)
        result = get_account_gate_data(1)
        assert result is not None
        assert result["targets"]["btc_pct"] == 50.0

    def test_get_missing_account_returns_none(self):
        from app.services.rebalance_monitor import get_account_gate_data
        assert get_account_gate_data(99999) is None

    def test_cache_expires_after_ttl(self):
        from app.services.rebalance_monitor import set_account_gate_data, get_account_gate_data, _CACHE_TTL_SECONDS
        payload = {"agg_current": {}, "targets": {}, "threshold": 5.0}
        set_account_gate_data(2, payload)
        # Artificially age the cache entry
        from app.services import rebalance_monitor
        ts, data = rebalance_monitor._allocation_cache[2]
        rebalance_monitor._allocation_cache[2] = (ts - timedelta(seconds=_CACHE_TTL_SECONDS + 1), data)
        assert get_account_gate_data(2) is None

    def test_fresh_cache_not_expired(self):
        from app.services.rebalance_monitor import set_account_gate_data, get_account_gate_data
        payload = {"agg_current": {}, "targets": {}, "threshold": 5.0}
        set_account_gate_data(3, payload)
        assert get_account_gate_data(3) is not None


class TestQuoteIsOverweight:
    """Tests for quote_is_overweight()."""

    def setup_method(self):
        from app.services import rebalance_monitor
        rebalance_monitor._allocation_cache.clear()

    def _set_cache(self, account_id, current_pcts, target_pcts, threshold=5.0):
        from app.services.rebalance_monitor import set_account_gate_data
        set_account_gate_data(account_id, {
            "agg_current": current_pcts,
            "targets": target_pcts,
            "threshold": threshold,
        })

    def test_returns_true_when_clearly_overweight(self):
        """USDC at 75% vs target 50% with 5% threshold → overweight."""
        from app.services.rebalance_monitor import quote_is_overweight
        self._set_cache(1,
            {"usd_pct": 0.0, "btc_pct": 25.0, "eth_pct": 0.0, "usdc_pct": 75.0},
            {"usd_pct": 0.0, "btc_pct": 50.0, "eth_pct": 0.0, "usdc_pct": 50.0},
        )
        assert quote_is_overweight(1, "USDC") is True

    def test_returns_false_when_exactly_at_threshold(self):
        """BTC at 55% vs target 50% with 5% threshold → NOT overweight (needs strict >)."""
        from app.services.rebalance_monitor import quote_is_overweight
        self._set_cache(1,
            {"usd_pct": 0.0, "btc_pct": 55.0, "eth_pct": 0.0, "usdc_pct": 45.0},
            {"usd_pct": 0.0, "btc_pct": 50.0, "eth_pct": 0.0, "usdc_pct": 50.0},
        )
        assert quote_is_overweight(1, "BTC") is False

    def test_returns_false_when_within_threshold(self):
        """USD at 3% vs target 0% with 5% threshold → within bounds."""
        from app.services.rebalance_monitor import quote_is_overweight
        self._set_cache(1,
            {"usd_pct": 3.0, "btc_pct": 48.5, "eth_pct": 0.0, "usdc_pct": 48.5},
            {"usd_pct": 0.0, "btc_pct": 50.0, "eth_pct": 0.0, "usdc_pct": 50.0},
        )
        assert quote_is_overweight(1, "USD") is False

    def test_returns_false_when_no_cache(self):
        """Fail open: no cache data → do not gate the bot."""
        from app.services.rebalance_monitor import quote_is_overweight
        assert quote_is_overweight(99, "USDC") is False

    def test_returns_false_when_cache_stale(self):
        """Stale cache → fail open."""
        from app.services.rebalance_monitor import quote_is_overweight, _CACHE_TTL_SECONDS
        from app.services import rebalance_monitor
        rebalance_monitor._allocation_cache[5] = (
            datetime.utcnow() - timedelta(seconds=_CACHE_TTL_SECONDS + 1),
            {"agg_current": {"usdc_pct": 80.0, "btc_pct": 20.0, "usd_pct": 0.0, "eth_pct": 0.0},
             "targets": {"usdc_pct": 50.0, "btc_pct": 50.0, "usd_pct": 0.0, "eth_pct": 0.0},
             "threshold": 5.0}
        )
        assert quote_is_overweight(5, "USDC") is False

    def test_underweight_currency_not_gated(self):
        """BTC underweight → not overweight, bot should NOT be gated."""
        from app.services.rebalance_monitor import quote_is_overweight
        self._set_cache(1,
            {"usd_pct": 0.0, "btc_pct": 30.0, "eth_pct": 0.0, "usdc_pct": 70.0},
            {"usd_pct": 0.0, "btc_pct": 50.0, "eth_pct": 0.0, "usdc_pct": 50.0},
        )
        assert quote_is_overweight(1, "BTC") is False

    def test_just_over_threshold(self):
        """USDC at 56% vs target 50% with threshold 5% → 6% drift → overweight."""
        from app.services.rebalance_monitor import quote_is_overweight
        self._set_cache(1,
            {"usd_pct": 0.0, "btc_pct": 44.0, "eth_pct": 0.0, "usdc_pct": 56.0},
            {"usd_pct": 0.0, "btc_pct": 50.0, "eth_pct": 0.0, "usdc_pct": 50.0},
        )
        assert quote_is_overweight(1, "USDC") is True
