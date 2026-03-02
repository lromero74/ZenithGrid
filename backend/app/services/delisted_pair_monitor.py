"""
Trading Pair Monitor

Daily background job that:
1. Removes delisted trading pairs from bots
2. Adds newly listed pairs that match bot's quote currency (BTC/USD)
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import Bot, Account
from app.services.exchange_service import get_exchange_client_for_account
from app.multi_bot_monitor import filter_pairs_by_allowed_categories

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


def is_stable_pair(product_id: str) -> bool:
    """Check if a trading pair is a stablecoin or wrapped/pegged same-asset pair."""
    return product_id in STABLE_PAIRS


class TradingPairMonitor:
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

    def __init__(self, check_interval_seconds: int = 86400):  # 24 hours default
        self.check_interval_seconds = check_interval_seconds
        self.running = False
        self.task = None
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

            exchange = await get_exchange_client_for_account(db, account.id)
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
        quote_currencies = ("BTC", "ETH", "SOL")
        for quote in quote_currencies:
            suffix = f"-{quote}"
            if product_id.endswith(suffix):
                base = product_id[: -len(suffix)]
                if any(base.upper().startswith(p) for p in self.WRAPPED_PREFIXES):
                    return abs(price - 1.0) <= tolerance
                break

        return False

    async def _verify_stable_with_candles(self, product_id: str) -> bool:
        """
        Verify a candidate stable pair by checking 24h candle data.

        Returns True if the high/low of every candle stayed within 0.5% of 1.0.
        """
        if not self._exchange_client:
            return False

        try:
            now = int(datetime.utcnow().timestamp())
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

    async def check_and_sync_pairs(self) -> dict:
        """
        Check all bots for delisted pairs and newly available pairs.

        Returns:
            dict with summary of changes made
        """
        results = {
            "checked_at": datetime.utcnow().isoformat(),
            "bots_checked": 0,
            "pairs_removed": 0,
            "pairs_added": 0,
            "affected_bots": [],
            "new_pairs_available": [],
            "detected_stable_pairs": [],
            "errors": []
        }

        try:
            async with async_session_maker() as db:
                # Get available products
                available_products = await self.get_available_products(db)

                if not available_products:
                    results["errors"].append("Could not fetch available products")
                    return results

                # Get all bots with product_ids configured
                bot_result = await db.execute(
                    select(Bot).where(Bot.product_ids.isnot(None))
                )
                bots = bot_result.scalars().all()

                for bot in bots:
                    results["bots_checked"] += 1

                    if not bot.product_ids:
                        continue

                    current_pairs = set(bot.product_ids)
                    quote_currency = self._get_quote_currency(bot.product_ids)

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

                    changes_made = False
                    bot_change = {
                        "bot_id": bot.id,
                        "bot_name": bot.name,
                        "removed_pairs": [],
                        "added_pairs": [],
                    }

                    # Remove delisted pairs
                    if delisted_pairs:
                        new_pair_list = [p for p in bot.product_ids if p not in delisted_pairs]
                        bot.product_ids = new_pair_list
                        bot_change["removed_pairs"] = list(delisted_pairs)
                        results["pairs_removed"] += len(delisted_pairs)
                        changes_made = True

                        logger.warning(
                            f"Bot '{bot.name}' (id={bot.id}): "
                            f"Removing delisted pairs: {delisted_pairs}"
                        )

                    # Add new pairs (only if auto_add_new_pairs is enabled)
                    if new_pairs:
                        updated_pairs = list(bot.product_ids) + list(new_pairs)
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
                all_bot_pairs = set()
                for bot in bots:
                    if bot.product_ids:
                        all_bot_pairs.update(bot.product_ids)

                new_btc = self._btc_pairs - all_bot_pairs
                new_usd = self._usd_pairs - all_bot_pairs
                if new_btc or new_usd:
                    results["new_pairs_available"] = {
                        "BTC": sorted(list(new_btc))[:20],  # Limit to 20 for log readability
                        "USD": sorted(list(new_usd))[:20],
                    }

                if results["pairs_removed"] > 0 or results["pairs_added"] > 0:
                    await db.commit()
                    logger.info(
                        f"Pair sync complete: "
                        f"Removed {results['pairs_removed']}, Added {results['pairs_added']} "
                        f"pairs across {len(results['affected_bots'])} bots"
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

        self._last_check = datetime.utcnow()
        return results

    async def run_loop(self):
        """Background loop that runs the check periodically."""
        # Wait 5 minutes after startup before first check
        await asyncio.sleep(300)

        while self.running:
            try:
                logger.info("Running daily trading pair sync...")
                results = await self.check_and_sync_pairs()

                if results["pairs_removed"] > 0:
                    logger.warning(
                        f"DELISTED PAIRS REMOVED: {results['pairs_removed']} pairs "
                        f"from {len(results['affected_bots'])} bots"
                    )

                if results["pairs_added"] > 0:
                    logger.info(
                        f"NEW PAIRS ADDED: {results['pairs_added']} pairs "
                        f"to {len(results['affected_bots'])} bots"
                    )

            except Exception as e:
                logger.error(f"Error in pair monitor loop: {e}", exc_info=True)

            # Sleep for check interval (default 24 hours)
            await asyncio.sleep(self.check_interval_seconds)

    async def start(self):
        """Start the background monitor."""
        if self.running:
            return

        self.running = True
        self.task = asyncio.create_task(self.run_loop())
        logger.info(
            f"Trading pair monitor started - "
            f"checking every {self.check_interval_seconds / 3600:.1f} hours"
        )

    async def stop(self):
        """Stop the background monitor."""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Trading pair monitor stopped")

    def get_status(self) -> dict:
        """Get current status of the monitor."""
        return {
            "running": self.running,
            "last_check": self._last_check.isoformat() if self._last_check else None,
            "check_interval_hours": self.check_interval_seconds / 3600,
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
