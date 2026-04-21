"""
Tests for QFLIndicatorEvaluator and _find_bases
"""

import pytest

from app.indicators.qfl_indicator import (
    QFLIndicatorEvaluator,
    QFLParams,
    _find_bases,
)


def _make_candle(high, low, close, volume=1000.0):
    return {"open": close, "high": high, "low": low, "close": close, "volume": volume}


# ---------------------------------------------------------------------------
# _find_bases
# ---------------------------------------------------------------------------


class TestFindBases:
    def test_simple_pivot_low_with_strong_bounce(self):
        """A clear local low followed by a big bounce should be found as a base."""
        # 7 candles: descending to pivot, then sharp rebound
        candles = (
            [_make_candle(105, 103, 104)] * 3           # before pivot
            + [_make_candle(99, 95, 96)]                 # pivot low at 95
            + [_make_candle(108, 100, 107)]              # rebound start
            + [_make_candle(115, 106, 114)]              # big bounce
            + [_make_candle(112, 109, 110)]              # settle
        )
        bases = _find_bases(candles, bounce_pct=5.0, pivot_window=2)
        # bounce from 95 to 115 = ~21% ≥ 5% → should find it
        assert 95.0 in bases

    def test_weak_bounce_not_a_base(self):
        """If the bounce is below bounce_pct, it should not be identified as a base."""
        candles = (
            [_make_candle(100, 98, 99)] * 3
            + [_make_candle(97, 95, 96)]      # pivot low 95
            + [_make_candle(97, 95, 96.5)]    # tiny bounce
            + [_make_candle(97, 95, 96.8)]
            + [_make_candle(97, 95, 96.5)]
        )
        # Bounce from 95 to 97 = ~2.1%, less than 5%
        bases = _find_bases(candles, bounce_pct=5.0, pivot_window=2)
        assert 95.0 not in bases

    def test_not_a_pivot_because_neighbour_is_lower(self):
        """If a neighbour has a lower low, the candidate is not a pivot."""
        candles = (
            [_make_candle(100, 99, 99.5)] * 2
            + [_make_candle(98, 96, 97)]      # low=96
            + [_make_candle(95, 93, 94)]      # lower low=93 → makes 96 not a pivot
            + [_make_candle(100, 94, 99)]     # bounce
            + [_make_candle(110, 99, 108)]
            + [_make_candle(109, 105, 107)]
        )
        bases = _find_bases(candles, bounce_pct=5.0, pivot_window=1)
        # 96 is NOT a pivot because 93 is lower (within pivot_window=1)
        assert 96.0 not in bases

    def test_empty_candles(self):
        assert _find_bases([], bounce_pct=3.0, pivot_window=3) == []

    def test_no_valid_pivot_returns_empty(self):
        # All candles at same price — no pivot
        candles = [_make_candle(100, 100, 100)] * 10
        assert _find_bases(candles, bounce_pct=3.0, pivot_window=2) == []


# ---------------------------------------------------------------------------
# QFLIndicatorEvaluator.evaluate
# ---------------------------------------------------------------------------


class TestQFLEvaluate:
    def setup_method(self):
        self.evaluator = QFLIndicatorEvaluator()
        self.params = QFLParams(
            base_timeframe="ONE_HOUR",
            crack_timeframe="ONE_HOUR",
            lookback_candles=200,
            bounce_pct=3.0,
            crack_pct=2.0,
            pivot_window=2,
        )

    def test_insufficient_candles_returns_zero(self):
        result = self.evaluator.evaluate([], self.params)
        assert result.signal == 0
        assert result.rejection_reason is not None

    def test_no_bases_found_returns_zero(self):
        # Monotonic candles — no pivot
        candles = [_make_candle(100 - i * 0.1, 99 - i * 0.1, 99.5 - i * 0.1) for i in range(20)]
        result = self.evaluator.evaluate(candles, self.params)
        assert result.signal == 0

    def test_happy_path_crack_detected(self):
        """
        Setup a clear base at 95, strong bounce to 115, then price cracks to 92
        (3.2% below base 95, crack_pct=2%).
        """
        history = (
            [_make_candle(103, 101, 102)] * 3      # before pivot
            + [_make_candle(97, 95, 96)]            # pivot low = 95
            + [_make_candle(106, 96, 104)]          # bounce start
            + [_make_candle(115, 104, 113)]         # strong bounce (+20%)
            + [_make_candle(112, 109, 110)] * 5    # consolidation
        )
        # Current (incomplete) candle: price cracked to 92 (< 95 * 0.98 = 93.1)
        current = _make_candle(95, 91, 92)
        candles = history + [current]

        result = self.evaluator.evaluate(candles, self.params)

        assert result.signal == 1
        assert result.cracked_base is not None
        assert result.cracked_base == pytest.approx(95.0)
        assert result.crack_depth_pct is not None
        assert result.crack_depth_pct > 0

    def test_price_above_base_no_signal(self):
        """Price is above the base — no crack."""
        history = (
            [_make_candle(103, 101, 102)] * 3
            + [_make_candle(97, 95, 96)]
            + [_make_candle(106, 96, 104)]
            + [_make_candle(115, 104, 113)]
            + [_make_candle(112, 109, 110)] * 5
        )
        current = _make_candle(110, 97, 98)  # price at 98, just above base 95
        candles = history + [current]

        result = self.evaluator.evaluate(candles, self.params)
        assert result.signal == 0

    def test_price_at_base_level_not_enough_crack(self):
        """Price is at the base exactly — needs crack_pct below, not just touching."""
        history = (
            [_make_candle(103, 101, 102)] * 3
            + [_make_candle(97, 95, 96)]
            + [_make_candle(106, 96, 104)]
            + [_make_candle(115, 104, 113)]
            + [_make_candle(112, 109, 110)] * 5
        )
        current = _make_candle(96, 94, 95.0)  # exactly at base, not 2% below
        candles = history + [current]

        result = self.evaluator.evaluate(candles, self.params)
        assert result.signal == 0  # need 2% below = 93.1, price is 95

    def test_result_includes_bases_list(self):
        history = (
            [_make_candle(103, 101, 102)] * 3
            + [_make_candle(97, 95, 96)]
            + [_make_candle(106, 96, 104)]
            + [_make_candle(115, 104, 113)]
            + [_make_candle(112, 109, 110)] * 5
        )
        current = _make_candle(100, 99, 100)
        candles = history + [current]

        result = self.evaluator.evaluate(candles, self.params)
        assert isinstance(result.bases, list)
        assert len(result.bases) >= 1


