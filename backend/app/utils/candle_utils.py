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
    "TEN_MINUTE": 600,       # Synthetic - aggregated from 5-minute candles
    "FIFTEEN_MINUTE": 900,
    "THIRTY_MINUTE": 1800,
    "ONE_HOUR": 3600,
    "TWO_HOUR": 7200,
    "FOUR_HOUR": 14400,
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
    "TEN_MINUTE": ("FIVE_MINUTE", 2),
    "FOUR_HOUR": ("ONE_HOUR", 4),
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


def calculate_bot_check_interval(bot_config: Dict[str, Any]) -> int:
    """
    Calculate the minimum check interval for a bot based on its indicator timeframes.

    The bot should check as frequently as its shortest timeframe indicator,
    since that's the fastest-moving signal that could trigger a trade.

    Args:
        bot_config: Bot's strategy_config dict containing conditions for each phase

    Returns:
        Minimum check interval in seconds (defaults to 300 if no timeframes found)

    Example:
        Bot with 15-min SMA + 3-min RSI -> returns 180 (check every 3 minutes)
        Bot with only 1-hour indicators -> returns 3600 (check every hour)
    """
    timeframes = []

    # Extract timeframes from all phases
    for phase in ['base_order_conditions', 'safety_order_conditions', 'take_profit_conditions']:
        phase_data = bot_config.get(phase, [])

        # Handle both formats:
        # 1. List format: [{condition}, {condition}, ...]
        # 2. Dict format: {"groups": [{"conditions": [...]}, ...]}
        conditions_to_check = []

        if isinstance(phase_data, list):
            # Old format: direct list of conditions
            conditions_to_check = phase_data
        elif isinstance(phase_data, dict) and 'groups' in phase_data:
            # New format: grouped conditions
            for group in phase_data.get('groups', []):
                if isinstance(group, dict) and 'conditions' in group:
                    conditions_to_check.extend(group['conditions'])

        # Extract timeframes from conditions
        for condition in conditions_to_check:
            if isinstance(condition, dict) and 'timeframe' in condition:
                tf = condition['timeframe']
                if tf and tf != 'required':  # Skip special "required" markers
                    timeframes.append(tf)

    # Also check standalone indicator config (for bots that use different format)
    if 'indicators' in bot_config and isinstance(bot_config['indicators'], dict):
        for indicator_config in bot_config['indicators'].values():
            if isinstance(indicator_config, dict) and 'timeframe' in indicator_config:
                tf = indicator_config['timeframe']
                if tf and tf != 'required':
                    timeframes.append(tf)

    # Convert to seconds and find minimum
    if not timeframes:
        return 300  # Default to 5 minutes if no timeframes found

    intervals_seconds = [timeframe_to_seconds(tf) for tf in timeframes]
    return min(intervals_seconds)


def next_check_time_aligned(interval_seconds: int, current_time: int) -> int:
    """
    Calculate the next check time aligned to candle close boundaries.

    This ensures we check RIGHT when candles close, not mid-candle.

    Args:
        interval_seconds: Check interval in seconds (e.g., 180 for 3-minute)
        current_time: Current Unix timestamp

    Returns:
        Next check time as Unix timestamp

    Example:
        Current time: 12:04:30, interval: 180 (3-min)
        Next boundary: 12:06:00 (next 3-min candle close at :00, :03, :06, :09...)
    """
    # Calculate seconds since Unix epoch start
    # For proper alignment, we need to align to hour boundaries
    # Example: 3-min candles close at :00, :03, :06, :09, :12, :15, etc.

    # Get current hour boundary
    hour_boundary = (current_time // 3600) * 3600

    # Calculate seconds since hour start
    seconds_since_hour = current_time - hour_boundary

    # Find next boundary within the hour
    next_offset = ((seconds_since_hour // interval_seconds) + 1) * interval_seconds

    # If next boundary is beyond the hour, wrap to next hour
    if next_offset >= 3600:
        next_check = hour_boundary + 3600  # Start of next hour
    else:
        next_check = hour_boundary + next_offset

    return next_check


def get_timeframes_for_phases(
    bot_config: Dict[str, Any], phases: List[str]
) -> set:
    """
    Extract unique timeframes needed for specific trading phases.

    Phase 3 optimization: Only fetch candles for timeframes actually needed
    in the current phase (e.g., only take_profit timeframes for open positions).

    Args:
        bot_config: Bot's strategy_config dict
        phases: List of phase names to extract timeframes from
                (e.g., ["base_order_conditions"], ["safety_order_conditions", "take_profit_conditions"])

    Returns:
        Set of unique timeframe strings needed for the specified phases

    Example:
        # For open position (checking DCA + exit):
        get_timeframes_for_phases(config, ["safety_order_conditions", "take_profit_conditions"])
        -> {"THREE_MINUTE", "FIFTEEN_MINUTE"}

        # For new position (checking entry):
        get_timeframes_for_phases(config, ["base_order_conditions"])
        -> {"FIVE_MINUTE"}
    """
    timeframes = set()

    for phase in phases:
        phase_data = bot_config.get(phase, [])

        # Handle both formats:
        # 1. List format: [{condition}, {condition}, ...]
        # 2. Dict format: {"groups": [{"conditions": [...]}, ...]}
        conditions_to_check = []

        if isinstance(phase_data, list):
            # Old format: direct list of conditions
            conditions_to_check = phase_data
        elif isinstance(phase_data, dict) and 'groups' in phase_data:
            # New format: grouped conditions
            for group in phase_data.get('groups', []):
                if isinstance(group, dict) and 'conditions' in group:
                    conditions_to_check.extend(group['conditions'])

        # Extract timeframes from conditions
        for condition in conditions_to_check:
            if isinstance(condition, dict) and 'timeframe' in condition:
                tf = condition['timeframe']
                if tf and tf != 'required':  # Skip special "required" markers
                    timeframes.add(tf)

    # Also check standalone indicator config if provided (for different bot formats)
    if 'indicators' in bot_config and isinstance(bot_config['indicators'], dict):
        for indicator_config in bot_config['indicators'].values():
            if isinstance(indicator_config, dict) and 'timeframe' in indicator_config:
                tf = indicator_config['timeframe']
                if tf and tf != 'required':
                    timeframes.add(tf)

    # Default to FIVE_MINUTE if no timeframes found
    if not timeframes:
        timeframes.add("FIVE_MINUTE")

    return timeframes
