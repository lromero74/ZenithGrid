"""Tests for MODEL_PRICING lookup + cost estimator (Phase F)."""

import pytest

from app.indicators.ai_pricing import (
    MODEL_PRICING,
    _match_pricing,
    estimate_cost_usd,
    provider_for_model,
)


class TestMatchPricing:
    def test_exact_match_wins(self):
        assert _match_pricing("claude-opus-4-7") == MODEL_PRICING["claude-opus-4-7"]

    def test_longest_prefix_match_for_versioned_id(self):
        """Versioned IDs like claude-sonnet-4-20250514 fall back to the dated
        row when listed, and the base family otherwise."""
        # Exact match — dated snapshot listed.
        assert _match_pricing("claude-sonnet-4-20250514") == (3.00, 15.00)
        # Unknown dated snapshot for claude-opus-4 falls back to the base row.
        assert _match_pricing("claude-opus-4-20250999") == MODEL_PRICING["claude-opus-4"]

    def test_unknown_model_returns_none(self):
        assert _match_pricing("totally-made-up-model") is None

    def test_empty_model_returns_none(self):
        assert _match_pricing("") is None
        assert _match_pricing(None) is None  # type: ignore[arg-type]

    def test_prefix_picks_longer_key(self):
        """claude-opus-4-5 (more specific) must outrank claude-opus-4."""
        assert _match_pricing("claude-opus-4-5") == MODEL_PRICING["claude-opus-4-5"]


class TestEstimateCostUsd:
    def test_known_model_computes_cost(self):
        # claude-opus-4-7 = ($15 / M input, $75 / M output).
        # 1000 input + 500 output = (1000*15 + 500*75) / 1_000_000 = 0.0525
        cost = estimate_cost_usd(
            model="claude-opus-4-7", input_tokens=1000, output_tokens=500,
        )
        assert cost == pytest.approx(0.0525, rel=1e-6)

    def test_unknown_model_returns_zero(self):
        cost = estimate_cost_usd(
            model="mystery-llm", input_tokens=1000, output_tokens=500,
        )
        assert cost == 0.0

    def test_missing_model_returns_zero(self):
        assert estimate_cost_usd(model=None, input_tokens=100, output_tokens=100) == 0.0
        assert estimate_cost_usd(model="", input_tokens=100, output_tokens=100) == 0.0

    def test_zero_tokens_returns_zero(self):
        cost = estimate_cost_usd(
            model="claude-opus-4-7", input_tokens=0, output_tokens=0,
        )
        assert cost == 0.0

    def test_none_tokens_treated_as_zero(self):
        # Guard against log rows where the column arrived as NULL.
        cost = estimate_cost_usd(
            model="claude-opus-4-7",
            input_tokens=None,  # type: ignore[arg-type]
            output_tokens=None,  # type: ignore[arg-type]
        )
        assert cost == 0.0

    def test_rounded_to_six_decimals(self):
        # claude-opus-4-7 = (15, 75). 1 in + 1 out → (15 + 75)/1M = 9.0e-5.
        # Result is 0.00009 exactly — checks the round(..., 6) stays stable.
        cost = estimate_cost_usd(
            model="claude-opus-4-7", input_tokens=1, output_tokens=1,
        )
        assert cost == pytest.approx(0.00009, rel=1e-6)

    def test_versioned_id_falls_back_to_prefix_pricing(self):
        # claude-opus-4-99999 is unknown; longest-prefix match gives claude-opus-4.
        cost_versioned = estimate_cost_usd(
            model="claude-opus-4-99999", input_tokens=1000, output_tokens=1000,
        )
        cost_base = estimate_cost_usd(
            model="claude-opus-4", input_tokens=1000, output_tokens=1000,
        )
        assert cost_versioned == cost_base


class TestProviderForModel:
    def test_claude_prefix(self):
        assert provider_for_model("claude-opus-4-7") == "claude"
        assert provider_for_model("claude-sonnet-4-5") == "claude"

    def test_gpt_prefix(self):
        assert provider_for_model("gpt-4o") == "gpt"
        assert provider_for_model("gpt-3.5-turbo") == "gpt"
        assert provider_for_model("o1-mini") == "gpt"

    def test_gemini_prefix(self):
        assert provider_for_model("gemini-2.0-flash") == "gemini"

    def test_unknown_model_returns_none(self):
        assert provider_for_model("mystery-llm") is None

    def test_missing_model_returns_none(self):
        assert provider_for_model(None) is None
        assert provider_for_model("") is None

    def test_case_insensitive(self):
        assert provider_for_model("CLAUDE-OPUS-4-7") == "claude"
        assert provider_for_model("Gemini-2.0-flash") == "gemini"
