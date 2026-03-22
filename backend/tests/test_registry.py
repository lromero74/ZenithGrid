"""
Tests for app/registry.py

TDD: these tests are written BEFORE implementation and must initially FAIL
with ModuleNotFoundError: No module named 'app.registry'.

Covers:
- _default_registry exists and is ServiceRegistry
- Each field holds the correct module-level singleton (identity check)
- get_registry() returns _default_registry (same object, multiple calls)
- Protocol isinstance checks pass for broadcast, rate_limiter, credentials
- ServiceRegistry can be constructed with mock replacements (the swap point test)
"""
import pytest
from unittest.mock import MagicMock


class TestDefaultRegistry:

    def test_default_registry_is_service_registry(self):
        """Happy path: _default_registry is a ServiceRegistry instance."""
        from app.registry import ServiceRegistry, _default_registry
        assert isinstance(_default_registry, ServiceRegistry)

    def test_event_bus_is_module_singleton(self):
        """Happy path: registry.event_bus is the same object as the event_bus singleton."""
        from app.registry import _default_registry
        from app.event_bus import event_bus, InProcessEventBus
        assert _default_registry.event_bus is event_bus
        assert isinstance(_default_registry.event_bus, InProcessEventBus)

    def test_broadcast_is_module_singleton(self):
        """Happy path: registry.broadcast is the same object as broadcast_backend."""
        from app.registry import _default_registry
        from app.services.broadcast_backend import broadcast_backend, InProcessBroadcast
        assert _default_registry.broadcast is broadcast_backend
        assert isinstance(_default_registry.broadcast, InProcessBroadcast)

    def test_rate_limiter_is_module_singleton(self):
        """Happy path: registry.rate_limiter is the same object as rate_limit_backend."""
        from app.registry import _default_registry
        from app.auth_routers.rate_limit_backend import rate_limit_backend, PostgresRateLimitBackend
        assert _default_registry.rate_limiter is rate_limit_backend
        assert isinstance(_default_registry.rate_limiter, PostgresRateLimitBackend)

    def test_credentials_is_module_singleton(self):
        """Happy path: registry.credentials is the same object as credentials_provider."""
        from app.registry import _default_registry
        from app.services.credentials_provider import credentials_provider, LocalCredentialsProvider
        assert _default_registry.credentials is credentials_provider
        assert isinstance(_default_registry.credentials, LocalCredentialsProvider)


class TestGetRegistry:

    def test_get_registry_returns_service_registry(self):
        """Happy path: get_registry() returns a ServiceRegistry."""
        from app.registry import get_registry, ServiceRegistry
        registry = get_registry()
        assert isinstance(registry, ServiceRegistry)

    def test_get_registry_returns_same_singleton(self):
        """Happy path: get_registry() returns the same object on every call."""
        from app.registry import get_registry
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2


class TestProtocolCompliance:

    def test_broadcast_satisfies_protocol(self):
        """Happy path: registry.broadcast satisfies BroadcastBackend Protocol."""
        from app.registry import _default_registry
        from app.services.broadcast_backend import BroadcastBackend
        assert isinstance(_default_registry.broadcast, BroadcastBackend)

    def test_rate_limiter_satisfies_protocol(self):
        """Happy path: registry.rate_limiter satisfies RateLimitBackend Protocol."""
        from app.registry import _default_registry
        from app.auth_routers.rate_limit_backend import RateLimitBackend
        assert isinstance(_default_registry.rate_limiter, RateLimitBackend)

    def test_credentials_satisfies_protocol(self):
        """Happy path: registry.credentials satisfies CredentialsProvider Protocol."""
        from app.registry import _default_registry
        from app.services.credentials_provider import CredentialsProvider
        assert isinstance(_default_registry.credentials, CredentialsProvider)


class TestSwapPoint:

    def test_custom_registry_with_mocks(self):
        """Edge case: ServiceRegistry accepts mock replacements — the Phase 3 swap point."""
        from app.registry import ServiceRegistry
        from app.event_bus import InProcessEventBus
        mock_bus = MagicMock(spec=InProcessEventBus)
        mock_broadcast = MagicMock()
        mock_rl = MagicMock()
        mock_creds = MagicMock()

        registry = ServiceRegistry(
            event_bus=mock_bus,
            broadcast=mock_broadcast,
            rate_limiter=mock_rl,
            credentials=mock_creds,
        )

        assert registry.event_bus is mock_bus
        assert registry.broadcast is mock_broadcast
        assert registry.rate_limiter is mock_rl
        assert registry.credentials is mock_creds
