"""
Multi-Bot Price Monitor

Monitors prices for all active bots and processes signals using their configured strategies.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bot, MarketData
from app.coinbase_client import CoinbaseClient
from app.strategies import StrategyRegistry, TradingStrategy
from app.trading_engine_v2 import StrategyTradingEngine
from app.database import async_session_maker
from app.config import settings

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
        active_query = select(Bot).where(Bot.is_active == True)
        active_result = await db.execute(active_query)
        active_bots = list(active_result.scalars().all())

        # Get inactive bots that have open positions
        inactive_with_positions_query = (
            select(Bot)
            .join(Position, Position.bot_id == Bot.id)
            .where(Bot.is_active == False, Position.status == "open")
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

            # Process trading pairs in parallel batches to avoid Coinbase API throttling
            # Coinbase public API allows ~10 requests/second per IP
            # With safety margin: process 5 pairs per batch with 1s delay between batches
            results = {}
            batch_size = 5

            for i in range(0, len(trading_pairs), batch_size):
                batch = trading_pairs[i:i + batch_size]
                logger.info(f"  Processing batch {i // batch_size + 1} ({len(batch)} pairs): {batch}")

                # Process batch in parallel
                batch_tasks = [
                    self.process_bot_pair(db, bot, product_id)
                    for product_id in batch
                ]
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

                # Store results
                for product_id, result in zip(batch, batch_results):
                    if isinstance(result, Exception):
                        logger.error(f"  Error processing {product_id}: {result}")
                        results[product_id] = {"error": str(result)}
                    else:
                        results[product_id] = result

                # Add delay between batches (if not last batch)
                if i + batch_size < len(trading_pairs):
                    logger.info(f"  Waiting 1s before next batch to avoid API throttling...")
                    await asyncio.sleep(1)

            return results

        except Exception as e:
            logger.error(f"Error processing bot {bot.name}: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    async def process_bot_pair(self, db: AsyncSession, bot: Bot, product_id: str) -> Dict[str, Any]:
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
                # Adjust budget percentages if splitting across pairs
                strategy_config = bot.strategy_config.copy()
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

            # Get current price
            current_price = await self.coinbase.get_current_price(product_id)
            logger.info(f"    Current {product_id} price: {current_price:.8f}")

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

            # Analyze signal using strategy
            # For conditional_dca, pass the candles_by_timeframe dict
            if bot.strategy_type == "conditional_dca":
                logger.info(f"  Analyzing conditional_dca signals...")
                signal_data = await strategy.analyze_signal(candles, current_price, candles_by_timeframe)
            else:
                signal_data = await strategy.analyze_signal(candles, current_price)

            if not signal_data:
                logger.warning(f"  No signal from strategy (returned None)")
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

                        # Process each bot independently
                        for bot in bots:
                            try:
                                await self.process_bot(db, bot)
                            except Exception as e:
                                logger.error(f"Error processing bot {bot.name}: {e}")
                                # Continue with other bots even if one fails
                                continue

                # Wait for next interval
                await asyncio.sleep(self.interval_seconds)

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
