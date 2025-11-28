"""
Price Aggregator

Combines multiple price feeds to find the best prices across exchanges.
Used by arbitrage strategies to identify profitable opportunities.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from app.price_feeds.base import PriceFeed, PriceQuote

logger = logging.getLogger(__name__)


@dataclass
class AggregatedPrice:
    """
    Best prices across all feeds for a trading pair.

    Contains the best venue to buy and sell, along with
    spread and potential profit calculations.
    """
    base: str
    quote: str
    timestamp: datetime

    # Best place to buy (lowest ask)
    best_buy: Optional[PriceQuote] = None

    # Best place to sell (highest bid)
    best_sell: Optional[PriceQuote] = None

    # All quotes received
    all_quotes: List[PriceQuote] = None

    @property
    def product_id(self) -> str:
        return f"{self.base}-{self.quote}"

    @property
    def spread(self) -> Optional[Decimal]:
        """Absolute spread between best buy and sell venues"""
        if self.best_buy and self.best_sell:
            return self.best_sell.bid - self.best_buy.ask
        return None

    @property
    def spread_pct(self) -> Optional[Decimal]:
        """Spread as percentage of buy price"""
        if self.best_buy and self.best_buy.ask > 0 and self.spread:
            return (self.spread / self.best_buy.ask) * 100
        return None

    def calculate_profit(
        self,
        quantity: Decimal,
        include_fees: bool = True,
        include_gas: bool = True,
    ) -> Optional[Dict]:
        """
        Calculate potential arbitrage profit.

        Args:
            quantity: Amount of base currency to trade
            include_fees: Include trading fees in calculation
            include_gas: Include gas fees (for DEX)

        Returns:
            Dict with profit calculation details
        """
        if not self.best_buy or not self.best_sell:
            return None

        # Buy cost
        buy_price = self.best_buy.ask
        if include_fees:
            buy_price = buy_price * (1 + self.best_buy.taker_fee_pct / 100)

        buy_cost = quantity * buy_price

        # Add gas for DEX buy
        if include_gas and self.best_buy.exchange_type == "dex":
            # Convert gas from USD to quote currency
            # This is approximate - would need quote/USD price for accuracy
            gas_in_quote = self.best_buy.gas_estimate_usd or Decimal("0")
            buy_cost += gas_in_quote

        # Sell revenue
        sell_price = self.best_sell.bid
        if include_fees:
            sell_price = sell_price * (1 - self.best_sell.taker_fee_pct / 100)

        sell_revenue = quantity * sell_price

        # Subtract gas for DEX sell
        if include_gas and self.best_sell.exchange_type == "dex":
            gas_in_quote = self.best_sell.gas_estimate_usd or Decimal("0")
            sell_revenue -= gas_in_quote

        # Calculate profit
        profit = sell_revenue - buy_cost
        profit_pct = (profit / buy_cost) * 100 if buy_cost > 0 else Decimal("0")

        return {
            "quantity": quantity,
            "buy_exchange": self.best_buy.exchange,
            "buy_price": buy_price,
            "buy_cost": buy_cost,
            "sell_exchange": self.best_sell.exchange,
            "sell_price": sell_price,
            "sell_revenue": sell_revenue,
            "gross_profit": self.spread * quantity if self.spread else Decimal("0"),
            "net_profit": profit,
            "net_profit_pct": profit_pct,
            "is_profitable": profit > 0,
        }


@dataclass
class ArbitrageOpportunity:
    """
    Identified arbitrage opportunity ready for execution.

    Contains all information needed to execute the trade.
    """
    id: str
    timestamp: datetime
    product_id: str
    base: str
    quote: str

    # Execution details
    buy_exchange: str
    buy_exchange_type: str
    buy_price: Decimal
    sell_exchange: str
    sell_exchange_type: str
    sell_price: Decimal

    # Profit calculation
    spread: Decimal
    spread_pct: Decimal
    estimated_profit: Decimal
    estimated_profit_pct: Decimal

    # Constraints
    max_quantity: Decimal  # Limited by liquidity
    min_quantity: Decimal  # Minimum order size

    # Validity
    expires_at: datetime  # Opportunities are fleeting
    confidence: Decimal  # 0-100 confidence score


class PriceAggregator:
    """
    Aggregates prices from multiple feeds to find arbitrage opportunities.

    Usage:
        aggregator = PriceAggregator([coinbase_feed, uniswap_feed])
        prices = await aggregator.get_best_prices("ETH", "USDT")
        if prices.spread_pct > 0.5:
            profit = prices.calculate_profit(Decimal("1.0"))
    """

    def __init__(self, feeds: List[PriceFeed]):
        """
        Initialize aggregator with price feeds.

        Args:
            feeds: List of PriceFeed instances to aggregate
        """
        self.feeds = feeds

    async def get_best_prices(
        self,
        base: str,
        quote: str,
        timeout: float = 5.0,
    ) -> AggregatedPrice:
        """
        Get best buy and sell prices across all feeds.

        Args:
            base: Base currency (e.g., "ETH")
            quote: Quote currency (e.g., "USDT")
            timeout: Maximum seconds to wait for all feeds

        Returns:
            AggregatedPrice with best venues for buy/sell
        """
        # Fetch prices from all feeds concurrently
        async def fetch_with_timeout(feed: PriceFeed) -> Optional[PriceQuote]:
            try:
                return await asyncio.wait_for(
                    feed.get_price(base, quote),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"Timeout fetching price from {feed.name}")
                return None
            except Exception as e:
                logger.error(f"Error fetching price from {feed.name}: {e}")
                return None

        # Fetch all prices concurrently
        quotes = await asyncio.gather(
            *[fetch_with_timeout(feed) for feed in self.feeds]
        )

        # Filter out None results
        valid_quotes = [q for q in quotes if q is not None]

        if not valid_quotes:
            return AggregatedPrice(
                base=base,
                quote=quote,
                timestamp=datetime.utcnow(),
                all_quotes=[],
            )

        # Find best buy (lowest ask) and best sell (highest bid)
        best_buy = min(valid_quotes, key=lambda q: q.ask)
        best_sell = max(valid_quotes, key=lambda q: q.bid)

        return AggregatedPrice(
            base=base,
            quote=quote,
            timestamp=datetime.utcnow(),
            best_buy=best_buy,
            best_sell=best_sell,
            all_quotes=valid_quotes,
        )

    async def find_opportunities(
        self,
        pairs: List[Tuple[str, str]],
        min_profit_pct: Decimal = Decimal("0.3"),
        min_quantity: Decimal = Decimal("0.01"),
        timeout: float = 10.0,
    ) -> List[ArbitrageOpportunity]:
        """
        Scan multiple pairs for arbitrage opportunities.

        Args:
            pairs: List of (base, quote) tuples to scan
            min_profit_pct: Minimum profit percentage to report
            min_quantity: Minimum trade quantity
            timeout: Maximum seconds to wait

        Returns:
            List of ArbitrageOpportunity objects
        """
        opportunities = []

        # Fetch prices for all pairs concurrently
        async def check_pair(base: str, quote: str) -> Optional[ArbitrageOpportunity]:
            prices = await self.get_best_prices(base, quote, timeout=timeout)

            if not prices.best_buy or not prices.best_sell:
                return None

            # Calculate profit at minimum quantity
            profit_calc = prices.calculate_profit(min_quantity)

            if not profit_calc or not profit_calc["is_profitable"]:
                return None

            if profit_calc["net_profit_pct"] < min_profit_pct:
                return None

            # Create opportunity
            return ArbitrageOpportunity(
                id=f"{base}-{quote}-{datetime.utcnow().timestamp()}",
                timestamp=datetime.utcnow(),
                product_id=f"{base}-{quote}",
                base=base,
                quote=quote,
                buy_exchange=prices.best_buy.exchange,
                buy_exchange_type=prices.best_buy.exchange_type,
                buy_price=prices.best_buy.ask,
                sell_exchange=prices.best_sell.exchange,
                sell_exchange_type=prices.best_sell.exchange_type,
                sell_price=prices.best_sell.bid,
                spread=prices.spread or Decimal("0"),
                spread_pct=prices.spread_pct or Decimal("0"),
                estimated_profit=profit_calc["net_profit"],
                estimated_profit_pct=profit_calc["net_profit_pct"],
                max_quantity=Decimal("100"),  # Would need orderbook depth for accurate value
                min_quantity=min_quantity,
                expires_at=datetime.utcnow(),  # Expires immediately - prices change fast
                confidence=Decimal("80"),  # Base confidence, would adjust based on liquidity
            )

        # Check all pairs
        results = await asyncio.gather(
            *[check_pair(base, quote) for base, quote in pairs],
            return_exceptions=True
        )

        for result in results:
            if isinstance(result, ArbitrageOpportunity):
                opportunities.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Error checking pair: {result}")

        # Sort by profit percentage (highest first)
        opportunities.sort(key=lambda o: o.estimated_profit_pct, reverse=True)

        return opportunities

    async def monitor_spread(
        self,
        base: str,
        quote: str,
        callback,
        interval_seconds: float = 1.0,
    ):
        """
        Continuously monitor spread between exchanges.

        Args:
            base: Base currency
            quote: Quote currency
            callback: Async function called with AggregatedPrice on each update
            interval_seconds: Seconds between checks
        """
        while True:
            try:
                prices = await self.get_best_prices(base, quote)
                await callback(prices)
            except Exception as e:
                logger.error(f"Error in spread monitor: {e}")

            await asyncio.sleep(interval_seconds)

    def add_feed(self, feed: PriceFeed):
        """Add a new price feed to the aggregator."""
        self.feeds.append(feed)

    def remove_feed(self, feed_name: str):
        """Remove a price feed by name."""
        self.feeds = [f for f in self.feeds if f.name != feed_name]

    async def check_feed_health(self) -> Dict[str, bool]:
        """
        Check health of all feeds.

        Returns:
            Dict mapping feed name to availability status
        """
        results = {}

        for feed in self.feeds:
            try:
                results[feed.name] = await feed.is_available()
            except Exception:
                results[feed.name] = False

        return results
