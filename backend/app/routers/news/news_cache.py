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

# Cache timing constants (background refresh service handles actual refresh timing)
NEWS_CACHE_CHECK_MINUTES = 30  # Fallback: check every 30 minutes if no background refresh
VIDEO_CACHE_CHECK_MINUTES = 60  # Videos refresh hourly (less frequent than news)
NEWS_ITEM_MAX_AGE_DAYS = 7  # Prune items older than this
FEAR_GREED_CACHE_MINUTES = 60  # Fear/greed updates daily, no need for frequent checks
BLOCK_HEIGHT_CACHE_MINUTES = 10  # Keep for halving countdown accuracy
US_DEBT_CACHE_HOURS = 24  # Update US debt once per day

# Export constants needed by fetchers
__all__ = [
    # File paths
    "CACHE_DIR",
    "CACHE_FILE",
    "VIDEO_CACHE_FILE",
    "FEAR_GREED_CACHE_FILE",
    "BLOCK_HEIGHT_CACHE_FILE",
    "US_DEBT_CACHE_FILE",
    # Timing constants
    "NEWS_CACHE_CHECK_MINUTES",
    "VIDEO_CACHE_CHECK_MINUTES",
    "NEWS_ITEM_MAX_AGE_DAYS",
    "FEAR_GREED_CACHE_MINUTES",
    "BLOCK_HEIGHT_CACHE_MINUTES",
    "US_DEBT_CACHE_HOURS",
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
