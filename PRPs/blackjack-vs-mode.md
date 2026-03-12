# PRP: Blackjack VS Mode — Shared Table Multiplayer

**Feature**: Two human players sit at the same Blackjack table, each playing their own hands against a shared dealer, taking turns in a real-time shared experience.
**Created**: 2026-03-12
**One-Pass Confidence Score**: 8/10

> This is a **frontend-only feature** — no backend changes needed. The existing `game:action` WebSocket infrastructure handles all turn-based communication. The Blackjack engine (`blackjackEngine.ts`) needs moderate refactoring to support a shared-table model where the host controls the shoe/dealer and broadcasts authoritative state to the guest.

---

## 1. Context & Goal

### Problem
Blackjack currently only supports `best_score` race mode — both players play independent games and compare chip counts. The user wants a proper **shared-table** experience where both players sit at the same table, see the same dealer cards, and take turns playing their hands against a shared dealer.

### Solution
Build a `BlackjackMultiplayer` component (VS mode) that:
- **Host owns the game state** (shoe, dealer hand, all player hands) and broadcasts it after each action
- **Guest receives state updates** and sends actions (hit/stand/double/split/bet) via `game:action`
- Both players see the same table — dealer at top, host's hand at bottom-left, guest's hand at bottom-right
- Turn order: betting → host plays hands → guest plays hands → dealer draws → payout → next round

### Who Benefits
- Multiplayer game players who want a shared social card game experience (like sitting at a casino table together)

### Scope
**In scope:**
- New `BlackjackMultiplayer` component for VS mode
- New `blackjackVsEngine.ts` engine for shared-table state management
- Shared 6-deck shoe, shared dealer, individual player chip stacks
- Turn-based play: betting phase → each player plays → dealer reveals → payout
- Both players see the full table at all times
- Game over when one player busts out (0 chips)
- Difficulty selection in lobby (shared, host picks)

**Out of scope:**
- Insurance, surrender, even-money side bets
- More than 2 human players (AI seats stay single-player only)
- Spectator mode for VS blackjack
- Tournament/ranking integration
- Server-authoritative game logic (client-validated, same as Chess VS)

---

## 2. Existing Code Patterns (Reference)

### 2.1 Chess VS Mode — The Reference Pattern

**File**: `frontend/src/pages/games/components/games/chess/Chess.tsx` (lines 512-531)

The `renderMultiplayer` function branches on mode:
```typescript
renderMultiplayer={(roomId, players, playerNames, mode, roomConfig, onLeave) =>
  mode === 'vs' ? (
    <ChessMultiplayer roomId={roomId} players={players} playerNames={playerNames} onLeave={onLeave} />
  ) : (
    <ChessRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} onLeave={onLeave} />
  )
}
```

**File**: `frontend/src/pages/games/components/games/chess/ChessMultiplayer.tsx`

Key patterns to follow:
- **Role assignment**: `players[0]` (host) = Player 1 (acts first), `players[1]` (guest) = Player 2
- **State ownership**: Both clients maintain local game state. For Blackjack, the **host is authoritative** because of the shared shoe (random card draws must be consistent)
- **Message filtering**: `if (msg.playerId === user?.id) return` — ignore own echoed actions
- **Ref-based state**: `stateRef.current` avoids stale closures in WebSocket listeners
- **Turn disabling**: `disabled={!isMyTurn}` prevents out-of-turn clicks

### 2.2 Blackjack Engine — Current State

**File**: `frontend/src/pages/games/components/games/blackjack/blackjackEngine.ts` (562 lines)

Key types:
```typescript
interface BlackjackState {
  shoe: Card[]
  playerHands: Hand[]      // Current active player's hands
  dealerHand: Card[]
  aiPlayers: AiPlayer[]
  chips: number            // Active player's chips
  dealerChips: number
  currentBet: number
  phase: Phase             // 'betting' | 'playerTurn' | 'aiTurn' | 'dealerTurn' | 'payout'
  difficulty: Difficulty
  message: string
}

interface Hand {
  cards: Card[]
  bet: number
  stood: boolean
  doubled: boolean
  result: string  // '', 'win', 'lose', 'push', 'bust', 'blackjack'
}
```

