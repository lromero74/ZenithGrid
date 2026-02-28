"""
Tests for AISpotOpinionEvaluator — AI-powered trading indicator.

Covers:
- AISpotOpinionParams creation and defaults
- Time-gating (_should_check_now, _timeframe_to_seconds)
- Metric calculation from candle data
- Buy prefilter logic (RSI, volume, price drop)
- LLM call dispatch and response parsing
- Full evaluate() orchestration
- Error handling for bad AI responses
"""

import json
import importlib
import importlib.util
import sys
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# Avoid circular import through app.indicators.__init__ -> strategies -> indicators
# by importing the module directly without triggering __init__.py
_mod_spec = importlib.util.spec_from_file_location(
    "app.indicators.ai_spot_opinion",
    "/home/ec2-user/ZenithGrid/backend/app/indicators/ai_spot_opinion.py",
)
_mod = importlib.util.module_from_spec(_mod_spec)
sys.modules.setdefault("app.indicators.ai_spot_opinion", _mod)
_mod_spec.loader.exec_module(_mod)
AISpotOpinionEvaluator = _mod.AISpotOpinionEvaluator
AISpotOpinionParams = _mod.AISpotOpinionParams

# Patch target for get_user_api_key — the lazy import in _call_llm resolves from this module
_API_KEY_PATCH = "app.services.ai_credential_service.get_user_api_key"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candles(count=60, base_price=100.0, volume=1000.0):
    """Generate candle data with enough history for indicator calculation."""
    candles = []
    for i in range(count):
        price = base_price + (i * 0.5)
        candles.append({
            "open": price * 0.999,
            "high": price * 1.005,
            "low": price * 0.995,
            "close": price,
            "volume": volume,
        })
    return candles


def _metrics_for_prompt():
    """Return a metrics dict with all keys needed by the prompt builder in _call_llm."""
    return {
        "rsi": 50.0, "macd_bullish": False, "macd_bearish": False,
        "price_vs_ma20": 0.0, "price_vs_ma50": 0.0,
        "bb_position": 50.0, "volume_ratio": 1.0, "price_change_24h": 0.0,
    }


# ---------------------------------------------------------------------------
# TestAISpotOpinionParams
# ---------------------------------------------------------------------------

class TestAISpotOpinionParams:
    """Tests for AISpotOpinionParams dataclass."""

    def test_default_params(self):
        params = AISpotOpinionParams()
        assert params.ai_model == "claude"
        assert params.ai_timeframe == "15m"
        assert params.ai_min_confidence == 60
        assert params.enable_buy_prefilter is True
        assert params.prefilter_rsi_max == 70.0
        assert params.prefilter_volume_min_ratio == 1.2
        assert params.prefilter_max_drop_24h == 10.0

    def test_from_config_all_fields(self):
        config = {
            "ai_model": "gpt",
            "ai_timeframe": "1h",
            "ai_min_confidence": 80,
            "enable_buy_prefilter": False,
            "prefilter_rsi_max": 65.0,
            "prefilter_volume_min_ratio": 1.5,
            "prefilter_max_drop_24h": 5.0,
        }
        params = AISpotOpinionParams.from_config(config)
        assert params.ai_model == "gpt"
        assert params.ai_timeframe == "1h"
        assert params.ai_min_confidence == 80
        assert params.enable_buy_prefilter is False
        assert params.prefilter_rsi_max == 65.0

    def test_from_config_empty_uses_defaults(self):
        params = AISpotOpinionParams.from_config({})
        assert params.ai_model == "claude"
        assert params.ai_timeframe == "15m"

    def test_from_config_partial_override(self):
        params = AISpotOpinionParams.from_config({"ai_model": "gemini"})
        assert params.ai_model == "gemini"
        assert params.ai_timeframe == "15m"  # default kept


# ---------------------------------------------------------------------------
# TestTimeframeConversion
# ---------------------------------------------------------------------------

class TestTimeframeConversion:
    """Tests for timeframe string to seconds conversion."""

    def test_minutes(self):
        evaluator = AISpotOpinionEvaluator()
        assert evaluator._timeframe_to_seconds("15m") == 900
        assert evaluator._timeframe_to_seconds("5m") == 300
        assert evaluator._timeframe_to_seconds("1m") == 60

    def test_hours(self):
        evaluator = AISpotOpinionEvaluator()
        assert evaluator._timeframe_to_seconds("1h") == 3600
        assert evaluator._timeframe_to_seconds("4h") == 14400

    def test_days(self):
        evaluator = AISpotOpinionEvaluator()
        assert evaluator._timeframe_to_seconds("1d") == 86400

    def test_uppercase_handled(self):
        evaluator = AISpotOpinionEvaluator()
        assert evaluator._timeframe_to_seconds("15M") == 900
        assert evaluator._timeframe_to_seconds("4H") == 14400

    def test_unknown_format_defaults_to_15m(self):
        evaluator = AISpotOpinionEvaluator()
        assert evaluator._timeframe_to_seconds("xyz") == 900


