"""
Exchange Client Factory

Factory pattern for creating exchange clients based on configuration.
Determines whether to create a CEX (Coinbase, ByBit), DEX (Uniswap),
or bridge (MT5) client based on bot configuration.

This centralizes exchange client creation and makes it easy to add new exchange types.
"""

from typing import Optional

from app.exchange_clients.base import ExchangeClient


def create_exchange_client(
    exchange_type: str,
    exchange_name: str = "coinbase",
    # CEX (Coinbase) parameters
    coinbase_key_name: Optional[str] = None,
    coinbase_private_key: Optional[str] = None,
    # ByBit parameters
    bybit_api_key: Optional[str] = None,
    bybit_api_secret: Optional[str] = None,
    bybit_testnet: bool = False,
    # MT5 Bridge parameters
    mt5_bridge_url: Optional[str] = None,
    mt5_magic_number: int = 12345,
    mt5_account_balance: float = 100000.0,
    # DEX parameters
    chain_id: Optional[int] = None,
    private_key: Optional[str] = None,
    rpc_url: Optional[str] = None,
    dex_router: Optional[str] = None,
) -> Optional[ExchangeClient]:
    """
    Factory function to create the appropriate exchange client.

    Args:
        exchange_type: Type of exchange ("cex" or "dex")
        exchange_name: Specific exchange ("coinbase", "bybit", "mt5_bridge")

    Returns:
        ExchangeClient instance, or None if credentials missing

    Raises:
        ValueError: If exchange_type or exchange_name is invalid
    """

    if exchange_type == "cex":
        if exchange_name == "bybit":
            # ByBit V5 (HyroTrader / prop firms)
            if not bybit_api_key or not bybit_api_secret:
                return None
            # Lazy import to avoid loading pybit unless needed
            from app.exchange_clients.bybit_client import ByBitClient
            from app.exchange_clients.bybit_adapter import ByBitAdapter
            client = ByBitClient(
                api_key=bybit_api_key,
                api_secret=bybit_api_secret,
                testnet=bybit_testnet,
            )
            return ByBitAdapter(client)

        elif exchange_name == "mt5_bridge":
            # MT5 Bridge (FTMO)
            if not mt5_bridge_url:
                return None
            from app.exchange_clients.mt5_bridge_client import MT5BridgeClient
            return MT5BridgeClient(
                bridge_url=mt5_bridge_url,
                magic_number=mt5_magic_number,
                account_balance=mt5_account_balance,
            )

        else:
            # Default: Coinbase
            if not coinbase_key_name or not coinbase_private_key:
                return None

            from app.coinbase_unified_client import CoinbaseClient
            from app.exchange_clients.coinbase_adapter import CoinbaseAdapter
            coinbase = CoinbaseClient(
                key_name=coinbase_key_name,
                private_key=coinbase_private_key,
            )
            return CoinbaseAdapter(coinbase)

    elif exchange_type == "dex":
        if not chain_id or not private_key or not rpc_url or not dex_router:
            raise ValueError("DEX requires chain_id, private_key, rpc_url, and dex_router")

        from app.exchange_clients.dex_client import DEXClient
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

    Args:
        bot_config: Bot configuration dictionary containing exchange credentials

    Returns:
        ExchangeClient instance configured for this bot
    """
    exchange_type = bot_config.get("exchange_type", "cex")
    exchange_name = bot_config.get("exchange_name", "coinbase")

    if exchange_type == "cex":
        if exchange_name == "bybit":
            return create_exchange_client(
                exchange_type="cex",
                exchange_name="bybit",
                bybit_api_key=bot_config.get("bybit_api_key"),
                bybit_api_secret=bot_config.get("bybit_api_secret"),
                bybit_testnet=bot_config.get("bybit_testnet", False),
            )
        elif exchange_name == "mt5_bridge":
            return create_exchange_client(
                exchange_type="cex",
                exchange_name="mt5_bridge",
                mt5_bridge_url=bot_config.get("mt5_bridge_url"),
                mt5_magic_number=bot_config.get("mt5_magic_number", 12345),
                mt5_account_balance=bot_config.get("mt5_account_balance", 100000.0),
            )
        else:
            return create_exchange_client(
                exchange_type="cex",
                exchange_name="coinbase",
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
