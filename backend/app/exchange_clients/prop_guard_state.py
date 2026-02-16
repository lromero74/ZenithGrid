"""
PropGuard State Helpers

Pure functions for drawdown calculation, daily reset detection, and
volatility adjustments. No imports from models/services/database.
Easy to unit test in isolation.
"""

import math
from datetime import datetime, timedelta
from typing import List, Optional


def calculate_daily_drawdown_pct(
    daily_start_equity: float,
    current_equity: float,
) -> float:
    """
    Calculate daily drawdown percentage.

    Returns:
        Positive number = drawdown (e.g. 3.5 means 3.5% down).
        Zero or negative = no drawdown (equity at or above start).
    """
    if daily_start_equity <= 0:
        return 0.0
    drawdown = (daily_start_equity - current_equity) / daily_start_equity * 100
    return max(0.0, drawdown)


def calculate_total_drawdown_pct(
    initial_deposit: float,
    current_equity: float,
) -> float:
    """
    Calculate total drawdown percentage from initial deposit.

    Returns:
        Positive number = drawdown from initial deposit.
    """
    if initial_deposit <= 0:
        return 0.0
    drawdown = (initial_deposit - current_equity) / initial_deposit * 100
    return max(0.0, drawdown)


def should_reset_daily(
    daily_start_timestamp: Optional[datetime],
    now: Optional[datetime] = None,
    reset_hour: int = 17,
    tz_offset_hours: int = -5,
) -> bool:
    """
    Check if daily P&L should be reset.

    Prop firms typically reset at 17:00 EST (22:00 UTC).

    Args:
        daily_start_timestamp: When the current daily period started
        now: Current time (default: utcnow)
        reset_hour: Reset hour in local prop firm time (default 17)
        tz_offset_hours: UTC offset for prop firm timezone
                         (EST = -5, EDT = -4)

    Returns:
        True if we've crossed the reset time since last snapshot
    """
    if now is None:
        now = datetime.utcnow()

    if daily_start_timestamp is None:
        return True  # No snapshot yet, need to create one

    # Convert reset hour to UTC
    reset_hour_utc = (reset_hour - tz_offset_hours) % 24

    # Find the most recent reset time
    today_reset = now.replace(
        hour=reset_hour_utc, minute=0, second=0, microsecond=0
    )
    if today_reset > now:
        today_reset -= timedelta(days=1)

    # If last snapshot was before the most recent reset time
    return daily_start_timestamp < today_reset


def calculate_btc_volatility(
    candles: List[dict],
    price_key: str = "close",
) -> float:
    """
    Calculate realized volatility from candle data.

    Uses log returns standard deviation (annualized).

    Args:
        candles: List of candle dicts with 'close' prices
        price_key: Key for close price in candle dict

    Returns:
        Volatility as a percentage (e.g. 2.5 = 2.5%)
    """
    if len(candles) < 2:
        return 0.0

    prices = []
    for c in candles:
        try:
            p = float(c.get(price_key, 0))
            if p > 0:
                prices.append(p)
        except (ValueError, TypeError):
            continue

    if len(prices) < 2:
        return 0.0

    # Calculate log returns
    log_returns = []
    for i in range(1, len(prices)):
        log_returns.append(math.log(prices[i] / prices[i - 1]))

    if not log_returns:
        return 0.0

    # Standard deviation of log returns
    mean = sum(log_returns) / len(log_returns)
    variance = sum(
        (r - mean) ** 2 for r in log_returns
    ) / len(log_returns)
    std_dev = math.sqrt(variance)

    # Return as percentage
    return std_dev * 100


def calculate_spread_pct(bid: float, ask: float) -> float:
    """
    Calculate bid-ask spread as a percentage.

    Args:
        bid: Best bid price
        ask: Best ask price

    Returns:
        Spread percentage (e.g. 0.05 = 0.05%)
    """
    if bid <= 0:
        return 0.0
    return ((ask - bid) / bid) * 100


def adjust_size_for_volatility(
    size: float,
    volatility: float,
    threshold: float = 2.0,
    reduction_pct: float = 0.20,
) -> float:
    """
    Reduce position size when volatility exceeds threshold.

    Args:
        size: Original position size
        volatility: Current volatility percentage
        threshold: Volatility threshold to trigger reduction
        reduction_pct: How much to reduce (0.20 = 20% reduction)

    Returns:
        Adjusted size (may be smaller than original)
    """
    if volatility > threshold:
        return size * (1.0 - reduction_pct)
    return size
