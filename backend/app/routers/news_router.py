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
import edge_tts
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlparse

from app.database import async_session_maker
from app.indicator_calculator import IndicatorCalculator
from app.models import ContentSource, MetricSnapshot, NewsArticle, VideoArticle
from app.routers.news import (
    CACHE_FILE,
    DEBT_CEILING_HISTORY,
    FEAR_GREED_CACHE_MINUTES,
    NEWS_CACHE_CHECK_MINUTES,
    NEWS_CATEGORIES,
    NEWS_ITEM_MAX_AGE_DAYS,
    VIDEO_CACHE_CHECK_MINUTES,
    NEWS_SOURCES,
    US_DEBT_CACHE_HOURS,
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
    load_btc_dominance_cache,
    load_altseason_cache,
    load_funding_rates_cache,
    load_stablecoin_mcap_cache,
    load_mempool_cache,
    load_hash_rate_cache,
    load_lightning_cache,
    load_ath_cache,
    load_btc_rsi_cache,
    merge_news_items,
    prune_old_items,
    save_block_height_cache,
    save_fear_greed_cache,
    save_us_debt_cache,
    save_video_cache,
    save_btc_dominance_cache,
    save_altseason_cache,
    save_funding_rates_cache,
    save_stablecoin_mcap_cache,
    save_mempool_cache,
    save_hash_rate_cache,
    save_lightning_cache,
    save_ath_cache,
    save_btc_rsi_cache,
)
from app.services.news_image_cache import download_image_as_base64

logger = logging.getLogger(__name__)

# Track when we last refreshed news/videos (in-memory for this process)
_last_news_refresh: Optional[datetime] = None
_last_video_refresh: Optional[datetime] = None

router = APIRouter(prefix="/api/news", tags=["news"])

METRIC_SNAPSHOT_PRUNE_DAYS = 90


async def record_metric_snapshot(metric_name: str, value: float) -> None:
    """Record a metric value for sparkline history. Non-blocking, errors are logged."""
    try:
        async with async_session_maker() as db:
            db.add(MetricSnapshot(
                metric_name=metric_name,
                value=value,
                recorded_at=datetime.utcnow(),
            ))
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to record metric snapshot {metric_name}: {e}")


