"""
Multi-Bot Price Monitor

Monitors prices for all active bots and processes signals using their configured strategies.
"""

import asyncio
import contextvars
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    CANDLE_CACHE_DEFAULT_TTL,
    CANDLE_CACHE_TTL,
    PAIR_PROCESSING_DELAY_SECONDS,
)
from app.database import async_session_maker
from app.exchange_clients.base import ExchangeClient
from app.models import Bot
from app.services.indicator_log_service import log_indicator_evaluation
from app.strategies import StrategyRegistry
from app.strategies.bull_flag_scanner import log_scanner_decision, scan_for_bull_flag_opportunities
from app.trading_engine.trailing_stops import (
    check_bull_flag_exit_conditions,
    setup_bull_flag_position_stops,
)
from app.trading_engine_v2 import StrategyTradingEngine
from app.utils.candle_utils import (
    SYNTHETIC_TIMEFRAMES,
    aggregate_candles,
    calculate_bot_check_interval,
    fill_candle_gaps,
    get_timeframes_for_phases,
    next_check_time_aligned,
    prepare_market_context,
    timeframe_to_seconds,
)

logger = logging.getLogger(__name__)

# Module-level reference to the active monitor instance (set in __init__)
_active_monitor_instance: Optional["MultiBotMonitor"] = None

# Per-task exchange client context (each asyncio.Task gets its own copy)
# This allows parallel bot processing without shared mutable state
_ctx_exchange: contextvars.ContextVar[Optional["ExchangeClient"]] = contextvars.ContextVar(
    "_ctx_exchange", default=None
)


def clear_monitor_exchange_cache(account_id: Optional[int] = None):
    """Clear the monitor's exchange client cache (called when credentials change)."""
    if _active_monitor_instance is None:
        return
    if account_id is not None:
        _active_monitor_instance._exchange_cache.pop(account_id, None)
    else:
        _active_monitor_instance._exchange_cache.clear()


async def filter_pairs_by_allowed_categories(
    db: AsyncSession,
    trading_pairs: List[str],
    allowed_categories: Optional[List[str]] = None,
    user_id: Optional[int] = None,
) -> List[str]:
    """
    Filter trading pairs based on allowed coin categories from blacklist table.

    Args:
        db: Database session
        trading_pairs: List of pairs to filter (e.g., ["ETH-BTC", "ADA-BTC"])
        allowed_categories: List of allowed categories (e.g., ["APPROVED", "BORDERLINE"])
                          If None or empty, no filtering is applied.
        user_id: Optional user ID. If provided, per-user overrides take precedence
                 over global entries.

    Returns:
        Filtered list of trading pairs that match allowed categories
    """
    if not allowed_categories or len(allowed_categories) == 0:
        # No filtering - allow all pairs
        return trading_pairs

    from app.models import BlacklistedCoin

    # Extract base currencies from pairs
    base_currencies = set()
    pair_to_base = {}
    for pair in trading_pairs:
        if "-" in pair:
            base = pair.split("-")[0]
            base_currencies.add(base.upper())
            pair_to_base[pair] = base.upper()

    # Query blacklist table for these currencies (user_id IS NULL = global entries)
    query = select(BlacklistedCoin).where(
        BlacklistedCoin.symbol.in_(base_currencies),
        BlacklistedCoin.user_id.is_(None)
    )
    result = await db.execute(query)
    blacklist_entries = result.scalars().all()

    def _category_from_reason(reason: str) -> str:
        if reason.startswith("[APPROVED]"):
            return "APPROVED"
        elif reason.startswith("[BORDERLINE]"):
            return "BORDERLINE"
        elif reason.startswith("[QUESTIONABLE]"):
            return "QUESTIONABLE"
        elif reason.startswith("[MEME]"):
            return "MEME"
        return "BLACKLISTED"

    # Build map of currency -> category (global entries first)
    currency_categories = {}
    for entry in blacklist_entries:
        reason = entry.reason or ""
        currency_categories[entry.symbol] = _category_from_reason(reason)

    # Apply per-user overrides if user_id is provided
    if user_id is not None:
        override_query = select(BlacklistedCoin).where(
            BlacklistedCoin.symbol.in_(base_currencies),
            BlacklistedCoin.user_id == user_id,
        )
        override_result = await db.execute(override_query)
        for entry in override_result.scalars().all():
            reason = entry.reason or ""
            currency_categories[entry.symbol] = _category_from_reason(reason)

    # Filter pairs based on allowed categories
    filtered_pairs = []
    for pair in trading_pairs:
        base = pair_to_base.get(pair)
        if not base:
            continue

        category = currency_categories.get(base, "APPROVED")  # Default to APPROVED if not in blacklist
        if category in allowed_categories:
            filtered_pairs.append(pair)
        else:
            logger.debug(f"  Filtered out {pair}: {base} is {category}, not in allowed {allowed_categories}")

    if len(filtered_pairs) < len(trading_pairs):
        logger.info(
            f"  Category filter: {len(trading_pairs)} pairs → {len(filtered_pairs)} pairs "
            f"(allowed: {', '.join(allowed_categories)})"
        )

    return filtered_pairs


