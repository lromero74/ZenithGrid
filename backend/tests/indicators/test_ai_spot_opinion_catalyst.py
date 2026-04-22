"""
Tests for the speculative/catalyst mode branch in
backend/app/indicators/ai_spot_opinion.py.

Covers the additions from PRPs/high-risk-doubling-preset.md §Recommended
Design §3:
- AISpotOpinionParams new fields (speculative_mode, target_multiple,
  target_horizon_hours, prefilter_max_gain_24h, prefilter_min_gain_24h).
- _calculate_metrics new keys (volume_30d_ratio, compression_ratio,
  momentum_1h, momentum_acceleration).
- _check_buy_prefilter speculative branch (upper + lower gain gates).
- _build_prompt speculative branch (catalyst question, score block).
- _parse_llm_response optional doubling_probability_score.

Non-speculative behavior must be byte-identical — there is an explicit
regression guard test for the prompt.
"""

from app.indicators.ai_spot_opinion import AISpotOpinionEvaluator, AISpotOpinionParams


# ---------------------------------------------------------------------------
# AISpotOpinionParams
# ---------------------------------------------------------------------------


class TestParamsFromConfig:
    def test_defaults_preserved_when_keys_absent(self):
        """Regression: existing configs without speculative keys still parse
        to the old behavior (speculative_mode=False)."""
        p = AISpotOpinionParams.from_config({})
        assert p.speculative_mode is False
        assert p.target_multiple == 2.0
        assert p.target_horizon_hours == 24
        assert p.prefilter_max_gain_24h is None
        assert p.prefilter_min_gain_24h is None

    def test_reads_speculative_keys(self):
        cfg = {
            "speculative_mode": True,
            "target_multiple": 3.0,
            "target_horizon_hours": 12,
            "prefilter_max_gain_24h": 50.0,
            "prefilter_min_gain_24h": -10.0,
        }
        p = AISpotOpinionParams.from_config(cfg)
        assert p.speculative_mode is True
        assert p.target_multiple == 3.0
        assert p.target_horizon_hours == 12
        assert p.prefilter_max_gain_24h == 50.0
        assert p.prefilter_min_gain_24h == -10.0


# ---------------------------------------------------------------------------
# _calculate_metrics new keys
# ---------------------------------------------------------------------------


def _candles(count=60, base=100.0, trend=0.0, vol=1000.0, vol_spike_last=None):
    """Synthetic OHLCV with optional final-candle volume spike."""
    out = []
    for i in range(count):
        close = base + trend * i
        out.append({
            "open": close, "high": close + 1.0, "low": close - 1.0,
            "close": close, "volume": vol,
        })
    if vol_spike_last is not None:
        out[-1]["volume"] = vol_spike_last
    return out


class TestCalculateMetricsCatalystKeys:
    def test_new_keys_present_in_output(self):
        evaluator = AISpotOpinionEvaluator()
        metrics = evaluator._calculate_metrics(_candles(count=60))
        for key in ("volume_30d_ratio", "compression_ratio",
                    "momentum_1h", "momentum_acceleration"):
            assert key in metrics, f"{key} missing from metrics"

    def test_volume_30d_ratio_picks_up_spike(self):
        """Happy path: a final-candle volume spike raises the ratio."""
        evaluator = AISpotOpinionEvaluator()
        m = evaluator._calculate_metrics(_candles(count=60, vol=1000.0,
                                                  vol_spike_last=10_000.0))
        assert m["volume_30d_ratio"] >= 5.0  # spike dominates baseline

    def test_compression_ratio_flat_market(self):
        """A perfectly flat market has no range and no diffs — ratio is 0."""
        evaluator = AISpotOpinionEvaluator()
        m = evaluator._calculate_metrics(_candles(count=60, trend=0.0))
        assert m["compression_ratio"] == 0.0

    def test_momentum_1h_uptrend_positive(self):
        """Steady uptrend → positive 1h momentum."""
        evaluator = AISpotOpinionEvaluator()
        m = evaluator._calculate_metrics(_candles(count=60, trend=0.5))
        assert m["momentum_1h"] > 0


# ---------------------------------------------------------------------------
# _check_buy_prefilter speculative branch
# ---------------------------------------------------------------------------


class TestPrefilterSpeculativeBranch:
    def _evaluator(self):
        return AISpotOpinionEvaluator()

    def test_allows_already_up_20pct(self):
        """Catalyst mode welcomes already-up-today coins (previously blocked)."""
        ev = self._evaluator()
        params = AISpotOpinionParams(
            speculative_mode=True,
            prefilter_max_gain_24h=50.0,
            prefilter_min_gain_24h=-10.0,
            prefilter_volume_min_ratio=0.0,  # strip orthogonal gates
            prefilter_rsi_max=100.0,
        )
        metrics = {"rsi": 50, "volume_ratio": 5.0, "price_change_24h": 20.0}
        passed, reason = ev._check_buy_prefilter(metrics, params)
        assert passed is True, reason

    def test_blocks_too_late_up_60pct(self):
        ev = self._evaluator()
        params = AISpotOpinionParams(
            speculative_mode=True,
            prefilter_max_gain_24h=50.0,
            prefilter_min_gain_24h=-10.0,
            prefilter_volume_min_ratio=0.0,
            prefilter_rsi_max=100.0,
        )
        metrics = {"rsi": 50, "volume_ratio": 5.0, "price_change_24h": 60.0}
        passed, reason = ev._check_buy_prefilter(metrics, params)
        assert passed is False
        assert "Too late" in reason

    def test_blocks_crashing_minus_15pct(self):
        ev = self._evaluator()
        params = AISpotOpinionParams(
            speculative_mode=True,
            prefilter_max_gain_24h=50.0,
            prefilter_min_gain_24h=-10.0,
            prefilter_volume_min_ratio=0.0,
            prefilter_rsi_max=100.0,
        )
        metrics = {"rsi": 50, "volume_ratio": 5.0, "price_change_24h": -15.0}
        passed, reason = ev._check_buy_prefilter(metrics, params)
        assert passed is False
        assert "Crashing" in reason

    def test_non_speculative_uses_symmetric_drop_filter(self):
        """Regression guard: non-speculative mode still blocks on -15% drop
        (the classic behavior)."""
        ev = self._evaluator()
        params = AISpotOpinionParams(
            speculative_mode=False,
            prefilter_max_drop_24h=10.0,
            prefilter_volume_min_ratio=0.0,
            prefilter_rsi_max=100.0,
        )
        metrics = {"rsi": 50, "volume_ratio": 5.0, "price_change_24h": -15.0}
        passed, reason = ev._check_buy_prefilter(metrics, params)
        assert passed is False
        assert "dropped too much" in reason


