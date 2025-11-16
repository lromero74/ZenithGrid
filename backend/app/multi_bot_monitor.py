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

from app.coinbase_client import CoinbaseClient
from app.database import async_session_maker
from app.models import Bot
from app.strategies import StrategyRegistry
from app.trading_engine_v2 import StrategyTradingEngine

logger = logging.getLogger(__name__)


class MultiBotMonitor:
    """
    Monitor prices and signals for multiple active bots.

    Each bot can use a different strategy and trade a different product pair.
    """

    def __init__(
        self,
        coinbase: CoinbaseClient,
        interval_seconds: int = 60
    ):
        """
        Initialize multi-bot monitor

        Args:
            coinbase: Coinbase API client
            interval_seconds: How often to check signals (default: 60s)
        """
        self.coinbase = coinbase
        self.interval_seconds = interval_seconds
        self.running = False
        self.task: Optional[asyncio.Task] = None

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
            "ONE_DAY": 86400
        }
        return timeframe_map.get(timeframe, 300)  # Default to 5 minutes

    async def get_candles_cached(
        self,
        product_id: str,
        granularity: str,
        lookback_candles: int = 100
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

            logger.info(f"  Requesting {lookback_candles} {granularity} candles for {product_id} (time range: {start_time} to {end_time})")

            candles = await self.coinbase.get_candles(
                product_id=product_id,
                start=start_time,
                end=end_time,
                granularity=granularity
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

    async def process_bot(self, db: AsyncSession, bot: Bot) -> Dict[str, Any]:
        """
        Process signals for a single bot across all its trading pairs

        Args:
            db: Database session
            bot: Bot instance to process

        Returns:
            Result dictionary with action/signal info for all pairs
        """
        try:
            # Get all trading pairs for this bot (supports multi-pair)
            trading_pairs = bot.get_trading_pairs()
            logger.info(f"Processing bot: {bot.name} with {len(trading_pairs)} pair(s): {trading_pairs} ({bot.strategy_type})")

            # Check if strategy supports batch analysis (AI strategies)
            # Note: For batch mode, we use bot's current config since batch mode only applies to new analysis
            # Individual positions will still use frozen config in process_bot_pair
            strategy = StrategyRegistry.get_strategy(bot.strategy_type, bot.strategy_config)
            supports_batch = hasattr(strategy, 'analyze_multiple_pairs_batch') and len(trading_pairs) > 1

            if supports_batch:
                logger.info(f"🚀 Using BATCH analysis mode - {len(trading_pairs)} pairs in 1 API call!")
                return await self.process_bot_batch(db, bot, trading_pairs, strategy)
            else:
                logger.info("Using sequential analysis mode")
                # Original sequential processing logic
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
                            result = await self.process_bot_pair(db, bot, product_id)
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
        self,
        db: AsyncSession,
        bot: Bot,
        trading_pairs: List[str],
        strategy: Any
    ) -> Dict[str, Any]:
        """
        Process multiple trading pairs using AI batch analysis (single API call for all pairs)

        Args:
            db: Database session
            bot: Bot instance
            trading_pairs: List of product IDs to analyze
            strategy: Strategy instance that supports batch analysis

        Returns:
            Result dictionary with action/signal info for all pairs
        """
        try:
            from app.models import Position

            # Check how many open positions this bot has
            open_positions_query = (
                select(Position)
                .where(Position.bot_id == bot.id, Position.status == "open")
            )
            open_positions_result = await db.execute(open_positions_query)
            open_positions = list(open_positions_result.scalars().all())
            open_count = len(open_positions)

            # Get max concurrent deals from strategy config
            max_concurrent_deals = bot.strategy_config.get("max_concurrent_deals", 1)

            # Determine which pairs to analyze
            pairs_to_analyze = trading_pairs

            if open_count >= max_concurrent_deals:
                # At capacity - only analyze pairs with open positions (for sell signals)
                pairs_with_positions = {p.product_id for p in open_positions if p.product_id}
                pairs_to_analyze = [p for p in trading_pairs if p in pairs_with_positions]

                if len(pairs_to_analyze) < len(trading_pairs):
                    logger.info(f"  📊 Bot at max capacity ({open_count}/{max_concurrent_deals} positions)")
                    logger.info(f"  🎯 Analyzing only {len(pairs_to_analyze)} pairs with open positions: {pairs_to_analyze}")
                    logger.info(f"  ⏭️  Skipping {len(trading_pairs) - len(pairs_to_analyze)} pairs without positions")
            else:
                # Below capacity - analyze all configured pairs (looking for buy + sell signals)
                logger.info(f"  📊 Bot below capacity ({open_count}/{max_concurrent_deals} positions)")
                logger.info(f"  🔍 Analyzing all {len(trading_pairs)} pairs for opportunities")

                # Filter by minimum daily volume (only for new positions, not existing ones)
                min_daily_volume = strategy.config.get("min_daily_volume", 0.0)
                if min_daily_volume > 0:
                    logger.info(f"  📊 Filtering pairs by minimum 24h volume: {min_daily_volume}")
                    filtered_pairs = []
                    for product_id in pairs_to_analyze:
                        try:
                            stats = await self.coinbase.get_product_stats(product_id)
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
            logger.info(f"  Fetching market data for {len(pairs_to_analyze)} pairs...")

            for product_id in pairs_to_analyze:
                try:
                    # Get candles first (they have reliable prices!)
                    candles = await self.get_candles_cached(product_id, "FIVE_MINUTE", 100)

                    # Get current price from most recent candle (more reliable than ticker!)
                    if not candles or len(candles) == 0:
                        logger.warning(f"  No candles available for {product_id}, skipping")
                        continue

                    current_price = float(candles[-1].get("close", 0))

                    # Validate price
                    if current_price is None or current_price <= 0:
                        logger.warning(f"  Invalid price for {product_id}: {current_price}, skipping")
                        continue

                    # Prepare market context
                    market_context = strategy._prepare_market_context(candles, current_price)

                    pairs_data[product_id] = {
                        "current_price": current_price,
                        "candles": candles,
                        "market_context": market_context
                    }

                except Exception as e:
                    logger.error(f"  Error fetching data for {product_id}: {e}")
                    # Skip pairs with errors instead of adding them with invalid data
                    continue

            # Call batch AI analysis (1 API call for ALL pairs!)
            logger.info(f"  🧠 Calling AI for batch analysis of {len(pairs_data)} pairs...")
            batch_analyses = await strategy.analyze_multiple_pairs_batch(pairs_data)

            # Process each pair's analysis result
            results = {}
            for product_id in pairs_data.keys():
                try:
                    signal_data = batch_analyses.get(product_id, {
                        "signal_type": "hold",
                        "confidence": 0,
                        "reasoning": "No analysis result"
                    })

                    # Log AI decision
                    await self.log_ai_decision(db, bot, product_id, signal_data, pairs_data.get(product_id, {}))

                    # Execute trading logic based on signal
                    result = await self.execute_trading_logic(db, bot, product_id, signal_data, pairs_data.get(product_id, {}))
                    results[product_id] = result

                except Exception as e:
                    logger.error(f"  Error processing {product_id} result: {e}")
                    results[product_id] = {"error": str(e)}

            # Update bot's last check time
            bot.last_signal_check = datetime.utcnow()
            await db.commit()

            return results

        except Exception as e:
            logger.error(f"Error in batch processing: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    async def log_ai_decision(
        self,
        db: AsyncSession,
        bot: Bot,
        product_id: str,
        signal_data: Dict[str, Any],
        pair_data: Dict[str, Any]
    ):
        """Log AI decision to database"""
        try:
            from app.models import AIBotLog

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
                context=additional_context  # Only store additional context, not duplicate fields
            )
            db.add(log_entry)
            await db.flush()

        except Exception as e:
            logger.error(f"Error logging AI decision for {product_id}: {e}")

    async def execute_trading_logic(
        self,
        db: AsyncSession,
        bot: Bot,
        product_id: str,
        signal_data: Dict[str, Any],
        pair_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute trading logic for a single pair based on AI signal"""
        # Reuse existing process_bot_pair logic but with pre-analyzed signal
        # This avoids code duplication
        return await self.process_bot_pair(db, bot, product_id, pre_analyzed_signal=signal_data, pair_data=pair_data)

    async def process_bot_pair(self, db: AsyncSession, bot: Bot, product_id: str, pre_analyzed_signal=None, pair_data=None) -> Dict[str, Any]:
        """
        Process signals for a single bot/pair combination

        Args:
            db: Database session
            bot: Bot instance to process
            product_id: Trading pair to evaluate (e.g., "ETH-BTC")

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
                query = select(Position).where(
                    Position.bot_id == bot.id,
                    Position.product_id == product_id,
                    Position.status == "open"
                ).order_by(desc(Position.opened_at))
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
                    if bot.split_budget_across_pairs and len(bot.get_trading_pairs()) > 1:
                        num_pairs = len(bot.get_trading_pairs())
                        logger.info(f"    Splitting budget across {num_pairs} pairs")

                        # Adjust percentage-based parameters
                        if "base_order_percentage" in strategy_config:
                            original = strategy_config["base_order_percentage"]
                            strategy_config["base_order_percentage"] = original / num_pairs
                            logger.info(f"      Base order: {original}% → {strategy_config['base_order_percentage']:.2f}%")

                        if "safety_order_percentage" in strategy_config:
                            original = strategy_config["safety_order_percentage"]
                            strategy_config["safety_order_percentage"] = original / num_pairs
                            logger.info(f"      Safety order: {original}% → {strategy_config['safety_order_percentage']:.2f}%")

                        if "max_btc_usage_percentage" in strategy_config:
                            original = strategy_config["max_btc_usage_percentage"]
                            strategy_config["max_btc_usage_percentage"] = original / num_pairs
                            logger.info(f"      Max usage: {original}% → {strategy_config['max_btc_usage_percentage']:.2f}%")

                strategy = StrategyRegistry.get_strategy(bot.strategy_type, strategy_config)
            except ValueError as e:
                logger.error(f"Unknown strategy: {bot.strategy_type}")
                return {"error": str(e)}

            # Use provided pair_data if available (from batch), otherwise fetch market data
            if pair_data:
                logger.info("    Using pre-fetched market data")
                current_price = pair_data.get("current_price", 0)
                candles = pair_data.get("candles", [])
                candles_by_timeframe = {"FIVE_MINUTE": candles}  # Simplified for batch mode
            else:
                # Fetch candles first to get reliable price
                temp_candles = await self.get_candles_cached(product_id, "FIVE_MINUTE", 100)
                if temp_candles and len(temp_candles) > 0:
                    current_price = float(temp_candles[-1].get("close", 0))
                    logger.info(f"    Current {product_id} price (from candles): {current_price:.8f}")
                else:
                    logger.warning(f"    No candles available for {product_id}, using fallback ticker")
                    current_price = await self.coinbase.get_current_price(product_id)
                    logger.info(f"    Current {product_id} price (from ticker): {current_price:.8f}")

            # For conditional_dca strategy, extract all timeframes from conditions
            if bot.strategy_type == "conditional_dca":
                # Extract unique timeframes from all conditions
                timeframes_needed = set()
                for phase_key in ['base_order_conditions', 'safety_order_conditions', 'take_profit_conditions']:
                    conditions = bot.strategy_config.get(phase_key, [])
                    for condition in conditions:
                        tf = condition.get('timeframe', 'FIVE_MINUTE')
                        timeframes_needed.add(tf)

                # If no conditions, use default
                if not timeframes_needed:
                    timeframes_needed.add('FIVE_MINUTE')

                logger.info(f"  Fetching candles for timeframes: {timeframes_needed}")

                # Fetch candles for each unique timeframe
                # Use more lookback for longer timeframes to ensure we get enough data
                candles_by_timeframe = {}
                for timeframe in timeframes_needed:
                    # Coinbase limits: ~300 candles max per request
                    # Stay conservative to ensure we get data
                    lookback_map = {
                        'ONE_MINUTE': 200,
                        'FIVE_MINUTE': 200,
                        'FIFTEEN_MINUTE': 150,
                        'THIRTY_MINUTE': 100,  # 100 candles = 50 hours
                        'ONE_HOUR': 100,       # 100 candles = 4 days
                        'TWO_HOUR': 100,
                        'SIX_HOUR': 100,
                        'ONE_DAY': 100
                    }
                    lookback = lookback_map.get(timeframe, 100)

                    tf_candles = await self.get_candles_cached(
                        product_id=product_id,
                        granularity=timeframe,
                        lookback_candles=lookback
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
                    product_id=product_id,
                    granularity=timeframe,
                    lookback_candles=100
                )

                if not candles:
                    logger.warning(f"    No candles available for {product_id}")
                    return {"error": "No candles available"}

                candles_by_timeframe = {timeframe: candles}

            # Use pre-analyzed signal if provided (from batch analysis), otherwise analyze now
            if pre_analyzed_signal:
                logger.info("  Using pre-analyzed signal from batch")
                signal_data = pre_analyzed_signal
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

            logger.info(f"  Signal data: base_order={signal_data.get('base_order_signal')}, safety_order={signal_data.get('safety_order_signal')}, take_profit={signal_data.get('take_profit_signal')}")

            signal_type = signal_data.get("signal_type")
            logger.info(f"  🔔 Signal detected: {signal_type}")

            # Create trading engine for this bot/pair combination
            engine = StrategyTradingEngine(
                db=db,
                coinbase=self.coinbase,
                bot=bot,
                strategy=strategy,
                product_id=product_id  # Specify which pair this engine instance trades
            )

            # Process the signal
            result = await engine.process_signal(candles, current_price)

            logger.info(f"  Result: {result['action']} - {result['reason']}")

            # Update bot's last check time
            bot.last_signal_check = datetime.utcnow()
            await db.commit()

            return result

        except Exception as e:
            logger.error(f"Error processing bot {bot.name}: {e}", exc_info=True)
            return {"error": str(e)}

    async def monitor_loop(self):
        """Main monitoring loop for all active bots"""
        logger.info("Starting multi-bot monitor")
        self.running = True

        while self.running:
            try:
                async with async_session_maker() as db:
                    # Get all active bots
                    bots = await self.get_active_bots(db)

                    if not bots:
                        logger.debug("No active bots to monitor")
                    else:
                        logger.info(f"Monitoring {len(bots)} active bot(s)")

                        # Process each bot independently based on their individual check intervals
                        for bot in bots:
                            try:
                                # Check if enough time has elapsed since last check
                                check_interval = bot.check_interval_seconds or self.interval_seconds
                                now = datetime.utcnow()

                                if bot.last_signal_check:
                                    time_since_last_check = (now - bot.last_signal_check).total_seconds()
                                    if time_since_last_check < check_interval:
                                        logger.debug(f"Skipping {bot.name} - last checked {time_since_last_check:.0f}s ago (interval: {check_interval}s)")
                                        continue

                                logger.info(f"Processing {bot.name} (interval: {check_interval}s)")
                                await self.process_bot(db, bot)
                            except Exception as e:
                                logger.error(f"Error processing bot {bot.name}: {e}")
                                # Continue with other bots even if one fails
                                continue

                # Wait for next interval (use minimum bot interval or default)
                await asyncio.sleep(60)  # Check every minute for bots that need processing

            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)
                # Wait a bit before retrying
                await asyncio.sleep(10)

        logger.info("Multi-bot monitor stopped")

    def start(self):
        """Start the monitoring task"""
        if not self.running:
            self.task = asyncio.create_task(self.monitor_loop())
            logger.info("Multi-bot monitor task started")

    async def stop(self):
        """Stop the monitoring task"""
        self.running = False
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
                            "product_id": bot.get_trading_pairs()[0] if bot.get_trading_pairs() else None,  # Legacy compatibility
                            "strategy": bot.strategy_type,
                            "last_check": bot.last_signal_check.isoformat() if bot.last_signal_check else None
                        }
                        for bot in bots
                    ]
                }
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return {
                "running": self.running,
                "interval_seconds": self.interval_seconds,
                "error": str(e)
            }
