"""
Account and portfolio API routes

Handles account-related endpoints:
- Account balances (BTC, ETH, totals)
- Aggregate portfolio value calculations
- Full portfolio breakdown (3Commas-style)
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import api_cache, portfolio_cache
from app.coinbase_unified_client import CoinbaseClient
from app.database import get_db
from app.encryption import decrypt_value, is_encrypted
from app.exchange_clients.factory import create_exchange_client
from app.models import Account, Bot, PendingOrder, Position, User
from app.auth.dependencies import get_current_user
from app.services import portfolio_conversion_service as pcs
from app.services.exchange_service import get_exchange_client_for_account

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account", tags=["account"])


async def get_user_paper_account(db: AsyncSession, user_id: int) -> Optional[Account]:
    """Get user's paper trading account if they have no live CEX account."""
    # Check if user has a live CEX account
    live_result = await db.execute(
        select(Account).where(
            Account.user_id == user_id,
            Account.type == "cex",
            Account.is_active.is_(True),
            Account.is_paper_trading.is_not(True)
        ).limit(1)
    )
    if live_result.scalar_one_or_none():
        return None  # Has live account, not paper-only

    # Get paper trading account
    paper_result = await db.execute(
        select(Account).where(
            Account.user_id == user_id,
            Account.is_paper_trading.is_(True),
            Account.is_active.is_(True),
        ).limit(1)
    )
    return paper_result.scalar_one_or_none()


async def get_coinbase_from_db(db: AsyncSession, user_id: int = None) -> CoinbaseClient:
    """
    Get Coinbase client from the first active CEX account in the database.
    Excludes paper trading accounts. Filters by user_id if provided.
    """
    # Get first active CEX account for this user (excluding paper trading)
    query = select(Account).where(
        Account.type == "cex",
        Account.is_active.is_(True),
        Account.is_paper_trading.is_not(True)
    )
    if user_id:
        query = query.where(Account.user_id == user_id)
    query = query.order_by(Account.is_default.desc(), Account.created_at).limit(1)
    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=503,
            detail="No Coinbase account configured. Please add your API credentials in Settings."
        )

    if not account.api_key_name or not account.api_private_key:
        raise HTTPException(
            status_code=503,
            detail="Coinbase account missing API credentials. Please update in Settings."
        )

    # Decrypt private key if encrypted
    private_key = account.api_private_key
    if is_encrypted(private_key):
        private_key = decrypt_value(private_key)

    # Create and return the client
    client = create_exchange_client(
        exchange_type="cex",
        coinbase_key_name=account.api_key_name,
        coinbase_private_key=private_key,
    )

    if not client:
        raise HTTPException(
            status_code=503,
            detail="Failed to create Coinbase client. Please check your API credentials."
        )

    return client