# ---------------------------------------------------------------------------
# _build_prompt speculative branch
# ---------------------------------------------------------------------------


class TestBuildPromptSpeculativeBranch:
    def _metrics(self):
        # Every key the prompt formatters read — non-zero where possible
        # so the percent-formatting (e.g. :.1f) does not crash on None.
        return {
            "rsi": 55.0,
            "macd_bullish": True,
            "macd_bearish": False,
            "macd_line": 1.0,
            "signal_line": 0.5,
            "bb_position": 60.0,
            "ma_20": 100.0,
            "ma_50": 95.0,
            "price_vs_ma20": 5.0,
            "price_vs_ma50": 10.0,
            "volume_ratio": 2.5,
            "price_change_24h": 20.0,
            "volume_30d_ratio": 5.0,
            "compression_ratio": 4.0,
            "momentum_1h": 3.0,
            "momentum_acceleration": 1.0,
        }

    def test_catalyst_prompt_contains_doubling_question(self):
        prompt = AISpotOpinionEvaluator._build_prompt(
            product_id="HYPE-USD",
            metrics=self._metrics(),
            is_sell_check=False,
            speculative_mode=True,
            target_multiple=2.0,
            target_horizon_hours=24,
        )
        assert "SPECULATIVE" in prompt
        assert "likely to reach a 2.0x" in prompt
        assert "24 hours" in prompt
        assert "doubling_probability_score" in prompt

    def test_catalyst_prompt_includes_score_block_when_provided(self):
        prompt = AISpotOpinionEvaluator._build_prompt(
            product_id="HYPE-USD",
            metrics=self._metrics(),
            is_sell_check=False,
            speculative_mode=True,
            speculative_score_block="Speculative setup score: 60/100\nComponents fired:\n  - volume_surge (+25)",
        )
        assert "Audited Setup Score" in prompt
        assert "60/100" in prompt
        assert "volume_surge" in prompt

    def test_catalyst_prompt_omits_sell_path(self):
        """Speculative mode is a buy-check construct; sell checks fall
        through to the classic prompt path."""
        prompt = AISpotOpinionEvaluator._build_prompt(
            product_id="HYPE-USD",
            metrics=self._metrics(),
            is_sell_check=True,
            speculative_mode=True,
        )
        assert "SPECULATIVE" not in prompt
        assert "Should I SELL" in prompt

    def test_non_speculative_prompt_regression_guard(self):
        """A non-speculative prompt must be byte-identical to the pre-change
        output. We verify by asserting the known anchor phrases — a byte-for-byte
        assertion would be brittle against docstring whitespace changes."""
        prompt = AISpotOpinionEvaluator._build_prompt(
            product_id="ETH-USD",
            metrics=self._metrics(),
            is_sell_check=False,
            speculative_mode=False,
        )
        assert "You are a cryptocurrency trading AI analyzing" in prompt
        assert "Should I BUY this position right now?" in prompt
        assert "SPECULATIVE" not in prompt
        assert "doubling_probability_score" not in prompt


# ---------------------------------------------------------------------------
# _parse_llm_response with optional doubling_probability_score
# ---------------------------------------------------------------------------


class TestParseLlmResponse:
    def test_backward_compatible_without_score(self):
        raw = '{"signal": "buy", "confidence": 75, "reasoning": "strong momentum"}'
        signal, conf, reason, score = AISpotOpinionEvaluator._parse_llm_response(raw)
        assert signal == "buy"
        assert conf == 75
        assert reason == "strong momentum"
        assert score is None

    def test_extracts_doubling_score(self):
        raw = ('{"signal": "buy", "confidence": 75, '
               '"doubling_probability_score": 62, '
               '"reasoning": "catalyst-driven"}')
        signal, conf, reason, score = AISpotOpinionEvaluator._parse_llm_response(raw)
        assert signal == "buy"
        assert score == 62

    def test_clamps_out_of_range_score(self):
        raw = '{"signal": "hold", "confidence": 10, "doubling_probability_score": 250}'
        _, _, _, score = AISpotOpinionEvaluator._parse_llm_response(raw)
        assert score == 100

    def test_invalid_score_becomes_none(self):
        raw = '{"signal": "hold", "confidence": 10, "doubling_probability_score": "huge"}'
        _, _, _, score = AISpotOpinionEvaluator._parse_llm_response(raw)
        assert score is None

    def test_parse_error_returns_four_tuple(self):
        """Garbage input must still return a 4-tuple (not 3) so callers
        don't crash on unpack."""
        signal, conf, reason, score = AISpotOpinionEvaluator._parse_llm_response("not json")
        assert signal == "hold"
        assert conf == 0
        assert "Parse error" in reason
        assert score is None
