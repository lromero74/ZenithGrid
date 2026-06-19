"""PnL calculation service — extracted from Position model."""


def calculate_realized_spot_profit(
    total_quote_spent: float,
    total_quote_received: float,
    entry_fees_quote: float = 0.0,
    exit_fees_quote: float = 0.0,
) -> tuple[float, float]:
    """Return fee-net realized spot profit and percentage in quote currency."""
    cost_basis = total_quote_spent + entry_fees_quote
    net_proceeds = total_quote_received - exit_fees_quote
    profit_quote = net_proceeds - cost_basis
    profit_pct = (profit_quote / cost_basis) * 100 if cost_basis > 0 else 0.0
    return profit_quote, profit_pct


def calculate_profit(position, current_price: float) -> dict:
    """
    Calculate P&L for long/short positions.

    Args:
        position: Position object (or any object with the required attributes)
        current_price: Current market price

    Returns:
        Dict with profit_quote, profit_pct, unrealized_value
    """
    if position.direction == "long":
        unrealized_value = position.total_base_acquired * current_price
        profit_quote = unrealized_value - position.total_quote_spent
        profit_pct = (profit_quote / position.total_quote_spent) * 100 if position.total_quote_spent > 0 else 0.0
    else:
        cost_to_cover = (position.short_total_sold_base or 0.0) * current_price
        profit_quote = (position.short_total_sold_quote or 0.0) - cost_to_cover
        profit_pct = (profit_quote / (position.short_total_sold_quote or 1.0)) * 100
        unrealized_value = cost_to_cover

    return {
        "profit_quote": profit_quote,
        "profit_pct": profit_pct,
        "unrealized_value": unrealized_value,
    }
