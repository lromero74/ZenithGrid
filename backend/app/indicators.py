"""
Technical Indicator Calculators

Provides calculators for technical analysis indicators:
- MACD (Moving Average Convergence Divergence)
- RSI (Relative Strength Index)

These indicators are used by trading strategies to generate buy/sell signals.
"""

from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import MarketData


class MACDCalculator:
    """Calculate MACD indicator and detect crossover signals"""

    def __init__(self, fast_period: int = None, slow_period: int = None, signal_period: int = None):
        self.fast_period = fast_period or settings.macd_fast_period
        self.slow_period = slow_period or settings.macd_slow_period
        self.signal_period = signal_period or settings.macd_signal_period

    def calculate_ema(self, data: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average"""
        return data.ewm(span=period, adjust=False).mean()

    def calculate_macd(self, prices: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate MACD, Signal line, and Histogram

        Returns:
            Tuple of (macd_line, signal_line, histogram)
        """
        # Calculate EMAs
        ema_fast = self.calculate_ema(prices, self.fast_period)
        ema_slow = self.calculate_ema(prices, self.slow_period)

        # MACD line
        macd_line = ema_fast - ema_slow

        # Signal line
        signal_line = self.calculate_ema(macd_line, self.signal_period)

        # Histogram
        histogram = macd_line - signal_line

        return macd_line, signal_line, histogram

    def detect_crossover(self, current_histogram: float, previous_histogram: float) -> Optional[str]:
        """
        Detect MACD crossover by monitoring the histogram (MACD - Signal)

        A crossover occurs when the MACD line crosses the signal line, which
        happens when the histogram crosses zero. This works regardless of whether
        the MACD and signal lines are above or below the zero baseline.

        - Cross Up: MACD crosses ABOVE signal (histogram goes from ≤0 to >0)
          → BUY SIGNAL (works above AND below zero baseline)
        - Cross Down: MACD crosses BELOW signal (histogram goes from ≥0 to <0)
          → SELL SIGNAL (works above AND below zero baseline)

        Returns:
            'cross_up' if MACD crosses above signal (bullish)
            'cross_down' if MACD crosses below signal (bearish)
            None if no crossover
        """
        if previous_histogram <= 0 and current_histogram > 0:
            # MACD crossed above signal - BULLISH
            return "cross_up"
        elif previous_histogram >= 0 and current_histogram < 0:
            # MACD crossed below signal - BEARISH
            return "cross_down"
        return None

    async def get_recent_market_data(self, db: AsyncSession, limit: int = 100) -> pd.DataFrame:
        """Fetch recent market data from database"""
        query = select(MarketData).order_by(desc(MarketData.timestamp)).limit(limit)
        result = await db.execute(query)
        data = result.scalars().all()

        if not data:
            return pd.DataFrame()

        # Convert to DataFrame (reverse to get chronological order)
        df = pd.DataFrame(
            [
                {
                    "timestamp": d.timestamp,
                    "price": d.price,
                    "macd_value": d.macd_value,
                    "macd_signal": d.macd_signal,
                    "macd_histogram": d.macd_histogram,
                }
                for d in reversed(data)
            ]
        )

        return df

    async def add_market_data(self, db: AsyncSession, price: float, volume: Optional[float] = None) -> MarketData:
        """
        Add new market data point and calculate MACD

        Args:
            db: Database session
            price: Current ETH/BTC price
            volume: Optional volume data

        Returns:
            MarketData object with MACD values
        """
        # Get recent data
        df = await self.get_recent_market_data(db, limit=100)

        # Add new price
        new_row = pd.DataFrame(
            [
                {
                    "timestamp": datetime.utcnow(),
                    "price": price,
                    "macd_value": None,
                    "macd_signal": None,
                    "macd_histogram": None,
                }
            ]
        )

        df = pd.concat([df, new_row], ignore_index=True)

        # Calculate MACD if we have enough data
        macd_value = None
        macd_signal = None
        macd_histogram = None

        if len(df) >= self.slow_period:
            prices = df["price"]
            macd_line, signal_line, histogram = self.calculate_macd(prices)

            # Get the latest values
            macd_value = float(macd_line.iloc[-1])
            macd_signal = float(signal_line.iloc[-1])
            macd_histogram = float(histogram.iloc[-1])

        # Create and save market data
        market_data = MarketData(
            timestamp=datetime.utcnow(),
            price=price,
            macd_value=macd_value,
            macd_signal=macd_signal,
            macd_histogram=macd_histogram,
            volume=volume,
        )

        db.add(market_data)
        await db.commit()
        await db.refresh(market_data)

        return market_data

    async def check_for_signal(self, db: AsyncSession) -> Optional[Tuple[str, MarketData]]:
        """
        Check if there's a MACD crossover signal

        Returns:
            Tuple of (signal_type, market_data) or None
            signal_type is 'cross_up' or 'cross_down'
        """
        # Get last two data points
        query = select(MarketData).order_by(desc(MarketData.timestamp)).limit(2)
        result = await db.execute(query)
        data = result.scalars().all()

        if len(data) < 2:
            return None

        current = data[0]
        previous = data[1]

        # Check if we have MACD values
        if current.macd_histogram is None or previous.macd_histogram is None:
            return None

        # Detect crossover
        signal = self.detect_crossover(current.macd_histogram, previous.macd_histogram)

        if signal:
            return (signal, current)

        return None

    def calculate_from_prices(self, prices: List[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Calculate MACD from a list of prices

        Returns:
            Tuple of (macd_value, signal_value, histogram) or (None, None, None)
        """
        if len(prices) < self.slow_period:
            return None, None, None

        prices_series = pd.Series(prices)
        macd_line, signal_line, histogram = self.calculate_macd(prices_series)

        return (float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(histogram.iloc[-1]))
