"""
Portfolio Rebalance Monitor Service

Periodically checks each account's free USD/BTC/ETH allocation against
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
        free_balances: {"USD": amount, "BTC": amount, "ETH": amount}
        prices: {"BTC-USD": price, "ETH-USD": price}

    Returns:
        {"usd_pct": float, "btc_pct": float, "eth_pct": float,
         "total_value_usd": float}
    """
    usd_value = free_balances.get("USD", 0.0)
    btc_value = free_balances.get("BTC", 0.0) * prices.get("BTC-USD", 0.0)
    eth_value = free_balances.get("ETH", 0.0) * prices.get("ETH-USD", 0.0)

    total = usd_value + btc_value + eth_value

    if total <= 0:
        return {
            "usd_pct": 0.0,
            "btc_pct": 0.0,
            "eth_pct": 0.0,
            "total_value_usd": 0.0,
        }

    return {
        "usd_pct": (usd_value / total) * 100,
        "btc_pct": (btc_value / total) * 100,
        "eth_pct": (eth_value / total) * 100,
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
    for key in ("usd_pct", "btc_pct", "eth_pct"):
        drift = abs(current[key] - targets[key])
        if drift > threshold:
            return True
    return False


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
    ]

    # USD value of each currency's free balance
    free_values = {
        "USD": free_balances.get("USD", 0.0),
        "BTC": free_balances.get("BTC", 0.0) * prices.get("BTC-USD", 0.0),
        "ETH": free_balances.get("ETH", 0.0) * prices.get("ETH-USD", 0.0),
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
            for product_id in ("BTC-USD", "ETH-USD"):
                try:
                    price = await client.get_current_price(product_id)
                    prices[product_id] = float(price)
                except Exception as e:
                    logger.error(
                        f"Rebalance: could not get price for {product_id}: {e}"
                    )
                    return  # Can't rebalance without prices

            # Aggregate values (free + positions) for drift detection
            aggregate = {}
            for currency in ("USD", "BTC", "ETH"):
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
            }
            threshold = account.rebalance_drift_threshold_pct or 5.0

            if not needs_rebalance(current, targets, threshold):
                logger.debug(
                    f"Rebalance: account {account.name} within threshold "
                    f"(USD={current['usd_pct']:.1f}%, "
                    f"BTC={current['btc_pct']:.1f}%, "
                    f"ETH={current['eth_pct']:.1f}%)"
                )
                self._account_timers[account.id] = datetime.utcnow()
                return

            # Free balances only — trades only move free capital
            free_balances = {}
            balance_methods = {
                "USD": client.get_usd_balance,
                "BTC": client.get_btc_balance,
                "ETH": client.get_eth_balance,
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

            # Plan trades using free balances only
            min_pct = account.rebalance_min_trade_pct or DEFAULT_MIN_TRADE_PCT
            trades = plan_trades(free_balances, targets, prices, min_trade_pct=min_pct)

            if not trades:
                logger.debug(
                    f"Rebalance: no actionable trades for account {account.name}"
                )
                self._account_timers[account.id] = datetime.utcnow()
                return

            logger.info(
                f"Rebalance: executing {len(trades)} trade(s) for account "
                f"{account.name} — current: USD={current['usd_pct']:.1f}%, "
                f"BTC={current['btc_pct']:.1f}%, ETH={current['eth_pct']:.1f}%"
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

            if side == "BUY" and trade["from_currency"] == "USD":
                # Buying BTC or ETH with USD
                result = await client.buy_with_usd(usd_amount, product_id)
            elif side == "SELL" and trade["to_currency"] == "USD":
                # Selling BTC or ETH for USD
                price = prices.get(product_id, 0)
                if price <= 0:
                    return
                base_amount = usd_amount / price
                result = await client.sell_for_usd(base_amount, product_id)
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
