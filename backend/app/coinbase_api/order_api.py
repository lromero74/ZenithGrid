"""
Order operations for Coinbase API
Handles order creation, management, and trading helpers
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from app.precision import format_quote_amount, format_base_amount
from app.product_precision import format_quote_amount_for_product, format_base_amount_for_product

logger = logging.getLogger(__name__)


async def create_market_order(
    request_func: Callable,
    product_id: str,
    side: str,  # "BUY" or "SELL"
    size: Optional[str] = None,  # Amount of base currency (e.g., ETH)
    funds: Optional[str] = None,  # Amount of quote currency (e.g., BTC) to spend
) -> Dict[str, Any]:
    """
    Create a market order

    Args:
        request_func: Authenticated request function
        product_id: Trading pair (e.g., "ETH-BTC", "AAVE-BTC")
        side: "BUY" or "SELL"
        size: Amount of base currency to buy/sell
        funds: Amount of quote currency to spend (for buy orders)

    Note: Use either size OR funds, not both
    """
    order_config: Dict[str, Dict] = {"market_market_ioc": {}}

    # Extract currencies from product_id for proper precision formatting
    if "-" in product_id:
        base_currency, quote_currency = product_id.split("-")
    else:
        base_currency, quote_currency = "ETH", "BTC"  # fallback

    if size:
        # Format base amount with product-specific precision
        formatted_size = format_base_amount_for_product(float(size), product_id)
        order_config["market_market_ioc"]["base_size"] = formatted_size
    elif funds:
        # Format quote amount with product-specific precision
        # Uses precision lookup table from Coinbase API to ensure exact requirements
        formatted_funds = format_quote_amount_for_product(float(funds), product_id)
        order_config["market_market_ioc"]["quote_size"] = formatted_funds
    else:
        raise ValueError("Must specify either size or funds")

    data = {
        "client_order_id": f"{int(time.time() * 1000)}",
        "product_id": product_id,
        "side": side,
        "order_configuration": order_config,
    }

    result = await request_func("POST", "/api/v3/brokerage/orders", data=data)
    return result


async def create_limit_order(
    request_func: Callable,
    product_id: str,
    side: str,  # "BUY" or "SELL"
    limit_price: float,  # Target price
    size: Optional[str] = None,  # Amount of base currency (e.g., ETH)
    funds: Optional[str] = None,  # Amount of quote currency (e.g., BTC) to spend
) -> Dict[str, Any]:
    """
    Create a limit order (Good-Til-Cancelled)

    Args:
        request_func: Authenticated request function
        product_id: Trading pair (e.g., "ETH-BTC", "AAVE-BTC")
        side: "BUY" or "SELL"
        limit_price: Target price for the order
        size: Amount of base currency to buy/sell
        funds: Amount of quote currency to spend (for buy orders)

    Note: Use either size OR funds, not both
    """
    # Extract currencies from product_id for proper precision formatting
    if "-" in product_id:
        base_currency, quote_currency = product_id.split("-")
    else:
        base_currency, quote_currency = "ETH", "BTC"  # fallback

    # Format limit price with proper precision (price is in quote currency)
    formatted_limit_price = format_quote_amount(limit_price, quote_currency)

    order_config = {
        "limit_limit_gtc": {"limit_price": formatted_limit_price, "post_only": False}  # Allow immediate partial fills
    }

    if size:
        # Format base amount with proper precision
        formatted_size = format_base_amount(float(size), base_currency)
        order_config["limit_limit_gtc"]["base_size"] = formatted_size
    elif funds:
        # For limit orders with funds, we calculate base size from limit price
        base_size = float(funds) / limit_price
        # Format with proper precision
        formatted_base_size = format_base_amount(base_size, base_currency)
        order_config["limit_limit_gtc"]["base_size"] = formatted_base_size
    else:
        raise ValueError("Must specify either size or funds")

    data = {
        "client_order_id": f"{int(time.time() * 1000)}",
        "product_id": product_id,
        "side": side,
        "order_configuration": order_config,
    }

    result = await request_func("POST", "/api/v3/brokerage/orders", data=data)
    return result


async def get_order(request_func: Callable, auth_type: str, order_id: str) -> Dict[str, Any]:
    """
    Get order details

    Args:
        request_func: Authenticated request function
        auth_type: Either "cdp" or "hmac"
        order_id: Coinbase order ID

    Returns:
        Order details including status
    """
    result = await request_func("GET", f"/api/v3/brokerage/orders/historical/{order_id}")

    # CDP returns full dict, HMAC returns nested in "order" key
    if auth_type == "hmac" and "order" in result:
        return result.get("order", {})
    return result


async def cancel_order(request_func: Callable, order_id: str) -> Dict[str, Any]:
    """
    Cancel an open order

    Args:
        request_func: Authenticated request function
        order_id: Coinbase order ID

    Returns:
        Cancellation result
    """
    data = {"order_ids": [order_id]}
    result = await request_func("POST", "/api/v3/brokerage/orders/batch_cancel", data=data)
    return result


async def list_orders(
    request_func: Callable, product_id: Optional[str] = None, order_status: Optional[List[str]] = None, limit: int = 100
) -> List[Dict[str, Any]]:
    """
    List orders with optional filtering

    Args:
        request_func: Authenticated request function
        product_id: Filter by trading pair
        order_status: Filter by status (e.g., ["OPEN", "FILLED"])
        limit: Max number of orders to return

    Returns:
        List of order details
    """
    params = {"limit": limit}
    if product_id:
        params["product_id"] = product_id
    if order_status:
        params["order_status"] = order_status

    result = await request_func("GET", "/api/v3/brokerage/orders/historical/batch", params=params)
    return result.get("orders", [])


# ===== Convenience Trading Methods =====


async def buy_eth_with_btc(request_func: Callable, btc_amount: float, product_id: str = "ETH-BTC") -> Dict[str, Any]:
    """
    Buy crypto with specified amount of BTC

    Args:
        request_func: Authenticated request function
        btc_amount: Amount of BTC to spend
        product_id: Trading pair (e.g., "ETH-BTC", "AAVE-BTC")

    Returns:
        Order response
    """
    return await create_market_order(request_func, product_id=product_id, side="BUY", funds=f"{btc_amount:.8f}")


async def sell_eth_for_btc(request_func: Callable, eth_amount: float, product_id: str = "ETH-BTC") -> Dict[str, Any]:
    """
    Sell crypto for BTC

    Args:
        request_func: Authenticated request function
        eth_amount: Amount of crypto to sell
        product_id: Trading pair (e.g., "ETH-BTC", "AAVE-BTC")

    Returns:
        Order response
    """
    # Extract base currency from product_id (e.g., "ETH" from "ETH-BTC")
    base_currency = product_id.split("-")[0] if "-" in product_id else "ETH"

    return await create_market_order(
        request_func, product_id=product_id, side="SELL", size=format_base_amount(eth_amount, base_currency)
    )


async def buy_with_usd(request_func: Callable, usd_amount: float, product_id: str) -> Dict[str, Any]:
    """
    Buy crypto with specified amount of USD

    Args:
        request_func: Authenticated request function
        usd_amount: Amount of USD to spend
        product_id: Trading pair (e.g., "ADA-USD", "ETH-USD")

    Returns:
        Order response
    """
    return await create_market_order(request_func, product_id=product_id, side="BUY", funds=f"{usd_amount:.2f}")


async def sell_for_usd(request_func: Callable, base_amount: float, product_id: str) -> Dict[str, Any]:
    """
    Sell crypto for USD

    Args:
        request_func: Authenticated request function
        base_amount: Amount of base currency to sell (e.g., ETH, ADA)
        product_id: Trading pair (e.g., "ADA-USD", "ETH-USD")

    Returns:
        Order response
    """
    # Extract base currency from product_id
    base_currency = product_id.split("-")[0] if "-" in product_id else "ETH"

    return await create_market_order(
        request_func, product_id=product_id, side="SELL", size=format_base_amount(base_amount, base_currency)
    )
