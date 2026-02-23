"""
Tests for backend/app/indicator_calculator.py

Covers the IndicatorCalculator class including:
- calculate_rsi
- calculate_sma
- calculate_ema
- calculate_macd
- calculate_bollinger_bands
- calculate_stochastic
- calculate_all_indicators (integration with required_indicators routing)
- extract_required_indicators
- _get_indicator_key
"""

import pytest

from app.indicator_calculator import IndicatorCalculator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def calc():
    """Fresh IndicatorCalculator instance."""
    return IndicatorCalculator()


@pytest.fixture
def trending_up_prices():
    """50 prices trending upward for indicator calculations."""
    return [100.0 + i * 0.5 for i in range(50)]


@pytest.fixture
def trending_down_prices():
    """50 prices trending downward."""
    return [150.0 - i * 0.5 for i in range(50)]


@pytest.fixture
def flat_prices():
    """50 flat prices (all the same)."""
    return [100.0] * 50


@pytest.fixture
def sample_candle_list():
    """Generate a list of 40 candles with increasing close prices."""
    candles = []
    for i in range(40):
        price = 100.0 + i * 0.5
        candles.append({
            "open": price - 0.1,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price,
            "volume": 100.0 + i,
            "start": 1000000 + i * 300,
        })
    return candles


# ---------------------------------------------------------------------------
# calculate_rsi
# ---------------------------------------------------------------------------


class TestCalculateRSI:
    """Tests for calculate_rsi()."""

    def test_rsi_trending_up(self, calc, trending_up_prices):
        """Happy path: RSI should be high for uptrending prices."""
        rsi = calc.calculate_rsi(trending_up_prices, 14)
        assert rsi is not None
        assert rsi > 70  # Strong uptrend

    def test_rsi_trending_down(self, calc, trending_down_prices):
        """Happy path: RSI should be low for downtrending prices."""
        rsi = calc.calculate_rsi(trending_down_prices, 14)
        assert rsi is not None
        assert rsi < 30  # Strong downtrend

    def test_rsi_not_enough_data(self, calc):
        """Failure: not enough data for RSI calculation."""
        prices = [100.0] * 10  # Only 10 prices, need period + 1 = 15
        assert calc.calculate_rsi(prices, 14) is None

    def test_rsi_minimum_data(self, calc):
        """Edge case: exactly period + 1 data points."""
        # 15 prices for period=14
        prices = [100.0 + i for i in range(15)]
        rsi = calc.calculate_rsi(prices, 14)
        assert rsi is not None
        assert 0 <= rsi <= 100

    def test_rsi_all_gains_returns_100(self, calc):
        """Edge case: all prices go up -> RSI = 100."""
        prices = [float(i) for i in range(1, 20)]  # 1, 2, 3, ..., 19
        rsi = calc.calculate_rsi(prices, 14)
        assert rsi == 100.0

    def test_rsi_range_bounded(self, calc, trending_up_prices):
        """Edge case: RSI is always between 0 and 100."""
        rsi = calc.calculate_rsi(trending_up_prices, 14)
        assert 0 <= rsi <= 100


# ---------------------------------------------------------------------------
# calculate_sma
# ---------------------------------------------------------------------------


class TestCalculateSMA:
    """Tests for calculate_sma()."""

    def test_sma_basic(self, calc):
        """Happy path: SMA of known values."""
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = calc.calculate_sma(prices, 5)
        assert result == pytest.approx(30.0)

    def test_sma_uses_last_n_prices(self, calc):
        """Happy path: SMA uses only the last N prices."""
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = calc.calculate_sma(prices, 3)
        # Average of last 3: (30 + 40 + 50) / 3 = 40
        assert result == pytest.approx(40.0)

    def test_sma_not_enough_data(self, calc):
        """Failure: not enough data returns None."""
        prices = [10.0, 20.0]
        assert calc.calculate_sma(prices, 5) is None

    def test_sma_exact_period_length(self, calc):
        """Edge case: exactly period number of prices."""
        prices = [10.0, 20.0, 30.0]
        result = calc.calculate_sma(prices, 3)
        assert result == pytest.approx(20.0)

    def test_sma_single_value(self, calc):
        """Edge case: period of 1."""
        prices = [42.0, 100.0]
        result = calc.calculate_sma(prices, 1)
        assert result == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# calculate_ema
