"""
Accounts management API routes

Handles CRUD operations for trading accounts:
- CEX accounts (Coinbase) with API credentials
- DEX wallets (MetaMask, WalletConnect) with wallet addresses

This enables multi-account trading where each bot is linked to a specific account,
and the UI can filter by selected account.
"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.exceptions import AppError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.encryption import encrypt_value, mask_api_key
from app.models import Account, Bot, User
from app.auth.dependencies import get_current_user, require_permission, Perm
from app.services.account_service import (
    VALID_PROP_FIRMS,
    create_exchange_account,
    get_portfolio_for_account,
    validate_prop_firm_config,
)
from app.services.exchange_service import (
    clear_exchange_client_cache,
    get_coinbase_for_account,
)

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

    # Prop firm fields (optional)
    prop_firm: Optional[str] = Field(None, description="Prop firm: 'hyrotrader', 'ftmo', or None")
    prop_firm_config: Optional[dict] = Field(None, description="Firm-specific JSON config")
    prop_daily_drawdown_pct: Optional[float] = Field(
        None, ge=0.1, le=100.0, description="Max daily drawdown % (0.1-100)"
    )
    prop_total_drawdown_pct: Optional[float] = Field(
        None, ge=0.1, le=100.0, description="Max total drawdown % (0.1-100)"
    )
    prop_initial_deposit: Optional[float] = Field(
        None, gt=0, le=100_000_000, description="Starting capital in USD (>0)"
    )


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

    # Prop firm fields
    prop_firm: Optional[str] = None
    prop_firm_config: Optional[dict] = None
    prop_daily_drawdown_pct: Optional[float] = Field(None, ge=0.1, le=100.0)
    prop_total_drawdown_pct: Optional[float] = Field(None, ge=0.1, le=100.0)
    prop_initial_deposit: Optional[float] = Field(None, gt=0, le=100_000_000)


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

    # Perpetual Futures
    perps_portfolio_uuid: Optional[str] = None
    default_leverage: int = 1
    margin_type: str = "CROSS"

    # Prop firm
    prop_firm: Optional[str] = None
    prop_daily_drawdown_pct: Optional[float] = None
    prop_total_drawdown_pct: Optional[float] = None
    prop_initial_deposit: Optional[float] = None

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


# Portfolio Rebalancing Schemas
class RebalanceSettingsResponse(BaseModel):
    """Portfolio rebalance settings for an account"""
    enabled: bool
    target_usd_pct: float
    target_btc_pct: float
    target_eth_pct: float
    target_usdc_pct: float
    drift_threshold_pct: float
    check_interval_minutes: int
    min_trade_pct: float
    min_balance_usd: float
    min_balance_btc: float
    min_balance_eth: float
    min_balance_usdc: float


class RebalanceSettingsUpdate(BaseModel):
    """Update model for rebalance settings (all fields optional)"""
    enabled: Optional[bool] = None
    target_usd_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    target_btc_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    target_eth_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    target_usdc_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    drift_threshold_pct: Optional[float] = Field(None, ge=1.0, le=10.0)
    check_interval_minutes: Optional[int] = Field(None, ge=15, le=1440)
    min_trade_pct: Optional[float] = Field(None, ge=1.0, le=25.0)
    min_balance_usd: Optional[float] = Field(None, ge=0.0)
    min_balance_btc: Optional[float] = Field(None, ge=0.0)
    min_balance_eth: Optional[float] = Field(None, ge=0.0)
    min_balance_usdc: Optional[float] = Field(None, ge=0.0)


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("", response_model=List[AccountResponse])
async def list_accounts(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all accounts for the current user.

    Returns all active accounts by default. Set include_inactive=true to include
    disabled accounts. If authenticated, returns only accounts belonging to the user.
    """
    try:
        query = select(Account)
        query = query.where(Account.user_id == current_user.id)
        if not include_inactive:
            query = query.where(Account.is_active)
        query = query.order_by(Account.is_default.desc(), Account.created_at.asc())

        result = await db.execute(query)
        accounts = result.scalars().all()

        # Get bot counts for all accounts in a single aggregate query
        account_ids = [a.id for a in accounts]
        count_q = select(
            Bot.account_id, func.count(Bot.id).label("cnt")
        ).where(Bot.account_id.in_(account_ids)).group_by(Bot.account_id)
        count_result = await db.execute(count_q)
        bot_counts = {row.account_id: row.cnt for row in count_result}

        response = []
        for account in accounts:
            bot_count = bot_counts.get(account.id, 0)

            response.append(AccountResponse(
                id=account.id,
                name=account.name,
                type=account.type,
                is_default=account.is_default,
                is_active=account.is_active,
                is_paper_trading=account.is_paper_trading or False,
                exchange=account.exchange,
                api_key_name=mask_api_key(account.api_key_name),
                chain_id=account.chain_id,
                wallet_address=account.wallet_address,
                rpc_url=account.rpc_url,
                wallet_type=account.wallet_type,
                perps_portfolio_uuid=account.perps_portfolio_uuid,
                default_leverage=account.default_leverage or 1,
                margin_type=account.margin_type or "CROSS",
                prop_firm=account.prop_firm,
                prop_daily_drawdown_pct=account.prop_daily_drawdown_pct,
                prop_total_drawdown_pct=account.prop_total_drawdown_pct,
                prop_initial_deposit=account.prop_initial_deposit,
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
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific account by ID (must belong to current user if authenticated)."""
    try:
        query = select(Account).where(Account.id == account_id, Account.user_id == current_user.id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        # Get bot count with aggregate query
        bot_count_result = await db.execute(
            select(func.count(Bot.id)).where(Bot.account_id == account.id)
        )
        bot_count = bot_count_result.scalar() or 0

        return AccountResponse(
            id=account.id,
            name=account.name,
            type=account.type,
            is_default=account.is_default,
            is_active=account.is_active,
            is_paper_trading=account.is_paper_trading or False,
            exchange=account.exchange,
            api_key_name=mask_api_key(account.api_key_name),
            chain_id=account.chain_id,
            wallet_address=account.wallet_address,
            rpc_url=account.rpc_url,
            wallet_type=account.wallet_type,
            perps_portfolio_uuid=account.perps_portfolio_uuid,
            default_leverage=account.default_leverage or 1,
            margin_type=account.margin_type or "CROSS",
            prop_firm=account.prop_firm,
            prop_daily_drawdown_pct=account.prop_daily_drawdown_pct,
            prop_total_drawdown_pct=account.prop_total_drawdown_pct,
            prop_initial_deposit=account.prop_initial_deposit,
            created_at=account.created_at,
            updated_at=account.updated_at,
            last_used_at=account.last_used_at,
            display_name=account.get_display_name(),
            short_address=account.get_short_address() if account.type == "dex" else None,
            bot_count=bot_count
        )

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error getting account {account_id}: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.post("", response_model=AccountResponse)
async def create_account(
    account_data: AccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE))
):
    """
    Create a new account for the current user.

    For CEX accounts, provide exchange, api_key_name, and api_private_key.
    For DEX accounts, provide chain_id, wallet_address, and optionally rpc_url and wallet_private_key.
    """
    # Block non-privileged users from adding live exchange accounts
    if not current_user.is_superuser:
        user_groups = {g.name for g in (current_user.groups or [])}
        privileged = {"System Owners", "Administrators", "Traders"}
        if not user_groups & privileged:
            raise HTTPException(
                status_code=403,
                detail="live_accounts_restricted",
            )

    try:
        account = await create_exchange_account(db, current_user, account_data)

        return AccountResponse(
            id=account.id,
            name=account.name,
            type=account.type,
            is_default=account.is_default,
            is_active=account.is_active,
            is_paper_trading=account.is_paper_trading or False,
            exchange=account.exchange,
            api_key_name=mask_api_key(account.api_key_name),
            chain_id=account.chain_id,
            wallet_address=account.wallet_address,
            rpc_url=account.rpc_url,
            wallet_type=account.wallet_type,
            perps_portfolio_uuid=account.perps_portfolio_uuid,
            default_leverage=account.default_leverage or 1,
            margin_type=account.margin_type or "CROSS",
            prop_firm=account.prop_firm,
            prop_daily_drawdown_pct=account.prop_daily_drawdown_pct,
            prop_total_drawdown_pct=account.prop_total_drawdown_pct,
            prop_initial_deposit=account.prop_initial_deposit,
            created_at=account.created_at,
            updated_at=account.updated_at,
            last_used_at=account.last_used_at,
            display_name=account.get_display_name(),
            short_address=account.get_short_address() if account.type == "dex" else None,
            bot_count=0
        )

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error creating account: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.put("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    account_data: AccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE))
):
    """Update an existing account."""
    try:
        # Get the account
        query = select(Account).where(Account.id == account_id, Account.user_id == current_user.id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        # Update fields that are provided
        update_data = account_data.model_dump(exclude_unset=True)

        # Validate prop firm fields if being updated
        if 'prop_firm' in update_data and update_data['prop_firm']:
            if update_data['prop_firm'] not in VALID_PROP_FIRMS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported prop firm '{update_data['prop_firm']}'. "
                           f"Valid: {', '.join(sorted(VALID_PROP_FIRMS))}",
                )
        if 'prop_firm_config' in update_data and update_data['prop_firm_config']:
            validate_prop_firm_config(
                update_data['prop_firm_config'],
                update_data.get('exchange') or account.exchange or "",
            )

        # Encrypt sensitive fields before storing
        sensitive_fields = {'api_private_key', 'wallet_private_key'}
        # Fields that affect exchange client construction — invalidate cache on change
        exchange_config_fields = {
            'api_key_name', 'exchange',
            'prop_firm', 'prop_firm_config',
            'prop_daily_drawdown_pct', 'prop_total_drawdown_pct', 'prop_initial_deposit',
        }
        credentials_changed = False
        for field, value in update_data.items():
            if value is not None:
                if field in sensitive_fields:
                    credentials_changed = True
                    value = encrypt_value(value)
                if field == 'api_key_name':
                    credentials_changed = True
                    value = encrypt_value(value)
                if field in exchange_config_fields:
                    credentials_changed = True
                setattr(account, field, value)

        # Clear cached exchange client if credentials changed
        if credentials_changed:
            clear_exchange_client_cache(account_id)

        account.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(account)

        # Get bot count with aggregate query
        bot_count_result = await db.execute(
            select(func.count(Bot.id)).where(Bot.account_id == account.id)
        )
        bot_count = bot_count_result.scalar() or 0

        logger.info(f"Updated account: {account.name} (id={account.id})")

        return AccountResponse(
            id=account.id,
            name=account.name,
            type=account.type,
            is_default=account.is_default,
            is_active=account.is_active,
            is_paper_trading=account.is_paper_trading or False,
            exchange=account.exchange,
            api_key_name=mask_api_key(account.api_key_name),
            chain_id=account.chain_id,
            wallet_address=account.wallet_address,
            rpc_url=account.rpc_url,
            wallet_type=account.wallet_type,
            perps_portfolio_uuid=account.perps_portfolio_uuid,
            default_leverage=account.default_leverage or 1,
            margin_type=account.margin_type or "CROSS",
            prop_firm=account.prop_firm,
            prop_daily_drawdown_pct=account.prop_daily_drawdown_pct,
            prop_total_drawdown_pct=account.prop_total_drawdown_pct,
            prop_initial_deposit=account.prop_initial_deposit,
            created_at=account.created_at,
            updated_at=account.updated_at,
            last_used_at=account.last_used_at,
            display_name=account.get_display_name(),
            short_address=account.get_short_address() if account.type == "dex" else None,
            bot_count=bot_count
        )

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error updating account {account_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE))
):
    """
    Delete an account.

    This will fail if there are bots linked to this account.
    Unlink or delete bots first.
    """
    try:
        # Get the account (filtered by user)
        query = select(Account).where(Account.id == account_id, Account.user_id == current_user.id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail="Not found")

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

        # Clear cached exchange client before deleting account
        clear_exchange_client_cache(account_id)

        # Delete the account
        await db.delete(account)
        await db.commit()

        logger.info(f"Deleted account: {account.name} (id={account_id})")

        return {"message": f"Account '{account.name}' deleted successfully"}

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error deleting account {account_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.post("/{account_id}/set-default")
async def set_default_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE))
):
    """Set an account as the default."""
    try:
        # Get the account (filtered by user)
        query = select(Account).where(Account.id == account_id, Account.user_id == current_user.id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail="Not found")

        # Unset all other defaults for this user
        await db.execute(
            update(Account).where(Account.is_default, Account.user_id == current_user.id).values(is_default=False)
        )

        # Set this one as default
        account.is_default = True
        account.updated_at = datetime.utcnow()

        await db.commit()

        logger.info(f"Set default account: {account.name} (id={account_id})")

        return {"message": f"Account '{account.name}' is now the default"}

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error setting default account {account_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/{account_id}/bots")
async def get_account_bots(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all bots linked to an account."""
    try:
        # Verify account exists and belongs to user
        account_query = select(Account).where(Account.id == account_id, Account.user_id == current_user.id)
        account_result = await db.execute(account_query)
        account = account_result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail="Not found")

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

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error getting bots for account {account_id}: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/default", response_model=AccountResponse)
async def get_default_account(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get the default account."""
    try:
        query = select(Account).where(Account.is_default, Account.user_id == current_user.id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            # If no default, return the first active account
            query = (
                select(Account)
                .where(Account.is_active, Account.user_id == current_user.id)
                .order_by(Account.created_at.asc())
                .limit(1)
            )
            result = await db.execute(query)
            account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail="No accounts configured")

        # Get bot count with aggregate query
        bot_count_result = await db.execute(
            select(func.count(Bot.id)).where(Bot.account_id == account.id)
        )
        bot_count = bot_count_result.scalar() or 0

        return AccountResponse(
            id=account.id,
            name=account.name,
            type=account.type,
            is_default=account.is_default,
            is_active=account.is_active,
            is_paper_trading=account.is_paper_trading or False,
            exchange=account.exchange,
            api_key_name=mask_api_key(account.api_key_name),
            chain_id=account.chain_id,
            wallet_address=account.wallet_address,
            rpc_url=account.rpc_url,
            wallet_type=account.wallet_type,
            perps_portfolio_uuid=account.perps_portfolio_uuid,
            default_leverage=account.default_leverage or 1,
            margin_type=account.margin_type or "CROSS",
            created_at=account.created_at,
            updated_at=account.updated_at,
            last_used_at=account.last_used_at,
            display_name=account.get_display_name(),
            short_address=account.get_short_address() if account.type == "dex" else None,
            bot_count=bot_count
        )

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error getting default account: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/{account_id}/portfolio")
async def get_account_portfolio(
    account_id: int,
    force_fresh: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get portfolio for a specific account.

    For CEX accounts: Fetches from Coinbase API
    For DEX accounts: Fetches from blockchain via RPC
    For Paper Trading accounts: Returns virtual balances
    """
    try:
        return await get_portfolio_for_account(db, current_user, account_id, force_fresh)
    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error getting portfolio for account {account_id}: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


# =============================================================================
# Auto-Buy BTC Settings Endpoints
# =============================================================================

@router.get("/{account_id}/auto-buy-settings", response_model=AutoBuySettings)
async def get_auto_buy_settings(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get auto-buy BTC settings for an account"""
    query = select(Account).where(Account.id == account_id)

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
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE))
):
    """Update auto-buy BTC settings for an account"""
    query = select(Account).where(Account.id == account_id)

    query = query.where(Account.user_id == current_user.id)

    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    # Mutual exclusivity: enabling auto-buy disables portfolio rebalancing
    if settings.enabled and account.rebalance_enabled:
        account.rebalance_enabled = False

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


# =============================================================================
# Perpetual Futures Portfolio Linking
# =============================================================================


@router.post("/{account_id}/link-perps-portfolio")
async def link_perps_portfolio(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE)),
):
    """
    Discover and link the INTX perpetuals portfolio for a CEX account.

    Queries Coinbase for the user's perpetuals portfolio UUID and saves it
    to the account record.
    """
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if account.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if account.type != "cex":
        raise HTTPException(status_code=400, detail="Perps portfolio only available for CEX accounts")

    # Get exchange client
    coinbase_client = await get_coinbase_for_account(account)

    try:
        # Try to get portfolios and find the INTX perpetuals portfolio
        portfolios = await coinbase_client.get_portfolios()

        perps_uuid = None
        for portfolio in portfolios:
            ptype = portfolio.get("type", "")
            if ptype in ("PERPETUALS", "INTX", "DEFAULT"):
                # Try to query perps positions to confirm it's a perps portfolio
                uuid = portfolio.get("uuid", "")
                if uuid:
                    try:
                        await coinbase_client.get_perps_portfolio_summary(uuid)
                        perps_uuid = uuid
                        break
                    except Exception:
                        continue

        if not perps_uuid:
            raise HTTPException(
                status_code=404,
                detail="No INTX perpetuals portfolio found. Please enable perpetual futures on Coinbase first."
            )

        # Save to account
        account.perps_portfolio_uuid = perps_uuid
        await db.commit()

        return {
            "success": True,
            "portfolio_uuid": perps_uuid,
            "message": "Perpetuals portfolio linked successfully",
        }

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Failed to discover perps portfolio: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/{account_id}/perps-portfolio")
async def get_perps_portfolio_status(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the perps portfolio linking status for an account"""
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if account.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    return {
        "account_id": account_id,
        "perps_portfolio_uuid": account.perps_portfolio_uuid,
        "default_leverage": account.default_leverage,
        "margin_type": account.margin_type,
        "linked": account.perps_portfolio_uuid is not None,
    }


# =============================================================================
# Portfolio Rebalancing Endpoints
# =============================================================================


@router.get("/{account_id}/rebalance-settings", response_model=RebalanceSettingsResponse)
async def get_rebalance_settings(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get portfolio rebalance settings for an account."""
    query = select(Account).where(
        Account.id == account_id, Account.user_id == current_user.id
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    return _build_rebalance_response(account)


def _build_rebalance_response(account) -> RebalanceSettingsResponse:
    """Build RebalanceSettingsResponse from an Account model instance."""
    return RebalanceSettingsResponse(
        enabled=account.rebalance_enabled or False,
        target_usd_pct=account.rebalance_target_usd_pct if account.rebalance_target_usd_pct is not None else 34.0,
        target_btc_pct=account.rebalance_target_btc_pct if account.rebalance_target_btc_pct is not None else 33.0,
        target_eth_pct=account.rebalance_target_eth_pct if account.rebalance_target_eth_pct is not None else 33.0,
        target_usdc_pct=account.rebalance_target_usdc_pct if account.rebalance_target_usdc_pct is not None else 0.0,
        drift_threshold_pct=account.rebalance_drift_threshold_pct or 5.0,
        check_interval_minutes=account.rebalance_check_interval_minutes or 60,
        min_trade_pct=account.rebalance_min_trade_pct if account.rebalance_min_trade_pct is not None else 5.0,
        min_balance_usd=account.min_balance_usd or 0.0,
        min_balance_btc=account.min_balance_btc or 0.0,
        min_balance_eth=account.min_balance_eth or 0.0,
        min_balance_usdc=account.min_balance_usdc or 0.0,
    )


@router.put("/{account_id}/rebalance-settings", response_model=RebalanceSettingsResponse)
async def update_rebalance_settings(
    account_id: int,
    settings: RebalanceSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE)),
):
    """Update portfolio rebalance settings for an account."""
    query = select(Account).where(
        Account.id == account_id, Account.user_id == current_user.id
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    # If percentages are being updated, validate they sum to 100
    usd = settings.target_usd_pct if settings.target_usd_pct is not None else account.rebalance_target_usd_pct or 34.0
    btc = settings.target_btc_pct if settings.target_btc_pct is not None else account.rebalance_target_btc_pct or 33.0
    eth = settings.target_eth_pct if settings.target_eth_pct is not None else account.rebalance_target_eth_pct or 33.0
    usdc = (settings.target_usdc_pct if settings.target_usdc_pct is not None
            else account.rebalance_target_usdc_pct or 0.0)

    pct_total = usd + btc + eth + usdc
    if abs(pct_total - 100.0) > 0.1:
        raise HTTPException(
            status_code=400,
            detail=f"Target percentages must sum to 100% (got {pct_total:.1f}%)"
        )

    # Mutual exclusivity: enabling rebalancing disables auto-buy
    if settings.enabled and account.auto_buy_enabled:
        account.auto_buy_enabled = False

    # Update fields
    if settings.enabled is not None:
        account.rebalance_enabled = settings.enabled
    if settings.target_usd_pct is not None:
        account.rebalance_target_usd_pct = settings.target_usd_pct
    if settings.target_btc_pct is not None:
        account.rebalance_target_btc_pct = settings.target_btc_pct
    if settings.target_eth_pct is not None:
        account.rebalance_target_eth_pct = settings.target_eth_pct
    if settings.target_usdc_pct is not None:
        account.rebalance_target_usdc_pct = settings.target_usdc_pct
    if settings.drift_threshold_pct is not None:
        account.rebalance_drift_threshold_pct = settings.drift_threshold_pct
    if settings.check_interval_minutes is not None:
        account.rebalance_check_interval_minutes = settings.check_interval_minutes
    if settings.min_trade_pct is not None:
        account.rebalance_min_trade_pct = settings.min_trade_pct
    if settings.min_balance_usd is not None:
        account.min_balance_usd = settings.min_balance_usd
    if settings.min_balance_btc is not None:
        account.min_balance_btc = settings.min_balance_btc
    if settings.min_balance_eth is not None:
        account.min_balance_eth = settings.min_balance_eth
    if settings.min_balance_usdc is not None:
        account.min_balance_usdc = settings.min_balance_usdc

    await db.commit()
    await db.refresh(account)

    return _build_rebalance_response(account)


async def get_public_prices() -> dict:
    """Fetch current prices from public Coinbase API (no auth needed)."""
    from app.coinbase_api import public_market_data
    prices = {}
    for product_id in ("BTC-USD", "ETH-USD", "USDC-USD"):
        try:
            prices[product_id] = float(await public_market_data.get_current_price(product_id))
        except Exception:
            prices[product_id] = 1.0 if product_id == "USDC-USD" else 0.0
    return prices


def _compute_allocation(balances: dict, prices: dict) -> dict:
    """Compute USD-denominated allocation percentages from balances and prices."""
    usd_value = balances.get("USD", 0.0)
    btc_value = balances.get("BTC", 0.0) * prices.get("BTC-USD", 0.0)
    eth_value = balances.get("ETH", 0.0) * prices.get("ETH-USD", 0.0)
    usdc_value = balances.get("USDC", 0.0) * prices.get("USDC-USD", 1.0)
    total = usd_value + btc_value + eth_value + usdc_value

    if total > 0:
        usd_pct = round(usd_value / total * 100, 2)
        btc_pct = round(btc_value / total * 100, 2)
        eth_pct = round(eth_value / total * 100, 2)
        usdc_pct = round(usdc_value / total * 100, 2)
    else:
        usd_pct = btc_pct = eth_pct = usdc_pct = 0.0

    return {
        "current_usd_pct": usd_pct,
        "current_btc_pct": btc_pct,
        "current_eth_pct": eth_pct,
        "current_usdc_pct": usdc_pct,
        "total_value_usd": round(total, 2),
    }


@router.get("/{account_id}/rebalance-status")
async def get_rebalance_status(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current portfolio allocation vs targets for an account."""
    query = select(Account).where(
        Account.id == account_id, Account.user_id == current_user.id
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    if account.type != "cex":
        raise HTTPException(status_code=400, detail="Rebalancing only available for CEX accounts")

    try:
        if account.is_paper_trading:
            # Paper trading: read balances from JSON, use public prices
            balances = json.loads(account.paper_balances) if account.paper_balances else {}
            prices = await get_public_prices()
            alloc = _compute_allocation(balances, prices)
        else:
            # Live account: use Coinbase client with aggregate values
            coinbase = await get_coinbase_for_account(account)

            aggregate_values = {}
            for currency in ("USD", "BTC", "ETH", "USDC"):
                try:
                    aggregate_values[currency] = float(
                        await coinbase.calculate_aggregate_quote_value(currency)
                    )
                except Exception:
                    aggregate_values[currency] = 0.0

            prices = {}
            for product_id in ("BTC-USD", "ETH-USD", "USDC-USD"):
                try:
                    prices[product_id] = float(await coinbase.get_current_price(product_id))
                except Exception:
                    prices[product_id] = 1.0 if product_id == "USDC-USD" else 0.0

            alloc = _compute_allocation(aggregate_values, prices)

        t_usd = account.rebalance_target_usd_pct
        t_btc = account.rebalance_target_btc_pct
        t_eth = account.rebalance_target_eth_pct
        t_usdc = account.rebalance_target_usdc_pct
        return {
            "account_id": account_id,
            **alloc,
            "target_usd_pct": t_usd if t_usd is not None else 34.0,
            "target_btc_pct": t_btc if t_btc is not None else 33.0,
            "target_eth_pct": t_eth if t_eth is not None else 33.0,
            "target_usdc_pct": t_usdc if t_usdc is not None else 0.0,
            "rebalance_enabled": bool(account.rebalance_enabled),
            "min_balance_usd": account.min_balance_usd or 0.0,
            "min_balance_btc": account.min_balance_btc or 0.0,
            "min_balance_eth": account.min_balance_eth or 0.0,
            "min_balance_usdc": account.min_balance_usdc or 0.0,
        }

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error getting rebalance status for account {account_id}: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


# =============================================================================
# Dust Sweep Endpoints
# =============================================================================


class DustSweepSettingsUpdate(BaseModel):
    """Update model for dust sweep settings."""
    enabled: Optional[bool] = None
    threshold_usd: Optional[float] = Field(None, ge=1.0, le=1000.0)


TARGET_CURRENCIES = {"USD", "BTC", "ETH", "USDC"}


@router.get("/{account_id}/dust-sweep-settings")
async def get_dust_sweep_settings(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get dust sweep settings and current dust positions for an account."""
    query = select(Account).where(
        Account.id == account_id, Account.user_id == current_user.id
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    # Build dust positions list
    dust_positions = []
    try:
        if account.is_paper_trading:
            balances = json.loads(account.paper_balances) if account.paper_balances else {}
        else:
            # Live account: get all balances via exchange client
            try:
                coinbase = await get_coinbase_for_account(account)
                accounts_data = await coinbase.get_accounts()
                balances = {}
                for acct in accounts_data:
                    currency = acct.get("currency", "")
                    available = float(
                        acct.get("available_balance", {}).get("value", 0)
                    )
                    if available > 0:
                        balances[currency] = available
            except Exception:
                balances = {}

        # Subtract amounts locked in open positions
        from app.services.rebalance_monitor import (
            get_position_locked_amounts, subtract_locked_amounts,
        )
        locked = await get_position_locked_amounts(db, account.id)
        balances = subtract_locked_amounts(balances, locked)

        prices = await get_public_prices()
        threshold = account.dust_sweep_threshold_usd or 5.0

        for coin, amount in balances.items():
            if coin in TARGET_CURRENCIES or amount <= 0:
                continue
            usd_price = prices.get(f"{coin}-USD", 0.0)
            if usd_price <= 0:
                # Try fetching price for this coin
                try:
                    from app.coinbase_api import public_market_data
                    usd_price = float(
                        await public_market_data.get_current_price(f"{coin}-USD")
                    )
                except Exception:
                    continue
            usd_value = amount * usd_price
            if usd_value >= threshold:
                dust_positions.append({
                    "coin": coin,
                    "amount": round(amount, 8),
                    "usd_value": round(usd_value, 2),
                })

        dust_positions.sort(key=lambda d: d["usd_value"], reverse=True)
    except Exception as e:
        logger.warning(f"Error building dust positions for account {account_id}: {e}")

    return {
        "enabled": account.dust_sweep_enabled or False,
        "threshold_usd": account.dust_sweep_threshold_usd or 5.0,
        "last_sweep_at": (
            account.dust_last_sweep_at.isoformat()
            if account.dust_last_sweep_at else None
        ),
        "dust_positions": dust_positions,
    }


@router.put("/{account_id}/dust-sweep-settings")
async def update_dust_sweep_settings(
    account_id: int,
    settings: DustSweepSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE)),
):
    """Update dust sweep settings for an account."""
    query = select(Account).where(
        Account.id == account_id, Account.user_id == current_user.id
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    if settings.enabled is not None:
        account.dust_sweep_enabled = settings.enabled
    if settings.threshold_usd is not None:
        account.dust_sweep_threshold_usd = settings.threshold_usd

    await db.commit()
    await db.refresh(account)

    return {
        "enabled": account.dust_sweep_enabled or False,
        "threshold_usd": account.dust_sweep_threshold_usd or 5.0,
        "last_sweep_at": (
            account.dust_last_sweep_at.isoformat()
            if account.dust_last_sweep_at else None
        ),
    }


@router.post("/{account_id}/dust-sweep")
async def sweep_dust(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ACCOUNTS_WRITE)),
):
    """Execute an on-demand dust sweep for an account."""
    query = select(Account).where(
        Account.id == account_id, Account.user_id == current_user.id
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    if account.type != "cex":
        raise HTTPException(status_code=400, detail="Dust sweep only available for CEX accounts")

    try:
        if account.is_paper_trading:
            client = await get_coinbase_for_account(account)
        else:
            client = await get_coinbase_for_account(account)

        from app.services.rebalance_monitor import execute_dust_sweep
        results = await execute_dust_sweep(account, client, db)

        successes = [r for r in results if r.get("status") == "success"]
        failures = [r for r in results if r.get("status") == "failed"]

        return {
            "swept": len(successes),
            "failed": len(failures),
            "details": [
                {
                    "coin": r["coin"],
                    "amount": r["amount"],
                    "usd_value": r["usd_value"],
                    "target_currency": r["target_currency"],
                    "order_id": r.get("order_id", ""),
                }
                for r in successes
            ],
            "errors": [
                {
                    "coin": r["coin"],
                    "amount": r["amount"],
                    "usd_value": r["usd_value"],
                    "error": r.get("error", "Unknown error"),
                }
                for r in failures
            ],
        }

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error executing dust sweep for account {account_id}: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")
