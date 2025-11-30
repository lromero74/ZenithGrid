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

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coinbase_unified_client import CoinbaseClient
from app.database import get_db
from app.models import Bot, Position

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account", tags=["account"])


# Dependency - will be injected from main.py
def get_coinbase() -> CoinbaseClient:
    """Get coinbase client - will be overridden in main.py"""
    raise NotImplementedError("Must override coinbase dependency")


@router.get("/balances")
async def get_balances(coinbase: CoinbaseClient = Depends(get_coinbase)):
    """Get current account balances"""
    try:
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
async def get_aggregate_value(coinbase: CoinbaseClient = Depends(get_coinbase)):
    """Get aggregate portfolio value (BTC + USD) for bot budgeting"""
    try:
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
async def get_portfolio(db: AsyncSession = Depends(get_db), coinbase: CoinbaseClient = Depends(get_coinbase)):
    """Get full portfolio breakdown (all coins like 3Commas)"""
    try:
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

        # Fetch all prices with rate limiting to avoid 429 errors
        async def fetch_price(asset: str, delay: float = 0):
            try:
                # Add small delay to avoid rate limiting
                if delay > 0:
                    await asyncio.sleep(delay)
                price = await coinbase.get_current_price(f"{asset}-USD")
                return (asset, price)
            except Exception as e:
                print(f"Could not get USD price for {asset}, skipping: {e}")
                return (asset, None)

        # Fetch prices with staggered delays (every 0.1 seconds) to avoid rate limits
        price_results = await asyncio.gather(
            *[fetch_price(asset, idx * 0.1) for idx, (asset, _, _) in enumerate(assets_to_price)]
        )

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
