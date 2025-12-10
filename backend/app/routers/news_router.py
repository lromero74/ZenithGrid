"""
Crypto News Router

Fetches and caches crypto news from multiple sources.
Cache behavior:
- Checks for new content every 15 minutes
- Merges new items with existing cache (new items at top)
- Prunes items older than 7 days

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
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp
import feedparser
import trafilatura
from fastapi import APIRouter, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlparse

from app.database import async_session_maker
from app.models import ContentSource, NewsArticle
from app.routers.news import (
    CACHE_FILE,
    DEBT_CEILING_HISTORY,
    FEAR_GREED_CACHE_MINUTES,
    NEWS_CACHE_CHECK_MINUTES,
    NEWS_ITEM_MAX_AGE_DAYS,
    NEWS_SOURCES,
    US_DEBT_CACHE_HOURS,
    VIDEO_CACHE_FILE,
    VIDEO_SOURCES,
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
    load_block_height_cache,
    load_fear_greed_cache,
    load_us_debt_cache,
    load_video_cache,
    merge_news_items,
    prune_old_items,
    save_block_height_cache,
    save_fear_greed_cache,
    save_us_debt_cache,
    save_video_cache,
)
from app.services.news_image_cache import download_image_as_base64

logger = logging.getLogger(__name__)

# Track when we last refreshed news (in-memory for this process)
_last_news_refresh: Optional[datetime] = None

router = APIRouter(prefix="/api/news", tags=["news"])


# =============================================================================
# Database Functions for Content Sources
# =============================================================================


async def get_news_sources_from_db() -> Dict[str, Dict]:
    """Get news sources from database, formatted like NEWS_SOURCES dict."""
    async with async_session_maker() as db:
        result = await db.execute(
            select(ContentSource)
            .where(ContentSource.type == "news")
            .where(ContentSource.is_enabled.is_(True))
        )
        sources = result.scalars().all()

    return {
        s.source_key: {
            "name": s.name,
            "url": s.url,
            "type": "reddit" if "reddit" in s.source_key else "rss",
            "website": s.website,
        }
        for s in sources
    }


async def get_video_sources_from_db() -> Dict[str, Dict]:
    """Get video sources from database, formatted like VIDEO_SOURCES dict."""
    async with async_session_maker() as db:
        result = await db.execute(
            select(ContentSource)
            .where(ContentSource.type == "video")
            .where(ContentSource.is_enabled.is_(True))
        )
        sources = result.scalars().all()

    return {
        s.source_key: {
            "name": s.name,
            "channel_id": s.channel_id,
            "url": s.url,
            "website": s.website,
            "description": s.description or "",
        }
        for s in sources
    }


async def get_all_sources_from_db() -> Dict[str, List[Dict]]:
    """Get all sources from database for API responses."""
    async with async_session_maker() as db:
        result = await db.execute(
            select(ContentSource).where(ContentSource.is_enabled.is_(True))
        )
        sources = result.scalars().all()

    news_sources = []
    video_sources = []

    for s in sources:
        if s.type == "news":
            news_sources.append({
                "id": s.source_key,
                "name": s.name,
                "website": s.website,
                "type": "reddit" if "reddit" in s.source_key else "rss",
            })
        elif s.type == "video":
            video_sources.append({
                "id": s.source_key,
                "name": s.name,
                "website": s.website,
                "description": s.description,
            })

    return {"news": news_sources, "video": video_sources}


# =============================================================================
# Database Functions for News Articles
# =============================================================================


async def get_articles_from_db(db: AsyncSession, limit: int = 100) -> List[NewsArticle]:
    """Get recent news articles from database, sorted by published date."""
    cutoff = datetime.utcnow() - timedelta(days=NEWS_ITEM_MAX_AGE_DAYS)
    result = await db.execute(
        select(NewsArticle)
        .where(NewsArticle.published_at >= cutoff)
        .order_by(desc(NewsArticle.published_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def store_article_in_db(
    db: AsyncSession,
    item: NewsItem,
    image_data: Optional[str] = None
) -> Optional[NewsArticle]:
    """Store a news article in the database. Returns None if already exists."""
    # Check if article already exists by URL
    result = await db.execute(
        select(NewsArticle).where(NewsArticle.url == item.url)
    )
    existing = result.scalars().first()
    if existing:
        return None  # Already exists

    # Parse published date
    published_at = None
    if item.published:
        try:
            pub_str = item.published.rstrip("Z")
            published_at = datetime.fromisoformat(pub_str)
        except (ValueError, TypeError):
            pass

    article = NewsArticle(
        title=item.title,
        url=item.url,
        source=item.source,
        published_at=published_at,
        summary=item.summary,
        original_thumbnail_url=item.thumbnail,
        image_data=image_data,  # Base64 data URI
        fetched_at=datetime.utcnow(),
    )
    db.add(article)
    return article


async def cleanup_old_articles(db: AsyncSession, max_age_days: int = NEWS_ITEM_MAX_AGE_DAYS) -> int:
    """Delete articles older than max_age_days. Returns count deleted."""
    from sqlalchemy import delete
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    result = await db.execute(
        delete(NewsArticle).where(NewsArticle.fetched_at < cutoff)
    )
    await db.commit()
    deleted_count = result.rowcount
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} old news articles from database")
    return deleted_count


def article_to_news_item(article: NewsArticle, sources: Optional[Dict[str, Dict]] = None) -> Dict[str, Any]:
    """Convert a NewsArticle database object to a NewsItem dict for API response."""
    # Use provided sources for name mapping, fall back to hardcoded
    source_map = sources if sources else NEWS_SOURCES
    # Use base64 image data if available, otherwise fall back to original URL
    thumbnail = article.image_data or article.original_thumbnail_url
    return {
        "title": article.title,
        "url": article.url,
        "source": article.source,
        "source_name": source_map.get(article.source, {}).get("name", article.source),
        "published": article.published_at.isoformat() + "Z" if article.published_at else None,
        "summary": article.summary,
        "thumbnail": thumbnail,
    }


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
                                logger.info("Treasury data shows temporary debt decrease, using default rate")
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

                # Extract video ID from link (supports regular videos and Shorts)
                video_id = ""
                link = entry.get("link", "")
                if "watch?v=" in link:
                    video_id = link.split("watch?v=")[-1].split("&")[0]
                elif "/shorts/" in link:
                    # YouTube Shorts: https://www.youtube.com/shorts/VIDEO_ID
                    video_id = link.split("/shorts/")[-1].split("?")[0]

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
    """Fetch videos from all YouTube sources and merge with existing cache.

    Strategy:
    - Fetch fresh videos from all sources (from database)
    - Merge with existing cached videos (new items at top, dedupe by URL)
    - Prune videos older than 7 days
    - Save merged cache
    """
    fresh_items: List[VideoItem] = []

    # Get sources from database (fall back to hardcoded if DB is empty)
    db_sources = await get_video_sources_from_db()
    sources_to_use = db_sources if db_sources else VIDEO_SOURCES

    async with aiohttp.ClientSession() as session:
        tasks = []
        for source_id, config in sources_to_use.items():
            tasks.append(fetch_youtube_videos(session, source_id, config))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                fresh_items.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Video fetch task failed: {result}")

    # Convert to dicts for merge
    fresh_dicts = [item.model_dump() for item in fresh_items]

    # Load existing cache for merge (even if "expired")
    existing_cache = load_video_cache(for_merge=True)
    existing_items = existing_cache.get("videos", []) if existing_cache else []

    # Merge: add new items to existing, dedupe by URL
    merged_items = merge_news_items(existing_items, fresh_dicts)

    # Prune videos older than 7 days
    merged_items = prune_old_items(merged_items)

    # Build sources list for UI from sources used
    sources_list = [
        {"id": sid, "name": cfg["name"], "website": cfg["website"], "description": cfg.get("description", "")}
        for sid, cfg in sources_to_use.items()
    ]

    now = datetime.now()
    cache_data = {
        "videos": merged_items,
        "sources": sources_list,
        "cached_at": now.isoformat(),
        "cache_expires_at": (now + timedelta(minutes=NEWS_CACHE_CHECK_MINUTES)).isoformat(),
        "total_items": len(merged_items),
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


async def fetch_all_news() -> None:
    """Fetch news from all sources, cache images, and store in database.

    Strategy:
    - Fetch fresh items from all sources (from database)
    - Download and cache thumbnail images locally
    - Store new articles in database (deduped by URL)
    - Skip articles that already exist
    """
    global _last_news_refresh
    fresh_items: List[NewsItem] = []

    # Get sources from database (fall back to hardcoded if DB is empty)
    db_sources = await get_news_sources_from_db()
    sources_to_use = db_sources if db_sources else NEWS_SOURCES

    async with aiohttp.ClientSession() as session:
        # Fetch news from all sources
        tasks = []
        for source_id, config in sources_to_use.items():
            if config["type"] == "reddit":
                tasks.append(fetch_reddit_news(session, source_id, config))
            elif config["type"] == "rss":
                tasks.append(fetch_rss_news(session, source_id, config))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                fresh_items.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Task failed: {result}")

        # Download images as base64 and store articles in database
        new_articles_count = 0
        async with async_session_maker() as db:
            for item in fresh_items:
                # Download thumbnail as base64 data URI if present
                image_data = None
                if item.thumbnail:
                    image_data = await download_image_as_base64(session, item.thumbnail)

                # Store in database (returns None if already exists)
                article = await store_article_in_db(db, item, image_data)
                if article:
                    new_articles_count += 1

            await db.commit()

        if new_articles_count > 0:
            logger.info(f"Added {new_articles_count} new news articles to database")

    _last_news_refresh = datetime.utcnow()


async def get_news_from_db() -> Dict[str, Any]:
    """Get news articles from database and format for API response."""
    # Get sources from database for name mapping
    db_sources = await get_news_sources_from_db()
    sources_to_use = db_sources if db_sources else NEWS_SOURCES

    async with async_session_maker() as db:
        articles = await get_articles_from_db(db, limit=100)

    # Convert to API response format (pass sources for name mapping)
    news_items = [article_to_news_item(article, sources_to_use) for article in articles]

    # Build sources list for UI
    sources_list = [
        {"id": sid, "name": cfg["name"], "website": cfg["website"]}
        for sid, cfg in sources_to_use.items()
    ]

    now = datetime.utcnow()
    return {
        "news": news_items,
        "sources": sources_list,
        "cached_at": now.isoformat() + "Z",
        "cache_expires_at": (now + timedelta(minutes=NEWS_CACHE_CHECK_MINUTES)).isoformat() + "Z",
        "total_items": len(news_items),
    }


@router.get("/", response_model=NewsResponse)
async def get_news(force_refresh: bool = False):
    """
    Get crypto news from database cache.

    News is fetched from multiple sources and stored in the database.
    Checks for new content every 15 minutes, keeps articles for 7 days.
    Use force_refresh=true to bypass cache timing and fetch fresh data.
    """
    global _last_news_refresh

    # Determine if we need to refresh from sources
    needs_refresh = force_refresh
    if not needs_refresh and _last_news_refresh:
        cache_age = datetime.utcnow() - _last_news_refresh
        if cache_age > timedelta(minutes=NEWS_CACHE_CHECK_MINUTES):
            needs_refresh = True
            logger.info(f"News cache needs refresh (age: {cache_age})")
    elif not _last_news_refresh:
        # First request since server start - check if we have recent data
        needs_refresh = True

    # Fetch fresh news if needed
    if needs_refresh:
        logger.info("Fetching fresh news from all sources...")
        try:
            await fetch_all_news()
        except Exception as e:
            logger.error(f"Failed to fetch news: {e}")
            # Continue to serve from database even if fetch fails

    # Get news from database
    try:
        data = await get_news_from_db()
        if data["news"]:
            logger.info(f"Serving {len(data['news'])} news articles from database")
            return NewsResponse(**data)
    except Exception as e:
        logger.error(f"Failed to get news from database: {e}")

    # Fall back to old JSON cache if database is empty or fails
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r") as f:
                stale_cache = json.load(f)
            logger.warning("Serving from JSON cache (database empty or failed)")
            return NewsResponse(**stale_cache)
        except Exception:
            pass

    raise HTTPException(status_code=503, detail="No news available")


@router.get("/sources")
async def get_sources():
    """Get list of news sources with links (from database)"""
    # Get sources from database (fall back to hardcoded if DB is empty)
    db_sources = await get_news_sources_from_db()
    sources_to_use = db_sources if db_sources else NEWS_SOURCES
    return {
        "sources": [
            {"id": sid, "name": cfg["name"], "website": cfg["website"], "type": cfg["type"]}
            for sid, cfg in sources_to_use.items()
        ],
        "note": "TikTok is not included as it lacks a public API for content. "
                "These sources provide reliable crypto news via RSS feeds or public APIs."
    }


@router.get("/cache-stats")
async def get_cache_stats():
    """Get news cache statistics including database article count."""
    # Get article count and articles with images from database
    async with async_session_maker() as db:
        from sqlalchemy import func
        result = await db.execute(select(func.count(NewsArticle.id)))
        article_count = result.scalar() or 0

        # Count articles with embedded images
        result = await db.execute(
            select(func.count(NewsArticle.id)).where(NewsArticle.image_data.isnot(None))
        )
        articles_with_images = result.scalar() or 0

    return {
        "database": {
            "article_count": article_count,
            "articles_with_images": articles_with_images,
        },
        "last_refresh": _last_news_refresh.isoformat() + "Z" if _last_news_refresh else None,
        "cache_check_interval_minutes": NEWS_CACHE_CHECK_MINUTES,
        "max_age_days": NEWS_ITEM_MAX_AGE_DAYS,
    }


@router.post("/cleanup")
async def cleanup_cache():
    """Manually trigger cleanup of old news articles (older than 7 days)."""
    # Cleanup old articles from database (images are stored inline, so they're deleted with articles)
    async with async_session_maker() as db:
        articles_deleted = await cleanup_old_articles(db)

    return {
        "articles_deleted": articles_deleted,
        "message": f"Cleaned up {articles_deleted} articles older than {NEWS_ITEM_MAX_AGE_DAYS} days"
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
    """Get list of video sources (YouTube channels) with links (from database)"""
    # Get sources from database (fall back to hardcoded if DB is empty)
    db_sources = await get_video_sources_from_db()
    sources_to_use = db_sources if db_sources else VIDEO_SOURCES
    return {
        "sources": [
            {
                "id": sid,
                "name": cfg["name"],
                "website": cfg["website"],
                "description": cfg.get("description", ""),
            }
            for sid, cfg in sources_to_use.items()
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


@router.get("/debt-ceiling-history", response_model=DebtCeilingHistoryResponse)
async def get_debt_ceiling_history(limit: int = 100):
    """
    Get historical debt ceiling changes/suspensions.

    Returns debt ceiling legislation events from 1939 (first statutory limit) to present.
    Data is sourced from Congressional Research Service (RL31967) and Treasury records.

    Note: Debt ceiling changes require Congressional action and happen infrequently
    (typically every 1-2 years). This data is updated when new legislation passes.

    Query params:
    - limit: Number of events to return (default: 100, max: 100 to get all events)
    """
    # Clamp limit to reasonable range
    limit = max(1, min(limit, 100))

    events = DEBT_CEILING_HISTORY[:limit]

    return DebtCeilingHistoryResponse(
        events=[DebtCeilingEvent(**e) for e in events],
        total_events=len(DEBT_CEILING_HISTORY),
        last_updated="2025-11-29",  # Update this when adding new ceiling events
    )


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
    "bitcoinmagazine.com",
    "www.bitcoinmagazine.com",
    "beincrypto.com",
    "www.beincrypto.com",
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
