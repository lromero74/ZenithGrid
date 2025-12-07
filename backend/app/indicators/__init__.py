"""
Aggregate Indicators Package

Provides higher-level "aggregate indicators" that combine multiple signals
for use in the condition-based bot building system.

Available Aggregate Indicators:
- AI_BUY: AI-powered buy signal with confluence analysis
- AI_SELL: AI-powered sell signal
- BULL_FLAG: Bull flag pattern detection

These indicators return 0 or 1 (binary signals) and can be used
in conditions like: AI_BUY == 1
"""

from .risk_presets import RISK_PRESETS, get_risk_preset_defaults
from .confluence_calculator import ConfluenceCalculator, ConfluenceResult, SetupType
from .ai_indicator import AIIndicatorEvaluator
from .bull_flag_indicator import BullFlagIndicatorEvaluator


__all__ = [
    "ConfluenceCalculator",
    "ConfluenceResult",
    "SetupType",
    "AIIndicatorEvaluator",
    "BullFlagIndicatorEvaluator",
    "RISK_PRESETS",
    "get_risk_preset_defaults",
]