# ---------------------------------------------------------------------------
# TestTimeGating
# ---------------------------------------------------------------------------

class TestTimeGating:
    """Tests for _should_check_now time-gating logic."""

    def test_first_check_always_allowed(self):
        evaluator = AISpotOpinionEvaluator()
        assert evaluator._should_check_now("BTC-USD", "15m") is True

    def test_second_check_too_soon_blocked(self):
        evaluator = AISpotOpinionEvaluator()
        evaluator._update_last_check("BTC-USD", "15m")
        assert evaluator._should_check_now("BTC-USD", "15m") is False

    def test_second_check_after_enough_time_allowed(self):
        evaluator = AISpotOpinionEvaluator()
        evaluator._last_check_cache["BTC-USD:15m"] = datetime.utcnow() - timedelta(minutes=20)
        assert evaluator._should_check_now("BTC-USD", "15m") is True

    def test_different_products_independent(self):
        evaluator = AISpotOpinionEvaluator()
        evaluator._update_last_check("BTC-USD", "15m")
        assert evaluator._should_check_now("BTC-USD", "15m") is False
        assert evaluator._should_check_now("ETH-USD", "15m") is True

    def test_different_timeframes_independent(self):
        evaluator = AISpotOpinionEvaluator()
        evaluator._update_last_check("BTC-USD", "15m")
        assert evaluator._should_check_now("BTC-USD", "15m") is False
        assert evaluator._should_check_now("BTC-USD", "1h") is True


# ---------------------------------------------------------------------------
# TestCalculateMetrics
# ---------------------------------------------------------------------------

class TestCalculateMetrics:
    """Tests for _calculate_metrics from candle data."""

    def test_sufficient_candles_returns_metrics(self):
        evaluator = AISpotOpinionEvaluator()
        candles = _make_candles(60)
        metrics = evaluator._calculate_metrics(candles)
        assert "rsi" in metrics
        assert "macd_bullish" in metrics
        assert "macd_bearish" in metrics
        assert "bb_position" in metrics
        assert "current_price" in metrics
        assert "volume_ratio" in metrics
        assert "price_change_24h" in metrics
        assert "ma_20" in metrics
        assert "ma_50" in metrics
        assert "price_vs_ma20" in metrics
        assert "price_vs_ma50" in metrics

    def test_insufficient_candles_returns_empty(self):
        evaluator = AISpotOpinionEvaluator()
        candles = _make_candles(10)
        metrics = evaluator._calculate_metrics(candles)
        assert metrics == {}

    def test_empty_candles_returns_empty(self):
        evaluator = AISpotOpinionEvaluator()
        assert evaluator._calculate_metrics([]) == {}
        assert evaluator._calculate_metrics(None) == {}

    def test_current_price_is_last_close(self):
        evaluator = AISpotOpinionEvaluator()
        candles = _make_candles(60, base_price=100.0)
        metrics = evaluator._calculate_metrics(candles)
        expected_last = 100.0 + (59 * 0.5)
        assert metrics["current_price"] == pytest.approx(expected_last, rel=1e-6)

    def test_volume_ratio_calculation(self):
        evaluator = AISpotOpinionEvaluator()
        candles = _make_candles(60, volume=100.0)
        metrics = evaluator._calculate_metrics(candles)
        assert metrics["volume_ratio"] == pytest.approx(1.0, rel=1e-6)


# ---------------------------------------------------------------------------
# TestBuyPrefilter
# ---------------------------------------------------------------------------

