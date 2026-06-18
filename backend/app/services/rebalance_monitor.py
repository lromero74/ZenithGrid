"""
Portfolio Rebalance Monitor Service

Periodically checks each account's free USD/BTC/ETH/USDC allocation against
configured targets and executes market trades to rebalance when any
currency drifts beyond the threshold.

Settings are per-account (stored on the Account model). Only genuinely-free
balances are rebalanced: coins acquired by open bot positions are subtracted
from the wallet balance first (the exchange does not hold filled coins), so a
position's coins are never sold out from under the bot. A position's deployed
capital still counts toward its quote currency at cost.
"""

import asyncio
import json
from app.utils.timeutil import utcnow
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Position
from app.precision import format_base_amount
from app.services.realmoney_audit import set_subsystem
from app.services.exchange_service import get_exchange_client_for_account
from app.services.session_maker_mixin import SessionMakerMixin

logger = logging.getLogger(__name__)

# Max concurrent dust price lookups — parallelize the per-coin price fetches
# while staying well under exchange rate limits.
DUST_PRICE_CONCURRENCY = 8

# Absolute safety floor for a single rebalance order. The real per-product
# minimum is fetched live from the exchange (order_validation.get_product_minimums)
# and takes precedence when higher; this floor only guards against the API
# reporting a sub-cent granularity value (Coinbase spot exposes ~$0.00000001 as
# quote_min_size, which is not a usable notional). Previously a flat $10 — that is
# the Coinbase *perps* notional, not spot, and wrongly blocked small spot sells.
EXCHANGE_MIN_USD = 1.0
DEFAULT_MIN_TRADE_PCT = 2.0  # Default: only trade if shift is >= 2% of portfolio
TARGET_CURRENCIES = {"USD", "BTC", "ETH", "USDC"}
DUST_SWEEP_INTERVAL_DAYS = 30

# ---------------------------------------------------------------------------
# Per-account allocation cache (written by rebalance monitor, read by bot gate)
# ---------------------------------------------------------------------------

# {account_id: (timestamp, {"agg_current": {...}, "targets": {...}, "threshold": float})}
_allocation_cache: Dict[int, Tuple[datetime, dict]] = {}
_CACHE_TTL_SECONDS = 21600  # 6 hours — covers the longest rebalancer check interval (4h) + buffer


def set_account_gate_data(account_id: int, data: dict) -> None:
    """Store fresh allocation data for the bot-gate lookup."""
    _allocation_cache[account_id] = (utcnow(), data)


def get_account_gate_data(account_id: int) -> Optional[dict]:
    """Return cached allocation data. None if missing or older than TTL."""
    entry = _allocation_cache.get(account_id)
    if not entry:
        return None
    ts, payload = entry
    if (utcnow() - ts).total_seconds() > _CACHE_TTL_SECONDS:
        return None
    return payload


def clear_account_gate_data(account_id: int) -> None:
    """Invalidate the gate cache for one account.

    Called when the user disables portfolio rebalancing on the account.
    Without this, the monitor's 6h-stale cache would continue flagging bots
    as overweight even though no new data will ever be written (the
    rebalancer service is off).  See multi_bot_monitor.py for the gate logic.
    """
    _allocation_cache.pop(account_id, None)


def quote_is_overweight(account_id: int, quote_currency: str) -> bool:
    """Check if a bot's quote currency is overweight for the given account.

    Uses the deployable-pool allocation (reserves already subtracted) so that
    reserve balances don't count as driftable allocation.

    Returns False (fail-open) when no fresh cache data is available.
    """
    gate_data = get_account_gate_data(account_id)
    if not gate_data:
        return False
    agg_current = gate_data.get("agg_current", {})
    targets = gate_data.get("targets", {})
    threshold = gate_data.get("threshold", 5.0)
    key = f"{quote_currency.lower()}_pct"
    current_pct = agg_current.get(key, 0.0)
    target_pct = targets.get(key, 0.0)
    return current_pct > target_pct + threshold


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
    # USD↔USDC: _execute_trade uses convert_currency() instead of market orders,
    # but plan functions still need these entries to build trade dicts.
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