async def prune_old_snapshots() -> None:
    """Delete metric snapshots older than 90 days."""
    try:
        cutoff = datetime.utcnow() - timedelta(days=METRIC_SNAPSHOT_PRUNE_DAYS)
        async with async_session_maker() as db:
            from sqlalchemy import delete
            await db.execute(
                delete(MetricSnapshot).where(MetricSnapshot.recorded_at < cutoff)
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to prune old snapshots: {e}")


# =============================================================================
# Database Functions for Content Sources
# =============================================================================


async def get_allowed_article_domains() -> set[str]:
    """
    Get allowed domains for article content extraction from database.
    Extracts domains from website URLs of all enabled content sources.
    """
    async with async_session_maker() as db:
        result = await db.execute(
            select(ContentSource.website)
            .where(ContentSource.is_enabled.is_(True))
            .where(ContentSource.website.isnot(None))
        )
        websites = result.scalars().all()

    allowed = set()
    for website in websites:
        try:
            parsed = urlparse(website)
            domain = parsed.netloc.lower()
            if domain:
                allowed.add(domain)
                # Also add www. variant if not present, or non-www if www present
                if domain.startswith("www."):
                    allowed.add(domain[4:])
                else:
                    allowed.add(f"www.{domain}")
        except Exception:
            pass

    return allowed


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
            "category": getattr(s, 'category', 'CryptoCurrency'),
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
            "category": getattr(s, 'category', 'CryptoCurrency'),
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


async def get_articles_from_db(
    db: AsyncSession, page: int = 1, page_size: int = 50, category: Optional[str] = None
) -> tuple[List[NewsArticle], int]:
    """Get paginated news articles from database, sorted by published date.

    Args:
        db: Database session
        page: Page number (1-indexed)
        page_size: Number of items per page
        category: Optional category filter (e.g., "CryptoCurrency", "Technology")

    Returns:
        Tuple of (articles list, total count)
    """
    from sqlalchemy import func

    cutoff = datetime.utcnow() - timedelta(days=NEWS_ITEM_MAX_AGE_DAYS)

    # Build base query conditions
    conditions = [NewsArticle.published_at >= cutoff]
    if category:
        conditions.append(NewsArticle.category == category)

    # Get total count
    count_query = select(func.count(NewsArticle.id))
    for condition in conditions:
        count_query = count_query.where(condition)
    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0

    # Get paginated results
    offset = (page - 1) * page_size
    query = select(NewsArticle)
    for condition in conditions:
        query = query.where(condition)
    query = query.order_by(desc(NewsArticle.published_at)).offset(offset).limit(page_size)
    result = await db.execute(query)
    return list(result.scalars().all()), total_count


async def store_article_in_db(
    db: AsyncSession,
    item: NewsItem,
    image_data: Optional[str] = None,
    category: str = "CryptoCurrency"
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
        category=category,
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
    # Use image proxy URL if we have cached image, otherwise fall back to original URL
    # This keeps response small while serving cached images with proper cache headers
    if article.image_data:
        thumbnail = f"/api/news/image/{article.id}"
    else:
        thumbnail = article.original_thumbnail_url
    return {
        "title": article.title,
        "url": article.url,
        "source": article.source,
        "source_name": source_map.get(article.source, {}).get("name", article.source),
        "published": article.published_at.isoformat() + "Z" if article.published_at else None,
        "summary": article.summary,
        "thumbnail": thumbnail,
        "category": getattr(article, 'category', 'CryptoCurrency'),
    }


# ============================================================================
# VIDEO DATABASE FUNCTIONS
# ============================================================================


async def store_video_in_db(
    db: AsyncSession,
    item: VideoItem,
    category: str = "CryptoCurrency"
) -> Optional[VideoArticle]:
    """Store a video article in the database. Returns None if already exists."""
    # Check if video already exists by URL
    result = await db.execute(
        select(VideoArticle).where(VideoArticle.url == item.url)
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

    video = VideoArticle(
        title=item.title,
        url=item.url,
        video_id=item.video_id,
        source=item.source,
        channel_name=item.channel_name,
        published_at=published_at,
        description=item.description,
        thumbnail_url=item.thumbnail,
        category=category,
        fetched_at=datetime.utcnow(),
    )
    db.add(video)
    return video


async def get_videos_from_db_list(db: AsyncSession, category: Optional[str] = None) -> List[VideoArticle]:
    """Get all recent videos from database within max age, sorted by published date.

    Args:
        db: Database session
        category: Optional category filter (e.g., "CryptoCurrency")
    """
    cutoff = datetime.utcnow() - timedelta(days=NEWS_ITEM_MAX_AGE_DAYS)
    conditions = [VideoArticle.published_at >= cutoff]
    if category:
        conditions.append(VideoArticle.category == category)

    query = select(VideoArticle)
    for condition in conditions:
        query = query.where(condition)
    query = query.order_by(desc(VideoArticle.published_at))

    result = await db.execute(query)
    return list(result.scalars().all())


async def cleanup_old_videos(db: AsyncSession, max_age_days: int = NEWS_ITEM_MAX_AGE_DAYS) -> int:
    """Delete videos older than max_age_days. Returns count deleted."""
    from sqlalchemy import delete
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    result = await db.execute(
        delete(VideoArticle).where(VideoArticle.fetched_at < cutoff)
    )
    await db.commit()
    deleted_count = result.rowcount
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} old videos from database")
    return deleted_count


def video_to_item(video: VideoArticle, sources: Optional[Dict[str, Dict]] = None) -> Dict[str, Any]:
    """Convert a VideoArticle database object to a VideoItem dict for API response."""
    source_map = sources if sources else VIDEO_SOURCES
    return {
        "title": video.title,
        "url": video.url,
        "video_id": video.video_id,
        "source": video.source,
        "source_name": source_map.get(video.source, {}).get("name", video.source),
        "channel_name": video.channel_name,
        "published": video.published_at.isoformat() + "Z" if video.published_at else None,
        "thumbnail": video.thumbnail_url,
        "description": video.description,
        "category": getattr(video, 'category', 'CryptoCurrency'),
    }


async def get_videos_from_db(category: Optional[str] = None) -> Dict[str, Any]:
    """Get videos from database and format for API response.

    Args:
        category: Optional category filter (e.g., "CryptoCurrency")
    """
    # Get sources from database for name mapping
    db_sources = await get_video_sources_from_db()
    sources_to_use = db_sources if db_sources else VIDEO_SOURCES

    async with async_session_maker() as db:
        videos = await get_videos_from_db_list(db, category=category)

    # Convert to API response format
    video_items = [video_to_item(video, sources_to_use) for video in videos]

    # Build sources list for UI
    sources_list = [
        {"id": sid, "name": cfg["name"], "website": cfg["website"], "description": cfg.get("description", "")}
        for sid, cfg in sources_to_use.items()
    ]

    now = datetime.utcnow()
    return {
        "videos": video_items,
        "sources": sources_list,
        "cached_at": now.isoformat() + "Z",
        "cache_expires_at": (now + timedelta(minutes=VIDEO_CACHE_CHECK_MINUTES)).isoformat() + "Z",
        "total_items": len(video_items),
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

            # Get last 8 records to calculate 7-day weighted average rate
            debt_url = (
                "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
                "v2/accounting/od/debt_to_penny"
                "?sort=-record_date&page[size]=8"
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

                # Calculate rate of change per second using 7-day weighted average
                # Default: ~$1T/year = ~$31,710/second (debt always grows long-term)
                default_rate = 31710.0
                debt_per_second = default_rate

                # Calculate daily rates and apply weighted average
                # Weights: oldest days (1-4) get weight 1, recent days (5-6) get weight 2, most recent (7) gets weight 3
                # This gives preference to last 3 days while still smoothing with older data
                if len(records) >= 2:
                    daily_rates = []
                    for i in range(len(records) - 1):
                        curr = records[i]
                        prev = records[i + 1]
                        curr_debt = float(curr.get("tot_pub_debt_out_amt", 0))
                        prev_debt = float(prev.get("tot_pub_debt_out_amt", 0))
                        curr_date = curr.get("record_date", "")
                        prev_date = prev.get("record_date", "")

                        if prev_date and curr_date:
                            date1 = datetime.strptime(curr_date, "%Y-%m-%d")
                            date2 = datetime.strptime(prev_date, "%Y-%m-%d")
                            days_diff = (date1 - date2).days

                            if days_diff > 0:
                                debt_change = curr_debt - prev_debt
                                seconds_diff = days_diff * 24 * 60 * 60
                                rate = debt_change / seconds_diff
                                # Only include positive rates (debt normally grows)
                                if rate > 0:
                                    daily_rates.append(rate)

                    if daily_rates:
                        # Apply weights: most recent gets highest weight
                        # For 7 rates: weights are [1, 1, 1, 1, 2, 2, 3] (oldest to newest)
                        # For fewer rates, use available with proportional weighting
                        num_rates = len(daily_rates)
                        weights = []
                        for i in range(num_rates):
                            # Position 0 is most recent, position num_rates-1 is oldest
                            if i < 1:  # Most recent day
                                weights.append(3)
                            elif i < 3:  # Next 2 days
                                weights.append(2)
                            else:  # Older days
                                weights.append(1)

                        # Calculate weighted average
                        weighted_sum = sum(r * w for r, w in zip(daily_rates, weights))
                        total_weight = sum(weights)
                        debt_per_second = weighted_sum / total_weight
                        logger.info(f"Calculated debt rate from {num_rates} days: ${debt_per_second:.2f}/sec (weighted avg)")
                    else:
                        logger.info("No positive debt rates found, using default rate")
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

            # Get current debt ceiling from history (most recent non-suspended entry)
            debt_ceiling = None
            debt_ceiling_suspended = False
            debt_ceiling_note = None
            headroom = None

            if DEBT_CEILING_HISTORY:
                latest_ceiling = DEBT_CEILING_HISTORY[0]
                debt_ceiling_suspended = latest_ceiling.get("suspended", False)
                debt_ceiling_note = latest_ceiling.get("note", "")

                if debt_ceiling_suspended:
                    suspension_end = latest_ceiling.get("suspension_end")
                    if suspension_end:
                        debt_ceiling_note = f"Suspended until {suspension_end}"
                else:
                    amount_trillion = latest_ceiling.get("amount_trillion")
                    if amount_trillion:
                        debt_ceiling = amount_trillion * 1_000_000_000_000  # Convert to dollars
                        headroom = debt_ceiling - total_debt

            now = datetime.now()
            cache_data = {
                "total_debt": total_debt,
                "debt_per_second": debt_per_second,
                "gdp": gdp,
                "debt_to_gdp_ratio": round(debt_to_gdp_ratio, 2),
                "record_date": record_date,
                "cached_at": now.isoformat(),
                "cache_expires_at": (now + timedelta(hours=US_DEBT_CACHE_HOURS)).isoformat(),
                "debt_ceiling": debt_ceiling,
                "debt_ceiling_suspended": debt_ceiling_suspended,
                "debt_ceiling_note": debt_ceiling_note,
                "headroom": headroom,
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
                asyncio.create_task(record_metric_snapshot("fear_greed", cache_data["data"]["value"]))

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
                    category=config.get("category", "CryptoCurrency"),
                ))
    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching videos from {source_id}")
    except Exception as e:
        logger.error(f"Error fetching videos from {source_id}: {e}")

    return items


async def fetch_all_videos() -> Dict[str, Any]:
    """Fetch videos from all YouTube sources and store in database.

    Strategy:
    - Fetch fresh videos from all sources (from database config)
    - Store new videos in database (deduplication by URL)
    - Clean up old videos (older than 7 days)
    - Also save to JSON cache for backward compatibility
    """
    global _last_video_refresh
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

    # Store new videos in database
    new_count = 0
    async with async_session_maker() as db:
        for item in fresh_items:
            video = await store_video_in_db(db, item, category=item.category)
            if video:
                new_count += 1
        await db.commit()

        # Clean up old videos
        await cleanup_old_videos(db)

    if new_count > 0:
        logger.info(f"Stored {new_count} new videos in database")

    # Also save to JSON cache for backward compatibility during migration
    fresh_dicts = [item.model_dump() for item in fresh_items]
    existing_cache = load_video_cache(for_merge=True)
    existing_items = existing_cache.get("videos", []) if existing_cache else []
    merged_items = merge_news_items(existing_items, fresh_dicts)
    merged_items = prune_old_items(merged_items)

    sources_list = [
        {"id": sid, "name": cfg["name"], "website": cfg["website"], "description": cfg.get("description", "")}
        for sid, cfg in sources_to_use.items()
    ]

    now = datetime.utcnow()
    cache_data = {
        "videos": merged_items,
        "sources": sources_list,
        "cached_at": now.isoformat(),
        "cache_expires_at": (now + timedelta(minutes=VIDEO_CACHE_CHECK_MINUTES)).isoformat(),
        "total_items": len(merged_items),
    }
    save_video_cache(cache_data)

    _last_video_refresh = datetime.utcnow()
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
                    category=config.get("category", "CryptoCurrency"),
                ))
    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching {source_id}")
    except Exception as e:
        logger.error(f"Error fetching {source_id}: {e}")

    return items


async def fetch_og_image(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    """Fetch og:image meta tag from an article URL."""
    import html as html_module
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ZenithGrid/1.0)",
            "Accept": "text/html",
        }
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status != 200:
                return None
            html_content = await response.text()
            # Extract og:image meta tag
            import re
            match = re.search(
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                html_content,
                re.IGNORECASE
            )
            if not match:
                # Try alternate format: content before property
                match = re.search(
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                    html_content,
                    re.IGNORECASE
                )
            if match:
                # Decode HTML entities (e.g., &amp; -> &)
                return html_module.unescape(match.group(1))
            return None
    except Exception:
        return None


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
                elif hasattr(entry, "enclosures") and entry.enclosures:
                    # Some feeds use enclosures for images
                    for enc in entry.enclosures:
                        if enc.get("type", "").startswith("image/"):
                            thumbnail = enc.get("url")
                            break

                # Fallback: extract first img src from description/content HTML
                if not thumbnail:
                    import re
                    content_html = entry.get("content", [{}])[0].get("value", "") if entry.get("content") else ""
                    description_html = entry.get("description", "") or entry.get("summary", "")
                    for html in [content_html, description_html]:
                        if html:
                            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
                            if img_match:
                                thumbnail = img_match.group(1)
                                break

                items.append(NewsItem(
                    title=entry.get("title", ""),
                    url=entry.get("link", ""),
                    source=source_id,
                    source_name=config["name"],
                    published=published,
                    summary=summary,
                    thumbnail=thumbnail,
                    category=config.get("category", "CryptoCurrency"),
                ))

            # Fetch og:image for items without thumbnails (e.g., Blockworks)
            items_needing_og = [(i, item) for i, item in enumerate(items) if not item.thumbnail and item.url]
            if items_needing_og:
                logger.info(f"Fetching og:image for {len(items_needing_og)} {source_id} articles without thumbnails")
                og_tasks = [fetch_og_image(session, item.url) for _, item in items_needing_og]
                og_results = await asyncio.gather(*og_tasks, return_exceptions=True)
                for (idx, item), og_url in zip(items_needing_og, og_results):
                    if isinstance(og_url, str) and og_url:
                        items[idx] = NewsItem(
                            title=item.title,
                            url=item.url,
                            source=item.source,
                            source_name=item.source_name,
                            published=item.published,
                            summary=item.summary,
                            thumbnail=og_url,
                            category=item.category,
                        )

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
                article = await store_article_in_db(db, item, image_data, category=item.category)
                if article:
                    new_articles_count += 1

            await db.commit()

        if new_articles_count > 0:
            logger.info(f"Added {new_articles_count} new news articles to database")

    _last_news_refresh = datetime.utcnow()


