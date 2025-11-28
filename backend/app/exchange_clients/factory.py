"""
Exchange Client Factory

Factory pattern for creating exchange clients based on configuration.
Determines whether to create a CEX (Coinbase) or DEX (Uniswap, PancakeSwap, etc.)
client based on bot configuration.

This centralizes exchange client creation and makes it easy to add new exchange types.
"""

from typing import Optional

from app.coinbase_unified_client import CoinbaseClient
from app.exchange_clients.base import ExchangeClient
from app.exchange_clients.coinbase_adapter import CoinbaseAdapter
from app.exchange_clients.dex_client import DEXClient


def create_exchange_client(
    exchange_type: str,
    # CEX (Coinbase) parameters
    coinbase_key_name: Optional[str] = None,
    coinbase_private_key: Optional[str] = None,
    # DEX parameters (for future implementation)
    chain_id: Optional[int] = None,
    private_key: Optional[str] = None,
    rpc_url: Optional[str] = None,
    dex_router: Optional[str] = None,
) -> ExchangeClient:
    """
    Factory function to create the appropriate exchange client.

    Args:
        exchange_type: Type of exchange ("cex" or "dex")

        # For CEX (Coinbase):
        coinbase_key_name: Coinbase API key name (CDP key name or legacy API key)
        coinbase_private_key: Coinbase private key (EC private key or HMAC secret)

        # For DEX (future):
        chain_id: Blockchain ID (1=Ethereum, 56=BSC, 137=Polygon, 42161=Arbitrum)
        private_key: Wallet private key for signing transactions
        rpc_url: RPC endpoint URL for blockchain connection
        dex_router: DEX router contract address (Uniswap V3, PancakeSwap, etc.)

    Returns:
        ExchangeClient instance (CoinbaseAdapter or DEXClient)

    Raises:
        ValueError: If exchange_type is invalid or required parameters are missing

    Examples:
        # Create Coinbase CEX client
        exchange = create_exchange_client(
            exchange_type="cex",
            coinbase_key_name="organizations/abc/apiKeys/xyz",
            coinbase_private_key="-----BEGIN EC PRIVATE KEY-----\\n..."
        )

        # Create DEX client (future)
        exchange = create_exchange_client(
            exchange_type="dex",
            chain_id=1,  # Ethereum
            private_key="0x...",
            rpc_url="https://mainnet.infura.io/v3/...",
            dex_router="0xE592427A0AEce92De3Edee1F18E0157C05861564"  # Uniswap V3
        )
    """

    if exchange_type == "cex":
        # Centralized Exchange (Coinbase)
        if not coinbase_key_name or not coinbase_private_key:
            raise ValueError("CEX requires coinbase_key_name and coinbase_private_key")

        # Create CoinbaseClient and wrap it with adapter
        coinbase = CoinbaseClient(
            key_name=coinbase_key_name,
            private_key=coinbase_private_key,
        )
        return CoinbaseAdapter(coinbase)

    elif exchange_type == "dex":
        # Decentralized Exchange (Ethereum + Uniswap V3)
        if not chain_id or not private_key or not rpc_url or not dex_router:
            raise ValueError("DEX requires chain_id, private_key, rpc_url, and dex_router")

        # Create DEX client (Ethereum + Uniswap V3 for Phase 3)
        return DEXClient(
            chain_id=chain_id,
            rpc_url=rpc_url,
            wallet_private_key=private_key,
            dex_router=dex_router,
        )

    else:
        raise ValueError(f"Unknown exchange type: {exchange_type}. Must be 'cex' or 'dex'.")


def create_exchange_client_from_bot_config(bot_config: dict) -> ExchangeClient:
    """
    Convenience function to create exchange client from bot configuration.

    This function examines the bot configuration and determines which exchange
    client to create based on the exchange_type field (or defaults to CEX).

    Args:
        bot_config: Bot configuration dictionary containing exchange credentials

    Returns:
        ExchangeClient instance configured for this bot

    Example bot_config for CEX:
        {
            "exchange_type": "cex",  # Optional, defaults to "cex"
            "coinbase_key_name": "...",
            "coinbase_private_key": "..."
        }

    Example bot_config for DEX (future):
        {
            "exchange_type": "dex",
            "chain_id": 1,
            "wallet_private_key": "...",
            "dex_type": "uniswap_v3",
            "rpc_url": "...",
            "dex_router": "..."
        }
    """
    exchange_type = bot_config.get("exchange_type", "cex")

    if exchange_type == "cex":
        return create_exchange_client(
            exchange_type="cex",
            coinbase_key_name=bot_config["coinbase_key_name"],
            coinbase_private_key=bot_config["coinbase_private_key"],
        )
    elif exchange_type == "dex":
        return create_exchange_client(
            exchange_type="dex",
            chain_id=bot_config["chain_id"],
            private_key=bot_config["wallet_private_key"],
            rpc_url=bot_config["rpc_url"],
            dex_router=bot_config["dex_router"],
        )
    else:
        raise ValueError(f"Unknown exchange type in bot config: {exchange_type}")
