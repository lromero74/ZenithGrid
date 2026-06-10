"""
Tests for SPA cache-control headers.

Stale cached index.html references content-hashed chunk files that no longer
exist after a rebuild — clients then boot from a missing bundle and render a
blank screen. index.html must always revalidate (no-cache); hashed assets are
immutable and may be cached forever.
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import FileResponse
from httpx import ASGITransport, AsyncClient

from app.static_cache import ASSET_CACHE_CONTROL, HTML_CACHE_CONTROL, CachedStaticFiles


@pytest.fixture
def spa_app(tmp_path):
    """Mini app mirroring main.py's SPA serving setup."""
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index-abc123.js").write_text("console.log('hi')")
    index_html = tmp_path / "index.html"
    index_html.write_text("<html><body>app</body></html>")

    app = FastAPI()
    app.mount("/assets", CachedStaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(str(index_html), headers={"Cache-Control": HTML_CACHE_CONTROL})

    return app


@pytest.mark.asyncio
async def test_hashed_assets_are_immutable(spa_app):
    """Happy path: content-hashed assets get a long-lived immutable cache header."""
    transport = ASGITransport(app=spa_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/assets/index-abc123.js")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == ASSET_CACHE_CONTROL
    assert "immutable" in resp.headers["cache-control"]


@pytest.mark.asyncio
async def test_index_html_is_no_cache(spa_app):
    """Happy path: the SPA shell must always be revalidated by the browser."""
    transport = ASGITransport(app=spa_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == HTML_CACHE_CONTROL


@pytest.mark.asyncio
async def test_missing_asset_is_404_not_index(spa_app):
    """Failure case: a deleted hashed chunk must 404, not silently serve HTML."""
    transport = ASGITransport(app=spa_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/assets/index-deleted.js")
    assert resp.status_code == 404
