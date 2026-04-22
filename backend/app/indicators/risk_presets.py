"""
Risk Presets for AI Indicators

Defines default configurations for different risk tolerance levels.
Separated from __init__.py to avoid circular imports.
"""

RISK_PRESETS = {
    # Scoring context: Max possible scores are ~50-65 depending on setup type
    # MOMENTUM: 15+15+10+10 = 50, +15 trend bonus = 65 max
    # OVERSOLD: 20+15+10+5 = 50, +10 trend bonus = 60 max
    # BREAKOUT: 15+15+10+10 = 50, +15 trend bonus = 65 max
    "aggressive": {
        "min_confluence_score": 30,  # Low bar - triggers on weak setups
        "ai_confidence_threshold": 60,
        "entry_timeframe": "FIVE_MINUTE",
        "trend_timeframe": "ONE_HOUR",
        "require_trend_alignment": False,
        "max_volatility": None,
    },
    "moderate": {
        "min_confluence_score": 40,  # Decent setup required
        "ai_confidence_threshold": 70,
        "entry_timeframe": "FIFTEEN_MINUTE",
        "trend_timeframe": "FOUR_HOUR",
        "require_trend_alignment": True,
        "max_volatility": 10.0,
    },
    "conservative": {
        "min_confluence_score": 50,  # Strong setup required
        "ai_confidence_threshold": 80,
        "entry_timeframe": "THIRTY_MINUTE",
        "trend_timeframe": "ONE_DAY",
        "require_trend_alignment": True,
        "max_volatility": 5.0,
    },
    # High-risk "2x in a day" catalyst hunter. Opts the bot into the
    # account-level speculative bucket (is_speculative tag) and rewires
    # the AI indicator into catalyst mode. Designed for asymmetric upside
    # with contained downside (tight SL, no safety orders, time-based exit).
    # See PRPs/high-risk-doubling-preset.md §Recommended Design §2.
    "speculative": {
        # AI evaluation
        "min_confluence_score": 35,
        "ai_confidence_threshold": 70,
        "entry_timeframe": "FIFTEEN_MINUTE",
        "trend_timeframe": "ONE_HOUR",
        "require_trend_alignment": False,
        "max_volatility": None,
        # Preset-only keys (consumed by indicator_based + ai_spot_opinion +
        # bucket service). `is_speculative` MUST be the string "true" (not
        # the bool True) — see speculative_bucket_service._speculative_bot_filter
        # docstring for the PG-vs-SQLite JSON-bool extraction difference.
        "is_speculative": "true",
        "speculative_mode": True,
        "target_multiple": 2.0,
        "target_horizon_hours": 24,
        # Exit discipline defaults
        "take_profit_percentage": 25.0,
        "trailing_take_profit": True,
        "trailing_tp_deviation": 5.0,
        "stop_loss_enabled": True,
        "stop_loss_percentage": -12.0,
        "max_safety_orders": 0,
        "speculative_max_hold_hours": 24,
        # Prefilter overrides (catalyst-hunt tuned)
        "prefilter_max_drop_24h": 10.0,
        "prefilter_max_gain_24h": 50.0,
        "prefilter_min_gain_24h": -10.0,
        "prefilter_volume_min_ratio": 1.5,
        "prefilter_rsi_max": 85.0,
    },
}


def get_risk_preset_defaults(preset_name: str) -> dict:
    """Get default parameters for a risk preset."""
    return RISK_PRESETS.get(preset_name, RISK_PRESETS["moderate"]).copy()
