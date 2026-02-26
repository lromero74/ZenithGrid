"""
Exchange Client Factory

Factory pattern for creating exchange clients based on configuration.
Determines whether to create a CEX (Coinbase, ByBit), DEX (Uniswap),
or bridge (MT5) client based on bot configuration.

This centralizes exchange client creation and makes it easy to add new exchange types.
"""

from dataclasses import dataclass, field
from typing import Optional

from app.exchange_clients.base import ExchangeClient


@dataclass
class CoinbaseCredentials:
    """Coinbase API credentials."""
    key_name: Optional[str] = None
    private_key: Optional[str] = None
    account_id: Optional[int] = None


@dataclass
class ByBitCredentials:
    """ByBit API credentials."""
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    testnet: bool = False


@dataclass
class MT5BridgeCredentials:
    """MT5 Bridge connection config."""
    bridge_url: Optional[str] = None
    magic_number: int = 12345
    account_balance: float = 100000.0


@dataclass
class DEXCredentials:
    """DEX wallet and chain config."""
    chain_id: Optional[int] = None
    private_key: Optional[str] = None
    rpc_url: Optional[str] = None
    dex_router: Optional[str] = None


@dataclass
class ExchangeClientConfig:
    """Configuration for creating an exchange client.

    Groups all exchange credentials by type, eliminating the 15-param
    function signature. Only populate the credentials relevant to
    the exchange_type/exchange_name being used.
    """
    exchange_type: str
    exchange_name: str = "coinbase"
    coinbase: CoinbaseCredentials = field(default_factory=CoinbaseCredentials)
    bybit: ByBitCredentials = field(default_factory=ByBitCredentials)
    mt5: MT5BridgeCredentials = field(default_factory=MT5BridgeCredentials)
    dex: DEXCredentials = field(default_factory=DEXCredentials)


def create_exchange_client(config: ExchangeClientConfig) -> Optional[ExchangeClient]:
    """
    Factory function to create the appropriate exchange client.

    Args:
        config: ExchangeClientConfig with exchange type and credentials

    Returns:
        ExchangeClient instance, or None if credentials missing

    Raises:
        ValueError: If exchange_type or exchange_name is invalid
    """

    if config.exchange_type == "cex":
        if config.exchange_name == "bybit":
            # ByBit V5 (HyroTrader / prop firms)
            if not config.bybit.api_key or not config.bybit.api_secret:
                return None
            # Lazy import to avoid loading pybit unless needed
            from app.exchange_clients.bybit_client import ByBitClient
            from app.exchange_clients.bybit_adapter import ByBitAdapter
            client = ByBitClient(
                api_key=config.bybit.api_key,
                api_secret=config.bybit.api_secret,
                testnet=config.bybit.testnet,
            )
            return ByBitAdapter(client)

        elif config.exchange_name == "mt5_bridge":
            # MT5 Bridge (FTMO)
            if not config.mt5.bridge_url:
                return None
            from app.exchange_clients.mt5_bridge_client import MT5BridgeClient
            return MT5BridgeClient(
                bridge_url=config.mt5.bridge_url,
                magic_number=config.mt5.magic_number,
                account_balance=config.mt5.account_balance,
            )

        else:
            # Default: Coinbase
            if not config.coinbase.key_name or not config.coinbase.private_key:
                return None

            from app.coinbase_unified_client import CoinbaseClient
            from app.exchange_clients.coinbase_adapter import CoinbaseAdapter
            coinbase = CoinbaseClient(
                key_name=config.coinbase.key_name,
                private_key=config.coinbase.private_key,
                account_id=config.coinbase.account_id,
            )
            return CoinbaseAdapter(coinbase)

    elif config.exchange_type == "dex":
        if (not config.dex.chain_id or not config.dex.private_key
                or not config.dex.rpc_url or not config.dex.dex_router):
            raise ValueError("DEX requires chain_id, private_key, rpc_url, and dex_router")

        from app.exchange_clients.dex_client import DEXClient
        return DEXClient(
            chain_id=config.dex.chain_id,
            rpc_url=config.dex.rpc_url,
            wallet_private_key=config.dex.private_key,
            dex_router=config.dex.dex_router,
        )

    else:
        raise ValueError(f"Unknown exchange type: {config.exchange_type}. Must be 'cex' or 'dex'.")


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
            return create_exchange_client(ExchangeClientConfig(
                exchange_type="cex",
                exchange_name="bybit",
                bybit=ByBitCredentials(
                    api_key=bot_config.get("bybit_api_key"),
                    api_secret=bot_config.get("bybit_api_secret"),
                    testnet=bot_config.get("bybit_testnet", False),
                ),
            ))
        elif exchange_name == "mt5_bridge":
            return create_exchange_client(ExchangeClientConfig(
                exchange_type="cex",
                exchange_name="mt5_bridge",
                mt5=MT5BridgeCredentials(
                    bridge_url=bot_config.get("mt5_bridge_url"),
                    magic_number=bot_config.get("mt5_magic_number", 12345),
                    account_balance=bot_config.get("mt5_account_balance", 100000.0),
                ),
            ))
        else:
            return create_exchange_client(ExchangeClientConfig(
                exchange_type="cex",
                exchange_name="coinbase",
                coinbase=CoinbaseCredentials(
                    key_name=bot_config["coinbase_key_name"],
                    private_key=bot_config["coinbase_private_key"],
                    account_id=bot_config.get("account_id"),
                ),
            ))
    elif exchange_type == "dex":
        return create_exchange_client(ExchangeClientConfig(
            exchange_type="dex",
            dex=DEXCredentials(
                chain_id=bot_config["chain_id"],
                private_key=bot_config["wallet_private_key"],
                rpc_url=bot_config["rpc_url"],
                dex_router=bot_config["dex_router"],
            ),
        ))
    else:
        raise ValueError(f"Unknown exchange type in bot config: {exchange_type}")