Key engine functions (all pure, immutable):
- `createBlackjackGame(difficulty, numOpponents)` → initial state
- `placeBet(state, bet)` → deals cards, checks blackjacks
- `hit(state)` → draw card for active hand
- `stand(state)` → mark hand as stood, advance
- `doubleDown(state)` → double bet, draw one card
- `split(state)` → split pair into two hands
- `dealerStep(state)` → dealer draws one card (called repeatedly by UI timer)
- `resolvePayout(state)` → compare all hands to dealer, update chips
- `scoreHand(cards)` → `{ total, isSoft, isBust, isBlackjack }`

### 2.3 MultiplayerWrapper Integration

**File**: `frontend/src/pages/games/components/multiplayer/MultiplayerWrapper.tsx`

The `renderMultiplayer` callback receives:
```typescript
(roomId: string, players: number[], playerNames: Record<number, string>,
 mode: string, roomConfig: RoomConfig, onLeave: () => void) => ReactNode
```

- `players[0]` = host (room creator), `players[1]` = guest (joiner)
- `roomConfig.difficulty` = shared difficulty chosen in lobby
- `mode` = `'vs'` or `'race'` (simplified from the full MultiplayerMode)

### 2.4 WebSocket Communication

**File**: `frontend/src/services/gameSocket.ts`

```typescript
gameSocket.sendAction(roomId, { type: 'bet', amount: 50 })
gameSocket.on('game:action', (msg) => {
  if (msg.playerId === user?.id) return  // Skip own echo
  const action = msg.action
  // Apply action...
})
```

The `game:action` message is broadcast to ALL players in the room (including sender). The `msg.playerId` field is set server-side and is authoritative.

### 2.5 Game Registration

**File**: `frontend/src/pages/games/constants.ts` (lines 249-261)
```typescript
{
  id: 'blackjack',
  name: 'Blackjack',
  multiplayer: ['best_score'],  // Change to: ['vs', 'best_score']
}
```

---

## 3. Architecture Design

### 3.1 State Ownership Model

**Host-authoritative** — the host controls the shoe and dealer logic:

```
Host                                Guest
┌───────────────────────┐          ┌───────────────────────┐
│ VsBlackjackState      │          │ VsBlackjackState      │
│ (owns shoe, dealer)   │          │ (mirror of host)      │
│                       │          │                       │
│ ┌─ Host actions ────┐ │          │                       │
│ │ placeBet, hit,    │ │ action   │                       │
│ │ stand, double,    │─┼─────────►│ Apply action          │
│ │ split             │ │          │ (no shoe needed)      │
│ └───────────────────┘ │          │                       │
│                       │ sync     │                       │
│ After each action:    │─────────►│ Replace full state    │
│ broadcast full state  │          │ (except shoe)         │
│                       │          │                       │
│ ┌─ Guest actions ───┐ │ action   │ ┌─ Guest actions ───┐ │
│ │ Host applies      │◄┼─────────┤ │ placeBet, hit,    │ │
│ │ on behalf of guest│ │          │ │ stand, double,    │ │
│ └───────────────────┘ │          │ │ split             │ │
│                       │ sync     │ └───────────────────┘ │
│ Broadcast updated     │─────────►│ Replace full state    │
│ state after guest act │          │                       │
└───────────────────────┘          └───────────────────────┘
```

**Why host-authoritative?** The shoe contains random card draws. If both clients maintained independent shoes, they'd draw different cards. The host draws cards and broadcasts the results. The guest never touches the shoe.

### 3.2 VS State Interface

New file: `blackjackVsEngine.ts`

