"""
Account and portfolio API routes

Handles account-related endpoints:
- Account balances (BTC, ETH, totals)
- Aggregate portfolio value calculations
- Full portfolio breakdown (3Commas-style)
"""

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.coinbase_unified_client import CoinbaseClient
from app.database import get_db
from app.models import Bot, Position, Account, User
from app.exchange_clients.factory import create_exchange_client
from app.routers.auth_dependencies import get_current_user_optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account", tags=["account"])


async def get_coinbase_from_db(db: AsyncSession) -> CoinbaseClient:
    """
    Get Coinbase client from the first active CEX account in the database.

    TODO: Once authentication is wired up, this should get the exchange
    client for the currently logged-in user's account.
    """
    # Get first active CEX account
    result = await db.execute(
        select(Account).where(
            Account.type == "cex",
            Account.is_active.is_(True)
        ).order_by(Account.is_default.desc(), Account.created_at)
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
async def get_balances(db: AsyncSession = Depends(get_db)):
    """Get current account balances"""
    try:
        coinbase = await get_coinbase_from_db(db)
        btc_balance = await coinbase.get_btc_balance()
        eth_balance = await coinbase.get_eth_balance()
        current_price = await coinbase.get_current_price()
        btc_usd_price = await coinbase.get_btc_usd_price()

        total_btc_value = btc_balance + (eth_balance * current_price)

        return {
            "btc": btc_balance,
            "eth": eth_balance,
            "eth_value_in_btc": eth_balance * current_price,
            "total_btc_value": total_btc_value,
            "current_eth_btc_price": current_price,
            "btc_usd_price": btc_usd_price,
            "total_usd_value": total_btc_value * btc_usd_price,
        }
    except Exception as e:
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
                    # Log this for debugging
                    logger.warning(f"Could not get USD price for {asset}, including with $0 value")
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


@router.post("/sell-portfolio-to-base")
async def sell_portfolio_to_base_currency(
    target_currency: str = Query("BTC", description="Target currency: BTC or USD"),
    confirm: bool = Query(False, description="Must be true to execute"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Sell entire portfolio to BTC or USD.

    This sells actual account balances (ETH, ADA, etc.), NOT positions/deals.
    Use this to consolidate your portfolio into a single base currency.
    """
    if not confirm:
        raise HTTPException(status_code=400, detail="Must confirm with confirm=true")

    if target_currency not in ["BTC", "USD"]:
        raise HTTPException(status_code=400, detail="target_currency must be BTC or USD")

    # Get user's default account (or iterate through all accounts)
    account_query = select(Account).where(
        Account.user_id == current_user.id,
        Account.is_default == True
    )
    account_result = await db.execute(account_query)
    account = account_result.scalars().first()

    if not account:
        raise HTTPException(status_code=404, detail="No default account found")

    # Get exchange client for this account
    from app.services.exchange_service import get_exchange_client_for_account

    exchange = await get_exchange_client_for_account(db, account.id)

    # Get all account balances from Coinbase
    try:
        all_accounts = await exchange.get_accounts(force_fresh=True)
    except Exception as e:
        logger.error(f"Failed to fetch accounts from Coinbase: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to fetch account balances from Coinbase: {str(e)}"
        )

    # Filter to currencies we want to sell (exclude target currency)
    # Only sell currencies with available balance > minimum threshold
    currencies_to_sell = []
    for acc in all_accounts:
        currency = acc.get("currency")
        available_str = acc.get("available_balance", {}).get("value", "0")
        available = float(available_str)

        # Skip target currency, skip zero balances
        if currency == target_currency or available <= 0:
            continue

        # Skip if balance is below exchange minimum (0.0001 for BTC pairs)
        # For simplicity, use a threshold based on USD value or BTC value
        currencies_to_sell.append({
            "currency": currency,
            "available": available,
        })

    if not currencies_to_sell:
        return {
            "message": f"Portfolio already in {target_currency} (no other currencies to sell)",
            "sold_count": 0,
            "failed_count": 0,
            "errors": []
        }

    # Sell each currency to target
    sold_count = 0
    failed_count = 0
    errors = []
    converted_via_usd = []  # Track currencies that were sold to USD (for BTC conversion later)

    for item in currencies_to_sell:
        currency = item["currency"]
        available = item["available"]

        try:
            # For BTC target: Try direct pair first, fall back to USD route if needed
            if target_currency == "BTC":
                product_id = f"{currency}-BTC"
                try:
                    # Try direct CURRENCY-BTC trade
                    result = await exchange.create_market_order(
                        product_id=product_id,
                        side="SELL",
                        size=str(available),
                    )
                    sold_count += 1
                    logger.info(f"Sold {available} {currency} to BTC directly: {result.get('order_id')}")
                    await asyncio.sleep(0.2)  # Rate limit delay
                except Exception as direct_error:
                    # If direct BTC pair fails (likely 403 = pair doesn't exist), try USD route
                    if "403" in str(direct_error) or "400" in str(direct_error):
                        # Sell to USD first (we'll convert all USD to BTC at the end)
                        usd_product_id = f"{currency}-USD"
                        sell_result = await exchange.create_market_order(
                            product_id=usd_product_id,
                            side="SELL",
                            size=str(available),
                        )
                        logger.info(f"Sold {available} {currency} to USD (will convert to BTC later): {sell_result.get('order_id')}")
                        converted_via_usd.append(currency)
                        sold_count += 1
                        await asyncio.sleep(0.2)  # Rate limit delay
                    else:
                        raise direct_error
            else:
                # For USD target: Direct conversion
                product_id = f"{currency}-{target_currency}"
                result = await exchange.create_market_order(
                    product_id=product_id,
                    side="SELL",
                    size=str(available),
                )
                sold_count += 1
                logger.info(f"Sold {available} {currency} to {target_currency}: {result.get('order_id')}")

            # Small delay to avoid hitting Coinbase rate limits
            await asyncio.sleep(0.2)

        except Exception as e:
            failed_count += 1
            error_msg = f"{currency} ({available:.8f}): {str(e)}"
            errors.append(error_msg)
            logger.error(f"Failed to sell {currency}: {e}")

    # If converting to BTC and we sold currencies to USD, now convert all USD to BTC
    if target_currency == "BTC" and converted_via_usd:
        try:
            # Wait a moment for orders to settle
            await asyncio.sleep(1.0)

            # Refresh account to get current USD balance
            accounts = await exchange.get_accounts(force_fresh=True)
            usd_account = next((acc for acc in accounts if acc.get("currency") == "USD"), None)
            if usd_account:
                usd_available = float(usd_account.get("available_balance", {}).get("value", "0"))
                if usd_available > 1.0:  # Only convert if we have at least $1
                    # Buy BTC with all available USD
                    btc_result = await exchange.create_market_order(
                        product_id="BTC-USD",
                        side="BUY",
                        funds=str(usd_available),
                    )
                    logger.info(f"✅ Converted ${usd_available} USD to BTC: {btc_result.get('order_id')}")
                else:
                    logger.warning(f"USD balance too small to convert to BTC: ${usd_available}")
        except Exception as e:
            logger.error(f"Failed to convert USD to BTC: {e}")
            errors.append(f"USD-to-BTC conversion: {str(e)}")

    logger.warning(
        f"🚨 PORTFOLIO CONVERSION to {target_currency} by user {current_user.id}: "
        f"{sold_count} currencies sold, {failed_count} failed"
    )

    return {
        "message": f"Portfolio conversion complete: {sold_count} currencies sold to {target_currency}",
        "sold_count": sold_count,
        "failed_count": failed_count,
        "errors": errors
    }
