"""
VWAP Bounce Indicator Evaluator

Provides VWAP_BOUNCE_UP and VWAP_BOUNCE_DOWN as aggregate indicators that detect
when price bounces off the VWAP level.

Bounce definition (user-specified):
  VWAP_BOUNCE_UP:
    - The penultimate closed candle's LOW touched or crossed below VWAP (the "retest")
    - The last closed candle's CLOSE is above VWAP (the "bounce confirmation")

  VWAP_BOUNCE_DOWN:
    - The penultimate closed candle's HIGH touched or crossed above VWAP (the "retest")
    - The last closed candle's CLOSE is below VWAP (the "bounce confirmation")

A wick touch (not a full close through VWAP) is sufficient for the retest candle,
matching how traders visually interpret VWAP bounces.

These indicators return a binary signal (0 or 1) and can be used in the condition
builder like any other aggregate indicator.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class VWAPBounceParams:
    """Parameters for VWAP bounce indicator evaluation."""

    timeframe: str = "FIVE_MINUTE"

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "VWAPBounceParams":
        return cls(timeframe=config.get("timeframe", "FIVE_MINUTE"))


@dataclass
class VWAPBounceResult:
    """Result of VWAP bounce pattern detection."""

    signal: int        # 0 or 1
    vwap: Optional[float] = None
    retest_low: Optional[float] = None    # penultimate candle low (for bounce up)
    retest_high: Optional[float] = None   # penultimate candle high (for bounce down)
    confirm_close: Optional[float] = None
    rejection_reason: Optional[str] = None


def _calculate_vwap(candles: List[Dict[str, Any]]) -> Optional[float]:
    """Calculate VWAP over the provided closed candles."""
    cumulative_tp_vol = 0.0
    cumulative_vol = 0.0
    for c in candles:
        h = float(c.get("high", 0))
        lo = float(c.get("low", 0))
        cl = float(c.get("close", 0))
        v = float(c.get("volume", 0))
        cumulative_tp_vol += ((h + lo + cl) / 3.0) * v
        cumulative_vol += v
    return cumulative_tp_vol / cumulative_vol if cumulative_vol > 0 else None


class VWAPBounceIndicatorEvaluator:
    """
    Evaluates VWAP_BOUNCE_UP and VWAP_BOUNCE_DOWN aggregate indicators.

    Both use the two most recent CLOSED candles (the current candle is excluded
    as it is still forming):
      - candles[-2] is the current candle (incomplete, excluded)
      - candles[-3] is the last fully closed candle (bounce confirmation)
      - candles[-4] is the penultimate closed candle (the retest)

    VWAP is calculated over all closed candles available.
    """

    def evaluate_bounce_up(
        self,
        candles: List[Dict[str, Any]],
        params: Optional[VWAPBounceParams] = None,
    ) -> VWAPBounceResult:
        """
        Detect a bullish VWAP bounce: price came down to test VWAP and
        closed back above it on the most recent closed candle.
        """
        if params is None:
            params = VWAPBounceParams()

        # Need at least: enough candles for VWAP + 2 reference candles + 1 incomplete
        if not candles or len(candles) < 4:
            return VWAPBounceResult(
                signal=0, rejection_reason=f"Need ≥4 candles, got {len(candles) if candles else 0}"
            )

        # Exclude the last (incomplete) candle from VWAP and pattern detection
        closed = candles[:-1]

        vwap = _calculate_vwap(closed)
        if vwap is None:
            return VWAPBounceResult(signal=0, rejection_reason="Could not calculate VWAP (zero volume)")

        # The two most recent closed candles
        confirm_candle = closed[-1]   # last closed — should close above VWAP
        retest_candle = closed[-2]    # penultimate closed — low should have touched VWAP

        retest_low = float(retest_candle.get("low", 0))
        confirm_close = float(confirm_candle.get("close", 0))

        # Bounce up conditions:
        #   1. Retest candle's low <= VWAP (wick touched or crossed below)
        #   2. Confirmation candle's close > VWAP (closed back above)
        if retest_low <= vwap and confirm_close > vwap:
            logger.debug(
                f"VWAP_BOUNCE_UP detected: vwap={vwap:.4f}, "
                f"retest_low={retest_low:.4f}, confirm_close={confirm_close:.4f}"
            )
            return VWAPBounceResult(
                signal=1,
                vwap=vwap,
                retest_low=retest_low,
                confirm_close=confirm_close,
            )

        reason = (
            f"Bounce up not met: vwap={vwap:.4f}, "
            f"retest_low={retest_low:.4f} ({'✓' if retest_low <= vwap else '✗'} ≤ vwap), "
            f"confirm_close={confirm_close:.4f} ({'✓' if confirm_close > vwap else '✗'} > vwap)"
        )
        logger.debug(f"VWAP_BOUNCE_UP not detected: {reason}")
        return VWAPBounceResult(signal=0, vwap=vwap, rejection_reason=reason)

    def evaluate_bounce_down(
        self,
        candles: List[Dict[str, Any]],
        params: Optional[VWAPBounceParams] = None,
    ) -> VWAPBounceResult:
        """
        Detect a bearish VWAP bounce: price came up to test VWAP and
        closed back below it on the most recent closed candle.
        """
        if params is None:
            params = VWAPBounceParams()

        if not candles or len(candles) < 4:
            return VWAPBounceResult(
                signal=0, rejection_reason=f"Need ≥4 candles, got {len(candles) if candles else 0}"
            )

        closed = candles[:-1]

        vwap = _calculate_vwap(closed)
        if vwap is None:
            return VWAPBounceResult(signal=0, rejection_reason="Could not calculate VWAP (zero volume)")

        confirm_candle = closed[-1]
        retest_candle = closed[-2]

        retest_high = float(retest_candle.get("high", 0))
        confirm_close = float(confirm_candle.get("close", 0))

        # Bounce down conditions:
        #   1. Retest candle's high >= VWAP (wick touched or crossed above)
        #   2. Confirmation candle's close < VWAP (closed back below)
        if retest_high >= vwap and confirm_close < vwap:
            logger.debug(
                f"VWAP_BOUNCE_DOWN detected: vwap={vwap:.4f}, "
                f"retest_high={retest_high:.4f}, confirm_close={confirm_close:.4f}"
            )
            return VWAPBounceResult(
                signal=1,
                vwap=vwap,
                retest_high=retest_high,
                confirm_close=confirm_close,
            )

        reason = (
            f"Bounce down not met: vwap={vwap:.4f}, "
            f"retest_high={retest_high:.4f} ({'✓' if retest_high >= vwap else '✗'} ≥ vwap), "
            f"confirm_close={confirm_close:.4f} ({'✓' if confirm_close < vwap else '✗'} < vwap)"
        )
        logger.debug(f"VWAP_BOUNCE_DOWN not detected: {reason}")
        return VWAPBounceResult(signal=0, vwap=vwap, rejection_reason=reason)
