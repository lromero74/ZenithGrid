"""PnL calculation service — extracted from Position model."""

import logging

from app.constants import FALLBACK_BTC_USD_PRICE

logger = logging.getLogger(__name__)


def resolve_btc_usd_price(position) -> float:
    """Return the BTC/USD price to convert a position's USD P&L into BTC.

    Prefers the price stored at close, then at open. Only when a closed BTC-pair
    position recorded neither does this fall back to the fixed
    ``FALLBACK_BTC_USD_PRICE`` — and logs a warning, because that path silently
    distorts BTC-denominated P&L and should be rare for real positions.
    Single source of truth for the fallback (CLAUDE.md rule 13).
    """
    price = getattr(position, "btc_usd_price_at_close", None) \
        or getattr(position, "btc_usd_price_at_open", None)
    if price and price > 0:
        return price
    logger.warning(
        "No stored BTC/USD price for position %s; using fallback %.1f for BTC P&L conversion",
        getattr(position, "id", "?"), FALLBACK_BTC_USD_PRICE,
    )
    return FALLBACK_BTC_USD_PRICE


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


def calculate_realized_short_profit(
    total_quote_received: float,
    total_quote_spent_to_cover: float,
    entry_fees_quote: float = 0.0,
    exit_fees_quote: float = 0.0,
) -> tuple[float, float]:
    """Return fee-net realized short profit and percentage in quote currency."""
    net_entry_proceeds = total_quote_received - entry_fees_quote
    total_cover_cost = total_quote_spent_to_cover + exit_fees_quote
    profit_quote = net_entry_proceeds - total_cover_cost
    profit_pct = (profit_quote / net_entry_proceeds) * 100 if net_entry_proceeds > 0 else 0.0
    return profit_quote, profit_pct


# Fallback round-trip taker-fee rate (fraction of notional, per leg) used only when
# a position never recorded an entry fee (pre-fee-tracking history). Real positions
# self-calibrate from the fee they actually paid, so this default is rarely hit.
DEFAULT_TAKER_FEE_RATE = 0.006  # 0.6% — Coinbase low-volume taker tier


def position_exit_fee_rate(position, fallback: float = DEFAULT_TAKER_FEE_RATE) -> float:
    """Estimated per-leg fee rate (fraction) for a position, calibrated from the
    entry leg it actually paid: ``entry_fees_quote / total_quote_spent``.

    The bot pays the same taker tier on both legs, so the entry rate is the best
    available estimate for the not-yet-paid exit fee. Falls back to the default
    taker rate when the position has no recorded entry fee (legacy positions).
    """
    spent = float(getattr(position, "total_quote_spent", 0.0) or 0.0)
    if spent <= 0:
        # Shorts never set total_quote_spent — their entry notional is the quote
        # received from the opening short-sell. Without this, every short fell
        # through to the flat fallback rate, skewing its fee-adjusted TP floor.
        spent = float(getattr(position, "short_total_sold_quote", 0.0) or 0.0)
    entry_fee = float(getattr(position, "entry_fees_quote", 0.0) or 0.0)
    if spent > 0 and entry_fee > 0:
        return entry_fee / spent
    return fallback


def fee_adjusted_tp_floor(position, target_pct: float,
                          fallback_fee_rate: float = DEFAULT_TAKER_FEE_RATE) -> float:
    """Gross profit-% a position must reach so that, AFTER round-trip fees, the
    realized net profit is at least ``target_pct``.

    Every take-profit gate compares a *gross* profit% (value-vs-cost, fees never
    subtracted) to the configured ``take_profit_percentage``. That let a target
    trigger a sell whose net was below target — even a loss — once entry+exit fees
    were paid. This inflates the threshold by the position's own fee drag so the
    configured target is honored on a NET basis. Returns ``target_pct`` unchanged
    for a degenerate (>=100%) fee rate so we never divide by <= 0.
    """
    f = position_exit_fee_rate(position, fallback_fee_rate)
    if not (0.0 <= f < 1.0):
        return target_pct
    t = target_pct / 100.0
    return ((1.0 + f) * (1.0 + t) / (1.0 - f) - 1.0) * 100.0


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
