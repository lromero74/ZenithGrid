"""
Flexible Condition Framework (3Commas-style)

Allows mixing and matching indicators with comparison operators:
- Greater than (>)
- Less than (<)
- Greater than or equal (>=)
- Less than or equal (<=)
- Equal (==)
- Crossing above (crosses up)
- Crossing below (crosses down)

Conditions can be combined with AND/OR logic.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ComparisonOperator(str, Enum):
    """Comparison operators for conditions"""

    GREATER_THAN = "greater_than"  # >
    LESS_THAN = "less_than"  # <
    GREATER_EQUAL = "greater_equal"  # >=
    LESS_EQUAL = "less_equal"  # <=
    EQUAL = "equal"  # ==
    CROSSING_ABOVE = "crossing_above"  # Crosses from below to above
    CROSSING_BELOW = "crossing_below"  # Crosses from above to below


class IndicatorType(str, Enum):
    """Available indicators for conditions"""

    # Traditional indicators
    RSI = "rsi"
    MACD = "macd"
    MACD_SIGNAL = "macd_signal"
    MACD_HISTOGRAM = "macd_histogram"
    EMA = "ema"
    SMA = "sma"
    PRICE = "price"
    BOLLINGER_UPPER = "bollinger_upper"
    BOLLINGER_MIDDLE = "bollinger_middle"
    BOLLINGER_LOWER = "bollinger_lower"
    STOCHASTIC_K = "stochastic_k"
    STOCHASTIC_D = "stochastic_d"
    VOLUME = "volume"

    # Aggregate indicators (return 0 or 1)
    AI_BUY = "ai_buy"  # Multi-timeframe confluence buy signal
    AI_SELL = "ai_sell"  # Multi-timeframe confluence sell signal
    BULL_FLAG = "bull_flag"  # Bull flag pattern detection


class LogicOperator(str, Enum):
    """Logic operators for combining conditions"""

    AND = "and"
    OR = "or"


class Condition(BaseModel):
    """
    A single condition to evaluate

    Examples:
    - RSI < 30
    - MACD crossing above signal
    - Price > EMA(20)
    - Bollinger Lower crossing below Price
    """

    id: str = Field(default_factory=lambda: f"cond_{id(object())}")
    indicator: IndicatorType
    operator: ComparisonOperator
    value_type: str = "static"  # "static" or "indicator"
    static_value: Optional[float] = None  # For comparisons like "RSI < 30"
    compare_indicator: Optional[IndicatorType] = None  # For indicator vs indicator

    # Indicator parameters
    indicator_params: Dict[str, Any] = Field(default_factory=dict)  # e.g., {"period": 14} for RSI
    compare_indicator_params: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class ConditionGroup(BaseModel):
    """
    Group of conditions with AND/OR logic

    Examples:
    - (RSI < 30 AND MACD crossing above signal)
    - (RSI < 30 OR Stochastic K < 20)
    - Nested: ((RSI < 30 AND MACD > signal) OR (Price < Bollinger Lower))
    """

    id: str = Field(default_factory=lambda: f"group_{id(object())}")
    logic: LogicOperator = LogicOperator.AND
    conditions: List[Condition] = Field(default_factory=list)
    sub_groups: List["ConditionGroup"] = Field(default_factory=list)

    class Config:
        use_enum_values = True


class ConditionEvaluator:
    """
    Evaluates conditions against market data

    Handles:
    - Static comparisons (RSI > 30)
    - Indicator comparisons (MACD > signal)
    - Crossing detection (MACD crossing above signal)
    - Nested condition groups with AND/OR logic
    """

    def __init__(self, indicator_calculator):
        """
        Args:
            indicator_calculator: Instance of IndicatorCalculator for computing indicators
        """
        self.indicator_calculator = indicator_calculator

    def evaluate_condition(
        self,
        condition: Condition,
        current_indicators: Dict[str, Any],
        previous_indicators: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Evaluate a single condition

        Args:
            condition: Condition to evaluate
            current_indicators: Current indicator values
            previous_indicators: Previous indicator values (for crossing detection)

        Returns:
            True if condition is met, False otherwise
        """
        # Get current value of the indicator
        current_value = self._get_indicator_value(condition.indicator, condition.indicator_params, current_indicators)

        if current_value is None:
            return False

        # Get comparison value
        if condition.value_type == "static":
            compare_value = condition.static_value
        else:  # indicator comparison
            compare_value = self._get_indicator_value(
                condition.compare_indicator, condition.compare_indicator_params, current_indicators
            )

        if compare_value is None:
            return False

        # Handle crossing operators (need previous values)
        if condition.operator in [ComparisonOperator.CROSSING_ABOVE, ComparisonOperator.CROSSING_BELOW]:
            if previous_indicators is None:
                return False

            previous_value = self._get_indicator_value(
                condition.indicator, condition.indicator_params, previous_indicators
            )

            if previous_value is None:
                return False

            if condition.value_type == "indicator":
                previous_compare = self._get_indicator_value(
                    condition.compare_indicator, condition.compare_indicator_params, previous_indicators
                )
                if previous_compare is None:
                    return False
            else:
                previous_compare = compare_value  # Static value doesn't change

            # Crossing above: was below, now above
            if condition.operator == ComparisonOperator.CROSSING_ABOVE:
                return previous_value <= previous_compare and current_value > compare_value

            # Crossing below: was above, now below
            if condition.operator == ComparisonOperator.CROSSING_BELOW:
                return previous_value >= previous_compare and current_value < compare_value

        # Handle simple comparison operators
        if condition.operator == ComparisonOperator.GREATER_THAN:
            return current_value > compare_value
        elif condition.operator == ComparisonOperator.LESS_THAN:
            return current_value < compare_value
        elif condition.operator == ComparisonOperator.GREATER_EQUAL:
            return current_value >= compare_value
        elif condition.operator == ComparisonOperator.LESS_EQUAL:
            return current_value <= compare_value
        elif condition.operator == ComparisonOperator.EQUAL:
            return abs(current_value - compare_value) < 1e-9  # Float comparison

        return False

    def evaluate_group(
        self,
        group: ConditionGroup,
        current_indicators: Dict[str, Any],
        previous_indicators: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Evaluate a condition group (with AND/OR logic)

        Args:
            group: ConditionGroup to evaluate
            current_indicators: Current indicator values
            previous_indicators: Previous indicator values

        Returns:
            True if group conditions are met, False otherwise
        """
        results = []

        # Evaluate all conditions
        for condition in group.conditions:
            result = self.evaluate_condition(condition, current_indicators, previous_indicators)
            results.append(result)

        # Evaluate all sub-groups
        for sub_group in group.sub_groups:
            result = self.evaluate_group(sub_group, current_indicators, previous_indicators)
            results.append(result)

        # Combine results with logic operator
        if not results:
            return False

        if group.logic == LogicOperator.AND:
            return all(results)
        else:  # OR
            return any(results)

    def _get_indicator_value(
        self, indicator_type: IndicatorType, params: Dict[str, Any], indicators: Dict[str, Any]
    ) -> Optional[float]:
        """
        Extract indicator value from indicators dict

        Args:
            indicator_type: Type of indicator
            params: Indicator parameters (e.g., period)
            indicators: Dictionary of calculated indicators

        Returns:
            Indicator value or None if not available
        """
        # Get the key for this indicator with parameters
        if indicator_type == IndicatorType.PRICE:
            return indicators.get("price")

        if indicator_type == IndicatorType.RSI:
            period = params.get("period", 14)
            return indicators.get(f"rsi_{period}")

        if indicator_type == IndicatorType.MACD:
            fast = params.get("fast_period", 12)
            slow = params.get("slow_period", 26)
            signal = params.get("signal_period", 9)
            return indicators.get(f"macd_{fast}_{slow}_{signal}")

        if indicator_type == IndicatorType.MACD_SIGNAL:
            fast = params.get("fast_period", 12)
            slow = params.get("slow_period", 26)
            signal = params.get("signal_period", 9)
            return indicators.get(f"macd_signal_{fast}_{slow}_{signal}")

        if indicator_type == IndicatorType.MACD_HISTOGRAM:
            fast = params.get("fast_period", 12)
            slow = params.get("slow_period", 26)
            signal = params.get("signal_period", 9)
            return indicators.get(f"macd_histogram_{fast}_{slow}_{signal}")

        if indicator_type == IndicatorType.SMA:
            period = params.get("period", 20)
            return indicators.get(f"sma_{period}")

        if indicator_type == IndicatorType.EMA:
            period = params.get("period", 20)
            return indicators.get(f"ema_{period}")

        if indicator_type == IndicatorType.BOLLINGER_UPPER:
            period = params.get("period", 20)
            std_dev = params.get("std_dev", 2)
            return indicators.get(f"bb_upper_{period}_{std_dev}")

        if indicator_type == IndicatorType.BOLLINGER_MIDDLE:
            period = params.get("period", 20)
            std_dev = params.get("std_dev", 2)
            return indicators.get(f"bb_middle_{period}_{std_dev}")

        if indicator_type == IndicatorType.BOLLINGER_LOWER:
            period = params.get("period", 20)
            std_dev = params.get("std_dev", 2)
            return indicators.get(f"bb_lower_{period}_{std_dev}")

        if indicator_type == IndicatorType.STOCHASTIC_K:
            k_period = params.get("k_period", 14)
            d_period = params.get("d_period", 3)
            return indicators.get(f"stoch_k_{k_period}_{d_period}")

        if indicator_type == IndicatorType.STOCHASTIC_D:
            k_period = params.get("k_period", 14)
            d_period = params.get("d_period", 3)
            return indicators.get(f"stoch_d_{k_period}_{d_period}")

        if indicator_type == IndicatorType.VOLUME:
            return indicators.get("volume")

        # Aggregate indicators (return 0 or 1)
        if indicator_type == IndicatorType.AI_BUY:
            # AI_BUY is pre-calculated and stored in indicators dict
            return indicators.get("ai_buy")

        if indicator_type == IndicatorType.AI_SELL:
            # AI_SELL is pre-calculated and stored in indicators dict
            return indicators.get("ai_sell")

        if indicator_type == IndicatorType.BULL_FLAG:
            # BULL_FLAG is pre-calculated and stored in indicators dict
            return indicators.get("bull_flag")

        return None