async def get_news_from_db(page: int = 1, page_size: int = 50, category: Optional[str] = None) -> Dict[str, Any]:
    """Get paginated news articles from database and format for API response.

    Args:
        page: Page number (1-indexed)
        page_size: Number of items per page
        category: Optional category filter (e.g., "CryptoCurrency", "Technology")
    """
    import math

    # Get sources from database for name mapping
    db_sources = await get_news_sources_from_db()
    sources_to_use = db_sources if db_sources else NEWS_SOURCES

    async with async_session_maker() as db:
        articles, total_count = await get_articles_from_db(db, page=page, page_size=page_size, category=category)

    # Convert to API response format (pass sources for name mapping)
    news_items = [article_to_news_item(article, sources_to_use) for article in articles]

    # Build sources list for UI
    sources_list = [
        {"id": sid, "name": cfg["name"], "website": cfg["website"]}
        for sid, cfg in sources_to_use.items()
    ]

    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

    now = datetime.utcnow()
    return {
        "news": news_items,
        "sources": sources_list,
        "cached_at": now.isoformat() + "Z",
        "cache_expires_at": (now + timedelta(minutes=NEWS_CACHE_CHECK_MINUTES)).isoformat() + "Z",
        "total_items": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/", response_model=NewsResponse)
async def get_news(
    force_refresh: bool = False,
    page: int = 1,
    page_size: int = 50,
    category: Optional[str] = Query(None, description="Filter by category (e.g., CryptoCurrency, Technology)")
):
    """
    Get news from database cache with pagination.

    News is fetched from multiple sources by background service and stored in database.
    Returns immediately from database. Background refresh runs every 30 minutes.
    Use force_refresh=true to trigger immediate refresh (runs in background).

    Query params:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 50, max: 100)
    - category: Filter by category (e.g., CryptoCurrency, World, Technology)
    """
    global _last_news_refresh

    # Clamp page_size minimum (no upper cap - we already prune old articles)
    page_size = max(10, page_size)
    page = max(1, page)

    # If force refresh requested, trigger background fetch
    if force_refresh:
        logger.info("Force refresh requested - triggering news fetch...")
        asyncio.create_task(fetch_all_news())

    # Try to serve from database first (fast path)
    try:
        data = await get_news_from_db(page=page, page_size=page_size, category=category)
        if data["news"] or data["total_items"] > 0:
            logger.debug(f"Serving page {page} with {len(data['news'])} news articles from database")
            return NewsResponse(**data)
    except Exception as e:
        logger.error(f"Failed to get news from database: {e}")

    # Fall back to JSON cache if database is empty
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r") as f:
                stale_cache = json.load(f)
            logger.info("Serving from JSON cache (database empty)")
            return NewsResponse(**stale_cache)
        except Exception:
            pass

    # No data available yet - trigger initial fetch if not already running
    if not _last_news_refresh:
        logger.info("No news cache available - triggering initial fetch...")
        asyncio.create_task(fetch_all_news())

    raise HTTPException(status_code=503, detail="News not yet available - please try again shortly")


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


@router.get("/categories")
async def get_categories():
    """Get list of available news categories.

    Categories:
    - CryptoCurrency: Crypto-specific news (default)
    - World: International news
    - Nation: US national news
    - Business: Business and finance
    - Technology: Tech industry news
    - Entertainment: Movies, TV, music
    - Sports: Sports news
    - Science: Scientific discoveries
    - Health: Health and medical news
    """
    return {
        "categories": NEWS_CATEGORIES,
        "default": "CryptoCurrency",
    }


@router.get("/image/{article_id}")
async def get_article_image(article_id: int):
    """
    Serve cached article thumbnail image.

    Returns the base64-decoded image with proper cache headers (7 days).
    This allows small JSON responses while still serving cached images efficiently.
    """
    import base64

    async with async_session_maker() as db:
        result = await db.execute(
            select(NewsArticle.image_data).where(NewsArticle.id == article_id)
        )
        row = result.first()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Image not found")

    image_data = row[0]

    # Parse the data URI: data:image/jpeg;base64,/9j/4AAQSkZJRgAB...
    if image_data.startswith("data:"):
        # Extract mime type and base64 data
        header, b64_data = image_data.split(",", 1)
        mime_type = header.split(":")[1].split(";")[0]
    else:
        # Assume it's raw base64 JPEG
        b64_data = image_data
        mime_type = "image/jpeg"

    try:
        image_bytes = base64.b64decode(b64_data)
    except Exception:
        raise HTTPException(status_code=500, detail="Invalid image data")

    # Return with 7-day cache headers
    return Response(
        content=image_bytes,
        media_type=mime_type,
        headers={
            "Cache-Control": "public, max-age=604800",  # 7 days
            "ETag": f'"{article_id}"',
        }
    )


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
async def get_videos(
    force_refresh: bool = False,
    category: Optional[str] = Query(None, description="Filter by category (e.g., CryptoCurrency)")
):
    """
    Get video news from database cache.

    Videos are fetched from YouTube channels by background service and stored in database.
    Returns immediately from database. Background refresh runs every 60 minutes.
    Use force_refresh=true to trigger immediate refresh (runs in background).

    Query params:
    - category: Filter by category (e.g., CryptoCurrency)
    """
    global _last_video_refresh

    # If force refresh requested, trigger background fetch
    if force_refresh:
        logger.info("Force refresh requested - triggering video fetch...")
        asyncio.create_task(fetch_all_videos())

    # Try to serve from database first (fast path)
    try:
        data = await get_videos_from_db(category=category)
        if data["videos"]:
            logger.debug(f"Serving {len(data['videos'])} videos from database")
            return VideoResponse(**data)
    except Exception as e:
        logger.error(f"Failed to get videos from database: {e}")

    # Fall back to JSON cache if database is empty
    cache = load_video_cache()
    if cache and cache.get("videos"):
        logger.info("Serving videos from JSON cache (database empty)")
        return VideoResponse(**cache)

    # No data available yet - trigger initial fetch if not already running
    if not _last_video_refresh:
        logger.info("No video cache available - triggering initial fetch...")
        asyncio.create_task(fetch_all_videos())

    raise HTTPException(status_code=503, detail="Videos not yet available - please try again shortly")


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


# ============================================================================
# MARKET METRICS ENDPOINTS
# ============================================================================


async def fetch_btc_dominance() -> Dict[str, Any]:
    """Fetch Bitcoin dominance from CoinGecko"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}
            url = "https://api.coingecko.com/api/v3/global"

            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status != 200:
                    logger.warning(f"CoinGecko global API returned {response.status}")
                    raise HTTPException(status_code=503, detail="CoinGecko API unavailable")

                data = await response.json()
                global_data = data.get("data", {})

                btc_dominance = global_data.get("market_cap_percentage", {}).get("btc", 0)
                eth_dominance = global_data.get("market_cap_percentage", {}).get("eth", 0)
                total_mcap = global_data.get("total_market_cap", {}).get("usd", 0)

                now = datetime.now()
                cache_data = {
                    "btc_dominance": round(btc_dominance, 2),
                    "eth_dominance": round(eth_dominance, 2),
                    "others_dominance": round(100 - btc_dominance - eth_dominance, 2),
                    "total_market_cap": total_mcap,
                    "cached_at": now.isoformat(),
                }

                save_btc_dominance_cache(cache_data)
                asyncio.create_task(record_metric_snapshot("btc_dominance", cache_data["btc_dominance"]))
                asyncio.create_task(record_metric_snapshot("total_market_cap", cache_data["total_market_cap"]))
                return cache_data

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching BTC dominance")
        raise HTTPException(status_code=503, detail="CoinGecko API timeout")
    except Exception as e:
        logger.error(f"Error fetching BTC dominance: {e}")
        raise HTTPException(status_code=503, detail=f"CoinGecko API error: {str(e)}")


async def fetch_altseason_index() -> Dict[str, Any]:
    """
    Calculate Altcoin Season Index based on top coins performance vs BTC.
    Altcoin season = 75%+ of top 50 altcoins outperformed BTC over 30 days.
    (Using 30-day as 90-day data not available in free CoinGecko API)
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}

            # Get top 50 coins with 30-day price change data
            url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=51&sparkline=false&price_change_percentage=30d"

            async with session.get(url, headers=headers, timeout=20) as response:
                if response.status != 200:
                    logger.warning(f"CoinGecko markets API returned {response.status}")
                    raise HTTPException(status_code=503, detail="CoinGecko API unavailable")

                coins = await response.json()

                # Find BTC's 30-day change
                btc_change = 0
                altcoins = []
                for coin in coins:
                    if coin.get("id") == "bitcoin":
                        btc_change = coin.get("price_change_percentage_30d_in_currency", 0) or 0
                    elif coin.get("id") not in ["tether", "usd-coin", "dai", "binance-usd"]:  # Exclude stablecoins
                        altcoins.append(coin)

                # Count altcoins that outperformed BTC
                outperformers = 0
                for coin in altcoins[:50]:  # Top 50 altcoins
                    coin_change = coin.get("price_change_percentage_30d_in_currency", 0) or 0
                    if coin_change > btc_change:
                        outperformers += 1

                # Calculate index (0-100)
                total_altcoins = min(len(altcoins), 50)
                altseason_index = round((outperformers / total_altcoins) * 100) if total_altcoins > 0 else 50

                # Determine season
                if altseason_index >= 75:
                    season = "Altcoin Season"
                elif altseason_index <= 25:
                    season = "Bitcoin Season"
                else:
                    season = "Neutral"

                now = datetime.now()
                cache_data = {
                    "altseason_index": altseason_index,
                    "season": season,
                    "outperformers": outperformers,
                    "total_altcoins": total_altcoins,
                    "btc_30d_change": round(btc_change, 2),
                    "cached_at": now.isoformat(),
                }

                save_altseason_cache(cache_data)
                asyncio.create_task(record_metric_snapshot("altseason_index", cache_data["altseason_index"]))
                return cache_data

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching altseason index")
        raise HTTPException(status_code=503, detail="CoinGecko API timeout")
    except Exception as e:
        logger.error(f"Error fetching altseason index: {e}")
        raise HTTPException(status_code=503, detail=f"CoinGecko API error: {str(e)}")


