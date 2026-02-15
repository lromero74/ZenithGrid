"""
Unified Coinbase Advanced Trade API Client (Refactored)

Wrapper class that coordinates all Coinbase API modules.
Maintains backward compatibility with existing code.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.coinbase_api import auth
from app.coinbase_api import account_balance_api
from app.coinbase_api import market_data_api
from app.coinbase_api import order_api
from app.coinbase_api import perpetuals_api

logger = logging.getLogger(__name__)

# Global rate limiter state for Coinbase API
# Coinbase allows ~10 requests/second, we'll use 7/sec to be safe
_last_request_time = 0
_rate_limit_lock = asyncio.Lock()
_min_interval = 0.15  # 150ms between requests = ~6.6 req/sec


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
        api_secret: Optional[str] = None,
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
            self.key_name, self.private_key = auth.load_cdp_credentials_from_file(key_file_path)
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

            if (
                hasattr(settings, "coinbase_cdp_key_name")
                and settings.coinbase_cdp_key_name
                and hasattr(settings, "coinbase_cdp_private_key")
                and settings.coinbase_cdp_private_key
            ):
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

    async def _request(
        self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make authenticated request with rate limiting"""
        global _last_request_time

        # Rate limiting: ensure minimum interval between requests
        async with _rate_limit_lock:
            now = time.time()
            time_since_last = now - _last_request_time

            if time_since_last < _min_interval:
                delay = _min_interval - time_since_last
                await asyncio.sleep(delay)

            _last_request_time = time.time()

        return await auth.authenticated_request(
            method,
            endpoint,
            self.auth_type,
            key_name=getattr(self, "key_name", None),
            private_key=getattr(self, "private_key", None),
            api_key=getattr(self, "api_key", None),
            api_secret=getattr(self, "api_secret", None),
            params=params,
            data=data,
        )

    # ===== Account & Balance Methods =====

    async def get_accounts(self, force_fresh: bool = False) -> List[Dict[str, Any]]:
        """Get all accounts (cached to reduce API calls unless force_fresh=True)"""
        return await account_balance_api.get_accounts(self._request, force_fresh)

    async def get_account(self, account_id: str) -> Dict[str, Any]:
        """Get specific account details"""
        return await account_balance_api.get_account(self._request, account_id)

    async def get_portfolios(self) -> List[Dict[str, Any]]:
        """Get list of all portfolios"""
        return await account_balance_api.get_portfolios(self._request)

    async def get_portfolio_breakdown(self, portfolio_uuid: Optional[str] = None) -> dict:
        """Get portfolio breakdown with all spot positions"""
        return await account_balance_api.get_portfolio_breakdown(self._request, portfolio_uuid)

    async def get_btc_balance(self) -> float:
        """Get BTC balance"""
        return await account_balance_api.get_btc_balance(self._request, self.auth_type)

    async def get_eth_balance(self) -> float:
        """Get ETH balance"""
        return await account_balance_api.get_eth_balance(self._request, self.auth_type)

    async def get_usd_balance(self) -> float:
        """Get USD balance"""
        return await account_balance_api.get_usd_balance(self._request)

    async def get_usdc_balance(self) -> float:
        """Get USDC balance"""
        return await account_balance_api.get_usdc_balance(self._request)

    async def get_usdt_balance(self) -> float:
        """Get USDT balance"""
        return await account_balance_api.get_usdt_balance(self._request)

    async def invalidate_balance_cache(self):
        """Invalidate balance cache (call after trades)"""
        await account_balance_api.invalidate_balance_cache()

    async def calculate_aggregate_btc_value(self, bypass_cache: bool = False) -> float:
        """
        Calculate total BTC value of entire account (available BTC + liquidation value of all positions)

        Args:
            bypass_cache: If True, skip cache and force fresh calculation (use for critical operations)
        """
        return await account_balance_api.calculate_aggregate_btc_value(
            self._request, self.auth_type, self.get_current_price, bypass_cache=bypass_cache
        )

    async def calculate_aggregate_usd_value(self) -> float:
        """Calculate aggregate USD value of entire portfolio"""
        return await account_balance_api.calculate_aggregate_usd_value(
            self._request, self.get_btc_usd_price, self.get_current_price
        )

    # ===== Product & Market Data Methods =====

    async def list_products(self) -> List[Dict[str, Any]]:
        """Get all available products/trading pairs"""
        return await market_data_api.list_products(self._request)

    async def get_product(self, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Get product details"""
        return await market_data_api.get_product(self._request, product_id)

    async def get_ticker(self, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Get current ticker/price for a product"""
        return await market_data_api.get_ticker(self._request, product_id)

    async def get_current_price(self, product_id: str = "ETH-BTC") -> float:
        """Get current price (cached for 10s to reduce API spam)"""
        return await market_data_api.get_current_price(self._request, self.auth_type, product_id)

    async def get_btc_usd_price(self) -> float:
        """Get current BTC/USD price"""
        return await market_data_api.get_btc_usd_price(self._request, self.auth_type)

    async def get_eth_usd_price(self) -> float:
        """Get current ETH/USD price"""
        return await market_data_api.get_eth_usd_price(self._request, self.auth_type)

    async def get_product_stats(self, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Get 24-hour stats for a product"""
        return await market_data_api.get_product_stats(self._request, product_id)

    async def get_candles(
        self, product_id: str, start: int, end: int, granularity: str = "FIVE_MINUTE"
    ) -> List[Dict[str, Any]]:
        """Get historical candles/OHLCV data"""
        return await market_data_api.get_candles(self._request, product_id, start, end, granularity)

    async def get_product_book(self, product_id: str, limit: int = 50) -> Dict[str, Any]:
        """Get order book (Level 2) for a product"""
        return await market_data_api.get_product_book(self._request, product_id, limit)

    # ===== Order Methods =====

    async def create_market_order(
        self, product_id: str, side: str, size: Optional[str] = None, funds: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a market order"""
        return await order_api.create_market_order(self._request, product_id, side, size, funds)

    async def create_limit_order(
        self,
        product_id: str,
        side: str,
        limit_price: float,
        size: Optional[str] = None,
        funds: Optional[str] = None,
        time_in_force: str = "gtc",
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Create a limit order with configurable time-in-force (GTC or GTD)"""
        return await order_api.create_limit_order(
            self._request, product_id, side, limit_price, size, funds, time_in_force, end_time
        )

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get order details"""
        return await order_api.get_order(self._request, self.auth_type, order_id)

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an open order"""
        return await order_api.cancel_order(self._request, order_id)

    async def edit_order(
        self, order_id: str, price: Optional[str] = None, size: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Edit an existing order's price or size.

        Only works for limit orders with time_in_force = GTC (good-till-cancelled).

        Queue position behavior:
        - Loses position if increasing size or changing price
        - Keeps position if only decreasing size

        Args:
            order_id: The order ID to edit
            price: New limit price (optional)
            size: New order size (optional)

        Returns:
            Dict with edited order details
        """
        return await order_api.edit_order(self._request, order_id, price, size)

    async def edit_order_preview(
        self, order_id: str, price: Optional[str] = None, size: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Preview the results of editing an order before actually editing it.

        Args:
            order_id: The order ID to preview editing
            price: New limit price (optional)
            size: New order size (optional)

        Returns:
            Dict with preview details including slippage, fees, etc.
        """
        return await order_api.edit_order_preview(self._request, order_id, price, size)

    async def list_orders(
        self, product_id: Optional[str] = None, order_status: Optional[List[str]] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List orders with optional filtering"""
        return await order_api.list_orders(self._request, product_id, order_status, limit)

    # ===== Convenience Trading Methods =====

    async def buy_eth_with_btc(self, btc_amount: float, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Buy crypto with specified amount of BTC"""
        return await order_api.buy_eth_with_btc(self._request, btc_amount, product_id)

    async def sell_eth_for_btc(self, eth_amount: float, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Sell crypto for BTC"""
        return await order_api.sell_eth_for_btc(self._request, eth_amount, product_id)

    async def buy_with_usd(self, usd_amount: float, product_id: str) -> Dict[str, Any]:
        """Buy crypto with specified amount of USD"""
        return await order_api.buy_with_usd(self._request, usd_amount, product_id)

    async def sell_for_usd(self, base_amount: float, product_id: str) -> Dict[str, Any]:
        """Sell crypto for USD"""
        return await order_api.sell_for_usd(self._request, base_amount, product_id)

    # ===== Perpetual Futures (INTX) Methods =====

    async def get_perps_portfolio_summary(self, portfolio_uuid: str) -> Dict[str, Any]:
        """Get perpetuals portfolio summary (margin, balances, positions)"""
        return await perpetuals_api.get_perps_portfolio_summary(self._request, portfolio_uuid)

    async def list_perps_positions(self, portfolio_uuid: str) -> List[Dict[str, Any]]:
        """List all open perpetual futures positions"""
        return await perpetuals_api.list_perps_positions(self._request, portfolio_uuid)

    async def get_perps_position(self, portfolio_uuid: str, symbol: str) -> Dict[str, Any]:
        """Get a specific perpetual futures position"""
        return await perpetuals_api.get_perps_position(self._request, portfolio_uuid, symbol)

    async def get_perps_balances(self, portfolio_uuid: str) -> Dict[str, Any]:
        """Get perpetuals portfolio balances"""
        return await perpetuals_api.get_perps_portfolio_balances(self._request, portfolio_uuid)

    async def list_perps_products(self) -> List[Dict[str, Any]]:
        """List available INTX perpetual products (e.g., BTC-PERP-INTX)"""
        return await perpetuals_api.list_perpetual_products(self._request)

    async def create_perps_order(
        self,
        product_id: str,
        side: str,
        base_size: str,
        leverage: Optional[str] = None,
        margin_type: Optional[str] = None,
        tp_price: Optional[str] = None,
        sl_price: Optional[str] = None,
        limit_price: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a perpetual futures order with optional bracket TP/SL.

        Args:
            product_id: e.g., "BTC-PERP-INTX"
            side: "BUY" (long) or "SELL" (short)
            base_size: Position size in base currency
            leverage: Leverage multiplier (e.g., "3")
            margin_type: "CROSS" or "ISOLATED"
            tp_price: Take profit limit price
            sl_price: Stop loss trigger price
            limit_price: Entry limit price (None = market)
        """
        return await order_api.create_bracket_order(
            self._request,
            product_id=product_id,
            side=side,
            base_size=base_size,
            limit_price=limit_price,
            tp_price=tp_price,
            sl_price=sl_price,
            leverage=leverage,
            margin_type=margin_type,
        )

    async def close_perps_position(
        self, product_id: str, base_size: str, side: str
    ) -> Dict[str, Any]:
        """
        Close a perpetual futures position with a market order.

        Args:
            product_id: e.g., "BTC-PERP-INTX"
            base_size: Size to close
            side: Opposite side of position ("SELL" to close long, "BUY" to close short)
        """
        return await order_api.create_market_order(
            self._request, product_id=product_id, side=side, size=base_size
        )

    # ===== Connection Test =====

    async def test_connection(self) -> bool:
        """Test if API connection works"""
        return await market_data_api.test_connection(self._request)
