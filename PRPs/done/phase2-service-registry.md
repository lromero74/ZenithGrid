# PRP: Phase 2.2 — ServiceRegistry Pattern

## Feature Summary

Introduce a `ServiceRegistry` dataclass in `app/registry.py` that holds the four
abstraction singletons built in Phases 2.3–2.6 as a single, composable injection point.
A `get_registry()` FastAPI dependency exposes it to routers.

- Single new file: `app/registry.py`
- Single new test file: `tests/test_registry.py` (TDD — written first)
- Zero existing files changed

**Motivation** (from `docs/SCALABILITY_ROADMAP.md` Phase 2.2): Today each router imports
singletons directly (`from app.event_bus import event_bus`, etc.). In Phase 3, swapping
a backend requires finding and patching every import. With `ServiceRegistry`, a single
reassignment (`_default_registry = ServiceRegistry(NATSEventBus(), RedisBroadcast(), ...)`)
switches all four backends simultaneously — at startup, in tests, or per-request.

---

## The Four Singletons Being Registered

| Field name | Type | Module | Singleton variable |
|---|---|---|---|
| `event_bus` | `InProcessEventBus` | `app/event_bus.py` | `event_bus` |
| `broadcast` | `BroadcastBackend` | `app/services/broadcast_backend.py` | `broadcast_backend` |
| `rate_limiter` | `RateLimitBackend` | `app/auth_routers/rate_limit_backend.py` | `rate_limit_backend` |
| `credentials` | `CredentialsProvider` | `app/services/credentials_provider.py` | `credentials_provider` |

**Note on `event_bus` typing**: `event_bus.py` exposes only `InProcessEventBus` (no
`EventBus` Protocol was defined in Phase 2.3). Type the field as `InProcessEventBus`
for now — the concrete class IS the type until NATS is needed. A Protocol can be
added to `event_bus.py` when Phase 3 demands it.

---

## Architecture

```
FastAPI Router endpoint
    │
    ├── db: AsyncSession = Depends(get_db)           (existing)
    ├── user: User = Depends(get_current_user)        (existing)
    └── registry: ServiceRegistry = Depends(get_registry)  (NEW)
              │
              ├── .event_bus      → InProcessEventBus (→ NATSEventBus Phase 3)
              ├── .broadcast      → InProcessBroadcast (→ RedisBroadcast Phase 3)
              ├── .rate_limiter   → PostgresRateLimitBackend (→ Redis Phase 3)
              └── .credentials    → LocalCredentialsProvider (→ Remote Phase 3)

Phase 3 swap — one place, zero router changes:
    _default_registry = ServiceRegistry(
        event_bus=NATSEventBus(nats_url),
        broadcast=RedisBroadcast(redis_url),
        rate_limiter=RedisRateLimitBackend(redis_url),
        credentials=RemoteCredentialsProvider(credentials_url),
    )
```

---

## Reference Files

| File | Purpose |
|------|---------|
| `backend/app/event_bus.py` | `InProcessEventBus`, `event_bus` singleton |
| `backend/app/services/broadcast_backend.py` | `BroadcastBackend`, `InProcessBroadcast`, `broadcast_backend` |
| `backend/app/auth_routers/rate_limit_backend.py` | `RateLimitBackend`, `PostgresRateLimitBackend`, `rate_limit_backend` |
| `backend/app/services/credentials_provider.py` | `CredentialsProvider`, `LocalCredentialsProvider`, `credentials_provider` |
| `backend/app/database.py` | Pattern for `get_db()` FastAPI dependency (sync, returns singleton) |
| `backend/tests/services/test_broadcast_backend.py` | TDD test structure to mirror |
| `backend/tests/services/test_credentials_provider.py` | TDD test structure to mirror |

### `get_db()` dependency pattern to follow (from `app/database.py`)

```python
async def get_db():
    async with async_session_maker() as session:
        yield session
```

`get_registry()` is even simpler — sync, no yield, just returns the singleton:

```python
def get_registry() -> ServiceRegistry:
    return _default_registry
```

---

## Implementation Blueprint

### File: `backend/app/registry.py`

```python
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
from app.auth_routers.rate_limit_backend import RateLimitBackend, rate_limit_backend as _rate_limit_backend
from app.services.credentials_provider import CredentialsProvider, credentials_provider as _credentials_provider


@dataclass
class ServiceRegistry:
    """Composable holder for all service backends.

    Fields use the Protocol types (BroadcastBackend, RateLimitBackend,
    CredentialsProvider) for structural typing. event_bus is typed as the
    concrete InProcessEventBus until an EventBus Protocol is defined in
    Phase 3 (when NATS replaces the in-process bus).

    Phase 3 swap (single statement at app startup):
        from app.registry import _default_registry
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


# Default registry — pre-populated with current in-process singletons
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
```

---

## TDD Test File: `backend/tests/test_registry.py`

Write FIRST — all tests must initially fail with `ModuleNotFoundError`.

