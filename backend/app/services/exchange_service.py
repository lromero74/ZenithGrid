"""
Exchange Service

Provides exchange clients based on user accounts stored in the database.
Supports per-user, per-account exchange client instantiation.
Includes support for paper trading accounts.
"""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Account
from app.exchange_clients.factory import create_exchange_client
from app.exchange_clients.base import ExchangeClient
from app.exchange_clients.paper_trading_client import PaperTradingClient

logger = logging.getLogger(__name__)

# Cache for exchange clients (key: account_id)
# This avoids recreating clients on every request
_exchange_client_cache: dict[int, ExchangeClient] = {}


def clear_exchange_client_cache(account_id: Optional[int] = None):
    """Clear cached exchange clients (call when credentials change)"""
    global _exchange_client_cache
    if account_id is not None:
        _exchange_client_cache.pop(account_id, None)
    else:
        _exchange_client_cache.clear()


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
    global _exchange_client_cache

    # Check cache first
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
        client = PaperTradingClient(account=account, db=db)
        # Don't cache paper trading clients (they hold db session)
        return client

    # Create exchange client based on account type
    if account.type == "cex":
        if not account.api_key_name or not account.api_private_key:
            logger.warning(f"Account {account_id} missing API credentials")
            return None

        client = create_exchange_client(
            exchange_type="cex",
            coinbase_key_name=account.api_key_name,
            coinbase_private_key=account.api_private_key,
        )
    elif account.type == "dex":
        if not account.wallet_private_key or not account.rpc_url:
            logger.warning(f"Account {account_id} missing DEX credentials")
            return None

        client = create_exchange_client(
            exchange_type="dex",
            chain_id=account.chain_id,
            private_key=account.wallet_private_key,
            rpc_url=account.rpc_url,
            dex_router=None,  # TODO: Get from account or default
        )
    else:
        logger.error(f"Unknown account type: {account.type}")
        return None

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
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        result = await db.execute(
            select(Account).where(
                Account.user_id == user_id,
                Account.type == "cex",
                Account.is_active.is_(True)
            ).order_by(Account.created_at)
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

    if account:
        # Update existing
        account.name = name
        account.api_key_name = api_key_name
        account.api_private_key = api_private_key
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
            api_private_key=api_private_key,
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
