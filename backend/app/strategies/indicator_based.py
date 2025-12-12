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
from app.indicators import AIIndicatorEvaluator, BullFlagIndicatorEvaluator, RISK_PRESETS
from app.indicators.ai_indicator import AIIndicatorParams
from app.indicators.bull_flag_indicator import BullFlagParams
from app.phase_conditions import PhaseConditionEvaluator
from app.strategies import (
    StrategyDefinition,
    StrategyParameter,
    StrategyRegistry,
    TradingStrategy,
)

logger = logging.getLogger(__name__)


@StrategyRegistry.register
class IndicatorBasedStrategy(TradingStrategy):
    """
    Unified indicator-based strategy.

    All trading decisions are made by evaluating user-configured conditions
    against indicator values. This includes aggregate indicators like AI_BUY,
    AI_SELL, and BULL_FLAG alongside traditional indicators.
    """

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="indicator_based",
            name="Custom Bot (Indicator-Based)",
            description="Build your own bot by selecting indicators and conditions. "
            "Mix traditional indicators (RSI, MACD, BB%) with AI-powered signals (AI_BUY, AI_SELL) "
            "and pattern detection (BULL_FLAG). Configure entry, DCA, and exit conditions.",
            parameters=[
                # ========================================
                # DEAL MANAGEMENT
                # ========================================
                StrategyParameter(
                    name="max_concurrent_deals",
                    display_name="Max Concurrent Deals",
                    description="Maximum positions that can be open at the same time",
                    type="int",
                    default=1,
                    min_value=1,
                    max_value=20,
                    group="Deal Management",
                ),
                # ========================================
                # BASE ORDER SETTINGS
                # ========================================
                StrategyParameter(
                    name="base_order_type",
                    display_name="Base Order Type",
                    description="How to calculate base order size",
                    type="str",
                    default="percentage",
                    options=["percentage", "fixed_btc", "fixed_usd"],
                    group="Base Order",
                ),
                StrategyParameter(
                    name="base_order_percentage",
                    display_name="Base Order % of Balance",
                    description="Percentage of available balance for base order",
                    type="float",
                    default=10.0,
                    min_value=1.0,
                    max_value=100.0,
                    group="Base Order",
                ),
                StrategyParameter(
                    name="base_order_fixed",
                    display_name="Base Order Fixed Amount",
                    description="Fixed amount for base order (BTC or USD)",
                    type="float",
                    default=0.001,
                    min_value=0.0001,
                    max_value=10000.0,
                    group="Base Order",
                ),
                # ========================================
                # SAFETY ORDER (DCA) SETTINGS
                # ========================================
                StrategyParameter(
                    name="max_safety_orders",
                    display_name="Max Safety Orders",
                    description="Maximum number of DCA safety orders",
                    type="int",
                    default=5,
                    min_value=0,
                    max_value=20,
                    group="Safety Orders",
                ),
                StrategyParameter(
                    name="safety_order_type",
                    display_name="Safety Order Type",
                    description="How to calculate safety order size",
                    type="str",
                    default="percentage_of_base",
                    options=["percentage_of_base", "fixed_btc", "fixed_usd"],
                    group="Safety Orders",
                ),
                StrategyParameter(
                    name="safety_order_percentage",
                    display_name="Safety Order % of Base",
                    description="Each safety order as % of base order",
                    type="float",
                    default=50.0,
                    min_value=10.0,
                    max_value=500.0,
                    group="Safety Orders",
                ),
                StrategyParameter(
                    name="safety_order_fixed",
                    display_name="Safety Order Fixed Amount",
                    description="Fixed amount for each safety order",
                    type="float",
                    default=0.0005,
                    min_value=0.0001,
                    max_value=10000.0,
                    group="Safety Orders",
                ),
                StrategyParameter(
                    name="price_deviation",
                    display_name="Price Deviation %",
                    description="Price drop % to trigger first safety order",
                    type="float",
                    default=2.0,
                    min_value=0.1,
                    max_value=20.0,
                    group="Safety Orders",
                ),
                StrategyParameter(
                    name="safety_order_step_scale",
                    display_name="Safety Order Step Scale",
                    description="Multiplier for price deviation between orders",
                    type="float",
                    default=1.0,
                    min_value=1.0,
                    max_value=5.0,
                    group="Safety Orders",
                ),
                StrategyParameter(
                    name="safety_order_volume_scale",
                    display_name="Safety Order Volume Scale",
                    description="Multiplier for each safety order size",
                    type="float",
                    default=1.0,
                    min_value=1.0,
                    max_value=5.0,
                    group="Safety Orders",
                ),
                StrategyParameter(
                    name="dca_target_reference",
                    display_name="DCA Target Reference",
                    description="Price to calculate DCA target deviation from",
                    type="string",
                    default="average_price",
                    options=["base_order", "average_price", "last_buy"],
                    group="Safety Orders",
                ),
                # ========================================
                # TAKE PROFIT SETTINGS
                # ========================================
                StrategyParameter(
                    name="take_profit_percentage",
                    display_name="Take Profit %",
                    description="Target profit % from average buy price",
                    type="float",
                    default=3.0,
                    min_value=0.1,
                    max_value=50.0,
                    group="Take Profit",
                ),
                StrategyParameter(
                    name="take_profit_order_type",
                    display_name="Take Profit Order Type",
                    description="Use limit or market order for take profit",
                    type="str",
                    default="limit",
                    options=["limit", "market"],
                    group="Take Profit",
                ),
                StrategyParameter(
                    name="min_profit_for_conditions",
                    display_name="Min Profit for Condition Exit (Override)",
                    description="Override: Min profit % for condition exits. If not set, uses Take Profit %",
                    type="float",
                    default=None,  # None = use take_profit_percentage
                    min_value=-50.0,
                    max_value=50.0,
                    group="Take Profit",
                    optional=True,  # Only show if user wants to override
                ),
                StrategyParameter(
                    name="trailing_take_profit",
                    display_name="Trailing Take Profit",
                    description="Enable trailing take profit",
                    type="bool",
                    default=False,
                    group="Take Profit",
                ),
                StrategyParameter(
                    name="trailing_deviation",
                    display_name="Trailing Deviation %",
                    description="How far price can drop from peak before selling",
                    type="float",
                    default=1.0,
                    min_value=0.1,
                    max_value=10.0,
                    group="Take Profit",
                ),
                # ========================================
                # STOP LOSS SETTINGS
                # ========================================
                StrategyParameter(
                    name="stop_loss_enabled",
                    display_name="Enable Stop Loss",
                    description="Enable stop loss protection",
                    type="bool",
                    default=False,
                    group="Stop Loss",
                ),
                StrategyParameter(
                    name="stop_loss_percentage",
                    display_name="Stop Loss %",
                    description="Stop loss % from average buy price (negative)",
                    type="float",
                    default=-10.0,
                    min_value=-50.0,
                    max_value=-0.1,
                    group="Stop Loss",
                ),
                StrategyParameter(
                    name="trailing_stop_loss",
                    display_name="Trailing Stop Loss",
                    description="Enable trailing stop loss",
                    type="bool",
                    default=False,
                    group="Stop Loss",
                ),
                StrategyParameter(
                    name="trailing_stop_deviation",
                    display_name="Trailing Stop Deviation %",
                    description="How far price can drop from peak before stop loss",
                    type="float",
                    default=5.0,
                    min_value=0.1,
                    max_value=20.0,
                    group="Stop Loss",
                ),
                # ========================================
                # AI INDICATOR SETTINGS
                # ========================================
                StrategyParameter(
                    name="ai_risk_preset",
                    display_name="AI Risk Preset",
                    description="Risk preset for AI_BUY/AI_SELL indicators",
                    type="str",
                    default="moderate",
                    options=["aggressive", "moderate", "conservative"],
                    group="AI Indicators",
                ),
                StrategyParameter(
                    name="ai_min_confluence_score",
                    display_name="AI Min Confluence Score",
                    description="Minimum confluence score (0-100) for AI signals. Presets: aggressive=30, moderate=40, conservative=50",
                    type="int",
                    default=40,  # Match moderate preset
                    min_value=20,
                    max_value=95,
                    group="AI Indicators",
                ),
                StrategyParameter(
                    name="ai_entry_timeframe",
                    display_name="AI Entry Timeframe",
                    description="Timeframe for AI entry signal analysis",
                    type="str",
                    default="FIFTEEN_MINUTE",
                    options=["FIVE_MINUTE", "FIFTEEN_MINUTE", "THIRTY_MINUTE", "ONE_HOUR"],
                    group="AI Indicators",
                ),
                StrategyParameter(
                    name="ai_trend_timeframe",
                    display_name="AI Trend Timeframe",
                    description="Higher timeframe for trend confirmation",
                    type="str",
                    default="FOUR_HOUR",
                    options=["ONE_HOUR", "TWO_HOUR", "FOUR_HOUR", "SIX_HOUR", "ONE_DAY"],
                    group="AI Indicators",
                ),
                # ========================================
                # BULL FLAG INDICATOR SETTINGS
                # ========================================
                StrategyParameter(
                    name="bull_flag_timeframe",
                    display_name="Bull Flag Timeframe",
                    description="Timeframe for bull flag pattern detection",
                    type="str",
                    default="FIFTEEN_MINUTE",
                    options=["FIVE_MINUTE", "FIFTEEN_MINUTE", "THIRTY_MINUTE", "ONE_HOUR"],
                    group="Bull Flag",
                ),
                StrategyParameter(
                    name="bull_flag_min_pole_gain",
                    display_name="Bull Flag Min Pole Gain %",
                    description="Minimum percentage gain required in the pole",
                    type="float",
                    default=3.0,
                    min_value=1.0,
                    max_value=20.0,
                    group="Bull Flag",
                ),
                # ========================================
                # CONDITIONS (stored as JSON in strategy_config)
                # ========================================
                # Note: These are not StrategyParameters but part of config dict:
                # - base_order_conditions: List of conditions for entry
                # - base_order_logic: "and" or "or"
                # - safety_order_conditions: List of conditions for DCA
                # - safety_order_logic: "and" or "or"
                # - take_profit_conditions: List of conditions for exit
                # - take_profit_logic: "and" or "or"
            ],
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
        self.ai_evaluator = AIIndicatorEvaluator()
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

    def _get_ai_params(self, condition_params: Optional[Dict[str, Any]] = None) -> AIIndicatorParams:
        """
        Get AI indicator parameters from condition or config.

        Priority:
        1. Condition-level params (risk_preset, ai_provider)
        2. Bot-level config (ai_risk_preset)
        3. Default (moderate preset)
        """
        # Use condition-level preset if provided
        if condition_params and condition_params.get("risk_preset"):
            preset_name = condition_params["risk_preset"]
        else:
            preset_name = self.config.get("ai_risk_preset", "moderate")

        preset = RISK_PRESETS.get(preset_name, RISK_PRESETS["moderate"])

        # Log the AI provider being used (for debugging)
        ai_provider = "claude"
        if condition_params and condition_params.get("ai_provider"):
            ai_provider = condition_params["ai_provider"]
        logger.debug(f"AI indicator using preset={preset_name}, provider={ai_provider}")

        return AIIndicatorParams(
            risk_preset=preset_name,
            min_confluence_score=self.config.get("ai_min_confluence_score", preset["min_confluence_score"]),
            entry_timeframe=self.config.get("ai_entry_timeframe", preset["entry_timeframe"]),
            trend_timeframe=self.config.get("ai_trend_timeframe", preset["trend_timeframe"]),
            require_trend_alignment=preset.get("require_trend_alignment", True),
            max_volatility=preset.get("max_volatility"),
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
            self._flatten_conditions(self.base_order_conditions) +
            self._flatten_conditions(self.safety_order_conditions) +
            self._flatten_conditions(self.take_profit_conditions)
        )

        for condition in all_conditions:
            # Check both 'indicator' (legacy) and 'type' (new) keys
            indicator = (condition.get("type") or condition.get("indicator") or "").lower()

            if indicator == "ai_buy":
                needs["ai_buy"] = True
                # Extract params from the first AI_BUY condition
                if needs["ai_params"] is None:
                    needs["ai_params"] = {
                        "risk_preset": condition.get("risk_preset", "moderate"),
                        "ai_provider": condition.get("ai_provider", "claude"),
                    }
            elif indicator == "ai_sell":
                needs["ai_sell"] = True
                # Extract params from AI_SELL if no params yet
                if needs["ai_params"] is None:
                    needs["ai_params"] = {
                        "risk_preset": condition.get("risk_preset", "moderate"),
                        "ai_provider": condition.get("ai_provider", "claude"),
                    }
            elif indicator == "bull_flag":
                needs["bull_flag"] = True

        return needs

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
        # This persists across check cycles (strategy instances are recreated each cycle)
        # Priority: 1) Position-based storage (for open positions)
        #           2) Monitor-level cache (for entry conditions, passed via kwargs)
        if position is not None and hasattr(position, 'previous_indicators') and position.previous_indicators:
            self.previous_indicators = position.previous_indicators
            logger.debug(f"Loaded previous_indicators from position {position.id}")
        elif kwargs.get('previous_indicators_cache'):
            # For entry conditions (no position yet), use monitor-level cache
            self.previous_indicators = kwargs['previous_indicators_cache']
            logger.debug("Loaded previous_indicators from monitor cache (entry conditions)")

        # Determine which aggregate indicators are needed
        needs = self._needs_aggregate_indicators()

        # Calculate traditional indicators for each required timeframe
        current_indicators = {}

        # Extract required traditional indicators from conditions
        # Uses get_required_indicators_from_expression which handles both formats
        required_indicators = set()
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
        timeframes_needed = set()
        for indicator_key in required_indicators:
            parts = indicator_key.split("_", 2)
            if len(parts) >= 2 and parts[0] in ["ONE", "TWO", "THREE", "FIVE", "SIX", "FIFTEEN", "THIRTY", "FOUR"]:
                timeframe = f"{parts[0]}_{parts[1]}"
                timeframes_needed.add(timeframe)

        # Calculate traditional indicators for each timeframe
        for timeframe in timeframes_needed:
            tf_candles = candles_by_timeframe.get(timeframe, candles)
            if len(tf_candles) < min_candles_needed:
                continue

            tf_required = set()
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
                current_indicators[f"{timeframe}_{key}"] = value

        # Calculate aggregate indicators if needed
        if needs["ai_buy"] or needs["ai_sell"]:
            # Pass condition-level params (risk_preset, ai_provider) if found
            ai_params = self._get_ai_params(needs.get("ai_params"))
            entry_candles = candles_by_timeframe.get(ai_params.entry_timeframe, candles)
            trend_candles = candles_by_timeframe.get(ai_params.trend_timeframe, candles)

            if needs["ai_buy"]:
                ai_buy_result = self.ai_evaluator.evaluate_ai_buy(
                    candles_entry=entry_candles,
                    candles_trend=trend_candles,
                    current_price=current_price,
                    params=ai_params,
                )
                current_indicators["ai_buy"] = ai_buy_result["signal"]
                current_indicators["ai_buy_score"] = ai_buy_result["confluence_score"]
                current_indicators["ai_buy_explanation"] = ai_buy_result["explanation"]

            if needs["ai_sell"]:
                # For AI_SELL, we need position info
                entry_price = getattr(position, "average_buy_price", current_price) if position else current_price
                profit_pct = 0.0
                if position and hasattr(position, "total_quote_spent") and position.total_quote_spent > 0:
                    current_value = position.total_base_acquired * current_price
                    profit_pct = ((current_value - position.total_quote_spent) / position.total_quote_spent) * 100

                ai_sell_result = self.ai_evaluator.evaluate_ai_sell(
                    candles_entry=entry_candles,
                    candles_trend=trend_candles,
                    current_price=current_price,
                    entry_price=entry_price,
                    profit_pct=profit_pct,
                    params=ai_params,
                )
                current_indicators["ai_sell"] = ai_sell_result["signal"]
                current_indicators["ai_sell_score"] = ai_sell_result["confluence_score"]
                current_indicators["ai_sell_explanation"] = ai_sell_result["explanation"]

        if needs["bull_flag"]:
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

        # Add current price
        current_indicators["price"] = current_price

        # Evaluate conditions for each phase with detail capture
        # Uses evaluate_expression which handles both:
        # - New grouped format: { groups: [...], groupLogic: 'and'|'or' }
        # - Legacy flat format: [ condition1, condition2, ... ]
        base_order_signal = False
        base_order_details = []
        if self.base_order_conditions:
            base_order_signal, base_order_details = self.phase_evaluator.evaluate_expression(
                self.base_order_conditions, current_indicators, self.previous_indicators, self.base_order_logic,
                capture_details=True
            )

        safety_order_signal = False
        safety_order_details = []
        if self.safety_order_conditions:
            safety_order_signal, safety_order_details = self.phase_evaluator.evaluate_expression(
                self.safety_order_conditions, current_indicators, self.previous_indicators, self.safety_order_logic,
                capture_details=True
            )

        take_profit_signal = False
        take_profit_details = []
        if self.take_profit_conditions:
            take_profit_signal, take_profit_details = self.phase_evaluator.evaluate_expression(
                self.take_profit_conditions, current_indicators, self.previous_indicators, self.take_profit_logic,
                capture_details=True
            )

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
            # Condition evaluation details for logging
            "condition_details": {
                "base_order": base_order_details,
                "safety_order": safety_order_details,
                "take_profit": take_profit_details,
            },
        }

    def calculate_base_order_size(self, balance: float) -> float:
        """Calculate base order size based on configuration."""
        order_type = self.config.get("base_order_type", "percentage")

        if order_type == "percentage":
            percentage = self.config.get("base_order_percentage", 10.0)
            max_deals = self.config.get("max_concurrent_deals", 1)
            if max_deals > 1:
                per_deal_percentage = percentage / max_deals
                return balance * (per_deal_percentage / 100.0)
            return balance * (percentage / 100.0)
        elif order_type == "fixed_btc":
            # UI uses base_order_btc for fixed BTC amount
            return self.config.get("base_order_btc", 0.0001)
        else:
            # Fallback for legacy configs
            return self.config.get("base_order_fixed", 0.001)

    def calculate_safety_order_size(self, base_order_size: float, order_number: int) -> float:
        """Calculate safety order size with volume scaling."""
        order_type = self.config.get("safety_order_type", "percentage_of_base")

        if order_type == "percentage_of_base":
            base_safety_size = base_order_size * (self.config.get("safety_order_percentage", 50.0) / 100.0)
        elif order_type == "fixed_btc":
            # UI uses safety_order_btc for fixed BTC amount
            base_safety_size = self.config.get("safety_order_btc", 0.0001)
        else:
            # Fallback for legacy configs using safety_order_fixed
            base_safety_size = self.config.get("safety_order_fixed", 0.0005)

        volume_scale = self.config.get("safety_order_volume_scale", 1.0)
        return base_safety_size * (volume_scale ** (order_number - 1))

    def calculate_safety_order_price(self, entry_price: float, order_number: int) -> float:
        """Calculate trigger price for safety order with step scaling."""
        deviation = self.config.get("price_deviation", 2.0)
        step_scale = self.config.get("safety_order_step_scale", 1.0)

        total_deviation = 0.0
        for i in range(order_number):
            if i == 0:
                total_deviation += deviation
            else:
                total_deviation += deviation * (step_scale ** i)

        return entry_price * (1.0 - total_deviation / 100.0)

    async def should_buy(
        self, signal_data: Dict[str, Any], position: Optional[Any], balance: float, **kwargs
    ) -> Tuple[bool, float, str]:
        """Determine if we should buy based on signal data."""
        current_price = signal_data.get("price", 0)
        base_order_signal = signal_data.get("base_order_signal", False)
        safety_order_signal = signal_data.get("safety_order_signal", False)

        if position is None:
            # Initial base order
            if not base_order_signal and self.base_order_conditions:
                return False, 0.0, "Base order conditions not met"

            amount = self.calculate_base_order_size(balance)
            if amount <= 0 or amount > balance:
                return False, 0.0, "Insufficient balance"

            return True, amount, f"Base order (conditions met): {amount:.8f}"
        else:
            # Safety order logic

            # Skip safety orders for pattern-based positions (e.g., bull flag)
            # These use TSL/TTP exit strategy, not DCA
            if hasattr(position, "entry_stop_loss") and position.entry_stop_loss is not None:
                return False, 0.0, "Pattern position - DCA disabled (using TSL/TTP)"

            max_safety = self.config.get("max_safety_orders", 5)
            if max_safety == 0:
                return False, 0.0, "Safety orders disabled"

            # Count buy trades to determine safety orders completed
            # DCA orders = total buys - 1 (excluding the initial base order)
            buy_trades = [t for t in position.trades if t.side == "buy"]
            safety_orders_count = max(0, len(buy_trades) - 1)  # -1 for base order, min 0
            if safety_orders_count >= max_safety:
                return False, 0.0, f"Max safety orders reached ({safety_orders_count}/{max_safety})"

            next_order_number = safety_orders_count + 1

            # Determine reference price for DCA target calculation
            dca_reference = self.config.get("dca_target_reference", "average_price")
            sorted_buys = sorted(buy_trades, key=lambda t: t.timestamp if t.timestamp else 0) if buy_trades else []

            if dca_reference == "base_order" and sorted_buys:
                # Use the price of the first buy (base order)
                first_buy = sorted_buys[0]
                reference_price = first_buy.price if first_buy.price else position.average_buy_price
            elif dca_reference == "last_buy" and sorted_buys:
                # Use the price of the last buy trade
                last_buy = sorted_buys[-1]
                reference_price = last_buy.price if last_buy.price else position.average_buy_price
            else:
                # "average_price" or fallback - use average buy price
                reference_price = position.average_buy_price

            # Always check price target as minimum threshold
            # DCA targets set the MINIMUM drop required before a DCA can trigger
            trigger_price = self.calculate_safety_order_price(reference_price, next_order_number)
            if current_price > trigger_price:
                return False, 0.0, f"Price not low enough for SO #{next_order_number} (need ≤{trigger_price:.8f})"

            # If safety order conditions exist (like AI_BUY), also check them
            # Price target must be met AND conditions must be satisfied
            if self.safety_order_conditions:
                if not safety_order_signal:
                    return False, 0.0, f"SO #{next_order_number} price target met but conditions not met"

            # Calculate safety order size
            base_order_size = position.total_quote_spent / (1 + safety_orders_count)
            safety_size = self.calculate_safety_order_size(base_order_size, next_order_number)

            if safety_size > balance:
                return False, 0.0, "Insufficient balance for safety order"

            return True, safety_size, f"Safety order #{next_order_number}"

    async def should_sell(
        self, signal_data: Dict[str, Any], position: Any, current_price: float, market_context: Optional[Dict[str, Any]] = None
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
                return True, f"Pattern TSL triggered: ${current_price:.4f} <= TSL ${current_tsl:.4f} (profit: {profit_pct:.2f}%)"

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
                        return True, f"Pattern TTP triggered: ${current_price:.4f} (peak ${highest_since_tp:.4f}, profit: {profit_pct:.2f}%)"

                    return False, f"Pattern TTP active: holding for more (profit: {profit_pct:.2f}%, peak ${highest_since_tp:.4f})"

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

        # Check take profit %
        tp_pct = self.config.get("take_profit_percentage")
        if tp_pct is not None and profit_pct >= tp_pct:
            if self.config.get("trailing_take_profit", False):
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
            else:
                return True, f"Take profit target reached: {profit_pct:.2f}%"

        # Check take profit conditions
        # CRITICAL: Use take_profit_percentage as default min profit for condition exits
        # This prevents selling at low profits just because conditions triggered
        if take_profit_signal and self.take_profit_conditions:
            # If min_profit_for_conditions is explicitly set to a non-None value, use it
            # Otherwise fall back to take_profit_percentage
            # NOTE: We check for None explicitly because dict.get() returns 0.0 if that's the stored value
            min_profit_override = self.config.get("min_profit_for_conditions")
            if min_profit_override is not None:
                min_profit = min_profit_override
            else:
                min_profit = self.config.get("take_profit_percentage", 3.0)
            if profit_pct >= min_profit:
                return True, f"Take profit conditions met (profit: {profit_pct:.2f}%)"
            return False, f"Conditions met but profit too low ({profit_pct:.2f}% < {min_profit}%)"

        target_str = f"{tp_pct}%" if tp_pct is not None else "conditions"
        return False, f"Holding (profit: {profit_pct:.2f}%, target: {target_str})"
