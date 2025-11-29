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
import trafilatura
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/news", tags=["news"])

# Cache configuration
CACHE_FILE = Path(__file__).parent.parent.parent / "news_cache.json"
VIDEO_CACHE_FILE = Path(__file__).parent.parent.parent / "video_cache.json"
FEAR_GREED_CACHE_FILE = Path(__file__).parent.parent.parent / "fear_greed_cache.json"
BLOCK_HEIGHT_CACHE_FILE = Path(__file__).parent.parent.parent / "block_height_cache.json"
US_DEBT_CACHE_FILE = Path(__file__).parent.parent.parent / "us_debt_cache.json"
CACHE_DURATION_HOURS = 24
FEAR_GREED_CACHE_MINUTES = 15  # Update fear/greed every 15 minutes
BLOCK_HEIGHT_CACHE_MINUTES = 10  # Update block height every 10 minutes
US_DEBT_CACHE_HOURS = 24  # Update US debt once per day

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


class FearGreedData(BaseModel):
    """Fear & Greed Index data"""
    value: int  # 0-100
    value_classification: str  # "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
    timestamp: str
    time_until_update: Optional[str] = None


class FearGreedResponse(BaseModel):
    """Fear & Greed API response"""
    data: FearGreedData
    cached_at: str
    cache_expires_at: str


class BlockHeightResponse(BaseModel):
    """BTC block height API response"""
    height: int
    timestamp: str


class USDebtResponse(BaseModel):
    """US National Debt API response"""
    total_debt: float  # Total public debt in dollars
    debt_per_second: float  # Rate of change per second (for animation)
    gdp: float  # US GDP in dollars
    debt_to_gdp_ratio: float  # Debt as percentage of GDP
    record_date: str  # Date of the debt record
    cached_at: str
    cache_expires_at: str


class ArticleContentResponse(BaseModel):
    """Article content extraction response"""
    url: str
    title: Optional[str] = None
    content: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    success: bool
    error: Optional[str] = None


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


async def fetch_btc_block_height() -> Dict[str, Any]:
    """Fetch current BTC block height from blockchain.info API"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}
            async with session.get(
                "https://blockchain.info/q/getblockcount",
                headers=headers,
                timeout=10
            ) as response:
                if response.status != 200:
                    logger.warning(f"Blockchain.info API returned {response.status}")
                    raise HTTPException(status_code=503, detail="Block height API unavailable")

                height_text = await response.text()
                height = int(height_text.strip())

                now = datetime.now()
                cache_data = {
                    "height": height,
                    "timestamp": now.isoformat(),
                    "cached_at": now.isoformat(),
                }

                # Save to cache
                save_block_height_cache(cache_data)

                return cache_data
    except asyncio.TimeoutError:
        logger.warning("Timeout fetching BTC block height")
        raise HTTPException(status_code=503, detail="Block height API timeout")
    except ValueError as e:
        logger.error(f"Invalid block height response: {e}")
        raise HTTPException(status_code=503, detail="Invalid block height response")
    except Exception as e:
        logger.error(f"Error fetching BTC block height: {e}")
        raise HTTPException(status_code=503, detail=f"Block height API error: {str(e)}")


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


async def fetch_us_debt() -> Dict[str, Any]:
    """Fetch US National Debt from Treasury Fiscal Data API and GDP from FRED"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}

            # Get most recent debt data (last 2 records to calculate rate)
            debt_url = (
                "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
                "v2/accounting/od/debt_to_penny"
                "?sort=-record_date&page[size]=2"
            )

            # Fetch debt data
            async with session.get(debt_url, headers=headers, timeout=15) as response:
                if response.status != 200:
                    logger.warning(f"Treasury API returned {response.status}")
                    raise HTTPException(status_code=503, detail="Treasury API unavailable")

                data = await response.json()
                records = data.get("data", [])

                if len(records) < 1:
                    raise HTTPException(status_code=503, detail="No debt data available")

                # Get current debt
                latest = records[0]
                total_debt = float(latest.get("tot_pub_debt_out_amt", 0))
                record_date = latest.get("record_date", "")

                # Calculate rate of change per second
                # Default: ~$1T/year = ~$31,710/second (debt always grows long-term)
                default_rate = 31710.0
                debt_per_second = default_rate

                if len(records) >= 2:
                    prev = records[1]
                    prev_debt = float(prev.get("tot_pub_debt_out_amt", 0))
                    prev_date = prev.get("record_date", "")

                    if prev_date and record_date:
                        date1 = datetime.strptime(record_date, "%Y-%m-%d")
                        date2 = datetime.strptime(prev_date, "%Y-%m-%d")
                        days_diff = (date1 - date2).days

                        if days_diff > 0:
                            debt_change = total_debt - prev_debt
                            seconds_diff = days_diff * 24 * 60 * 60
                            calculated_rate = debt_change / seconds_diff
                            # Only use calculated rate if positive (debt normally grows)
                            # Negative rates can occur due to temporary accounting adjustments
                            if calculated_rate > 0:
                                debt_per_second = calculated_rate
                            else:
                                logger.info(f"Treasury data shows temporary debt decrease, using default rate")
                                debt_per_second = default_rate

            # Fetch GDP from FRED (Federal Reserve) - no API key needed for this endpoint
            gdp = 28_000_000_000_000.0  # Default ~$28T fallback
            try:
                gdp_url = (
                    "https://api.stlouisfed.org/fred/series/observations"
                    "?series_id=GDP&api_key=DEMO_KEY&file_type=json"
                    "&sort_order=desc&limit=1"
                )
                async with session.get(gdp_url, headers=headers, timeout=10) as gdp_response:
                    if gdp_response.status == 200:
                        gdp_data = await gdp_response.json()
                        observations = gdp_data.get("observations", [])
                        if observations:
                            # FRED GDP is in billions, convert to dollars
                            gdp_billions = float(observations[0].get("value", 28000))
                            gdp = gdp_billions * 1_000_000_000
                    else:
                        logger.warning(f"FRED GDP API returned {gdp_response.status}, using fallback")
            except Exception as e:
                logger.warning(f"Failed to fetch GDP: {e}, using fallback")

            # Calculate debt-to-GDP ratio
            debt_to_gdp_ratio = (total_debt / gdp * 100) if gdp > 0 else 0

            now = datetime.now()
            cache_data = {
                "total_debt": total_debt,
                "debt_per_second": debt_per_second,
                "gdp": gdp,
                "debt_to_gdp_ratio": round(debt_to_gdp_ratio, 2),
                "record_date": record_date,
                "cached_at": now.isoformat(),
                "cache_expires_at": (now + timedelta(hours=US_DEBT_CACHE_HOURS)).isoformat(),
            }

            # Save to cache
            save_us_debt_cache(cache_data)

            return cache_data
    except asyncio.TimeoutError:
        logger.warning("Timeout fetching US debt")
        raise HTTPException(status_code=503, detail="Treasury API timeout")
    except Exception as e:
        logger.error(f"Error fetching US debt: {e}")
        raise HTTPException(status_code=503, detail=f"Treasury API error: {str(e)}")


