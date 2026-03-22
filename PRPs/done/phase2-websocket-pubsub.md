# PRP: Phase 2.5 — WebSocket Pub/Sub Backend Abstraction

## Feature Summary

Add a `BroadcastBackend` protocol in front of the existing `ws_manager` singleton.
- `ws_manager` (WebSocketManager) remains the **connection registry** — unchanged
- `BroadcastBackend` is the new **fan-out layer** — a thin protocol that can be swapped for Redis pub/sub in Phase 3 without touching any publisher code
- `InProcessBroadcast` implementation today: wraps `ws_manager` exactly, zero behavior change
- `RedisBroadcast` stub: documents the future interface, raises `NotImplementedError`
- Single new file: `app/services/broadcast_backend.py`
- One new test file: `tests/services/test_broadcast_backend.py` (written FIRST per TDD)

**Motivation** (from `docs/SCALABILITY_ROADMAP.md` Phase 2.5): When we move to multi-process deployment (Phase 3), WebSocket connections will be spread across processes. `broadcast()` must fan out across processes via Redis pub/sub. By introducing this seam now, the swap becomes a config change, not a code change.

---

## Architecture

```
Request handler / trading engine
         │
         ▼  (today)                        (Phase 3)
   ws_manager.broadcast_order_fill()  ──►  broadcast_backend.broadcast_order_fill()
   ws_manager.send_to_user()          ──►  broadcast_backend.send_to_user()
   ws_manager.send_to_room()          ──►  broadcast_backend.send_to_room()
         │                                          │
         ▼                                          ▼
   WebSocketManager                     InProcessBroadcast → ws_manager (same process)
   (connection registry)                RedisBroadcast     → Redis PUBLISH (multi-process)
```

**Key constraint**: `ws_manager` keeps ALL connection management methods (`connect`, `disconnect`, `sweep_stale_connections`, `get_connected_user_ids`). The `BroadcastBackend` protocol covers only the **fan-out** (broadcast) methods.

---

## Reference Files

| File | Purpose |
|------|---------|
| `backend/app/services/websocket_manager.py` | The existing manager — `InProcessBroadcast` wraps this exactly |
| `backend/app/event_bus.py` | Pattern to follow — Protocol + InProcess + module singleton |
| `backend/tests/test_event_bus.py` | TDD test pattern to mirror |
| `docs/SCALABILITY_ROADMAP.md` | Phase 2.5 context and motivation |

### Key excerpt — `websocket_manager.py` methods to expose in the protocol

```python
# Fan-out methods (these go into BroadcastBackend protocol):
async def broadcast(self, message: dict, user_id: Optional[int] = None) -> None
async def send_to_user(self, user_id: int, message: dict) -> None
async def send_to_room(self, player_ids: set[int], message: dict, exclude_user: int | None = None) -> None
async def broadcast_order_fill(self, event: OrderFillEvent) -> None

# Connection-registry methods (stay on ws_manager ONLY — NOT in protocol):
async def connect(self, websocket: WebSocket, user_id: int) -> bool
async def disconnect(self, websocket: WebSocket) -> None
async def sweep_stale_connections(self) -> int
def get_connected_user_ids(self) -> set[int]
```

### Key excerpt — `event_bus.py` module singleton pattern

```python
# Module-level singleton — same pattern as ws_manager
event_bus = InProcessEventBus()
```

We follow the identical pattern:
```python
broadcast_backend: BroadcastBackend = InProcessBroadcast(ws_manager)
```

---

## Implementation Blueprint

### File: `backend/app/services/broadcast_backend.py`

