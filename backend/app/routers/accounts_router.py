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
from app.models import Account, Bot

logger = logging.getLogger(__name__)

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


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("", response_model=List[AccountResponse])
async def list_accounts(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    List all accounts.

    Returns all active accounts by default. Set include_inactive=true to include
    disabled accounts.
    """
    try:
        query = select(Account)
        if not include_inactive:
            query = query.where(Account.is_active == True)
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
    db: AsyncSession = Depends(get_db)
):
    """Get a specific account by ID."""
    try:
        query = select(Account).where(Account.id == account_id)
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
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new account.

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

        # If this is set as default, unset other defaults
        if account_data.is_default:
            await db.execute(
                update(Account).where(Account.is_default == True).values(is_default=False)
            )

        # Create the account
        account = Account(
            name=account_data.name,
            type=account_data.type,
            is_default=account_data.is_default,
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
            update(Account).where(Account.is_default == True).values(is_default=False)
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
        query = select(Account).where(Account.is_default == True)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            # If no default, return the first active account
            query = select(Account).where(Account.is_active == True).order_by(Account.created_at.asc())
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
