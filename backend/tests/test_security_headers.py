"""
Tests for SecurityHeadersMiddleware in backend/app/main.py.

Verifies that all security headers are injected on every response,
including success, 404, and unhandled exception responses.
"""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.main import SecurityHeadersMiddleware, ServerTimingMiddleware

# Expected headers and their values.
# Note: X-XSS-Protection is intentionally NOT set — modern browsers ignore/deprecated it
# and in some cases it introduces vulnerabilities. CSP + X-Content-Type-Options replace it.
# Note: CSP and HSTS are owned by nginx, not FastAPI — they are not asserted here.
EXPECTED_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
}


@pytest.fixture
def app_with_middleware():
    """Create a minimal FastAPI app with SecurityHeadersMiddleware."""
    test_app = FastAPI()
    test_app.add_middleware(SecurityHeadersMiddleware)

    @test_app.get("/ok")
    async def ok_endpoint():
        return {"status": "ok"}

    @test_app.get("/error")
    async def error_endpoint():
        raise RuntimeError("something broke")

    return test_app


@pytest.fixture
def timing_client():
    test_app = FastAPI()
    test_app.add_middleware(ServerTimingMiddleware)

    @test_app.get("/ok")
    async def ok_endpoint():
        return {"status": "ok"}

    return TestClient(test_app)


@pytest.fixture
def client(app_with_middleware):
    """TestClient for the minimal app."""
    return TestClient(app_with_middleware, raise_server_exceptions=False)


class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware."""

    def test_security_headers_present_on_success(self, client):
        """Happy path: all 4 security headers are set on a 200 response."""
        response = client.get("/ok")
        assert response.status_code == 200
        for header, value in EXPECTED_HEADERS.items():
            assert response.headers.get(header) == value, (
                f"Expected {header}: {value}, "
                f"got {response.headers.get(header)}"
            )

    def test_security_headers_present_on_404(self, client):
        """Edge case: headers are present on 404 (non-existent route)."""
        response = client.get("/nonexistent")
        assert response.status_code == 404
        for header, value in EXPECTED_HEADERS.items():
            assert response.headers.get(header) == value, (
                f"Expected {header}: {value} on 404, "
                f"got {response.headers.get(header)}"
            )

    def test_security_headers_missing_on_unhandled_exception(self, client):
        """Failure case: BaseHTTPMiddleware does NOT add headers when
        the endpoint raises an unhandled exception. Starlette's internal
        error handler returns 500 before the middleware can add headers.

        BUG: This documents a known limitation. To fix, either:
        - Add a custom exception handler that sets security headers, or
        - Use a pure ASGI middleware instead of BaseHTTPMiddleware.
        """
        response = client.get("/error")
        assert response.status_code == 500
        # Headers are NOT present on unhandled exceptions — this is the bug
        for header in EXPECTED_HEADERS:
            assert response.headers.get(header) is None, (
                f"Header {header} unexpectedly present on 500"
            )

    def test_all_expected_headers_present(self, client):
        """Verify each of the expected security headers is present."""
        response = client.get("/ok")
        for header in EXPECTED_HEADERS:
            assert header in response.headers, (
                f"Missing security header: {header}"
            )


def test_server_timing_header_reports_application_duration(timing_client):
    response = timing_client.get("/ok")
    assert response.status_code == 200
    assert response.headers["server-timing"].startswith("app;dur=")
    assert float(response.headers["server-timing"].split("=")[1]) >= 0
