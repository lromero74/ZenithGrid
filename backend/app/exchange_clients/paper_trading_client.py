"""
Paper Trading Exchange Client

Simulates order execution for paper trading accounts without hitting real exchanges.
Uses real market data for price feeds but fakes order fills and balance updates.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.exchange_clients.base import ExchangeClient
from app.models import Account

logger = logging.getLogger(__name__)


class PaperTradingClient(ExchangeClient):
    """
    Simulated exchange client for paper trading.

    Inherits from ExchangeClient base class and overrides order methods
    to simulate execution without hitting real exchanges.
    """

    def __init__(self, account: Account, db: AsyncSession, real_client: Optional[ExchangeClient] = None):
        """
        Initialize paper trading client.

        Args:
            account: Paper trading account
            db: Database session for balance updates
            real_client: Optional real exchange client for price data (uses Coinbase if not provided)
        """
        if not account.is_paper_trading:
            raise ValueError("PaperTradingClient requires a paper trading account")

        self.account = account
        self.db = db
        self.real_client = real_client  # For fetching real prices

        # Load virtual balances
        if account.paper_balances:
            self.balances = json.loads(account.paper_balances)
        else:
            # Default balances
            self.balances = {
                "BTC": 1.0,
                "ETH": 10.0,
                "USD": 100000.0,
                "USDC": 0.0,
                "USDT": 0.0
            }
            account.paper_balances = json.dumps(self.balances)

        logger.info(f"Initialized paper trading client for account {account.id}")

    async def _save_balances(self):
        """Save current balances to database."""
        self.account.paper_balances = json.dumps(self.balances)
        await self.db.commit()
        await self.db.refresh(self.account)

    async def get_price(self, product_id: str) -> Optional[float]:
        """
        Get current market price from real exchange.

        Paper trading uses real price data for realistic simulation.
        """
        if self.real_client:
            return await self.real_client.get_price(product_id)

        # Fallback: import and use Coinbase client
        from app.coinbase_unified_client import CoinbaseUnifiedClient
        from app.config import settings

        # Use system API key for price data
        real_client = CoinbaseUnifiedClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret,
            user_id=self.account.user_id
        )
        return await real_client.get_price(product_id)

    async def get_candles(
        self,
        product_id: str,
        granularity: int = 300,
        start: Optional[str] = None,
        end: Optional[str] = None
    ) -> List[Dict]:
        """Get candle data from real exchange (paper trading uses real market data)."""
        if self.real_client:
            return await self.real_client.get_candles(product_id, granularity, start, end)

        from app.coinbase_unified_client import CoinbaseUnifiedClient
        from app.config import settings

        real_client = CoinbaseUnifiedClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret,
            user_id=self.account.user_id
        )
        return await real_client.get_candles(product_id, granularity, start, end)

    async def get_balance(self, currency: str) -> float:
        """
        Get virtual balance for a currency.

        Args:
            currency: Currency code (BTC, ETH, USD, etc.)

        Returns:
            Virtual balance for that currency
        """
        return self.balances.get(currency.upper(), 0.0)

    async def get_all_balances(self) -> Dict[str, float]:
        """Get all virtual balances."""
        return self.balances.copy()

    async def place_order(
        self,
        product_id: str,
        side: str,
        order_type: str,
        size: Optional[float] = None,
        price: Optional[float] = None,
        funds: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Simulate order placement and immediate fill.

        Paper trading orders are filled instantly at current market price.

        Args:
            product_id: Trading pair (e.g., "ETH-BTC")
            side: "buy" or "sell"
            order_type: "market" or "limit" (both treated as market for paper trading)
            size: Amount of base currency
            price: Limit price (ignored for paper trading)
            funds: Amount of quote currency to spend (for market buys)

        Returns:
            Fake order response with simulated fill
        """
        base_currency, quote_currency = product_id.split("-")

        # Get current market price
        current_price = await self.get_price(product_id)
        if not current_price:
            raise Exception(f"Could not get price for {product_id}")

        # Calculate order size
        if side == "buy":
            if funds:
                # Market buy with funds
                actual_size = funds / current_price
                actual_funds = funds
            elif size:
                # Buy specific size
                actual_size = size
                actual_funds = size * current_price
            else:
                raise ValueError("Must specify either size or funds for buy order")

            # Check sufficient quote currency
            available_quote = self.balances.get(quote_currency, 0.0)
            if available_quote < actual_funds:
                raise Exception(
                    f"Insufficient {quote_currency} balance. "
                    f"Available: {available_quote}, Required: {actual_funds}"
                )

            # Execute simulated buy
            self.balances[quote_currency] -= actual_funds
            self.balances[base_currency] = self.balances.get(base_currency, 0.0) + actual_size

        else:  # sell
            if not size:
                raise ValueError("Must specify size for sell order")

            actual_size = size
            actual_funds = size * current_price

            # Check sufficient base currency
            available_base = self.balances.get(base_currency, 0.0)
            if available_base < actual_size:
                raise Exception(
                    f"Insufficient {base_currency} balance. "
                    f"Available: {available_base}, Required: {actual_size}"
                )

            # Execute simulated sell
            self.balances[base_currency] -= actual_size
            self.balances[quote_currency] = self.balances.get(quote_currency, 0.0) + actual_funds

        # Save updated balances
        await self._save_balances()

        # Generate fake order ID
        order_id = f"paper-{uuid.uuid4()}"

        # Log the simulated trade
        logger.info(
            f"Paper trade executed: {side.upper()} {actual_size:.8f} {base_currency} "
            f"at {current_price:.8f} {quote_currency} (order_id: {order_id})"
        )

        # Return fake order response (matches Coinbase format)
        return {
            "order_id": order_id,
            "success": True,
            "product_id": product_id,
            "side": side,
            "type": "market",  # Paper trading always treats as market
            "size": str(actual_size),
            "price": str(current_price),
            "funds": str(actual_funds),
            "status": "filled",
            "filled_size": str(actual_size),
            "filled_value": str(actual_funds),
            "created_time": datetime.utcnow().isoformat(),
            "done_time": datetime.utcnow().isoformat(),
            "done_reason": "filled",
            "paper_trading": True
        }

    async def cancel_order(self, order_id: str) -> bool:
        """
        Simulate order cancellation.

        Paper trading orders are filled instantly, so cancellation always returns False
        (order already filled).
        """
        logger.info(f"Paper trading: Cancel requested for {order_id} (already filled)")
        return False  # Paper orders fill instantly, can't be cancelled

    async def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Get order details (always returns filled status for paper orders).
        """
        if not order_id.startswith("paper-"):
            return None

        return {
            "order_id": order_id,
            "status": "filled",
            "paper_trading": True
        }

    async def get_products(self) -> List[Dict[str, Any]]:
        """Get available trading pairs from real exchange."""
        if self.real_client:
            return await self.real_client.get_products()

        from app.coinbase_unified_client import CoinbaseUnifiedClient
        from app.config import settings

        real_client = CoinbaseUnifiedClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret,
            user_id=self.account.user_id
        )
        return await real_client.get_products()

    async def get_order_book(self, product_id: str, level: int = 2) -> Dict[str, Any]:
        """Get order book from real exchange."""
        if self.real_client:
            return await self.real_client.get_order_book(product_id, level)

        from app.coinbase_unified_client import CoinbaseUnifiedClient
        from app.config import settings

        real_client = CoinbaseUnifiedClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret,
            user_id=self.account.user_id
        )
        return await real_client.get_order_book(product_id, level)

    async def get_recent_trades(
        self,
        product_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent trades from real exchange."""
        if self.real_client:
            return await self.real_client.get_recent_trades(product_id, limit)

        from app.coinbase_unified_client import CoinbaseUnifiedClient
        from app.config import settings

        real_client = CoinbaseUnifiedClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret,
            user_id=self.account.user_id
        )
        return await real_client.get_recent_trades(product_id, limit)

    async def get_btc_usd_price(self) -> float:
        """Get BTC/USD price from real exchange."""
        if self.real_client:
            return await self.real_client.get_btc_usd_price()

        from app.coinbase_unified_client import CoinbaseUnifiedClient
        from app.config import settings

        real_client = CoinbaseUnifiedClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret,
            user_id=self.account.user_id
        )
        return await real_client.get_btc_usd_price()

    async def get_eth_usd_price(self) -> float:
        """Get ETH/USD price from real exchange."""
        if self.real_client:
            return await self.real_client.get_eth_usd_price()

        from app.coinbase_unified_client import CoinbaseUnifiedClient
        from app.config import settings

        real_client = CoinbaseUnifiedClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret,
            user_id=self.account.user_id
        )
        return await real_client.get_eth_usd_price()

    def is_paper_trading(self) -> bool:
        """Returns True to indicate this is a paper trading client."""
        return True
