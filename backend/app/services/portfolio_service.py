"""
Portfolio Service

Provides portfolio calculation functions for CEX and DEX accounts,
balance retrieval, and portfolio conversion orchestration.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ExchangeUnavailableError, NotFoundError

from app.cache import api_cache, portfolio_cache
from app.coinbase_unified_client import CoinbaseClient
from app.encryption import decrypt_value, is_encrypted
from app.exchange_clients.factory import create_exchange_client, ExchangeClientConfig, CoinbaseCredentials
from app.models import Account, Bot, PendingOrder, Position, User
from app.services.dex_wallet_service import dex_wallet_service
from app.services.exchange_service import get_exchange_client_for_account

logger = logging.getLogger(__name__)


async def get_user_paper_account(db: AsyncSession, user_id: int) -> Optional[Account]:
    """Get user's paper trading account if they have no live CEX account."""
    live_result = await db.execute(
        select(Account).where(
            Account.user_id == user_id,
            Account.type == "cex",
            Account.is_active.is_(True),
            Account.is_paper_trading.is_not(True)
        ).limit(1)
    )
    if live_result.scalar_one_or_none():
        return None

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
        raise ExchangeUnavailableError(
            "No Coinbase account configured. Please add your API credentials in Settings."
        )

    if not account.api_key_name or not account.api_private_key:
        raise ExchangeUnavailableError(
            "Coinbase account missing API credentials. Please update in Settings."
        )

    private_key = account.api_private_key
    if is_encrypted(private_key):
        private_key = decrypt_value(private_key)

    client = create_exchange_client(ExchangeClientConfig(
        exchange_type="cex",
        coinbase=CoinbaseCredentials(
            key_name=account.api_key_name,
            private_key=private_key,
        ),
    ))

    if not client:
        raise ExchangeUnavailableError(
            "Failed to create Coinbase client. Please check your API credentials."
        )

    return client


async def get_cex_portfolio(
    account: Account,
    db: AsyncSession,
    get_coinbase_for_account_func,
    force_fresh: bool = False,
) -> dict:
    """
    Get portfolio for a CEX (Coinbase) account.

    Uses Coinbase's portfolio breakdown which returns USD values for every
    position in a single API call — no individual price fetches needed.
    """
    cache_key = f"portfolio_response_{account.id}"

    if not force_fresh:
        # Check in-memory cache first (60s TTL)
        cached = await api_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Using cached portfolio response for account {account.id}")
            return cached

        # Check persistent cache (survives restarts)
        persistent = await portfolio_cache.get(account.user_id)
        if persistent is not None:
            await api_cache.set(cache_key, persistent, 60)
            logger.info(f"Serving persistent portfolio cache for account {account.id}")
            return persistent

    coinbase = await get_coinbase_for_account_func(account)

    # Single API call: breakdown has USD values for every position
    breakdown = await coinbase.get_portfolio_breakdown()
    spot_positions = breakdown.get("spot_positions", [])

    # Get BTC/USD price for BTC value column (uses cache, very fast)
    btc_usd_price = await coinbase.get_btc_usd_price()

    # Build portfolio directly from breakdown data
    portfolio_holdings = []
    total_usd_value = 0.0
    total_btc_value = 0.0
    actual_usd_balance = 0.0
    actual_usdc_balance = 0.0
    actual_btc_balance = 0.0

    # Price lookup derived from breakdown (for position PnL)
    breakdown_prices = {}

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

    # Get PnL from positions for this account (strictly scoped)
    positions_query = select(Position).where(
        Position.status == "open",
        Position.account_id == account.id
    )
    positions_result = await db.execute(positions_query)
    open_positions = positions_result.scalars().all()

    # Use prices derived from breakdown — no additional API calls
    asset_pnl = {}
    for position in open_positions:
        base = position.get_base_currency()
        quote = position.get_quote_currency()

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

    # Cache in-memory (60s) and persist to disk (survives restarts)
    await api_cache.set(cache_key, result, 60)
    await portfolio_cache.save(account.user_id, result)
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


