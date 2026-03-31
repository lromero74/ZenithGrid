"""
QFL (Quick Fingers Luke) Indicator Evaluator

QFL is a contrarian strategy that identifies historically validated support levels
("bases") and signals when price temporarily cracks below them due to panic selling.

A base is a pivot low that was followed by a significant bounce (≥ bounce_pct).
A crack occurs when the current price drops crack_pct% below a validated base.

Reference: quickfingersluc.com / 3Commas QFL implementation

Signal: 1 when price is cracking below a validated base, 0 otherwise.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_LOOKBACK = 100       # candles to scan for bases
_DEFAULT_BOUNCE_PCT = 3.0     # min bounce % to validate a base
_DEFAULT_CRACK_PCT = 2.0      # how far below base triggers a crack
_DEFAULT_PIVOT_WINDOW = 3     # candles on each side to confirm a pivot low


@dataclass
class QFLParams:
    """Parameters for QFL indicator evaluation."""

    base_timeframe: str = "ONE_HOUR"          # timeframe to find support bases
    crack_timeframe: str = "FIFTEEN_MINUTE"   # timeframe to detect price crack
    lookback_candles: int = _DEFAULT_LOOKBACK
    bounce_pct: float = _DEFAULT_BOUNCE_PCT
    crack_pct: float = _DEFAULT_CRACK_PCT
    pivot_window: int = _DEFAULT_PIVOT_WINDOW

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "QFLParams":
        # timeframe key is used for backwards compatibility (crack detection timeframe)
        default_tf = config.get("timeframe", "ONE_HOUR")
        return cls(
            base_timeframe=config.get("qfl_base_timeframe", "ONE_HOUR"),
            crack_timeframe=config.get("qfl_crack_timeframe", default_tf),
            lookback_candles=int(config.get("qfl_lookback_candles", _DEFAULT_LOOKBACK)),
            bounce_pct=float(config.get("qfl_bounce_pct", _DEFAULT_BOUNCE_PCT)),
            crack_pct=float(config.get("qfl_crack_pct", _DEFAULT_CRACK_PCT)),
            pivot_window=int(config.get("qfl_pivot_window", _DEFAULT_PIVOT_WINDOW)),
        )


@dataclass
class QFLResult:
    """Result of QFL crack detection."""

    signal: int                              # 0 or 1
    bases: List[float]                       # all validated base levels found
    cracked_base: Optional[float] = None     # the base being cracked (if signal=1)
    crack_depth_pct: Optional[float] = None  # how far below base current price is
    rejection_reason: Optional[str] = None


def _find_bases(candles: List[Dict[str, Any]], bounce_pct: float, pivot_window: int) -> List[float]:
    """
    Identify QFL base levels from closed candle data.

    A base is a pivot low (lower than pivot_window candles on both sides) that
    was subsequently followed by a price bounce of at least bounce_pct.

    Args:
        candles: List of OHLCV candle dicts (closed candles only).
        bounce_pct: Minimum % bounce from the pivot low to validate a base.
        pivot_window: Number of candles on each side required to confirm a pivot.

    Returns:
        List of validated base price levels (ascending).
    """
    bases: List[float] = []
    n = len(candles)

    # Need pivot_window candles on each side + lookahead for bounce detection
    lookahead = 50  # candles to look forward for the bounce high

    for i in range(pivot_window, n - pivot_window):
        pivot_low = float(candles[i]["low"])

        # Confirm local low: lower than pivot_window candles on each side
        is_pivot = all(
            pivot_low <= float(candles[j]["low"])
            for j in range(i - pivot_window, i + pivot_window + 1)
            if j != i
        )
        if not is_pivot:
            continue

        # Scan forward for the bounce high
        end_idx = min(n, i + 1 + lookahead)
        future_candles = candles[i + 1:end_idx]
        if not future_candles:
            continue

        max_high = max(float(c["high"]) for c in future_candles)
        if pivot_low <= 0:
            continue
        bounce = (max_high - pivot_low) / pivot_low * 100.0

        if bounce >= bounce_pct:
            bases.append(pivot_low)
            logger.debug(f"QFL base found at {pivot_low:.4f} (bounce={bounce:.2f}%)")

    return sorted(set(bases))


class QFLIndicatorEvaluator:
    """
    Evaluates the QFL crack indicator.

    Returns signal=1 when the current price has cracked crack_pct% below any
    validated base found in the lookback window.

    Usage:
        evaluator = QFLIndicatorEvaluator()
        result = evaluator.evaluate(candles, params)
        if result.signal == 1:
            # Price is below a QFL base — potential bounce opportunity
    """

    def evaluate(
        self,
        candles: List[Dict[str, Any]],
        params: Optional[QFLParams] = None,
        base_candles: Optional[List[Dict[str, Any]]] = None,
    ) -> QFLResult:
        """
        Evaluate QFL crack indicator.

        Args:
            candles: Candle data for crack detection (lower TF).
                     Includes the current (incomplete) candle as last entry.
            params: QFL parameters.
            base_candles: Optional candle data for base identification (higher TF).
                          If None, bases are identified from 'candles'.

        Returns:
            QFLResult with signal (0 or 1) and supporting data.
        """
        from app.constants import CANDLE_CACHE_TTL

        if params is None:
            params = QFLParams()

        # Enforce Base TF >= Crack TF (pro setup validation)
        base_seconds = CANDLE_CACHE_TTL.get(params.base_timeframe, 3600)
        crack_seconds = CANDLE_CACHE_TTL.get(params.crack_timeframe, 3600)
        if base_seconds < crack_seconds:
            return QFLResult(
                signal=0, bases=[],
                rejection_reason=f"Invalid setup: Base timeframe ({params.base_timeframe}) "
                                 f"must be \u2265 Crack timeframe ({params.crack_timeframe})"
            )

        min_candles = params.pivot_window * 2 + 2

        # Use provided base_candles if available, otherwise use candles
        target_base_candles = base_candles if base_candles is not None else candles
        if not target_base_candles or len(target_base_candles) < min_candles:
            return QFLResult(
                signal=0, bases=[],
                rejection_reason=f"Base candles: Need \u2265{min_candles}, got {len(target_base_candles) if target_base_candles else 0}"
            )

        if not candles:
            return QFLResult(signal=0, bases=[], rejection_reason="No crack detection candles provided")

        # Use the live price from the current (incomplete) candle for crack detection
        current_price = float(candles[-1]["close"])

        # Find bases from closed candles
        # If using separate base_candles, we assume they are already 'closed' enough
        # (the monitor typically passes full history for higher TF)
        closed_base = target_base_candles[:-1] if base_candles is None else target_base_candles

        # Apply lookback limit
        history = closed_base[-params.lookback_candles:] if params.lookback_candles < len(closed_base) else closed_base

        bases = _find_bases(history, params.bounce_pct, params.pivot_window)

        if not bases:
            return QFLResult(
                signal=0, bases=[],
                rejection_reason=f"No QFL bases found in last {len(history)} {params.base_timeframe} candles "
                                 f"(bounce_pct={params.bounce_pct}%)"
            )

        # Check if current price is cracking below any base
        crack_threshold_mult = 1.0 - (params.crack_pct / 100.0)
        for base in bases:
            crack_level = base * crack_threshold_mult
            if current_price <= crack_level:
                depth_pct = (base - current_price) / base * 100.0
                logger.debug(
                    f"QFL crack detected: base={base:.4f}, current={current_price:.4f}, "
                    f"crack_level={crack_level:.4f}, depth={depth_pct:.2f}%"
                )
                return QFLResult(
                    signal=1,
                    bases=bases,
                    cracked_base=base,
                    crack_depth_pct=depth_pct,
                )

        return QFLResult(
            signal=0,
            bases=bases,
            rejection_reason=f"Price {current_price:.4f} not cracking any base "
                             f"(closest: {min(bases, key=lambda b: abs(b - current_price)):.4f}, "
                             f"need {params.crack_pct}% below)"
        )
