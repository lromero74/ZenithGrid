"""
Risk Presets for AI Indicators

Defines default configurations for different risk tolerance levels.
Separated from __init__.py to avoid circular imports.
"""

RISK_PRESETS = {
    "aggressive": {
        "min_confluence_score": 50,
        "ai_confidence_threshold": 60,
        "entry_timeframe": "FIVE_MINUTE",
        "trend_timeframe": "ONE_HOUR",
        "require_trend_alignment": False,
        "max_volatility": None,
    },
    "moderate": {
        "min_confluence_score": 65,
        "ai_confidence_threshold": 70,
        "entry_timeframe": "FIFTEEN_MINUTE",
        "trend_timeframe": "FOUR_HOUR",
        "require_trend_alignment": True,
        "max_volatility": 10.0,
    },
    "conservative": {
        "min_confluence_score": 80,
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