@router.get("/balances")
async def get_balances(
    account_id: Optional[int] = Query(None, description="Account ID (defaults to first active CEX account)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current account balances for all quote currencies with capital reservation tracking.

    Returns:
    - Account balances from exchange (what you have in your account)
    - Reserved capital in open positions (locked in active trades)
    - Reserved capital in pending orders (locked in grid bot limit orders)
    - Available balance (what you can use for new bots)

    For paper trading accounts, returns virtual balances from paper_balances JSON field.
    """
    try:
        import json

        # Get account (either specified or default) — always filter by current user
        if account_id:
            account_result = await db.execute(
                select(Account).where(Account.id == account_id, Account.user_id == current_user.id)
            )
            account = account_result.scalar_one_or_none()
            if not account:
                raise HTTPException(status_code=404, detail="Account not found")
        else:
            # Get first active CEX account for current user
            account_result = await db.execute(
                select(Account).where(
                    Account.type == "cex",
                    Account.is_active.is_(True),
                    Account.user_id == current_user.id,
                ).order_by(Account.is_default.desc(), Account.created_at)
                .limit(1)
            )
            account = account_result.scalar_one_or_none()
            if not account:
                raise HTTPException(status_code=404, detail="No active account found")

        # Check if this is a paper trading account
        if account.is_paper_trading:
            # Use virtual balances from paper_balances JSON
            if account.paper_balances:
                balances = json.loads(account.paper_balances)
            else:
                balances = {"BTC": 0.0, "ETH": 0.0, "USD": 0.0, "USDC": 0.0, "USDT": 0.0}

            btc_balance = balances.get("BTC", 0.0)
            eth_balance = balances.get("ETH", 0.0)
            usd_balance = balances.get("USD", 0.0)
            usdc_balance = balances.get("USDC", 0.0)
            usdt_balance = balances.get("USDT", 0.0)

            # Use public market data for prices (no auth needed for paper trading)
            from app.coinbase_api.public_market_data import (
                get_btc_usd_price as get_public_btc_price,
                get_current_price as get_public_price,
            )
            current_price = await get_public_price("ETH-BTC")
            btc_usd_price = await get_public_btc_price()
        else:
            # Live account - fetch from Coinbase
            coinbase = await get_coinbase_from_db(db, current_user.id)

            # Get account balances from Coinbase
            btc_balance = await coinbase.get_btc_balance()
            eth_balance = await coinbase.get_eth_balance()
            usd_balance = await coinbase.get_usd_balance()
            usdc_balance = await coinbase.get_usdc_balance()
            usdt_balance = await coinbase.get_usdt_balance()
            current_price = await coinbase.get_current_price()
            btc_usd_price = await coinbase.get_btc_usd_price()

        # Calculate reserved capital in OPEN POSITIONS (by quote currency)
        # Filter by account_id to only include positions for this account
        positions_result = await db.execute(
            select(Position).where(
                Position.status == "open",
                Position.account_id == account.id
            )
        )
        open_positions = positions_result.scalars().all()

        reserved_in_positions = {"BTC": 0.0, "ETH": 0.0, "USD": 0.0, "USDC": 0.0, "USDT": 0.0}
        for pos in open_positions:
            if pos.product_id and "-" in pos.product_id:
                quote_currency = pos.product_id.split("-")[1]
                if quote_currency in reserved_in_positions and pos.total_quote_spent:
                    reserved_in_positions[quote_currency] += pos.total_quote_spent

        # Calculate reserved capital in PENDING ORDERS (by currency)
        # Get all bots for this account, then filter pending orders by those bot IDs
        bots_result = await db.execute(
            select(Bot).where(Bot.account_id == account.id)
        )
        account_bots = bots_result.scalars().all()
        bot_ids = [bot.id for bot in account_bots]

        if bot_ids:
            pending_result = await db.execute(
                select(PendingOrder).where(
                    PendingOrder.status == "pending",
                    PendingOrder.bot_id.in_(bot_ids)
                )
            )
            pending_orders = pending_result.scalars().all()
        else:
            pending_orders = []

        reserved_in_pending_orders = {"BTC": 0.0, "ETH": 0.0, "USD": 0.0, "USDC": 0.0, "USDT": 0.0}
        for order in pending_orders:
            # For buy orders: reserved quote currency
            if order.side == "BUY" and order.product_id and "-" in order.product_id:
                quote_currency = order.product_id.split("-")[1]
                if quote_currency in reserved_in_pending_orders and order.reserved_amount_quote:
                    reserved_in_pending_orders[quote_currency] += order.reserved_amount_quote

            # For sell orders: reserved base currency
            elif order.side == "SELL" and order.product_id and "-" in order.product_id:
                base_currency = order.product_id.split("-")[0]
                if base_currency in reserved_in_pending_orders and order.reserved_amount_base:
                    reserved_in_pending_orders[base_currency] += order.reserved_amount_base

        # Calculate truly AVAILABLE balances (what can be used for new bots)
        # Available = Account Balance - Reserved in Positions - Reserved in Pending Orders
        available_btc = btc_balance - reserved_in_positions["BTC"] - reserved_in_pending_orders["BTC"]
        available_eth = eth_balance - reserved_in_positions["ETH"] - reserved_in_pending_orders["ETH"]
        available_usd = usd_balance - reserved_in_positions["USD"] - reserved_in_pending_orders["USD"]
        available_usdc = usdc_balance - reserved_in_positions["USDC"] - reserved_in_pending_orders["USDC"]
        available_usdt = usdt_balance - reserved_in_positions["USDT"] - reserved_in_pending_orders["USDT"]

        # Ensure no negative available balances (edge case protection)
        available_btc = max(0, available_btc)
        available_eth = max(0, available_eth)
        available_usd = max(0, available_usd)
        available_usdc = max(0, available_usdc)
        available_usdt = max(0, available_usdt)

        total_btc_value = btc_balance + (eth_balance * current_price)
        total_usd_value = (total_btc_value * btc_usd_price) + usd_balance + usdc_balance + usdt_balance

        return {
            # Account balances (from exchange)
            "btc": btc_balance,
            "eth": eth_balance,
            "usd": usd_balance,
            "usdc": usdc_balance,
            "usdt": usdt_balance,

            # Reserved capital tracking
            "reserved_in_positions": reserved_in_positions,
            "reserved_in_pending_orders": reserved_in_pending_orders,

            # Available balances (for new bots)
            "available_btc": available_btc,
            "available_eth": available_eth,
            "available_usd": available_usd,
            "available_usdc": available_usdc,
            "available_usdt": available_usdt,

            # Calculated values
            "eth_value_in_btc": eth_balance * current_price,
            "total_btc_value": total_btc_value,
            "current_eth_btc_price": current_price,
            "btc_usd_price": btc_usd_price,
            "total_usd_value": total_usd_value,
        }
    except Exception as e:
        logger.error(f"Error getting balances: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/aggregate-value")
async def get_aggregate_value(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get aggregate portfolio value (BTC + USD) for bot budgeting"""
    try:
        # Check if user is paper-only
        paper_account = await get_user_paper_account(db, current_user.id)
        if paper_account:
            client = await get_exchange_client_for_account(db, paper_account.id)
            if client:
                aggregate_btc = await client.calculate_aggregate_btc_value()
                aggregate_usd = await client.calculate_aggregate_usd_value()
                btc_usd_price = await client.get_btc_usd_price()
                return {
                    "aggregate_btc_value": aggregate_btc,
                    "aggregate_usd_value": aggregate_usd,
                    "btc_usd_price": btc_usd_price,
                }
            # Paper account but client creation failed — return defaults
            return {
                "aggregate_btc_value": 0.0,
                "aggregate_usd_value": 0.0,
                "btc_usd_price": 0.0,
            }

        coinbase = await get_coinbase_from_db(db, current_user.id)
        aggregate_btc = await coinbase.calculate_aggregate_btc_value()
        aggregate_usd = await coinbase.calculate_aggregate_usd_value()
        btc_usd_price = await coinbase.get_btc_usd_price()

        return {
            "aggregate_btc_value": aggregate_btc,
            "aggregate_usd_value": aggregate_usd,
            "btc_usd_price": btc_usd_price,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/portfolio")
async def get_portfolio(
    force_fresh: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full portfolio breakdown (all coins like 3Commas)"""
    try:
        # Paper-only users get a simulated portfolio from their virtual balances
        paper_account = await get_user_paper_account(db, current_user.id)
        if paper_account:
            client = await get_exchange_client_for_account(db, paper_account.id)
            if client and hasattr(client, 'balances'):
                btc_usd_price = 0.0
                try:
                    btc_usd_price = await client.get_btc_usd_price()
                except Exception:
                    pass
                assets = []
                for currency, balance in client.balances.items():
                    if balance > 0:
                        assets.append({
                            "asset": currency,
                            "total_balance": balance,
                            "available_balance": balance,
                            "hold_balance": 0.0,
                            "usd_value": (
                                balance * btc_usd_price if currency == "BTC"
                                else balance if currency in ("USD", "USDC")
                                else 0.0
                            ),
                            "btc_value": balance if currency == "BTC" else 0.0,
                            "allocation_pct": 0.0,
                            "price_usd": (
                                btc_usd_price if currency == "BTC"
                                else 1.0 if currency in ("USD", "USDC")
                                else 0.0
                            ),
                            "change_24h": 0.0,
                        })
                return {
                    "assets": assets,
                    "total_usd_value": sum(a["usd_value"] for a in assets),
                    "total_btc_value": sum(a["btc_value"] for a in assets),
                    "btc_usd_price": btc_usd_price,
                    "is_paper_trading": True,
                }
            return {
                "assets": [], "total_usd_value": 0,
                "total_btc_value": 0, "btc_usd_price": 0,
                "is_paper_trading": True,
            }

        cache_key = f"portfolio_response_{current_user.id}"

        if not force_fresh:
            # Check in-memory cache first (60s TTL)
            cached = await api_cache.get(cache_key)
            if cached is not None:
                logger.debug("Using cached portfolio response")
                return cached

            # Check persistent cache (survives restarts)
            persistent = await portfolio_cache.get(current_user.id)
            if persistent is not None:
                # Serve stale data immediately, populate in-memory cache
                await api_cache.set(cache_key, persistent, 60)
                logger.info("Serving persistent portfolio cache while fresh data loads")
                return persistent

        coinbase = await get_coinbase_from_db(db, current_user.id)

        # Single API call: breakdown has USD values for every position
        breakdown = await coinbase.get_portfolio_breakdown()
        spot_positions = breakdown.get("spot_positions", [])

        # Get BTC/USD price for BTC value column (uses cache, very fast)
        btc_usd_price = await coinbase.get_btc_usd_price()

        # Build portfolio directly from breakdown data — no individual
        # price fetches needed. Coinbase returns total_balance_fiat (USD)
        # for every position in the single breakdown call.
        portfolio_holdings = []
        total_usd_value = 0.0
        total_btc_value = 0.0

        # Track actual balances for balance breakdown section
        actual_usd_balance = 0.0
        actual_usdc_balance = 0.0
        actual_btc_balance = 0.0

        # Price lookup derived from breakdown (for position PnL later)
        breakdown_prices = {}  # {asset: usd_price}

        for position in spot_positions:
            asset = position.get("asset", "")
            total_balance = float(position.get("total_balance_crypto", 0))
            available = float(position.get("available_to_trade_crypto", 0))
            hold = total_balance - available

            if total_balance == 0:
                continue

            # Use Coinbase's pre-calculated fiat value
            usd_value = float(position.get("total_balance_fiat", 0))

            # Derive current price from fiat/crypto ratio
            if total_balance > 0 and usd_value > 0:
                current_price_usd = usd_value / total_balance
            elif asset == "USD":
                current_price_usd = 1.0
                usd_value = total_balance
            elif asset == "USDC":
                current_price_usd = 1.0
                usd_value = total_balance
            elif asset == "BTC":
                current_price_usd = btc_usd_price
                usd_value = total_balance * btc_usd_price
            else:
                current_price_usd = 0.0

            # Track actual quote currency balances
            if asset == "USD":
                actual_usd_balance += total_balance
            elif asset == "USDC":
                actual_usdc_balance += total_balance
            elif asset == "BTC":
                actual_btc_balance += total_balance

            # Store derived price for position PnL calculations
            if current_price_usd > 0:
                breakdown_prices[asset] = current_price_usd

            btc_value = usd_value / btc_usd_price if btc_usd_price > 0 else 0

            # Skip dust (< $0.01)
            if usd_value < 0.01 and current_price_usd > 0:
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

        # Calculate unrealized PnL from open positions (scoped to current user)
        user_accounts_q = select(Account.id).where(Account.user_id == current_user.id)
        user_accounts_r = await db.execute(user_accounts_q)
        user_account_ids = [row[0] for row in user_accounts_r.fetchall()]

        positions_query = select(Position).where(
            Position.status == "open",
            Position.account_id.in_(user_account_ids) if user_account_ids else Position.id < 0,
        )
        positions_result = await db.execute(positions_query)
        open_positions = positions_result.scalars().all()

        # Use prices derived from breakdown — no additional API calls
        asset_pnl = {}
        for position in open_positions:
            base = position.get_base_currency()
            quote = position.get_quote_currency()

            # For USD pairs: use breakdown-derived USD price
            # For BTC pairs: use breakdown-derived BTC price (USD price / BTC price)
            if quote == "USD":
                current_price = breakdown_prices.get(base)
            elif quote == "BTC":
                base_usd = breakdown_prices.get(base)
                if base_usd and btc_usd_price > 0:
                    current_price = base_usd / btc_usd_price
                else:
                    current_price = None
            else:
                current_price = None

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

        # Add PnL to holdings
        for holding in portfolio_holdings:
            asset = holding["asset"]
            if asset in asset_pnl:
                pnl_data = asset_pnl[asset]
                holding["unrealized_pnl_usd"] = pnl_data["pnl_usd"]
                if pnl_data["cost_usd"] > 0:
                    holding["unrealized_pnl_percentage"] = (
                        pnl_data["pnl_usd"] / pnl_data["cost_usd"]
                    ) * 100

        # Sort by USD value descending
        portfolio_holdings.sort(key=lambda x: x["usd_value"], reverse=True)

        # Calculate free (unreserved) balances for BTC and USD
        # Free = Total Portfolio - (Bot Reservations + Open Position Balances)

        # Get bots for current user and sum their reservations
        bots_query = select(Bot).where(
            Bot.account_id.in_(user_account_ids) if user_account_ids else Bot.id < 0,
        )
        bots_result = await db.execute(bots_query)
        all_bots = bots_result.scalars().all()

        total_reserved_btc = sum(bot.reserved_btc_balance for bot in all_bots)
        total_reserved_usd = sum(bot.reserved_usd_balance for bot in all_bots)

        # Reuse open_positions from above (no duplicate query)
        total_in_positions_btc = 0.0
        total_in_positions_usd = 0.0
        total_in_positions_usdc = 0.0

        for position in open_positions:
            quote = position.get_quote_currency()
            base = position.get_base_currency()

            # Derive position price from breakdown data
            if quote == "USD" or quote == "USDC":
                pos_price = breakdown_prices.get(base)
            elif quote == "BTC":
                base_usd = breakdown_prices.get(base)
                pos_price = base_usd / btc_usd_price if base_usd and btc_usd_price > 0 else None
            else:
                pos_price = None

            if pos_price is not None:
                current_value = position.total_base_acquired * pos_price
            else:
                current_value = position.total_quote_spent

            if quote == "USD":
                total_in_positions_usd += current_value
            elif quote == "USDC":
                total_in_positions_usdc += current_value
            else:  # BTC
                total_in_positions_btc += current_value

        # Balance breakdown should show ONLY actual balances + their respective positions
        # NOT the total portfolio value converted
        # BTC: actual BTC balance + BTC value of BTC-pair positions
        # USD: actual USD balance + USD value of USD-pair positions
        # USDC: actual USDC balance + USDC value of USDC-pair positions
        total_btc_portfolio = actual_btc_balance + total_in_positions_btc
        total_usd_portfolio = actual_usd_balance + total_in_positions_usd
        total_usdc_portfolio = actual_usdc_balance + total_in_positions_usdc

        # Calculate free balances
        # Note: No USDC bots yet, so total_reserved_usdc = 0
        total_reserved_usdc = 0.0
        free_btc = total_btc_portfolio - (total_reserved_btc + total_in_positions_btc)
        free_usd = total_usd_portfolio - (total_reserved_usd + total_in_positions_usd)
        free_usdc = total_usdc_portfolio - (total_reserved_usdc + total_in_positions_usdc)

        # Ensure free balances don't go negative
        free_btc = max(0.0, free_btc)
        free_usd = max(0.0, free_usd)
        free_usdc = max(0.0, free_usdc)

        # Calculate realized PnL from closed positions (scoped to current user)
        closed_positions_query = select(Position).where(
            Position.status == "closed",
            Position.account_id.in_(user_account_ids) if user_account_ids else Position.id < 0,
        )
        closed_positions_result = await db.execute(closed_positions_query)
        closed_positions = closed_positions_result.scalars().all()

        pnl_all_time_usd = 0.0
        pnl_all_time_btc = 0.0
        pnl_all_time_usdc = 0.0
        pnl_today_usd = 0.0
        pnl_today_btc = 0.0
        pnl_today_usdc = 0.0

        now = datetime.utcnow()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        for position in closed_positions:
            if position.profit_quote is not None:
                quote = position.get_quote_currency()

                # All-time PnL
                if quote == "USD":
                    pnl_all_time_usd += position.profit_quote
                elif quote == "USDC":
                    pnl_all_time_usdc += position.profit_quote
                else:  # BTC
                    pnl_all_time_btc += position.profit_quote

                # Today's PnL
                if position.closed_at and position.closed_at >= start_of_today:
                    if quote == "USD":
                        pnl_today_usd += position.profit_quote
                    elif quote == "USDC":
                        pnl_today_usdc += position.profit_quote
                    else:  # BTC
                        pnl_today_btc += position.profit_quote

        # Log portfolio summary for debugging inconsistent results
        logger.info(
            f"Portfolio summary: {len(spot_positions)} raw positions -> "
            f"{len(portfolio_holdings)} after filtering (${total_usd_value:.2f} total)"
        )

        result = {
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
                    "reserved_by_bots": total_reserved_usdc,
                    "in_open_positions": total_in_positions_usdc,
                    "free": free_usdc,
                },
            },
            "pnl": {
                "today": {"usd": pnl_today_usd, "btc": pnl_today_btc, "usdc": pnl_today_usdc},
                "all_time": {"usd": pnl_all_time_usd, "btc": pnl_all_time_btc, "usdc": pnl_all_time_usdc},
            },
        }

        # Cache in-memory (60s) and persist to disk (survives restarts)
        await api_cache.set(cache_key, result, 60)
        await portfolio_cache.save(current_user.id, result)
        return result
    except Exception as e:
        logger.exception(f"Portfolio endpoint error: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred")


@router.get("/conversion-status/{task_id}")
async def get_conversion_status(task_id: str, current_user: User = Depends(get_current_user)):
    """
    Get status of a portfolio conversion task (requires auth)
    """
    progress = pcs.get_task_progress(task_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Conversion task not found")
    return progress


async def _run_portfolio_conversion(
    task_id: str,
    account_id: int,
    target_currency: str,
    user_id: int,
):
    """
    Background task to convert portfolio to target currency
    """
    from app.database import get_db

    try:
        pcs.update_task_progress(task_id, status="running", message="Initializing conversion...")

        # Get database session
        async for db in get_db():
            # Get exchange client
            exchange = await get_exchange_client_for_account(db, account_id)
            if not exchange:
                pcs.update_task_progress(
                    task_id,
                    status="failed",
                    message=f"No exchange client for account {account_id}"
                )
                return

            # Get all account balances
            pcs.update_task_progress(task_id, message="Fetching account balances...")
            try:
                all_accounts = await exchange.get_accounts(force_fresh=True)
            except Exception as e:
                pcs.update_task_progress(
                    task_id,
                    status="failed",
                    message=f"Failed to fetch account balances: {str(e)}"
                )
                return

            # Filter currencies to sell (excluding target and dust)
            currencies_to_sell = []
            for acc in all_accounts:
                currency = acc.get("currency")
                available_str = acc.get("available_balance", {}).get("value", "0")
                available = float(available_str)

                if currency == target_currency or available <= 0:
                    continue

                # Skip dust
                if currency == "USD" and available < 0.50:
                    continue
                if currency == "BTC" and available < 0.00001:
                    continue

                currencies_to_sell.append({
                    "currency": currency,
                    "available": available,
                })

            if not currencies_to_sell:
                pcs.update_task_progress(
                    task_id,
                    status="completed",
                    message=f"Portfolio already in {target_currency}",
                    total=0,
                    current=0
                )
                return

            # Start conversion
            total_to_process = len(currencies_to_sell)
            pcs.update_task_progress(
                task_id,
                total=total_to_process,
                current=0,
                message=f"Converting {total_to_process} currencies..."
            )

            sold_count = 0
            failed_count = 0
            errors = []
            converted_via_usd = []
            converted_via_btc = []

            logger.info(f"🔄 Task {task_id}: Starting portfolio conversion: {total_to_process} currencies to process")

            # Process each currency
            for idx, item in enumerate(currencies_to_sell, 1):
                currency = item["currency"]
                available = item["available"]

                try:
                    if target_currency == "BTC":
                        # Try BTC pair first, fallback to USD
                        product_id = f"{currency}-BTC"
                        try:
                            await exchange.create_market_order(
                                product_id=product_id,
                                side="SELL",
                                size=str(available),
                            )
                            sold_count += 1
                            progress_pct = int((idx / total_to_process) * 100)
                            logger.info(
                                f"✅ [{idx}/{total_to_process}] ({progress_pct}%) "
                                f"Sold {available} {currency} to BTC directly"
                            )
                            await asyncio.sleep(0.2)
                        except Exception as direct_error:
                            if "403" in str(direct_error) or "400" in str(direct_error):
                                usd_product_id = f"{currency}-USD"
                                await exchange.create_market_order(
                                    product_id=usd_product_id,
                                    side="SELL",
                                    size=str(available),
                                )
                                converted_via_usd.append(currency)
                                sold_count += 1
                                progress_pct = int((idx / total_to_process) * 100)
                                logger.info(
                                    f"✅ [{idx}/{total_to_process}] ({progress_pct}%) "
                                    f"Sold {available} {currency} to USD"
                                )
                                await asyncio.sleep(0.2)
                            else:
                                raise direct_error
                    else:
                        # Try USD pair first, fallback to BTC
                        product_id = f"{currency}-USD"
                        try:
                            await exchange.create_market_order(
                                product_id=product_id,
                                side="SELL",
                                size=str(available),
                            )
                            sold_count += 1
                            progress_pct = int((idx / total_to_process) * 100)
                            logger.info(
                                f"✅ [{idx}/{total_to_process}] ({progress_pct}%) "
                                f"Sold {available} {currency} to USD directly"
                            )
                            await asyncio.sleep(0.2)
                        except Exception as direct_error:
                            if "403" in str(direct_error) or "400" in str(direct_error):
                                btc_product_id = f"{currency}-BTC"
                                await exchange.create_market_order(
                                    product_id=btc_product_id,
                                    side="SELL",
                                    size=str(available),
                                )
                                converted_via_btc.append(currency)
                                sold_count += 1
                                progress_pct = int((idx / total_to_process) * 100)
                                logger.info(
                                    f"✅ [{idx}/{total_to_process}] ({progress_pct}%) "
                                    f"Sold {available} {currency} to BTC"
                                )
                                await asyncio.sleep(0.2)
                            else:
                                raise direct_error

                except Exception as e:
                    failed_count += 1
                    progress_pct = int((idx / total_to_process) * 100)
                    error_msg = f"{currency} ({available:.8f}): {str(e)}"
                    errors.append(error_msg)
                    logger.error(f"❌ [{idx}/{total_to_process}] ({progress_pct}%) Failed to sell {currency}: {e}")

                # Update progress after each currency
                pcs.update_task_progress(
                    task_id,
                    current=idx,
                    sold_count=sold_count,
                    failed_count=failed_count,
                    errors=errors,
                    message=f"Processing {idx}/{total_to_process} currencies..."
                )

            # Step 2: Convert intermediate currency
            if target_currency == "BTC" and converted_via_usd:
                pcs.update_task_progress(task_id, message="Converting USD to BTC...")
                logger.info(f"🔄 Task {task_id}: Converting accumulated USD to BTC")
                await asyncio.sleep(1.0)

                try:
                    accounts = await exchange.get_accounts(force_fresh=True)
                    usd_account = next((acc for acc in accounts if acc.get("currency") == "USD"), None)
                    if usd_account:
                        usd_available = float(usd_account.get("available_balance", {}).get("value", "0"))
                        if usd_available > 1.0:
                            await exchange.create_market_order(
                                product_id="BTC-USD",
                                side="BUY",
                                funds=str(usd_available),
                            )
                            logger.info(f"✅ Converted ${usd_available} USD to BTC")
                except Exception as e:
                    logger.error(f"Failed to convert USD to BTC: {e}")
                    errors.append(f"USD-to-BTC conversion: {str(e)}")

            if target_currency == "USD" and converted_via_btc:
                pcs.update_task_progress(task_id, message="Converting BTC to USD...")
                logger.info(f"🔄 Task {task_id}: Converting accumulated BTC to USD")
                await asyncio.sleep(1.0)

                try:
                    accounts = await exchange.get_accounts(force_fresh=True)
                    btc_account = next((acc for acc in accounts if acc.get("currency") == "BTC"), None)
                    if btc_account:
                        btc_available = float(btc_account.get("available_balance", {}).get("value", "0"))
                        if btc_available > 0.00001:
                            await exchange.create_market_order(
                                product_id="BTC-USD",
                                side="SELL",
                                size=str(btc_available),
                            )
                            logger.info(f"✅ Converted {btc_available} BTC to USD")
                except Exception as e:
                    logger.error(f"Failed to convert BTC to USD: {e}")
                    errors.append(f"BTC-to-USD conversion: {str(e)}")

            # Mark as completed
            success_rate = f"{int((sold_count / total_to_process) * 100)}%" if total_to_process > 0 else "0%"
            pcs.update_task_progress(
                task_id,
                status="completed",
                message=f"Conversion complete: {sold_count}/{total_to_process} sold ({success_rate})",
                sold_count=sold_count,
                failed_count=failed_count,
                errors=errors
            )

            logger.warning(
                f"🚨 Task {task_id}: PORTFOLIO CONVERSION completed: "
                f"{sold_count}/{total_to_process} sold, {failed_count} failed"
            )
            break  # Exit the async for loop

    except Exception as e:
        logger.error(f"Task {task_id} failed with error: {e}")
        pcs.update_task_progress(
            task_id,
            status="failed",
            message=f"Conversion failed: {str(e)}"
        )


@router.post("/sell-portfolio-to-base")
async def sell_portfolio_to_base_currency(
    background_tasks: BackgroundTasks,
    target_currency: str = Query("BTC", description="Target currency: BTC or USD"),
    confirm: bool = Query(False, description="Must be true to execute"),
    account_id: Optional[int] = Query(None, description="Account ID to convert (defaults to default account)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Start portfolio conversion to BTC or USD (runs in background).

    Returns immediately with a task_id to check progress via /conversion-status/{task_id}
    """
    if not confirm:
        raise HTTPException(status_code=400, detail="Must confirm with confirm=true")

    if target_currency not in ["BTC", "USD"]:
        raise HTTPException(status_code=400, detail="target_currency must be BTC or USD")

    # Get the specified account or user's default account
    if account_id:
        account_query = select(Account).where(
            Account.id == account_id,
            Account.user_id == current_user.id
        )
    else:
        account_query = select(Account).where(
            Account.user_id == current_user.id,
            Account.is_default.is_(True)
        )
    account_result = await db.execute(account_query)
    account = account_result.scalars().first()

    if not account:
        if account_id:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
        else:
            raise HTTPException(status_code=404, detail="No default account found")

    # Generate task ID and start background task
    task_id = str(uuid.uuid4())

    # Start the conversion in the background
    background_tasks.add_task(
        _run_portfolio_conversion,
        task_id=task_id,
        account_id=account.id,
        target_currency=target_currency,
        user_id=current_user.id
    )

    return {
        "task_id": task_id,
        "message": f"Portfolio conversion to {target_currency} started",
        "status_url": f"/api/account/conversion-status/{task_id}"
    }