class TestBuyPrefilter:
    """Tests for _check_buy_prefilter logic."""

    def test_prefilter_disabled_always_passes(self):
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(enable_buy_prefilter=False)
        passed, reason = evaluator._check_buy_prefilter({}, params)
        assert passed is True
        assert "disabled" in reason.lower()

    def test_rsi_too_high_rejected(self):
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(prefilter_rsi_max=70.0)
        metrics = {"rsi": 75.0, "volume_ratio": 2.0, "price_change_24h": 0}
        passed, reason = evaluator._check_buy_prefilter(metrics, params)
        assert passed is False
        assert "RSI too high" in reason

    def test_volume_too_low_rejected(self):
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(prefilter_volume_min_ratio=1.2)
        metrics = {"rsi": 50.0, "volume_ratio": 0.8, "price_change_24h": 0}
        passed, reason = evaluator._check_buy_prefilter(metrics, params)
        assert passed is False
        assert "Volume too low" in reason

    def test_price_dropped_too_much_rejected(self):
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(prefilter_max_drop_24h=10.0)
        metrics = {"rsi": 50.0, "volume_ratio": 2.0, "price_change_24h": -15.0}
        passed, reason = evaluator._check_buy_prefilter(metrics, params)
        assert passed is False
        assert "dropped too much" in reason

    def test_all_conditions_pass(self):
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams()
        metrics = {"rsi": 50.0, "volume_ratio": 2.0, "price_change_24h": 2.0}
        passed, reason = evaluator._check_buy_prefilter(metrics, params)
        assert passed is True
        assert "passed" in reason.lower()

    def test_boundary_rsi_exactly_at_max_passes(self):
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(prefilter_rsi_max=70.0)
        metrics = {"rsi": 70.0, "volume_ratio": 2.0, "price_change_24h": 0}
        passed, _ = evaluator._check_buy_prefilter(metrics, params)
        assert passed is True  # 70 is not > 70

    def test_boundary_volume_exactly_at_min_passes(self):
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(prefilter_volume_min_ratio=1.2)
        metrics = {"rsi": 50.0, "volume_ratio": 1.2, "price_change_24h": 0}
        passed, _ = evaluator._check_buy_prefilter(metrics, params)
        assert passed is True  # 1.2 is not < 1.2

    def test_missing_metrics_use_safe_defaults(self):
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams()
        passed, reason = evaluator._check_buy_prefilter({}, params)
        assert passed is False
        assert "Volume too low" in reason


# ---------------------------------------------------------------------------
# TestCallLLM
# ---------------------------------------------------------------------------

