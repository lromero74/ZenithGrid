"""
Tests for backend/app/middleware/public_rate_limit.py

Covers:
- PublicEndpointRateLimiter middleware:
  - Passes through non-HTTP scopes (websocket)
  - Passes through non-public paths
  - Rate limits public paths after _MAX_REQUESTS
  - Extracts client IP from X-Forwarded-For header
  - Falls back to scope["client"] IP
  - Falls back to "unknown" when no client info
  - Returns 429 with Retry-After header when limited
  - prune_stale() class method removes old entries
"""

import time
import pytest
from unittest.mock import AsyncMock

from app.middleware.public_rate_limit import (
    PublicEndpointRateLimiter,
    _PUBLIC_PREFIXES,
    _MAX_REQUESTS,
    _WINDOW,
    _STALE_SECONDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scope(path="/api/ticker/BTC-USD", client_ip="192.168.1.1",
                headers=None, scope_type="http"):
    """Build a minimal ASGI scope dict."""
    scope = {
        "type": scope_type,
        "path": path,
        "client": (client_ip, 12345) if client_ip else None,
        "headers": headers or [],
    }
    return scope


def _make_xff_headers(ip):
    """Build headers list with X-Forwarded-For."""
    return [(b"x-forwarded-for", ip.encode())]


async def _collect_response(app_or_response, scope, receive, send):
    """Run an ASGI app and collect the response status/headers."""
    response_started = {}

    async def capture_send(message):
        if message["type"] == "http.response.start":
            response_started["status"] = message["status"]
            response_started["headers"] = dict(message.get("headers", []))
        # Also handle body
        await send(message)

    await app_or_response(scope, receive, capture_send)
    return response_started


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_rate_limit_state():
    """Reset shared class state before each test."""
    PublicEndpointRateLimiter._ip_timestamps.clear()
    yield
    PublicEndpointRateLimiter._ip_timestamps.clear()


@pytest.fixture
def inner_app():
    """A no-op ASGI inner app that returns 200."""
    async def app(scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [],
        })
        await send({
            "type": "http.response.body",
            "body": b"OK",
        })
    return app


@pytest.fixture
def middleware(inner_app):
    """Create the rate limiter middleware wrapping the inner app."""
    return PublicEndpointRateLimiter(inner_app)


# ---------------------------------------------------------------------------
# Non-matching paths and scopes — should pass through
# ---------------------------------------------------------------------------


class TestPassThrough:
    """Tests for requests that should NOT be rate limited."""

    @pytest.mark.asyncio
    async def test_non_http_scope_passes_through(self, middleware):
        """Happy path: websocket scopes should pass through without rate limiting."""
        scope = _make_scope(scope_type="websocket")
        receive = AsyncMock()
        send = AsyncMock()

        # The inner app will be called directly
        await middleware(scope, receive, send)

        # Inner app was called (send was invoked)
        assert send.called

    @pytest.mark.asyncio
    async def test_non_public_path_passes_through(self, middleware):
        """Happy path: non-public paths should not be rate limited."""
        scope = _make_scope(path="/api/bots/")
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        assert send.called

    @pytest.mark.asyncio
    async def test_auth_endpoint_passes_through(self, middleware):
        """Happy path: auth endpoint is not in public prefixes."""
        scope = _make_scope(path="/api/auth/login")
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        assert send.called

    @pytest.mark.asyncio
    async def test_root_path_passes_through(self, middleware):
        """Edge case: root path should not be rate limited."""
        scope = _make_scope(path="/")
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        assert send.called


# ---------------------------------------------------------------------------
# Public path matching
# ---------------------------------------------------------------------------


class TestPublicPathMatching:
    """Tests for path matching against _PUBLIC_PREFIXES."""

    @pytest.mark.asyncio
    async def test_ticker_path_is_rate_limited(self, middleware):
        """Happy path: /api/ticker/ is a public prefix."""
        scope = _make_scope(path="/api/ticker/BTC-USD")
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        # Should pass on first request
        assert send.called
        # But should have recorded the timestamp
        assert len(PublicEndpointRateLimiter._ip_timestamps) > 0

    @pytest.mark.asyncio
    async def test_version_path_is_rate_limited(self, middleware):
        """Happy path: /api/version is a public prefix."""
        scope = _make_scope(path="/api/version")
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        assert len(PublicEndpointRateLimiter._ip_timestamps) > 0

    @pytest.mark.asyncio
    async def test_brand_path_is_rate_limited(self, middleware):
        """Happy path: /api/brand is a public prefix."""
        scope = _make_scope(path="/api/brand")
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        assert len(PublicEndpointRateLimiter._ip_timestamps) > 0

    def test_public_prefixes_are_all_api_paths(self):
        """Sanity: all public prefixes should start with /api/."""
        for prefix in _PUBLIC_PREFIXES:
            assert prefix.startswith("/api/"), (
                f"Public prefix '{prefix}' doesn't start with /api/"
            )


