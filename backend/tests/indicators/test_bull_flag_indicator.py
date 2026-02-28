"""
Tests for BullFlagIndicatorEvaluator — bull flag chart pattern detection.

Covers:
- BullFlagParams creation, from_config, to_scanner_config
- BullFlagResult dataclass
- evaluate() with valid patterns, no patterns, insufficient data
- Convenience functions (evaluate_bull_flag_indicator, _with_details)
- get_required_timeframe
- Edge cases: empty candles, None candles, boundary thresholds
"""

import importlib
import importlib.util
import sys
import types
import pytest
from unittest.mock import patch, MagicMock

# Avoid circular import: bull_flag_indicator -> app.strategies.bull_flag_scanner
# -> app.strategies.__init__ -> indicator_based -> app.indicators -> bull_flag_indicator
# Solution: force-register a mock for app.strategies.bull_flag_scanner BEFORE loading
# the module, preventing the circular chain from triggering.
_mock_scanner = types.ModuleType("app.strategies.bull_flag_scanner")
_mock_scanner.detect_bull_flag_pattern = MagicMock()

# Force-register regardless of whether a real module was loaded already
sys.modules["app.strategies.bull_flag_scanner"] = _mock_scanner

_mod_spec = importlib.util.spec_from_file_location(
    "app.indicators.bull_flag_indicator",
    "/home/ec2-user/ZenithGrid/backend/app/indicators/bull_flag_indicator.py",
)
_mod = importlib.util.module_from_spec(_mod_spec)
sys.modules["app.indicators.bull_flag_indicator"] = _mod
_mod_spec.loader.exec_module(_mod)

BullFlagParams = _mod.BullFlagParams
BullFlagResult = _mod.BullFlagResult
BullFlagIndicatorEvaluator = _mod.BullFlagIndicatorEvaluator
evaluate_bull_flag_indicator = _mod.evaluate_bull_flag_indicator
evaluate_bull_flag_indicator_with_details = _mod.evaluate_bull_flag_indicator_with_details


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candles(count=20, base_price=100.0, volume=1000.0):
    """Generate basic candle data."""
    candles = []
    for i in range(count):
        price = base_price + (i * 0.5)
        candles.append({
            "open": price * 0.999,
            "high": price * 1.005,
            "low": price * 0.995,
            "close": price,
            "volume": volume,
            "timestamp": f"2025-01-{(i+1):02d}T00:00:00Z",
        })
    return candles


def _valid_pattern_dict():
    """Return a pattern dict that detect_bull_flag_pattern would produce on success."""
    return {
        "pattern_valid": True,
        "entry_price": 105.0,
        "stop_loss": 100.0,
        "take_profit_target": 115.0,
        "pole_gain_pct": 5.2,
        "retracement_pct": 35.0,
        "risk_reward_ratio": 2.0,
        "volume_ratio": 1.8,
    }


# ---------------------------------------------------------------------------
# TestBullFlagParams
# ---------------------------------------------------------------------------

class TestBullFlagParams:
    """Tests for BullFlagParams dataclass."""

    def test_default_params(self):
        params = BullFlagParams()
        assert params.timeframe == "FIFTEEN_MINUTE"
        assert params.min_pole_candles == 3
        assert params.min_pole_gain_pct == 3.0
        assert params.min_pullback_candles == 2
        assert params.max_pullback_candles == 8
        assert params.pullback_retracement_max == 50.0
        assert params.reward_risk_ratio == 2.0
        assert params.require_volume_spike is False
        assert params.volume_multiplier == 5.0

    def test_from_config_all_fields(self):
        config = {
            "timeframe": "ONE_HOUR",
            "min_pole_candles": 5,
            "min_pole_gain_pct": 5.0,
            "min_pullback_candles": 3,
            "max_pullback_candles": 10,
            "pullback_retracement_max": 40.0,
            "reward_risk_ratio": 3.0,
            "require_volume_spike": True,
            "volume_multiplier": 7.0,
        }
        params = BullFlagParams.from_config(config)
        assert params.timeframe == "ONE_HOUR"
        assert params.min_pole_candles == 5
        assert params.min_pole_gain_pct == 5.0
        assert params.require_volume_spike is True
        assert params.volume_multiplier == 7.0

    def test_from_config_empty_uses_defaults(self):
        params = BullFlagParams.from_config({})
        assert params.min_pole_candles == 3
        assert params.timeframe == "FIFTEEN_MINUTE"

    def test_from_config_partial_override(self):
        params = BullFlagParams.from_config({"min_pole_candles": 7})
        assert params.min_pole_candles == 7
        assert params.min_pole_gain_pct == 3.0  # default

    def test_to_scanner_config(self):
        params = BullFlagParams(
            min_pole_candles=4,
            min_pole_gain_pct=4.0,
            min_pullback_candles=3,
            max_pullback_candles=9,
            pullback_retracement_max=45.0,
            reward_risk_ratio=2.5,
        )
        config = params.to_scanner_config()
        assert config["min_pole_candles"] == 4
        assert config["min_pole_gain_pct"] == 4.0
        assert config["min_pullback_candles"] == 3
        assert config["max_pullback_candles"] == 9
        assert config["pullback_retracement_max"] == 45.0
        assert config["reward_risk_ratio"] == 2.5
        # Should not include timeframe or volume settings
        assert "timeframe" not in config
        assert "require_volume_spike" not in config

    def test_to_scanner_config_excludes_volume_fields(self):
        params = BullFlagParams(require_volume_spike=True, volume_multiplier=10.0)
        config = params.to_scanner_config()
        assert "require_volume_spike" not in config
        assert "volume_multiplier" not in config


