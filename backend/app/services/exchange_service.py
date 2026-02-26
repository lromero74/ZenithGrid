"""
Exchange Service

Provides exchange clients based on user accounts stored in the database.
Supports per-user, per-account exchange client instantiation.
Includes support for paper trading accounts.
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ExchangeUnavailableError, ValidationError

from app.coinbase_unified_client import CoinbaseClient
from app.encryption import decrypt_value, is_encrypted
from app.exchange_clients.base import ExchangeClient
from app.exchange_clients.factory import (
    create_exchange_client, ExchangeClientConfig, CoinbaseCredentials,
    ByBitCredentials, MT5BridgeCredentials, DEXCredentials,
)
from app.exchange_clients.paper_trading_client import PaperTradingClient
from app.models import Account

logger = logging.getLogger(__name__)

# Cache for exchange clients (key: account_id)
# This avoids recreating clients on every request
_exchange_client_cache: dict[int, ExchangeClient] = {}
_exchange_client_lock = asyncio.Lock()


async def get_coinbase_for_account(
    account: Account,
) -> CoinbaseClient:
    """
    Create a Coinbase client for a specific account.

    Args:
        account: The CEX account with API credentials

    Returns:
        CoinbaseClient instance
    """
    if account.type != "cex":
        raise ValidationError("Cannot create Coinbase client for non-CEX account")

    if not account.api_key_name or not account.api_private_key:
        raise ExchangeUnavailableError(
            "Coinbase account missing API credentials. Please update in Settings."
        )

    # Decrypt credentials if encrypted
    key_name = account.api_key_name
    if is_encrypted(key_name):
        key_name = decrypt_value(key_name)
    private_key = account.api_private_key
    if is_encrypted(private_key):
        private_key = decrypt_value(private_key)

    client = create_exchange_client(ExchangeClientConfig(
        exchange_type="cex",
        coinbase=CoinbaseCredentials(key_name=key_name, private_key=private_key),
    ))

    if not client:
        raise ExchangeUnavailableError(
            "Failed to create Coinbase client. Please check your API credentials."
        )

    return client


def clear_exchange_client_cache(account_id: Optional[int] = None):
    """Clear cached exchange clients (call when credentials change or account deleted)."""
    if account_id is not None:
        client = _exchange_client_cache.pop(account_id, None)
        if client and hasattr(client, 'close'):
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(client.close())
            except RuntimeError:
                pass  # No event loop — client will be GC'd
    else:
        # Close all clients that support it before clearing
        for _aid, _client in list(_exchange_client_cache.items()):
            if _client and hasattr(_client, 'close'):
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_client.close())
                except RuntimeError:
                    pass
        _exchange_client_cache.clear()

    # Also clear the monitor's per-account exchange cache
    try:
        from app.multi_bot_monitor import clear_monitor_exchange_cache
        clear_monitor_exchange_cache(account_id)
    except ImportError:
        pass


async def get_exchange_client_for_account(
    db: AsyncSession,
    account_id: int,
    use_cache: bool = True
) -> Optional[ExchangeClient]:
    """
    Get an exchange client for a specific account.

    Args:
        db: Database session
        account_id: The account ID to get client for
        use_cache: Whether to use cached client (default True)

    Returns:
        ExchangeClient or None if account not found or credentials missing
    """
    # Check cache first (lock-free fast path)
    if use_cache and account_id in _exchange_client_cache:
        return _exchange_client_cache[account_id]

    # Acquire lock for creation to prevent concurrent duplicate creation
    async with _exchange_client_lock:
        # Double-check after acquiring lock (another coroutine may have created it)
        if use_cache and account_id in _exchange_client_cache:
            return _exchange_client_cache[account_id]

        # Fetch account from database
        result = await db.execute(
            select(Account).where(Account.id == account_id)
        )
        account = result.scalar_one_or_none()

        if not account:
            logger.warning(f"Account {account_id} not found")
            return None

        if not account.is_active:
            logger.warning(f"Account {account_id} is not active")
            return None

        # Check if this is a paper trading account
        if account.is_paper_trading:
            logger.info(f"Creating paper trading client for account {account_id}")

            # Get a real CEX account for price data (scoped to same user)
            real_client = None
            try:
                cex_result = await db.execute(
                    select(Account).where(
                        Account.type == "cex",
                        Account.user_id == account.user_id,
                        Account.is_active.is_(True),
                        Account.is_paper_trading.is_(False),
                        Account.api_key_name.isnot(None),
                        Account.api_private_key.isnot(None)
                    ).order_by(Account.is_default.desc(), Account.created_at)
                    .limit(1)
                )
                cex_account = cex_result.scalar_one_or_none()

                if cex_account:
                    kn = cex_account.api_key_name
                    if is_encrypted(kn):
                        kn = decrypt_value(kn)
                    pk = cex_account.api_private_key
                    if is_encrypted(pk):
                        pk = decrypt_value(pk)
                    real_client = create_exchange_client(ExchangeClientConfig(
                        exchange_type="cex",
                        coinbase=CoinbaseCredentials(
                            key_name=kn, private_key=pk, account_id=cex_account.id,
                        ),
                    ))
                    logger.info(f"Using CEX account {cex_account.id} for paper trading price data")
            except Exception as e:
                logger.warning(f"Failed to get real client for paper trading price data: {e}")

            client = PaperTradingClient(account=account, db=db, real_client=real_client)
            # Don't cache paper trading clients (they hold db session)
            return client

        # Create exchange client based on account type
        client = None
        if account.type == "cex":
            exchange_name = account.exchange or "coinbase"

            if exchange_name == "bybit":
                # ByBit V5 (HyroTrader / prop firms)
                if not account.api_key_name or not account.api_private_key:
                    logger.warning(f"Account {account_id} missing ByBit API credentials")
                    return None
                ak = account.api_key_name
                if is_encrypted(ak):
                    ak = decrypt_value(ak)
                sk = account.api_private_key
                if is_encrypted(sk):
                    sk = decrypt_value(sk)
                # Testnet flag from prop_firm_config
                config = account.prop_firm_config or {}
                testnet = config.get("testnet", False)
                client = create_exchange_client(ExchangeClientConfig(
                    exchange_type="cex",
                    exchange_name="bybit",
                    bybit=ByBitCredentials(api_key=ak, api_secret=sk, testnet=testnet),
                ))

            elif exchange_name == "mt5_bridge":
                # MT5 Bridge (FTMO)
                config = account.prop_firm_config or {}
                bridge_url = config.get("bridge_url")
                if not bridge_url:
                    logger.warning(f"Account {account_id} missing MT5 bridge_url")
                    return None
                client = create_exchange_client(ExchangeClientConfig(
                    exchange_type="cex",
                    exchange_name="mt5_bridge",
                    mt5=MT5BridgeCredentials(
                        bridge_url=bridge_url,
                        magic_number=config.get("magic_number", 12345),
                        account_balance=account.prop_initial_deposit or 100000.0,
                    ),
                ))

            else:
                # Default: Coinbase
                if not account.api_key_name or not account.api_private_key:
                    logger.warning(f"Account {account_id} missing API credentials")
                    return None
                kn = account.api_key_name
                if is_encrypted(kn):
                    kn = decrypt_value(kn)
                pk = account.api_private_key
                if is_encrypted(pk):
                    pk = decrypt_value(pk)
                client = create_exchange_client(ExchangeClientConfig(
                    exchange_type="cex",
                    coinbase=CoinbaseCredentials(
                        key_name=kn, private_key=pk, account_id=account_id,
                    ),
                ))

        elif account.type == "dex":
            if not account.wallet_private_key or not account.rpc_url:
                logger.warning(f"Account {account_id} missing DEX credentials")
                return None

            wpk = account.wallet_private_key
            if is_encrypted(wpk):
                wpk = decrypt_value(wpk)
            client = create_exchange_client(ExchangeClientConfig(
                exchange_type="dex",
                dex=DEXCredentials(
                    chain_id=account.chain_id,
                    private_key=wpk,
                    rpc_url=account.rpc_url,
                    dex_router=None,  # TODO: Get from account or default
                ),
            ))
        else:
            logger.error(f"Unknown account type: {account.type}")
            return None

        # Wrap with PropGuard if this is a prop firm account
        if client and account.prop_firm:
            from app.database import async_session_maker
            from app.exchange_clients.prop_guard import PropGuardClient
            from app.exchange_clients.bybit_ws import get_ws_manager

            ws_state = None
            ws_mgr = get_ws_manager(account_id)
            if ws_mgr:
                ws_state = ws_mgr.state

            client = PropGuardClient(
                inner=client,
                account_id=account_id,
                db_session_maker=async_session_maker,
                daily_drawdown_pct=account.prop_daily_drawdown_pct or 4.5,
                total_drawdown_pct=account.prop_total_drawdown_pct or 9.0,
                initial_deposit=account.prop_initial_deposit or 100000.0,
                ws_state=ws_state,
            )
            logger.info(
                f"PropGuard wrapped account {account_id} "
                f"(firm={account.prop_firm}, "
                f"daily_dd={account.prop_daily_drawdown_pct}%, "
                f"total_dd={account.prop_total_drawdown_pct}%)"
            )

        # Cache the client
        if client and use_cache:
            _exchange_client_cache[account_id] = client

        return client


async def get_exchange_client_for_user(
    db: AsyncSession,
    user_id: int,
    account_type: str = "cex"
) -> Optional[ExchangeClient]:
    """
    Get the default exchange client for a user.

    Args:
        db: Database session
        user_id: The user ID
        account_type: "cex" or "dex" (default "cex")

    Returns:
        ExchangeClient for user's default account, or first active account
    """
    # First try to find default account
    result = await db.execute(
        select(Account).where(
            Account.user_id == user_id,
            Account.type == account_type,
            Account.is_default.is_(True),
            Account.is_active.is_(True)
        )
    )
    account = result.scalar_one_or_none()

    # If no default, get first active account of type
    if not account:
        result = await db.execute(
            select(Account).where(
                Account.user_id == user_id,
                Account.type == account_type,
                Account.is_active.is_(True)
            ).order_by(Account.created_at)
            .limit(1)
        )
        account = result.scalar_one_or_none()

    if not account:
        logger.debug(f"No {account_type} account found for user {user_id}")
        return None

    return await get_exchange_client_for_account(db, account.id)


async def get_default_cex_account(db: AsyncSession, user_id: int) -> Optional[Account]:
    """Get user's default CEX account (or first active one)"""
    # First try default
    result = await db.execute(
        select(Account).where(
            Account.user_id == user_id,
            Account.type == "cex",
            Account.is_default.is_(True),
            Account.is_active.is_(True)
        ).limit(1)
    )
    account = result.scalar_one_or_none()

    if not account:
        result = await db.execute(
            select(Account).where(
                Account.user_id == user_id,
                Account.type == "cex",
                Account.is_active.is_(True)
            ).order_by(Account.created_at)
            .limit(1)
        )
        account = result.scalar_one_or_none()

    return account


