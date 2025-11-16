"""
Currency utilities for multi-quote-currency support

Handles detection and formatting for both BTC and USD quote currencies.
"""

from typing import Optional, Tuple


def get_currencies_from_pair(product_id: str) -> Tuple[str, str]:
    """
    Extract base and quote currencies from product_id

    Args:
        product_id: Trading pair like "ETH-BTC" or "ADA-USD"

    Returns:
        Tuple of (base_currency, quote_currency)
        Example: "ETH-BTC" -> ("ETH", "BTC")
                 "ADA-USD" -> ("ADA", "USD")
    """
    if '-' in product_id:
        parts = product_id.split('-')
        return (parts[0], parts[1])
    return ("ETH", "BTC")  # Default fallback


def get_quote_currency(product_id: str) -> str:
    """
    Get just the quote currency from product_id

    Args:
        product_id: Trading pair like "ETH-BTC" or "ADA-USD"

    Returns:
        Quote currency string ("BTC" or "USD")
    """
    _, quote = get_currencies_from_pair(product_id)
    return quote


def get_base_currency(product_id: str) -> str:
    """
    Get just the base currency from product_id

    Args:
        product_id: Trading pair like "ETH-BTC" or "ADA-USD"

    Returns:
        Base currency string ("ETH", "ADA", etc.)
    """
    base, _ = get_currencies_from_pair(product_id)
    return base


def format_quote_amount(amount: float, product_id: str) -> str:
    """
    Format quote currency amount with correct precision and symbol

    Args:
        amount: Amount in quote currency
        product_id: Trading pair to determine currency type

    Returns:
        Formatted string like "0.00057000 BTC" or "15.42 USD"
    """
    quote = get_quote_currency(product_id)

    if quote == "USD":
        return f"${amount:.2f}"
    else:  # BTC or other crypto
        return f"{amount:.8f} {quote}"


def format_base_amount(amount: float, product_id: str) -> str:
    """
    Format base currency amount with correct precision

    Args:
        amount: Amount in base currency
        product_id: Trading pair to determine currency type

    Returns:
        Formatted string like "0.12345678 ETH"
    """
    base = get_base_currency(product_id)
    return f"{amount:.8f} {base}"


def format_price(price: float, product_id: str) -> str:
    """
    Format price with correct precision based on quote currency

    Args:
        price: Price (base/quote)
        product_id: Trading pair

    Returns:
        Formatted price string
    """
    quote = get_quote_currency(product_id)

    if quote == "USD":
        return f"${price:.2f}"
    else:  # BTC or other crypto
        return f"{price:.8f} {quote}"


def format_with_usd(quote_amount: float, product_id: str, btc_usd_price: Optional[float] = None) -> str:
    """
    Format quote amount with USD equivalent for logging

    Args:
        quote_amount: Amount in quote currency
        product_id: Trading pair
        btc_usd_price: Current BTC/USD price (only needed for BTC pairs)

    Returns:
        Formatted string like "0.00057000 BTC ($54.15 USD)" or "$15.42 USD"
    """
    quote = get_quote_currency(product_id)

    if quote == "USD":
        return f"${quote_amount:.2f}"

    # For BTC pairs, show BTC amount with USD equivalent if available
    quote_str = f"{quote_amount:.8f} {quote}"
    if btc_usd_price and quote == "BTC":
        usd_value = quote_amount * btc_usd_price
        return f"{quote_str} (${usd_value:.2f} USD)"

    return quote_str


def get_quote_decimals(product_id: str) -> int:
    """
    Get the number of decimal places to use for quote currency

    Args:
        product_id: Trading pair

    Returns:
        Number of decimal places (2 for USD, 8 for crypto)
    """
    quote = get_quote_currency(product_id)
    return 2 if quote == "USD" else 8


def get_base_decimals(product_id: str) -> int:
    """
    Get the number of decimal places to use for base currency

    Args:
        product_id: Trading pair

    Returns:
        Number of decimal places (always 8 for crypto)
    """
    return 8
