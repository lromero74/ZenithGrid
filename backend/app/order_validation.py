"""
Order validation utilities for Coinbase API

Ensures orders meet minimum size requirements before submission.
"""

import json
import logging
import os
from decimal import Decimal
from typing import Dict, Optional, Tuple

from app.cache import api_cache

logger = logging.getLogger(__name__)

# Load product precision data from JSON file
_PRODUCT_PRECISION = None


def _load_product_precision():
    """Load product precision data from product_precision.json"""
    global _PRODUCT_PRECISION
    if _PRODUCT_PRECISION is None:
        precision_file = os.path.join(os.path.dirname(__file__), "product_precision.json")
        try:
            with open(precision_file, "r") as f:
                _PRODUCT_PRECISION = json.load(f)
                logger.info(f"Loaded precision data for {len(_PRODUCT_PRECISION)} products")
        except Exception as e:
            logger.error(f"Failed to load product_precision.json: {e}")
            _PRODUCT_PRECISION = {}
    return _PRODUCT_PRECISION


# Common minimum order sizes for BTC pairs (fallback if API call fails)
# Based on Coinbase documentation and empirical testing
DEFAULT_MINIMUMS = {
    "BTC": {
        "quote_min_size": "0.0001",  # 0.0001 BTC minimum (~$10 at $100k/BTC)
        "base_min_size": "0.00000001",  # 1 satoshi
    },
    "USD": {"quote_min_size": "1.00", "base_min_size": "0.00000001"},  # $1 minimum
}


async def get_product_minimums(coinbase_client, product_id: str) -> Dict[str, str]:
    """
    Get minimum order sizes for a product

    Args:
        coinbase_client: Coinbase API client
        product_id: Trading pair (e.g., "DASH-BTC")

    Returns:
        Dict with quote_min_size and base_min_size
    """
    # Check cache first
    cache_key = f"product_minimums_{product_id}"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        # Load product precision from our JSON file (more reliable than Coinbase API)
        precision_data = _load_product_precision()
        product_precision = precision_data.get(product_id, {})

        # Fetch product details from Coinbase (for quote/base currency info)
        product = await coinbase_client.get_product(product_id)

        # Use our precision table values (they're more reliable than Coinbase's API)
        minimums = {
            "quote_min_size": product.get("quote_min_size", "0.0001"),
            "base_min_size": product.get("base_min_size", "0.00000001"),
            "quote_currency": product.get("quote_currency", "BTC"),
            "base_currency": product.get("base_currency", ""),
            # CRITICAL: Use our precision table instead of Coinbase API (which returns None)
            "quote_increment": product_precision.get("quote_increment", product.get("quote_increment", "0.00000001")),
            "base_increment": product_precision.get("base_increment", product.get("base_increment", "0.00000001")),
        }

        logger.info(f"Product {product_id} precision: base_increment={minimums['base_increment']}, quote_increment={minimums['quote_increment']}")

        # Cache for 1 hour (product minimums rarely change)
        await api_cache.set(cache_key, minimums, ttl_seconds=3600)

        return minimums

    except Exception as e:
        logger.warning(f"Failed to fetch product minimums for {product_id}: {e}")

        # Use defaults based on quote currency
        quote_currency = product_id.split("-")[1] if "-" in product_id else "BTC"
        return DEFAULT_MINIMUMS.get(quote_currency, DEFAULT_MINIMUMS["BTC"])


async def validate_order_size(
    coinbase_client, product_id: str, quote_amount: Optional[float] = None, base_amount: Optional[float] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate if an order meets minimum size requirements

    Args:
        coinbase_client: Coinbase API client
        product_id: Trading pair (e.g., "DASH-BTC")
        quote_amount: Amount of quote currency (BTC/USD)
        base_amount: Amount of base currency (DASH/ETH)

    Returns:
        Tuple of (is_valid, error_message)
        - (True, None) if valid
        - (False, "error message") if invalid
    """
    minimums = await get_product_minimums(coinbase_client, product_id)

    quote_min = Decimal(minimums["quote_min_size"])
    base_min = Decimal(minimums["base_min_size"])
    quote_currency = minimums["quote_currency"]

    # Validate quote amount if provided
    if quote_amount is not None:
        quote_decimal = Decimal(str(quote_amount))
        if quote_decimal < quote_min:
            return (
                False,
                f"Order size {quote_amount} {quote_currency} is below minimum {quote_min} {quote_currency} for {product_id}",
            )

    # Validate base amount if provided
    if base_amount is not None:
        base_decimal = Decimal(str(base_amount))
        if base_decimal < base_min:
            base_currency = minimums["base_currency"]
            return (
                False,
                f"Order size {base_amount} {base_currency} is below minimum {base_min} {base_currency} for {product_id}",
            )

    return (True, None)


async def calculate_minimum_budget_percentage(coinbase_client, product_id: str, quote_balance: float) -> float:
    """
    Calculate minimum budget percentage needed to meet order minimums

    Args:
        coinbase_client: Coinbase API client
        product_id: Trading pair (e.g., "DASH-BTC")
        quote_balance: Available quote currency balance

    Returns:
        Minimum percentage (e.g., 0.5 for 0.5%)
    """
    if quote_balance <= 0:
        return 100.0  # Cannot calculate if no balance

    minimums = await get_product_minimums(coinbase_client, product_id)
    quote_min = Decimal(minimums["quote_min_size"])

    # Calculate what percentage of balance equals the minimum
    min_percentage = (float(quote_min) / quote_balance) * 100

    # Round up to nearest 0.1%
    min_percentage = round(min_percentage * 10) / 10

    return min_percentage
