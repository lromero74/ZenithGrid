"""
Account and balance operations for Coinbase API
Handles accounts, portfolios, balances, and aggregate calculations
"""

import logging
import os
from typing import Any, Callable, Dict, List, Optional

from app.cache import api_cache
from app.constants import BALANCE_CACHE_TTL, AGGREGATE_VALUE_CACHE_TTL, MIN_USD_BALANCE_FOR_AGGREGATE

logger = logging.getLogger(__name__)


async def get_accounts(
    request_func: Callable, force_fresh: bool = False,
    account_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Get all accounts with pagination support (cached to reduce API calls unless force_fresh=True).

    Coinbase API may paginate results. This function fetches all pages to ensure
    no accounts are missed.
    """
    acct_suffix = str(account_id) if account_id is not None else "none"
    cache_key = f"accounts_list_{acct_suffix}"

    if not force_fresh:
        cached = await api_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Using cached accounts list ({len(cached)} accounts)")
            return cached

    all_accounts = []
    cursor = None
    page_count = 0
    max_pages = 10  # Safety limit to prevent infinite loops

    while page_count < max_pages:
        # Build URL with pagination parameters
        url = "/api/v3/brokerage/accounts?limit=250"  # Max limit per page
        if cursor:
            url += f"&cursor={cursor}"

        result = await request_func("GET", url)
        accounts = result.get("accounts", [])
        all_accounts.extend(accounts)
        page_count += 1

        logger.debug(f"Fetched page {page_count}: {len(accounts)} accounts (total so far: {len(all_accounts)})")

        # Check for next page
        cursor = result.get("cursor")
        if not cursor or len(accounts) == 0:
            break  # No more pages

    if page_count >= max_pages:
        logger.warning(f"Hit max page limit ({max_pages}) when fetching accounts - some may be missing")

    # Cache for 60 seconds (same as BALANCE_CACHE_TTL)
    await api_cache.set(cache_key, all_accounts, BALANCE_CACHE_TTL)
    logger.info(
        f"Fetched {len(all_accounts)} total accounts across {page_count} page(s), "
        f"cached for {BALANCE_CACHE_TTL}s"
    )
    return all_accounts


async def get_account(request_func: Callable, account_id: str) -> Dict[str, Any]:
    """Get specific account details"""
    result = await request_func("GET", f"/api/v3/brokerage/accounts/{account_id}")
    return result.get("account", {})


async def get_portfolios(request_func: Callable) -> List[Dict[str, Any]]:
    """Get list of all portfolios"""
    result = await request_func("GET", "/api/v3/brokerage/portfolios")
    return result.get("portfolios", [])


async def get_portfolio_breakdown(request_func: Callable, portfolio_uuid: Optional[str] = None) -> dict:
    """
    Get portfolio breakdown with all spot positions

    This is a CDP-specific endpoint that provides a consolidated view of all holdings.
    If portfolio_uuid is not provided, automatically fetches the first available portfolio.
    """
    if portfolio_uuid is None:
        # Dynamically fetch the first available portfolio UUID
        portfolios = await get_portfolios(request_func)
        if not portfolios:
            raise Exception("No portfolios found for this API key")
        portfolio_uuid = portfolios[0].get("uuid")
        logger.info(f"Using portfolio UUID: {portfolio_uuid} (name: {portfolios[0].get('name', 'Unknown')})")

    result = await request_func("GET", f"/api/v3/brokerage/portfolios/{portfolio_uuid}")
    return result.get("breakdown", {})


async def get_btc_balance(request_func: Callable, auth_type: str, account_id: Optional[int] = None) -> float:
    """
    Get BTC balance - always fetches fresh data from Coinbase (no caching)

    Uses portfolio breakdown for CDP auth, individual accounts for HMAC auth.
    """
    if auth_type == "cdp":
        # Use portfolio breakdown for CDP
        try:
            breakdown = await get_portfolio_breakdown(request_func)
            spot_positions = breakdown.get("spot_positions", [])
            for pos in spot_positions:
                if pos.get("asset") == "BTC":
                    balance = float(pos.get("available_to_trade_crypto", 0))
                    return balance
        except Exception as e:
            logger.warning(f"Portfolio endpoint failed for BTC balance: {e}. Falling back to get_accounts().")

        # Fallback to get_accounts() if portfolio fails
        try:
            accounts = await get_accounts(request_func, account_id=account_id)
            for account in accounts:
                if account.get("currency") == "BTC":
                    available = account.get("available_balance", {})
                    balance = float(available.get("value", 0))
                    return balance
        except Exception as fallback_error:
            logger.error(f"Fallback get_accounts() also failed: {fallback_error}")

        return 0.0
    else:
        # Use accounts for HMAC
        accounts = await get_accounts(request_func, account_id=account_id)
        balance = 0.0
        for account in accounts:
            if account.get("currency") == "BTC":
                available = account.get("available_balance", {})
                balance = float(available.get("value", 0))
                break

        return balance


async def get_eth_balance(request_func: Callable, auth_type: str, account_id: Optional[int] = None) -> float:
    """
    Get ETH balance

    Uses portfolio breakdown for CDP auth, individual accounts for HMAC auth.
    Both methods are cached to reduce API calls.
    """
    acct_suffix = str(account_id) if account_id is not None else "none"
    cache_key = f"balance_eth_{acct_suffix}"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        return cached

    if auth_type == "cdp":
        # Use portfolio breakdown for CDP
        try:
            breakdown = await get_portfolio_breakdown(request_func)
            spot_positions = breakdown.get("spot_positions", [])
            for pos in spot_positions:
                if pos.get("asset") == "ETH":
                    balance = float(pos.get("available_to_trade_crypto", 0))
                    await api_cache.set(cache_key, balance, BALANCE_CACHE_TTL)
                    return balance
        except Exception:
            pass
        return 0.0
    else:
        # Use accounts for HMAC
        accounts = await get_accounts(request_func, account_id=account_id)
        balance = 0.0
        for account in accounts:
            if account.get("currency") == "ETH":
                available = account.get("available_balance", {})
                balance = float(available.get("value", 0))
                break

        await api_cache.set(cache_key, balance, BALANCE_CACHE_TTL)
        return balance


async def get_usd_balance(request_func: Callable, account_id: Optional[int] = None) -> float:
    """Get USD balance (cached to reduce API calls)"""
    acct_suffix = str(account_id) if account_id is not None else "none"
    cache_key = f"balance_usd_{acct_suffix}"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        return cached

    accounts = await get_accounts(request_func, account_id=account_id)
    balance = 0.0
    for account in accounts:
        if account.get("currency") == "USD":
            available = account.get("available_balance", {})
            balance = float(available.get("value", 0))
            break

    await api_cache.set(cache_key, balance, BALANCE_CACHE_TTL)
    return balance


async def get_usdc_balance(request_func: Callable, account_id: Optional[int] = None) -> float:
    """Get USDC balance (cached to reduce API calls)"""
    acct_suffix = str(account_id) if account_id is not None else "none"
    cache_key = f"balance_usdc_{acct_suffix}"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        return cached

    accounts = await get_accounts(request_func, account_id=account_id)
    balance = 0.0
    for account in accounts:
        if account.get("currency") == "USDC":
            available = account.get("available_balance", {})
            balance = float(available.get("value", 0))
            break

    await api_cache.set(cache_key, balance, BALANCE_CACHE_TTL)
    return balance


async def get_usdt_balance(request_func: Callable, account_id: Optional[int] = None) -> float:
    """Get USDT balance (cached to reduce API calls)"""
    acct_suffix = str(account_id) if account_id is not None else "none"
    cache_key = f"balance_usdt_{acct_suffix}"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        return cached

    accounts = await get_accounts(request_func, account_id=account_id)
    balance = 0.0
    for account in accounts:
        if account.get("currency") == "USDT":
            available = account.get("available_balance", {})
            balance = float(available.get("value", 0))
            break

    await api_cache.set(cache_key, balance, BALANCE_CACHE_TTL)
    return balance


async def get_currency_balance(
    request_func: Callable, currency: str, account_id: Optional[int] = None
) -> float:
    """Get balance for a specific currency (cached).

    Unlike the specific get_usd_balance/get_btc_balance functions, this works for
    ANY currency. Used by calculate_aggregate_quote_value for per-market budget allocation.

    Args:
        request_func: Function to make API requests
        currency: Exact currency code (e.g., "USD", "USDC", "USDT", "BTC")
        account_id: Scoping key for per-user cache isolation

    Returns:
        Balance for exactly that currency (no grouping of stablecoins)
    """
    acct_suffix = str(account_id) if account_id is not None else "none"
    cache_key = f"balance_{currency.lower()}_{acct_suffix}"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        return cached

    accounts = await get_accounts(request_func, account_id=account_id)
    balance = 0.0
    for account in accounts:
        if account.get("currency") == currency:
            available = account.get("available_balance", {})
            balance = float(available.get("value", 0))
            break

    await api_cache.set(cache_key, balance, BALANCE_CACHE_TTL)
    return balance


async def invalidate_balance_cache(account_id: Optional[int] = None):
    """Invalidate balance cache (call after trades).

    If account_id is provided, only that account's scoped keys are cleared.
    If None, all balance/accounts/aggregate keys are cleared (global invalidation).
    """
    if account_id is not None:
        suffix = str(account_id)
        await api_cache.delete(f"balance_btc_{suffix}")
        await api_cache.delete(f"balance_eth_{suffix}")
        await api_cache.delete(f"balance_usd_{suffix}")
        await api_cache.delete(f"balance_usdc_{suffix}")
        await api_cache.delete(f"balance_usdt_{suffix}")
        await api_cache.delete(f"accounts_list_{suffix}")
        await api_cache.delete(f"aggregate_btc_{suffix}")
        await api_cache.delete(f"aggregate_usd_{suffix}")
        await api_cache.delete_prefix("aggregate_quote_")
    else:
        # Global invalidation — clear all scoped keys
        await api_cache.delete_prefix("balance_")
        await api_cache.delete_prefix("accounts_list_")
        await api_cache.delete_prefix("aggregate_")
    # Also invalidate cached portfolio responses (stale after trades)
    await api_cache.delete("portfolio_response")
    await api_cache.delete_prefix("portfolio_response_")


async def calculate_aggregate_btc_value(
    request_func: Callable, auth_type: str, get_current_price_func: Callable = None,
    bypass_cache: bool = False, account_id: Optional[int] = None
) -> float:
    """
    Calculate total BTC value of entire account (available BTC + liquidation value of all BTC-pair positions).
    This is used for bot budget allocation.

    Uses database to get positions held in open trades (since Coinbase API doesn't provide this).
    Uses CURRENT market prices (not cost basis) for true liquidation value.

    Args:
        request_func: Function to make API requests
        auth_type: Authentication type
        get_current_price_func: Optional function to fetch current prices
        bypass_cache: If True, skip cache and force fresh calculation
            (use for critical operations like position creation)
        account_id: Scoping key for per-user cache isolation

    Returns:
        Total BTC value across all holdings (available + current value of positions)
    """
    import asyncio

    # Check cache first to reduce API spam (unless bypassed for critical operations)
    acct_suffix = str(account_id) if account_id is not None else "none"
    cache_key = f"aggregate_btc_{acct_suffix}"
    if not bypass_cache:
        cached = await api_cache.get(cache_key)
        if cached is not None:
            logger.info(f"✅ Using cached aggregate BTC value: {cached:.8f} BTC")
            return cached

    if bypass_cache:
        logger.info("📊 Calculating FRESH aggregate BTC value (cache bypassed for critical operation)...")
    else:
        logger.info("📊 Calculating aggregate BTC value for budget allocation...")

    # Get available BTC balance from Coinbase
    available_btc = await get_btc_balance(request_func, auth_type, account_id=account_id)
    total_btc_value = available_btc
    logger.debug(f"  💰 Available BTC: {available_btc:.8f} BTC")

    # Get BTC value of open positions from database using CURRENT prices
    try:
        import sqlite3

        # Use relative path from this file's location (backend/app/coinbase_api/ -> backend/)
        _backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_path = os.path.join(_backend_dir, "trading.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Query open BTC-pair positions, scoped to account via bots table
        if account_id is not None:
            cursor.execute(
                """
                SELECT p.product_id, p.total_base_acquired, p.average_buy_price
                FROM positions p JOIN bots b ON p.bot_id = b.id
                WHERE p.status = 'open' AND p.product_id LIKE '%-BTC' AND b.account_id = ?
                """,
                (account_id,)
            )
        else:
            cursor.execute(
                """
                SELECT product_id, total_base_acquired, average_buy_price
                FROM positions
                WHERE status = 'open' AND product_id LIKE '%-BTC'
                """
            )

        positions = cursor.fetchall()
        conn.close()
        btc_in_positions = 0.0

        if positions and get_current_price_func:
            # Fetch all prices in PARALLEL instead of sequentially
            unique_products = list({p[0] for p in positions if p[0]})

            async def fetch_price(product_id: str):
                try:
                    price = await get_current_price_func(product_id)
                    return (product_id, price)
                except Exception:
                    return (product_id, None)

            # Batch fetch prices (15 at a time to avoid rate limits)
            price_map = {}
            batch_size = 15
            for i in range(0, len(unique_products), batch_size):
                batch = unique_products[i:i + batch_size]
                batch_results = await asyncio.gather(*[fetch_price(pid) for pid in batch])
                for pid, price in batch_results:
                    if price is not None:
                        price_map[pid] = price
                if i + batch_size < len(unique_products):
                    await asyncio.sleep(0.1)

            # Now calculate BTC value using cached prices
            for product_id, amount, avg_price in positions:
                if amount:
                    amount = float(amount)
                    current_price = price_map.get(product_id)
                    if current_price is not None:
                        btc_value = amount * current_price
                        logger.debug(
                            f"  💰 Position {product_id}: {amount:.8f} × "
                            f"{current_price:.8f} BTC = {btc_value:.8f} BTC"
                        )
                    elif avg_price:
                        # Fallback to avg_price if price fetch failed
                        btc_value = amount * float(avg_price)
                        logger.debug(
                            f"  💰 Position {product_id}: {amount:.8f} × "
                            f"{avg_price:.8f} BTC (fallback) = {btc_value:.8f} BTC"
                        )
                    else:
                        btc_value = 0.0
                    btc_in_positions += btc_value
        elif positions:
            # No price function, use avg_price for all
            for product_id, amount, avg_price in positions:
                if amount and avg_price:
                    btc_value = float(amount) * float(avg_price)
                    btc_in_positions += btc_value

        total_btc_value += btc_in_positions
        logger.debug(f"  💰 BTC in positions: {btc_in_positions:.8f} BTC")

    except Exception as e:
        logger.error(f"Failed to get positions from database: {e}")
        logger.debug("  ⚠️  Continuing with available BTC only")

    # Cache the result using configured TTL
    await api_cache.set(cache_key, total_btc_value, ttl_seconds=AGGREGATE_VALUE_CACHE_TTL)
    logger.info(
        f"✅ Total account BTC value (liquidation): {total_btc_value:.8f} BTC "
        f"(cached for {AGGREGATE_VALUE_CACHE_TTL}s)"
    )
    return total_btc_value


async def calculate_aggregate_usd_value(
    request_func: Callable, get_btc_usd_price_func: Callable, get_current_price_func: Callable,
    account_id: Optional[int] = None
) -> float:
    """
    Calculate aggregate USD value of entire portfolio (USD + all pairs converted to USD).
    This is used for USD-based bot budget allocation.

    Returns:
        Total USD value across all holdings
    """
    import asyncio

    # Check cache first to reduce API spam
    acct_suffix = str(account_id) if account_id is not None else "none"
    cache_key = f"aggregate_usd_{acct_suffix}"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        logger.info(f"✅ Using cached aggregate USD value: ${cached:.2f}")
        return cached

    # Use get_accounts() as primary method (more reliable than portfolio endpoint)
    try:
        accounts = await get_accounts(request_func, account_id=account_id)
        btc_usd_price = await get_btc_usd_price_func()
        total_usd_value = 0.0

        # Build list of currencies that need USD price fetching
        currencies_to_price = []
        account_data = []  # (currency, available, needs_price)

        # Count skipped dust balances for logging
        dust_skipped = 0

        for account in accounts:
            currency = account.get("currency", "")
            available_str = account.get("available_balance", {}).get("value", "0")
            available = float(available_str)

            if available == 0:
                continue

            if currency in ["USD", "USDC"]:
                total_usd_value += available
            elif currency == "BTC":
                btc_value_usd = available * btc_usd_price
                if btc_value_usd >= MIN_USD_BALANCE_FOR_AGGREGATE:
                    total_usd_value += btc_value_usd
                else:
                    dust_skipped += 1
            else:
                # Heuristic: skip very small quantities that are likely dust
                # Most coins have prices < $100k, so 0.00001 of any coin is < $1
                if available < 0.00001:
                    dust_skipped += 1
                    continue
                currencies_to_price.append(currency)
                account_data.append((currency, available))

        if dust_skipped > 0:
            logger.debug(f"Skipped {dust_skipped} dust balances in aggregate USD calculation")

        # Fetch all prices in PARALLEL instead of sequentially
        if currencies_to_price:
            async def fetch_usd_price(currency: str):
                try:
                    price = await get_current_price_func(f"{currency}-USD")
                    return (currency, price)
                except Exception:
                    return (currency, None)

            # Batch fetch prices (15 at a time to avoid rate limits)
            price_map = {}
            batch_size = 15
            for i in range(0, len(currencies_to_price), batch_size):
                batch = currencies_to_price[i:i + batch_size]
                batch_results = await asyncio.gather(*[fetch_usd_price(c) for c in batch])
                for currency, price in batch_results:
                    if price is not None:
                        price_map[currency] = price
                if i + batch_size < len(currencies_to_price):
                    await asyncio.sleep(0.1)

            # Add values using fetched prices
            for currency, available in account_data:
                price = price_map.get(currency)
                if price is not None:
                    total_usd_value += available * price

        # Cache the result using configured TTL
        await api_cache.set(cache_key, total_usd_value, ttl_seconds=AGGREGATE_VALUE_CACHE_TTL)
        logger.info(
            f"✅ Calculated aggregate USD value: ${total_usd_value:.2f} "
            f"(cached for {AGGREGATE_VALUE_CACHE_TTL}s)"
        )
        return total_usd_value

    except Exception as e:
        logger.error(f"Error calculating aggregate USD value using accounts endpoint: {e}")
        # Raise exception to trigger conservative fallback in calling code
        raise Exception(f"Failed to calculate aggregate USD value: accounts API failed ({e})")


async def calculate_aggregate_quote_value(
    request_func: Callable, quote_currency: str,
    get_current_price_func: Callable = None,
    bypass_cache: bool = False, account_id: Optional[int] = None
) -> float:
    """
    Calculate total value in a specific quote currency for budget allocation.

    Returns: raw balance for exactly that currency + current liquidation value
    of open positions denominated in that currency's pairs (e.g., %-USD for USD).

    This is NOT the total portfolio value — it's only the assets in this market.
    Coinbase treats USD, USDC, and USDT as separate markets.

    Args:
        request_func: Function to make API requests
        quote_currency: Exact quote currency (e.g., "USD", "USDC", "BTC")
        get_current_price_func: Optional function to fetch current prices
        bypass_cache: If True, skip cache and force fresh calculation
        account_id: Scoping key for per-user cache isolation

    Returns:
        Total value in the specified quote currency
    """
    import asyncio
    import sqlite3

    acct_suffix = str(account_id) if account_id is not None else "none"
    cache_key = f"aggregate_quote_{quote_currency.lower()}_{acct_suffix}"

    if not bypass_cache:
        cached = await api_cache.get(cache_key)
        if cached is not None:
            logger.info(
                f"✅ Using cached aggregate {quote_currency} value: {cached}"
            )
            return cached

    # 1. Get raw balance for exactly this currency
    raw_balance = await get_currency_balance(
        request_func, quote_currency, account_id
    )
    total_value = raw_balance

    # 2. Add current value of open positions in this quote currency's pairs
    try:
        _backend_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        db_path = os.path.join(_backend_dir, "trading.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        like_pattern = f"%-{quote_currency}"
        if account_id is not None:
            cursor.execute(
                """
                SELECT p.product_id, p.total_base_acquired,
                       p.average_buy_price
                FROM positions p JOIN bots b ON p.bot_id = b.id
                WHERE p.status = 'open'
                  AND p.product_id LIKE ?
                  AND b.account_id = ?
                """,
                (like_pattern, account_id)
            )
        else:
            cursor.execute(
                """
                SELECT product_id, total_base_acquired, average_buy_price
                FROM positions
                WHERE status = 'open' AND product_id LIKE ?
                """,
                (like_pattern,)
            )

        positions = cursor.fetchall()
        conn.close()
        positions_value = 0.0

        if positions and get_current_price_func:
            unique_products = list({p[0] for p in positions if p[0]})

            async def fetch_price(pid: str):
                try:
                    return (pid, await get_current_price_func(pid))
                except Exception:
                    return (pid, None)

            # Batch fetch prices (15 at a time to avoid rate limits)
            price_map = {}
            batch_size = 15
            for i in range(0, len(unique_products), batch_size):
                batch = unique_products[i:i + batch_size]
                results = await asyncio.gather(
                    *[fetch_price(pid) for pid in batch]
                )
                for pid, price in results:
                    if price is not None:
                        price_map[pid] = price
                if i + batch_size < len(unique_products):
                    await asyncio.sleep(0.1)

            for product_id, amount, avg_price in positions:
                if amount:
                    amount = float(amount)
                    price = price_map.get(product_id)
                    if price is not None:
                        positions_value += amount * price
                    elif avg_price:
                        positions_value += amount * float(avg_price)
        elif positions:
            # No price function — use avg_price for all
            for _, amount, avg_price in positions:
                if amount and avg_price:
                    positions_value += float(amount) * float(avg_price)

        total_value += positions_value
        if positions_value > 0:
            logger.debug(
                f"  💰 {quote_currency} in positions: {positions_value}"
            )

    except Exception as e:
        logger.error(
            f"Failed to get positions for {quote_currency} aggregate: {e}"
        )
        logger.debug(
            f"  ⚠️  Continuing with {quote_currency} balance only"
        )

    await api_cache.set(
        cache_key, total_value, ttl_seconds=AGGREGATE_VALUE_CACHE_TTL
    )
    logger.info(
        f"✅ Aggregate {quote_currency} value (budget): {total_value} "
        f"(cached for {AGGREGATE_VALUE_CACHE_TTL}s)"
    )
    return total_value
