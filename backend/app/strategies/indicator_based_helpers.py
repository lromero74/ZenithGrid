"""
Indicator-Based Strategy helpers.

Pure, side-effect-free utilities extracted from IndicatorBasedStrategy to
keep the main strategy module under the 1200-LOC cap. These helpers are
callable without an instance — they take the relevant config / conditions
as arguments.
"""

from typing import Any, Dict, List

from app.indicators import AISpotOpinionParams
from app.indicators.bull_flag_indicator import BullFlagParams


def flatten_conditions(expression) -> List[Dict[str, Any]]:
    """
    Flatten conditions from either grouped or flat format.

    Handles both:
    - New grouped format: { groups: [{ conditions: [...] }], groupLogic }
    - Old flat format: [condition1, condition2, ...]
    """
    if not expression:
        return []

    if isinstance(expression, dict) and "groups" in expression:
        conditions: List[Dict[str, Any]] = []
        for group in expression.get("groups", []):
            conditions.extend(group.get("conditions", []))
        return conditions

    if isinstance(expression, list):
        return expression

    return []


def needs_aggregate_indicators(
    base_order_conditions,
    safety_order_conditions,
    take_profit_conditions,
) -> Dict[str, Any]:
    """
    Check which aggregate indicators are needed based on conditions.

    Returns:
        Dict with keys: ai_buy, ai_sell, bull_flag, vwap_bounce_up,
        vwap_bounce_down, qfl_crack (bool).
    """
    needs = {
        "ai_buy": False,
        "ai_sell": False,
        "bull_flag": False,
        "vwap_bounce_up": False,
        "vwap_bounce_down": False,
        "qfl_crack": False,
        "fear_greed": False,
        "ai_params": None,
    }

    tp_conditions = flatten_conditions(take_profit_conditions)
    tp_ids = {id(c) for c in tp_conditions}
    all_conditions = (
        flatten_conditions(base_order_conditions)
        + flatten_conditions(safety_order_conditions)
        + tp_conditions
    )

    for condition in all_conditions:
        indicator = (condition.get("type") or condition.get("indicator") or "").lower()

        if indicator in ["ai_opinion", "ai_confidence", "ai_reasoning"]:
            if id(condition) in tp_ids:
                needs["ai_sell"] = True
            else:
                needs["ai_buy"] = True
        elif indicator == "ai_buy":
            needs["ai_buy"] = True
        elif indicator == "ai_sell":
            needs["ai_sell"] = True
        elif indicator == "bull_flag":
            needs["bull_flag"] = True
        elif indicator == "vwap_bounce_up":
            needs["vwap_bounce_up"] = True
        elif indicator == "vwap_bounce_down":
            needs["vwap_bounce_down"] = True
        elif indicator == "qfl_crack":
            needs["qfl_crack"] = True
        elif indicator == "fear_greed":
            needs["fear_greed"] = True

    return needs


def build_ai_params(config: Dict[str, Any]) -> AISpotOpinionParams:
    """Get AI Spot Opinion parameters from config."""
    return AISpotOpinionParams(
        ai_model=config.get("ai_model", "claude"),
        ai_timeframe=config.get("ai_timeframe", "15m"),
        ai_min_confidence=config.get("ai_min_confidence", 60),
        enable_buy_prefilter=config.get("enable_buy_prefilter", True),
    )


def build_bull_flag_params(config: Dict[str, Any]) -> BullFlagParams:
    """Get Bull Flag indicator parameters from config.

    Priority: explicit config > migrated config > defaults.
    """
    return BullFlagParams(
        timeframe=config.get("bull_flag_timeframe", "FIFTEEN_MINUTE"),
        min_pole_gain_pct=config.get(
            "bull_flag_min_pole_gain",
            config.get("_migrated_min_pole_gain_pct", 3.0),
        ),
        min_pole_candles=config.get(
            "bull_flag_min_pole_candles",
            config.get("_migrated_min_pole_candles", 3),
        ),
        min_pullback_candles=config.get(
            "bull_flag_min_pullback_candles",
            config.get("_migrated_min_pullback_candles", 2),
        ),
        max_pullback_candles=config.get(
            "bull_flag_max_pullback_candles",
            config.get("_migrated_max_pullback_candles", 8),
        ),
        pullback_retracement_max=config.get(
            "bull_flag_pullback_retracement_max",
            config.get("_migrated_pullback_retracement_max", 50.0),
        ),
        reward_risk_ratio=config.get(
            "bull_flag_reward_risk_ratio",
            config.get("_migrated_reward_risk_ratio", 2.0),
        ),
    )
