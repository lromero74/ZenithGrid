"""
Portfolio Service

Provides portfolio calculation functions for CEX and DEX accounts,
balance retrieval, and portfolio conversion orchestration.
"""

import logging
from app.utils.timeutil import utcnow
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ExchangeUnavailableError, NotFoundError

from app.cache import api_cache, portfolio_cache
from app.coinbase_unified_client import CoinbaseClient
from app.encryption import decrypt_value, is_encrypted
from app.exchange_clients.factory import create_exchange_client, ExchangeClientConfig, CoinbaseCredentials
from app.models import Account, Bot, PendingOrder, Position, User
from app.services.account_access import accessible_account_ids, accessible_accounts_filter
from app.services.dex_wallet_service import dex_wallet_service
from app.services.exchange_service import get_exchange_client_for_account
from app.services.portfolio_calculations import (
    BalanceBreakdownParams,
    _apply_asset_pnl_to_holdings,
    _build_portfolio_holdings,
    _compute_balance_breakdown,
    _compute_position_pnl,
    aggregate_pnl_rows,
)

logger = logging.getLogger(__name__)


async def _query_closed_pnl(db: AsyncSession, account_ids) -> tuple:
    """Aggregate realized PnL (all-time + today) for the given account id(s).

    Sums ``profit_quote`` in SQL grouped by ``product_id``, so the result set is
    one row per distinct trading pair — not one row per closed position. This
    bounds the work by the (small) number of pairs an account trades instead of
    its entire, ever-growing trade history, which previously had to be loaded
    into memory and summed on every portfolio fetch.
    """
    zero = ({"usd": 0.0, "btc": 0.0, "usdc": 0.0}, {"usd": 0.0, "btc": 0.0, "usdc": 0.0})
    if not account_ids:
        return zero

    start_of_today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_sum = func.sum(
        case((Position.closed_at >= start_of_today, Position.profit_quote), else_=0.0)
    )
    query = (
        select(Position.product_id, func.sum(Position.profit_quote), today_sum)
        .where(
            Position.status == "closed",
            Position.account_id.in_(account_ids),
            Position.profit_quote.isnot(None),
        )
        .group_by(Position.product_id)
    )
    rows = (await db.execute(query)).all()
    return aggregate_pnl_rows(rows)


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


