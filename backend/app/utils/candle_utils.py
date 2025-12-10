"""
Candle Data Utilities

Utility functions for processing and manipulating OHLCV candle data.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# Timeframe mapping from string identifiers to seconds
TIMEFRAME_MAP = {
    "ONE_MINUTE": 60,
    "THREE_MINUTE": 180,    # Synthetic - aggregated from 1-minute candles
    "FIVE_MINUTE": 300,
    "FIFTEEN_MINUTE": 900,
    "THIRTY_MINUTE": 1800,
    "ONE_HOUR": 3600,
    "TWO_HOUR": 7200,
    "SIX_HOUR": 21600,
    "ONE_DAY": 86400,
    "TWO_DAY": 172800,      # Synthetic - aggregated from 1-day candles (2 days)
    "THREE_DAY": 259200,    # Synthetic - aggregated from 1-day candles (3 days)
    "ONE_WEEK": 604800,     # Synthetic - aggregated from 1-day candles (7 days)
    "TWO_WEEK": 1209600,    # Synthetic - aggregated from 1-day candles (14 days)
    "ONE_MONTH": 2592000,   # Synthetic - aggregated from 1-day candles (30 days)
}

# Synthetic timeframes that need aggregation from base candles
# Maps synthetic timeframe -> (base_timeframe, aggregation_factor)
SYNTHETIC_TIMEFRAMES = {
    "THREE_MINUTE": ("ONE_MINUTE", 3),
    "TWO_DAY": ("ONE_DAY", 2),
    "THREE_DAY": ("ONE_DAY", 3),
    "ONE_WEEK": ("ONE_DAY", 7),
    "TWO_WEEK": ("ONE_DAY", 14),
    "ONE_MONTH": ("ONE_DAY", 30),
}


def timeframe_to_seconds(timeframe: str) -> int:
    """Convert timeframe string to seconds.

    Args:
        timeframe: Timeframe identifier (e.g., "ONE_MINUTE", "FIVE_MINUTE")

    Returns:
        Number of seconds for the timeframe (defaults to 300 if unknown)
    """
    return TIMEFRAME_MAP.get(timeframe, 300)  # Default to 5 minutes


def aggregate_candles(
    candles: List[Dict[str, Any]], aggregation_factor: int
) -> List[Dict[str, Any]]:
    """
    Aggregate candles into larger timeframes.

    Args:
        candles: List of candles (must be sorted by time ascending)
        aggregation_factor: How many candles to combine (e.g., 3 to convert 1-min to 3-min)

    Returns:
        List of aggregated candles
    """
    if not candles or aggregation_factor <= 1:
        return candles

    aggregated = []

    # Process candles in groups of aggregation_factor
    for i in range(0, len(candles) - aggregation_factor + 1, aggregation_factor):
        group = candles[i:i + aggregation_factor]
        if len(group) < aggregation_factor:
            break  # Not enough candles for a complete group

        # OHLCV aggregation logic:
        # Open: first candle's open
        # High: max of all highs
        # Low: min of all lows
        # Close: last candle's close
        # Volume: sum of all volumes
        aggregated_candle = {
            "start": group[0].get("start", group[0].get("time", 0)),
            "open": group[0].get("open"),
            "high": max(float(c.get("high", 0)) for c in group),
            "low": min(float(c.get("low", float("inf"))) for c in group),
            "close": group[-1].get("close"),
            "volume": sum(float(c.get("volume", 0)) for c in group),
        }
        aggregated.append(aggregated_candle)

    return aggregated


def prepare_market_context(
    candles: List[Dict[str, Any]], current_price: float
) -> Dict[str, Any]:
    """
    Prepare summarized market context data (token-efficient format for AI analysis).

    Takes raw candle data and extracts key metrics like price changes, volatility,
    and recent price history for AI decision-making.

    Args:
        candles: List of candles (sorted by time ascending)
        current_price: Current market price

    Returns:
        Dict with market context including price changes, volatility, etc.
    """
    if not candles:
        return {
            "current_price": current_price,
            "price_24h_ago": current_price,
            "price_change_24h_pct": 0.0,
            "period_high": current_price,
            "period_low": current_price,
            "recent_prices": [current_price],
            "data_points": 0,
            "volatility": 0.0,
        }

    # Extract close prices
    closes = []
    for c in candles:
        close = c.get("close")
        if close is not None:
            try:
                closes.append(float(close))
            except (ValueError, TypeError):
                continue

    if not closes:
        return {
            "current_price": current_price,
            "price_24h_ago": current_price,
            "price_change_24h_pct": 0.0,
            "period_high": current_price,
            "period_low": current_price,
            "recent_prices": [current_price],
            "data_points": 0,
            "volatility": 0.0,
        }

    # Calculate metrics
    price_24h_ago = closes[0] if closes else current_price
    price_change_24h_pct = ((current_price - price_24h_ago) / price_24h_ago * 100) if price_24h_ago else 0

    # Get highs and lows
    highs = [float(c.get("high", 0)) for c in candles if c.get("high") is not None]
    lows = [float(c.get("low", float("inf"))) for c in candles if c.get("low") is not None]

    period_high = max(highs) if highs else current_price
    period_low = min(lows) if lows else current_price

    # Calculate volatility (standard deviation of returns)
    volatility = 0.0
    if len(closes) > 1:
        returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes)) if closes[i - 1] != 0]
        if returns:
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            volatility = variance ** 0.5 * 100  # Convert to percentage

    # Recent prices (last 10 for AI context)
    recent_prices = closes[-10:] if len(closes) >= 10 else closes

    return {
        "current_price": current_price,
        "price_24h_ago": price_24h_ago,
        "price_change_24h_pct": round(price_change_24h_pct, 2),
        "period_high": period_high,
        "period_low": period_low,
        "recent_prices": recent_prices,
        "data_points": len(candles),
        "volatility": round(volatility, 4),
    }


def fill_candle_gaps(
    candles: List[Dict[str, Any]], interval_seconds: int, max_candles: int = 300
) -> List[Dict[str, Any]]:
    """
    Fill gaps in candle data by creating synthetic candles.

    When there are no trades for a time period, Coinbase doesn't return a candle.
    Charting platforms fill these gaps by copying the previous close price.
    This function does the same to ensure continuous data for indicator calculations.

    Args:
        candles: List of candles sorted by time ascending
        interval_seconds: Expected interval between candles (60 for ONE_MINUTE)
        max_candles: Maximum number of candles to return (to avoid memory issues)

    Returns:
        List of candles with gaps filled
    """
    if not candles or len(candles) < 2:
        return candles

    filled = []
    total_gaps_filled = 0
    max_gap_seen = 0

    for i, candle in enumerate(candles):
        if i == 0:
            filled.append(candle)
            continue

        prev_candle = filled[-1]
        prev_time = int(prev_candle.get("start", prev_candle.get("time", 0)))
        curr_time = int(candle.get("start", candle.get("time", 0)))

        # Calculate how many candles are missing between prev and curr
        time_gap = curr_time - prev_time
        max_gap_seen = max(max_gap_seen, time_gap)
        missing_count = (time_gap // interval_seconds) - 1

        # Fill in missing candles (use previous close as OHLC, volume = 0)
        if missing_count > 0:
            total_gaps_filled += missing_count
            prev_close = prev_candle.get("close")
            for j in range(1, missing_count + 1):
                synthetic_time = prev_time + (j * interval_seconds)
                synthetic_candle = {
                    "start": synthetic_time,
                    "open": prev_close,
                    "high": prev_close,
                    "low": prev_close,
                    "close": prev_close,
                    "volume": 0,  # No trades in this period
                }
                filled.append(synthetic_candle)

                # Safety check to avoid memory issues
                if len(filled) >= max_candles:
                    break

        filled.append(candle)

        if len(filled) >= max_candles:
            break

    # Log gap-fill stats only if gaps were filled
    if total_gaps_filled > 0:
        logger.debug(
            f"Gap-filled: input={len(candles)}, filled={total_gaps_filled} gaps, "
            f"max_gap={max_gap_seen}s, output={len(filled)}"
        )

    return filled[-max_candles:] if len(filled) > max_candles else filled
