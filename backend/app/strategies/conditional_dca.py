"""
Conditional DCA Strategy (3Commas-style)

Full-featured DCA strategy with user-defined conditions using:
- Custom buy conditions (mix and match indicators with operators)
- Custom sell conditions
- Base order + safety orders with scaling
- Traditional DCA features (volume scaling, step scaling, trailing, etc.)

Example Conditions:
- Buy when: RSI < 30 AND MACD crossing above signal
- Sell when: RSI > 70 OR Price > Bollinger Upper
"""

from typing import Dict, Any, List, Optional, Tuple
from app.strategies import (
    TradingStrategy,
    StrategyDefinition,
    StrategyParameter,
    StrategyRegistry
)
from app.indicator_calculator import IndicatorCalculator
from app.phase_conditions import PhaseConditionEvaluator


@StrategyRegistry.register
class ConditionalDCAStrategy(TradingStrategy):
    """
    Conditional DCA strategy with flexible indicator-based conditions

    Combines the power of:
    1. Custom conditions (buy when RSI < 30 AND MACD crosses up)
    2. DCA features (safety orders, volume/step scaling)
    3. Traditional risk management (TP, SL, trailing)
    """

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="conditional_dca",
            name="Conditional DCA (Custom Conditions)",
            description="Advanced DCA with user-defined buy/sell conditions. "
                       "Mix and match any indicators with operators like >, <, crossing above, etc. "
                       "Each condition can use its own timeframe.",
            parameters=[
                # Deal Management
                StrategyParameter(
                    name="max_concurrent_deals",
                    display_name="Max Concurrent Deals",
                    description="Maximum number of positions that can be open at the same time (3Commas style)",
                    type="int",
                    default=1,
                    min_value=1,
                    max_value=20
                ),

                # Base Order Settings
                StrategyParameter(
                    name="base_order_type",
                    display_name="Base Order Type",
                    description="How to calculate base order size",
                    type="str",
                    default="percentage",
                    options=["percentage", "fixed_btc"]
                ),
                StrategyParameter(
                    name="base_order_percentage",
                    display_name="Base Order % of BTC Balance",
                    description="Percentage of BTC balance for base order (if using percentage)",
                    type="float",
                    default=10.0,
                    min_value=1.0,
                    max_value=100.0
                ),
                StrategyParameter(
                    name="base_order_btc",
                    display_name="Base Order BTC Amount",
                    description="Fixed BTC amount for base order (if using fixed)",
                    type="float",
                    default=0.001,
                    min_value=0.0001,
                    max_value=10.0
                ),

                # Safety Order Settings
                StrategyParameter(
                    name="safety_order_type",
                    display_name="Safety Order Type",
                    description="How to calculate safety order size",
                    type="str",
                    default="percentage_of_base",
                    options=["percentage_of_base", "fixed_btc"]
                ),
                StrategyParameter(
                    name="safety_order_percentage",
                    display_name="Safety Order % of Base",
                    description="Each safety order as % of base order (if using percentage)",
                    type="float",
                    default=50.0,
                    min_value=10.0,
                    max_value=500.0
                ),
                StrategyParameter(
                    name="safety_order_btc",
                    display_name="Safety Order BTC Amount",
                    description="Fixed BTC amount for each safety order (if using fixed)",
                    type="float",
                    default=0.0005,
                    min_value=0.0001,
                    max_value=10.0
                ),
                StrategyParameter(
                    name="max_safety_orders",
                    display_name="Max Safety Orders",
                    description="Maximum number of safety orders",
                    type="int",
                    default=5,
                    min_value=0,
                    max_value=20
                ),

                # Price Deviation Settings
                StrategyParameter(
                    name="price_deviation",
                    display_name="Price Deviation %",
                    description="Price drop % to trigger first safety order",
                    type="float",
                    default=2.0,
                    min_value=0.1,
                    max_value=20.0
                ),
                StrategyParameter(
                    name="safety_order_step_scale",
                    display_name="Safety Order Step Scale",
                    description="Multiplier for price deviation between orders (1.0 = even spacing)",
                    type="float",
                    default=1.0,
                    min_value=1.0,
                    max_value=5.0
                ),

                # Volume Scaling
                StrategyParameter(
                    name="safety_order_volume_scale",
                    display_name="Safety Order Volume Scale",
                    description="Multiplier for each safety order size (1.0 = same size, 2.0 = double)",
                    type="float",
                    default=1.0,
                    min_value=1.0,
                    max_value=5.0
                ),

                # Take Profit Settings
                StrategyParameter(
                    name="take_profit_percentage",
                    display_name="Take Profit %",
                    description="Target profit % from average buy price",
                    type="float",
                    default=3.0,
                    min_value=0.1,
                    max_value=50.0
                ),
                StrategyParameter(
                    name="min_profit_for_conditions",
                    display_name="Min Profit % for Condition Exit",
                    description="Minimum profit % required to exit on take profit conditions (set negative to allow selling at a loss)",
                    type="float",
                    default=0.0,
                    min_value=-50.0,
                    max_value=50.0
                ),
                StrategyParameter(
                    name="trailing_take_profit",
                    display_name="Trailing Take Profit",
                    description="Enable trailing take profit (follows price up)",
                    type="bool",
                    default=False
                ),
                StrategyParameter(
                    name="trailing_deviation",
                    display_name="Trailing Deviation %",
                    description="How far price can drop from peak before selling (if trailing enabled)",
                    type="float",
                    default=1.0,
                    min_value=0.1,
                    max_value=10.0
                ),

                # Stop Loss Settings
                StrategyParameter(
                    name="stop_loss_enabled",
                    display_name="Enable Stop Loss",
                    description="Enable stop loss protection",
                    type="bool",
                    default=False
                ),
                StrategyParameter(
                    name="stop_loss_percentage",
                    display_name="Stop Loss %",
                    description="Stop loss % from average buy price (negative)",
                    type="float",
                    default=-10.0,
                    min_value=-50.0,
                    max_value=-0.1
                ),
                StrategyParameter(
                    name="trailing_stop_loss",
                    display_name="Trailing Stop Loss",
                    description="Enable trailing stop loss (SL follows price upward to protect profits)",
                    type="bool",
                    default=False
                ),
                StrategyParameter(
                    name="trailing_stop_deviation",
                    display_name="Trailing Stop Deviation %",
                    description="How far price can drop from peak before stop loss triggers (if trailing SL enabled)",
                    type="float",
                    default=5.0,
                    min_value=0.1,
                    max_value=20.0
                ),

                # Condition Settings (stored as JSON in strategy_config)
                # These are not StrategyParameters but part of config dict:
                # - buy_conditions: ConditionGroup
                # - sell_conditions: ConditionGroup
            ],
            supported_products=["ETH-BTC", "BTC-USD", "ETH-USD", "SOL-BTC", "SOL-USD"]
        )

    def validate_config(self):
        """Validate configuration parameters"""
        definition = self.get_definition()

        # Set defaults for missing parameters
        for param in definition.parameters:
            if param.name not in self.config:
                self.config[param.name] = param.default

        # Validate ranges
        for param in definition.parameters:
            if param.name not in self.config:
                continue
            value = self.config[param.name]
            if param.type in ["int", "float"]:
                if param.min_value is not None and value < param.min_value:
                    raise ValueError(f"{param.display_name} must be >= {param.min_value}")
                if param.max_value is not None and value > param.max_value:
                    raise ValueError(f"{param.display_name} must be <= {param.max_value}")

        # Initialize indicator calculator and phase condition evaluator
        self.indicator_calculator = IndicatorCalculator()
        self.phase_evaluator = PhaseConditionEvaluator(self.indicator_calculator)

        # Get phase conditions from config
        self.base_order_conditions = self.config.get("base_order_conditions", [])
        self.base_order_logic = self.config.get("base_order_logic", "and")

        self.safety_order_conditions = self.config.get("safety_order_conditions", [])
        self.safety_order_logic = self.config.get("safety_order_logic", "and")

        self.take_profit_conditions = self.config.get("take_profit_conditions", [])
        self.take_profit_logic = self.config.get("take_profit_logic", "and")

        # Track previous indicators for crossing detection
        self.previous_indicators = None

    async def analyze_signal(
        self,
        candles: List[Dict[str, Any]],
        current_price: float,
        candles_by_timeframe: Optional[Dict[str, List[Dict[str, Any]]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze market data and evaluate phase conditions

        Returns:
            Signal data dict with:
            - base_order_signal: bool
            - safety_order_signal: bool
            - take_profit_signal: bool
            - indicators: dict of all indicator values
            - price: current price
        """
        # Need fewer candles for longer timeframes (30min needs less data than 5min)
        min_candles_needed = 30  # Reduced from 50 to work with longer timeframes
        if len(candles) < min_candles_needed:
            print(f"[CONDITIONAL_DCA] Not enough candles: got {len(candles)}, need {min_candles_needed}")
            return None

        print(f"[CONDITIONAL_DCA] Analyzing with {len(candles)} candles for {len(timeframes_needed) if 'timeframes_needed' in locals() else 'unknown'} timeframes")

        # Extract required indicators from all phase conditions
        required = set()
        required.update(self.phase_evaluator.get_required_indicators(self.base_order_conditions))
        required.update(self.phase_evaluator.get_required_indicators(self.safety_order_conditions))
        required.update(self.phase_evaluator.get_required_indicators(self.take_profit_conditions))

        # Extract unique timeframes from required indicators
        timeframes_needed = set()
        for indicator_key in required:
            # Extract timeframe from keys like "FIVE_MINUTE_rsi_14"
            parts = indicator_key.split('_', 2)
            if len(parts) >= 2:
                # Reconstruct timeframe (handles ONE_MINUTE, FIVE_MINUTE, etc.)
                if parts[0] in ['ONE', 'FIVE', 'FIFTEEN', 'THIRTY', 'TWO', 'SIX']:
                    timeframe = f"{parts[0]}_{parts[1]}"
                    timeframes_needed.add(timeframe)

        # Use provided candles_by_timeframe or fallback to default candles
        if candles_by_timeframe is None:
            candles_by_timeframe = {'FIVE_MINUTE': candles}

        # Calculate indicators for each timeframe using actual candles
        current_indicators = {}

        for timeframe in timeframes_needed:
            # Get candles for this timeframe (fallback to default if not available)
            tf_candles = candles_by_timeframe.get(timeframe, candles)

            print(f"[CONDITIONAL_DCA] Timeframe {timeframe}: got {len(tf_candles)} candles")

            if len(tf_candles) < min_candles_needed:
                print(f"[CONDITIONAL_DCA] Skipping {timeframe}: only {len(tf_candles)} candles, need {min_candles_needed}")
                continue  # Not enough data for this timeframe

            # Extract just the indicator names (without timeframe prefix) for this timeframe
            tf_required = set()
            for indicator_key in required:
                if indicator_key.startswith(f"{timeframe}_"):
                    # Remove timeframe prefix
                    indicator_name = indicator_key[len(timeframe) + 1:]
                    tf_required.add(indicator_name)

            # Calculate indicators for this timeframe
            indicators_for_tf = self.indicator_calculator.calculate_all_indicators(
                tf_candles,
                tf_required
            )

            # Prefix each indicator with the timeframe
            for key, value in indicators_for_tf.items():
                current_indicators[f"{timeframe}_{key}"] = value

        # Evaluate base order conditions
        base_order_signal = False
        if self.base_order_conditions:
            base_order_signal = self.phase_evaluator.evaluate_phase_conditions(
                self.base_order_conditions,
                self.base_order_logic,
                current_indicators,
                self.previous_indicators
            )

        # Evaluate safety order conditions
        safety_order_signal = False
        if self.safety_order_conditions:
            safety_order_signal = self.phase_evaluator.evaluate_phase_conditions(
                self.safety_order_conditions,
                self.safety_order_logic,
                current_indicators,
                self.previous_indicators
            )

        # Evaluate take profit conditions
        take_profit_signal = False
        if self.take_profit_conditions:
            take_profit_signal = self.phase_evaluator.evaluate_phase_conditions(
                self.take_profit_conditions,
                self.take_profit_logic,
                current_indicators,
                self.previous_indicators
            )

        # Store current as previous for next iteration
        self.previous_indicators = current_indicators.copy()

        return {
            "signal_type": "phase_condition_check",
            "base_order_signal": base_order_signal,
            "safety_order_signal": safety_order_signal,
            "take_profit_signal": take_profit_signal,
            "indicators": current_indicators,
            "price": current_price
        }

    def calculate_base_order_size(self, btc_balance: float) -> float:
        """
        Calculate base order size based on configuration

        Smart budget allocation:
        - If max_concurrent_deals > 1, divide budget by max_deals
        - Example: 30% budget, 3 max deals → 10% per deal
        - This ensures each concurrent position gets equal budget
        """
        if self.config["base_order_type"] == "percentage":
            base_percentage = self.config["base_order_percentage"]

            # Smart budget division by max concurrent deals (3Commas style)
            max_deals = self.config.get("max_concurrent_deals", 1)
            if max_deals > 1:
                # Divide budget equally among max concurrent deals
                per_deal_percentage = base_percentage / max_deals
                return btc_balance * (per_deal_percentage / 100.0)
            else:
                return btc_balance * (base_percentage / 100.0)
        else:  # fixed_btc
            return self.config["base_order_btc"]

    def calculate_safety_order_size(self, base_order_size: float, order_number: int) -> float:
        """
        Calculate safety order size with volume scaling

        Args:
            base_order_size: Size of the base order
            order_number: Which safety order (1, 2, 3, etc.)
        """
        # Base safety order size
        if self.config["safety_order_type"] == "percentage_of_base":
            base_safety_size = base_order_size * (self.config["safety_order_percentage"] / 100.0)
        else:  # fixed_btc
            base_safety_size = self.config["safety_order_btc"]

        # Apply volume scaling: size * (scale ^ (order_number - 1))
        volume_scale = self.config["safety_order_volume_scale"]
        if volume_scale == 1.0:
            return base_safety_size

        return base_safety_size * (volume_scale ** (order_number - 1))

    def calculate_safety_order_price(self, entry_price: float, order_number: int) -> float:
        """
        Calculate trigger price for safety order with step scaling

        Args:
            entry_price: Initial entry price
            order_number: Which safety order (1, 2, 3, etc.)
        """
        deviation = self.config["price_deviation"]
        step_scale = self.config["safety_order_step_scale"]

        # Calculate cumulative deviation
        total_deviation = 0.0
        for i in range(order_number):
            if i == 0:
                total_deviation += deviation
            else:
                total_deviation += deviation * (step_scale ** i)

        # Calculate trigger price
        trigger_price = entry_price * (1.0 - total_deviation / 100.0)
        return trigger_price

    async def should_buy(
        self,
        signal_data: Dict[str, Any],
        position: Optional[Any],
        btc_balance: float
    ) -> Tuple[bool, float, str]:
        """
        Determine if we should buy

        Logic:
        1. If no position: Check base order conditions
        2. If position exists: Check safety order conditions OR price deviation
        """
        current_price = signal_data.get("price", 0)
        base_order_signal = signal_data.get("base_order_signal", False)
        safety_order_signal = signal_data.get("safety_order_signal", False)

        if position is None:
            # Initial base order - check conditions
            if not base_order_signal and len(self.base_order_conditions) > 0:
                return False, 0.0, "Base order conditions not met"

            btc_to_spend = self.calculate_base_order_size(btc_balance)
            if btc_to_spend <= 0 or btc_to_spend > btc_balance:
                return False, 0.0, "Insufficient BTC balance"

            return True, btc_to_spend, f"Base order (conditions met): {btc_to_spend:.8f} BTC"

        else:
            # Safety order logic
            max_safety = self.config["max_safety_orders"]
            if max_safety == 0:
                return False, 0.0, "Safety orders disabled"

            # Count existing safety orders
            safety_orders_count = position.trade_count - 1 if hasattr(position, 'trade_count') else 0

            if safety_orders_count >= max_safety:
                return False, 0.0, f"Max safety orders reached ({max_safety})"

            next_order_number = safety_orders_count + 1
            entry_price = position.average_buy_price

            # Check safety order conditions if set
            if len(self.safety_order_conditions) > 0:
                if not safety_order_signal:
                    return False, 0.0, "Safety order conditions not met"
            else:
                # Fallback to price deviation
                trigger_price = self.calculate_safety_order_price(entry_price, next_order_number)
                if current_price > trigger_price:
                    return False, 0.0, f"Price not low enough for SO #{next_order_number} (need {trigger_price:.8f})"

            # Calculate safety order size
            base_order_size = position.total_btc_spent / (1 + safety_orders_count)
            safety_size = self.calculate_safety_order_size(base_order_size, next_order_number)

            if safety_size > btc_balance:
                return False, 0.0, "Insufficient BTC for safety order"

            return True, safety_size, f"Safety order #{next_order_number} (conditions met)"

    async def should_sell(
        self,
        signal_data: Dict[str, Any],
        position: Any,
        current_price: float
    ) -> Tuple[bool, str]:
        """
        Determine if we should sell

        Logic:
        1. Update trailing trackers (highest price for TP/SL)
        2. Check trailing stop loss
        3. Check stop loss
        4. Check trailing take profit
        5. Check simple take profit
        6. Check take profit conditions
        """
        take_profit_signal = signal_data.get("take_profit_signal", False)

        # Calculate current profit
        avg_price = position.average_buy_price
        eth_value = position.total_eth_acquired * current_price
        profit_btc = eth_value - position.total_btc_spent
        profit_pct = (profit_btc / position.total_btc_spent) * 100

        # Update highest price since entry (for trailing SL)
        if position.highest_price_since_entry is None:
            position.highest_price_since_entry = current_price
        elif current_price > position.highest_price_since_entry:
            position.highest_price_since_entry = current_price

        # Check trailing stop loss first (if enabled)
        if self.config.get("trailing_stop_loss", False):
            trailing_stop_dev = self.config.get("trailing_stop_deviation", 5.0)
            highest_price = position.highest_price_since_entry or avg_price

            # Calculate trailing SL price: highest_price * (1 - deviation/100)
            trailing_sl_price = highest_price * (1.0 - trailing_stop_dev / 100.0)

            if current_price <= trailing_sl_price:
                return True, f"Trailing stop loss triggered (Peak: {highest_price:.8f}, SL: {trailing_sl_price:.8f}, Current: {current_price:.8f})"

        # Check regular stop loss
        if self.config["stop_loss_enabled"]:
            stop_loss_pct = self.config["stop_loss_percentage"]
            if profit_pct <= stop_loss_pct:
                return True, f"Stop loss triggered at {profit_pct:.2f}%"

        # Check take profit %
        target_profit = self.config["take_profit_percentage"]

        if profit_pct >= target_profit:
            if self.config["trailing_take_profit"]:
                # Proper trailing take profit logic
                trailing_dev = self.config["trailing_deviation"]

                # Activate trailing TP when we hit target
                if not position.trailing_tp_active:
                    position.trailing_tp_active = True
                    position.highest_price_since_tp = current_price

                # Update highest price since TP activated
                if position.highest_price_since_tp is None:
                    position.highest_price_since_tp = current_price
                elif current_price > position.highest_price_since_tp:
                    position.highest_price_since_tp = current_price

                # Check if price dropped by trailing_deviation from peak
                peak_price = position.highest_price_since_tp
                trailing_trigger_price = peak_price * (1.0 - trailing_dev / 100.0)

                if current_price <= trailing_trigger_price:
                    return True, f"Trailing TP triggered (Peak: {peak_price:.8f}, Trigger: {trailing_trigger_price:.8f}, Profit: {profit_pct:.2f}%)"

                return False, f"Trailing TP active (Peak: {peak_price:.8f}, Current: {current_price:.8f}, Profit: {profit_pct:.2f}%)"
            else:
                # Simple take profit
                return True, f"Take profit target reached: {profit_pct:.2f}%"

        # Check additional take profit conditions
        if take_profit_signal and len(self.take_profit_conditions) > 0:
            # Only sell on conditions if profit meets minimum threshold
            min_profit = self.config.get("min_profit_for_conditions", 0.0)
            if profit_pct >= min_profit:
                return True, f"Take profit conditions met (P&L: {profit_pct:.2f}%, Min: {min_profit}%)"
            else:
                return False, f"Conditions met but profit too low ({profit_pct:.2f}% < {min_profit}%)"

        return False, f"Holding (P&L: {profit_pct:.2f}%, Target: {target_profit}%)"
