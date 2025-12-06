"""
News Image Caching Service

Downloads news article thumbnails and converts them to base64 data URIs
for storage directly in the database. This avoids path/proxy issues with
SSH tunneling and simplifies serving images from any environment.
"""

import asyncio
import base64
import logging
from typing import Optional
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)

# Image download settings
IMAGE_DOWNLOAD_TIMEOUT = 10  # seconds
MAX_IMAGE_SIZE = 2 * 1024 * 1024  # 2MB max (smaller for base64 storage)


def get_mime_type_from_url(url: str) -> str:
    """Determine MIME type from URL extension."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    if path.endswith('.png'):
        return 'image/png'
    elif path.endswith('.gif'):
        return 'image/gif'
    elif path.endswith('.webp'):
        return 'image/webp'
    else:
        return 'image/jpeg'  # Default to jpeg


def get_mime_type_from_content_type(content_type: str) -> str:
    """Extract MIME type from Content-Type header."""
    # Content-Type might be "image/jpeg; charset=utf-8" etc.
    mime = content_type.split(';')[0].strip().lower()
    if mime in ('image/jpeg', 'image/png', 'image/gif', 'image/webp'):
        return mime
    return 'image/jpeg'  # Default


async def download_image(session: aiohttp.ClientSession, url: str) -> Optional[tuple[bytes, str]]:
    """
    Download an image from URL with timeout and size limits.

    Returns:
        Tuple of (image_bytes, mime_type) or None if download failed.
    """
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

            # Get MIME type from header, fallback to URL extension
            mime_type = get_mime_type_from_content_type(content_type)

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

            return (data, mime_type)

    except asyncio.TimeoutError:
        logger.debug(f"Timeout downloading image: {url}")
        return None
    except Exception as e:
        logger.debug(f"Error downloading image {url}: {e}")
        return None


async def download_image_as_base64(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    """
    Download an image and return it as a base64 data URI.

    Returns:
        Base64 data URI (e.g., "data:image/jpeg;base64,/9j/4AAQ...")
        or None if download failed.
    """
    if not url:
        return None

    result = await download_image(session, url)
    if not result:
        return None

    image_data, mime_type = result

    # Convert to base64 data URI
    b64_data = base64.b64encode(image_data).decode('ascii')
    data_uri = f"data:{mime_type};base64,{b64_data}"

    logger.debug(f"Converted image to base64 ({len(b64_data)} chars): {url[:50]}...")
    return data_uri


async def download_images_batch(urls: list[str]) -> dict[str, Optional[str]]:
    """
    Download multiple images concurrently and convert to base64 data URIs.

    Args:
        urls: List of image URLs to download

    Returns:
        Dict mapping original URL to base64 data URI (or None if failed)
    """
    if not urls:
        return {}

    results = {}
    async with aiohttp.ClientSession() as session:
        tasks = []
        for url in urls:
            if url:
                tasks.append((url, download_image_as_base64(session, url)))
            else:
                results[url] = None

        for url, task in tasks:
            try:
                data_uri = await task
                results[url] = data_uri
            except Exception as e:
                logger.error(f"Error downloading image {url}: {e}")
                results[url] = None

    return results
