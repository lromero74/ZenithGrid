"""
Shared helpers for position routers.

Functions used by multiple position sub-routers live here to avoid
cross-router imports.
"""

from typing import Optional

from app.models import Bot, Position
from app.trading_engine.position_manager import (
    calculate_expected_position_budget,
    calculate_max_deal_cost,
)


def compute_resize_budget(position: Position, bot: Optional[Bot]) -> float:
    """Compute the true max deal cost for a position from its config and trades."""
    config = position.strategy_config_snapshot or (bot.strategy_config if bot else {}) or {}

    # Try calculate_expected_position_budget first (works for fixed order configs)
    expected = calculate_expected_position_budget(config, 0)
    if expected > 0:
        return expected

    # Fallback: derive from position's first buy trade
    base_order_size = 0.0
    if position.trades:
        buy_trades = sorted(
            [t for t in position.trades if t.side == "buy"],
            key=lambda t: t.timestamp,
        )
        if buy_trades:
            base_order_size = buy_trades[0].quote_amount or 0.0

    # If still no base order size, try config values
    if base_order_size <= 0:
        base_order_size = config.get("base_order_btc", 0.0) or config.get("base_order_fixed", 0.0)

    if base_order_size <= 0:
        return 0.0

    return calculate_max_deal_cost(config, base_order_size)
