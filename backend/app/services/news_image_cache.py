"""
News Image Caching Service

Downloads news article thumbnails and converts them to base64 data URIs
for storage directly in the database. This avoids path/proxy issues with
SSH tunneling and simplifies serving images from any environment.
"""

import asyncio
import base64
import io
import logging
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from PIL import Image

logger = logging.getLogger(__name__)

# Image download settings
IMAGE_DOWNLOAD_TIMEOUT = 10  # seconds
MAX_IMAGE_SIZE = 2 * 1024 * 1024  # 2MB max (smaller for base64 storage)

# Image compression settings
THUMBNAIL_MAX_WIDTH = 600  # Resize thumbnails to max 600px width (50% increase from 400px)
WEBP_QUALITY = 85  # 85% quality - visually identical but much smaller


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


def compress_image(image_bytes: bytes) -> tuple[bytes, str]:
    """
    Compress and optimize an image for thumbnail storage.

    - Resizes to max 600px width while maintaining aspect ratio
    - Converts to WebP format for better compression
    - Applies 85% quality (visually identical but much smaller)

    Returns:
        Tuple of (compressed_bytes, 'image/webp')
    """
    try:
        # Open image from bytes
        img = Image.open(io.BytesIO(image_bytes))

        # Convert RGBA/LA to RGB (WebP doesn't handle transparency well in all cases)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Resize if image is wider than max width
        if img.width > THUMBNAIL_MAX_WIDTH:
            # Calculate new height to maintain aspect ratio
            ratio = THUMBNAIL_MAX_WIDTH / img.width
            new_height = int(img.height * ratio)
            img = img.resize((THUMBNAIL_MAX_WIDTH, new_height), Image.Resampling.LANCZOS)
            logger.debug(f"Resized image to {THUMBNAIL_MAX_WIDTH}x{new_height}")

        # Save as WebP with optimization
        output = io.BytesIO()
        img.save(output, format='WEBP', quality=WEBP_QUALITY, method=6)  # method=6 = best compression
        compressed_bytes = output.getvalue()

        original_size = len(image_bytes)
        compressed_size = len(compressed_bytes)
        savings = (1 - compressed_size / original_size) * 100
        logger.debug(f"Compressed image: {original_size:,} → {compressed_size:,} bytes ({savings:.1f}% savings)")

        return (compressed_bytes, 'image/webp')
    except Exception as e:
        logger.warning(f"Failed to compress image: {e}, returning original")
        # If compression fails, return original
        return (image_bytes, 'image/jpeg')


async def download_image_as_base64(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    """
    Download an image, compress it, and return it as a base64 data URI.

    Returns:
        Base64 data URI (e.g., "data:image/webp;base64,/9j/4AAQ...")
        or None if download failed.
    """
    if not url:
        return None

    result = await download_image(session, url)
    if not result:
        return None

    image_data, mime_type = result

    # Compress the image (resize + convert to WebP)
    compressed_data, compressed_mime = compress_image(image_data)

    # Convert to base64 data URI
    b64_data = base64.b64encode(compressed_data).decode('ascii')
    data_uri = f"data:{compressed_mime};base64,{b64_data}"

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
