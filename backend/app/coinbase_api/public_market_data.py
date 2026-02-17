"""
Public (unauthenticated) Coinbase market data API.

These endpoints require NO API credentials and return the same JSON format
as the authenticated /brokerage/products/ endpoints.  This module is used as
the fallback for paper-trading accounts that have no Coinbase API keys.

Public endpoints used:
  GET /api/v3/brokerage/market/products
  GET /api/v3/brokerage/market/products/{product_id}
  GET /api/v3/brokerage/market/products/{product_id}/ticker
  GET /api/v3/brokerage/market/products/{product_id}/candles
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.cache import api_cache
from app.constants import PRICE_CACHE_TTL, PRODUCT_STATS_CACHE_TTL

logger = logging.getLogger(__name__)

BASE_URL = "https://api.coinbase.com"

# Module-level rate limiting: 200ms minimum between requests
_rate_lock = asyncio.Lock()
_last_request_time: float = 0.0


async def _public_request(
    endpoint: str,
    params: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Make a rate-limited GET request to a public Coinbase endpoint.

    Retries once on 429 (rate-limited) after a 1-second backoff.
    """
    global _last_request_time

    async with _rate_lock:
        now = time.monotonic()
        elapsed = now - _last_request_time
        if elapsed < 0.2:
            await asyncio.sleep(0.2 - elapsed)
        _last_request_time = time.monotonic()

    url = f"{BASE_URL}{endpoint}"

    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)

            if resp.status_code == 429:
                logger.warning("Public API rate-limited (429), backing off 1s")
                await asyncio.sleep(1.0)
                continue

            resp.raise_for_status()
            return resp.json()

        except httpx.HTTPStatusError as exc:
            logger.error(
                "Public API HTTP %s for %s: %s",
                exc.response.status_code,
                endpoint,
                exc.response.text[:200],
            )
            raise
        except Exception as exc:
            if attempt == 0:
                logger.warning("Public API request failed (%s), retrying: %s", endpoint, exc)
                await asyncio.sleep(0.5)
                continue
            raise

    raise RuntimeError(f"Public API request failed after retries: {endpoint}")


# ---------------------------------------------------------------------------
# Product list
# ---------------------------------------------------------------------------

async def list_products() -> List[Dict[str, Any]]:
    """Fetch all products (cached 1 hour)."""
    cache_key = "all_products"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        return cached

    result = await _public_request("/api/v3/brokerage/market/products")
    products = result.get("products", [])

    await api_cache.set(cache_key, products, ttl_seconds=3600)
    return products


# ---------------------------------------------------------------------------
# Single product
# ---------------------------------------------------------------------------

async def get_product(product_id: str) -> Dict[str, Any]:
    """Fetch product details (no cache — lightweight call)."""
    return await _public_request(f"/api/v3/brokerage/market/products/{product_id}")


# ---------------------------------------------------------------------------
# Ticker (best bid/ask)
# ---------------------------------------------------------------------------

async def get_ticker(product_id: str) -> Dict[str, Any]:
    """Fetch best bid/ask for a product."""
    return await _public_request(
        f"/api/v3/brokerage/market/products/{product_id}/ticker"
    )


# ---------------------------------------------------------------------------
# Current price (mid-price from bid/ask, cached)
# ---------------------------------------------------------------------------

async def get_current_price(product_id: str) -> float:
    """
    Return the mid-price for *product_id* (cached for PRICE_CACHE_TTL seconds).

    Falls back to most-recent trade price if bid/ask unavailable.
    """
    cache_key = f"price_{product_id}"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        return cached

    ticker = await get_ticker(product_id)

    best_bid = float(ticker.get("best_bid", 0))
    best_ask = float(ticker.get("best_ask", 0))

    if best_bid > 0 and best_ask > 0:
        price = (best_bid + best_ask) / 2.0
    else:
        trades = ticker.get("trades", [])
        if trades:
            price = float(trades[0].get("price", 0))
        else:
            price = 0.0

    if price > 0:
        await api_cache.set(cache_key, price, PRICE_CACHE_TTL)

    return price


async def get_btc_usd_price() -> float:
    """Convenience: BTC-USD mid-price."""
    return await get_current_price("BTC-USD")


async def get_eth_usd_price() -> float:
    """Convenience: ETH-USD mid-price."""
    return await get_current_price("ETH-USD")


# ---------------------------------------------------------------------------
# Product stats (24h data, cached)
# ---------------------------------------------------------------------------

async def get_product_stats(product_id: str) -> Dict[str, Any]:
    """
    24-hour stats extracted from the product endpoint (cached 10 min).
    """
    cache_key = f"stats_{product_id}"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        return cached

    result = await get_product(product_id)

    stats = {
        "volume_24h": float(result.get("volume_24h", 0)),
        "volume_percentage_change_24h": float(
            result.get("volume_percentage_change_24h", 0)
        ),
        "price_percentage_change_24h": float(
            result.get("price_percentage_change_24h", 0)
        ),
    }

    await api_cache.set(cache_key, stats, PRODUCT_STATS_CACHE_TTL)
    return stats


# ---------------------------------------------------------------------------
# Candles (OHLCV)
# ---------------------------------------------------------------------------

async def get_candles(
    product_id: str,
    start: int,
    end: int,
    granularity: str = "FIVE_MINUTE",
) -> List[Dict[str, Any]]:
    """Fetch historical candles from the public endpoint."""
    params = {
        "start": str(start),
        "end": str(end),
        "granularity": granularity,
    }
    result = await _public_request(
        f"/api/v3/brokerage/market/products/{product_id}/candles",
        params=params,
    )
    return result.get("candles", [])


# ---------------------------------------------------------------------------
# PublicMarketDataClient — duck-types CoinbaseClient for market_data_router
# ---------------------------------------------------------------------------

class PublicMarketDataClient:
    """
    Drop-in replacement for CoinbaseClient that uses only public endpoints.

    Implements the subset of methods used by market_data_router.py so that
    ``get_coinbase()`` can return this when no credentials are available.
    """

    async def list_products(self) -> List[Dict[str, Any]]:
        return await list_products()

    async def get_current_price(self, product_id: str = "ETH-BTC") -> float:
        return await get_current_price(product_id)

    async def get_btc_usd_price(self) -> float:
        return await get_btc_usd_price()

    async def get_eth_usd_price(self) -> float:
        return await get_eth_usd_price()

    async def get_candles(
        self,
        product_id: str,
        start: int,
        end: int,
        granularity: str = "FIVE_MINUTE",
    ) -> List[Dict[str, Any]]:
        return await get_candles(product_id, start, end, granularity)

    async def get_product_book(
        self, product_id: str, limit: int = 50
    ) -> Dict[str, Any]:
        """No public order-book endpoint — return empty structure."""
        return {"pricebook": {"bids": [], "asks": []}}
