# PRP: Multiplayer Gaming Framework

**Feature**: Real-time multiplayer infrastructure, friends system, game history, tournaments
**Created**: 2026-03-10
**One-Pass Confidence Score**: 6/10

> This is a **massive feature** spanning backend models, WebSocket infrastructure, frontend social UI, and integration into 3 proof-of-concept games. The PRP is designed for **phased execution** — each phase is independently shippable. The score reflects the total scope; individual phase confidence is 7-8/10.

---

## Context & Goal

### Problem
Games are currently single-player client-side only. Users cannot play against each other, track competitive results, or build social connections on the platform. There's no way to challenge friends to a game or compete in tournaments.

### Solution
Build a real-time multiplayer framework with:
1. **Friends system** — search users by display name, send/accept/reject/block friend requests
2. **Multiplayer game modes** — "VS" (head-to-head), "Race" (first to win / last to lose)
3. **Low-latency WebSocket communication** — shared game state in real-time
4. **Game history** — persistent records of games played, viewable by friends (with privacy controls)
5. **Tournaments** — organize multi-game competitions among friends
6. **Proof-of-concept games** — Dino Runner (last to lose), Texas Hold'em (first to win + VS), Connect Four (VS + first to win)

### Who Benefits
All users. Social gaming increases engagement and retention.

### Scope
- **In**: Friends CRUD, display name uniqueness, WebSocket game rooms, shared state protocol, game history, tournaments, privacy controls, 3 PoC game integrations
- **Out**: Matchmaking with strangers, ELO/ranking system, spectator mode, voice/video chat, cross-platform push notifications

---

## Existing Code Patterns (Reference)

### Backend

#### User Model (`backend/app/models/auth.py:46-113`)
- `display_name = Column(String, nullable=True)` — exists but NOT unique, NOT required
- User has `id`, `email`, `is_active`, `is_superuser`, timestamps
- Multi-tenant: all resources scoped by `user_id` foreign keys
- RBAC: groups → roles → permissions

#### WebSocket Manager (`backend/app/services/websocket_manager.py`)
- Singleton `ws_manager` with `active_connections: List[Tuple[WebSocket, int]]`
- `connect(ws, user_id)`, `disconnect(ws)`, `broadcast(message, user_id=None)`
- Per-user scoping, MAX_CONNECTIONS_PER_USER = 5, asyncio.Lock for thread safety
- Currently only handles `OrderFillEvent` — needs extension for game rooms

#### WebSocket Endpoint (`backend/app/main.py:662-729`)
- Mounted at `/ws` with JWT token auth via query param
- Auth flow: decode JWT → check revocation → verify user active → accept connection
- Currently echoes received messages — needs routing to game-specific handlers

#### Router Registration (`backend/app/main.py:146-165`)
- Pattern: `app.include_router(router_module.router)` with prefix/tags set in router files
- Example: `app.include_router(accounts_router.router)`

#### Database (`backend/app/database.py`)
- PostgreSQL (production) with async SQLAlchemy
- `async_session_maker` for async sessions
- All models inherit from `Base`
- Migrations in `backend/migrations/` auto-discovered by `update.py`

### Frontend

#### Game Architecture
- **Pure logic separation**: Game engines (e.g., `connectFourEngine.ts`) are pure TS with no React deps
- **State management**: `useState` + `useGameState` hook (localStorage persistence, user-scoped)
- **Component structure**: `GameLayout` wrapper → game board → `GameOverModal`
- **Audio**: `useGameMusic` + `useGameSFX` hooks
- **Types** (`pages/games/types.ts`): `GameStatus`, `Difficulty`, `GameInfo`, `GameScore`

#### Auth Context (`frontend/src/contexts/AuthContext.tsx`)
- `User` type: `{ id, email, display_name, is_active, is_superuser, ... }`
- `useAuth()` hook returns `{ user, login, logout, isAuthenticated }`

