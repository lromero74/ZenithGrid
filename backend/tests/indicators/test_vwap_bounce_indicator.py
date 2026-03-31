"""
Tests for VWAPBounceIndicatorEvaluator
"""

import pytest

from app.indicators.vwap_bounce_indicator import (
    VWAPBounceIndicatorEvaluator,
    VWAPBounceParams,
    _calculate_vwap,
)


def _make_candle(high, low, close, volume=1000.0, open_=None):
    """Build a minimal candle dict."""
    return {
        "open": open_ if open_ is not None else close,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


# ---------------------------------------------------------------------------
# _calculate_vwap helpers
# ---------------------------------------------------------------------------


class TestCalculateVwap:
    def test_single_candle(self):
        # typical price = (10 + 8 + 9) / 3 = 9
        candles = [_make_candle(high=10, low=8, close=9, volume=100)]
        result = _calculate_vwap(candles)
        assert result == pytest.approx(9.0)

    def test_equal_volume_candles_returns_average_typical_price(self):
        # Two candles with equal volume; VWAP = mean of typical prices
        c1 = _make_candle(high=12, low=10, close=11, volume=200)  # tp = 11
        c2 = _make_candle(high=14, low=12, close=13, volume=200)  # tp = 13
        result = _calculate_vwap([c1, c2])
        assert result == pytest.approx(12.0)

    def test_zero_volume_returns_none(self):
        candles = [_make_candle(high=10, low=8, close=9, volume=0)]
        assert _calculate_vwap(candles) is None

    def test_empty_list_returns_none(self):
        assert _calculate_vwap([]) is None

    def test_higher_volume_candle_skews_vwap(self):
        low_vol = _make_candle(high=10, low=8, close=9, volume=100)   # tp=9
        high_vol = _make_candle(high=20, low=18, close=19, volume=900) # tp=19
        result = _calculate_vwap([low_vol, high_vol])
        # VWAP = (9*100 + 19*900) / 1000 = 18.0
        assert result == pytest.approx(18.0)


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _make_candles(n=10, price=100.0, volume=1000.0):
    """Make n identical closed candles + 1 incomplete (current) candle."""
    closed = [_make_candle(high=price, low=price, close=price, volume=volume) for _ in range(n)]
    incomplete = _make_candle(high=price, low=price, close=price, volume=volume)
    return closed + [incomplete]


# ---------------------------------------------------------------------------
# VWAPBounceIndicatorEvaluator.evaluate_bounce_up
# ---------------------------------------------------------------------------


class TestEvaluateBounceUp:
    def setup_method(self):
        self.evaluator = VWAPBounceIndicatorEvaluator()
        self.params = VWAPBounceParams(timeframe="FIVE_MINUTE")

    def test_insufficient_candles_returns_zero(self):
        result = self.evaluator.evaluate_bounce_up([], self.params)
        assert result.signal == 0
        assert result.rejection_reason is not None

    def test_exactly_three_candles_is_insufficient(self):
        candles = [_make_candle(100, 100, 100)] * 3
        result = self.evaluator.evaluate_bounce_up(candles, self.params)
        assert result.signal == 0

    def test_happy_path_bounce_up_detected(self):
        """
        Setup: VWAP ≈ 100 (all history at 100).
        Penultimate closed candle: high=101, low=98, close=99 → low(98) < VWAP(100): retest ✓
        Last closed candle: high=103, low=100, close=102 → close(102) > VWAP(100): confirm ✓
        Current (incomplete): doesn't matter
        """
        history = [_make_candle(high=100, low=100, close=100, volume=1000) for _ in range(8)]
        retest = _make_candle(high=101, low=98, close=99, volume=1000)    # wick below VWAP
        confirm = _make_candle(high=103, low=100, close=102, volume=1000)  # closed above VWAP
        incomplete = _make_candle(high=103, low=101, close=102, volume=500)
        candles = history + [retest, confirm, incomplete]

        result = self.evaluator.evaluate_bounce_up(candles, self.params)

        assert result.signal == 1
        assert result.retest_low is not None
        assert result.confirm_close is not None
        assert result.confirm_close > result.vwap

    def test_retest_low_exactly_at_vwap_counts(self):
        """Low == VWAP (exact touch) should still trigger."""
        vwap_price = 100.0
        history = [_make_candle(high=vwap_price, low=vwap_price, close=vwap_price, volume=1000) for _ in range(8)]
        retest = _make_candle(high=101, low=vwap_price, close=100.5, volume=1000)  # low == VWAP
        confirm = _make_candle(high=103, low=100.5, close=102, volume=1000)
        incomplete = _make_candle(high=103, low=101, close=102, volume=500)
        candles = history + [retest, confirm, incomplete]

        result = self.evaluator.evaluate_bounce_up(candles, self.params)
        assert result.signal == 1

    def test_no_retest_returns_zero(self):
        """If the retest candle's low is above VWAP, no bounce detected."""
        vwap_price = 100.0
        history = [_make_candle(high=vwap_price, low=vwap_price, close=vwap_price, volume=1000) for _ in range(8)]
        # Retest candle stays above VWAP (low=101)
        no_retest = _make_candle(high=103, low=101, close=102, volume=1000)
        confirm = _make_candle(high=105, low=102, close=104, volume=1000)
        incomplete = _make_candle(high=105, low=103, close=104, volume=500)
        candles = history + [no_retest, confirm, incomplete]

        result = self.evaluator.evaluate_bounce_up(candles, self.params)
        assert result.signal == 0

    def test_confirm_close_below_vwap_returns_zero(self):
        """Retest happened but price didn't close back above VWAP."""
        vwap_price = 100.0
        history = [_make_candle(high=vwap_price, low=vwap_price, close=vwap_price, volume=1000) for _ in range(8)]
        retest = _make_candle(high=101, low=98, close=99, volume=1000)   # wick below VWAP ✓
        bad_confirm = _make_candle(high=100, low=96, close=97, volume=1000)  # closed below VWAP ✗
        incomplete = _make_candle(high=100, low=97, close=98, volume=500)
        candles = history + [retest, bad_confirm, incomplete]

        result = self.evaluator.evaluate_bounce_up(candles, self.params)
        assert result.signal == 0


# ---------------------------------------------------------------------------
# VWAPBounceIndicatorEvaluator.evaluate_bounce_down
# ---------------------------------------------------------------------------


class TestEvaluateBounceDown:
    def setup_method(self):
        self.evaluator = VWAPBounceIndicatorEvaluator()
        self.params = VWAPBounceParams(timeframe="FIVE_MINUTE")

    def test_insufficient_candles_returns_zero(self):
        result = self.evaluator.evaluate_bounce_down([], self.params)
        assert result.signal == 0

    def test_happy_path_bounce_down_detected(self):
        """
        VWAP ≈ 100.
        Penultimate closed: high=103, low=99, close=101 → high(103) > VWAP: retest ✓
        Last closed: high=100, low=96, close=97 → close(97) < VWAP: confirm ✓
        """
        history = [_make_candle(high=100, low=100, close=100, volume=1000) for _ in range(8)]
        retest = _make_candle(high=103, low=99, close=101, volume=1000)   # wick above VWAP
        confirm = _make_candle(high=100, low=96, close=97, volume=1000)    # closed below VWAP
        incomplete = _make_candle(high=100, low=96, close=97, volume=500)
        candles = history + [retest, confirm, incomplete]

        result = self.evaluator.evaluate_bounce_down(candles, self.params)

        assert result.signal == 1
        assert result.retest_high is not None
        assert result.confirm_close is not None
        assert result.confirm_close < result.vwap

    def test_retest_high_exactly_at_vwap_counts(self):
        vwap_price = 100.0
        history = [_make_candle(high=vwap_price, low=vwap_price, close=vwap_price, volume=1000) for _ in range(8)]
        retest = _make_candle(high=vwap_price, low=98, close=99, volume=1000)  # high == VWAP
        confirm = _make_candle(high=99, low=96, close=97, volume=1000)
        incomplete = _make_candle(high=99, low=96, close=97, volume=500)
        candles = history + [retest, confirm, incomplete]

        result = self.evaluator.evaluate_bounce_down(candles, self.params)
        assert result.signal == 1

    def test_no_retest_above_vwap_returns_zero(self):
        vwap_price = 100.0
        history = [_make_candle(high=vwap_price, low=vwap_price, close=vwap_price, volume=1000) for _ in range(8)]
        no_retest = _make_candle(high=99, low=97, close=98, volume=1000)  # high(99) < VWAP(100)
        confirm = _make_candle(high=98, low=95, close=96, volume=1000)
        incomplete = _make_candle(high=98, low=95, close=96, volume=500)
        candles = history + [no_retest, confirm, incomplete]

        result = self.evaluator.evaluate_bounce_down(candles, self.params)
        assert result.signal == 0

    def test_confirm_close_above_vwap_returns_zero(self):
        vwap_price = 100.0
        history = [_make_candle(high=vwap_price, low=vwap_price, close=vwap_price, volume=1000) for _ in range(8)]
        retest = _make_candle(high=103, low=99, close=101, volume=1000)   # wick above ✓
        bad_confirm = _make_candle(high=104, low=100, close=102, volume=1000)  # closed above ✗
        incomplete = _make_candle(high=104, low=101, close=103, volume=500)
        candles = history + [retest, bad_confirm, incomplete]

        result = self.evaluator.evaluate_bounce_down(candles, self.params)
        assert result.signal == 0


# ---------------------------------------------------------------------------
# VWAPBounceParams.from_config
# ---------------------------------------------------------------------------


class TestVWAPBounceParams:
    def test_defaults(self):
        params = VWAPBounceParams()
        assert params.timeframe == "FIVE_MINUTE"

    def test_from_config(self):
        params = VWAPBounceParams.from_config({"timeframe": "FIFTEEN_MINUTE"})
        assert params.timeframe == "FIFTEEN_MINUTE"

    def test_from_empty_config(self):
        params = VWAPBounceParams.from_config({})
        assert params.timeframe == "FIVE_MINUTE"
