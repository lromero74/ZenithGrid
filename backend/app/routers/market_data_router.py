"""
Market data API routes

Handles market data endpoints:
- Current ticker/price for products
- Batch price fetching
- Historical candle data
- Product listings
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_unified_client import CoinbaseClient
from app.config import settings
from app.database import get_db
from app.models import Account
from app.exchange_clients.factory import create_exchange_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["market_data"])


async def get_coinbase(db: AsyncSession = Depends(get_db)) -> CoinbaseClient:
    """
    Get Coinbase client from the first active CEX account in the database.

    TODO: Once authentication is wired up, this should get the exchange
    client for the currently logged-in user's account.
    """
    # Get first active CEX account
    result = await db.execute(
        select(Account).where(
            Account.type == "cex",
            Account.is_active.is_(True)
        ).order_by(Account.is_default.desc(), Account.created_at)
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=503,
            detail="No Coinbase account configured. Please add your API credentials in Settings."
        )

    if not account.api_key_name or not account.api_private_key:
        raise HTTPException(
            status_code=503,
            detail="Coinbase account missing API credentials. Please update in Settings."
        )

    # Create and return the client
    client = create_exchange_client(
        exchange_type="cex",
        coinbase_key_name=account.api_key_name,
        coinbase_private_key=account.api_private_key,
    )

    if not client:
        raise HTTPException(
            status_code=503,
            detail="Failed to create Coinbase client. Please check your API credentials."
        )

    return client


@router.get("/ticker/{product_id}")
async def get_ticker(product_id: str, coinbase: CoinbaseClient = Depends(get_coinbase)):
    """Get current ticker/price for a product"""
    try:
        # Use get_current_price() which properly calculates mid-price from best_bid/best_ask
        current_price = await coinbase.get_current_price(product_id)

        return {
            "product_id": product_id,
            "price": current_price,
            "time": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prices/batch")
async def get_prices_batch(products: str, coinbase: CoinbaseClient = Depends(get_coinbase)):
    """
    Get current prices for multiple products in a single request

    Args:
        products: Comma-separated list of product IDs (e.g., "ETH-BTC,AAVE-BTC,ALGO-BTC")

    Returns:
        Dict mapping product_id to price
    """
    try:
        product_list = [p.strip() for p in products.split(",") if p.strip()]

        if not product_list:
            raise HTTPException(status_code=400, detail="No products specified")

        # Fetch all prices concurrently
        async def fetch_price(product_id: str):
            try:
                price = await coinbase.get_current_price(product_id)
                return (product_id, price)
            except Exception as e:
                logger.warning(f"Failed to fetch price for {product_id}: {e}")
                return (product_id, None)

        results = await asyncio.gather(*[fetch_price(p) for p in product_list])

        # Build response dict, filtering out failed requests
        prices = {product_id: price for product_id, price in results if price is not None}

        return {
            "prices": prices,
            "time": datetime.utcnow().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/candles")
async def get_candles(
    product_id: str = "ETH-BTC",
    granularity: Optional[str] = None,
    limit: int = 300,
    coinbase: CoinbaseClient = Depends(get_coinbase),
):
    """
    Get historical candle data for charting

    Args:
        product_id: Trading pair (default: ETH-BTC)
        granularity: Candle interval - ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE,
                     THIRTY_MINUTE, ONE_HOUR, TWO_HOUR, SIX_HOUR, ONE_DAY
        limit: Number of candles to fetch (default: 300)
    """
    try:
        interval = granularity or settings.candle_interval

        # Calculate start time based on limit and granularity
        interval_seconds = {
            "ONE_MINUTE": 60,
            "FIVE_MINUTE": 300,
            "FIFTEEN_MINUTE": 900,
            "THIRTY_MINUTE": 1800,
            "ONE_HOUR": 3600,
            "TWO_HOUR": 7200,
            "SIX_HOUR": 21600,
            "ONE_DAY": 86400,
        }

        seconds = interval_seconds.get(interval, 300)
        end_time = int(time.time())
        start_time = end_time - (seconds * limit)

        candles = await coinbase.get_candles(
            product_id=product_id, start=start_time, end=end_time, granularity=interval
        )

        # Coinbase returns candles in reverse chronological order
        # Format: {"start": timestamp, "low": str, "high": str, "open": str, "close": str, "volume": str}
        formatted_candles = []
        for candle in reversed(candles):  # Reverse to get chronological order
            formatted_candles.append(
                {
                    "time": int(candle["start"]),
                    "open": float(candle["open"]),
                    "high": float(candle["high"]),
                    "low": float(candle["low"]),
                    "close": float(candle["close"]),
                    "volume": float(candle["volume"]),
                }
            )

        return {"candles": formatted_candles, "interval": interval, "product_id": product_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch candles: {str(e)}")


@router.get("/products")
async def get_products(coinbase: CoinbaseClient = Depends(get_coinbase)):
    """Get all available trading products from Coinbase"""
    try:
        products = await coinbase.list_products()

        # Filter to only USD, USDC, and BTC pairs that are tradeable
        filtered_products = []
        for product in products:
            product_id = product.get("product_id", "")
            status = product.get("status", "")

            # Only include online/active products
            if status != "online":
                continue

            # Only include USD, USDC, and BTC pairs
            if product_id.endswith("-USD") or product_id.endswith("-USDC") or product_id.endswith("-BTC"):
                base_currency = product.get("base_currency_id", "")
                quote_currency = product.get("quote_currency_id", "")

                filtered_products.append(
                    {
                        "product_id": product_id,
                        "base_currency": base_currency,
                        "quote_currency": quote_currency,
                        "display_name": product.get("display_name", product_id),
                    }
                )

        # Sort: BTC-USD first, then alphabetically
        def sort_key(p):
            if p["product_id"] == "BTC-USD":
                return "0"
            elif p["quote_currency"] == "USD":
                return "1_" + p["product_id"]
            elif p["quote_currency"] == "USDC":
                return "2_" + p["product_id"]
            else:  # BTC pairs
                return "3_" + p["product_id"]

        filtered_products.sort(key=sort_key)

        return {"products": filtered_products, "count": len(filtered_products)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/coins")
async def get_unique_coins(coinbase: CoinbaseClient = Depends(get_coinbase)):
    """
    Get unique coins (base currencies) available across all markets.

    Returns coins that trade on USD, USDC, or BTC markets.
    Each coin appears once regardless of how many markets it trades on.
    """
    try:
        products = await coinbase.list_products()

        # Track unique coins and which markets they trade on
        coins: dict[str, dict] = {}

        for product in products:
            product_id = product.get("product_id", "")
            status = product.get("status", "")

            # Only include online/active products
            if status != "online":
                continue

            # Only include USD, USDC, and BTC pairs
            quote_currencies = ["USD", "USDC", "BTC"]
            quote = None
            for q in quote_currencies:
                if product_id.endswith(f"-{q}"):
                    quote = q
                    break

            if not quote:
                continue

            base_currency = product.get("base_currency_id", "")

            # Skip BTC itself (it's a quote currency, not tradeable as base on BTC market)
            if base_currency == "BTC" and quote == "BTC":
                continue

            if base_currency not in coins:
                coins[base_currency] = {
                    "symbol": base_currency,
                    "markets": [],
                    "product_ids": [],
                }

            coins[base_currency]["markets"].append(quote)
            coins[base_currency]["product_ids"].append(product_id)

        # Convert to list and sort alphabetically
        coin_list = sorted(coins.values(), key=lambda c: c["symbol"])

        return {
            "coins": coin_list,
            "count": len(coin_list),
        }
    except Exception as e:
        logger.error(f"Error fetching unique coins: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/product-precision/{product_id}")
async def get_product_precision(product_id: str):
    """
    Get precision data for a specific product from product_precision.json

    Returns quote_increment, quote_decimals, and base_increment
    """
    try:
        from app.product_precision import get_precision_data

        precision_data = get_precision_data()

        if product_id not in precision_data:
            # Return defaults based on quote currency
            quote_currency = product_id.split("-")[1] if "-" in product_id else "BTC"
            if quote_currency == "USD":
                return {
                    "product_id": product_id,
                    "quote_increment": "0.01",
                    "quote_decimals": 2,
                    "base_increment": "0.00000001",
                }
            else:
                return {
                    "product_id": product_id,
                    "quote_increment": "0.00000001",
                    "quote_decimals": 8,
                    "base_increment": "0.00000001",
                }

        product_data = precision_data[product_id]
        return {
            "product_id": product_id,
            "quote_increment": product_data.get("quote_increment", "0.00000001"),
            "quote_decimals": product_data.get("quote_decimals", 8),
            "base_increment": product_data.get("base_increment", "0.00000001"),
        }

    except Exception as e:
        logger.error(f"Error fetching product precision for {product_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
