"""
Bull Flag Scanner Module

Utilities for detecting volume spikes and bull flag patterns on USD trading pairs.
Used by the BullFlagStrategy to find entry opportunities.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BlacklistedCoin, Settings

logger = logging.getLogger(__name__)

# Cache for volume SMA to avoid repeated API calls
_volume_sma_cache: Dict[str, Tuple[float, datetime]] = {}
VOLUME_SMA_CACHE_HOURS = 4


async def get_tradeable_usd_coins(db: AsyncSession) -> List[str]:
    """
    Get USD pairs for coins in allowed categories.

    Queries the BlacklistedCoin table for coins in allowed categories,
    then builds product_ids like "{symbol}-USD".

    Returns:
        List of product IDs (e.g., ["ETH-USD", "SOL-USD", ...])
    """
    # Import here to avoid circular import
    from app.routers.blacklist_router import get_allowed_categories

    # Get allowed categories from Settings
    allowed = await get_allowed_categories(db)
    logger.debug(f"Allowed categories: {allowed}")

    if not allowed:
        logger.warning("No allowed categories configured, defaulting to APPROVED")
        allowed = ["APPROVED"]

    # Build query conditions for each allowed category
    conditions = []
    for cat in allowed:
        cat_upper = cat.upper()
        if cat_upper == "BLACKLISTED":
            # No prefix means blacklisted (legacy behavior)
            # Match entries where reason doesn't start with [CATEGORY]
            conditions.append(
                ~BlacklistedCoin.reason.like("[%]%") | BlacklistedCoin.reason.is_(None)
            )
        else:
            # Match entries with [CATEGORY] prefix
            conditions.append(BlacklistedCoin.reason.like(f"[{cat_upper}]%"))

    if not conditions:
        return []

    # Query coins matching any allowed category
    query = select(BlacklistedCoin.symbol).where(or_(*conditions))
    result = await db.execute(query)
    symbols = [row[0] for row in result.fetchall()]

    # Build USD product IDs
    product_ids = [f"{symbol}-USD" for symbol in symbols]
    logger.info(f"Found {len(product_ids)} tradeable USD coins in categories {allowed}")

    return product_ids


async def calculate_volume_sma_50(
    exchange_client: Any,
    product_id: str,
    force_refresh: bool = False
) -> Optional[float]:
    """
    Calculate 50-day SMA of daily volume for a product.

    Uses caching to avoid repeated API calls. Cache expires after 4 hours.

    Args:
        exchange_client: Coinbase client instance
        product_id: Trading pair (e.g., "ETH-USD")
        force_refresh: Force cache refresh

    Returns:
        50-day average daily volume, or None if unable to calculate
    """
    global _volume_sma_cache

    # Check cache
    cache_key = product_id
    if not force_refresh and cache_key in _volume_sma_cache:
        cached_value, cached_time = _volume_sma_cache[cache_key]
        cache_age = datetime.utcnow() - cached_time
        if cache_age < timedelta(hours=VOLUME_SMA_CACHE_HOURS):
            return cached_value

    try:
        # Fetch 55 days of daily candles (extra buffer for calculation)
        # Calculate start/end timestamps (Coinbase API requires these, not limit)
        end_time = int(datetime.utcnow().timestamp())
        start_time = int((datetime.utcnow() - timedelta(days=55)).timestamp())
        candles = await exchange_client.get_candles(
            product_id=product_id,
            granularity="ONE_DAY",
            start=start_time,
            end=end_time
        )

        if not candles or len(candles) < 50:
            logger.warning(f"Insufficient candle data for {product_id}: {len(candles) if candles else 0} candles")
            return None

        # Extract volumes (candle format: [timestamp, low, high, open, close, volume])
        volumes = []
        for candle in candles[:50]:  # Use most recent 50 days
            if isinstance(candle, dict):
                volume = float(candle.get("volume", 0))
            else:
                # Assume list format [timestamp, low, high, open, close, volume]
                volume = float(candle[5]) if len(candle) > 5 else 0
            volumes.append(volume)

        if not volumes:
            return None

        # Calculate SMA
        avg_volume = sum(volumes) / len(volumes)

        # Cache the result
        _volume_sma_cache[cache_key] = (avg_volume, datetime.utcnow())

        logger.debug(f"{product_id} 50-day avg volume: {avg_volume:.2f}")
        return avg_volume

    except Exception as e:
        logger.error(f"Error calculating volume SMA for {product_id}: {e}")
        return None


async def detect_volume_spike(
    exchange_client: Any,
    product_id: str,
    multiplier: float = 5.0
) -> Tuple[bool, float, float]:
    """
    Check if current 24h volume >= multiplier * 50-day average volume.

    Args:
        exchange_client: Coinbase client instance
        product_id: Trading pair (e.g., "ETH-USD")
        multiplier: Volume spike threshold (default 5x)

    Returns:
        Tuple of (is_spike, current_volume, avg_volume)
    """
    try:
        # Get 50-day average
        avg_volume = await calculate_volume_sma_50(exchange_client, product_id)
        if avg_volume is None or avg_volume <= 0:
            return (False, 0.0, 0.0)

        # Get current 24h volume from ticker or recent candle
        ticker = await exchange_client.get_ticker(product_id)
        if not ticker:
            return (False, 0.0, avg_volume)

        current_volume = float(ticker.get("volume_24h", 0) or ticker.get("volume", 0))

        # Check for spike
        threshold = avg_volume * multiplier
        is_spike = current_volume >= threshold

        if is_spike:
            logger.info(
                f"Volume spike detected for {product_id}: "
                f"{current_volume:.2f} >= {threshold:.2f} ({multiplier}x avg)"
            )

        return (is_spike, current_volume, avg_volume)

    except Exception as e:
        logger.error(f"Error detecting volume spike for {product_id}: {e}")
        return (False, 0.0, 0.0)


def detect_bull_flag_pattern(
    candles: List[Dict[str, Any]],
    config: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Detect bull flag pattern in candle data.

    Algorithm:
    1. Find the POLE: Series of up candles with significant gain
    2. Find the FLAG: Pullback with minimum red candles
    3. Find CONFIRMATION: First green candle after pullback
    4. Calculate stop_loss (pullback low) and take_profit_target (2x risk)
    5. REJECT if take_profit_target > pole_high

    Args:
        candles: List of candle dicts, most recent first. Each has:
                 open, high, low, close, volume, timestamp
        config: Strategy configuration with:
                - min_pole_candles: Minimum candles in pole (default 3)
                - min_pole_gain_pct: Minimum % gain in pole (default 3.0)
                - min_pullback_candles: Minimum red candles in pullback (default 2)
                - max_pullback_candles: Maximum pullback length (default 8)
                - pullback_retracement_max: Max % of pole retraced (default 50.0)
                - reward_risk_ratio: TTP target multiplier (default 2.0)

    Returns:
        Pattern dict with entry details, or None if no valid pattern
    """
    # Extract config with defaults
    min_pole_candles = config.get("min_pole_candles", 3)
    min_pole_gain_pct = config.get("min_pole_gain_pct", 3.0)
    min_pullback_candles = config.get("min_pullback_candles", 2)
    max_pullback_candles = config.get("max_pullback_candles", 8)
    pullback_retracement_max = config.get("pullback_retracement_max", 50.0)
    reward_risk_ratio = config.get("reward_risk_ratio", 2.0)

    if not candles or len(candles) < (min_pole_candles + min_pullback_candles + 1):
        return None

    # Ensure candles are in chronological order (oldest first for analysis)
    # API usually returns newest first, so we may need to reverse
    if len(candles) > 1:
        first_ts = _get_candle_timestamp(candles[0])
        last_ts = _get_candle_timestamp(candles[-1])
        if first_ts > last_ts:
            candles = list(reversed(candles))

    # Helper to get candle values
    def get_ohlc(candle):
        if isinstance(candle, dict):
            return (
                float(candle.get("open", 0)),
                float(candle.get("high", 0)),
                float(candle.get("low", 0)),
                float(candle.get("close", 0))
            )
        else:
            # List format: [timestamp, low, high, open, close, volume]
            return (float(candle[3]), float(candle[2]), float(candle[1]), float(candle[4]))

    def is_green(candle):
        o, h, l, c = get_ohlc(candle)
        return c > o

    def is_red(candle):
        o, h, l, c = get_ohlc(candle)
        return c < o

    # Start from most recent candle and work backwards
    n = len(candles)

    # Step 1: Look for CONFIRMATION candle (most recent green candle)
    confirmation_idx = None
    for i in range(n - 1, -1, -1):
        if is_green(candles[i]):
            confirmation_idx = i
            break

    if confirmation_idx is None or confirmation_idx < min_pullback_candles + min_pole_candles:
        logger.debug("No confirmation candle found or not enough history")
        return None

    confirmation_candle = candles[confirmation_idx]
    _, _, _, entry_price = get_ohlc(confirmation_candle)

    # Step 2: Find FLAG (pullback) - consecutive red candles before confirmation
    pullback_start = confirmation_idx - 1
    red_count = 0
    pullback_low = float("inf")
    pullback_high = 0.0

    for i in range(pullback_start, -1, -1):
        candle = candles[i]
        o, h, l, c = get_ohlc(candle)

        # Track pullback range
        pullback_low = min(pullback_low, l)
        pullback_high = max(pullback_high, h)

        if is_red(candle):
            red_count += 1
        else:
            # First non-red candle marks end of pullback
            break

        # Check max pullback length
        if (pullback_start - i + 1) > max_pullback_candles:
            logger.debug(f"Pullback too long: {pullback_start - i + 1} > {max_pullback_candles}")
            return None

    if red_count < min_pullback_candles:
        logger.debug(f"Insufficient pullback candles: {red_count} < {min_pullback_candles}")
        return None

    pullback_end_idx = pullback_start - red_count

    # Step 3: Find POLE before pullback
    pole_end_idx = pullback_end_idx
    pole_start_idx = None
    pole_high = 0.0
    pole_low = float("inf")
    pole_candle_count = 0

    for i in range(pole_end_idx, -1, -1):
        candle = candles[i]
        o, h, l, c = get_ohlc(candle)

        # Pole should be upward trending
        if is_green(candle) or (i > 0 and c > get_ohlc(candles[i-1])[3]):
            pole_high = max(pole_high, h)
            pole_low = min(pole_low, l)
            pole_candle_count += 1
            pole_start_idx = i
        else:
            # End of pole trend
            break

    if pole_candle_count < min_pole_candles:
        logger.debug(f"Insufficient pole candles: {pole_candle_count} < {min_pole_candles}")
        return None

    # Calculate pole gain
    if pole_low <= 0:
        return None
    pole_gain_pct = ((pole_high - pole_low) / pole_low) * 100

    if pole_gain_pct < min_pole_gain_pct:
        logger.debug(f"Insufficient pole gain: {pole_gain_pct:.2f}% < {min_pole_gain_pct}%")
        return None

    # Step 4: Validate retracement
    pole_range = pole_high - pole_low
    if pole_range <= 0:
        return None

    retracement = ((pole_high - pullback_low) / pole_range) * 100
    if retracement > pullback_retracement_max:
        logger.debug(f"Retracement too deep: {retracement:.2f}% > {pullback_retracement_max}%")
        return None

    # Step 5: Calculate stop loss and take profit target
    stop_loss = pullback_low
    risk = entry_price - stop_loss

    if risk <= 0:
        logger.debug(f"Invalid risk (entry {entry_price} <= stop_loss {stop_loss})")
        return None

    take_profit_target = entry_price + (risk * reward_risk_ratio)

    # Step 6: REJECT if take profit target exceeds pole high
    if take_profit_target > pole_high:
        logger.debug(
            f"TTP target {take_profit_target:.4f} exceeds pole high {pole_high:.4f}, "
            f"pattern rejected"
        )
        return None

    # Pattern is valid - return pattern data
    pattern = {
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit_target": take_profit_target,
        "pole_high": pole_high,
        "pole_low": pole_low,
        "pole_gain_pct": pole_gain_pct,
        "pole_candle_count": pole_candle_count,
        "pullback_low": pullback_low,
        "pullback_candles": red_count,
        "retracement_pct": retracement,
        "risk": risk,
        "reward": take_profit_target - entry_price,
        "risk_reward_ratio": reward_risk_ratio,
        "confirmation_timestamp": _get_candle_timestamp(confirmation_candle),
        "pattern_valid": True,
    }

    logger.info(
        f"Bull flag pattern detected: entry={entry_price:.4f}, "
        f"SL={stop_loss:.4f}, TP={take_profit_target:.4f}, "
        f"pole_gain={pole_gain_pct:.2f}%, retracement={retracement:.2f}%"
    )

    return pattern


