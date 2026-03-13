"""
IP-based rate limiter for public (unauthenticated) API endpoints.

Prevents DoS on endpoints that don't require authentication.
Runs as raw ASGI middleware for minimal overhead on non-matching paths.
"""

import time
from collections import defaultdict
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import JSONResponse

# Public path prefixes that should be rate-limited
_PUBLIC_PREFIXES = (
    "/api/ticker/",
    "/api/prices/",
    "/api/candles",
    "/api/coins",
    "/api/coin-icons/",
    "/api/market/btc-usd-price",
    "/api/market/eth-usd-price",
    "/api/product-precision/",
    "/api/version",
    "/api/brand",
)

_MAX_REQUESTS = 120   # per window
_WINDOW = 60.0        # 60 seconds
_STALE_SECONDS = 120.0  # prune entries older than this


class PublicEndpointRateLimiter:
    """ASGI middleware that rate-limits public endpoints by client IP."""

    _ip_timestamps: dict[str, list[float]] = defaultdict(list)

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if not any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            await self.app(scope, receive, send)
            return

        # Extract client IP (X-Forwarded-For from Nginx, fallback to direct)
        client_ip = None
        for header_name, header_value in scope.get("headers", []):
            if header_name == b"x-forwarded-for":
                client_ip = header_value.decode().split(",")[0].strip()
                break
        if not client_ip:
            client = scope.get("client")
            client_ip = client[0] if client else "unknown"

        now = time.time()
        cutoff = now - _WINDOW
        timestamps = self._ip_timestamps[client_ip]
        timestamps[:] = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= _MAX_REQUESTS:
            response = JSONResponse(
                {"detail": "Too many requests. Please slow down."},
                status_code=429,
                headers={"Retry-After": str(int(_WINDOW))},
            )
            await response(scope, receive, send)
            return

        timestamps.append(now)
        await self.app(scope, receive, send)

    @classmethod
    def prune_stale(cls) -> int:
        """Remove stale IP entries. Called by periodic cleanup job."""
        now = time.time()
        stale = [ip for ip, ts in cls._ip_timestamps.items()
                 if not ts or (now - max(ts)) > _STALE_SECONDS]
        for ip in stale:
            del cls._ip_timestamps[ip]
        return len(stale)
