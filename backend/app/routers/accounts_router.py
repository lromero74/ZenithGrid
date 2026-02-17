"""
Accounts management API routes

Handles CRUD operations for trading accounts:
- CEX accounts (Coinbase) with API credentials
- DEX wallets (MetaMask, WalletConnect) with wallet addresses

This enables multi-account trading where each bot is linked to a specific account,
and the UI can filter by selected account.
"""

import logging
import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.encryption import encrypt_value, decrypt_value, is_encrypted
from app.models import Account, Bot, User
from app.routers.auth_dependencies import get_current_user
from app.exchange_clients.factory import create_exchange_client
from app.coinbase_unified_client import CoinbaseClient
from app.routers.accounts import get_cex_portfolio, get_dex_portfolio
from app.services.exchange_service import (
    clear_exchange_client_cache,
    get_exchange_client_for_account,
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

    # Decrypt credentials if encrypted
    key_name = account.api_key_name
    if is_encrypted(key_name):
        key_name = decrypt_value(key_name)
    private_key = account.api_private_key
    if is_encrypted(private_key):
        private_key = decrypt_value(private_key)

    client = create_exchange_client(
        exchange_type="cex",
        coinbase_key_name=key_name,
        coinbase_private_key=private_key,
    )

    if not client:
        raise HTTPException(
            status_code=503,
            detail="Failed to create Coinbase client. Please check your API credentials."
        )

    return client

VALID_EXCHANGES = {"coinbase", "bybit", "mt5_bridge"}
VALID_PROP_FIRMS = {"hyrotrader", "ftmo"}


def _validate_prop_firm_config(config: dict, exchange: str) -> None:
    """Validate prop_firm_config schema and prevent SSRF via bridge_url."""
    if not isinstance(config, dict):
        raise HTTPException(status_code=400, detail="prop_firm_config must be a JSON object")

    # MT5 bridge requires a bridge_url
    if exchange == "mt5_bridge":
        bridge_url = config.get("bridge_url", "")
        if bridge_url:
            parsed = urlparse(bridge_url)
            # Only allow http/https schemes
            if parsed.scheme not in ("http", "https"):
                raise HTTPException(
                    status_code=400,
                    detail="bridge_url must use http:// or https:// scheme",
                )
            # Block obvious internal/private IPs
            host = parsed.hostname or ""
            if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or \
               host.startswith("10.") or host.startswith("192.168.") or \
               re.match(r"^172\.(1[6-9]|2\d|3[01])\.", host):
                raise HTTPException(
                    status_code=400,
                    detail="bridge_url must not point to a private/internal address",
                )

    # Validate testnet flag if present
    if "testnet" in config and not isinstance(config["testnet"], bool):
        raise HTTPException(
            status_code=400,
            detail="prop_firm_config.testnet must be a boolean",
        )

    # Only allow known keys to prevent arbitrary data injection
    allowed_keys = {"bridge_url", "testnet", "api_key", "api_secret", "broker", "server"}
    unknown = set(config.keys()) - allowed_keys
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown keys in prop_firm_config: {', '.join(sorted(unknown))}",
        )


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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting account {account_id}: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.post("", response_model=AccountResponse)
async def create_account(
    account_data: AccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
            if account_data.exchange not in VALID_EXCHANGES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported exchange '{account_data.exchange}'. "
                           f"Valid: {', '.join(sorted(VALID_EXCHANGES))}",
                )
        else:  # dex
            if not account_data.chain_id:
                raise HTTPException(status_code=400, detail="DEX accounts require 'chain_id' field")
            if not account_data.wallet_address:
                raise HTTPException(status_code=400, detail="DEX accounts require 'wallet_address' field")

        # Validate prop firm fields
        if account_data.prop_firm:
            if account_data.prop_firm not in VALID_PROP_FIRMS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported prop firm '{account_data.prop_firm}'. "
                           f"Valid: {', '.join(sorted(VALID_PROP_FIRMS))}",
                )
        if account_data.prop_firm_config:
            _validate_prop_firm_config(
                account_data.prop_firm_config,
                account_data.exchange or "",
            )

        # If this is set as default, unset other defaults for this user
        if account_data.is_default:
            default_filter = Account.is_default & (Account.user_id == current_user.id)
            await db.execute(
                update(Account).where(default_filter).values(is_default=False)
            )

        # Create the account
        account = Account(
            name=account_data.name,
            type=account_data.type,
            is_default=account_data.is_default,
            user_id=current_user.id,
            is_active=True,
            exchange=account_data.exchange,
            api_key_name=(
                encrypt_value(account_data.api_key_name)
                if account_data.api_key_name
                else None
            ),
            api_private_key=encrypt_value(account_data.api_private_key) if account_data.api_private_key else None,
            chain_id=account_data.chain_id,
            wallet_address=account_data.wallet_address,
            wallet_private_key=(
                encrypt_value(account_data.wallet_private_key)
                if account_data.wallet_private_key else None
            ),
            rpc_url=account_data.rpc_url,
            wallet_type=account_data.wallet_type,
            # Prop firm fields
            prop_firm=account_data.prop_firm,
            prop_firm_config=account_data.prop_firm_config,
            prop_daily_drawdown_pct=account_data.prop_daily_drawdown_pct,
            prop_total_drawdown_pct=account_data.prop_total_drawdown_pct,
            prop_initial_deposit=account_data.prop_initial_deposit,
        )

        db.add(account)
        await db.commit()
        await db.refresh(account)

        # Verify credentials by testing connection
        # Include prop_firm_config for MT5 accounts (use bridge_url instead of API keys)
        if account.api_key_name or account.wallet_private_key or account.prop_firm_config:
            try:
                client = await get_exchange_client_for_account(db, account.id, use_cache=False)
                if client:
                    connected = await client.test_connection()
                    if not connected:
                        # Credentials don't work — delete the account
                        await db.delete(account)
                        await db.commit()
                        raise HTTPException(
                            status_code=400,
                            detail="Connection test failed. Please verify your API credentials.",
                        )
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"Connection test error for account {account.id}: {e}")
                await db.delete(account)
                await db.commit()
                raise HTTPException(
                    status_code=400,
                    detail=f"Connection test failed: {str(e)}",
                )

        logger.info(f"Created account: {account.name} (type={account.type}, id={account.id})")

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

    except HTTPException:
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
    current_user: User = Depends(get_current_user)
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
            _validate_prop_firm_config(
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating account {account_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting account {account_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.post("/{account_id}/set-default")
async def set_default_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
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

    except HTTPException:
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

    except HTTPException:
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting default account: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


async def _get_generic_cex_portfolio(
    account: Account,
    db: AsyncSession,
) -> dict:
    """
    Build a portfolio view for non-Coinbase CEX accounts (ByBit, MT5).

    Uses the exchange adapter's get_accounts() for balances and
    the database for position-level P&L.
    """
    from app.models import Position, Bot

    exchange = await get_exchange_client_for_account(db, account.id)
    if not exchange:
        raise HTTPException(
            status_code=503,
            detail="Could not connect to exchange. Check API credentials.",
        )

    # Get balances from the exchange
    try:
        coin_accounts = await exchange.get_accounts()
    except Exception as e:
        logger.error(f"Failed to fetch balances for account {account.id}: {e}")
        raise HTTPException(
            status_code=503,
            detail="Failed to fetch balances from exchange.",
        )

    # Get BTC/USD price for valuations
    try:
        btc_usd_price = await exchange.get_btc_usd_price()
    except Exception:
        btc_usd_price = 95000.0  # fallback

    # Build holdings from coin balances
    portfolio_holdings = []
    total_usd_value = 0.0
    total_btc_value = 0.0

    for coin_acct in coin_accounts:
        currency = coin_acct.get("currency", "")
        avail_val = coin_acct.get("available_balance", {}).get("value", "0")
        hold_val = coin_acct.get("hold", {}).get("value", "0")
        available = float(avail_val)
        hold = float(hold_val)
        total_balance = available + hold

        if total_balance < 0.000001:
            continue

        # Calculate USD value
        usd_value = 0.0
        btc_value = 0.0
        current_price_usd = 0.0

        if currency in ("USD", "USDC", "USDT"):
            usd_value = total_balance
            btc_value = total_balance / btc_usd_price if btc_usd_price > 0 else 0
            current_price_usd = 1.0
        elif currency == "BTC":
            usd_value = total_balance * btc_usd_price
            btc_value = total_balance
            current_price_usd = btc_usd_price
        else:
            # Try to get price for other coins
            try:
                price = await exchange.get_current_price(f"{currency}-USD")
                if price > 0:
                    current_price_usd = price
                    usd_value = total_balance * price
                    btc_value = usd_value / btc_usd_price if btc_usd_price > 0 else 0
            except Exception:
                continue  # skip coins we can't price

        if usd_value < 0.01:
            continue

        total_usd_value += usd_value
        total_btc_value += btc_value

        portfolio_holdings.append({
            "asset": currency,
            "total_balance": total_balance,
            "available": available,
            "hold": hold,
            "current_price_usd": current_price_usd,
            "usd_value": usd_value,
            "btc_value": btc_value,
            "percentage": 0.0,
            "unrealized_pnl_usd": 0.0,
            "unrealized_pnl_percentage": 0.0,
        })

    # Also include equity from exchange if available (unrealized PnL)
    try:
        equity = await exchange.get_equity()
        if equity > total_usd_value:
            # Equity includes unrealized PnL — show the difference
            unrealized = equity - total_usd_value
            total_usd_value = equity
            total_btc_value = equity / btc_usd_price if btc_usd_price > 0 else 0
            # Attribute unrealized to positions bucket
            if portfolio_holdings:
                portfolio_holdings[0]["unrealized_pnl_usd"] = unrealized
    except Exception:
        pass  # not all adapters have get_equity

    # Calculate percentages
    for holding in portfolio_holdings:
        if total_usd_value > 0:
            holding["percentage"] = (holding["usd_value"] / total_usd_value) * 100

    portfolio_holdings.sort(key=lambda x: x["usd_value"], reverse=True)

    # Get position P&L from database (strictly scoped to this account)
    positions_q = select(Position).where(
        Position.status == "open",
        Position.account_id == account.id,
    )
    closed_q = select(Position).where(
        Position.status == "closed",
        Position.account_id == account.id,
    )

    open_result = await db.execute(positions_q)
    open_positions = open_result.scalars().all()
    closed_result = await db.execute(closed_q)
    closed_positions = closed_result.scalars().all()

    # Tally in-positions value
    total_in_positions_usd = 0.0
    total_in_positions_btc = 0.0
    for pos in open_positions:
        quote = pos.get_quote_currency()
        if quote in ("USD", "USDC", "USDT"):
            total_in_positions_usd += pos.total_quote_spent
        else:
            total_in_positions_btc += pos.total_quote_spent

    # Calculate realized P&L
    now = datetime.utcnow()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    pnl_all_time = {"usd": 0.0, "btc": 0.0, "usdc": 0.0}
    pnl_today = {"usd": 0.0, "btc": 0.0, "usdc": 0.0}

    for pos in closed_positions:
        if pos.profit_quote is not None:
            quote = pos.get_quote_currency()
            key = quote.lower() if quote in ("USD", "BTC", "USDC") else "usd"
            pnl_all_time[key] += pos.profit_quote
            if pos.closed_at and pos.closed_at >= start_of_today:
                pnl_today[key] += pos.profit_quote

    # Bot reservations
    bots_q = select(Bot).where(Bot.account_id == account.id)
    bots_result = await db.execute(bots_q)
    account_bots = bots_result.scalars().all()
    total_reserved_btc = sum(b.reserved_btc_balance for b in account_bots)
    total_reserved_usd = sum(b.reserved_usd_balance for b in account_bots)

    return {
        "total_usd_value": total_usd_value,
        "total_btc_value": total_btc_value,
        "btc_usd_price": btc_usd_price,
        "holdings": portfolio_holdings,
        "holdings_count": len(portfolio_holdings),
        "balance_breakdown": {
            "btc": {
                "total": total_btc_value,
                "reserved_by_bots": total_reserved_btc,
                "in_open_positions": total_in_positions_btc,
                "free": max(0.0, total_btc_value - total_reserved_btc - total_in_positions_btc),
            },
            "usd": {
                "total": total_usd_value,
                "reserved_by_bots": total_reserved_usd,
                "in_open_positions": total_in_positions_usd,
                "free": max(0.0, total_usd_value - total_reserved_usd - total_in_positions_usd),
            },
            "usdc": {
                "total": 0.0,
                "reserved_by_bots": 0.0,
                "in_open_positions": 0.0,
                "free": 0.0,
            },
        },
        "pnl": {
            "today": pnl_today,
            "all_time": pnl_all_time,
        },
        "account_id": account.id,
        "account_name": account.name,
        "account_type": "cex",
        "is_dex": False,
    }


@router.get("/{account_id}/portfolio")
async def get_account_portfolio(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get portfolio for a specific account.

    For CEX accounts: Fetches from Coinbase API
    For DEX accounts: Fetches from blockchain via RPC
    For Paper Trading accounts: Returns virtual balances
    """
    try:
        import json

        # Get the account (filtered by user)
        query = select(Account).where(Account.id == account_id, Account.user_id == current_user.id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail="Not found")

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
            exchange_name = account.exchange or "coinbase"
            if exchange_name in ("bybit", "mt5_bridge"):
                # Non-Coinbase exchange: use generic portfolio builder
                return await _get_generic_cex_portfolio(account, db)
            else:
                # Coinbase: use existing rich portfolio logic
                return await get_cex_portfolio(account, db, get_coinbase_for_account)
        else:
            # Use DEX wallet service for blockchain balances
            return await get_dex_portfolio(account, db, get_coinbase_for_account)

    except HTTPException:
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
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user),
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

    except HTTPException:
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