# ---------------------------------------------------------------------------
# TestBullFlagResult
# ---------------------------------------------------------------------------

class TestBullFlagResult:
    """Tests for BullFlagResult dataclass."""

    def test_successful_detection_result(self):
        result = BullFlagResult(
            signal=1, pattern_valid=True,
            entry_price=105.0, stop_loss=100.0, take_profit_target=115.0,
            pole_gain_pct=5.2, retracement_pct=35.0, risk_reward_ratio=2.0,
        )
        assert result.signal == 1
        assert result.pattern_valid is True
        assert result.rejection_reason is None

    def test_no_detection_result(self):
        result = BullFlagResult(signal=0, pattern_valid=False, rejection_reason="No pole found")
        assert result.signal == 0
        assert result.pattern_valid is False
        assert result.rejection_reason == "No pole found"

    def test_default_pattern_data_is_empty_dict(self):
        result = BullFlagResult(signal=0, pattern_valid=False)
        assert result.pattern_data == {}


# ---------------------------------------------------------------------------
# TestBullFlagIndicatorEvaluator
# ---------------------------------------------------------------------------

class TestBullFlagIndicatorEvaluator:
    """Tests for the main evaluate() method."""

    @patch("app.indicators.bull_flag_indicator.detect_bull_flag_pattern")
    def test_pattern_detected_returns_signal_1(self, mock_detect):
        pattern = _valid_pattern_dict()
        mock_detect.return_value = (pattern, None)

        evaluator = BullFlagIndicatorEvaluator()
        result = evaluator.evaluate(candles=_make_candles(20), current_price=105.0)

        assert result.signal == 1
        assert result.pattern_valid is True
        assert result.entry_price == 105.0
        assert result.stop_loss == 100.0
        assert result.take_profit_target == 115.0
        assert result.pole_gain_pct == 5.2
        assert result.retracement_pct == 35.0
        assert result.risk_reward_ratio == 2.0
        assert result.volume_ratio == 1.8
        assert result.pattern_data == pattern

    @patch("app.indicators.bull_flag_indicator.detect_bull_flag_pattern")
    def test_no_pattern_returns_signal_0(self, mock_detect):
        mock_detect.return_value = (None, "No pole found")

        evaluator = BullFlagIndicatorEvaluator()
        result = evaluator.evaluate(candles=_make_candles(20), current_price=100.0)

        assert result.signal == 0
        assert result.pattern_valid is False
        assert result.rejection_reason == "No pole found"

    @patch("app.indicators.bull_flag_indicator.detect_bull_flag_pattern")
    def test_pattern_not_valid_flag_returns_signal_0(self, mock_detect):
        """Pattern dict returned but pattern_valid=False."""
        mock_detect.return_value = ({"pattern_valid": False}, "Retracement too deep")

        evaluator = BullFlagIndicatorEvaluator()
        result = evaluator.evaluate(candles=_make_candles(20), current_price=100.0)

        assert result.signal == 0
        assert result.pattern_valid is False

    def test_insufficient_candles_returns_signal_0(self):
        evaluator = BullFlagIndicatorEvaluator()
        result = evaluator.evaluate(candles=_make_candles(5), current_price=100.0)
        assert result.signal == 0
        assert result.pattern_valid is False
        assert "Insufficient candles" in result.rejection_reason

    def test_empty_candles_returns_signal_0(self):
        evaluator = BullFlagIndicatorEvaluator()
        result = evaluator.evaluate(candles=[], current_price=100.0)
        assert result.signal == 0
        assert "Insufficient candles: 0" in result.rejection_reason

    def test_none_candles_returns_signal_0(self):
        evaluator = BullFlagIndicatorEvaluator()
        result = evaluator.evaluate(candles=None, current_price=100.0)
        assert result.signal == 0
        assert "Insufficient candles: 0" in result.rejection_reason

    def test_exactly_10_candles_calls_detector(self):
        """10 candles is the boundary — should proceed to detection."""
        evaluator = BullFlagIndicatorEvaluator()
        with patch("app.indicators.bull_flag_indicator.detect_bull_flag_pattern") as mock_detect:
            mock_detect.return_value = (None, "No pattern")
            result = evaluator.evaluate(candles=_make_candles(10), current_price=100.0)
        mock_detect.assert_called_once()
        assert result.signal == 0

    def test_9_candles_does_not_call_detector(self):
        """9 candles is below threshold — should not call detector."""
        evaluator = BullFlagIndicatorEvaluator()
        with patch("app.indicators.bull_flag_indicator.detect_bull_flag_pattern") as mock_detect:
            result = evaluator.evaluate(candles=_make_candles(9), current_price=100.0)
        mock_detect.assert_not_called()

    @patch("app.indicators.bull_flag_indicator.detect_bull_flag_pattern")
    def test_default_params_used_when_none(self, mock_detect):
        mock_detect.return_value = (None, "No pattern")
        evaluator = BullFlagIndicatorEvaluator()
        evaluator.evaluate(candles=_make_candles(20), current_price=100.0, params=None)
        # Check the config passed to detect uses defaults
        call_config = mock_detect.call_args[0][1]
        assert call_config["min_pole_candles"] == 3
        assert call_config["min_pole_gain_pct"] == 3.0

    @patch("app.indicators.bull_flag_indicator.detect_bull_flag_pattern")
    def test_custom_params_passed_to_scanner(self, mock_detect):
        mock_detect.return_value = (None, "No pattern")
        evaluator = BullFlagIndicatorEvaluator()
        params = BullFlagParams(min_pole_candles=5, min_pole_gain_pct=6.0)
        evaluator.evaluate(candles=_make_candles(20), current_price=100.0, params=params)
        call_config = mock_detect.call_args[0][1]
        assert call_config["min_pole_candles"] == 5
        assert call_config["min_pole_gain_pct"] == 6.0