# ---------------------------------------------------------------------------
# Multi-timeframe evaluate() — base_candles kwarg
# ---------------------------------------------------------------------------


class TestQFLMultiTimeframe:
    def setup_method(self):
        self.evaluator = QFLIndicatorEvaluator()
        self.params = QFLParams(
            base_timeframe="ONE_HOUR",
            crack_timeframe="FIFTEEN_MINUTE",
            lookback_candles=200,
            bounce_pct=5.0,
            crack_pct=2.0,
            pivot_window=2,
        )

    def _base_candles_with_clear_base(self):
        """Higher-TF candles containing a validated base at 95."""
        return (
            [_make_candle(103, 101, 102)] * 3
            + [_make_candle(97, 95, 96)]
            + [_make_candle(106, 96, 104)]
            + [_make_candle(115, 104, 113)]
            + [_make_candle(112, 109, 110)] * 5
        )

    def test_base_candles_used_for_base_identification(self):
        """
        base_candles has a clear base at 95 with a strong bounce.
        crack_candles (lower TF) has a crack to 92 — well below 95 * 0.98.
        Signal should fire using the base from base_candles.
        """
        base_candles = self._base_candles_with_clear_base()
        # crack_candles are flat at 110 (no base would be found here alone)
        crack_candles = [_make_candle(112, 109, 110)] * 5 + [_make_candle(95, 91, 92)]

        result = self.evaluator.evaluate(crack_candles, self.params, base_candles=base_candles)
        assert result.signal == 1
        assert result.cracked_base == pytest.approx(95.0)

    def test_no_base_candles_falls_back_to_crack_candles(self):
        """When base_candles is None, evaluate() uses crack_candles for base detection."""
        candles = self._base_candles_with_clear_base() + [_make_candle(95, 91, 92)]
        result = self.evaluator.evaluate(candles, self.params, base_candles=None)
        assert result.signal == 1

    def test_invalid_setup_base_tf_shorter_than_crack_tf_returns_zero(self):
        """
        base_timeframe < crack_timeframe is an invalid setup.
        QFLParams with base=FIFTEEN_MINUTE, crack=ONE_HOUR should be rejected.
        """
        invalid_params = QFLParams(
            base_timeframe="FIFTEEN_MINUTE",
            crack_timeframe="ONE_HOUR",
            lookback_candles=100,
            bounce_pct=3.0,
            crack_pct=2.0,
        )
        candles = self._base_candles_with_clear_base() + [_make_candle(95, 91, 92)]
        result = self.evaluator.evaluate(candles, invalid_params)
        assert result.signal == 0
        assert result.rejection_reason is not None
        assert "Invalid setup" in result.rejection_reason

    def test_empty_base_candles_returns_zero(self):
        """Passing an empty base_candles list returns 0 with a rejection reason."""
        crack_candles = [_make_candle(95, 91, 92)]
        result = self.evaluator.evaluate(crack_candles, self.params, base_candles=[])
        assert result.signal == 0
        assert result.rejection_reason is not None

    def test_sufficient_base_candles_insufficient_crack_candles(self):
        """Signal requires both candle sets to be present."""
        base_candles = self._base_candles_with_clear_base()
        result = self.evaluator.evaluate([], self.params, base_candles=base_candles)
        assert result.signal == 0
        assert result.rejection_reason is not None


# ---------------------------------------------------------------------------
# QFLParams
# ---------------------------------------------------------------------------


class TestQFLParams:
    def test_defaults(self):
        params = QFLParams()
        assert params.base_timeframe == "ONE_HOUR"
        assert params.crack_timeframe == "FIFTEEN_MINUTE"
        assert params.bounce_pct == 3.0
        assert params.crack_pct == 2.0
        assert params.lookback_candles == 100

    def test_from_config(self):
        params = QFLParams.from_config({
            "qfl_base_timeframe": "FOUR_HOUR",
            "qfl_crack_timeframe": "FIFTEEN_MINUTE",
            "qfl_bounce_pct": 5.0,
            "qfl_crack_pct": 3.0,
            "qfl_lookback_candles": 200,
        })
        assert params.base_timeframe == "FOUR_HOUR"
        assert params.crack_timeframe == "FIFTEEN_MINUTE"
        assert params.bounce_pct == 5.0
        assert params.crack_pct == 3.0
        assert params.lookback_candles == 200

    def test_from_empty_config_uses_defaults(self):
        params = QFLParams.from_config({})
        assert params.bounce_pct == 3.0
        assert params.crack_pct == 2.0