# ---------------------------------------------------------------------------


class TestCalculateEMA:
    """Tests for calculate_ema()."""

    def test_ema_basic(self, calc):
        """Happy path: EMA with enough data returns a valid number."""
        prices = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        result = calc.calculate_ema(prices, 5)
        assert result is not None
        # EMA should be >= SMA due to recency weighting on an uptrend
        sma = calc.calculate_sma(prices, 5)
        assert result >= sma

    def test_ema_not_enough_data(self, calc):
        """Failure: not enough data returns None."""
        prices = [10.0, 20.0]
        assert calc.calculate_ema(prices, 5) is None

    def test_ema_exact_period_length(self, calc):
        """Edge case: exactly period prices -> EMA equals SMA (no smoothing applied)."""
        prices = [10.0, 20.0, 30.0]
        ema = calc.calculate_ema(prices, 3)
        sma = calc.calculate_sma(prices, 3)
        # With exactly period prices, EMA start is SMA and no further smoothing
        assert ema == pytest.approx(sma)

    def test_ema_weights_recent_more(self, calc):
        """Happy path: EMA weights recent prices more than SMA does."""
        # Prices with a big jump at the end
        prices = [10.0] * 10 + [100.0]
        ema = calc.calculate_ema(prices, 10)
        sma = calc.calculate_sma(prices, 10)
        # EMA should react faster to the recent jump
        assert ema > sma


# ---------------------------------------------------------------------------
# calculate_macd
# ---------------------------------------------------------------------------


class TestCalculateMACD:
    """Tests for calculate_macd()."""

    def test_macd_basic(self, calc, trending_up_prices):
        """Happy path: MACD returns valid triple for trending data."""
        macd_line, signal_line, histogram = calc.calculate_macd(trending_up_prices, 12, 26, 9)
        assert macd_line is not None
        assert signal_line is not None
        assert histogram is not None
        # In an uptrend, fast EMA > slow EMA -> MACD line > 0
        assert macd_line > 0

    def test_macd_not_enough_data(self, calc):
        """Failure: not enough data returns (None, None, None)."""
        prices = [100.0] * 20  # Need slow_period + signal_period = 35
        result = calc.calculate_macd(prices, 12, 26, 9)
        assert result == (None, None, None)

    def test_macd_histogram_is_difference(self, calc, trending_up_prices):
        """Happy path: histogram = macd_line - signal_line."""
        macd_line, signal_line, histogram = calc.calculate_macd(trending_up_prices, 12, 26, 9)
        assert histogram == pytest.approx(macd_line - signal_line)

    def test_macd_flat_prices_near_zero(self, calc, flat_prices):
        """Edge case: flat prices produce MACD near zero."""
        macd_line, signal_line, histogram = calc.calculate_macd(flat_prices, 12, 26, 9)
        assert macd_line == pytest.approx(0.0, abs=0.01)

    def test_macd_downtrend_negative(self, calc, trending_down_prices):
        """Happy path: downtrend produces negative MACD."""
        macd_line, signal_line, histogram = calc.calculate_macd(trending_down_prices, 12, 26, 9)
        assert macd_line is not None
        assert macd_line < 0


# ---------------------------------------------------------------------------
# calculate_bollinger_bands
# ---------------------------------------------------------------------------


