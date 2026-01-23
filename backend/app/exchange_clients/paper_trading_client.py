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
        from app.coinbase_unified_client import CoinbaseClient
        from app.config import settings

        # Use system API key for price data
        real_client = CoinbaseClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret
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

        from app.coinbase_unified_client import CoinbaseClient
        from app.config import settings

        real_client = CoinbaseClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret
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

        from app.coinbase_unified_client import CoinbaseClient
        from app.config import settings

        real_client = CoinbaseClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret
        )
        return await real_client.get_products()

    async def get_order_book(self, product_id: str, level: int = 2) -> Dict[str, Any]:
        """Get order book from real exchange."""
        if self.real_client:
            return await self.real_client.get_order_book(product_id, level)

        from app.coinbase_unified_client import CoinbaseClient
        from app.config import settings

        real_client = CoinbaseClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret
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

        from app.coinbase_unified_client import CoinbaseClient
        from app.config import settings

        real_client = CoinbaseClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret
        )
        return await real_client.get_recent_trades(product_id, limit)

    async def get_btc_usd_price(self) -> float:
        """Get BTC/USD price from real exchange."""
        if self.real_client:
            return await self.real_client.get_btc_usd_price()

        from app.coinbase_unified_client import CoinbaseClient
        from app.config import settings

        real_client = CoinbaseClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret
        )
        return await real_client.get_btc_usd_price()

    async def get_eth_usd_price(self) -> float:
        """Get ETH/USD price from real exchange."""
        if self.real_client:
            return await self.real_client.get_eth_usd_price()

        from app.coinbase_unified_client import CoinbaseClient
        from app.config import settings

        real_client = CoinbaseClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret
        )
        return await real_client.get_eth_usd_price()

    def is_paper_trading(self) -> bool:
        """Returns True to indicate this is a paper trading client."""
        return True

    # ========================================
    # MISSING ABSTRACT METHOD IMPLEMENTATIONS
    # ========================================

    async def get_accounts(self, force_fresh: bool = False) -> List[Dict[str, Any]]:
        """Get virtual accounts (returns single paper trading account)."""
        accounts = []
        for currency, balance in self.balances.items():
            if balance > 0:
                accounts.append({
                    "uuid": f"paper-{currency.lower()}",
                    "currency": currency,
                    "available_balance": {
                        "value": str(balance),
                        "currency": currency
                    }
                })
        return accounts

    async def get_account(self, account_id: str = None) -> Dict[str, float]:
        """
        Get account balances.

        Returns:
            Dict mapping currency to balance (e.g., {"BTC": 1.0, "USD": 100000.0})
        """
        return self.balances.copy()

    async def get_btc_balance(self) -> float:
        """Get BTC balance."""
        return self.balances.get("BTC", 0.0)

    async def get_eth_balance(self) -> float:
        """Get ETH balance."""
        return self.balances.get("ETH", 0.0)

    async def get_usd_balance(self) -> float:
        """Get USD balance (includes USDC and USDT)."""
        usd = self.balances.get("USD", 0.0)
        usdc = self.balances.get("USDC", 0.0)
        usdt = self.balances.get("USDT", 0.0)
        return usd + usdc + usdt

    async def get_balance(self, currency: str) -> Dict[str, Any]:
        """Get balance for specific currency."""
        balance = self.balances.get(currency.upper(), 0.0)
        return {
            "currency": currency.upper(),
            "available": str(balance),
            "hold": "0.00"
        }

    async def invalidate_balance_cache(self):
        """No-op for paper trading (balances always up-to-date in memory)."""
        pass

    async def calculate_aggregate_btc_value(self, bypass_cache: bool = False) -> float:
        """
        Calculate total portfolio value in BTC.

        Args:
            bypass_cache: Not used for paper trading (uses simulated balances, no API caching)

        Includes:
        - BTC balance
        - BTC value of altcoins (ETH, etc.)
        """
        total_btc = self.balances.get("BTC", 0.0)

        # Convert ETH to BTC
        eth_balance = self.balances.get("ETH", 0.0)
        if eth_balance > 0:
            try:
                eth_btc_price = await self.get_price("ETH-BTC")
                if eth_btc_price:
                    total_btc += eth_balance * eth_btc_price
            except Exception as e:
                logger.warning(f"Failed to get ETH-BTC price for aggregate calculation: {e}")

        # Convert USD/stablecoins to BTC
        usd_balance = await self.get_usd_balance()
        if usd_balance > 0:
            try:
                btc_usd_price = await self.get_btc_usd_price()
                if btc_usd_price and btc_usd_price > 0:
                    total_btc += usd_balance / btc_usd_price
            except Exception as e:
                logger.warning(f"Failed to get BTC-USD price for aggregate calculation: {e}")

        return total_btc

    async def calculate_aggregate_usd_value(self) -> float:
        """
        Calculate total portfolio value in USD.

        Includes:
        - USD balance (including stablecoins)
        - USD value of crypto holdings
        """
        total_usd = await self.get_usd_balance()

        # Convert BTC to USD
        btc_balance = self.balances.get("BTC", 0.0)
        if btc_balance > 0:
            try:
                btc_usd_price = await self.get_btc_usd_price()
                if btc_usd_price:
                    total_usd += btc_balance * btc_usd_price
            except Exception as e:
                logger.warning(f"Failed to get BTC-USD price for aggregate calculation: {e}")

        # Convert ETH to USD
        eth_balance = self.balances.get("ETH", 0.0)
        if eth_balance > 0:
            try:
                eth_usd_price = await self.get_eth_usd_price()
                if eth_usd_price:
                    total_usd += eth_balance * eth_usd_price
            except Exception as e:
                logger.warning(f"Failed to get ETH-USD price for aggregate calculation: {e}")

        return total_usd

    async def list_products(self) -> List[Dict[str, Any]]:
        """List available trading pairs from real exchange."""
        return await self.get_products()

    async def get_product(self, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Get product details from real exchange."""
        if self.real_client:
            return await self.real_client.get_product(product_id)

        from app.coinbase_unified_client import CoinbaseClient
        from app.config import settings

        real_client = CoinbaseClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret
        )
        return await real_client.get_product(product_id)

    async def get_ticker(self, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Get ticker data from real exchange."""
        if self.real_client:
            return await self.real_client.get_ticker(product_id)

        from app.coinbase_unified_client import CoinbaseClient
        from app.config import settings

        real_client = CoinbaseClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret
        )
        return await real_client.get_ticker(product_id)

    async def get_current_price(self, product_id: str = "ETH-BTC") -> float:
        """Get current price from real exchange."""
        return await self.get_price(product_id)

    async def get_product_stats(self, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Get 24hr stats from real exchange."""
        if self.real_client:
            return await self.real_client.get_product_stats(product_id)

        from app.coinbase_unified_client import CoinbaseClient
        from app.config import settings

        real_client = CoinbaseClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret
        )
        return await real_client.get_product_stats(product_id)

    async def get_candles(
        self,
        product_id: str,
        start: int,
        end: int,
        granularity: str,
    ) -> List[Dict[str, Any]]:
        """Get candle data from real exchange (updated signature)."""
        if self.real_client:
            return await self.real_client.get_candles(product_id, start, end, granularity)

        from app.coinbase_unified_client import CoinbaseClient
        from app.config import settings

        real_client = CoinbaseClient(
            api_key=settings.coinbase_api_key,
            api_secret=settings.coinbase_api_secret
        )
        return await real_client.get_candles(product_id, start, end, granularity)

    async def create_market_order(
        self,
        product_id: str,
        side: str,
        size: Optional[str] = None,
        funds: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create market order (wrapper around place_order)."""
        size_float = float(size) if size else None
        funds_float = float(funds) if funds else None

        return await self.place_order(
            product_id=product_id,
            side=side.lower(),
            order_type="market",
            size=size_float,
            funds=funds_float
        )

    async def create_limit_order(
        self,
        product_id: str,
        side: str,
        limit_price: float,
        size: Optional[str] = None,
        funds: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create limit order (paper trading treats as market order).

        Note: Paper trading executes immediately at current price,
        not at the limit price.
        """
        logger.info(f"Paper trading: Limit order requested at {limit_price}, executing as market")
        return await self.create_market_order(product_id, side, size, funds)

    async def list_orders(
        self,
        product_id: Optional[str] = None,
        order_status: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List orders (paper trading orders are all immediately filled)."""
        # Paper trading orders fill instantly, so no open orders exist
        return []

    async def buy_eth_with_btc(self, btc_amount: float, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Buy ETH with BTC."""
        return await self.create_market_order(
            product_id=product_id,
            side="buy",
            funds=str(btc_amount)
        )

    async def sell_eth_for_btc(self, eth_amount: float, product_id: str = "ETH-BTC") -> Dict[str, Any]:
        """Sell ETH for BTC."""
        return await self.create_market_order(
            product_id=product_id,
            side="sell",
            size=str(eth_amount)
        )

    async def buy_with_usd(self, usd_amount: float, product_id: str) -> Dict[str, Any]:
        """Buy crypto with USD."""
        return await self.create_market_order(
            product_id=product_id,
            side="buy",
            funds=str(usd_amount)
        )

    async def sell_for_usd(self, base_amount: float, product_id: str) -> Dict[str, Any]:
        """Sell crypto for USD."""
        return await self.create_market_order(
            product_id=product_id,
            side="sell",
            size=str(base_amount)
        )

    def get_exchange_type(self) -> str:
        """Return exchange type."""
        return "cex"  # Paper trading simulates CEX behavior

    async def test_connection(self) -> bool:
        """Test connection (always succeeds for paper trading)."""
        return True
