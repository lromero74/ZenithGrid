# PRP: Session-Scoped Admin Messaging

**Feature**: Target individual sessions of Observer (shared) accounts with admin messages
**Created**: 2026-03-14
**One-Pass Confidence Score**: 7/10

> Extends the WebSocket manager with session-level tracking and adds a session-targeted notification delivery mechanism. The existing user-scoped admin_dm chat remains unchanged for regular accounts.

---

## Context & Goal

### Problem
Observer accounts (e.g., `demo_usd`) are shared — multiple people log in simultaneously from different locations. The current admin_dm chat is user-scoped: a message to `demo_usd` reaches ALL sessions (France, Japan, Brazil, etc.). An admin needs to communicate with a specific person (session) — e.g., the person in France.

### Solution
1. **Session-aware WebSocket tracking** — extend WebSocketManager to map `session_id → WebSocket` alongside existing `user_id → Set[WebSocket]`
2. **Session list in admin UI** — for Observer accounts, show each active session as a separate row with geo data, instead of (or in addition to) the user row
3. **Session-targeted admin messages** — delivered as a toast notification to a specific session's WebSocket connection, not as a chat channel message
4. **User-scoped chat preserved** — `admin_dm` channels continue to work for non-Observer accounts and for broadcasting to all sessions of a user

### Who Benefits
- **Admin**: Can reach a specific person using a shared Observer account
- **Observer users**: Only see messages intended for their session, not noise from other sessions

### Scope
- **In**: WebSocket session tracking, session-targeted notifications, admin UI session rows for Observers, geo per session
- **Out**: Full chat channels per session (too heavy for temporary sessions), session-to-session messaging between non-admin users

---

## Architecture

### Data Flow

```
Admin sees Observer user expanded in Users tab
  → Shows individual sessions: "demo_usd — Session 1 (Paris, FR)" / "Session 2 (Tokyo, JP)"
  → Admin clicks message icon on Session 1
  ↓
POST /api/admin/sessions/{session_id}/message { content: "Hello from admin" }
  ↓
Backend looks up session_id → WebSocket connection via ws_manager
  ↓
ws_manager.send_to_session(session_id, {
  type: "admin:session_message",
  content: "Hello from admin",
  sender_name: "Louis (Admin)",
})
  ↓
Frontend NotificationContext receives admin:session_message
  ↓
Shows as a toast notification (not a chat channel)
```

### Key Architectural Decisions

1. **Session messages are notifications, not chat channels** — sessions are temporary; a full chat channel would be orphaned when the session ends
2. **Toast-based delivery** — uses the existing toast system (`addToast` with `'social'` type) for immediate, non-persistent messages
3. **No message persistence** — session messages are ephemeral; they're delivered via WebSocket and displayed as toasts. Not stored in DB. If the session isn't connected, the message is lost.
4. **Fallback for disconnected sessions** — if the target session has no active WebSocket, return an error to the admin

---

## Existing Code: Session ID → WebSocket Chain

The chain exists but has a gap at step 10:

```
LOGIN → ActiveSession created with session_id (UUID)
  → session_id embedded in JWT "sid" claim
  → Frontend stores JWT in localStorage
  → WebSocket connects with ?token=<jwt>
  → Backend decodes JWT, extracts user_id
  → ❌ Backend does NOT extract "sid" from JWT
  → ws_manager.connect(websocket, user_id) — no session awareness
```

**The fix**: Extract `sid` from the JWT payload in the websocket endpoint and pass it to a new `ws_manager.connect_with_session()`.

---

## Implementation Tasks (in order)

### Backend

#### 1. Extend WebSocketManager (`backend/app/services/websocket_manager.py`)

Add session-level tracking alongside existing user-level:

```python
class WebSocketManager:
    def __init__(self):
        self._user_connections: dict[int, set[WebSocket]] = {}
        self._socket_owners: dict[WebSocket, int] = {}
        self._lock = asyncio.Lock()
        # NEW: session_id → WebSocket mapping
        self._session_sockets: dict[str, WebSocket] = {}
        self._socket_sessions: dict[WebSocket, str] = {}  # reverse lookup

    async def connect(self, websocket, user_id, session_id=None):
        # ... existing logic ...
        # NEW: track session mapping if provided
        if session_id:
            self._session_sockets[session_id] = websocket
            self._socket_sessions[websocket] = session_id

    async def disconnect(self, websocket):
        # ... existing logic ...
        # NEW: clean up session mapping
        sid = self._socket_sessions.pop(websocket, None)
        if sid:
            self._session_sockets.pop(sid, None)

    async def send_to_session(self, session_id: str, message: dict) -> bool:
        """Send to a specific session's WebSocket. Returns True if delivered."""
        ws = self._session_sockets.get(session_id)
        if not ws:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception:
            return False
```

#### 2. Extract session_id in WebSocket endpoint (`backend/app/main.py`)

In `websocket_endpoint()`, after decoding the JWT (around line 708):

```python
user_id = int(payload.get("sub"))
session_id = payload.get("sid")  # NEW: extract session_id from JWT
```

Update the connect call (around line 738):

```python
connected = await ws_manager.connect(websocket, user_id, session_id=session_id)
```

#### 3. Admin session message endpoint (`backend/app/routers/admin_router.py`)

New endpoint:

```python
@router.post("/sessions/{session_id}/message")
async def send_session_message(
    session_id: str,
    body: SessionMessageRequest,  # { content: str }
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
):
    admin_name = current_user.admin_display_name or current_user.display_name or "Admin"
    delivered = await ws_manager.send_to_session(session_id, {
        "type": "admin:session_message",
        "content": body.content,
        "sender_name": f"{admin_name} (Admin)",
    })
    if not delivered:
        raise HTTPException(404, "Session not connected")
    return {"status": "delivered"}
```

