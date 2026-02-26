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
from typing import Any, Dict, List, Optional, Tuple

from app.indicator_calculator import IndicatorCalculator
from app.indicators import AISpotOpinionEvaluator, AISpotOpinionParams, BullFlagIndicatorEvaluator
from app.indicators.bull_flag_indicator import BullFlagParams
from app.phase_conditions import PhaseConditionEvaluator
from app.strategies import (
    StrategyDefinition,
    StrategyParameter,
    StrategyRegistry,
    TradingStrategy,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Indicator-Based strategy parameter definitions (data-driven config)
# Each dict is unpacked into StrategyParameter(**entry) by get_definition().
# ---------------------------------------------------------------------------
_INDICATOR_PARAMS = [
    # ── Deal Management ───────────────────────────────────────────────────
    {"name": "max_concurrent_deals", "display_name": "Max Concurrent Deals",
     "description": "Maximum positions that can be open at the same time",
     "type": "int", "default": 1, "min_value": 1, "max_value": 20,
     "group": "Deal Management"},
    {"name": "max_simultaneous_same_pair", "display_name": "Max Simultaneous Deals (Same Pair)",
     "description": ("Maximum concurrent positions allowed on the same trading pair."
                     " New deals open only after all existing deals have used all"
                     " their safety orders."),
     "type": "int", "default": 1, "min_value": 1, "max_value": 20,
     "group": "Deal Management"},
    {"name": "deal_cooldown_seconds", "display_name": "Deal Cooldown (seconds)",
     "description": ("Wait time before opening a new deal on the same pair"
                     " after the previous deal closes. 0 or empty = no cooldown."),
     "type": "int", "default": 0, "min_value": 0, "max_value": 86400,
     "group": "Deal Management"},
    # ── Base Order ────────────────────────────────────────────────────────
    {"name": "base_order_type", "display_name": "Base Order Type",
     "description": "How to calculate base order size",
     "type": "str", "default": "percentage",
     "options": ["percentage", "fixed_btc", "fixed_usd"],
     "group": "Base Order"},
    {"name": "base_order_percentage", "display_name": "Base Order % of Balance",
     "description": "Percentage of available balance for base order",
     "type": "float", "default": 10.0, "min_value": 1.0, "max_value": 100.0,
     "group": "Base Order"},
    {"name": "base_order_fixed", "display_name": "Base Order Fixed Amount",
     "description": "Fixed amount for base order (BTC or USD)",
     "type": "float", "default": 0.001, "min_value": 0.0001, "max_value": 10000.0,
     "group": "Base Order"},
    {"name": "base_execution_type", "display_name": "Base Order Execution",
     "description": "Market (instant fill) or Limit (at current price)",
     "type": "str", "default": "market",
     "options": ["market", "limit"],
     "group": "Base Order"},
    # ── Safety Orders (DCA) ───────────────────────────────────────────────
    {"name": "max_safety_orders", "display_name": "Max Safety Orders",
     "description": "Maximum number of DCA safety orders",
     "type": "int", "default": 5, "min_value": 0, "max_value": 20,
     "group": "Safety Orders"},
    {"name": "safety_order_type", "display_name": "Safety Order Type",
     "description": "How to calculate safety order size",
     "type": "str", "default": "percentage_of_base",
     "options": ["percentage_of_base", "fixed_btc", "fixed_usd"],
     "group": "Safety Orders"},
    {"name": "safety_order_percentage", "display_name": "Safety Order % of Base",
     "description": "Each safety order as % of base order",
     "type": "float", "default": 50.0, "min_value": 10.0, "max_value": 500.0,
     "group": "Safety Orders"},
    {"name": "safety_order_fixed", "display_name": "Safety Order Fixed Amount",
     "description": "Fixed amount for each safety order",
     "type": "float", "default": 0.0005, "min_value": 0.0001, "max_value": 10000.0,
     "group": "Safety Orders"},
    {"name": "price_deviation", "display_name": "Price Deviation %",
     "description": "Price drop % to trigger first safety order",
     "type": "float", "default": 2.0, "min_value": 0.1, "max_value": 20.0,
     "group": "Safety Orders"},
    {"name": "safety_order_step_scale", "display_name": "Safety Order Step Scale",
     "description": "Multiplier for price deviation between orders",
     "type": "float", "default": 1.0, "min_value": 1.0, "max_value": 5.0,
     "group": "Safety Orders"},
    {"name": "safety_order_volume_scale", "display_name": "Safety Order Volume Scale",
     "description": "Multiplier for each safety order size",
     "type": "float", "default": 1.0, "min_value": 1.0, "max_value": 5.0,
     "group": "Safety Orders"},
    {"name": "dca_target_reference", "display_name": "DCA Target Reference",
     "description": "Price to calculate DCA target deviation from",
     "type": "string", "default": "average_price",
     "options": ["base_order", "average_price", "last_buy"],
     "group": "Safety Orders"},
    {"name": "dca_execution_type", "display_name": "DCA Order Execution",
     "description": "Market (instant fill) or Limit (at current price)",
     "type": "str", "default": "market",
     "options": ["market", "limit"],
     "group": "Safety Orders"},
    # ── Take Profit ───────────────────────────────────────────────────────
    {"name": "take_profit_percentage", "display_name": "Take Profit %",
     "description": "Profit target % from average buy price",
     "type": "float", "default": 3.0, "min_value": 0.1, "max_value": 50.0,
     "group": "Take Profit"},
    {"name": "take_profit_mode", "display_name": "Take Profit Mode",
     "description": ("Fixed: sell at TP%. Trailing: trail from peak after TP%."
                     " Minimum: TP% is floor, conditions trigger exit."),
     "type": "str", "default": "fixed",
     "options": ["fixed", "trailing", "minimum"],
     "group": "Take Profit"},
    {"name": "trailing_deviation", "display_name": "Trailing Deviation %",
     "description": "How far price can drop from peak before selling",
     "type": "float", "default": 1.0, "min_value": 0.1, "max_value": 10.0,
     "group": "Take Profit",
     "visible_when": {"take_profit_mode": "trailing"}},
    {"name": "take_profit_order_type", "display_name": "Exit Order Execution",
     "description": "Market (instant fill) or Limit (at mark price)",
     "type": "str", "default": "market",
     "options": ["market", "limit"],
     "group": "Take Profit"},
    # ── Slippage Guard ────────────────────────────────────────────────────
    {"name": "slippage_guard", "display_name": "Slippage Guard",
     "description": "Check order book depth before market orders to prevent excessive slippage",
     "type": "bool", "default": False,
     "group": "Slippage Guard"},
    {"name": "max_buy_slippage_pct", "display_name": "Max Buy Slippage %",
     "description": "Max % above best ask for buy VWAP",
     "type": "float", "default": 0.5, "min_value": 0.01, "max_value": 5.0,
     "group": "Slippage Guard",
     "visible_when": {"slippage_guard": True}},
    {"name": "max_sell_slippage_pct", "display_name": "Max Sell Slippage %",
     "description": "Max % below best bid for sell VWAP (fixed/trailing modes)",
     "type": "float", "default": 0.5, "min_value": 0.01, "max_value": 5.0,
     "group": "Slippage Guard",
     "visible_when": {"slippage_guard": True}},
    # ── Stop Loss ─────────────────────────────────────────────────────────
    {"name": "stop_loss_enabled", "display_name": "Enable Stop Loss",
     "description": "Enable stop loss protection",
     "type": "bool", "default": False,
     "group": "Stop Loss"},
    {"name": "stop_loss_percentage", "display_name": "Stop Loss %",
     "description": "Stop loss % from average buy price (negative)",
     "type": "float", "default": -10.0, "min_value": -50.0, "max_value": -0.1,
     "group": "Stop Loss"},
    {"name": "trailing_stop_loss", "display_name": "Trailing Stop Loss",
     "description": "Enable trailing stop loss",
     "type": "bool", "default": False,
     "group": "Stop Loss"},
    {"name": "trailing_stop_deviation", "display_name": "Trailing Stop Deviation %",
     "description": "How far price can drop from peak before stop loss",
     "type": "float", "default": 5.0, "min_value": 0.1, "max_value": 20.0,
     "group": "Stop Loss"},
    # ── AI Indicators ─────────────────────────────────────────────────────
    {"name": "ai_model", "display_name": "AI Model",
     "description": "Which LLM to use for AI spot opinions",
     "type": "str", "default": "claude",
     "options": ["claude", "gpt", "gemini"],
     "group": "AI Indicators"},
    {"name": "ai_timeframe", "display_name": "AI Check Timeframe",
     "description": "How often to ask AI for opinion (once per candle close)",
     "type": "str", "default": "15m",
     "options": ["5m", "15m", "30m", "1h", "4h"],
     "group": "AI Indicators"},
    {"name": "ai_min_confidence", "display_name": "AI Min Confidence",
     "description": "Minimum confidence % (0-100) to act on AI signal",
     "type": "int", "default": 60, "min_value": 0, "max_value": 100,
     "group": "AI Indicators"},
    {"name": "enable_buy_prefilter", "display_name": "Enable Buy Pre-filter",
     "description": "Use technical pre-filter before asking AI (saves LLM costs)",
     "type": "bool", "default": True,
     "group": "AI Indicators"},
    # ── Bull Flag ─────────────────────────────────────────────────────────
    {"name": "bull_flag_timeframe", "display_name": "Bull Flag Timeframe",
     "description": "Timeframe for bull flag pattern detection",
     "type": "str", "default": "FIFTEEN_MINUTE",
     "options": ["FIVE_MINUTE", "FIFTEEN_MINUTE", "THIRTY_MINUTE", "ONE_HOUR"],
     "group": "Bull Flag"},
    {"name": "bull_flag_min_pole_gain", "display_name": "Bull Flag Min Pole Gain %",
     "description": "Minimum percentage gain required in the pole",
     "type": "float", "default": 3.0, "min_value": 1.0, "max_value": 20.0,
     "group": "Bull Flag"},
    # ── Bidirectional ─────────────────────────────────────────────────────
    {"name": "enable_bidirectional", "display_name": "Enable Bidirectional Trading",
     "description": "Run both long and short DCA strategies simultaneously (requires USD + BTC reserves)",
     "type": "bool", "default": False,
     "group": "Bidirectional"},
    {"name": "long_budget_percentage", "display_name": "Long Budget %",
     "description": "% of bot budget allocated to long positions (buying)",
     "type": "float", "default": 50.0, "min_value": 10.0, "max_value": 90.0,
     "group": "Bidirectional"},
    {"name": "short_budget_percentage", "display_name": "Short Budget %",
     "description": "% of bot budget allocated to short positions (selling)",
     "type": "float", "default": 50.0, "min_value": 10.0, "max_value": 90.0,
     "group": "Bidirectional"},
    {"name": "enable_dynamic_allocation", "display_name": "Enable Dynamic Allocation",
     "description": "Automatically shift capital to better-performing direction (70/30 max)",
     "type": "bool", "default": False,
     "group": "Bidirectional"},
    {"name": "enable_neutral_zone", "display_name": "Enforce Neutral Zone",
     "description": "Require minimum price distance between long and short entries",
     "type": "bool", "default": True,
     "group": "Bidirectional"},
    {"name": "neutral_zone_percentage", "display_name": "Neutral Zone %",
     "description": "Minimum % distance between long and short entry prices",
     "type": "float", "default": 5.0, "min_value": 1.0, "max_value": 20.0,
     "group": "Bidirectional"},
    {"name": "auto_mirror_conditions", "display_name": "Auto-Mirror Conditions",
     "description": "Automatically create mirrored short conditions from long conditions",
     "type": "bool", "default": True,
     "group": "Bidirectional"},
]


@StrategyRegistry.register
class IndicatorBasedStrategy(TradingStrategy):
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
            parameters=[StrategyParameter(**p) for p in _INDICATOR_PARAMS],
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

        # Get phase conditions from config
        self.base_order_conditions = self.config.get("base_order_conditions", [])
        self.base_order_logic = self.config.get("base_order_logic", "and")
        self.safety_order_conditions = self.config.get("safety_order_conditions", [])
        self.safety_order_logic = self.config.get("safety_order_logic", "and")
        self.take_profit_conditions = self.config.get("take_profit_conditions", [])
        self.take_profit_logic = self.config.get("take_profit_logic", "and")

        # Track previous indicators for crossing detection
        self.previous_indicators = None

    def _get_ai_params(self) -> AISpotOpinionParams:
        """Get AI Spot Opinion parameters from config."""
        return AISpotOpinionParams(
            ai_model=self.config.get("ai_model", "claude"),
            ai_timeframe=self.config.get("ai_timeframe", "15m"),
            ai_min_confidence=self.config.get("ai_min_confidence", 60),
            enable_buy_prefilter=self.config.get("enable_buy_prefilter", True),
        )

    def _get_bull_flag_params(self) -> BullFlagParams:
        """Get Bull Flag indicator parameters from config."""
        # Read all bull flag params from config, including migrated values
        # Priority: explicit config > migrated config > defaults
        return BullFlagParams(
            timeframe=self.config.get("bull_flag_timeframe", "FIFTEEN_MINUTE"),
            min_pole_gain_pct=self.config.get(
                "bull_flag_min_pole_gain",
                self.config.get("_migrated_min_pole_gain_pct", 3.0)
            ),
            min_pole_candles=self.config.get(
                "bull_flag_min_pole_candles",
                self.config.get("_migrated_min_pole_candles", 3)
            ),
            min_pullback_candles=self.config.get(
                "bull_flag_min_pullback_candles",
                self.config.get("_migrated_min_pullback_candles", 2)
            ),
            max_pullback_candles=self.config.get(
                "bull_flag_max_pullback_candles",
                self.config.get("_migrated_max_pullback_candles", 8)
            ),
            pullback_retracement_max=self.config.get(
                "bull_flag_pullback_retracement_max",
                self.config.get("_migrated_pullback_retracement_max", 50.0)
            ),
            reward_risk_ratio=self.config.get(
                "bull_flag_reward_risk_ratio",
                self.config.get("_migrated_reward_risk_ratio", 2.0)
            ),
        )

    def _flatten_conditions(self, expression) -> List[Dict[str, Any]]:
        """
        Flatten conditions from either grouped or flat format.

        Handles both:
        - New grouped format: { groups: [{ conditions: [...] }], groupLogic }
        - Old flat format: [condition1, condition2, ...]
        """
        if not expression:
            return []

        # New grouped format
        if isinstance(expression, dict) and "groups" in expression:
            conditions = []
            for group in expression.get("groups", []):
                conditions.extend(group.get("conditions", []))
            return conditions

        # Old flat list format
        if isinstance(expression, list):
            return expression

        return []

    def _needs_aggregate_indicators(self) -> Dict[str, Any]:
        """
        Check which aggregate indicators are needed based on conditions.

        Returns:
            Dict with keys: ai_buy, ai_sell, bull_flag (bool)
            and ai_params: first found AI condition params (or None)
        """
        needs = {
            "ai_buy": False,
            "ai_sell": False,
            "bull_flag": False,
            "ai_params": None,  # First AI condition's params
        }

        # Flatten all conditions from potentially grouped format
        all_conditions = (
            self._flatten_conditions(self.base_order_conditions)
            + self._flatten_conditions(self.safety_order_conditions)
            + self._flatten_conditions(self.take_profit_conditions)
        )

        for condition in all_conditions:
            # Check both 'indicator' (legacy) and 'type' (new) keys
            indicator = (condition.get("type") or condition.get("indicator") or "").lower()

            # New AI opinion indicators
            if indicator in ["ai_opinion", "ai_confidence", "ai_reasoning"]:
                # Determine if this is used in entry or exit conditions
                # If in base_order or safety_order -> buy signal needed
                # If in take_profit -> sell signal needed
                if condition in self._flatten_conditions(self.take_profit_conditions):
                    needs["ai_sell"] = True
                else:
                    needs["ai_buy"] = True
            # Legacy AI indicators (backward compatibility)
            elif indicator == "ai_buy":
                needs["ai_buy"] = True
            elif indicator == "ai_sell":
                needs["ai_sell"] = True
            elif indicator == "bull_flag":
                needs["bull_flag"] = True

        return needs

    # =========================================================================
    # analyze_signal() and its private helpers
    # =========================================================================

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

        # Extract timeframes needed
        timeframes_needed: set = set()
        for indicator_key in required_indicators:
            parts = indicator_key.split("_", 2)
            tf_prefixes = [
                "ONE", "TWO", "THREE", "FOUR", "FIVE",
                "SIX", "TEN", "FIFTEEN", "THIRTY",
            ]
            if len(parts) >= 2 and parts[0] in tf_prefixes:
                timeframe = f"{parts[0]}_{parts[1]}"
                timeframes_needed.add(timeframe)

        # Calculate traditional indicators for each timeframe
        for timeframe in timeframes_needed:
            tf_candles = candles_by_timeframe.get(timeframe, candles)
            if len(tf_candles) < min_candles_needed:
                continue

            tf_required: set = set()
            for indicator_key in required_indicators:
                if indicator_key.startswith(f"{timeframe}_"):
                    indicator_name = indicator_key[len(timeframe) + 1:]
                    tf_required.add(indicator_name)

            # calculate_previous=True enables crossing detection by calculating
            # indicators for both current candle and previous candle (prev_ prefix)
            indicators_for_tf = self.indicator_calculator.calculate_all_indicators(
                tf_candles, tf_required, calculate_previous=True
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
            ai_params = self._get_ai_params()

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

                ai_result = await self.ai_evaluator.evaluate(
                    candles=candles,
                    current_price=current_price,
                    product_id=product_id,
                    db=db,
                    user_id=user_id,
                    params=ai_params,
                    is_sell_check=is_sell_check
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
        bf_params = self._get_bull_flag_params()
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

    def _get_dca_reference_price(self, position: Any, buy_trades: List) -> float:
        """
        Determine the reference price for DCA target calculation.

        Based on dca_target_reference config: "base_order", "last_buy", or "average_price".
        """
        dca_reference = self.config.get("dca_target_reference", "average_price")
        sorted_buys = sorted(
            buy_trades, key=lambda t: t.timestamp if t.timestamp else 0
        ) if buy_trades else []

        if dca_reference == "base_order" and sorted_buys:
            first_buy = sorted_buys[0]
            return first_buy.price if first_buy.price else position.average_buy_price
        elif dca_reference == "last_buy" and sorted_buys:
            last_buy = sorted_buys[-1]
            return last_buy.price if last_buy.price else position.average_buy_price
        else:
            return position.average_buy_price

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
        buy_trades = [t for t in position.trades if t.side == "buy"] if hasattr(position, "trades") else []
        safety_orders_count = max(0, len(buy_trades) - 1)  # -1 for base order, min 0
        next_order_number = safety_orders_count + 1

        reference_price = self._get_dca_reference_price(position, buy_trades)

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

            # For DCA, also require price drop below target (this is a mandatory condition)
            # The price drop condition is ALWAYS required for DCA, regardless of other conditions
            if position is not None and hasattr(position, "average_buy_price") and position.average_buy_price:
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

        # Determine which aggregate indicators are needed
        needs = self._needs_aggregate_indicators()

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

        Note: The 'balance' passed in is already the per-position budget (accounting for
        split_budget_across_pairs if enabled). The strategy just applies the percentage
        to whatever budget it receives - no need to divide by max_concurrent_deals here.

        For fixed orders with safety orders enabled, this auto-calculates the base order
        size that fits within the budget after accounting for all safety orders (working
        backwards from total budget to determine optimal base order size).
        """
        order_type = self.config.get("base_order_type", "percentage")
        max_safety_orders = self.config.get("max_safety_orders", 0)
        auto_calculate = self.config.get("auto_calculate_order_sizes", False)

        # DEBUG (2026-02-06): Investigating RSI Runner Bot placing 2x base orders vs other bots
        # RSI Runner: ~0.0002 BTC base orders (62% of budget)
        # AI Bot Test: ~0.0001 BTC base orders (31% of budget, hitting minimum)
        # Both have identical config: auto_calc=True, max_so=2, so_type=percentage_of_base, so_pct=100, vol_scale=2
        # Expected multiplier=4.0, expected result=budget/4 → 0.00008 → bumped to 0.0001 minimum
        # REMOVE THIS DEBUG LOGGING once issue is resolved
        logger.info(f"🔍 calc_base_order_size: balance={balance:.8f}, order_type={order_type}, "
                    f"auto_calc={auto_calculate}, max_so={max_safety_orders}, "
                    f"so_type={self.config.get('safety_order_type')}, "
                    f"so_pct={self.config.get('safety_order_percentage')}, "
                    f"vol_scale={self.config.get('safety_order_volume_scale')}")

        if order_type == "percentage":
            # For percentage-based with auto-calculate, compute the optimal percentage
            # that ensures full budget utilization when all safety orders execute
            if auto_calculate and max_safety_orders > 0:
                # Calculate total multiplier (base + all safety orders)
                total_multiplier = 1.0  # Base order

                safety_order_type = self.config.get("safety_order_type", "percentage_of_base")
                volume_scale = self.config.get("safety_order_volume_scale", 1.0)

                if safety_order_type == "percentage_of_base":
                    # Safety orders as percentage of base
                    so_percentage = self.config.get("safety_order_percentage", 50.0) / 100.0
                    for order_num in range(1, max_safety_orders + 1):
                        scaled_multiplier = so_percentage * (volume_scale ** (order_num - 1))
                        total_multiplier += scaled_multiplier

                    # Calculate percentage that results in full budget usage
                    # If total_multiplier = 4.0, then base should be 25% of budget
                    optimal_percentage = 100.0 / total_multiplier
                    return balance * (optimal_percentage / 100.0)
                # For fixed safety orders with percentage base, fall through to manual mode

            # Manual mode: use the configured percentage
            percentage = self.config.get("base_order_percentage", 10.0)
            return balance * (percentage / 100.0)
        elif order_type in ["fixed", "fixed_btc"]:
            # For fixed orders WITH safety orders AND auto-calculate enabled, auto-calculate base size to fit budget
            if self.config.get("auto_calculate_order_sizes", False) and max_safety_orders > 0 and balance > 0:
                safety_order_type = self.config.get("safety_order_type", "percentage_of_base")

                # FIXED: When both base and safety orders are fixed types, dynamically calculate X where:
                # base = X, SO1 = X, SO2 = X * volume_scale, etc., and all orders fit within budget
                if safety_order_type in ["fixed", "fixed_btc"]:
                    volume_scale = self.config.get("safety_order_volume_scale", 1.0)

                    # Calculate total multiplier: base + SO1 + SO2*scale + SO3*scale^2 + ...
                    # If base_order_btc = safety_order_btc (configured to be same), then:
                    # base = X, SO1 = X, SO2 = X*scale, SO3 = X*scale^2, ...
                    # Total = X + X + X*scale + X*scale^2 + ... = X * (1 + 1 + scale + scale^2 + ...)
                    total_multiplier = 1.0  # Base order = X
                    total_multiplier += 1.0  # SO1 = X (same as base)

                    # Add remaining safety orders with volume scaling
                    for order_num in range(2, max_safety_orders + 1):
                        scaled_multiplier = volume_scale ** (order_num - 1)
                        total_multiplier += scaled_multiplier

                    # Solve for X: total_multiplier * X = balance
                    base_order_size = balance / total_multiplier
                    result = base_order_size

                    # DEBUG: Log result for RSI Runner 2x issue
                    logger.info(f"🔍 calc_base_order_size RESULT (fixed SO path): "
                                f"multiplier={total_multiplier:.2f}, raw={base_order_size:.8f}, final={result:.8f}")

                    # Exchange-specific minimums enforced by order_validation at execution time
                    return result
                else:
                    # Safety orders are percentage_of_base - calculate base to fit budget
                    # Calculate the total multiplier (base + all safety orders)
                    total_multiplier = 1.0  # Base order
                    volume_scale = self.config.get("safety_order_volume_scale", 1.0)

                    # Add safety order multipliers
                    for order_num in range(1, max_safety_orders + 1):
                        # Safety order as percentage of base (e.g., 100% = 1.0x base)
                        so_multiplier = self.config.get("safety_order_percentage", 50.0) / 100.0
                        # Apply volume scaling to the multiplier
                        scaled_multiplier = so_multiplier * (volume_scale ** (order_num - 1))
                        total_multiplier += scaled_multiplier

                    # Calculate base order size that fits within budget
                    # budget = base * total_multiplier → base = budget / total_multiplier
                    base_order_size = balance / total_multiplier
                    result = base_order_size

                    # DEBUG: Log result for RSI Runner 2x issue
                    logger.info(f"🔍 calc_base_order_size RESULT (pct_of_base path): "
                                f"multiplier={total_multiplier:.2f}, raw={base_order_size:.8f}, final={result:.8f}")

                    # Exchange-specific minimums enforced by order_validation at execution time
                    return result
            else:
                # No safety orders or no balance - use configured fixed amount
                # FIXED: Prioritize base_order_btc over base_order_fixed for better auto-calculate support
                # If base_order_btc exists and is different from default, use it (modern config)
                # Otherwise fall back to base_order_fixed (legacy config)
                base_order_btc = self.config.get("base_order_btc", 0.0001)
                base_order_fixed = self.config.get("base_order_fixed", 0.001)

                # Use base_order_btc if it's explicitly set (not default) or if order_type is "fixed_btc"
                if order_type == "fixed_btc" or (base_order_btc != 0.0001 and base_order_btc < base_order_fixed):
                    return base_order_btc
                else:
                    return base_order_fixed
        else:
            # Fallback for unknown types
            return self.config.get("base_order_fixed", 0.001)

    def calculate_safety_order_size(self, base_order_size: float, order_number: int) -> float:
        """Calculate safety order size with volume scaling."""
        order_type = self.config.get("safety_order_type", "percentage_of_base")

        if order_type == "percentage_of_base":
            base_safety_size = base_order_size * (self.config.get("safety_order_percentage", 50.0) / 100.0)
        elif order_type in ["fixed", "fixed_btc"]:
            # FIXED: When auto_calculate is enabled, treat fixed safety orders as equal to base order
            # (they scale together: base = SO1 = X, SO2 = X * volume_scale, etc.)
            if self.config.get("auto_calculate_order_sizes", False):
                # Safety order size equals base order size (then scaled by volume_scale)
                base_safety_size = base_order_size
            else:
                # Use configured fixed amount
                base_safety_size = self.config.get("safety_order_btc", 0.0001)
        else:
            # Fallback for legacy configs using safety_order_fixed
            base_safety_size = self.config.get("safety_order_fixed", 0.0005)

        volume_scale = self.config.get("safety_order_volume_scale", 1.0)
        return base_safety_size * (volume_scale ** (order_number - 1))

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

        # Calculate cumulative deviation
        total_deviation = 0.0
        for i in range(order_number):
            if i == 0:
                total_deviation += deviation
            else:
                total_deviation += deviation * (step_scale ** i)

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

            # Divide by max concurrent deals if configured
            max_concurrent = self.config.get("max_concurrent_deals", 1)
            if max_concurrent > 1:
                per_position_budget /= max_concurrent

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
        self, signal_data: Dict[str, Any], position: Any, balance: float
    ) -> Tuple[bool, float, str]:
        """
        Check DCA/safety order conditions for an existing position.

        Validates pattern position exclusion, max safety orders, price target,
        indicator conditions, and balance sufficiency.
        """
        current_price = signal_data.get("price", 0)
        safety_order_signal = signal_data.get("safety_order_signal", False)

        # Skip safety orders for pattern-based positions (e.g., bull flag)
        if hasattr(position, "entry_stop_loss") and position.entry_stop_loss is not None:
            return False, 0.0, "Pattern position - DCA disabled (using TSL/TTP)"

        max_safety = self.config.get("max_safety_orders", 5)
        if max_safety == 0:
            return False, 0.0, "Safety orders disabled"

        # Count buy trades to determine safety orders completed
        buy_trades = [t for t in position.trades if t.side == "buy"]
        safety_orders_count = max(0, len(buy_trades) - 1)  # -1 for base order, min 0
        if safety_orders_count >= max_safety:
            return False, 0.0, f"Max safety orders reached ({safety_orders_count}/{max_safety})"

        next_order_number = safety_orders_count + 1

        # Determine reference price for DCA target calculation
        reference_price = self._get_dca_reference_price(position, buy_trades)

        # Always check price target as minimum threshold (direction-aware)
        direction = getattr(position, "direction", "long")
        trigger_price = self.calculate_safety_order_price(reference_price, next_order_number, direction)

        # Check price target based on direction
        if direction == "long":
            price_target_met = current_price <= trigger_price
            reason = f"Price not low enough for SO #{next_order_number} (need \u2264{trigger_price:.8f})"
        else:  # short
            price_target_met = current_price >= trigger_price
            reason = f"Price not high enough for SO #{next_order_number} (need \u2265{trigger_price:.8f})"

        if not price_target_met:
            return False, 0.0, reason

        # If safety order conditions exist (like AI_BUY), also check them
        if self.safety_order_conditions:
            if not safety_order_signal:
                return False, 0.0, f"SO #{next_order_number} price target met but conditions not met"

        # Calculate safety order size
        safety_size = self._calculate_safety_order_amount(position, safety_orders_count, next_order_number)

        if safety_size > balance:
            logger.warning(f"💰 BUDGET BLOCKER: Insufficient balance for safety order #{next_order_number}")
            logger.warning(f"   Available balance: {balance:.8f} BTC")
            logger.warning(f"   Required for SO #{next_order_number}: {safety_size:.8f} BTC")
            logger.warning(f"   Position allocated budget: {position.max_quote_allowed:.8f} BTC")
            logger.warning(f"   Position spent so far: {position.total_quote_spent:.8f} BTC")
            shortfall = safety_size - balance
            shortfall_pct = shortfall / safety_size * 100
            logger.warning(
                f"   Shortfall: {shortfall:.8f} BTC ({shortfall_pct:.1f}%)"
            )
            return (
                False, 0.0,
                f"Insufficient balance for safety order #{next_order_number}"
                f" (need {safety_size:.8f} BTC, have {balance:.8f} BTC)"
            )

        return True, safety_size, f"Safety order #{next_order_number}"

    def _calculate_safety_order_amount(
        self, position: Any, safety_orders_count: int, next_order_number: int
    ) -> float:
        """
        Compute the order size for the next safety order.

        For auto-calculate mode, recalculates base order size from the position's
        allocated budget. For manual mode, infers from average spent per order.
        """
        # CRITICAL FIX: For auto-calculate mode, recalculate base order size using the same logic
        # Don't try to reverse-engineer it from total_quote_spent (which doesn't account for volume scaling)
        if self.config.get("auto_calculate_order_sizes", False):
            base_order_size = self.calculate_base_order_size(position.max_quote_allowed)
        else:
            base_order_size = position.total_quote_spent / (1 + safety_orders_count)

        return self.calculate_safety_order_size(base_order_size, next_order_number)

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
            return self._check_dca_conditions(signal_data, position, balance)

    async def should_sell(
        self, signal_data: Dict[str, Any], position: Any,
        current_price: float,
        market_context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str]:
        """Determine if we should sell based on signal data and TP/SL settings."""
        take_profit_signal = signal_data.get("take_profit_signal", False)
        avg_price = position.average_buy_price

        # Calculate current profit
        current_value = position.total_base_acquired * current_price
        profit_amount = current_value - position.total_quote_spent
        profit_pct = (profit_amount / position.total_quote_spent) * 100

        # Track highest price for trailing
        if not hasattr(position, "highest_price_since_entry") or position.highest_price_since_entry is None:
            position.highest_price_since_entry = current_price
        elif current_price > position.highest_price_since_entry:
            position.highest_price_since_entry = current_price

        # =============================================================
        # PATTERN-BASED TSL/TTP (e.g., Bull Flag positions)
        # If position has pattern targets, use those instead of percentage-based
        # =============================================================
        if hasattr(position, "entry_stop_loss") and position.entry_stop_loss is not None:
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

                    # TTP triggers when price drops 1% from peak (after reaching target)
                    ttp_deviation = 1.0  # 1% trailing deviation after TTP activation
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

        # =============================================================
        # PERCENTAGE-BASED TP/SL (standard positions without pattern targets)
        # =============================================================

        # Check trailing stop loss
        if self.config.get("trailing_stop_loss", False):
            deviation = self.config.get("trailing_stop_deviation", 5.0)
            highest = position.highest_price_since_entry or avg_price
            tsl_price = highest * (1.0 - deviation / 100.0)
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
            if tp_pct is not None and profit_pct >= tp_pct:
                return True, f"Take profit target reached: {profit_pct:.2f}%"

        # --- TRAILING mode: activate trail when TP% hit, sell on deviation ---
        elif tp_mode == "trailing":
            if tp_pct is not None and profit_pct >= tp_pct:
                trailing_dev = self.config.get("trailing_deviation", 1.0)
                if not hasattr(position, "trailing_tp_active"):
                    position.trailing_tp_active = True
                    position.highest_price_since_tp = current_price

                if position.highest_price_since_tp is None:
                    position.highest_price_since_tp = current_price
                elif current_price > position.highest_price_since_tp:
                    position.highest_price_since_tp = current_price

                peak = position.highest_price_since_tp
                trigger = peak * (1.0 - trailing_dev / 100.0)
                if current_price <= trigger:
                    return True, f"Trailing TP triggered (profit: {profit_pct:.2f}%)"
                return False, f"Trailing TP active (profit: {profit_pct:.2f}%)"

        # --- MINIMUM mode: TP% is floor, conditions trigger exit ---
        elif tp_mode == "minimum":
            if take_profit_signal and self.take_profit_conditions:
                min_profit = tp_pct if tp_pct is not None else 3.0
                if profit_pct >= min_profit:
                    return True, f"Take profit conditions met (profit: {profit_pct:.2f}%)"
                return False, f"Conditions met but profit too low ({profit_pct:.2f}% < {min_profit}%)"
            if not self.take_profit_conditions:
                logger.warning("Minimum TP mode with no conditions configured - will never sell via TP")

        target_str = f"{tp_pct}%" if tp_pct is not None else "conditions"
        return False, f"Holding (profit: {profit_pct:.2f}%, target: {target_str})"
