"""
Tests for backend/app/utils/candle_utils.py

Covers:
- timeframe_to_seconds
- aggregate_candles
- prepare_market_context
- fill_candle_gaps
- calculate_bot_check_interval
- next_check_time_aligned
- get_timeframes_for_phases
"""

import pytest

from app.utils.candle_utils import (
    TIMEFRAME_MAP,
    timeframe_to_seconds,
    aggregate_candles,
    prepare_market_context,
    fill_candle_gaps,
    calculate_bot_check_interval,
    next_check_time_aligned,
    get_timeframes_for_phases,
)


# ---------------------------------------------------------------------------
# timeframe_to_seconds
# ---------------------------------------------------------------------------


class TestTimeframeToSeconds:
    """Tests for timeframe_to_seconds()."""

    def test_known_timeframe(self):
        """Happy path: known timeframe returns correct seconds."""
        assert timeframe_to_seconds("ONE_MINUTE") == 60
        assert timeframe_to_seconds("FIVE_MINUTE") == 300
        assert timeframe_to_seconds("ONE_HOUR") == 3600
        assert timeframe_to_seconds("ONE_DAY") == 86400

    def test_synthetic_timeframes(self):
        """Happy path: synthetic timeframes are in the map."""
        assert timeframe_to_seconds("THREE_MINUTE") == 180
        assert timeframe_to_seconds("TEN_MINUTE") == 600
        assert timeframe_to_seconds("TWO_DAY") == 172800
        assert timeframe_to_seconds("ONE_WEEK") == 604800

    def test_unknown_timeframe_defaults_to_300(self):
        """Edge case: unknown timeframe defaults to 5 minutes (300)."""
        assert timeframe_to_seconds("UNKNOWN") == 300
        assert timeframe_to_seconds("") == 300

    def test_all_timeframes_in_map_are_positive(self):
        """Edge case: all timeframe values are positive integers."""
        for key, value in TIMEFRAME_MAP.items():
            assert value > 0, f"Timeframe {key} has non-positive value {value}"


# ---------------------------------------------------------------------------
# aggregate_candles
# ---------------------------------------------------------------------------


class TestAggregateCandles:
    """Tests for aggregate_candles()."""

    def test_aggregate_basic(self):
        """Happy path: aggregate 3 candles into 1."""
        candles = [
            {"start": 0, "open": 100, "high": 110, "low": 90, "close": 105, "volume": 50},
            {"start": 60, "open": 105, "high": 115, "low": 95, "close": 108, "volume": 60},
            {"start": 120, "open": 108, "high": 120, "low": 88, "close": 112, "volume": 70},
        ]
        result = aggregate_candles(candles, 3)
        assert len(result) == 1
        assert result[0]["open"] == 100         # First candle's open
        assert result[0]["high"] == 120.0       # Max of all highs
        assert result[0]["low"] == 88.0         # Min of all lows
        assert result[0]["close"] == 112        # Last candle's close
        assert result[0]["volume"] == pytest.approx(180.0)  # Sum of volumes

    def test_aggregate_factor_1_returns_same(self):
        """Edge case: factor 1 returns same candles."""
        candles = [
            {"start": 0, "open": 100, "high": 110, "low": 90, "close": 105, "volume": 50},
        ]
        result = aggregate_candles(candles, 1)
        assert result == candles

    def test_aggregate_empty_list(self):
        """Edge case: empty list returns empty list."""
        assert aggregate_candles([], 3) == []

    def test_aggregate_none_candles(self):
        """Edge case: None returns None (passthrough)."""
        result = aggregate_candles(None, 3)
        assert result is None

    def test_aggregate_incomplete_last_group(self):
        """Edge case: not enough candles for final group -> dropped."""
        candles = [
            {"start": 0, "open": 100, "high": 110, "low": 90, "close": 105, "volume": 50},
            {"start": 60, "open": 105, "high": 115, "low": 95, "close": 108, "volume": 60},
            {"start": 120, "open": 108, "high": 120, "low": 88, "close": 112, "volume": 70},
            {"start": 180, "open": 112, "high": 118, "low": 92, "close": 115, "volume": 40},
        ]
        result = aggregate_candles(candles, 3)
        assert len(result) == 1  # Only first 3, last candle dropped

    def test_aggregate_tracks_synthetic_candles(self):
        """Happy path: synthetic candles tracked in aggregated result."""
        candles = [
            {"start": 0, "open": 100, "high": 110, "low": 90, "close": 100, "volume": 50, "_synthetic": False},
            {"start": 60, "open": 100, "high": 100, "low": 100, "close": 100, "volume": 0, "_synthetic": True},
            {"start": 120, "open": 100, "high": 105, "low": 95, "close": 102, "volume": 30, "_synthetic": False},
        ]
        result = aggregate_candles(candles, 3)
        assert len(result) == 1
        assert result[0]["_synthetic_count"] == 1
        assert result[0]["_synthetic_total"] == 3

    def test_aggregate_no_synthetic_no_keys(self):
        """Edge case: no synthetic candles -> no _synthetic keys in result."""
        candles = [
            {"start": 0, "open": 100, "high": 110, "low": 90, "close": 105, "volume": 50},
            {"start": 60, "open": 105, "high": 115, "low": 95, "close": 108, "volume": 60},
            {"start": 120, "open": 108, "high": 120, "low": 88, "close": 112, "volume": 70},
        ]
        result = aggregate_candles(candles, 3)
        assert "_synthetic_count" not in result[0]
        assert "_synthetic_total" not in result[0]