class TestCalculateBollingerBands:
    """Tests for calculate_bollinger_bands()."""

    def test_bb_basic(self, calc):
        """Happy path: bands bracket the price."""
        prices = [100.0 + i * 0.1 for i in range(30)]
        upper, middle, lower = calc.calculate_bollinger_bands(prices, 20, 2.0)
        assert upper is not None
        assert middle is not None
        assert lower is not None
        assert upper > middle > lower

    def test_bb_not_enough_data(self, calc):
        """Failure: not enough data returns (None, None, None)."""
        prices = [100.0] * 10
        assert calc.calculate_bollinger_bands(prices, 20, 2.0) == (None, None, None)

    def test_bb_flat_prices_bands_converge(self, calc):
        """Edge case: flat prices make upper == middle == lower."""
        prices = [100.0] * 25
        upper, middle, lower = calc.calculate_bollinger_bands(prices, 20, 2.0)
        assert upper == pytest.approx(100.0)
        assert middle == pytest.approx(100.0)
        assert lower == pytest.approx(100.0)

    def test_bb_middle_is_sma(self, calc):
        """Happy path: middle band equals SMA."""
        prices = [100.0 + i for i in range(25)]
        upper, middle, lower = calc.calculate_bollinger_bands(prices, 20, 2.0)
        sma = calc.calculate_sma(prices, 20)
        assert middle == pytest.approx(sma)

    def test_bb_higher_std_dev_wider_bands(self, calc):
        """Edge case: higher std_dev widens bands."""
        prices = [100.0 + i for i in range(25)]
        u1, m1, l1 = calc.calculate_bollinger_bands(prices, 20, 1.0)
        u2, m2, l2 = calc.calculate_bollinger_bands(prices, 20, 3.0)
        # 3x std dev bands should be wider than 1x
        assert (u2 - l2) > (u1 - l1)


# ---------------------------------------------------------------------------
# calculate_stochastic
# ---------------------------------------------------------------------------


class TestCalculateStochastic:
    """Tests for calculate_stochastic()."""

    def test_stochastic_basic(self, calc):
        """Happy path: stochastic with enough data returns k and d."""
        highs = [100.0 + i for i in range(20)]
        lows = [90.0 + i for i in range(20)]
        closes = [95.0 + i for i in range(20)]
        k, d = calc.calculate_stochastic(highs, lows, closes, 14, 3)
        assert k is not None
        assert 0 <= k <= 100

    def test_stochastic_not_enough_data(self, calc):
        """Failure: not enough data returns (None, None)."""
        highs = [100.0] * 5
        lows = [90.0] * 5
        closes = [95.0] * 5
        assert calc.calculate_stochastic(highs, lows, closes, 14, 3) == (None, None)

    def test_stochastic_flat_prices_returns_50(self, calc):
        """Edge case: all same prices -> k = 50.0 (highest == lowest)."""
        highs = [100.0] * 20
        lows = [100.0] * 20
        closes = [100.0] * 20
        k, d = calc.calculate_stochastic(highs, lows, closes, 14, 3)
        assert k == 50.0

    def test_stochastic_at_high_returns_100(self, calc):
        """Edge case: close at highest high -> k = 100."""
        highs = [100.0] * 14
        lows = [90.0] * 14
        closes = [95.0] * 13 + [100.0]  # Last close = highest high
        k, d = calc.calculate_stochastic(highs, lows, closes, 14, 3)
        assert k == pytest.approx(100.0)

    def test_stochastic_at_low_returns_0(self, calc):
        """Edge case: close at lowest low -> k = 0."""
        highs = [100.0] * 14
        lows = [90.0] * 14
        closes = [95.0] * 13 + [90.0]  # Last close = lowest low
        k, d = calc.calculate_stochastic(highs, lows, closes, 14, 3)
        assert k == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# calculate_all_indicators
# ---------------------------------------------------------------------------


