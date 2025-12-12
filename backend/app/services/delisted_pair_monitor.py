"""
Trading Pair Monitor

Daily background job that:
1. Removes delisted trading pairs from bots
2. Adds newly listed pairs that match bot's quote currency (BTC/USD)
"""

import asyncio
import logging
from datetime import datetime
from typing import Set, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import Bot, Account
from app.services.exchange_service import get_exchange_client_for_account

logger = logging.getLogger(__name__)

# Pairs to exclude from auto-addition (stablecoins, wrapped tokens, etc.)
EXCLUDED_PAIRS = {
    # Stablecoins (not interesting for trading bots)
    "USDC-USD", "USDT-USD", "DAI-USD", "GUSD-USD", "PAX-USD", "BUSD-USD",
    "USDP-USD", "PYUSD-USD", "EURC-USD", "EURT-USD",
    # Wrapped tokens that just track other assets
    "WBTC-BTC", "CBBTC-BTC", "WETH-ETH",
}


class TradingPairMonitor:
    """
    Monitors trading pairs and keeps bot configurations up to date.

    Runs once per day (24 hours) and:
    1. Fetches all available products from Coinbase
    2. Removes delisted pairs from bots
    3. Adds newly listed pairs matching bot's quote currency
    4. Logs all changes for audit trail
    """

    def __init__(self, check_interval_seconds: int = 86400):  # 24 hours default
        self.check_interval_seconds = check_interval_seconds
        self.running = False
        self.task = None
        self._last_check: datetime = None
        self._available_products: Set[str] = set()
        self._btc_pairs: Set[str] = set()
        self._usd_pairs: Set[str] = set()

    async def get_available_products(self, db: AsyncSession) -> Set[str]:
        """
        Fetch all available trading products from Coinbase.

        Returns:
            Set of product IDs (e.g., {"ETH-BTC", "SOL-USD", ...})
        """
        try:
            # Get primary account (account_id=1)
            result = await db.execute(select(Account).where(Account.id == 1))
            account = result.scalars().first()

            if not account:
                logger.warning("No primary account found for pair check")
                return set()

            exchange = await get_exchange_client_for_account(db, account.id)
            if not exchange:
                logger.warning("Could not get exchange client for pair check")
                return set()

            # Fetch all products from Coinbase
            products = await exchange.list_products()

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
                        new_pairs = valid_pairs - current_pairs

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
