"""
Condition Mirroring Logic for Bidirectional DCA Grid Bots

Automatically mirrors long entry/exit conditions to create short conditions.
Example: "RSI crosses above 30" (long) becomes "RSI crosses below 70" (short)
"""

from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class ConditionMirror:
    """
    Auto-generates mirrored short conditions from long conditions.

    Mirroring Rules:
    - Operators: crossing_above <-> crossing_below, greater_than <-> less_than
    - Values:
      - RSI/Stochastic: 30 <-> 70 (mirror around 50)
      - BB%: 10 <-> 90 (mirror around 50)
      - MACD: > 0 <-> < 0 (flip sign)
    - Negate flag: NOT preserved (double negative = positive)
    """

    # Operator mirroring map
    OPERATOR_MIRRORS = {
        "crossing_above": "crossing_below",
        "crossing_below": "crossing_above",
        "greater_than": "less_than",
        "less_than": "greater_than",
        "greater_than_or_equal": "less_than_or_equal",
        "less_than_or_equal": "greater_than_or_equal",
    }

    @staticmethod
    def mirror_condition(long_condition: Dict) -> Dict:
        """
        Create mirrored short condition from long condition.

        Args:
            long_condition: Long entry/exit condition dict

        Returns:
            Mirrored short condition dict
        """
        short_condition = long_condition.copy()

        # Mirror operator if applicable
        operator = long_condition.get("operator", "")
        if operator in ConditionMirror.OPERATOR_MIRRORS:
            short_condition["operator"] = ConditionMirror.OPERATOR_MIRRORS[operator]

        # Mirror value based on indicator type
        indicator_type = long_condition.get("type", "")
        original_value = long_condition.get("value", 0)

        if indicator_type in ["rsi", "stochastic"]:
            # RSI/Stochastic: Mirror around 50 (30 -> 70, 20 -> 80, etc.)
            short_condition["value"] = 100 - original_value
            logger.debug(
                f"Mirrored {indicator_type} value: {original_value} -> {short_condition['value']}"
            )

        elif indicator_type == "bb_percent":
            # Bollinger Band %: Mirror around 50 (10 -> 90, 20 -> 80, etc.)
            short_condition["value"] = 100 - original_value
            logger.debug(
                f"Mirrored BB% value: {original_value} -> {short_condition['value']}"
            )

        elif indicator_type in ["macd", "macd_signal", "macd_histogram"]:
            # MACD: Flip sign (positive <-> negative)
            short_condition["value"] = -original_value
            logger.debug(
                f"Mirrored {indicator_type} value: {original_value} -> {short_condition['value']}"
            )

        # For other indicators (price, volume, etc.), keep value unchanged
        # The operator mirroring is usually sufficient

        # Tag with direction
        short_condition["direction"] = "short"

        return short_condition

    @staticmethod
    def mirror_condition_group(long_group: List[Dict]) -> List[Dict]:
        """
        Mirror entire condition group (preserves AND/OR/NOT logic).

        Args:
            long_group: List of long conditions (with AND/OR combinators)

        Returns:
            List of mirrored short conditions
        """
        mirrored_group = []

        for condition in long_group:
            mirrored = ConditionMirror.mirror_condition(condition)
            mirrored_group.append(mirrored)

        logger.info(
            f"Mirrored condition group: {len(long_group)} long conditions -> {len(mirrored_group)} short conditions"
        )

        return mirrored_group

    @staticmethod
    def get_bidirectional_conditions(
        strategy_config: Dict, auto_mirror: bool = True
    ) -> Dict[str, List[Dict]]:
        """
        Get both long and short conditions from strategy config.

        Args:
            strategy_config: Bot's strategy configuration
            auto_mirror: If True, auto-generate short conditions from long conditions

        Returns:
            Dict with "long" and "short" condition lists
        """
        # Get long conditions
        long_base_conditions = strategy_config.get("base_order_conditions", [])
        long_tp_conditions = strategy_config.get("take_profit_conditions", [])

        # Get or generate short conditions
        if auto_mirror:
            # Auto-mirror long conditions to create short conditions
            short_base_conditions = ConditionMirror.mirror_condition_group(
                long_base_conditions
            )
            short_tp_conditions = ConditionMirror.mirror_condition_group(
                long_tp_conditions
            )

            logger.info(
                "Auto-mirrored conditions: "
                f"{len(long_base_conditions)} long base -> {len(short_base_conditions)} short base, "
                f"{len(long_tp_conditions)} long TP -> {len(short_tp_conditions)} short TP"
            )

        else:
            # Use manually configured short conditions
            short_base_conditions = strategy_config.get("short_base_order_conditions", [])
            short_tp_conditions = strategy_config.get("short_take_profit_conditions", [])

            logger.info(
                f"Using manual short conditions: "
                f"{len(short_base_conditions)} base, {len(short_tp_conditions)} TP"
            )

        return {
            "long": {
                "base_order_conditions": long_base_conditions,
                "take_profit_conditions": long_tp_conditions,
            },
            "short": {
                "base_order_conditions": short_base_conditions,
                "take_profit_conditions": short_tp_conditions,
            },
        }


# Example usage and testing
if __name__ == "__main__":
    # Test RSI condition mirroring
    long_rsi_condition = {
        "type": "rsi",
        "operator": "crossing_above",
        "value": 30,
    }

    short_rsi_condition = ConditionMirror.mirror_condition(long_rsi_condition)
    print(f"Long RSI: {long_rsi_condition}")
    print(f"Short RSI: {short_rsi_condition}")
    # Expected: crossing_below with value 70

    # Test BB% condition mirroring
    long_bb_condition = {
        "type": "bb_percent",
        "operator": "less_than",
        "value": 10,
    }

    short_bb_condition = ConditionMirror.mirror_condition(long_bb_condition)
    print(f"\nLong BB%: {long_bb_condition}")
    print(f"Short BB%: {short_bb_condition}")
    # Expected: greater_than with value 90

    # Test MACD condition mirroring
    long_macd_condition = {
        "type": "macd",
        "operator": "greater_than",
        "value": 0,
    }

    short_macd_condition = ConditionMirror.mirror_condition(long_macd_condition)
    print(f"\nLong MACD: {long_macd_condition}")
    print(f"Short MACD: {short_macd_condition}")
    # Expected: less_than with value 0 (flipped sign)
