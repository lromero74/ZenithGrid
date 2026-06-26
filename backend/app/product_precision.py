"""
Product precision specifications from Coinbase API.

Each trading pair has specific increment requirements for quote and base amounts.
This module provides a lookup system to ensure orders meet Coinbase's precision requirements.

Missing products are fetched from the Coinbase public API on demand by
ensure_product_precision() and written back to product_precision.json so future
calls are served from the file without a network round-trip.
"""

import json
import logging
import os
from decimal import ROUND_DOWN, Decimal
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Cache for precision data
_PRECISION_CACHE: Optional[Dict] = None


def get_precision_data() -> Dict:
    """Load precision data from JSON file (cached).

    Prefers the runtime cache (product_precision.json, gitignored, mutated by
    ensure_product_precision) and falls back to the tracked baseline
    (product_precision.seed.json) so fresh clones aren't empty before the first
    auto-fetch writes the runtime file.
    """
    global _PRECISION_CACHE

    if _PRECISION_CACHE is not None:
        return _PRECISION_CACHE

    base_dir = os.path.dirname(__file__)
    for filename in ("product_precision.json", "product_precision.seed.json"):
        path = os.path.join(base_dir, filename)
        if os.path.exists(path):
            with open(path, "r") as f:
                _PRECISION_CACHE = json.load(f)
                return _PRECISION_CACHE

    # Fallback: return empty dict (will use default precision)
    _PRECISION_CACHE = {}
    return _PRECISION_CACHE


def get_quote_precision(product_id: str) -> int:
    """
    Get the required decimal precision for quote currency in a trading pair.

    Args:
        product_id: Trading pair (e.g., "DASH-BTC", "ETH-USD")

    Returns:
        Number of decimal places required for quote amounts

    Examples:
        >>> get_quote_precision("DASH-BTC")
        6  # DASH-BTC requires 6 decimal places
        >>> get_quote_precision("ETH-USD")
        2  # USD always uses 2 decimal places
    """
    # Get quote currency from product_id
    if "-" in product_id:
        _, quote_currency = product_id.split("-")
    else:
        quote_currency = "BTC"  # fallback

    # USD always uses 2 decimals
    if quote_currency == "USD":
        return 2

    # Look up precision from cached data
    precision_data = get_precision_data()

    if product_id in precision_data:
        return precision_data[product_id].get("quote_decimals", 8)

    # Default fallback for BTC pairs (conservative)
    if quote_currency == "BTC":
        return 6  # Most BTC pairs use 6 or fewer decimals

    # Default for other crypto
    return 8


def get_base_precision(product_id: str) -> int:
    """
    Get the required decimal precision for base currency in a trading pair.

    Args:
        product_id: Trading pair (e.g., "DASH-BTC", "ETH-USD")

    Returns:
        Number of decimal places required for base amounts

    Examples:
        >>> get_base_precision("XLM-BTC")
        0  # base_increment="1" means whole numbers only
        >>> get_base_precision("DASH-BTC")
        3  # base_increment="0.001"
    """
    precision_data = get_precision_data()

    if product_id in precision_data:
        base_inc = precision_data[product_id].get("base_increment", "")
        if base_inc:
            if "." in base_inc:
                return len(base_inc.split(".")[1].rstrip("0"))
            else:
                # No decimal point (e.g., "1") means 0 decimal places (whole numbers only)
                return 0

    # Default: 8 decimals for crypto
    return 8


def format_quote_amount_for_product(amount: float, product_id: str) -> str:
    """
    Format a quote amount with the correct precision for a specific product.

    Args:
        amount: The amount to format
        product_id: Trading pair (e.g., "DASH-BTC")

    Returns:
        Properly formatted string with correct precision

    Examples:
        >>> format_quote_amount_for_product(0.00010174, "DASH-BTC")
        '0.00010200'  # Rounded to 6 decimals, formatted to 8
        >>> format_quote_amount_for_product(0.00010174, "ETH-BTC")
        '0.00010000'  # Rounded to 5 decimals, formatted to 8
    """
    precision = get_quote_precision(product_id)

    # Quantize DOWN to the required precision — never round up (rounding a size up can
    # exceed the wallet balance and trigger INSUFFICIENT_FUND / invalid-precision rejects).
    rounded = Decimal(str(amount)).quantize(Decimal(1).scaleb(-precision), rounding=ROUND_DOWN)

    # Format with 8 decimal places (standard for crypto display)
    # This pads with trailing zeros if needed
    return f"{rounded:.8f}"


async def ensure_product_precision(product_id: str) -> None:
    """
    If product_id is missing from product_precision.json, fetch its increment
    data from the Coinbase public API and persist it so future calls are fast.

    Safe to call from async sell/buy paths. No-op if already in the cache.
    """
    precision_data = get_precision_data()
    if product_id in precision_data:
        return  # Already known

    try:
        from app.coinbase_api.public_market_data import get_product as _fetch_product
        product = await _fetch_product(product_id)
        base_inc = product.get("base_increment", "")
        quote_inc = product.get("quote_increment", "")
        if not base_inc:
            logger.warning("ensure_product_precision: no base_increment for %s", product_id)
            return

        def _count_decimals(inc: str) -> int:
            if "." in inc:
                return len(inc.split(".")[1].rstrip("0")) or 0
            return 0

        entry = {
            "quote_increment": quote_inc,
            "quote_decimals": _count_decimals(quote_inc),
            "base_increment": base_inc,
        }
        precision_data[product_id] = entry
        logger.info(
            "ensure_product_precision: fetched %s base_increment=%s quote_increment=%s",
            product_id, base_inc, quote_inc,
        )

        # Persist back to JSON so restarts don't need to re-fetch
        json_path = os.path.join(os.path.dirname(__file__), "product_precision.json")
        try:
            with open(json_path, "w") as f:
                json.dump(precision_data, f, indent=2)
        except OSError as e:
            logger.warning("ensure_product_precision: could not write JSON: %s", e)

    except Exception as e:
        logger.warning("ensure_product_precision: failed for %s: %s", product_id, e)


def format_base_amount_for_product(amount: float, product_id: str) -> str:
    """
    Format a base amount with the correct precision for a specific product.

    Args:
        amount: The amount to format
        product_id: Trading pair (e.g., "DASH-BTC")

    Returns:
        Properly formatted string with correct precision
    """
    precision = get_base_precision(product_id)

    # Quantize DOWN to the required precision — never round up (rounding a size up can
    # exceed the wallet balance and trigger INSUFFICIENT_FUND / invalid-precision rejects).
    rounded = Decimal(str(amount)).quantize(Decimal(1).scaleb(-precision), rounding=ROUND_DOWN)

    # Format with 8 decimal places (standard for crypto display)
    return f"{rounded:.8f}"
