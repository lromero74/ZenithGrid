"""
Rebalance portfolio allocation service.

Pure business logic for computing portfolio allocation percentages,
reserve values, and deployable pools. Extracted from accounts_router.py.
"""

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account
from app.models.trading import Position

logger = logging.getLogger(__name__)


async def get_public_prices() -> dict:
    """Fetch current prices from public Coinbase API (no auth needed)."""
    from app.coinbase_api import public_market_data
    try:
        all_products = await public_market_data.list_products()
        bulk = {p.get("product_id", ""): float(p.get("price") or 0) for p in all_products}
    except Exception:
        bulk = {}
    stables = {"USDC-USD", "USDT-USD"}
    return {
        pid: bulk.get(pid, 1.0 if pid in stables else 0.0)
        for pid in ("BTC-USD", "ETH-USD", "USDC-USD", "USDT-USD")
    }


def compute_allocation(
    balances: dict, prices: dict, total_override: float | None = None,
) -> dict:
    """Compute USD-denominated allocation percentages from balances and prices.

    total_override: if provided, use this as the total instead of summing the
    four standard currencies. Used when the account holds altcoins that are
    priced separately.
    """
    usd_value = balances.get("USD", 0.0)
    btc_value = balances.get("BTC", 0.0) * prices.get("BTC-USD", 0.0)
    eth_value = balances.get("ETH", 0.0) * prices.get("ETH-USD", 0.0)
    usdc_value = balances.get("USDC", 0.0) * prices.get("USDC-USD", 1.0)
    usdt_value = balances.get("USDT", 0.0) * prices.get("USDT-USD", 1.0)
    total = total_override if total_override is not None else (
        usd_value + btc_value + eth_value + usdc_value + usdt_value
    )

    if total > 0:
        usd_pct = round(usd_value / total * 100, 2)
        btc_pct = round(btc_value / total * 100, 2)
        eth_pct = round(eth_value / total * 100, 2)
        usdc_pct = round(usdc_value / total * 100, 2)
        usdt_pct = round(usdt_value / total * 100, 2)
    else:
        usd_pct = btc_pct = eth_pct = usdc_pct = usdt_pct = 0.0

    return {
        "current_usd_pct": usd_pct,
        "current_btc_pct": btc_pct,
        "current_eth_pct": eth_pct,
        "current_usdc_pct": usdc_pct,
        "current_usdt_pct": usdt_pct,
        "total_value_usd": round(total, 2),
    }


async def _get_open_positions(db: AsyncSession, account_id: int) -> list:
    """Fetch open long positions for an account."""
    result = await db.execute(
        select(Position).where(
            Position.account_id == account_id,
            Position.status == "open",
            Position.direction == "long",
        )
    )
    return result.scalars().all()


async def _compute_paper_balances(
    account: Account, db: AsyncSession, prices: dict,
) -> dict:
    """Compute folded balances for a paper trading account.

    Folds altcoin free balances into their quote-currency bucket (USD, BTC, ETH,
    USDC) based on which pair the altcoin has an open position in.
    """
    from app.coinbase_api import public_market_data

    balances = json.loads(account.paper_balances) if account.paper_balances else {}

    # Build coin → quote-currency map from open positions
    open_positions = await _get_open_positions(db, account.id)
    coin_quote: dict = {}
    for pos in open_positions:
        parts = (pos.product_id or "").split("-")
        if len(parts) == 2:
            base, quote = parts
            coin_quote[base] = quote  # last open position wins; good enough

    # Collect altcoins that need pricing
    known_currencies = {"USD", "BTC", "ETH", "USDC", "USDT"}
    altcoins = [
        (currency, amount, coin_quote.get(currency, "USD"))
        for currency, amount in list(balances.items())
        if currency not in known_currencies and amount > 0
    ]

    if not altcoins:
        return balances

    # Fetch all prices in bulk (single API call, cached 1hr) — avoids N sequential
    # rate-limited ticker calls which cause timeouts on accounts with many altcoins.
    try:
        all_products = await public_market_data.list_products()
        bulk_prices = {
            p.get("product_id", ""): float(p.get("price") or 0)
            for p in all_products
        }
    except Exception:
        bulk_prices = {}

    primary_rates = [bulk_prices.get(f"{cur}-{quote}", 0.0) for cur, _, quote in altcoins]

    # Fallback to USD pair for any that returned 0 with a non-USD quote
    for i, (cur, _amt, quote) in enumerate(altcoins):
        if primary_rates[i] == 0.0 and quote != "USD":
            primary_rates[i] = bulk_prices.get(f"{cur}-USD", 0.0)

    # Fold priced altcoins into quote-currency buckets
    for (currency, amount, quote), rate in zip(altcoins, primary_rates):
        if rate == 0.0:
            continue
        if quote in ("BTC", "ETH", "USDC"):
            balances[quote] = balances.get(quote, 0.0) + amount * rate
        else:
            balances["USD"] = balances.get("USD", 0.0) + amount * rate

    return balances


