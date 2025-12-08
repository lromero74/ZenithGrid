"""
Phase-Based Conditions (3Commas Style)

Supports advanced condition grouping with AND/OR/NOT logic:
- Groups can contain multiple conditions with internal AND/OR logic
- Groups are combined with AND/OR logic between them
- Individual conditions can be negated (NOT)

Example: (RSI < 30 AND MACD > 0) OR (BB% < 20) AND NOT (price_change > 5)
"""

from typing import Any, Dict, List, Optional, Union

from app.indicator_calculator import IndicatorCalculator


class PhaseConditionEvaluator:
    """
    Evaluates phase-based conditions with advanced grouping support.

    Supports two formats:
    1. Legacy flat format: { conditions: [...], logic: 'and'|'or' }
    2. New grouped format: { groups: [...], groupLogic: 'and'|'or' }
    """

    def __init__(self, indicator_calculator: IndicatorCalculator):
        self.indicator_calculator = indicator_calculator

    def evaluate_expression(
        self,
        expression: Union[Dict[str, Any], List[Dict[str, Any]]],
        current_indicators: Dict[str, Any],
        previous_indicators: Optional[Dict[str, Any]] = None,
        legacy_logic: str = "and",
    ) -> bool:
        """
        Evaluate a condition expression (supports both legacy and new format)

        Args:
            expression: Either:
                - New format: { groups: [...], groupLogic: 'and'|'or' }
                - Legacy format: List of condition dicts
            current_indicators: Current indicator values
            previous_indicators: Previous indicator values (for crossing)
            legacy_logic: Logic to use for legacy flat list format

        Returns:
            True if expression is satisfied, False otherwise
        """
        # Handle empty/None
        if not expression:
            return False

        # Check if new grouped format (dict with 'groups' key)
        if isinstance(expression, dict) and "groups" in expression:
            return self._evaluate_grouped_expression(expression, current_indicators, previous_indicators)

        # Legacy flat list format
        if isinstance(expression, list):
            return self.evaluate_phase_conditions(expression, legacy_logic, current_indicators, previous_indicators)

        # Unknown format
        print(f"[WARNING] Unknown expression format: {type(expression)}")
        return False

    def _evaluate_grouped_expression(
        self,
        expression: Dict[str, Any],
        current_indicators: Dict[str, Any],
        previous_indicators: Optional[Dict[str, Any]],
    ) -> bool:
        """
        Evaluate a grouped expression: { groups: [...], groupLogic: 'and'|'or' }

        Each group has: { id, conditions: [...], logic: 'and'|'or' }
        Groups are combined using groupLogic.
        """
        groups = expression.get("groups", [])
        group_logic = expression.get("groupLogic", "and")

        if not groups:
            return False

        group_results = []
        for group in groups:
            group_result = self._evaluate_group(group, current_indicators, previous_indicators)
            group_results.append(group_result)
            print(f"[DEBUG] Group {group.get('id', '?')} result: {group_result}")

        # Combine groups
        if group_logic == "and":
            final_result = all(group_results)
        else:  # 'or'
            final_result = any(group_results)

        print(f"[DEBUG] Final expression result ({group_logic.upper()} of {len(groups)} groups): {final_result}")
        return final_result

    def _evaluate_group(
        self,
        group: Dict[str, Any],
        current_indicators: Dict[str, Any],
        previous_indicators: Optional[Dict[str, Any]],
    ) -> bool:
        """
        Evaluate a single group of conditions

        Group format: { id, conditions: [...], logic: 'and'|'or' }
        """
        conditions = group.get("conditions", [])
        logic = group.get("logic", "and")

        if not conditions:
            return False

        results = []
        for condition in conditions:
            result = self._evaluate_single_condition(condition, current_indicators, previous_indicators)

            # Handle NOT (negate) modifier
            if condition.get("negate", False):
                print(f"[DEBUG] Negating condition result: {result} -> {not result}")
                result = not result

            results.append(result)

        if logic == "and":
            return all(results)
        else:  # 'or'
            return any(results)

    def evaluate_phase_conditions(
        self,
        conditions: List[Dict[str, Any]],
        logic: str,
        current_indicators: Dict[str, Any],
        previous_indicators: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Evaluate a flat list of phase conditions (legacy format)

        Args:
            conditions: List of phase condition dicts
            logic: 'and' or 'or'
            current_indicators: Current indicator values
            previous_indicators: Previous indicator values (for crossing)

        Returns:
            True if conditions are met, False otherwise
        """
        if not conditions:
            return False

        results = []
        for condition in conditions:
            result = self._evaluate_single_condition(condition, current_indicators, previous_indicators)

            # Handle NOT (negate) modifier
            if condition.get("negate", False):
                result = not result

            results.append(result)

        if logic == "and":
            return all(results)
        else:  # 'or'
            return any(results)

    def _evaluate_single_condition(
        self,
        condition: Dict[str, Any],
        current_indicators: Dict[str, Any],
        previous_indicators: Optional[Dict[str, Any]],
    ) -> bool:
        """Evaluate a single phase condition"""
        condition_type = condition.get("type")
        operator = condition.get("operator")
        value = condition.get("value", 0)
        timeframe = condition.get("timeframe", "FIVE_MINUTE")

        # Get current indicator value
        current_val = self._get_indicator_value(condition_type, condition, current_indicators)
        if current_val is None:
            print(f"[DEBUG] Condition {condition_type} on {timeframe}: indicator value is None")
            return False

        print(f"[DEBUG] Evaluating: {condition_type} on {timeframe}: {current_val} {operator} {value}")

        # Handle crossing operators
        if operator in ["crossing_above", "crossing_below"]:
            if previous_indicators is None:
                print("[DEBUG] Crossing check: no previous indicators available")
                return False

            previous_val = self._get_indicator_value(condition_type, condition, previous_indicators)
            if previous_val is None:
                print("[DEBUG] Crossing check: previous indicator value is None")
                return False

            print(f"[DEBUG] Crossing check: previous={previous_val}, current={current_val}, threshold={value}")

            if operator == "crossing_above":
                result = previous_val <= value and current_val > value
                print(
                    f"[DEBUG] Crossing above result: {result} (was {previous_val} <= {value} and now {current_val} > {value})"
                )
                return result
            else:  # crossing_below
                result = previous_val >= value and current_val < value
                print(
                    f"[DEBUG] Crossing below result: {result} (was {previous_val} >= {value} and now {current_val} < {value})"
                )
                return result

        # Handle simple comparisons
        result = False
        if operator == "greater_than":
            result = current_val > value
        elif operator == "less_than":
            result = current_val < value
        elif operator == "greater_equal":
            result = current_val >= value
        elif operator == "less_equal":
            result = current_val <= value

        print(f"[DEBUG] Result: {result}")
        return result

    def _get_indicator_value(
        self, condition_type: str, condition: Dict[str, Any], indicators: Dict[str, Any]
    ) -> Optional[float]:
        """Get indicator value from indicators dict, respecting timeframe"""
        timeframe = condition.get("timeframe", "FIVE_MINUTE")

        if condition_type == "rsi":
            period = condition.get("period", 14)
            return indicators.get(f"{timeframe}_rsi_{period}")

        elif condition_type == "macd":
            fast = condition.get("fast_period", 12)
            slow = condition.get("slow_period", 26)
            signal = condition.get("signal_period", 9)
            return indicators.get(f"{timeframe}_macd_histogram_{fast}_{slow}_{signal}")

        elif condition_type == "bb_percent":
            period = condition.get("period", 20)
            std_dev = condition.get("std_dev", 2)
            # Calculate BB% from price and bands
            price = indicators.get(f"{timeframe}_price")
            upper = indicators.get(f"{timeframe}_bb_upper_{period}_{std_dev}")
            lower = indicators.get(f"{timeframe}_bb_lower_{period}_{std_dev}")

            if price is None or upper is None or lower is None:
                return None

            if upper == lower:
                return 50.0

            # BB% = (price - lower) / (upper - lower) * 100
            return ((price - lower) / (upper - lower)) * 100

        elif condition_type == "ema_cross":
            period = condition.get("period", 50)
            price = indicators.get(f"{timeframe}_price")
            ema = indicators.get(f"{timeframe}_ema_{period}")

            # For crossing, we compare price to EMA
            # The value field is ignored, we just return price - EMA
            # so crossing_above/below can detect when price crosses EMA
            if price is None or ema is None:
                return None

            return price - ema

        elif condition_type == "sma_cross":
            period = condition.get("period", 50)
            price = indicators.get(f"{timeframe}_price")
            sma = indicators.get(f"{timeframe}_sma_{period}")

            if price is None or sma is None:
                return None

            return price - sma

        elif condition_type == "stochastic":
            period = condition.get("period", 14)
            return indicators.get(f"{timeframe}_stoch_k_{period}_3")

        elif condition_type == "price_change":
            # Calculate price change % from previous candle
            # This requires special handling - we'd need previous price
            # For now, return None (to be implemented if needed)
            return None

        elif condition_type == "volume":
            return indicators.get(f"{timeframe}_volume")

        return None

    def get_required_indicators_from_expression(
        self, expression: Union[Dict[str, Any], List[Dict[str, Any]]]
    ) -> set:
        """
        Extract required indicators from an expression (supports both formats)

        Args:
            expression: Either grouped format { groups: [...] } or flat list [...]

        Returns:
            Set of required indicator keys
        """
        # Handle empty/None
        if not expression:
            return set()

        # New grouped format
        if isinstance(expression, dict) and "groups" in expression:
            required = set()
            for group in expression.get("groups", []):
                conditions = group.get("conditions", [])
                required.update(self.get_required_indicators(conditions))
            return required

        # Legacy flat list format
        if isinstance(expression, list):
            return self.get_required_indicators(expression)

        return set()

    def get_required_indicators(self, conditions: List[Dict[str, Any]]) -> set:
        """Extract which indicators are needed from conditions, with timeframe"""
        required = set()

        for condition in conditions:
            condition_type = condition.get("type") or condition.get("indicator")
            timeframe = condition.get("timeframe", "FIVE_MINUTE")

            if condition_type == "rsi":
                period = condition.get("period", 14)
                required.add(f"{timeframe}_rsi_{period}")

            elif condition_type == "macd":
                fast = condition.get("fast_period", 12)
                slow = condition.get("slow_period", 26)
                signal = condition.get("signal_period", 9)
                required.add(f"{timeframe}_macd_{fast}_{slow}_{signal}")

            elif condition_type == "bb_percent":
                period = condition.get("period", 20)
                std_dev = condition.get("std_dev", 2)
                required.add(f"{timeframe}_bb_upper_{period}_{std_dev}")
                required.add(f"{timeframe}_price")

            elif condition_type in ["ema_cross", "ema"]:
                period = condition.get("period", 50)
                required.add(f"{timeframe}_ema_{period}")
                required.add(f"{timeframe}_price")

            elif condition_type in ["sma_cross", "sma"]:
                period = condition.get("period", 50)
                required.add(f"{timeframe}_sma_{period}")
                required.add(f"{timeframe}_price")

            elif condition_type == "stochastic":
                period = condition.get("period", 14)
                required.add(f"{timeframe}_stoch_k_{period}_3")

            elif condition_type == "volume":
                required.add(f"{timeframe}_volume")

            # Aggregate indicators (ai_buy, ai_sell, bull_flag) don't need
            # specific indicator values - they're evaluated separately

        return required
