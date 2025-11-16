"""
Quote-currency agnostic trading client wrapper

Wraps CoinbaseClient to provide currency-agnostic buy/sell operations.
Automatically detects quote currency and calls appropriate methods.
"""

import logging
from typing import Any, Dict

from app.coinbase_client import CoinbaseClient
from app.currency_utils import get_quote_currency

logger = logging.getLogger(__name__)


class TradingClient:
    """
    Currency-agnostic trading client

    Provides buy/sell methods that automatically detect quote currency
    and call the appropriate Coinbase API methods.
    """

    def __init__(self, coinbase: CoinbaseClient):
        """
        Initialize with Coinbase client

        Args:
            coinbase: CoinbaseClient instance
        """
        self.coinbase = coinbase

    async def get_balance(self, currency: str) -> float:
        """
        Get balance for any currency

        Args:
            currency: Currency code (e.g., "BTC", "USD", "ETH")

        Returns:
            Balance amount
        """
        if currency == "BTC":
            return await self.coinbase.get_btc_balance()
        elif currency == "USD":
            return await self.coinbase.get_usd_balance()
        else:
            # For other currencies, use generic method if it exists
            # Otherwise, get from portfolio
            portfolio = await self.coinbase.get_portfolio()
            balances = portfolio.get("balances", {})
            currency_data = balances.get(currency, {})
            return float(currency_data.get("available", 0))

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

    async def buy(
        self,
        product_id: str,
        quote_amount: float
    ) -> Dict[str, Any]:
        """
        Buy base currency with quote currency

        Automatically detects quote currency and uses appropriate method.

        Args:
            product_id: Trading pair (e.g., "ETH-BTC", "ADA-USD")
            quote_amount: Amount of quote currency to spend

        Returns:
            Order response from Coinbase
        """
        quote_currency = get_quote_currency(product_id)

        if quote_currency == "BTC":
            # Buy with BTC
            return await self.coinbase.buy_eth_with_btc(
                btc_amount=quote_amount,
                product_id=product_id
            )
        elif quote_currency == "USD":
            # Buy with USD
            return await self.coinbase.buy_with_usd(
                usd_amount=quote_amount,
                product_id=product_id
            )
        else:
            raise ValueError(f"Unsupported quote currency: {quote_currency}")

    async def sell(
        self,
        product_id: str,
        base_amount: float
    ) -> Dict[str, Any]:
        """
        Sell base currency for quote currency

        Automatically detects quote currency and uses appropriate method.

        Args:
            product_id: Trading pair (e.g., "ETH-BTC", "ADA-USD")
            base_amount: Amount of base currency to sell

        Returns:
            Order response from Coinbase
        """
        quote_currency = get_quote_currency(product_id)

        if quote_currency == "BTC":
            # Sell for BTC
            return await self.coinbase.sell_eth_for_btc(
                eth_amount=base_amount,
                product_id=product_id
            )
        elif quote_currency == "USD":
            # Sell for USD
            return await self.coinbase.sell_for_usd(
                base_amount=base_amount,
                product_id=product_id
            )
        else:
            raise ValueError(f"Unsupported quote currency: {quote_currency}")

    async def invalidate_balance_cache(self):
        """Invalidate balance cache after trades"""
        await self.coinbase.invalidate_balance_cache()

    async def get_btc_usd_price(self) -> float:
        """Get BTC/USD price for logging purposes"""
        return await self.coinbase.get_btc_usd_price()
