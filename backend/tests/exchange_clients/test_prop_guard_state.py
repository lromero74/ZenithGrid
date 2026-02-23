"""
Tests for backend/app/exchange_clients/prop_guard_state.py

Pure function tests for drawdown calculations, daily reset detection,
volatility calculations, spread calculations, and size adjustments.
No mocking needed -- these are stateless math functions.
"""

from datetime import datetime

import pytest

from app.exchange_clients.prop_guard_state import (
    adjust_size_for_volatility,
    calculate_btc_volatility,
    calculate_daily_drawdown_pct,
    calculate_spread_pct,
    calculate_total_drawdown_pct,
    should_reset_daily,
)


# =========================================================
# calculate_daily_drawdown_pct
# =========================================================


class TestCalculateDailyDrawdownPct:
    """Tests for calculate_daily_drawdown_pct()"""

    def test_no_drawdown_equity_unchanged(self):
        """Happy path: equity equals start, drawdown is 0."""
        result = calculate_daily_drawdown_pct(100000.0, 100000.0)
        assert result == pytest.approx(0.0)

    def test_drawdown_5_percent(self):
        """Happy path: 5% loss from starting equity."""
        result = calculate_daily_drawdown_pct(100000.0, 95000.0)
        assert result == pytest.approx(5.0)

    def test_equity_above_start_returns_zero(self):
        """Edge case: equity increased (profit), should return 0 not negative."""
        result = calculate_daily_drawdown_pct(100000.0, 105000.0)
        assert result == pytest.approx(0.0)

    def test_zero_start_equity_returns_zero(self):
        """Failure case: zero starting equity avoids division by zero."""
        result = calculate_daily_drawdown_pct(0.0, 50000.0)
        assert result == pytest.approx(0.0)

    def test_negative_start_equity_returns_zero(self):
        """Failure case: negative starting equity returns 0."""
        result = calculate_daily_drawdown_pct(-100.0, 50000.0)
        assert result == pytest.approx(0.0)

    def test_total_loss_returns_100(self):
        """Edge case: equity drops to zero (100% drawdown)."""
        result = calculate_daily_drawdown_pct(100000.0, 0.0)
        assert result == pytest.approx(100.0)

    def test_small_fractional_drawdown(self):
        """Edge case: very small drawdown (0.01%)."""
        result = calculate_daily_drawdown_pct(100000.0, 99990.0)
        assert result == pytest.approx(0.01)


# =========================================================
# calculate_total_drawdown_pct
# =========================================================


class TestCalculateTotalDrawdownPct:
    """Tests for calculate_total_drawdown_pct()"""

    def test_no_drawdown_from_initial(self):
        """Happy path: equity at initial deposit."""
        result = calculate_total_drawdown_pct(100000.0, 100000.0)
        assert result == pytest.approx(0.0)

    def test_drawdown_9_percent(self):
        """Happy path: 9% total drawdown."""
        result = calculate_total_drawdown_pct(100000.0, 91000.0)
        assert result == pytest.approx(9.0)

    def test_equity_above_initial_returns_zero(self):
        """Edge case: profit above initial deposit returns 0."""
        result = calculate_total_drawdown_pct(100000.0, 110000.0)
        assert result == pytest.approx(0.0)

    def test_zero_initial_deposit_returns_zero(self):
        """Failure case: zero initial deposit avoids division by zero."""
        result = calculate_total_drawdown_pct(0.0, 50000.0)
        assert result == pytest.approx(0.0)

    def test_negative_initial_deposit_returns_zero(self):
        """Failure case: negative initial deposit returns 0."""
        result = calculate_total_drawdown_pct(-50000.0, 50000.0)
        assert result == pytest.approx(0.0)


# =========================================================
# should_reset_daily
# =========================================================


