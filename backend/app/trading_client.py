"""
Quote-currency agnostic trading client wrapper

Wraps ExchangeClient to provide currency-agnostic buy/sell operations.
Automatically detects quote currency and calls appropriate methods.

Works with any exchange type (CEX or DEX) that implements ExchangeClient interface.
"""

import logging
from typing import Any, Dict

from app.exchange_clients.base import ExchangeClient
from app.currency_utils import get_quote_currency

logger = logging.getLogger(__name__)


class TradingClient:
    """
    Currency-agnostic trading client

    Provides buy/sell methods that automatically detect quote currency
    and call the appropriate exchange API methods.

    Works with any ExchangeClient implementation (Coinbase CEX, DEX, etc.)
    """

    def __init__(self, exchange: ExchangeClient):
        """
        Initialize with exchange client

        Args:
            exchange: ExchangeClient instance (CoinbaseAdapter, DEXClient, etc.)
        """
        self.exchange = exchange

    async def get_balance(self, currency: str) -> float:
        """
        Get balance for any currency

        Args:
            currency: Currency code (e.g., "BTC", "USD", "USDT", "ETH")

        Returns:
            Balance amount
        """
        if currency == "BTC":
            return await self.exchange.get_btc_balance()
        elif currency in ("USD", "USDT", "USDC"):
            return await self.exchange.get_usd_balance()
        else:
            raise ValueError(
                f"Unsupported quote currency: {currency}. "
                f"Supported: BTC, USD, USDT, USDC."
            )

    async def get_quote_balance(self, product_id: str) -> float:
        """
        Get balance for the quote currency of a trading pair

        Args:
            product_id: Trading pair (e.g., "ETH-BTC", "ADA-USD")

        Returns:
            Quote currency balance
        """
        quote_currency = get_quote_currency(product_id)
        return await self.get_balance(quote_currency)

    async def buy(self, product_id: str, quote_amount: float) -> Dict[str, Any]:
        """
        Buy base currency with quote currency (market order)

        Automatically detects quote currency and uses appropriate method.

        Args:
            product_id: Trading pair (e.g., "ETH-BTC", "ADA-USD")
            quote_amount: Amount of quote currency to spend

        Returns:
            Order response from exchange
        """
        quote_currency = get_quote_currency(product_id)

        if quote_currency == "BTC":
            # Buy with BTC
            return await self.exchange.buy_eth_with_btc(btc_amount=quote_amount, product_id=product_id)
        elif quote_currency in ("USD", "USDT", "USDC"):
            # Buy with USD/USDT/USDC (stablecoins treated as USD)
            return await self.exchange.buy_with_usd(usd_amount=quote_amount, product_id=product_id)
        else:
            raise ValueError(f"Unsupported quote currency: {quote_currency}")

    async def buy_limit(self, product_id: str, limit_price: float, quote_amount: float) -> Dict[str, Any]:
        """
        Buy base currency with quote currency using a limit order

        Args:
            product_id: Trading pair (e.g., "ETH-BTC", "ADA-USD")
            limit_price: Limit price for the order
            quote_amount: Amount of quote currency to spend

        Returns:
            Order response from exchange
        """
        return await self.exchange.create_limit_order(
            product_id=product_id, side="BUY", limit_price=limit_price, funds=str(quote_amount)
        )

    async def sell_limit(self, product_id: str, limit_price: float, base_amount: float) -> Dict[str, Any]:
        """
        Sell base currency for quote currency using a limit order

        Args:
            product_id: Trading pair (e.g., "ETH-BTC", "ADA-USD")
            limit_price: Limit price for the order
            base_amount: Amount of base currency to sell

        Returns:
            Order response from exchange
        """
        return await self.exchange.create_limit_order(
            product_id=product_id, side="SELL", limit_price=limit_price, size=str(base_amount)
        )

    async def sell(self, product_id: str, base_amount: float) -> Dict[str, Any]:
        """
        Sell base currency for quote currency

        Automatically detects quote currency and uses appropriate method.

        Args:
            product_id: Trading pair (e.g., "ETH-BTC", "ADA-USD")
            base_amount: Amount of base currency to sell

        Returns:
            Order response from exchange
        """
        quote_currency = get_quote_currency(product_id)

        if quote_currency == "BTC":
            # Sell for BTC
            return await self.exchange.sell_eth_for_btc(eth_amount=base_amount, product_id=product_id)
        elif quote_currency in ("USD", "USDT", "USDC"):
            # Sell for USD/USDT/USDC (stablecoins treated as USD)
            return await self.exchange.sell_for_usd(base_amount=base_amount, product_id=product_id)
        else:
            raise ValueError(f"Unsupported quote currency: {quote_currency}")

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """
        Get order details by ID

        Args:
            order_id: Exchange order ID

        Returns:
            Order details from exchange
        """
        return await self.exchange.get_order(order_id)

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel an open order

        Args:
            order_id: Exchange order ID to cancel (order ID for CEX, tx hash for DEX)

        Returns:
            Cancellation result from exchange
        """
        return await self.exchange.cancel_order(order_id)

    async def invalidate_balance_cache(self):
        """Invalidate balance cache after trades"""
        await self.exchange.invalidate_balance_cache()

    async def get_btc_usd_price(self) -> float:
        """Get BTC/USD price for logging purposes"""
        return await self.exchange.get_btc_usd_price()