```typescript
export interface VsPlayer {
  id: number               // User ID
  name: string             // Display name
  hands: Hand[]            // Current hands (supports split)
  activeHandIndex: number  // Which hand is being played
  chips: number
  currentBet: number
  finished: boolean        // All hands stood/busted for this round
}

export type VsPhase =
  | 'betting'         // Both players place bets (simultaneous)
  | 'dealing'         // Cards being dealt (animated)
  | 'playerTurn'      // A specific player is acting
  | 'dealerTurn'      // Dealer drawing cards
  | 'payout'          // Results shown

export interface VsBlackjackState {
  shoe: Card[]             // Only meaningful on host
  players: VsPlayer[]      // [0] = host, [1] = guest
  dealerHand: Card[]
  dealerChips: number
  activePlayerIndex: number  // Which player's turn (0=host, 1=guest)
  phase: VsPhase
  difficulty: Difficulty
  message: string
  betsPlaced: boolean[]    // Track which players have placed bets [host, guest]
  roundNumber: number
}
```

### 3.3 Game Flow

```
Round start: phase = 'betting'
├─ Both players select bet amounts (simultaneous, not turn-based)
├─ Each player sends: { type: 'bet', amount: N }
├─ Once both bets received → host deals cards
│
phase = 'playerTurn', activePlayerIndex = 0 (host)
├─ Host plays: hit/stand/double/split
├─ Host finishes all hands → activePlayerIndex = 1 (guest)
│
phase = 'playerTurn', activePlayerIndex = 1 (guest)
├─ Guest plays: hit/stand/double/split
├─ Guest finishes all hands → dealer turn
│
phase = 'dealerTurn'
├─ Host runs dealer logic (one card at a time, animated)
├─ Dealer stands or busts → payout
│
phase = 'payout'
├─ Results shown for both players
├─ "Next Hand" button (either player can trigger)
├─ Check game over (any player at 0 chips)
└─ Loop back to betting
```

### 3.4 Action Messages

All actions flow through `game:action`:

```typescript
// Betting
{ type: 'bet', amount: number }

// Player actions (only valid when it's your turn)
{ type: 'hit' }
{ type: 'stand' }
{ type: 'double' }
{ type: 'split' }

// State sync (host → guest, sent after every state change)
{ type: 'state_sync', state: VsBlackjackState }  // shoe omitted

// Next round
{ type: 'next_round' }

// Game over acknowledgment
{ type: 'game_over' }
```

### 3.5 Table Layout

```
┌─────────────────────────────────────────┐
│              DEALER (top)               │
│         [Card] [Card] [Card?]           │
│            Chips: 5000                  │
├─────────────────────────────────────────┤
│                                         │
│    Host (P1)          Guest (P2)        │
│    ┌────────┐         ┌────────┐        │
│    │ [Card] │         │ [Card] │        │
│    │ [Card] │         │ [Card] │        │
│    │ 15     │         │ 19     │        │
│    │ 💰 950 │         │ 💰 1050│        │
│    └────────┘         └────────┘        │
│                                         │
│          [Actions: Hit/Stand/...]       │
│          (only shown for active player) │
│                                         │
│              [Message Area]             │
└─────────────────────────────────────────┘
```

- Active player's hand has a highlight ring
- Non-active player's hand is dimmed
- Both players always see both hands
- Actions only appear for the currently-active player on their own screen

---

## 4. Implementation Tasks

### Task 1: Create `blackjackVsEngine.ts`

**File**: `frontend/src/pages/games/components/games/blackjack/blackjackVsEngine.ts`

This engine manages shared-table state. Key differences from single-player engine:
- Two player slots instead of one
- Betting is simultaneous (tracked by `betsPlaced[]`)
- Turn order: host first, then guest, then dealer
- Payout resolves each player's hands independently against dealer
- Game over when any player hits 0 chips