async def fetch_funding_rates() -> Dict[str, Any]:
    """
    Fetch BTC and ETH perpetual funding rates from CoinGlass public API.
    Positive = longs pay shorts (bullish overcrowded)
    Negative = shorts pay longs (bearish overcrowded)
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}

            # CoinGlass has a public endpoint for aggregate funding rates
            # Using their open-data endpoint
            url = "https://open-api.coinglass.com/public/v2/funding"

            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    funding_data = data.get("data", [])

                    btc_funding = None
                    eth_funding = None

                    for item in funding_data:
                        symbol = item.get("symbol", "").upper()
                        if symbol == "BTC":
                            btc_funding = item.get("uMarginList", [{}])[0].get("rate", 0)
                        elif symbol == "ETH":
                            eth_funding = item.get("uMarginList", [{}])[0].get("rate", 0)

                    if btc_funding is not None:
                        now = datetime.now()
                        cache_data = {
                            "btc_funding_rate": round(btc_funding * 100, 4),  # Convert to percentage
                            "eth_funding_rate": round((eth_funding or 0) * 100, 4),
                            "sentiment": "Overleveraged Longs" if (btc_funding or 0) > 0.01 else (
                                "Overleveraged Shorts" if (btc_funding or 0) < -0.01 else "Neutral"
                            ),
                            "cached_at": now.isoformat(),
                        }
                        save_funding_rates_cache(cache_data)
                        return cache_data

                # Fallback: return neutral data if API fails
                logger.warning("CoinGlass funding API unavailable, using fallback")
                now = datetime.now()
                return {
                    "btc_funding_rate": 0.01,
                    "eth_funding_rate": 0.01,
                    "sentiment": "Data Unavailable",
                    "cached_at": now.isoformat(),
                }

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching funding rates")
        return {"btc_funding_rate": 0, "eth_funding_rate": 0, "sentiment": "Data Unavailable", "cached_at": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching funding rates: {e}")
        return {"btc_funding_rate": 0, "eth_funding_rate": 0, "sentiment": "Data Unavailable", "cached_at": datetime.now().isoformat()}


async def fetch_stablecoin_mcap() -> Dict[str, Any]:
    """Fetch total stablecoin market cap from CoinGecko"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}

            # Get top stablecoins
            url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&category=stablecoins&order=market_cap_desc&per_page=20&sparkline=false"

            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status != 200:
                    logger.warning(f"CoinGecko stablecoins API returned {response.status}")
                    raise HTTPException(status_code=503, detail="CoinGecko API unavailable")

                coins = await response.json()

                total_mcap = sum(coin.get("market_cap", 0) or 0 for coin in coins)

                # Get individual breakdowns
                usdt_mcap = 0
                usdc_mcap = 0
                dai_mcap = 0
                others_mcap = 0

                for coin in coins:
                    coin_id = coin.get("id", "")
                    mcap = coin.get("market_cap", 0) or 0
                    if coin_id == "tether":
                        usdt_mcap = mcap
                    elif coin_id == "usd-coin":
                        usdc_mcap = mcap
                    elif coin_id == "dai":
                        dai_mcap = mcap
                    else:
                        others_mcap += mcap

                now = datetime.now()
                cache_data = {
                    "total_stablecoin_mcap": total_mcap,
                    "usdt_mcap": usdt_mcap,
                    "usdc_mcap": usdc_mcap,
                    "dai_mcap": dai_mcap,
                    "others_mcap": others_mcap,
                    "cached_at": now.isoformat(),
                }

                save_stablecoin_mcap_cache(cache_data)
                asyncio.create_task(record_metric_snapshot("stablecoin_mcap", cache_data["total_stablecoin_mcap"]))
                return cache_data

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching stablecoin mcap")
        raise HTTPException(status_code=503, detail="CoinGecko API timeout")
    except Exception as e:
        logger.error(f"Error fetching stablecoin mcap: {e}")
        raise HTTPException(status_code=503, detail=f"CoinGecko API error: {str(e)}")