class TestShouldResetDaily:
    """Tests for should_reset_daily()"""

    def test_no_previous_snapshot_returns_true(self):
        """Happy path: first run with no previous snapshot needs reset."""
        result = should_reset_daily(None)
        assert result is True

    def test_snapshot_before_reset_time_returns_true(self):
        """Happy path: snapshot was taken before today's reset; needs refresh."""
        # Reset at 17:00 EST = 22:00 UTC (tz_offset=-5)
        now = datetime(2025, 6, 15, 23, 0, 0)  # 23:00 UTC (after reset)
        old_snapshot = datetime(2025, 6, 15, 10, 0, 0)  # Before 22:00 UTC
        result = should_reset_daily(old_snapshot, now=now)
        assert result is True

    def test_snapshot_after_reset_time_returns_false(self):
        """Happy path: snapshot taken after reset time, no reset needed."""
        now = datetime(2025, 6, 15, 23, 30, 0)  # 23:30 UTC
        recent_snapshot = datetime(2025, 6, 15, 22, 5, 0)  # 22:05 UTC (just after reset)
        result = should_reset_daily(recent_snapshot, now=now)
        assert result is False

    def test_snapshot_same_as_reset_time_returns_false(self):
        """Edge case: snapshot at exactly the reset time should not trigger reset."""
        now = datetime(2025, 6, 15, 23, 0, 0)
        # Snapshot at exactly 22:00 UTC (the reset boundary)
        snapshot_at_reset = datetime(2025, 6, 15, 22, 0, 0)
        result = should_reset_daily(snapshot_at_reset, now=now)
        assert result is False

    def test_snapshot_yesterday_before_reset_returns_true(self):
        """Edge case: snapshot from yesterday, well before today's reset."""
        now = datetime(2025, 6, 16, 1, 0, 0)  # 01:00 UTC on the 16th
        old_snapshot = datetime(2025, 6, 14, 22, 5, 0)  # Two days old
        result = should_reset_daily(old_snapshot, now=now)
        assert result is True

    def test_before_reset_time_today_snapshot_from_yesterday_after_reset(self):
        """Edge case: now is before today's reset but snapshot is from yesterday after reset."""
        now = datetime(2025, 6, 16, 20, 0, 0)  # 20:00 UTC (before 22:00 UTC reset)
        snapshot = datetime(2025, 6, 15, 22, 5, 0)  # Yesterday at 22:05 UTC
        # Most recent reset boundary is yesterday at 22:00 UTC
        # Snapshot is at 22:05 UTC which is after 22:00 UTC -> no reset
        result = should_reset_daily(snapshot, now=now)
        assert result is False

    def test_custom_reset_hour(self):
        """Edge case: custom reset hour (e.g., midnight UTC)."""
        now = datetime(2025, 6, 16, 1, 0, 0)  # 01:00 UTC
        old_snapshot = datetime(2025, 6, 15, 23, 0, 0)  # 23:00 UTC yesterday
        # Reset at midnight UTC: reset_hour=0, tz_offset=0 -> reset_hour_utc = 0
        result = should_reset_daily(
            old_snapshot, now=now, reset_hour=0, tz_offset_hours=0
        )
        assert result is True


# =========================================================
# calculate_btc_volatility
# =========================================================


class TestCalculateBtcVolatility:
    """Tests for calculate_btc_volatility()"""

    def test_stable_prices_low_volatility(self):
        """Happy path: stable prices produce low volatility."""
        candles = [{"close": "100.0"} for _ in range(10)]
        result = calculate_btc_volatility(candles)
        assert result == pytest.approx(0.0)

    def test_volatile_prices_high_volatility(self):
        """Happy path: large price swings produce measurable volatility."""
        candles = [
            {"close": "100"},
            {"close": "110"},
            {"close": "95"},
            {"close": "105"},
            {"close": "90"},
        ]
        result = calculate_btc_volatility(candles)
        assert result > 0.0

    def test_single_candle_returns_zero(self):
        """Edge case: need at least 2 candles for returns."""
        candles = [{"close": "100"}]
        result = calculate_btc_volatility(candles)
        assert result == pytest.approx(0.0)

    def test_empty_candles_returns_zero(self):
        """Failure case: empty list returns 0."""
        result = calculate_btc_volatility([])
        assert result == pytest.approx(0.0)

    def test_candles_with_invalid_prices_skipped(self):
        """Edge case: candles with non-numeric prices are skipped."""
        candles = [
            {"close": "100"},
            {"close": "invalid"},
            {"close": "105"},
        ]
        result = calculate_btc_volatility(candles)
        # Only 2 valid prices, so one log return
        assert result >= 0.0

    def test_candles_with_zero_prices_skipped(self):
        """Edge case: candles with zero or negative prices are filtered out."""
        candles = [
            {"close": "100"},
            {"close": "0"},
            {"close": "105"},
        ]
        result = calculate_btc_volatility(candles)
        # Zero price is filtered out, so 2 valid candles remain
        assert result >= 0.0

    def test_candles_all_invalid_returns_zero(self):
        """Failure case: all candles have invalid prices."""
        candles = [
            {"close": "bad"},
            {"close": None},
            {"close": "0"},
        ]
        result = calculate_btc_volatility(candles)
        assert result == pytest.approx(0.0)

    def test_custom_price_key(self):
        """Edge case: using a different price key."""
        candles = [
            {"open": "100"},
            {"open": "110"},
            {"open": "105"},
        ]
        result = calculate_btc_volatility(candles, price_key="open")
        assert result > 0.0

    def test_two_candles_returns_positive(self):
        """Edge case: minimum viable input (2 candles)."""
        candles = [{"close": "100"}, {"close": "110"}]
        result = calculate_btc_volatility(candles)
        # log(110/100) = log(1.1) ~ 0.0953, std_dev of a single value = 0
        # Because mean == single_value, variance is 0
        assert result == pytest.approx(0.0)

    def test_three_candles_nonzero_vol(self):
        """Happy path: 3 candles with mixed movement gives nonzero volatility."""
        candles = [{"close": "100"}, {"close": "110"}, {"close": "95"}]
        result = calculate_btc_volatility(candles)
        assert result > 0.0


