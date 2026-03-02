"""
Bull Flag Indicator Evaluator

Provides BULL_FLAG as an aggregate indicator that detects bull flag chart patterns.

This indicator returns a binary signal (0 or 1) and can be used in the
condition builder:
    BULL_FLAG == 1

The indicator wraps the existing bull flag scanner logic from strategies/bull_flag_scanner.py
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Lazy-imported to break circular import chain:
# indicators.__init__ → bull_flag_indicator → strategies.bull_flag_scanner
# → strategies.__init__ → indicator_based → indicators.__init__

logger = logging.getLogger(__name__)


@dataclass
class BullFlagParams:
    """Parameters for BULL_FLAG indicator evaluation."""

    # Pattern detection settings
    timeframe: str = "FIFTEEN_MINUTE"
    min_pole_candles: int = 3
    min_pole_gain_pct: float = 3.0
    min_pullback_candles: int = 2
    max_pullback_candles: int = 8
    pullback_retracement_max: float = 50.0
    reward_risk_ratio: float = 2.0

    # Volume spike settings (optional - can be checked externally)
    require_volume_spike: bool = False
    volume_multiplier: float = 5.0

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "BullFlagParams":
        """Create params from strategy config dict."""
        return cls(
            timeframe=config.get("timeframe", "FIFTEEN_MINUTE"),
            min_pole_candles=config.get("min_pole_candles", 3),
            min_pole_gain_pct=config.get("min_pole_gain_pct", 3.0),
            min_pullback_candles=config.get("min_pullback_candles", 2),
            max_pullback_candles=config.get("max_pullback_candles", 8),
            pullback_retracement_max=config.get("pullback_retracement_max", 50.0),
            reward_risk_ratio=config.get("reward_risk_ratio", 2.0),
            require_volume_spike=config.get("require_volume_spike", False),
            volume_multiplier=config.get("volume_multiplier", 5.0),
        )

    def to_scanner_config(self) -> Dict[str, Any]:
        """Convert to config dict for detect_bull_flag_pattern()."""
        return {
            "min_pole_candles": self.min_pole_candles,
            "min_pole_gain_pct": self.min_pole_gain_pct,
            "min_pullback_candles": self.min_pullback_candles,
            "max_pullback_candles": self.max_pullback_candles,
            "pullback_retracement_max": self.pullback_retracement_max,
            "reward_risk_ratio": self.reward_risk_ratio,
        }


@dataclass
class BullFlagResult:
    """Result of bull flag pattern detection."""

    signal: int  # 0 or 1
    pattern_valid: bool
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_target: Optional[float] = None
    pole_gain_pct: Optional[float] = None
    retracement_pct: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    volume_ratio: Optional[float] = None
    rejection_reason: Optional[str] = None
    pattern_data: Dict[str, Any] = field(default_factory=dict)


class BullFlagIndicatorEvaluator:
    """
    Evaluates BULL_FLAG aggregate indicator.

    This indicator detects bull flag chart patterns:
    - Strong upward move (the "pole")
    - Consolidation/pullback (the "flag")
    - Confirmation candle breaking out

    Usage:
        evaluator = BullFlagIndicatorEvaluator()
        result = evaluator.evaluate(
            candles=fifteen_min_candles,
            current_price=current_price,
            params=BullFlagParams.from_config(bot_config)
        )
        if result.signal == 1:
            # Bull flag pattern detected
    """

    def evaluate(
        self,
        candles: List[Dict[str, Any]],
        current_price: float,
        params: Optional[BullFlagParams] = None,
    ) -> BullFlagResult:
        """
        Evaluate BULL_FLAG indicator.

        Returns 1 if a valid bull flag pattern is detected.

        Args:
            candles: Candle data for the configured timeframe
            current_price: Current market price
            params: Indicator parameters

        Returns:
            BullFlagResult with signal (0 or 1) and pattern details
        """
        if params is None:
            params = BullFlagParams()

        if not candles or len(candles) < 10:
            return BullFlagResult(
                signal=0,
                pattern_valid=False,
                rejection_reason=f"Insufficient candles: {len(candles) if candles else 0}",
            )

        # Convert params to scanner config
        config = params.to_scanner_config()

        # Run pattern detection (lazy import to break circular import)
        from app.strategies.bull_flag_scanner import detect_bull_flag_pattern
        pattern, rejection_reason = detect_bull_flag_pattern(candles, config)

        if pattern and pattern.get("pattern_valid"):
            logger.debug(
                f"BULL_FLAG detected: entry={pattern['entry_price']:.4f}, "
                f"SL={pattern['stop_loss']:.4f}, TP={pattern['take_profit_target']:.4f}"
            )

            return BullFlagResult(
                signal=1,
                pattern_valid=True,
                entry_price=pattern.get("entry_price"),
                stop_loss=pattern.get("stop_loss"),
                take_profit_target=pattern.get("take_profit_target"),
                pole_gain_pct=pattern.get("pole_gain_pct"),
                retracement_pct=pattern.get("retracement_pct"),
                risk_reward_ratio=pattern.get("risk_reward_ratio"),
                volume_ratio=pattern.get("volume_ratio"),
                pattern_data=pattern,
            )
        else:
            logger.debug(f"BULL_FLAG not detected: {rejection_reason}")

            return BullFlagResult(
                signal=0,
                pattern_valid=False,
                rejection_reason=rejection_reason,
            )

    def get_required_timeframe(
        self, params: Optional[BullFlagParams] = None
    ) -> str:
        """
        Get the timeframe required for bull flag evaluation.

        Returns:
            Timeframe string (e.g., "FIFTEEN_MINUTE")
        """
        if params is None:
            params = BullFlagParams()
        return params.timeframe


# Convenience function for direct indicator evaluation
def evaluate_bull_flag_indicator(
    candles: List[Dict[str, Any]],
    current_price: float,
    config: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Convenience function to evaluate BULL_FLAG indicator.

    Returns:
        0 or 1
    """
    evaluator = BullFlagIndicatorEvaluator()
    params = BullFlagParams.from_config(config or {})
    result = evaluator.evaluate(
        candles=candles,
        current_price=current_price,
        params=params,
    )
    return result.signal


def evaluate_bull_flag_indicator_with_details(
    candles: List[Dict[str, Any]],
    current_price: float,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluate BULL_FLAG indicator and return full details.

    Returns:
        Dict with signal, pattern_valid, entry_price, stop_loss,
        take_profit_target, and other pattern details
    """
    evaluator = BullFlagIndicatorEvaluator()
    params = BullFlagParams.from_config(config or {})
    result = evaluator.evaluate(
        candles=candles,
        current_price=current_price,
        params=params,
    )

    return {
        "signal": result.signal,
        "pattern_valid": result.pattern_valid,
        "entry_price": result.entry_price,
        "stop_loss": result.stop_loss,
        "take_profit_target": result.take_profit_target,
        "pole_gain_pct": result.pole_gain_pct,
        "retracement_pct": result.retracement_pct,
        "risk_reward_ratio": result.risk_reward_ratio,
        "volume_ratio": result.volume_ratio,
        "rejection_reason": result.rejection_reason,
        "pattern_data": result.pattern_data,
    }