@router.get("/btc-dominance")
async def get_btc_dominance():
    """
    Get Bitcoin market dominance percentage.

    Rising dominance = risk-off, altcoins underperforming
    Falling dominance = alt season potential
    """
    cache = load_btc_dominance_cache()
    if cache:
        logger.info("Serving BTC dominance from cache")
        return cache

    logger.info("Fetching fresh BTC dominance data...")
    return await fetch_btc_dominance()


@router.get("/altseason-index")
async def get_altseason_index():
    """
    Get Altcoin Season Index (0-100).

    Index >= 75: Altcoin Season (75%+ of top 50 altcoins outperformed BTC over 90 days)
    Index <= 25: Bitcoin Season
    25 < Index < 75: Neutral
    """
    cache = load_altseason_cache()
    if cache:
        logger.info("Serving altseason index from cache")
        return cache

    logger.info("Fetching fresh altseason index...")
    return await fetch_altseason_index()


@router.get("/funding-rates")
async def get_funding_rates():
    """
    Get BTC and ETH perpetual futures funding rates.

    Positive rates = longs pay shorts (market overleveraged long, correction risk)
    Negative rates = shorts pay longs (market overleveraged short, squeeze potential)
    """
    cache = load_funding_rates_cache()
    if cache:
        logger.info("Serving funding rates from cache")
        return cache

    logger.info("Fetching fresh funding rates...")
    return await fetch_funding_rates()


@router.get("/stablecoin-mcap")
async def get_stablecoin_mcap():
    """
    Get total stablecoin market cap.

    High/rising stablecoin mcap = "dry powder" waiting to be deployed = bullish
    Falling stablecoin mcap = capital leaving crypto = bearish
    """
    cache = load_stablecoin_mcap_cache()
    if cache:
        logger.info("Serving stablecoin mcap from cache")
        return cache

    logger.info("Fetching fresh stablecoin mcap...")
    return await fetch_stablecoin_mcap()


# =============================================================================
# Additional Market Metrics (Free APIs)
# =============================================================================

async def fetch_mempool_stats() -> Dict[str, Any]:
    """
    Fetch Bitcoin mempool statistics from mempool.space API.
    Shows network congestion and fee estimates.
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}

            # Fetch mempool stats
            async with session.get(
                "https://mempool.space/api/mempool",
                headers=headers,
                timeout=15
            ) as response:
                if response.status != 200:
                    raise HTTPException(status_code=503, detail="Mempool API unavailable")
                mempool_data = await response.json()

            # Fetch recommended fees
            async with session.get(
                "https://mempool.space/api/v1/fees/recommended",
                headers=headers,
                timeout=15
            ) as response:
                if response.status != 200:
                    fee_data = {"fastestFee": 0, "halfHourFee": 0, "hourFee": 0, "economyFee": 0}
                else:
                    fee_data = await response.json()

            now = datetime.now()
            cache_data = {
                "tx_count": mempool_data.get("count", 0),
                "vsize": mempool_data.get("vsize", 0),  # Virtual size in vbytes
                "total_fee": mempool_data.get("total_fee", 0),  # Total fees in sats
                "fee_fastest": fee_data.get("fastestFee", 0),  # sat/vB
                "fee_half_hour": fee_data.get("halfHourFee", 0),
                "fee_hour": fee_data.get("hourFee", 0),
                "fee_economy": fee_data.get("economyFee", 0),
                "congestion": "High" if mempool_data.get("count", 0) > 50000 else (
                    "Medium" if mempool_data.get("count", 0) > 20000 else "Low"
                ),
                "cached_at": now.isoformat(),
            }

            save_mempool_cache(cache_data)
            asyncio.create_task(record_metric_snapshot("mempool_tx_count", cache_data["tx_count"]))
            return cache_data

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching mempool stats")
        raise HTTPException(status_code=503, detail="Mempool API timeout")
    except Exception as e:
        logger.error(f"Error fetching mempool stats: {e}")
        raise HTTPException(status_code=503, detail=f"Mempool API error: {str(e)}")


async def fetch_hash_rate() -> Dict[str, Any]:
    """
    Fetch Bitcoin network hash rate from mempool.space API.
    Higher hash rate = more secure network.
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}

            # Fetch current hash rate from mempool.space (3 day average)
            async with session.get(
                "https://mempool.space/api/v1/mining/hashrate/3d",
                headers=headers,
                timeout=15
            ) as response:
                if response.status != 200:
                    raise HTTPException(status_code=503, detail="Mempool API unavailable")
                data = await response.json()
                hashrates = data.get("hashrates", [])
                if hashrates:
                    # Get latest hash rate (H/s), convert to EH/s
                    latest = hashrates[-1].get("avgHashrate", 0)
                    hash_rate_eh = latest / 1e18  # H/s to EH/s
                else:
                    hash_rate_eh = 0

            # Fetch difficulty from mempool.space
            async with session.get(
                "https://mempool.space/api/v1/difficulty-adjustment",
                headers=headers,
                timeout=15
            ) as response:
                if response.status != 200:
                    difficulty = 0
                else:
                    diff_data = await response.json()
                    difficulty = diff_data.get("difficultyChange", 0)

            now = datetime.now()
            cache_data = {
                "hash_rate_eh": round(hash_rate_eh, 2),  # Exahashes per second
                "difficulty": difficulty,  # Difficulty change percentage
                "difficulty_t": round(difficulty, 2),  # Same value for display
                "cached_at": now.isoformat(),
            }

            save_hash_rate_cache(cache_data)
            asyncio.create_task(record_metric_snapshot("hash_rate", cache_data["hash_rate_eh"]))
            return cache_data

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching hash rate")
        raise HTTPException(status_code=503, detail="Mempool API timeout")
    except Exception as e:
        logger.error(f"Error fetching hash rate: {e}")
        raise HTTPException(status_code=503, detail=f"Mempool API error: {str(e)}")


