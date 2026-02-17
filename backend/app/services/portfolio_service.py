"""
Portfolio Service

Provides portfolio calculation functions for CEX and DEX accounts.
Extracted from routers/accounts/portfolio_utils.py to live at the proper
service layer.
"""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import api_cache
from app.models import Account, Bot, Position
from app.services.dex_wallet_service import dex_wallet_service

logger = logging.getLogger(__name__)


async def get_cex_portfolio(
    account: Account,
    db: AsyncSession,
    get_coinbase_for_account_func,
) -> dict:
    """
    Get portfolio for a CEX (Coinbase) account.

    Args:
        account: The CEX account to get portfolio for
        db: Database session
        get_coinbase_for_account_func: Function to create a Coinbase client for an account

    Returns:
        Dict with portfolio data including holdings, balances, and PnL
    """
    # Check response cache first (60s TTL) to avoid slow re-computation
    cache_key = f"portfolio_response_{account.id}"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        logger.debug(f"Using cached portfolio response for account {account.id}")
        return cached

    coinbase = await get_coinbase_for_account_func(account)

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
            # 404 errors are expected for delisted pairs - log at DEBUG level
            # Other errors (rate limits, network issues, etc.) are WARNING level
            error_str = str(e)
            if "404" in error_str or "Not Found" in error_str:
                logger.debug(f"Could not get USD price for {asset}: {e}")
            else:
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

    # Get PnL from positions for this account (strictly scoped)
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
        unique_products = list(
            {f"{p.get_base_currency()}-{p.get_quote_currency()}" for p in open_positions}
        )

        # Batch price fetching for positions: 15 concurrent, then 0.2s delay
        position_price_results = []
        for i in range(0, len(unique_products), batch_size):
            batch = unique_products[i:i + batch_size]
            batch_results = await asyncio.gather(
                *[fetch_price_for_product(pid) for pid in batch]
            )
            position_price_results.extend(batch_results)
            if i + batch_size < len(unique_products):
                await asyncio.sleep(0.2)

        position_prices = {
            pid: price for pid, price in position_price_results if price is not None
        }

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
                holding["unrealized_pnl_percentage"] = (
                    pnl_data["pnl_usd"] / pnl_data["cost_usd"]
                ) * 100

    portfolio_holdings.sort(key=lambda x: x["usd_value"], reverse=True)

    # Get balance breakdown for this account's bots (strictly scoped)
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

    # Calculate PnL (strictly scoped to this account)
    closed_positions_query = select(Position).where(
        Position.status == "closed",
        Position.account_id == account.id
    )
    closed_positions_result = await db.execute(closed_positions_query)
    closed_positions = closed_positions_result.scalars().all()

    pnl_all_time = {"usd": 0.0, "btc": 0.0, "usdc": 0.0}
    pnl_today = {"usd": 0.0, "btc": 0.0, "usdc": 0.0}
    now = datetime.utcnow()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    for position in closed_positions:
        if position.profit_quote is not None:
            quote = position.get_quote_currency()
            quote_key = quote.lower() if quote in ["USD", "BTC", "USDC"] else "usd"

            pnl_all_time[quote_key] += position.profit_quote

            if position.closed_at and position.closed_at >= start_of_today:
                pnl_today[quote_key] += position.profit_quote

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

    # Cache the response for 60s
    await api_cache.set(cache_key, result, 60)
    return result


async def get_dex_portfolio(
    account: Account,
    db: AsyncSession,
    get_coinbase_for_account_func,
) -> dict:
    """
    Get portfolio for a DEX (wallet) account.

    Args:
        account: The DEX account to get portfolio for
        db: Database session
        get_coinbase_for_account_func: Function to create a Coinbase client for an account

    Returns:
        Dict with portfolio data including holdings and balances
    """
    # Get ETH/USD price for valuations (from same user's CEX account or fallback)
    try:
        # Find a CEX account belonging to the same user for price data
        cex_result = await db.execute(
            select(Account).where(
                Account.user_id == account.user_id,
                Account.type == "cex",
                Account.is_active.is_(True)
            ).order_by(Account.is_default.desc(), Account.created_at)
            .limit(1)
        )
        cex_account = cex_result.scalar_one_or_none()

        if cex_account and cex_account.api_key_name and cex_account.api_private_key:
            coinbase = await get_coinbase_for_account_func(cex_account)
            eth_usd_price = await coinbase.get_current_price("ETH-USD")
            btc_usd_price = await coinbase.get_btc_usd_price()
        else:
            raise ValueError("No CEX account available for price data")
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
