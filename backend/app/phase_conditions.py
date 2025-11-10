"""
Phase-Based Conditions (3Commas Style)

Simpler condition system with three phases:
1. Base Order Entry - when to open initial position
2. Safety Order Entry - when to add to position
3. Take Profit - when to close position

Each phase has simple conditions without deep nesting.
"""

from typing import Dict, Any, List, Optional
from app.indicator_calculator import IndicatorCalculator


class PhaseConditionEvaluator:
    """
    Evaluates phase-based conditions (3Commas style)

    Much simpler than nested ConditionGroups - just a list of conditions
    with AND/OR logic at the phase level.
    """

    def __init__(self, indicator_calculator: IndicatorCalculator):
        self.indicator_calculator = indicator_calculator

    def evaluate_phase_conditions(
        self,
        conditions: List[Dict[str, Any]],
        logic: str,
        current_indicators: Dict[str, Any],
        previous_indicators: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Evaluate a list of phase conditions

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
            result = self._evaluate_single_condition(
                condition,
                current_indicators,
                previous_indicators
            )
            results.append(result)

        if logic == 'and':
            return all(results)
        else:  # 'or'
            return any(results)

    def _evaluate_single_condition(
        self,
        condition: Dict[str, Any],
        current_indicators: Dict[str, Any],
        previous_indicators: Optional[Dict[str, Any]]
    ) -> bool:
        """Evaluate a single phase condition"""
        condition_type = condition.get('type')
        operator = condition.get('operator')
        value = condition.get('value', 0)

        # Get current indicator value
        current_val = self._get_indicator_value(condition_type, condition, current_indicators)
        if current_val is None:
            return False

        # Handle crossing operators
        if operator in ['crossing_above', 'crossing_below']:
            if previous_indicators is None:
                return False

            previous_val = self._get_indicator_value(condition_type, condition, previous_indicators)
            if previous_val is None:
                return False

            if operator == 'crossing_above':
                return previous_val <= value and current_val > value
            else:  # crossing_below
                return previous_val >= value and current_val < value

        # Handle simple comparisons
        if operator == 'greater_than':
            return current_val > value
        elif operator == 'less_than':
            return current_val < value
        elif operator == 'greater_equal':
            return current_val >= value
        elif operator == 'less_equal':
            return current_val <= value

        return False

    def _get_indicator_value(
        self,
        condition_type: str,
        condition: Dict[str, Any],
        indicators: Dict[str, Any]
    ) -> Optional[float]:
        """Get indicator value from indicators dict"""
        if condition_type == 'rsi':
            period = condition.get('period', 14)
            return indicators.get(f'rsi_{period}')

        elif condition_type == 'macd':
            fast = condition.get('fast_period', 12)
            slow = condition.get('slow_period', 26)
            signal = condition.get('signal_period', 9)
            return indicators.get(f'macd_histogram_{fast}_{slow}_{signal}')

        elif condition_type == 'bb_percent':
            period = condition.get('period', 20)
            std_dev = condition.get('std_dev', 2)
            # Calculate BB% from price and bands
            price = indicators.get('price')
            upper = indicators.get(f'bb_upper_{period}_{std_dev}')
            lower = indicators.get(f'bb_lower_{period}_{std_dev}')

            if price is None or upper is None or lower is None:
                return None

            if upper == lower:
                return 50.0

            # BB% = (price - lower) / (upper - lower) * 100
            return ((price - lower) / (upper - lower)) * 100

        elif condition_type == 'ema_cross':
            period = condition.get('period', 50)
            price = indicators.get('price')
            ema = indicators.get(f'ema_{period}')

            # For crossing, we compare price to EMA
            # The value field is ignored, we just return price - EMA
            # so crossing_above/below can detect when price crosses EMA
            if price is None or ema is None:
                return None

            return price - ema

        elif condition_type == 'sma_cross':
            period = condition.get('period', 50)
            price = indicators.get('price')
            sma = indicators.get(f'sma_{period}')

            if price is None or sma is None:
                return None

            return price - sma

        elif condition_type == 'stochastic':
            period = condition.get('period', 14)
            return indicators.get(f'stoch_k_{period}_3')

        elif condition_type == 'price_change':
            # Calculate price change % from previous candle
            # This requires special handling - we'd need previous price
            # For now, return None (to be implemented if needed)
            return None

        elif condition_type == 'volume':
            return indicators.get('volume')

        return None

    def get_required_indicators(self, conditions: List[Dict[str, Any]]) -> set:
        """Extract which indicators are needed from conditions"""
        required = set()

        for condition in conditions:
            condition_type = condition.get('type')

            if condition_type == 'rsi':
                period = condition.get('period', 14)
                required.add(f'rsi_{period}')

            elif condition_type == 'macd':
                fast = condition.get('fast_period', 12)
                slow = condition.get('slow_period', 26)
                signal = condition.get('signal_period', 9)
                required.add(f'macd_{fast}_{slow}_{signal}')

            elif condition_type == 'bb_percent':
                period = condition.get('period', 20)
                std_dev = condition.get('std_dev', 2)
                required.add(f'bb_upper_{period}_{std_dev}')
                required.add('price')

            elif condition_type in ['ema_cross', 'ema']:
                period = condition.get('period', 50)
                required.add(f'ema_{period}')
                required.add('price')

            elif condition_type in ['sma_cross', 'sma']:
                period = condition.get('period', 50)
                required.add(f'sma_{period}')
                required.add('price')

            elif condition_type == 'stochastic':
                period = condition.get('period', 14)
                required.add(f'stoch_k_{period}_3')

            elif condition_type == 'volume':
                required.add('volume')

        return required
