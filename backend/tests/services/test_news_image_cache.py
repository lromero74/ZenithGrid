"""
Tests for backend/app/services/news_image_cache.py

Covers:
- MIME type detection from URL and Content-Type header
- Image downloading with size limits and timeouts
- Image compression (resize + WebP conversion)
- download_image_as_base64 wrapper
- download_and_save_image filesystem writer
- download_images_batch concurrent downloader
"""

import asyncio
import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image

from app.services.news_image_cache import (
    get_mime_type_from_url,
    get_mime_type_from_content_type,
    compress_image,
    download_image,
    download_image_as_base64,
    download_and_save_image,
    download_images_batch,
    MAX_IMAGE_SIZE,
    THUMBNAIL_MAX_WIDTH,
)


# ---------------------------------------------------------------------------
# get_mime_type_from_url
# ---------------------------------------------------------------------------


class TestGetMimeTypeFromUrl:
    """Tests for get_mime_type_from_url()"""

    def test_png_extension(self):
        """Happy path: .png URL returns image/png."""
        assert get_mime_type_from_url("https://example.com/image.png") == "image/png"

    def test_gif_extension(self):
        """Happy path: .gif URL returns image/gif."""
        assert get_mime_type_from_url("https://example.com/image.gif") == "image/gif"

    def test_webp_extension(self):
        """Happy path: .webp URL returns image/webp."""
        assert get_mime_type_from_url("https://example.com/image.webp") == "image/webp"

    def test_jpg_defaults_to_jpeg(self):
        """Happy path: .jpg URL returns image/jpeg (default)."""
        assert get_mime_type_from_url("https://example.com/image.jpg") == "image/jpeg"

    def test_unknown_extension_defaults_to_jpeg(self):
        """Edge case: unknown extension returns image/jpeg default."""
        assert get_mime_type_from_url("https://example.com/image.bmp") == "image/jpeg"

    def test_no_extension_defaults_to_jpeg(self):
        """Edge case: URL without file extension defaults to image/jpeg."""
        assert get_mime_type_from_url("https://example.com/api/image/123") == "image/jpeg"

    def test_url_with_query_params(self):
        """Edge case: URL with query params extracts extension correctly."""
        assert get_mime_type_from_url("https://example.com/image.png?w=300") == "image/png"


# ---------------------------------------------------------------------------
# get_mime_type_from_content_type
# ---------------------------------------------------------------------------


class TestGetMimeTypeFromContentType:
    """Tests for get_mime_type_from_content_type()"""

    def test_simple_jpeg(self):
        """Happy path: simple image/jpeg."""
        assert get_mime_type_from_content_type("image/jpeg") == "image/jpeg"

    def test_content_type_with_charset(self):
        """Edge case: Content-Type with charset suffix."""
        assert get_mime_type_from_content_type("image/png; charset=utf-8") == "image/png"

    def test_webp_content_type(self):
        """Happy path: image/webp recognized."""
        assert get_mime_type_from_content_type("image/webp") == "image/webp"

    def test_unknown_content_type_defaults(self):
        """Failure: unrecognized MIME defaults to image/jpeg."""
        assert get_mime_type_from_content_type("application/octet-stream") == "image/jpeg"

    def test_empty_content_type(self):
        """Failure: empty string defaults to image/jpeg."""
        assert get_mime_type_from_content_type("") == "image/jpeg"


# ---------------------------------------------------------------------------
# compress_image
# ---------------------------------------------------------------------------