# ---------------------------------------------------------------------------
# IP extraction
# ---------------------------------------------------------------------------


class TestIPExtraction:
    """Tests for client IP extraction logic."""

    @pytest.mark.asyncio
    async def test_ip_from_x_forwarded_for(self, middleware):
        """Happy path: should extract IP from X-Forwarded-For header."""
        headers = _make_xff_headers("10.0.0.1")
        scope = _make_scope(path="/api/ticker/X", client_ip="192.168.1.1", headers=headers)
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        assert "10.0.0.1" in PublicEndpointRateLimiter._ip_timestamps

    @pytest.mark.asyncio
    async def test_ip_from_x_forwarded_for_multiple_ips(self, middleware):
        """Edge case: X-Forwarded-For with multiple IPs should use the first."""
        headers = [(b"x-forwarded-for", b"1.2.3.4, 5.6.7.8, 9.10.11.12")]
        scope = _make_scope(path="/api/ticker/X", headers=headers)
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        assert "1.2.3.4" in PublicEndpointRateLimiter._ip_timestamps

    @pytest.mark.asyncio
    async def test_ip_from_scope_client_fallback(self, middleware):
        """Happy path: falls back to scope client when no XFF header."""
        scope = _make_scope(path="/api/ticker/X", client_ip="172.16.0.1")
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        assert "172.16.0.1" in PublicEndpointRateLimiter._ip_timestamps

    @pytest.mark.asyncio
    async def test_ip_unknown_when_no_client(self, middleware):
        """Edge case: no XFF and no client tuple should use 'unknown'."""
        scope = _make_scope(path="/api/ticker/X", client_ip=None)
        scope["client"] = None
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        assert "unknown" in PublicEndpointRateLimiter._ip_timestamps


