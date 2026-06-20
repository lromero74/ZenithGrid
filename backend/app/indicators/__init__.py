"""
Aggregate Indicators Package

Provides higher-level "aggregate indicators" that combine multiple signals
for use in the condition-based bot building system.

Available Aggregate Indicators:
- AI_OPINION: AI-powered buy/sell/hold signals with LLM reasoning and confidence scores
- BULL_FLAG: Bull flag pattern detection
- VWAP_BOUNCE_UP / VWAP_BOUNCE_DOWN: VWAP bounce pattern detection
- QFL_CRACK: Quick Fingers Luke base crack detection

These indicators can be used in conditions like: ai_opinion == "buy" AND ai_confidence >= 70
"""

from .risk_presets import RISK_PRESETS, get_risk_preset_defaults
from .ai_spot_opinion import AISpotOpinionEvaluator, AISpotOpinionParams
from .bull_flag_indicator import BullFlagIndicatorEvaluator
from .vwap_bounce_indicator import VWAPBounceIndicatorEvaluator, VWAPBounceParams
from .qfl_indicator import QFLIndicatorEvaluator, QFLParams
from .fear_greed_indicator import FearGreedIndicatorEvaluator, FearGreedParams


__all__ = [
    "AISpotOpinionEvaluator",
    "AISpotOpinionParams",
    "BullFlagIndicatorEvaluator",
    "VWAPBounceIndicatorEvaluator",
    "VWAPBounceParams",
    "QFLIndicatorEvaluator",
    "QFLParams",
    "FearGreedIndicatorEvaluator",
    "FearGreedParams",
    "RISK_PRESETS",
    "get_risk_preset_defaults",
]
