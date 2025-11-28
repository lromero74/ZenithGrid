"""
Price Feeds Module

Provides unified price feed abstraction for multiple exchanges and DEXes.
Used by arbitrage strategies to find price discrepancies across venues.

Components:
- PriceFeed: Abstract base class for price data sources
- CoinbasePriceFeed: Centralized exchange price feed (Coinbase)
- DEXPriceFeed: Decentralized exchange price feed (Uniswap, etc.)
- PriceAggregator: Combines multiple feeds for best price discovery
"""

from app.price_feeds.base import PriceFeed, PriceQuote, OrderBook, OrderBookLevel
from app.price_feeds.aggregator import PriceAggregator, AggregatedPrice, ArbitrageOpportunity

__all__ = [
    "PriceFeed",
    "PriceQuote",
    "OrderBook",
    "OrderBookLevel",
    "PriceAggregator",
    "AggregatedPrice",
    "ArbitrageOpportunity",
]
