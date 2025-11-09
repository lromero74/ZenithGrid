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
        """Fetch all active bots from database"""
        query = select(Bot).where(Bot.is_active == True)
        result = await db.execute(query)
        return list(result.scalars().all())

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

            candles = await self.coinbase.get_candles(
                product_id=product_id,
                start=start_time,
                end=end_time,
                granularity=granularity
            )

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
        Process signals for a single bot

        Args:
            db: Database session
            bot: Bot instance to process

        Returns:
            Result dictionary with action/signal info
        """
        try:
            logger.info(f"Processing bot: {bot.name} ({bot.product_id}, {bot.strategy_type})")

            # Get strategy instance for this bot
            try:
                strategy = StrategyRegistry.get_strategy(bot.strategy_type, bot.strategy_config)
            except ValueError as e:
                logger.error(f"Unknown strategy: {bot.strategy_type}")
                return {"error": str(e)}

            # Get current price
            current_price = await self.coinbase.get_current_price(bot.product_id)
            logger.info(f"  Current {bot.product_id} price: {current_price:.8f}")

            # Get bot's configured timeframe (default to FIVE_MINUTE if not set)
            timeframe = bot.strategy_config.get("timeframe", "FIVE_MINUTE")
            logger.info(f"  Using timeframe: {timeframe}")

            # Get historical candles for signal analysis
            candles = await self.get_candles_cached(
                product_id=bot.product_id,
                granularity=timeframe,
                lookback_candles=100
            )

            if not candles:
                logger.warning(f"  No candles available for {bot.product_id}")
                return {"error": "No candles available"}

            # Analyze signal using strategy
            signal_data = await strategy.analyze_signal(candles, current_price)

            if not signal_data:
                logger.debug(f"  No signal from strategy")
                return {"action": "none", "reason": "No signal"}

            signal_type = signal_data.get("signal_type")
            logger.info(f"  🔔 Signal detected: {signal_type}")

            # Create trading engine for this bot
            engine = StrategyTradingEngine(
                db=db,
                coinbase=self.coinbase,
                bot=bot,
                strategy=strategy
            )

            # Process the signal
            result = await engine.process_signal(signal_type, signal_data)

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
                            "product_id": bot.product_id,
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