Functions to implement:
```typescript
// Creation
createVsGame(difficulty: Difficulty, hostId: number, hostName: string,
             guestId: number, guestName: string): VsBlackjackState

// Betting (both players bet, deal when both ready)
vsPlaceBet(state: VsBlackjackState, playerIndex: number, amount: number): VsBlackjackState
vsBothBetsPlaced(state: VsBlackjackState): boolean
vsDeal(state: VsBlackjackState): VsBlackjackState  // Deal cards once both bets in

// Player actions (operate on activePlayerIndex)
vsHit(state: VsBlackjackState): VsBlackjackState
vsStand(state: VsBlackjackState): VsBlackjackState
vsDoubleDown(state: VsBlackjackState): VsBlackjackState
vsSplit(state: VsBlackjackState): VsBlackjackState

// Dealer
vsDealerStep(state: VsBlackjackState): VsBlackjackState
vsDealerMustHit(state: VsBlackjackState): boolean

// Payout & queries
vsResolvePayout(state: VsBlackjackState): VsBlackjackState
vsNewRound(state: VsBlackjackState): VsBlackjackState
vsIsGameOver(state: VsBlackjackState): boolean
vsGetWinner(state: VsBlackjackState): number | null  // playerIndex of winner, null if draw

// Query helpers
vsCanSplit(state: VsBlackjackState): boolean
vsCanDoubleDown(state: VsBlackjackState): boolean
```

Reuse from existing engine: `scoreHand()`, `ensureShoe()`, `drawCard()`, `Hand` type, `BET_SIZES`, `STARTING_CHIPS`, `SHOE_DECKS`, `RESHUFFLE_THRESHOLD`. Export these from `blackjackEngine.ts` if not already exported.

### Task 2: Create `BlackjackMultiplayer.tsx`

**File**: `frontend/src/pages/games/components/games/blackjack/BlackjackMultiplayer.tsx`

Component structure:
```typescript
interface BlackjackMultiplayerProps {
  roomId: string
  players: number[]
  playerNames?: Record<number, string>
  difficulty?: string
  onLeave?: () => void
}

function BlackjackMultiplayer({ roomId, players, playerNames, difficulty, onLeave }: BlackjackMultiplayerProps) {
  const { user } = useAuth()
  const isHost = players[0] === user?.id
  const myPlayerIndex = isHost ? 0 : 1

  const [gameState, setGameState] = useState<VsBlackjackState>(() =>
    createVsGame(
      (difficulty as Difficulty) || 'easy',
      players[0], playerNames?.[players[0]] ?? 'Player 1',
      players[1], playerNames?.[players[1]] ?? 'Player 2',
    )
  )
  const stateRef = useRef(gameState)
  stateRef.current = gameState

  const [selectedBet, setSelectedBet] = useState(BET_SIZES[0])
  const [gameStatus, setGameStatus] = useState<'playing' | 'won' | 'lost'>('playing')

  // Music & SFX
  const song = useMemo(() => getSongForGame('blackjack'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('blackjack')

  // === WebSocket: listen for opponent actions ===
  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg) => {
      if (msg.playerId === user?.id) return  // Ignore own echo

      const action = msg.action
      if (!action) return

      if (action.type === 'state_sync') {
        // Guest receives authoritative state from host
        if (!isHost) {
          setGameState(action.state as VsBlackjackState)
        }
        return
      }

      // Host processes guest actions
      if (isHost) {
        if (action.type === 'bet') {
          handleRemoteBet(action.amount as number)
        } else if (action.type === 'hit') {
          handleRemoteAction(vsHit)
        } else if (action.type === 'stand') {
          handleRemoteAction(vsStand)
        } else if (action.type === 'double') {
          handleRemoteAction(vsDoubleDown)
        } else if (action.type === 'split') {
          handleRemoteAction(vsSplit)
        } else if (action.type === 'next_round') {
          handleNextRound()
        }
      }

      // Non-host: next_round from host
      if (!isHost && action.type === 'next_round') {
        // State sync will handle the update
      }
    })
    return unsub
  }, [roomId, isHost])

  // Host: broadcast state after every change
  useEffect(() => {
    if (isHost) {
      // Strip shoe from broadcast (guest doesn't need it, saves bandwidth)
      const { shoe, ...stateWithoutShoe } = gameState
      gameSocket.sendAction(roomId, {
        type: 'state_sync',
        state: { ...stateWithoutShoe, shoe: [] },
      })
    }
  }, [gameState, isHost, roomId])

  // ... action handlers, dealer timer, rendering ...
}
```

