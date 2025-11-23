"""
Account and balance operations for Coinbase API
Handles accounts, portfolios, balances, and aggregate calculations
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from app.cache import api_cache
from app.constants import BALANCE_CACHE_TTL

logger = logging.getLogger(__name__)


async def get_accounts(
    request_func: Callable,
    force_fresh: bool = False
) -> List[Dict[str, Any]]:
    """Get all accounts (cached to reduce API calls unless force_fresh=True)"""
    cache_key = "accounts_list"

    if not force_fresh:
        cached = await api_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Using cached accounts list ({len(cached)} accounts)")
            return cached

    result = await request_func("GET", "/api/v3/brokerage/accounts")
    accounts = result.get("accounts", [])

    # Cache for 60 seconds (same as BALANCE_CACHE_TTL)
    await api_cache.set(cache_key, accounts, BALANCE_CACHE_TTL)
    logger.debug(f"Cached accounts list ({len(accounts)} accounts) for {BALANCE_CACHE_TTL}s")
    return accounts


async def get_account(
    request_func: Callable,
    account_id: str
) -> Dict[str, Any]:
    """Get specific account details"""
    result = await request_func("GET", f"/api/v3/brokerage/accounts/{account_id}")
    return result.get("account", {})


async def get_portfolios(request_func: Callable) -> List[Dict[str, Any]]:
    """Get list of all portfolios"""
    result = await request_func("GET", "/api/v3/brokerage/portfolios")
    return result.get("portfolios", [])


async def get_portfolio_breakdown(
    request_func: Callable,
    portfolio_uuid: Optional[str] = None
) -> dict:
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


async def get_btc_balance(
    request_func: Callable,
    auth_type: str
) -> float:
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
            accounts = await get_accounts(request_func)
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
        accounts = await get_accounts(request_func)
        balance = 0.0
        for account in accounts:
            if account.get("currency") == "BTC":
                available = account.get("available_balance", {})
                balance = float(available.get("value", 0))
                break

        return balance


async def get_eth_balance(
    request_func: Callable,
    auth_type: str
) -> float:
    """
    Get ETH balance

    Uses portfolio breakdown for CDP auth, individual accounts for HMAC auth.
    Both methods are cached to reduce API calls.
    """
    cache_key = "balance_eth"
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
        accounts = await get_accounts(request_func)
        balance = 0.0
        for account in accounts:
            if account.get("currency") == "ETH":
                available = account.get("available_balance", {})
                balance = float(available.get("value", 0))
                break

        await api_cache.set(cache_key, balance, BALANCE_CACHE_TTL)
        return balance


async def get_usd_balance(request_func: Callable) -> float:
    """Get USD balance (cached to reduce API calls)"""
    cache_key = "balance_usd"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        return cached

    accounts = await get_accounts(request_func)
    balance = 0.0
    for account in accounts:
        if account.get("currency") == "USD":
            available = account.get("available_balance", {})
            balance = float(available.get("value", 0))
            break

    await api_cache.set(cache_key, balance, BALANCE_CACHE_TTL)
    return balance


async def invalidate_balance_cache():
    """Invalidate balance cache (call after trades)"""
    await api_cache.delete("balance_btc")
    await api_cache.delete("balance_eth")
    await api_cache.delete("balance_usd")
    await api_cache.delete("accounts_list")
    await api_cache.delete("aggregate_btc_value")
    await api_cache.delete("aggregate_usd_value")


async def calculate_aggregate_btc_value(request_func: Callable, auth_type: str) -> float:
    """
    Calculate total BTC value of entire account (available BTC + BTC value of all positions).
    This is used for bot budget allocation (90% of total account value).

    Uses database to get positions held in open trades (since Coinbase API doesn't provide this).

    Returns:
        Total BTC value across all holdings (available + in positions)
    """
    logger.warning("📊 Calculating aggregate BTC value for budget allocation...")

    # Get available BTC balance from Coinbase
    available_btc = await get_btc_balance(request_func, auth_type)
    total_btc_value = available_btc
    logger.warning(f"  💰 Available BTC: {available_btc:.8f} BTC")

    # Get BTC value of open positions from database
    try:
        import sqlite3
        db_path = "/home/ec2-user/GetRidOf3CommasBecauseTheyGoDownTooOften/backend/trading.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Query all open positions in BTC pairs
        cursor.execute("""
            SELECT product_id, total_base_acquired, average_buy_price
            FROM positions
            WHERE status = 'open' AND product_id LIKE '%-BTC'
        """)

        positions = cursor.fetchall()
        btc_in_positions = 0.0

        for product_id, amount, avg_price in positions:
            if amount and avg_price:
                btc_value = float(amount) * float(avg_price)
                btc_in_positions += btc_value
                logger.warning(f"  💰 Position {product_id}: {amount:.8f} × {avg_price:.8f} BTC = {btc_value:.8f} BTC")

        conn.close()

        total_btc_value += btc_in_positions
        logger.warning(f"  💰 BTC in positions: {btc_in_positions:.8f} BTC")

    except Exception as e:
        logger.error(f"Failed to get positions from database: {e}")
        logger.warning("  ⚠️  Continuing with available BTC only")

    logger.warning(f"✅ Total account BTC value: {total_btc_value:.8f} BTC")
    return total_btc_value


async def calculate_aggregate_usd_value(
    request_func: Callable,
    get_btc_usd_price_func: Callable,
    get_current_price_func: Callable
) -> float:
    """
    Calculate aggregate USD value of entire portfolio (USD + all pairs converted to USD).
    This is used for USD-based bot budget allocation.

    Returns:
        Total USD value across all holdings
    """
    # Check cache first to reduce API spam
    cache_key = "aggregate_usd_value"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        logger.info(f"✅ Using cached aggregate USD value: ${cached:.2f}")
        return cached

    # Use get_accounts() as primary method (more reliable than portfolio endpoint)
    try:
        accounts = await get_accounts(request_func)
        btc_usd_price = await get_btc_usd_price_func()
        total_usd_value = 0.0

        for account in accounts:
            currency = account.get("currency", "")
            available_str = account.get("available_balance", {}).get("value", "0")
            available = float(available_str)

            if available == 0:
                continue

            # Convert all currencies to USD value
            if currency in ["USD", "USDC"]:
                total_usd_value += available
            elif currency == "BTC":
                total_usd_value += available * btc_usd_price
            else:
                try:
                    usd_price = await get_current_price_func(f"{currency}-USD")
                    total_usd_value += available * usd_price
                except Exception:
                    pass  # Skip assets we can't price

        # Cache the result for 30 seconds
        await api_cache.set(cache_key, total_usd_value, ttl_seconds=30)
        logger.info(f"✅ Calculated aggregate USD value: ${total_usd_value:.2f}")
        return total_usd_value

    except Exception as e:
        logger.error(f"Error calculating aggregate USD value using accounts endpoint: {e}")
        # Raise exception to trigger conservative fallback in calling code
        raise Exception(f"Failed to calculate aggregate USD value: accounts API failed ({e})")
