import hmac
import hashlib
import time
import json
from typing import Dict, Any, Optional, List
import httpx
from app.config import settings
from app.cache import api_cache
from app.constants import BALANCE_CACHE_TTL, PRICE_CACHE_TTL


class CoinbaseClient:
    """Coinbase Advanced Trade API Client"""

    BASE_URL = "https://api.coinbase.com"

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key or settings.coinbase_api_key
        self.api_secret = api_secret or settings.coinbase_api_secret

    def _generate_signature(
        self,
        timestamp: str,
        method: str,
        request_path: str,
        body: str = ""
    ) -> str:
        """Generate HMAC signature for Coinbase API"""
        message = timestamp + method + request_path + body
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return signature

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make authenticated request to Coinbase API"""
        url = f"{self.BASE_URL}{endpoint}"
        timestamp = str(int(time.time()))

        # Prepare body
        body = ""
        if data:
            body = json.dumps(data)

        # Generate signature
        signature = self._generate_signature(timestamp, method, endpoint, body)

        headers = {
            "CB-ACCESS-KEY": self.api_key,
            "CB-ACCESS-SIGN": signature,
            "CB-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                response = await client.get(url, headers=headers, params=params)
            elif method == "POST":
                response = await client.post(url, headers=headers, json=data)
            elif method == "DELETE":
                response = await client.delete(url, headers=headers, params=params)
            else:
                raise ValueError(f"Unsupported method: {method}")

            response.raise_for_status()
            return response.json()

    async def get_accounts(self) -> List[Dict[str, Any]]:
        """Get all accounts"""
        result = await self._request("GET", "/api/v3/brokerage/accounts")
        return result.get("accounts", [])

    async def get_account(self, account_id: str) -> Dict[str, Any]:
        """Get specific account details"""
        result = await self._request("GET", f"/api/v3/brokerage/accounts/{account_id}")
        return result.get("account", {})

    async def get_btc_balance(self) -> float:
        """Get BTC balance (cached to reduce API calls)"""
        cache_key = "balance_btc"
        cached = await api_cache.get(cache_key)
        if cached is not None:
            return cached

        accounts = await self.get_accounts()
        balance = 0.0
        for account in accounts:
            if account.get("currency") == "BTC":
                available = account.get("available_balance", {})
                balance = float(available.get("value", 0))
                break

        await api_cache.set(cache_key, balance, BALANCE_CACHE_TTL)
        return balance

    async def get_eth_balance(self) -> float:
        """Get ETH balance (cached to reduce API calls)"""
        cache_key = "balance_eth"
        cached = await api_cache.get(cache_key)
        if cached is not None:
            return cached

        accounts = await self.get_accounts()
        balance = 0.0
        for account in accounts:
            if account.get("currency") == "ETH":
                available = account.get("available_balance", {})
                balance = float(available.get("value", 0))
                break

        await api_cache.set(cache_key, balance, BALANCE_CACHE_TTL)
        return balance

    async def get_usd_balance(self) -> float:
        """Get USD balance (cached to reduce API calls)"""
        cache_key = "balance_usd"
        cached = await api_cache.get(cache_key)
        if cached is not None:
            return cached

        accounts = await self.get_accounts()
        balance = 0.0
        for account in accounts:
            if account.get("currency") == "USD":
                available = account.get("available_balance", {})
                balance = float(available.get("value", 0))
                break

        await api_cache.set(cache_key, balance, BALANCE_CACHE_TTL)
        return balance

    async def list_products(self) -> List[Dict[str, Any]]:
        """Get all available products/trading pairs"""
        cache_key = "all_products"
        cached = await api_cache.get(cache_key)
        if cached is not None:
            return cached

        result = await self._request("GET", "/api/v3/brokerage/products")
        products = result.get("products", [])

        # Cache for 1 hour (product list doesn't change often)
        await api_cache.set(cache_key, products, ttl_seconds=3600)
        return products

    async def get_product(self, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Get product details"""
        result = await self._request("GET", f"/api/v3/brokerage/products/{product_id}")
        return result.get("product", {})

    async def get_ticker(self, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Get current ticker/price for a product"""
        result = await self._request("GET", f"/api/v3/brokerage/products/{product_id}/ticker")
        return result

    async def get_current_price(self, product_id: str = "ETH-BTC") -> float:
        """Get current price (cached for 10s to reduce API spam)"""
        cache_key = f"price_{product_id}"
        cached = await api_cache.get(cache_key)
        if cached is not None:
            return cached

        ticker = await self.get_ticker(product_id)

        # Debug logging for price issues
        if "price" not in ticker or not ticker.get("price"):
            logger.error(f"❌ Ticker response for {product_id} missing price! Response: {ticker}")

        price = float(ticker.get("price", "0"))

        if price == 0.0:
            logger.warning(f"⚠️  Price is 0.0 for {product_id}. Ticker response: {ticker}")

        await api_cache.set(cache_key, price, PRICE_CACHE_TTL)
        return price

    async def get_btc_usd_price(self) -> float:
        """Get current BTC/USD price"""
        return await self.get_current_price("BTC-USD")

    async def invalidate_balance_cache(self):
        """Invalidate balance cache (call after trades)"""
        await api_cache.delete("balance_btc")
        await api_cache.delete("balance_eth")
        await api_cache.delete("balance_usd")

    async def create_market_order(
        self,
        product_id: str,
        side: str,  # "BUY" or "SELL"
        size: Optional[str] = None,  # Amount of base currency (ETH)
        funds: Optional[str] = None  # Amount of quote currency (BTC) to spend
    ) -> Dict[str, Any]:
        """
        Create a market order

        Args:
            product_id: Trading pair (e.g., "ETH-BTC")
            side: "BUY" or "SELL"
            size: Amount of base currency (ETH) to buy/sell
            funds: Amount of quote currency (BTC) to spend (for buy orders)

        Note: Use either size OR funds, not both
        """
        order_config = {
            "market_market_ioc": {}
        }

        if size:
            order_config["market_market_ioc"]["base_size"] = str(size)
        elif funds:
            order_config["market_market_ioc"]["quote_size"] = str(funds)
        else:
            raise ValueError("Must specify either size or funds")

        data = {
            "client_order_id": f"{int(time.time() * 1000)}",
            "product_id": product_id,
            "side": side,
            "order_configuration": order_config
        }

        result = await self._request("POST", "/api/v3/brokerage/orders", data=data)
        return result

    async def buy_eth_with_btc(self, btc_amount: float, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """
        Buy ETH with specified amount of BTC

        Args:
            btc_amount: Amount of BTC to spend
            product_id: Trading pair

        Returns:
            Order response
        """
        return await self.create_market_order(
            product_id=product_id,
            side="BUY",
            funds=f"{btc_amount:.8f}"
        )

    async def sell_eth_for_btc(self, eth_amount: float, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """
        Sell ETH for BTC

        Args:
            eth_amount: Amount of ETH to sell
            product_id: Trading pair

        Returns:
            Order response
        """
        return await self.create_market_order(
            product_id=product_id,
            side="SELL",
            size=f"{eth_amount:.8f}"
        )

    async def buy_with_usd(self, usd_amount: float, product_id: str) -> Dict[str, Any]:
        """
        Buy crypto with specified amount of USD

        Args:
            usd_amount: Amount of USD to spend
            product_id: Trading pair (e.g., "ADA-USD", "ETH-USD")

        Returns:
            Order response
        """
        return await self.create_market_order(
            product_id=product_id,
            side="BUY",
            funds=f"{usd_amount:.2f}"
        )

    async def sell_for_usd(self, base_amount: float, product_id: str) -> Dict[str, Any]:
        """
        Sell crypto for USD

        Args:
            base_amount: Amount of base currency to sell (e.g., ETH, ADA)
            product_id: Trading pair (e.g., "ADA-USD", "ETH-USD")

        Returns:
            Order response
        """
        return await self.create_market_order(
            product_id=product_id,
            side="SELL",
            size=f"{base_amount:.8f}"
        )

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get order details"""
        result = await self._request("GET", f"/api/v3/brokerage/orders/historical/{order_id}")
        return result.get("order", {})

    async def list_orders(
        self,
        product_id: Optional[str] = None,
        order_status: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List orders"""
        params = {"limit": limit}
        if product_id:
            params["product_id"] = product_id
        if order_status:
            params["order_status"] = order_status

        result = await self._request("GET", "/api/v3/brokerage/orders/historical/batch", params=params)
        return result.get("orders", [])

    async def get_candles(
        self,
        product_id: str = "ETH-BTC",
        start: Optional[int] = None,
        end: Optional[int] = None,
        granularity: str = "ONE_MINUTE"
    ) -> List[Dict[str, Any]]:
        """
        Get historical candles/OHLCV data

        Args:
            product_id: Trading pair
            start: Start time (unix timestamp)
            end: End time (unix timestamp)
            granularity: ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE, THIRTY_MINUTE,
                        ONE_HOUR, TWO_HOUR, SIX_HOUR, ONE_DAY
        """
        params = {
            "granularity": granularity
        }
        if start:
            params["start"] = str(start)
        if end:
            params["end"] = str(end)

        result = await self._request(
            "GET",
            f"/api/v3/brokerage/products/{product_id}/candles",
            params=params
        )
        return result.get("candles", [])

    async def test_connection(self) -> bool:
        """Test if API credentials are valid"""
        try:
            await self.get_accounts()
            return True
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False