class TestCallLLM:
    """Tests for _call_llm dispatch and response parsing."""

    @pytest.mark.asyncio
    async def test_valid_claude_response_parsed(self):
        evaluator = AISpotOpinionEvaluator()
        response_json = json.dumps({
            "signal": "buy", "confidence": 75, "reasoning": "Bullish MACD crossover"
        })

        with patch.object(evaluator, "_call_claude", new_callable=AsyncMock, return_value=response_json):
            with patch(_API_KEY_PATCH, new_callable=AsyncMock, return_value="sk-test"):
                signal, confidence, reasoning = await evaluator._call_llm(
                    db=MagicMock(), user_id=1, product_id="BTC-USD",
                    metrics=_metrics_for_prompt(), ai_model="claude", is_sell_check=False
                )
        assert signal == "buy"
        assert confidence == 75
        assert reasoning == "Bullish MACD crossover"

    @pytest.mark.asyncio
    async def test_openai_model_dispatched_correctly(self):
        evaluator = AISpotOpinionEvaluator()
        response_json = json.dumps({"signal": "sell", "confidence": 60, "reasoning": "Overbought"})

        with patch.object(evaluator, "_call_openai", new_callable=AsyncMock, return_value=response_json) as mock_call:
            with patch(_API_KEY_PATCH, new_callable=AsyncMock, return_value="sk-test"):
                signal, confidence, reasoning = await evaluator._call_llm(
                    db=MagicMock(), user_id=1, product_id="BTC-USD",
                    metrics=_metrics_for_prompt(), ai_model="gpt", is_sell_check=False
                )
        mock_call.assert_awaited_once()
        assert signal == "sell"

    @pytest.mark.asyncio
    async def test_gemini_model_dispatched_correctly(self):
        evaluator = AISpotOpinionEvaluator()
        response_json = json.dumps({"signal": "hold", "confidence": 40, "reasoning": "Mixed signals"})

        with patch.object(evaluator, "_call_gemini", new_callable=AsyncMock, return_value=response_json) as mock_call:
            with patch(_API_KEY_PATCH, new_callable=AsyncMock, return_value="sk-test"):
                signal, confidence, reasoning = await evaluator._call_llm(
                    db=MagicMock(), user_id=1, product_id="BTC-USD",
                    metrics=_metrics_for_prompt(), ai_model="gemini", is_sell_check=False
                )
        mock_call.assert_awaited_once()
        assert signal == "hold"

    @pytest.mark.asyncio
    async def test_unknown_model_raises_value_error(self):
        evaluator = AISpotOpinionEvaluator()
        with patch(_API_KEY_PATCH, new_callable=AsyncMock, return_value="sk-test"):
            with pytest.raises(ValueError, match="Unknown AI model"):
                await evaluator._call_llm(
                    db=MagicMock(), user_id=1, product_id="BTC-USD",
                    metrics=_metrics_for_prompt(), ai_model="deepseek", is_sell_check=False
                )

    @pytest.mark.asyncio
    async def test_no_api_key_raises_value_error(self):
        evaluator = AISpotOpinionEvaluator()
        with patch(_API_KEY_PATCH, new_callable=AsyncMock, return_value=None):
            with pytest.raises(ValueError, match="No API key configured"):
                await evaluator._call_llm(
                    db=MagicMock(), user_id=1, product_id="BTC-USD",
                    metrics=_metrics_for_prompt(), ai_model="claude", is_sell_check=False
                )

    @pytest.mark.asyncio
    async def test_response_with_markdown_code_block_stripped(self):
        evaluator = AISpotOpinionEvaluator()
        response_text = '```json\n{"signal": "buy", "confidence": 80, "reasoning": "Strong"}\n```'

        with patch.object(evaluator, "_call_claude", new_callable=AsyncMock, return_value=response_text):
            with patch(_API_KEY_PATCH, new_callable=AsyncMock, return_value="sk-test"):
                signal, confidence, reasoning = await evaluator._call_llm(
                    db=MagicMock(), user_id=1, product_id="BTC-USD",
                    metrics=_metrics_for_prompt(), ai_model="claude", is_sell_check=False
                )
        assert signal == "buy"
        assert confidence == 80

    @pytest.mark.asyncio
    async def test_invalid_signal_defaults_to_hold(self):
        evaluator = AISpotOpinionEvaluator()
        response_json = json.dumps({"signal": "maybe", "confidence": 50, "reasoning": "Hmm"})

        with patch.object(evaluator, "_call_claude", new_callable=AsyncMock, return_value=response_json):
            with patch(_API_KEY_PATCH, new_callable=AsyncMock, return_value="sk-test"):
                signal, _, _ = await evaluator._call_llm(
                    db=MagicMock(), user_id=1, product_id="BTC-USD",
                    metrics=_metrics_for_prompt(), ai_model="claude", is_sell_check=False
                )
        assert signal == "hold"

    @pytest.mark.asyncio
    async def test_confidence_clamped_to_0_100(self):
        evaluator = AISpotOpinionEvaluator()
        response_json = json.dumps({"signal": "buy", "confidence": 150, "reasoning": "Very confident"})

        with patch.object(evaluator, "_call_claude", new_callable=AsyncMock, return_value=response_json):
            with patch(_API_KEY_PATCH, new_callable=AsyncMock, return_value="sk-test"):
                _, confidence, _ = await evaluator._call_llm(
                    db=MagicMock(), user_id=1, product_id="BTC-USD",
                    metrics=_metrics_for_prompt(), ai_model="claude", is_sell_check=False
                )
        assert confidence == 100

    @pytest.mark.asyncio
    async def test_negative_confidence_clamped_to_zero(self):
        evaluator = AISpotOpinionEvaluator()
        response_json = json.dumps({"signal": "hold", "confidence": -20, "reasoning": "Unsure"})

        with patch.object(evaluator, "_call_claude", new_callable=AsyncMock, return_value=response_json):
            with patch(_API_KEY_PATCH, new_callable=AsyncMock, return_value="sk-test"):
                _, confidence, _ = await evaluator._call_llm(
                    db=MagicMock(), user_id=1, product_id="BTC-USD",
                    metrics=_metrics_for_prompt(), ai_model="claude", is_sell_check=False
                )
        assert confidence == 0

    @pytest.mark.asyncio
    async def test_llm_exception_returns_hold_with_zero_confidence(self):
        evaluator = AISpotOpinionEvaluator()

        with patch.object(evaluator, "_call_claude", new_callable=AsyncMock, side_effect=RuntimeError("API down")):
            with patch(_API_KEY_PATCH, new_callable=AsyncMock, return_value="sk-test"):
                signal, confidence, reasoning = await evaluator._call_llm(
                    db=MagicMock(), user_id=1, product_id="BTC-USD",
                    metrics=_metrics_for_prompt(), ai_model="claude", is_sell_check=False
                )
        assert signal == "hold"
        assert confidence == 0
        assert "LLM error" in reasoning

    @pytest.mark.asyncio
    async def test_invalid_json_returns_hold(self):
        evaluator = AISpotOpinionEvaluator()

        with patch.object(evaluator, "_call_claude", new_callable=AsyncMock, return_value="not json at all"):
            with patch(_API_KEY_PATCH, new_callable=AsyncMock, return_value="sk-test"):
                signal, confidence, reasoning = await evaluator._call_llm(
                    db=MagicMock(), user_id=1, product_id="BTC-USD",
                    metrics=_metrics_for_prompt(), ai_model="claude", is_sell_check=False
                )
        assert signal == "hold"
        assert confidence == 0


