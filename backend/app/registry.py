"""
ServiceRegistry — Phase 2.2 of the scalability roadmap.

Single injection point for all service backends. Routers receive a
ServiceRegistry via Depends(get_registry) instead of importing singletons
directly, making Phase 3 backend swaps a one-line config change.

Today: all four fields hold in-process / local implementations.
Phase 3: reassign _default_registry at startup to switch all backends.

Usage in a router:
    from app.registry import get_registry, ServiceRegistry

    @router.post("/some-endpoint")
    async def handler(
        registry: ServiceRegistry = Depends(get_registry),
        db: AsyncSession = Depends(get_db),
    ):
        client = await registry.credentials.get_exchange_client(account_id, db=db)
        await registry.broadcast.send_to_user(user_id, {"type": "update"})
        await registry.event_bus.publish("order.filled", payload)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.event_bus import InProcessEventBus, event_bus as _event_bus
from app.services.broadcast_backend import BroadcastBackend, broadcast_backend as _broadcast_backend
from app.auth_routers.rate_limit_backend import (
    RateLimitBackend,
    rate_limit_backend as _rate_limit_backend,
)
from app.services.credentials_provider import (
    CredentialsProvider,
    credentials_provider as _credentials_provider,
)


@dataclass
class ServiceRegistry:
    """Composable holder for all service backends.

    Fields use the Protocol types (BroadcastBackend, RateLimitBackend,
    CredentialsProvider) for structural typing. event_bus is typed as the
    concrete InProcessEventBus until an EventBus Protocol is defined in
    Phase 3 (when NATS replaces the in-process bus).

    Phase 3 swap (single statement at app startup):
        import app.registry as _reg
        _reg._default_registry = ServiceRegistry(
            event_bus=NATSEventBus(nats_url),
            broadcast=RedisBroadcast(redis_url),
            rate_limiter=RedisRateLimitBackend(redis_url),
            credentials=RemoteCredentialsProvider(creds_url),
        )
    """
    event_bus: InProcessEventBus     # swap for NATSEventBus in Phase 3
    broadcast: BroadcastBackend
    rate_limiter: RateLimitBackend
    credentials: CredentialsProvider


# Default registry — pre-populated with current in-process singletons.
# Populated at import time (same pattern as event_bus, broadcast_backend, etc.).
_default_registry: ServiceRegistry = ServiceRegistry(
    event_bus=_event_bus,
    broadcast=_broadcast_backend,
    rate_limiter=_rate_limit_backend,
    credentials=_credentials_provider,
)


def get_registry() -> ServiceRegistry:
    """FastAPI dependency — returns the application-wide service registry.

    Sync (no yield needed — no resources to clean up).
    FastAPI calls this once per request; all four backends are stateless singletons.
    """
    return _default_registry
