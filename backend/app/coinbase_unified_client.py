"""
Unified Coinbase Advanced Trade API Client

Supports both authentication methods:
1. CDP (Developer Platform) - JWT with EC private key (recommended)
2. HMAC-SHA256 - Traditional API key/secret authentication

Auto-detects authentication method based on provided credentials.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx
import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from app.cache import api_cache
from app.constants import BALANCE_CACHE_TTL, PRICE_CACHE_TTL
from app.precision import format_quote_amount, format_base_amount
from app.product_precision import format_quote_amount_for_product, format_base_amount_for_product

logger = logging.getLogger(__name__)


class CoinbaseClient:
    """
    Unified Coinbase Advanced Trade API Client

    Supports both CDP (JWT) and HMAC authentication methods.
    Auto-detects which method to use based on provided credentials.
    """

    BASE_URL = "https://api.coinbase.com"

    def __init__(
        self,
        # CDP/JWT auth params
        key_name: Optional[str] = None,
        private_key: Optional[str] = None,
        key_file_path: Optional[str] = None,
        # HMAC auth params
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None
    ):
        """
        Initialize Coinbase client with auto-detection of auth method

        Auth method priority:
        1. CDP via key_name + private_key
        2. CDP via key_file_path
        3. HMAC via api_key + api_secret
        4. Fallback to settings

        Args:
            key_name: CDP API key name (from JSON file's 'name' field)
            private_key: CDP EC private key PEM string (from JSON file's 'privateKey' field)
            key_file_path: Path to cdp_api_key.json file
            api_key: HMAC API key
            api_secret: HMAC API secret
        """
        # Auto-detect authentication method
        if key_name and private_key:
            # CDP auth with explicit credentials
            self.auth_type = "cdp"
            self.key_name = key_name
            self.private_key = private_key
            logger.info("Using CDP authentication (explicit credentials)")
        elif key_file_path:
            # CDP auth from file
            self.auth_type = "cdp"
            self._load_from_file(key_file_path)
            logger.info(f"Using CDP authentication (loaded from {key_file_path})")
        elif api_key and api_secret:
            # HMAC auth with explicit credentials
            self.auth_type = "hmac"
            self.api_key = api_key
            self.api_secret = api_secret
            logger.info("Using HMAC authentication (explicit credentials)")
        else:
            # Fallback to settings
            from app.config import settings
            if hasattr(settings, 'coinbase_cdp_key_name') and settings.coinbase_cdp_key_name and \
               hasattr(settings, 'coinbase_cdp_private_key') and settings.coinbase_cdp_private_key:
                # CDP from settings
                self.auth_type = "cdp"
                self.key_name = settings.coinbase_cdp_key_name
                self.private_key = settings.coinbase_cdp_private_key
                logger.info("Using CDP authentication (from settings)")
            else:
                # HMAC from settings
                self.auth_type = "hmac"
                self.api_key = settings.coinbase_api_key
                self.api_secret = settings.coinbase_api_secret
                logger.info("Using HMAC authentication (from settings)")

    def _load_from_file(self, file_path: str):
        """Load CDP credentials from JSON key file"""
        with open(file_path, 'r') as f:
            data = json.load(f)

        self.key_name = data['name']
        self.private_key = data['privateKey']

    # ===== CDP/JWT Authentication Methods =====

    def _generate_jwt(self, request_method: str, request_path: str) -> str:
        """
        Generate JWT token for CDP API request

        Args:
            request_method: HTTP method (GET, POST, etc.)
            request_path: API endpoint path

        Returns:
            JWT token string
        """
        # Load the EC private key
        private_key_obj = serialization.load_pem_private_key(
            self.private_key.encode('utf-8'),
            password=None,
            backend=default_backend()
        )

        # Create JWT payload - URI must include hostname per Coinbase spec
        uri = f"{request_method} api.coinbase.com{request_path}"
        current_time = int(time.time())

        payload = {
            "sub": self.key_name,
            "iss": "cdp",  # Coinbase Developer Platform
            "nbf": current_time,
            "exp": current_time + 120,  # Expires in 2 minutes
            "uri": uri
        }

        # Sign JWT with ES256 algorithm (ECDSA with P-256 curve)
        token = jwt.encode(
            payload,
            private_key_obj,
            algorithm="ES256",
            headers={"kid": self.key_name, "nonce": str(current_time)}
        )

        # Debug output
        print(f"DEBUG: Generated JWT for {uri}")
        print(f"DEBUG: Payload: {payload}")
        print(f"DEBUG: Token: {token[:50]}...")

        return token

    # ===== HMAC Authentication Methods =====

    def _generate_signature(
        self,
        timestamp: str,
        method: str,
        request_path: str,
        body: str = ""
    ) -> str:
        """Generate HMAC-SHA256 signature for API request"""
        message = timestamp + method + request_path + body
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return signature

    # ===== Unified Request Method =====

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make authenticated request to Coinbase API

        Uses either CDP (JWT) or HMAC authentication based on auth_type
        """
        url = f"{self.BASE_URL}{endpoint}"

        if self.auth_type == "cdp":
            # CDP/JWT Authentication
            jwt_token = self._generate_jwt(method, endpoint)
            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Content-Type": "application/json"
            }
        else:
            # HMAC Authentication
            timestamp = str(int(time.time()))
            body = ""
            if data:
                body = json.dumps(data)

            signature = self._generate_signature(timestamp, method, endpoint, body)
            headers = {
                "CB-ACCESS-KEY": self.api_key,
                "CB-ACCESS-SIGN": signature,
                "CB-ACCESS-TIMESTAMP": timestamp,
                "Content-Type": "application/json"
            }

        async with httpx.AsyncClient(timeout=30.0) as client:
            max_retries = 3
            for attempt in range(max_retries):
                try:
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

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:  # Too Many Requests
                        if attempt < max_retries - 1:
                            # Exponential backoff: 1s, 2s, 4s
                            wait_time = 2 ** attempt
                            logger.warning(f"⚠️  Rate limited (429) on {method} {endpoint}, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"❌ Rate limit exceeded after {max_retries} attempts on {method} {endpoint}")
                            raise
                    else:
                        # Non-429 error, raise immediately
                        raise

    # ===== Account & Balance Methods =====

    async def get_accounts(self) -> List[Dict[str, Any]]:
        """Get all accounts (cached to reduce API calls)"""
        cache_key = "accounts_list"
        cached = await api_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Using cached accounts list ({len(cached)} accounts)")
            return cached

        result = await self._request("GET", "/api/v3/brokerage/accounts")
        accounts = result.get("accounts", [])

        # Cache for 60 seconds (same as BALANCE_CACHE_TTL)
        await api_cache.set(cache_key, accounts, BALANCE_CACHE_TTL)
        logger.debug(f"Cached accounts list ({len(accounts)} accounts) for {BALANCE_CACHE_TTL}s")
        return accounts

    async def get_account(self, account_id: str) -> Dict[str, Any]:
        """Get specific account details"""
        result = await self._request("GET", f"/api/v3/brokerage/accounts/{account_id}")
        return result.get("account", {})

    async def get_portfolios(self) -> List[Dict[str, Any]]:
        """Get list of all portfolios"""
        result = await self._request("GET", "/api/v3/brokerage/portfolios")
        return result.get("portfolios", [])

    async def get_portfolio_breakdown(self, portfolio_uuid: Optional[str] = None) -> dict:
        """
        Get portfolio breakdown with all spot positions

        This is a CDP-specific endpoint that provides a consolidated view of all holdings.
        If portfolio_uuid is not provided, automatically fetches the first available portfolio.
        """
        if portfolio_uuid is None:
            # Dynamically fetch the first available portfolio UUID
            portfolios = await self.get_portfolios()
            if not portfolios:
                raise Exception("No portfolios found for this API key")
            portfolio_uuid = portfolios[0].get("uuid")
            logger.info(f"Using portfolio UUID: {portfolio_uuid} (name: {portfolios[0].get('name', 'Unknown')})")

        result = await self._request("GET", f"/api/v3/brokerage/portfolios/{portfolio_uuid}")
        return result.get("breakdown", {})

    async def get_btc_balance(self) -> float:
        """
        Get BTC balance

        Uses portfolio breakdown for CDP auth, individual accounts for HMAC auth.
        Both methods are cached to reduce API calls.
        """
        cache_key = "balance_btc"
        cached = await api_cache.get(cache_key)
        if cached is not None:
            return cached

        if self.auth_type == "cdp":
            # Use portfolio breakdown for CDP
            try:
                breakdown = await self.get_portfolio_breakdown()
                spot_positions = breakdown.get("spot_positions", [])
                for pos in spot_positions:
                    if pos.get("asset") == "BTC":
                        balance = float(pos.get("available_to_trade_crypto", 0))
                        await api_cache.set(cache_key, balance, BALANCE_CACHE_TTL)
                        return balance
            except Exception as e:
                logger.warning(f"Portfolio endpoint failed for BTC balance: {e}. Falling back to get_accounts().")

            # Fallback to get_accounts() if portfolio fails
            try:
                accounts = await self.get_accounts()
                for account in accounts:
                    if account.get("currency") == "BTC":
                        available = account.get("available_balance", {})
                        balance = float(available.get("value", 0))
                        await api_cache.set(cache_key, balance, BALANCE_CACHE_TTL)
                        return balance
            except Exception as fallback_error:
                logger.error(f"Fallback get_accounts() also failed: {fallback_error}")

            return 0.0
        else:
            # Use accounts for HMAC
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
        """
        Get ETH balance

        Uses portfolio breakdown for CDP auth, individual accounts for HMAC auth.
        Both methods are cached to reduce API calls.
        """
        cache_key = "balance_eth"
        cached = await api_cache.get(cache_key)
        if cached is not None:
            return cached

        if self.auth_type == "cdp":
            # Use portfolio breakdown for CDP
            try:
                breakdown = await self.get_portfolio_breakdown()
                spot_positions = breakdown.get("spot_positions", [])
                for pos in spot_positions:
                    if pos.get("asset") == "ETH":
                        balance = float(pos.get("available_to_trade_crypto", 0))
                        await api_cache.set(cache_key, balance, BALANCE_CACHE_TTL)
                        return balance
            except Exception:
                pass
            return 0.0
        else:
            # Use accounts for HMAC
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

    async def invalidate_balance_cache(self):
        """Invalidate balance cache (call after trades)"""
        await api_cache.delete("balance_btc")
        await api_cache.delete("balance_eth")
        await api_cache.delete("balance_usd")
        await api_cache.delete("accounts_list")
        await api_cache.delete("aggregate_btc_value")
        await api_cache.delete("aggregate_usd_value")

    # ===== Product & Market Data Methods =====

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
        """
        Get current price (cached for 10s to reduce API spam)

        CDP auth returns mid-price from best bid/ask.
        HMAC auth returns direct price field.
        """
        cache_key = f"price_{product_id}"
        cached = await api_cache.get(cache_key)
        if cached is not None:
            return cached

        ticker = await self.get_ticker(product_id)

        if self.auth_type == "cdp":
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

    async def get_btc_usd_price(self) -> float:
        """Get current BTC/USD price"""
        return await self.get_current_price("BTC-USD")

    async def get_product_stats(self, product_id: str = "ETH-BTC") -> Dict[str, Any]:
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

        result = await self._request("GET", f"/api/v3/brokerage/products/{product_id}")

        # Extract 24h stats from product data
        stats = {
            "volume_24h": float(result.get("volume_24h", 0)),
            "volume_percentage_change_24h": float(result.get("volume_percentage_change_24h", 0)),
            "price_percentage_change_24h": float(result.get("price_percentage_change_24h", 0))
        }

        # Cache for 5 minutes (volume doesn't change that quickly)
        await api_cache.set(cache_key, stats, 300)
        return stats

    async def get_candles(
        self,
        product_id: str,
        start: int,
        end: int,
        granularity: str = "FIVE_MINUTE"
    ) -> List[Dict[str, Any]]:
        """Get historical candles/OHLCV data"""
        params = {
            "start": str(start),
            "end": str(end),
            "granularity": granularity
        }
        result = await self._request("GET", f"/api/v3/brokerage/products/{product_id}/candles", params=params)
        return result.get("candles", [])

    # ===== Order Methods =====

    async def create_market_order(
        self,
        product_id: str,
        side: str,  # "BUY" or "SELL"
        size: Optional[str] = None,  # Amount of base currency (e.g., ETH)
        funds: Optional[str] = None  # Amount of quote currency (e.g., BTC) to spend
    ) -> Dict[str, Any]:
        """
        Create a market order

        Args:
            product_id: Trading pair (e.g., "ETH-BTC", "AAVE-BTC")
            side: "BUY" or "SELL"
            size: Amount of base currency to buy/sell
            funds: Amount of quote currency to spend (for buy orders)

        Note: Use either size OR funds, not both
        """
        order_config = {
            "market_market_ioc": {}
        }

        # Extract currencies from product_id for proper precision formatting
        if '-' in product_id:
            base_currency, quote_currency = product_id.split('-')
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
            "order_configuration": order_config
        }

        result = await self._request("POST", "/api/v3/brokerage/orders", data=data)
        return result

    async def create_limit_order(
        self,
        product_id: str,
        side: str,  # "BUY" or "SELL"
        limit_price: float,  # Target price
        size: Optional[str] = None,  # Amount of base currency (e.g., ETH)
        funds: Optional[str] = None  # Amount of quote currency (e.g., BTC) to spend
    ) -> Dict[str, Any]:
        """
        Create a limit order (Good-Til-Cancelled)

        Args:
            product_id: Trading pair (e.g., "ETH-BTC", "AAVE-BTC")
            side: "BUY" or "SELL"
            limit_price: Target price for the order
            size: Amount of base currency to buy/sell
            funds: Amount of quote currency to spend (for buy orders)

        Note: Use either size OR funds, not both
        """
        # Extract currencies from product_id for proper precision formatting
        if '-' in product_id:
            base_currency, quote_currency = product_id.split('-')
        else:
            base_currency, quote_currency = "ETH", "BTC"  # fallback

        # Format limit price with proper precision (price is in quote currency)
        formatted_limit_price = format_quote_amount(limit_price, quote_currency)

        order_config = {
            "limit_limit_gtc": {
                "limit_price": formatted_limit_price,
                "post_only": False  # Allow immediate partial fills
            }
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
            "order_configuration": order_config
        }

        result = await self._request("POST", "/api/v3/brokerage/orders", data=data)
        return result

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """
        Get order details

        Args:
            order_id: Coinbase order ID

        Returns:
            Order details including status
        """
        result = await self._request("GET", f"/api/v3/brokerage/orders/historical/{order_id}")

        # CDP returns full dict, HMAC returns nested in "order" key
        if self.auth_type == "hmac" and "order" in result:
            return result.get("order", {})
        return result

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel an open order

        Args:
            order_id: Coinbase order ID

        Returns:
            Cancellation result
        """
        data = {
            "order_ids": [order_id]
        }
        result = await self._request("POST", "/api/v3/brokerage/orders/batch_cancel", data=data)
        return result

    async def list_orders(
        self,
        product_id: Optional[str] = None,
        order_status: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List orders with optional filtering

        Args:
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

        result = await self._request("GET", "/api/v3/brokerage/orders/historical/batch", params=params)
        return result.get("orders", [])

    # ===== Convenience Trading Methods =====

    async def buy_eth_with_btc(self, btc_amount: float, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """
        Buy crypto with specified amount of BTC

        Args:
            btc_amount: Amount of BTC to spend
            product_id: Trading pair (e.g., "ETH-BTC", "AAVE-BTC")

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
        Sell crypto for BTC

        Args:
            eth_amount: Amount of crypto to sell
            product_id: Trading pair (e.g., "ETH-BTC", "AAVE-BTC")

        Returns:
            Order response
        """
        # Extract base currency from product_id (e.g., "ETH" from "ETH-BTC")
        base_currency = product_id.split('-')[0] if '-' in product_id else "ETH"

        return await self.create_market_order(
            product_id=product_id,
            side="SELL",
            size=format_base_amount(eth_amount, base_currency)
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
        # Extract base currency from product_id
        base_currency = product_id.split('-')[0] if '-' in product_id else "ETH"

        return await self.create_market_order(
            product_id=product_id,
            side="SELL",
            size=format_base_amount(base_amount, base_currency)
        )

    # ===== Portfolio Aggregation for Bot Budgeting =====

    async def calculate_aggregate_btc_value(self) -> float:
        """
        Calculate aggregate BTC value - simplified to just return actual BTC balance.
        This is used for bot budget allocation.

        Returns:
            Total BTC balance from Coinbase
        """
        # SIMPLIFIED: Just return the actual BTC balance from Coinbase
        # This resolves budget calculation issues where bots couldn't analyze all pairs
        btc_balance = await self.get_balance("BTC")
        logger.info(f"✅ BTC balance from Coinbase: {btc_balance:.8f} BTC")
        return btc_balance

    async def calculate_aggregate_usd_value(self) -> float:
        """
        Calculate aggregate USD value of entire portfolio (USD + all pairs converted to USD).
        This is used for USD-based bot budget allocation.

        Returns:
            Total USD value across all holdings
        """
        # Check cache first to reduce API spam
        cache_key = "aggregate_usd_value"
        cached = await api_cache.get(cache_key)
        if cached is not None:
            logger.info(f"✅ Using cached aggregate USD value: ${cached:.2f}")
            return cached

        # Use get_accounts() as primary method (more reliable than portfolio endpoint)
        try:
            accounts = await self.get_accounts()
            btc_usd_price = await self.get_btc_usd_price()
            total_usd_value = 0.0

            for account in accounts:
                currency = account.get("currency", "")
                available_str = account.get("available_balance", {}).get("value", "0")
                available = float(available_str)

                if available == 0:
                    continue

                # Convert all currencies to USD value
                if currency in ["USD", "USDC"]:
                    total_usd_value += available
                elif currency == "BTC":
                    total_usd_value += available * btc_usd_price
                else:
                    try:
                        usd_price = await self.get_current_price(f"{currency}-USD")
                        total_usd_value += available * usd_price
                    except Exception:
                        pass  # Skip assets we can't price

            # Cache the result for 30 seconds
            await api_cache.set(cache_key, total_usd_value, ttl_seconds=30)
            logger.info(f"✅ Calculated aggregate USD value: ${total_usd_value:.2f}")
            return total_usd_value

        except Exception as e:
            logger.error(f"Error calculating aggregate USD value using accounts endpoint: {e}")
            # Raise exception to trigger conservative fallback in calling code
            raise Exception(f"Failed to calculate aggregate USD value: accounts API failed ({e})")

    # ===== Connection Test =====

    async def test_connection(self) -> bool:
        """Test if API connection works"""
        try:
            await self.get_accounts()
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