# ---------------------------------------------------------------------------
# prepare_market_context
# ---------------------------------------------------------------------------


class TestPrepareMarketContext:
    """Tests for prepare_market_context()."""

    def test_basic_context(self):
        """Happy path: correct metrics from candle data."""
        candles = [
            {"open": 95, "high": 100, "low": 90, "close": 95},
            {"open": 96, "high": 102, "low": 94, "close": 100},
            {"open": 100, "high": 105, "low": 98, "close": 103},
        ]
        result = prepare_market_context(candles, 103.0)
        assert result["current_price"] == 103.0
        assert result["price_24h_ago"] == 95.0  # First candle's close
        assert result["data_points"] == 3
        assert result["period_high"] == 105.0
        assert result["period_low"] == 90.0

    def test_empty_candles(self):
        """Edge case: no candles returns defaults."""
        result = prepare_market_context([], 50000.0)
        assert result["current_price"] == 50000.0
        assert result["price_change_24h_pct"] == 0.0
        assert result["data_points"] == 0
        assert result["volatility"] == 0.0

    def test_candles_with_invalid_close(self):
        """Edge case: candles with non-numeric close are skipped."""
        candles = [
            {"open": 95, "high": 100, "low": 90, "close": "not_a_number"},
            {"open": 96, "high": 102, "low": 94, "close": 100},
        ]
        result = prepare_market_context(candles, 100.0)
        assert result["price_24h_ago"] == 100.0  # Only valid close
        assert result["data_points"] == 2  # Both candles counted

    def test_price_change_calculation(self):
        """Happy path: correct price change percentage."""
        candles = [
            {"open": 95, "high": 100, "low": 90, "close": 100},
            {"open": 100, "high": 110, "low": 95, "close": 110},
        ]
        result = prepare_market_context(candles, 110.0)
        # (110 - 100) / 100 * 100 = 10%
        assert result["price_change_24h_pct"] == pytest.approx(10.0)

    def test_volatility_calculation(self):
        """Happy path: volatility is non-zero for varying prices."""
        candles = [
            {"open": 100, "high": 105, "low": 95, "close": 100},
            {"open": 100, "high": 110, "low": 90, "close": 110},
            {"open": 110, "high": 115, "low": 100, "close": 95},
        ]
        result = prepare_market_context(candles, 95.0)
        assert result["volatility"] > 0

    def test_recent_prices_limited_to_10(self):
        """Edge case: recent_prices is capped at 10."""
        candles = [{"open": 100, "high": 101, "low": 99, "close": 100.0 + i} for i in range(15)]
        result = prepare_market_context(candles, 120.0)
        assert len(result["recent_prices"]) == 10

    def test_all_none_closes(self):
        """Edge case: all closes are None -> fallback to defaults."""
        candles = [
            {"open": 100, "high": 101, "low": 99, "close": None},
            {"open": 100, "high": 101, "low": 99, "close": None},
        ]
        result = prepare_market_context(candles, 50000.0)
        assert result["current_price"] == 50000.0
        assert result["data_points"] == 0
        assert result["volatility"] == 0.0


# ---------------------------------------------------------------------------
# fill_candle_gaps
# ---------------------------------------------------------------------------


