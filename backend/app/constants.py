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
CANDLE_INTERVALS = [
    "ONE_MINUTE",
    "FIVE_MINUTE",
    "FIFTEEN_MINUTE",
    "THIRTY_MINUTE",
    "ONE_HOUR",
    "TWO_HOUR",
    "SIX_HOUR",
    "ONE_DAY",
]

# Cache TTL (seconds)
BALANCE_CACHE_TTL = 60  # Cache balances for 60 seconds
PRICE_CACHE_TTL = 10  # Cache prices for 10 seconds
