"""
Coinbase Adapter

Wraps the existing CoinbaseClient to implement the ExchangeClient interface.
This adapter pattern allows us to use the established CoinbaseClient implementation
without modification while providing the standard interface expected by trading strategies.

All methods simply delegate to the underlying CoinbaseClient instance.
"""

from typing import Any, Dict, List, Optional

from app.coinbase_unified_client import CoinbaseClient
from app.exchange_clients.base import ExchangeClient


class CoinbaseAdapter(ExchangeClient):
    """
    Adapter that wraps CoinbaseClient to implement the ExchangeClient interface.

    This class uses the Adapter design pattern to make the existing CoinbaseClient
    compatible with the new ExchangeClient abstraction without requiring changes
    to the original CoinbaseClient implementation.

    Usage:
        coinbase = CoinbaseClient(key_name="...", private_key="...")
        exchange = CoinbaseAdapter(coinbase)
        # Now 'exchange' can be used anywhere an ExchangeClient is expected
    """

    def __init__(self, coinbase_client: CoinbaseClient):
        """
        Initialize the adapter with a CoinbaseClient instance.

        Args:
            coinbase_client: Configured CoinbaseClient instance
        """
        self._client = coinbase_client

    # ========================================
    # ACCOUNT & BALANCE METHODS
    # ========================================

    async def get_accounts(self, force_fresh: bool = False) -> List[Dict[str, Any]]:
        """Get all Coinbase accounts."""
        return await self._client.get_accounts(force_fresh=force_fresh)

    async def get_account(self, account_id: str) -> Dict[str, Any]:
        """Get details for a specific account."""
        return await self._client.get_account(account_id)

    async def get_btc_balance(self) -> float:
        """Get available BTC balance."""
        return await self._client.get_btc_balance()

    async def get_eth_balance(self) -> float:
        """Get available ETH balance."""
        return await self._client.get_eth_balance()

    async def get_usd_balance(self) -> float:
        """Get available USD balance."""
        return await self._client.get_usd_balance()

    async def invalidate_balance_cache(self):
        """Invalidate cached balance data."""
        await self._client.invalidate_balance_cache()

    async def calculate_aggregate_btc_value(self) -> float:
        """Calculate total portfolio value in BTC."""
        return await self._client.calculate_aggregate_btc_value()

    async def calculate_aggregate_usd_value(self) -> float:
        """Calculate total portfolio value in USD."""
        return await self._client.calculate_aggregate_usd_value()

    # ========================================
    # MARKET DATA METHODS
    # ========================================

    async def list_products(self) -> List[Dict[str, Any]]:
        """List all available trading pairs."""
        return await self._client.list_products()

    async def get_product(self, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Get details for a specific trading pair."""
        return await self._client.get_product(product_id)

    async def get_ticker(self, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Get real-time ticker data."""
        return await self._client.get_ticker(product_id)

    async def get_current_price(self, product_id: str = "ETH-BTC") -> float:
        """Get current market price."""
        return await self._client.get_current_price(product_id)

    async def get_btc_usd_price(self) -> float:
        """Get current BTC-USD price."""
        return await self._client.get_btc_usd_price()

    async def get_product_stats(self, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Get 24-hour statistics."""
        return await self._client.get_product_stats(product_id)

    async def get_candles(
        self,
        product_id: str,
        start: int,
        end: int,
        granularity: str,
    ) -> List[Dict[str, Any]]:
        """Get historical OHLCV candle data."""
        return await self._client.get_candles(
            product_id=product_id,
            start=start,
            end=end,
            granularity=granularity,
        )

    # ========================================
    # ORDER EXECUTION METHODS
    # ========================================

    async def create_market_order(
        self,
        product_id: str,
        side: str,
        size: Optional[str] = None,
        funds: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create and execute a market order."""
        return await self._client.create_market_order(
            product_id=product_id,
            side=side,
            size=size,
            funds=funds,
        )

    async def create_limit_order(
        self,
        product_id: str,
        side: str,
        limit_price: float,
        size: Optional[str] = None,
        funds: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a limit order."""
        return await self._client.create_limit_order(
            product_id=product_id,
            side=side,
            limit_price=limit_price,
            size=size,
            funds=funds,
        )

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get status and details of an order."""
        return await self._client.get_order(order_id)

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel a pending order."""
        return await self._client.cancel_order(order_id)

    async def list_orders(
        self,
        product_id: Optional[str] = None,
        order_status: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List orders, optionally filtered."""
        return await self._client.list_orders(
            product_id=product_id,
            order_status=order_status,
            limit=limit,
        )

    # ========================================
    # CONVENIENCE TRADING METHODS
    # ========================================

    async def buy_eth_with_btc(self, btc_amount: float, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Buy ETH using BTC."""
        return await self._client.buy_eth_with_btc(btc_amount, product_id)

    async def sell_eth_for_btc(self, eth_amount: float, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Sell ETH for BTC."""
        return await self._client.sell_eth_for_btc(eth_amount, product_id)

    async def buy_with_usd(self, usd_amount: float, product_id: str) -> Dict[str, Any]:
        """Buy crypto with USD."""
        return await self._client.buy_with_usd(usd_amount, product_id)

    async def sell_for_usd(self, base_amount: float, product_id: str) -> Dict[str, Any]:
        """Sell crypto for USD."""
        return await self._client.sell_for_usd(base_amount, product_id)

    # ========================================
    # EXCHANGE METADATA
    # ========================================

    def get_exchange_type(self) -> str:
        """Return 'cex' for Coinbase (centralized exchange)."""
        return "cex"

    async def test_connection(self) -> bool:
        """Test connectivity to Coinbase."""
        return await self._client.test_connection()

    # ========================================
    # ADDITIONAL COINBASE-SPECIFIC METHODS
    # ========================================
    # These are not part of ExchangeClient interface but may be needed
    # for backward compatibility with existing code

    async def get_portfolios(self) -> List[Dict[str, Any]]:
        """Get Coinbase portfolios (pass-through method)."""
        return await self._client.get_portfolios()

    async def get_portfolio_breakdown(self, portfolio_uuid: Optional[str] = None) -> dict:
        """Get portfolio breakdown (pass-through method)."""
        return await self._client.get_portfolio_breakdown(portfolio_uuid)
