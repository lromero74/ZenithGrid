"""
Slippage Guard — Order Book Depth Protection

Checks order book depth before market orders and blocks execution
if estimated slippage exceeds acceptable thresholds.

Buy side: walks ASK side, blocks if VWAP > max_buy_slippage_pct above best ask.
Sell side:
  - Minimum/Trailing mode: blocks if VWAP profit < take_profit_percentage (profit floor).
  - Fixed mode: blocks if VWAP > max_sell_slippage_pct below best bid.

Gracefully skips when book data is unavailable (paper trading, API errors).
"""

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def _fmt_price(price: float) -> str:
    """Format a price with enough decimals to be meaningful for any coin."""
    if price >= 1.0:
        return f"${price:.2f}"
    elif price >= 0.01:
        return f"${price:.4f}"
    elif price >= 0.0001:
        return f"${price:.6f}"
    else:
        return f"${price:.8f}"


def calculate_vwap_from_bids(
    bids: list, sell_amount: float
) -> Tuple[float, float, bool]:
    """
    Walk bid levels to calculate VWAP for selling `sell_amount` base currency.

    Args:
        bids: List of {"price": str, "size": str} dicts, highest price first.
        sell_amount: Amount of base currency to sell.

    Returns:
        (vwap, filled_amount, fully_filled)
        - vwap: Volume-weighted average price across filled levels.
        - filled_amount: Total base currency that could be filled.
        - fully_filled: Whether the entire sell_amount was filled.
    """
    if sell_amount <= 0 or not bids:
        return 0.0, 0.0, False

    remaining = sell_amount
    total_quote = 0.0
    total_base = 0.0

    for level in bids:
        price = float(level["price"])
        size = float(level["size"])

        if price <= 0 or size <= 0:
            continue

        fill = min(remaining, size)
        total_quote += fill * price
        total_base += fill
        remaining -= fill

        if remaining <= 0:
            break

    if total_base <= 0:
        return 0.0, 0.0, False

    vwap = total_quote / total_base
    fully_filled = remaining <= 1e-12  # float tolerance
    return vwap, total_base, fully_filled


def calculate_vwap_from_asks(
    asks: list, buy_quote_amount: float
) -> Tuple[float, float, bool]:
    """
    Walk ask levels to calculate VWAP for buying with `buy_quote_amount` quote currency.

    Args:
        asks: List of {"price": str, "size": str} dicts, lowest price first.
        buy_quote_amount: Amount of quote currency to spend.

    Returns:
        (vwap, filled_quote, fully_filled)
        - vwap: Volume-weighted average price across filled levels.
        - filled_quote: Total quote currency that could be spent.
        - fully_filled: Whether the entire buy_quote_amount was spent.
    """
    if buy_quote_amount <= 0 or not asks:
        return 0.0, 0.0, False

    remaining_quote = buy_quote_amount
    total_quote = 0.0
    total_base = 0.0

    for level in asks:
        price = float(level["price"])
        size = float(level["size"])

        if price <= 0 or size <= 0:
            continue

        level_quote = price * size  # Total quote available at this level
        spend = min(remaining_quote, level_quote)
        base_filled = spend / price

        total_quote += spend
        total_base += base_filled
        remaining_quote -= spend

        if remaining_quote <= 1e-12:
            break

    if total_base <= 0:
        return 0.0, 0.0, False

    vwap = total_quote / total_base
    fully_filled = remaining_quote <= 1e-12  # float tolerance
    return vwap, total_quote, fully_filled


