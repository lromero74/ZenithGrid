"""
Trading Pair Monitor

Daily background job that:
1. Removes delisted trading pairs from bots
2. Adds newly listed pairs that match bot's quote currency (BTC/USD)
"""

import asyncio
from app.utils.timeutil import utcnow
import json
import logging
from datetime import datetime
from typing import Dict, List, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bot, BotProduct, Account
from app.services.exchange_service import get_exchange_client_for_account
from app.services.session_maker_mixin import SessionMakerMixin
from app.multi_bot_monitor import filter_pairs_by_allowed_categories
from app.utils.candle_utils import get_timeframes_for_phases

logger = logging.getLogger(__name__)

# Stable/pegged pairs — stablecoins vs USD and wrapped/pegged same-asset pairs.
# These rarely move in price and are not interesting for trading bots.
STABLE_PAIRS = {
    # Stablecoins vs USD
    "USDC-USD", "USDT-USD", "DAI-USD", "GUSD-USD", "PAX-USD", "BUSD-USD",
    "USDP-USD", "PYUSD-USD", "EURC-USD", "EURT-USD", "USDS-USD", "USD1-USD",
    # Wrapped/pegged same-asset pairs
    "WBTC-BTC", "CBBTC-BTC", "WETH-ETH", "CBETH-ETH", "LSETH-ETH",
    "MSOL-SOL", "JITOSOL-SOL",
}

# Backwards-compatible alias
EXCLUDED_PAIRS = STABLE_PAIRS

# Non-USD quote currencies for stable pair detection (frozenset for O(1) lookup)
_NON_USD_QUOTES = frozenset({"BTC", "ETH", "SOL"})

# All known stablecoin tickers — used to detect stable-vs-stable cross pairs
# (e.g. DAI-USDC, USDT-USDC) which are not in STABLE_PAIRS but should also be skipped.
_STABLECOIN_TICKERS = frozenset({
    "USD", "USDC", "USDT", "DAI", "GUSD", "PAX", "BUSD",
    "USDP", "PYUSD", "EURC", "EURT", "USDS", "USD1",
})

_AUTO_ADD_MIN_DAILY_CANDLES = 30
_AUTO_ADD_DAILY_LOOKBACK_DAYS = 100


def is_stable_pair(product_id: str) -> bool:
    """
    Check if a trading pair is a stablecoin or wrapped/pegged same-asset pair.

    Covers:
    - Explicit entries in STABLE_PAIRS (e.g. DAI-USD, WBTC-BTC)
    - Stable-vs-stable cross pairs where both sides are known stablecoins
      (e.g. DAI-USDC, USDT-USDC) — these slip through the explicit list because
      there are too many combinations to enumerate.
    """
    if product_id in STABLE_PAIRS:
        return True
    parts = product_id.split("-", 1)
    if len(parts) == 2:
        base, quote = parts
        if base in _STABLECOIN_TICKERS and quote in _STABLECOIN_TICKERS:
            return True
    return False


