"""
Accounts management API routes

Handles CRUD operations for trading accounts:
- CEX accounts (Coinbase) with API credentials
- DEX wallets (MetaMask, WalletConnect) with wallet addresses

This enables multi-account trading where each bot is linked to a specific account,
and the UI can filter by selected account.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Account, Bot, User
from app.routers.auth_dependencies import get_current_user_optional
from app.exchange_clients.factory import create_exchange_client
from app.coinbase_unified_client import CoinbaseClient
from app.routers.accounts import get_cex_portfolio, get_dex_portfolio

logger = logging.getLogger(__name__)


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
        raise HTTPException(
            status_code=400,
            detail="Cannot create Coinbase client for non-CEX account"
        )

    if not account.api_key_name or not account.api_private_key:
        raise HTTPException(
            status_code=503,
            detail="Coinbase account missing API credentials. Please update in Settings."
        )

    client = create_exchange_client(
        exchange_type="cex",
        coinbase_key_name=account.api_key_name,
        coinbase_private_key=account.api_private_key,
    )

    if not client:
        raise HTTPException(
            status_code=503,
            detail="Failed to create Coinbase client. Please check your API credentials."
        )

    return client

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


# =============================================================================
# Pydantic Models
# =============================================================================


class AccountBase(BaseModel):
    """Base fields for account creation/update"""
    name: str = Field(..., description="User-friendly account name")
    type: str = Field(..., description="Account type: 'cex' or 'dex'")

    # CEX fields (optional)
    exchange: Optional[str] = Field(None, description="Exchange name (e.g., 'coinbase')")
    api_key_name: Optional[str] = Field(None, description="API key name/ID")
    api_private_key: Optional[str] = Field(None, description="API private key (will be encrypted)")

    # DEX fields (optional)
    chain_id: Optional[int] = Field(None, description="Blockchain chain ID")
    wallet_address: Optional[str] = Field(None, description="Wallet public address")
    wallet_private_key: Optional[str] = Field(None, description="Wallet private key (optional, will be encrypted)")
    rpc_url: Optional[str] = Field(None, description="RPC endpoint URL")
    wallet_type: Optional[str] = Field(None, description="Wallet type: 'metamask', 'walletconnect', 'private_key'")


class AccountCreate(AccountBase):
    """Model for creating a new account"""
    is_default: bool = Field(False, description="Set as default account")


class AccountUpdate(BaseModel):
    """Model for updating an account (all fields optional)"""
    name: Optional[str] = None
    is_active: Optional[bool] = None

    # CEX fields
    exchange: Optional[str] = None
    api_key_name: Optional[str] = None
    api_private_key: Optional[str] = None

    # DEX fields
    chain_id: Optional[int] = None
    wallet_address: Optional[str] = None
    wallet_private_key: Optional[str] = None
    rpc_url: Optional[str] = None
    wallet_type: Optional[str] = None


class AccountResponse(BaseModel):
    """Response model for account data"""
    id: int
    name: str
    type: str
    is_default: bool
    is_active: bool
    is_paper_trading: bool = False

    # CEX fields
    exchange: Optional[str] = None
    api_key_name: Optional[str] = None
    # Note: api_private_key is never returned for security

    # DEX fields
    chain_id: Optional[int] = None
    wallet_address: Optional[str] = None
    # Note: wallet_private_key is never returned for security
    rpc_url: Optional[str] = None
    wallet_type: Optional[str] = None

    # Metadata
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None

    # Computed fields
    display_name: Optional[str] = None
    short_address: Optional[str] = None
    bot_count: int = 0

    class Config:
        from_attributes = True


class AccountWithBalance(AccountResponse):
    """Account response with balance information"""
    balance_usd: float = 0.0
    balance_native: float = 0.0  # BTC for CEX, ETH for DEX (chain-dependent)
    native_symbol: str = "BTC"


# Auto-buy BTC Settings Schemas
class AutoBuySettings(BaseModel):
    """Auto-buy BTC settings for an account"""
    enabled: bool
    check_interval_minutes: int
    order_type: str  # "market" or "limit"

    # Per-stablecoin settings
    usd_enabled: bool
    usd_min: float

    usdc_enabled: bool
    usdc_min: float

    usdt_enabled: bool
    usdt_min: float


class AutoBuySettingsUpdate(BaseModel):
    """Update model for auto-buy settings (all fields optional)"""
    enabled: Optional[bool] = None
    check_interval_minutes: Optional[int] = None
    order_type: Optional[str] = None

    # Per-stablecoin settings
    usd_enabled: Optional[bool] = None
    usd_min: Optional[float] = None

    usdc_enabled: Optional[bool] = None
    usdc_min: Optional[float] = None

    usdt_enabled: Optional[bool] = None
    usdt_min: Optional[float] = None


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("", response_model=List[AccountResponse])
async def list_accounts(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    List all accounts for the current user.

    Returns all active accounts by default. Set include_inactive=true to include
    disabled accounts. If authenticated, returns only accounts belonging to the user.
    """
    try:
        query = select(Account)
        # Filter by user if authenticated
        if current_user:
            query = query.where(Account.user_id == current_user.id)
        if not include_inactive:
            query = query.where(Account.is_active)
        query = query.order_by(Account.is_default.desc(), Account.created_at.asc())

        result = await db.execute(query)
        accounts = result.scalars().all()

        # Get bot counts for each account
        response = []
        for account in accounts:
            bot_count_query = select(Bot).where(Bot.account_id == account.id)
            bot_result = await db.execute(bot_count_query)
            bot_count = len(bot_result.scalars().all())

            response.append(AccountResponse(
                id=account.id,
                name=account.name,
                type=account.type,
                is_default=account.is_default,
                is_active=account.is_active,
                is_paper_trading=account.is_paper_trading or False,
                exchange=account.exchange,
                api_key_name=account.api_key_name,
                chain_id=account.chain_id,
                wallet_address=account.wallet_address,
                rpc_url=account.rpc_url,
                wallet_type=account.wallet_type,
                created_at=account.created_at,
                updated_at=account.updated_at,
                last_used_at=account.last_used_at,
                display_name=account.get_display_name(),
                short_address=account.get_short_address() if account.type == "dex" else None,
                bot_count=bot_count
            ))

        return response

    except Exception as e:
        logger.error(f"Error listing accounts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Get a specific account by ID (must belong to current user if authenticated)."""
    try:
        query = select(Account).where(Account.id == account_id)
        # Filter by user if authenticated
        if current_user:
            query = query.where(Account.user_id == current_user.id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        # Get bot count
        bot_count_query = select(Bot).where(Bot.account_id == account.id)
        bot_result = await db.execute(bot_count_query)
        bot_count = len(bot_result.scalars().all())

        return AccountResponse(
            id=account.id,
            name=account.name,
            type=account.type,
            is_default=account.is_default,
            is_active=account.is_active,
            is_paper_trading=account.is_paper_trading or False,
            exchange=account.exchange,
            api_key_name=account.api_key_name,
            chain_id=account.chain_id,
            wallet_address=account.wallet_address,
            rpc_url=account.rpc_url,
            wallet_type=account.wallet_type,
            created_at=account.created_at,
            updated_at=account.updated_at,
            last_used_at=account.last_used_at,
            display_name=account.get_display_name(),
            short_address=account.get_short_address() if account.type == "dex" else None,
            bot_count=bot_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting account {account_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=AccountResponse)
async def create_account(
    account_data: AccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Create a new account for the current user.

    For CEX accounts, provide exchange, api_key_name, and api_private_key.
    For DEX accounts, provide chain_id, wallet_address, and optionally rpc_url and wallet_private_key.
    """
    try:
        # Validate account type
        if account_data.type not in ["cex", "dex"]:
            raise HTTPException(status_code=400, detail="Account type must be 'cex' or 'dex'")

        # Validate required fields based on type
        if account_data.type == "cex":
            if not account_data.exchange:
                raise HTTPException(status_code=400, detail="CEX accounts require 'exchange' field")
        else:  # dex
            if not account_data.chain_id:
                raise HTTPException(status_code=400, detail="DEX accounts require 'chain_id' field")
            if not account_data.wallet_address:
                raise HTTPException(status_code=400, detail="DEX accounts require 'wallet_address' field")

        # If this is set as default, unset other defaults (for this user if authenticated)
        if account_data.is_default:
            default_filter = Account.is_default
            if current_user:
                default_filter = Account.is_default & (Account.user_id == current_user.id)
            await db.execute(
                update(Account).where(default_filter).values(is_default=False)
            )

        # Create the account
        account = Account(
            name=account_data.name,
            type=account_data.type,
            is_default=account_data.is_default,
            user_id=current_user.id if current_user else None,
            is_active=True,
            exchange=account_data.exchange,
            api_key_name=account_data.api_key_name,
            api_private_key=account_data.api_private_key,  # TODO: Encrypt this
            chain_id=account_data.chain_id,
            wallet_address=account_data.wallet_address,
            wallet_private_key=account_data.wallet_private_key,  # TODO: Encrypt this
            rpc_url=account_data.rpc_url,
            wallet_type=account_data.wallet_type,
        )

        db.add(account)
        await db.commit()
        await db.refresh(account)

        logger.info(f"Created account: {account.name} (type={account.type}, id={account.id})")

        return AccountResponse(
            id=account.id,
            name=account.name,
            type=account.type,
            is_default=account.is_default,
            is_active=account.is_active,
            is_paper_trading=account.is_paper_trading or False,
            exchange=account.exchange,
            api_key_name=account.api_key_name,
            chain_id=account.chain_id,
            wallet_address=account.wallet_address,
            rpc_url=account.rpc_url,
            wallet_type=account.wallet_type,
            created_at=account.created_at,
            updated_at=account.updated_at,
            last_used_at=account.last_used_at,
            display_name=account.get_display_name(),
            short_address=account.get_short_address() if account.type == "dex" else None,
            bot_count=0
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating account: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    account_data: AccountUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an existing account."""
    try:
        # Get the account
        query = select(Account).where(Account.id == account_id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        # Update fields that are provided
        update_data = account_data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if value is not None:
                setattr(account, field, value)

        account.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(account)

        # Get bot count
        bot_count_query = select(Bot).where(Bot.account_id == account.id)
        bot_result = await db.execute(bot_count_query)
        bot_count = len(bot_result.scalars().all())

        logger.info(f"Updated account: {account.name} (id={account.id})")

        return AccountResponse(
            id=account.id,
            name=account.name,
            type=account.type,
            is_default=account.is_default,
            is_active=account.is_active,
            is_paper_trading=account.is_paper_trading or False,
            exchange=account.exchange,
            api_key_name=account.api_key_name,
            chain_id=account.chain_id,
            wallet_address=account.wallet_address,
            rpc_url=account.rpc_url,
            wallet_type=account.wallet_type,
            created_at=account.created_at,
            updated_at=account.updated_at,
            last_used_at=account.last_used_at,
            display_name=account.get_display_name(),
            short_address=account.get_short_address() if account.type == "dex" else None,
            bot_count=bot_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating account {account_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete an account.

    This will fail if there are bots linked to this account.
    Unlink or delete bots first.
    """
    try:
        # Get the account
        query = select(Account).where(Account.id == account_id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        # Check if any bots are linked
        bot_query = select(Bot).where(Bot.account_id == account_id)
        bot_result = await db.execute(bot_query)
        linked_bots = bot_result.scalars().all()

        if linked_bots:
            bot_names = ", ".join([b.name for b in linked_bots])
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete account with linked bots. Unlink these bots first: {bot_names}"
            )

        # Delete the account
        await db.delete(account)
        await db.commit()

        logger.info(f"Deleted account: {account.name} (id={account_id})")

        return {"message": f"Account '{account.name}' deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting account {account_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{account_id}/set-default")
async def set_default_account(
    account_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Set an account as the default."""
    try:
        # Get the account
        query = select(Account).where(Account.id == account_id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        # Unset all other defaults
        await db.execute(
            update(Account).where(Account.is_default).values(is_default=False)
        )

        # Set this one as default
        account.is_default = True
        account.updated_at = datetime.utcnow()

        await db.commit()

        logger.info(f"Set default account: {account.name} (id={account_id})")

        return {"message": f"Account '{account.name}' is now the default"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting default account {account_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{account_id}/bots")
async def get_account_bots(
    account_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get all bots linked to an account."""
    try:
        # Verify account exists
        account_query = select(Account).where(Account.id == account_id)
        account_result = await db.execute(account_query)
        account = account_result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        # Get bots
        bot_query = select(Bot).where(Bot.account_id == account_id)
        bot_result = await db.execute(bot_query)
        bots = bot_result.scalars().all()

        return {
            "account_id": account_id,
            "account_name": account.name,
            "bot_count": len(bots),
            "bots": [
                {
                    "id": bot.id,
                    "name": bot.name,
                    "strategy_type": bot.strategy_type,
                    "is_active": bot.is_active,
                    "product_ids": bot.get_trading_pairs()
                }
                for bot in bots
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting bots for account {account_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/default", response_model=AccountResponse)
async def get_default_account(
    db: AsyncSession = Depends(get_db)
):
    """Get the default account."""
    try:
        query = select(Account).where(Account.is_default)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            # If no default, return the first active account
            query = select(Account).where(Account.is_active).order_by(Account.created_at.asc())
            result = await db.execute(query)
            account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail="No accounts configured")

        # Get bot count
        bot_count_query = select(Bot).where(Bot.account_id == account.id)
        bot_result = await db.execute(bot_count_query)
        bot_count = len(bot_result.scalars().all())

        return AccountResponse(
            id=account.id,
            name=account.name,
            type=account.type,
            is_default=account.is_default,
            is_active=account.is_active,
            is_paper_trading=account.is_paper_trading or False,
            exchange=account.exchange,
            api_key_name=account.api_key_name,
            chain_id=account.chain_id,
            wallet_address=account.wallet_address,
            rpc_url=account.rpc_url,
            wallet_type=account.wallet_type,
            created_at=account.created_at,
            updated_at=account.updated_at,
            last_used_at=account.last_used_at,
            display_name=account.get_display_name(),
            short_address=account.get_short_address() if account.type == "dex" else None,
            bot_count=bot_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting default account: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{account_id}/portfolio")
async def get_account_portfolio(
    account_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get portfolio for a specific account.

    For CEX accounts: Fetches from Coinbase API
    For DEX accounts: Fetches from blockchain via RPC
    For Paper Trading accounts: Returns virtual balances
    """
    try:
        import json

        # Get the account
        query = select(Account).where(Account.id == account_id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        # Handle paper trading accounts
        if account.is_paper_trading:
            # Parse virtual balances from JSON
            if account.paper_balances:
                balances = json.loads(account.paper_balances)
            else:
                balances = {"BTC": 0.0, "ETH": 0.0, "USD": 0.0, "USDC": 0.0, "USDT": 0.0}

            # Get real prices for valuation (use system Coinbase client)
            from app.config import settings
            from app.coinbase_unified_client import CoinbaseClient

            system_coinbase = CoinbaseClient(
                api_key=settings.coinbase_api_key,
                api_secret=settings.coinbase_api_secret
            )
            btc_usd_price = await system_coinbase.get_btc_usd_price()
            eth_btc_price = await system_coinbase.get_current_price()  # ETH-BTC

            # Calculate totals
            btc_balance = balances.get("BTC", 0.0)
            eth_balance = balances.get("ETH", 0.0)
            usd_balance = balances.get("USD", 0.0)
            usdc_balance = balances.get("USDC", 0.0)
            usdt_balance = balances.get("USDT", 0.0)

            total_btc = btc_balance + (eth_balance * eth_btc_price)
            total_usd = (total_btc * btc_usd_price) + usd_balance + usdc_balance + usdt_balance

            # Build holdings array (compatible with frontend Portfolio page)
            holdings = []
            for currency, amount in balances.items():
                if amount > 0:
                    # Calculate USD and BTC values for this holding
                    if currency == "BTC":
                        usd_value = amount * btc_usd_price
                        btc_value = amount
                        current_price_usd = btc_usd_price
                    elif currency == "ETH":
                        btc_value = amount * eth_btc_price
                        usd_value = btc_value * btc_usd_price
                        current_price_usd = eth_btc_price * btc_usd_price
                    elif currency in ["USD", "USDC", "USDT"]:
                        usd_value = amount
                        btc_value = amount / btc_usd_price if btc_usd_price > 0 else 0
                        current_price_usd = 1.0
                    else:
                        # Unknown currency
                        usd_value = 0
                        btc_value = 0
                        current_price_usd = 0

                    percentage = (usd_value / total_usd * 100) if total_usd > 0 else 0

                    holdings.append({
                        "asset": currency,
                        "total_balance": amount,
                        "available": amount,
                        "hold": 0.0,
                        "current_price_usd": current_price_usd,
                        "usd_value": usd_value,
                        "btc_value": btc_value,
                        "percentage": percentage
                    })

            return {
                "holdings": holdings,
                "holdings_count": len(holdings),
                "total_btc_value": total_btc,
                "total_usd_value": total_usd,
                "btc_usd_price": btc_usd_price,
                "is_paper_trading": True
            }

        if account.type == "cex":
            # Use existing Coinbase portfolio logic
            return await get_cex_portfolio(account, db, get_coinbase_for_account)
        else:
            # Use DEX wallet service for blockchain balances
            return await get_dex_portfolio(account, db, get_coinbase_for_account)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting portfolio for account {account_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Auto-Buy BTC Settings Endpoints
# =============================================================================

@router.get("/{account_id}/auto-buy-settings", response_model=AutoBuySettings)
async def get_auto_buy_settings(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Get auto-buy BTC settings for an account"""
    query = select(Account).where(Account.id == account_id)

    # Filter by user if authenticated
    if current_user:
        query = query.where(Account.user_id == current_user.id)

    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    return AutoBuySettings(
        enabled=account.auto_buy_enabled or False,
        check_interval_minutes=account.auto_buy_check_interval_minutes or 5,
        order_type=account.auto_buy_order_type or "market",
        usd_enabled=account.auto_buy_usd_enabled or False,
        usd_min=account.auto_buy_usd_min or 10.0,
        usdc_enabled=account.auto_buy_usdc_enabled or False,
        usdc_min=account.auto_buy_usdc_min or 10.0,
        usdt_enabled=account.auto_buy_usdt_enabled or False,
        usdt_min=account.auto_buy_usdt_min or 10.0,
    )


@router.put("/{account_id}/auto-buy-settings", response_model=AutoBuySettings)
async def update_auto_buy_settings(
    account_id: int,
    settings: AutoBuySettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Update auto-buy BTC settings for an account"""
    query = select(Account).where(Account.id == account_id)

    # Filter by user if authenticated
    if current_user:
        query = query.where(Account.user_id == current_user.id)

    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    # Update fields if provided
    if settings.enabled is not None:
        account.auto_buy_enabled = settings.enabled
    if settings.check_interval_minutes is not None:
        account.auto_buy_check_interval_minutes = settings.check_interval_minutes
    if settings.order_type is not None:
        account.auto_buy_order_type = settings.order_type

    # Update per-stablecoin settings
    if settings.usd_enabled is not None:
        account.auto_buy_usd_enabled = settings.usd_enabled
    if settings.usd_min is not None:
        account.auto_buy_usd_min = settings.usd_min

    if settings.usdc_enabled is not None:
        account.auto_buy_usdc_enabled = settings.usdc_enabled
    if settings.usdc_min is not None:
        account.auto_buy_usdc_min = settings.usdc_min

    if settings.usdt_enabled is not None:
        account.auto_buy_usdt_enabled = settings.usdt_enabled
    if settings.usdt_min is not None:
        account.auto_buy_usdt_min = settings.usdt_min

    await db.commit()
    await db.refresh(account)

    return AutoBuySettings(
        enabled=account.auto_buy_enabled or False,
        check_interval_minutes=account.auto_buy_check_interval_minutes or 5,
        order_type=account.auto_buy_order_type or "market",
        usd_enabled=account.auto_buy_usd_enabled or False,
        usd_min=account.auto_buy_usd_min or 10.0,
        usdc_enabled=account.auto_buy_usdc_enabled or False,
        usdc_min=account.auto_buy_usdc_min or 10.0,
        usdt_enabled=account.auto_buy_usdt_enabled or False,
        usdt_min=account.auto_buy_usdt_min or 10.0,
    )