async def fetch_lightning_stats() -> Dict[str, Any]:
    """
    Fetch Lightning Network statistics from mempool.space API.
    Shows LN adoption and capacity.
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}

            async with session.get(
                "https://mempool.space/api/v1/lightning/statistics/latest",
                headers=headers,
                timeout=15
            ) as response:
                if response.status != 200:
                    raise HTTPException(status_code=503, detail="Lightning API unavailable")
                response_data = await response.json()
                # API wraps data in "latest" object
                data = response_data.get("latest", response_data)

            now = datetime.now()
            cache_data = {
                "channel_count": data.get("channel_count", 0),
                "node_count": data.get("node_count", 0),
                "total_capacity_btc": round(data.get("total_capacity", 0) / 100_000_000, 2),  # sats to BTC
                "avg_capacity_sats": data.get("avg_capacity", 0),
                "avg_fee_rate": data.get("avg_fee_rate", 0),
                "cached_at": now.isoformat(),
            }

            save_lightning_cache(cache_data)
            asyncio.create_task(record_metric_snapshot("lightning_capacity", cache_data["total_capacity_btc"]))
            return cache_data

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching lightning stats")
        raise HTTPException(status_code=503, detail="Lightning API timeout")
    except Exception as e:
        logger.error(f"Error fetching lightning stats: {e}")
        raise HTTPException(status_code=503, detail=f"Lightning API error: {str(e)}")


async def fetch_ath_data() -> Dict[str, Any]:
    """
    Fetch Bitcoin ATH (All-Time High) data from CoinGecko.
    Shows days since ATH and drawdown percentage.
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "ZenithGrid/1.0"}

            async with session.get(
                "https://api.coingecko.com/api/v3/coins/bitcoin?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false",
                headers=headers,
                timeout=15
            ) as response:
                if response.status != 200:
                    raise HTTPException(status_code=503, detail="CoinGecko API unavailable")
                data = await response.json()

            market_data = data.get("market_data", {})
            current_price = market_data.get("current_price", {}).get("usd", 0)
            ath = market_data.get("ath", {}).get("usd", 0)
            ath_date_str = market_data.get("ath_date", {}).get("usd", "")
            ath_change_pct = market_data.get("ath_change_percentage", {}).get("usd", 0)

            # Calculate days since ATH
            days_since_ath = 0
            if ath_date_str:
                try:
                    ath_date = datetime.fromisoformat(ath_date_str.replace("Z", "+00:00"))
                    days_since_ath = (datetime.now(ath_date.tzinfo) - ath_date).days
                except Exception:
                    pass

            now = datetime.now()
            cache_data = {
                "current_price": round(current_price, 2),
                "ath": round(ath, 2),
                "ath_date": ath_date_str[:10] if ath_date_str else "",  # Just the date part
                "days_since_ath": days_since_ath,
                "drawdown_pct": round(ath_change_pct, 2),  # Negative percentage from ATH
                "recovery_pct": round(100 + ath_change_pct, 2) if ath_change_pct < 0 else 100,
                "cached_at": now.isoformat(),
            }

            save_ath_cache(cache_data)
            return cache_data

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching ATH data")
        raise HTTPException(status_code=503, detail="CoinGecko API timeout")
    except Exception as e:
        logger.error(f"Error fetching ATH data: {e}")
        raise HTTPException(status_code=503, detail=f"CoinGecko API error: {str(e)}")


@router.get("/total-market-cap")
async def get_total_market_cap():
    """
    Get total crypto market capitalization.
    Uses cached BTC dominance data which includes total market cap.
    """
    cache = load_btc_dominance_cache()
    if cache:
        return {
            "total_market_cap": cache.get("total_market_cap", 0),
            "cached_at": cache.get("cached_at"),
        }

    # Fetch fresh if no cache
    fresh_data = await fetch_btc_dominance()
    return {
        "total_market_cap": fresh_data.get("total_market_cap", 0),
        "cached_at": fresh_data.get("cached_at"),
    }


@router.get("/btc-supply")
async def get_btc_supply():
    """
    Get Bitcoin supply progress - how much of the 21M has been mined.
    Calculated from current block height.
    """
    cache = load_block_height_cache()
    if not cache:
        # Try to fetch fresh
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"User-Agent": "ZenithGrid/1.0"}
                async with session.get(
                    "https://blockchain.info/q/getblockcount",
                    headers=headers,
                    timeout=10
                ) as response:
                    if response.status == 200:
                        height = int(await response.text())
                        cache = {"height": height}
        except Exception:
            pass

    if not cache:
        raise HTTPException(status_code=503, detail="Could not fetch block height")

    height = cache.get("height", 0)

    # Calculate circulating supply based on halving schedule
    # Block rewards: 50 BTC (0-210000), 25 (210000-420000), 12.5, 6.25, 3.125...
    circulating = 0
    remaining_blocks = height
    reward = 50
    blocks_per_halving = 210_000

    while remaining_blocks > 0:
        blocks_in_era = min(remaining_blocks, blocks_per_halving)
        circulating += blocks_in_era * reward
        remaining_blocks -= blocks_in_era
        reward /= 2
        blocks_per_halving = 210_000

    max_supply = 21_000_000
    percent_mined = (circulating / max_supply) * 100
    remaining = max_supply - circulating

    return {
        "circulating": round(circulating, 2),
        "max_supply": max_supply,
        "remaining": round(remaining, 2),
        "percent_mined": round(percent_mined, 4),
        "current_block": height,
        "cached_at": cache.get("timestamp", datetime.now().isoformat()),
    }


