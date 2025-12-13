"""
News router package.

This package contains the news router and its supporting modules.
"""

from .debt_ceiling_data import DEBT_CEILING_HISTORY
from .news_cache import (
    BLOCK_HEIGHT_CACHE_FILE,
    BLOCK_HEIGHT_CACHE_MINUTES,
    CACHE_FILE,
    FEAR_GREED_CACHE_FILE,
    FEAR_GREED_CACHE_MINUTES,
    NEWS_CACHE_CHECK_MINUTES,
    NEWS_ITEM_MAX_AGE_DAYS,
    US_DEBT_CACHE_FILE,
    US_DEBT_CACHE_HOURS,
    VIDEO_CACHE_CHECK_MINUTES,
    VIDEO_CACHE_FILE,
    load_block_height_cache,
    load_cache,
    load_fear_greed_cache,
    load_us_debt_cache,
    load_video_cache,
    merge_news_items,
    prune_old_items,
    save_block_height_cache,
    save_cache,
    save_fear_greed_cache,
    save_us_debt_cache,
    save_video_cache,
)
from .news_models import (
    ArticleContentResponse,
    BlockHeightResponse,
    DebtCeilingEvent,
    DebtCeilingHistoryResponse,
    FearGreedResponse,
    NewsItem,
    NewsResponse,
    USDebtResponse,
    VideoItem,
    VideoResponse,
)
from .news_sources import NEWS_SOURCES, VIDEO_SOURCES

__all__ = [
    # Data
    "DEBT_CEILING_HISTORY",
    "NEWS_SOURCES",
    "VIDEO_SOURCES",
    # Cache paths
    "CACHE_FILE",
    "VIDEO_CACHE_FILE",
    "FEAR_GREED_CACHE_FILE",
    "BLOCK_HEIGHT_CACHE_FILE",
    "US_DEBT_CACHE_FILE",
    # Cache constants
    "NEWS_CACHE_CHECK_MINUTES",
    "NEWS_ITEM_MAX_AGE_DAYS",
    "VIDEO_CACHE_CHECK_MINUTES",
    "FEAR_GREED_CACHE_MINUTES",
    "BLOCK_HEIGHT_CACHE_MINUTES",
    "US_DEBT_CACHE_HOURS",
    # Cache functions
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
    # Models
    "ArticleContentResponse",
    "BlockHeightResponse",
    "DebtCeilingEvent",
    "DebtCeilingHistoryResponse",
    "FearGreedResponse",
    "NewsItem",
    "NewsResponse",
    "USDebtResponse",
    "VideoItem",
    "VideoResponse",
]
