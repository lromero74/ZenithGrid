"""
ExchangeClient Abstract Base Class

This module defines the interface that all exchange clients (CEX and DEX) must implement.
By adhering to this interface, trading strategies can work seamlessly across different
exchange types without modification.

The interface is designed to match the existing CoinbaseClient API to minimize refactoring
while still being generic enough to support DEX implementations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ExchangeClient(ABC):
    """
    Abstract base class for all exchange clients (centralized and decentralized).

    All exchange implementations must provide these methods to ensure compatibility
    with the existing trading engine, strategies, and position management systems.

    Design Philosophy:
    - Methods return standardized data structures (dicts with consistent keys)
    - All prices are returned as floats in quote currency
    - All amounts/sizes are returned as floats
    - Order IDs can be exchange-specific (CEX order ID vs DEX transaction hash)
    - Async methods support high-performance concurrent operations
    """

    # ========================================
    # ACCOUNT & BALANCE METHODS
    # ========================================

    @abstractmethod
    async def get_accounts(self, force_fresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get all accounts/wallets for this exchange.

        For CEX: Returns Coinbase accounts
        For DEX: Returns wallet information

        Args:
            force_fresh: If True, bypass cache and fetch fresh data

        Returns:
            List of account dictionaries with structure:
            [
                {
                    "uuid": "account-id",
                    "currency": "BTC",
                    "available_balance": {"value": "0.5", "currency": "BTC"},
                    ...
                }
            ]
        """
        pass

    @abstractmethod
    async def get_account(self, account_id: str) -> Dict[str, Any]:
        """Get details for a specific account."""
        pass

    @abstractmethod
    async def get_btc_balance(self) -> float:
        """
        Get available BTC balance.

        Returns:
            Float representing BTC balance
        """
        pass

    @abstractmethod
    async def get_eth_balance(self) -> float:
        """Get available ETH balance."""
        pass

    @abstractmethod
    async def get_usd_balance(self) -> float:
        """Get available USD balance (or stablecoin equivalent for DEX)."""
        pass

    @abstractmethod
    async def invalidate_balance_cache(self):
        """
        Invalidate cached balance data to force fresh fetch on next call.

        Important after trades to ensure accurate balance reporting.
        """
        pass

    @abstractmethod
    async def calculate_aggregate_btc_value(self) -> float:
        """
        Calculate total portfolio value in BTC.

        Should include:
        - Available BTC balance
        - BTC value of all altcoin positions in BTC pairs

        For BTC-based bots, this determines available trading budget.

        Returns:
            Total BTC value as float
        """
        pass

    @abstractmethod
    async def calculate_aggregate_usd_value(self) -> float:
        """
        Calculate total portfolio value in USD.

        Should include:
        - Available USD balance
        - USD value of all crypto holdings

        Returns:
            Total USD value as float
        """
        pass

    # ========================================
    # MARKET DATA METHODS
    # ========================================

    @abstractmethod
    async def list_products(self) -> List[Dict[str, Any]]:
        """
        List all available trading pairs.

        Returns:
            List of product/pair dictionaries:
            [
                {
                    "product_id": "ETH-BTC",
                    "base_currency": "ETH",
                    "quote_currency": "BTC",
                    "base_min_size": "0.001",
                    "base_max_size": "10000",
                    ...
                }
            ]
        """
        pass

    @abstractmethod
    async def get_product(self, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """
        Get details for a specific trading pair.

        Args:
            product_id: Trading pair (e.g., "ETH-BTC", "ADA-USD")

        Returns:
            Product details dictionary
        """
        pass

    @abstractmethod
    async def get_ticker(self, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """
        Get real-time ticker data for a product.

        Returns:
            Ticker dict with price, volume, etc.
        """
        pass

    @abstractmethod
    async def get_current_price(self, product_id: str = "ETH-BTC") -> float:
        """
        Get current market price for a trading pair.

        Args:
            product_id: Trading pair

        Returns:
            Current price as float in quote currency
        """
        pass

    @abstractmethod
    async def get_btc_usd_price(self) -> float:
        """
        Get current BTC-USD price.

        Used for portfolio valuation and conversions.

        Returns:
            BTC price in USD as float
        """
        pass

    @abstractmethod
    async def get_product_stats(self, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """
        Get 24-hour statistics for a product.

        Returns:
            Stats dict with open, high, low, close, volume
        """
        pass

    @abstractmethod
    async def get_candles(
        self,
        product_id: str,
        start: int,
        end: int,
        granularity: str,
    ) -> List[Dict[str, Any]]:
        """
        Get historical OHLCV candle data.

        Critical for technical analysis strategies (MACD, RSI, Bollinger, etc.)

        Args:
            product_id: Trading pair
            start: Unix timestamp (seconds) for start time
            end: Unix timestamp (seconds) for end time
            granularity: Candle interval ("ONE_MINUTE", "FIVE_MINUTE", "ONE_HOUR", etc.)

        Returns:
            List of candle dictionaries:
            [
                {
                    "start": "1234567890",  # Unix timestamp string
                    "low": "0.00012",
                    "high": "0.00015",
                    "open": "0.00013",
                    "close": "0.00014",
                    "volume": "1000.5"
                },
                ...
            ]
        """
        pass

    # ========================================
    # ORDER EXECUTION METHODS
    # ========================================

    @abstractmethod
    async def create_market_order(
        self,
        product_id: str,
        side: str,
        size: Optional[str] = None,
        funds: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create and execute a market order immediately at current market price.

        Args:
            product_id: Trading pair (e.g., "ETH-BTC")
            side: "BUY" or "SELL"
            size: Amount of base currency (e.g., "0.5" ETH). Use either size OR funds.
            funds: Amount of quote currency (e.g., "0.001" BTC). Use either size OR funds.

        Returns:
            Order response dict:
            {
                "success": True,
                "order_id": "...",  # CEX: order ID, DEX: transaction hash
                "product_id": "ETH-BTC",
                "side": "BUY",
                "filled_size": "0.5",  # Actual amount filled
                "filled_value": "0.001",  # Actual quote spent
                "average_filled_price": "0.002"  # Average fill price
            }
        """
        pass

    @abstractmethod
    async def create_limit_order(
        self,
        product_id: str,
        side: str,
        limit_price: float,
        size: Optional[str] = None,
        funds: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a limit order at a specific price.

        For CEX: Standard limit order on order book
        For DEX: May not be supported (depends on DEX type)

        Args:
            product_id: Trading pair
            side: "BUY" or "SELL"
            limit_price: Target price for execution
            size: Amount of base currency
            funds: Amount of quote currency

        Returns:
            Order response dict (same structure as market order)
        """
        pass

    @abstractmethod
    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """
        Get status and details of an order.

        For CEX: Query order by ID
        For DEX: Query transaction by hash

        Args:
            order_id: Order identifier (order ID or tx hash)

        Returns:
            Order details dict with status, fills, etc.
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel a pending order.

        For CEX: Cancel open order
        For DEX: May not be possible (tx already broadcast)

        Args:
            order_id: Order to cancel

        Returns:
            Cancellation response dict
        """
        pass

    @abstractmethod
    async def list_orders(
        self,
        product_id: Optional[str] = None,
        order_status: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List orders, optionally filtered.

        Args:
            product_id: Filter by trading pair
            order_status: Filter by status (["OPEN"], ["FILLED"], etc.)
            limit: Max number of orders to return

        Returns:
            List of order dicts
        """
        pass

    # ========================================
    # CONVENIENCE TRADING METHODS
    # ========================================

    @abstractmethod
    async def buy_eth_with_btc(self, btc_amount: float, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """
        Convenience method: Buy ETH using BTC.

        Args:
            btc_amount: Amount of BTC to spend
            product_id: Trading pair (default ETH-BTC)

        Returns:
            Order response dict
        """
        pass

    @abstractmethod
    async def sell_eth_for_btc(self, eth_amount: float, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """
        Convenience method: Sell ETH for BTC.

        Args:
            eth_amount: Amount of ETH to sell
            product_id: Trading pair (default ETH-BTC)

        Returns:
            Order response dict
        """
        pass

    @abstractmethod
    async def buy_with_usd(self, usd_amount: float, product_id: str) -> Dict[str, Any]:
        """
        Convenience method: Buy crypto with USD.

        Args:
            usd_amount: Amount of USD to spend
            product_id: Trading pair (e.g., "BTC-USD", "ETH-USD")

        Returns:
            Order response dict
        """
        pass

    @abstractmethod
    async def sell_for_usd(self, base_amount: float, product_id: str) -> Dict[str, Any]:
        """
        Convenience method: Sell crypto for USD.

        Args:
            base_amount: Amount of base currency to sell
            product_id: Trading pair

        Returns:
            Order response dict
        """
        pass

    # ========================================
    # EXCHANGE METADATA
    # ========================================

    @abstractmethod
    def get_exchange_type(self) -> str:
        """
        Return the exchange type.

        Returns:
            "cex" for centralized exchanges (Coinbase, Binance, etc.)
            "dex" for decentralized exchanges (Uniswap, PancakeSwap, etc.)
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Test connectivity to the exchange.

        Returns:
            True if connection successful, False otherwise
        """
        pass