#### 4. Admin sessions list endpoint (`backend/app/routers/admin_router.py`)

New endpoint to list Observer sessions with geo:

```python
@router.get("/observer-sessions")
async def list_observer_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Perm.ADMIN_USERS)),
):
    # Get Observer user IDs
    # Query active sessions for those users
    # Lookup geo for each IP (using ban_monitor._lookup_ip_geo)
    # Check which sessions have active WebSocket connections
    # Return: session_id, user_email, ip, geo, is_ws_connected, created_at
```

This is a separate endpoint from the user list to avoid slowing it down with geo lookups.

### Frontend

#### 5. NotificationContext — handle session messages (`frontend/src/contexts/NotificationContext.tsx`)

Add handler for `admin:session_message`:

```typescript
} else if (data.type === 'admin:session_message') {
  addToast({
    type: 'social',
    title: data.sender_name,
    message: String(data.content),
    persistent: true,  // Don't auto-dismiss admin messages
  })
}
```

#### 6. AdminUsers — expandable Observer sessions (`frontend/src/pages/admin/AdminUsers.tsx`)

For Observer users, show an expandable section with individual sessions:

- Each session row shows: session_id (truncated), IP, geo (city, country), user_agent (parsed to browser/OS), created_at, WebSocket status (connected/disconnected)
- Message icon button per connected session
- On click: opens inline message input (not full chat — just a text field + send button)
- Sends `POST /api/admin/sessions/{session_id}/message`

#### 7. API types (`frontend/src/services/api.ts`)

```typescript
export interface ObserverSession {
  session_id: string
  user_id: number
  user_email: string
  ip: string
  city?: string
  region?: string
  country?: string
  org?: string
  user_agent?: string
  created_at: string
  is_ws_connected: boolean
}

// Add to adminApi:
getObserverSessions: () =>
  api.get<ObserverSession[]>('/admin/observer-sessions').then(r => r.data),
sendSessionMessage: (sessionId: string, content: string) =>
  api.post(`/admin/sessions/${sessionId}/message`, { content }).then(r => r.data),
```

### Tests

#### 8. Backend tests (`backend/tests/services/test_session_messaging.py`)

- `test_send_to_session_delivers_to_correct_websocket`
- `test_send_to_session_returns_false_if_disconnected`
- `test_session_mapping_cleaned_up_on_disconnect`
- `test_connect_without_session_id_still_works`
- `test_observer_sessions_endpoint_returns_geo`

---

## Key Files to Modify

| File | Change |
|------|--------|
| `backend/app/services/websocket_manager.py` | Add `_session_sockets`, `_socket_sessions`, `send_to_session()`, update `connect()`/`disconnect()` |
| `backend/app/main.py` | Extract `sid` from JWT, pass to `ws_manager.connect()` |
| `backend/app/routers/admin_router.py` | Add `/sessions/{session_id}/message` and `/observer-sessions` endpoints |
| `frontend/src/contexts/NotificationContext.tsx` | Handle `admin:session_message` events |
| `frontend/src/pages/admin/AdminUsers.tsx` | Expandable Observer session rows with message button |
| `frontend/src/services/api.ts` | Add ObserverSession type, getObserverSessions, sendSessionMessage |

---

## Session ID Availability

**IMPORTANT**: The `sid` claim is only present in JWT tokens for users with session limits (checked via `has_any_limits(policy)` in auth_core_router.py line 201). Observer accounts in the "Observers" group DO have session limits (configured via the group's `session_policy`), so they WILL have `sid` in their tokens.

Non-Observer users may or may not have `sid` depending on their group's session policy. The WebSocket manager handles this gracefully — if `session_id` is `None`, it just doesn't create a session mapping.

---

## Validation Gates

```bash
# Python lint
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m flake8 --max-line-length=120 \
  app/services/websocket_manager.py \
  app/main.py \
  app/routers/admin_router.py

# TypeScript
cd /home/ec2-user/ZenithGrid/frontend && npx tsc --noEmit

# Tests
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m pytest tests/services/test_session_messaging.py -v
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Session has no WebSocket (closed tab) | Return 404 "Session not connected" — admin sees which sessions are connected |
| Multiple tabs same session_id | Last WebSocket wins (overwrite in _session_sockets) — all tabs share same session |
| Message lost if session disconnects mid-send | Ephemeral by design — admin sees "delivered" or "not connected" |
| Non-Observer users without sid | Gracefully handled — session tracking skipped, user-level messaging still works |
| Geo lookup slows observer-sessions endpoint | Cached in ban_monitor pattern — run in thread pool executor |

---

## UX Flow

1. Admin opens Users tab → sees Observer users with expand arrow
2. Clicks expand → sees list of active sessions with geo (e.g., "192.168.1.1 — Paris, France (Orange SA)")
3. Connected sessions show green dot + message icon
4. Admin clicks message icon → inline text field appears under session row
5. Admin types "Welcome! Let me know if you need help" → clicks Send
6. Backend delivers via WebSocket → recipient sees toast: "Louis (Admin): Welcome! Let me know if you need help"
7. Toast is persistent (doesn't auto-dismiss) — recipient can dismiss manually

---

## Quality Checklist

- [x] All necessary context included (WebSocket manager, JWT chain, session model, Observer detection)
- [x] Validation gates are executable
- [x] References existing patterns (ws_manager, ban_monitor geo, toast system)
- [x] Clear implementation path (8 ordered tasks)
- [x] Error handling documented (disconnected sessions, missing sid)
- [x] Ephemeral design documented (no DB persistence for session messages)
- [x] RBAC-scoped (Observer group detection, admin permission required)
