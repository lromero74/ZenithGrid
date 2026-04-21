"""
Tests for backend/app/routers/coin_icons_router.py

Covers:
- GET /api/coin-icons/{symbol} — happy path (cached hit, remote fetch, fallback)
- Input validation (path traversal guard)
- Disk-fill guard (MAX_CACHED_ICONS)
- Remote failure → fallback SVG cached on disk
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse, Response


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Point the router's CACHE_DIR at a tmp directory so tests don't touch disk state."""
    import app.routers.coin_icons_router as mod

    fake_dir = tmp_path / "coin_icons_cache"
    fake_dir.mkdir()
    monkeypatch.setattr(mod, "CACHE_DIR", fake_dir)
    return fake_dir


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestSymbolValidation:
    """Reject non-alphanumeric symbols to prevent path traversal."""

    @pytest.mark.asyncio
    async def test_rejects_path_traversal(self, isolated_cache):
        from app.routers.coin_icons_router import get_coin_icon

        with pytest.raises(HTTPException) as exc:
            await get_coin_icon(symbol="../etc/passwd")
        assert exc.value.status_code == 400
        assert "Invalid symbol" in exc.value.detail

    @pytest.mark.asyncio
    async def test_rejects_symbol_with_special_chars(self, isolated_cache):
        from app.routers.coin_icons_router import get_coin_icon

        with pytest.raises(HTTPException) as exc:
            await get_coin_icon(symbol="btc$")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rejects_symbol_with_slash(self, isolated_cache):
        from app.routers.coin_icons_router import get_coin_icon

        with pytest.raises(HTTPException) as exc:
            await get_coin_icon(symbol="btc/eth")
        assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Cache hits
# ---------------------------------------------------------------------------


class TestCacheHits:
    """Returning files already in the cache directory without network calls."""

    @pytest.mark.asyncio
    async def test_returns_cached_png(self, isolated_cache):
        from app.routers.coin_icons_router import get_coin_icon

        cached = isolated_cache / "btc.png"
        cached.write_bytes(b"fake-png-bytes")

        result = await get_coin_icon(symbol="BTC")

        assert isinstance(result, FileResponse)
        assert result.media_type == "image/png"
        assert Path(result.path) == cached
        assert result.headers["cache-control"] == "public, max-age=86400"

    @pytest.mark.asyncio
    async def test_returns_cached_svg_fallback(self, isolated_cache):
        from app.routers.coin_icons_router import get_coin_icon

        cached = isolated_cache / "foo.svg"
        cached.write_text("<svg>cached-fallback</svg>")

        result = await get_coin_icon(symbol="FOO")

        assert isinstance(result, FileResponse)
        assert result.media_type == "image/svg+xml"
        assert Path(result.path) == cached

    @pytest.mark.asyncio
    async def test_png_preferred_over_svg_when_both_exist(self, isolated_cache):
        """Edge: if both .png and .svg exist, .png wins (ordering in code)."""
        from app.routers.coin_icons_router import get_coin_icon

        (isolated_cache / "eth.png").write_bytes(b"real-png")
        (isolated_cache / "eth.svg").write_text("<svg>fallback</svg>")

        result = await get_coin_icon(symbol="eth")
        assert result.media_type == "image/png"


# ---------------------------------------------------------------------------
# Remote fetch success
# ---------------------------------------------------------------------------


class TestRemoteFetchSuccess:
    """Happy path: symbol not cached → fetch from CoinCap → cache + return."""

    @pytest.mark.asyncio
    async def test_successful_fetch_caches_and_returns_png(self, isolated_cache):
        from app.routers import coin_icons_router as mod

        # Mock httpx.AsyncClient context manager + .get
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.content = b"remote-png-bytes"

        fake_client = MagicMock()
        fake_client.get = AsyncMock(return_value=fake_response)
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(mod.httpx, "AsyncClient", return_value=fake_client):
            result = await mod.get_coin_icon(symbol="ada")

        assert isinstance(result, Response)
        assert result.media_type == "image/png"
        assert result.body == b"remote-png-bytes"

        # Verify cache file was written
        cached = isolated_cache / "ada.png"
        assert cached.exists()
        assert cached.read_bytes() == b"remote-png-bytes"

        # Verify the URL used lower-cased @2x form
        called_url = fake_client.get.call_args[0][0]
        assert called_url.endswith("/ada@2x.png")


# ---------------------------------------------------------------------------
# Remote fetch failure → fallback SVG
# ---------------------------------------------------------------------------


class TestFallbackSVG:
    """When remote fetch fails or 404s, return (and cache) a letter-SVG."""

    @pytest.mark.asyncio
    async def test_network_exception_returns_cached_fallback(self, isolated_cache):
        from app.routers import coin_icons_router as mod

        fake_client = MagicMock()
        fake_client.get = AsyncMock(side_effect=httpx.ConnectError("no network"))
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(mod.httpx, "AsyncClient", return_value=fake_client):
            result = await mod.get_coin_icon(symbol="xyz")

        assert isinstance(result, Response)
        assert result.media_type == "image/svg+xml"
        body = result.body.decode()
        assert "<svg" in body
        assert ">X<" in body  # Letter from symbol uppercased

        # Fallback is persisted to disk for cache-reuse on next hit
        cached = isolated_cache / "xyz.svg"
        assert cached.exists()
        assert "<svg" in cached.read_text()

    @pytest.mark.asyncio
    async def test_non_200_status_falls_back_to_svg(self, isolated_cache):
        """Edge: CoinCap returns 404 → we still get a letter-SVG."""
        from app.routers import coin_icons_router as mod

        resp = MagicMock()
        resp.status_code = 404
        resp.content = b""

        fake_client = MagicMock()
        fake_client.get = AsyncMock(return_value=resp)
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(mod.httpx, "AsyncClient", return_value=fake_client):
            result = await mod.get_coin_icon(symbol="notreal")

        assert result.media_type == "image/svg+xml"
        assert "<svg" in result.body.decode()
        # No .png was cached (remote failure)
        assert not (isolated_cache / "notreal.png").exists()


# ---------------------------------------------------------------------------
# Disk-fill guard
# ---------------------------------------------------------------------------


class TestDiskFillGuard:
    """Refuse to cache beyond MAX_CACHED_ICONS to prevent enumeration attacks."""

    @pytest.mark.asyncio
    async def test_over_limit_returns_inline_svg_without_caching(self, isolated_cache, monkeypatch):
        from app.routers import coin_icons_router as mod

        # Lower the cap so the test stays fast
        monkeypatch.setattr(mod, "MAX_CACHED_ICONS", 3)

        # Fill cache to the cap
        for i in range(3):
            (isolated_cache / f"coin{i}.png").write_bytes(b"x")

        # Network patched but should never be called when over limit
        fake_client = MagicMock()
        fake_client.get = AsyncMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(mod.httpx, "AsyncClient", return_value=fake_client):
            result = await mod.get_coin_icon(symbol="zzz")

        assert result.media_type == "image/svg+xml"
        body = result.body.decode()
        assert "<svg" in body
        assert ">Z<" in body
        # No cache write
        assert not (isolated_cache / "zzz.png").exists()
        assert not (isolated_cache / "zzz.svg").exists()
        # And network was not hit
        fake_client.get.assert_not_called()
