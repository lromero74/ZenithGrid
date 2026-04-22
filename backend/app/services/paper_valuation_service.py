"""
Shared paper-account valuation helpers.

Keeps paper summary totals and full paper portfolio holdings on the same
bounded-concurrency pricing path so the dashboard and Portfolio page stay in
sync without hammering Coinbase.
"""

import asyncio
import json
from typing import Any

from app.coinbase_api.public_market_data import (
    get_btc_usd_price as get_public_btc_usd_price,
    get_current_price as get_public_price,
)

PAPER_PRICE_CONCURRENCY = 5
_STABLES = {"USD", "USDC", "USDT"}


def load_paper_balances(account: Any) -> dict[str, float]:
    """Return normalized paper balances for an account-like object."""
    if account.paper_balances:
        raw_balances = json.loads(account.paper_balances)
    else:
        raw_balances = {"BTC": 0.0, "ETH": 0.0, "USD": 0.0, "USDC": 0.0, "USDT": 0.0}

    return {currency: float(amount or 0.0) for currency, amount in raw_balances.items()}


async def _get_asset_valuation(
    currency: str,
    amount: float,
    btc_usd_price: float,
    semaphore: asyncio.Semaphore,
) -> dict[str, float | str]:
    """Return a small valuation record for one paper balance."""
    if amount <= 0:
        return {
            "asset": currency,
            "amount": amount,
            "current_price_usd": 0.0,
            "usd_value": 0.0,
            "btc_value": 0.0,
        }

    if currency == "BTC":
        usd_value = amount * btc_usd_price
        return {
            "asset": currency,
            "amount": amount,
            "current_price_usd": btc_usd_price,
            "usd_value": usd_value,
            "btc_value": amount,
        }

    if currency in _STABLES:
        btc_value = amount / btc_usd_price if btc_usd_price > 0 else 0.0
        return {
            "asset": currency,
            "amount": amount,
            "current_price_usd": 1.0,
            "usd_value": amount,
            "btc_value": btc_value,
        }

    try:
        async with semaphore:
            usd_price = await get_public_price(f"{currency}-USD")
        usd_value = amount * usd_price
        btc_value = usd_value / btc_usd_price if btc_usd_price > 0 else 0.0
        return {
            "asset": currency,
            "amount": amount,
            "current_price_usd": usd_price,
            "usd_value": usd_value,
            "btc_value": btc_value,
        }
    except Exception:
        pass

    try:
        async with semaphore:
            btc_price = await get_public_price(f"{currency}-BTC")
        btc_value = amount * btc_price
        usd_value = btc_value * btc_usd_price
        current_price_usd = usd_value / amount if amount > 0 else 0.0
        return {
            "asset": currency,
            "amount": amount,
            "current_price_usd": current_price_usd,
            "usd_value": usd_value,
            "btc_value": btc_value,
        }
    except Exception:
        return {
            "asset": currency,
            "amount": amount,
            "current_price_usd": 0.0,
            "usd_value": 0.0,
            "btc_value": 0.0,
        }


async def build_paper_holdings_and_totals(account: Any) -> dict[str, Any]:
    """Build holdings and totals for a paper account with bounded concurrency."""
    balances = load_paper_balances(account)
    btc_usd_price = await get_public_btc_usd_price()
    semaphore = asyncio.Semaphore(PAPER_PRICE_CONCURRENCY)

    tasks = [
        _get_asset_valuation(currency, amount, btc_usd_price, semaphore)
        for currency, amount in balances.items()
        if amount > 0
    ]
    valuations = await asyncio.gather(*tasks) if tasks else []

    total_usd_value = sum(float(item["usd_value"]) for item in valuations)
    total_btc_value = sum(float(item["btc_value"]) for item in valuations)

    holdings = []
    for item in valuations:
        holdings.append({
            "asset": item["asset"],
            "total_balance": item["amount"],
            "available": item["amount"],
            "hold": 0.0,
            "current_price_usd": item["current_price_usd"],
            "usd_value": item["usd_value"],
            "btc_value": item["btc_value"],
            "percentage": 0.0,
        })

    for holding in holdings:
        if total_usd_value > 0:
            holding["percentage"] = (holding["usd_value"] / total_usd_value) * 100

    return {
        "btc_usd_price": btc_usd_price,
        "total_usd_value": total_usd_value,
        "total_btc_value": total_btc_value,
        "holdings": holdings,
        "holdings_count": len(holdings),
    }
