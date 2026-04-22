"""
Tests for _apply_risk_preset_defaults and the speculative preset
auto-population branch in backend/app/bot_routers/bot_crud_router.py.

See PRPs/high-risk-doubling-preset.md §Task C2.
"""

from app.bot_routers.bot_crud_router import _apply_risk_preset_defaults


class TestApplyRiskPresetDefaults:
    def test_no_preset_returns_config_unchanged(self):
        cfg = {"take_profit_percentage": 5.0, "foo": "bar"}
        merged = _apply_risk_preset_defaults(cfg)
        assert merged == cfg
        # Must be a fresh dict — mutating merged should not leak back
        merged["foo"] = "zzz"
        assert cfg["foo"] == "bar"

    def test_unknown_preset_returns_config_unchanged(self):
        cfg = {"ai_risk_preset": "not_a_real_preset", "take_profit_percentage": 5.0}
        merged = _apply_risk_preset_defaults(cfg)
        assert merged == cfg

    def test_empty_config_returns_empty(self):
        assert _apply_risk_preset_defaults({}) == {}
        assert _apply_risk_preset_defaults(None) == {}

    def test_speculative_preset_fills_defaults(self):
        cfg = {"ai_risk_preset": "speculative"}
        merged = _apply_risk_preset_defaults(cfg)
        # From the speculative preset
        assert merged["is_speculative"] == "true"
        assert merged["speculative_mode"] is True
        assert merged["target_multiple"] == 2.0
        assert merged["speculative_max_hold_hours"] == 24
        assert merged["stop_loss_enabled"] is True
        assert merged["stop_loss_percentage"] == -12.0
        assert merged["max_safety_orders"] == 0
        # User's own key is preserved
        assert merged["ai_risk_preset"] == "speculative"

    def test_user_values_win_over_preset(self):
        """Explicit user overrides must survive — preset only fills missing keys."""
        cfg = {
            "ai_risk_preset": "speculative",
            "stop_loss_percentage": -8.0,    # user tighter than preset default
            "take_profit_percentage": 40.0,  # user wider than preset default
        }
        merged = _apply_risk_preset_defaults(cfg)
        assert merged["stop_loss_percentage"] == -8.0
        assert merged["take_profit_percentage"] == 40.0
        # Other preset keys still fill in
        assert merged["speculative_max_hold_hours"] == 24
        assert merged["is_speculative"] == "true"

    def test_idempotent(self):
        """Applying the preset twice produces the same result as applying once."""
        cfg = {"ai_risk_preset": "speculative", "stop_loss_percentage": -8.0}
        once = _apply_risk_preset_defaults(cfg)
        twice = _apply_risk_preset_defaults(once)
        assert once == twice

    def test_works_for_existing_presets(self):
        """The helper handles the original three presets too (not just speculative)."""
        cfg = {"ai_risk_preset": "moderate"}
        merged = _apply_risk_preset_defaults(cfg)
        # moderate preset's known defaults
        assert merged["min_confluence_score"] == 40
        assert merged["ai_confidence_threshold"] == 70
        assert merged["entry_timeframe"] == "FIFTEEN_MINUTE"
