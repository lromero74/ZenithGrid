"""
Product precision specifications from Coinbase API.

Each trading pair has specific increment requirements for quote and base amounts.
This module provides a lookup system to ensure orders meet Coinbase's precision requirements.
"""

import json
import os
from typing import Dict, Optional

# Cache for precision data
_PRECISION_CACHE: Optional[Dict] = None


def get_precision_data() -> Dict:
    """Load precision data from JSON file (cached)."""
    global _PRECISION_CACHE

    if _PRECISION_CACHE is not None:
        return _PRECISION_CACHE

    # Try to load from file
    json_path = os.path.join(os.path.dirname(__file__), "product_precision.json")
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
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
    """
    precision_data = get_precision_data()

    if product_id in precision_data:
        base_inc = precision_data[product_id].get("base_increment", "")
        if base_inc and "." in base_inc:
            return len(base_inc.split(".")[1].rstrip("0"))

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

    # Round to required precision
    rounded = round(float(amount), precision)

    # Format with 8 decimal places (standard for crypto display)
    # This pads with trailing zeros if needed
    return f"{rounded:.8f}"


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

    # Round to required precision
    rounded = round(float(amount), precision)

    # Format with 8 decimal places (standard for crypto display)
    return f"{rounded:.8f}"