#### Game Registry (`frontend/src/pages/games/constants.ts`)
- `GAMES` array with 50+ game entries
- Each game: `{ id, name, description, icon, path, difficulty, sessionLength, category }`
- `getStoragePrefix()` returns `zenith-games-u${userId}-` for user-scoped localStorage

#### Routing (`frontend/src/pages/Games.tsx`)
- Lazy-loaded game components with `<Route path="gameId" element={<Game />} />`

---

## Architecture Design

### WebSocket Protocol

Game communication uses a **room-based WebSocket protocol**. The existing `/ws` endpoint is extended with message routing:

```
Client → Server messages:
  { type: "game:create", gameId: string, mode: "vs"|"race", config: {...} }
  { type: "game:join", roomId: string }
  { type: "game:leave", roomId: string }
  { type: "game:action", roomId: string, action: {...} }
  { type: "game:ready", roomId: string }

Server → Client messages:
  { type: "game:created", roomId: string, gameId: string, players: [...] }
  { type: "game:joined", roomId: string, player: {...} }
  { type: "game:state", roomId: string, state: {...}, sequence: number }
  { type: "game:action", roomId: string, playerId: number, action: {...}, sequence: number }
  { type: "game:over", roomId: string, result: {...} }
  { type: "game:error", roomId: string, error: string }

  { type: "friend:request", from: { id, displayName } }
  { type: "friend:accepted", userId: number }
  { type: "friend:online", userId: number, online: boolean }
```

### Game Room Architecture

```
GameRoomManager (singleton, in-memory)
├── rooms: Dict[str, GameRoom]
│   ├── room_id: UUID
│   ├── game_id: "connect-four" | "texas-holdem" | "dino-runner" | ...
│   ├── mode: "vs" | "race"
│   ├── host_user_id: int
│   ├── players: List[{ user_id, display_name, ws, ready, score }]
│   ├── spectators: List[...]  (future)
│   ├── state: GameState (JSON, game-specific)
│   ├── sequence: int (monotonic, for ordering)
│   ├── created_at: datetime
│   └── status: "waiting" | "playing" | "finished"
└── user_rooms: Dict[int, str]  (user_id → room_id, max 1 active room)
```

**Server-authoritative for VS mode**: Server validates moves, updates state, broadcasts.
**Client-authoritative for Race mode**: Each client runs their own game, reports score/status. Server timestamps and determines winner.

### Database Schema

#### New Models (`backend/app/models/social.py`)

