"""
Aggregate Indicators Package

Provides higher-level "aggregate indicators" that combine multiple signals
for use in the condition-based bot building system.

Available Aggregate Indicators:
- AI_OPINION: AI-powered buy/sell/hold signals with LLM reasoning and confidence scores
- BULL_FLAG: Bull flag pattern detection

These indicators can be used in conditions like: ai_opinion == "buy" AND ai_confidence >= 70
"""

from .risk_presets import RISK_PRESETS, get_risk_preset_defaults
from .ai_spot_opinion import AISpotOpinionEvaluator, AISpotOpinionParams
from .bull_flag_indicator import BullFlagIndicatorEvaluator


__all__ = [
    "AISpotOpinionEvaluator",
    "AISpotOpinionParams",
    "BullFlagIndicatorEvaluator",
    "RISK_PRESETS",
    "get_risk_preset_defaults",
]
