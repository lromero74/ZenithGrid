"""
Indicator-Based Strategy (Unified Approach)

The unified strategy that replaces all pre-baked strategies. Users configure their
bot by selecting indicators and conditions for entry, DCA, and exit phases.

This strategy supports:
- Traditional indicators (RSI, MACD, BB%, etc.)
- Aggregate indicators (AI_BUY, AI_SELL, BULL_FLAG)
- Phase-based conditions (base order, safety order, take profit)
- All DCA features (safety orders, volume scaling, step scaling)
- Risk management (TP, SL, trailing)

Migration from old strategies:
- conditional_dca → indicator_based (conditions preserved)
- ai_autonomous → indicator_based with AI_BUY/AI_SELL conditions
- bull_flag → indicator_based with BULL_FLAG condition
- Other strategies → indicator_based with equivalent conditions
"""

import logging
import math
from app.utils.timeutil import utcnow
from app.services.pnl_service import fee_adjusted_tp_floor
from typing import Any, Dict, List, Optional, Tuple

from app.indicator_calculator import IndicatorCalculator
from app.indicators import (
    AISpotOpinionEvaluator,
    BullFlagIndicatorEvaluator,
    VWAPBounceIndicatorEvaluator,
    QFLIndicatorEvaluator,
    FearGreedIndicatorEvaluator,
)
from app.phase_conditions import PhaseConditionEvaluator
from app.strategies import (
    StrategyDefinition,
    StrategyParameter,
    StrategyRegistry,
    TradingStrategy,
)
from app.strategies.indicator_based_helpers import (
    needs_aggregate_indicators,
)
from app.strategies.indicator_based_indicators import IndicatorCalculationMixin
from app.strategies.indicator_params import INDICATOR_PARAMS
from app.strategies.safety_order_calculator import (
    calculate_base_order_size as _calc_base_order_size,
    calculate_safety_order_size as _calc_safety_order_size,
    count_deployed_safety_orders,
    effective_max_safety_orders,
    entry_trades_for_position,
)

logger = logging.getLogger(__name__)


