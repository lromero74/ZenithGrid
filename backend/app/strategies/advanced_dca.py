"""
Advanced DCA Strategy (3Commas-style)

Full-featured DCA strategy with:
- Base order (BTC amount or % of balance)
- Safety orders with volume/step scaling
- Take profit with trailing option
- Stop loss with trailing option
- Price deviation controls
"""

from typing import Any, Dict, List, Optional, Tuple

from app.strategies import (
    StrategyDefinition,
    StrategyParameter,
    StrategyRegistry,
    TradingStrategy,
)


@StrategyRegistry.register
class AdvancedDCAStrategy(TradingStrategy):
    """Advanced DCA strategy with 3Commas-style features"""

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="advanced_dca",
            name="Advanced DCA (3Commas-style)",
            description="Full-featured DCA strategy with base order, safety orders, "
            "volume/step scaling, trailing take profit, and stop loss.",
            parameters=[
                StrategyParameter(
                    name="timeframe",
                    display_name="Timeframe / Candle Interval",
                    description="Timeframe for price monitoring (e.g., 5min, 1hour, 1day)",
                    type="str",
                    default="FIVE_MINUTE",
                    options=[
                        "ONE_MINUTE",
                        "FIVE_MINUTE",
                        "FIFTEEN_MINUTE",
                        "THIRTY_MINUTE",
                        "ONE_HOUR",
                        "TWO_HOUR",
                        "SIX_HOUR",
                        "ONE_DAY",
                    ],
                ),
                # Base Order Settings
                StrategyParameter(
                    name="base_order_type",
                    display_name="Base Order Type",
                    description="How to calculate base order size",
                    type="str",
                    default="percentage",
                    options=["percentage", "fixed_btc"],
                ),
                StrategyParameter(
                    name="base_order_percentage",
                    display_name="Base Order % of BTC Balance",
                    description="Percentage of BTC balance for base order (if using percentage)",
                    type="float",
                    default=10.0,
                    min_value=1.0,
                    max_value=100.0,
                ),
                StrategyParameter(
                    name="base_order_btc",
                    display_name="Base Order BTC Amount",
                    description="Fixed BTC amount for base order (if using fixed)",
                    type="float",
                    default=0.001,
                    min_value=0.0001,
                    max_value=10.0,
                ),
                # Safety Order Settings
                StrategyParameter(
                    name="safety_order_type",
                    display_name="Safety Order Type",
                    description="How to calculate safety order size",
                    type="str",
                    default="percentage_of_base",
                    options=["percentage_of_base", "fixed_btc"],
                ),
                StrategyParameter(
                    name="safety_order_percentage",
                    display_name="Safety Order % of Base",
                    description="Each safety order as % of base order (if using percentage)",
                    type="float",
                    default=50.0,
                    min_value=10.0,
                    max_value=500.0,
                ),
                StrategyParameter(
                    name="safety_order_btc",
                    display_name="Safety Order BTC Amount",
                    description="Fixed BTC amount for each safety order (if using fixed)",
                    type="float",
                    default=0.0005,
                    min_value=0.0001,
                    max_value=10.0,
                ),
                StrategyParameter(
                    name="max_safety_orders",
                    display_name="Max Safety Orders",
                    description="Maximum number of safety orders",
                    type="int",
                    default=5,
                    min_value=0,
                    max_value=20,
                ),
                # Price Deviation Settings
                StrategyParameter(
                    name="price_deviation",
                    display_name="Price Deviation %",
                    description="Price drop % to trigger first safety order",
                    type="float",
                    default=2.0,
                    min_value=0.1,
                    max_value=20.0,
                ),
                StrategyParameter(
                    name="safety_order_step_scale",
                    display_name="Safety Order Step Scale",
                    description="Multiplier for price deviation between orders (1.0 = even spacing)",
                    type="float",
                    default=1.0,
                    min_value=1.0,
                    max_value=5.0,
                ),
                # Volume Scaling
                StrategyParameter(
                    name="safety_order_volume_scale",
                    display_name="Safety Order Volume Scale",
                    description="Multiplier for each safety order size (1.0 = same size, 2.0 = double)",
                    type="float",
                    default=1.0,
                    min_value=1.0,
                    max_value=5.0,
                ),
                # Take Profit Settings
                StrategyParameter(
                    name="take_profit_percentage",
                    display_name="Take Profit %",
                    description="Target profit % from average buy price",
                    type="float",
                    default=3.0,
                    min_value=0.1,
                    max_value=50.0,
                ),
                StrategyParameter(
                    name="trailing_take_profit",
                    display_name="Trailing Take Profit",
                    description="Enable trailing take profit (follows price up)",
                    type="bool",
                    default=False,
                ),
                StrategyParameter(
                    name="trailing_deviation",
                    display_name="Trailing Deviation %",
                    description="How far price can drop from peak before selling (if trailing enabled)",
                    type="float",
                    default=1.0,
                    min_value=0.1,
                    max_value=10.0,
                ),
                # Stop Loss Settings
                StrategyParameter(
                    name="stop_loss_enabled",
                    display_name="Enable Stop Loss",
                    description="Enable stop loss protection",
                    type="bool",
                    default=False,
                ),
                StrategyParameter(
                    name="stop_loss_percentage",
                    display_name="Stop Loss %",
                    description="Stop loss % from average buy price (negative)",
                    type="float",
                    default=-10.0,
                    min_value=-50.0,
                    max_value=-0.1,
                ),
                StrategyParameter(
                    name="trailing_stop_loss",
                    display_name="Trailing Stop Loss",
                    description="Enable trailing stop loss (SL follows price upward to protect profits)",
                    type="bool",
                    default=False,
                ),
                StrategyParameter(
                    name="trailing_stop_deviation",
                    display_name="Trailing Stop Deviation %",
                    description="How far price can drop from peak before stop loss triggers (if trailing SL enabled)",
                    type="float",
                    default=5.0,
                    min_value=0.1,
                    max_value=20.0,
                ),
            ],
            supported_products=["ETH-BTC", "BTC-USD", "ETH-USD", "SOL-BTC", "SOL-USD"],
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

    async def analyze_signal(self, candles: List[Dict[str, Any]], current_price: float, **kwargs -> Optional[Dict[str, Any]]:
        """
        Advanced DCA doesn't use technical indicators - it only buys on initial entry
        and then uses price-based safety orders.

        Returns None - signals are generated by position logic in should_buy/should_sell
        """
        # This strategy is price-based, not indicator-based
        # Return a simple "check" signal that triggers position evaluation
        return {"signal_type": "check", "price": current_price}

    def calculate_base_order_size(self, btc_balance: float) -> float:
        """Calculate base order size based on configuration"""
        if self.config["base_order_type"] == "percentage":
            return btc_balance * (self.config["base_order_percentage"] / 100.0)
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
        # Order 1: -deviation
        # Order 2: -deviation - (deviation * step_scale)
        # Order 3: -deviation - (deviation * step_scale) - (deviation * step_scale^2)

        total_deviation = 0.0
        for i in range(order_number):
            if i == 0:
                total_deviation += deviation
            else:
                total_deviation += deviation * (step_scale**i)

        # Calculate trigger price
        trigger_price = entry_price * (1.0 - total_deviation / 100.0)
        return trigger_price

    async def should_buy(
        self, signal_data: Dict[str, Any], position: Optional[Any], btc_balance: float
    ) -> Tuple[bool, float, str]:
        """
        Determine if we should buy

        Logic:
        - If no position: Create base order
        - If position exists: Check if price has dropped enough for next safety order
        """
        current_price = signal_data.get("price", 0)

        if position is None:
            # Initial base order
            btc_to_spend = self.calculate_base_order_size(btc_balance)
            if btc_to_spend <= 0 or btc_to_spend > btc_balance:
                return False, 0.0, "Insufficient BTC balance"
            return True, btc_to_spend, f"Base order: {btc_to_spend:.8f} BTC"

        else:
            # Check for safety order
            max_safety = self.config["max_safety_orders"]
            if max_safety == 0:
                return False, 0.0, "Safety orders disabled"

            # Count existing safety orders (total trades - 1 base order)
            safety_orders_count = position.trade_count - 1 if hasattr(position, "trade_count") else 0

            if safety_orders_count >= max_safety:
                return False, 0.0, f"Max safety orders reached ({max_safety})"

            # Calculate what the next safety order number would be
            next_order_number = safety_orders_count + 1

            # Get entry price (average price from position)
            entry_price = position.average_buy_price

            # SAFETY CHECK: Price must be at least 2% below cost basis to DCA
            # This prevents "chasing" the price and ensures we only average down meaningfully
            min_required_drop = entry_price * 0.98  # 2% below cost basis
            if current_price > min_required_drop:
                return False, 0.0, f"Price ({current_price:.8f}) must be 2% below cost basis ({entry_price:.8f}) to DCA"

            # Calculate trigger price for next safety order
            trigger_price = self.calculate_safety_order_price(entry_price, next_order_number)

            # Check if current price has dropped enough
            if current_price <= trigger_price:
                # Calculate safety order size
                base_order_size = position.total_btc_spent / (1 + safety_orders_count)  # Approximate
                safety_size = self.calculate_safety_order_size(base_order_size, next_order_number)

                if safety_size > btc_balance:
                    return False, 0.0, "Insufficient BTC for safety order"

                return True, safety_size, f"Safety order #{next_order_number} at {current_price:.8f}"

            return False, 0.0, f"Price not low enough for SO #{next_order_number} (need {trigger_price:.8f})"

    async def should_sell(self, signal_data: Dict[str, Any], position: Any, current_price: float) -> Tuple[bool, str]:
        """
        Determine if we should sell

        Logic:
        1. Update trailing trackers (highest price for TP/SL)
        2. Check trailing stop loss
        3. Check regular stop loss
        4. Check trailing take profit
        5. Check simple take profit
        """
        avg_price = position.average_buy_price

        # Calculate current profit
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
                return True, f"Trailing stop loss triggered (Peak: {highest_price:.8f}, SL: {trailing_sl_price:.8f})"

        # Check regular stop loss
        if self.config["stop_loss_enabled"]:
            stop_loss_pct = self.config["stop_loss_percentage"]
            if profit_pct <= stop_loss_pct:
                return True, f"Stop loss triggered at {profit_pct:.2f}%"

        # Check take profit
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
                    return True, f"Trailing TP triggered (Peak: {peak_price:.8f}, Profit: {profit_pct:.2f}%)"

                return False, f"Trailing TP active (Peak: {peak_price:.8f}, Profit: {profit_pct:.2f}%)"
            else:
                # Simple take profit
                return True, f"Take profit target reached: {profit_pct:.2f}%"

        return False, f"Profit {profit_pct:.2f}% below target {target_profit}%"
