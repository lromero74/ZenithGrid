# PRP: Chat-to-Game Lobby Integration

**Feature**: Game controller icon in chat input that creates a game lobby and invites all channel members
**Created**: 2026-03-14
**One-Pass Confidence Score**: 8/10

> The game invitation infrastructure is already complete (WebSocket messaging, invite toast, room creation, join flow). This PRP adds a UI entry point from chat and a game picker component. Low backend work.

---

## Context & Goal

### Problem
Players in a chat conversation have no way to seamlessly start a game together. They must navigate to the Games hub, create a room, copy the room code, and share it in chat. This breaks the flow.

### Solution
Add a game controller icon to the chat input bar (next to the Giphy icon). Clicking it opens a game picker that:
1. Shows searchable multiplayer games filtered by player count
2. On selection: creates a room, navigates host to the game lobby, and sends `game:invite` to all channel members
3. Invited members see the existing `GameInviteNotification` toast with Accept/Decline

### Scope
- **In**: Game picker UI in chat input, room creation + batch invite, player count filtering
- **Out**: Mode/difficulty pre-selection in the picker (host chooses in lobby after creation), new backend endpoints

---

## Existing Infrastructure (Already Built)

### Invitation Flow (fully working)
```
Host sends game:invite → Backend validates → Routes to target user → GameInviteNotification toast
→ User clicks Accept → gameSocket.joinRoom(roomId) → Navigates to game → Lobby loads
```

### Key Components
| Component | File | Purpose |
|-----------|------|---------|
| `GameInviteNotification` | `multiplayer/GameInviteNotification.tsx` | Toast for incoming invites (Accept/Decline) |
| `GameLobby` | `multiplayer/GameLobby.tsx` | Room creation, mode/difficulty selection, invite panel |
| `InGameInvite` | `multiplayer/InGameInvite.tsx` | Mid-game friend invite dropdown (reusable pattern) |
| `gameSocket` | `services/gameSocket.ts` | `createRoom()`, `joinRoom()`, invite via `send()` |
| `game_ws_handler` | `services/game_ws_handler.py` | Handles `game:invite` — validates and routes to target |
| `game_room_manager` | `services/game_room_manager.py` | Room lifecycle, player tracking |

### WebSocket Message: `game:invite`
```typescript
gameSocket.send({
  type: 'game:invite',
  roomId: string,
  targetUserId: number,
})
```
Backend broadcasts to target:
```typescript
{
  type: 'game:invite',
  roomId, gameId, mode,
  fromUserId, fromDisplayName,
  midGame: false,
}
```

### Chat Input Bar (`ChatInput.tsx` line 336)
Current layout: `[GIF button] [textarea] [send button]`
New layout: `[GIF button] [Game button] [textarea] [send button]`

---

## Implementation Tasks

### Frontend Only (no backend changes needed)

#### 1. Create GamePicker component (`frontend/src/pages/games/components/social/GamePicker.tsx`)

A dropdown/popup similar to the GIF picker (`ChatInput.tsx` GifPicker):

```typescript
interface GamePickerProps {
  memberCount: number  // channel member count (for filtering)
  onSelect: (game: GameInfo) => void
  onClose: () => void
}
```

**UI Design:**
- Same positioning as GifPicker: `absolute bottom-full` above the input bar
- Search input at top (filter by game name)
- Scrollable list of multiplayer games
- Each game shows: icon, name, supported modes, max players
- Games filtered by: `game.multiplayer?.length > 0`
- Optionally filter by player count compatibility (if `memberCount > maxPlayers`, dim/disable)

**Filter logic:**
```typescript
const multiplayerGames = GAMES.filter(g => g.multiplayer && g.multiplayer.length > 0)
const filtered = query
  ? multiplayerGames.filter(g => g.name.toLowerCase().includes(query.toLowerCase()))
  : multiplayerGames
```

#### 2. Add game icon button to ChatInput (`ChatInput.tsx`)