```
Tests to cover:
1.  _default_registry exists and is ServiceRegistry
2.  _default_registry.event_bus is the module-level event_bus singleton (InProcessEventBus)
3.  _default_registry.broadcast is the module-level broadcast_backend singleton (InProcessBroadcast)
4.  _default_registry.rate_limiter is the module-level rate_limit_backend singleton (PostgresRateLimitBackend)
5.  _default_registry.credentials is the module-level credentials_provider singleton (LocalCredentialsProvider)
6.  get_registry() returns _default_registry (same object, multiple calls)
7.  _default_registry.broadcast satisfies BroadcastBackend Protocol (isinstance)
8.  _default_registry.rate_limiter satisfies RateLimitBackend Protocol (isinstance)
9.  _default_registry.credentials satisfies CredentialsProvider Protocol (isinstance)
10. ServiceRegistry can be constructed with mock replacements (the swap point test)
```

### Key test patterns

```python
from app.registry import ServiceRegistry, get_registry, _default_registry
from app.event_bus import InProcessEventBus, event_bus
from app.services.broadcast_backend import InProcessBroadcast, BroadcastBackend, broadcast_backend
from app.auth_routers.rate_limit_backend import PostgresRateLimitBackend, RateLimitBackend, rate_limit_backend
from app.services.credentials_provider import LocalCredentialsProvider, CredentialsProvider, credentials_provider

def test_default_registry_is_service_registry():
    assert isinstance(_default_registry, ServiceRegistry)

def test_get_registry_returns_singleton():
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2  # same object — no re-instantiation per call

def test_custom_registry_with_mocks():
    """The swap point: verify ServiceRegistry accepts mock replacements."""
    from unittest.mock import MagicMock
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
```

---

## Gotchas

- **`_default_registry` is a module-level mutable** — Python allows reassignment of module globals. `import app.registry as _reg; _reg._default_registry = ServiceRegistry(...)` is the Phase 3 swap idiom. Tests should NOT modify `_default_registry` (use `ServiceRegistry(...)` directly to test the constructor).

- **`dataclass` field ordering** — Python dataclasses require fields with defaults after fields without. All four fields have no default (injected at construction), so order doesn't matter for construction. The order in the blueprint is logical: event_bus → broadcast → rate_limiter → credentials.

- **Import order in `registry.py`** — imports from `app.auth_routers.rate_limit_backend` cross a package boundary (`auth_routers` is a subpackage of `app`). This is fine — `registry.py` is a top-level `app/` module and can import from any subpackage. No circular import risk (none of the four modules import from `app.registry`).

- **`get_registry` is synchronous** — unlike `get_db()` (which is async + yield for session lifecycle), `get_registry()` just returns the singleton. FastAPI's dependency injection handles both sync and async dependencies. A sync dependency that returns (not yields) is the simplest form.

- **Do NOT add `get_registry` to `app/main.py` startup** — the registry is populated at module import time (module-level `_default_registry = ServiceRegistry(...)`), not in `startup_event`. This is intentional — it matches how `event_bus`, `broadcast_backend`, etc. are all module-level singletons.

- **Test imports** — all four singleton names are imported directly from their modules in tests. This verifies the registry holds the SAME object (identity check with `is`), not just an equal value.

- **No changes to existing call sites** — routers that currently do `from app.event_bus import event_bus` are NOT migrated. The registry is additive. Incremental migration of call sites happens in Phase 3.

---

## Tasks (in order)

1. **Write failing tests** in `backend/tests/test_registry.py`
2. **Run tests** — confirm all fail with `ModuleNotFoundError: No module named 'app.registry'`
3. **Write implementation** in `backend/app/registry.py`
4. **Run tests** — confirm all pass
5. **Lint**: `flake8 app/registry.py --max-line-length=120`
6. **Import check**: `python3 -c "from app.registry import ServiceRegistry, get_registry, _default_registry; print('OK')"`

---

## Validation Gates

```bash
# Run from: /home/ec2-user/ZenithGrid/backend

# 1. New tests pass
./venv/bin/python3 -m pytest tests/test_registry.py -v

# 2. Lint
./venv/bin/python3 -m flake8 app/registry.py --max-line-length=120

# 3. Import check (also exercises all four singleton imports)
./venv/bin/python3 -c "from app.registry import ServiceRegistry, get_registry, _default_registry; print('imports OK')"

# 4. Spot-check none of the existing singleton modules are broken
./venv/bin/python3 -m pytest tests/test_event_bus.py tests/services/test_broadcast_backend.py tests/test_rate_limit_backend.py tests/services/test_credentials_provider.py -q
```

---

## Quality Checklist

- [ ] Tests written before implementation (TDD)
- [ ] All 10 tests pass
- [ ] `@dataclass` used (not plain class)
- [ ] `get_registry()` is sync (not async, no yield)
- [ ] Module-level `_default_registry` populated at import time
- [ ] Zero changes to any existing file
- [ ] Lint passes (flake8 --max-line-length=120)
- [ ] All four dependent module tests still pass

---

**Confidence score: 10/10** — Single new file, pure composition of already-built singletons, no behavior changes, no DB/async complexity. The only subtlety is the identity test (`is`) to confirm the registry holds the actual singletons — fully covered in the test patterns above.