class RebalanceMonitor(SessionMakerMixin):
    """Background service that rebalances account allocations."""

    def __init__(self):
        self._account_timers: Dict[int, datetime] = {}
        self._processing: set = set()  # Account IDs currently being processed
        # Protects _account_timers against concurrent access from cleanup_in_memory_caches().
        self._account_timers_lock = threading.Lock()

    async def run_once(self):
        """Check all accounts once. Called by APScheduler every 30 seconds."""
        try:
            await self._check_accounts()
        except Exception as e:
            logger.error(f"Error in rebalance monitor: {e}", exc_info=True)

    def cleanup_stale_entries(self, active_account_ids: set) -> dict:
        """Remove tracking entries for accounts that are no longer active.

        Called from the main loop while the monitor may run on the secondary loop,
        so _account_timers_lock must be held for any dict mutation.
        """
        with self._account_timers_lock:
            stale = [aid for aid in self._account_timers if aid not in active_account_ids]
            for aid in stale:
                del self._account_timers[aid]
                self._processing.discard(aid)
        return {"timers_pruned": len(stale)}

    async def _check_accounts(self):
        async with self._get_sm()() as db:
            query = select(Account).where(Account.rebalance_enabled.is_(True))
            result = await db.execute(query)
            accounts = result.scalars().all()

            for account in accounts:
                if self._should_check_account(account):
                    await self._process_account(account, db)

    def _should_check_account(self, account: Account) -> bool:
        now = utcnow()
        last_check = self._account_timers.get(account.id)
        if not last_check:
            return True
        interval_min = account.rebalance_check_interval_minutes
        interval_seconds = (interval_min if interval_min is not None else 60) * 60
        return (now - last_check).total_seconds() >= interval_seconds

    async def _process_account(self, account, db: AsyncSession):
        """Process one account — check allocations and rebalance if needed."""
        if not account.rebalance_enabled:
            return

        if account.id in self._processing:
            return  # Already processing this account

        self._processing.add(account.id)
        try:
            client = await get_exchange_client_for_account(db, account.id, session_maker=self._get_sm())
            if not client:
                logger.warning(
                    f"Rebalance: no exchange client for account {account.id}"
                )
                return

            # Fetch current prices
            prices = {}
            for product_id in ("BTC-USD", "ETH-USD", "USDC-USD"):
                try:
                    price = await client.get_current_price(product_id)
                    prices[product_id] = float(price)
                except Exception as e:
                    if product_id == "USDC-USD":
                        # USDC is pegged ~1:1, safe fallback
                        prices[product_id] = 1.0
                        logger.debug(
                            f"Rebalance: USDC-USD price fetch failed, using 1.0: {e}"
                        )
                    else:
                        logger.error(
                            f"Rebalance: could not get price for {product_id}: {e}"
                        )
                        return  # Can't rebalance without BTC/ETH prices

            # Free balances — needed for both top-up and rebalancing
            free_balances = {}
            balance_methods = {
                "USD": client.get_usd_balance,
                "BTC": client.get_btc_balance,
                "ETH": client.get_eth_balance,
                "USDC": client.get_usdc_balance,
            }
            for currency, method in balance_methods.items():
                try:
                    free_balances[currency] = float(await method())
                except Exception as e:
                    # Skip this currency entirely rather than setting 0.0.
                    # Setting 0.0 would make the rebalancer see it as
                    # severely underweight and buy it — causing unnecessary
                    # trades and fees when the real balance is substantial.
                    logger.warning(
                        f"Rebalance: could not get free {currency} "
                        f"for account {account.id}: {e} — skipping currency"
                    )

            # Phase 0: Dust sweep (monthly or on-demand)
            if (account.dust_sweep_enabled
                    and should_dust_sweep(account.dust_last_sweep_at)):
                swept = await self._sweep_dust(
                    client, account, db, prices, free_balances
                )
                if swept:
                    # Balances are stale after sweeps; skip rebalancing this cycle
                    with self._account_timers_lock:
                        self._account_timers[account.id] = utcnow()
                    return

            # Load minimum balance reserves
            min_balances = {
                "USD": account.min_balance_usd or 0.0,
                "BTC": account.min_balance_btc or 0.0,
                "ETH": account.min_balance_eth or 0.0,
                "USDC": account.min_balance_usdc or 0.0,
            }

            # Real per-product minimums, used by both the reserve top-up and the
            # drift rebalance so every order respects the exchange's actual limits.
            min_usd_by_currency = await get_min_usd_by_currency(client)

            # Phase 1: Top-up currencies below their minimum reserve.
            # This runs BEFORE drift detection — reserves must be
            # maintained even when the portfolio is within threshold.
            topup_trades = plan_topup_trades(
                free_balances, min_balances, prices,
                min_usd_by_currency=min_usd_by_currency,
            )
            if topup_trades:
                logger.info(
                    f"Rebalance: executing {len(topup_trades)} top-up "
                    f"trade(s) for account {account.name}"
                )
                for trade in topup_trades:
                    await self._execute_trade(
                        client, account, trade, prices
                    )
                # Skip normal rebalancing this cycle — balances are stale
                # after top-up trades. Next cycle will rebalance if needed.
                self._account_timers[account.id] = utcnow()
                return

            # Phase 2: Build portfolio-composition view — free_balances +
            # capital locked in open positions (grouped by quote currency).
            # This matches the UI rebalance-status display and the portfolio
            # breakdown from the Coinbase API.
            # Do NOT use calculate_market_budget: it returns the accounts-API
            # available_balance which diverges significantly from the portfolio
            # breakdown value (e.g., $59 vs $411 for BTC with open positions).
            pos_result = await db.execute(
                select(Position).where(
                    Position.account_id == account.id,
                    Position.status == "open",
                )
            )
            open_positions_list = pos_result.scalars().all()

            # Coins acquired by open positions sit in the spot wallet as
            # spendable balance (the exchange holds nothing on filled coins), so
            # the exchange "free" balance includes them. Subtract them here,
            # before BOTH the drift view and the sell caps are built, so the
            # rebalancer can never liquidate coins a bot is actively holding.
            # Their deployed cost is still counted toward the position's QUOTE
            # currency below (total_quote_spent), so e.g. a USD bot's BTC counts
            # as USD-at-cost, not as sellable BTC. (Top-up/dust phases above run
            # on the raw wallet balance and return early, so they're unaffected.)
            locked_base = sum_locked_base_amounts(open_positions_list)
            free_balances = {
                c: max(0.0, free_balances[c] - locked_base.get(c, 0.0))
                for c in free_balances
            }

            portfolio_balances: Dict[str, float] = dict(free_balances)
            for pos in open_positions_list:
                pid = pos.product_id or ""
                parts = pid.split("-")
                if len(parts) != 2:
                    continue
                _, quote_cur = parts
                if quote_cur not in portfolio_balances:
                    continue
                portfolio_balances[quote_cur] += pos.total_quote_spent or 0.0

            targets = {
                "usd_pct": account.rebalance_target_usd_pct if account.rebalance_target_usd_pct is not None else 34.0,
                "btc_pct": account.rebalance_target_btc_pct if account.rebalance_target_btc_pct is not None else 33.0,
                "eth_pct": account.rebalance_target_eth_pct if account.rebalance_target_eth_pct is not None else 33.0,
                "usdc_pct": account.rebalance_target_usdc_pct if account.rebalance_target_usdc_pct is not None else 0.0,
            }
            drift_thresh = account.rebalance_drift_threshold_pct
            threshold = drift_thresh if drift_thresh is not None else 5.0

            # Subtract reserves from free balances (what's actually tradeable)
            rebalanceable = {
                c: max(0.0, free_balances[c] - min_balances[c])
                for c in free_balances
            }

            # Reserve-adjusted portfolio for direction/magnitude reference.
            # Targets apply to the investable portion only (portfolio minus reserves).
            # Drift detection uses this too — reserve balances don't count as driftable
            # allocation, so comparing full-portfolio % against targets would produce
            # false positives when a reserve is held in an "untargeted" currency.
            rebalanceable_agg: Dict[str, float] = {
                c: max(0.0, portfolio_balances.get(c, 0.0) - min_balances.get(c, 0.0))
                for c in portfolio_balances
            }

            agg_current = calculate_current_allocations(rebalanceable_agg, prices)

            # Populate the bot-gate cache so multi_bot_monitor can check overweight
            # status without extra exchange calls.
            set_account_gate_data(account.id, {
                "agg_current": agg_current,
                "targets": targets,
                "threshold": threshold,
            })

            if not needs_rebalance(agg_current, targets, threshold):
                logger.debug(
                    f"Rebalance: account {account.name} within threshold "
                    f"(USD={agg_current['usd_pct']:.1f}%, "
                    f"BTC={agg_current['btc_pct']:.1f}%, "
                    f"ETH={agg_current['eth_pct']:.1f}%, "
                    f"USDC={agg_current['usdc_pct']:.1f}%)"
                )
                self._account_timers[account.id] = utcnow()
                return

            current = calculate_current_allocations(portfolio_balances, prices)
            logger.debug(
                f"Rebalance plan inputs — account {account.name}: "
                f"portfolio USD={agg_current['usd_pct']:.1f}% "
                f"BTC={agg_current['btc_pct']:.1f}% "
                f"ETH={agg_current['eth_pct']:.1f}% "
                f"USDC={agg_current['usdc_pct']:.1f}% "
                f"(total ${agg_current['total_value_usd']:.0f}); "
                f"rebalanceable USD={rebalanceable.get('USD', 0):.2f} "
                f"BTC={rebalanceable.get('BTC', 0):.6f} "
                f"USDC={rebalanceable.get('USDC', 0):.2f}"
            )

            min_trade = account.rebalance_min_trade_pct
            min_pct = min_trade if min_trade is not None else DEFAULT_MIN_TRADE_PCT
            trades = plan_trades(
                rebalanceable, targets, prices,
                min_trade_pct=min_pct,
                aggregate=rebalanceable_agg,
                min_usd_by_currency=min_usd_by_currency,
            )

            if not trades:
                logger.debug(
                    f"Rebalance: no actionable trades for account "
                    f"{account.name}"
                )
                self._account_timers[account.id] = utcnow()
                return

            logger.info(
                f"Rebalance: executing {len(trades)} trade(s) for account "
                f"{account.name} — current: USD={current['usd_pct']:.1f}%, "
                f"BTC={current['btc_pct']:.1f}%, "
                f"ETH={current['eth_pct']:.1f}%, "
                f"USDC={current['usdc_pct']:.1f}%"
            )

            for trade in trades:
                await self._execute_trade(client, account, trade, prices)

            with self._account_timers_lock:
                self._account_timers[account.id] = utcnow()

        except Exception as e:
            logger.error(
                f"Rebalance failed for account {account.id}: {e}", exc_info=True
            )
        finally:
            self._processing.discard(account.id)

    async def _execute_trade(self, client, account, trade: dict, prices: dict):
        """Execute a single rebalance trade."""
        try:
            set_subsystem("rebalancer")
            product_id = trade["product_id"]
            side = trade["side"]
            usd_amount = trade["usd_amount"]

            # Reserve 1% for fees (same as auto-buy)
            usd_amount = round(usd_amount * 0.99, 2)

            # Hard safety floor — the exchange API often reports a sub-cent
            # quote_min_size (granularity, not a usable notional), so a flat floor
            # is still needed below the real per-product minimum.
            if usd_amount < EXCHANGE_MIN_USD:
                return

            # Execution backstop: also honor the product's real exchange minimum.
            # The rebalancer places market orders directly, bypassing the
            # trading-engine validators, so validate the notional here.
            from app.order_validation import validate_order_size
            is_valid, err = await validate_order_size(
                client, product_id, quote_amount=usd_amount
            )
            if not is_valid:
                logger.info(
                    "Rebalance: skipping below-minimum %s ~$%.2f: %s",
                    product_id, usd_amount, err,
                )
                return

            from_curr = trade["from_currency"]
            to_curr = trade["to_currency"]

            # USD↔USDC: no direct market pair — route via BTC as intermediary.
            # The Coinbase convert endpoint is unreliable for fiat↔stablecoin;
            # USD→BTC and BTC→USDC are both proven market-order paths.
            if {from_curr, to_curr} == {"USD", "USDC"}:
                btc_price = prices.get("BTC-USD", 0.0)
                if btc_price <= 0:
                    logger.warning(
                        f"Rebalance: {from_curr}→{to_curr} skipped — "
                        f"no BTC-USD price available for intermediary route"
                    )
                    return
                btc_amount = round(usd_amount / btc_price, 8)
                if from_curr == "USD":
                    # USD → BTC → USDC
                    r1 = await client.buy_with_usd(usd_amount, "BTC-USD")
                    self._log_trade_result(r1, {**trade, "to_currency": "BTC"}, account)
                    if not r1.get("success_response"):
                        return
                    try:
                        result = await client.create_market_order(
                            product_id="BTC-USDC",
                            side="SELL",
                            size=f"{btc_amount:.8f}",
                        )
                    except Exception:
                        logger.error(
                            "Rebalance: USD→USDC second leg (BTC→USDC sell) failed — "
                            "portfolio left in intermediate state (BTC). "
                            "Attempting rollback: selling BTC back to USD.",
                            exc_info=True,
                        )
                        # Attempt rollback: sell the BTC back to USD
                        try:
                            rollback = await client.sell_for_usd(btc_amount, "BTC-USD")
                            self._log_trade_result(
                                rollback,
                                {**trade, "from_currency": "BTC", "to_currency": "USD"},
                                account,
                            )
                            logger.warning(
                                "Rebalance: USD→USDC rollback completed — "
                                "BTC sold back to USD, portfolio restored"
                            )
                        except Exception:
                            logger.error(
                                "Rebalance: USD→USDC rollback ALSO failed — "
                                "portfolio stuck in BTC. Manual intervention required.",
                                exc_info=True,
                            )
                        return
                else:
                    # USDC → BTC → USD
                    r1 = await client.create_market_order(
                        product_id="BTC-USDC",
                        side="BUY",
                        funds=f"{usd_amount:.2f}",
                    )
                    self._log_trade_result(r1, {**trade, "from_currency": "USDC", "to_currency": "BTC"}, account)
                    if not r1.get("success_response"):
                        return
                    try:
                        result = await client.sell_for_usd(btc_amount, "BTC-USD")
                    except Exception:
                        logger.error(
                            "Rebalance: USDC→USD second leg (BTC→USD sell) failed — "
                            "portfolio left in intermediate state (BTC). "
                            "Attempting rollback: buying USDC back with BTC.",
                            exc_info=True,
                        )
                        # Attempt rollback: buy USDC back with the BTC
                        try:
                            rollback = await client.create_market_order(
                                product_id="BTC-USDC",
                                side="BUY",
                                funds=f"{usd_amount:.2f}",
                            )
                            self._log_trade_result(
                                rollback,
                                {**trade, "from_currency": "BTC", "to_currency": "USDC"},
                                account,
                            )
                            logger.warning(
                                "Rebalance: USDC→USD rollback completed — "
                                "USDC bought back, portfolio restored"
                            )
                        except Exception:
                            logger.error(
                                "Rebalance: USDC→USD rollback ALSO failed — "
                                "portfolio stuck in BTC. Manual intervention required.",
                                exc_info=True,
                            )
                        return
                self._log_trade_result(result, trade, account)
                return

            if side == "BUY" and from_curr == "USD":
                # Buying BTC or ETH with USD
                result = await client.buy_with_usd(usd_amount, product_id)
            elif side == "SELL" and to_curr == "USD":
                # Selling BTC or ETH for USD
                price = prices.get(product_id, 0)
                if price <= 0:
                    return
                base_amount = usd_amount / price
                result = await client.sell_for_usd(base_amount, product_id)
            elif product_id in ("BTC-USDC", "ETH-USDC"):
                # BTC↔USDC or ETH↔USDC via market order
                if side == "BUY":
                    # Buying BTC/ETH with USDC (funds in USDC)
                    result = await client.create_market_order(
                        product_id=product_id,
                        side="BUY",
                        funds=f"{usd_amount:.2f}",
                    )
                else:
                    # Selling BTC/ETH for USDC
                    base = product_id.split("-")[0]  # BTC or ETH
                    base_price = prices.get(f"{base}-USD", 0)
                    if base_price <= 0:
                        return
                    base_amount = usd_amount / base_price
                    result = await client.create_market_order(
                        product_id=product_id,
                        side="SELL",
                        size=f"{base_amount:.8f}",
                    )
            else:
                # BTC↔ETH via ETH-BTC pair
                if side == "BUY":
                    # Buying ETH with BTC
                    btc_price = prices.get("BTC-USD", 100000.0)
                    btc_amount = usd_amount / btc_price
                    result = await client.create_market_order(
                        product_id=product_id,
                        side="BUY",
                        funds=f"{btc_amount:.8f}",
                    )
                else:
                    # Selling ETH for BTC
                    eth_price = prices.get("ETH-USD", 2500.0)
                    eth_amount = usd_amount / eth_price
                    result = await client.create_market_order(
                        product_id=product_id,
                        side="SELL",
                        size=f"{eth_amount:.8f}",
                    )

            self._log_trade_result(result, trade, account)

        except Exception as e:
            logger.error(
                f"Error executing rebalance trade for account "
                f"{account.name}: {e}",
                exc_info=True,
            )

    def _log_trade_result(self, result: dict, trade: dict, account):
        """Log success or failure for a rebalance trade/convert."""
        success = result.get("success_response", {})
        order_id = success.get("order_id", "")

        if order_id:
            logger.info(
                f"Rebalance trade executed: {trade['from_currency']} → "
                f"{trade['to_currency']} ~${trade['usd_amount']:.2f} "
                f"(Account: {account.name}, Order: {order_id})"
            )
        else:
            error = result.get("error_response", {})
            error_msg = (
                error.get("message")
                or error.get("error")
                or error.get("preview_failure_reason")
                or f"Unknown failure — raw: {result}"
            )
            logger.warning(
                f"Rebalance trade skipped: {trade['from_currency']} → "
                f"{trade['to_currency']} ~${trade['usd_amount']:.2f} "
                f"(Account: {account.name}): {error_msg}"
            )

    async def _price_dust_coins(self, client, coins: list, prices: dict) -> None:
        """Fetch USD prices for ``coins`` concurrently (bounded) into ``prices``.

        Mutates ``prices`` in place, adding ``{coin}-USD`` keys. Coins that can't
        be priced (no market / API error) are silently skipped, matching the prior
        behavior — only the serial round-trips become bounded-concurrent.
        """
        if not coins:
            return
        sem = asyncio.Semaphore(DUST_PRICE_CONCURRENCY)

        async def _price_one(coin):
            async with sem:
                try:
                    p = await client.get_current_price(f"{coin}-USD")
                    return coin, float(p)
                except Exception:
                    return coin, None  # Can't price it, will be skipped

        for coin, price in await asyncio.gather(*(_price_one(c) for c in coins)):
            if price is not None:
                prices[f"{coin}-USD"] = price

    async def _sweep_dust(
        self, client, account, db: AsyncSession,
        prices: dict, free_balances: dict,
    ) -> List[dict]:
        """Sweep non-target dust positions into the most underweight currency.

        Returns list of executed sweep results.
        """
        try:
            set_subsystem("dust_sweep")
            # Get all balances (paper or live)
            if account.is_paper_trading:
                all_balances = (
                    json.loads(account.paper_balances)
                    if account.paper_balances else {}
                )
            else:
                all_balances = {}
                try:
                    accounts_data = await client.get_accounts()
                    for acct in accounts_data:
                        currency = acct.get("currency", "")
                        available = float(
                            acct.get("available_balance", {}).get("value", 0)
                        )
                        if available > 0:
                            all_balances[currency] = available
                except Exception:
                    # Fallback: use known free balances only
                    all_balances = free_balances.copy()

            # Subtract amounts locked in open positions — don't sweep
            # coins that bots are actively trading
            locked = await get_position_locked_amounts(db, account.id)
            all_balances = subtract_locked_amounts(all_balances, locked)

            # Subtract minimum-balance reserves — a coin held back as a reserve is
            # not "free" and must never be swept (e.g. a USDT spending reserve).
            reserves = {
                "USD": account.min_balance_usd or 0.0,
                "BTC": account.min_balance_btc or 0.0,
                "ETH": account.min_balance_eth or 0.0,
                "USDC": account.min_balance_usdc or 0.0,
                "USDT": account.min_balance_usdt or 0.0,
            }
            all_balances = subtract_locked_amounts(all_balances, reserves)

            # Fetch prices for dust coins
            dust_coins = {
                c for c in all_balances
                if c not in TARGET_CURRENCIES and all_balances[c] > 0
            }
            # Price the unpriced dust coins concurrently (bounded) instead of one
            # serial round-trip each — the wall-clock was O(coins) × API latency.
            coins_to_price = [c for c in dust_coins if f"{c}-USD" not in prices]
            await self._price_dust_coins(client, coins_to_price, prices)

            # Get available products
            available_products = set()
            try:
                products = await client.list_products()
                for p in products:
                    pid = p.get("product_id", "")
                    if pid:
                        available_products.add(pid)
            except Exception:
                pass

            targets = {
                "usd_pct": account.rebalance_target_usd_pct if account.rebalance_target_usd_pct is not None else 34.0,
                "btc_pct": account.rebalance_target_btc_pct if account.rebalance_target_btc_pct is not None else 33.0,
                "eth_pct": account.rebalance_target_eth_pct if account.rebalance_target_eth_pct is not None else 33.0,
                "usdc_pct": account.rebalance_target_usdc_pct if account.rebalance_target_usdc_pct is not None else 0.0,
            }

            # Sweep everything that is actually sellable: floor at the exchange
            # minimum so free, non-reserved, non-target coins down to ~$1 are
            # swept. dust_sweep_threshold_usd acts only as an optional HIGHER floor
            # (set it above the minimum to deliberately KEEP some dust unswept).
            user_floor = account.dust_sweep_threshold_usd or 0.0
            threshold = max(EXCHANGE_MIN_USD, user_floor)
            sweeps = plan_dust_sweeps(
                all_balances, targets, prices, available_products, threshold
            )

            if not sweeps:
                # Update timestamp even if nothing to sweep
                account.dust_last_sweep_at = utcnow()
                await db.commit()
                return []

            results = []
            for sweep in sweeps:
                try:
                    # Format size with proper precision for the product
                    # and apply a tiny haircut to avoid "Insufficient balance"
                    # from rounding/hold timing differences
                    coin = sweep["coin"]
                    sell_amount = sweep["amount"] * 0.999
                    size_str = format_base_amount(sell_amount, coin)
                    if float(size_str) <= 0:
                        continue

                    result = await client.create_market_order(
                        product_id=sweep["product_id"],
                        side="SELL",
                        size=size_str,
                    )
                    success = result.get("success_response", {})
                    order_id = success.get("order_id", "")

                    if order_id:
                        logger.info(
                            f"Dust sweep: sold {sweep['amount']:.6f} "
                            f"{sweep['coin']} (~${sweep['usd_value']}) "
                            f"→ {sweep['target_currency']} "
                            f"(Account: {account.name}, Order: {order_id})"
                        )
                        results.append({**sweep, "order_id": order_id, "status": "success"})
                    else:
                        error = result.get("error_response", {})
                        error_msg = error.get("message", "unknown error")
                        logger.warning(
                            f"Dust sweep failed for {sweep['coin']}: {error_msg}"
                        )
                        results.append({
                            **sweep, "order_id": "", "status": "failed",
                            "error": error_msg,
                        })
                except Exception as e:
                    logger.error(
                        f"Dust sweep error for {sweep['coin']}: {e}"
                    )
                    results.append({
                        **sweep, "order_id": "", "status": "failed",
                        "error": str(e),
                    })

            account.dust_last_sweep_at = utcnow()
            await db.commit()
            return results

        except Exception as e:
            logger.error(
                f"Dust sweep failed for account {account.id}: {e}",
                exc_info=True,
            )
            return []


