"""
Perpetual futures (INTX) operations for Coinbase API
Handles portfolio management, positions, and balances for INTX perpetual contracts
"""

import logging
from typing import Any, Callable, Dict, List

from app.cache import api_cache

logger = logging.getLogger(__name__)


async def get_perps_portfolio_summary(
    request_func: Callable, portfolio_uuid: str
) -> Dict[str, Any]:
    """
    Get perpetuals portfolio summary including margin, balances, and positions overview.

    Args:
        request_func: Authenticated request function
        portfolio_uuid: INTX perpetuals portfolio UUID

    Returns:
        Portfolio summary with margin utilization, unrealized PnL, etc.
    """
    result = await request_func(
        "GET", f"/api/v3/brokerage/intx/portfolio/{portfolio_uuid}"
    )
    return result.get("portfolio", result)


async def list_perps_positions(
    request_func: Callable, portfolio_uuid: str
) -> List[Dict[str, Any]]:
    """
    List all open perpetual futures positions for a portfolio.

    Args:
        request_func: Authenticated request function
        portfolio_uuid: INTX perpetuals portfolio UUID

    Returns:
        List of position dicts with symbol, size, entry_price, unrealized_pnl, etc.
    """
    result = await request_func(
        "GET", f"/api/v3/brokerage/intx/positions/{portfolio_uuid}"
    )
    return result.get("positions", [])


async def get_perps_position(
    request_func: Callable, portfolio_uuid: str, symbol: str
) -> Dict[str, Any]:
    """
    Get a specific perpetual futures position.

    Args:
        request_func: Authenticated request function
        portfolio_uuid: INTX perpetuals portfolio UUID
        symbol: Product symbol (e.g., "BTC-PERP-INTX")

    Returns:
        Position details including size, entry_price, unrealized_pnl, liquidation_price
    """
    result = await request_func(
        "GET", f"/api/v3/brokerage/intx/positions/{portfolio_uuid}/{symbol}"
    )
    return result.get("position", result)


async def get_perps_portfolio_balances(
    request_func: Callable, portfolio_uuid: str
) -> Dict[str, Any]:
    """
    Get portfolio balances (USDC margin, collateral breakdown).

    Args:
        request_func: Authenticated request function
        portfolio_uuid: INTX perpetuals portfolio UUID

    Returns:
        Balance breakdown including available margin, used margin, etc.
    """
    result = await request_func(
        "GET", f"/api/v3/brokerage/intx/balances/{portfolio_uuid}"
    )
    return result


async def allocate_portfolio(
    request_func: Callable,
    portfolio_uuid: str,
    symbol: str,
    amount: str,
    currency: str,
) -> Dict[str, Any]:
    """
    Allocate funds to a perpetuals portfolio.

    Args:
        request_func: Authenticated request function
        portfolio_uuid: INTX perpetuals portfolio UUID
        symbol: Asset symbol (e.g., "USDC")
        amount: Amount to allocate
        currency: Currency of the amount

    Returns:
        Allocation result
    """
    data = {
        "portfolio_uuid": portfolio_uuid,
        "symbol": symbol,
        "amount": amount,
        "currency": currency,
    }
    result = await request_func(
        "POST", "/api/v3/brokerage/intx/allocate", data=data
    )
    return result


async def list_perpetual_products(request_func: Callable) -> List[Dict[str, Any]]:
    """
    List all available perpetual futures products (e.g., BTC-PERP-INTX, ETH-PERP-INTX).

    Returns:
        List of perpetual product dicts
    """
    cache_key = "perps_products"
    cached = await api_cache.get(cache_key)
    if cached is not None:
        return cached

    result = await request_func(
        "GET",
        "/api/v3/brokerage/products",
        params={
            "product_type": "FUTURE",
            "contract_expiry_type": "PERPETUAL",
        },
    )
    products = result.get("products", [])

    # Cache for 1 hour
    await api_cache.set(cache_key, products, ttl_seconds=3600)
    return products