**Key behaviors:**
- **Host** processes ALL game actions (both local and remote) and broadcasts state
- **Guest** sends action intents and receives authoritative state via `state_sync`
- **Betting** is simultaneous — both players can bet at the same time, deal happens when both are ready
- **Player turn** actions are only accepted when `activePlayerIndex` matches
- **Dealer timer** only runs on host (same pattern as single-player: `useEffect` with `setTimeout`)
- **Game over** detected by either player when chips hit 0

### Task 3: Update `Blackjack.tsx` Export

**File**: `frontend/src/pages/games/components/games/blackjack/Blackjack.tsx`

Update the default export to support both modes:
```typescript
import { BlackjackMultiplayer } from './BlackjackMultiplayer'

export default function Blackjack() {
  return (
    <MultiplayerWrapper
      config={{
        gameId: 'blackjack',
        gameName: 'Blackjack',
        modes: ['vs', 'best_score'],       // ADD 'vs'
        maxPlayers: 2,
        hasDifficulty: true,
        modeDescriptions: {
          vs: 'Same table, same dealer',
          best_score: 'Highest chip count wins',
        },
      }}
      renderSinglePlayer={() => <BlackjackSinglePlayer />}
      renderMultiplayer={(roomId, players, playerNames, mode, roomConfig, onLeave) =>
        mode === 'vs' ? (
          <BlackjackMultiplayer
            roomId={roomId}
            players={players}
            playerNames={playerNames}
            difficulty={roomConfig.difficulty as string}
            onLeave={onLeave}
          />
        ) : (
          <BlackjackRaceWrapper roomId={roomId} difficulty={roomConfig.difficulty} onLeave={onLeave} />
        )
      }
    />
  )
}
```

### Task 4: Update Game Constants

**File**: `frontend/src/pages/games/constants.ts` (line 260)

```typescript
multiplayer: ['vs', 'best_score'],  // was: ['best_score']
```

### Task 5: Export Shared Utilities from `blackjackEngine.ts`

Some constants and functions need to be accessible from `blackjackVsEngine.ts`:

Already exported: `scoreHand`, `BET_SIZES`, `STARTING_CHIPS`, `Hand`, `Difficulty`, `canSplit`, `canDoubleDown`

Need to export (currently private):
```typescript
export const SHOE_DECKS = 6
export const RESHUFFLE_THRESHOLD = 0.25
export function ensureShoe(shoe: Card[]): Card[] { ... }
export function drawCard(shoe: Card[]): [Card, Card[]] { ... }
```

### Task 6: Handle Game Over in VS Mode

When a player's chips reach 0:
- Show a result overlay (can reuse `GameOverModal` pattern or custom overlay)
- The player with chips remaining wins
- Both players see the result
- "Back to Lobby" button sends `game:back_to_lobby` via the existing `onLeave` prop

---

## 5. Files to Modify

| File | Changes |
|------|---------|
| `blackjack/blackjackVsEngine.ts` | **NEW** — VS mode game engine |
| `blackjack/BlackjackMultiplayer.tsx` | **NEW** — VS mode multiplayer component |
| `blackjack/Blackjack.tsx` | Add `'vs'` mode, import `BlackjackMultiplayer`, update `renderMultiplayer` branch |
| `blackjack/blackjackEngine.ts` | Export `SHOE_DECKS`, `RESHUFFLE_THRESHOLD`, `ensureShoe`, `drawCard` |
| `games/constants.ts` | Add `'vs'` to blackjack multiplayer array |

---

## 6. Validation Gates

```bash
# TypeScript — must pass with no errors
cd /home/ec2-user/ZenithGrid/frontend && npx tsc --noEmit

# Build — must produce valid bundle
cd /home/ec2-user/ZenithGrid && ./bot.sh build

# Manual testing checklist (2 browser windows):
# 1. Create room in VS mode, second player joins
# 2. Both players can select and place bets simultaneously
# 3. After both bet, cards are dealt to both players + dealer
# 4. Host plays first (hit/stand/double/split work)
# 5. After host finishes, guest plays (same actions available)
# 6. Dealer draws after both players finish
# 7. Payout shows correct results for both players
# 8. "Next Hand" works to start another round
# 9. Game over when a player hits 0 chips
# 10. Both players see identical table state at all times
```