```python
"""
BroadcastBackend abstraction — Phase 2.5 of the scalability roadmap.

Puts a protocol in front of WebSocketManager's fan-out methods so that
Phase 3 (multi-process) can swap InProcessBroadcast for RedisBroadcast
without touching any publisher code.

ws_manager remains the connection registry (connect/disconnect/sweep).
BroadcastBackend is the fan-out layer only.

Usage (new code should use this, not ws_manager directly for broadcasts):
    from app.services.broadcast_backend import broadcast_backend
    await broadcast_backend.send_to_user(user_id, {"type": "order_fill", ...})
    await broadcast_backend.broadcast_order_fill(event)
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol, runtime_checkable

from app.services.websocket_manager import OrderFillEvent, WebSocketManager, ws_manager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol — the interface any backend must satisfy
# ---------------------------------------------------------------------------

@runtime_checkable
class BroadcastBackend(Protocol):
    """Fan-out abstraction over WebSocket connections.

    Implementations:
    - InProcessBroadcast: delegates to WebSocketManager (single process, today)
    - RedisBroadcast:     publishes to Redis channel (multi-process, Phase 3)
    """

    async def broadcast(self, message: dict, user_id: Optional[int] = None) -> None:
        """Broadcast to all connected clients, or to one user if user_id given."""
        ...

    async def send_to_user(self, user_id: int, message: dict) -> None:
        """Send a message to all connections belonging to user_id."""
        ...

    async def send_to_room(
        self,
        player_ids: set[int],
        message: dict,
        exclude_user: int | None = None,
    ) -> None:
        """Send a message to all players in a room (game lobby/spectator)."""
        ...

    async def broadcast_order_fill(self, event: OrderFillEvent) -> None:
        """Broadcast an order fill notification to the owning user."""
        ...


# ---------------------------------------------------------------------------
# In-process implementation — wraps WebSocketManager, zero behavior change
# ---------------------------------------------------------------------------

class InProcessBroadcast:
    """BroadcastBackend backed by the in-process WebSocketManager.

    All calls delegate 1-to-1 to ws_manager. The manager is injected so
    that tests can pass a mock without patching globals.
    """

    def __init__(self, manager: WebSocketManager) -> None:
        self._manager = manager

    async def broadcast(self, message: dict, user_id: Optional[int] = None) -> None:
        await self._manager.broadcast(message, user_id=user_id)

    async def send_to_user(self, user_id: int, message: dict) -> None:
        await self._manager.send_to_user(user_id, message)

    async def send_to_room(
        self,
        player_ids: set[int],
        message: dict,
        exclude_user: int | None = None,
    ) -> None:
        await self._manager.send_to_room(player_ids, message, exclude_user=exclude_user)

    async def broadcast_order_fill(self, event: OrderFillEvent) -> None:
        await self._manager.broadcast_order_fill(event)


# ---------------------------------------------------------------------------
# Redis stub — documented seam for Phase 3 multi-process deployment
# ---------------------------------------------------------------------------

class RedisBroadcast:
    """BroadcastBackend backed by Redis pub/sub (Phase 3).

    When ZenithGrid runs multiple backend workers, each process has its own
    WebSocketManager. Broadcasting to a user requires publishing to a shared
    Redis channel that ALL workers subscribe to. Each worker then delivers to
    locally-connected sockets.

    Architecture (Phase 3):
        Publisher → PUBLISH ws:user:{user_id} <message>
        Each worker subscribes: SUB ws:user:* → ws_manager.send_to_user()

    NOT IMPLEMENTED — raises NotImplementedError. Swap this in when Phase 3
    deploys multi-process uvicorn or adds a Celery/Dramatiq worker fleet.
    """

    async def broadcast(self, message: dict, user_id: Optional[int] = None) -> None:
        raise NotImplementedError("RedisBroadcast not yet implemented (Phase 3)")

    async def send_to_user(self, user_id: int, message: dict) -> None:
        raise NotImplementedError("RedisBroadcast not yet implemented (Phase 3)")

    async def send_to_room(
        self,
        player_ids: set[int],
        message: dict,
        exclude_user: int | None = None,
    ) -> None:
        raise NotImplementedError("RedisBroadcast not yet implemented (Phase 3)")

    async def broadcast_order_fill(self, event: OrderFillEvent) -> None:
        raise NotImplementedError("RedisBroadcast not yet implemented (Phase 3)")


# ---------------------------------------------------------------------------
# Module-level singleton — same pattern as ws_manager and event_bus
# ---------------------------------------------------------------------------

broadcast_backend: BroadcastBackend = InProcessBroadcast(ws_manager)
```

