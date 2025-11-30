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
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Account, Bot, Position
from app.services.dex_wallet_service import dex_wallet_service

logger = logging.getLogger(__name__)


# Dependency - will be injected from main.py
_coinbase_client = None


def set_coinbase_client(client):
    """Set the coinbase client (called from main.py)"""
    global _coinbase_client
    _coinbase_client = client


def get_coinbase():
    """Get coinbase client"""
    if _coinbase_client is None:
        raise RuntimeError("Coinbase client not initialized")
    return _coinbase_client

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


@router.get("/{account_id}/portfolio")
async def get_account_portfolio(
    account_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get portfolio for a specific account.

    For CEX accounts: Fetches from Coinbase API
    For DEX accounts: Fetches from blockchain via RPC
    """
    try:
        # Get the account
        query = select(Account).where(Account.id == account_id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()

        if not account:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")

        if account.type == "cex":
            # Use existing Coinbase portfolio logic
            return await _get_cex_portfolio(account, db)
        else:
            # Use DEX wallet service for blockchain balances
            return await _get_dex_portfolio(account, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting portfolio for account {account_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _get_cex_portfolio(account: Account, db: AsyncSession) -> dict:
    """Get portfolio for a CEX (Coinbase) account."""
    import asyncio

    coinbase = get_coinbase()

    # Get portfolio breakdown with all holdings
    breakdown = await coinbase.get_portfolio_breakdown()
    spot_positions = breakdown.get("spot_positions", [])

    # Get BTC/USD price for valuations
    btc_usd_price = await coinbase.get_btc_usd_price()

    # Prepare list of assets that need pricing
    assets_to_price = []
    for position in spot_positions:
        asset = position.get("asset", "")
        total_balance = float(position.get("total_balance_crypto", 0))

        if total_balance == 0:
            continue

        if asset not in ["USD", "USDC", "BTC"]:
            assets_to_price.append((asset, total_balance, position))

    # Fetch prices in batches to avoid rate limiting
    async def fetch_price(asset: str):
        try:
            price = await coinbase.get_current_price(f"{asset}-USD")
            return (asset, price)
        except Exception as e:
            logger.warning(f"Could not get USD price for {asset}: {e}")
            return (asset, None)

    # Batch price fetching: 15 concurrent requests, then 0.2s delay, repeat
    batch_size = 15
    price_results = []
    for i in range(0, len(assets_to_price), batch_size):
        batch = assets_to_price[i:i + batch_size]
        batch_results = await asyncio.gather(
            *[fetch_price(asset) for asset, _, _ in batch]
        )
        price_results.extend(batch_results)
        # Small delay between batches (not between individual requests)
        if i + batch_size < len(assets_to_price):
            await asyncio.sleep(0.2)

    prices = {asset: price for asset, price in price_results if price is not None}

    # Build portfolio with all prices
    portfolio_holdings = []
    total_usd_value = 0.0
    total_btc_value = 0.0
    actual_usd_balance = 0.0
    actual_usdc_balance = 0.0
    actual_btc_balance = 0.0

    for position in spot_positions:
        asset = position.get("asset", "")
        total_balance = float(position.get("total_balance_crypto", 0))
        available = float(position.get("available_to_trade_crypto", 0))
        hold = total_balance - available

        if total_balance == 0:
            continue

        usd_value = 0.0
        btc_value = 0.0
        current_price_usd = 0.0

        if asset == "USD":
            usd_value = total_balance
            btc_value = total_balance / btc_usd_price if btc_usd_price > 0 else 0
            current_price_usd = 1.0
            actual_usd_balance += total_balance
        elif asset == "USDC":
            usd_value = total_balance
            btc_value = total_balance / btc_usd_price if btc_usd_price > 0 else 0
            current_price_usd = 1.0
            actual_usdc_balance += total_balance
        elif asset == "BTC":
            usd_value = total_balance * btc_usd_price
            btc_value = total_balance
            current_price_usd = btc_usd_price
            actual_btc_balance += total_balance
        else:
            if asset not in prices:
                continue
            current_price_usd = prices[asset]
            usd_value = total_balance * current_price_usd
            btc_value = usd_value / btc_usd_price if btc_usd_price > 0 else 0

        if usd_value < 0.01:
            continue

        total_usd_value += usd_value
        total_btc_value += btc_value

        portfolio_holdings.append({
            "asset": asset,
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

    # Calculate percentages
    for holding in portfolio_holdings:
        if total_usd_value > 0:
            holding["percentage"] = (holding["usd_value"] / total_usd_value) * 100

    # Get PnL from positions for this account
    # Include positions with NULL account_id for CEX default accounts (legacy positions)
    if account.is_default and account.type == "cex":
        positions_query = select(Position).where(
            Position.status == "open",
            or_(Position.account_id == account.id, Position.account_id.is_(None))
        )
    else:
        positions_query = select(Position).where(
            Position.status == "open",
            Position.account_id == account.id
        )
    positions_result = await db.execute(positions_query)
    open_positions = positions_result.scalars().all()

    # Fetch all position prices in PARALLEL to avoid slow sequential API calls
    position_prices = {}
    if open_positions:
        async def fetch_price_for_product(product_id: str):
            try:
                price = await coinbase.get_current_price(product_id)
                return (product_id, price)
            except Exception as e:
                logger.warning(f"Could not get price for {product_id}: {e}")
                return (product_id, None)

        # Get unique product_ids to avoid duplicate fetches
        unique_products = list({f"{p.get_base_currency()}-{p.get_quote_currency()}" for p in open_positions})

        # Batch price fetching for positions: 15 concurrent, then 0.2s delay
        position_price_results = []
        for i in range(0, len(unique_products), batch_size):
            batch = unique_products[i:i + batch_size]
            batch_results = await asyncio.gather(*[fetch_price_for_product(pid) for pid in batch])
            position_price_results.extend(batch_results)
            if i + batch_size < len(unique_products):
                await asyncio.sleep(0.2)

        position_prices = {pid: price for pid, price in position_price_results if price is not None}

    asset_pnl = {}
    for position in open_positions:
        base = position.get_base_currency()
        quote = position.get_quote_currency()
        product_id = f"{base}-{quote}"

        current_price = position_prices.get(product_id)
        if current_price is None:
            continue

        current_value_quote = position.total_base_acquired * current_price
        profit_quote = current_value_quote - position.total_quote_spent

        if quote == "USD":
            profit_usd = profit_quote
            cost_usd = position.total_quote_spent
        elif quote == "BTC":
            profit_usd = profit_quote * btc_usd_price
            cost_usd = position.total_quote_spent * btc_usd_price
        else:
            continue

        if base not in asset_pnl:
            asset_pnl[base] = {"pnl_usd": 0.0, "cost_usd": 0.0}

        asset_pnl[base]["pnl_usd"] += profit_usd
        asset_pnl[base]["cost_usd"] += cost_usd

    for holding in portfolio_holdings:
        asset = holding["asset"]
        if asset in asset_pnl:
            pnl_data = asset_pnl[asset]
            holding["unrealized_pnl_usd"] = pnl_data["pnl_usd"]
            if pnl_data["cost_usd"] > 0:
                holding["unrealized_pnl_percentage"] = (pnl_data["pnl_usd"] / pnl_data["cost_usd"]) * 100

    portfolio_holdings.sort(key=lambda x: x["usd_value"], reverse=True)

    # Get balance breakdown for this account's bots
    # Include bots with NULL account_id for CEX default accounts (legacy bots)
    if account.is_default and account.type == "cex":
        bots_query = select(Bot).where(or_(Bot.account_id == account.id, Bot.account_id.is_(None)))
    else:
        bots_query = select(Bot).where(Bot.account_id == account.id)
    bots_result = await db.execute(bots_query)
    account_bots = bots_result.scalars().all()

    total_reserved_btc = sum(bot.reserved_btc_balance for bot in account_bots)
    total_reserved_usd = sum(bot.reserved_usd_balance for bot in account_bots)

    total_in_positions_btc = 0.0
    total_in_positions_usd = 0.0
    total_in_positions_usdc = 0.0

    # Use cached prices from earlier parallel fetch
    for position in open_positions:
        quote = position.get_quote_currency()
        base = position.get_base_currency()
        product_id = f"{base}-{quote}"

        current_price = position_prices.get(product_id)
        if current_price is not None:
            current_value = position.total_base_acquired * current_price
        else:
            # Fallback to quote spent if price unavailable
            current_value = position.total_quote_spent

        if quote == "USD":
            total_in_positions_usd += current_value
        elif quote == "USDC":
            total_in_positions_usdc += current_value
        else:
            total_in_positions_btc += current_value

    total_btc_portfolio = actual_btc_balance + total_in_positions_btc
    total_usd_portfolio = actual_usd_balance + total_in_positions_usd
    total_usdc_portfolio = actual_usdc_balance + total_in_positions_usdc

    free_btc = max(0.0, total_btc_portfolio - (total_reserved_btc + total_in_positions_btc))
    free_usd = max(0.0, total_usd_portfolio - (total_reserved_usd + total_in_positions_usd))
    free_usdc = max(0.0, total_usdc_portfolio - total_in_positions_usdc)

    # Calculate PnL
    # Include closed positions with NULL account_id for CEX default accounts (legacy positions)
    if account.is_default and account.type == "cex":
        closed_positions_query = select(Position).where(
            Position.status == "closed",
            or_(Position.account_id == account.id, Position.account_id.is_(None))
        )
    else:
        closed_positions_query = select(Position).where(
            Position.status == "closed",
            Position.account_id == account.id
        )
    closed_positions_result = await db.execute(closed_positions_query)
    closed_positions = closed_positions_result.scalars().all()

    pnl_all_time = {"usd": 0.0, "btc": 0.0, "usdc": 0.0}
    pnl_today = {"usd": 0.0, "btc": 0.0, "usdc": 0.0}
    today = datetime.utcnow().date()

    for position in closed_positions:
        if position.profit_quote is not None:
            quote = position.get_quote_currency()
            quote_key = quote.lower() if quote in ["USD", "BTC", "USDC"] else "usd"

            pnl_all_time[quote_key] += position.profit_quote

            if position.closed_at and position.closed_at.date() == today:
                pnl_today[quote_key] += position.profit_quote

    return {
        "total_usd_value": total_usd_value,
        "total_btc_value": total_btc_value,
        "btc_usd_price": btc_usd_price,
        "holdings": portfolio_holdings,
        "holdings_count": len(portfolio_holdings),
        "balance_breakdown": {
            "btc": {
                "total": total_btc_portfolio,
                "reserved_by_bots": total_reserved_btc,
                "in_open_positions": total_in_positions_btc,
                "free": free_btc,
            },
            "usd": {
                "total": total_usd_portfolio,
                "reserved_by_bots": total_reserved_usd,
                "in_open_positions": total_in_positions_usd,
                "free": free_usd,
            },
            "usdc": {
                "total": total_usdc_portfolio,
                "reserved_by_bots": 0.0,
                "in_open_positions": total_in_positions_usdc,
                "free": free_usdc,
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


async def _get_dex_portfolio(account: Account, db: AsyncSession) -> dict:
    """Get portfolio for a DEX (wallet) account."""
    # Get ETH/USD price for valuations (from Coinbase or other source)
    try:
        coinbase = get_coinbase()
        eth_usd_price = await coinbase.get_current_price("ETH-USD")
        btc_usd_price = await coinbase.get_btc_usd_price()
    except Exception:
        # Fallback prices if Coinbase is not available
        eth_usd_price = 3500.0
        btc_usd_price = 95000.0

    # Fetch wallet portfolio from blockchain
    portfolio = await dex_wallet_service.get_wallet_portfolio(
        chain_id=account.chain_id or 1,
        wallet_address=account.wallet_address or "",
        rpc_url=account.rpc_url,
        include_tokens=True,
    )

    if portfolio.error:
        logger.warning(f"Error fetching DEX portfolio: {portfolio.error}")

    # Format for API response (includes CoinGecko price fetching)
    formatted = await dex_wallet_service.format_portfolio_for_api(
        portfolio,
        eth_usd_price=eth_usd_price,
        btc_usd_price=btc_usd_price,
    )

    # Add account info and PnL placeholders
    formatted["account_id"] = account.id
    formatted["account_name"] = account.name
    formatted["account_type"] = "dex"
    formatted["pnl"] = {
        "today": {"usd": 0.0, "btc": 0.0, "eth": 0.0},
        "all_time": {"usd": 0.0, "btc": 0.0, "eth": 0.0},
    }
    formatted["balance_breakdown"] = {
        "eth": {
            "total": float(portfolio.native_balance),
            "reserved_by_bots": 0.0,
            "in_open_positions": 0.0,
            "free": float(portfolio.native_balance),
        }
    }

    return formatted
