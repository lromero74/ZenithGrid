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

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.coinbase_unified_client import CoinbaseClient
from app.database import get_db
from app.models import Bot, Position, Account, User, PendingOrder
from app.exchange_clients.factory import create_exchange_client
from app.routers.auth_dependencies import get_current_user_optional
from app.services import portfolio_conversion_service as pcs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account", tags=["account"])


async def calculate_available_balance(
    currency: str,
    db: AsyncSession,
    coinbase: CoinbaseClient
) -> float:
    """
    Calculate truly available balance for a specific currency.

    This subtracts capital reserved in:
    1. Open positions (total_quote_spent)
    2. Pending orders (reserved_amount_quote/base)

    Args:
        currency: Currency code (BTC, ETH, USD, USDC, USDT)
        db: Database session
        coinbase: Coinbase client instance

    Returns:
        Available balance (can be used for new bots)
    """
    # Get account balance from exchange
    if currency == "BTC":
        account_balance = await coinbase.get_btc_balance()
    elif currency == "ETH":
        account_balance = await coinbase.get_eth_balance()
    elif currency == "USD":
        account_balance = await coinbase.get_usd_balance()
    elif currency == "USDC":
        account_balance = await coinbase.get_usdc_balance()
    elif currency == "USDT":
        account_balance = await coinbase.get_usdt_balance()
    else:
        raise ValueError(f"Unsupported currency: {currency}")

    # Calculate reserved in open positions
    positions_result = await db.execute(
        select(Position).where(
            Position.status == "open",
            Position.product_id.like(f"%-{currency}")
        )
    )
    open_positions = positions_result.scalars().all()
    reserved_in_positions = sum(pos.total_quote_spent or 0 for pos in open_positions)

    # Calculate reserved in pending orders
    # For quote currency (buy orders)
    pending_quote_result = await db.execute(
        select(PendingOrder).where(
            PendingOrder.status == "pending",
            PendingOrder.side == "BUY",
            PendingOrder.product_id.like(f"%-{currency}")
        )
    )
    pending_quote_orders = pending_quote_result.scalars().all()
    reserved_quote = sum(order.reserved_amount_quote or 0 for order in pending_quote_orders)

    # For base currency (sell orders)
    pending_base_result = await db.execute(
        select(PendingOrder).where(
            PendingOrder.status == "pending",
            PendingOrder.side == "SELL",
            PendingOrder.product_id.like(f"{currency}-%")
        )
    )
    pending_base_orders = pending_base_result.scalars().all()
    reserved_base = sum(order.reserved_amount_base or 0 for order in pending_base_orders)

    # Calculate available
    available = account_balance - reserved_in_positions - reserved_quote - reserved_base

    # Ensure non-negative
    return max(0, available)


async def get_coinbase_from_db(db: AsyncSession) -> CoinbaseClient:
    """
    Get Coinbase client from the first active CEX account in the database.
    Excludes paper trading accounts.

    TODO: Once authentication is wired up, this should get the exchange
    client for the currently logged-in user's account.
    """
    # Get first active CEX account (excluding paper trading)
    result = await db.execute(
        select(Account).where(
            Account.type == "cex",
            Account.is_active.is_(True),
            Account.is_paper_trading.is_not(True)  # Exclude paper trading accounts
        ).order_by(Account.is_default.desc(), Account.created_at).limit(1)
    )
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

    # Create and return the client
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


