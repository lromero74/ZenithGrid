"""
Cache loading and saving functions for news, videos, and other data.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cache file paths
CACHE_DIR = Path(__file__).parent.parent.parent.parent
CACHE_FILE = CACHE_DIR / "news_cache.json"
VIDEO_CACHE_FILE = CACHE_DIR / "video_cache.json"
FEAR_GREED_CACHE_FILE = CACHE_DIR / "fear_greed_cache.json"
BLOCK_HEIGHT_CACHE_FILE = CACHE_DIR / "block_height_cache.json"
US_DEBT_CACHE_FILE = CACHE_DIR / "us_debt_cache.json"
# New market metrics caches
BTC_DOMINANCE_CACHE_FILE = CACHE_DIR / "btc_dominance_cache.json"
ALTSEASON_CACHE_FILE = CACHE_DIR / "altseason_cache.json"
FUNDING_RATES_CACHE_FILE = CACHE_DIR / "funding_rates_cache.json"
STABLECOIN_MCAP_CACHE_FILE = CACHE_DIR / "stablecoin_mcap_cache.json"
EXCHANGE_FLOWS_CACHE_FILE = CACHE_DIR / "exchange_flows_cache.json"
MEMPOOL_CACHE_FILE = CACHE_DIR / "mempool_cache.json"
HASH_RATE_CACHE_FILE = CACHE_DIR / "hash_rate_cache.json"
LIGHTNING_CACHE_FILE = CACHE_DIR / "lightning_cache.json"
ATH_CACHE_FILE = CACHE_DIR / "ath_cache.json"

# Cache timing constants (background refresh service handles actual refresh timing)
NEWS_CACHE_CHECK_MINUTES = 30  # Fallback: check every 30 minutes if no background refresh
VIDEO_CACHE_CHECK_MINUTES = 60  # Videos refresh hourly (less frequent than news)
NEWS_ITEM_MAX_AGE_DAYS = 14  # Prune items older than this
FEAR_GREED_CACHE_MINUTES = 60  # Fear/greed updates daily, no need for frequent checks
BLOCK_HEIGHT_CACHE_MINUTES = 10  # Keep for halving countdown accuracy
US_DEBT_CACHE_HOURS = 24  # Update US debt once per day
# Market metrics cache timing
MARKET_METRICS_CACHE_MINUTES = 15  # Update market metrics every 15 minutes

# Export constants needed by fetchers
__all__ = [
    # File paths
    "CACHE_DIR",
    "CACHE_FILE",
    "VIDEO_CACHE_FILE",
    "FEAR_GREED_CACHE_FILE",
    "BLOCK_HEIGHT_CACHE_FILE",
    "US_DEBT_CACHE_FILE",
    "BTC_DOMINANCE_CACHE_FILE",
    "ALTSEASON_CACHE_FILE",
    "FUNDING_RATES_CACHE_FILE",
    "STABLECOIN_MCAP_CACHE_FILE",
    "MEMPOOL_CACHE_FILE",
    "HASH_RATE_CACHE_FILE",
    "LIGHTNING_CACHE_FILE",
    "ATH_CACHE_FILE",
    # Timing constants
    "NEWS_CACHE_CHECK_MINUTES",
    "VIDEO_CACHE_CHECK_MINUTES",
    "NEWS_ITEM_MAX_AGE_DAYS",
    "FEAR_GREED_CACHE_MINUTES",
    "BLOCK_HEIGHT_CACHE_MINUTES",
    "US_DEBT_CACHE_HOURS",
    "MARKET_METRICS_CACHE_MINUTES",
    # Functions
    "load_cache",
    "save_cache",
    "load_video_cache",
    "save_video_cache",
    "load_fear_greed_cache",
    "save_fear_greed_cache",
    "load_block_height_cache",
    "save_block_height_cache",
    "load_us_debt_cache",
    "save_us_debt_cache",
    "load_btc_dominance_cache",
    "save_btc_dominance_cache",
    "load_altseason_cache",
    "save_altseason_cache",
    "load_funding_rates_cache",
    "save_funding_rates_cache",
    "load_stablecoin_mcap_cache",
    "save_stablecoin_mcap_cache",
    "load_mempool_cache",
    "save_mempool_cache",
    "load_hash_rate_cache",
    "save_hash_rate_cache",
    "load_lightning_cache",
    "save_lightning_cache",
    "load_ath_cache",
    "save_ath_cache",
    "prune_old_items",
    "merge_news_items",
]


def load_cache(for_merge: bool = False) -> Optional[Dict[str, Any]]:
    """Load news cache from file.

    Args:
        for_merge: If True, return cache even if expired (for merging new items)
    """
    if not CACHE_FILE.exists():
        return None

    try:
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)

        # Check if cache needs refresh (15 minutes)
        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        cache_age = datetime.now() - cached_at

        if for_merge:
            # For merging, return cache regardless of age
            return cache

        if cache_age > timedelta(minutes=NEWS_CACHE_CHECK_MINUTES):
            logger.info(f"News cache needs refresh (age: {cache_age})")
            return None

        return cache
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to load news cache: {e}")
        return None


def save_cache(data: Dict[str, Any]) -> None:
    """Save news cache to file"""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("News cache saved")
    except Exception as e:
        logger.error(f"Failed to save news cache: {e}")


def prune_old_items(items: List[Dict], max_age_days: int = NEWS_ITEM_MAX_AGE_DAYS) -> List[Dict]:
    """Remove items older than max_age_days based on published date."""
    cutoff = datetime.now() - timedelta(days=max_age_days)
    pruned = []
    removed_count = 0

    for item in items:
        published = item.get("published")
        if not published:
            # Keep items without published date (rare edge case)
            pruned.append(item)
            continue

        try:
            # Handle both with and without Z suffix
            pub_str = published.rstrip("Z")
            pub_date = datetime.fromisoformat(pub_str)

            if pub_date >= cutoff:
                pruned.append(item)
            else:
                removed_count += 1
        except (ValueError, TypeError):
            # If we can't parse date, keep the item
            pruned.append(item)

    if removed_count > 0:
        logger.info(f"Pruned {removed_count} items older than {max_age_days} days")

    return pruned


def merge_news_items(existing: List[Dict], new_items: List[Dict]) -> List[Dict]:
    """Merge new items with existing cache. New items go to top, deduped by URL."""
    # Create set of existing URLs for fast lookup
    existing_urls = {item.get("url") for item in existing if item.get("url")}

    # Find truly new items
    truly_new = [item for item in new_items if item.get("url") not in existing_urls]

    if truly_new:
        logger.info(f"Found {len(truly_new)} new news items to add")

    # New items at top, then existing (already sorted by date)
    merged = truly_new + existing

    # Sort by published date (most recent first)
    merged.sort(
        key=lambda x: x.get("published") or "1970-01-01",
        reverse=True
    )

    return merged


def load_video_cache(for_merge: bool = False) -> Optional[Dict[str, Any]]:
    """Load video cache from file.

    Args:
        for_merge: If True, return cache even if expired (for merging new items)
    """
    if not VIDEO_CACHE_FILE.exists():
        return None

    try:
        with open(VIDEO_CACHE_FILE, "r") as f:
            cache = json.load(f)

        # Check if cache needs refresh (15 minutes)
        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        cache_age = datetime.now() - cached_at

        if for_merge:
            # For merging, return cache regardless of age
            return cache

        if cache_age > timedelta(minutes=NEWS_CACHE_CHECK_MINUTES):
            logger.info(f"Video cache needs refresh (age: {cache_age})")
            return None

        return cache
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to load video cache: {e}")
        return None


def save_video_cache(data: Dict[str, Any]) -> None:
    """Save video cache to file"""
    try:
        with open(VIDEO_CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Video cache saved")
    except Exception as e:
        logger.error(f"Failed to save video cache: {e}")


def load_fear_greed_cache() -> Optional[Dict[str, Any]]:
    """Load fear/greed cache from file (15 minute cache)"""
    if not FEAR_GREED_CACHE_FILE.exists():
        return None

    try:
        with open(FEAR_GREED_CACHE_FILE, "r") as f:
            cache = json.load(f)

        # Check if cache is expired (15 minutes)
        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        if datetime.now() - cached_at > timedelta(minutes=FEAR_GREED_CACHE_MINUTES):
            logger.info("Fear/Greed cache expired")
            return None

        return cache
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to load fear/greed cache: {e}")
        return None


def save_fear_greed_cache(data: Dict[str, Any]) -> None:
    """Save fear/greed cache to file"""
    try:
        with open(FEAR_GREED_CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Fear/Greed cache saved")
    except Exception as e:
        logger.error(f"Failed to save fear/greed cache: {e}")


def load_block_height_cache() -> Optional[Dict[str, Any]]:
    """Load block height cache from file (10 minute cache)"""
    if not BLOCK_HEIGHT_CACHE_FILE.exists():
        return None

    try:
        with open(BLOCK_HEIGHT_CACHE_FILE, "r") as f:
            cache = json.load(f)

        # Check if cache is expired (10 minutes)
        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        if datetime.now() - cached_at > timedelta(minutes=BLOCK_HEIGHT_CACHE_MINUTES):
            logger.info("Block height cache expired")
            return None

        return cache
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to load block height cache: {e}")
        return None


def save_block_height_cache(data: Dict[str, Any]) -> None:
    """Save block height cache to file"""
    try:
        with open(BLOCK_HEIGHT_CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Block height cache saved")
    except Exception as e:
        logger.error(f"Failed to save block height cache: {e}")


def load_us_debt_cache() -> Optional[Dict[str, Any]]:
    """Load US debt cache from file (24-hour cache)"""
    if not US_DEBT_CACHE_FILE.exists():
        return None

    try:
        with open(US_DEBT_CACHE_FILE, "r") as f:
            cache = json.load(f)

        # Check if cache is expired (24 hours)
        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        if datetime.now() - cached_at > timedelta(hours=US_DEBT_CACHE_HOURS):
            logger.info("US debt cache expired")
            return None

        return cache
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to load US debt cache: {e}")
        return None


def save_us_debt_cache(data: Dict[str, Any]) -> None:
    """Save US debt cache to file"""
    try:
        with open(US_DEBT_CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("US debt cache saved")
    except Exception as e:
        logger.error(f"Failed to save US debt cache: {e}")


# Generic market metrics cache functions
def _load_market_metrics_cache(cache_file: Path, name: str) -> Optional[Dict[str, Any]]:
    """Generic loader for market metrics caches (15 minute expiry)"""
    if not cache_file.exists():
        return None

    try:
        with open(cache_file, "r") as f:
            cache = json.load(f)

        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        if datetime.now() - cached_at > timedelta(minutes=MARKET_METRICS_CACHE_MINUTES):
            logger.info(f"{name} cache expired")
            return None

        return cache
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to load {name} cache: {e}")
        return None


def _save_market_metrics_cache(cache_file: Path, name: str, data: Dict[str, Any]) -> None:
    """Generic saver for market metrics caches"""
    try:
        with open(cache_file, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"{name} cache saved")
    except Exception as e:
        logger.error(f"Failed to save {name} cache: {e}")


def load_btc_dominance_cache() -> Optional[Dict[str, Any]]:
    return _load_market_metrics_cache(BTC_DOMINANCE_CACHE_FILE, "BTC dominance")


def save_btc_dominance_cache(data: Dict[str, Any]) -> None:
    _save_market_metrics_cache(BTC_DOMINANCE_CACHE_FILE, "BTC dominance", data)


def load_altseason_cache() -> Optional[Dict[str, Any]]:
    return _load_market_metrics_cache(ALTSEASON_CACHE_FILE, "Altseason index")


def save_altseason_cache(data: Dict[str, Any]) -> None:
    _save_market_metrics_cache(ALTSEASON_CACHE_FILE, "Altseason index", data)


def load_funding_rates_cache() -> Optional[Dict[str, Any]]:
    return _load_market_metrics_cache(FUNDING_RATES_CACHE_FILE, "Funding rates")


def save_funding_rates_cache(data: Dict[str, Any]) -> None:
    _save_market_metrics_cache(FUNDING_RATES_CACHE_FILE, "Funding rates", data)


def load_stablecoin_mcap_cache() -> Optional[Dict[str, Any]]:
    return _load_market_metrics_cache(STABLECOIN_MCAP_CACHE_FILE, "Stablecoin mcap")


def save_stablecoin_mcap_cache(data: Dict[str, Any]) -> None:
    _save_market_metrics_cache(STABLECOIN_MCAP_CACHE_FILE, "Stablecoin mcap", data)


def load_exchange_flows_cache() -> Optional[Dict[str, Any]]:
    return _load_market_metrics_cache(EXCHANGE_FLOWS_CACHE_FILE, "Exchange flows")


def save_exchange_flows_cache(data: Dict[str, Any]) -> None:
    _save_market_metrics_cache(EXCHANGE_FLOWS_CACHE_FILE, "Exchange flows", data)


def load_mempool_cache() -> Optional[Dict[str, Any]]:
    return _load_market_metrics_cache(MEMPOOL_CACHE_FILE, "Mempool")


def save_mempool_cache(data: Dict[str, Any]) -> None:
    _save_market_metrics_cache(MEMPOOL_CACHE_FILE, "Mempool", data)


def load_hash_rate_cache() -> Optional[Dict[str, Any]]:
    return _load_market_metrics_cache(HASH_RATE_CACHE_FILE, "Hash rate")


def save_hash_rate_cache(data: Dict[str, Any]) -> None:
    _save_market_metrics_cache(HASH_RATE_CACHE_FILE, "Hash rate", data)


def load_lightning_cache() -> Optional[Dict[str, Any]]:
    return _load_market_metrics_cache(LIGHTNING_CACHE_FILE, "Lightning")


def save_lightning_cache(data: Dict[str, Any]) -> None:
    _save_market_metrics_cache(LIGHTNING_CACHE_FILE, "Lightning", data)


def load_ath_cache() -> Optional[Dict[str, Any]]:
    return _load_market_metrics_cache(ATH_CACHE_FILE, "ATH")


def save_ath_cache(data: Dict[str, Any]) -> None:
    _save_market_metrics_cache(ATH_CACHE_FILE, "ATH", data)