# ---------------------------------------------------------------------------
# TestEvaluate (full orchestration)
# ---------------------------------------------------------------------------

class TestEvaluate:
    """Tests for the full evaluate() orchestration method."""

    @pytest.mark.asyncio
    async def test_insufficient_data_returns_hold(self):
        evaluator = AISpotOpinionEvaluator()
        result = await evaluator.evaluate(
            candles=_make_candles(10), current_price=100.0,
            product_id="BTC-USD", db=MagicMock(), user_id=1,
        )
        assert result["signal"] == "hold"
        assert result["confidence"] == 0
        assert "Insufficient" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_time_gated_returns_hold(self):
        evaluator = AISpotOpinionEvaluator()
        evaluator._update_last_check("BTC-USD", "15m")
        result = await evaluator.evaluate(
            candles=_make_candles(60), current_price=100.0,
            product_id="BTC-USD", db=MagicMock(), user_id=1,
        )
        assert result["signal"] == "hold"
        assert "Waiting for next" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_prefilter_failure_returns_hold_with_metrics(self):
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(prefilter_rsi_max=30.0)
        candles = _make_candles(60)
        result = await evaluator.evaluate(
            candles=candles, current_price=100.0,
            product_id="BTC-USD", db=MagicMock(), user_id=1,
            params=params, is_sell_check=False
        )
        assert result["signal"] == "hold"
        assert result["prefilter_passed"] is False
        assert result["metrics"] != {}

    @pytest.mark.asyncio
    async def test_sell_check_skips_prefilter(self):
        evaluator = AISpotOpinionEvaluator()

        with patch.object(evaluator, "_call_llm", new_callable=AsyncMock, return_value=("sell", 85, "Take profit")):
            result = await evaluator.evaluate(
                candles=_make_candles(60), current_price=100.0,
                product_id="BTC-USD", db=MagicMock(), user_id=1,
                is_sell_check=True
            )
        assert result["signal"] == "sell"
        assert result["prefilter_passed"] is True

    @pytest.mark.asyncio
    async def test_successful_buy_evaluation(self):
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(enable_buy_prefilter=False)

        with patch.object(evaluator, "_call_llm", new_callable=AsyncMock, return_value=("buy", 78, "Good entry")):
            result = await evaluator.evaluate(
                candles=_make_candles(60), current_price=100.0,
                product_id="BTC-USD", db=MagicMock(), user_id=1,
                params=params, is_sell_check=False
            )
        assert result["signal"] == "buy"
        assert result["confidence"] == 78
        assert result["reasoning"] == "Good entry"
        assert result["prefilter_passed"] is True
        assert "metrics" in result

    @pytest.mark.asyncio
    async def test_evaluate_updates_last_check_timestamp(self):
        evaluator = AISpotOpinionEvaluator()
        params = AISpotOpinionParams(enable_buy_prefilter=False)

        with patch.object(evaluator, "_call_llm", new_callable=AsyncMock, return_value=("hold", 50, "Wait")):
            await evaluator.evaluate(
                candles=_make_candles(60), current_price=100.0,
                product_id="ETH-USD", db=MagicMock(), user_id=1,
                params=params,
            )
        assert "ETH-USD:15m" in evaluator._last_check_cache

    @pytest.mark.asyncio
    async def test_default_params_used_when_none(self):
        evaluator = AISpotOpinionEvaluator()
        result = await evaluator.evaluate(
            candles=_make_candles(60), current_price=100.0,
            product_id="BTC-USD", db=MagicMock(), user_id=1,
            params=None,
        )
        assert result["signal"] == "hold"
        # prefilter should fail since volume ratio ~1.0 < 1.2
        assert result["prefilter_passed"] is False
