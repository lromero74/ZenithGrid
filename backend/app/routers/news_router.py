"""
Crypto News Router

Fetches and caches crypto news from multiple sources.
Cache refreshes once per day (24 hours).

Sources:
- Reddit r/cryptocurrency and r/bitcoin (JSON API)
- CoinDesk (RSS)
- CoinTelegraph (RSS)
- Decrypt (RSS)
- The Block (RSS)
- CryptoSlate (RSS)

Video Sources (YouTube RSS):
- Coin Bureau - Educational crypto content
- Benjamin Cowen - Technical analysis
- Altcoin Daily - Daily crypto news
- Bankless - Ethereum/DeFi focused
- The Defiant - DeFi news

Note: TikTok doesn't have a public API for content, so we focus on
established crypto news sources with RSS feeds or public APIs.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import feedparser
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/news", tags=["news"])

# Cache configuration
CACHE_FILE = Path(__file__).parent.parent.parent / "news_cache.json"
VIDEO_CACHE_FILE = Path(__file__).parent.parent.parent / "video_cache.json"
CACHE_DURATION_HOURS = 24

# News sources configuration
NEWS_SOURCES = {
    "reddit_crypto": {
        "name": "Reddit r/CryptoCurrency",
        "url": "https://www.reddit.com/r/CryptoCurrency/hot.json?limit=15",
        "type": "reddit",
        "website": "https://www.reddit.com/r/CryptoCurrency",
    },
    "reddit_bitcoin": {
        "name": "Reddit r/Bitcoin",
        "url": "https://www.reddit.com/r/Bitcoin/hot.json?limit=10",
        "type": "reddit",
        "website": "https://www.reddit.com/r/Bitcoin",
    },
    "coindesk": {
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "type": "rss",
        "website": "https://www.coindesk.com",
    },
    "cointelegraph": {
        "name": "CoinTelegraph",
        "url": "https://cointelegraph.com/rss",
        "type": "rss",
        "website": "https://cointelegraph.com",
    },
    "decrypt": {
        "name": "Decrypt",
        "url": "https://decrypt.co/feed",
        "type": "rss",
        "website": "https://decrypt.co",
    },
    "theblock": {
        "name": "The Block",
        "url": "https://www.theblock.co/rss.xml",
        "type": "rss",
        "website": "https://www.theblock.co",
    },
    "cryptoslate": {
        "name": "CryptoSlate",
        "url": "https://cryptoslate.com/feed/",
        "type": "rss",
        "website": "https://cryptoslate.com",
    },
}

# YouTube video sources - most reputable crypto channels
VIDEO_SOURCES = {
    "coin_bureau": {
        "name": "Coin Bureau",
        "channel_id": "UCqK_GSMbpiV8spgD3ZGloSw",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCqK_GSMbpiV8spgD3ZGloSw",
        "website": "https://www.youtube.com/@CoinBureau",
        "description": "Educational crypto content & analysis",
    },
    "benjamin_cowen": {
        "name": "Benjamin Cowen",
        "channel_id": "UCRvqjQPSeaWn-uEx-w0XOIg",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCRvqjQPSeaWn-uEx-w0XOIg",
        "website": "https://www.youtube.com/@intothecryptoverse",
        "description": "Technical analysis & market cycles",
    },
    "altcoin_daily": {
        "name": "Altcoin Daily",
        "channel_id": "UCbLhGKVY-bJPcawebgtNfbw",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCbLhGKVY-bJPcawebgtNfbw",
        "website": "https://www.youtube.com/@AltcoinDaily",
        "description": "Daily crypto news & updates",
    },
    "bankless": {
        "name": "Bankless",
        "channel_id": "UCAl9Ld79qaZxp9JzEOwd3aA",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCAl9Ld79qaZxp9JzEOwd3aA",
        "website": "https://www.youtube.com/@Bankless",
        "description": "Ethereum & DeFi ecosystem",
    },
    "the_defiant": {
        "name": "The Defiant",
        "channel_id": "UCL0J4MLEdLP0-UyLu0hCktg",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCL0J4MLEdLP0-UyLu0hCktg",
        "website": "https://www.youtube.com/@TheDefiant",
        "description": "DeFi news & interviews",
    },
    "crypto_banter": {
        "name": "Crypto Banter",
        "channel_id": "UCN9Nj4tjXbVTLYWN0EKly_Q",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCN9Nj4tjXbVTLYWN0EKly_Q",
        "website": "https://www.youtube.com/@CryptoBanter",
        "description": "Live crypto shows & trading",
    },
}


class NewsItem(BaseModel):
    """Individual news item"""
    title: str
    url: str
    source: str
    source_name: str
    published: Optional[str] = None
    summary: Optional[str] = None
    thumbnail: Optional[str] = None


class VideoItem(BaseModel):
    """Individual video item from YouTube"""
    title: str
    url: str
    video_id: str
    source: str
    source_name: str
    channel_name: str
    published: Optional[str] = None
    thumbnail: Optional[str] = None
    description: Optional[str] = None


class NewsResponse(BaseModel):
    """News API response"""
    news: List[NewsItem]
    sources: List[Dict[str, str]]
    cached_at: str
    cache_expires_at: str
    total_items: int


class VideoResponse(BaseModel):
    """Video API response"""
    videos: List[VideoItem]
    sources: List[Dict[str, str]]
    cached_at: str
    cache_expires_at: str
    total_items: int


def load_cache() -> Optional[Dict[str, Any]]:
    """Load news cache from file"""
    if not CACHE_FILE.exists():
        return None

    try:
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)

        # Check if cache is expired
        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        if datetime.now() - cached_at > timedelta(hours=CACHE_DURATION_HOURS):
            logger.info("News cache expired")
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


def load_video_cache() -> Optional[Dict[str, Any]]:
    """Load video cache from file"""
    if not VIDEO_CACHE_FILE.exists():
        return None

    try:
        with open(VIDEO_CACHE_FILE, "r") as f:
            cache = json.load(f)

        # Check if cache is expired
        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        if datetime.now() - cached_at > timedelta(hours=CACHE_DURATION_HOURS):
            logger.info("Video cache expired")
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


async def fetch_youtube_videos(session: aiohttp.ClientSession, source_id: str, config: Dict) -> List[VideoItem]:
    """Fetch videos from YouTube RSS feed"""
    items = []
    try:
        headers = {"User-Agent": "ZenithGrid/1.0"}
        async with session.get(config["url"], headers=headers, timeout=15) as response:
            if response.status != 200:
                logger.warning(f"YouTube RSS returned {response.status} for {source_id}")
                return items

            content = await response.text()
            feed = feedparser.parse(content)

            for entry in feed.entries[:8]:  # Get latest 8 videos per channel
                # Parse published date
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6]).isoformat()
                    except (ValueError, TypeError):
                        pass

                # Extract video ID from link
                video_id = ""
                link = entry.get("link", "")
                if "watch?v=" in link:
                    video_id = link.split("watch?v=")[-1].split("&")[0]

                # Get thumbnail (YouTube provides standard thumbnails)
                thumbnail = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg" if video_id else None

                # Get description/summary
                description = None
                if hasattr(entry, "media_group") and entry.media_group:
                    desc = entry.media_group.get("media_description", "")
                    if desc:
                        description = desc[:200] if len(desc) > 200 else desc
                elif hasattr(entry, "summary"):
                    description = entry.summary[:200] if len(entry.summary) > 200 else entry.summary

                items.append(VideoItem(
                    title=entry.get("title", ""),
                    url=link,
                    video_id=video_id,
                    source=source_id,
                    source_name=config["name"],
                    channel_name=config["name"],
                    published=published,
                    thumbnail=thumbnail,
                    description=description,
                ))
    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching videos from {source_id}")
    except Exception as e:
        logger.error(f"Error fetching videos from {source_id}: {e}")

    return items


async def fetch_all_videos() -> Dict[str, Any]:
    """Fetch videos from all YouTube sources"""
    all_items: List[VideoItem] = []

    async with aiohttp.ClientSession() as session:
        tasks = []
        for source_id, config in VIDEO_SOURCES.items():
            tasks.append(fetch_youtube_videos(session, source_id, config))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_items.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Video fetch task failed: {result}")

    # Sort by published date (most recent first)
    all_items.sort(
        key=lambda x: x.published or "1970-01-01",
        reverse=True
    )

    # Build sources list for UI
    sources_list = [
        {"id": sid, "name": cfg["name"], "website": cfg["website"], "description": cfg["description"]}
        for sid, cfg in VIDEO_SOURCES.items()
    ]

    now = datetime.now()
    cache_data = {
        "videos": [item.model_dump() for item in all_items],
        "sources": sources_list,
        "cached_at": now.isoformat(),
        "cache_expires_at": (now + timedelta(hours=CACHE_DURATION_HOURS)).isoformat(),
        "total_items": len(all_items),
    }

    # Save to cache
    save_video_cache(cache_data)

    return cache_data


async def fetch_reddit_news(session: aiohttp.ClientSession, source_id: str, config: Dict) -> List[NewsItem]:
    """Fetch news from Reddit JSON API"""
    items = []
    try:
        # Reddit requires a descriptive user-agent per their API rules
        headers = {
            "User-Agent": "ZenithGrid:v1.0 (by /u/zenithgrid_bot)",
            "Accept": "application/json",
        }
        async with session.get(config["url"], headers=headers, timeout=15) as response:
            if response.status != 200:
                logger.warning(f"Reddit API returned {response.status} for {source_id}")
                return items

            data = await response.json()
            posts = data.get("data", {}).get("children", [])

            for post in posts[:15]:
                post_data = post.get("data", {})
                if post_data.get("stickied"):
                    continue

                # Get thumbnail if available
                thumbnail = post_data.get("thumbnail")
                if thumbnail in ["self", "default", "nsfw", "spoiler", ""]:
                    thumbnail = None

                items.append(NewsItem(
                    title=post_data.get("title", ""),
                    url=f"https://reddit.com{post_data.get('permalink', '')}",
                    source=source_id,
                    source_name=config["name"],
                    published=datetime.fromtimestamp(post_data.get("created_utc", 0)).isoformat(),
                    summary=post_data.get("selftext", "")[:200] if post_data.get("selftext") else None,
                    thumbnail=thumbnail,
                ))
    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching {source_id}")
    except Exception as e:
        logger.error(f"Error fetching {source_id}: {e}")

    return items


async def fetch_rss_news(session: aiohttp.ClientSession, source_id: str, config: Dict) -> List[NewsItem]:
    """Fetch news from RSS feed"""
    items = []
    try:
        headers = {"User-Agent": "ZenithGrid/1.0"}
        async with session.get(config["url"], headers=headers, timeout=15) as response:
            if response.status != 200:
                logger.warning(f"RSS feed returned {response.status} for {source_id}")
                return items

            content = await response.text()
            feed = feedparser.parse(content)

            for entry in feed.entries[:10]:
                # Parse published date
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6]).isoformat()
                    except (ValueError, TypeError):
                        pass

                # Get summary
                summary = None
                if hasattr(entry, "summary"):
                    # Strip HTML tags (simple approach)
                    summary = entry.summary
                    if "<" in summary:
                        import re
                        summary = re.sub(r"<[^>]+>", "", summary)
                    summary = summary[:200] if len(summary) > 200 else summary

                # Get thumbnail
                thumbnail = None
                if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                    thumbnail = entry.media_thumbnail[0].get("url")
                elif hasattr(entry, "media_content") and entry.media_content:
                    thumbnail = entry.media_content[0].get("url")

                items.append(NewsItem(
                    title=entry.get("title", ""),
                    url=entry.get("link", ""),
                    source=source_id,
                    source_name=config["name"],
                    published=published,
                    summary=summary,
                    thumbnail=thumbnail,
                ))
    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching {source_id}")
    except Exception as e:
        logger.error(f"Error fetching {source_id}: {e}")

    return items


async def fetch_all_news() -> Dict[str, Any]:
    """Fetch news from all sources"""
    all_items: List[NewsItem] = []

    async with aiohttp.ClientSession() as session:
        tasks = []
        for source_id, config in NEWS_SOURCES.items():
            if config["type"] == "reddit":
                tasks.append(fetch_reddit_news(session, source_id, config))
            elif config["type"] == "rss":
                tasks.append(fetch_rss_news(session, source_id, config))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_items.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Task failed: {result}")

    # Sort by published date (most recent first)
    all_items.sort(
        key=lambda x: x.published or "1970-01-01",
        reverse=True
    )

    # Build sources list for UI
    sources_list = [
        {"id": sid, "name": cfg["name"], "website": cfg["website"]}
        for sid, cfg in NEWS_SOURCES.items()
    ]

    now = datetime.now()
    cache_data = {
        "news": [item.model_dump() for item in all_items],
        "sources": sources_list,
        "cached_at": now.isoformat(),
        "cache_expires_at": (now + timedelta(hours=CACHE_DURATION_HOURS)).isoformat(),
        "total_items": len(all_items),
    }

    # Save to cache
    save_cache(cache_data)

    return cache_data


@router.get("/", response_model=NewsResponse)
async def get_news(force_refresh: bool = False):
    """
    Get cached crypto news.

    News is fetched from multiple sources and cached for 24 hours.
    Use force_refresh=true to bypass cache and fetch fresh data.
    """
    # Try to load from cache first
    if not force_refresh:
        cache = load_cache()
        if cache:
            logger.info("Serving news from cache")
            return NewsResponse(**cache)

    # Fetch fresh news
    logger.info("Fetching fresh news from all sources...")
    try:
        data = await fetch_all_news()
        return NewsResponse(**data)
    except Exception as e:
        logger.error(f"Failed to fetch news: {e}")

        # Try to serve stale cache if available
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r") as f:
                    stale_cache = json.load(f)
                logger.warning("Serving stale cache due to fetch failure")
                return NewsResponse(**stale_cache)
            except Exception:
                pass

        raise HTTPException(status_code=503, detail="Unable to fetch news")


@router.get("/sources")
async def get_sources():
    """Get list of news sources with links"""
    return {
        "sources": [
            {"id": sid, "name": cfg["name"], "website": cfg["website"], "type": cfg["type"]}
            for sid, cfg in NEWS_SOURCES.items()
        ],
        "note": "TikTok is not included as it lacks a public API for content. "
                "These sources provide reliable crypto news via RSS feeds or public APIs."
    }


@router.get("/videos", response_model=VideoResponse)
async def get_videos(force_refresh: bool = False):
    """
    Get cached crypto video news from YouTube channels.

    Videos are fetched from reputable crypto YouTube channels and cached for 24 hours.
    Use force_refresh=true to bypass cache and fetch fresh data.
    """
    # Try to load from cache first
    if not force_refresh:
        cache = load_video_cache()
        if cache:
            logger.info("Serving videos from cache")
            return VideoResponse(**cache)

    # Fetch fresh videos
    logger.info("Fetching fresh videos from YouTube channels...")
    try:
        data = await fetch_all_videos()
        return VideoResponse(**data)
    except Exception as e:
        logger.error(f"Failed to fetch videos: {e}")

        # Try to serve stale cache if available
        if VIDEO_CACHE_FILE.exists():
            try:
                with open(VIDEO_CACHE_FILE, "r") as f:
                    stale_cache = json.load(f)
                logger.warning("Serving stale video cache due to fetch failure")
                return VideoResponse(**stale_cache)
            except Exception:
                pass

        raise HTTPException(status_code=503, detail="Unable to fetch videos")


@router.get("/video-sources")
async def get_video_sources():
    """Get list of video sources (YouTube channels) with links"""
    return {
        "sources": [
            {
                "id": sid,
                "name": cfg["name"],
                "website": cfg["website"],
                "description": cfg["description"],
            }
            for sid, cfg in VIDEO_SOURCES.items()
        ],
        "note": "These are reputable crypto YouTube channels providing educational content, "
                "market analysis, and news coverage."
    }
