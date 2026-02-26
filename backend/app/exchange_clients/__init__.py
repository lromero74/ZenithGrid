"""
Exchange Client Abstraction Layer

This package provides a unified interface for interacting with both centralized exchanges (CEX)
and decentralized exchanges (DEX). All exchange clients must implement the ExchangeClient
abstract base class to ensure consistent behavior across different exchange types.

Supported Exchange Types:
- CEX: Coinbase (via CoinbaseAdapter)
- DEX: Uniswap V3, PancakeSwap, SushiSwap (via DEXClient) - coming soon

Usage:
    from app.exchange_clients.factory import create_exchange_client, ExchangeClientConfig, CoinbaseCredentials

    # Create a CEX client
    exchange = create_exchange_client(ExchangeClientConfig(
        exchange_type="cex",
        coinbase=CoinbaseCredentials(key_name="...", private_key="..."),
    ))

    # Create a DEX client (future)
    from app.exchange_clients.factory import DEXCredentials
    exchange = create_exchange_client(ExchangeClientConfig(
        exchange_type="dex",
        dex=DEXCredentials(chain_id=1, private_key="...", rpc_url="...", dex_router="..."),
    ))
"""

from app.exchange_clients.base import ExchangeClient

__all__ = ["ExchangeClient"]
