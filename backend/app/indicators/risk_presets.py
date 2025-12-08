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
}


def get_risk_preset_defaults(preset_name: str) -> dict:
    """Get default parameters for a risk preset."""
    return RISK_PRESETS.get(preset_name, RISK_PRESETS["moderate"]).copy()
