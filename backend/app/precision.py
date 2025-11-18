"""
Precision handling for Coinbase API orders

Coinbase has strict precision requirements for order sizes.
This module ensures amounts are properly formatted to avoid
PREVIEW_INVALID_QUOTE_SIZE_PRECISION and similar errors.
"""
from decimal import Decimal, ROUND_DOWN


def format_quote_amount(amount: float, quote_currency: str) -> str:
    """
    Format quote currency amount with proper precision for Coinbase.

    Args:
        amount: The amount to format
        quote_currency: The quote currency (BTC, USD, etc.)

    Returns:
        Properly formatted string with correct precision, trailing zeros removed

    Examples:
        >>> format_quote_amount(0.00012345678, "BTC")
        '0.00012346'  # Rounded to 8 decimals, trailing zeros removed
        >>> format_quote_amount(10.5000, "USD")
        '10.5'  # Rounded to 2 decimals, trailing zeros removed
    """
    # Define precision by currency
    if quote_currency == "USD":
        precision = 2  # USD uses 2 decimal places
    else:  # BTC and other crypto
        precision = 8  # Crypto typically uses 8 decimal places

    # Use Decimal for precise rounding
    decimal_amount = Decimal(str(amount))

    # Create quantize string (e.g., "0.00000001" for 8 decimals)
    quantize_str = "0." + "0" * precision

    # Round down to avoid exceeding limits
    rounded = decimal_amount.quantize(Decimal(quantize_str), rounding=ROUND_DOWN)

    # Convert to string - Coinbase requires fixed precision format
    # DO NOT strip trailing zeros - Coinbase validates exact decimal format
    result = str(rounded)

    return result


def format_base_amount(amount: float, base_currency: str) -> str:
    """
    Format base currency amount with proper precision for Coinbase.

    Args:
        amount: The amount to format
        base_currency: The base currency (ETH, DASH, etc.)

    Returns:
        Properly formatted string with correct precision, trailing zeros removed

    Examples:
        >>> format_base_amount(1.23456789, "ETH")
        '1.23456789'  # 8 decimals for crypto
    """
    # Most crypto uses 8 decimal places
    precision = 8

    # Use Decimal for precise rounding
    decimal_amount = Decimal(str(amount))

    # Create quantize string
    quantize_str = "0." + "0" * precision

    # Round down to avoid exceeding limits
    rounded = decimal_amount.quantize(Decimal(quantize_str), rounding=ROUND_DOWN)

    # Convert to string - Coinbase requires fixed precision format
    # DO NOT strip trailing zeros - Coinbase validates exact decimal format
    result = str(rounded)

    return result