@StrategyRegistry.register
class IndicatorBasedStrategy(IndicatorCalculationMixin, TradingStrategy):
    """
    Unified indicator-based strategy.

    All trading decisions are made by evaluating user-configured conditions
    against indicator values. This includes AI-powered indicators (ai_opinion, ai_confidence)
    and pattern detection (BULL_FLAG) alongside traditional indicators.
    """

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="indicator_based",
            name="Custom Bot (Indicator-Based)",
            description="Build your own bot by selecting indicators and conditions. "
            "Mix traditional indicators (RSI, MACD, BB%) with AI-powered opinions (ai_opinion, ai_confidence) "
            "and pattern detection (BULL_FLAG). Configure entry, DCA, and exit conditions.",
            parameters=[StrategyParameter(**p) for p in INDICATOR_PARAMS],
            supported_products=["ETH-BTC", "BTC-USD", "ETH-USD", "SOL-BTC", "SOL-USD", "*-BTC", "*-USD"],
        )

    def validate_config(self):
        """Validate configuration and set defaults."""
        definition = self.get_definition()

        # Set defaults for missing parameters
        for param in definition.parameters:
            if param.name not in self.config:
                self.config[param.name] = param.default

        # Initialize calculators and evaluators
        self.indicator_calculator = IndicatorCalculator()
        self.phase_evaluator = PhaseConditionEvaluator(self.indicator_calculator)
        self.ai_evaluator = AISpotOpinionEvaluator()
        self.bull_flag_evaluator = BullFlagIndicatorEvaluator()
        self.vwap_bounce_evaluator = VWAPBounceIndicatorEvaluator()
        self.qfl_evaluator = QFLIndicatorEvaluator()
        self.fear_greed_evaluator = FearGreedIndicatorEvaluator()

        # Get phase conditions from config
        self.base_order_conditions = self.config.get("base_order_conditions", [])
        self.base_order_logic = self.config.get("base_order_logic", "and")
        self.safety_order_conditions = self.config.get("safety_order_conditions", [])
        self.safety_order_logic = self.config.get("safety_order_logic", "and")
        self.take_profit_conditions = self.config.get("take_profit_conditions", [])
        self.take_profit_logic = self.config.get("take_profit_logic", "and")

        # Track previous indicators for crossing detection
        self.previous_indicators = None

        # E8: Cache needs_aggregate_indicators result (config doesn't change per instance)
        self._needs_cache = needs_aggregate_indicators(
            self.base_order_conditions,
            self.safety_order_conditions,
            self.take_profit_conditions,
        )

    # =========================================================================
    # analyze_signal() and its private helpers
    # =========================================================================

    def _get_dca_reference_price(self, position: Any, entry_trades: List) -> float:
        """
        Determine the reference price for DCA target calculation.

        Based on dca_target_reference config: "base_order", "last_buy", or "average_price".
        Direction-aware: a short's average entry is short_average_sell_price, not
        average_buy_price (which is unset for shorts).
        """
        dca_reference = self.config.get("dca_target_reference", "average_price")
        sorted_entries = sorted(
            entry_trades, key=lambda t: t.timestamp if t.timestamp else 0
        ) if entry_trades else []

        is_short = getattr(position, "direction", "long") == "short"
        if is_short:
            # average_buy_price is always 0 for shorts; fall back to the first short
            # entry's price (NOT average_buy_price, which would collapse SO triggers to 0).
            avg_entry = (getattr(position, "short_average_sell_price", None)
                         or (sorted_entries[0].price if sorted_entries else 0.0))
        else:
            avg_entry = position.average_buy_price

        if dca_reference == "base_order" and sorted_entries:
            first = sorted_entries[0]
            return first.price if first.price else avg_entry
        elif dca_reference == "last_buy" and sorted_entries:
            last = sorted_entries[-1]
            return last.price if last.price else avg_entry
        else:
            return avg_entry

    def _evaluate_dca_price_condition(
        self,
        position: Any,
        current_price: float,
        indicator_signal: bool,
        safety_order_details: List,
    ) -> bool:
        """
        Evaluate the mandatory price-drop condition for DCA safety orders.

        Calculates the next safety order trigger price and checks whether
        the current price has reached it. Appends a price_drop detail to
        safety_order_details.

        Returns:
            True if both indicator conditions AND price drop are met.
        """
        entry_trades = entry_trades_for_position(position)  # buys for long, sells for short
        safety_orders_count = count_deployed_safety_orders(entry_trades)  # sums cascade levels
        next_order_number = safety_orders_count + 1

        reference_price = self._get_dca_reference_price(position, entry_trades)

        # Calculate trigger price using the existing method (direction-aware)
        direction = getattr(position, "direction", "long")
        trigger_price = self.calculate_safety_order_price(reference_price, next_order_number, direction)

        # Check if price target met (direction-specific)
        if direction == "long":
            price_drop_met = current_price <= trigger_price
        else:  # short
            price_drop_met = current_price >= trigger_price

        # Add price_drop as a condition detail
        price_drop_detail = {
            "type": "price_drop",
            "timeframe": "required",
            "operator": "less_equal",
            "threshold": trigger_price,
            "actual_value": current_price,
            "result": price_drop_met,
        }
        safety_order_details.append(price_drop_detail)

        # Both indicator conditions AND price drop must be met
        return indicator_signal and price_drop_met

    def _evaluate_phase_conditions(
        self,
        current_indicators: Dict[str, Any],
        current_price: float,
        position: Optional[Any],
    ) -> Tuple[bool, List, bool, List, bool, List]:
        """
        Evaluate conditions for each phase (base order, safety order, take profit).

        Handles both grouped and legacy flat condition formats via evaluate_expression.

        Returns:
            Tuple of (base_order_signal, base_order_details,
                      safety_order_signal, safety_order_details,
                      take_profit_signal, take_profit_details)
        """
        base_order_signal = False
        base_order_details: List = []
        if self.base_order_conditions:
            base_order_signal, base_order_details = self.phase_evaluator.evaluate_expression(
                self.base_order_conditions, current_indicators, self.previous_indicators, self.base_order_logic,
                capture_details=True
            )

        safety_order_signal = False
        safety_order_details: List = []
        if self.safety_order_conditions:
            # First evaluate the indicator conditions
            indicator_signal, indicator_details = self.phase_evaluator.evaluate_expression(
                self.safety_order_conditions, current_indicators, self.previous_indicators, self.safety_order_logic,
                capture_details=True
            )
            safety_order_details = indicator_details

            # For DCA, also require the price-move condition (mandatory, regardless of
            # other conditions). _evaluate_dca_price_condition is direction-aware (it
            # uses the short sell-side reference for shorts); the old
            # `position.average_buy_price` guard skipped it for shorts (avg = 0), letting
            # short safety orders fire on indicator signal alone with no price gate.
            if position is not None:
                safety_order_signal = self._evaluate_dca_price_condition(
                    position, current_price, indicator_signal, safety_order_details
                )
            else:
                # No position means DCA not applicable
                safety_order_signal = indicator_signal

        take_profit_signal = False
        take_profit_details: List = []
        if self.take_profit_conditions:
            take_profit_signal, take_profit_details = self.phase_evaluator.evaluate_expression(
                self.take_profit_conditions, current_indicators, self.previous_indicators, self.take_profit_logic,
                capture_details=True
            )

        return (
            base_order_signal, base_order_details,
            safety_order_signal, safety_order_details,
            take_profit_signal, take_profit_details,
        )

    def _build_signal_response(
        self,
        current_indicators: Dict[str, Any],
        current_price: float,
        position: Optional[Any],
        base_order_signal: bool,
        base_order_details: List,
        safety_order_signal: bool,
        safety_order_details: List,
        take_profit_signal: bool,
        take_profit_details: List,
    ) -> Dict[str, Any]:
        """
        Store indicators for persistence and construct the signal response dict.

        Saves current_indicators as previous for the next iteration (crossing detection)
        and persists to position if available.
        """
        # Store current as previous for next iteration
        self.previous_indicators = current_indicators.copy()

        # Save current_indicators to position for persistence across check cycles
        # This enables crossing_above/crossing_below operators to work
        if position is not None and hasattr(position, 'previous_indicators'):
            position.previous_indicators = current_indicators.copy()
            logger.debug(f"Saved previous_indicators to position {position.id}")

        return {
            "signal_type": "indicator_based_check",
            "base_order_signal": base_order_signal,
            "safety_order_signal": safety_order_signal,
            "take_profit_signal": take_profit_signal,
            "indicators": current_indicators,
            "price": current_price,
            "condition_details": {
                "base_order": base_order_details,
                "safety_order": safety_order_details,
                "take_profit": take_profit_details,
            },
        }

    async def analyze_signal(
        self,
        candles: List[Dict[str, Any]],
        current_price: float,
        candles_by_timeframe: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        position: Optional[Any] = None,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze market data and evaluate phase conditions.

        Calculates all required indicators including aggregate indicators,
        then evaluates conditions for each phase (base order, safety order, take profit).
        """
        min_candles_needed = 30
        if len(candles) < min_candles_needed:
            logger.debug(f"Not enough candles: {len(candles)}, need {min_candles_needed}")
            return None

        if candles_by_timeframe is None:
            candles_by_timeframe = {"FIVE_MINUTE": candles}

        # Load previous_indicators for crossing detection
        self._load_previous_indicators(position, **kwargs)

        # Determine which aggregate indicators are needed (cached at init)
        needs = self._needs_cache

        # Calculate traditional indicators for each required timeframe
        current_indicators = self._calculate_traditional_indicators(
            candles_by_timeframe, candles, min_candles_needed
        )

        # Calculate aggregate indicators if needed
        await self._calculate_ai_indicators(
            needs, current_indicators, candles, current_price, position, **kwargs
        )

        if needs["bull_flag"]:
            self._calculate_bull_flag_indicators(
                candles_by_timeframe, candles, current_price, current_indicators
            )

        if needs["vwap_bounce_up"] or needs["vwap_bounce_down"]:
            self._calculate_vwap_bounce_indicators(
                candles_by_timeframe, candles, needs, current_indicators
            )

        if needs["qfl_crack"]:
            self._calculate_qfl_indicators(candles_by_timeframe, candles, current_indicators)

        if needs["fear_greed"]:
            await self._calculate_fear_greed_indicators(current_indicators)

        # Add current price
        current_indicators["price"] = current_price

        # Evaluate conditions for each phase
        (
            base_order_signal, base_order_details,
            safety_order_signal, safety_order_details,
            take_profit_signal, take_profit_details,
        ) = self._evaluate_phase_conditions(current_indicators, current_price, position)

        return self._build_signal_response(
            current_indicators, current_price, position,
            base_order_signal, base_order_details,
            safety_order_signal, safety_order_details,
            take_profit_signal, take_profit_details,
        )

    def calculate_base_order_size(self, balance: float) -> float:
        """Calculate base order size based on configuration.

        Delegates to safety_order_calculator module for the actual math.
        """
        return _calc_base_order_size(self.config, balance)

    def calculate_safety_order_size(self, base_order_size: float, order_number: int) -> float:
        """Calculate safety order size with volume scaling."""
        return _calc_safety_order_size(self.config, base_order_size, order_number)

    def calculate_safety_order_price(
        self, entry_price: float, order_number: int, direction: str = "long"
    ) -> float:
        """
        Calculate trigger price for safety order with step scaling.

        Args:
            entry_price: Reference price (entry or average)
            order_number: Safety order number (1, 2, 3, ...)
            direction: "long" or "short"

        Returns:
            Trigger price for the safety order

        For LONG: SO prices go DOWN (buy dips)
        For SHORT: SO prices go UP (short into pumps)
        """
        deviation = self.config.get("price_deviation", 2.0)
        step_scale = self.config.get("safety_order_step_scale", 1.0)

        # E7: Closed-form geometric series for cumulative deviation (O(1) instead of O(n))
        if order_number <= 0:
            total_deviation = 0.0
        elif step_scale == 1.0:
            # Linear: deviation * order_number
            total_deviation = deviation * order_number
        else:
            # Geometric series: deviation * (1 + s + s^2 + ... + s^(n-1))
            # = deviation * (step_scale^n - 1) / (step_scale - 1)
            total_deviation = deviation * (step_scale ** order_number - 1) / (step_scale - 1)

        # Apply direction-specific calculation
        if direction == "long":
            # Long: Buy when price drops below reference
            return entry_price * (1.0 - total_deviation / 100.0)
        else:  # short
            # Short: Sell when price rises above reference
            return entry_price * (1.0 + total_deviation / 100.0)

    def _check_entry_conditions(self, signal_data: Dict[str, Any], direction: str) -> bool:
        """
        Check if entry conditions are met for a specific direction.

        Args:
            signal_data: Signal data with base_order_signal
            direction: "long" or "short"

        Returns:
            True if conditions met for this direction
        """
        # For now, use the base_order_signal from signal_data
        # In the future, this will evaluate direction-specific conditions
        base_order_signal = signal_data.get("base_order_signal", False)

        # If no base order conditions configured, always allow entry
        if not self.base_order_conditions:
            return True

        return base_order_signal

    # =========================================================================
    # should_buy() and its private helpers
    # =========================================================================

    def _calculate_bidirectional_order_amount(
        self, direction: str, balance: float, **kwargs
    ) -> float:
        """
        Calculate the order amount for bidirectional trading mode.

        Computes direction-specific budget from aggregate value and config percentages,
        then delegates to calculate_base_order_size. Falls back to balance-based
        calculation when no aggregate value is available.
        """
        aggregate_value = kwargs.get("aggregate_btc_value", 0) or kwargs.get("aggregate_usd_value", 0)
        if aggregate_value > 0:
            bot_budget_pct = self.config.get("budget_percentage", 10.0)
            bot_total_budget = aggregate_value * (bot_budget_pct / 100.0)

            # Check for dynamic allocation
            if self.config.get("enable_dynamic_allocation", False):
                # TODO: Implement dynamic allocation based on performance
                long_budget_pct = self.config.get("long_budget_percentage", 50.0)
                short_budget_pct = self.config.get("short_budget_percentage", 50.0)
            else:
                long_budget_pct = self.config.get("long_budget_percentage", 50.0)
                short_budget_pct = self.config.get("short_budget_percentage", 50.0)

            # Allocate budget based on direction
            if direction == "long":
                per_position_budget = bot_total_budget * (long_budget_pct / 100.0)
            else:  # short
                per_position_budget = bot_total_budget * (short_budget_pct / 100.0)

            # Divide by the effective deal count. When the soft ceiling is on,
            # use the engine-computed effective ceiling (passed in as
            # effective_max_deals) so the base order is sized for the number of
            # deals that can actually open — not the raw configured maximum.
            # Splitting by the configured max instead would under-size every
            # base order (e.g. budget/20 when only 1 deal can fund). Mirrors the
            # batch path in batch_analyzer.py.
            effective_max_deals = kwargs.get("effective_max_deals")
            if (self.config.get("enable_soft_ceiling", False)
                    and effective_max_deals is not None
                    and effective_max_deals > 0):
                deal_divisor = effective_max_deals
            else:
                deal_divisor = self.config.get("max_concurrent_deals", 1)
            if deal_divisor > 1:
                per_position_budget /= deal_divisor

            return self.calculate_base_order_size(per_position_budget)
        else:
            # Fallback to balance-based calculation
            return self.calculate_base_order_size(balance)

    def _check_base_order_conditions(
        self, signal_data: Dict[str, Any], balance: float, **kwargs
    ) -> Tuple[bool, float, str]:
        """
        Check if a new position should open (no existing position).

        Handles both bidirectional and traditional long-only modes.
        Validates signals, calculates order amount, and checks balance sufficiency.
        """
        base_order_signal = signal_data.get("base_order_signal", False)
        enable_bidirectional = self.config.get("enable_bidirectional", False)

        if enable_bidirectional:
            # Bidirectional mode: check both long and short conditions
            long_signal = self._check_entry_conditions(signal_data, "long")
            short_signal = self._check_entry_conditions(signal_data, "short")

            # Neutral zone enforcement: prevent simultaneous long/short entries too close together
            if long_signal and short_signal:
                if self.config.get("enable_neutral_zone", True):
                    return False, 0.0, "Neutral zone - both signals active, waiting for clear direction"

            # Determine direction to enter
            if long_signal:
                direction = "long"
            elif short_signal:
                direction = "short"
            else:
                return False, 0.0, "No entry signal (bidirectional mode)"

            amount = self._calculate_bidirectional_order_amount(direction, balance, **kwargs)

            if amount <= 0:
                logger.warning("💰 BUDGET BLOCKER: Calculated amount is zero or negative")
                logger.warning(f"   Calculated amount: {amount:.8f} BTC")
                return False, 0.0, f"Calculated {direction} entry amount is invalid ({amount:.8f} BTC)"

            if amount > balance:
                logger.warning(f"💰 BUDGET BLOCKER: Insufficient balance for {direction} entry")
                logger.warning(f"   Available balance: {balance:.8f} BTC")
                logger.warning(f"   Required amount: {amount:.8f} BTC")
                shortfall = amount - balance
                shortfall_pct = shortfall / amount * 100
                logger.warning(
                    f"   Shortfall: {shortfall:.8f} BTC ({shortfall_pct:.1f}%)"
                )
                return (
                    False, 0.0,
                    f"Insufficient balance for {direction} entry"
                    f" (need {amount:.8f} BTC, have {balance:.8f} BTC)"
                )

            # Store direction in signal data for position creation
            signal_data["direction"] = direction

            return True, amount, f"{direction.upper()} entry (conditions met): {amount:.8f}"

        else:
            # Traditional long-only mode
            if not base_order_signal and self.base_order_conditions:
                return False, 0.0, "Base order conditions not met"

            amount = self.calculate_base_order_size(balance)

            if amount <= 0:
                logger.warning("💰 BUDGET BLOCKER: Calculated base order amount is zero or negative")
                logger.warning(f"   Available balance: {balance:.8f} BTC")
                logger.warning(f"   Calculated amount: {amount:.8f} BTC")
                return False, 0.0, f"Calculated base order amount is invalid ({amount:.8f} BTC)"

            if amount > balance:
                logger.warning("💰 BUDGET BLOCKER: Insufficient balance for base order")
                logger.warning(f"   Available balance: {balance:.8f} BTC")
                logger.warning(f"   Required amount: {amount:.8f} BTC")
                shortfall = amount - balance
                shortfall_pct = shortfall / amount * 100
                logger.warning(
                    f"   Shortfall: {shortfall:.8f} BTC ({shortfall_pct:.1f}%)"
                )
                return (
                    False, 0.0,
                    f"Insufficient balance for base order"
                    f" (need {amount:.8f} BTC, have {balance:.8f} BTC)"
                )

            return True, amount, f"Base order (conditions met): {amount:.8f}"

    def _check_dca_conditions(
        self, signal_data: Dict[str, Any], position: Any, balance: float,
        dca_rounding_tolerance: float = 0.0, quote_increment: float = 0.0,
    ) -> Tuple[bool, float, str]:
        """
        Check DCA/safety order conditions for an existing position.

        Supports cascade execution: if price has dropped past multiple SO
        trigger levels, all eligible SOs are combined into a single order.
        """
        current_price = signal_data.get("price", 0)
        safety_order_signal = signal_data.get("safety_order_signal", False)

        # Skip safety orders for pattern-based positions (e.g., bull flag)
        if hasattr(position, "entry_stop_loss") and position.entry_stop_loss is not None:
            return False, 0.0, "Pattern position - DCA disabled (using TSL/TTP)"

        max_safety = self.config.get("max_safety_orders", 5)
        if max_safety == 0:
            return False, 0.0, "Safety orders disabled"

        # Placement ceiling includes grace (bonus) SOs that fire after the configured
        # ones are spent. Grace is excluded from budget/sizing (see safety_order_calculator
        # / _shared.py); only the limit grows here.
        effective_max = effective_max_safety_orders(self.config)

        # Count entry trades (buys for long, sells for short) = safety orders completed
        entry_trades = entry_trades_for_position(position)
        safety_orders_count = count_deployed_safety_orders(entry_trades)  # sums cascade levels
        if safety_orders_count >= effective_max:
            return False, 0.0, f"Max safety orders reached ({safety_orders_count}/{effective_max})"

        # Determine reference price for DCA target calculation
        reference_price = self._get_dca_reference_price(position, entry_trades)
        direction = getattr(position, "direction", "long")

        # Check if at least the next SO trigger is met
        first_so = safety_orders_count + 1
        first_trigger = self.calculate_safety_order_price(reference_price, first_so, direction)

        if direction == "long":
            price_target_met = current_price <= first_trigger
        else:
            price_target_met = current_price >= first_trigger

        if not price_target_met:
            if direction == "long":
                return False, 0.0, f"Price not low enough for SO #{first_so} (need \u2264{first_trigger:.8f})"
            else:
                return False, 0.0, f"Price not high enough for SO #{first_so} (need \u2265{first_trigger:.8f})"

        # If safety order conditions exist (like AI_BUY), also check them
        if self.safety_order_conditions:
            if not safety_order_signal:
                return False, 0.0, f"SO #{first_so} price target met but conditions not met"

        # Cascade: check all remaining SO levels that current price has passed
        total_amount = 0.0
        orders_to_execute = 0
        remaining_balance = balance
        rounding_adjusted = False

        for so_num in range(first_so, effective_max + 1):
            trigger = self.calculate_safety_order_price(reference_price, so_num, direction)

            if direction == "long" and current_price > trigger:
                break  # Price hasn't reached this level
            elif direction == "short" and current_price < trigger:
                break

            so_size = self._calculate_safety_order_amount(position, safety_orders_count + orders_to_execute, so_num)

            # Grace safety orders are intentional just-in-time OVERALLOCATION: when the
            # price has dropped to a grace level (so_num beyond the configured max), fund
            # the order even if it exceeds the deal's configured budget — the whole point
            # is to catch a deep dip / rebound. Bounded by effective_max (configured +
            # grace) and sized off the real base order; the wallet is the real backstop at
            # execution. Configured SOs (so_num <= max_safety) still respect the budget below.
            if so_num > max_safety and so_size > remaining_balance:
                overalloc = so_size - remaining_balance
                position.max_quote_allowed = (position.max_quote_allowed or 0.0) + overalloc
                remaining_balance += overalloc
                logger.info(
                    f"  🌱 Grace overallocation: position #{getattr(position, 'id', '?')} "
                    f"{getattr(position, 'product_id', '?')} funding grace SO #{so_num} "
                    f"(+{overalloc:.8f} beyond configured budget)"
                )

            if so_size > remaining_balance:
                shortfall = so_size - remaining_balance
                if (
                    orders_to_execute == 0
                    and quote_increment > 0
                    and 0 < shortfall <= dca_rounding_tolerance
                ):
                    # Prior fills can drift from ideal quote sizing when the product
                    # only fills in coarse base increments. Use the remaining
                    # allocation, rounded DOWN to the exchange quote increment, so
                    # the final SO fits without weakening the position's hard cap.
                    adjusted_size = math.floor(remaining_balance / quote_increment) * quote_increment
                    if adjusted_size > 0:
                        total_amount += adjusted_size
                        remaining_balance -= adjusted_size
                        orders_to_execute += 1
                        rounding_adjusted = True
                        break

                # Budget only covers partial cascade — execute what fits
                if orders_to_execute == 0:
                    # Can't even afford the first SO. Log the position + budget context so a
                    # grace-budget-expansion miss (max_quote_allowed not grown to cover the
                    # grace SOs) is diagnosable vs. a genuine wallet shortfall.
                    _pid = getattr(position, "id", "?")
                    _prod = getattr(position, "product_id", "?")
                    _mqa = getattr(position, "max_quote_allowed", None)
                    _grace = int((self.config.get("grace_safety_orders", 0) or 0))
                    logger.warning(
                        f"\U0001f4b0 BUDGET BLOCKER: Position #{_pid} {_prod} can't afford safety order "
                        f"#{so_num} — need {so_size:.8f}, have {balance:.8f} "
                        f"(max_quote_allowed={_mqa}, configured_max={max_safety}, grace={_grace}, "
                        f"effective_max={effective_max}, deployed={safety_orders_count})"
                    )
                    return (
                        False, 0.0,
                        f"Insufficient balance for safety order #{so_num}"
                        f" (need {so_size:.8f}, have {balance:.8f})"
                    )
                break  # Stop cascade, execute what we've accumulated

            total_amount += so_size
            remaining_balance -= so_size
            orders_to_execute += 1

        last_so = first_so + orders_to_execute - 1
        if orders_to_execute == 1:
            reason = f"Safety order #{first_so}"
        else:
            reason = f"Safety order #{first_so}-#{last_so} (cascade: {orders_to_execute} orders)"

        if rounding_adjusted:
            reason += " (rounding-adjusted to remaining position budget)"

        # Record how many SO levels this (possibly combined) order deploys, so the
        # recorded trade carries dca_levels and the deployed-SO count stays accurate.
        signal_data["dca_levels"] = orders_to_execute

        return True, total_amount, reason

    def _calculate_safety_order_amount(
        self, position: Any, safety_orders_count: int, next_order_number: int
    ) -> float:
        """
        Compute the order size for the next safety order.

        Safety orders scale off the deal's ACTUAL base order (earliest entry trade), so
        sizing matches what was placed AND compute_grace_expanded_budget. Re-deriving the
        base from max_quote_allowed (auto-calculate) overshot once max_quote_allowed
        diverged from the placed base — grace SOs were sized off an inflated base and blew
        the deal budget (a grace SO ended up larger than the whole remaining allocation).
        Falls back to the prior per-mode derivation only when there's no usable entry
        trade (e.g. test mocks / a brand-new position).
        """
        base_order_size = self._recorded_base_order_size(position)
        if base_order_size <= 0:
            if self.config.get("auto_calculate_order_sizes", False):
                base_order_size = self.calculate_base_order_size(position.max_quote_allowed)
            else:
                base_order_size = self._manual_base_order_size(position, safety_orders_count)

        return self.calculate_safety_order_size(base_order_size, next_order_number)

    def _recorded_base_order_size(self, position: Any) -> float:
        """The deal's ACTUAL base order quote (earliest entry trade), or 0.0 if none.

        Safety orders scale off the base order that was really placed, so this is the
        single source for SO sizing in BOTH modes — keeping sizes consistent with what
        was placed and with compute_grace_expanded_budget. 0.0 means 'no usable entry
        trade' (e.g. a brand-new position or a test mock), letting each caller apply its
        own fallback.
        """
        entry_trades = entry_trades_for_position(position)
        if entry_trades:
            try:
                first = min(entry_trades, key=lambda t: t.timestamp)
            except TypeError:
                first = entry_trades[0]
            try:
                q = float(getattr(first, "quote_amount", None))
                if q > 0:
                    return q
            except (TypeError, ValueError):
                # Malformed/absent quote_amount on the recorded entry trade. We
                # fall back to 0.0 (caller re-derives the base size), but surface
                # it: a silent 0 here cascades into zero-sized safety orders.
                logger.debug(
                    "Position %s entry trade has unusable quote_amount=%r; "
                    "base-order size falls back to 0.0",
                    getattr(position, "id", "?"), getattr(first, "quote_amount", None),
                    exc_info=True,
                )
        return 0.0

    def _manual_base_order_size(self, position: Any, safety_orders_count: int) -> float:
        """Base-order quote size for manual (non-auto-calculate) sizing.

        Prefers the deal's actual base order (earliest entry trade). Reverse-engineering
        it as ``total_quote_spent / (1 + count)`` assumes every order equalled the base,
        which is wrong for any volume scaling or for ``safety_order_percentage != 100``.
        Falls back to that average only when no usable entry trade is available.
        """
        recorded = self._recorded_base_order_size(position)
        if recorded > 0:
            return recorded
        return position.total_quote_spent / (1 + safety_orders_count)

    async def should_buy(
        self, signal_data: Dict[str, Any], position: Optional[Any], balance: float, **kwargs
    ) -> Tuple[bool, float, str]:
        """
        Determine if we should buy/sell based on signal data.

        Supports bidirectional trading: can initiate long (buy) or short (sell) positions.
        """
        if position is None:
            return self._check_base_order_conditions(signal_data, balance, **kwargs)
        else:
            return self._check_dca_conditions(
                signal_data,
                position,
                balance,
                dca_rounding_tolerance=kwargs.get("dca_rounding_tolerance", 0.0),
                quote_increment=kwargs.get("quote_increment", 0.0),
            )

    async def should_sell(
        self, signal_data: Dict[str, Any], position: Any,
        current_price: float,
        market_context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str]:
        """Determine if we should sell based on signal data and TP/SL settings.

        Orchestrates the exit checks in priority order: speculative max-hold,
        then (after computing direction-aware profit) pattern-based TSL/TTP, then
        the standard percentage-based trailing-stop / stop-loss / take-profit.
        """
        take_profit_signal = signal_data.get("take_profit_signal", False)
        avg_price = position.average_buy_price

        spec = self._check_speculative_max_hold(position)
        if spec is not None:
            return spec

        # Calculate current profit (direction-aware). Longs profit as price rises;
        # shorts sold base for quote up front and profit by buying it back cheaper, so
        # they use the short_total_sold_* fields (the long fields are 0 for shorts —
        # using them gave a constant 0% and a divide-by-zero). Guard zero cost basis.
        direction = getattr(position, "direction", "long")
        if direction == "short":
            sold_quote = position.short_total_sold_quote or 0.0
            sold_base = position.short_total_sold_base or 0.0
            buyback_value = sold_base * current_price
            profit_amount = sold_quote - buyback_value
            profit_pct = (profit_amount / sold_quote * 100.0) if sold_quote > 0 else 0.0
        else:
            spent = position.total_quote_spent or 0.0
            current_value = position.total_base_acquired * current_price
            profit_amount = current_value - spent
            profit_pct = (profit_amount / spent * 100.0) if spent > 0 else 0.0

        # Track the most-favorable price since entry for trailing: the highest price for
        # longs, the lowest for shorts (a short's gains grow as price falls).
        if not hasattr(position, "highest_price_since_entry") or position.highest_price_since_entry is None:
            position.highest_price_since_entry = current_price
        elif direction == "short":
            if current_price < position.highest_price_since_entry:
                position.highest_price_since_entry = current_price
        elif current_price > position.highest_price_since_entry:
            position.highest_price_since_entry = current_price

        pattern = self._check_pattern_exit(position, current_price, avg_price, profit_pct)
        if pattern is not None:
            return pattern

        return self._check_percentage_exit(
            position, current_price, avg_price, profit_pct, direction, take_profit_signal
        )

    def _check_speculative_max_hold(self, position: Any) -> Optional[Tuple[bool, str]]:
        """Time-based forced exit for catalyst-hunt (speculative) setups. None = no exit."""
        # Speculative max-hold: time-based forced exit for catalyst-hunt setups
        # that haven't moved. Runs BEFORE PnL / TP / SL checks so we always
        # escape the bucket slot on schedule. Only active when the preset
        # set speculative_max_hold_hours — absent on all non-speculative bots.
        # See PRPs/high-risk-doubling-preset.md §Recommended Design §5.
        max_hold_hours = self.config.get("speculative_max_hold_hours")
        if max_hold_hours and getattr(position, "opened_at", None) is not None:
            age_seconds = (utcnow() - position.opened_at).total_seconds()
            if age_seconds >= float(max_hold_hours) * 3600.0:
                return (
                    True,
                    f"Speculative max hold ({max_hold_hours}h) reached — "
                    f"exiting to free the bucket slot"
                )
        return None

    def _check_pattern_exit(
        self, position: Any, current_price: float, avg_price: float, profit_pct: float
    ) -> Optional[Tuple[bool, str]]:
        """Pattern-based TSL/TTP exit (e.g. bull-flag positions). Returns None for
        non-pattern positions so the caller falls through to percentage TP/SL."""
        direction = getattr(position, "direction", "long")
        # =============================================================
        # PATTERN-BASED TSL/TTP (e.g., Bull Flag positions)
        # If position has pattern targets, use those instead of percentage-based
        # =============================================================
        # Pattern TSL/TTP is long/bull-flag oriented (risk measured DOWN from entry,
        # trailing the high). Its math breaks for shorts (entry_price=avg_buy=0 →
        # negative risk distance), so shorts skip it and use the standard inverted
        # trailing stop below.
        if (direction != "short" and hasattr(position, "entry_stop_loss")
                and position.entry_stop_loss is not None):
            entry_price = avg_price
            entry_sl = position.entry_stop_loss
            entry_tp = getattr(position, "entry_take_profit_target", None)

            # Calculate risk distance for trailing stop
            risk_distance = entry_price - entry_sl

            # Track highest price since entry for TSL
            highest = position.highest_price_since_entry or entry_price

            # Update trailing stop loss (moves up as price rises, never down)
            current_tsl = getattr(position, "trailing_stop_loss_price", entry_sl) or entry_sl

            # TSL moves up when price creates new highs (locks in profits)
            # Simple approach: TSL = highest - risk_distance (maintains original risk)
            if highest > entry_price:
                new_tsl = highest - risk_distance
                if new_tsl > current_tsl:
                    position.trailing_stop_loss_price = new_tsl
                    current_tsl = new_tsl

            # Check TSL hit
            if current_price <= current_tsl:
                return (
                    True,
                    f"Pattern TSL triggered: ${current_price:.4f}"
                    f" <= TSL ${current_tsl:.4f} (profit: {profit_pct:.2f}%)"
                )

            # Check TTP (Trailing Take Profit)
            if entry_tp is not None:
                # TTP activates when price reaches target
                tp_active = getattr(position, "trailing_tp_active", False)

                if current_price >= entry_tp:
                    if not tp_active:
                        position.trailing_tp_active = True
                        position.highest_price_since_tp = current_price
                        tp_active = True

                if tp_active:
                    # Track peak since TTP activation
                    highest_since_tp = getattr(position, "highest_price_since_tp", current_price) or current_price
                    if current_price > highest_since_tp:
                        position.highest_price_since_tp = current_price
                        highest_since_tp = current_price

                    # TTP triggers when price drops by the configured trailing
                    # deviation from the peak (matches the regular trailing-TP path;
                    # was hardcoded 1%, ignoring the bot's trailing_deviation).
                    ttp_deviation = self.config.get("trailing_deviation", 1.0)
                    ttp_trigger = highest_since_tp * (1.0 - ttp_deviation / 100.0)

                    if current_price <= ttp_trigger:
                        return (
                            True,
                            f"Pattern TTP triggered: ${current_price:.4f}"
                            f" (peak ${highest_since_tp:.4f},"
                            f" profit: {profit_pct:.2f}%)"
                        )

                    return (
                        False,
                        f"Pattern TTP active: holding for more"
                        f" (profit: {profit_pct:.2f}%,"
                        f" peak ${highest_since_tp:.4f})"
                    )

            # Pattern position still open
            return False, f"Pattern position: TSL ${current_tsl:.4f}, TP ${entry_tp:.4f}, profit: {profit_pct:.2f}%"
        return None

    def _check_percentage_exit(
        self, position: Any, current_price: float, avg_price: float,
        profit_pct: float, direction: str, take_profit_signal: bool
    ) -> Tuple[bool, str]:
        """Standard percentage-based trailing-stop / stop-loss / take-profit exit."""
        # =============================================================
        # PERCENTAGE-BASED TP/SL (standard positions without pattern targets)
        # =============================================================

        # Check trailing stop loss (direction-aware: longs trail below the high and
        # exit on a drop; shorts trail above the low and exit on a rise).
        if self.config.get("trailing_stop_loss", False):
            deviation = self.config.get("trailing_stop_deviation", 5.0)
            extreme = position.highest_price_since_entry or avg_price or current_price
            if direction == "short":
                tsl_price = extreme * (1.0 + deviation / 100.0)
                if current_price >= tsl_price:
                    return True, f"Trailing stop loss triggered at {current_price:.8f}"
            else:
                tsl_price = extreme * (1.0 - deviation / 100.0)
                if current_price <= tsl_price:
                    return True, f"Trailing stop loss triggered at {current_price:.8f}"

        # Check regular stop loss
        if self.config.get("stop_loss_enabled", False):
            sl_pct = self.config.get("stop_loss_percentage", -10.0)
            if profit_pct <= sl_pct:
                return True, f"Stop loss triggered at {profit_pct:.2f}%"

        # Determine take profit mode (with legacy fallback)
        tp_pct = self.config.get("take_profit_percentage")
        tp_mode = self.config.get("take_profit_mode")
        if tp_mode is None:
            # Legacy: infer mode from old fields
            if self.config.get("trailing_take_profit", False):
                tp_mode = "trailing"
            elif self.config.get("min_profit_for_conditions") is not None:
                tp_mode = "minimum"
            else:
                tp_mode = "fixed"

        # --- FIXED mode: hard sell at TP% ---
        if tp_mode == "fixed":
            if tp_pct is not None and profit_pct >= fee_adjusted_tp_floor(position, tp_pct):
                return True, f"Take profit target reached (net of fees): {profit_pct:.2f}%"

        # --- TRAILING mode: activate trail when TP% hit, sell on deviation ---
        elif tp_mode == "trailing":
            if tp_pct is not None and profit_pct >= fee_adjusted_tp_floor(position, tp_pct):
                trailing_dev = self.config.get("trailing_deviation", 1.0)
                if not hasattr(position, "trailing_tp_active"):
                    position.trailing_tp_active = True
                    position.highest_price_since_tp = current_price

                # Track the favorable extreme since TP armed (peak for long, trough for
                # short) and trigger on the adverse reversal past the deviation.
                if position.highest_price_since_tp is None:
                    position.highest_price_since_tp = current_price
                elif direction == "short":
                    if current_price < position.highest_price_since_tp:
                        position.highest_price_since_tp = current_price
                elif current_price > position.highest_price_since_tp:
                    position.highest_price_since_tp = current_price

                extreme = position.highest_price_since_tp
                if direction == "short":
                    trigger = extreme * (1.0 + trailing_dev / 100.0)
                    if current_price >= trigger:
                        return True, f"Trailing TP triggered (profit: {profit_pct:.2f}%)"
                else:
                    trigger = extreme * (1.0 - trailing_dev / 100.0)
                    if current_price <= trigger:
                        return True, f"Trailing TP triggered (profit: {profit_pct:.2f}%)"
                return False, f"Trailing TP active (profit: {profit_pct:.2f}%)"

        # --- MINIMUM mode: TP% is floor, conditions trigger exit ---
        elif tp_mode == "minimum":
            if take_profit_signal and self.take_profit_conditions:
                min_profit = fee_adjusted_tp_floor(position, tp_pct if tp_pct is not None else 3.0)
                if profit_pct >= min_profit:
                    return True, f"Take profit conditions met (profit: {profit_pct:.2f}%, net of fees)"
                return False, f"Conditions met but profit too low after fees ({profit_pct:.2f}% < {min_profit:.2f}%)"
            if not self.take_profit_conditions:
                logger.warning("Minimum TP mode with no conditions configured - will never sell via TP")

        target_str = f"{tp_pct}%" if tp_pct is not None else "conditions"
        return False, f"Holding (profit: {profit_pct:.2f}%, target: {target_str})"