class MultiBotMonitor:
    """
    Monitor prices and signals for multiple active bots.

    Each bot can use a different strategy and trade a different product pair.
    Supports multi-user with per-account exchange clients.
    """

    def __init__(self, exchange: Optional[ExchangeClient] = None, interval_seconds: int = 60):
        """
        Initialize multi-bot monitor

        Args:
            exchange: Optional fallback exchange client (for backwards compatibility)
            interval_seconds: How often to check signals (default: 60s)
        """
        global _active_monitor_instance
        _active_monitor_instance = self
        self._fallback_exchange = exchange  # Fallback for bots without account_id
        self.interval_seconds = interval_seconds
        self.running = False
        self.task: Optional[asyncio.Task] = None

        # Current exchange client (legacy — used by serial fallback path)
        self._current_exchange: Optional[ExchangeClient] = None
        self._current_account_id: Optional[int] = None

        # Semaphore to limit concurrent bot processing (protects API rate limits + t2.micro CPU)
        self._bot_semaphore = asyncio.Semaphore(5)

        # Initialize order monitor (will get exchange per-bot)
        self.order_monitor = None  # Initialized lazily when needed

        # Cache for candle data (to avoid fetching same data multiple times)
        # Shared across all bots monitoring the same product_id:granularity
        # TTL is per-timeframe (e.g., 15-min candles cached for 15 minutes)
        self._candle_cache: Dict[str, tuple] = {}  # product_id:granularity -> (timestamp, candles)

        # Cache for exchange clients per account (with lock for concurrent safety)
        self._exchange_cache: Dict[int, ExchangeClient] = {}
        self._exchange_cache_lock = asyncio.Lock()

        # Cache for previous indicators (for crossing detection)
        # Key: (bot_id, product_id) -> Dict of indicator values
        # This enables crossing_above/crossing_below operators for ENTRY conditions
        # (Position-based storage only works for open positions)
        self._previous_indicators_cache: Dict[tuple, Dict] = {}

        # Per-bot next check time tracking (Phase 2 optimization)
        # Key: bot_id -> next_check_timestamp
        # Bots check only when their fastest indicator timeframe closes
        self._bot_next_check: Dict[int, int] = {}

    async def get_exchange_for_bot(self, db: AsyncSession, bot: Bot) -> Optional[ExchangeClient]:
        """
        Get the exchange client for a specific bot based on its account.

        Args:
            db: Database session
            bot: The bot to get exchange for

        Returns:
            ExchangeClient or None if no account/credentials configured
        """
        from app.services.exchange_service import get_exchange_client_for_account, get_exchange_client_for_user

        # If bot has an account_id, use that account's credentials
        if bot.account_id:
            # Check cache first (lock-free fast path)
            if bot.account_id in self._exchange_cache:
                return self._exchange_cache[bot.account_id]

            async with self._exchange_cache_lock:
                # Double-check after acquiring lock
                if bot.account_id in self._exchange_cache:
                    return self._exchange_cache[bot.account_id]

                client = await get_exchange_client_for_account(db, bot.account_id)
                if client:
                    self._exchange_cache[bot.account_id] = client
                    return client

        # If bot has a user_id but no account_id, get user's default account
        if bot.user_id:
            client = await get_exchange_client_for_user(db, bot.user_id, "cex")
            if client:
                return client

        # Fallback to global exchange client (for backwards compatibility)
        if self._fallback_exchange:
            return self._fallback_exchange

        logger.warning(f"No exchange client available for bot {bot.name} (id={bot.id})")
        return None

    @property
    def exchange(self) -> Optional[ExchangeClient]:
        """Returns current exchange client (per-bot task context) or fallback"""
        return _ctx_exchange.get() or self._current_exchange or self._fallback_exchange

    async def get_active_bots(self, db: AsyncSession) -> List[Bot]:
        """
        Fetch all bots that need processing:
        - Active bots (is_active == True) - can open new positions and manage existing ones
        - Inactive bots with open positions - only manage existing positions, no new ones
        """
        from app.models import Position

        # Get all active bots
        active_query = select(Bot).where(Bot.is_active)
        active_result = await db.execute(active_query)
        active_bots = list(active_result.scalars().all())

        # Get inactive bots that have open positions
        # Note: Use Bot.is_active == False (not "not Bot.is_active") for SQLAlchemy
        inactive_with_positions_query = (
            select(Bot)
            .join(Position, Position.bot_id == Bot.id)
            .where(Bot.is_active == False, Position.status == "open")  # noqa: E712
            .distinct()
        )
        inactive_result = await db.execute(inactive_with_positions_query)
        inactive_bots_with_positions = list(inactive_result.scalars().all())

        # Combine both lists
        all_bots = active_bots + inactive_bots_with_positions

        if inactive_bots_with_positions:
            logger.info(f"Including {len(inactive_bots_with_positions)} stopped bot(s) with open positions")

        return all_bots

    async def get_candles_cached(
        self, product_id: str, granularity: str, lookback_candles: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get historical candles with caching

        Args:
            product_id: Trading pair (e.g., "ETH-BTC")
            granularity: Candle interval (e.g., "FIVE_MINUTE", "ONE_HOUR", "THREE_MINUTE")
            lookback_candles: Number of candles to fetch

        Note: THREE_MINUTE is not natively supported by Coinbase, so it's synthesized
        by aggregating ONE_MINUTE candles.

        Caching: Uses per-timeframe TTL (e.g., 15-min candles cached for 15 minutes).
        This dramatically reduces API calls since candles don't change until the next
        candle closes.
        """
        # Candle data is public (same for all users/accounts)
        cache_key = f"{product_id}:{granularity}"

        # Check cache with per-timeframe TTL
        now = datetime.utcnow().timestamp()
        if cache_key in self._candle_cache:
            cached_time, cached_candles = self._candle_cache[cache_key]
            # Get TTL for this specific timeframe (falls back to default for unknown timeframes)
            cache_ttl = CANDLE_CACHE_TTL.get(granularity, CANDLE_CACHE_DEFAULT_TTL)
            age_seconds = now - cached_time
            if age_seconds < cache_ttl:
                # Cache hit - log occasionally for monitoring (every ~5 minutes)
                if int(now) % 300 < 10:  # Log for 10 seconds every 5 minutes
                    logger.debug(
                        f"📦 Cache hit: {product_id} {granularity} (age: {int(age_seconds)}s, TTL: {cache_ttl}s)"
                    )
                return cached_candles

        # Fetch new candles
        try:
            import time

            # Check if this is a synthetic timeframe that needs aggregation
            if granularity in SYNTHETIC_TIMEFRAMES:
                base_timeframe, aggregation_factor = SYNTHETIC_TIMEFRAMES[granularity]

                # Need N x base candles to create the requested number of synthetic candles
                # Coinbase API limit is 300 candles max per request, so we cap accordingly
                base_candles_needed = min(lookback_candles * aggregation_factor, 300)
                base_candles = await self.get_candles_cached(
                    product_id, base_timeframe, base_candles_needed
                )
                if base_candles:
                    # Gap-fill the base candles first (for sparse BTC pairs)
                    # This ensures continuous data like charting platforms show
                    base_interval_seconds = timeframe_to_seconds(base_timeframe)
                    original_count = len(base_candles)
                    base_candles = fill_candle_gaps(base_candles, base_interval_seconds, base_candles_needed)
                    filled_count = len(base_candles)

                    candles = aggregate_candles(base_candles, aggregation_factor)
                    if filled_count > original_count:
                        logger.info(
                            f"  📊 Gap-filled {product_id}: {original_count}→{filled_count} {base_timeframe}, "
                            f"aggregated to {len(candles)} {granularity}"
                        )
                    else:
                        logger.debug(
                            f"Aggregated {len(base_candles)} {base_timeframe} into "
                            f"{len(candles)} {granularity} for {product_id}"
                        )
                    # Cache the aggregated result
                    self._candle_cache[cache_key] = (now, candles)
                    return candles
                logger.debug(f"No {base_timeframe} candles for {product_id}, {granularity} empty")
                return []

            # Calculate time range based on granularity
            granularity_seconds = timeframe_to_seconds(granularity)
            end_time = int(time.time())
            start_time = end_time - (lookback_candles * granularity_seconds)

            candles = await self.exchange.get_candles(
                product_id=product_id, start=start_time, end=end_time, granularity=granularity
            )

            # All exchange adapters now return candles oldest-first (chronological)

            # Gap-fill sparse candles (BTC pairs often have low volume)
            # This ensures indicators have continuous data like charting platforms
            if candles and len(candles) > 0:
                original_count = len(candles)
                candles = fill_candle_gaps(candles, granularity_seconds, lookback_candles)
                if len(candles) > original_count:
                    logger.info(
                        f"  📊 Gap-filled {product_id} {granularity}: {original_count}→{len(candles)} candles"
                    )

            # Cache the result
            self._candle_cache[cache_key] = (now, candles)

            return candles

        except Exception as e:
            logger.error(f"Error fetching candles for {product_id} ({granularity}): {e}")
            return []

    async def process_bot(self, db: AsyncSession, bot: Bot, skip_ai_analysis: bool = False) -> Dict[str, Any]:
        """
        Process signals for a single bot across all its trading pairs

        Args:
            db: Database session
            bot: Bot instance to process
            skip_ai_analysis: If True, skip expensive AI analysis and use recent AI opinions from database

        Returns:
            Result dictionary with action/signal info for all pairs
        """
        try:
            print(f"🔍 process_bot() ENTERED for {bot.name}")

            # Bull flag strategy uses a different processing flow
            if bot.strategy_type == "bull_flag":
                return await self.process_bull_flag_bot(db, bot)
            # Get all trading pairs for this bot (supports multi-pair)
            trading_pairs = bot.get_trading_pairs()
            print(f"🔍 Got {len(trading_pairs)} trading pairs: {trading_pairs}")

            # Get pairs with open positions (always need to monitor these)
            from app.models import Position
            open_pos_query = select(Position).where(Position.bot_id == bot.id, Position.status == "open")
            open_pos_result = await db.execute(open_pos_query)
            open_positions = list(open_pos_result.scalars().all())
            pairs_with_positions = {p.product_id for p in open_positions if p.product_id}

            # Filter pairs by allowed categories (bot-level control)
            # BUT always include pairs with existing positions
            allowed_categories = bot.strategy_config.get("allowed_categories") if bot.strategy_config else None
            if allowed_categories:
                filtered_pairs = await filter_pairs_by_allowed_categories(
                    db, trading_pairs, allowed_categories, user_id=bot.user_id
                )
                # Add back any pairs with open positions (must monitor existing positions!)
                trading_pairs = list(set(filtered_pairs) | pairs_with_positions)
                print(f"🔍 After category filter: {len(trading_pairs)} trading pairs: {trading_pairs}")
                if pairs_with_positions - set(filtered_pairs):
                    extra = len(pairs_with_positions - set(filtered_pairs))
                    logger.info(
                        f"  Including {extra} pairs with open positions"
                        " despite category filter"
                    )

            logger.info(
                f"Processing bot: {bot.name} with {len(trading_pairs)} pair(s): {trading_pairs} ({bot.strategy_type})"
            )

            # If bot is stopped, filter to only pairs with open positions (for DCA/exit)
            if not bot.is_active:
                trading_pairs = [p for p in trading_pairs if p in pairs_with_positions]
                logger.info(f"  ⏸️  Bot is STOPPED - filtered to {len(trading_pairs)} pairs with open positions")
                if len(trading_pairs) == 0:
                    logger.info("  ℹ️  No open positions to manage - skipping analysis")
                    return {"action": "skip", "reason": "Bot stopped with no open positions"}

            # Check if strategy supports batch analysis (AI strategies)
            # Note: For batch mode, we use bot's current config since batch mode only applies to new analysis
            # Individual positions will still use frozen config in process_bot_pair
            print(f"🔍 Getting strategy instance for {bot.strategy_type}...")
            # Inject user_id into strategy config for per-user AI API key lookup
            strategy_config_with_user = {**bot.strategy_config, "user_id": bot.user_id}
            strategy = StrategyRegistry.get_strategy(bot.strategy_type, strategy_config_with_user)
            print("🔍 Strategy instance created")
            supports_batch = hasattr(strategy, "analyze_multiple_pairs_batch") and len(trading_pairs) > 1
            print(f"🔍 Supports batch: {supports_batch}")

            if supports_batch:
                print("🔍 Calling process_bot_batch()...")
                logger.info(f"🚀 Using BATCH analysis mode - {len(trading_pairs)} pairs in 1 API call!")
                result = await self.process_bot_batch(db, bot, trading_pairs, strategy, skip_ai_analysis)
                print("✅ process_bot_batch() returned")
                return result
            else:
                logger.info("Using sequential analysis mode")
                # Original sequential processing logic

                # Check capacity: filter to only pairs with positions when at max capacity
                from app.models import Position
                open_pos_query = select(Position).where(Position.bot_id == bot.id, Position.status == "open")
                open_pos_result = await db.execute(open_pos_query)
                open_positions = list(open_pos_result.scalars().all())
                open_count = len(open_positions)
                max_concurrent_deals = bot.strategy_config.get("max_concurrent_deals", 1)

                if open_count >= max_concurrent_deals:
                    # At max capacity - only analyze pairs with open positions (for DCA/exit signals)
                    pairs_with_positions = {p.product_id for p in open_positions if p.product_id}
                    original_count = len(trading_pairs)
                    trading_pairs = [p for p in trading_pairs if p in pairs_with_positions]
                    logger.info(f"  📊 Bot at max capacity ({open_count}/{max_concurrent_deals} positions)")
                    logger.info(f"  🎯 Analyzing only {len(trading_pairs)} pairs with open positions")
                    if original_count > len(trading_pairs):
                        skipped = original_count - len(trading_pairs)
                        logger.info(
                            f"  ⏭️  Skipping {skipped} pairs without"
                            " positions (no room for new entries)"
                        )
                else:
                    logger.info(f"  📊 Bot below capacity ({open_count}/{max_concurrent_deals} positions)")

                # Process trading pairs in batches to avoid Coinbase API throttling
                results = {}
                batch_size = 5

                for i in range(0, len(trading_pairs), batch_size):
                    batch = trading_pairs[i:i + batch_size]
                    logger.info(f"  Processing batch {i // batch_size + 1} ({len(batch)} pairs): {batch}")

                    # Process batch sequentially to avoid DB session conflicts
                    batch_results = []
                    for product_id in batch:
                        try:
                            result = await self.process_bot_pair(db, bot, product_id, skip_ai_analysis=skip_ai_analysis)
                            batch_results.append(result)
                        except Exception as e:
                            logger.error(f"  Error processing {product_id}: {e}")
                            batch_results.append({"error": str(e)})
                        # Throttle between pairs to reduce CPU burst (t2.micro friendly)
                        await asyncio.sleep(PAIR_PROCESSING_DELAY_SECONDS)

                    # Store results
                    for product_id, result in zip(batch, batch_results):
                        if isinstance(result, Exception):
                            logger.error(f"  Error processing {product_id}: {result}")
                            results[product_id] = {"error": str(result)}
                        else:
                            results[product_id] = result

                    # Add delay between batches (if not last batch)
                    if i + batch_size < len(trading_pairs):
                        logger.info("  Waiting 1s before next batch to avoid API throttling...")
                        await asyncio.sleep(1)

                return results

        except Exception as e:
            logger.error(f"Error processing bot {bot.name}: {e}")
            import traceback

            traceback.print_exc()
            return {"error": str(e)}

    async def process_bot_batch(
        self, db: AsyncSession, bot: Bot, trading_pairs: List[str], strategy: Any, skip_ai_analysis: bool = False
    ) -> Dict[str, Any]:
        """
        Process multiple trading pairs using AI batch analysis (single API call for all pairs)

        Args:
            db: Database session
            bot: Bot instance
            trading_pairs: List of product IDs to analyze
            strategy: Strategy instance that supports batch analysis
            skip_ai_analysis: If True, skip AI analysis and check only technical conditions

        Returns:
            Result dictionary with action/signal info for all pairs
        """
        try:
            print("🔍 process_bot_batch() ENTERED")
            from app.models import Position

            print("🔍 Checking open positions...")
            # Check how many open positions this bot has
            open_positions_query = select(Position).where(Position.bot_id == bot.id, Position.status == "open")
            open_positions_result = await db.execute(open_positions_query)
            open_positions = list(open_positions_result.scalars().all())
            open_count = len(open_positions)
            print(f"🔍 Found {open_count} open positions")

            # Refresh bot from database to get latest config (in case max_concurrent_deals changed)
            await db.refresh(bot)

            # Get max concurrent deals from strategy config
            max_concurrent_deals = bot.strategy_config.get("max_concurrent_deals", 1)
            print(f"🔍 Max concurrent deals: {max_concurrent_deals}")

            # Calculate available budget for new positions
            # Bypass cache for position creation to ensure accurate budget allocation
            quote_currency = bot.get_quote_currency()
            try:
                if quote_currency == "BTC":
                    aggregate_value = await self.exchange.calculate_aggregate_btc_value(bypass_cache=True)
                else:  # USD
                    aggregate_value = await self.exchange.calculate_aggregate_usd_value()
            except Exception as e:
                # If portfolio API fails (403/rate limit), use a conservative fallback
                logger.warning(f"  ⚠️  Failed to get aggregate balance (API error), using 0.001 BTC fallback: {e}")
                aggregate_value = 0.001  # Conservative fallback - allows ~3 positions at 30% budget

            # Get actual available balance (what's spendable right now)
            try:
                if quote_currency == "BTC":
                    actual_available = await self.exchange.get_btc_balance()
                else:  # USD
                    actual_available = await self.exchange.get_usd_balance()
            except Exception as e:
                logger.warning(f"  ⚠️  Failed to get actual available balance: {e}")
                actual_available = 0.0

            # Defensive logging: Warn if aggregate value is suspiciously low
            if aggregate_value < 0.0001:
                logger.warning(
                    f"  ⚠️  SUSPICIOUS: Aggregate {quote_currency} value is very low"
                    f" ({aggregate_value:.8f}). This may indicate API issues."
                )
                logger.warning("  ⚠️  Bot may be unable to open new positions due to insufficient calculated balance.")

            # Calculate bot's reserved balance (percentage of total account value from bot config)
            reserved_balance = bot.get_reserved_balance(aggregate_value)
            budget_pct = bot.budget_percentage

            # Calculate how much budget is already used by this bot's positions
            total_in_positions = sum(p.total_quote_spent for p in open_positions)

            # Available budget = max allowed - already in use
            available_budget = reserved_balance - total_in_positions

            # Calculate minimum required per new position (budget / max_deals)
            min_per_position = reserved_balance / max(max_concurrent_deals, 1)

            # Determine if we have enough budget for new positions or DCA
            # Must pass TWO checks:
            # 1. Has room in allocation (available_budget >= min_per_position)
            # 2. Has actual spendable balance (actual_available >= min_per_position)
            has_allocation_room = available_budget >= min_per_position
            has_actual_balance = actual_available >= min_per_position
            has_budget_for_new = has_allocation_room and has_actual_balance

            logger.warning(
                f"  💰 Budget: {reserved_balance:.8f} {quote_currency} reserved ({budget_pct}% of {aggregate_value:.8f})"
            )
            logger.warning(
                f"  💰 In positions: {total_in_positions:.8f} {quote_currency},"
                f" Available allocation: {available_budget:.8f} {quote_currency}"
            )
            logger.warning(
                f"  💰 Actual {quote_currency} balance: {actual_available:.8f} {quote_currency}"
            )
            logger.warning(
                f"  💰 Min per position: {min_per_position:.8f} {quote_currency}"
            )
            logger.warning(
                f"  💰 Has allocation room: {has_allocation_room},"
                f" Has actual balance: {has_actual_balance},"
                f" Can open new: {has_budget_for_new}"
            )

            # Determine which pairs to analyze
            pairs_to_analyze = trading_pairs

            # If bot is stopped, only analyze pairs with open positions (for DCA/exit signals)
            if not bot.is_active:
                pairs_with_positions = {p.product_id for p in open_positions if p.product_id}
                pairs_to_analyze = [p for p in trading_pairs if p in pairs_with_positions]
                logger.info(
                    f"  ⏸️  Bot is STOPPED - analyzing only {len(pairs_to_analyze)}"
                    " pairs with open positions for DCA/exit"
                )
                if len(pairs_to_analyze) == 0:
                    logger.info("  ℹ️  No open positions to manage - skipping analysis")
                    return {"action": "skip", "reason": "Bot stopped with no open positions"}

            elif open_count >= max_concurrent_deals:
                # At capacity - only analyze pairs with open positions (for sell signals)
                pairs_with_positions = {p.product_id for p in open_positions if p.product_id}
                pairs_to_analyze = [p for p in trading_pairs if p in pairs_with_positions]

                if len(pairs_to_analyze) < len(trading_pairs):
                    logger.info(f"  📊 Bot at max capacity ({open_count}/{max_concurrent_deals} positions)")
                    logger.info(
                        f"  🎯 Analyzing only {len(pairs_to_analyze)} pairs with open positions: {pairs_to_analyze}"
                    )
                    logger.info(f"  ⏭️  Skipping {len(trading_pairs) - len(pairs_to_analyze)} pairs without positions")
            elif not has_budget_for_new:
                # Insufficient budget - only analyze pairs with open positions (for sell signals, no new buys/DCA)
                pairs_with_positions = {p.product_id for p in open_positions if p.product_id}
                pairs_to_analyze = [p for p in trading_pairs if p in pairs_with_positions]

                logger.warning(
                    f"  ⚠️  INSUFFICIENT FUNDS: Only {available_budget:.8f}"
                    f" {quote_currency} available, need {min_per_position:.8f}"
                )
                logger.info(
                    f"  💰 Skipping new position analysis - analyzing only"
                    f" {len(pairs_to_analyze)} pairs with open positions for sell signals"
                )
                logger.info("  ℹ️  Will resume looking for new opportunities once funds are available")
            else:
                # Below capacity AND has budget - analyze all configured pairs (looking for buy + sell signals)
                logger.info(f"  📊 Bot below capacity ({open_count}/{max_concurrent_deals} positions)")
                logger.info(f"  🔍 Analyzing all {len(trading_pairs)} pairs for opportunities")

                # Filter by minimum daily volume (only for NEW positions, not existing ones)
                # Pairs with open positions are ALWAYS analyzed so AI can recommend sells
                min_daily_volume = strategy.config.get("min_daily_volume", 0.0)
                if min_daily_volume > 0:
                    logger.info(f"  📊 Filtering pairs by minimum 24h volume: {min_daily_volume}")
                    # Get pairs that have existing positions - these bypass volume filter
                    pairs_with_existing_positions = {p.product_id for p in open_positions if p.product_id}
                    filtered_pairs = []
                    for product_id in pairs_to_analyze:
                        # Always include pairs with existing positions (for sell analysis)
                        if product_id in pairs_with_existing_positions:
                            filtered_pairs.append(product_id)
                            logger.info(f"    🔒 {product_id}: Has open position (bypassing volume filter)")
                            continue

                        try:
                            stats = await self.exchange.get_product_stats(product_id)
                            volume_24h = stats.get("volume_24h", 0.0)

                            if volume_24h >= min_daily_volume:
                                filtered_pairs.append(product_id)
                                logger.info(f"    ✅ {product_id}: Volume {volume_24h:.2f} (meets threshold)")
                            else:
                                logger.info(f"    ⏭️  {product_id}: Volume {volume_24h:.2f} (below {min_daily_volume})")
                        except Exception as e:
                            logger.warning(
                                f"    ⚠️  {product_id}: Could not fetch volume"
                                f" stats ({e}), including anyway"
                            )
                            filtered_pairs.append(product_id)  # Include pairs where we can't get stats

                    pairs_to_analyze = filtered_pairs
                    logger.info(f"  📊 After volume filter: {len(pairs_to_analyze)} pairs remain")

            if not pairs_to_analyze:
                logger.info("  ⏭️  No pairs to analyze")
                return {}

            # Collect market data for pairs we're analyzing
            pairs_data = {}
            failed_pairs = {}  # Track pairs that failed to load data
            successful_pairs = set()  # Track pairs that succeeded (to clear stale errors)
            print(f"🔍 Fetching market data for {len(pairs_to_analyze)} pairs...")
            logger.info(f"  Fetching market data for {len(pairs_to_analyze)} pairs...")

            # Check which pairs have open positions (critical to retry)
            pairs_with_positions = {p.product_id for p in open_positions if p.product_id}

            for product_id in pairs_to_analyze:
                print(f"🔍 Fetching data for {product_id}...")
                has_open_position = product_id in pairs_with_positions
                max_retries = 3 if has_open_position else 1  # Retry more for open positions

                success = False
                last_error = None

                for attempt in range(max_retries):
                    try:
                        if attempt > 0:
                            logger.info(f"  🔄 Retry {attempt}/{max_retries-1} for {product_id}")
                            await asyncio.sleep(0.5 * attempt)  # Brief backoff

                        # Get candles for multiple timeframes (for BB%, MACD crossing, etc.)
                        candles = await self.get_candles_cached(product_id, "FIVE_MINUTE", 100)
                        # Fetch 300 ONE_MINUTE candles (max allowed by Coinbase API per request)
                        # This allows up to 100 THREE_MINUTE candles (300/3 = 100)
                        one_min_candles = await self.get_candles_cached(product_id, "ONE_MINUTE", 300)
                        # THREE_MINUTE is synthetic (aggregated from 1-min) but now supported
                        three_min_candles = await self.get_candles_cached(product_id, "THREE_MINUTE", 100)
                        # TEN_MINUTE is synthetic (aggregated from 5-min)
                        ten_min_candles = await self.get_candles_cached(product_id, "TEN_MINUTE", 100)
                        # ONE_HOUR candles for hourly MACD/RSI conditions
                        one_hour_candles = await self.get_candles_cached(product_id, "ONE_HOUR", 100)
                        # Higher timeframes for multi-timeframe indicator conditions
                        fifteen_min_candles = await self.get_candles_cached(product_id, "FIFTEEN_MINUTE", 100)
                        four_hour_candles = await self.get_candles_cached(product_id, "FOUR_HOUR", 100)

                        # Get current price from most recent candle (more reliable than ticker!)
                        if not candles or len(candles) == 0:
                            last_error = "No candles available from API"
                            if attempt < max_retries - 1:
                                continue  # Retry
                            logger.warning(f"  ⚠️  {product_id}: {last_error} after {max_retries} attempts")
                            break

                        current_price = float(candles[-1].get("close", 0))

                        # Validate price
                        if current_price is None or current_price <= 0:
                            last_error = f"Invalid price: {current_price}"
                            if attempt < max_retries - 1:
                                continue  # Retry
                            logger.warning(f"  ⚠️  {product_id}: {last_error} after {max_retries} attempts")
                            break

                        # Build candles_by_timeframe for multi-timeframe indicator calculation
                        candles_by_timeframe = {"FIVE_MINUTE": candles}
                        if one_min_candles and len(one_min_candles) > 0:
                            candles_by_timeframe["ONE_MINUTE"] = one_min_candles
                        if three_min_candles and len(three_min_candles) >= 20:
                            # Need at least 20 THREE_MINUTE candles for reliable BB% calculation
                            candles_by_timeframe["THREE_MINUTE"] = three_min_candles
                            logger.debug(
                                f"  ✅ THREE_MINUTE OK for {product_id}: {len(three_min_candles)} candles"
                            )
                        else:
                            # Log why THREE_MINUTE is insufficient
                            # Note: three_min_candles already went through gap-filling in get_candles_cached
                            three_min_count = len(three_min_candles) if three_min_candles else 0
                            logger.warning(
                                f"  ⚠️ THREE_MINUTE insufficient for {product_id}: "
                                f"have {three_min_count}/20 candles after gap-filling (very low volume pair)"
                            )
                        # Add TEN_MINUTE candles for multi-timeframe conditions
                        if ten_min_candles and len(ten_min_candles) >= 36:
                            candles_by_timeframe["TEN_MINUTE"] = ten_min_candles
                            logger.debug(
                                f"  ✅ TEN_MINUTE OK for {product_id}: {len(ten_min_candles)} candles"
                            )
                        # Add ONE_HOUR candles for hourly MACD/RSI conditions
                        if one_hour_candles and len(one_hour_candles) >= 36:
                            # Need at least 36 candles for MACD (26 slow + 9 signal + buffer for crossing)
                            candles_by_timeframe["ONE_HOUR"] = one_hour_candles
                            logger.debug(
                                f"  ✅ ONE_HOUR OK for {product_id}: {len(one_hour_candles)} candles"
                            )
                        # Add FIFTEEN_MINUTE candles for multi-timeframe conditions
                        if fifteen_min_candles and len(fifteen_min_candles) >= 36:
                            candles_by_timeframe["FIFTEEN_MINUTE"] = fifteen_min_candles
                            logger.debug(
                                f"  ✅ FIFTEEN_MINUTE OK for {product_id}: {len(fifteen_min_candles)} candles"
                            )
                        # Add FOUR_HOUR candles for longer timeframe conditions
                        if four_hour_candles and len(four_hour_candles) >= 36:
                            candles_by_timeframe["FOUR_HOUR"] = four_hour_candles
                            logger.debug(
                                f"  ✅ FOUR_HOUR OK for {product_id}: {len(four_hour_candles)} candles"
                            )

                        # Prepare market context (for AI batch analysis)
                        market_context = prepare_market_context(candles, current_price)

                        pairs_data[product_id] = {
                            "current_price": current_price,
                            "candles": candles,
                            "candles_by_timeframe": candles_by_timeframe,
                            "market_context": market_context,
                        }
                        success = True
                        break  # Success, exit retry loop

                    except Exception as e:
                        last_error = str(e)
                        if attempt < max_retries - 1:
                            logger.warning(f"  ⚠️  {product_id}: Error on attempt {attempt+1}: {e}, retrying...")
                            continue  # Retry
                        logger.error(f"  ❌ {product_id}: Error after {max_retries} attempts: {e}")

                # Track failures and successes for open positions
                if not success and has_open_position:
                    failed_pairs[product_id] = last_error
                    logger.error(f"  🚨 CRITICAL: Failed to fetch data for open position {product_id}: {last_error}")
                elif success and has_open_position:
                    # Track successful fetches so we can clear any stale errors
                    successful_pairs.add(product_id)

                # Throttle between pairs to reduce CPU burst (t2.micro friendly)
                await asyncio.sleep(PAIR_PROCESSING_DELAY_SECONDS)

            # Calculate per-position budget (total budget / max concurrent deals)
            max_concurrent_deals = bot.strategy_config.get("max_concurrent_deals", 1)
            # Get total bot budget using Bot's get_reserved_balance method
            quote_currency = bot.get_quote_currency()
            if quote_currency == "BTC":
                # Calculate aggregate BTC value if needed
                aggregate_btc = await self.exchange.calculate_aggregate_btc_value()
                total_bot_budget = bot.get_reserved_balance(aggregate_btc)
            else:
                # USD bots - get balance directly (no aggregation needed)
                total_bot_budget = bot.get_reserved_balance()

            # Only split budget if split_budget_across_pairs is enabled
            # Otherwise each deal gets the full budget (3Commas style)
            if bot.split_budget_across_pairs and max_concurrent_deals > 0:
                per_position_budget = total_bot_budget / max_concurrent_deals
                print(
                    f"💰 Budget calculation (SPLIT): Total={total_bot_budget:.8f},"
                    f" MaxDeals={max_concurrent_deals},"
                    f" PerPosition={per_position_budget:.8f}"
                )
            else:
                per_position_budget = total_bot_budget
                print(
                    f"💰 Budget calculation (FULL): Total={total_bot_budget:.8f},"
                    f" MaxDeals={max_concurrent_deals},"
                    f" PerPosition={per_position_budget:.8f}"
                    " (each deal gets full budget)"
                )

            # Call batch AI analysis (1 API call for ALL pairs!) - or skip if technical-only check
            if skip_ai_analysis:
                print("⏭️  Skipping AI analysis (technical-only check)")
                logger.info(f"  ⏭️  SKIPPING AI: Technical-only check for {len(pairs_data)} pairs")
                # When skipping AI, we only check existing positions (DCA, TP logic)
                # Don't open new positions without fresh AI analysis
                batch_analyses = {
                    product_id: {"signal_type": "hold", "confidence": 0, "reasoning": "Technical-only check (no AI)"}
                    for product_id in pairs_data.keys()
                }
            else:
                print(f"🔍 About to call AI batch analysis for {len(pairs_data)} pairs...")
                logger.info(f"  🧠 Calling AI for batch analysis of {len(pairs_data)} pairs...")
                batch_analyses = await strategy.analyze_multiple_pairs_batch(pairs_data, per_position_budget)
                print(f"✅ AI batch analysis returned with {len(batch_analyses)} results")
                logger.info(f"  ✅ Received {len(batch_analyses)} analyses from AI")

            # Process each pair's analysis result
            results = {}
            print(f"🔍 Processing {len(pairs_data)} pairs from batch analysis...")
            logger.info(f"  📋 Processing {len(pairs_data)} pairs from batch analysis...")
            for product_id in pairs_data.keys():
                try:
                    print(f"🔍 Processing result for {product_id}...")
                    signal_data = batch_analyses.get(
                        product_id, {"signal_type": "hold", "confidence": 0, "reasoning": "No analysis result"}
                    )

                    # Debug logging to track duplicate opinions
                    logger.info(
                        f"    Processing {product_id}:"
                        f" {signal_data.get('signal_type')}"
                        f" ({signal_data.get('confidence')}%)"
                    )

                    # Add current_price to signal_data for DCA logic (AI response doesn't include it)
                    pair_info = pairs_data.get(product_id, {})
                    signal_data["current_price"] = pair_info.get("current_price", 0)

                    # Only log actual AI analysis, not technical-only checks (reduces UI noise)
                    ai_log_entry = None
                    if signal_data.get("reasoning") != "Technical-only check (no AI)":
                        print(f"🔍 Logging AI decision for {product_id}...")
                        # Log AI decision with position info if one exists
                        ai_log_entry = await self.log_ai_decision(
                            db, bot, product_id, signal_data, pair_info, open_positions
                        )
                        print(f"✅ Logged AI decision for {product_id}")

                        # Mark signal as already logged to prevent duplicate logging in trading_engine_v2.py
                        signal_data["_already_logged"] = True
                    else:
                        # Technical-only check - still mark as logged to skip duplicate logging
                        signal_data["_already_logged"] = True

                    print(f"🔍 Executing trading logic for {product_id}...")
                    # Execute trading logic based on signal
                    result = await self.execute_trading_logic(db, bot, product_id, signal_data, pair_info)
                    print(f"✅ Trading logic complete for {product_id}")
                    results[product_id] = result

                    # Rate limit between order attempts to avoid Coinbase 403 throttling
                    # Coinbase returns 403 (not 429) when requests are too rapid
                    await asyncio.sleep(PAIR_PROCESSING_DELAY_SECONDS)

                    # Update AI log with position_id if a NEW position was created (not existing)
                    if ai_log_entry and result.get("position") and not ai_log_entry.position_id:
                        position = result["position"]
                        ai_log_entry.position_id = position.id
                        ai_log_entry.position_status = "open"  # New position just opened
                        logger.info(f"  🔗 Linked AI log to new position #{position.id} for {product_id}")

                except Exception as e:
                    logger.error(f"  Error processing {product_id} result: {e}")
                    results[product_id] = {"error": str(e)}

            # Log errors to positions that failed to load market data
            if failed_pairs:
                from datetime import datetime

                logger.info(f"  💾 Logging {len(failed_pairs)} market data errors to positions...")
                for product_id, error_msg in failed_pairs.items():
                    # Find the position for this product
                    position = next((p for p in open_positions if p.product_id == product_id), None)
                    if position:
                        position.last_error_message = f"Market data fetch failed: {error_msg}"
                        position.last_error_timestamp = datetime.utcnow()
                        logger.info(f"    📝 Position #{position.id} ({product_id}): Error logged")

            # Clear stale errors for positions that succeeded this cycle
            if successful_pairs:
                cleared_count = 0
                for product_id in successful_pairs:
                    position = next((p for p in open_positions if p.product_id == product_id), None)
                    if position and position.last_error_message:
                        position.last_error_message = None
                        position.last_error_timestamp = None
                        cleared_count += 1
                        logger.debug(f"    ✅ Position #{position.id} ({product_id}): Stale error cleared")
                if cleared_count > 0:
                    logger.info(f"  🧹 Cleared {cleared_count} stale error(s) from positions")

            # Note: bot.last_signal_check is updated BEFORE processing starts (in monitor_loop)
            # to prevent race conditions where the same bot gets processed twice
            print("🔍 Committing database changes...")
            await db.commit()
            print("✅ Database committed, returning results")

            return results

        except Exception as e:
            logger.error(f"Error in batch processing: {e}")
            import traceback

            traceback.print_exc()
            return {"error": str(e)}

    async def log_ai_decision(
        self, db: AsyncSession, bot: Bot, product_id: str,
        signal_data: Dict[str, Any], pair_data: Dict[str, Any],
        open_positions: List = None
    ):
        """Log AI decision to database and return the log entry"""
        try:
            import traceback

            from app.models import AIBotLog

            # DEBUG: Log stack trace to find duplicate calls
            stack = "".join(traceback.format_stack()[-5:-1])
            logger.info(
                f"  📝 Logging AI decision for Bot #{bot.id} {product_id}:"
                f" {signal_data.get('signal_type')}"
                f" ({signal_data.get('confidence')}%)"
            )
            logger.debug(f"  Call stack:\n{stack}")

            # Extract only additional context (avoid duplicating fields already in columns)
            additional_context = signal_data.get("context", {})  # Get nested context if exists
            if not additional_context and isinstance(signal_data, dict):
                # Build minimal context from signal_data, excluding fields that have dedicated columns
                excluded_fields = {"reasoning", "signal_type", "confidence"}
                additional_context = {k: v for k, v in signal_data.items() if k not in excluded_fields}

            # Determine position status from open positions
            position_status = "none"
            existing_position = None
            if open_positions:
                existing_position = next((p for p in open_positions if p.product_id == product_id), None)
                if existing_position:
                    position_status = existing_position.status  # "open" or "closed"

            log_entry = AIBotLog(
                bot_id=bot.id,
                thinking=signal_data.get("reasoning", ""),
                decision=signal_data.get("signal_type", "hold"),
                confidence=signal_data.get("confidence", 0),
                current_price=pair_data.get("current_price"),
                position_status=position_status,
                position_id=existing_position.id if existing_position else None,
                product_id=product_id,
                context=additional_context,  # Only store additional context, not duplicate fields
            )
            db.add(log_entry)
            # Don't flush here - let the session commit handle it to avoid greenlet async issues
            return log_entry

        except Exception as e:
            logger.error(f"Error logging AI decision for {product_id}: {e}")
            # Don't rollback here - let the outer transaction handle it
            # Rolling back mid-batch corrupts the async session state
            return None

    async def execute_trading_logic(
        self, db: AsyncSession, bot: Bot, product_id: str, signal_data: Dict[str, Any], pair_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute trading logic for a single pair based on AI signal"""
        # Reuse existing process_bot_pair logic but with pre-analyzed signal
        # This avoids code duplication
        # Pass commit=False to prevent mid-batch commits that corrupt the session
        return await self.process_bot_pair(
            db, bot, product_id, pre_analyzed_signal=signal_data, pair_data=pair_data, commit=False
        )

    async def process_bot_pair(
        self, db: AsyncSession, bot: Bot, product_id: str,
        pre_analyzed_signal=None, pair_data=None, commit=True,
        skip_ai_analysis: bool = False
    ) -> Dict[str, Any]:
        """
        Process signals for a single bot/pair combination

        Args:
            db: Database session
            bot: Bot instance to process
            product_id: Trading pair to evaluate (e.g., "ETH-BTC")
            pre_analyzed_signal: Pre-analyzed signal from batch analysis (optional)
            pair_data: Pre-fetched market data from batch analysis (optional)
            commit: Whether to commit the database session after processing (default: True)
                    Set to False when processing in batch mode to avoid corrupting the session
            skip_ai_analysis: If True, skip AI analysis and check only technical conditions

        Returns:
            Result dictionary with action/signal info
        """
        try:
            logger.info(f"  Evaluating pair: {product_id}")

            # Get strategy instance for this bot
            try:
                # Get ALL open positions for this pair (supports simultaneous same-pair deals)
                from app.trading_engine.position_manager import (
                    all_positions_exhausted_safety_orders,
                    get_active_positions_for_pair,
                )

                all_pair_positions = await get_active_positions_for_pair(db, bot, product_id)
                existing_position = all_pair_positions[0] if all_pair_positions else None

                if existing_position and existing_position.strategy_config_snapshot:
                    # Use frozen config from position (like 3Commas)
                    strategy_config = existing_position.strategy_config_snapshot.copy()
                    logger.info(f"    Using FROZEN strategy config from position #{existing_position.id}")
                else:
                    # Use current bot config (for new positions or legacy positions without snapshot)
                    strategy_config = bot.strategy_config.copy()
                    logger.info("    Using CURRENT bot strategy config")

                    # Adjust budget percentages if splitting across pairs (only for new positions)
                    if bot.split_budget_across_pairs:
                        max_concurrent_deals = max(strategy_config.get("max_concurrent_deals", 1), 1)
                        logger.info(f"    Splitting budget across {max_concurrent_deals} max concurrent deals")

                        # Adjust percentage-based parameters
                        if "base_order_percentage" in strategy_config:
                            original = strategy_config["base_order_percentage"]
                            strategy_config["base_order_percentage"] = original / max_concurrent_deals
                            logger.info(
                                f"      Base order: {original}% → {strategy_config['base_order_percentage']:.2f}%"
                            )

                        if "safety_order_percentage" in strategy_config:
                            original = strategy_config["safety_order_percentage"]
                            strategy_config["safety_order_percentage"] = original / max_concurrent_deals
                            logger.info(
                                f"      Safety order: {original}% → {strategy_config['safety_order_percentage']:.2f}%"
                            )

                        if "max_btc_usage_percentage" in strategy_config:
                            original = strategy_config["max_btc_usage_percentage"]
                            strategy_config["max_btc_usage_percentage"] = original / max_concurrent_deals
                            logger.info(
                                f"      Max usage: {original}% → {strategy_config['max_btc_usage_percentage']:.2f}%"
                            )

                # Inject user_id into strategy config for per-user AI API key lookup
                strategy_config["user_id"] = bot.user_id
                strategy = StrategyRegistry.get_strategy(bot.strategy_type, strategy_config)
            except ValueError as e:
                logger.error(f"Unknown strategy: {bot.strategy_type}")
                return {"error": str(e)}

            # Use provided pair_data if available (from batch), otherwise fetch market data
            if pair_data:
                logger.info("    Using pre-fetched market data")
                current_price = pair_data.get("current_price", 0)
                candles = pair_data.get("candles", [])
                # Use candles_by_timeframe from pair_data if available (supports multiple timeframes for BB%)
                candles_by_timeframe = pair_data.get("candles_by_timeframe", {"FIVE_MINUTE": candles})
            else:
                # Initialize candles variables for later use
                candles = None
                candles_by_timeframe = {}

                # Fetch candles first to get reliable price
                temp_candles = await self.get_candles_cached(product_id, "FIVE_MINUTE", 100)
                if temp_candles and len(temp_candles) > 0:
                    current_price = float(temp_candles[-1].get("close", 0))
                    logger.info(f"    Current {product_id} price (from candles): {current_price:.8f}")
                else:
                    logger.warning(f"    No candles available for {product_id}, using fallback ticker")
                    current_price = await self.exchange.get_current_price(product_id)
                    logger.info(f"    Current {product_id} price (from ticker): {current_price:.8f}")

            # Simultaneous same-pair deal settings (used for all strategy types)
            max_same_pair = strategy_config.get("max_simultaneous_same_pair", 1)
            max_safety = strategy_config.get("max_safety_orders", 5)
            same_pair_count = len(all_pair_positions)

            # For indicator-based strategies, extract timeframes from conditions
            if bot.strategy_type in ("conditional_dca", "indicator_based"):
                # Phase 3 Optimization: Lazy fetching - only fetch timeframes for current phase
                # Determine which phases we need to check based on position status
                if existing_position:
                    # Check if a simultaneous deal might be possible (need entry phases too)
                    if (same_pair_count < max_same_pair
                            and all_positions_exhausted_safety_orders(all_pair_positions, max_safety)):
                        # Need both DCA/exit for existing AND entry for potential new deal
                        phases_to_check = ["base_order_conditions", "safety_order_conditions", "take_profit_conditions"]
                        print(
                            f"  📊 {same_pair_count} position(s), all SOs exhausted"
                            " - checking entry + DCA + exit phases"
                        )
                    else:
                        # Open position: check safety orders (DCA) + take profit (exit)
                        phases_to_check = ["safety_order_conditions", "take_profit_conditions"]
                        print("  📊 Open position detected - checking DCA + exit phases only")
                else:
                    # No position: check base order (entry) conditions only
                    phases_to_check = ["base_order_conditions"]
                    print("  📊 No position - checking entry phase only")

                # Extract unique timeframes for the phases we actually need
                timeframes_needed = get_timeframes_for_phases(bot.strategy_config, phases_to_check)

                print(
                    f"  📊 Fetching candles for timeframes: {timeframes_needed} "
                    f"(phases: {phases_to_check})"
                )

                # Fetch candles for each unique timeframe
                # Use more lookback for longer timeframes to ensure we get enough data
                candles_by_timeframe = {}
                for timeframe in timeframes_needed:
                    # Coinbase limits: ~300 candles max per request
                    # Stay conservative to ensure we get data
                    lookback_map = {
                        "ONE_MINUTE": 200,
                        "THREE_MINUTE": 200,
                        "FIVE_MINUTE": 200,
                        "TEN_MINUTE": 150,
                        "FIFTEEN_MINUTE": 150,
                        "THIRTY_MINUTE": 100,  # 100 candles = 50 hours
                        "ONE_HOUR": 100,  # 100 candles = 4 days
                        "TWO_HOUR": 100,
                        "FOUR_HOUR": 100,
                        "SIX_HOUR": 100,
                        "ONE_DAY": 100,
                    }
                    lookback = lookback_map.get(timeframe, 100)

                    tf_candles = await self.get_candles_cached(
                        product_id=product_id, granularity=timeframe, lookback_candles=lookback
                    )
                    if tf_candles:
                        logger.info(f"    Got {len(tf_candles)} candles for {timeframe}")
                        candles_by_timeframe[timeframe] = tf_candles
                    else:
                        logger.warning(f"    No candles returned for {timeframe}")

                if not candles_by_timeframe:
                    logger.warning(f"    No candles available for {product_id}")
                    return {"error": "No candles available"}

                # Use first timeframe's candles as default for backward compatibility
                candles = list(candles_by_timeframe.values())[0]
            else:
                # Legacy: Get bot's configured timeframe (default to FIVE_MINUTE if not set)
                timeframe = bot.strategy_config.get("timeframe", "FIVE_MINUTE")
                logger.info(f"  Using timeframe: {timeframe}")

                # Get historical candles for signal analysis (if not already provided via pair_data)
                if not candles:
                    candles = await self.get_candles_cached(
                        product_id=product_id, granularity=timeframe, lookback_candles=100
                    )

                if not candles:
                    logger.warning(f"    No candles available for {product_id}")
                    return {"error": "No candles available"}

                # Only set default candles_by_timeframe if not already populated from pair_data
                # This preserves THREE_MINUTE and other timeframes from batch mode
                if not candles_by_timeframe or len(candles_by_timeframe) == 0:
                    candles_by_timeframe = {timeframe: candles}
                else:
                    logger.info(
                        f"  📊 Using pre-fetched candles_by_timeframe with"
                        f" {len(candles_by_timeframe)} timeframes:"
                        f" {list(candles_by_timeframe.keys())}"
                    )

            # Use pre-analyzed signal if provided (from batch analysis), otherwise analyze now
            if pre_analyzed_signal:
                logger.info("  Using pre-analyzed signal from batch")
                signal_data = pre_analyzed_signal
            elif skip_ai_analysis:
                # Skip AI analysis for technical-only check
                # Pass previous_indicators_cache for crossing detection on ALL strategies
                cache_key = (bot.id, product_id)
                previous_indicators_from_cache = self._previous_indicators_cache.get(cache_key)
                if bot.strategy_type in ("conditional_dca", "indicator_based"):
                    print("  ⏭️  Technical check: Analyzing indicator-based signals")
                    signal_data = await strategy.analyze_signal(
                        candles, current_price, candles_by_timeframe,
                        position=existing_position,
                        previous_indicators_cache=previous_indicators_from_cache,
                        db=db, user_id=bot.user_id, product_id=product_id
                    )
                else:
                    logger.info("  ⏭️  Technical check: Evaluating conditions with cached AI values")
                    signal_data = await strategy.analyze_signal(
                        candles, current_price,
                        position=existing_position,
                        previous_indicators_cache=previous_indicators_from_cache,
                        db=db,
                        user_id=bot.user_id,
                        product_id=product_id,
                        use_cached_ai=True  # Use cached AI values, don't call LLM
                    )
            else:
                # Analyze signal using strategy
                # Pass previous_indicators_cache for crossing detection on ALL strategies
                cache_key = (bot.id, product_id)
                previous_indicators_from_cache = self._previous_indicators_cache.get(cache_key)
                if bot.strategy_type in ("conditional_dca", "indicator_based"):
                    print("  📊 Analyzing indicator-based signals...")
                    signal_data = await strategy.analyze_signal(
                        candles, current_price, candles_by_timeframe,
                        position=existing_position,
                        previous_indicators_cache=previous_indicators_from_cache,
                        db=db, user_id=bot.user_id, product_id=product_id
                    )
                else:
                    signal_data = await strategy.analyze_signal(
                        candles, current_price,
                        position=existing_position,
                        previous_indicators_cache=previous_indicators_from_cache,
                        db=db,
                        user_id=bot.user_id,
                        product_id=product_id
                    )

            # Update previous_indicators cache for ALL strategies (crossing detection)
            if signal_data and "indicators" in signal_data:
                cache_key = (bot.id, product_id)
                self._previous_indicators_cache[cache_key] = signal_data["indicators"].copy()
                logger.debug(f"    Updated previous_indicators cache for {cache_key}")

            # Commit any position changes (e.g., previous_indicators for crossing detection)
            if existing_position is not None:
                await db.commit()

            if not signal_data:
                logger.warning("  No signal from strategy (returned None)")
                return {"action": "none", "reason": "No signal"}

            logger.info(
                f"  Signal data:"
                f" base_order={signal_data.get('base_order_signal')},"
                f" safety_order={signal_data.get('safety_order_signal')},"
                f" take_profit={signal_data.get('take_profit_signal')}"
            )

            signal_type = signal_data.get("signal_type")
            logger.info(f"  🔔 Signal detected: {signal_type}")

            # Log AI decision to database (only for actual AI analysis, not technical-only checks)
            # Handle both direct reasoning field (AI strategies) and indicator-based AI explanations
            reasoning = signal_data.get("reasoning")
            indicators = signal_data.get("indicators", {})
            ai_buy_explanation = indicators.get("ai_buy_explanation") if indicators else None
            ai_sell_explanation = indicators.get("ai_sell_explanation") if indicators else None

            should_log_ai = False
            log_signal_data = signal_data

            if reasoning and reasoning != "Technical-only check (no AI)":
                # Direct AI strategy with reasoning field
                should_log_ai = True
            elif ai_buy_explanation or ai_sell_explanation:
                # indicator_based strategy with AI conditions
                should_log_ai = True

                # Determine clear BUY/SELL/HOLD decision from signals
                base_order = signal_data.get("base_order_signal", False)
                safety_order = signal_data.get("safety_order_signal", False)
                take_profit = signal_data.get("take_profit_signal", False)

                ai_buy_score = indicators.get("ai_buy_score", 0) or 0
                ai_sell_score = indicators.get("ai_sell_score", 0) or 0

                # Determine decision and confidence based on which signal triggered
                # IMPORTANT: Only show SELL if there's actually a position to sell
                has_position = existing_position is not None
                if take_profit and has_position:
                    decision = "sell"
                    confidence = ai_sell_score
                    reasoning = ai_sell_explanation or "Take profit conditions met"
                elif base_order or safety_order:
                    decision = "buy"
                    confidence = ai_buy_score
                    reasoning = ai_buy_explanation or "Buy conditions met"
                else:
                    # For pairs without positions, show AI_BUY analysis
                    # For pairs with positions, show combined analysis
                    decision = "hold"
                    if has_position:
                        confidence = max(ai_buy_score, ai_sell_score)
                        combined_parts = []
                        if ai_buy_explanation:
                            combined_parts.append(f"AI Buy: {ai_buy_explanation}")
                        if ai_sell_explanation:
                            combined_parts.append(f"AI Sell: {ai_sell_explanation}")
                        reasoning = " | ".join(combined_parts) if combined_parts else "Conditions not met"
                    else:
                        # No position - show only BUY analysis (what we need to enter)
                        confidence = ai_buy_score
                        reasoning = ai_buy_explanation or "Waiting for buy conditions"

                log_signal_data = {
                    **signal_data,
                    "signal_type": decision,
                    "reasoning": reasoning,
                    "confidence": confidence,
                }

            if should_log_ai:
                pair_info = {"current_price": current_price}
                # Get open positions for this bot to link logs to positions
                from app.models import Position
                open_pos_query = select(Position).where(Position.bot_id == bot.id, Position.status == "open")
                open_pos_result = await db.execute(open_pos_query)
                open_positions_list = list(open_pos_result.scalars().all())
                await self.log_ai_decision(db, bot, product_id, log_signal_data, pair_info, open_positions_list)
                logger.info(f"  📝 Logged AI decision for {product_id}")

            # Log indicator condition evaluations for indicator-based bots
            # This includes bots with AI indicators - they get BOTH AI logs AND indicator logs
            # Only log when conditions MATCH to reduce noise:
            # - Entry (base_order): log only when entry conditions are met AND bot has capacity
            # - DCA (safety_order): log only when we have a position AND DCA slots available AND DCA conditions are met
            # - Exit (take_profit): log only when we have a position AND exit conditions are met
            condition_details = signal_data.get("condition_details")
            if condition_details:
                has_position = existing_position is not None
                logged_any = False

                # Check if position has DCA slots available (for safety_order logging)
                dca_slots_available = False
                if has_position and existing_position:
                    # Get max safety orders from frozen config or current bot config
                    config = existing_position.strategy_config_snapshot or bot.strategy_config or {}
                    max_safety_orders = config.get("max_safety_orders", 5)
                    # Count completed safety orders (buy trades - 1 for base order)
                    buy_trades = (
                        [t for t in existing_position.trades if t.side == "buy"]
                        if existing_position.trades else []
                    )
                    safety_orders_completed = max(0, len(buy_trades) - 1)
                    dca_slots_available = safety_orders_completed < max_safety_orders

                # Log each phase that has conditions
                for phase, details in condition_details.items():
                    if not details:  # Skip if no conditions for this phase
                        continue
                    phase_signal_key = f"{phase}_signal"
                    conditions_met = signal_data.get(phase_signal_key, False)

                    # Skip DCA/Exit phases when there's no position (irrelevant)
                    if not has_position and phase in ("safety_order", "take_profit"):
                        continue
                    # Skip Entry phase when we already have a position (can't enter twice)
                    if has_position and phase == "base_order":
                        continue
                    # Skip DCA phase when no DCA slots available
                    if phase == "safety_order" and not dca_slots_available:
                        continue

                    # Log ALL evaluations (both passing and failing) for debugging
                    await log_indicator_evaluation(
                        db=db,
                        bot_id=bot.id,
                        product_id=product_id,
                        phase=phase,
                        conditions_met=conditions_met,
                        conditions_detail=details,
                        indicators_snapshot=indicators,
                        current_price=current_price,
                    )
                    logged_any = True
                if logged_any:
                    logger.info(f"  📊 Logged indicator evaluation for {product_id}")

            # Process each existing position for DCA/sell
            result = {"action": "none", "reason": "No signal"}
            for pos in all_pair_positions:
                # For each position, use ITS frozen config if available
                pos_strategy_config = (
                    pos.strategy_config_snapshot.copy()
                    if pos.strategy_config_snapshot
                    else bot.strategy_config.copy()
                )
                pos_strategy_config["user_id"] = bot.user_id
                pos_strategy = StrategyRegistry.get_strategy(bot.strategy_type, pos_strategy_config)

                pos_engine = StrategyTradingEngine(
                    db=db, exchange=self.exchange, bot=bot, strategy=pos_strategy, product_id=product_id,
                )
                pos_result = await pos_engine.process_signal(
                    candles, current_price, pre_analyzed_signal=signal_data,
                    candles_by_timeframe=candles_by_timeframe, position_override=pos,
                )
                logger.info(f"  Position #{pos.id} result: {pos_result['action']} - {pos_result['reason']}")
                # Keep track of most interesting result
                if pos_result.get("action") not in ("none", "hold"):
                    result = pos_result

            # Check if a new simultaneous deal can be opened
            if (bot.is_active
                    and same_pair_count > 0
                    and same_pair_count < max_same_pair
                    and all_positions_exhausted_safety_orders(all_pair_positions, max_safety)):
                # Open new simultaneous deal - pass position=None
                logger.info(f"  🔄 All {same_pair_count} position(s) exhausted SOs — evaluating new simultaneous deal")
                new_engine = StrategyTradingEngine(
                    db=db, exchange=self.exchange, bot=bot, strategy=strategy, product_id=product_id,
                )
                new_result = await new_engine.process_signal(
                    candles, current_price, pre_analyzed_signal=signal_data,
                    candles_by_timeframe=candles_by_timeframe, position_override=None,
                )
                logger.info(f"  New simultaneous deal result: {new_result['action']} - {new_result['reason']}")
                if new_result.get("action") not in ("none", "hold"):
                    result = new_result
            elif same_pair_count == 0:
                # No existing positions - normal flow (process_signal handles base order check)
                engine = StrategyTradingEngine(
                    db=db, exchange=self.exchange, bot=bot, strategy=strategy, product_id=product_id,
                )
                result = await engine.process_signal(
                    candles, current_price, pre_analyzed_signal=signal_data,
                    candles_by_timeframe=candles_by_timeframe,
                )

            logger.info(f"  Result: {result['action']} - {result['reason']}")

            # Note: bot.last_signal_check is updated BEFORE processing starts (in monitor_loop)
            # to prevent race conditions where the same bot gets processed twice
            # Only commit if not in batch mode (batch mode commits once at the end)
            if commit:
                await db.commit()

            return result

        except Exception as e:
            logger.error(f"Error processing bot {bot.name}: {e}", exc_info=True)
            return {"error": str(e)}

    async def process_bull_flag_bot(self, db: AsyncSession, bot: Bot) -> Dict[str, Any]:
        """
        Process a bull flag strategy bot.

        Bull flag bots work differently from other strategies:
        1. Scan allowed USD coins for volume spikes and bull flag patterns
        2. Enter positions when patterns are detected (with TSL at pullback low, TTP at 2x risk)
        3. Monitor existing positions for TSL/TTP exit conditions

        Args:
            db: Database session
            bot: Bot instance with bull_flag strategy

        Returns:
            Result dictionary with actions taken
        """
        from app.models import Position

        try:
            logger.info(f"Processing bull flag bot: {bot.name}")
            results = {"scanned": 0, "opportunities": 0, "entries": [], "exits": [], "errors": []}

            # Step 1: Get open positions for this bot
            open_positions_query = select(Position).where(
                Position.bot_id == bot.id,
                Position.status == "open"
            )
            open_positions_result = await db.execute(open_positions_query)
            open_positions = list(open_positions_result.scalars().all())

            # Step 2: Check trailing stops on existing positions
            for position in open_positions:
                try:
                    # Get current price
                    current_price = await self.exchange.get_current_price(position.product_id)
                    if not current_price or current_price <= 0:
                        logger.warning(f"  Could not get price for {position.product_id}")
                        continue

                    # Check exit conditions (TSL/TTP)
                    should_sell, reason = await check_bull_flag_exit_conditions(
                        position, current_price, db
                    )

                    # Log exit signal check
                    await log_scanner_decision(
                        db=db,
                        bot_id=bot.id,
                        product_id=position.product_id,
                        scan_type="exit_signal",
                        decision="triggered" if should_sell else "hold",
                        reason=reason,
                        current_price=current_price,
                    )

                    if should_sell:
                        logger.info(f"  🔔 Exit signal for {position.product_id}: {reason}")

                        # Execute sell order
                        try:
                            order = await self.exchange.create_market_sell_order(
                                product_id=position.product_id,
                                quantity=position.total_quantity
                            )

                            if order:
                                # Update position
                                position.status = "closed"
                                position.closed_at = datetime.utcnow()
                                position.close_price = current_price
                                await db.commit()

                                results["exits"].append({
                                    "product_id": position.product_id,
                                    "reason": reason,
                                    "price": current_price,
                                    "quantity": position.total_quantity,
                                })
                                logger.info(f"  ✅ Sold {position.product_id}: {reason}")
                        except Exception as e:
                            logger.error(f"  Error executing sell for {position.product_id}: {e}")
                            results["errors"].append(f"Sell error {position.product_id}: {e}")

                except Exception as e:
                    logger.error(f"  Error checking position {position.product_id}: {e}")
                    results["errors"].append(f"Position check error: {e}")

            # Step 3: Check if we can open new positions
            max_concurrent = bot.strategy_config.get("max_concurrent_positions", 5)
            if len(open_positions) >= max_concurrent:
                logger.info(f"  At max positions ({len(open_positions)}/{max_concurrent}), skipping scan")
                # Commit any exit signal logs before returning
                await db.commit()
                return results

            # Step 4: Scan for new opportunities
            # max_scan_coins: configurable limit for rate limiting, defaults to 200 (covers 151 approved)
            max_scan_coins = bot.strategy_config.get("max_scan_coins", 200)
            opportunities = await scan_for_bull_flag_opportunities(
                db=db,
                exchange_client=self.exchange,
                config=bot.strategy_config,
                max_coins=max_scan_coins,
                bot_id=bot.id,  # Pass bot_id for scanner logging
                user_id=bot.user_id,  # Scope blacklist query to this user
            )

            # Commit scanner logs immediately after scan completes
            await db.commit()

            results["scanned"] = len(opportunities)
            results["opportunities"] = len([o for o in opportunities if o.get("pattern")])

            # Filter opportunities by allowed categories
            allowed_categories = bot.strategy_config.get("allowed_categories") if bot.strategy_config else None
            if allowed_categories and opportunities:
                # Extract pairs from opportunities
                opportunity_pairs = [o.get("product_id") for o in opportunities if o.get("product_id")]
                filtered_pairs = await filter_pairs_by_allowed_categories(
                    db, opportunity_pairs, allowed_categories, user_id=bot.user_id
                )
                filtered_pairs_set = set(filtered_pairs)
                # Filter opportunities to only include allowed pairs
                opportunities = [o for o in opportunities if o.get("product_id") in filtered_pairs_set]
                logger.info(f"  Category filtered: {len(opportunities)} opportunities remain")

            # Step 5: Enter positions for valid opportunities
            # Skip coins we already have positions in
            existing_product_ids = {p.product_id for p in open_positions}
            available_slots = max_concurrent - len(open_positions)

            for opportunity in opportunities[:available_slots]:
                product_id = opportunity.get("product_id")
                pattern = opportunity.get("pattern")

                if not product_id or not pattern:
                    continue

                if product_id in existing_product_ids:
                    logger.info(f"  Skipping {product_id} - already have position")
                    continue

                try:
                    # Calculate position size
                    budget_mode = bot.strategy_config.get("budget_mode", "percentage")
                    if budget_mode == "fixed_usd":
                        usd_amount = bot.strategy_config.get("fixed_usd_amount", 100.0)
                    else:
                        # Get aggregate USD value
                        aggregate_usd = await self.exchange.calculate_aggregate_usd_value()
                        budget_pct = bot.strategy_config.get("budget_percentage", 5.0)
                        usd_amount = aggregate_usd * (budget_pct / 100.0)

                    # Check minimum
                    if usd_amount < 10.0:
                        logger.warning(f"  Position size ${usd_amount:.2f} below minimum for {product_id}")
                        continue

                    # Get current price
                    current_price = pattern.get("entry_price", 0)
                    if current_price <= 0:
                        current_price = await self.exchange.get_current_price(product_id)

                    if not current_price or current_price <= 0:
                        logger.warning(f"  Could not get entry price for {product_id}")
                        continue

                    # Calculate quantity
                    quantity = usd_amount / current_price

                    # Execute buy order
                    order = await self.exchange.create_market_buy_order(
                        product_id=product_id,
                        quantity=quantity
                    )

                    if order:
                        # Create position
                        position = Position(
                            bot_id=bot.id,
                            account_id=bot.account_id,
                            product_id=product_id,
                            status="open",
                            opened_at=datetime.utcnow(),
                            average_buy_price=current_price,
                            total_quantity=quantity,
                            total_quote_spent=usd_amount,
                            strategy_type="bull_flag",
                            strategy_config_snapshot=bot.strategy_config.copy(),
                        )

                        # Set up trailing stops using pattern data
                        setup_bull_flag_position_stops(position, pattern)

                        db.add(position)
                        await db.commit()

                        results["entries"].append({
                            "product_id": product_id,
                            "price": current_price,
                            "quantity": quantity,
                            "usd_amount": usd_amount,
                            "stop_loss": pattern.get("stop_loss"),
                            "take_profit_target": pattern.get("take_profit_target"),
                        })

                        logger.info(
                            f"  ✅ Entered {product_id}: ${usd_amount:.2f} at ${current_price:.4f}, "
                            f"SL=${pattern.get('stop_loss'):.4f}, TP=${pattern.get('take_profit_target'):.4f}"
                        )

                        # Update existing_product_ids to prevent duplicate entries
                        existing_product_ids.add(product_id)

                except Exception as e:
                    logger.error(f"  Error entering {product_id}: {e}")
                    results["errors"].append(f"Entry error {product_id}: {e}")

            await db.commit()
            return results

        except Exception as e:
            logger.error(f"Error processing bull flag bot {bot.name}: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    async def _process_single_bot(self, bot: Bot, needs_ai_analysis: bool) -> None:
        """
        Process a single bot with its own DB session and exchange context.

        Designed to run as a concurrent task — each invocation gets its own
        DB session and sets the exchange client via contextvars so that
        self.exchange returns the correct client for this bot.
        """
        async with self._bot_semaphore:
            async with async_session_maker() as db:
                try:
                    # Get exchange client for this bot (per-user/per-account)
                    exchange = await self.get_exchange_for_bot(db, bot)
                    if not exchange:
                        logger.warning(
                            f"No exchange client for bot {bot.name}"
                            f" (account_id={bot.account_id})"
                        )
                        return

                    # Set exchange in task-local context (each asyncio.Task gets its own copy)
                    _ctx_exchange.set(exchange)

                    # Re-fetch bot in this session to avoid detached instance errors
                    result = await db.execute(select(Bot).where(Bot.id == bot.id))
                    local_bot = result.scalar_one_or_none()
                    if not local_bot:
                        logger.warning(f"Bot {bot.id} not found in DB")
                        return

                    # Update timestamp BEFORE processing to prevent race condition
                    local_bot.last_signal_check = datetime.utcnow()
                    if needs_ai_analysis:
                        local_bot.last_ai_check = datetime.utcnow()
                    await db.commit()

                    print(f"🔍 Calling process_bot for {local_bot.name} (AI: {needs_ai_analysis})...")
                    await self.process_bot(db, local_bot, skip_ai_analysis=not needs_ai_analysis)
                    print(f"✅ Finished processing {local_bot.name}")

                    # Calculate and store next check time (aligned to candle boundaries)
                    bot_check_interval = calculate_bot_check_interval(local_bot.strategy_config or {})
                    current_timestamp = int(datetime.utcnow().timestamp())
                    next_check_timestamp = next_check_time_aligned(bot_check_interval, current_timestamp)
                    self._bot_next_check[bot.id] = next_check_timestamp
                    next_check_in = next_check_timestamp - current_timestamp
                    logger.debug(
                        f"📅 {local_bot.name}: Next check in {next_check_in}s "
                        f"(interval: {bot_check_interval}s, aligned to candle close)"
                    )

                except Exception as e:
                    logger.error(f"Error processing bot {bot.name}: {e}")

    async def monitor_loop(self):
        """Main monitoring loop for all active bots"""
        print("🔍 monitor_loop() ENTERED - starting multi-bot monitor loop")
        # Note: self.running is set to True in start() to prevent race conditions

        while self.running:
            print(f"🔁 Monitor loop iteration, self.running={self.running}")
            try:
                async with async_session_maker() as db:
                    # Get all active bots
                    print("🔍 Calling get_active_bots()...")
                    bots = await self.get_active_bots(db)
                    print(f"🔍 Got {len(bots)} bots from get_active_bots()")

                    if not bots:
                        print("⚠️ No active bots to monitor")
                    else:
                        print(f"✅ Monitoring {len(bots)} active bot(s)")

                        # Determine which bots are due for processing
                        bots_to_process: List[tuple] = []  # (bot, needs_ai_analysis)
                        for bot in bots:
                            try:
                                print(f"🔍 Checking bot: {bot.name} (ID: {bot.id})")

                                # Phase 2 Optimization: Smart check scheduling
                                bot_check_interval = calculate_bot_check_interval(bot.strategy_config or {})
                                current_timestamp = int(datetime.utcnow().timestamp())

                                # Check if this bot is due for a check
                                if bot.id in self._bot_next_check:
                                    next_check = self._bot_next_check[bot.id]
                                    if current_timestamp < next_check:
                                        seconds_until = next_check - current_timestamp
                                        print(
                                            f"⏭️  Skipping {bot.name} - not due yet "
                                            f"(next check in {seconds_until}s, interval: {bot_check_interval}s)"
                                        )
                                        continue

                                # Determine if we need AI analysis
                                ai_check_interval = bot.check_interval_seconds or self.interval_seconds
                                needs_ai_analysis = True
                                now = datetime.utcnow()

                                if bot.last_ai_check:
                                    time_since_last_ai_check = (now - bot.last_ai_check).total_seconds()
                                    if time_since_last_ai_check < ai_check_interval:
                                        needs_ai_analysis = False
                                        print(
                                            f"🔧 {bot.name}: Technical-only check "
                                            f"(last AI: {time_since_last_ai_check:.0f}s ago, "
                                            f"AI interval: {ai_check_interval}s, "
                                            f"candle interval: {bot_check_interval}s)"
                                        )
                                    else:
                                        print(
                                            f"🤖 {bot.name}: Full check with AI analysis "
                                            f"(AI: {ai_check_interval}s, candle: {bot_check_interval}s)"
                                        )
                                else:
                                    print(
                                        f"🤖 {bot.name}: First-time AI analysis "
                                        f"(candle interval: {bot_check_interval}s)"
                                    )

                                bots_to_process.append((bot, needs_ai_analysis))
                            except Exception as e:
                                logger.error(f"Error scheduling bot {bot.name}: {e}")
                                continue

                        # Process bots concurrently (semaphore limits to 5 at a time)
                        if bots_to_process:
                            print(f"🚀 Processing {len(bots_to_process)} bot(s) concurrently (max 5 parallel)")
                            tasks = [
                                asyncio.create_task(
                                    self._process_single_bot(bot, needs_ai),
                                    name=f"bot-{bot.id}-{bot.name}"
                                )
                                for bot, needs_ai in bots_to_process
                            ]
                            await asyncio.gather(*tasks, return_exceptions=True)
                            print(f"✅ Finished processing {len(bots_to_process)} bot(s)")

                        # Prune stale entries from unbounded caches
                        active_bot_ids = {b.id for b in bots}
                        active_pairs = set()
                        for b in bots:
                            for p in b.get_trading_pairs():
                                active_pairs.add((b.id, p))

                        # Prune _previous_indicators_cache
                        stale_indicator_keys = [
                            k for k in self._previous_indicators_cache
                            if k not in active_pairs
                        ]
                        for k in stale_indicator_keys:
                            del self._previous_indicators_cache[k]
                        if stale_indicator_keys:
                            logger.debug(
                                f"Pruned {len(stale_indicator_keys)} stale "
                                "entries from indicators cache"
                            )

                        # Prune _bot_next_check for deleted/deactivated bots
                        stale_schedule_keys = [
                            bid for bid in self._bot_next_check
                            if bid not in active_bot_ids
                        ]
                        for bid in stale_schedule_keys:
                            del self._bot_next_check[bid]

                # Wait for next interval - check frequently so bots with short intervals are responsive
                print("🔍 Sleeping 10 seconds before next iteration...")
                await asyncio.sleep(10)  # Check every 10 seconds for bots that need processing
                print("🔍 Woke up from sleep, looping back...")

            except Exception as e:
                print(f"❌ ERROR in monitor loop: {e}")
                logger.error(f"Error in monitor loop: {e}", exc_info=True)
                # Wait a bit before retrying
                await asyncio.sleep(10)

        print("🛑 Multi-bot monitor loop EXITED - self.running is False")
        logger.info("Multi-bot monitor stopped")

    def start(self):
        """Start the monitoring task (synchronous - for backward compatibility)"""
        if not self.running:
            self.running = True  # Set IMMEDIATELY to prevent race condition (double-start)
            self.task = asyncio.create_task(self.monitor_loop())
            # Start order monitor alongside bot monitor (if available)
            if self.order_monitor:
                asyncio.create_task(self.order_monitor.start())
            logger.info("Multi-bot monitor task started")
        else:
            logger.warning("Monitor already running, ignoring duplicate start() call")

    async def start_async(self):
        """Start the monitoring task (async - preferred method)"""
        print(f"🔍 start_async() called, self.running={self.running}")
        if not self.running:
            print("🔍 Setting self.running=True and creating tasks")
            self.running = True  # Set IMMEDIATELY to prevent race condition (double-start)
            self.task = asyncio.create_task(self.monitor_loop())
            # Start order monitor alongside bot monitor (if available)
            if self.order_monitor:
                asyncio.create_task(self.order_monitor.start())
            print("✅ Multi-bot monitor task started")
            # Give the task a moment to actually start
            await asyncio.sleep(0.1)
            print("✅ Multi-bot monitor loop should be running now")
        else:
            print("⚠️ Monitor already running, ignoring duplicate start() call")

    async def stop(self):
        """Stop the monitoring task"""
        self.running = False
        # Stop order monitor (if available)
        if self.order_monitor:
            await self.order_monitor.stop()
        if self.task:
            await self.task
            logger.info("Multi-bot monitor task stopped")

    async def get_status(self) -> Dict[str, Any]:
        """Get monitor status"""
        try:
            async with async_session_maker() as db:
                bots = await self.get_active_bots(db)
                return {
                    "running": self.running,
                    "interval_seconds": self.interval_seconds,
                    "active_bots": len(bots),
                    "bots": [
                        {
                            "id": bot.id,
                            "name": bot.name,
                            "product_ids": bot.get_trading_pairs(),  # Multi-pair support
                            "product_id": (
                                bot.get_trading_pairs()[0] if bot.get_trading_pairs() else None
                            ),  # Legacy compatibility
                            "strategy": bot.strategy_type,
                            "last_check": bot.last_signal_check.isoformat() if bot.last_signal_check else None,
                        }
                        for bot in bots
                    ],
                }
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return {"running": self.running, "interval_seconds": self.interval_seconds, "error": str(e)}
