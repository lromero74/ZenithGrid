"""
Coinbase Price Feed

Implements PriceFeed interface for Coinbase exchange.
Wraps the existing CoinbaseClient to provide unified price access.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from app.price_feeds.base import PriceFeed, PriceQuote, OrderBook, OrderBookLevel

logger = logging.getLogger(__name__)


class CoinbasePriceFeed(PriceFeed):
    """
    Price feed implementation for Coinbase.

    Uses the existing CoinbaseClient (via CoinbaseAdapter) to fetch
    real-time prices and order book data.
    """

    # Coinbase fee structure (for Advanced Trade)
    TAKER_FEE_PCT = Decimal("0.6")  # 0.6% for low volume
    MAKER_FEE_PCT = Decimal("0.4")  # 0.4% for low volume

    def __init__(self, coinbase_client):
        """
        Initialize Coinbase price feed.

        Args:
            coinbase_client: CoinbaseAdapter or CoinbaseClient instance
        """
        super().__init__(name="coinbase", exchange_type="cex")
        self.client = coinbase_client
        self._supported_pairs_cache: Optional[List[str]] = None

    async def get_price(self, base: str, quote: str) -> Optional[PriceQuote]:
        """
        Get current price quote from Coinbase.

        Args:
            base: Base currency (e.g., "ETH")
            quote: Quote currency (e.g., "USD", "BTC")

        Returns:
            PriceQuote with bid/ask prices
        """
        product_id = f"{base}-{quote}"

        try:
            # Get best bid/ask from ticker
            ticker = await self.client.get_ticker(product_id)

            if not ticker:
                logger.warning(f"No ticker data for {product_id}")
                return None

            bid = Decimal(str(ticker.get("bid", 0)))
            ask = Decimal(str(ticker.get("ask", 0)))

            if bid <= 0 or ask <= 0:
                logger.warning(f"Invalid bid/ask for {product_id}: bid={bid}, ask={ask}")
                return None

            return PriceQuote(
                exchange="coinbase",
                exchange_type="cex",
                base=base,
                quote=quote,
                bid=bid,
                ask=ask,
                timestamp=datetime.utcnow(),
                taker_fee_pct=self.TAKER_FEE_PCT,
                maker_fee_pct=self.MAKER_FEE_PCT,
            )

        except Exception as e:
            logger.error(f"Error fetching price for {product_id}: {e}")
            return None

    async def get_orderbook(
        self, base: str, quote: str, depth: int = 10
    ) -> Optional[OrderBook]:
        """
        Get order book snapshot from Coinbase.

        Args:
            base: Base currency
            quote: Quote currency
            depth: Number of levels to retrieve

        Returns:
            OrderBook with bids and asks
        """
        product_id = f"{base}-{quote}"

        try:
            # Coinbase order book endpoint
            book = await self.client.get_orderbook(product_id, level=2)

            if not book:
                return None

            bids = []
            asks = []

            # Parse bids (price, size, num_orders)
            for bid in book.get("bids", [])[:depth]:
                bids.append(OrderBookLevel(
                    price=Decimal(str(bid[0])),
                    quantity=Decimal(str(bid[1]))
                ))

            # Parse asks
            for ask in book.get("asks", [])[:depth]:
                asks.append(OrderBookLevel(
                    price=Decimal(str(ask[0])),
                    quantity=Decimal(str(ask[1]))
                ))

            return OrderBook(
                exchange="coinbase",
                exchange_type="cex",
                base=base,
                quote=quote,
                timestamp=datetime.utcnow(),
                bids=bids,
                asks=asks,
            )

        except Exception as e:
            logger.error(f"Error fetching orderbook for {product_id}: {e}")
            return None

    async def get_supported_pairs(self) -> List[str]:
        """
        Get list of supported trading pairs on Coinbase.

        Returns:
            List of product IDs (e.g., ["ETH-USD", "BTC-USD", ...])
        """
        if self._supported_pairs_cache:
            return self._supported_pairs_cache

        try:
            products = await self.client.get_products()
            self._supported_pairs_cache = [
                p["product_id"] for p in products
                if p.get("trading_disabled") is not True
            ]
            return self._supported_pairs_cache

        except Exception as e:
            logger.error(f"Error fetching supported pairs: {e}")
            return []

    async def is_available(self) -> bool:
        """
        Check if Coinbase API is available.

        Returns:
            True if API is responsive
        """
        try:
            # Try to get a simple ticker
            price = await self.client.get_current_price("BTC-USD")
            return price is not None and price > 0
        except Exception:
            return False

    def get_fee_estimate(self, side: str, is_maker: bool = False) -> Decimal:
        """
        Get Coinbase trading fee.

        Args:
            side: "buy" or "sell" (same fee either way)
            is_maker: True for maker orders

        Returns:
            Fee percentage
        """
        return self.MAKER_FEE_PCT if is_maker else self.TAKER_FEE_PCT