class TradingPairMonitor(SessionMakerMixin):
    """
    Monitors trading pairs and keeps bot configurations up to date.

    Runs once per day (24 hours) and:
    1. Fetches all available products from Coinbase
    2. Removes delisted pairs from bots
    3. Adds newly listed pairs matching bot's quote currency
    4. Logs all changes for audit trail
    """

    # Known wrapped/pegged prefixes for non-USD quote currencies.
    # If BASE starts with one of these, it's likely pegged to the quote asset.
    WRAPPED_PREFIXES = ("W", "CB", "ST", "LS", "JITO", "M")

    def __init__(self):
        self._last_check: datetime = None
        self._available_products: Set[str] = set()
        self._btc_pairs: Set[str] = set()
        self._usd_pairs: Set[str] = set()
        self._exchange_client = None
        self._raw_products: List[Dict] = []

    async def get_available_products(self, db: AsyncSession) -> Set[str]:
        """
        Fetch all available trading products from Coinbase.

        Returns:
            Set of product IDs (e.g., {"ETH-BTC", "SOL-USD", ...})
        """
        try:
            # Get any active CEX account for API credentials (products are global on Coinbase)
            result = await db.execute(
                select(Account).where(
                    Account.type == "cex",
                    Account.is_active.is_(True),
                ).limit(1)
            )
            account = result.scalars().first()

            if not account:
                logger.warning("No active CEX account found for pair check")
                return set()

            exchange = await get_exchange_client_for_account(db, account.id, session_maker=self._get_sm())
            if not exchange:
                logger.warning("Could not get exchange client for pair check")
                return set()

            # Store exchange client for use by detect_stable_pairs
            self._exchange_client = exchange

            # Fetch all products from Coinbase
            products = await exchange.list_products()
            self._raw_products = products

            # Extract product IDs and categorize by quote currency
            available = set()
            btc_pairs = set()
            usd_pairs = set()

            for product in products:
                product_id = product.get("product_id")
                if not product_id:
                    continue

                # Skip excluded pairs
                if product_id in EXCLUDED_PAIRS:
                    continue

                # Skip if trading is disabled
                if product.get("trading_disabled", False):
                    continue

                # Skip if not in online status
                status = product.get("status", "").lower()
                if status and status != "online":
                    continue

                available.add(product_id)

                # Categorize by quote currency
                if product_id.endswith("-BTC"):
                    btc_pairs.add(product_id)
                elif product_id.endswith("-USD"):
                    usd_pairs.add(product_id)

            self._available_products = available
            self._btc_pairs = btc_pairs
            self._usd_pairs = usd_pairs

            logger.info(
                f"Fetched {len(available)} available products from Coinbase "
                f"({len(btc_pairs)} BTC pairs, {len(usd_pairs)} USD pairs)"
            )
            return available

        except Exception as e:
            logger.error(f"Error fetching available products: {e}")
            return set()

    def _get_quote_currency(self, pairs: List[str]) -> str:
        """Determine quote currency from a list of pairs."""
        if not pairs:
            return None
        first_pair = pairs[0]
        if "-BTC" in first_pair:
            return "BTC"
        elif "-USD" in first_pair:
            return "USD"
        return None

    async def _filter_auto_add_pairs_by_entry_history(self, pairs: Set[str], bot: Bot) -> Set[str]:
        """Skip auto-add candidates that cannot satisfy the bot's entry history requirements."""
        if not pairs:
            return pairs

        strategy_config = bot.strategy_config or {}
        entry_timeframes = get_timeframes_for_phases(strategy_config, ["base_order_conditions"])
        if "ONE_DAY" not in entry_timeframes:
            return pairs

        if not self._exchange_client:
            logger.warning(
                "Bot '%s' (id=%s): cannot verify ONE_DAY history for auto-add candidates; "
                "skipping %d candidates",
                bot.name, bot.id, len(pairs),
            )
            return set()

        now = int(utcnow().timestamp())
        start = now - (_AUTO_ADD_DAILY_LOOKBACK_DAYS * 86400)
        eligible: Set[str] = set()

        for product_id in sorted(pairs):
            try:
                candles = await self._exchange_client.get_candles(
                    product_id=product_id,
                    start=start,
                    end=now,
                    granularity="ONE_DAY",
                )
            except Exception as exc:
                logger.warning(
                    "Bot '%s' (id=%s): skipping auto-add candidate %s; "
                    "ONE_DAY history check failed: %s",
                    bot.name, bot.id, product_id, exc,
                )
                continue

            candle_count = len(candles or [])
            if candle_count < _AUTO_ADD_MIN_DAILY_CANDLES:
                logger.info(
                    "Bot '%s' (id=%s): skipping auto-add candidate %s; "
                    "not enough ONE_DAY candles: %d/%d",
                    bot.name, bot.id, product_id, candle_count, _AUTO_ADD_MIN_DAILY_CANDLES,
                )
                continue

            eligible.add(product_id)

        return eligible

    def _is_stable_candidate_by_price(self, product: Dict) -> bool:
        """
        Quick heuristic: check if a product's current price suggests it's a stable/pegged pair.

        For -USD pairs: price should be ~1.0 (stablecoin).
        For -BTC/-ETH/-SOL pairs: base symbol should start with a wrapped prefix
            AND price should be ~1.0 (pegged to the quote asset).
        """
        product_id = product.get("product_id", "")
        price_str = product.get("price", "0")
        try:
            price = float(price_str)
        except (ValueError, TypeError):
            return False

        if price <= 0:
            return False

        # Already known — skip
        if product_id in STABLE_PAIRS:
            return False

        tolerance = 0.005  # 0.5%

        if product_id.endswith("-USD"):
            # Stablecoin check: price ~$1.00
            return abs(price - 1.0) <= tolerance

        # For non-USD pairs, check wrapped prefix + price proximity
        parts = product_id.rsplit("-", 1)
        if len(parts) == 2 and parts[1] in _NON_USD_QUOTES:
            base = parts[0]
            if any(base.upper().startswith(p) for p in self.WRAPPED_PREFIXES):
                return abs(price - 1.0) <= tolerance

        return False

    async def _verify_stable_with_candles(self, product_id: str) -> bool:
        """
        Verify a candidate stable pair by checking 24h candle data.

        Returns True if the high/low of every candle stayed within 0.5% of 1.0.
        """
        if not self._exchange_client:
            return False

        try:
            now = int(utcnow().timestamp())
            one_day_ago = now - 86400

            candles = await self._exchange_client.get_candles(
                product_id=product_id,
                start=one_day_ago,
                end=now,
                granularity="ONE_HOUR",  # Hourly candles for 24h = ~24 data points
            )

            if not candles:
                logger.debug(f"No candle data for {product_id}, skipping stable verification")
                return False

            tolerance = 0.005  # 0.5%
            for candle in candles:
                try:
                    low = float(candle.get("low", 0))
                    high = float(candle.get("high", 0))
                except (ValueError, TypeError):
                    return False

                if low <= 0 or high <= 0:
                    return False

                # Both high and low must be within tolerance of 1.0
                if abs(low - 1.0) > tolerance or abs(high - 1.0) > tolerance:
                    return False

            return True

        except Exception as e:
            logger.debug(f"Error fetching candles for {product_id}: {e}")
            return False

    async def detect_stable_pairs(self) -> List[str]:
        """
        Dynamically detect stable/pegged trading pairs by analyzing price data.

        Heuristic:
        1. Filter products whose current price is ~1.0 (within 0.5% tolerance)
        2. For candidates, verify with 24h hourly candle data that price stayed stable
        3. Add confirmed pairs to the module-level STABLE_PAIRS set (runtime only)

        Returns:
            List of newly detected stable pair product IDs
        """
        detected = []

        try:
            if not self._raw_products:
                return detected

            # Step 1: Find candidates by current price
            candidates = []
            for product in self._raw_products:
                product_id = product.get("product_id", "")
                if not product_id:
                    continue
                # Skip disabled/offline products
                if product.get("trading_disabled", False):
                    continue
                status = product.get("status", "").lower()
                if status and status != "online":
                    continue

                if self._is_stable_candidate_by_price(product):
                    candidates.append(product_id)

            if not candidates:
                logger.info("Stable pair detection: no new candidates found")
                return detected

            logger.info(
                f"Stable pair detection: {len(candidates)} candidate(s) to verify: "
                f"{candidates}"
            )

            # Step 2: Verify each candidate with candle data
            for product_id in candidates:
                is_stable = await self._verify_stable_with_candles(product_id)

                if is_stable:
                    STABLE_PAIRS.add(product_id)
                    detected.append(product_id)
                    logger.warning(
                        f"NEW STABLE PAIR DETECTED: {product_id} — "
                        f"added to runtime STABLE_PAIRS. "
                        f"Consider adding to hardcoded list."
                    )

                # Be courteous to the API — small delay between candle fetches
                await asyncio.sleep(0.2)

            if detected:
                logger.warning(
                    f"Stable pair detection complete: {len(detected)} new pair(s) detected: "
                    f"{detected}"
                )
            else:
                logger.info(
                    f"Stable pair detection complete: "
                    f"{len(candidates)} candidate(s) checked, none confirmed stable"
                )

        except Exception as e:
            logger.error(f"Error in stable pair detection: {e}", exc_info=True)

        return detected

    async def _get_unresolvable_coins(self, db: AsyncSession, available_products: set) -> set[str]:
        """
        Return the set of coin tickers that are held in any paper account but have no
        tradeable pair (neither <COIN>-USD nor <COIN>-BTC) on the exchange.

        These balances are kept as-is (mirroring real-exchange behaviour where delisted
        coins still sit in your account), but callers can use this set to suppress
        repeated pricing attempts that would always fail with a 404.
        """
        DUST = 1e-4
        # Build set of tradeable base currencies
        tradeable_bases: set[str] = set()
        for pid in available_products:
            parts = pid.split("-", 1)
            if len(parts) == 2:
                tradeable_bases.add(parts[0])

        always_priceable = {"USD", "USDC", "USDT", "BTC", "ETH"}
        unresolvable: set[str] = set()

        account_result = await db.execute(
            select(Account).where(
                Account.is_paper_trading.is_(True),
                Account.paper_balances.isnot(None),
            )
        )
        for account in account_result.scalars().all():
            try:
                balances: dict = json.loads(account.paper_balances) if account.paper_balances else {}
            except Exception:
                continue
            for currency, amount in balances.items():
                if currency in always_priceable:
                    continue
                if amount <= DUST:
                    continue
                if currency not in tradeable_bases:
                    unresolvable.add(currency)

        if unresolvable:
            logger.info(
                "Paper accounts hold %d delisted/unresolvable coin(s): %s — "
                "pricing will be skipped; balances are preserved (mirrors real-exchange behaviour)",
                len(unresolvable), sorted(unresolvable),
            )
        return unresolvable

    async def check_and_sync_pairs(self) -> dict:
        """
        Check all bots for delisted pairs and newly available pairs.

        Returns:
            dict with summary of changes made
        """
        results = {
            "checked_at": utcnow().isoformat(),
            "bots_checked": 0,
            "pairs_removed": 0,
            "pairs_added": 0,
            "affected_bots": [],
            "new_pairs_available": [],
            "detected_stable_pairs": [],
            "unresolvable_paper_coins": [],
            "errors": []
        }

        try:
            async with self._get_sm()() as db:
                # Get available products
                available_products = await self.get_available_products(db)

                if not available_products:
                    results["errors"].append("Could not fetch available products")
                    return results

                # Get all bots (product_ids list AND legacy single product_id)
                bot_result = await db.execute(select(Bot))
                bots = bot_result.scalars().all()

                all_bot_pairs = set()
                for bot in bots:
                    results["bots_checked"] += 1

                    # ── Legacy single-pair field ──────────────────────────────
                    if bot.product_id and not bot.product_ids:
                        if bot.product_id not in available_products:
                            logger.warning(
                                "Bot '%s' (id=%d): product_id '%s' is delisted — "
                                "clearing product_id and deactivating bot",
                                bot.name, bot.id, bot.product_id,
                            )
                            bot_change = {
                                "bot_id": bot.id,
                                "bot_name": bot.name,
                                "removed_pairs": [bot.product_id],
                                "added_pairs": [],
                            }
                            results["pairs_removed"] += 1
                            results["affected_bots"].append(bot_change)
                            bot.product_id = None
                            bot.is_active = False
                        else:
                            all_bot_pairs.add(bot.product_id)
                        continue  # single-pair bot: nothing more to do

                    junction_products = list(getattr(bot, "products", []) or [])
                    junction_pairs = {
                        bp.product_id for bp in junction_products if bp.product_id
                    }
                    json_pairs = list(bot.product_ids or [])
                    configured_pairs = list(junction_pairs or json_pairs)

                    if not configured_pairs:
                        continue

                    all_bot_pairs.update(configured_pairs)
                    current_pairs = set(configured_pairs)
                    quote_currency = self._get_quote_currency(configured_pairs)

                    # Determine which pairs to check against
                    if quote_currency == "BTC":
                        valid_pairs = self._btc_pairs
                    elif quote_currency == "USD":
                        valid_pairs = self._usd_pairs
                    else:
                        continue  # Unknown quote currency

                    # Find delisted pairs (in bot config but not available)
                    delisted_pairs = current_pairs - available_products

                    # Find new pairs (available but not in bot config)
                    # Only for bots configured to auto-add new pairs (check strategy_config)
                    auto_add_enabled = bot.strategy_config and bot.strategy_config.get(
                        "auto_add_new_pairs", False
                    )

                    new_pairs = set()
                    if auto_add_enabled:
                        candidate_pairs = valid_pairs - current_pairs
                        # Filter stable/pegged pairs (unless bot explicitly allows them)
                        skip_stable = (
                            bot.strategy_config.get("skip_stable_pairs", True)
                            if bot.strategy_config else True
                        )
                        if skip_stable:
                            candidate_pairs = {p for p in candidate_pairs if not is_stable_pair(p)}
                        # Filter by bot's allowed categories
                        allowed_categories = (
                            bot.strategy_config.get("allowed_categories")
                            if bot.strategy_config else None
                        )
                        if candidate_pairs and allowed_categories:
                            filtered = await filter_pairs_by_allowed_categories(
                                db, list(candidate_pairs), allowed_categories,
                                user_id=bot.user_id,
                            )
                            new_pairs = set(filtered)
                        else:
                            new_pairs = candidate_pairs

                        new_pairs = await self._filter_auto_add_pairs_by_entry_history(new_pairs, bot)

                    changes_made = False
                    bot_change = {
                        "bot_id": bot.id,
                        "bot_name": bot.name,
                        "removed_pairs": [],
                        "added_pairs": [],
                    }

                    # Remove delisted pairs
                    if delisted_pairs:
                        if json_pairs:
                            bot.product_ids = [p for p in json_pairs if p not in delisted_pairs]
                        for bot_product in junction_products:
                            if bot_product.product_id in delisted_pairs:
                                await db.delete(bot_product)
                        bot_change["removed_pairs"] = list(delisted_pairs)
                        results["pairs_removed"] += len(delisted_pairs)
                        changes_made = True

                        logger.warning(
                            f"Bot '{bot.name}' (id={bot.id}): "
                            f"Removing delisted pairs: {delisted_pairs}"
                        )

                    # Add new pairs (only if auto_add_new_pairs is enabled)
                    if new_pairs:
                        if junction_pairs:
                            for product_id in sorted(new_pairs):
                                db.add(BotProduct(bot_id=bot.id, product_id=product_id))
                        else:
                            updated_pairs = list(bot.product_ids or []) + list(new_pairs)
                            # Sort for consistency
                            updated_pairs.sort()
                            bot.product_ids = updated_pairs
                        bot_change["added_pairs"] = list(new_pairs)
                        results["pairs_added"] += len(new_pairs)
                        changes_made = True

                        logger.info(
                            f"Bot '{bot.name}' (id={bot.id}): "
                            f"Adding new pairs: {new_pairs}"
                        )

                    if changes_made:
                        results["affected_bots"].append(bot_change)

                # Track newly available pairs for reporting
                new_btc = self._btc_pairs - all_bot_pairs
                new_usd = self._usd_pairs - all_bot_pairs
                if new_btc or new_usd:
                    results["new_pairs_available"] = {
                        "BTC": sorted(list(new_btc))[:20],  # Limit to 20 for log readability
                        "USD": sorted(list(new_usd))[:20],
                    }

                # Identify delisted coins sitting in paper accounts (balances preserved,
                # but we cache the set so the paper trading client can skip pricing them)
                unresolvable = await self._get_unresolvable_coins(db, available_products)
                if unresolvable:
                    results["unresolvable_paper_coins"] = sorted(unresolvable)
                    # Publish to module-level cache so paper_trading_client can read it
                    _unresolvable_paper_coins.update(unresolvable)

                if results["pairs_removed"] > 0 or results["pairs_added"] > 0:
                    await db.commit()
                    logger.info(
                        "Pair sync complete: removed %d, added %d pairs across %d bots",
                        results["pairs_removed"], results["pairs_added"],
                        len(results["affected_bots"]),
                    )
                else:
                    logger.info("Pair sync complete: No changes needed")

        except Exception as e:
            logger.error(f"Error in pair sync: {e}", exc_info=True)
            results["errors"].append(str(e))

        # Run stable pair detection after the main sync logic
        detected = await self.detect_stable_pairs()
        if detected:
            results["detected_stable_pairs"] = detected

        self._last_check = utcnow()
        return results

    def get_status(self) -> dict:
        """Get current status of the monitor."""
        return {
            "last_check": self._last_check.isoformat() if self._last_check else None,
            "available_products_count": len(self._available_products),
            "btc_pairs_count": len(self._btc_pairs),
            "usd_pairs_count": len(self._usd_pairs),
        }

    async def run_once(self) -> dict:
        """
        Run the sync once immediately (for manual triggering via API).

        Returns:
            Results dict from check_and_sync_pairs()
        """
        logger.info("Manual pair sync triggered")
        return await self.check_and_sync_pairs()


# Module-level set of coin tickers known to have no tradeable pair on the exchange.
# Populated by TradingPairMonitor.check_and_sync_pairs() after each daily run.
# Read by paper_trading_client._price_in_usd / _price_in_btc to suppress repeated
# 404 requests for coins that can never be priced (e.g. RONIN after delisting).
# Balances for these coins are intentionally kept — mirrors real-exchange behaviour.
_unresolvable_paper_coins: set[str] = set()


# Module-level singleton — imported by scheduler.py and main.py
trading_pair_monitor = TradingPairMonitor()