async def get_coinbase_from_db(db: AsyncSession, user_id: int) -> CoinbaseClient:
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
            # Scope the client to this account so calculate_market_budget()
            # filters open positions to this account's bots and uses an
            # account-isolated cache key. Without it the budget/soft-ceiling
            # math sums USD-quoted positions across ALL accounts and users.
            account_id=account.id,
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
    include_details: bool = True,
) -> dict:
    """
    Get portfolio for a CEX (Coinbase) account.

    Uses Coinbase's portfolio breakdown which returns USD values for every
    position in a single API call — no individual price fetches needed.
    """
    cache_key = f"portfolio_response_{account.id}"

    if not force_fresh:
        # Check in-memory cache first (25s TTL — expires before 30s frontend poll)
        cached = await api_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Using cached portfolio response for account {account.id}")
            return cached

        # Check persistent cache (survives restarts). Keyed by account.id — a
        # user owns multiple accounts, so keying by user_id would let one
        # account's portfolio overwrite/serve another's.
        persistent = await portfolio_cache.get(account.id)
        if persistent is not None:
            await api_cache.set(cache_key, persistent, 25)
            logger.info(f"Serving persistent portfolio cache for account {account.id}")
            return persistent

    coinbase = await get_coinbase_for_account_func(account)

    # Single API call: breakdown has USD values for every position
    breakdown = await coinbase.get_portfolio_breakdown()
    spot_positions = breakdown.get("spot_positions", [])

    # Get BTC/USD price for BTC value column (uses cache, very fast)
    btc_usd_price = await coinbase.get_btc_usd_price()

    if not include_details:
        (_, total_usd_value, total_btc_value, _, _, _, _) = _build_portfolio_holdings(
            spot_positions,
            btc_usd_price,
            [],
        )
        result = {
            "total_usd_value": total_usd_value,
            "total_btc_value": total_btc_value,
            "btc_usd_price": btc_usd_price,
            "account_id": account.id,
            "account_name": account.name,
            "account_type": "cex",
            "is_dex": False,
            "holdings": [],
            "holdings_count": 0,
        }
        return result

    # Get open positions for this account (needed for "in deals" amounts)
    positions_query = select(Position).where(
        Position.status == "open",
        Position.account_id == account.id
    )
    positions_result = await db.execute(positions_query)
    open_positions = positions_result.scalars().all()

    # Build portfolio holdings from breakdown data
    (
        portfolio_holdings, total_usd_value, total_btc_value,
        actual_usd_balance, actual_usdc_balance, actual_btc_balance,
        breakdown_prices,
    ) = _build_portfolio_holdings(spot_positions, btc_usd_price, open_positions)

    # Compute unrealized PnL and apply to holdings
    asset_pnl = _compute_position_pnl(open_positions, breakdown_prices, btc_usd_price)
    _apply_asset_pnl_to_holdings(portfolio_holdings, asset_pnl)

    portfolio_holdings.sort(key=lambda x: x["usd_value"], reverse=True)

    # Get balance breakdown for this account's bots (strictly scoped)
    bots_query = select(Bot).where(Bot.account_id == account.id)
    bots_result = await db.execute(bots_query)
    account_bots = bots_result.scalars().all()

    total_reserved_btc = sum(bot.reserved_btc_balance for bot in account_bots)
    total_reserved_usd = sum(bot.reserved_usd_balance for bot in account_bots)

    balance_breakdown = _compute_balance_breakdown(BalanceBreakdownParams(
        account_bots=account_bots, open_positions=open_positions,
        actual_btc=actual_btc_balance, actual_usd=actual_usd_balance,
        actual_usdc=actual_usdc_balance, total_reserved_btc=total_reserved_btc,
        total_reserved_usd=total_reserved_usd,
        breakdown_prices=breakdown_prices, btc_usd_price=btc_usd_price,
    ))

    # Calculate realized PnL (strictly scoped to this account)
    pnl_all_time, pnl_today = await _query_closed_pnl(db, [account.id])

    result = {
        "total_usd_value": total_usd_value,
        "total_btc_value": total_btc_value,
        "btc_usd_price": btc_usd_price,
        "holdings": portfolio_holdings,
        "holdings_count": len(portfolio_holdings),
        "balance_breakdown": balance_breakdown,
        "pnl": {
            "today": pnl_today,
            "all_time": pnl_all_time,
        },
        "account_id": account.id,
        "account_name": account.name,
        "account_type": "cex",
        "is_dex": False,
    }

    # Cache in-memory (25s — expires before 30s frontend poll) and persist to disk
    await api_cache.set(cache_key, result, 25)
    await portfolio_cache.save(account.id, result)  # account-scoped, not user-scoped
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
    now = utcnow()
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
            select(Account).where(Account.id == account_id, accessible_accounts_filter(current_user.id))
        )
        account = account_result.scalar_one_or_none()
        if not account:
            raise NotFoundError("Account not found")
    else:
        account_result = await db.execute(
            select(Account).where(
                Account.type == "cex",
                Account.is_active.is_(True),
                accessible_accounts_filter(current_user.id),
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
        # Use the account owner's credentials (not the observer's — they have none)
        coinbase = await get_coinbase_from_db(db, account.user_id)
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


async def _get_paper_portfolio(client, btc_usd_price: float) -> dict:
    """Build portfolio data for a paper trading account."""
    altcoin_btc_prices = {}
    for currency in client.balances:
        if currency in ("BTC", "USD", "USDC", "USDT"):
            continue
        try:
            price = await client.get_current_price(f"{currency}-BTC")
            if price is not None:
                altcoin_btc_prices[currency] = price
                continue
        except Exception:
            logger.debug("Paper portfolio: %s-BTC price lookup failed", currency, exc_info=True)
        try:
            usd_price = await client.get_current_price(f"{currency}-USD")
            if usd_price is not None and btc_usd_price > 0:
                altcoin_btc_prices[currency] = usd_price / btc_usd_price
                continue
        except Exception:
            logger.debug("Paper portfolio: %s-USD price lookup failed", currency, exc_info=True)
        altcoin_btc_prices[currency] = 0.0

    holdings = []
    total_btc = 0.0
    total_usd = 0.0
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

            total_btc += btc_value
            total_usd += usd_value
            holdings.append({
                "asset": currency, "total_balance": balance,
                "available": balance, "hold": 0.0,
                "current_price_usd": price_usd, "usd_value": usd_value,
                "btc_value": btc_value, "percentage": 0.0,
            })

    for h in holdings:
        if total_usd > 0:
            h["percentage"] = (h["usd_value"] / total_usd) * 100

    return {
        "holdings": holdings, "holdings_count": len(holdings),
        "total_usd_value": total_usd, "total_btc_value": total_btc,
        "btc_usd_price": btc_usd_price, "is_paper_trading": True,
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
                logger.warning("Paper portfolio: BTC/USD price lookup failed", exc_info=True)
            return await _get_paper_portfolio(client, btc_usd_price)
        return {
            "holdings": [], "holdings_count": 0,
            "total_usd_value": 0, "total_btc_value": 0,
            "btc_usd_price": 0, "is_paper_trading": True,
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

    # Phase 1: Fetch open positions for all accessible accounts (owned + shared).
    # Must happen before building holdings so the "in_positions" amount per asset
    # correctly reduces the per-holding `available` figure.
    user_account_ids = await accessible_account_ids(db, current_user.id)

    positions_query = select(Position).where(
        Position.status == "open",
        Position.account_id.in_(user_account_ids) if user_account_ids else Position.id < 0,
    )
    positions_result = await db.execute(positions_query)
    open_positions = positions_result.scalars().all()

    # Phase 2: Build portfolio holdings
    (
        holdings, total_usd_value, total_btc_value,
        actual_usd_balance, actual_usdc_balance, actual_btc_balance,
        breakdown_prices,
    ) = _build_portfolio_holdings(spot_positions, btc_usd_price, open_positions)

    # Phase 3: Apply unrealized PnL to holdings
    asset_pnl = _compute_position_pnl(open_positions, breakdown_prices, btc_usd_price)
    _apply_asset_pnl_to_holdings(holdings, asset_pnl)
    holdings.sort(key=lambda x: x["usd_value"], reverse=True)

    # Phase 4: Balance breakdown (reserved, in-positions, free)
    bots_query = select(Bot).where(
        Bot.account_id.in_(user_account_ids) if user_account_ids else Bot.id < 0,
    )
    bots_result = await db.execute(bots_query)
    all_bots = bots_result.scalars().all()

    total_reserved_btc = sum(bot.reserved_btc_balance for bot in all_bots)
    total_reserved_usd = sum(bot.reserved_usd_balance for bot in all_bots)

    balance_breakdown = _compute_balance_breakdown(BalanceBreakdownParams(
        account_bots=all_bots, open_positions=open_positions,
        actual_btc=actual_btc_balance, actual_usd=actual_usd_balance,
        actual_usdc=actual_usdc_balance,
        total_reserved_btc=total_reserved_btc,
        total_reserved_usd=total_reserved_usd,
        breakdown_prices=breakdown_prices, btc_usd_price=btc_usd_price,
    ))

    # Phase 5: Realized PnL (scoped to the user's accounts; aggregated in SQL)
    pnl_all_time, pnl_today = await _query_closed_pnl(db, user_account_ids)
    pnl = {"all_time": pnl_all_time, "today": pnl_today}

    logger.info(
        f"Portfolio summary: {len(spot_positions)} raw positions -> "
        f"{len(holdings)} after filtering (${total_usd_value:.2f} total)"
    )

    result = {
        "total_usd_value": total_usd_value,
        "total_btc_value": total_btc_value,
        "btc_usd_price": btc_usd_price,
        "holdings": holdings,
        "holdings_count": len(holdings),
        "balance_breakdown": balance_breakdown,
        "pnl": pnl,
    }

    await api_cache.set(cache_key, result, 60)
    await portfolio_cache.save(current_user.id, result)
    return result
