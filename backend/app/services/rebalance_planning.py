"""
Pure rebalance-planning helpers, extracted from rebalance_monitor.

Stateless functions that compute allocations, plan top-up / rebalance / dust-sweep
trades, and reconcile position-locked balances. No I/O state — the RebalanceMonitor
class (in rebalance_monitor) imports and orchestrates these.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.timeutil import utcnow

logger = logging.getLogger(__name__)

EXCHANGE_MIN_USD = 1.0
DEFAULT_MIN_TRADE_PCT = 2.0  # Default: only trade if shift is >= 2% of portfolio
TARGET_CURRENCIES = {"USD", "BTC", "ETH", "USDC"}
DUST_SWEEP_INTERVAL_DAYS = 30


def calculate_current_allocations(
    free_balances: Dict[str, float],
    prices: Dict[str, float],
) -> dict:
    """Calculate current allocation percentages from free balances.

    Args:
        free_balances: {"USD": amount, "BTC": amount, "ETH": amount, "USDC": amount}
        prices: {"BTC-USD": price, "ETH-USD": price, "USDC-USD": price}

    Returns:
        {"usd_pct": float, "btc_pct": float, "eth_pct": float,
         "usdc_pct": float, "total_value_usd": float}
    """
    usd_value = free_balances.get("USD", 0.0)
    btc_value = free_balances.get("BTC", 0.0) * prices.get("BTC-USD", 0.0)
    eth_value = free_balances.get("ETH", 0.0) * prices.get("ETH-USD", 0.0)
    usdc_value = free_balances.get("USDC", 0.0) * prices.get("USDC-USD", 1.0)

    total = usd_value + btc_value + eth_value + usdc_value

    if total <= 0:
        return {
            "usd_pct": 0.0,
            "btc_pct": 0.0,
            "eth_pct": 0.0,
            "usdc_pct": 0.0,
            "total_value_usd": 0.0,
        }

    return {
        "usd_pct": (usd_value / total) * 100,
        "btc_pct": (btc_value / total) * 100,
        "eth_pct": (eth_value / total) * 100,
        "usdc_pct": (usdc_value / total) * 100,
        "total_value_usd": total,
    }


def needs_rebalance(
    current: Dict[str, float],
    targets: Dict[str, float],
    threshold: float = 5.0,
) -> bool:
    """Check if any currency allocation drifts beyond the threshold.

    Returns True only if drift strictly exceeds the threshold.
    """
    for key in ("usd_pct", "btc_pct", "eth_pct", "usdc_pct"):
        drift = abs(current[key] - targets[key])
        if drift > threshold:
            return True
    return False


def plan_topup_trades(
    free_balances: Dict[str, float],
    min_balances: Dict[str, float],
    prices: Dict[str, float],
    min_usd_by_currency: Optional[Dict[str, float]] = None,
) -> List[dict]:
    """Plan trades to top up currencies that are below their minimum reserve.

    A *minimum* reserve is honored even when the exact shortfall is smaller than
    the exchange's minimum order size: the top-up is rounded UP to that minimum,
    buying the smallest valid order and overshooting the reserve slightly (e.g.
    a $0.70 shortfall on a 5-USDC reserve buys $1 → 5.30 USDC). The small surplus
    is not later sold off, because it too falls below the sell minimum and selling
    more would breach the reserve.

    Funds are sourced largest-donor-first (never from a currency that is itself
    at/below its own reserve) so that every resulting order clears the exchange
    minimum — proportional splitting could otherwise produce sub-minimum,
    un-placeable pieces. If available funds can't cover even one minimum order, no
    top-up is attempted.

    Returns a list of trade dicts (same format as plan_trades).
    """
    _mins = min_usd_by_currency or {}

    def _min_for(currency: str) -> float:
        return max(_mins.get(currency, EXCHANGE_MIN_USD), EXCHANGE_MIN_USD)

    # Price lookup helper: convert currency amount to USD
    def to_usd(currency: str, amount: float) -> float:
        if currency == "USD":
            return amount
        pair = f"{currency}-USD" if currency != "USDC" else "USDC-USD"
        return amount * prices.get(pair, 1.0 if currency == "USDC" else 0.0)

    # Find currencies with deficits, rounding each UP to the currency's real
    # exchange minimum so a sub-minimum shortfall is still honored.
    deficits = {}  # currency -> top-up target in USD
    for currency, min_bal in min_balances.items():
        if min_bal <= 0:
            continue
        free = free_balances.get(currency, 0.0)
        if free < min_bal:
            deficit_usd = to_usd(currency, min_bal - free)
            if deficit_usd > 0:
                deficits[currency] = max(deficit_usd, _min_for(currency))

    if not deficits:
        return []

    trades = []

    for deficit_currency, topup_usd in deficits.items():
        # Calculate available USD-equivalent from all non-deficit currencies
        donors = {}
        for currency, free in free_balances.items():
            if currency == deficit_currency or free <= 0:
                continue
            # Don't source from currencies that are themselves below minimum
            min_bal = min_balances.get(currency, 0.0)
            available = max(0.0, free - min_bal) if min_bal > 0 else free
            available_usd = to_usd(currency, available)
            if available_usd > 0:
                donors[currency] = available_usd

        if not donors:
            continue

        # Cap the top-up to what's actually available.
        actual = min(topup_usd, sum(donors.values()))
        floor = _min_for(deficit_currency)

        # Source largest-donor-first so each order clears the exchange minimum.
        remaining = actual
        for donor_currency, donor_usd in sorted(
            donors.items(), key=lambda kv: kv[1], reverse=True
        ):
            if remaining < floor:
                break
            chunk = min(donor_usd, remaining)
            if chunk < floor:
                continue

            product_id, side = _get_trade_params(donor_currency, deficit_currency)
            trades.append({
                "from_currency": donor_currency,
                "to_currency": deficit_currency,
                "usd_amount": round(chunk, 2),
                "product_id": product_id,
                "side": side,
            })
            remaining -= chunk

    return trades


async def get_min_usd_by_currency(
    client, currencies: Iterable[str] = ("BTC", "ETH", "USDC")
) -> Dict[str, float]:
    """Real per-product minimum order size (USD) for each rebalanceable currency.

    Each currency's ``X-USD`` product minimum is read live from the exchange via
    order_validation.get_product_minimums (cached) and floored at EXCHANGE_MIN_USD.
    For an ``X-USD`` product the quote currency IS USD, so ``quote_min_size`` is
    already a USD notional. USD itself is held as cash (no market) → the floor.
    """
    from app.order_validation import get_product_minimums

    mins = {"USD": EXCHANGE_MIN_USD}
    for currency in currencies:
        quote_min = 0.0
        try:
            m = await get_product_minimums(client, f"{currency}-USD")
            quote_min = float(m.get("quote_min_size", 0) or 0)
        except Exception as e:
            logger.debug("Rebalance: min lookup failed for %s-USD: %s", currency, e)
        mins[currency] = max(quote_min, EXCHANGE_MIN_USD)
    return mins


def plan_trades(
    free_balances: Dict[str, float],
    targets: Dict[str, float],
    prices: Dict[str, float],
    min_trade_pct: float = DEFAULT_MIN_TRADE_PCT,
    aggregate: Optional[Dict[str, float]] = None,
    min_usd_by_currency: Optional[Dict[str, float]] = None,
) -> List[dict]:
    """Plan trades to rebalance from current to target allocations.

    Deltas are computed against the AGGREGATE portfolio (free + locked in positions)
    when `aggregate` is provided. This ensures trades move in the correct direction
    even when bot positions cause free balances to diverge from aggregate totals.
    For example, BTC acquired by bots inflates the free BTC wallet but is deducted
    from the BTC aggregate to avoid double-counting — without aggregate-awareness,
    plan_trades would (incorrectly) see free BTC as overweight and sell it.

    All trade amounts are in USD-equivalent terms, even for BTC↔ETH trades.
    A trade is skipped unless it clears, for its currency, the larger of the
    churn guard (min_trade_pct % of the free portfolio) and that currency's real
    exchange minimum (``min_usd_by_currency``, fetched live; EXCHANGE_MIN_USD
    safety floor when absent).

    Args:
        free_balances: Tradeable balances by currency (native units).
        targets: Target allocation percentages {"usd_pct", "btc_pct", ...}.
        prices: Current market prices {"BTC-USD", "ETH-USD", "USDC-USD"}.
        min_trade_pct: Minimum trade size as % of total free portfolio.
        aggregate: Optional full portfolio balances (free + locked in positions).
            When provided, deltas are computed from aggregate so direction and
            magnitude are correct. When None, falls back to free-balance-only mode.
        min_usd_by_currency: Real per-currency minimum order size in USD (from
            get_min_usd_by_currency). When None, every currency uses the
            EXCHANGE_MIN_USD safety floor.

    Returns a list of trade dicts:
        {"from_currency": str, "to_currency": str, "usd_amount": float,
         "product_id": str, "side": str}
    """
    # Reference balances for computing deltas: aggregate if available, else free
    ref_balances = aggregate if aggregate is not None else free_balances
    ref_current = calculate_current_allocations(ref_balances, prices)
    total_ref = ref_current["total_value_usd"]

    free_current = calculate_current_allocations(free_balances, prices)
    total_free = free_current["total_value_usd"]

    if total_ref <= 0 or total_free <= 0:
        return []

    # Per-currency minimum trade size: the larger of the portfolio churn guard
    # (min_trade_pct of the free portfolio) and the currency's real exchange
    # minimum in USD (min_usd_by_currency, fetched live), falling back to the
    # absolute safety floor when a currency has no entry.
    churn_floor = total_free * min_trade_pct / 100.0
    _mins = min_usd_by_currency or {}

    def _min_for(currency: str) -> float:
        return max(churn_floor, _mins.get(currency, EXCHANGE_MIN_USD))

    # Calculate USD-denominated delta for each currency relative to reference
    # (aggregate when provided, else free).
    # Positive delta = underweight (need to buy), negative = overweight (need to sell)
    currencies = [
        ("USD", targets["usd_pct"]),
        ("BTC", targets["btc_pct"]),
        ("ETH", targets["eth_pct"]),
        ("USDC", targets["usdc_pct"]),
    ]

    # USD value of each currency's FREE balance (caps sell amounts)
    free_values = {
        "USD": free_balances.get("USD", 0.0),
        "BTC": free_balances.get("BTC", 0.0) * prices.get("BTC-USD", 0.0),
        "ETH": free_balances.get("ETH", 0.0) * prices.get("ETH-USD", 0.0),
        "USDC": free_balances.get("USDC", 0.0) * prices.get("USDC-USD", 1.0),
    }

    deltas = {}
    for currency, target_pct in currencies:
        current_pct = ref_current[f"{currency.lower()}_pct"]
        delta_usd = (target_pct - current_pct) / 100 * total_ref
        deltas[currency] = delta_usd

    # Identify overweight (sell) and underweight (buy) currencies
    # Cap sells to available free balance — can't sell more than you have
    sells = []
    for c, d in deltas.items():
        if d < -_min_for(c):
            sell_amount = min(-d, free_values.get(c, 0.0))
            if sell_amount >= _min_for(c):
                sells.append((c, sell_amount))
    buys = [(c, d) for c, d in deltas.items() if d > _min_for(c)]

    # Sort: largest sell first, largest buy first
    sells.sort(key=lambda x: x[1], reverse=True)
    buys.sort(key=lambda x: x[1], reverse=True)

    trades = []

    # Match sells to buys
    for sell_currency, sell_amount in sells:
        remaining_sell = sell_amount

        for i, (buy_currency, buy_amount) in enumerate(buys):
            if remaining_sell <= 0 or buy_amount <= 0:
                continue

            trade_usd = min(remaining_sell, buy_amount)
            if trade_usd < max(_min_for(sell_currency), _min_for(buy_currency)):
                continue

            product_id, side = _get_trade_params(sell_currency, buy_currency)

            trades.append({
                "from_currency": sell_currency,
                "to_currency": buy_currency,
                "usd_amount": trade_usd,
                "product_id": product_id,
                "side": side,
            })

            remaining_sell -= trade_usd
            buys[i] = (buy_currency, buy_amount - trade_usd)

    return trades


def sum_locked_base_amounts(positions: Iterable) -> Dict[str, float]:
    """Sum base-currency amounts held across open positions, keyed by base coin.

    A position's acquired base coin (e.g. the BTC from a BTC-USD deal) settles
    into the spot wallet as ordinary spendable balance — the exchange places no
    hold on filled coins — so the exchange "free" balance includes it. These
    amounts must be excluded from rebalanceable funds so the rebalancer never
    sells coins a bot is actively holding. Each position counts toward its base
    coin here and toward its QUOTE currency separately (via total_quote_spent).

    Returns {base_coin: total_base_acquired}, e.g. an open ADA-USD position with
    50 ADA acquired contributes {"ADA": 50.0}.
    """
    locked: Dict[str, float] = {}
    for pos in positions:
        if not pos.product_id or not pos.total_base_acquired:
            continue
        base_currency = pos.product_id.split("-")[0]
        locked[base_currency] = locked.get(base_currency, 0.0) + (
            pos.total_base_acquired or 0.0
        )
    return locked


async def get_position_locked_amounts(
    db: AsyncSession, account_id: int,
) -> Dict[str, float]:
    """Query open positions for an account and sum base coins locked in them.

    Thin DB wrapper around sum_locked_base_amounts (the single source of truth
    for the per-base-coin tally). Used by the dust sweeper; the main rebalance
    path reuses sum_locked_base_amounts directly on its already-fetched list.
    """
    from app.models import Position

    query = select(Position).where(
        Position.account_id == account_id,
        Position.status == "open",
    )
    result = await db.execute(query)
    return sum_locked_base_amounts(result.scalars().all())


def subtract_locked_amounts(
    balances: Dict[str, float],
    locked: Dict[str, float],
) -> Dict[str, float]:
    """Subtract position-locked amounts from balances, returning free amounts.

    Only includes coins with positive free balance.
    """
    free = {}
    for coin, amount in balances.items():
        free_amount = amount - locked.get(coin, 0.0)
        if free_amount > 0:
            free[coin] = free_amount
    return free


def should_dust_sweep(last_sweep_at: Optional[datetime]) -> bool:
    """Check if enough time has passed for another dust sweep.

    Returns True if last_sweep_at is None or >= DUST_SWEEP_INTERVAL_DAYS ago.
    """
    if last_sweep_at is None:
        return True
    elapsed = utcnow() - last_sweep_at
    return elapsed >= timedelta(days=DUST_SWEEP_INTERVAL_DAYS)


def plan_dust_sweeps(
    all_balances: Dict[str, float],
    targets: Dict[str, float],
    prices: Dict[str, float],
    available_products: Set[str],
    threshold_usd: float = 5.0,
) -> List[dict]:
    """Plan dust sweep trades for non-target currencies.

    Identifies coins not in TARGET_CURRENCIES whose USD value exceeds
    threshold_usd, and plans to sell each into the most underweight
    target currency.

    Args:
        all_balances: {coin: amount} for ALL coins in the account
        targets: {"usd_pct": float, "btc_pct": float, ...} target allocations
        prices: {pair: price} e.g. {"BTC-USD": 100000, "ADA-USD": 0.38}
        available_products: set of tradable product IDs e.g. {"ADA-USD", "ADA-BTC"}
        threshold_usd: minimum USD value to sweep a dust position

    Returns:
        List of dicts: {"coin", "amount", "usd_value", "product_id",
                        "side", "target_currency"}
    """
    # Calculate current allocation to find most underweight target
    target_balances = {c: all_balances.get(c, 0.0) for c in TARGET_CURRENCIES}
    current = calculate_current_allocations(target_balances, prices)
    total_usd = current["total_value_usd"]

    # Find most underweight target currency
    if total_usd > 0:
        deficits = []
        for currency in TARGET_CURRENCIES:
            key = f"{currency.lower()}_pct"
            target_pct = targets.get(key, 0.0)
            current_pct = current.get(key, 0.0)
            deficit = target_pct - current_pct  # positive = underweight
            deficits.append((currency, deficit))
        deficits.sort(key=lambda x: x[1], reverse=True)
        most_underweight = deficits[0][0]
    else:
        most_underweight = "USD"  # fallback

    sweeps = []

    for coin, amount in all_balances.items():
        if coin in TARGET_CURRENCIES or amount <= 0:
            continue

        # Price the dust coin in USD
        usd_price = prices.get(f"{coin}-USD", 0.0)
        if usd_price <= 0:
            continue

        usd_value = amount * usd_price
        if usd_value < threshold_usd:
            continue

        # Find the best trading pair: prefer direct pair to underweight currency
        product_id = None
        target_currency = None

        # Try direct pair to most underweight currency first
        if most_underweight != "USD":
            direct_pair = f"{coin}-{most_underweight}"
            if direct_pair in available_products:
                product_id = direct_pair
                target_currency = most_underweight

        # Fall back to {COIN}-USD
        if product_id is None:
            usd_pair = f"{coin}-USD"
            if usd_pair in available_products:
                product_id = usd_pair
                target_currency = "USD"

        if product_id is None:
            continue  # No tradable pair

        sweeps.append({
            "coin": coin,
            "amount": amount,
            "usd_value": round(usd_value, 2),
            "product_id": product_id,
            "side": "SELL",
            "target_currency": target_currency,
        })

    # Sort by USD value descending (sweep largest dust first)
    sweeps.sort(key=lambda s: s["usd_value"], reverse=True)
    return sweeps


def _get_trade_params(from_currency: str, to_currency: str) -> Tuple[str, str]:
    """Determine product_id and side for a currency conversion.

    Returns (product_id, side).
    """
    # USD↔USDC and other cross pairs are routed by _execute_trade via a BTC
    # intermediary (e.g. USD→BTC→USDC), not a single market order; these entries
    # let the plan functions build the trade dicts.
    pair_map = {
        ("USD", "BTC"): ("BTC-USD", "BUY"),
        ("BTC", "USD"): ("BTC-USD", "SELL"),
        ("USD", "ETH"): ("ETH-USD", "BUY"),
        ("ETH", "USD"): ("ETH-USD", "SELL"),
        ("BTC", "ETH"): ("ETH-BTC", "BUY"),
        ("ETH", "BTC"): ("ETH-BTC", "SELL"),
        ("USD", "USDC"): ("USDC-USD", "BUY"),
        ("USDC", "USD"): ("USDC-USD", "SELL"),
        ("BTC", "USDC"): ("BTC-USDC", "SELL"),
        ("USDC", "BTC"): ("BTC-USDC", "BUY"),
        ("ETH", "USDC"): ("ETH-USDC", "SELL"),
        ("USDC", "ETH"): ("ETH-USDC", "BUY"),
    }
    return pair_map[(from_currency, to_currency)]