@router.get("/balances")
async def get_balances(
    account_id: Optional[int] = Query(None, description="Account ID (defaults to first active CEX account)"),
    db: AsyncSession = Depends(get_db)
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

        # Get account (either specified or default)
        if account_id:
            account_result = await db.execute(
                select(Account).where(Account.id == account_id)
            )
            account = account_result.scalar_one_or_none()
            if not account:
                raise HTTPException(status_code=404, detail="Account not found")
        else:
            # Get first active CEX account (backwards compatibility)
            account_result = await db.execute(
                select(Account).where(
                    Account.type == "cex",
                    Account.is_active == True
                ).order_by(Account.is_default.desc(), Account.created_at)
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

            # Still need real prices for calculations
            coinbase = await get_coinbase_from_db(db)
            current_price = await coinbase.get_current_price()
            btc_usd_price = await coinbase.get_btc_usd_price()
        else:
            # Live account - fetch from Coinbase
            coinbase = await get_coinbase_from_db(db)

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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/aggregate-value")
async def get_aggregate_value(db: AsyncSession = Depends(get_db)):
    """Get aggregate portfolio value (BTC + USD) for bot budgeting"""
    try:
        coinbase = await get_coinbase_from_db(db)
        aggregate_btc = await coinbase.calculate_aggregate_btc_value()
        aggregate_usd = await coinbase.calculate_aggregate_usd_value()
        btc_usd_price = await coinbase.get_btc_usd_price()

        return {
            "aggregate_btc_value": aggregate_btc,
            "aggregate_usd_value": aggregate_usd,
            "btc_usd_price": btc_usd_price,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio")
async def get_portfolio(db: AsyncSession = Depends(get_db)):
    """Get full portfolio breakdown (all coins like 3Commas)"""
    try:
        coinbase = await get_coinbase_from_db(db)
        # Get portfolio breakdown with all holdings
        breakdown = await coinbase.get_portfolio_breakdown()
        spot_positions = breakdown.get("spot_positions", [])

        # Log raw position count for debugging
        logger.info(f"Portfolio API returned {len(spot_positions)} spot positions")

        # Get BTC/USD price for valuations
        btc_usd_price = await coinbase.get_btc_usd_price()

        # Prepare list of assets that need pricing
        assets_to_price = []
        for position in spot_positions:
            asset = position.get("asset", "")
            total_balance = float(position.get("total_balance_crypto", 0))

            # Skip if zero balance
            if total_balance == 0:
                continue

            # Skip stablecoins and BTC (we already have prices for these)
            if asset not in ["USD", "USDC", "BTC"]:
                assets_to_price.append((asset, total_balance, position))

        # Fetch all prices in batches to balance speed vs rate limiting
        async def fetch_price(asset: str):
            try:
                price = await coinbase.get_current_price(f"{asset}-USD")
                return (asset, price)
            except Exception as e:
                # 404 errors are expected for delisted pairs - log at DEBUG level
                # Other errors (rate limits, network issues, etc.) are WARNING level
                error_str = str(e)
                if "404" in error_str or "Not Found" in error_str:
                    logger.debug(f"Could not get USD price for {asset}: {e}")
                else:
                    logger.warning(f"Could not get USD price for {asset}: {e}")
                return (asset, None)

        # Batch price fetching: 15 concurrent requests, then 0.2s delay, repeat
        # This is much faster than 0.1s delay per coin while still avoiding rate limits
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

        # Create price lookup dict
        prices = {asset: price for asset, price in price_results if price is not None}

        # Now build portfolio with all prices available
        portfolio_holdings = []
        total_usd_value = 0.0
        total_btc_value = 0.0

        # Track actual USD, USDC, and BTC balances separately (for balance breakdown)
        actual_usd_balance = 0.0  # USD only
        actual_usdc_balance = 0.0  # USDC only
        actual_btc_balance = 0.0  # BTC only

        for position in spot_positions:
            asset = position.get("asset", "")
            total_balance = float(position.get("total_balance_crypto", 0))
            available = float(position.get("available_to_trade_crypto", 0))
            hold = total_balance - available

            # Skip if zero balance
            if total_balance == 0:
                continue

            # Get USD value for this asset
            usd_value = 0.0
            btc_value = 0.0
            current_price_usd = 0.0

            if asset == "USD":
                usd_value = total_balance
                btc_value = total_balance / btc_usd_price if btc_usd_price > 0 else 0
                current_price_usd = 1.0
                # Track actual USD balance
                actual_usd_balance += total_balance
            elif asset == "USDC":
                usd_value = total_balance
                btc_value = total_balance / btc_usd_price if btc_usd_price > 0 else 0
                current_price_usd = 1.0
                # Track actual USDC balance
                actual_usdc_balance += total_balance
            elif asset == "BTC":
                usd_value = total_balance * btc_usd_price
                btc_value = total_balance
                current_price_usd = btc_usd_price
                # Track actual BTC balance
                actual_btc_balance += total_balance
            else:
                # Use price from parallel fetch
                if asset in prices:
                    current_price_usd = prices[asset]
                    usd_value = total_balance * current_price_usd
                    # Calculate BTC value from USD value
                    btc_value = usd_value / btc_usd_price if btc_usd_price > 0 else 0
                else:
                    # Still include asset even if we couldn't get price
                    # Log at DEBUG level (detailed error already logged in fetch_price)
                    logger.debug(f"Could not get USD price for {asset}, including with $0 value")
                    current_price_usd = 0.0
                    usd_value = 0.0
                    btc_value = 0.0

            # Skip assets worth less than $0.01 USD, UNLESS we couldn't get price (they might be valuable)
            if usd_value < 0.01 and current_price_usd > 0:
                continue

            total_usd_value += usd_value
            total_btc_value += btc_value

            portfolio_holdings.append(
                {
                    "asset": asset,
                    "total_balance": total_balance,
                    "available": available,
                    "hold": hold,
                    "current_price_usd": current_price_usd,
                    "usd_value": usd_value,
                    "btc_value": btc_value,
                    "percentage": 0.0,  # Will calculate after we know total
                    "unrealized_pnl_usd": 0.0,  # Will calculate from open positions
                    "unrealized_pnl_percentage": 0.0,
                }
            )

        # Calculate percentages
        for holding in portfolio_holdings:
            if total_usd_value > 0:
                holding["percentage"] = (holding["usd_value"] / total_usd_value) * 100

        # Calculate unrealized PnL from open positions
        # Get all open positions
        positions_query = select(Position).where(Position.status == "open")
        positions_result = await db.execute(positions_query)
        open_positions_for_pnl = positions_result.scalars().all()

        # Track PnL by base asset
        asset_pnl = {}  # {asset: {"pnl_usd": X, "cost_usd": Y}}

        for position in open_positions_for_pnl:
            base = position.get_base_currency()
            quote = position.get_quote_currency()

            try:
                # Get current price
                current_price = await coinbase.get_current_price(f"{base}-{quote}")
                current_value_quote = position.total_base_acquired * current_price

                # Calculate profit in quote currency
                profit_quote = current_value_quote - position.total_quote_spent

                # Convert to USD
                if quote == "USD":
                    profit_usd = profit_quote
                    cost_usd = position.total_quote_spent
                elif quote == "BTC":
                    profit_usd = profit_quote * btc_usd_price
                    cost_usd = position.total_quote_spent * btc_usd_price
                else:
                    continue  # Skip unknown quote currencies

                # Accumulate PnL by base asset
                if base not in asset_pnl:
                    asset_pnl[base] = {"pnl_usd": 0.0, "cost_usd": 0.0}

                asset_pnl[base]["pnl_usd"] += profit_usd
                asset_pnl[base]["cost_usd"] += cost_usd

            except Exception as e:
                logger.warning(f"Could not calculate PnL for position {position.id}: {e}")
                continue

        # Add PnL to holdings
        for holding in portfolio_holdings:
            asset = holding["asset"]
            if asset in asset_pnl:
                pnl_data = asset_pnl[asset]
                holding["unrealized_pnl_usd"] = pnl_data["pnl_usd"]

                # Calculate percentage if cost > 0
                if pnl_data["cost_usd"] > 0:
                    holding["unrealized_pnl_percentage"] = (pnl_data["pnl_usd"] / pnl_data["cost_usd"]) * 100

        # Sort by USD value descending
        portfolio_holdings.sort(key=lambda x: x["usd_value"], reverse=True)

        # Calculate free (unreserved) balances for BTC and USD
        # Free = Total Portfolio - (Bot Reservations + Open Position Balances)

        # Get all bots and sum their reservations
        bots_query = select(Bot)
        bots_result = await db.execute(bots_query)
        all_bots = bots_result.scalars().all()

        total_reserved_btc = sum(bot.reserved_btc_balance for bot in all_bots)
        total_reserved_usd = sum(bot.reserved_usd_balance for bot in all_bots)

        # Get all open positions and calculate their current values
        positions_query = select(Position).where(Position.status == "open")
        positions_result = await db.execute(positions_query)
        open_positions = positions_result.scalars().all()

        total_in_positions_btc = 0.0
        total_in_positions_usd = 0.0
        total_in_positions_usdc = 0.0

        for position in open_positions:
            quote = position.get_quote_currency()
            base = position.get_base_currency()

            # Get current price for the position
            try:
                current_price = await coinbase.get_current_price(f"{base}-{quote}")
                current_value = position.total_base_acquired * current_price

                if quote == "USD":
                    total_in_positions_usd += current_value
                elif quote == "USDC":
                    total_in_positions_usdc += current_value
                else:  # BTC
                    total_in_positions_btc += current_value
            except Exception as e:
                # Fallback to quote spent if can't get current price
                print(f"Could not get current price for {base}-{quote}, using quote spent: {e}")
                if quote == "USD":
                    total_in_positions_usd += position.total_quote_spent
                elif quote == "USDC":
                    total_in_positions_usdc += position.total_quote_spent
                else:
                    total_in_positions_btc += position.total_quote_spent

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

        # Calculate realized PnL from closed positions
        # All-time PnL
        closed_positions_query = select(Position).where(Position.status == "closed")
        closed_positions_result = await db.execute(closed_positions_query)
        closed_positions = closed_positions_result.scalars().all()

        pnl_all_time_usd = 0.0
        pnl_all_time_btc = 0.0
        pnl_all_time_usdc = 0.0
        pnl_today_usd = 0.0
        pnl_today_btc = 0.0
        pnl_today_usdc = 0.0

        today = datetime.utcnow().date()

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
                if position.closed_at and position.closed_at.date() == today:
                    if quote == "USD":
                        pnl_today_usd += position.profit_quote
                    elif quote == "USDC":
                        pnl_today_usdc += position.profit_quote
                    else:  # BTC
                        pnl_today_btc += position.profit_quote

        # Log portfolio summary for debugging inconsistent results
        logger.info(f"Portfolio summary: {len(spot_positions)} raw positions -> {len(portfolio_holdings)} after filtering (${total_usd_value:.2f} total)")

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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversion-status/{task_id}")
async def get_conversion_status(task_id: str):
    """
    Get status of a portfolio conversion task
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
            from app.services.exchange_service import get_exchange_client_for_account
            exchange = await get_exchange_client_for_account(db, account_id)

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
                            result = await exchange.create_market_order(
                                product_id=product_id,
                                side="SELL",
                                size=str(available),
                            )
                            sold_count += 1
                            progress_pct = int((idx / total_to_process) * 100)
                            logger.info(f"✅ [{idx}/{total_to_process}] ({progress_pct}%) Sold {available} {currency} to BTC directly")
                            await asyncio.sleep(0.2)
                        except Exception as direct_error:
                            if "403" in str(direct_error) or "400" in str(direct_error):
                                usd_product_id = f"{currency}-USD"
                                sell_result = await exchange.create_market_order(
                                    product_id=usd_product_id,
                                    side="SELL",
                                    size=str(available),
                                )
                                converted_via_usd.append(currency)
                                sold_count += 1
                                progress_pct = int((idx / total_to_process) * 100)
                                logger.info(f"✅ [{idx}/{total_to_process}] ({progress_pct}%) Sold {available} {currency} to USD")
                                await asyncio.sleep(0.2)
                            else:
                                raise direct_error
                    else:
                        # Try USD pair first, fallback to BTC
                        product_id = f"{currency}-USD"
                        try:
                            result = await exchange.create_market_order(
                                product_id=product_id,
                                side="SELL",
                                size=str(available),
                            )
                            sold_count += 1
                            progress_pct = int((idx / total_to_process) * 100)
                            logger.info(f"✅ [{idx}/{total_to_process}] ({progress_pct}%) Sold {available} {currency} to USD directly")
                            await asyncio.sleep(0.2)
                        except Exception as direct_error:
                            if "403" in str(direct_error) or "400" in str(direct_error):
                                btc_product_id = f"{currency}-BTC"
                                sell_result = await exchange.create_market_order(
                                    product_id=btc_product_id,
                                    side="SELL",
                                    size=str(available),
                                )
                                converted_via_btc.append(currency)
                                sold_count += 1
                                progress_pct = int((idx / total_to_process) * 100)
                                logger.info(f"✅ [{idx}/{total_to_process}] ({progress_pct}%) Sold {available} {currency} to BTC")
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
                            btc_result = await exchange.create_market_order(
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
                            usd_result = await exchange.create_market_order(
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

            logger.warning(f"🚨 Task {task_id}: PORTFOLIO CONVERSION completed: {sold_count}/{total_to_process} sold, {failed_count} failed")
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
    current_user: Optional[User] = Depends(get_current_user_optional)
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
            Account.is_default == True
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
