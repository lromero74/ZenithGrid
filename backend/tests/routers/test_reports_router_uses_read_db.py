"""
Tests that analytics GET endpoints in reports_router use get_read_db,
and that write endpoints continue to use get_db.

We verify this by inspecting the FastAPI dependency tree registered on each
endpoint — if get_read_db is in the dependency set for a GET endpoint, the
routing is correct.
"""
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.database import get_db, get_read_db


def _get_direct_dep_callables(route: APIRoute) -> set:
    """Collect only the direct (top-level) dependency callables of a route.

    We intentionally do NOT recurse into sub-dependencies because get_current_user
    itself declares Depends(get_db) internally, which would make get_db appear as
    a transitive dep of every endpoint. We only care about what the endpoint
    function directly declares.
    """
    return {d.call for d in route.dependant.dependencies if d.call is not None}


def _find_route(app: FastAPI, method: str, path: str) -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and method in route.methods and route.path == path:
            return route
    raise AssertionError(f"Route {method} {path} not found")


@pytest.fixture
def app():
    """Import the FastAPI app for dependency inspection."""
    from app.main import app as _app
    return _app


class TestReportsRouterReadEndpointsUseReadDb:
    """GET endpoints that are read-only must use get_read_db, not get_db."""

    @pytest.mark.parametrize("path", [
        "/api/reports/goals",
        "/api/reports/schedules",
        "/api/reports/history",
    ])
    def test_get_endpoint_uses_get_read_db(self, app, path):
        """Happy path: GET list endpoints declare get_read_db as a dependency."""
        route = _find_route(app, "GET", path)
        deps = _get_direct_dep_callables(route)
        assert get_read_db in deps, (
            f"GET {path} should use get_read_db but found: {deps}"
        )
        assert get_db not in deps, (
            f"GET {path} should NOT use get_db but it does"
        )

    @pytest.mark.parametrize("path", [
        "/api/reports/goals",
        "/api/reports/schedules",
    ])
    def test_post_endpoint_uses_get_db(self, app, path):
        """Edge case: POST write endpoints must still use get_db."""
        route = _find_route(app, "POST", path)
        deps = _get_direct_dep_callables(route)
        assert get_db in deps, (
            f"POST {path} should use get_db but found: {deps}"
        )
        assert get_read_db not in deps, (
            f"POST {path} should NOT use get_read_db but it does"
        )


class TestAccountValueRouterReadEndpointsUseReadDb:
    """GET endpoints in account_value_router must use get_read_db."""

    @pytest.mark.parametrize("path", [
        "/api/account-value/history",
        "/api/account-value/latest",
        "/api/account-value/activity",
    ])
    def test_get_endpoint_uses_get_read_db(self, app, path):
        """Happy path: read GET endpoints use get_read_db."""
        route = _find_route(app, "GET", path)
        deps = _get_direct_dep_callables(route)
        assert get_read_db in deps, (
            f"GET {path} should use get_read_db but found: {deps}"
        )

    def test_capture_post_endpoint_uses_get_db(self, app):
        """Failure case: POST /capture is a write endpoint and must use get_db."""
        route = _find_route(app, "POST", "/api/account-value/capture")
        deps = _get_direct_dep_callables(route)
        assert get_db in deps
        assert get_read_db not in deps
