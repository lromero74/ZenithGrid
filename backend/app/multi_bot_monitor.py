"""
Multi-Bot Price Monitor

Monitors prices for all active bots and processes signals using their configured strategies.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.exchange_clients.base import ExchangeClient
from app.models import Bot
from app.services.order_monitor import OrderMonitor
from app.strategies import StrategyRegistry
from app.strategies.ai_autonomous import market_analysis
from app.trading_engine_v2 import StrategyTradingEngine

logger = logging.getLogger(__name__)


class MultiBotMonitor:
    """
    Monitor prices and signals for multiple active bots.

    Each bot can use a different strategy and trade a different product pair.
    """

    def __init__(self, exchange: ExchangeClient, interval_seconds: int = 60):
        """
        Initialize multi-bot monitor

        Args:
            exchange: Exchange client instance (CEX or DEX)
            interval_seconds: How often to check signals (default: 60s)
        """
        self.exchange = exchange
        self.interval_seconds = interval_seconds
        self.running = False
        self.task: Optional[asyncio.Task] = None

        # Initialize order monitor for tracking limit orders
        self.order_monitor = OrderMonitor(exchange, check_interval=30)

        # Cache for candle data (to avoid fetching same data multiple times)
        self._candle_cache: Dict[str, tuple] = {}  # product_id -> (timestamp, candles)
        self._cache_ttl = 30  # Cache candles for 30 seconds

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
        inactive_with_positions_query = (
            select(Bot)
            .join(Position, Position.bot_id == Bot.id)
            .where(not Bot.is_active, Position.status == "open")
            .distinct()
        )
        inactive_result = await db.execute(inactive_with_positions_query)
        inactive_bots_with_positions = list(inactive_result.scalars().all())

        # Combine both lists
        all_bots = active_bots + inactive_bots_with_positions

        if inactive_bots_with_positions:
            logger.info(f"Including {len(inactive_bots_with_positions)} stopped bot(s) with open positions")

        return all_bots

    def timeframe_to_seconds(self, timeframe: str) -> int:
        """Convert timeframe string to seconds"""
        timeframe_map = {
            "ONE_MINUTE": 60,
            "FIVE_MINUTE": 300,
            "FIFTEEN_MINUTE": 900,
            "THIRTY_MINUTE": 1800,
            "ONE_HOUR": 3600,
            "TWO_HOUR": 7200,
            "SIX_HOUR": 21600,
            "ONE_DAY": 86400,
        }
        return timeframe_map.get(timeframe, 300)  # Default to 5 minutes

    async def get_candles_cached(
        self, product_id: str, granularity: str, lookback_candles: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get historical candles with caching

        Args:
            product_id: Trading pair (e.g., "ETH-BTC")
            granularity: Candle interval (e.g., "FIVE_MINUTE", "ONE_HOUR")
            lookback_candles: Number of candles to fetch
        """
        # Use product_id + granularity as cache key
        cache_key = f"{product_id}:{granularity}"

        # Check cache
        now = datetime.utcnow().timestamp()
        if cache_key in self._candle_cache:
            cached_time, cached_candles = self._candle_cache[cache_key]
            if now - cached_time < self._cache_ttl:
                return cached_candles

        # Fetch new candles
        try:
            import time

            # Calculate time range based on granularity
            granularity_seconds = self.timeframe_to_seconds(granularity)
            end_time = int(time.time())
            start_time = end_time - (lookback_candles * granularity_seconds)

            logger.info(
                f"  Requesting {lookback_candles} {granularity} candles for {product_id} (time range: {start_time} to {end_time})"
            )

            candles = await self.exchange.get_candles(
                product_id=product_id, start=start_time, end=end_time, granularity=granularity
            )

            logger.info(f"  Coinbase returned {len(candles)} candles")

            # Coinbase returns newest first, reverse to get oldest first
            candles = list(reversed(candles))

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
            # Get all trading pairs for this bot (supports multi-pair)
            trading_pairs = bot.get_trading_pairs()
            print(f"🔍 Got {len(trading_pairs)} trading pairs: {trading_pairs}")
            logger.info(
                f"Processing bot: {bot.name} with {len(trading_pairs)} pair(s): {trading_pairs} ({bot.strategy_type})"
            )

            # Check if strategy supports batch analysis (AI strategies)
            # Note: For batch mode, we use bot's current config since batch mode only applies to new analysis
            # Individual positions will still use frozen config in process_bot_pair
            print(f"🔍 Getting strategy instance for {bot.strategy_type}...")
            strategy = StrategyRegistry.get_strategy(bot.strategy_type, bot.strategy_config)
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
                # Process trading pairs in batches to avoid Coinbase API throttling
                results = {}
                batch_size = 5

                for i in range(0, len(trading_pairs), batch_size):
                    batch = trading_pairs[i : i + batch_size]
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
            quote_currency = bot.get_quote_currency()
            try:
                if quote_currency == "BTC":
                    aggregate_value = await self.exchange.calculate_aggregate_btc_value()
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
                    f"  ⚠️  SUSPICIOUS: Aggregate {quote_currency} value is very low ({aggregate_value:.8f}). This may indicate API issues."
                )
                logger.warning("  ⚠️  Bot may be unable to open new positions due to insufficient calculated balance.")

            # Calculate bot's reserved balance (percentage of total account value from bot config)
            reserved_balance = bot.get_reserved_balance(aggregate_value)
            budget_pct = bot.budget_percentage or 0

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
                f"  💰 In positions: {total_in_positions:.8f} {quote_currency}, Available allocation: {available_budget:.8f} {quote_currency}"
            )
            logger.warning(
                f"  💰 Actual {quote_currency} balance: {actual_available:.8f} {quote_currency}"
            )
            logger.warning(
                f"  💰 Min per position: {min_per_position:.8f} {quote_currency}"
            )
            logger.warning(
                f"  💰 Has allocation room: {has_allocation_room}, Has actual balance: {has_actual_balance}, Can open new: {has_budget_for_new}"
            )

            # Determine which pairs to analyze
            pairs_to_analyze = trading_pairs

            if open_count >= max_concurrent_deals:
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
                    f"  ⚠️  INSUFFICIENT FUNDS: Only {available_budget:.8f} {quote_currency} available, need {min_per_position:.8f}"
                )
                logger.info(
                    f"  💰 Skipping new position analysis - analyzing only {len(pairs_to_analyze)} pairs with open positions for sell signals"
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
                            logger.warning(f"    ⚠️  {product_id}: Could not fetch volume stats ({e}), including anyway")
                            filtered_pairs.append(product_id)  # Include pairs where we can't get stats

                    pairs_to_analyze = filtered_pairs
                    logger.info(f"  📊 After volume filter: {len(pairs_to_analyze)} pairs remain")

            if not pairs_to_analyze:
                logger.info("  ⏭️  No pairs to analyze")
                return {}

            # Collect market data for pairs we're analyzing
            pairs_data = {}
            failed_pairs = {}  # Track pairs that failed to load data
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

                        # Get candles for multiple timeframes (for BB% calculations)
                        candles = await self.get_candles_cached(product_id, "FIVE_MINUTE", 100)
                        three_min_candles = await self.get_candles_cached(product_id, "THREE_MINUTE", 100)

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
                        if three_min_candles and len(three_min_candles) > 0:
                            candles_by_timeframe["THREE_MINUTE"] = three_min_candles

                        # Prepare market context (for AI batch analysis)
                        market_context = market_analysis.prepare_market_context(candles, current_price)

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

                # Track failures for open positions
                if not success and has_open_position:
                    failed_pairs[product_id] = last_error
                    logger.error(f"  🚨 CRITICAL: Failed to fetch data for open position {product_id}: {last_error}")

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

            per_position_budget = total_bot_budget / max_concurrent_deals if max_concurrent_deals > 0 else 0
            print(f"💰 Budget calculation: Total={total_bot_budget:.8f}, MaxDeals={max_concurrent_deals}, PerPosition={per_position_budget:.8f}")

            # Call batch AI analysis (1 API call for ALL pairs!) - or skip if technical-only check
            if skip_ai_analysis:
                print(f"⏭️  Skipping AI analysis (technical-only check)")
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
                        f"    Processing {product_id}: {signal_data.get('signal_type')} ({signal_data.get('confidence')}%)"
                    )

                    # Add current_price to signal_data for DCA logic (AI response doesn't include it)
                    pair_info = pairs_data.get(product_id, {})
                    signal_data["current_price"] = pair_info.get("current_price", 0)

                    # Only log actual AI analysis, not technical-only checks (reduces UI noise)
                    ai_log_entry = None
                    if signal_data.get("reasoning") != "Technical-only check (no AI)":
                        print(f"🔍 Logging AI decision for {product_id}...")
                        # Log AI decision (position_id will be updated after position is created)
                        ai_log_entry = await self.log_ai_decision(db, bot, product_id, signal_data, pair_info)
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

                    # Update AI log with position_id if a position was created
                    if ai_log_entry and result.get("position"):
                        position = result["position"]
                        ai_log_entry.position_id = position.id
                        logger.info(f"  🔗 Linked AI log to position #{position.id} for {product_id}")

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
        self, db: AsyncSession, bot: Bot, product_id: str, signal_data: Dict[str, Any], pair_data: Dict[str, Any]
    ):
        """Log AI decision to database and return the log entry"""
        try:
            import traceback
            from app.models import AIBotLog

            # DEBUG: Log stack trace to find duplicate calls
            stack = "".join(traceback.format_stack()[-5:-1])
            logger.info(
                f"  📝 Logging AI decision for Bot #{bot.id} {product_id}: {signal_data.get('signal_type')} ({signal_data.get('confidence')}%)"
            )
            logger.debug(f"  Call stack:\n{stack}")

            # Extract only additional context (avoid duplicating fields already in columns)
            additional_context = signal_data.get("context", {})  # Get nested context if exists
            if not additional_context and isinstance(signal_data, dict):
                # Build minimal context from signal_data, excluding fields that have dedicated columns
                excluded_fields = {"reasoning", "signal_type", "confidence"}
                additional_context = {k: v for k, v in signal_data.items() if k not in excluded_fields}

            log_entry = AIBotLog(
                bot_id=bot.id,
                thinking=signal_data.get("reasoning", ""),
                decision=signal_data.get("signal_type", "hold"),
                confidence=signal_data.get("confidence", 0),
                current_price=pair_data.get("current_price"),
                position_status="unknown",  # Will be determined by trading logic
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
        self, db: AsyncSession, bot: Bot, product_id: str, pre_analyzed_signal=None, pair_data=None, commit=True, skip_ai_analysis: bool = False
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
                # Check if there's an existing position for this pair
                # If yes, use frozen config snapshot (like 3Commas)
                # If no, use current bot config (will be frozen when position is created)
                from sqlalchemy import desc, select

                from app.models import Position

                query = (
                    select(Position)
                    .where(Position.bot_id == bot.id, Position.product_id == product_id, Position.status == "open")
                    .order_by(desc(Position.opened_at))
                )
                result = await db.execute(query)
                existing_position = result.scalars().first()

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
                # Fetch candles first to get reliable price
                temp_candles = await self.get_candles_cached(product_id, "FIVE_MINUTE", 100)
                if temp_candles and len(temp_candles) > 0:
                    current_price = float(temp_candles[-1].get("close", 0))
                    logger.info(f"    Current {product_id} price (from candles): {current_price:.8f}")
                else:
                    logger.warning(f"    No candles available for {product_id}, using fallback ticker")
                    current_price = await self.exchange.get_current_price(product_id)
                    logger.info(f"    Current {product_id} price (from ticker): {current_price:.8f}")

            # For conditional_dca strategy, extract all timeframes from conditions
            if bot.strategy_type == "conditional_dca":
                # Extract unique timeframes from all conditions
                timeframes_needed = set()
                for phase_key in ["base_order_conditions", "safety_order_conditions", "take_profit_conditions"]:
                    conditions = bot.strategy_config.get(phase_key, [])
                    for condition in conditions:
                        tf = condition.get("timeframe", "FIVE_MINUTE")
                        timeframes_needed.add(tf)

                # If no conditions, use default
                if not timeframes_needed:
                    timeframes_needed.add("FIVE_MINUTE")

                logger.info(f"  Fetching candles for timeframes: {timeframes_needed}")

                # Fetch candles for each unique timeframe
                # Use more lookback for longer timeframes to ensure we get enough data
                candles_by_timeframe = {}
                for timeframe in timeframes_needed:
                    # Coinbase limits: ~300 candles max per request
                    # Stay conservative to ensure we get data
                    lookback_map = {
                        "ONE_MINUTE": 200,
                        "FIVE_MINUTE": 200,
                        "FIFTEEN_MINUTE": 150,
                        "THIRTY_MINUTE": 100,  # 100 candles = 50 hours
                        "ONE_HOUR": 100,  # 100 candles = 4 days
                        "TWO_HOUR": 100,
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

                # Get historical candles for signal analysis
                candles = await self.get_candles_cached(
                    product_id=product_id, granularity=timeframe, lookback_candles=100
                )

                if not candles:
                    logger.warning(f"    No candles available for {product_id}")
                    return {"error": "No candles available"}

                candles_by_timeframe = {timeframe: candles}

            # Use pre-analyzed signal if provided (from batch analysis), otherwise analyze now
            if pre_analyzed_signal:
                logger.info("  Using pre-analyzed signal from batch")
                signal_data = pre_analyzed_signal
            elif skip_ai_analysis:
                # Skip AI analysis for technical-only check
                # For conditional_dca: Still evaluate conditions (it doesn't use AI)
                # For AI strategies: Skip entirely and only check existing positions
                if bot.strategy_type == "conditional_dca":
                    logger.info("  ⏭️  Technical check: Analyzing conditional_dca signals without AI")
                    signal_data = await strategy.analyze_signal(candles, current_price, candles_by_timeframe)
                else:
                    logger.info("  ⏭️  SKIPPING AI: Technical-only check (existing positions only)")
                    signal_data = {"signal_type": "hold", "confidence": 0, "reasoning": "Technical-only check (no AI)"}
            else:
                # Analyze signal using strategy
                # For conditional_dca, pass the candles_by_timeframe dict
                if bot.strategy_type == "conditional_dca":
                    logger.info("  Analyzing conditional_dca signals...")
                    signal_data = await strategy.analyze_signal(candles, current_price, candles_by_timeframe)
                else:
                    signal_data = await strategy.analyze_signal(candles, current_price)

            if not signal_data:
                logger.warning("  No signal from strategy (returned None)")
                return {"action": "none", "reason": "No signal"}

            logger.info(
                f"  Signal data: base_order={signal_data.get('base_order_signal')}, safety_order={signal_data.get('safety_order_signal')}, take_profit={signal_data.get('take_profit_signal')}"
            )

            signal_type = signal_data.get("signal_type")
            logger.info(f"  🔔 Signal detected: {signal_type}")

            # Create trading engine for this bot/pair combination
            engine = StrategyTradingEngine(
                db=db,
                exchange=self.exchange,
                bot=bot,
                strategy=strategy,
                product_id=product_id,  # Specify which pair this engine instance trades
            )

            # Process the signal (pass pre_analyzed_signal if available from batch mode)
            result = await engine.process_signal(
                candles, current_price, pre_analyzed_signal=pre_analyzed_signal, candles_by_timeframe=candles_by_timeframe
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

                        # Process each bot independently based on their individual check intervals
                        for bot in bots:
                            try:
                                print(f"🔍 Checking bot: {bot.name} (ID: {bot.id})")

                                # Two-tier checking strategy:
                                # 1. Technical conditions checked every 45s (fast, cheap) - faster to catch BB% crossings
                                # 2. AI analysis only at longer intervals (expensive)
                                technical_check_interval = 45  # Always check technical conditions every 45s
                                ai_check_interval = bot.check_interval_seconds or self.interval_seconds
                                now = datetime.utcnow()

                                # Determine if we need ANY check at all (technical + AI or just technical)
                                time_since_last_signal_check = 0
                                if bot.last_signal_check:
                                    time_since_last_signal_check = (now - bot.last_signal_check).total_seconds()
                                    if time_since_last_signal_check < technical_check_interval:
                                        print(
                                            f"⏭️  Skipping {bot.name} - last checked {time_since_last_signal_check:.0f}s ago (technical interval: {technical_check_interval}s)"
                                        )
                                        continue

                                # Determine if we need AI analysis
                                needs_ai_analysis = True
                                time_since_last_ai_check = None
                                if bot.last_ai_check:
                                    time_since_last_ai_check = (now - bot.last_ai_check).total_seconds()
                                    if time_since_last_ai_check < ai_check_interval:
                                        needs_ai_analysis = False
                                        print(
                                            f"🔧 {bot.name}: Technical-only check (last AI: {time_since_last_ai_check:.0f}s ago, AI interval: {ai_check_interval}s)"
                                        )
                                    else:
                                        print(f"🤖 {bot.name}: Full check with AI analysis (interval: {ai_check_interval}s)")
                                else:
                                    print(f"🤖 {bot.name}: First-time AI analysis")

                                # Update timestamp BEFORE processing to prevent race condition
                                # (if processing takes >10s, next loop iteration would start processing again!)
                                bot.last_signal_check = datetime.utcnow()
                                if needs_ai_analysis:
                                    bot.last_ai_check = datetime.utcnow()
                                await db.commit()  # Commit immediately to prevent concurrent processing

                                print(f"🔍 Calling process_bot for {bot.name} (AI: {needs_ai_analysis})...")
                                await self.process_bot(db, bot, skip_ai_analysis=not needs_ai_analysis)
                                print(f"✅ Finished processing {bot.name}")
                            except Exception as e:
                                logger.error(f"Error processing bot {bot.name}: {e}")
                                # Continue with other bots even if one fails
                                continue

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
            # Start order monitor alongside bot monitor
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
            # Start order monitor alongside bot monitor
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
        # Stop order monitor
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
