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
    prices = {}
    for product_id in ("BTC-USD", "ETH-USD", "USDC-USD", "USDT-USD"):
        try:
            prices[product_id] = float(await public_market_data.get_current_price(product_id))
        except Exception:
            prices[product_id] = 1.0 if product_id in ("USDC-USD", "USDT-USD") else 0.0
    return prices


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

    # Fold each free altcoin into its quote-currency bucket
    known_currencies = {"USD", "BTC", "ETH", "USDC", "USDT"}
    for currency, amount in list(balances.items()):
        if currency in known_currencies or amount <= 0:
            continue
        quote = coin_quote.get(currency, "USD")
        try:
            pair = f"{currency}-{quote}"
            rate = float(await public_market_data.get_current_price(pair))
            if quote in ("BTC", "ETH", "USDC"):
                # rate is in quote units; add native quote amount
                balances[quote] = balances.get(quote, 0.0) + amount * rate
            else:
                # USD (or unknown): add USD value directly
                balances["USD"] = balances.get("USD", 0.0) + amount * rate
        except Exception:
            # Try USD fallback for BTC-quoted coins whose price lookup failed
            if quote != "USD":
                try:
                    usd_rate = float(await public_market_data.get_current_price(
                        f"{currency}-USD"
                    ))
                    balances["USD"] = balances.get("USD", 0.0) + amount * usd_rate
                except Exception:
                    pass  # unpriceable coin; omit from total

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

    async def _safe_price(product_id: str, fallback: float = 0.0) -> float:
        try:
            return float(await coinbase.get_current_price(product_id))
        except Exception:
            return fallback

    # Fetch all balances and prices in parallel
    (
        usd_bal, btc_bal, eth_bal, usdc_bal, usdt_bal,
        btc_price, eth_price, usdc_price, usdt_price,
    ) = await asyncio.gather(
        _safe_balance(coinbase.get_usd_balance),
        _safe_balance(coinbase.get_btc_balance),
        _safe_balance(coinbase.get_eth_balance),
        _safe_balance(coinbase.get_usdc_balance),
        _safe_balance(coinbase.get_usdt_balance),
        _safe_price("BTC-USD"),
        _safe_price("ETH-USD"),
        _safe_price("USDC-USD", fallback=1.0),
        _safe_price("USDT-USD", fallback=1.0),
    )

    balances = {"USD": usd_bal, "BTC": btc_bal, "ETH": eth_bal, "USDC": usdc_bal, "USDT": usdt_bal}
    prices = {"BTC-USD": btc_price, "ETH-USD": eth_price, "USDC-USD": usdc_price, "USDT-USD": usdt_price}

    # Add open position market values to their quote-currency bucket
    open_positions = await _get_open_positions(db, account.id)
    for pos in open_positions:
        pid = pos.product_id or ""
        parts = pid.split("-") if pid else []
        if len(parts) != 2:
            continue
        _, quote_cur = parts[0], parts[1]
        base_qty = pos.total_base_acquired or 0.0
        if base_qty <= 0:
            continue
        try:
            price_val = float(await coinbase.get_current_price(pid))
        except Exception:
            price_val = pos.entry_price or 0.0
        position_value = base_qty * price_val
        if quote_cur in balances:
            balances[quote_cur] = balances.get(quote_cur, 0.0) + position_value

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