---

## TDD Test File: `backend/tests/services/test_broadcast_backend.py`

Write FIRST — all tests must initially fail with `ModuleNotFoundError`.

```
Tests to cover:
1. InProcessBroadcast.broadcast() delegates to manager.broadcast() — default (no user_id)
2. InProcessBroadcast.broadcast() delegates with user_id
3. InProcessBroadcast.send_to_user() delegates to manager.send_to_user()
4. InProcessBroadcast.send_to_room() delegates to manager.send_to_room() with exclude_user
5. InProcessBroadcast.broadcast_order_fill() delegates to manager.broadcast_order_fill()
6. Module-level singleton exists and is InProcessBroadcast
7. broadcast_backend satisfies BroadcastBackend Protocol (isinstance check)
8. RedisBroadcast is importable and raises NotImplementedError on all methods
9. InProcessBroadcast can be constructed with a custom manager (injection)
```

---

## Tasks (in order)

1. **Create test directory** `backend/tests/services/` with `__init__.py` if it doesn't exist
2. **Write failing tests** in `backend/tests/services/test_broadcast_backend.py`
3. **Run tests** — confirm all fail with `ModuleNotFoundError: No module named 'app.services.broadcast_backend'`
4. **Write implementation** in `backend/app/services/broadcast_backend.py`
5. **Run tests** — confirm all pass
6. **Run lint** — `cd backend && ./venv/bin/python3 -m flake8 app/services/broadcast_backend.py --max-line-length=120`
7. **Run mypy** if available
8. **Verify no existing tests broken** — run tests for websocket_manager

---

## Validation Gates

```bash
# 1. Confirm test directory exists
ls /home/ec2-user/ZenithGrid/backend/tests/services/

# 2. Run new tests
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m pytest tests/services/test_broadcast_backend.py -v

# 3. Lint
./venv/bin/python3 -m flake8 app/services/broadcast_backend.py --max-line-length=120

# 4. TypeScript (no frontend changes, skip)

# 5. Verify existing ws tests unbroken
./venv/bin/python3 -m pytest tests/ -k "websocket or broadcast" -v
```

---

## Gotchas

- **`@runtime_checkable` is required** for `isinstance(obj, BroadcastBackend)` to work. Without it, `isinstance` raises `TypeError`.
- **`Protocol` methods need `...` body** — they are abstract by definition. Don't put `pass` — use `...`.
- **`ws_manager` is imported at module level in `broadcast_backend.py`** — this creates a module import, not a circular dependency (broadcast_backend imports from websocket_manager, not vice versa).
- **Inject manager in tests** — don't patch `ws_manager` globally. `InProcessBroadcast(mock_manager)` is cleaner and test-safe.
- **`send_to_room` keyword arg** — `websocket_manager.send_to_room(player_ids, message, exclude_user=exclude_user)`. The `exclude_user` param must be passed as keyword (the signature has it positional but callers pass it both ways — use keyword to be safe).
- **No changes to existing `ws_manager` call sites** — this PR is addition-only. Migrating call sites is Phase 3 prep work.

---

## Quality Checklist

- [ ] Tests written before implementation (TDD)
- [ ] All tests pass
- [ ] `@runtime_checkable` on Protocol
- [ ] `RedisBroadcast` stub has docstring explaining Phase 3 architecture
- [ ] Module-level singleton follows `event_bus` / `ws_manager` pattern
- [ ] Zero changes to `websocket_manager.py` or any existing call site
- [ ] Lint passes (flake8 --max-line-length=120)
- [ ] `tests/services/__init__.py` exists

---

**Confidence score: 9/10** — Single new file, thin delegation layer, no behavior changes, clear existing patterns (`event_bus.py`, `websocket_manager.py`) to mirror. TDD is straightforward because we can inject a mock `WebSocketManager`. The only complexity is getting the `Protocol` typing right with `@runtime_checkable`.