class TestCompressImage:
    """Tests for compress_image()"""

    def _make_test_image(self, width=800, height=600, mode="RGB"):
        """Helper: create a test image as bytes."""
        img = Image.new(mode, (width, height), color=(100, 150, 200))
        buf = io.BytesIO()
        if mode in ("RGBA", "LA", "P"):
            img.save(buf, format="PNG")
        else:
            img.save(buf, format="JPEG")
        return buf.getvalue()

    def test_compress_rgb_image(self):
        """Happy path: RGB image is compressed to WebP."""
        image_bytes = self._make_test_image(800, 600, "RGB")
        compressed, mime = compress_image(image_bytes)

        assert mime == "image/webp"
        assert len(compressed) > 0
        # Verify it's a valid WebP by opening it
        img = Image.open(io.BytesIO(compressed))
        assert img.format == "WEBP"

    def test_compress_resizes_wide_image(self):
        """Happy path: image wider than THUMBNAIL_MAX_WIDTH is resized."""
        image_bytes = self._make_test_image(1200, 900, "RGB")
        compressed, mime = compress_image(image_bytes)

        img = Image.open(io.BytesIO(compressed))
        assert img.width == THUMBNAIL_MAX_WIDTH
        # Aspect ratio maintained
        expected_height = int(900 * (THUMBNAIL_MAX_WIDTH / 1200))
        assert img.height == expected_height

    def test_compress_small_image_not_resized(self):
        """Edge case: image smaller than max width is NOT resized."""
        image_bytes = self._make_test_image(400, 300, "RGB")
        compressed, mime = compress_image(image_bytes)

        img = Image.open(io.BytesIO(compressed))
        assert img.width == 400
        assert img.height == 300

    def test_compress_rgba_image(self):
        """Edge case: RGBA image is converted to RGB (white background)."""
        img = Image.new("RGBA", (200, 200), color=(100, 150, 200, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        compressed, mime = compress_image(image_bytes)
        assert mime == "image/webp"
        result_img = Image.open(io.BytesIO(compressed))
        assert result_img.mode == "RGB"

    def test_compress_invalid_image_returns_original(self):
        """Failure: invalid image data returns original bytes with jpeg mime."""
        bad_bytes = b"not an image at all"
        result_bytes, mime = compress_image(bad_bytes)

        assert result_bytes == bad_bytes
        assert mime == "image/jpeg"


# ---------------------------------------------------------------------------
# download_image (mocked aiohttp)
# ---------------------------------------------------------------------------


class TestDownloadImage:
    """Tests for download_image() with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_download_success(self):
        """Happy path: successful image download returns bytes and mime."""
        image_data = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # JPEG-like bytes

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {
            "Content-Type": "image/jpeg",
            "Content-Length": str(len(image_data)),
        }

        # Mock async iterator for content chunks
        async def mock_iter_chunked(chunk_size):
            yield image_data

        mock_response.content = MagicMock()
        mock_response.content.iter_chunked = mock_iter_chunked

        mock_session = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_ctx)

        result = await download_image(mock_session, "https://example.com/img.jpg")

        assert result is not None
        data, mime = result
        assert data == image_data
        assert mime == "image/jpeg"

    @pytest.mark.asyncio
    async def test_download_non_200_returns_none(self):
        """Failure: non-200 status returns None."""
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.headers = {"Content-Type": "text/html"}

        mock_session = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_ctx)

        result = await download_image(mock_session, "https://example.com/missing.jpg")
        assert result is None

    @pytest.mark.asyncio
    async def test_download_non_image_content_type_returns_none(self):
        """Failure: non-image content type returns None."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "text/html"}

        mock_session = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_ctx)

        result = await download_image(mock_session, "https://example.com/page.html")
        assert result is None

    @pytest.mark.asyncio
    async def test_download_content_length_too_large_returns_none(self):
        """Failure: Content-Length exceeding MAX_IMAGE_SIZE returns None."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {
            "Content-Type": "image/jpeg",
            "Content-Length": str(MAX_IMAGE_SIZE + 1),
        }

        mock_session = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_ctx)

        result = await download_image(mock_session, "https://example.com/huge.jpg")
        assert result is None

    @pytest.mark.asyncio
    async def test_download_timeout_returns_none(self):
        """Failure: timeout returns None."""
        mock_session = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_ctx)

        result = await download_image(mock_session, "https://example.com/slow.jpg")
        assert result is None


# ---------------------------------------------------------------------------
# download_image_as_base64
# ---------------------------------------------------------------------------


class TestDownloadImageAsBase64:
    """Tests for download_image_as_base64()"""

    @pytest.mark.asyncio
    async def test_returns_data_uri(self):
        """Happy path: returns a base64 data URI string."""
        # Create a real small image
        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        with patch(
            "app.services.news_image_cache.download_image",
            new_callable=AsyncMock,
            return_value=(image_bytes, "image/jpeg"),
        ):
            result = await download_image_as_base64(MagicMock(), "https://example.com/img.jpg")

        assert result is not None
        assert result.startswith("data:image/webp;base64,")

    @pytest.mark.asyncio
    async def test_empty_url_returns_none(self):
        """Edge case: empty URL returns None immediately."""
        result = await download_image_as_base64(MagicMock(), "")
        assert result is None

    @pytest.mark.asyncio
    async def test_download_failure_returns_none(self):
        """Failure: if download_image returns None, result is None."""
        with patch(
            "app.services.news_image_cache.download_image",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await download_image_as_base64(MagicMock(), "https://example.com/fail.jpg")

        assert result is None


# ---------------------------------------------------------------------------
# download_and_save_image
# ---------------------------------------------------------------------------


class TestDownloadAndSaveImage:
    """Tests for download_and_save_image()"""

    @pytest.mark.asyncio
    async def test_saves_webp_file(self, tmp_path):
        """Happy path: image is saved as .webp file and filename returned."""
        img = Image.new("RGB", (100, 100), color=(0, 255, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        with patch(
            "app.services.news_image_cache.download_image",
            new_callable=AsyncMock,
            return_value=(image_bytes, "image/jpeg"),
        ):
            with patch("app.services.news_image_cache.NEWS_IMAGES_DIR", tmp_path):
                result = await download_and_save_image(MagicMock(), "https://example.com/img.jpg", 42)

        assert result == "42.webp"
        assert (tmp_path / "42.webp").exists()
        assert (tmp_path / "42.webp").stat().st_size > 0

    @pytest.mark.asyncio
    async def test_empty_url_returns_none(self):
        """Edge case: empty URL returns None."""
        result = await download_and_save_image(MagicMock(), "", 1)
        assert result is None

    @pytest.mark.asyncio
    async def test_download_failure_returns_none(self):
        """Failure: download failure returns None."""
        with patch(
            "app.services.news_image_cache.download_image",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await download_and_save_image(MagicMock(), "https://example.com/fail.jpg", 1)

        assert result is None

    @pytest.mark.asyncio
    async def test_write_failure_returns_none(self, tmp_path):
        """Failure: filesystem write error returns None."""
        img = Image.new("RGB", (100, 100), color=(0, 0, 255))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        # Use a directory path that can't be written to
        bad_dir = tmp_path / "no_write"
        bad_dir.mkdir()

        with patch(
            "app.services.news_image_cache.download_image",
            new_callable=AsyncMock,
            return_value=(image_bytes, "image/jpeg"),
        ):
            with patch("app.services.news_image_cache.NEWS_IMAGES_DIR", bad_dir):
                # Make the file path a directory to force write error
                (bad_dir / "99.webp").mkdir()
                result = await download_and_save_image(MagicMock(), "https://example.com/img.jpg", 99)

        assert result is None


# ---------------------------------------------------------------------------
# download_images_batch
# ---------------------------------------------------------------------------


class TestDownloadImagesBatch:
    """Tests for download_images_batch()"""

    @pytest.mark.asyncio
    async def test_empty_urls_returns_empty_dict(self):
        """Edge case: empty list returns empty dict."""
        result = await download_images_batch([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_batch_with_none_url(self):
        """Edge case: None/empty URLs in list are handled."""
        # The function checks `if url:` for each item
        result = await download_images_batch([""])
        assert result == {"": None}
