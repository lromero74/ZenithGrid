"""
Indicator-calculation methods for IndicatorBasedStrategy.

Extracted from indicator_based.py as a mixin to keep that file under the size
limit. These methods compute the per-cycle indicator snapshot (traditional, AI,
bull-flag, VWAP-bounce, QFL, fear/greed) and load a position's prior indicators.
They run on the composed IndicatorBasedStrategy instance (self), so they rely on
attributes/evaluators set up in its __init__.
"""

import logging
from typing import Any, Dict, List, Optional

from app.indicators import VWAPBounceParams, QFLParams, FearGreedParams
from app.strategies.indicator_based_helpers import (
    build_ai_params,
    build_bull_flag_params,
    flatten_conditions,
)

logger = logging.getLogger(__name__)

# Track QFL base_timeframe fallback warnings — log once per product+TF combo, not every cycle
_qfl_base_fallback_warned: set = set()

# Timeframe prefixes used to split indicator keys (e.g. "FIVE_MINUTE_RSI"). Module-level
# so it isn't reallocated every strategy cycle in the per-pair hot path.
_TF_PREFIXES = frozenset([
    "ONE", "TWO", "THREE", "FOUR", "FIVE",
    "SIX", "TEN", "FIFTEEN", "THIRTY",
])


class IndicatorCalculationMixin:
    """Indicator-snapshot computation methods mixed into IndicatorBasedStrategy."""

    def _load_previous_indicators(self, position: Optional[Any], **kwargs) -> None:
        """
        Load previous_indicators for crossing detection.

        Persists across check cycles (strategy instances are recreated each cycle).
        Priority: 1) Position-based storage (for open positions)
                  2) Monitor-level cache (for entry conditions, passed via kwargs)
        """
        if position is not None and hasattr(position, 'previous_indicators') and position.previous_indicators:
            self.previous_indicators = position.previous_indicators
            logger.debug(f"Loaded previous_indicators from position {position.id}")
        elif kwargs.get('previous_indicators_cache'):
            self.previous_indicators = kwargs['previous_indicators_cache']
            logger.debug("Loaded previous_indicators from monitor cache (entry conditions)")

    def _calculate_traditional_indicators(
        self,
        candles_by_timeframe: Dict[str, List[Dict[str, Any]]],
        candles: List[Dict[str, Any]],
        min_candles_needed: int,
    ) -> Dict[str, Any]:
        """
        Calculate traditional indicators (RSI, MACD, BB%, etc.) for each required timeframe.

        Extracts required indicators from all phase conditions, determines which timeframes
        are needed, then calculates indicators per timeframe with previous-candle values
        for crossing detection.

        Returns:
            Dict of indicator values keyed by {timeframe}_{indicator_name}.
        """
        current_indicators: Dict[str, Any] = {}

        # Extract required traditional indicators from conditions
        # Uses get_required_indicators_from_expression which handles both formats
        required_indicators: set = set()
        required_indicators.update(
            self.phase_evaluator.get_required_indicators_from_expression(self.base_order_conditions)
        )
        required_indicators.update(
            self.phase_evaluator.get_required_indicators_from_expression(self.safety_order_conditions)
        )
        required_indicators.update(
            self.phase_evaluator.get_required_indicators_from_expression(self.take_profit_conditions)
        )

        # E9: Single-pass to build timeframe→indicator mapping (O(I) instead of O(T×I))
        tf_to_indicators: dict = {}
        for indicator_key in required_indicators:
            parts = indicator_key.split("_", 2)
            if len(parts) >= 2 and parts[0] in _TF_PREFIXES:
                timeframe = f"{parts[0]}_{parts[1]}"
                indicator_name = indicator_key[len(timeframe) + 1:]
                tf_to_indicators.setdefault(timeframe, set()).add(indicator_name)

        # Calculate traditional indicators for each timeframe
        for timeframe, tf_required in tf_to_indicators.items():
            tf_candles = candles_by_timeframe.get(timeframe, candles)
            if len(tf_candles) < min_candles_needed:
                current_indicators[f"{timeframe}_missing_reason"] = (
                    f"not enough {timeframe} candles: {len(tf_candles)}/{min_candles_needed}"
                )
                continue

            # calculate_previous=True enables crossing detection by calculating
            # indicators for both current candle and previous candle (prev_ prefix)
            # E10: Pass previous_indicators as cache to skip recursive recalculation
            indicators_for_tf = self.indicator_calculator.calculate_all_indicators(
                tf_candles, tf_required, calculate_previous=True,
                previous_indicators_cache=self.previous_indicators,
            )

            for key, value in indicators_for_tf.items():
                # Handle prev_ prefix correctly: prev_rsi_14 -> prev_{timeframe}_rsi_14
                # This ensures crossing detection works properly
                if key.startswith("prev_"):
                    indicator_name = key[5:]  # Remove "prev_" prefix
                    current_indicators[f"prev_{timeframe}_{indicator_name}"] = value
                else:
                    current_indicators[f"{timeframe}_{key}"] = value

        return current_indicators

    async def _calculate_ai_indicators(
        self,
        needs: Dict[str, Any],
        current_indicators: Dict[str, Any],
        candles: List[Dict[str, Any]],
        current_price: float,
        position: Optional[Any],
        **kwargs,
    ) -> None:
        """
        Calculate AI aggregate indicators if needed (ai_opinion, ai_confidence, etc.).

        Uses cached AI values when available, otherwise calls the AI evaluator fresh.
        Mutates current_indicators in place to add AI-related keys.
        """
        if not (needs["ai_buy"] or needs["ai_sell"]):
            return

        # Check if we should use cached AI values (from previous check) or call AI fresh
        use_cached_ai = kwargs.get("use_cached_ai", False)
        previous_indicators_cache = kwargs.get("previous_indicators_cache")

        # If using cached AI and we have cached values, reuse them
        if use_cached_ai and previous_indicators_cache:
            current_indicators["ai_opinion"] = previous_indicators_cache.get("ai_opinion", "hold")
            current_indicators["ai_confidence"] = previous_indicators_cache.get("ai_confidence", 0)
            current_indicators["ai_reasoning"] = previous_indicators_cache.get(
                "ai_reasoning", "Using cached AI values"
            )
            current_indicators["ai_buy"] = previous_indicators_cache.get("ai_buy", 0)
            current_indicators["ai_sell"] = previous_indicators_cache.get("ai_sell", 0)
        else:
            # Call AI fresh (full AI check)
            ai_params = build_ai_params(self.config)

            # Evaluate AI opinion for buy or sell
            # We call it once - for buy checks (no position) or sell checks (with position)
            product_id = kwargs.get("product_id", "UNKNOWN")
            is_sell_check = (
                position is not None
                and (needs["ai_sell"] or "ai_opinion" in str(self.take_profit_conditions))
            )

            if needs["ai_buy"] or needs["ai_sell"]:
                # Get db and user_id from kwargs (passed from signal_processor)
                db = kwargs.get("db")
                user_id = kwargs.get("user_id")
                if not db or not user_id:
                    raise ValueError("AI strategies require db and user_id in kwargs")

                bot = kwargs.get("bot")
                account_id = kwargs.get("account_id")
                ai_result = await self.ai_evaluator.evaluate(
                    candles=candles,
                    current_price=current_price,
                    product_id=product_id,
                    db=db,
                    user_id=user_id,
                    params=ai_params,
                    is_sell_check=is_sell_check,
                    bot=bot,
                    account_id=account_id,
                    position=position,
                )
                # Store AI opinion results
                current_indicators["ai_opinion"] = ai_result["signal"]  # "buy", "sell", or "hold"
                current_indicators["ai_confidence"] = ai_result["confidence"]  # 0-100
                current_indicators["ai_reasoning"] = ai_result["reasoning"]

                # For backward compatibility during migration (deprecated)
                # Map to old indicator names temporarily
                if ai_result["signal"] == "buy":
                    current_indicators["ai_buy"] = 1
                    current_indicators["ai_sell"] = 0
                elif ai_result["signal"] == "sell":
                    current_indicators["ai_buy"] = 0
                    current_indicators["ai_sell"] = 1
                else:  # hold
                    current_indicators["ai_buy"] = 0
                    current_indicators["ai_sell"] = 0

    def _calculate_bull_flag_indicators(
        self,
        candles_by_timeframe: Dict[str, List[Dict[str, Any]]],
        candles: List[Dict[str, Any]],
        current_price: float,
        current_indicators: Dict[str, Any],
    ) -> None:
        """
        Calculate bull flag pattern detection indicators.

        Mutates current_indicators in place to add bull_flag-related keys.
        """
        bf_params = build_bull_flag_params(self.config)
        bf_candles = candles_by_timeframe.get(bf_params.timeframe, candles)
        bf_result = self.bull_flag_evaluator.evaluate(
            candles=bf_candles,
            current_price=current_price,
            params=bf_params,
        )
        current_indicators["bull_flag"] = bf_result.signal
        if bf_result.signal == 1:
            current_indicators["bull_flag_entry"] = bf_result.entry_price
            current_indicators["bull_flag_stop"] = bf_result.stop_loss
            current_indicators["bull_flag_target"] = bf_result.take_profit_target

    def _calculate_vwap_bounce_indicators(
        self,
        candles_by_timeframe: Dict[str, List[Dict[str, Any]]],
        candles: List[Dict[str, Any]],
        needs: Dict[str, Any],
        current_indicators: Dict[str, Any],
    ) -> None:
        """
        Calculate VWAP bounce pattern indicators.

        Uses the timeframe from the first vwap_bounce_* condition found in any phase.
        Mutates current_indicators in place.
        """
        # Determine timeframe from the first matching condition
        timeframe = "FIVE_MINUTE"
        for cond_list in [self.base_order_conditions, self.safety_order_conditions, self.take_profit_conditions]:
            for cond in flatten_conditions(cond_list):
                if cond.get("type") in ("vwap_bounce_up", "vwap_bounce_down"):
                    timeframe = cond.get("timeframe", "FIVE_MINUTE")
                    break

        params = VWAPBounceParams(timeframe=timeframe)
        tf_candles = candles_by_timeframe.get(timeframe, candles)

        if needs["vwap_bounce_up"]:
            result = self.vwap_bounce_evaluator.evaluate_bounce_up(tf_candles, params)
            current_indicators["vwap_bounce_up"] = result.signal

        if needs["vwap_bounce_down"]:
            result = self.vwap_bounce_evaluator.evaluate_bounce_down(tf_candles, params)
            current_indicators["vwap_bounce_down"] = result.signal

    def _calculate_qfl_indicators(
        self,
        candles_by_timeframe: Dict[str, List[Dict[str, Any]]],
        candles: List[Dict[str, Any]],
        current_indicators: Dict[str, Any],
    ) -> None:
        """
        Calculate QFL (Quick Fingers Luke) crack indicator.

        Supports multi-timeframe: Base identification (higher TF) and
        Crack detection (lower TF).
        Mutates current_indicators in place.
        """
        # Determine timeframe and config params from the first matching condition
        base_timeframe = "ONE_HOUR"
        crack_timeframe = "FIFTEEN_MINUTE"
        config_overrides: Dict[str, Any] = {}

        for cond_list in [self.base_order_conditions, self.safety_order_conditions, self.take_profit_conditions]:
            for cond in flatten_conditions(cond_list):
                if cond.get("type") == "qfl_crack":
                    # Default timeframe in condition is the crack (signal) timeframe
                    crack_timeframe = cond.get("timeframe", "FIFTEEN_MINUTE")
                    # Optional base_timeframe for identifying bases on a higher TF
                    base_timeframe = cond.get("base_timeframe", cond.get("timeframe", "ONE_HOUR"))

                    config_overrides = {
                        "qfl_base_timeframe": base_timeframe,
                        "qfl_crack_timeframe": crack_timeframe,
                        "qfl_lookback_candles": cond.get("lookback_candles", 100),
                        "qfl_bounce_pct": cond.get("bounce_pct", 3.0),
                        "qfl_crack_pct": cond.get("crack_pct", 2.0),
                        "qfl_pivot_window": cond.get("pivot_window", 3),
                    }
                    break

        params = QFLParams.from_config({**self.config, **config_overrides})

        # Get candles for both timeframes
        crack_candles = candles_by_timeframe.get(crack_timeframe, candles)
        base_candles = candles_by_timeframe.get(base_timeframe)  # None if same TF or not fetched

        if base_timeframe != crack_timeframe and base_candles is None:
            fallback_key = f"{base_timeframe}:{crack_timeframe}"
            if fallback_key not in _qfl_base_fallback_warned:
                _qfl_base_fallback_warned.add(fallback_key)
                logger.info(
                    f"QFL: base_timeframe={base_timeframe} candles not available "
                    f"in candles_by_timeframe; falling back to "
                    f"crack_timeframe={crack_timeframe} for base identification "
                    f"(subsequent fallbacks silenced)"
                )

        # If base_timeframe is same as crack_timeframe, pass None so evaluate() uses single-TF logic
        effective_base_candles = base_candles if base_timeframe != crack_timeframe else None

        result = self.qfl_evaluator.evaluate(crack_candles, params, base_candles=effective_base_candles)
        current_indicators["qfl_crack"] = result.signal

    async def _calculate_fear_greed_indicators(
        self,
        current_indicators: Dict[str, Any],
    ) -> None:
        """
        Calculate Fear & Greed Index indicator.

        Fetches the current Fear & Greed value from the alternative.me API
        (cached for 1 hour). Mutates current_indicators in place.
        """
        params = FearGreedParams.from_config(self.config)
        result = await self.fear_greed_evaluator.evaluate(params)
        current_indicators["fear_greed"] = result.value
        current_indicators["fear_greed_classification"] = result.classification