@router.get("/mempool")
async def get_mempool_stats():
    """
    Get Bitcoin mempool statistics.
    Shows pending transactions and fee estimates.
    """
    cache = load_mempool_cache()
    if cache:
        logger.info("Serving mempool stats from cache")
        return cache

    logger.info("Fetching fresh mempool stats...")
    return await fetch_mempool_stats()


@router.get("/hash-rate")
async def get_hash_rate():
    """
    Get Bitcoin network hash rate.
    Higher = more secure network.
    """
    cache = load_hash_rate_cache()
    if cache:
        logger.info("Serving hash rate from cache")
        return cache

    logger.info("Fetching fresh hash rate...")
    return await fetch_hash_rate()


@router.get("/lightning")
async def get_lightning_stats():
    """
    Get Lightning Network statistics.
    Shows nodes, channels, and total capacity.
    """
    cache = load_lightning_cache()
    if cache:
        logger.info("Serving lightning stats from cache")
        return cache

    logger.info("Fetching fresh lightning stats...")
    return await fetch_lightning_stats()


@router.get("/ath")
async def get_ath():
    """
    Get Bitcoin ATH (All-Time High) data.
    Shows days since ATH and current drawdown.
    """
    cache = load_ath_cache()
    if cache:
        logger.info("Serving ATH data from cache")
        return cache

    logger.info("Fetching fresh ATH data...")
    return await fetch_ath_data()


async def fetch_btc_rsi() -> Dict[str, Any]:
    """Fetch BTC-USD daily candles from Coinbase and calculate RSI(14)."""
    try:
        now = int(datetime.now().timestamp())
        # Need ~20 daily candles for RSI-14 calculation
        start = now - (25 * 24 * 60 * 60)

        async with aiohttp.ClientSession() as session:
            url = (
                f"https://api.coinbase.com/api/v3/brokerage/market/products/BTC-USD/candles"
                f"?start={start}&end={now}&granularity=ONE_DAY"
            )
            headers = {"User-Agent": "ZenithGrid/1.0"}

            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status != 200:
                    logger.warning(f"Coinbase candles API returned {response.status}")
                    raise HTTPException(status_code=503, detail="Coinbase API unavailable")

                data = await response.json()
                candles = data.get("candles", [])

                if len(candles) < 15:
                    raise HTTPException(status_code=503, detail="Not enough candle data for RSI")

                # Coinbase returns newest first; reverse for chronological order
                candles.sort(key=lambda c: int(c["start"]))
                closes = [float(c["close"]) for c in candles]

                calc = IndicatorCalculator()
                rsi = calc.calculate_rsi(closes, 14)

                if rsi is None:
                    raise HTTPException(status_code=503, detail="RSI calculation failed")

                rsi = round(rsi, 2)

                if rsi < 30:
                    zone = "oversold"
                elif rsi > 70:
                    zone = "overbought"
                else:
                    zone = "neutral"

                now_dt = datetime.now()
                cache_data = {
                    "rsi": rsi,
                    "zone": zone,
                    "cached_at": now_dt.isoformat(),
                    "cache_expires_at": (now_dt + timedelta(minutes=15)).isoformat(),
                }

                save_btc_rsi_cache(cache_data)
                asyncio.create_task(record_metric_snapshot("btc_rsi", rsi))
                return cache_data

    except asyncio.TimeoutError:
        logger.warning("Timeout fetching BTC RSI candles")
        raise HTTPException(status_code=503, detail="Coinbase API timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching BTC RSI: {e}")
        raise HTTPException(status_code=503, detail=f"BTC RSI error: {str(e)}")


@router.get("/btc-rsi")
async def get_btc_rsi():
    """
    Get BTC RSI(14) based on daily candles.
    RSI < 30 = oversold, RSI > 70 = overbought.
    """
    cache = load_btc_rsi_cache()
    if cache:
        logger.info("Serving BTC RSI from cache")
        return cache

    logger.info("Fetching fresh BTC RSI data...")
    return await fetch_btc_rsi()


VALID_METRIC_NAMES = {
    "fear_greed", "btc_dominance", "altseason_index", "stablecoin_mcap",
    "total_market_cap", "hash_rate", "lightning_capacity", "mempool_tx_count",
    "btc_rsi",
}


@router.get("/metric-history/{metric_name}")
async def get_metric_history(
    metric_name: str,
    days: int = Query(default=30, ge=1, le=90),
    max_points: int = Query(default=30, ge=5, le=500),
):
    """
    Get historical snapshots for a metric (for sparkline charts).
    Returns averaged/downsampled data (default: 30 points over 14 days).
    """
    if metric_name not in VALID_METRIC_NAMES:
        raise HTTPException(status_code=400, detail=f"Invalid metric: {metric_name}")

    cutoff = datetime.utcnow() - timedelta(days=days)
    async with async_session_maker() as db:
        result = await db.execute(
            select(MetricSnapshot.value, MetricSnapshot.recorded_at)
            .where(MetricSnapshot.metric_name == metric_name)
            .where(MetricSnapshot.recorded_at >= cutoff)
            .order_by(MetricSnapshot.recorded_at)
        )
        rows = result.all()

    # Downsample by averaging into buckets for smooth sparklines
    if len(rows) > max_points:
        bucket_size = len(rows) / max_points
        sampled = []
        for i in range(max_points):
            start = int(i * bucket_size)
            end = int((i + 1) * bucket_size)
            bucket = rows[start:end]
            avg_value = sum(r.value for r in bucket) / len(bucket)
            # Use the last timestamp in the bucket as representative
            sampled.append(type('Row', (), {'value': avg_value, 'recorded_at': bucket[-1].recorded_at})())
    else:
        sampled = rows

    # Also prune old data periodically (piggyback on reads)
    if len(rows) > 0:
        asyncio.create_task(prune_old_snapshots())

    return {
        "metric_name": metric_name,
        "data": [{"value": r.value, "recorded_at": r.recorded_at.isoformat()} for r in sampled],
    }


