"""
Portfolio Rebalance Monitor Service

Periodically checks each account's free USD/BTC/ETH/USDC allocation against
configured targets and executes market trades to rebalance when any
currency drifts beyond the threshold.

Settings are per-account (stored on the Account model). Only free balances
are rebalanced — funds in open bot positions are untouched.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import Account
from app.services.exchange_service import get_exchange_client_for_account

logger = logging.getLogger(__name__)

EXCHANGE_MIN_USD = 10.0  # Coinbase minimum order size
DEFAULT_MIN_TRADE_PCT = 5.0  # Default: only trade if shift is >= 5% of portfolio


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
) -> List[dict]:
    """Plan trades to top up currencies that are below their minimum reserve.

    For each currency below its minimum, calculates the deficit in USD terms
    and sources funds proportionally from all other currencies based on their
    free USD-equivalent values. Individual contributions below EXCHANGE_MIN_USD
    are skipped.

    Returns a list of trade dicts (same format as plan_trades).
    """
    # Price lookup helper: convert currency amount to USD
    def to_usd(currency: str, amount: float) -> float:
        if currency == "USD":
            return amount
        pair = f"{currency}-USD" if currency != "USDC" else "USDC-USD"
        return amount * prices.get(pair, 1.0 if currency == "USDC" else 0.0)

    # Find currencies with deficits
    deficits = {}  # currency -> deficit in USD
    for currency, min_bal in min_balances.items():
        if min_bal <= 0:
            continue
        free = free_balances.get(currency, 0.0)
        if free < min_bal:
            deficit_native = min_bal - free
            deficit_usd = to_usd(currency, deficit_native)
            if deficit_usd >= EXCHANGE_MIN_USD:
                deficits[currency] = deficit_usd

    if not deficits:
        return []

    trades = []

    for deficit_currency, deficit_usd in deficits.items():
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

        total_donor_usd = sum(donors.values())
        if total_donor_usd <= 0:
            continue

        # Cap deficit to what's actually available
        actual_deficit = min(deficit_usd, total_donor_usd)

        # Source proportionally from each donor
        for donor_currency, donor_usd in donors.items():
            proportion = donor_usd / total_donor_usd
            contribution_usd = actual_deficit * proportion

            if contribution_usd < EXCHANGE_MIN_USD:
                continue

            product_id, side = _get_trade_params(
                donor_currency, deficit_currency
            )

            trades.append({
                "from_currency": donor_currency,
                "to_currency": deficit_currency,
                "usd_amount": round(contribution_usd, 2),
                "product_id": product_id,
                "side": side,
            })

    return trades


def plan_trades(
    free_balances: Dict[str, float],
    targets: Dict[str, float],
    prices: Dict[str, float],
    min_trade_pct: float = DEFAULT_MIN_TRADE_PCT,
) -> List[dict]:
    """Plan trades to rebalance from current to target allocations.

    All trade amounts are in USD-equivalent terms, even for BTC↔ETH trades.
    Trades below min_trade_pct (% of total portfolio) are skipped to avoid
    micro-trading. A hard floor of EXCHANGE_MIN_USD ($10) also applies.

    Returns a list of trade dicts:
        {"from_currency": str, "to_currency": str, "usd_amount": float,
         "product_id": str, "side": str}
    """
    current = calculate_current_allocations(free_balances, prices)
    total = current["total_value_usd"]

    if total <= 0:
        return []

    # Convert percentage minimum to USD, with exchange floor
    min_trade_usd = max(total * min_trade_pct / 100.0, EXCHANGE_MIN_USD)

    # Calculate USD-denominated delta for each currency
    # Positive delta = underweight (need to buy), negative = overweight (need to sell)
    currencies = [
        ("USD", targets["usd_pct"]),
        ("BTC", targets["btc_pct"]),
        ("ETH", targets["eth_pct"]),
        ("USDC", targets["usdc_pct"]),
    ]

    # USD value of each currency's free balance
    free_values = {
        "USD": free_balances.get("USD", 0.0),
        "BTC": free_balances.get("BTC", 0.0) * prices.get("BTC-USD", 0.0),
        "ETH": free_balances.get("ETH", 0.0) * prices.get("ETH-USD", 0.0),
        "USDC": free_balances.get("USDC", 0.0) * prices.get("USDC-USD", 1.0),
    }

    deltas = {}
    for currency, target_pct in currencies:
        current_pct = current[f"{currency.lower()}_pct"]
        delta_usd = (target_pct - current_pct) / 100 * total
        deltas[currency] = delta_usd

    # Identify overweight (sell) and underweight (buy) currencies
    # Cap sells to available free balance — can't sell more than you have
    sells = []
    for c, d in deltas.items():
        if d < -min_trade_usd:
            sell_amount = min(-d, free_values.get(c, 0.0))
            if sell_amount >= min_trade_usd:
                sells.append((c, sell_amount))
    buys = [(c, d) for c, d in deltas.items() if d > min_trade_usd]

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
            if trade_usd < min_trade_usd:
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


def _get_trade_params(from_currency: str, to_currency: str) -> Tuple[str, str]:
    """Determine product_id and side for a currency conversion.

    Returns (product_id, side).
    """
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


class RebalanceMonitor:
    """Background service that rebalances account allocations."""

    def __init__(self):
        self.running = False
        self.task = None
        self._account_timers: Dict[int, datetime] = {}
        self._processing: set = set()  # Account IDs currently being processed

    async def start(self):
        if not self.running:
            self.running = True
            self.task = asyncio.create_task(self._monitor_loop())
            logger.info("Rebalance Monitor started")

    async def stop(self):
        self.running = False
        if self.task:
            await self.task
        logger.info("Rebalance Monitor stopped")

    async def _monitor_loop(self):
        """Main loop — checks every 30 seconds."""
        while self.running:
            try:
                await self._check_accounts()
            except Exception as e:
                logger.error(f"Error in rebalance monitor loop: {e}", exc_info=True)
            await asyncio.sleep(30)

    async def _check_accounts(self):
        async with async_session_maker() as db:
            query = select(Account).where(Account.rebalance_enabled.is_(True))
            result = await db.execute(query)
            accounts = result.scalars().all()

            for account in accounts:
                if self._should_check_account(account):
                    await self._process_account(account, db)

    def _should_check_account(self, account: Account) -> bool:
        now = datetime.utcnow()
        last_check = self._account_timers.get(account.id)
        if not last_check:
            return True
        interval_seconds = (account.rebalance_check_interval_minutes or 60) * 60
        return (now - last_check).total_seconds() >= interval_seconds

    async def _process_account(self, account, db: AsyncSession):
        """Process one account — check allocations and rebalance if needed."""
        if not account.rebalance_enabled:
            return

        if account.id in self._processing:
            return  # Already processing this account

        self._processing.add(account.id)
        try:
            client = await get_exchange_client_for_account(db, account.id)
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
                    logger.warning(
                        f"Rebalance: could not get free {currency} "
                        f"for account {account.id}: {e}"
                    )
                    free_balances[currency] = 0.0

            # Load minimum balance reserves
            min_balances = {
                "USD": account.min_balance_usd or 0.0,
                "BTC": account.min_balance_btc or 0.0,
                "ETH": account.min_balance_eth or 0.0,
                "USDC": account.min_balance_usdc or 0.0,
            }

            # Phase 1: Top-up currencies below their minimum reserve.
            # This runs BEFORE drift detection — reserves must be
            # maintained even when the portfolio is within threshold.
            topup_trades = plan_topup_trades(
                free_balances, min_balances, prices
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
                self._account_timers[account.id] = datetime.utcnow()
                return

            # Phase 2: Percentage-based rebalancing (only if drifted)
            # Use aggregate values (free + positions) for drift detection
            aggregate = {}
            for currency in ("USD", "BTC", "ETH", "USDC"):
                try:
                    aggregate[currency] = float(
                        await client.calculate_aggregate_quote_value(currency)
                    )
                except Exception as e:
                    logger.warning(
                        f"Rebalance: could not get aggregate {currency} "
                        f"for account {account.id}: {e}"
                    )
                    aggregate[currency] = 0.0

            current = calculate_current_allocations(aggregate, prices)
            targets = {
                "usd_pct": account.rebalance_target_usd_pct or 34.0,
                "btc_pct": account.rebalance_target_btc_pct or 33.0,
                "eth_pct": account.rebalance_target_eth_pct or 33.0,
                "usdc_pct": account.rebalance_target_usdc_pct or 0.0,
            }
            threshold = account.rebalance_drift_threshold_pct or 5.0

            if not needs_rebalance(current, targets, threshold):
                logger.debug(
                    f"Rebalance: account {account.name} within threshold "
                    f"(USD={current['usd_pct']:.1f}%, "
                    f"BTC={current['btc_pct']:.1f}%, "
                    f"ETH={current['eth_pct']:.1f}%, "
                    f"USDC={current['usdc_pct']:.1f}%)"
                )
                self._account_timers[account.id] = datetime.utcnow()
                return

            # Subtract reserves from free balances for rebalancing
            rebalanceable = {
                c: max(0.0, free_balances[c] - min_balances[c])
                for c in free_balances
            }

            min_pct = account.rebalance_min_trade_pct or DEFAULT_MIN_TRADE_PCT
            trades = plan_trades(
                rebalanceable, targets, prices, min_trade_pct=min_pct
            )

            if not trades:
                logger.debug(
                    f"Rebalance: no actionable trades for account "
                    f"{account.name}"
                )
                self._account_timers[account.id] = datetime.utcnow()
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

            self._account_timers[account.id] = datetime.utcnow()

        except Exception as e:
            logger.error(
                f"Rebalance failed for account {account.id}: {e}", exc_info=True
            )
        finally:
            self._processing.discard(account.id)

    async def _execute_trade(self, client, account, trade: dict, prices: dict):
        """Execute a single rebalance trade."""
        try:
            product_id = trade["product_id"]
            side = trade["side"]
            usd_amount = trade["usd_amount"]

            # Reserve 1% for fees (same as auto-buy)
            usd_amount = round(usd_amount * 0.99, 2)

            if usd_amount < EXCHANGE_MIN_USD:
                return

            from_curr = trade["from_currency"]
            to_curr = trade["to_currency"]

            if product_id == "USDC-USD":
                # USDC↔USD: use buy_with_usd / sell_for_usd
                usdc_price = prices.get("USDC-USD", 1.0)
                if side == "BUY":
                    # Buying USDC with USD
                    result = await client.buy_with_usd(usd_amount, product_id)
                else:
                    # Selling USDC for USD
                    usdc_amount = usd_amount / usdc_price
                    result = await client.sell_for_usd(usdc_amount, product_id)
            elif side == "BUY" and from_curr == "USD":
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

        except Exception as e:
            logger.error(
                f"Error executing rebalance trade for account "
                f"{account.name}: {e}",
                exc_info=True,
            )