# =========================================================
# calculate_spread_pct
# =========================================================


class TestCalculateSpreadPct:
    """Tests for calculate_spread_pct()"""

    def test_normal_spread(self):
        """Happy path: normal bid-ask spread."""
        result = calculate_spread_pct(100.0, 100.05)
        assert result == pytest.approx(0.05)

    def test_zero_spread(self):
        """Edge case: bid equals ask (zero spread)."""
        result = calculate_spread_pct(100.0, 100.0)
        assert result == pytest.approx(0.0)

    def test_wide_spread(self):
        """Edge case: very wide spread (1%)."""
        result = calculate_spread_pct(100.0, 101.0)
        assert result == pytest.approx(1.0)

    def test_zero_bid_returns_zero(self):
        """Failure case: zero bid avoids division by zero."""
        result = calculate_spread_pct(0.0, 100.0)
        assert result == pytest.approx(0.0)

    def test_negative_bid_returns_zero(self):
        """Failure case: negative bid returns 0."""
        result = calculate_spread_pct(-50.0, 100.0)
        assert result == pytest.approx(0.0)


# =========================================================
# adjust_size_for_volatility
# =========================================================


class TestAdjustSizeForVolatility:
    """Tests for adjust_size_for_volatility()"""

    def test_below_threshold_no_reduction(self):
        """Happy path: volatility below threshold, size unchanged."""
        result = adjust_size_for_volatility(1.0, 1.5, threshold=2.0, reduction_pct=0.20)
        assert result == pytest.approx(1.0)

    def test_above_threshold_reduces_size(self):
        """Happy path: volatility above threshold, size reduced by 20%."""
        result = adjust_size_for_volatility(1.0, 3.0, threshold=2.0, reduction_pct=0.20)
        assert result == pytest.approx(0.8)

    def test_at_threshold_no_reduction(self):
        """Edge case: volatility exactly at threshold, no reduction."""
        result = adjust_size_for_volatility(1.0, 2.0, threshold=2.0, reduction_pct=0.20)
        assert result == pytest.approx(1.0)

    def test_100_percent_reduction(self):
        """Edge case: 100% reduction results in zero size."""
        result = adjust_size_for_volatility(1.0, 5.0, threshold=2.0, reduction_pct=1.0)
        assert result == pytest.approx(0.0)

    def test_zero_size_stays_zero(self):
        """Edge case: reducing zero size still gives zero."""
        result = adjust_size_for_volatility(0.0, 5.0, threshold=2.0, reduction_pct=0.20)
        assert result == pytest.approx(0.0)

    def test_large_size_reduction(self):
        """Happy path: larger position, 20% reduction."""
        result = adjust_size_for_volatility(10.0, 3.5, threshold=2.0, reduction_pct=0.20)
        assert result == pytest.approx(8.0)