Next to the GIF button (line 338 area):
```tsx
<button
  onClick={() => setShowGamePicker(!showGamePicker)}
  className={`p-1.5 rounded transition-colors shrink-0 ${
    showGamePicker ? 'text-blue-400 bg-slate-700/50' : 'text-slate-500 hover:text-slate-300'
  }`}
  title="Start a game with everyone"
>
  <Gamepad2 className="w-3.5 h-3.5" />
</button>
```

Import `Gamepad2` from `lucide-react`.

#### 3. Handle game selection → create room + invite all

When user picks a game from the picker:

```typescript
const handleGameSelect = async (game: GameInfo) => {
  setShowGamePicker(false)

  // 1. Create room (first available mode)
  const mode = game.multiplayer![0]
  gameSocket.createRoom(game.id, mode, { max_players: members.length })

  // 2. Listen for room creation response
  const unsub = gameSocket.on('game:created', (msg) => {
    unsub()
    const roomId = msg.roomId

    // 3. Invite all channel members (except self)
    for (const member of members) {
      if (member.user_id !== currentUserId) {
        gameSocket.send({
          type: 'game:invite',
          roomId,
          targetUserId: member.user_id,
        })
      }
    }

    // 4. Navigate host to the game lobby
    const gamePath = game.path
    navigate(gamePath, { state: { joiningFriend: false } })
  })
}
```

**Note**: `members` is already available as a prop to `ChatInput` (used for @mentions). `currentUserId` comes from `useAuth()`.

#### 4. Pass required props to ChatInput

In `ChatPanel.tsx`, ensure `members` and navigation capability are available to ChatInput. The `members` prop is already passed. Add `onStartGame` callback or handle navigation inside ChatInput.

#### 5. Send a chat message announcing the game

After creating the room, automatically send a chat message:
```typescript
// Auto-announce in chat
onSend(`🎮 Started a ${game.name} lobby! Check your notifications to join.`)
```

This uses the existing `onSend` prop that ChatInput already has.

---

## Key Files to Modify

| File | Change |
|------|--------|
| `frontend/src/pages/games/components/social/ChatInput.tsx` | Add game button + picker toggle + selection handler |
| `frontend/src/pages/games/components/social/GamePicker.tsx` | **New** — searchable game list popup |
| `frontend/src/pages/games/components/social/ChatPanel.tsx` | Pass `user` and navigation to ChatInput if not already |

---

## GamePicker Component Design

```
┌─────────────────────────────┐
│ 🔍 Search games...          │
├─────────────────────────────┤
│ 🎯 Tic-Tac-Toe    VS  FTW │
│ ♟️  Chess          VS  FTW │
│ 🃏 Go Fish        VS  FTW │
│ 🎰 Plinko         Race     │
│ 🐍 Snake          Race     │
│ ...                         │
└─────────────────────────────┘
```

Each row shows:
- Game icon (from GAME_ICONS)
- Game name
- Mode badges (VS, Race, Survival, Best Score)
- Click → selects and triggers room creation

---

## Edge Cases

| Case | Handling |
|------|----------|
| DM channel (2 members) | All games work — most support 2 players |
| Large group (>max_players) | Show warning; still create room — extra members get invite but room may be full |
| Member not online | Invite sent but not delivered (fire-and-forget, no error shown) |
| Host closes game picker | No action taken |
| GameSocket not connected | Button disabled or hidden |

---

## Validation Gates

```bash
# TypeScript
cd /home/ec2-user/ZenithGrid/frontend && npx tsc --noEmit

# No backend changes — no Python lint needed
```

---

## Quality Checklist

- [x] All necessary context included (invite flow, room creation, chat input, gameSocket API)
- [x] Validation gates are executable
- [x] References existing patterns (GifPicker positioning, InGameInvite flow, GameLobby creation)
- [x] Clear implementation path (5 ordered tasks)
- [x] Error handling documented (edge cases table)
- [x] No backend changes needed — existing WS infrastructure handles everything