async def check_sell_slippage(
    exchange: Any,
    product_id: str,
    position: Any,
    config: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Check order book depth before a market sell.

    Returns:
        (proceed, reason) — proceed=True means OK to sell, False means block.
    """
    if not hasattr(exchange, 'get_product_book'):
        return True, None

    try:
        book_data = await exchange.get_product_book(product_id)
    except Exception as e:
        logger.warning(f"Slippage guard: could not fetch book for {product_id}: {e}")
        return True, None

    pricebook = book_data.get("pricebook", book_data)
    bids = pricebook.get("bids", [])

    if not bids:
        logger.debug("Slippage guard: no bids in book, skipping check")
        return True, None

    sell_amount = position.total_base_acquired
    if not sell_amount or sell_amount <= 0:
        return True, None

    vwap, filled, fully_filled = calculate_vwap_from_bids(bids, sell_amount)

    if vwap <= 0:
        return True, None

    if not fully_filled:
        reason = (
            f"Insufficient book depth: only {filled:.8f} of {sell_amount:.8f}"
            f" base fillable at VWAP {_fmt_price(vwap)}"
        )
        logger.warning(f"Slippage guard BLOCKED sell: {reason}")
        return False, reason

    best_bid = float(bids[0]["price"])

    # Determine TP mode
    take_profit_mode = config.get("take_profit_mode")
    if take_profit_mode is None:
        if config.get("trailing_take_profit", False):
            take_profit_mode = "trailing"
        elif config.get("min_profit_for_conditions") is not None:
            take_profit_mode = "minimum"
        else:
            take_profit_mode = "fixed"

    if take_profit_mode in ("minimum", "trailing"):
        # Minimum/Trailing: TP% is the profit floor — check VWAP profit directly
        tp_pct = config.get("take_profit_percentage") or 3.0
        avg_price = position.average_buy_price
        if avg_price and avg_price > 0:
            vwap_profit_pct = ((vwap - avg_price) / avg_price) * 100
            if vwap_profit_pct < tp_pct:
                reason = (
                    f"VWAP profit {vwap_profit_pct:.2f}% < TP floor {tp_pct}%"
                    f" (VWAP {_fmt_price(vwap)} vs avg {_fmt_price(avg_price)})"
                )
                logger.warning(f"Slippage guard BLOCKED sell: {reason}")
                return False, reason
    else:
        # Fixed mode: check raw slippage below best bid
        max_sell_slip = config.get("max_sell_slippage_pct") or 0.5
        if best_bid > 0:
            slip_pct = ((best_bid - vwap) / best_bid) * 100
            if slip_pct > max_sell_slip:
                reason = (
                    f"Sell slippage {slip_pct:.2f}% > max {max_sell_slip}%"
                    f" (VWAP {_fmt_price(vwap)} vs best bid {_fmt_price(best_bid)})"
                )
                logger.warning(f"Slippage guard BLOCKED sell: {reason}")
                return False, reason

    return True, None


async def check_buy_slippage(
    exchange: Any,
    product_id: str,
    quote_amount: float,
    config: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Check order book depth before a market buy.

    Returns:
        (proceed, reason) — proceed=True means OK to buy, False means block.
    """
    if not hasattr(exchange, 'get_product_book'):
        return True, None

    try:
        book_data = await exchange.get_product_book(product_id)
    except Exception as e:
        logger.warning(f"Slippage guard: could not fetch book for {product_id}: {e}")
        return True, None

    pricebook = book_data.get("pricebook", book_data)
    asks = pricebook.get("asks", [])

    if not asks:
        logger.debug("Slippage guard: no asks in book, skipping check")
        return True, None

    if not quote_amount or quote_amount <= 0:
        return True, None

    vwap, filled_quote, fully_filled = calculate_vwap_from_asks(asks, quote_amount)

    if vwap <= 0:
        return True, None

    if not fully_filled:
        reason = (
            f"Insufficient book depth: only {_fmt_price(filled_quote)} of"
            f" {_fmt_price(quote_amount)} fillable at VWAP {_fmt_price(vwap)}"
        )
        logger.warning(f"Slippage guard BLOCKED buy: {reason}")
        return False, reason

    best_ask = float(asks[0]["price"])
    max_buy_slip = config.get("max_buy_slippage_pct", 0.5)

    if best_ask > 0:
        slip_pct = ((vwap - best_ask) / best_ask) * 100
        if slip_pct > max_buy_slip:
            reason = (
                f"Buy slippage {slip_pct:.2f}% > max {max_buy_slip}%"
                f" (VWAP {_fmt_price(vwap)} vs best ask {_fmt_price(best_ask)})"
            )
            logger.warning(f"Slippage guard BLOCKED buy: {reason}")
            return False, reason

    return True, None