async def fetch_fear_greed_index() -> Dict[str, Any]:
    """Fetch Fear & Greed Index from Alternative.me API"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}
            async with session.get(
                "https://api.alternative.me/fng/",
                headers=headers,
                timeout=10
            ) as response:
                if response.status != 200:
                    logger.warning(f"Fear/Greed API returned {response.status}")
                    raise HTTPException(status_code=503, detail="Fear/Greed API unavailable")

                data = await response.json()
                fng_data = data.get("data", [{}])[0]

                now = datetime.now()
                cache_data = {
                    "data": {
                        "value": int(fng_data.get("value", 50)),
                        "value_classification": fng_data.get("value_classification", "Neutral"),
                        "timestamp": datetime.fromtimestamp(int(fng_data.get("timestamp", 0))).isoformat(),
                        "time_until_update": fng_data.get("time_until_update"),
                    },
                    "cached_at": now.isoformat(),
                    "cache_expires_at": (now + timedelta(minutes=FEAR_GREED_CACHE_MINUTES)).isoformat(),
                }

                # Save to cache
                save_fear_greed_cache(cache_data)

                return cache_data
    except asyncio.TimeoutError:
        logger.warning("Timeout fetching Fear/Greed index")
        raise HTTPException(status_code=503, detail="Fear/Greed API timeout")
    except Exception as e:
        logger.error(f"Error fetching Fear/Greed index: {e}")
        raise HTTPException(status_code=503, detail=f"Fear/Greed API error: {str(e)}")


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
                        # Add Z suffix to indicate UTC timezone
                        published = datetime(*entry.published_parsed[:6]).isoformat() + "Z"
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
                    # Add Z suffix to indicate UTC timezone (created_utc is Unix UTC timestamp)
                    published=datetime.utcfromtimestamp(post_data.get("created_utc", 0)).isoformat() + "Z",
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
                        # Add Z suffix to indicate UTC timezone
                        published = datetime(*entry.published_parsed[:6]).isoformat() + "Z"
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


@router.get("/fear-greed", response_model=FearGreedResponse)
async def get_fear_greed():
    """
    Get the Crypto Fear & Greed Index.

    The index ranges from 0 (Extreme Fear) to 100 (Extreme Greed).
    Data is cached for 15 minutes.

    Source: Alternative.me Crypto Fear & Greed Index
    """
    # Try to load from cache first
    cache = load_fear_greed_cache()
    if cache:
        logger.info("Serving Fear/Greed from cache")
        return FearGreedResponse(**cache)

    # Fetch fresh data
    logger.info("Fetching fresh Fear/Greed index...")
    data = await fetch_fear_greed_index()
    return FearGreedResponse(**data)


@router.get("/btc-block-height", response_model=BlockHeightResponse)
async def get_btc_block_height():
    """
    Get the current Bitcoin block height.

    Used for BTC halving countdown calculations.
    Data is cached for 10 minutes.

    Source: blockchain.info
    """
    # Try to load from cache first
    cache = load_block_height_cache()
    if cache:
        logger.info("Serving BTC block height from cache")
        return BlockHeightResponse(**cache)

    # Fetch fresh data
    logger.info("Fetching fresh BTC block height...")
    data = await fetch_btc_block_height()
    return BlockHeightResponse(**data)


@router.get("/us-debt", response_model=USDebtResponse)
async def get_us_debt():
    """
    Get the current US National Debt with rate of change.

    Returns total debt, debt per second (for animation), GDP, and debt-to-GDP ratio.
    Data is cached for 24 hours.

    Sources:
    - Treasury Fiscal Data API (debt)
    - FRED Federal Reserve API (GDP)
    """
    # Try to load from cache first
    cache = load_us_debt_cache()
    if cache:
        logger.info("Serving US debt from cache")
        return USDebtResponse(**cache)

    # Fetch fresh data
    logger.info("Fetching fresh US debt data...")
    data = await fetch_us_debt()
    return USDebtResponse(**data)


# Allowed domains for article content extraction (security measure)
ALLOWED_ARTICLE_DOMAINS = {
    "coindesk.com",
    "www.coindesk.com",
    "cointelegraph.com",
    "www.cointelegraph.com",
    "decrypt.co",
    "www.decrypt.co",
    "theblock.co",
    "www.theblock.co",
    "cryptoslate.com",
    "www.cryptoslate.com",
    "reddit.com",
    "www.reddit.com",
    "old.reddit.com",
}


@router.get("/article-content", response_model=ArticleContentResponse)
async def get_article_content(url: str):
    """
    Extract article content from a news URL.

    Uses trafilatura to extract the main article text, title, and metadata.
    Only allows fetching from trusted crypto news domains for security.

    Returns clean, readable article content like browser reader mode.
    """
    # Validate URL
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return ArticleContentResponse(
                url=url,
                success=False,
                error="Invalid URL format"
            )

        # Security check: only allow known news domains
        domain = parsed.netloc.lower()
        if domain not in ALLOWED_ARTICLE_DOMAINS:
            logger.warning(f"Attempted to fetch article from non-allowed domain: {domain}")
            return ArticleContentResponse(
                url=url,
                success=False,
                error=f"Domain not allowed. Supported: {', '.join(sorted(ALLOWED_ARTICLE_DOMAINS))}"
            )
    except Exception as e:
        return ArticleContentResponse(
            url=url,
            success=False,
            error=f"URL validation failed: {str(e)}"
        )

    try:
        # Fetch the page content with browser-like headers to avoid 403 blocks
        async with aiohttp.ClientSession() as session:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"macOS"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }
            async with session.get(url, headers=headers, timeout=15, allow_redirects=True) as response:
                if response.status != 200:
                    return ArticleContentResponse(
                        url=url,
                        success=False,
                        error=f"Failed to fetch article: HTTP {response.status}"
                    )

                html_content = await response.text()

        # Extract article content using trafilatura
        # Run in executor since trafilatura is synchronous
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            extracted = await asyncio.get_event_loop().run_in_executor(
                executor,
                lambda: trafilatura.extract(
                    html_content,
                    include_comments=False,
                    include_tables=True,  # Include tables for structure
                    no_fallback=False,
                    favor_precision=True,
                    output_format="markdown"  # Use markdown to preserve headings, lists, etc.
                )
            )

            # Also extract metadata
            metadata = await asyncio.get_event_loop().run_in_executor(
                executor,
                lambda: trafilatura.extract_metadata(html_content)
            )

        if not extracted:
            return ArticleContentResponse(
                url=url,
                success=False,
                error="Could not extract article content. The page may be paywalled or use dynamic loading."
            )

        # Build response with metadata if available
        title = None
        author = None
        date = None

        if metadata:
            title = metadata.title
            author = metadata.author
            if metadata.date:
                date = metadata.date

        logger.info(f"Successfully extracted article from {domain}: {len(extracted)} chars")

        return ArticleContentResponse(
            url=url,
            title=title,
            content=extracted,
            author=author,
            date=date,
            success=True
        )

    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching article: {url}")
        return ArticleContentResponse(
            url=url,
            success=False,
            error="Request timed out. The website may be slow or unavailable."
        )
    except Exception as e:
        logger.error(f"Error extracting article content: {e}")
        return ArticleContentResponse(
            url=url,
            success=False,
            error=f"Failed to extract content: {str(e)}"
        )
