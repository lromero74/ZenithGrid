"""PnL calculation service — extracted from Position model."""


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