```python
class Friendship(Base):
    """Bidirectional friend relationship. Created when recipient accepts request."""
    __tablename__ = "friendships"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    friend_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # UniqueConstraint on (user_id, friend_id) — stored bidirectionally (2 rows per friendship)

class FriendRequest(Base):
    """Pending friend request. Deleted on accept/reject."""
    __tablename__ = "friend_requests"
    id = Column(Integer, primary_key=True)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # UniqueConstraint on (from_user_id, to_user_id)

class BlockedUser(Base):
    """User A blocks user B. Prevents friend requests from B to A."""
    __tablename__ = "blocked_users"
    id = Column(Integer, primary_key=True)
    blocker_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    blocked_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class GameResult(Base):
    """Persistent record of a completed multiplayer game."""
    __tablename__ = "game_results"
    id = Column(Integer, primary_key=True)
    room_id = Column(String, nullable=False, index=True)  # UUID of the game room
    game_id = Column(String, nullable=False, index=True)   # "connect-four", "texas-holdem", etc.
    mode = Column(String, nullable=False)                   # "vs", "race"
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, default=datetime.utcnow)
    result_data = Column(JSON, nullable=True)               # Game-specific result details
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=True)

class GameResultPlayer(Base):
    """Per-player result within a game. Links user to their outcome."""
    __tablename__ = "game_result_players"
    id = Column(Integer, primary_key=True)
    game_result_id = Column(Integer, ForeignKey("game_results.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    placement = Column(Integer, nullable=True)   # 1st, 2nd, etc.
    score = Column(Integer, nullable=True)
    is_winner = Column(Boolean, default=False)
    stats = Column(JSON, nullable=True)           # Game-specific stats

class GameHistoryVisibility(Base):
    """Per-user privacy control for game history sharing."""
    __tablename__ = "game_history_visibility"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # "all_friends", "opponents_only", or "private"
    default_visibility = Column(String, default="all_friends")
    # Per-game overrides (JSON: { "connect-four": "opponents_only" })
    game_overrides = Column(JSON, nullable=True)

class Tournament(Base):
    """Multi-game tournament among friends."""
    __tablename__ = "tournaments"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    game_ids = Column(JSON, nullable=False)         # List of game_ids included
    config = Column(JSON, nullable=True)             # Rounds, scoring rules, etc.
    status = Column(String, default="pending")       # "pending", "active", "completed", "archived"
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

class TournamentPlayer(Base):
    """Player enrolled in a tournament."""
    __tablename__ = "tournament_players"
    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    total_score = Column(Integer, default=0)
    placement = Column(Integer, nullable=True)
    archived = Column(Boolean, default=False)  # Per-user soft archive
    joined_at = Column(DateTime, default=datetime.utcnow)

class TournamentDeleteVote(Base):
    """Committee vote for tournament deletion. All players must vote to delete."""
    __tablename__ = "tournament_delete_votes"
    id = Column(Integer, primary_key=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    voted_at = Column(DateTime, default=datetime.utcnow)
```

#### Migration: Make `display_name` unique and required

```python
# Migration: add unique constraint to display_name, set default for existing users
# For existing users with NULL display_name, auto-generate from email prefix + random suffix
```

### Frontend Architecture

```
frontend/src/
├── services/
│   └── gameSocket.ts              # WebSocket client for game rooms
├── contexts/
│   └── MultiplayerContext.tsx      # React context for multiplayer state
├── pages/games/
│   ├── components/
│   │   ├── social/
│   │   │   ├── FriendsPanel.tsx         # Friends list, online status, invite
│   │   │   ├── FriendSearch.tsx         # Search users by display name
│   │   │   ├── FriendRequests.tsx       # Pending requests (accept/reject)
│   │   │   ├── BlockedUsers.tsx         # Manage blocked users
│   │   │   ├── GameHistory.tsx          # Match history with friends
│   │   │   └── GameHistorySettings.tsx  # Privacy controls
│   │   ├── multiplayer/
│   │   │   ├── GameLobby.tsx            # Pre-game room (waiting for players, ready up)
│   │   │   ├── MultiplayerWrapper.tsx   # HOC that adds multiplayer capabilities to a game
│   │   │   ├── InviteModal.tsx          # Invite friends to a game room
│   │   │   ├── TournamentCreate.tsx     # Create tournament
│   │   │   ├── TournamentView.tsx       # View tournament bracket/standings
│   │   │   └── TournamentList.tsx       # List active/past tournaments
│   │   └── games/
│   │       ├── connect-four/
│   │       │   └── ConnectFourMultiplayer.tsx  # Multiplayer wrapper for Connect Four
│   │       ├── texas-holdem/
│   │       │   └── TexasHoldemMultiplayer.tsx
│   │       └── dino-runner/
│   │           └── DinoRunnerMultiplayer.tsx
│   └── hooks/
│       ├── useGameSocket.ts       # WebSocket connection hook
│       ├── useFriends.ts          # Friends CRUD hook
│       └── useGameHistory.ts      # Game history queries
```

### Multiplayer Game Integration Pattern

Each game that supports multiplayer gets a `*Multiplayer.tsx` wrapper component that:
1. Manages the game room lifecycle (create/join/leave)
2. Translates WebSocket messages to/from the game's existing engine
3. Adds the lobby UI before game start
4. Adds the result screen after game end

