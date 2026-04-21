"""
Tests for backend/app/middleware/public_rate_limit.py.

Verifies that public (unauthenticated) market-data endpoints are rate
limited per-IP, and that non-public paths pass through untouched. This
covers the code-quality sweep v2.160.4 Phase 2.5 finding.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.public_rate_limit import (
    PublicEndpointRateLimiter,
    _MAX_REQUESTS,
    _PUBLIC_PREFIXES,
)


@pytest.fixture(autouse=True)
def _reset_limiter_state():
    """Ensure each test starts with an empty IP bucket."""
    PublicEndpointRateLimiter._ip_timestamps.clear()
    yield
    PublicEndpointRateLimiter._ip_timestamps.clear()


def _build_app(public_paths: list[str], private_paths: list[str] | None = None) -> TestClient:
    """Build a minimal FastAPI app with the rate limiter middleware installed."""
    app = FastAPI()

    for path in public_paths:
        app.get(path)(lambda: {"ok": True})
    for path in private_paths or []:
        app.get(path)(lambda: {"ok": True})

    app.add_middleware(PublicEndpointRateLimiter)
    return TestClient(app)


class TestPublicRateLimitCoverage:
    """Phase 2.5 — every public market_data route must be in _PUBLIC_PREFIXES."""

    def test_market_data_routes_are_covered(self):
        """All public-ish market_data endpoints are covered by the limiter prefix list."""
        expected = {
            "/api/ticker/",
            "/api/prices/",
            "/api/candles",
            "/api/coins",
            "/api/market/btc-usd-price",
            "/api/market/eth-usd-price",
            "/api/product-precision/",
        }
        missing = expected - set(_PUBLIC_PREFIXES)
        assert not missing, f"Public market_data prefixes not rate-limited: {missing}"


class TestPublicEndpointRateLimiter:
    def test_allows_requests_under_the_limit(self):
        client = _build_app(public_paths=["/api/ticker/BTC-USD"])
        # Hit the endpoint a few times — must all be 200.
        for _ in range(5):
            resp = client.get("/api/ticker/BTC-USD")
            assert resp.status_code == 200

    def test_blocks_after_limit_with_429(self):
        client = _build_app(public_paths=["/api/ticker/BTC-USD"])
        for _ in range(_MAX_REQUESTS):
            assert client.get("/api/ticker/BTC-USD").status_code == 200
        # Next request from the same IP must be denied.
        blocked = client.get("/api/ticker/BTC-USD")
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers
        assert "Too many requests" in blocked.json()["detail"]

    def test_non_public_paths_are_not_limited(self):
        """A path outside _PUBLIC_PREFIXES bypasses the limiter entirely."""
        client = _build_app(
            public_paths=[],
            private_paths=["/api/bots"],  # authenticated path, not in the prefix list
        )
        for _ in range(_MAX_REQUESTS + 10):
            assert client.get("/api/bots").status_code == 200

    def test_separate_ips_get_separate_buckets(self):
        client = _build_app(public_paths=["/api/candles"])
        # Exhaust budget for IP A.
        for _ in range(_MAX_REQUESTS):
            assert (
                client.get(
                    "/api/candles", headers={"X-Forwarded-For": "1.1.1.1"}
                ).status_code
                == 200
            )
        assert (
            client.get(
                "/api/candles", headers={"X-Forwarded-For": "1.1.1.1"}
            ).status_code
            == 429
        )
        # IP B still has its full budget.
        assert (
            client.get(
                "/api/candles", headers={"X-Forwarded-For": "2.2.2.2"}
            ).status_code
            == 200
        )

    def test_prune_stale_removes_inactive_ips(self):
        """Housekeeping: prune_stale() clears IPs that have gone cold."""
        # Seed a bucket with only ancient timestamps.
        PublicEndpointRateLimiter._ip_timestamps["9.9.9.9"] = [0.0]
        pruned = PublicEndpointRateLimiter.prune_stale()
        assert pruned >= 1
        assert "9.9.9.9" not in PublicEndpointRateLimiter._ip_timestamps
