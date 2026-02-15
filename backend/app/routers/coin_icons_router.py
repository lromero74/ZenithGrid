"""
Coin Icons Router

Proxies and caches cryptocurrency icons from CoinCap to avoid CORS issues.
Icons are cached locally on disk for fast subsequent requests.
"""

import logging
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/coin-icons", tags=["coin-icons"])

# Cache directory for coin icons
CACHE_DIR = Path(__file__).parent.parent.parent / "coin_icons_cache"
CACHE_DIR.mkdir(exist_ok=True)

# CoinCap API endpoint for coin images
COINCAP_URL = "https://assets.coincap.io/assets/icons"

# HTTP client timeout
TIMEOUT = 10.0


@router.get("/{symbol}")
async def get_coin_icon(symbol: str) -> Response:
    """
    Get a cryptocurrency icon by symbol.

    Proxies requests to CoinCap and caches the result locally.
    Returns a fallback SVG if the icon is not available.
    """
    # Validate symbol is alphanumeric only (prevent path traversal)
    if not re.match(r'^[a-zA-Z0-9]+$', symbol):
        raise HTTPException(status_code=400, detail="Invalid symbol")

    # Normalize symbol
    symbol_lower = symbol.lower().strip()
    cache_file = CACHE_DIR / f"{symbol_lower}.png"

    # Check cache first
    if cache_file.exists():
        return FileResponse(
            cache_file,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},  # Cache for 24h
        )

    # Fetch from CoinCap
    url = f"{COINCAP_URL}/{symbol_lower}@2x.png"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(url)

            if response.status_code == 200:
                # Cache the image
                cache_file.write_bytes(response.content)
                logger.info(f"Cached coin icon: {symbol_lower}")

                return Response(
                    content=response.content,
                    media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"},
                )

    except Exception as e:
        logger.debug(f"Failed to fetch icon for {symbol}: {e}")

    # Return fallback SVG with first letter (already validated as alphanumeric)
    letter = symbol[0].upper() if symbol else "?"
    fallback_svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
        <circle cx="32" cy="32" r="30" fill="#3b82f6" opacity="0.2"/>
        <text x="32" y="40" font-family="sans-serif" font-size="24" font-weight="bold" fill="#3b82f6" text-anchor="middle">{letter}</text>
    </svg>'''

    return Response(
        content=fallback_svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=3600"},  # Cache fallback for 1h
    )
