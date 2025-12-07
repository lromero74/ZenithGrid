"""
Confluence Calculator for Multi-Timeframe Technical Analysis

Calculates confluence scores (0-100) based on alignment of technical indicators
across multiple timeframes. Used by AI_BUY/AI_SELL indicators to identify
high-probability trading setups.

Setup Types:
- MOMENTUM_TREND: Trend following with momentum confirmation
- OVERSOLD_BOUNCE: Mean reversion from oversold conditions
- BREAKOUT: Volatility expansion breakout
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Tuple

from app.indicator_calculator import IndicatorCalculator

logger = logging.getLogger(__name__)


class SetupType(str, Enum):
    """Types of trading setups detected by confluence analysis."""

    MOMENTUM_TREND = "momentum_trend"
    OVERSOLD_BOUNCE = "oversold_bounce"
    BREAKOUT = "breakout"
    NONE = "none"


@dataclass
class ConfluenceResult:
    """Result of confluence calculation."""

    score: int  # 0-100
    setup_type: SetupType
    trend_direction: str  # "bullish", "bearish", "neutral"
    explanation: str
    indicators: Dict[str, Any]  # All calculated indicator values


class ConfluenceCalculator:
    """
    Calculates multi-timeframe confluence scores for AI trading decisions.

    The confluence score (0-100) indicates how many technical indicators
    align to support a trading setup. Higher scores = higher probability.

    Timeframes:
    - Entry timeframe (e.g., 15M): Used for precise entry timing
    - Trend timeframe (e.g., 1H): Used for overall trend confirmation
    """

    def __init__(self):
        self.calc = IndicatorCalculator()

    def calculate_confluence(
        self,
        candles_entry: List[Dict[str, Any]],
        candles_trend: List[Dict[str, Any]],
        current_price: float,
    ) -> ConfluenceResult:
        """
        Calculate confluence score and detect setup type.

        Args:
            candles_entry: Entry timeframe candles (e.g., 15M)
            candles_trend: Trend timeframe candles (e.g., 1H)
            current_price: Current market price

        Returns:
            ConfluenceResult with score, setup type, and explanation
        """
        # Calculate indicators for both timeframes
        entry_indicators = self._calculate_timeframe_indicators(candles_entry, current_price)
        trend_indicators = self._calculate_timeframe_indicators(candles_trend, current_price)

        # Detect trend direction from trend timeframe
        trend_direction = self._detect_trend_direction(trend_indicators, current_price)

        # Score each setup type
        momentum_score, momentum_details = self._score_momentum_trend(entry_indicators, trend_indicators, current_price)
        oversold_score, oversold_details = self._score_oversold_bounce(
            entry_indicators, trend_indicators, current_price
        )
        breakout_score, breakout_details = self._score_breakout(entry_indicators, trend_indicators, current_price)

        # Pick the best setup
        best_score = max(momentum_score, oversold_score, breakout_score)

        if best_score < 20:
            setup_type = SetupType.NONE
            explanation = "No clear setup - indicators mixed or neutral"
        elif momentum_score == best_score:
            setup_type = SetupType.MOMENTUM_TREND
            explanation = momentum_details
        elif oversold_score == best_score:
            setup_type = SetupType.OVERSOLD_BOUNCE
            explanation = oversold_details
        else:
            setup_type = SetupType.BREAKOUT
            explanation = breakout_details

        # Apply trend alignment bonus/penalty
        alignment_bonus = self._calculate_trend_alignment(setup_type, trend_direction, entry_indicators)
        final_score = min(100, max(0, best_score + alignment_bonus))

        # Combine all indicators for reference
        all_indicators = {
            "entry": entry_indicators,
            "trend": trend_indicators,
            "trend_direction": trend_direction,
        }

        logger.debug(
            f"Confluence: {final_score}/100 ({setup_type.value}) - "
            f"trend={trend_direction}, momentum={momentum_score}, "
            f"oversold={oversold_score}, breakout={breakout_score}"
        )

        return ConfluenceResult(
            score=final_score,
            setup_type=setup_type,
            trend_direction=trend_direction,
            explanation=explanation,
            indicators=all_indicators,
        )

    def _calculate_timeframe_indicators(
        self, candles: List[Dict[str, Any]], current_price: float
    ) -> Dict[str, Any]:
        """Calculate all indicators for a single timeframe."""
        if not candles or len(candles) < 35:  # Need at least 35 for MACD (26+9)
            return {}

        closes = [float(c["close"]) for c in candles]
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]

        result = {}

        # RSI
        rsi = self.calc.calculate_rsi(closes, 14)
        if rsi is not None:
            result["rsi_14"] = rsi

        # MACD
        macd_line, signal_line, histogram = self.calc.calculate_macd(closes, 12, 26, 9)
        if histogram is not None:
            result["macd_histogram"] = histogram
            result["macd_line"] = macd_line
            result["macd_signal"] = signal_line

        # Bollinger Bands and BB%
        bb_upper, bb_middle, bb_lower = self.calc.calculate_bollinger_bands(closes, 20, 2.0)
        if bb_upper is not None:
            result["bb_upper"] = bb_upper
            result["bb_middle"] = bb_middle
            result["bb_lower"] = bb_lower
            # Calculate BB%
            if bb_upper != bb_lower:
                result["bb_percent"] = (current_price - bb_lower) / (bb_upper - bb_lower)
            else:
                result["bb_percent"] = 0.5

        # EMA for trend
        ema_20 = self.calc.calculate_ema(closes, 20)
        if ema_20 is not None:
            result["ema_20"] = ema_20

        # Stochastic
        stoch_k, stoch_d = self.calc.calculate_stochastic(highs, lows, closes, 14, 3)
        if stoch_k is not None:
            result["stoch_k"] = stoch_k
            result["stoch_d"] = stoch_d

        return result

    def _detect_trend_direction(self, trend_indicators: Dict[str, Any], current_price: float) -> str:
        """Detect trend direction from trend timeframe indicators."""
        if not trend_indicators:
            return "neutral"

        bullish_signals = 0
        bearish_signals = 0

        # Price vs EMA20
        ema = trend_indicators.get("ema_20")
        if ema:
            if current_price > ema * 1.005:  # 0.5% above
                bullish_signals += 2
            elif current_price < ema * 0.995:  # 0.5% below
                bearish_signals += 2

        # MACD histogram
        macd_hist = trend_indicators.get("macd_histogram", 0)
        if macd_hist > 0:
            bullish_signals += 1
        elif macd_hist < 0:
            bearish_signals += 1

        # RSI
        rsi = trend_indicators.get("rsi_14", 50)
        if rsi > 55:
            bullish_signals += 1
        elif rsi < 45:
            bearish_signals += 1

        if bullish_signals >= bearish_signals + 2:
            return "bullish"
        elif bearish_signals >= bullish_signals + 2:
            return "bearish"
        return "neutral"

    def _score_momentum_trend(
        self, entry: Dict[str, Any], trend: Dict[str, Any], current_price: float
    ) -> Tuple[int, str]:
        """
        Score MOMENTUM_TREND setup.

        Criteria:
        - Entry TF: RSI 40-70 (not overbought)
        - Entry TF: MACD histogram positive
        - Entry TF: Price above EMA20
        - Trend TF: Price above EMA20 (bullish trend)
        """
        if not entry or not trend:
            return 0, ""

        score = 0
        details = []

        # RSI in healthy range (40-65)
        rsi = entry.get("rsi_14", 50)
        if 40 <= rsi <= 65:
            score += 15
            details.append(f"RSI {rsi:.0f} (healthy)")
        elif 35 <= rsi < 40 or 65 < rsi <= 70:
            score += 8
            details.append(f"RSI {rsi:.0f} (borderline)")

        # MACD histogram positive
        macd_hist = entry.get("macd_histogram", 0)
        if macd_hist > 0:
            score += 15
            details.append(f"MACD+ ({macd_hist:.6f})")
        elif macd_hist > -0.0001:  # Nearly zero
            score += 5
            details.append("MACD neutral")

        # Price above entry EMA20
        ema = entry.get("ema_20")
        if ema and current_price > ema:
            score += 10
            details.append("Above entry EMA20")

        # Trend timeframe bullish
        trend_ema = trend.get("ema_20")
        if trend_ema and current_price > trend_ema:
            score += 10
            details.append("Trend bullish")

        explanation = f"MOMENTUM: {', '.join(details)}" if details else ""
        return score, explanation

    def _score_oversold_bounce(
        self, entry: Dict[str, Any], trend: Dict[str, Any], current_price: float
    ) -> Tuple[int, str]:
        """
        Score OVERSOLD_BOUNCE setup.

        Criteria:
        - Entry TF: RSI < 35 (oversold)
        - Entry TF: BB% < 0.2 (near lower band)
        - Entry TF: MACD histogram turning positive
        - Entry TF: Stochastic oversold confirmation
        """
        if not entry:
            return 0, ""

        score = 0
        details = []

        # RSI oversold
        rsi = entry.get("rsi_14", 50)
        if rsi < 30:
            score += 20
            details.append(f"RSI {rsi:.0f} (oversold)")
        elif rsi < 35:
            score += 15
            details.append(f"RSI {rsi:.0f} (near oversold)")
        elif rsi < 40:
            score += 5
            details.append(f"RSI {rsi:.0f} (weakening)")

        # BB% near lower band
        bb_pct = entry.get("bb_percent", 0.5)
        if bb_pct < 0.1:
            score += 15
            details.append(f"BB% {bb_pct:.2f} (extreme)")
        elif bb_pct < 0.2:
            score += 12
            details.append(f"BB% {bb_pct:.2f} (oversold)")
        elif bb_pct < 0.3:
            score += 5
            details.append(f"BB% {bb_pct:.2f}")

        # MACD turning up (histogram > previous or positive)
        macd_hist = entry.get("macd_histogram", 0)
        if macd_hist > 0:
            score += 10
            details.append("MACD turning up")
        elif macd_hist > -0.0002:
            score += 5
            details.append("MACD flattening")

        # Stochastic oversold confirmation
        stoch_k = entry.get("stoch_k", 50)
        if stoch_k < 20:
            score += 5
            details.append(f"Stoch {stoch_k:.0f} (oversold)")

        explanation = f"OVERSOLD: {', '.join(details)}" if details else ""
        return score, explanation

    def _score_breakout(
        self, entry: Dict[str, Any], trend: Dict[str, Any], current_price: float
    ) -> Tuple[int, str]:
        """
        Score BREAKOUT setup.

        Criteria:
        - Entry TF: BB% > 0.8 or near upper band
        - Entry TF: Strong momentum (RSI rising, MACD positive)
        - Trend TF: Trend supportive
        """
        if not entry:
            return 0, ""

        score = 0
        details = []

        # BB% near upper band
        bb_pct = entry.get("bb_percent", 0.5)
        if bb_pct > 0.9:
            score += 15
            details.append(f"BB% {bb_pct:.2f} (breakout zone)")
        elif bb_pct > 0.8:
            score += 12
            details.append(f"BB% {bb_pct:.2f} (upper band)")
        elif bb_pct > 0.7:
            score += 5
            details.append(f"BB% {bb_pct:.2f}")

        # Strong momentum - RSI in 55-75 range
        rsi = entry.get("rsi_14", 50)
        if 55 <= rsi <= 75:
            score += 15
            details.append(f"RSI {rsi:.0f} (momentum)")
        elif 50 < rsi < 55:
            score += 8
            details.append(f"RSI {rsi:.0f}")

        # MACD positive and strong
        macd_hist = entry.get("macd_histogram", 0)
        if macd_hist > 0:
            score += 10
            details.append("MACD+ (momentum)")

        # Trend supportive
        if trend:
            trend_ema = trend.get("ema_20")
            if trend_ema and current_price > trend_ema:
                score += 10
                details.append("Trend supportive")

        explanation = f"BREAKOUT: {', '.join(details)}" if details else ""
        return score, explanation

    def _calculate_trend_alignment(
        self, setup_type: SetupType, trend_direction: str, entry_indicators: Dict[str, Any]
    ) -> int:
        """Calculate bonus/penalty for trend alignment."""
        bonus = 0

        # For momentum and breakout, aligned trends add bonus
        if setup_type in [SetupType.MOMENTUM_TREND, SetupType.BREAKOUT]:
            if trend_direction == "bullish":
                bonus += 15
            elif trend_direction == "bearish":
                bonus -= 10  # Counter-trend penalty

        # For oversold bounce in downtrend, less penalty (expecting reversal)
        elif setup_type == SetupType.OVERSOLD_BOUNCE:
            if trend_direction == "bullish":
                bonus += 10  # Dip in uptrend is good
            elif trend_direction == "bearish":
                bonus -= 5  # Catching falling knife is risky

        return bonus

    def calculate_sell_confluence(
        self,
        candles_entry: List[Dict[str, Any]],
        candles_trend: List[Dict[str, Any]],
        current_price: float,
        entry_price: float,
        profit_pct: float,
    ) -> ConfluenceResult:
        """
        Calculate sell confluence - when to exit a position.

        Considers:
        - Overbought conditions (RSI > 70, BB% > 0.9)
        - Trend reversal signals
        - Profit level
        """
        entry_indicators = self._calculate_timeframe_indicators(candles_entry, current_price)
        trend_indicators = self._calculate_timeframe_indicators(candles_trend, current_price)

        score = 0
        details = []

        # Overbought RSI
        rsi = entry_indicators.get("rsi_14", 50)
        if rsi > 80:
            score += 25
            details.append(f"RSI {rsi:.0f} (overbought)")
        elif rsi > 70:
            score += 15
            details.append(f"RSI {rsi:.0f} (near overbought)")

        # BB% near upper band
        bb_pct = entry_indicators.get("bb_percent", 0.5)
        if bb_pct > 0.95:
            score += 20
            details.append(f"BB% {bb_pct:.2f} (extreme)")
        elif bb_pct > 0.9:
            score += 15
            details.append(f"BB% {bb_pct:.2f} (high)")

        # MACD turning negative
        macd_hist = entry_indicators.get("macd_histogram", 0)
        if macd_hist < 0:
            score += 15
            details.append("MACD- (momentum fading)")
        elif macd_hist < 0.0001:
            score += 5
            details.append("MACD flattening")

        # Profit bonus (more willing to sell at higher profits)
        if profit_pct >= 5:
            score += 15
            details.append(f"+{profit_pct:.1f}% profit")
        elif profit_pct >= 3:
            score += 10
            details.append(f"+{profit_pct:.1f}% profit")

        # Trend reversal
        trend_ema = trend_indicators.get("ema_20")
        if trend_ema and current_price < trend_ema:
            score += 10
            details.append("Below trend EMA")

        explanation = f"SELL SIGNALS: {', '.join(details)}" if details else "No strong sell signals"

        return ConfluenceResult(
            score=min(100, score),
            setup_type=SetupType.NONE,  # Sell doesn't have setup types
            trend_direction=self._detect_trend_direction(trend_indicators, current_price),
            explanation=explanation,
            indicators={"entry": entry_indicators, "trend": trend_indicators},
        )
