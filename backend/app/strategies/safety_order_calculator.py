"""
Safety Order Calculator — pure math for DCA order sizing.

Extracted from indicator_based.py to keep file sizes manageable.
These functions compute order sizes based on config values only (no ORM, no I/O).
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


def calculate_base_order_size(config: Dict, balance: float) -> float:
    """Calculate base order size based on configuration.

    Note: The 'balance' passed in is already the per-position budget (accounting for
    split_budget_across_pairs if enabled). The strategy just applies the percentage
    to whatever budget it receives - no need to divide by max_concurrent_deals here.

    For fixed orders with safety orders enabled, this auto-calculates the base order
    size that fits within the budget after accounting for all safety orders (working
    backwards from total budget to determine optimal base order size).
    """
    order_type = config.get("base_order_type", "percentage")
    max_safety_orders = config.get("max_safety_orders", 0)
    auto_calculate = config.get("auto_calculate_order_sizes", False)

    if order_type == "percentage":
        if auto_calculate and max_safety_orders > 0:
            total_multiplier = 1.0  # Base order

            safety_order_type = config.get("safety_order_type", "percentage_of_base")
            volume_scale = config.get("safety_order_volume_scale", 1.0)

            if safety_order_type == "percentage_of_base":
                so_percentage = config.get("safety_order_percentage", 50.0) / 100.0
                for order_num in range(1, max_safety_orders + 1):
                    scaled_multiplier = so_percentage * (volume_scale ** (order_num - 1))
                    total_multiplier += scaled_multiplier

                optimal_percentage = 100.0 / total_multiplier
                return balance * (optimal_percentage / 100.0)

        percentage = config.get("base_order_percentage", 10.0)
        return balance * (percentage / 100.0)

    elif order_type in ["fixed", "fixed_btc"]:
        if config.get("auto_calculate_order_sizes", False) and max_safety_orders > 0 and balance > 0:
            safety_order_type = config.get("safety_order_type", "percentage_of_base")

            if safety_order_type in ["fixed", "fixed_btc"]:
                volume_scale = config.get("safety_order_volume_scale", 1.0)
                total_multiplier = 1.0  # Base order = X
                total_multiplier += 1.0  # SO1 = X (same as base)
                for order_num in range(2, max_safety_orders + 1):
                    scaled_multiplier = volume_scale ** (order_num - 1)
                    total_multiplier += scaled_multiplier
                return balance / total_multiplier
            else:
                total_multiplier = 1.0
                volume_scale = config.get("safety_order_volume_scale", 1.0)
                for order_num in range(1, max_safety_orders + 1):
                    so_multiplier = config.get("safety_order_percentage", 50.0) / 100.0
                    scaled_multiplier = so_multiplier * (volume_scale ** (order_num - 1))
                    total_multiplier += scaled_multiplier
                return balance / total_multiplier
        else:
            base_order_btc = config.get("base_order_btc", 0.0001)
            base_order_fixed = config.get("base_order_fixed", 0.001)
            if order_type == "fixed_btc" or (base_order_btc != 0.0001 and base_order_btc < base_order_fixed):
                return base_order_btc
            else:
                return base_order_fixed
    else:
        return config.get("base_order_fixed", 0.001)


def calculate_safety_order_size(config: Dict, base_order_size: float, order_number: int) -> float:
    """Calculate safety order size with volume scaling."""
    order_type = config.get("safety_order_type", "percentage_of_base")

    if order_type == "percentage_of_base":
        base_safety_size = base_order_size * (config.get("safety_order_percentage", 50.0) / 100.0)
    elif order_type in ["fixed", "fixed_btc"]:
        if config.get("auto_calculate_order_sizes", False):
            base_safety_size = base_order_size
        else:
            base_safety_size = config.get("safety_order_btc", 0.0001)
    else:
        base_safety_size = config.get("safety_order_fixed", 0.0005)

    volume_scale = config.get("safety_order_volume_scale", 1.0)
    return base_safety_size * (volume_scale ** (order_number - 1))