async def _compute_live_balances(
    account: Account, db: AsyncSession, coinbase: Any,
) -> tuple[dict, dict]:
    """Compute balances and prices for a live (non-paper) account.

    Returns (balances, prices) where balances include open position market values
    folded into their quote-currency buckets.
    """
    async def _safe_balance(getter, fallback: float = 0.0) -> float:
        try:
            return float(await getter())
        except Exception:
            return fallback

    # Fetch all balances in parallel and all prices via single bulk API call
    # (bulk list_products is cached 1hr; avoids N sequential rate-limited ticker calls)
    from app.coinbase_api import public_market_data as pmd
    (
        usd_bal, btc_bal, eth_bal, usdc_bal, usdt_bal, all_products,
    ) = await asyncio.gather(
        _safe_balance(coinbase.get_usd_balance),
        _safe_balance(coinbase.get_btc_balance),
        _safe_balance(coinbase.get_eth_balance),
        _safe_balance(coinbase.get_usdc_balance),
        _safe_balance(coinbase.get_usdt_balance),
        pmd.list_products(),
    )

    bulk_prices = {
        p.get("product_id", ""): float(p.get("price") or 0)
        for p in (all_products or [])
    }

    def _bulk_price(product_id: str, fallback: float = 0.0) -> float:
        return bulk_prices.get(product_id, fallback)

    btc_price = _bulk_price("BTC-USD")
    eth_price = _bulk_price("ETH-USD")
    usdc_price = _bulk_price("USDC-USD", fallback=1.0)
    usdt_price = _bulk_price("USDT-USD", fallback=1.0)

    balances = {"USD": usd_bal, "BTC": btc_bal, "ETH": eth_bal, "USDC": usdc_bal, "USDT": usdt_bal}
    prices = {"BTC-USD": btc_price, "ETH-USD": eth_price, "USDC-USD": usdc_price, "USDT-USD": usdt_price}

    # Add open position market values to their quote-currency bucket
    open_positions = await _get_open_positions(db, account.id)

    for pos in open_positions:
        pid = pos.product_id or ""
        parts = pid.split("-") if pid else []
        if len(parts) != 2:
            continue
        base_qty = pos.total_base_acquired or 0.0
        if base_qty <= 0:
            continue
        quote_cur = parts[1]
        price_val = _bulk_price(pid, fallback=pos.entry_price or 0.0)
        if quote_cur in balances:
            balances[quote_cur] = balances.get(quote_cur, 0.0) + base_qty * price_val

    return balances, prices