@router.get("/article-content", response_model=ArticleContentResponse)
async def get_article_content(url: str):
    """
    Extract article content from a news URL.

    Uses trafilatura to extract the main article text, title, and metadata.
    Only allows fetching from domains in the content_sources database table.

    Returns clean, readable article content like browser reader mode.

    TODO: Some sites (e.g., The Block) use Cloudflare protection and render content
    via JavaScript client-side. To support these sites, we'd need to:
    1. Install Playwright: pip install playwright && playwright install chromium
    2. Use Playwright to fetch pages that fail with regular HTTP requests
    3. Memory concern: Playwright uses significant RAM, may not work well on t2.micro (1GB)
    4. Consider upgrading to t2.small (2GB RAM) before implementing
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

        # Security check: only allow domains from database sources
        domain = parsed.netloc.lower()
        allowed_domains = await get_allowed_article_domains()
        if domain not in allowed_domains:
            logger.warning(f"Attempted to fetch article from non-allowed domain: {domain}")
            return ArticleContentResponse(
                url=url,
                success=False,
                error=f"Domain not allowed. Supported: {', '.join(sorted(allowed_domains))}"
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
                    include_links=False,  # Don't need links for reading
                    no_fallback=False,
                    favor_recall=True,  # Favor including more content over precision
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


# =============================================================================
# Text-to-Speech Endpoint
# =============================================================================

# Available voices for TTS (high-quality neural voices from all English locales)
TTS_VOICES = {
    # US voices
    "aria": "en-US-AriaNeural",        # Female - default
    "guy": "en-US-GuyNeural",          # Male
    "jenny": "en-US-JennyNeural",      # Female
    "brian": "en-US-BrianNeural",      # Male
    "emma": "en-US-EmmaNeural",        # Female
    "andrew": "en-US-AndrewNeural",    # Male
    "ava": "en-US-AvaNeural",          # Female, Expressive
    "ana": "en-US-AnaNeural",          # Female, Cute
    "christopher": "en-US-ChristopherNeural",  # Male, Reliable
    "eric": "en-US-EricNeural",        # Male, Rational
    "michelle": "en-US-MichelleNeural",  # Female, Friendly
    "roger": "en-US-RogerNeural",      # Male, Lively
    "steffan": "en-US-SteffanNeural",  # Male, Rational
    # British voices
    "libby": "en-GB-LibbyNeural",      # Female
    "sonia": "en-GB-SoniaNeural",      # Female
    "ryan": "en-GB-RyanNeural",        # Male
    "thomas": "en-GB-ThomasNeural",    # Male
    "maisie": "en-GB-MaisieNeural",    # Female (child)
    # Australian voices
    "natasha": "en-AU-NatashaNeural",  # Female
    "william": "en-AU-WilliamNeural",  # Male
    # Canadian voices
    "clara": "en-CA-ClaraNeural",      # Female
    "liam": "en-CA-LiamNeural",        # Male
    # Irish voices
    "connor": "en-IE-ConnorNeural",    # Male
    "emily": "en-IE-EmilyNeural",      # Female
    # Indian English voices
    "neerja": "en-IN-NeerjaNeural",    # Female
    "prabhat": "en-IN-PrabhatNeural",  # Male
    # New Zealand voices
    "mitchell": "en-NZ-MitchellNeural",  # Male
    "molly": "en-NZ-MollyNeural",      # Female
    # South African voices
    "leah": "en-ZA-LeahNeural",        # Female
    "luke": "en-ZA-LukeNeural",        # Male
    # Singapore voices
    "luna": "en-SG-LunaNeural",        # Female
    "wayne": "en-SG-WayneNeural",      # Male
    # Hong Kong voices
    "sam": "en-HK-SamNeural",          # Male
    "yan": "en-HK-YanNeural",          # Female
    # Kenya voices
    "asilia": "en-KE-AsiliaNeural",    # Female
    "chilemba": "en-KE-ChilembaNeural",  # Male
    # Nigeria voices
    "abeo": "en-NG-AbeoNeural",        # Male
    "ezinne": "en-NG-EzinneNeural",    # Female
    # Philippines voices
    "james": "en-PH-JamesNeural",      # Male
    "rosa": "en-PH-RosaNeural",        # Female
    # Tanzania voices
    "elimu": "en-TZ-ElimuNeural",      # Male
    "imani": "en-TZ-ImaniNeural",      # Female
}

DEFAULT_VOICE = "aria"


@router.post("/tts")
async def text_to_speech(
    text: str = Query(..., min_length=1, max_length=50000, description="Text to convert to speech"),
    voice: str = Query(DEFAULT_VOICE, description="Voice to use (aria, guy, jenny, brian, emma, andrew)"),
    rate: str = Query("+0%", description="Speech rate adjustment (e.g., +10%, -20%)"),
):
    """
    Convert text to speech using Microsoft Edge's neural TTS.

    Returns streaming MP3 audio. Free, high-quality neural voices.

    Query params:
    - text: The text to convert (max 50,000 characters)
    - voice: Voice selection (default: aria - female news voice)
    - rate: Speed adjustment (e.g., "+10%" for faster, "-20%" for slower)

    Available voices:
    - aria: Female, News voice (default) - clear and professional
    - guy: Male, News voice - authoritative
    - jenny: Female, General - friendly
    - brian: Male, Conversational - approachable
    - emma: Female, Conversational - cheerful
    - andrew: Male, Conversational - warm
    """
    # Validate voice selection
    voice_name = TTS_VOICES.get(voice.lower(), TTS_VOICES[DEFAULT_VOICE])

    # Validate rate format
    if not (rate.startswith("+") or rate.startswith("-")) or not rate.endswith("%"):
        rate = "+0%"

    async def generate_audio():
        """Generate audio chunks using edge-tts"""
        try:
            communicate = edge_tts.Communicate(text, voice_name, rate=rate)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]
        except Exception as e:
            logger.error(f"TTS generation error: {e}")
            raise

    try:
        return StreamingResponse(
            generate_audio(),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline",
                "Cache-Control": "no-cache",
            }
        )
    except Exception as e:
        logger.error(f"TTS endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")


@router.get("/tts/voices")
async def get_tts_voices():
    """
    Get available TTS voices.

    Returns list of voice options with descriptions.
    """
    return {
        "voices": [
            {"id": "aria", "name": "Aria", "gender": "Female", "style": "News", "desc": "Clear"},
            {"id": "guy", "name": "Guy", "gender": "Male", "style": "News", "desc": "Authoritative"},
            {"id": "jenny", "name": "Jenny", "gender": "Female", "style": "General", "desc": "Friendly"},
            {"id": "brian", "name": "Brian", "gender": "Male", "style": "Casual", "desc": "Approachable"},
            {"id": "emma", "name": "Emma", "gender": "Female", "style": "Casual", "desc": "Cheerful"},
            {"id": "andrew", "name": "Andrew", "gender": "Male", "style": "Casual", "desc": "Warm"},
        ],
        "default": DEFAULT_VOICE,
    }


@router.post("/tts-sync")
async def text_to_speech_with_sync(
    text: str = Query(..., min_length=1, max_length=50000),
    voice: str = Query(DEFAULT_VOICE),
    rate: str = Query("+0%"),
):
    """
    Convert text to speech with word-level timing for synchronized highlighting.

    Returns JSON with:
    - audio: Base64-encoded MP3 audio
    - words: Array of {text, startTime, endTime} for each word (times in seconds)

    This enables karaoke-style word highlighting during playback.
    """
    import base64

    voice_name = TTS_VOICES.get(voice.lower(), TTS_VOICES[DEFAULT_VOICE])

    if not (rate.startswith("+") or rate.startswith("-")) or not rate.endswith("%"):
        rate = "+0%"

    try:
        communicate = edge_tts.Communicate(text, voice_name, rate=rate, boundary="WordBoundary")

        audio_chunks = []
        word_boundaries = []

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # Convert 100-nanosecond units to seconds
                offset_sec = chunk["offset"] / 10_000_000
                duration_sec = chunk["duration"] / 10_000_000
                word_boundaries.append({
                    "text": chunk["text"],
                    "startTime": round(offset_sec, 3),
                    "endTime": round(offset_sec + duration_sec, 3),
                })

        # Combine audio chunks and encode as base64
        audio_data = b"".join(audio_chunks)
        audio_base64 = base64.b64encode(audio_data).decode("utf-8")

        return {
            "audio": audio_base64,
            "words": word_boundaries,
            "voice": voice,
            "rate": rate,
        }

    except Exception as e:
        logger.error(f"TTS sync generation error: {e}")
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")