# ---------------------------------------------------------------------------
# Rate limiting behavior
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Tests for the rate limiting enforcement."""

    @pytest.mark.asyncio
    async def test_allows_requests_under_limit(self, middleware):
        """Happy path: should allow up to _MAX_REQUESTS in a window."""
        scope = _make_scope(path="/api/ticker/X", client_ip="10.0.0.1")
        receive = AsyncMock()

        for i in range(_MAX_REQUESTS):
            send = AsyncMock()
            await middleware(scope, receive, send)
            # Inner app should have been called (200)
            calls = [c for c in send.call_args_list
                     if c[0][0].get("type") == "http.response.start"]
            assert calls[0][0][0]["status"] == 200

    @pytest.mark.asyncio
    async def test_blocks_after_exceeding_limit(self, middleware):
        """Failure: should return 429 after _MAX_REQUESTS."""
        scope = _make_scope(path="/api/ticker/X", client_ip="10.0.0.2")
        receive = AsyncMock()

        # Fill up the bucket
        for _ in range(_MAX_REQUESTS):
            send = AsyncMock()
            await middleware(scope, receive, send)

        # Next request should be blocked
        send = AsyncMock()
        await middleware(scope, receive, send)

        calls = [c for c in send.call_args_list
                 if c[0][0].get("type") == "http.response.start"]
        assert calls[0][0][0]["status"] == 429

    @pytest.mark.asyncio
    async def test_429_includes_retry_after_header(self, middleware):
        """Failure: 429 response should include Retry-After header."""
        scope = _make_scope(path="/api/ticker/X", client_ip="10.0.0.3")
        receive = AsyncMock()

        # Fill up the bucket
        for _ in range(_MAX_REQUESTS):
            send = AsyncMock()
            await middleware(scope, receive, send)

        # Trigger 429
        send = AsyncMock()
        await middleware(scope, receive, send)

        start_calls = [c for c in send.call_args_list
                       if c[0][0].get("type") == "http.response.start"]
        headers = dict(start_calls[0][0][0].get("headers", []))
        assert b"retry-after" in headers
        assert headers[b"retry-after"] == str(int(_WINDOW)).encode()

    @pytest.mark.asyncio
    async def test_different_ips_have_separate_limits(self, middleware):
        """Edge case: different IPs should have independent rate limits."""
        receive = AsyncMock()

        # Fill up IP A
        for _ in range(_MAX_REQUESTS):
            scope = _make_scope(path="/api/ticker/X", client_ip="1.1.1.1")
            send = AsyncMock()
            await middleware(scope, receive, send)

        # IP B should still be allowed
        scope = _make_scope(path="/api/ticker/X", client_ip="2.2.2.2")
        send = AsyncMock()
        await middleware(scope, receive, send)

        calls = [c for c in send.call_args_list
                 if c[0][0].get("type") == "http.response.start"]
        assert calls[0][0][0]["status"] == 200

    @pytest.mark.asyncio
    async def test_old_timestamps_are_pruned_within_window(self, middleware):
        """Edge case: timestamps outside the window should be discarded."""
        ip = "10.0.0.4"
        now = time.time()
        # Pre-fill with old timestamps (outside window)
        PublicEndpointRateLimiter._ip_timestamps[ip] = [
            now - _WINDOW - 10 for _ in range(_MAX_REQUESTS)
        ]

        # New request should succeed because old ones are outside window
        scope = _make_scope(path="/api/ticker/X", client_ip=ip)
        receive = AsyncMock()
        send = AsyncMock()
        await middleware(scope, receive, send)

        calls = [c for c in send.call_args_list
                 if c[0][0].get("type") == "http.response.start"]
        assert calls[0][0][0]["status"] == 200


# ---------------------------------------------------------------------------
# prune_stale
# ---------------------------------------------------------------------------


class TestPruneStale:
    """Tests for the prune_stale() class method."""

    def test_prune_stale_removes_old_entries(self):
        """Happy path: entries older than _STALE_SECONDS should be removed."""
        old_time = time.time() - _STALE_SECONDS - 10
        PublicEndpointRateLimiter._ip_timestamps["old-ip"] = [old_time]

        removed = PublicEndpointRateLimiter.prune_stale()

        assert removed == 1
        assert "old-ip" not in PublicEndpointRateLimiter._ip_timestamps

    def test_prune_stale_keeps_recent_entries(self):
        """Happy path: recent entries should not be pruned."""
        recent_time = time.time() - 5
        PublicEndpointRateLimiter._ip_timestamps["recent-ip"] = [recent_time]

        removed = PublicEndpointRateLimiter.prune_stale()

        assert removed == 0
        assert "recent-ip" in PublicEndpointRateLimiter._ip_timestamps

    def test_prune_stale_removes_empty_lists(self):
        """Edge case: IPs with empty timestamp lists should be pruned."""
        PublicEndpointRateLimiter._ip_timestamps["empty-ip"] = []

        removed = PublicEndpointRateLimiter.prune_stale()

        assert removed == 1
        assert "empty-ip" not in PublicEndpointRateLimiter._ip_timestamps

    def test_prune_stale_mixed_entries(self):
        """Edge case: mix of stale and fresh entries."""
        now = time.time()
        PublicEndpointRateLimiter._ip_timestamps["stale"] = [now - _STALE_SECONDS - 50]
        PublicEndpointRateLimiter._ip_timestamps["fresh"] = [now - 1]
        PublicEndpointRateLimiter._ip_timestamps["empty"] = []

        removed = PublicEndpointRateLimiter.prune_stale()

        assert removed == 2  # stale + empty
        assert "fresh" in PublicEndpointRateLimiter._ip_timestamps
        assert "stale" not in PublicEndpointRateLimiter._ip_timestamps
        assert "empty" not in PublicEndpointRateLimiter._ip_timestamps

    def test_prune_stale_returns_zero_when_nothing_to_prune(self):
        """Edge case: no entries at all should return 0."""
        removed = PublicEndpointRateLimiter.prune_stale()
        assert removed == 0

    def test_prune_stale_uses_max_timestamp(self):
        """Edge case: entry with mix of old and recent timestamps uses max."""
        now = time.time()
        PublicEndpointRateLimiter._ip_timestamps["mixed-ts"] = [
            now - _STALE_SECONDS - 100,  # old
            now - 1,                       # recent
        ]

        removed = PublicEndpointRateLimiter.prune_stale()

        assert removed == 0  # max timestamp is recent, so not stale
        assert "mixed-ts" in PublicEndpointRateLimiter._ip_timestamps


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Tests for module-level constants."""

    def test_max_requests_is_positive(self):
        """Sanity: _MAX_REQUESTS should be a positive integer."""
        assert _MAX_REQUESTS > 0
        assert isinstance(_MAX_REQUESTS, int)

    def test_window_is_positive(self):
        """Sanity: _WINDOW should be a positive number."""
        assert _WINDOW > 0

    def test_stale_seconds_greater_than_window(self):
        """Sanity: _STALE_SECONDS should be >= _WINDOW."""
        assert _STALE_SECONDS >= _WINDOW
