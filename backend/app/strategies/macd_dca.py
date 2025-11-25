"""
MACD DCA Strategy

Buys on MACD crossover (bullish signal) with Dollar Cost Averaging.
Sells on MACD cross down when profit target is reached.
"""

from typing import Any, Dict, List, Optional, Tuple

from app.indicators import MACDCalculator
from app.strategies import (
    StrategyDefinition,
    StrategyParameter,
    StrategyRegistry,
    TradingStrategy,
)


@StrategyRegistry.register
class MACDDCAStrategy(TradingStrategy):
    """MACD-based DCA strategy"""

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="macd_dca",
            name="MACD DCA Strategy",
            description="Dollar Cost Averaging based on MACD crossover signals. "
            "Buys when MACD crosses above signal line, sells when crosses below with profit.",
            parameters=[
                StrategyParameter(
                    name="timeframe",
                    display_name="Timeframe / Candle Interval",
                    description="Timeframe for MACD analysis (e.g., 5min, 1hour, 1day)",
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
                StrategyParameter(
                    name="base_order_type",
                    display_name="Base Order Type",
                    description="How to calculate base order size",
                    type="str",
                    default="percentage",
                    options=["percentage", "fixed_btc"],
                ),
                StrategyParameter(
                    name="initial_btc_percentage",
                    display_name="Initial Buy % of BTC Balance",
                    description="Percentage of BTC balance to use for initial buy (if using percentage)",
                    type="float",
                    default=10.0,
                    min_value=1.0,
                    max_value=50.0,
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
                StrategyParameter(
                    name="dca_order_type",
                    display_name="DCA Order Type",
                    description="How to calculate DCA order size",
                    type="str",
                    default="percentage_of_initial",
                    options=["percentage_of_initial", "fixed_btc"],
                ),
                StrategyParameter(
                    name="dca_percentage",
                    display_name="DCA Buy % of Initial",
                    description="Percentage of initial BTC for each DCA buy (if using percentage)",
                    type="float",
                    default=5.0,
                    min_value=1.0,
                    max_value=25.0,
                ),
                StrategyParameter(
                    name="dca_order_btc",
                    display_name="DCA Order BTC Amount",
                    description="Fixed BTC amount for each DCA order (if using fixed)",
                    type="float",
                    default=0.0005,
                    min_value=0.0001,
                    max_value=10.0,
                ),
                StrategyParameter(
                    name="max_btc_usage_percentage",
                    display_name="Max BTC Usage %",
                    description="Maximum percentage of initial BTC to use total",
                    type="float",
                    default=25.0,
                    min_value=10.0,
                    max_value=100.0,
                ),
                StrategyParameter(
                    name="min_profit_percentage",
                    display_name="Min Profit %",
                    description="Minimum profit percentage required to sell",
                    type="float",
                    default=1.0,
                    min_value=0.1,
                    max_value=10.0,
                ),
                StrategyParameter(
                    name="macd_fast_period",
                    display_name="MACD Fast Period",
                    description="Fast EMA period for MACD calculation",
                    type="int",
                    default=12,
                    min_value=5,
                    max_value=50,
                ),
                StrategyParameter(
                    name="macd_slow_period",
                    display_name="MACD Slow Period",
                    description="Slow EMA period for MACD calculation",
                    type="int",
                    default=26,
                    min_value=10,
                    max_value=100,
                ),
                StrategyParameter(
                    name="macd_signal_period",
                    display_name="MACD Signal Period",
                    description="Signal line period for MACD",
                    type="int",
                    default=9,
                    min_value=5,
                    max_value=50,
                ),
            ],
            supported_products=["ETH-BTC", "BTC-USD", "ETH-USD"],
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
            value = self.config[param.name]
            if param.min_value is not None and value < param.min_value:
                raise ValueError(f"{param.display_name} must be >= {param.min_value}")
            if param.max_value is not None and value > param.max_value:
                raise ValueError(f"{param.display_name} must be <= {param.max_value}")

        # Initialize MACD calculator
        self.macd_calculator = MACDCalculator(
            fast_period=int(self.config["macd_fast_period"]),
            slow_period=int(self.config["macd_slow_period"]),
            signal_period=int(self.config["macd_signal_period"]),
        )

    async def analyze_signal(self, candles: List[Dict[str, Any]], current_price: float, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Analyze MACD and detect crossover signals

        Returns:
            Dict with signal_type ("cross_up" or "cross_down"), macd values, etc.
        """
        if len(candles) < self.config["macd_slow_period"] + self.config["macd_signal_period"]:
            return None  # Not enough data

        # Extract close prices
        close_prices = [float(c["close"]) for c in candles]

        # Calculate MACD
        macd_line, signal_line, histogram = self.macd_calculator.calculate(close_prices)

        if len(histogram) < 2:
            return None  # Need at least 2 values to detect crossover

        # Detect crossover
        prev_hist = histogram[-2]
        curr_hist = histogram[-1]

        signal_type = None
        if prev_hist <= 0 and curr_hist > 0:
            signal_type = "cross_up"  # Bullish
        elif prev_hist >= 0 and curr_hist < 0:
            signal_type = "cross_down"  # Bearish

        if signal_type:
            return {
                "signal_type": signal_type,
                "macd_value": macd_line[-1],
                "macd_signal": signal_line[-1],
                "macd_histogram": curr_hist,
                "price": current_price,
            }

        return None

    async def should_buy(
        self, signal_data: Dict[str, Any], position: Optional[Any], btc_balance: float
    ) -> Tuple[bool, float, str]:
        """
        Determine if we should buy based on MACD cross up

        Logic:
        - If no position: Buy initial_btc_percentage
        - If position exists: DCA with dca_percentage (if within max limit)
        """
        if signal_data.get("signal_type") != "cross_up":
            return False, 0.0, "Not a buy signal"

        base_order_type = self.config.get("base_order_type", "percentage")
        dca_order_type = self.config.get("dca_order_type", "percentage_of_initial")
        max_usage_pct = self.config["max_btc_usage_percentage"]

        if position is None:
            # Initial buy - use base order type
            if base_order_type == "percentage":
                initial_pct = self.config["initial_btc_percentage"]
                btc_to_spend = btc_balance * (initial_pct / 100.0)
                reason = f"Initial position with {initial_pct}% of BTC"
            else:  # fixed_btc
                btc_to_spend = self.config["base_order_btc"]
                reason = f"Initial position with {btc_to_spend:.8f} BTC"

            if btc_to_spend <= 0 or btc_to_spend > btc_balance:
                return False, 0.0, "Insufficient BTC balance"
            return True, btc_to_spend, reason

        else:
            # DCA buy - use DCA order type
            if dca_order_type == "percentage_of_initial":
                dca_pct = self.config["dca_percentage"]
                btc_to_spend = position.initial_btc_balance * (dca_pct / 100.0)
                reason = f"DCA buy with {dca_pct}% of initial"
            else:  # fixed_btc
                btc_to_spend = self.config["dca_order_btc"]
                reason = f"DCA buy with {btc_to_spend:.8f} BTC"

            new_total = position.total_btc_spent + btc_to_spend
            max_allowed = position.initial_btc_balance * (max_usage_pct / 100.0)

            if new_total <= max_allowed:
                return True, btc_to_spend, reason
            else:
                return False, 0.0, f"Max BTC limit reached ({max_allowed:.8f} BTC)"

    async def should_sell(self, signal_data: Dict[str, Any], position: Any, current_price: float) -> Tuple[bool, str]:
        """
        Determine if we should sell based on MACD cross down and profit target

        Logic:
        - Only sell on cross_down signal
        - Only if profit >= min_profit_percentage
        """
        if signal_data.get("signal_type") != "cross_down":
            return False, "Not a sell signal"

        # Calculate current profit
        eth_value = position.total_eth_acquired * current_price
        current_profit_btc = eth_value - position.total_btc_spent
        current_profit_pct = (current_profit_btc / position.total_btc_spent) * 100

        min_profit = self.config["min_profit_percentage"]

        if current_profit_pct >= min_profit:
            return True, f"Profit {current_profit_pct:.2f}% >= target {min_profit}%"
        else:
            return False, f"Profit {current_profit_pct:.2f}% below target {min_profit}%"