async def create_or_update_cex_account(
    db: AsyncSession,
    user_id: int,
    name: str,
    api_key_name: str,
    api_private_key: str,
    exchange: str = "coinbase",
    make_default: bool = True
) -> Account:
    """
    Create or update a CEX account for a user.

    Args:
        db: Database session
        user_id: The user ID
        name: Account display name
        api_key_name: Coinbase CDP key name
        api_private_key: Coinbase CDP private key
        exchange: Exchange name (default "coinbase")
        make_default: Whether to make this the default account

    Returns:
        The created or updated Account
    """
    # Check if user already has an account with this exchange
    result = await db.execute(
        select(Account).where(
            Account.user_id == user_id,
            Account.type == "cex",
            Account.exchange == exchange
        )
    )
    account = result.scalar_one_or_none()

    from app.encryption import encrypt_value as _encrypt
    if account:
        # Update existing
        account.name = name
        account.api_key_name = api_key_name
        account.api_private_key = _encrypt(api_private_key)
        if make_default:
            account.is_default = True
        # Clear cache for this account
        clear_exchange_client_cache(account.id)
    else:
        # Create new
        account = Account(
            user_id=user_id,
            name=name,
            type="cex",
            exchange=exchange,
            api_key_name=api_key_name,
            api_private_key=_encrypt(api_private_key),
            is_default=make_default,
            is_active=True
        )
        db.add(account)

    # If making this default, unset other defaults
    if make_default:
        await db.execute(
            select(Account).where(
                Account.user_id == user_id,
                Account.type == "cex",
                Account.id != (account.id if account.id else -1)
            )
        )
        # Update all other accounts to not be default
        other_result = await db.execute(
            select(Account).where(
                Account.user_id == user_id,
                Account.type == "cex",
                Account.is_default.is_(True),
                Account.id != (account.id if account.id else -1)
            )
        )
        for other_account in other_result.scalars():
            other_account.is_default = False

    await db.commit()
    await db.refresh(account)

    return account