class TestCalculateAllIndicators:
    """Tests for calculate_all_indicators()."""

    def test_empty_candles_returns_empty(self, calc):
        """Edge case: empty candle list returns empty dict."""
        assert calc.calculate_all_indicators([], set()) == {}

    def test_always_includes_price_and_volume(self, calc, sample_candle_list):
        """Happy path: price and volume always included from last candle."""
        result = calc.calculate_all_indicators(sample_candle_list, set())
        assert "price" in result
        assert "volume" in result
        assert result["price"] == float(sample_candle_list[-1]["close"])

    def test_rsi_indicator_calculated(self, calc, sample_candle_list):
        """Happy path: RSI is calculated when requested."""
        result = calc.calculate_all_indicators(sample_candle_list, {"rsi_14"})
        assert "rsi_14" in result
        assert 0 <= result["rsi_14"] <= 100

    def test_sma_indicator_calculated(self, calc, sample_candle_list):
        """Happy path: SMA is calculated when requested."""
        result = calc.calculate_all_indicators(sample_candle_list, {"sma_20"})
        assert "sma_20" in result

    def test_ema_indicator_calculated(self, calc, sample_candle_list):
        result = calc.calculate_all_indicators(sample_candle_list, {"ema_10"})
        assert "ema_10" in result

    def test_macd_indicator_calculated(self, calc, sample_candle_list):
        result = calc.calculate_all_indicators(sample_candle_list, {"macd_12_26_9"})
        assert "macd_12_26_9" in result
        assert "macd_signal_12_26_9" in result
        assert "macd_histogram_12_26_9" in result

    def test_bollinger_bands_calculated(self, calc, sample_candle_list):
        result = calc.calculate_all_indicators(sample_candle_list, {"bb_upper_20_2"})
        assert "bb_upper_20_2" in result
        assert "bb_middle_20_2" in result
        assert "bb_lower_20_2" in result

    def test_stochastic_calculated(self, calc, sample_candle_list):
        result = calc.calculate_all_indicators(sample_candle_list, {"stoch_k_14_3"})
        assert "stoch_k_14_3" in result
        assert "stoch_d_14_3" in result

    def test_volume_rsi_calculated(self, calc, sample_candle_list):
        result = calc.calculate_all_indicators(sample_candle_list, {"volume_rsi_14"})
        assert "volume_rsi_14" in result

    def test_gap_fill_pct_no_synthetic(self, calc, sample_candle_list):
        """Happy path: no synthetic candles -> gap_fill_pct = 0."""
        result = calc.calculate_all_indicators(sample_candle_list, {"gap_fill_pct"})
        assert result["gap_fill_pct"] == pytest.approx(0.0)

    def test_gap_fill_pct_with_synthetic(self, calc):
        """Happy path: synthetic candles counted in gap_fill_pct."""
        candles = [
            {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 50, "_synthetic": False},
            {"open": 100, "high": 100, "low": 100, "close": 100, "volume": 0, "_synthetic": True},
            {"open": 100, "high": 101, "low": 99, "close": 101, "volume": 60},
            {"open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 70},  # current (incomplete)
        ]
        result = calc.calculate_all_indicators(candles, {"gap_fill_pct"})
        # 3 closed candles: 1 synthetic out of 3 = 33.33%
        assert result["gap_fill_pct"] == pytest.approx(33.333, abs=0.01)

    def test_gap_fill_pct_aggregated_candles(self, calc):
        """Edge case: aggregated candles use _synthetic_count/_synthetic_total."""
        candles = [
            {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 50,
             "_synthetic_count": 1, "_synthetic_total": 3},
            {"open": 100, "high": 101, "low": 99, "close": 101, "volume": 60},
            {"open": 101, "high": 102, "low": 100, "close": 101.5, "volume": 70},  # current
        ]
        result = calc.calculate_all_indicators(candles, {"gap_fill_pct"})
        # Closed: candle 0 (1 syn / 3 total) + candle 1 (0 syn / 1 total) = 1/4 = 25%
        assert result["gap_fill_pct"] == pytest.approx(25.0)

    def test_not_enough_closed_candles(self, calc):
        """Edge case: only one candle means no closed candles -> minimal result."""
        candles = [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 50}]
        result = calc.calculate_all_indicators(candles, {"rsi_14"})
        assert "price" in result
        assert "rsi_14" not in result  # Not enough data

    def test_calculate_previous_indicators(self, calc, sample_candle_list):
        """Happy path: calculate_previous adds prev_ prefix keys."""
        result = calc.calculate_all_indicators(sample_candle_list, {"rsi_14"}, calculate_previous=True)
        assert "rsi_14" in result
        assert "prev_rsi_14" in result

    def test_calculate_previous_needs_4_candles(self, calc):
        """Edge case: fewer than 4 candles means no prev_ keys."""
        candles = [
            {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 50},
            {"open": 101, "high": 102, "low": 100, "close": 101, "volume": 60},
            {"open": 102, "high": 103, "low": 101, "close": 102, "volume": 70},
        ]
        result = calc.calculate_all_indicators(candles, {"sma_2"}, calculate_previous=True)
        # Only 3 candles, prev_ not calculated
        assert not any(k.startswith("prev_") for k in result)


# ---------------------------------------------------------------------------
# extract_required_indicators
# ---------------------------------------------------------------------------