def build_rebalance_response(
    account: Account, balances: dict, prices: dict, alloc: dict,
) -> dict:
    """Build the full rebalance status response dict from computed allocation data.

    Handles reserve subtraction, deployable pool, per-currency reserve percentages,
    and target defaults.
    """
    t_usd = account.rebalance_target_usd_pct
    t_btc = account.rebalance_target_btc_pct
    t_eth = account.rebalance_target_eth_pct
    t_usdc = account.rebalance_target_usdc_pct
    t_usdt = account.rebalance_target_usdt_pct

    # Compute reserve value in USD (needed for deployable context)
    _p = prices if isinstance(prices, dict) else {}
    _btc_p = _p.get("BTC-USD", 0.0)
    _eth_p = _p.get("ETH-USD", 0.0)
    _reserve_usd = round(
        (account.min_balance_usd or 0.0)
        + (account.min_balance_btc or 0.0) * _btc_p
        + (account.min_balance_eth or 0.0) * _eth_p
        + (account.min_balance_usdc or 0.0)
        + (account.min_balance_usdt or 0.0),
        2,
    )
    _total = alloc.get("total_value_usd", 0.0)
    _deployable = round(max(0.0, _total - _reserve_usd), 2)

    # Current allocation as % of deployable pool (reserves subtracted).
    _deployable_balances = {
        "USD": max(0.0, balances.get("USD", 0.0) - (account.min_balance_usd or 0.0)),
        "BTC": max(0.0, balances.get("BTC", 0.0) - (account.min_balance_btc or 0.0)),
        "ETH": max(0.0, balances.get("ETH", 0.0) - (account.min_balance_eth or 0.0)),
        "USDC": max(0.0, balances.get("USDC", 0.0) - (account.min_balance_usdc or 0.0)),
        "USDT": max(0.0, balances.get("USDT", 0.0) - (account.min_balance_usdt or 0.0)),
    }
    _deploy_alloc = compute_allocation(_deployable_balances, prices)

    # Per-currency reserve as % of total portfolio (for chart display).
    def _pct_of_total(usd_val: float) -> float:
        return round(usd_val / _total * 100, 2) if _total > 0 else 0.0

    _reserve_pct_usd = _pct_of_total(
        min(account.min_balance_usd or 0.0, balances.get("USD", 0.0))
    )
    _reserve_pct_btc = _pct_of_total(
        min(account.min_balance_btc or 0.0, balances.get("BTC", 0.0)) * _btc_p
    )
    _reserve_pct_eth = _pct_of_total(
        min(account.min_balance_eth or 0.0, balances.get("ETH", 0.0)) * _eth_p
    )
    _reserve_pct_usdc = _pct_of_total(
        min(account.min_balance_usdc or 0.0, balances.get("USDC", 0.0))
    )
    _reserve_pct_usdt = _pct_of_total(
        min(account.min_balance_usdt or 0.0, balances.get("USDT", 0.0))
    )

    return {
        "account_id": account.id,
        "current_usd_pct": _deploy_alloc["current_usd_pct"],
        "current_btc_pct": _deploy_alloc["current_btc_pct"],
        "current_eth_pct": _deploy_alloc["current_eth_pct"],
        "current_usdc_pct": _deploy_alloc["current_usdc_pct"],
        "current_usdt_pct": _deploy_alloc["current_usdt_pct"],
        "total_value_usd": _total,
        "target_usd_pct": t_usd if t_usd is not None else 34.0,
        "target_btc_pct": t_btc if t_btc is not None else 33.0,
        "target_eth_pct": t_eth if t_eth is not None else 33.0,
        "target_usdc_pct": t_usdc if t_usdc is not None else 0.0,
        "target_usdt_pct": t_usdt if t_usdt is not None else 0.0,
        "rebalance_enabled": bool(account.rebalance_enabled),
        "min_balance_usd": account.min_balance_usd or 0.0,
        "min_balance_btc": account.min_balance_btc or 0.0,
        "min_balance_eth": account.min_balance_eth or 0.0,
        "min_balance_usdc": account.min_balance_usdc or 0.0,
        "min_balance_usdt": account.min_balance_usdt or 0.0,
        "reserve_value_usd": _reserve_usd,
        "deployable_value_usd": _deployable,
        "reserve_usd_pct": _reserve_pct_usd,
        "reserve_btc_pct": _reserve_pct_btc,
        "reserve_eth_pct": _reserve_pct_eth,
        "reserve_usdc_pct": _reserve_pct_usdc,
        "reserve_usdt_pct": _reserve_pct_usdt,
    }


async def compute_rebalance_status(
    db: AsyncSession, account: Account, get_coinbase_fn: Any = None,
    get_prices_fn: Any = None,
) -> dict:
    """Compute full rebalance status for an account.

    Args:
        db: Async database session
        account: The Account model instance
        get_coinbase_fn: Async callable that returns a coinbase client for the account
        get_prices_fn: Async callable that returns public prices dict

    Returns:
        Full rebalance status response dict
    """
    if account.is_paper_trading:
        if get_prices_fn is None:
            get_prices_fn = get_public_prices
        prices = await get_prices_fn()
        balances = await _compute_paper_balances(account, db, prices)
        alloc = compute_allocation(balances, prices)
    else:
        if get_coinbase_fn is None:
            from app.services.exchange_service import get_coinbase_for_account
            get_coinbase_fn = get_coinbase_for_account
        coinbase = await get_coinbase_fn(account)
        balances, prices = await _compute_live_balances(account, db, coinbase)
        alloc = compute_allocation(balances, prices)

    return build_rebalance_response(account, balances, prices, alloc)
