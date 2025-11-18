"""
Coinbase CDP (Developer Platform) API Client

Uses EC private key authentication with JWT tokens.
This is the new recommended authentication method for Coinbase Advanced Trade API.
"""

import json
import time
from typing import Any, Dict, List, Optional

import httpx
import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from app.cache import api_cache
from app.precision import format_quote_amount, format_base_amount


class CoinbaseCDPClient:
    """Coinbase Advanced Trade API Client with CDP Authentication"""

    BASE_URL = "https://api.coinbase.com"

    def __init__(self, key_file_path: Optional[str] = None, key_name: Optional[str] = None, private_key: Optional[str] = None):
        """
        Initialize CDP client

        Args:
            key_file_path: Path to cdp_api_key.json file
            key_name: API key name (from JSON file's 'name' field)
            private_key: EC private key PEM string (from JSON file's 'privateKey' field)
        """
        if key_file_path:
            self._load_from_file(key_file_path)
        elif key_name and private_key:
            self.key_name = key_name
            self.private_key = private_key
        else:
            raise ValueError("Must provide either key_file_path or both key_name and private_key")

    def _load_from_file(self, file_path: str):
        """Load credentials from CDP JSON key file"""
        with open(file_path, 'r') as f:
            data = json.load(f)

        self.key_name = data['name']
        self.private_key = data['privateKey']

    def _generate_jwt(self, request_method: str, request_path: str) -> str:
        """
        Generate JWT token for API request

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

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make authenticated request to Coinbase CDP API"""
        url = f"{self.BASE_URL}{endpoint}"

        # Generate JWT for this specific request
        jwt_token = self._generate_jwt(method, endpoint)

        headers = {
            "Authorization": f"Bearer {jwt_token}",
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

    # --- All the same API methods as the original client ---

    async def get_accounts(self) -> List[Dict[str, Any]]:
        """Get all accounts"""
        result = await self._request("GET", "/api/v3/brokerage/accounts")
        return result.get("accounts", [])

    async def get_account(self, account_id: str) -> Dict[str, Any]:
        """Get specific account details"""
        result = await self._request("GET", f"/api/v3/brokerage/accounts/{account_id}")
        return result.get("account", {})

    async def get_portfolio_breakdown(self, portfolio_uuid: str = "5b4aea83-9bf7-5ff0-9390-87153d9c1729") -> dict:
        """Get portfolio breakdown with all spot positions"""
        result = await self._request("GET", f"/api/v3/brokerage/portfolios/{portfolio_uuid}")
        return result.get("breakdown", {})

    async def get_btc_balance(self) -> float:
        """Get BTC balance from portfolio breakdown"""
        try:
            breakdown = await self.get_portfolio_breakdown()
            spot_positions = breakdown.get("spot_positions", [])
            for pos in spot_positions:
                if pos.get("asset") == "BTC":
                    return float(pos.get("available_to_trade_crypto", 0))
        except Exception:
            pass
        return 0.0

    async def get_eth_balance(self) -> float:
        """Get ETH balance from portfolio breakdown"""
        try:
            breakdown = await self.get_portfolio_breakdown()
            spot_positions = breakdown.get("spot_positions", [])
            for pos in spot_positions:
                if pos.get("asset") == "ETH":
                    return float(pos.get("available_to_trade_crypto", 0))
        except Exception:
            pass
        return 0.0

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
        """Get current price (mid-price from best bid/ask)"""
        ticker = await self.get_ticker(product_id)

        # Ticker returns best_bid and best_ask, calculate mid-price
        best_bid = float(ticker.get("best_bid", 0))
        best_ask = float(ticker.get("best_ask", 0))

        if best_bid > 0 and best_ask > 0:
            return (best_bid + best_ask) / 2.0

        # Fallback: use most recent trade price
        trades = ticker.get("trades", [])
        if trades:
            return float(trades[0].get("price", 0))

        return 0.0

    async def get_btc_usd_price(self) -> float:
        """Get current BTC/USD price"""
        return await self.get_current_price("BTC-USD")

    async def get_candles(
        self,
        product_id: str,
        start: int,
        end: int,
        granularity: str = "FIVE_MINUTE"
    ) -> List[Dict[str, Any]]:
        """Get historical candles"""
        params = {
            "start": str(start),
            "end": str(end),
            "granularity": granularity
        }
        result = await self._request("GET", f"/api/v3/brokerage/products/{product_id}/candles", params=params)
        return result.get("candles", [])

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
        import time

        order_config = {
            "market_market_ioc": {}
        }

        # Extract currencies from product_id for proper precision formatting
        if '-' in product_id:
            base_currency, quote_currency = product_id.split('-')
        else:
            base_currency, quote_currency = "ETH", "BTC"  # fallback

        if size:
            # Format base amount with proper precision
            formatted_size = format_base_amount(float(size), base_currency)
            order_config["market_market_ioc"]["base_size"] = formatted_size
        elif funds:
            # Format quote amount with proper precision
            formatted_funds = format_quote_amount(float(funds), quote_currency)
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
        import time

        order_config = {
            "limit_limit_gtc": {
                "limit_price": str(limit_price),
                "post_only": False  # Allow immediate partial fills
            }
        }

        # Extract currencies from product_id for proper precision formatting
        if '-' in product_id:
            base_currency, quote_currency = product_id.split('-')
        else:
            base_currency, quote_currency = "ETH", "BTC"  # fallback

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

    async def buy_eth_with_btc(self, btc_amount: float, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """
        Buy crypto with specified amount of BTC

        Args:
            btc_amount: Amount of BTC to spend
            product_id: Trading pair (e.g., "ETH-BTC", "AAVE-BTC")

        Returns:
            Order response
        """
        # Extract quote currency from product_id (e.g., "BTC" from "ETH-BTC")
        quote_currency = product_id.split('-')[1] if '-' in product_id else "BTC"

        return await self.create_market_order(
            product_id=product_id,
            side="BUY",
            funds=format_quote_amount(btc_amount, quote_currency)
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

    async def test_connection(self) -> bool:
        """Test if API connection works"""
        try:
            await self.get_accounts()
            return True
        except Exception:
            return False
