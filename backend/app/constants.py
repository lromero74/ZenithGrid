"""
Application Constants

Centralized constants for trading pairs, timeframes, etc.
"""

from typing import Dict

# Popular Coinbase trading pairs
# Focus on X/BTC pairs as requested
POPULAR_BTC_PAIRS = [
    "ETH-BTC",  # Ethereum
    "SOL-BTC",  # Solana
    "LINK-BTC",  # Chainlink
    "MATIC-BTC",  # Polygon
    "AVAX-BTC",  # Avalanche
    "DOT-BTC",  # Polkadot
    "UNI-BTC",  # Uniswap
    "ATOM-BTC",  # Cosmos
    "LTC-BTC",  # Litecoin
    "XLM-BTC",  # Stellar
]

# Also support major USD pairs
POPULAR_USD_PAIRS = [
    "BTC-USD",  # Bitcoin
    "ETH-USD",  # Ethereum
    "SOL-USD",  # Solana
    "USDC-USD",  # USD Coin
]

# All supported trading pairs
SUPPORTED_TRADING_PAIRS = POPULAR_BTC_PAIRS + POPULAR_USD_PAIRS

# Trading pair metadata for display
TRADING_PAIR_INFO: Dict[str, Dict[str, str]] = {
    "ETH-BTC": {"name": "Ethereum/Bitcoin", "base": "ETH", "quote": "BTC"},
    "SOL-BTC": {"name": "Solana/Bitcoin", "base": "SOL", "quote": "BTC"},
    "LINK-BTC": {"name": "Chainlink/Bitcoin", "base": "LINK", "quote": "BTC"},
    "MATIC-BTC": {"name": "Polygon/Bitcoin", "base": "MATIC", "quote": "BTC"},
    "AVAX-BTC": {"name": "Avalanche/Bitcoin", "base": "AVAX", "quote": "BTC"},
    "DOT-BTC": {"name": "Polkadot/Bitcoin", "base": "DOT", "quote": "BTC"},
    "UNI-BTC": {"name": "Uniswap/Bitcoin", "base": "UNI", "quote": "BTC"},
    "ATOM-BTC": {"name": "Cosmos/Bitcoin", "base": "ATOM", "quote": "BTC"},
    "LTC-BTC": {"name": "Litecoin/Bitcoin", "base": "LTC", "quote": "BTC"},
    "XLM-BTC": {"name": "Stellar/Bitcoin", "base": "XLM", "quote": "BTC"},
    "BTC-USD": {"name": "Bitcoin/USD", "base": "BTC", "quote": "USD"},
    "ETH-USD": {"name": "Ethereum/USD", "base": "ETH", "quote": "USD"},
    "SOL-USD": {"name": "Solana/USD", "base": "SOL", "quote": "USD"},
    "USDC-USD": {"name": "USDC/USD", "base": "USDC", "quote": "USD"},
}

# Candle intervals
# Coinbase natively supports: ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE, THIRTY_MINUTE,
# ONE_HOUR, TWO_HOUR, SIX_HOUR, ONE_DAY
# Additional synthetic intervals are aggregated from base candles:
# - THREE_MINUTE: aggregated from ONE_MINUTE
# - TWO_DAY, THREE_DAY, ONE_WEEK, TWO_WEEK, ONE_MONTH: aggregated from ONE_DAY
CANDLE_INTERVALS = [
    "ONE_MINUTE",
    "THREE_MINUTE",   # Synthetic - aggregated from 1-minute candles
    "FIVE_MINUTE",
    "FIFTEEN_MINUTE",
    "THIRTY_MINUTE",
    "ONE_HOUR",
    "TWO_HOUR",
    "SIX_HOUR",
    "ONE_DAY",
    "TWO_DAY",        # Synthetic - aggregated from 1-day candles
    "THREE_DAY",      # Synthetic - aggregated from 1-day candles
    "ONE_WEEK",       # Synthetic - aggregated from 1-day candles
    "TWO_WEEK",       # Synthetic - aggregated from 1-day candles
    "ONE_MONTH",      # Synthetic - aggregated from 1-day candles (30 days)
]

# Cache TTL (seconds)
BALANCE_CACHE_TTL = 60  # Cache balances for 60 seconds
PRICE_CACHE_TTL = 60  # Cache prices for 60 seconds (budget calc doesn't need real-time prices)
AGGREGATE_VALUE_CACHE_TTL = 300  # Cache aggregate portfolio values for 5 minutes (was 2 min)
PRODUCT_STATS_CACHE_TTL = 600  # Cache product stats (24h volume, etc.) for 10 minutes
CANDLE_CACHE_TTL = 60  # Cache candle data for 60 seconds (shared across bots, was 30s)
MIN_USD_BALANCE_FOR_AGGREGATE = 1.0  # Skip dust balances below $1 in aggregate calculations

# Throttling for low-resource environments (t2.micro)
# These delays are critical for allowing HTTP API requests to be processed
# during bot monitoring (single uvicorn worker shares event loop with monitor)
PAIR_PROCESSING_DELAY_SECONDS = 1.5  # Delay between processing each pair (was 0.5 - increased to allow API requests)
BOT_PROCESSING_DELAY_SECONDS = 2.0  # Delay between processing each bot (was 1.0)
API_YIELD_INTERVAL = 0.1  # Yield to event loop every N seconds during heavy processing
