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
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Position
from app.precision import format_base_amount
from app.services.realmoney_audit import set_subsystem
from app.services.exchange_service import get_exchange_client_for_account
from app.services.session_maker_mixin import SessionMakerMixin
from app.trading_engine.sell_executor import SELL_BALANCE_HAIRCUT
from app.services.rebalance_planning import (
    EXCHANGE_MIN_USD, DEFAULT_MIN_TRADE_PCT, TARGET_CURRENCIES,
    calculate_current_allocations, needs_rebalance, plan_topup_trades,
    get_min_usd_by_currency, plan_trades, sum_locked_base_amounts,
    get_position_locked_amounts, subtract_locked_amounts, should_dust_sweep,
    plan_dust_sweeps,
)

logger = logging.getLogger(__name__)

# Max concurrent dust price lookups — parallelize the per-coin price fetches
# while staying well under exchange rate limits.
DUST_PRICE_CONCURRENCY = 8

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
                # If the product list can't be fetched, the availability check
                # below skips every sell — log it rather than swallowing silently.
                logger.warning("Rebalance dust sweep: list_products failed; "
                               "product-availability check will skip sells", exc_info=True)

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
                    sell_amount = sweep["amount"] * SELL_BALANCE_HAIRCUT
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
