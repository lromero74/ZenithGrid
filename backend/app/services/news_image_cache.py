"""
News Image Caching Service

Downloads and caches news article thumbnails locally.
Images are stored in static/news_images/ with hashed filenames.
Cleanup removes images older than 7 days along with their articles.
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)

# Directory for cached images (relative to backend/)
STATIC_DIR = Path(__file__).parent.parent.parent / "static"
NEWS_IMAGES_DIR = STATIC_DIR / "news_images"

# Ensure directory exists
NEWS_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Image download settings
IMAGE_DOWNLOAD_TIMEOUT = 10  # seconds
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB max


def get_image_filename(url: str) -> str:
    """Generate a unique filename from URL using hash."""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    # Try to preserve extension from URL
    parsed = urlparse(url)
    path = parsed.path.lower()
    if path.endswith('.jpg') or path.endswith('.jpeg'):
        ext = '.jpg'
    elif path.endswith('.png'):
        ext = '.png'
    elif path.endswith('.gif'):
        ext = '.gif'
    elif path.endswith('.webp'):
        ext = '.webp'
    else:
        ext = '.jpg'  # Default to jpg
    return f"{url_hash}{ext}"


def get_cached_image_path(url: str) -> Path:
    """Get the full filesystem path for a cached image."""
    filename = get_image_filename(url)
    return NEWS_IMAGES_DIR / filename


def get_cached_image_url_path(url: str) -> str:
    """Get the URL path for serving a cached image (relative to static mount)."""
    filename = get_image_filename(url)
    return f"/static/news_images/{filename}"


async def download_image(session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
    """Download an image from URL with timeout and size limits."""
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=IMAGE_DOWNLOAD_TIMEOUT),
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; ZenithGrid/1.0)',
                'Accept': 'image/*'
            }
        ) as response:
            if response.status != 200:
                logger.debug(f"Failed to download image (status {response.status}): {url}")
                return None

            # Check content type
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                logger.debug(f"Not an image (content-type: {content_type}): {url}")
                return None

            # Check content length if available
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) > MAX_IMAGE_SIZE:
                logger.debug(f"Image too large ({content_length} bytes): {url}")
                return None

            # Download with size limit
            data = b''
            async for chunk in response.content.iter_chunked(8192):
                data += chunk
                if len(data) > MAX_IMAGE_SIZE:
                    logger.debug(f"Image exceeded size limit during download: {url}")
                    return None

            return data

    except asyncio.TimeoutError:
        logger.debug(f"Timeout downloading image: {url}")
        return None
    except Exception as e:
        logger.debug(f"Error downloading image {url}: {e}")
        return None


async def cache_image(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    """
    Download and cache an image, returning the cached URL path.

    Returns:
        The URL path for the cached image (e.g., "/static/news_images/abc123.jpg")
        or None if download failed.
    """
    if not url:
        return None

    # Check if already cached
    cached_path = get_cached_image_path(url)
    if cached_path.exists():
        return get_cached_image_url_path(url)

    # Download the image
    image_data = await download_image(session, url)
    if not image_data:
        return None

    # Save to disk
    try:
        with open(cached_path, 'wb') as f:
            f.write(image_data)
        logger.debug(f"Cached image: {url} -> {cached_path.name}")
        return get_cached_image_url_path(url)
    except Exception as e:
        logger.error(f"Failed to save image {url}: {e}")
        return None


async def cache_images_batch(urls: list[str]) -> dict[str, Optional[str]]:
    """
    Cache multiple images concurrently.

    Args:
        urls: List of image URLs to cache

    Returns:
        Dict mapping original URL to cached URL path (or None if failed)
    """
    if not urls:
        return {}

    results = {}
    async with aiohttp.ClientSession() as session:
        tasks = []
        for url in urls:
            if url:
                tasks.append((url, cache_image(session, url)))
            else:
                results[url] = None

        for url, task in tasks:
            try:
                cached_path = await task
                results[url] = cached_path
            except Exception as e:
                logger.error(f"Error caching image {url}: {e}")
                results[url] = None

    return results


def cleanup_old_images(max_age_days: int = 7) -> int:
    """
    Remove cached images older than max_age_days.

    Returns:
        Number of images removed
    """
    cutoff = datetime.now() - timedelta(days=max_age_days)
    removed_count = 0

    try:
        for image_file in NEWS_IMAGES_DIR.iterdir():
            if image_file.name == '.gitkeep':
                continue

            try:
                # Check file modification time
                mtime = datetime.fromtimestamp(image_file.stat().st_mtime)
                if mtime < cutoff:
                    image_file.unlink()
                    removed_count += 1
            except Exception as e:
                logger.warning(f"Failed to check/remove image {image_file}: {e}")

    except Exception as e:
        logger.error(f"Error during image cleanup: {e}")

    if removed_count > 0:
        logger.info(f"Cleaned up {removed_count} old news images")

    return removed_count


def get_disk_usage() -> dict:
    """Get disk usage stats for the news images cache."""
    total_size = 0
    file_count = 0

    try:
        for image_file in NEWS_IMAGES_DIR.iterdir():
            if image_file.name == '.gitkeep':
                continue
            if image_file.is_file():
                total_size += image_file.stat().st_size
                file_count += 1
    except Exception as e:
        logger.error(f"Error calculating disk usage: {e}")

    return {
        "file_count": file_count,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2)
    }