---

## 7. Edge Cases & Gotchas

1. **Shoe sync**: Only the host draws from the shoe. The guest receives dealt cards via state_sync. Never send the full shoe to the guest (unnecessary data, and prevents client-side card counting cheats).

2. **Simultaneous betting**: Both players bet at the same time. The host tracks `betsPlaced[0]` and `betsPlaced[1]`. When both are true, host calls `vsDeal()` and broadcasts. Show "Waiting for opponent's bet..." when one player has bet but the other hasn't.

3. **Disconnection during play**: Leverage existing `game:player_disconnect` / `game:player_reconnected` infrastructure in MultiplayerWrapper. On reconnect, the host re-sends the current state via `state_sync`. The guest's `useEffect` listener picks it up.

4. **Split with insufficient chips**: `vsCanSplit` must check the active player's chips, not a global value. Each player has independent chip stacks.

5. **Blackjack on deal**: If either player gets a natural 21 on deal, skip their turn (auto-stood). If both players have blackjacks, skip straight to dealer check.

6. **Dealer blackjack**: If dealer has blackjack on deal, skip all player turns and go straight to payout. Both players' hands are resolved against the dealer blackjack.

7. **All players bust**: If both players bust on all hands, dealer doesn't need to draw. Skip to payout.

8. **State sync size**: The full VsBlackjackState (minus shoe) should be small (~2-3KB at most). No throttling needed — send after every action.

9. **Turn enforcement**: The guest's action buttons should be disabled when it's not their turn (same as Chess pattern: `disabled={!isMyTurn}`). The host should also validate — ignore guest actions when `activePlayerIndex !== 1`.

10. **Difficulty from lobby**: The difficulty is selected in the lobby by the host and stored in `roomConfig.difficulty`. Pass it to `createVsGame()`. Don't show difficulty selection in the game UI during VS mode.

11. **Player names**: Use `playerNames` from MultiplayerWrapper to display actual usernames, not "P1"/"P2".

12. **Re-export for clean imports**: The new `BlackjackMultiplayer` component needs `useAuth` from `'../../../../../contexts/AuthContext'` and `gameSocket` from `'../../../../../services/gameSocket'`. Follow the same import paths as `ChessMultiplayer.tsx`.

---

## 8. References

### Codebase Files
- `frontend/src/pages/games/components/games/chess/ChessMultiplayer.tsx` — VS mode reference pattern (turn-based, game:action sync)
- `frontend/src/pages/games/components/games/blackjack/blackjackEngine.ts` — Current single-player engine to reuse
- `frontend/src/pages/games/components/games/blackjack/Blackjack.tsx` — Current UI to reference for table layout
- `frontend/src/pages/games/components/multiplayer/MultiplayerWrapper.tsx` — Multiplayer framework
- `frontend/src/services/gameSocket.ts` — WebSocket client
- `frontend/src/pages/games/utils/cardUtils.ts` — Card types, deck creation, shoe creation
- `frontend/src/pages/games/components/PlayingCard.tsx` — `CardFace`, `CardBack`, `CARD_SIZE` components

### External
- Standard Blackjack rules: https://en.wikipedia.org/wiki/Blackjack
- WebSocket API: https://developer.mozilla.org/en-US/docs/Web/API/WebSocket

---

## 9. Quality Checklist

- [x] All necessary context included (engine, multiplayer framework, VS pattern)
- [x] Validation gates are executable
- [x] References existing patterns (Chess VS mode)
- [x] Clear implementation path (5 tasks in order)
- [x] Error handling documented (disconnection, turn enforcement, edge cases)
- [x] State ownership model defined (host-authoritative)
- [x] No backend changes needed (uses existing game:action infrastructure)
