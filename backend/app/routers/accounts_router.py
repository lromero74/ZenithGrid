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

from app.exceptions import AppError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.encryption import encrypt_value, decrypt_value, is_encrypted
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


def _mask_key_name(val: Optional[str]) -> Optional[str]:
    """Mask an encrypted or plaintext API key name for safe API responses."""
    if not val:
        return None
    # Decrypt to get real value for masking
    plain = decrypt_value(val) if is_encrypted(val) else val
    if len(plain) <= 8:
        return "****"
    return plain[:4] + "****" + plain[-4:]


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
                api_key_name=_mask_key_name(account.api_key_name),
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
            api_key_name=_mask_key_name(account.api_key_name),
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
            api_key_name=_mask_key_name(account.api_key_name),
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
            api_key_name=_mask_key_name(account.api_key_name),
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
            api_key_name=_mask_key_name(account.api_key_name),
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