class TestExtractRequiredIndicators:
    """Tests for extract_required_indicators()."""

    def test_buy_conditions(self, calc):
        """Happy path: extracts indicators from buy_conditions."""
        config = {
            "buy_conditions": {
                "conditions": [
                    {"indicator": "rsi", "indicator_params": {"period": 14}},
                ]
            }
        }
        result = calc.extract_required_indicators(config)
        assert "rsi_14" in result

    def test_sell_conditions(self, calc):
        """Happy path: extracts indicators from sell_conditions."""
        config = {
            "sell_conditions": {
                "conditions": [
                    {"indicator": "macd", "indicator_params": {
                        "fast_period": 12, "slow_period": 26, "signal_period": 9
                    }},
                ]
            }
        }
        result = calc.extract_required_indicators(config)
        assert "macd_12_26_9" in result

    def test_indicator_comparison(self, calc):
        """Happy path: also extracts compare_indicator."""
        config = {
            "buy_conditions": {
                "conditions": [
                    {
                        "indicator": "rsi",
                        "indicator_params": {"period": 14},
                        "value_type": "indicator",
                        "compare_indicator": "sma",
                        "compare_indicator_params": {"period": 20},
                    }
                ]
            }
        }
        result = calc.extract_required_indicators(config)
        assert "rsi_14" in result
        assert "sma_20" in result

    def test_sub_groups(self, calc):
        """Happy path: recursively processes sub_groups."""
        config = {
            "buy_conditions": {
                "conditions": [
                    {"indicator": "rsi", "indicator_params": {"period": 14}},
                ],
                "sub_groups": [
                    {
                        "conditions": [
                            {"indicator": "ema", "indicator_params": {"period": 50}},
                        ]
                    }
                ]
            }
        }
        result = calc.extract_required_indicators(config)
        assert "rsi_14" in result
        assert "ema_50" in result

    def test_empty_config(self, calc):
        """Edge case: empty config returns empty set."""
        assert calc.extract_required_indicators({}) == set()


# ---------------------------------------------------------------------------
# _get_indicator_key
# ---------------------------------------------------------------------------


class TestGetIndicatorKey:
    """Tests for _get_indicator_key()."""

    def test_price(self, calc):
        assert calc._get_indicator_key({"indicator": "price"}) == "price"

    def test_volume(self, calc):
        assert calc._get_indicator_key({"indicator": "volume"}) == "volume"

    def test_rsi_default(self, calc):
        assert calc._get_indicator_key({"indicator": "rsi"}) == "rsi_14"

    def test_rsi_custom(self, calc):
        assert calc._get_indicator_key({"indicator": "rsi", "indicator_params": {"period": 7}}) == "rsi_7"

    def test_macd_default(self, calc):
        assert calc._get_indicator_key({"indicator": "macd"}) == "macd_12_26_9"

    def test_macd_signal(self, calc):
        assert calc._get_indicator_key({"indicator": "macd_signal"}) == "macd_12_26_9"

    def test_macd_histogram(self, calc):
        assert calc._get_indicator_key({"indicator": "macd_histogram"}) == "macd_12_26_9"

    def test_sma(self, calc):
        assert calc._get_indicator_key({"indicator": "sma", "indicator_params": {"period": 50}}) == "sma_50"

    def test_ema(self, calc):
        assert calc._get_indicator_key({"indicator": "ema", "indicator_params": {"period": 20}}) == "ema_20"

    def test_bollinger_upper(self, calc):
        cond = {"indicator": "bollinger_upper", "indicator_params": {"period": 20, "std_dev": 2}}
        assert calc._get_indicator_key(cond) == "bb_upper_20_2"

    def test_stochastic_k(self, calc):
        cond = {"indicator": "stochastic_k", "indicator_params": {"k_period": 14, "d_period": 3}}
        assert calc._get_indicator_key(cond) == "stoch_k_14_3"

    def test_volume_rsi(self, calc):
        cond = {"indicator": "volume_rsi", "indicator_params": {"period": 14}}
        assert calc._get_indicator_key(cond) == "volume_rsi_14"

    def test_unknown_indicator(self, calc):
        """Failure: unknown indicator returns 'unknown'."""
        assert calc._get_indicator_key({"indicator": "foobar"}) == "unknown"
