"""
Indicator Calculator for Condition-Based Strategies

Calculates all technical indicators from candle data and returns
a standardized dictionary that the ConditionEvaluator can use.

Supports:
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- SMA (Simple Moving Average)
- EMA (Exponential Moving Average)
- Bollinger Bands
- Stochastic Oscillator
- Volume
"""

import math
from typing import Any, Dict, List, Set


class IndicatorCalculator:
    """
    Calculates technical indicators from candle data

    Returns standardized dictionary with keys like:
    - "price": current price
    - "rsi_14": RSI with period 14
    - "macd_12_26_9": MACD line
    - "sma_20": SMA with period 20
    etc.
    """

    def __init__(self):
        """Initialize the calculator"""
        pass

    def calculate_all_indicators(
        self,
        candles: List[Dict[str, Any]],
        required_indicators: Set[str]
    ) -> Dict[str, float]:
        """
        Calculate all required indicators from candle data

        Args:
            candles: List of candle dictionaries with OHLCV data
            required_indicators: Set of indicator keys needed (e.g., {"rsi_14", "macd_12_26_9"})

        Returns:
            Dictionary of indicator values
        """
        if not candles:
            return {}

        indicators = {}

        # Always include current price
        indicators["price"] = float(candles[-1]["close"])
        indicators["volume"] = float(candles[-1]["volume"])

        # Extract price arrays
        closes = [float(c["close"]) for c in candles]
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        _volumes = [float(c["volume"]) for c in candles]  # Reserved for future volume-based indicators

        # Calculate indicators based on what's required
        for indicator_key in required_indicators:
            if indicator_key.startswith("rsi_"):
                period = int(indicator_key.split("_")[1])
                value = self.calculate_rsi(closes, period)
                if value is not None:
                    indicators[indicator_key] = value

            elif indicator_key.startswith("macd_"):
                parts = indicator_key.split("_")
                if len(parts) >= 4:
                    fast = int(parts[1])
                    slow = int(parts[2])
                    signal_period = int(parts[3])
                    macd_line, signal_line, histogram = self.calculate_macd(
                        closes, fast, slow, signal_period
                    )
                    if macd_line is not None:
                        indicators[f"macd_{fast}_{slow}_{signal_period}"] = macd_line
                        indicators[f"macd_signal_{fast}_{slow}_{signal_period}"] = signal_line
                        indicators[f"macd_histogram_{fast}_{slow}_{signal_period}"] = histogram

            elif indicator_key.startswith("sma_"):
                period = int(indicator_key.split("_")[1])
                value = self.calculate_sma(closes, period)
                if value is not None:
                    indicators[indicator_key] = value

            elif indicator_key.startswith("ema_"):
                period = int(indicator_key.split("_")[1])
                value = self.calculate_ema(closes, period)
                if value is not None:
                    indicators[indicator_key] = value

            elif indicator_key.startswith("bb_"):
                # bb_upper_20_2, bb_middle_20_2, bb_lower_20_2
                parts = indicator_key.split("_")
                if len(parts) >= 4:
                    _band_type = parts[1]  # upper, middle, lower (parsed but not used - returns all bands)
                    period = int(parts[2])
                    std_dev = float(parts[3])
                    upper, middle, lower = self.calculate_bollinger_bands(
                        closes, period, std_dev
                    )
                    if upper is not None:
                        indicators[f"bb_upper_{period}_{std_dev}"] = upper
                        indicators[f"bb_middle_{period}_{std_dev}"] = middle
                        indicators[f"bb_lower_{period}_{std_dev}"] = lower

            elif indicator_key.startswith("stoch_"):
                # stoch_k_14_3, stoch_d_14_3
                parts = indicator_key.split("_")
                if len(parts) >= 4:
                    _line_type = parts[1]  # k or d (parsed but not used - returns both k and d)
                    k_period = int(parts[2])
                    d_period = int(parts[3])
                    k_value, d_value = self.calculate_stochastic(
                        highs, lows, closes, k_period, d_period
                    )
                    if k_value is not None:
                        indicators[f"stoch_k_{k_period}_{d_period}"] = k_value
                        indicators[f"stoch_d_{k_period}_{d_period}"] = d_value

        return indicators

    def calculate_rsi(self, prices: List[float], period: int = 14) -> float | None:
        """Calculate RSI (Relative Strength Index)"""
        if len(prices) < period + 1:
            return None

        # Calculate price changes
        changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]

        gains = [change if change > 0 else 0 for change in changes]
        losses = [-change if change < 0 else 0 for change in changes]

        # Initial average gain/loss
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Smooth using Wilder's method
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_sma(self, prices: List[float], period: int) -> float | None:
        """Calculate SMA (Simple Moving Average)"""
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period

    def calculate_ema(self, prices: List[float], period: int) -> float | None:
        """Calculate EMA (Exponential Moving Average)"""
        if len(prices) < period:
            return None

        multiplier = 2 / (period + 1)

        # Start with SMA for initial value
        ema = sum(prices[:period]) / period

        # Calculate EMA for remaining values
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    def calculate_macd(
        self,
        prices: List[float],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> tuple[float | None, float | None, float | None]:
        """
        Calculate MACD (Moving Average Convergence Divergence)

        Returns:
            (macd_line, signal_line, histogram)
        """
        if len(prices) < slow_period + signal_period:
            return None, None, None

        # Calculate fast and slow EMAs
        fast_ema = self.calculate_ema(prices, fast_period)
        slow_ema = self.calculate_ema(prices, slow_period)

        if fast_ema is None or slow_ema is None:
            return None, None, None

        macd_line = fast_ema - slow_ema

        # Calculate MACD values for signal line calculation
        macd_values = []
        temp_prices = prices[:]
        for i in range(slow_period, len(prices) + 1):
            f_ema = self.calculate_ema(temp_prices[:i], fast_period)
            s_ema = self.calculate_ema(temp_prices[:i], slow_period)
            if f_ema is not None and s_ema is not None:
                macd_values.append(f_ema - s_ema)

        # Signal line is EMA of MACD line
        if len(macd_values) < signal_period:
            return macd_line, None, None

        signal_line = self.calculate_ema(macd_values, signal_period)

        if signal_line is None:
            return macd_line, None, None

        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    def calculate_bollinger_bands(
        self,
        prices: List[float],
        period: int = 20,
        std_dev: float = 2.0
    ) -> tuple[float | None, float | None, float | None]:
        """
        Calculate Bollinger Bands

        Returns:
            (upper_band, middle_band, lower_band)
        """
        if len(prices) < period:
            return None, None, None

        middle_band = self.calculate_sma(prices, period)

        if middle_band is None:
            return None, None, None

        # Calculate standard deviation
        recent_prices = prices[-period:]
        variance = sum((p - middle_band) ** 2 for p in recent_prices) / period
        std = math.sqrt(variance)

        upper_band = middle_band + (std_dev * std)
        lower_band = middle_band - (std_dev * std)

        return upper_band, middle_band, lower_band

    def calculate_stochastic(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        k_period: int = 14,
        d_period: int = 3
    ) -> tuple[float | None, float | None]:
        """
        Calculate Stochastic Oscillator

        Returns:
            (k_value, d_value)
        """
        if len(closes) < k_period:
            return None, None

        # Calculate %K
        recent_highs = highs[-k_period:]
        recent_lows = lows[-k_period:]
        current_close = closes[-1]

        highest_high = max(recent_highs)
        lowest_low = min(recent_lows)

        if highest_high == lowest_low:
            k_value = 50.0
        else:
            k_value = ((current_close - lowest_low) / (highest_high - lowest_low)) * 100

        # Calculate %D (SMA of %K)
        # Need to calculate K for last d_period candles
        k_values = []
        for i in range(max(k_period, len(closes) - d_period), len(closes)):
            if i < k_period:
                continue
            period_highs = highs[i - k_period:i]
            period_lows = lows[i - k_period:i]
            period_close = closes[i]

            h_high = max(period_highs)
            l_low = min(period_lows)

            if h_high == l_low:
                k_values.append(50.0)
            else:
                k_val = ((period_close - l_low) / (h_high - l_low)) * 100
                k_values.append(k_val)

        if len(k_values) < d_period:
            return k_value, None

        d_value = sum(k_values[-d_period:]) / d_period

        return k_value, d_value

    def extract_required_indicators(self, conditions_config: Dict[str, Any]) -> Set[str]:
        """
        Extract which indicators need to be calculated from conditions config

        Args:
            conditions_config: Dictionary containing condition groups

        Returns:
            Set of indicator keys needed
        """
        required = set()

        def process_group(group: Dict[str, Any]):
            # Process conditions
            for condition in group.get("conditions", []):
                required.add(self._get_indicator_key(condition))

                # If comparing to another indicator
                if condition.get("value_type") == "indicator":
                    compare_condition = {
                        "indicator": condition.get("compare_indicator"),
                        "indicator_params": condition.get("compare_indicator_params", {})
                    }
                    required.add(self._get_indicator_key(compare_condition))

            # Process sub-groups recursively
            for sub_group in group.get("sub_groups", []):
                process_group(sub_group)

        # Process buy and sell conditions
        if "buy_conditions" in conditions_config:
            process_group(conditions_config["buy_conditions"])
        if "sell_conditions" in conditions_config:
            process_group(conditions_config["sell_conditions"])

        return required

    def _get_indicator_key(self, condition: Dict[str, Any]) -> str:
        """Generate indicator key from condition"""
        indicator = condition.get("indicator")
        params = condition.get("indicator_params", {})

        if indicator == "price":
            return "price"
        elif indicator == "volume":
            return "volume"
        elif indicator == "rsi":
            period = params.get("period", 14)
            return f"rsi_{period}"
        elif indicator in ["macd", "macd_signal", "macd_histogram"]:
            fast = params.get("fast_period", 12)
            slow = params.get("slow_period", 26)
            signal = params.get("signal_period", 9)
            return f"macd_{fast}_{slow}_{signal}"
        elif indicator == "sma":
            period = params.get("period", 20)
            return f"sma_{period}"
        elif indicator == "ema":
            period = params.get("period", 20)
            return f"ema_{period}"
        elif indicator in ["bollinger_upper", "bollinger_middle", "bollinger_lower"]:
            period = params.get("period", 20)
            std_dev = params.get("std_dev", 2)
            return f"bb_upper_{period}_{std_dev}"  # Will calculate all 3 bands
        elif indicator in ["stochastic_k", "stochastic_d"]:
            k_period = params.get("k_period", 14)
            d_period = params.get("d_period", 3)
            return f"stoch_k_{k_period}_{d_period}"  # Will calculate both K and D

        return "unknown"