class TestFillCandleGaps:
    """Tests for fill_candle_gaps()."""

    def test_no_gaps(self):
        """Happy path: no gaps, candles returned as-is."""
        candles = [
            {"start": 0, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 50},
            {"start": 60, "open": 100, "high": 102, "low": 98, "close": 101, "volume": 60},
            {"start": 120, "open": 101, "high": 103, "low": 97, "close": 102, "volume": 70},
        ]
        result = fill_candle_gaps(candles, 60)
        assert len(result) == 3

    def test_single_gap_filled(self):
        """Happy path: one missing candle is filled."""
        candles = [
            {"start": 0, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 50},
            {"start": 120, "open": 101, "high": 103, "low": 97, "close": 102, "volume": 70},
        ]
        result = fill_candle_gaps(candles, 60)
        assert len(result) == 3  # Original 2 + 1 synthetic
        assert result[1]["_synthetic"] is True
        assert result[1]["start"] == 60
        assert result[1]["close"] == 100  # Previous close
        assert result[1]["volume"] == 0

    def test_multiple_gaps_filled(self):
        """Happy path: multiple missing candles filled."""
        candles = [
            {"start": 0, "close": 100, "open": 100, "high": 101, "low": 99, "volume": 50},
            {"start": 180, "close": 105, "open": 105, "high": 106, "low": 104, "volume": 60},
        ]
        result = fill_candle_gaps(candles, 60)
        # Missing: t=60, t=120 -> 2 synthetic + 2 original = 4
        assert len(result) == 4
        assert result[1]["_synthetic"] is True
        assert result[2]["_synthetic"] is True

    def test_empty_candles(self):
        """Edge case: empty list returns empty."""
        assert fill_candle_gaps([], 60) == []

    def test_single_candle(self):
        """Edge case: single candle returns as-is."""
        candles = [{"start": 0, "close": 100, "open": 100, "high": 101, "low": 99, "volume": 50}]
        assert fill_candle_gaps(candles, 60) == candles

    def test_max_candles_limit(self):
        """Edge case: max_candles limits output size."""
        candles = [
            {"start": 0, "close": 100, "open": 100, "high": 101, "low": 99, "volume": 50},
            {"start": 6000, "close": 105, "open": 105, "high": 106, "low": 104, "volume": 60},
        ]
        # 100 gaps to fill, but limit to 10 candles
        result = fill_candle_gaps(candles, 60, max_candles=10)
        assert len(result) <= 10

    def test_uses_time_key_fallback(self):
        """Edge case: uses 'time' key if 'start' is not present."""
        candles = [
            {"time": 0, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 50},
            {"time": 120, "open": 101, "high": 103, "low": 97, "close": 102, "volume": 70},
        ]
        result = fill_candle_gaps(candles, 60)
        assert len(result) == 3  # One gap filled


# ---------------------------------------------------------------------------
# calculate_bot_check_interval
# ---------------------------------------------------------------------------


class TestCalculateBotCheckInterval:
    """Tests for calculate_bot_check_interval()."""

    def test_single_timeframe(self):
        """Happy path: single timeframe condition."""
        config = {
            "base_order_conditions": [
                {"type": "rsi", "timeframe": "FIVE_MINUTE", "period": 14}
            ]
        }
        assert calculate_bot_check_interval(config) == 300

    def test_multiple_timeframes_returns_minimum(self):
        """Happy path: returns the shortest timeframe interval."""
        config = {
            "base_order_conditions": [
                {"type": "rsi", "timeframe": "FIFTEEN_MINUTE", "period": 14}
            ],
            "safety_order_conditions": [
                {"type": "macd", "timeframe": "THREE_MINUTE"}
            ]
        }
        assert calculate_bot_check_interval(config) == 180  # THREE_MINUTE

    def test_grouped_format(self):
        """Happy path: handles grouped condition format."""
        config = {
            "base_order_conditions": {
                "groups": [
                    {
                        "conditions": [
                            {"type": "rsi", "timeframe": "ONE_MINUTE", "period": 14}
                        ]
                    }
                ]
            }
        }
        assert calculate_bot_check_interval(config) == 60  # ONE_MINUTE

    def test_no_timeframes_defaults_to_300(self):
        """Edge case: no conditions -> defaults to 300 (5 minutes)."""
        assert calculate_bot_check_interval({}) == 300

    def test_skips_required_marker(self):
        """Edge case: 'required' timeframe is skipped."""
        config = {
            "base_order_conditions": [
                {"type": "rsi", "timeframe": "required"},
                {"type": "macd", "timeframe": "ONE_HOUR"},
            ]
        }
        assert calculate_bot_check_interval(config) == 3600

    def test_standalone_indicators_config(self):
        """Happy path: extracts from standalone 'indicators' key."""
        config = {
            "indicators": {
                "rsi": {"timeframe": "THREE_MINUTE"},
                "macd": {"timeframe": "FIFTEEN_MINUTE"},
            }
        }
        assert calculate_bot_check_interval(config) == 180


# ---------------------------------------------------------------------------
# next_check_time_aligned
# ---------------------------------------------------------------------------


