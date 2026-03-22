# PRP: Memory VS Mode — Turn-Based Two-Player Memory

**Feature**: Two human players share one board and take turns flipping cards. A player who finds a match keeps going; a mismatch ends their turn. When all pairs are found, the player with the most matches wins.
**Created**: 2026-03-12
**One-Pass Confidence Score**: 9/10

> This is a **frontend-only feature** — no backend changes needed. The existing `game:action` WebSocket relay handles all communication. The Memory engine needs a seeded shuffle function added, and a new `MemoryMultiplayer.tsx` component manages the shared board with turn-based play.

---

## 1. Context & Goal

### Problem
Memory currently supports only solo play and race modes (both players play independent boards). The user wants a classic **turn-based VS mode** where:
- Both players share **one board** and take turns
- On your turn, flip two cards. If they match, you score a point and flip again
- If they don't match, both cards flip back and it's the other player's turn
- Both players see all flips in real time (including opponent's reveals)
- When all pairs are found, the player with more matches wins

### Solution
Build a `MemoryMultiplayer` component (VS mode) that:
- **Host owns the board state** (card layout, who matched what) and broadcasts it after each action
- **Guest sends flip intents** via `game:action`; host processes and broadcasts the result
- Both players see the same board at all times
- Turn indicator shows whose turn it is, with player colors
- Score display shows each player's match count
- Seeded deck ensures both clients generate the same initial layout (for instant game start, no sync delay)

### Scope
**In scope:**
- New `MemoryMultiplayer` component for VS mode
- Seeded shuffle function in `memoryEngine.ts`
- Shared board, turn management, match scoring
- Both players see all card flips in real time
- Game over modal showing winner/loser
- Difficulty selection in lobby (shared, host picks)

**Out of scope:**
- More than 2 players
- AI opponent
- Spectator mode
- Server-authoritative game logic

---

## 2. Existing Code Patterns (Reference)

### 2.1 Connect Four VS Mode — The Reference Pattern

**File**: `frontend/src/pages/games/components/games/connect-four/ConnectFourMultiplayer.tsx`

This is the simplest existing VS mode implementation. Key patterns:

```typescript
interface ConnectFourMultiplayerProps {
  roomId: string
  players: number[]
  playerNames?: Record<number, string>
  onLeave?: () => void
}

export function ConnectFourMultiplayer({ roomId, players, playerNames = {}, onLeave }) {
  const { user } = useAuth()
  // Host = first player (red), guest = second player (yellow)
  const myColor: Player = players[0] === user?.id ? 'red' : 'yellow'
  const isMyTurn = currentPlayer === myColor

  // Listen for opponent actions
  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg) => {
      if (msg.playerId === user?.id) return  // Skip own echo
      // Apply opponent's move...
      setCurrentPlayer(myColor) // Switch back to my turn
    })
    return unsub
  }, [roomId, myColor, ...])

  // Send local move
  const handleClick = useCallback((col) => {
    if (!isMyTurn) return
    gameSocket.sendAction(roomId, { type: 'drop', col })
    // Apply locally, switch turn
    setCurrentPlayer(opponentColor)
  }, [...])
}
```

Key points:
- `players[0]` (host) always goes first
- `msg.playerId === user?.id` filters own echoed actions
- Both clients validate and apply moves locally
- `boardRef.current` avoids stale closures in WS listener
- `GameOverModal` with `playAgainText="Back to Lobby"` using `onLeave`

### 2.2 Memory Engine — Current State

**File**: `frontend/src/pages/games/components/games/memory/memoryEngine.ts` (85 lines)

Key types and functions:
```typescript
interface Card {
  id: number
  symbol: string
  flipped: boolean
  matched: boolean
}

type GridSize = 'easy' | 'medium' | 'hard'

// Grid configs: easy=3×4 (6 pairs), medium=4×4 (8 pairs), hard=4×6 (12 pairs)
function getGridDimensions(size: GridSize): { rows: number; cols: number; pairs: number }
function createDeck(pairCount: number): Card[]     // Fisher-Yates shuffle with Math.random
function flipCard(cards: Card[], index: number): Card[]  // Immutable update
function checkMatch(card1: Card, card2: Card): boolean   // Compare symbols
function checkGameComplete(cards: Card[]): boolean       // All cards matched?
function countMoves(flippedCount: number): number        // flips / 2
```

**Important**: `createDeck` uses `Math.random` for shuffle. For multiplayer, both clients need the same deck order, so we need a **seeded shuffle** variant. Add `createSeededDeck(pairCount, rng)` that accepts a PRNG function.

### 2.3 Memory Single Player — Card Click Flow

**File**: `frontend/src/pages/games/components/games/memory/Memory.tsx` (lines 200-268)

The single-player click handler shows the card matching flow:
1. Skip if locked, won, already matched/flipped
2. Flip the card (immutable update)
3. Push index to `flippedIndices` array
4. When 2 cards flipped:
   - Lock UI (`lockRef.current = true`)
   - If match: mark both `matched: true`, unlock immediately, check win
   - If no match: play mismatch SFX, wait 800ms, flip both back, unlock

For VS mode, the flow is similar but:
- Only the active player can flip cards
- A match means: score +1 and same player keeps going
- A mismatch means: flip back after 800ms delay, then switch turns
- Both clients see every flip in real time

### 2.4 Card Grid Rendering

The grid uses CSS 3D transforms for flip animation:
```tsx
<div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
  {cards.map((card, index) => {
    const isRevealed = card.flipped || card.matched
    return (
      <div key={card.id} style={{ perspective: '600px' }} onClick={() => handleClick(index)}>
        <div style={{
          transformStyle: 'preserve-3d',
          transform: isRevealed ? 'rotateY(180deg)' : 'none',
          transition: 'transform 0.4s',
        }}>
          {/* Back face: slate with "?" */}
          {/* Front face: white with emoji */}
        </div>
      </div>
    )
  })}
</div>
```

Card sizes: `w-16 h-20 sm:w-20 sm:h-24`

### 2.5 Seeded Random Utility

**File**: `frontend/src/pages/games/utils/seededRandom.ts`

```typescript
export function createSeededRandom(seed: number): () => number
```

Mulberry32 PRNG. Two clients with the same seed produce identical sequences. Use this to create a deterministic deck so both clients start with identical card layouts without needing to sync the full deck over WebSocket.

### 2.6 WebSocket Action Flow

**File**: `frontend/src/services/gameSocket.ts`

```typescript
// Send action to room
gameSocket.sendAction(roomId, { type: 'flip', index: 5 })

// Listen for actions
gameSocket.on('game:action', (msg) => {
  // msg.playerId — set by server (authoritative)
  // msg.action — the action payload
})
```

**File**: `backend/app/services/game_ws_handler.py` (line 479)

The backend simply relays `game:action` messages to all players in the room. It adds `playerId` server-side. No game logic validation on the backend.

### 2.7 MultiplayerWrapper Integration

**File**: `frontend/src/pages/games/components/multiplayer/MultiplayerWrapper.tsx`

The `renderMultiplayer` callback receives:
```typescript
(roomId: string, players: number[], playerNames: Record<number, string>,
 mode: string, roomConfig: RoomConfig, onLeave: () => void) => ReactNode
```

- `players[0]` = host, `players[1]` = guest
- `mode` = `'vs'` or `'race'`
- `roomConfig.difficulty` = difficulty chosen in lobby
- Branch on mode to render VS or Race component

### 2.8 Game Seed for Multiplayer

The multiplayer framework provides a `gameSeed` via `useRaceMode`, but for VS mode we don't use `useRaceMode`. Instead, the **host generates a seed** and sends it as the first action. Both clients use it to create identical decks via `createSeededDeck(pairs, createSeededRandom(seed))`.

Alternative (simpler): the host creates the deck and sends the full card array (sans symbols visible) as the first sync. But seeded is cleaner and saves bandwidth.

**Simplest approach**: Use `roomId` as the seed source. Both clients have `roomId` — hash it to a number and use as seed. No extra sync needed.

```typescript
// Simple string hash for seed
function hashString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0
  }
  return hash
}
const seed = hashString(roomId)
const rng = createSeededRandom(seed)
const cards = createSeededDeck(pairs, rng)
```

---

## 3. Architecture Design

### 3.1 State Ownership Model

**Host-authoritative** — the host processes all flips and broadcasts state:

```
Host                                Guest
┌──────────────────────────┐       ┌──────────────────────────┐
│ VsMemoryState            │       │ VsMemoryState            │
│ (authoritative)          │       │ (mirror of host)         │
│                          │       │                          │
│ ┌─ Host flips ─────────┐ │       │                          │
│ │ Flip card, check     │ │ sync  │                          │
│ │ match, update score, │─┼──────►│ Replace full state       │
│ │ switch turn if miss  │ │       │                          │
│ └──────────────────────┘ │       │                          │
│                          │       │ ┌─ Guest flips ────────┐ │
│ ┌─ Process guest flip ─┐ │ flip  │ │ Send flip intent:   │ │
│ │ Apply to board, sync │◄┼──────┤ │ { type:'flip', idx } │ │
│ └──────────────────────┘ │       │ └─────────────────────┘ │
│        │                 │ sync  │                          │
│        └─────────────────┼──────►│ Replace full state       │
│                          │       │                          │
└──────────────────────────┘       └──────────────────────────┘
```

**Why host-authoritative?** Even with seeded decks, the timing of flips, match resolution, and turn switching must be consistent. Having one source of truth prevents desync from race conditions (e.g., both players clicking at the same instant).

### 3.2 VS State Interface

```typescript
interface VsMemoryState {
  cards: Card[]                    // Shared board
  currentPlayer: 0 | 1            // Index into players array (0=host, 1=guest)
  scores: [number, number]        // [host matches, guest matches]
  flippedIndices: number[]         // Currently face-up (0, 1, or 2 cards)
  locked: boolean                  // True during match-check delay
  gameOver: boolean
  totalPairs: number
}
```

### 3.3 Game Flow

```
Game start:
├─ Both clients generate identical deck from seeded RNG (roomId hash)
├─ Host goes first (currentPlayer = 0)
│
Player's turn:
├─ Active player clicks a face-down card
│  ├─ If on host: process locally, broadcast state
│  └─ If on guest: send { type: 'flip', index } to host
│
├─ Card flips face-up (flippedIndices grows to 1)
├─ Active player clicks a second face-down card
│  ├─ flippedIndices grows to 2
│  ├─ Lock board (800ms delay for both players to see)
│  │
│  ├─ MATCH:
│  │  ├─ Mark both cards as matched
│  │  ├─ Increment active player's score
│  │  ├─ Clear flippedIndices, unlock
│  │  ├─ Same player keeps going!
│  │  └─ Check if all pairs matched → game over
│  │
│  └─ NO MATCH:
│     ├─ After 800ms: flip both cards back
│     ├─ Clear flippedIndices, unlock
│     └─ Switch currentPlayer to other player
│
Game over:
├─ All pairs matched
├─ Compare scores → winner has more matches
├─ Tie possible (equal scores)
└─ Show GameOverModal with result
```

### 3.4 Action Messages

```typescript
// Player flips a card
{ type: 'flip', index: number }

// Host broadcasts full board state after each action
{ type: 'state_sync', state: VsMemoryState }

// New game request (from either player, back to lobby)
// Uses existing onLeave / game:back_to_lobby
```

### 3.5 Table Layout

```
┌─────────────────────────────────────────────────┐
│  Memory — VS        [Your turn / Opponent's turn]│
│                                                   │
│  🟣 You: 3 matches    🟠 Opponent: 2 matches     │
│                                                   │
│  ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐                 │
│  │🐶│ │? │ │? │ │🐱│ │? │ │? │                 │
│  └──┘ └──┘ └──┘ └──┘ └──┘ └──┘                 │
│  ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐                 │
│  │? │ │? │ │🐭│ │? │ │🐭│ │? │                 │
│  └──┘ └──┘ └──┘ └──┘ └──┘ └──┘                 │
│  ... (more rows based on difficulty)             │
│                                                   │
│  Matched cards show with player's color border    │
│  (purple for you, orange for opponent)            │
└─────────────────────────────────────────────────┘
```

- Active player's score label has a pulsing indicator
- Matched cards show the color of the player who matched them
- Non-active player's clicks are ignored (disabled state)
- Both players see cards flip in real time (including opponent's reveals)

---

## 4. Implementation Tasks

### Task 1: Add seeded shuffle to `memoryEngine.ts`

**File**: `frontend/src/pages/games/components/games/memory/memoryEngine.ts`

Add a new export that accepts an RNG function:

```typescript
/** Create a shuffled deck using a provided RNG function (for multiplayer sync). */
export function createSeededDeck(pairCount: number, rng: () => number): Card[] {
  const selectedSymbols = SYMBOLS.slice(0, pairCount)
  const cards: Card[] = []
  for (let i = 0; i < pairCount; i++) {
    const symbol = selectedSymbols[i % selectedSymbols.length]
    cards.push(
      { id: i * 2, symbol, flipped: false, matched: false },
      { id: i * 2 + 1, symbol, flipped: false, matched: false },
    )
  }
  // Fisher-Yates with provided RNG
  const a = [...cards]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}
```

Also export `SYMBOLS` (currently private) so the VS component can reference it if needed, or just keep it internal since `createSeededDeck` handles it.

### Task 2: Create `MemoryMultiplayer.tsx`

**File**: `frontend/src/pages/games/components/games/memory/MemoryMultiplayer.tsx`

This is the main deliverable. Follow the ConnectFour VS pattern.

```typescript
interface MemoryMultiplayerProps {
  roomId: string
  players: number[]
  playerNames?: Record<number, string>
  difficulty?: string
  onLeave?: () => void
}

export function MemoryMultiplayer({
  roomId, players, playerNames = {}, difficulty = 'easy', onLeave
}: MemoryMultiplayerProps) {
  const { user } = useAuth()
  const isHost = players[0] === user?.id
  const myIndex = isHost ? 0 : 1
  const opponentIndex = isHost ? 1 : 0

  // Generate identical deck from roomId hash
  const gridSize = difficulty as GridSize
  const { pairs, cols } = getGridDimensions(gridSize)
  const initialCards = useMemo(() => {
    const seed = hashString(roomId)
    return createSeededDeck(pairs, createSeededRandom(seed))
  }, [roomId, pairs])

  const [cards, setCards] = useState<Card[]>(initialCards)
  const [currentPlayer, setCurrentPlayer] = useState<0 | 1>(0) // Host goes first
  const [scores, setScores] = useState<[number, number]>([0, 0])
  const [flippedIndices, setFlippedIndices] = useState<number[]>([])
  const [locked, setLocked] = useState(false)
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')

  const isMyTurn = currentPlayer === myIndex
  const totalPairs = pairs

  // Refs for WS listener
  const cardsRef = useRef(cards)
  cardsRef.current = cards
  const currentPlayerRef = useRef(currentPlayer)
  currentPlayerRef.current = currentPlayer
  const scoresRef = useRef(scores)
  scoresRef.current = scores
  const flippedRef = useRef(flippedIndices)
  flippedRef.current = flippedIndices
  const lockedRef = useRef(locked)
  lockedRef.current = locked

  // Host processes flips, broadcasts state
  // Guest sends flip intent, receives state_sync
  // ... (see full implementation in architecture section)
}
```

**Key logic in the component:**

1. **`handleFlip(index)`** — called when any player clicks a card:
   - If I'm host AND it's my turn: process flip locally, broadcast state
   - If I'm host AND it's guest's turn: ignore (guest will send flip action)
   - If I'm guest AND it's my turn: send `{ type: 'flip', index }` to host
   - If I'm guest AND it's not my turn: ignore

2. **Host flip processing** (extracted function `processFlip`):
   ```typescript
   function processFlip(index: number) {
     if (lockedRef.current) return
     const card = cardsRef.current[index]
     if (card.matched || card.flipped) return

     const newCards = flipCard(cardsRef.current, index)
     const newFlipped = [...flippedRef.current, index]
     setCards(newCards)
     setFlippedIndices(newFlipped)

     if (newFlipped.length === 2) {
       setLocked(true)
       const [first, second] = newFlipped
       if (checkMatch(newCards[first], newCards[second])) {
         // Match! Score + same player continues
         const matched = newCards.map((c, i) =>
           i === first || i === second
             ? { ...c, matched: true, matchedBy: currentPlayerRef.current }
             : c
         )
         const newScores = [...scoresRef.current] as [number, number]
         newScores[currentPlayerRef.current]++
         setCards(matched)
         setScores(newScores)
         setFlippedIndices([])
         setLocked(false)
         // Check game over
         if (checkGameComplete(matched)) {
           setGameStatus(newScores[myIndex] > newScores[opponentIndex] ? 'won'
             : newScores[myIndex] < newScores[opponentIndex] ? 'lost' : 'draw')
         }
         broadcastState(matched, currentPlayerRef.current, newScores, [])
       } else {
         // No match — flip back after 800ms, switch turn
         broadcastState(newCards, currentPlayerRef.current, scoresRef.current, newFlipped)
         setTimeout(() => {
           const flippedBack = newCards.map((c, i) =>
             i === first || i === second ? { ...c, flipped: false } : c
           )
           const nextPlayer = currentPlayerRef.current === 0 ? 1 : 0
           setCards(flippedBack)
           setCurrentPlayer(nextPlayer as 0 | 1)
           setFlippedIndices([])
           setLocked(false)
           broadcastState(flippedBack, nextPlayer, scoresRef.current, [])
         }, 800)
       }
     } else {
       // First card flipped — broadcast immediately so opponent sees it
       broadcastState(newCards, currentPlayerRef.current, scoresRef.current, newFlipped)
     }
   }
   ```

3. **`broadcastState`** — host sends full state to guest:
   ```typescript
   function broadcastState(cards, currentPlayer, scores, flippedIndices) {
     gameSocket.sendAction(roomId, {
       type: 'state_sync',
       state: { cards, currentPlayer, scores, flippedIndices, locked: false }
     })
   }
   ```

4. **WS listener** — processes incoming actions:
   ```typescript
   useEffect(() => {
     const unsub = gameSocket.on('game:action', (msg) => {
       if (msg.playerId === user?.id) return

       const action = msg.action
       if (action.type === 'flip' && isHost) {
         // Guest sent a flip — process it
         processFlip(action.index)
       } else if (action.type === 'state_sync' && !isHost) {
         // Guest receives authoritative state from host
         const s = action.state
         setCards(s.cards)
         setCurrentPlayer(s.currentPlayer)
         setScores(s.scores)
         setFlippedIndices(s.flippedIndices)
         setLocked(s.locked)
         if (checkGameComplete(s.cards)) {
           setGameStatus(s.scores[myIndex] > s.scores[opponentIndex] ? 'won'
             : s.scores[myIndex] < s.scores[opponentIndex] ? 'lost' : 'draw')
         }
       }
     })
     return unsub
   }, [roomId, isHost])
   ```

5. **Card rendering** — extend `Card` interface with `matchedBy` field:
   ```typescript
   // In the grid, matched cards show the player's color
   const matchColor = card.matchedBy === myIndex
     ? 'bg-indigo-900/30 border-indigo-500'  // My matches
     : 'bg-amber-900/30 border-amber-500'    // Opponent's matches
   ```

### Task 3: Extend Card interface for `matchedBy`

**File**: `frontend/src/pages/games/components/games/memory/memoryEngine.ts`

Add optional `matchedBy` to the `Card` interface:

```typescript
export interface Card {
  id: number
  symbol: string
  flipped: boolean
  matched: boolean
  matchedBy?: number  // Player index who matched this pair (VS mode only)
}
```

This doesn't break existing code since it's optional.

### Task 4: Update `Memory.tsx` Export

**File**: `frontend/src/pages/games/components/games/memory/Memory.tsx`

Update the default export to branch on mode:

```typescript
import { MemoryMultiplayer } from './MemoryMultiplayer'

export default function Memory() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'memory',
        gameName: 'Memory',
        modes: ['vs', 'first_to_win', 'best_score'],  // ADD 'vs'
        maxPlayers: 2,
        hasDifficulty: true,
        modeDescriptions: {
          vs: 'Take turns finding pairs',
          first_to_win: 'First to finish wins',
          best_score: 'Fewest moves wins',
        },
        allowPlayOn: true,
      }}
      renderSinglePlayer={() => <MemorySinglePlayer />}
      renderMultiplayer={(roomId, players, playerNames, mode, roomConfig, onLeave) =>
        mode === 'vs' ? (
          <MemoryMultiplayer
            roomId={roomId}
            players={players}
            playerNames={playerNames}
            difficulty={roomConfig.difficulty as string}
            onLeave={onLeave}
          />
        ) : (
          <MemoryRaceWrapper
            roomId={roomId}
            difficulty={roomConfig.difficulty}
            raceType={(roomConfig.race_type as 'first_to_win' | 'best_score') || 'best_score'}
            onLeave={onLeave}
          />
        )
      }
    />
  )
}
```

### Task 5: Update Game Constants

**File**: `frontend/src/pages/games/constants.ts` (line ~213)

```typescript
multiplayer: ['vs', 'first_to_win', 'best_score'],  // was: ['first_to_win', 'best_score']
```

---

## 5. Files to Modify

| File | Changes |
|------|---------|
| `memory/MemoryMultiplayer.tsx` | **NEW** — VS mode multiplayer component (~200 lines) |
| `memory/memoryEngine.ts` | Add `createSeededDeck()`, add `matchedBy?` to `Card`, export |
| `memory/Memory.tsx` | Add `'vs'` mode, import `MemoryMultiplayer`, branch `renderMultiplayer` on mode |
| `games/constants.ts` | Add `'vs'` to memory multiplayer array |

---

## 6. Validation Gates

```bash
# TypeScript — must pass with no errors
cd /home/ec2-user/ZenithGrid/frontend && npx tsc --noEmit

# Build — must produce valid bundle
cd /home/ec2-user/ZenithGrid/frontend && npx vite build

# Manual testing checklist (2 browser windows):
# 1. Navigate to Memory → select VS mode → create room
# 2. Second player joins room → both see same difficulty/grid
# 3. Host goes first — can click cards, guest cannot
# 4. Flip two cards → both players see the flip animation
# 5. Match: both cards stay up with host's color border, host flips again
# 6. No match: cards flip back after 800ms, turn switches to guest
# 7. Guest can now flip cards, host cannot
# 8. Guest finds a match → cards show guest's color, guest continues
# 9. Scores update in real time for both players
# 10. All pairs found → GameOverModal shows winner/loser/draw
# 11. "Back to Lobby" works from GameOverModal
# 12. Switching difficulty in lobby works (different grid sizes)
```

---

## 7. Edge Cases & Gotchas

1. **Deck sync**: Both clients must produce identical card layouts. Use `hashString(roomId)` as the seed for `createSeededRandom()`. The `roomId` is available to both clients at game start. No extra sync needed.

2. **Double-click prevention**: While the board is locked (during match check or mismatch flip-back), ignore all clicks. The `locked` state handles this. The host must also ignore guest flip actions while locked.

3. **Rapid flipping**: A player might click two cards very quickly. The `flippedIndices` array prevents flipping more than 2 cards — once length reaches 2, the board locks until match resolution completes.

4. **Same card clicked twice**: Clicking an already-flipped card should be a no-op. Check `card.flipped || card.matched` before processing.

5. **State sync ordering**: The host broadcasts state after every action. If the guest receives a sync while they were clicking (race condition), the sync overwrites their local state. This is correct — the host is authoritative.

6. **Guest sees first flip immediately**: When the host flips the first card, they broadcast immediately (before the second flip). The guest sees the card face-up in real time, not batched with the second flip.

7. **Disconnection**: If a player disconnects, the existing reconnection infrastructure handles it. On reconnect, the game state is whatever the host has. The guest can send a `{ type: 'request_sync' }` action and the host re-sends the current state.

8. **Tie scores**: With an even number of pairs, a tie is possible (each player matches exactly half). Handle as `'draw'` status in GameOverModal.

9. **Game over check on guest**: The guest should check `checkGameComplete(cards)` after every state_sync, not rely on a separate "game over" message. This keeps it simple.

10. **matchedBy tracking**: The `matchedBy` field on Card tracks which player matched each pair. This is used for color-coding matched cards. It's only set in VS mode — single-player and race mode don't set it, so no regression.

11. **Existing engine functions still work**: `flipCard`, `checkMatch`, `checkGameComplete` all work on `Card[]` — the new optional `matchedBy` field doesn't affect them.

12. **Sound effects**: Reuse existing SFX keys: `'flip'` for card flip, `'match'` for successful match, `'mismatch'` for failed match, `'win'` for game over win.

---

## 8. References

### Codebase Files
- `frontend/src/pages/games/components/games/connect-four/ConnectFourMultiplayer.tsx` — Simplest VS mode reference (174 lines)
- `frontend/src/pages/games/components/games/chess/ChessMultiplayer.tsx` — More complex VS mode reference
- `frontend/src/pages/games/components/games/memory/memoryEngine.ts` — Memory engine to extend
- `frontend/src/pages/games/components/games/memory/Memory.tsx` — Current Memory UI and race wrapper
- `frontend/src/pages/games/components/multiplayer/MultiplayerWrapper.tsx` — Multiplayer framework
- `frontend/src/services/gameSocket.ts` — WebSocket client (`sendAction`, `on`)
- `frontend/src/pages/games/utils/seededRandom.ts` — `createSeededRandom(seed)`
- `frontend/src/pages/games/components/GameOverModal.tsx` — Game over modal
- `frontend/src/pages/games/components/GameLayout.tsx` — Game layout wrapper
- `PRPs/blackjack-vs-mode.md` — Similar VS mode PRP for reference

### External
- Classic Memory game rules: https://en.wikipedia.org/wiki/Concentration_(card_game)

---

## 9. Quality Checklist

- [x] All necessary context included (engine, multiplayer framework, VS pattern, card rendering)
- [x] Validation gates are executable
- [x] References existing patterns (ConnectFour VS mode)
- [x] Clear implementation path (5 tasks in order)
- [x] Error handling documented (disconnection, double-click, race conditions)
- [x] State ownership model defined (host-authoritative)
- [x] No backend changes needed (uses existing game:action infrastructure)
- [x] Seeded deck generation solves sync problem cleanly