**VS mode** (Connect Four, Texas Hold'em):
- Server maintains authoritative game state
- Player sends action → server validates → broadcasts new state to all players
- Game engine runs on BOTH server (validation) and client (rendering)
- Turn enforcement: server rejects out-of-turn actions

**Race mode** (Dino Runner, Connect Four "first to win"):
- Each player runs their own game instance client-side
- Client periodically reports status (alive/dead, score, progress)
- Server timestamps reports and determines winner when race condition is met
- Other players see a simplified status view (score, alive/dead, time)

### WebSocket Client (`frontend/src/services/gameSocket.ts`)

```typescript
class GameSocketClient {
  private ws: WebSocket | null = null
  private listeners: Map<string, Set<(data: any) => void>> = new Map()
  private reconnectTimer: number | null = null
  private sequence: number = 0

  connect(token: string): void
  disconnect(): void
  send(message: object): void
  on(type: string, handler: (data: any) => void): () => void  // returns unsubscribe fn

  // Game room methods
  createRoom(gameId: string, mode: string, config?: object): void
  joinRoom(roomId: string): void
  leaveRoom(roomId: string): void
  sendAction(roomId: string, action: object): void
  ready(roomId: string): void
}

export const gameSocket = new GameSocketClient()  // singleton
```

---

## Backend API Endpoints

### Friends Router (`backend/app/routers/friends_router.py`)

```
GET    /api/friends                     # List friends (with online status)
POST   /api/friends/request             # Send friend request { display_name: string }
GET    /api/friends/requests             # List pending incoming requests
POST   /api/friends/requests/{id}/accept # Accept request
DELETE /api/friends/requests/{id}        # Reject/dismiss request (silent)
DELETE /api/friends/{friend_id}          # Remove friend
POST   /api/friends/block               # Block user { user_id: int }
DELETE /api/friends/block/{user_id}      # Unblock user
GET    /api/friends/blocked              # List blocked users
GET    /api/users/search?q=displayname   # Search users by display name (public)
```

### Game History Router (`backend/app/routers/game_history_router.py`)

```
GET    /api/games/history                # My game history (with filters)
GET    /api/games/history/friend/{id}    # Games played with/against a specific friend
GET    /api/games/history/stats          # Aggregate stats (win rate, games played, etc.)
PUT    /api/games/history/visibility     # Update privacy settings
```

### Tournament Router (`backend/app/routers/tournament_router.py`)

```
POST   /api/tournaments                  # Create tournament
GET    /api/tournaments                  # List my tournaments
GET    /api/tournaments/{id}             # Tournament details + standings
POST   /api/tournaments/{id}/join        # Join tournament
POST   /api/tournaments/{id}/start       # Start tournament (creator only)
PUT    /api/tournaments/{id}/archive     # Archive for self
POST   /api/tournaments/{id}/vote-delete # Vote to delete
```

### Display Name Router (`backend/app/routers/display_name_router.py`)

```
PUT    /api/users/display-name           # Set/update display name
GET    /api/users/display-name/check?name=x  # Check availability
```

### WebSocket Game Router (extend existing `/ws` in `main.py`)

The existing WebSocket endpoint at `/ws` is extended to handle game messages. A new `GameRoomManager` service processes game-type messages.

---

## Implementation Order

### Phase 1: Foundation (Backend Infrastructure)
**Files to create/modify — independently shippable**

1. **Display name uniqueness migration** (`backend/migrations/xxx_display_name_unique.py`)
   - Add unique index on `users.display_name` (case-insensitive)
   - Auto-generate display names for existing users with NULL values
   - Add `display_name_lower` computed column for case-insensitive lookups

2. **Social models** (`backend/app/models/social.py`)
   - `Friendship`, `FriendRequest`, `BlockedUser`
   - Import in `backend/app/models/__init__.py`

3. **Friends router** (`backend/app/routers/friends_router.py`)
   - All CRUD endpoints for friends, requests, blocks, search
   - Register in `main.py`

4. **Display name router** (`backend/app/routers/display_name_router.py`)
   - Set/update display name, check availability
   - Register in `main.py`

5. **Tests for friends & display name** (`backend/tests/routers/test_friends_router.py`, `backend/tests/routers/test_display_name_router.py`)

**Validation gate**: `flake8 --max-line-length=120`, `pytest tests/routers/test_friends_router.py tests/routers/test_display_name_router.py -v`

### Phase 2: Game Rooms (WebSocket Infrastructure)
**Files to create/modify**

6. **Game room manager** (`backend/app/services/game_room_manager.py`)
   - `GameRoomManager` class with room CRUD, player management
   - In-memory rooms (Dict[str, GameRoom])
   - Message routing: game:create, game:join, game:leave, game:action, game:ready

7. **Extend WebSocket manager** (`backend/app/services/websocket_manager.py`)
   - Add `send_to_room(room_id, message)` method
   - Add `send_to_user(user_id, message)` method (already exists as `broadcast` with user_id)

8. **Extend WebSocket endpoint** (`backend/app/main.py`)
   - Route game-type messages to `GameRoomManager`
   - Keep existing order fill handling unchanged

9. **Game result models** (`backend/app/models/social.py` — extend)
   - `GameResult`, `GameResultPlayer`
   - Migration for new tables

10. **Game result persistence service** (`backend/app/services/game_result_service.py`)
    - Save game results when rooms close
    - Query history with filters

11. **Tests** (`backend/tests/services/test_game_room_manager.py`)

**Validation gate**: `flake8`, `pytest tests/services/test_game_room_manager.py -v`

### Phase 3: Frontend Social UI
**Files to create**

12. **WebSocket client** (`frontend/src/services/gameSocket.ts`)
    - `GameSocketClient` class with reconnection, event system
    - Reuse existing auth token for connection

13. **Multiplayer context** (`frontend/src/contexts/MultiplayerContext.tsx`)
    - React context wrapping `GameSocketClient`
    - Exposes: `room`, `players`, `isConnected`, `sendAction`, `createRoom`, `joinRoom`

14. **Friends hooks** (`frontend/src/pages/games/hooks/useFriends.ts`)
    - `useFriends()`, `useFriendRequests()`, `useUserSearch()`
    - React Query based

15. **Friends panel** (`frontend/src/pages/games/components/social/FriendsPanel.tsx`)
    - Sidebar/tab in Games section showing friends list, online indicators, invite buttons
    - Integrated into GameHub

16. **Friend search** (`frontend/src/pages/games/components/social/FriendSearch.tsx`)
    - Search users by display name, send request

17. **Friend requests** (`frontend/src/pages/games/components/social/FriendRequests.tsx`)
    - Pending incoming requests with accept/reject

18. **Blocked users** (`frontend/src/pages/games/components/social/BlockedUsers.tsx`)
    - List and unblock

19. **Display name setup** — prompt in Games section if user has no display name

**Validation gate**: `npx tsc --noEmit`

### Phase 4: Game Lobby & Multiplayer Wrapper
**Files to create**

20. **Game lobby** (`frontend/src/pages/games/components/multiplayer/GameLobby.tsx`)
    - Pre-game room: player list, ready status, start button
    - Invite modal for friends

21. **Multiplayer wrapper** (`frontend/src/pages/games/components/multiplayer/MultiplayerWrapper.tsx`)
    - HOC that wraps any game with lobby → play → results flow
    - Handles WebSocket lifecycle, game state sync

22. **Invite modal** (`frontend/src/pages/games/components/multiplayer/InviteModal.tsx`)

### Phase 5: Proof-of-Concept Games

23. **Connect Four VS mode** (`frontend/src/pages/games/components/games/connect-four/ConnectFourMultiplayer.tsx`)
    - Reuses existing `ConnectFourBoard` and `connectFourEngine`
    - Replaces AI opponent with WebSocket-connected human
    - Server validates moves using engine (port `connectFourEngine` logic to Python or trust client with server reconciliation)
    - Add "Play Online" button to existing Connect Four page

24. **Connect Four Race mode** (first to win vs AI)
    - Both players play against AI simultaneously
    - First player to win their game wins the race
    - Show opponent's progress (board state or just status)

25. **Texas Hold'em VS mode**
    - Reuses existing `TexasHoldem` game engine
    - Multiple human players at the table (with AI filling empty seats)
    - Server manages deck, deals, pot — clients render hands
    - Real betting between players

26. **Texas Hold'em Race mode** (first to reach target chip count)
    - Both players play their own AI table
    - First to reach a chip target wins

27. **Dino Runner Race mode** (last to lose)
    - Both players run their own Dino Runner instance
    - Clients report score/alive status periodically (every 500ms)
    - Last player alive wins
    - Show opponent's score in real-time overlay

### Phase 6: Game History & Tournaments

28. **Game history UI** (`frontend/src/pages/games/components/social/GameHistory.tsx`)
    - List of past games with results
    - Filter by game, friend, date range
    - Privacy settings

29. **Tournament models & migration** (extend `backend/app/models/social.py`)
    - `Tournament`, `TournamentPlayer`, `TournamentDeleteVote`

30. **Tournament router** (`backend/app/routers/tournament_router.py`)

31. **Tournament UI** (`frontend/src/pages/games/components/multiplayer/Tournament*.tsx`)
    - Create, join, view standings, archive

**Validation gate**: `flake8`, `npx tsc --noEmit`, `pytest tests/ -v` (focused)

---

## Key Technical Decisions

### 1. Server Authority Model
- **VS games** (Connect Four, Texas Hold'em): Server-authoritative. Client sends intents, server validates and broadcasts state.
- **Race games** (Dino Runner): Client-authoritative with server timestamps. Server determines winner by timestamp comparison. Acceptable because players aren't directly interacting — they're competing in parallel.

### 2. State Synchronization
- **Sequence numbers**: Every state update has a monotonic sequence number. Clients ignore out-of-order messages.
- **No CRDT/OT**: Turn-based games don't need conflict resolution. Concurrent moves are impossible because turns are enforced server-side.
- **Race mode**: No shared state to sync — each client runs independently and reports outcomes.

### 3. Latency
- **WebSocket** (native, already supported by FastAPI + frontend): No additional library needed. FastAPI's built-in WebSocket support with `websockets` library handles the transport.
- **Message format**: JSON (simple, debuggable). Binary protobuf would be overkill for turn-based games.
- **Target latency**: < 100ms for turn-based, < 200ms for race status updates.
- **No additional npm packages needed** — browser-native `WebSocket` API is sufficient.

### 4. Room Lifecycle
- Rooms are **in-memory** on the server (not persisted to DB).
- When a game finishes, the result is persisted to `game_results` + `game_result_players`.
- If server restarts, active rooms are lost (acceptable for games — they can restart).
- Future: Redis-backed rooms for multi-process deployments.

### 5. Display Names
- Must be unique (case-insensitive).
- Migration auto-generates for existing users: `User_<first 4 chars of email>_<random 4 digits>`.
- Users can change display name at any time (validated for uniqueness).
- Display names are the ONLY identifier shown to other users — email is never exposed.

### 6. Privacy Controls
- Default: game history visible to all friends.
- User can restrict to: "opponents only" (only those who played in the game), or "private".
- Per-game overrides available.
- Blocking a user: hides all shared history from the blocked user's view.

### 7. Tournament Deletion
- Any player can **archive** a tournament (soft-delete for themselves only).
- **Deletion** requires all players to vote. Admin can force-delete.
- Game results within a tournament persist independently — deleting a tournament doesn't delete game history.

### 8. Demo Account Restrictions (RBAC-Controlled)
- **Demo users cannot play multiplayer games against human players.** They CAN play all games against AI.
- This is enforced via **RBAC permission**: `games:multiplayer` permission is required to create/join game rooms. Demo group/role does NOT have this permission.
- Multiple people can simultaneously use demo accounts (existing behavior), so demo users must not appear in friend search, cannot send/receive friend requests, and cannot join game rooms.
- The restriction is checked:
  - **Backend**: `game_room_manager.py` checks `games:multiplayer` permission on room create/join. `friends_router.py` checks permission on friend request send/search.
  - **Frontend**: `MultiplayerContext` checks user permissions and hides multiplayer UI (invite buttons, "Play Online" option) for users without `games:multiplayer`.
- Admin can grant `games:multiplayer` to any group/role via the existing RBAC system.
- This approach is clean: no hardcoded "is_demo" checks — purely permission-based. If a demo user is upgraded to a real account, they automatically gain multiplayer access when assigned the appropriate group/role.

---

## Error Handling

- **WebSocket disconnection**: Auto-reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s). Game rooms have a 60s grace period for disconnected players before forfeiting.
- **Invalid moves**: Server rejects with `game:error` message. Client shows toast notification.
- **Room full**: Server rejects join with `game:error`. Client shows "Room is full" message.
- **Friend request to blocked user**: Silently ignored (no error exposed to sender).
- **Display name taken**: Real-time availability check with debounced input.
- **Tournament with disconnected players**: Skip their turn after timeout, mark as "AFK" loss.

---

## Dependencies

### Backend
- No new Python packages. FastAPI + websockets + SQLAlchemy are sufficient.

### Frontend
- No new npm packages. Browser-native `WebSocket` API is used directly.

---

## Validation Gates

```bash
# Backend lint
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m flake8 --max-line-length=120 \
  app/models/social.py \
  app/routers/friends_router.py \
  app/routers/display_name_router.py \
  app/routers/game_history_router.py \
  app/routers/tournament_router.py \
  app/services/game_room_manager.py \
  app/services/game_result_service.py

# Backend tests
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m pytest tests/routers/test_friends_router.py -v
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 -m pytest tests/services/test_game_room_manager.py -v

# Frontend TypeScript
cd /home/ec2-user/ZenithGrid/frontend && npx tsc --noEmit

# Frontend tests
cd /home/ec2-user/ZenithGrid/frontend && npx vitest run src/pages/games/

# Migration
cd /home/ec2-user/ZenithGrid/backend && ./venv/bin/python3 update.py --yes
```

---

## References

- FastAPI WebSocket docs: https://fastapi.tiangolo.com/advanced/websockets/
- WebSocket API (MDN): https://developer.mozilla.org/en-US/docs/Web/API/WebSocket
- Existing WebSocket manager: `backend/app/services/websocket_manager.py`
- Existing WebSocket endpoint: `backend/app/main.py:662-729`
- Existing User model: `backend/app/models/auth.py:46-113`
- Existing game patterns: `frontend/src/pages/games/components/games/connect-four/ConnectFour.tsx`
- Existing game types: `frontend/src/pages/games/types.ts`
- Existing game state hook: `frontend/src/pages/games/hooks/useGameState.ts`
- Games hub PRP (for reference patterns): `PRPs/games-hub.md`

---

## Quality Checklist

- [x] All necessary context included (WebSocket infra, User model, game architecture, auth flow)
- [x] Validation gates are executable (`flake8`, `pytest`, `tsc`, `vitest`)
- [x] References existing patterns (WebSocket manager, router registration, game components)
- [x] Clear implementation path (6 phases, each independently shippable)
- [x] Error handling documented (disconnection, invalid moves, privacy, tournaments)
- [x] Server authority model chosen per game type (VS = server, Race = client)
- [x] No new dependencies required
- [x] Privacy controls specified (visibility settings, blocking)
- [x] Tournament lifecycle specified (archive vs delete, committee vote)
- [x] Display name migration plan (auto-generate for existing users)
