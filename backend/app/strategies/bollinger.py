"""
Bollinger Bands %B Strategy

Buys when %B indicates oversold (< 0.2).
Sells when %B indicates overbought (> 0.8) with profit target.

%B Formula: (Price - Lower Band) / (Upper Band - Lower Band)
- %B > 1: Price above upper band
- %B = 0.5: Price at middle band (SMA)
- %B < 0: Price below lower band
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from app.strategies import (
    StrategyDefinition,
    StrategyParameter,
    StrategyRegistry,
    TradingStrategy,
)


def calculate_sma(prices: List[float], period: int) -> List[float]:
    """Calculate Simple Moving Average"""
    if len(prices) < period:
        return []

    sma = []
    for i in range(period - 1, len(prices)):
        avg = sum(prices[i - period + 1 : i + 1]) / period
        sma.append(avg)
    return sma


def calculate_std_dev(prices: List[float], period: int, sma_values: List[float]) -> List[float]:
    """Calculate Standard Deviation"""
    std_devs = []

    for i in range(len(sma_values)):
        data_index = i + period - 1
        subset = prices[data_index - period + 1 : data_index + 1]
        mean = sma_values[i]
        variance = sum((x - mean) ** 2 for x in subset) / period
        std_dev = math.sqrt(variance)
        std_devs.append(std_dev)

    return std_devs


def calculate_bollinger_bands(
    prices: List[float], period: int = 20, std_multiplier: float = 2.0
) -> Tuple[List[float], List[float], List[float], List[float]]:
    """
    Calculate Bollinger Bands and %B

    Returns:
        Tuple of (middle_band, upper_band, lower_band, percent_b)
    """
    if len(prices) < period:
        return [], [], [], []

    # Calculate middle band (SMA)
    middle_band = calculate_sma(prices, period)

    # Calculate standard deviation
    std_dev = calculate_std_dev(prices, period, middle_band)

    # Calculate upper and lower bands
    upper_band = [middle_band[i] + (std_multiplier * std_dev[i]) for i in range(len(middle_band))]
    lower_band = [middle_band[i] - (std_multiplier * std_dev[i]) for i in range(len(middle_band))]

    # Calculate %B
    percent_b = []
    for i in range(len(middle_band)):
        price_index = i + period - 1
        current_price = prices[price_index]
        band_width = upper_band[i] - lower_band[i]

        if band_width == 0:
            pb = 0.5  # Default to middle if bands converge
        else:
            pb = (current_price - lower_band[i]) / band_width

        percent_b.append(pb)

    return middle_band, upper_band, lower_band, percent_b


@StrategyRegistry.register
class BollingerBandsStrategy(TradingStrategy):
    """Bollinger Bands %B strategy"""

    def get_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            id="bollinger_bands",
            name="Bollinger Bands %B Strategy",
            description="Buys when %B < 0.2 (price near lower band - oversold), "
            "sells when %B > 0.8 (price near upper band - overbought) with profit target.",
            parameters=[
                StrategyParameter(
                    name="timeframe",
                    display_name="Timeframe / Candle Interval",
                    description="Timeframe for Bollinger Bands analysis (e.g., 5min, 1hour, 1day)",
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
                    name="bb_period",
                    display_name="BB Period",
                    description="Number of periods for Bollinger Bands calculation",
                    type="int",
                    default=20,
                    min_value=5,
                    max_value=100,
                ),
                StrategyParameter(
                    name="bb_std_multiplier",
                    display_name="Standard Deviation Multiplier",
                    description="Number of standard deviations for band width",
                    type="float",
                    default=2.0,
                    min_value=1.0,
                    max_value=4.0,
                ),
                StrategyParameter(
                    name="buy_threshold",
                    display_name="Buy Threshold (%B)",
                    description="%B level below which to buy (oversold)",
                    type="float",
                    default=0.2,
                    min_value=0.0,
                    max_value=0.5,
                ),
                StrategyParameter(
                    name="sell_threshold",
                    display_name="Sell Threshold (%B)",
                    description="%B level above which to consider selling (overbought)",
                    type="float",
                    default=0.8,
                    min_value=0.5,
                    max_value=1.0,
                ),
                StrategyParameter(
                    name="buy_amount_percentage",
                    display_name="Buy Amount %",
                    description="Percentage of BTC balance to use per buy",
                    type="float",
                    default=15.0,
                    min_value=1.0,
                    max_value=50.0,
                ),
                StrategyParameter(
                    name="min_profit_percentage",
                    display_name="Min Profit %",
                    description="Minimum profit percentage required to sell",
                    type="float",
                    default=1.5,
                    min_value=0.1,
                    max_value=20.0,
                ),
                StrategyParameter(
                    name="max_position_size_btc",
                    display_name="Max Position Size (BTC)",
                    description="Maximum BTC to allocate to a single position",
                    type="float",
                    default=0.15,
                    min_value=0.001,
                    max_value=10.0,
                ),
            ],
            supported_products=["ETH-BTC", "BTC-USD", "ETH-USD", "SOL-USD"],
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

    async def analyze_signal(self, candles: List[Dict[str, Any]], current_price: float) -> Optional[Dict[str, Any]]:
        """
        Analyze Bollinger Bands and detect %B signals

        Returns:
            Dict with signal_type ("oversold" or "overbought"), %B value, bands, etc.
        """
        bb_period = int(self.config["bb_period"])
        std_multiplier = float(self.config["bb_std_multiplier"])

        if len(candles) < bb_period + 10:
            return None  # Need extra data for BB calculation

        # Extract close prices
        close_prices = [float(c["close"]) for c in candles]

        # Calculate Bollinger Bands
        middle, upper, lower, percent_b = calculate_bollinger_bands(close_prices, bb_period, std_multiplier)

        if len(percent_b) == 0:
            return None

        current_pb = percent_b[-1]
        buy_threshold = self.config["buy_threshold"]
        sell_threshold = self.config["sell_threshold"]

        signal_type = None
        if current_pb < buy_threshold:
            signal_type = "oversold"  # Buy signal
        elif current_pb > sell_threshold:
            signal_type = "overbought"  # Potential sell signal

        if signal_type:
            return {
                "signal_type": signal_type,
                "percent_b": current_pb,
                "middle_band": middle[-1],
                "upper_band": upper[-1],
                "lower_band": lower[-1],
                "price": current_price,
            }

        return None

    async def should_buy(
        self, signal_data: Dict[str, Any], position: Optional[Any], btc_balance: float
    ) -> Tuple[bool, float, str]:
        """
        Buy when %B indicates oversold

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

        pb = signal_data.get("percent_b", 0)
        lower_band = signal_data.get("lower_band", 0)
        return True, btc_to_spend, f"%B oversold ({pb:.3f}) near lower band ({lower_band:.8f})"

    async def should_sell(self, signal_data: Dict[str, Any], position: Any, current_price: float) -> Tuple[bool, str]:
        """
        Sell when %B indicates overbought AND profit target is met

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
            pb = signal_data.get("percent_b", 0)
            upper_band = signal_data.get("upper_band", 0)
            return (
                True,
                f"%B overbought ({pb:.3f}) near upper band ({upper_band:.8f}), profit {current_profit_pct:.2f}%",
            )
        else:
            return False, f"%B overbought but profit {current_profit_pct:.2f}% < target {min_profit}%"
