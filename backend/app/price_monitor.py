import asyncio
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.coinbase_client import CoinbaseClient
from app.indicators import MACDCalculator
from app.trading_engine import TradingEngine
from app.database import async_session_maker
import logging

logger = logging.getLogger(__name__)


class PriceMonitor:
    """Monitor ETH/BTC price and detect MACD signals"""

    def __init__(
        self,
        coinbase: CoinbaseClient,
        product_id: str = "ETH-BTC",
        interval_seconds: int = 60
    ):
        self.coinbase = coinbase
        self.product_id = product_id
        self.interval_seconds = interval_seconds
        self.macd = MACDCalculator()
        self.running = False
        self.task: Optional[asyncio.Task] = None

    async def fetch_and_process_price(self, db: AsyncSession):
        """Fetch current price and update MACD calculations"""
        try:
            # Get current price
            price = await self.coinbase.get_current_price(self.product_id)
            logger.info(f"Current {self.product_id} price: {price:.8f}")

            # Add to market data and calculate MACD
            market_data = await self.macd.add_market_data(db, price)

            # Check for MACD crossover signal
            signal_result = await self.macd.check_for_signal(db)

            if signal_result:
                signal_type, signal_data = signal_result

                # Determine if MACD is above or below zero baseline
                baseline_position = "above zero" if signal_data.macd_value > 0 else "below zero"

                logger.info(f"🔔 MACD Signal detected: {signal_type.upper()}")
                logger.info(f"   MACD: {signal_data.macd_value:.8f} ({baseline_position})")
                logger.info(f"   Signal: {signal_data.macd_signal:.8f}")
                logger.info(f"   Histogram: {signal_data.macd_histogram:.8f}")
                logger.info(f"   Price: {signal_data.price:.8f}")

                if signal_type == 'cross_up':
                    logger.info(f"   ✅ BUY signal - MACD crossed above signal line (works {baseline_position}!)")

                # Process the signal with trading engine
                engine = TradingEngine(db, self.coinbase, self.product_id)
                result = await engine.process_signal(signal_type, signal_data)

                logger.info(f"Signal processed: {result['action']} - {result['reason']}")

                return {
                    "signal": signal_type,
                    "action": result['action'],
                    "reason": result['reason'],
                    "market_data": market_data
                }

            return {"market_data": market_data}

        except Exception as e:
            logger.error(f"Error in fetch_and_process_price: {e}", exc_info=True)
            return {"error": str(e)}

    async def monitor_loop(self):
        """Main monitoring loop"""
        logger.info(f"Starting price monitor for {self.product_id}")
        self.running = True

        while self.running:
            try:
                async with async_session_maker() as db:
                    await self.fetch_and_process_price(db)

                # Wait for next interval
                await asyncio.sleep(self.interval_seconds)

            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)
                # Wait a bit before retrying
                await asyncio.sleep(10)

        logger.info("Price monitor stopped")

    def start(self):
        """Start the monitoring task"""
        if not self.running:
            self.task = asyncio.create_task(self.monitor_loop())
            logger.info("Price monitor task started")

    async def stop(self):
        """Stop the monitoring task"""
        self.running = False
        if self.task:
            await self.task
            logger.info("Price monitor task stopped")

    async def get_status(self) -> dict:
        """Get monitor status"""
        return {
            "running": self.running,
            "product_id": self.product_id,
            "interval_seconds": self.interval_seconds
        }
