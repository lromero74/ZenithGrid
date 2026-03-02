"""
Multi-Bot Price Monitor

Monitors prices for all active bots and processes signals using their configured strategies.

Processing logic is split into focused modules:
- monitor/batch_analyzer.py    - process_bot_batch() for AI batch analysis
- monitor/pair_processor.py    - process_bot_pair() for single pair processing
- monitor/bull_flag_processor.py - process_bull_flag_bot() for bull flag strategy
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
from app.monitor.batch_analyzer import process_bot_batch as _process_bot_batch
from app.monitor.bull_flag_processor import process_bull_flag_bot as _process_bull_flag_bot
from app.monitor.pair_processor import process_bot_pair as _process_bot_pair
from app.strategies import StrategyRegistry
from app.utils.candle_utils import (
    SYNTHETIC_TIMEFRAMES,
    aggregate_candles,
    calculate_bot_check_interval,
    fill_candle_gaps,
    next_check_time_aligned,
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
                    # Don't cache paper trading clients — they hold a reference
                    # to the caller's DB session, which becomes stale after the
                    # processing cycle ends. A fresh client is created each cycle.
                    is_paper = (hasattr(client, 'is_paper_trading')
                                and callable(client.is_paper_trading)
                                and client.is_paper_trading())
                    if is_paper:
                        return client
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
        Process signals for a single bot across all its trading pairs.
        Dispatches to specialized processors based on strategy type and pair count.

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
                return await _process_bull_flag_bot(self, db, bot)
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
                result = await _process_bot_batch(self, db, bot, trading_pairs, strategy, skip_ai_analysis)
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
                            result = await _process_bot_pair(
                                self, db, bot, product_id, skip_ai_analysis=skip_ai_analysis
                            )
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
        return await _process_bot_pair(
            self, db, bot, product_id, pre_analyzed_signal=signal_data, pair_data=pair_data, commit=False
        )

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

                        # On first iteration after restart, stagger bots to avoid
                        # SQLite lock contention from all bots writing at once.
                        if not self._bot_next_check and len(bots) > 5:
                            current_ts = int(datetime.utcnow().timestamp())
                            for i, bot in enumerate(bots):
                                # Spread bots across the first 30 seconds (groups of 5 every 2s)
                                delay = (i // 5) * 2
                                self._bot_next_check[bot.id] = current_ts + delay
                            logger.info(
                                f"Staggered {len(bots)} bots across "
                                f"{(len(bots) // 5) * 2}s to reduce startup DB contention"
                            )

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
