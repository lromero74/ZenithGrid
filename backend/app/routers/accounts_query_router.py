"""
Accounts query API routes (GET endpoints)

Read-only operations for trading accounts:
- Account listings, individual account retrieval
- Portfolio, balance, and bot queries
- Settings reads (auto-buy, rebalance, dust sweep, perps)
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.exceptions import AppError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.encryption import mask_api_key
from app.models import Account, Bot, User
from app.models.sharing import AccountMembership
from app.auth.dependencies import get_current_user
from app.services.account_access import accessible_accounts_filter
from app.services.account_responses import RebalanceSettingsResponse, build_rebalance_response
from app.services.account_service import get_portfolio_for_account
from app.services.exchange_service import get_coinbase_for_account

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

# TTL caches for live-account endpoints that make Coinbase API calls.
# Shared across all callers (owner + members) — limits live API calls to once per TTL
# per account, preventing members from exhausting the account owner's API rate quota.
_TTL_REBALANCE_STATUS: Dict[int, Tuple[float, Any]] = {}
_TTL_DUST_SWEEP: Dict[int, Tuple[float, Any]] = {}
_TTL_REBALANCE_SECONDS = 30
_TTL_DUST_SWEEP_SECONDS = 60


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

    # Sharing fields — null/absent means the current user owns this account
    membership_role: Optional[str] = None   # 'manager' | 'shadow' | None (owner)
    shared_by: Optional[str] = None         # Display name of the account owner (non-owners only)
    member_count: int = 0                   # Number of active non-owner members

    model_config = ConfigDict(from_attributes=True)


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


class RebalanceSettingsUpdate(BaseModel):
    """Update model for rebalance settings (all fields optional)"""
    enabled: Optional[bool] = None
    target_usd_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    target_btc_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    target_eth_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    target_usdc_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    target_usdt_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    drift_threshold_pct: Optional[float] = Field(None, ge=1.0, le=10.0)
    check_interval_minutes: Optional[int] = Field(None, ge=15, le=1440)
    min_trade_pct: Optional[float] = Field(None, ge=1.0, le=25.0)
    min_balance_usd: Optional[float] = Field(None, ge=0.0)
    min_balance_btc: Optional[float] = Field(None, ge=0.0)
    min_balance_eth: Optional[float] = Field(None, ge=0.0)
    min_balance_usdc: Optional[float] = Field(None, ge=0.0)
    min_balance_usdt: Optional[float] = Field(None, ge=0.0)


class DustSweepSettingsUpdate(BaseModel):
    """Update model for dust sweep settings."""
    enabled: Optional[bool] = None
    threshold_usd: Optional[float] = Field(None, ge=1.0, le=1000.0)


# =============================================================================
# Helpers
# =============================================================================


async def get_public_prices() -> dict:
    """Fetch current prices from public Coinbase API (no auth needed).

    Delegates to rebalance_service.get_public_prices.
    """
    from app.services.rebalance_service import get_public_prices as _get_public_prices
    return await _get_public_prices()


def _compute_allocation(balances: dict, prices: dict, total_override: float | None = None) -> dict:
    """Compute USD-denominated allocation percentages from balances and prices.

    Delegates to rebalance_service.compute_allocation. Kept here as a thin
    wrapper so existing callers and tests continue to work unchanged.
    """
    from app.services.rebalance_service import compute_allocation
    return compute_allocation(balances, prices, total_override)


TARGET_CURRENCIES = {"USD", "BTC", "ETH", "USDC", "USDT"}


# =============================================================================
# GET Endpoints
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
        query = query.where(accessible_accounts_filter(current_user.id))
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

        # Get member counts for all accounts (non-owner members only)
        member_count_q = select(
            AccountMembership.account_id, func.count(AccountMembership.id).label("cnt")
        ).where(
            AccountMembership.account_id.in_(account_ids),
            or_(
                AccountMembership.expires_at.is_(None),
                AccountMembership.expires_at > datetime.utcnow(),
            ),
        ).group_by(AccountMembership.account_id)
        member_count_result = await db.execute(member_count_q)
        member_counts = {row.account_id: row.cnt for row in member_count_result}

        # Get membership role for accounts this user doesn't own
        owned_ids = {a.id for a in accounts if a.user_id == current_user.id}
        membership_q = select(AccountMembership).where(
            AccountMembership.account_id.in_(account_ids),
            AccountMembership.user_id == current_user.id,
        )
        membership_result = await db.execute(membership_q)
        memberships = {m.account_id: m for m in membership_result.scalars().all()}

        response = []
        for account in accounts:
            bot_count = bot_counts.get(account.id, 0)
            member_count = member_counts.get(account.id, 0)
            is_owner = account.id in owned_ids

            membership_role = None
            shared_by = None
            if not is_owner:
                m = memberships.get(account.id)
                membership_role = m.role if m and not m.is_expired else None
                owner_user = await db.get(User, account.user_id)
                if owner_user:
                    shared_by = owner_user.display_name or owner_user.email

            # Mask API key name for non-owners
            api_key_name = mask_api_key(account.api_key_name) if is_owner else None

            response.append(AccountResponse(
                id=account.id,
                name=account.name,
                type=account.type,
                is_default=account.is_default,
                is_active=account.is_active,
                is_paper_trading=account.is_paper_trading or False,
                exchange=account.exchange,
                api_key_name=api_key_name,
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
                bot_count=bot_count,
                membership_role=membership_role,
                shared_by=shared_by,
                member_count=member_count,
            ))

        return response

    except Exception as e:
        logger.error(f"Error listing accounts: {e}")
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


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific account by ID. Returns owned accounts and shared accounts."""
    try:
        query = select(Account).where(
            Account.id == account_id,
            accessible_accounts_filter(current_user.id),
        )
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        # Get bot count with aggregate query
        bot_count_result = await db.execute(
            select(func.count(Bot.id)).where(Bot.account_id == account.id)
        )
        bot_count = bot_count_result.scalar() or 0

        # Resolve membership role and owner info for shared accounts
        is_owner = account.user_id == current_user.id
        membership_role = None
        shared_by = None
        if not is_owner:
            m_result = await db.execute(
                select(AccountMembership).where(
                    AccountMembership.account_id == account.id,
                    AccountMembership.user_id == current_user.id,
                )
            )
            m = m_result.scalar_one_or_none()
            membership_role = m.role if m and not m.is_expired else None
            owner_user = await db.get(User, account.user_id)
            if owner_user:
                shared_by = owner_user.display_name or owner_user.email

        member_count_result = await db.execute(
            select(func.count(AccountMembership.id)).where(
                AccountMembership.account_id == account.id,
                or_(
                    AccountMembership.expires_at.is_(None),
                    AccountMembership.expires_at > datetime.utcnow(),
                ),
            )
        )
        member_count = member_count_result.scalar() or 0

        return AccountResponse(
            id=account.id,
            name=account.name,
            type=account.type,
            is_default=account.is_default,
            is_active=account.is_active,
            is_paper_trading=account.is_paper_trading or False,
            exchange=account.exchange,
            api_key_name=mask_api_key(account.api_key_name) if is_owner else None,
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
            bot_count=bot_count,
            membership_role=membership_role,
            shared_by=shared_by,
            member_count=member_count,
        )

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error getting account {account_id}: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/{account_id}/bots")
async def get_account_bots(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all bots linked to an account."""
    try:
        # Verify account exists and is accessible (owner or member)
        account_query = select(Account).where(
            Account.id == account_id,
            accessible_accounts_filter(current_user.id),
        )
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
# Auto-Buy BTC Settings (GET)
# =============================================================================


@router.get("/{account_id}/auto-buy-settings", response_model=AutoBuySettings)
async def get_auto_buy_settings(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get auto-buy BTC settings for an account"""
    query = select(Account).where(
        Account.id == account_id, accessible_accounts_filter(current_user.id)
    )
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


# =============================================================================
# Perpetual Futures Portfolio (GET)
# =============================================================================


@router.get("/{account_id}/perps-portfolio")
async def get_perps_portfolio_status(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the perps portfolio linking status for an account."""
    # Gate by accessible_accounts_filter so non-members see 404, not 403 —
    # prevents enumerating which account IDs exist.
    query = select(Account).where(
        Account.id == account_id, accessible_accounts_filter(current_user.id)
    )
    account = (await db.execute(query)).scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    return {
        "account_id": account_id,
        "perps_portfolio_uuid": account.perps_portfolio_uuid,
        "default_leverage": account.default_leverage,
        "margin_type": account.margin_type,
        "linked": account.perps_portfolio_uuid is not None,
    }


# =============================================================================
# Portfolio Rebalancing (GET)
# =============================================================================


@router.get("/{account_id}/rebalance-settings", response_model=RebalanceSettingsResponse)
async def get_rebalance_settings(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get portfolio rebalance settings for an account."""
    query = select(Account).where(
        Account.id == account_id, accessible_accounts_filter(current_user.id)
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    return build_rebalance_response(account)


@router.get("/{account_id}/rebalance-status")
async def get_rebalance_status(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current portfolio allocation vs targets for an account."""
    from app.services.rebalance_service import compute_rebalance_status

    query = select(Account).where(
        Account.id == account_id, accessible_accounts_filter(current_user.id)
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    if account.type != "cex":
        raise HTTPException(status_code=400, detail="Rebalancing only available for CEX accounts")

    # M2: Serve from TTL cache for live accounts — prevents member requests from
    # exhausting the account owner's Coinbase API rate quota.
    if not account.is_paper_trading:
        cached = _TTL_REBALANCE_STATUS.get(account_id)
        if cached:
            cached_at, cached_data = cached
            if time.monotonic() - cached_at < _TTL_REBALANCE_SECONDS:
                return cached_data

    try:
        response_data = await compute_rebalance_status(db, account)
        if not account.is_paper_trading:
            _TTL_REBALANCE_STATUS[account_id] = (time.monotonic(), response_data)
        return response_data

    except (HTTPException, AppError):
        raise
    except Exception as e:
        logger.error(f"Error getting rebalance status for account {account_id}: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


# =============================================================================
# Dust Sweep (GET)
# =============================================================================


@router.get("/{account_id}/dust-sweep-settings")
async def get_dust_sweep_settings(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get dust sweep settings and current dust positions for an account."""
    query = select(Account).where(
        Account.id == account_id, accessible_accounts_filter(current_user.id)
    )
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

    # M2: Serve from TTL cache for live accounts
    if not account.is_paper_trading:
        cached = _TTL_DUST_SWEEP.get(account_id)
        if cached:
            cached_at, cached_data = cached
            if time.monotonic() - cached_at < _TTL_DUST_SWEEP_SECONDS:
                return cached_data

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
                logger.warning(
                    "Failed to load Coinbase balances for dust sweep on account %s",
                    account_id, exc_info=True,
                )
                balances = {}

        # Subtract amounts locked in open positions
        from app.services.rebalance_monitor import (
            get_position_locked_amounts, subtract_locked_amounts,
        )
        locked = await get_position_locked_amounts(db, account.id)
        balances = subtract_locked_amounts(balances, locked)

        prices = await get_public_prices()
        threshold = account.dust_sweep_threshold_usd or 5.0
        from app.coinbase_api import public_market_data

        # Collect altcoins to price, sorted by balance descending so we price
        # the most likely candidates first.  Cap at 40 price lookups to avoid
        # sequential-API timeouts on accounts with many small balances.
        altcoins = sorted(
            [(coin, amt) for coin, amt in balances.items()
             if coin not in TARGET_CURRENCIES and amt > 0],
            key=lambda x: x[1],
            reverse=True,
        )[:40]

        # Enrich price map from bulk product list (single API call, cached 1hr)
        # This avoids N sequential rate-limited ticker calls that cause timeouts.
        missing_price_coins = [
            coin for coin, _ in altcoins if prices.get(f"{coin}-USD", 0.0) <= 0
        ]
        if missing_price_coins:
            try:
                all_products = await public_market_data.list_products()
                bulk_prices = {
                    p.get("product_id", ""): float(p.get("price") or 0)
                    for p in all_products
                }
                for coin in missing_price_coins:
                    price = bulk_prices.get(f"{coin}-USD", 0.0)
                    if price > 0:
                        prices[f"{coin}-USD"] = price
            except Exception:
                # Falls through to "no price" handling below — not fatal.
                logger.warning(
                    "Bulk product-list fetch failed while pricing dust for account %s",
                    account_id, exc_info=True,
                )

        for coin, amount in altcoins:
            usd_price = prices.get(f"{coin}-USD", 0.0)
            if usd_price <= 0:
                continue
            usd_value = amount * usd_price
            if usd_value >= threshold:
                dust_positions.append({
                    "coin": coin,
                    "amount": round(amount, 8),
                    "usd_value": round(usd_value, 2),
                })

        dust_positions.sort(key=lambda d: d["usd_value"], reverse=True)
    except Exception:
        logger.warning(
            "Error building dust positions for account %s",
            account_id, exc_info=True,
        )

    response_data = {
        "enabled": account.dust_sweep_enabled or False,
        "threshold_usd": account.dust_sweep_threshold_usd or 5.0,
        "last_sweep_at": (
            account.dust_last_sweep_at.isoformat()
            if account.dust_last_sweep_at else None
        ),
        "dust_positions": dust_positions,
    }
    if not account.is_paper_trading:
        _TTL_DUST_SWEEP[account_id] = (time.monotonic(), response_data)
    return response_data
