"""
RSI Strategy

Buys when RSI indicates oversold conditions (< 30).
Sells when RSI indicates overbought conditions (> 70) with profit target.
"""

from typing import Any, Dict, List, Optional, Tuple

from app.strategies import (
    StrategyDefinition,
    StrategyParameter,
    StrategyRegistry,
    TradingStrategy,
)


def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
    """Calculate RSI (Relative Strength Index)"""
    if len(prices) < period + 1:
        return []

    # Calculate price changes
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]

    # Separate gains and losses
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    # Calculate initial average gain and loss
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    rsi_values = []

    # Calculate RSI for each point
    for i in range(period, len(deltas)):
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        rsi_values.append(rsi)

        # Update averages (smoothed)
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    return rsi_values


@StrategyRegistry.register
class RSIStrategy(TradingStrategy):
    """RSI-based trading strategy"""

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="rsi",
            name="RSI Strategy",
            description="Buys when RSI indicates oversold (< 30), sells when overbought (> 70) with profit target.",
            parameters=[
                StrategyParameter(
                    name="timeframe",
                    display_name="Timeframe / Candle Interval",
                    description="Timeframe for RSI analysis (e.g., 5min, 1hour, 1day)",
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
                    name="rsi_period",
                    display_name="RSI Period",
                    description="Number of periods for RSI calculation",
                    type="int",
                    default=14,
                    min_value=5,
                    max_value=50,
                ),
                StrategyParameter(
                    name="oversold_threshold",
                    display_name="Oversold Threshold",
                    description="RSI level below which to buy (oversold)",
                    type="float",
                    default=30.0,
                    min_value=10.0,
                    max_value=40.0,
                ),
                StrategyParameter(
                    name="overbought_threshold",
                    display_name="Overbought Threshold",
                    description="RSI level above which to consider selling (overbought)",
                    type="float",
                    default=70.0,
                    min_value=60.0,
                    max_value=90.0,
                ),
                StrategyParameter(
                    name="buy_amount_percentage",
                    display_name="Buy Amount %",
                    description="Percentage of BTC balance to use per buy",
                    type="float",
                    default=10.0,
                    min_value=1.0,
                    max_value=50.0,
                ),
                StrategyParameter(
                    name="min_profit_percentage",
                    display_name="Min Profit %",
                    description="Minimum profit percentage required to sell",
                    type="float",
                    default=2.0,
                    min_value=0.1,
                    max_value=20.0,
                ),
                StrategyParameter(
                    name="max_position_size_btc",
                    display_name="Max Position Size (BTC)",
                    description="Maximum BTC to allocate to a single position",
                    type="float",
                    default=0.1,
                    min_value=0.001,
                    max_value=10.0,
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

    async def analyze_signal(self, candles: List[Dict[str, Any]], current_price: float, **kwargs -> Optional[Dict[str, Any]]:
        """
        Analyze RSI and detect oversold/overbought conditions

        Returns:
            Dict with signal_type ("oversold" or "overbought"), RSI value, etc.
        """
        rsi_period = int(self.config["rsi_period"])

        if len(candles) < rsi_period + 10:  # Need extra data for RSI calculation
            return None

        # Extract close prices
        close_prices = [float(c["close"]) for c in candles]

        # Calculate RSI
        rsi_values = calculate_rsi(close_prices, rsi_period)

        if len(rsi_values) == 0:
            return None

        current_rsi = rsi_values[-1]
        oversold = self.config["oversold_threshold"]
        overbought = self.config["overbought_threshold"]

        signal_type = None
        if current_rsi < oversold:
            signal_type = "oversold"  # Buy signal
        elif current_rsi > overbought:
            signal_type = "overbought"  # Potential sell signal

        if signal_type:
            return {"signal_type": signal_type, "rsi": current_rsi, "price": current_price}

        return None

    async def should_buy(
        self, signal_data: Dict[str, Any], position: Optional[Any], btc_balance: float
    ) -> Tuple[bool, float, str]:
        """
        Buy when RSI indicates oversold

        Logic:
        - Only buy on oversold signal
        - Don't buy if we already have an open position
        - Use buy_amount_percentage of available BTC
        """
        if signal_data.get("signal_type") != "oversold":
            return False, 0.0, "Not an oversold signal"

        if position is not None:
            return False, 0.0, "Already have an open position"

        buy_pct = self.config["buy_amount_percentage"]
        max_position = self.config["max_position_size_btc"]

        btc_to_spend = min(btc_balance * (buy_pct / 100.0), max_position)

        if btc_to_spend <= 0:
            return False, 0.0, "Insufficient BTC balance"

        rsi = signal_data.get("rsi", 0)
        return True, btc_to_spend, f"RSI oversold ({rsi:.1f}) - buying {buy_pct}% of BTC"

    async def should_sell(self, signal_data: Dict[str, Any], position: Any, current_price: float) -> Tuple[bool, str]:
        """
        Sell when RSI indicates overbought AND profit target is met

        Logic:
        - Need overbought signal
        - Need to meet minimum profit target
        """
        if signal_data.get("signal_type") != "overbought":
            return False, "Not an overbought signal"

        # Calculate current profit
        eth_value = position.total_eth_acquired * current_price
        current_profit_btc = eth_value - position.total_btc_spent
        current_profit_pct = (current_profit_btc / position.total_btc_spent) * 100

        min_profit = self.config["min_profit_percentage"]

        if current_profit_pct >= min_profit:
            rsi = signal_data.get("rsi", 0)
            return True, f"RSI overbought ({rsi:.1f}) + profit {current_profit_pct:.2f}% >= target"
        else:
            return False, f"RSI overbought but profit {current_profit_pct:.2f}% < target {min_profit}%"