async def get_generic_cex_portfolio(
    account: Account,
    db: AsyncSession,
) -> dict:
    """
    Build a portfolio view for non-Coinbase CEX accounts (ByBit, MT5).

    Uses the exchange adapter's get_accounts() for balances and
    the database for position-level P&L.
    """
    from app.services.exchange_service import get_exchange_client_for_account

    exchange = await get_exchange_client_for_account(db, account.id)
    if not exchange:
        raise ExchangeUnavailableError(
            "Could not connect to exchange. Check API credentials."
        )

    # Get balances from the exchange
    try:
        coin_accounts = await exchange.get_accounts()
    except Exception as e:
        logger.error(f"Failed to fetch balances for account {account.id}: {e}")
        raise ExchangeUnavailableError(
            "Failed to fetch balances from exchange."
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
            unrealized = equity - total_usd_value
            total_usd_value = equity
            total_btc_value = equity / btc_usd_price if btc_usd_price > 0 else 0
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


async def get_account_balances(
    db: AsyncSession, current_user: User, account_id: int = None,
) -> dict:
    """
    Get account balances with capital reservation tracking.

    Returns balances from exchange, reserved capital in open positions
    and pending orders, and available balance for new bots.
    """
    import json

    if account_id:
        account_result = await db.execute(
            select(Account).where(Account.id == account_id, Account.user_id == current_user.id)
        )
        account = account_result.scalar_one_or_none()
        if not account:
            raise NotFoundError("Account not found")
    else:
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
            raise NotFoundError("No active account found")

    if account.is_paper_trading:
        if account.paper_balances:
            balances = json.loads(account.paper_balances)
        else:
            balances = {"BTC": 0.0, "ETH": 0.0, "USD": 0.0, "USDC": 0.0, "USDT": 0.0}

        btc_balance = balances.get("BTC", 0.0)
        eth_balance = balances.get("ETH", 0.0)
        usd_balance = balances.get("USD", 0.0)
        usdc_balance = balances.get("USDC", 0.0)
        usdt_balance = balances.get("USDT", 0.0)

        from app.coinbase_api.public_market_data import (
            get_btc_usd_price as get_public_btc_price,
            get_current_price as get_public_price,
        )
        current_price = await get_public_price("ETH-BTC")
        btc_usd_price = await get_public_btc_price()
    else:
        coinbase = await get_coinbase_from_db(db, current_user.id)
        btc_balance = await coinbase.get_btc_balance()
        eth_balance = await coinbase.get_eth_balance()
        usd_balance = await coinbase.get_usd_balance()
        usdc_balance = await coinbase.get_usdc_balance()
        usdt_balance = await coinbase.get_usdt_balance()
        current_price = await coinbase.get_current_price()
        btc_usd_price = await coinbase.get_btc_usd_price()

    # Reserved capital in open positions (by quote currency)
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

    # Reserved capital in pending orders
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
        if order.side == "BUY" and order.product_id and "-" in order.product_id:
            quote_currency = order.product_id.split("-")[1]
            if quote_currency in reserved_in_pending_orders and order.reserved_amount_quote:
                reserved_in_pending_orders[quote_currency] += order.reserved_amount_quote
        elif order.side == "SELL" and order.product_id and "-" in order.product_id:
            base_currency = order.product_id.split("-")[0]
            if base_currency in reserved_in_pending_orders and order.reserved_amount_base:
                reserved_in_pending_orders[base_currency] += order.reserved_amount_base

    available_btc = max(0, btc_balance - reserved_in_positions["BTC"] - reserved_in_pending_orders["BTC"])
    available_eth = max(0, eth_balance - reserved_in_positions["ETH"] - reserved_in_pending_orders["ETH"])
    available_usd = max(0, usd_balance - reserved_in_positions["USD"] - reserved_in_pending_orders["USD"])
    available_usdc = max(0, usdc_balance - reserved_in_positions["USDC"] - reserved_in_pending_orders["USDC"])
    available_usdt = max(0, usdt_balance - reserved_in_positions["USDT"] - reserved_in_pending_orders["USDT"])

    total_btc_value = btc_balance + (eth_balance * current_price)
    total_usd_value = (total_btc_value * btc_usd_price) + usd_balance + usdc_balance + usdt_balance

    return {
        "btc": btc_balance, "eth": eth_balance, "usd": usd_balance,
        "usdc": usdc_balance, "usdt": usdt_balance,
        "reserved_in_positions": reserved_in_positions,
        "reserved_in_pending_orders": reserved_in_pending_orders,
        "available_btc": available_btc, "available_eth": available_eth,
        "available_usd": available_usd, "available_usdc": available_usdc,
        "available_usdt": available_usdt,
        "eth_value_in_btc": eth_balance * current_price,
        "total_btc_value": total_btc_value,
        "current_eth_btc_price": current_price,
        "btc_usd_price": btc_usd_price,
        "total_usd_value": total_usd_value,
    }


async def get_account_portfolio_data(
    db: AsyncSession, current_user: User, force_fresh: bool = False,
) -> dict:
    """Get full portfolio breakdown for the current user."""
    # Paper-only users get a simulated portfolio
    paper_account = await get_user_paper_account(db, current_user.id)
    if paper_account:
        client = await get_exchange_client_for_account(db, paper_account.id)
        if client and hasattr(client, 'balances'):
            btc_usd_price = 0.0
            try:
                btc_usd_price = await client.get_btc_usd_price()
            except Exception:
                pass

            altcoin_btc_prices = {}
            for currency in client.balances:
                if currency in ("BTC", "USD", "USDC", "USDT"):
                    continue
                try:
                    price = await client.get_current_price(f"{currency}-BTC")
                    altcoin_btc_prices[currency] = price
                except Exception:
                    altcoin_btc_prices[currency] = 0.0

            assets = []
            for currency, balance in client.balances.items():
                if balance > 0:
                    if currency == "BTC":
                        btc_value = balance
                        usd_value = balance * btc_usd_price
                        price_usd = btc_usd_price
                    elif currency in ("USD", "USDC", "USDT"):
                        btc_value = balance / btc_usd_price if btc_usd_price > 0 else 0.0
                        usd_value = balance
                        price_usd = 1.0
                    else:
                        btc_price = altcoin_btc_prices.get(currency, 0.0)
                        btc_value = balance * btc_price
                        usd_value = btc_value * btc_usd_price
                        price_usd = btc_price * btc_usd_price

                    assets.append({
                        "asset": currency,
                        "total_balance": balance,
                        "available_balance": balance,
                        "hold_balance": 0.0,
                        "usd_value": usd_value,
                        "btc_value": btc_value,
                        "allocation_pct": 0.0,
                        "price_usd": price_usd,
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
        cached = await api_cache.get(cache_key)
        if cached is not None:
            logger.debug("Using cached portfolio response")
            return cached

        persistent = await portfolio_cache.get(current_user.id)
        if persistent is not None:
            await api_cache.set(cache_key, persistent, 60)
            logger.info("Serving persistent portfolio cache while fresh data loads")
            return persistent

    coinbase = await get_coinbase_from_db(db, current_user.id)

    breakdown = await coinbase.get_portfolio_breakdown()
    spot_positions = breakdown.get("spot_positions", [])
    btc_usd_price = await coinbase.get_btc_usd_price()

    portfolio_holdings = []
    total_usd_value = 0.0
    total_btc_value = 0.0
    actual_usd_balance = 0.0
    actual_usdc_balance = 0.0
    actual_btc_balance = 0.0
    breakdown_prices = {}

    for position in spot_positions:
        asset = position.get("asset", "")
        total_balance = float(position.get("total_balance_crypto", 0))
        available = float(position.get("available_to_trade_crypto", 0))
        hold = total_balance - available

        if total_balance == 0:
            continue

        usd_value = float(position.get("total_balance_fiat", 0))

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

        if asset == "USD":
            actual_usd_balance += total_balance
        elif asset == "USDC":
            actual_usdc_balance += total_balance
        elif asset == "BTC":
            actual_btc_balance += total_balance

        if current_price_usd > 0:
            breakdown_prices[asset] = current_price_usd

        btc_value = usd_value / btc_usd_price if btc_usd_price > 0 else 0

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

    for holding in portfolio_holdings:
        if total_usd_value > 0:
            holding["percentage"] = (holding["usd_value"] / total_usd_value) * 100

    # Unrealized PnL from open positions
    user_accounts_q = select(Account.id).where(Account.user_id == current_user.id)
    user_accounts_r = await db.execute(user_accounts_q)
    user_account_ids = [row[0] for row in user_accounts_r.fetchall()]

    positions_query = select(Position).where(
        Position.status == "open",
        Position.account_id.in_(user_account_ids) if user_account_ids else Position.id < 0,
    )
    positions_result = await db.execute(positions_query)
    open_positions = positions_result.scalars().all()

    asset_pnl = {}
    for position in open_positions:
        base = position.get_base_currency()
        quote = position.get_quote_currency()

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

    # Balance breakdown
    bots_query = select(Bot).where(
        Bot.account_id.in_(user_account_ids) if user_account_ids else Bot.id < 0,
    )
    bots_result = await db.execute(bots_query)
    all_bots = bots_result.scalars().all()

    total_reserved_btc = sum(bot.reserved_btc_balance for bot in all_bots)
    total_reserved_usd = sum(bot.reserved_usd_balance for bot in all_bots)

    total_in_positions_btc = 0.0
    total_in_positions_usd = 0.0
    total_in_positions_usdc = 0.0

    for position in open_positions:
        quote = position.get_quote_currency()
        base = position.get_base_currency()

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
        else:
            total_in_positions_btc += current_value

    total_btc_portfolio = actual_btc_balance + total_in_positions_btc
    total_usd_portfolio = actual_usd_balance + total_in_positions_usd
    total_usdc_portfolio = actual_usdc_balance + total_in_positions_usdc

    total_reserved_usdc = 0.0
    free_btc = max(0.0, total_btc_portfolio - (total_reserved_btc + total_in_positions_btc))
    free_usd = max(0.0, total_usd_portfolio - (total_reserved_usd + total_in_positions_usd))
    free_usdc = max(0.0, total_usdc_portfolio - (total_reserved_usdc + total_in_positions_usdc))

    # Realized PnL
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

            if quote == "USD":
                pnl_all_time_usd += position.profit_quote
            elif quote == "USDC":
                pnl_all_time_usdc += position.profit_quote
            else:
                pnl_all_time_btc += position.profit_quote

            if position.closed_at and position.closed_at >= start_of_today:
                if quote == "USD":
                    pnl_today_usd += position.profit_quote
                elif quote == "USDC":
                    pnl_today_usdc += position.profit_quote
                else:
                    pnl_today_btc += position.profit_quote

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

    await api_cache.set(cache_key, result, 60)
    await portfolio_cache.save(current_user.id, result)
    return result