class TestNextCheckTimeAligned:
    """Tests for next_check_time_aligned()."""

    def test_basic_alignment(self):
        """Happy path: next 3-minute boundary after 12:04:30."""
        # 12:04:30 -> 43470 seconds from midnight
        # Hour boundary: 43200 (12:00:00)
        # Seconds since hour: 270 (4 min 30 sec)
        # Next boundary: (270 // 180 + 1) * 180 = 2 * 180 = 360 seconds -> 12:06:00
        hour_boundary = 43200
        current_time = hour_boundary + 270
        result = next_check_time_aligned(180, current_time)
        assert result == hour_boundary + 360  # 12:06:00

    def test_exactly_on_boundary(self):
        """Edge case: current time is exactly on a boundary."""
        current_time = 300  # Exactly at 5-minute mark
        result = next_check_time_aligned(300, current_time)
        assert result == 600  # Next 5-minute mark

    def test_one_minute_interval(self):
        """Happy path: 1-minute interval."""
        current_time = 3630  # 1:00:30
        result = next_check_time_aligned(60, current_time)
        assert result == 3660  # 1:01:00

    def test_wraps_to_next_hour(self):
        """Edge case: next boundary wraps to next hour."""
        hour_boundary = 3600  # 1:00:00
        current_time = hour_boundary + 3590  # 1:59:50
        result = next_check_time_aligned(60, current_time)
        # seconds_since_hour = 3590, next_offset = (3590//60 + 1)*60 = 60*60 = 3600
        # That's >= 3600, so wraps to next hour: 3600 + 3600 = 7200
        assert result == 7200  # 2:00:00


# ---------------------------------------------------------------------------
# get_timeframes_for_phases
# ---------------------------------------------------------------------------


class TestGetTimeframesForPhases:
    """Tests for get_timeframes_for_phases()."""

    def test_single_phase_list_format(self):
        """Happy path: extract timeframes from list-format conditions."""
        config = {
            "base_order_conditions": [
                {"type": "rsi", "timeframe": "FIVE_MINUTE"},
                {"type": "macd", "timeframe": "FIFTEEN_MINUTE"},
            ]
        }
        result = get_timeframes_for_phases(config, ["base_order_conditions"])
        assert result == {"FIVE_MINUTE", "FIFTEEN_MINUTE"}

    def test_grouped_format(self):
        """Happy path: extract timeframes from grouped format."""
        config = {
            "take_profit_conditions": {
                "groups": [
                    {"conditions": [{"type": "rsi", "timeframe": "ONE_HOUR"}]}
                ]
            }
        }
        result = get_timeframes_for_phases(config, ["take_profit_conditions"])
        assert result == {"ONE_HOUR"}

    def test_multiple_phases(self):
        """Happy path: combine timeframes from multiple phases."""
        config = {
            "safety_order_conditions": [
                {"type": "rsi", "timeframe": "THREE_MINUTE"}
            ],
            "take_profit_conditions": [
                {"type": "macd", "timeframe": "ONE_HOUR"}
            ]
        }
        result = get_timeframes_for_phases(config, ["safety_order_conditions", "take_profit_conditions"])
        assert result == {"THREE_MINUTE", "ONE_HOUR"}

    def test_no_timeframes_defaults_to_five_minute(self):
        """Edge case: no timeframes found defaults to FIVE_MINUTE."""
        result = get_timeframes_for_phases({}, ["base_order_conditions"])
        assert result == {"FIVE_MINUTE"}

    def test_skips_required_marker(self):
        """Edge case: 'required' timeframe is skipped."""
        config = {
            "base_order_conditions": [
                {"type": "rsi", "timeframe": "required"},
                {"type": "macd", "timeframe": "ONE_HOUR"},
            ]
        }
        result = get_timeframes_for_phases(config, ["base_order_conditions"])
        assert result == {"ONE_HOUR"}

    def test_standalone_indicators_included(self):
        """Happy path: standalone indicators config is also checked."""
        config = {
            "indicators": {
                "rsi": {"timeframe": "TEN_MINUTE"},
            }
        }
        result = get_timeframes_for_phases(config, ["base_order_conditions"])
        assert "TEN_MINUTE" in result

    def test_deduplicates_timeframes(self):
        """Edge case: same timeframe in multiple conditions appears once."""
        config = {
            "base_order_conditions": [
                {"type": "rsi", "timeframe": "FIVE_MINUTE"},
                {"type": "macd", "timeframe": "FIVE_MINUTE"},
            ]
        }
        result = get_timeframes_for_phases(config, ["base_order_conditions"])
        assert result == {"FIVE_MINUTE"}