async def execute_dust_sweep(account, client, db: AsyncSession) -> List[dict]:
    """Execute an on-demand dust sweep for an account.

    Called from the API endpoint. Fetches prices, products, and balances,
    then plans and executes sweeps.
    """
    monitor = RebalanceMonitor()
    # Fetch prices
    prices = {}
    for product_id in ("BTC-USD", "ETH-USD", "USDC-USD"):
        try:
            price = await client.get_current_price(product_id)
            prices[product_id] = float(price)
        except Exception:
            prices[product_id] = 1.0 if product_id == "USDC-USD" else 0.0

    # Free balances
    free_balances = {}
    balance_methods = {
        "USD": client.get_usd_balance,
        "BTC": client.get_btc_balance,
        "ETH": client.get_eth_balance,
        "USDC": client.get_usdc_balance,
    }
    for currency, method in balance_methods.items():
        try:
            free_balances[currency] = float(await method())
        except Exception as e:
            # Skip this currency rather than defaulting to 0.0 (which would
            # cause unnecessary rebalancing trades).
            logger.warning(
                f"Rebalance preview: could not get {currency} balance: {e} — skipping"
            )

    return await monitor._sweep_dust(client, account, db, prices, free_balances)


# Module-level singleton — imported by scheduler.py and main.py
rebalance_monitor = RebalanceMonitor()
