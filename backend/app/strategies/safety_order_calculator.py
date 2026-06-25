"""
Safety Order Calculator — pure math for DCA order sizing.

Extracted from indicator_based.py to keep file sizes manageable.
These functions compute order sizes based on config values only (no ORM, no I/O).
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)


def effective_max_safety_orders(config: Dict) -> int:
    """Placement ceiling for safety orders = configured count + grace bonus.

    ``max_safety_orders`` is the budgeted count (drives sizing/soft-ceiling/budget — see
    ``get_total_multiplier`` / ``calculate_*_budget``). ``grace_safety_orders`` adds bonus
    SOs that fire only after the configured ones are spent; grace is NEVER part of any
    up-front budget/sizing calc. This helper is the single source for the *limit* used at
    the placement gate and cascade, so every limit site agrees. (Grace expands a deal's
    budget just-in-time when it actually crosses into grace — see _shared.py — exactly
    like manually bumping Max Safety Orders.)
    """
    configured = int(config.get("max_safety_orders", 0) or 0)
    grace = int(config.get("grace_safety_orders", 0) or 0)
    return configured + max(0, grace)


def get_total_multiplier(config: Dict) -> float:
    """Calculate the total multiplier for a full DCA cycle (base + all safety orders).

    Example: If base is 1.0 and SO is 0.5 of base with 2 SOs, total multiplier is 1.0 + 0.5 + 0.5 = 2.0.
    Accounting for volume scaling using the same geometric series logic as calculate_base_order_size.
    """
    max_safety_orders = config.get("max_safety_orders", 0)
    if max_safety_orders <= 0:
        return 1.0

    volume_scale = config.get("safety_order_volume_scale", 1.0)
    safety_order_type = config.get("safety_order_type", "percentage_of_base")

    if safety_order_type == "percentage_of_base":
        so_percentage = config.get("safety_order_percentage", 50.0) / 100.0
        # Geometric series sum: 1 + so_pct * (v^0 + v^1 + ... + v^(n-1))
        if volume_scale == 1.0:
            return 1.0 + so_percentage * max_safety_orders
        else:
            return 1.0 + so_percentage * (volume_scale ** max_safety_orders - 1) / (volume_scale - 1)

    elif safety_order_type in ["fixed", "fixed_btc"]:
        # If auto_calculate is on, SO = Base. Otherwise it's fixed.
        # But for the purpose of a soft ceiling multiplier, we assume auto-calculate
        # style scaling (where SO is derived from base) to find the ratio.
        # Base (1.0) + SO1 (1.0) + SO2..SOn (geometric)
        total = 2.0
        n = max_safety_orders
        if n > 1:
            if volume_scale == 1.0:
                total += (n - 1)
            else:
                total += volume_scale * (volume_scale ** (n - 1) - 1) / (volume_scale - 1)
        return total

    return 1.0 + (max_safety_orders * 0.5)  # Fallback


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
        # Auto-calculated percentage base orders divide the budget by the full-cycle
        # multiplier (base + all safety orders) so the base + every SO fits the budget.
        # Only the percentage_of_base safety type takes this path; a fixed safety type
        # falls through to the flat base_order_percentage below.
        if (
            auto_calculate
            and max_safety_orders > 0
            and config.get("safety_order_type", "percentage_of_base") == "percentage_of_base"
        ):
            total_multiplier = get_total_multiplier(config)
            if total_multiplier > 0:
                return balance / total_multiplier
            # Degenerate config (non-positive multiplier): fall through to flat % below
            # rather than divide by zero (CLAUDE.md rule 13 — never Infinity).

        percentage = config.get("base_order_percentage", 10.0)
        return balance * (percentage / 100.0)

    elif order_type in ["fixed", "fixed_btc"]:
        if auto_calculate and max_safety_orders > 0 and balance > 0:
            # Both safety types divide the budget by the full-cycle multiplier; the
            # series is defined once in get_total_multiplier.
            total_multiplier = get_total_multiplier(config)
            if total_multiplier > 0:
                return balance / total_multiplier
            # Degenerate config: floor to the whole budget rather than divide by zero.
            return balance
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


def count_deployed_safety_orders(entry_trades) -> int:
    """Count safety-order LEVELS deployed across a position's entry trades.

    A cascade fills several SO levels in a SINGLE trade (its ``dca_levels`` > 1),
    so counting trade rows (``len(entry_trades) - 1``) under-reports completed
    safety orders and lets the engine re-place an already-deployed level. This
    sums ``dca_levels`` and subtracts the one base order, which is identical to
    ``len - 1`` when every trade is a single level and correct for cascades.

    Legacy/unset ``dca_levels`` counts as one level.
    """
    total_levels = sum(int(getattr(t, "dca_levels", 1) or 1) for t in entry_trades)
    return max(0, total_levels - 1)


def entry_trades_for_position(position) -> list:
    """Trades that ADD to a position, for its direction: buys for a long, sells
    for a short. Excludes the opposite side (a short's closing buys, a long's
    take-profit sells) so the safety-order count is correct in both directions —
    counting only buys leaves a short stuck at 0 safety orders.
    """
    trades = getattr(position, "trades", None) or []
    entry_side = "sell" if getattr(position, "direction", "long") == "short" else "buy"
    return [t for t in trades if t.side == entry_side]
