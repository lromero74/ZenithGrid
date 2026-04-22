"""Shared Pydantic request/response schemas for the accounts routers.

Moved here from accounts_query_router so that accounts_mutation_router
does not have to reach across the router layer to reuse them.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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

    # Speculative bucket — see PRPs/high-risk-doubling-preset.md §Task D1.
    # 0 = no bucket (speculative bots are blocked from opening new positions).
    speculative_allocation_pct: Optional[float] = Field(None, ge=0.0, le=100.0)


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

    # Speculative bucket — surfaced so the UI can show/edit the allocation.
    speculative_allocation_pct: float = 0.0

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
