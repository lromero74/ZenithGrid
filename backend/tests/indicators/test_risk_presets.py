"""
Tests for backend/app/indicators/risk_presets.py

Ensures the three original presets and the new "speculative" preset
are well-formed and return the expected defaults.
"""

import pytest

from app.indicators.risk_presets import RISK_PRESETS, get_risk_preset_defaults


class TestExistingPresets:
    """Regression guard: existing presets must keep the same shape."""

    @pytest.mark.parametrize("name", ["aggressive", "moderate", "conservative"])
    def test_existing_preset_has_required_keys(self, name):
        preset = RISK_PRESETS[name]
        for key in (
            "min_confluence_score",
            "ai_confidence_threshold",
            "entry_timeframe",
            "trend_timeframe",
            "require_trend_alignment",
            "max_volatility",
        ):
            assert key in preset, f"{name} missing {key}"


class TestSpeculativePreset:
    """The "speculative" preset is new in PRP high-risk-doubling-preset."""

    def test_preset_exists(self):
        assert "speculative" in RISK_PRESETS

    def test_is_speculative_is_string_true(self):
        """MUST be the string "true" — not bool True — for cross-DB JSON
        extraction compatibility. See speculative_bucket_service docstring."""
        preset = RISK_PRESETS["speculative"]
        assert preset["is_speculative"] == "true"
        assert isinstance(preset["is_speculative"], str)

    def test_catalyst_mode_flag_is_bool(self):
        """speculative_mode is a Python bool consumed by the AI prompt
        builder — distinct from is_speculative which is a JSON string."""
        preset = RISK_PRESETS["speculative"]
        assert preset["speculative_mode"] is True

    def test_exit_discipline_defaults(self):
        """Preset bakes in the PRP's exit discipline: tight SL, trailing TP,
        no safety orders, time-based max hold."""
        preset = RISK_PRESETS["speculative"]
        assert preset["stop_loss_enabled"] is True
        assert preset["stop_loss_percentage"] == -12.0
        assert preset["trailing_take_profit"] is True
        assert preset["take_profit_percentage"] == 25.0
        assert preset["max_safety_orders"] == 0
        assert preset["speculative_max_hold_hours"] == 24

    def test_target_doubling_config(self):
        preset = RISK_PRESETS["speculative"]
        assert preset["target_multiple"] == 2.0
        assert preset["target_horizon_hours"] == 24

    def test_prefilter_allows_already_up_setups(self):
        """The catalyst hunt must not reject coins already up today — the
        upper bound (prefilter_max_gain_24h) is how we block too-late entries."""
        preset = RISK_PRESETS["speculative"]
        assert preset["prefilter_max_gain_24h"] == 50.0
        assert preset["prefilter_min_gain_24h"] == -10.0

    def test_get_risk_preset_defaults_returns_copy(self):
        """Verifies the existing helper returns a mutable copy, not the
        live dict — callers should be able to merge overrides safely."""
        a = get_risk_preset_defaults("speculative")
        b = get_risk_preset_defaults("speculative")
        a["take_profit_percentage"] = 999.0
        assert b["take_profit_percentage"] == 25.0
