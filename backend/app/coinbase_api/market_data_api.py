"""
Market data operations for Coinbase API
Handles products, prices, candles, and market statistics
"""

import logging
from typing import Any, Callable, Dict, List

from app.cache import api_cache
from app.constants import PRICE_CACHE_TTL

logger = logging.getLogger(__name__)


async def list_products(request_func: Callable) -> List[Dict[str, Any]]:
    """Get all available products/trading pairs"""
    cache_key = "all_products"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        return cached

    result = await request_func("GET", "/api/v3/brokerage/products")
    products = result.get("products", [])

    # Cache for 1 hour (product list doesn't change often)
    await api_cache.set(cache_key, products, ttl_seconds=3600)
    return products


async def get_product(request_func: Callable, product_id: str = "ETH-BTC") -> Dict[str, Any]:
    """Get product details"""
    result = await request_func("GET", f"/api/v3/brokerage/products/{product_id}")
    return result.get("product", {})


async def get_ticker(request_func: Callable, product_id: str = "ETH-BTC") -> Dict[str, Any]:
    """Get current ticker/price for a product"""
    result = await request_func("GET", f"/api/v3/brokerage/products/{product_id}/ticker")
    return result


async def get_current_price(request_func: Callable, auth_type: str, product_id: str = "ETH-BTC") -> float:
    """
    Get current price (cached for 10s to reduce API spam)

    CDP auth returns mid-price from best bid/ask.
    HMAC auth returns direct price field.
    """
    cache_key = f"price_{product_id}"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        return cached

    ticker = await get_ticker(request_func, product_id)

    if auth_type == "cdp":
        # CDP returns best_bid and best_ask, calculate mid-price
        best_bid = float(ticker.get("best_bid", 0))
        best_ask = float(ticker.get("best_ask", 0))

        if best_bid > 0 and best_ask > 0:
            price = (best_bid + best_ask) / 2.0
        else:
            # Fallback: use most recent trade price
            trades = ticker.get("trades", [])
            if trades:
                price = float(trades[0].get("price", 0))
            else:
                price = 0.0
    else:
        # HMAC returns price field directly
        if "price" not in ticker or not ticker.get("price"):
            logger.error(f"Ticker response for {product_id} missing price! Response: {ticker}")

        price = float(ticker.get("price", "0"))

        if price == 0.0:
            logger.warning(f"Price is 0.0 for {product_id}. Ticker response: {ticker}")

    await api_cache.set(cache_key, price, PRICE_CACHE_TTL)
    return price


async def get_btc_usd_price(request_func: Callable, auth_type: str) -> float:
    """Get current BTC/USD price"""
    return await get_current_price(request_func, auth_type, "BTC-USD")


async def get_product_stats(request_func: Callable, product_id: str = "ETH-BTC") -> Dict[str, Any]:
    """
    Get 24-hour stats for a product including volume

    Returns dict with keys like:
    - volume_24h: 24h volume in quote currency
    - volume_percentage_change_24h: % change in volume
    - price_percentage_change_24h: % change in price
    """
    cache_key = f"stats_{product_id}"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        return cached

    result = await request_func("GET", f"/api/v3/brokerage/products/{product_id}")

    # Extract 24h stats from product data
    stats = {
        "volume_24h": float(result.get("volume_24h", 0)),
        "volume_percentage_change_24h": float(result.get("volume_percentage_change_24h", 0)),
        "price_percentage_change_24h": float(result.get("price_percentage_change_24h", 0)),
    }

    # Cache for 5 minutes (volume doesn't change that quickly)
    await api_cache.set(cache_key, stats, 300)
    return stats


async def get_candles(
    request_func: Callable, product_id: str, start: int, end: int, granularity: str = "FIVE_MINUTE"
) -> List[Dict[str, Any]]:
    """Get historical candles/OHLCV data"""
    params = {"start": str(start), "end": str(end), "granularity": granularity}
    result = await request_func("GET", f"/api/v3/brokerage/products/{product_id}/candles", params=params)
    return result.get("candles", [])


async def test_connection(request_func: Callable) -> bool:
    """Test if API connection works"""
    try:
        from app.coinbase_api import account_balance_api

        await account_balance_api.get_accounts(request_func)
        return True
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return False