def _get_candle_timestamp(candle: Any) -> int:
    """Extract timestamp from candle (dict or list format)."""
    if isinstance(candle, dict):
        ts = candle.get("start") or candle.get("timestamp") or candle.get("time")
        return int(ts) if ts else 0
    else:
        return int(candle[0]) if candle else 0


def clear_volume_cache():
    """Clear the volume SMA cache (useful for testing)."""
    global _volume_sma_cache
    _volume_sma_cache = {}


async def scan_for_bull_flag_opportunities(
    db: AsyncSession,
    exchange_client: Any,
    config: Dict[str, Any],
    max_coins: int = 50
) -> List[Dict[str, Any]]:
    """
    Scan allowed USD coins for bull flag opportunities.

    This is the main entry point for the bull flag scanner.

    Args:
        db: Database session
        exchange_client: Coinbase client instance
        config: Strategy configuration
        max_coins: Maximum coins to scan (for rate limiting)

    Returns:
        List of opportunities with product_id and pattern data
    """
    opportunities = []

    # Get tradeable coins
    product_ids = await get_tradeable_usd_coins(db)
    if not product_ids:
        logger.warning("No tradeable USD coins found")
        return []

    # Limit to max_coins for rate limiting
    product_ids = product_ids[:max_coins]

    volume_multiplier = config.get("volume_multiplier", 5.0)
    timeframe = config.get("timeframe", "FIFTEEN_MINUTE")

    logger.info(f"Scanning {len(product_ids)} USD coins for bull flag patterns...")

    for product_id in product_ids:
        try:
            # Step 1: Check for volume spike
            is_spike, current_vol, avg_vol = await detect_volume_spike(
                exchange_client, product_id, volume_multiplier
            )

            if not is_spike:
                continue

            # Step 2: Get candles for pattern detection
            # Calculate timeframe-appropriate lookback period
            granularity_minutes = {
                "ONE_MINUTE": 1, "FIVE_MINUTE": 5, "FIFTEEN_MINUTE": 15,
                "THIRTY_MINUTE": 30, "ONE_HOUR": 60, "TWO_HOUR": 120,
                "SIX_HOUR": 360, "ONE_DAY": 1440
            }
            minutes = granularity_minutes.get(timeframe, 15)
            lookback_minutes = minutes * 50  # 50 candles worth
            pattern_end_time = int(datetime.utcnow().timestamp())
            pattern_start_time = int((datetime.utcnow() - timedelta(minutes=lookback_minutes)).timestamp())
            candles = await exchange_client.get_candles(
                product_id=product_id,
                granularity=timeframe,
                start=pattern_start_time,
                end=pattern_end_time
            )

            if not candles:
                continue

            # Step 3: Detect bull flag pattern
            pattern = detect_bull_flag_pattern(candles, config)

            if pattern:
                opportunities.append({
                    "product_id": product_id,
                    "pattern": pattern,
                    "current_volume": current_vol,
                    "avg_volume": avg_vol,
                    "volume_multiplier": current_vol / avg_vol if avg_vol > 0 else 0,
                })

        except Exception as e:
            logger.error(f"Error scanning {product_id}: {e}")
            continue

    logger.info(f"Found {len(opportunities)} bull flag opportunities")
    return opportunities