# ---------------------------------------------------------------------------
# TestGetRequiredTimeframe
# ---------------------------------------------------------------------------

class TestGetRequiredTimeframe:
    """Tests for get_required_timeframe."""

    def test_default_timeframe(self):
        evaluator = BullFlagIndicatorEvaluator()
        assert evaluator.get_required_timeframe() == "FIFTEEN_MINUTE"

    def test_custom_timeframe(self):
        evaluator = BullFlagIndicatorEvaluator()
        params = BullFlagParams(timeframe="ONE_HOUR")
        assert evaluator.get_required_timeframe(params) == "ONE_HOUR"

    def test_none_params_uses_default(self):
        evaluator = BullFlagIndicatorEvaluator()
        assert evaluator.get_required_timeframe(None) == "FIFTEEN_MINUTE"


# ---------------------------------------------------------------------------
# TestConvenienceFunctions
# ---------------------------------------------------------------------------

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    @patch("app.indicators.bull_flag_indicator.detect_bull_flag_pattern")
    def test_evaluate_bull_flag_indicator_returns_int(self, mock_detect):
        mock_detect.return_value = (_valid_pattern_dict(), None)
        result = evaluate_bull_flag_indicator(candles=_make_candles(20), current_price=105.0)
        assert result == 1
        assert isinstance(result, int)

    @patch("app.indicators.bull_flag_indicator.detect_bull_flag_pattern")
    def test_evaluate_bull_flag_indicator_no_pattern(self, mock_detect):
        mock_detect.return_value = (None, "No flag")
        result = evaluate_bull_flag_indicator(candles=_make_candles(20), current_price=100.0)
        assert result == 0

    @patch("app.indicators.bull_flag_indicator.detect_bull_flag_pattern")
    def test_evaluate_with_details_returns_full_dict(self, mock_detect):
        mock_detect.return_value = (_valid_pattern_dict(), None)
        result = evaluate_bull_flag_indicator_with_details(
            candles=_make_candles(20), current_price=105.0
        )
        assert result["signal"] == 1
        assert result["pattern_valid"] is True
        assert result["entry_price"] == 105.0
        assert result["stop_loss"] == 100.0
        assert result["take_profit_target"] == 115.0
        assert result["rejection_reason"] is None

    @patch("app.indicators.bull_flag_indicator.detect_bull_flag_pattern")
    def test_evaluate_with_details_no_pattern_dict(self, mock_detect):
        mock_detect.return_value = (None, "Retracement too deep")
        result = evaluate_bull_flag_indicator_with_details(
            candles=_make_candles(20), current_price=100.0
        )
        assert result["signal"] == 0
        assert result["pattern_valid"] is False
        assert result["entry_price"] is None
        assert result["rejection_reason"] == "Retracement too deep"

    @patch("app.indicators.bull_flag_indicator.detect_bull_flag_pattern")
    def test_convenience_function_with_custom_config(self, mock_detect):
        mock_detect.return_value = (None, "No pattern")
        config = {"min_pole_candles": 5, "min_pole_gain_pct": 8.0}
        evaluate_bull_flag_indicator(candles=_make_candles(20), current_price=100.0, config=config)
        call_config = mock_detect.call_args[0][1]
        assert call_config["min_pole_candles"] == 5

    @patch("app.indicators.bull_flag_indicator.detect_bull_flag_pattern")
    def test_convenience_function_none_config_uses_defaults(self, mock_detect):
        mock_detect.return_value = (None, "No pattern")
        evaluate_bull_flag_indicator(candles=_make_candles(20), current_price=100.0, config=None)
        call_config = mock_detect.call_args[0][1]
        assert call_config["min_pole_candles"] == 3
