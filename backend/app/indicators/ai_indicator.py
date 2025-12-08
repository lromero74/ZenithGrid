"""
AI Indicator Evaluator

Provides AI_BUY and AI_SELL aggregate indicators that use multi-timeframe
confluence analysis to identify high-probability trading setups.

These indicators return binary signals (0 or 1) and can be used in the
condition builder like any other indicator:
    AI_BUY == 1
    AI_SELL == 1

Parameters are configurable per-indicator via risk presets or manual overrides.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.indicators.confluence_calculator import (
    ConfluenceCalculator,
    ConfluenceResult,
    SetupType,
)
from app.indicators.risk_presets import RISK_PRESETS

logger = logging.getLogger(__name__)


@dataclass
class AIIndicatorParams:
    """Parameters for AI_BUY or AI_SELL indicator evaluation."""

    # Risk preset (aggressive, moderate, conservative) - sets defaults
    risk_preset: str = "moderate"

    # Confluence thresholds (max scores are ~50-65, so thresholds calibrated accordingly)
    min_confluence_score: int = 40  # Minimum score (0-100) to trigger (moderate default)
    ai_confidence_threshold: int = 70  # Legacy - now uses confluence score

    # Timeframe settings
    entry_timeframe: str = "FIFTEEN_MINUTE"  # Fine-grained entry timing
    trend_timeframe: str = "FOUR_HOUR"  # Higher timeframe for trend

    # Filters
    require_trend_alignment: bool = True  # Require trend TF to align
    max_volatility: Optional[float] = 10.0  # Max BB width % (None = no limit)

    # Setup type filters (which setups to accept)
    allowed_setups: List[str] = None  # None = all setups allowed

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "AIIndicatorParams":
        """Create params from strategy config dict."""
        # Start with risk preset defaults
        preset_name = config.get("risk_preset", "moderate")
        preset = RISK_PRESETS.get(preset_name, RISK_PRESETS["moderate"])

        return cls(
            risk_preset=preset_name,
            min_confluence_score=config.get(
                "min_confluence_score", preset["min_confluence_score"]
            ),
            ai_confidence_threshold=config.get(
                "ai_confidence_threshold", preset["ai_confidence_threshold"]
            ),
            entry_timeframe=config.get("entry_timeframe", preset["entry_timeframe"]),
            trend_timeframe=config.get("trend_timeframe", preset["trend_timeframe"]),
            require_trend_alignment=config.get(
                "require_trend_alignment", preset["require_trend_alignment"]
            ),
            max_volatility=config.get("max_volatility", preset.get("max_volatility")),
            allowed_setups=config.get("allowed_setups"),
        )


class AIIndicatorEvaluator:
    """
    Evaluates AI_BUY and AI_SELL aggregate indicators.

    These indicators combine multiple technical indicators across timeframes
    to produce high-confidence trading signals. The underlying confluence
    calculator scores setups (0-100) based on indicator alignment.

    Usage:
        evaluator = AIIndicatorEvaluator()
        result = await evaluator.evaluate_ai_buy(
            candles_entry=fifteen_min_candles,
            candles_trend=four_hour_candles,
            current_price=current_price,
            params=AIIndicatorParams.from_config(bot_config)
        )
        if result["signal"] == 1:
            # AI_BUY triggered
    """

    def __init__(self):
        self.confluence_calc = ConfluenceCalculator()

    def evaluate_ai_buy(
        self,
        candles_entry: List[Dict[str, Any]],
        candles_trend: List[Dict[str, Any]],
        current_price: float,
        params: Optional[AIIndicatorParams] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate AI_BUY indicator.

        Returns 1 if confluence score meets threshold and all filters pass.

        Args:
            candles_entry: Entry timeframe candles (e.g., 15M)
            candles_trend: Trend timeframe candles (e.g., 4H)
            current_price: Current market price
            params: Indicator parameters (uses moderate preset if None)

        Returns:
            Dict with:
                - signal: 0 or 1
                - confluence_score: 0-100
                - setup_type: detected setup type
                - trend_direction: bullish/bearish/neutral
                - explanation: human-readable reason
                - indicators: all calculated indicator values
        """
        if params is None:
            params = AIIndicatorParams()

        # Calculate confluence
        result = self.confluence_calc.calculate_confluence(
            candles_entry=candles_entry,
            candles_trend=candles_trend,
            current_price=current_price,
        )

        # Evaluate signal based on params
        signal, reason = self._evaluate_buy_signal(result, params)

        logger.debug(
            f"AI_BUY evaluation: signal={signal}, score={result.score}, "
            f"setup={result.setup_type.value}, trend={result.trend_direction}"
        )

        return {
            "signal": signal,
            "confluence_score": result.score,
            "setup_type": result.setup_type.value,
            "trend_direction": result.trend_direction,
            "explanation": reason,
            "indicators": result.indicators,
        }

    def _evaluate_buy_signal(
        self, result: ConfluenceResult, params: AIIndicatorParams
    ) -> Tuple[int, str]:
        """
        Apply filters to confluence result to determine if AI_BUY should trigger.

        Returns:
            Tuple of (signal: 0 or 1, reason: str)
        """
        # Check minimum confluence score
        if result.score < params.min_confluence_score:
            return (
                0,
                f"Score {result.score} below threshold {params.min_confluence_score}",
            )

        # Check setup type filter
        if result.setup_type == SetupType.NONE:
            return 0, "No valid setup detected"

        if params.allowed_setups:
            allowed = [s.lower() for s in params.allowed_setups]
            if result.setup_type.value not in allowed:
                return (
                    0,
                    f"Setup type {result.setup_type.value} not in allowed list {allowed}",
                )

        # Check trend alignment filter
        if params.require_trend_alignment:
            # For buy signals, we want bullish or at least neutral trend
            if result.trend_direction == "bearish":
                return 0, "Trend is bearish, require_trend_alignment=True"

        # Check volatility filter (BB width)
        if params.max_volatility is not None:
            entry_indicators = result.indicators.get("entry", {})
            bb_upper = entry_indicators.get("bb_upper")
            bb_lower = entry_indicators.get("bb_lower")
            bb_middle = entry_indicators.get("bb_middle")

            if bb_upper and bb_lower and bb_middle and bb_middle > 0:
                bb_width_pct = ((bb_upper - bb_lower) / bb_middle) * 100
                if bb_width_pct > params.max_volatility:
                    return (
                        0,
                        f"Volatility {bb_width_pct:.1f}% exceeds max {params.max_volatility}%",
                    )

        # All filters passed - signal is 1
        return 1, result.explanation

    def evaluate_ai_sell(
        self,
        candles_entry: List[Dict[str, Any]],
        candles_trend: List[Dict[str, Any]],
        current_price: float,
        entry_price: float,
        profit_pct: float,
        params: Optional[AIIndicatorParams] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate AI_SELL indicator.

        Returns 1 if sell conditions are met (overbought, trend reversal, etc.)

        Args:
            candles_entry: Entry timeframe candles
            candles_trend: Trend timeframe candles
            current_price: Current market price
            entry_price: Position entry price
            profit_pct: Current profit percentage
            params: Indicator parameters

        Returns:
            Dict with:
                - signal: 0 or 1
                - confluence_score: 0-100 (sell urgency)
                - trend_direction: current trend
                - explanation: human-readable reason
                - indicators: all calculated indicator values
        """
        if params is None:
            params = AIIndicatorParams()

        # Calculate sell confluence
        result = self.confluence_calc.calculate_sell_confluence(
            candles_entry=candles_entry,
            candles_trend=candles_trend,
            current_price=current_price,
            entry_price=entry_price,
            profit_pct=profit_pct,
        )

        # Evaluate signal
        signal, reason = self._evaluate_sell_signal(result, params, profit_pct)

        logger.debug(
            f"AI_SELL evaluation: signal={signal}, score={result.score}, "
            f"profit={profit_pct:.2f}%, trend={result.trend_direction}"
        )

        return {
            "signal": signal,
            "confluence_score": result.score,
            "trend_direction": result.trend_direction,
            "explanation": reason,
            "indicators": result.indicators,
        }

    def _evaluate_sell_signal(
        self, result: ConfluenceResult, params: AIIndicatorParams, profit_pct: float
    ) -> Tuple[int, str]:
        """
        Apply filters to determine if AI_SELL should trigger.

        Sell signals are more aggressive at higher profits.
        """
        # Adjust threshold based on profit level
        # Higher profits = more willing to sell
        if profit_pct >= 5:
            adjusted_threshold = params.min_confluence_score - 20
        elif profit_pct >= 3:
            adjusted_threshold = params.min_confluence_score - 10
        elif profit_pct >= 1:
            adjusted_threshold = params.min_confluence_score
        else:
            # Below 1% profit, require stronger signal to sell
            adjusted_threshold = params.min_confluence_score + 15

        adjusted_threshold = max(30, min(90, adjusted_threshold))

        if result.score < adjusted_threshold:
            return (
                0,
                f"Sell score {result.score} below adjusted threshold {adjusted_threshold} (profit={profit_pct:.2f}%)",
            )

        # If trend turns bearish and we have profit, be more aggressive about selling
        if result.trend_direction == "bearish" and profit_pct > 0:
            return 1, f"Trend turned bearish with {profit_pct:.2f}% profit - {result.explanation}"

        return 1, result.explanation

    def get_required_timeframes(
        self, params: Optional[AIIndicatorParams] = None
    ) -> List[str]:
        """
        Get the timeframes required for AI indicator evaluation.

        Returns:
            List of timeframe strings (e.g., ["FIFTEEN_MINUTE", "FOUR_HOUR"])
        """
        if params is None:
            params = AIIndicatorParams()

        return [params.entry_timeframe, params.trend_timeframe]


# Convenience functions for direct indicator evaluation
def evaluate_ai_buy_indicator(
    candles_entry: List[Dict[str, Any]],
    candles_trend: List[Dict[str, Any]],
    current_price: float,
    config: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Convenience function to evaluate AI_BUY indicator.

    Returns:
        0 or 1
    """
    evaluator = AIIndicatorEvaluator()
    params = AIIndicatorParams.from_config(config or {})
    result = evaluator.evaluate_ai_buy(
        candles_entry=candles_entry,
        candles_trend=candles_trend,
        current_price=current_price,
        params=params,
    )
    return result["signal"]


def evaluate_ai_sell_indicator(
    candles_entry: List[Dict[str, Any]],
    candles_trend: List[Dict[str, Any]],
    current_price: float,
    entry_price: float,
    profit_pct: float,
    config: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Convenience function to evaluate AI_SELL indicator.

    Returns:
        0 or 1
    """
    evaluator = AIIndicatorEvaluator()
    params = AIIndicatorParams.from_config(config or {})
    result = evaluator.evaluate_ai_sell(
        candles_entry=candles_entry,
        candles_trend=candles_trend,
        current_price=current_price,
        entry_price=entry_price,
        profit_pct=profit_pct,
        params=params,
    )
    return result["signal"]
