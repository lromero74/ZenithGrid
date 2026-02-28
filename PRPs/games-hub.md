# PRP: Games Hub

**Feature**: Browser-based mini-games hub accessible from the header navigation
**Created**: 2026-02-28
**One-Pass Confidence Score**: 7/10

> This is a **large feature** spanning 11 games. The PRP is designed for **phased execution** — each game is an independent unit that can be built, tested, and shipped separately. The score reflects the total scope; individual game confidence is 8-9/10.

---

## Context & Goal

### Problem
Users spending time monitoring trades have downtime between market events. There's no entertainment or mental-break feature in the platform. Adding casual games increases session time, user engagement, and platform stickiness — differentiating from competing trading platforms.

### Solution
Add a "Games" section to the header navigation with a hub page listing all available games. Each game is a self-contained, client-side-only React component with no backend required. Games persist high scores and preferences in localStorage. The hub page shows game cards with icons, descriptions, and personal best scores.

### Who Benefits
All users. Games are account-independent (no trading data needed).

### Scope
- **In**: 11 browser games (Sudoku, Tic-Tac-Toe, Ultimate Tic-Tac-Toe, Connect Four, Hangman, Mahjong Solitaire, Minesweeper, 2048, Wordle, Snake, Nonogram), Games hub page, nav integration, localStorage persistence, responsive layouts, unit tests
- **Out**: Backend API, leaderboards, multiplayer, achievements system, game analytics. These can be added later if desired.

---

## Existing Code Patterns (Reference)

### Navigation Pattern (from `App.tsx` lines 440-570)

Nav links follow this exact pattern — each is a `<Link>` with active state styling:

```tsx
import { Gamepad2 } from 'lucide-react'  // Add to icon imports on line 4

// Lazy load (add after line 42)
const Games = lazy(() => import('./pages/Games'))

// Nav link (add after Reports link, before Settings link ~line 557)
<Link
  to="/games"
  className={`px-3 sm:px-4 py-3 font-medium transition-colors text-sm sm:text-base ${
    location.pathname === '/games'
      ? 'text-blue-400 border-b-2 border-blue-400'
      : 'text-slate-400 hover:text-white'
  }`}
>
  <div className="flex items-center space-x-1 sm:space-x-2">
    <Gamepad2 className="w-4 h-4" />
    <span className="hidden sm:inline">Games</span>
  </div>
</Link>

// Route (add after /settings route ~line 592)
<Route path="/games/*" element={<Games />} />
```

**Note**: Use `/games/*` wildcard route so sub-routes like `/games/sudoku` work via nested routing.

### Page Component Pattern (from News, Charts, Bots)

Pages follow this structure:
```
pages/
├── Games.tsx                    # Main page component (lazy-loaded from App.tsx)
└── games/
    ├── index.ts                 # Module exports
    ├── types.ts                 # Game-specific TypeScript types
    ├── constants.ts             # Game registry, shared constants
    ├── helpers.ts               # Pure utility functions (tested)
    ├── helpers.test.ts          # Tests for helpers
    ├── components/
    │   ├── GameHub.tsx           # Hub landing page with game cards
    │   ├── GameCard.tsx          # Individual game card on hub
    │   ├── GameLayout.tsx        # Shared game page wrapper (back button, title, score)
    │   └── games/               # Individual game components
    │       ├── Sudoku/
    │       │   ├── Sudoku.tsx
    │       │   ├── SudokuBoard.tsx
    │       │   ├── SudokuControls.tsx
    │       │   ├── sudokuEngine.ts      # Pure game logic (generation, validation, solving)
    │       │   └── sudokuEngine.test.ts
    │       ├── TicTacToe/
    │       │   ├── TicTacToe.tsx
    │       │   ├── ticTacToeEngine.ts
    │       │   └── ticTacToeEngine.test.ts
    │       └── ... (same pattern for each game)
    └── hooks/
        ├── useGameScores.ts     # localStorage high score management
        ├── useGameTimer.ts      # Shared timer hook
        └── useKeyboard.ts       # Shared keyboard input hook
```

### Test Pattern (from `botUtils.test.ts`, `helpers.test.ts`)

Tests use vitest with this exact pattern:
```typescript
import { describe, test, expect } from 'vitest'
import { myFunction } from './myModule'

describe('myFunction', () => {
  test('happy path description', () => {
    expect(myFunction(validInput)).toBe(expectedOutput)
  })

  test('edge case description', () => {
    expect(myFunction(edgeInput)).toBe(edgeOutput)
  })

  test('error case description', () => {
    expect(() => myFunction(badInput)).toThrow()
  })
})
```

Run tests: `cd /home/ec2-user/ZenithGrid/frontend && npx vitest run src/pages/games/`

### Responsive Design Pattern

Mobile-first with TailwindCSS breakpoints:
```tsx
// Container
<div className="container mx-auto px-4 sm:px-6 py-4 sm:py-8">

// Grid: 1 col mobile, 2 cols tablet, 3 cols desktop
<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">

// Hide text on mobile, show on sm+
<span className="hidden sm:inline">Label</span>

// Different sizing by breakpoint
<div className="w-full max-w-[340px] sm:max-w-[400px] md:max-w-[500px] mx-auto">
```

### localStorage Persistence Pattern (from Charts.tsx)

```typescript
const [value, setValue] = useState<string>(() => {
  try { return localStorage.getItem('zenith-games-key') || 'default' } catch { return 'default' }
})
useEffect(() => {
  try { localStorage.setItem('zenith-games-key', value) } catch { /* ignored */ }
}, [value])
```

All games localStorage keys should be prefixed with `zenith-games-` for namespacing.

---

## Game Specifications

### Game 1: Tic-Tac-Toe
**Complexity**: Easy | **Session**: 1-2 min | **Icon**: `Grid3X3`

**Rules**: Two players alternate placing X/O on a 3x3 grid. First to get 3 in a row (horizontal, vertical, diagonal) wins. All 9 filled = draw.

**Layout**:
- 3x3 grid with large cells (80-120px each), centered
- Score tracker: X wins / Draws / O wins
- Turn indicator showing current player
- New game / reset button

**Features**:
- AI opponent using minimax (unbeatable) with optional "easy" mode (random moves)
- Animated winning line drawn across the 3 winning cells
- Win/draw detection with end-state message
- Score persistence across rounds (session, not localStorage)
- Difficulty toggle: Easy (random) / Hard (minimax)

**Colors**: X = `text-blue-400`, O = `text-red-400`, winning cells = `bg-emerald-900/30`, board lines = `border-slate-600`

**Engine functions to test**: `checkWinner(board)`, `getAIMove(board, difficulty)`, `isBoardFull(board)`, `minimax(board, isMaximizing)`

---

### Game 2: Connect Four
**Complexity**: Medium | **Session**: 3-5 min | **Icon**: `CircleDot`

**Rules**: Two players drop colored discs into a 7-column, 6-row vertical grid. Discs fall to the lowest available position. First to get 4 in a row (horizontal, vertical, diagonal) wins. Full board = draw.

**Layout**:
- 7x6 grid, cells ~50-60px, centered. Grid is a dark blue/navy frame (`bg-blue-900`) with circular cutouts
- Column hover: translucent preview disc above the column
- Drop animation: CSS transition disc falling into position
- Score panel above: Player colors, win counts, turn indicator

**Features**:
- AI opponent with minimax + alpha-beta pruning (depth 5-6 for challenge)
- Drop animation (CSS `transition` on `transform: translateY`)
- Column-click input (click column header area, not individual cells)
- Winning 4 highlighted with pulsing glow
- Difficulty: Easy (depth 2) / Medium (depth 4) / Hard (depth 6)

**Colors**: Player 1 = `bg-red-500`, Player 2/AI = `bg-yellow-400`, frame = `bg-blue-900`, empty = `bg-slate-800 rounded-full`

**Engine functions to test**: `dropDisc(board, col, player)`, `checkWinner(board)`, `getValidColumns(board)`, `evaluateBoard(board, player)`, `minimax(board, depth, alpha, beta, isMaximizing)`

---

### Game 3: 2048
**Complexity**: Medium | **Session**: 5-15 min | **Icon**: `Hash`

**Rules**: 4x4 grid. Arrow keys/swipe slide all tiles in one direction. Same-value tiles merge on collision (values add). New tile (2 or 4) appears after each move. Goal: create a 2048 tile. Game over when no moves remain.

**Layout**:
- 4x4 grid, ~400px square, generous gap between cells (`gap-3`)
- Rounded-corner cells with value-dependent background colors
- Score display above: Current + Best (localStorage)
- New Game and Undo buttons

**Features**:
- Smooth slide + merge animations (CSS transitions on `transform` and `scale`)
- Swipe support on mobile (touch events with direction detection)
- Arrow key + WASD input on desktop
- Score + best score persistence (localStorage)
- Undo last move (single step)
- Tile color progression from cream to gold to deep orange
- "You win!" celebration at 2048, with "Continue?" option
- Game over detection with final score

**Tile Colors** (value → bg):
```
2    → bg-amber-100 text-slate-800
4    → bg-amber-200 text-slate-800
8    → bg-orange-400 text-white
16   → bg-orange-500 text-white
32   → bg-red-400 text-white
64   → bg-red-600 text-white
128  → bg-yellow-400 text-slate-800
256  → bg-yellow-500 text-slate-800
512  → bg-yellow-600 text-white
1024 → bg-amber-500 text-white
2048 → bg-amber-400 text-white font-bold
```

**Engine functions to test**: `slideRow(row)`, `rotateBoard(board)`, `move(board, direction)`, `addRandomTile(board)`, `hasValidMoves(board)`, `calculateScore(board)`

---

### Game 4: Minesweeper
**Complexity**: Medium | **Session**: 3-15 min | **Icon**: `Bomb`

**Rules**: Grid hides mines. Click to reveal: mine = game over; number = count of adjacent mines; blank = auto-reveal adjacent blanks (flood fill). Right-click to flag. Win by revealing all non-mine cells. First click is always safe.

**Difficulties**:
- Beginner: 9x9, 10 mines
- Intermediate: 16x16, 40 mines
- Expert: 16x30, 99 mines (horizontal scroll on mobile)

**Layout**:
- Grid of cells, 28-32px each
- Header: Mine counter (mines - flags), smiley reset button, timer
- Cell states: hidden (raised), revealed (flat with number), flagged (flag icon), exploded (red bg)
- Number colors: 1=blue, 2=green, 3=red, 4=dark-blue, 5=maroon, 6=cyan, 7=black, 8=gray

**Features**:
- First-click safety: generate board AFTER first click, ensuring that cell + its neighbors are safe
- Recursive flood-fill reveal for blank cells
- Right-click flagging (or long-press on mobile)
- Timer starts on first click
- Win/loss animations (reveal all mines on loss, green flash on win)
- Best time per difficulty (localStorage)
- Chord clicking: click a revealed number where adjacent flags match the number → reveal remaining adjacent cells

**Engine functions to test**: `generateBoard(rows, cols, mines, safeRow, safeCol)`, `revealCell(board, row, col)`, `floodFill(board, row, col)`, `countAdjacentMines(board, row, col)`, `checkWin(board)`, `getAdjacentCells(row, col, rows, cols)`

---

### Game 5: Hangman
**Complexity**: Easy | **Session**: 2-5 min | **Icon**: `PenLine`

**Rules**: Game picks a secret word. Player guesses one letter at a time. Correct → reveal letter in all positions. Wrong → add body part to hangman (6 wrong = lose). Win by revealing all letters before hangman is complete.

**Layout**:
- Two sections: Left = SVG hangman drawing, Right = word + keyboard
- Word display: underscores for hidden letters, revealed letters shown, monospace font
- On-screen QWERTY keyboard: buttons gray out when used (green = correct, red = wrong)
- Category label above the word

**Features**:
- Progressive SVG hangman drawing (6 parts: head, body, left arm, right arm, left leg, right leg)
- Physical keyboard support (keydown listener)
- Categories: "Crypto", "Trading", "Animals", "Countries", "Movies", "Food", "Science"
- Curated word lists per category (30-50 words each, 4-10 letter words)
- Win/loss animations with word reveal
- Streak counter (consecutive wins)
- Category selector before starting

**Colors**: Correct key = `bg-emerald-600`, wrong key = `bg-red-900/50 text-slate-600`, hangman SVG = `stroke-slate-300`, gallows = `stroke-slate-500`

**Engine functions to test**: `selectWord(category)`, `processGuess(word, guessedLetters, letter)`, `isGameWon(word, guessedLetters)`, `isGameLost(wrongGuesses)`, `getDisplayWord(word, guessedLetters)`

---

### Game 6: Sudoku
**Complexity**: Medium-Hard | **Session**: 5-20 min | **Icon**: `Grid3X3` (or `Table2`)

**Rules**: Fill a 9x9 grid (divided into 3x3 boxes) with digits 1-9 so every row, column, and box contains each digit exactly once. Pre-filled cells are locked.

**Layout**:
- 9x9 grid with thick borders separating 3x3 boxes
- Cells ~45-55px on desktop, scales down on mobile
- Digit pad below (1-9 + erase button)
- Toolbar: Difficulty selector, Timer (toggleable), Notes mode, Undo, Hint, New Game, Validate

**Features**:
- **Pencil/notes mode**: toggle to write small candidate digits in cells (3x3 mini-grid per cell)
- **Conflict highlighting**: real-time red highlight on row/col/box duplicates
- **Peer highlighting**: light tint on cells in same row/col/box as selected cell
- **Same-value highlighting**: all cells with same digit as selected cell get accent tint
- **Undo** with full move history
- **Timer** with show/hide toggle
- **4 difficulty levels**: Easy (40+ givens), Medium (32-39), Hard (27-31), Expert (22-26)
- **Hint**: reveals one correct cell (limited to 3 per game)
- **Validate**: marks all incorrect cells in red
- **Auto-save**: saves current puzzle state to localStorage, restores on return
- **Puzzle generator**: backtracking solver that generates valid boards with unique solutions

**Colors**: Given cells = `bg-slate-700 text-slate-200 font-bold`, player cells = `text-blue-400`, selected = `bg-blue-900/40`, peers = `bg-slate-700/50`, conflict = `text-red-400 bg-red-900/20`, notes = `text-slate-500 text-xs`

**Engine functions to test**: `generatePuzzle(difficulty)`, `solveSudoku(board)`, `isValidPlacement(board, row, col, num)`, `hasUniqueSolution(board)`, `getConflicts(board, row, col)`, `getPeers(row, col)`, `removeClues(solvedBoard, count)`

---

### Game 7: Wordle
**Complexity**: Medium | **Session**: 5-10 min | **Icon**: `LetterText`

**Rules**: 6 attempts to guess a hidden 5-letter word. After each guess (must be valid word), each letter colored: green (right letter, right position), yellow (right letter, wrong position), gray (not in word).

**Layout**:
- 6-row x 5-column letter grid, centered (~60px cells)
- QWERTY keyboard below, keys colored by best result
- Current row: fills as user types
- Submit with Enter, backspace to delete

**Features**:
- **Flip animation**: staggered tile-flip reveal per cell on row submission
- **Shake animation**: row shakes on invalid word
- **Word validation**: check against a valid-guess dictionary (~12,000 words)
- **Answer list**: curated ~2,300 common 5-letter words (separate from valid-guess list)
- **Keyboard coloring**: keys update to best-achieved color (green > yellow > gray)
- **Physical keyboard input** + on-screen keyboard
- **Hard mode**: must use all revealed green/yellow letters in subsequent guesses
- **Stats**: win %, current streak, max streak, guess distribution histogram (localStorage)
- **Share**: copy emoji grid to clipboard (green/yellow/gray squares)
- **Daily mode**: deterministic word from answer list based on date (same word for all users on same day) + infinite random mode

**Colors**: Correct = `bg-emerald-600`, present = `bg-yellow-600`, absent = `bg-slate-700`, unfilled = `border-slate-600 border-2`, filled-unsubmitted = `border-slate-400 border-2`

**Engine functions to test**: `evaluateGuess(guess, answer)`, `isValidWord(word, dictionary)`, `getDailyWord(answerList, date)`, `updateKeyboardState(keyboard, guess, evaluation)`, `checkHardMode(guess, previousEvaluations)`

---

### Game 8: Snake
**Complexity**: Easy-Medium | **Session**: 2-10 min | **Icon**: `Waypoints`

**Rules**: Snake moves continuously in one direction. Arrow keys change direction. Eating food grows snake by 1. Hitting wall or self = game over. Speed increases with score.

**Layout**:
- Canvas-based game area, 20x20 grid, ~400-500px square
- Score and high score above the canvas
- Speed/level indicator
- Mobile: D-pad overlay buttons or swipe controls

**Features**:
- **Canvas rendering** (not DOM — performance matters at high speed)
- **Direction queue**: buffer next direction to prevent fast-key drops
- **No-reverse rule**: pressing opposite direction is ignored
- **Speed progression**: increases every 5 food items
- **Walls mode toggle**: walls kill (classic) vs. wrap-around (portal)
- **High score** persistence (localStorage)
- **Mobile controls**: swipe gestures + optional D-pad overlay
- **Pause/resume** with spacebar
- **Food variety**: occasional special food worth bonus points (different color)
- **Death animation**: snake flashes red, then score display

**Colors**: Snake head = `fill-emerald-400`, snake body = `fill-emerald-600` (gradient darker toward tail), food = `fill-red-400`, special food = `fill-yellow-400`, background = `fill-slate-900`, grid lines = `stroke-slate-800`

**Engine functions to test**: `moveSnake(snake, direction)`, `checkCollision(snake, walls)`, `checkFoodEaten(head, food)`, `growSnake(snake)`, `getNextHead(head, direction)`, `isOppositeDirection(current, next)`, `wrapPosition(pos, gridSize)`

---

### Game 9: Ultimate Tic-Tac-Toe
**Complexity**: Hard | **Session**: 10-20 min | **Icon**: `LayoutGrid`

**Rules**: 3x3 grid of 3x3 tic-tac-toe boards (81 cells). Your move's cell position within its sub-board determines which sub-board the opponent must play in next. Win a sub-board by getting 3 in a row. Win the game by winning 3 sub-boards in a row on the meta-board. If sent to a won/drawn sub-board, player may play anywhere.

**Layout**:
- Outer 3x3 grid of sub-boards with thick borders (`border-2 border-slate-500`)
- Inner cells ~35-45px each, total board ~400-500px
- Active sub-board highlighted with colored border/tint (`ring-2 ring-blue-400`)
- Won sub-boards show large X/O overlay with semi-transparent background
- Current player + meta-board state indicator

**Features**:
- **Active sub-board highlighting**: clear visual indication of where the player must play
- **"Any board" indicator**: when sent to a won/drawn board, all valid boards highlighted
- **Won sub-board overlay**: large X/O with transparent tint, underlying cells still visible
- **AI opponent**: minimax with depth limit (4-5) + heuristic evaluation
- **Move validation**: only allow clicks on legal cells
- **Undo** (essential — mistakes are costly)
- **Game state indicator**: show meta-board progress as mini-board in corner

**Colors**: Active board = `ring-2 ring-blue-400 bg-blue-900/10`, X-won board = `bg-blue-900/30` with large blue X, O-won board = `bg-red-900/30` with large red O, drawn board = `bg-slate-700/30`

**Engine functions to test**: `getActiveBoard(lastMove)`, `checkSubBoardWinner(subBoard)`, `checkMetaWinner(metaBoard)`, `getValidMoves(boards, activeBoard)`, `evaluatePosition(boards, metaBoard)`, `minimax(state, depth, alpha, beta, isMaximizing)`

---

### Game 10: Mahjong Solitaire
**Complexity**: Hard | **Session**: 10-20 min | **Icon**: `Layers`

**Rules**: 144 tiles in a multi-layer pyramid layout ("Turtle"). Match and remove identical pairs. A tile is "free" if: (1) no tile on top of it, (2) at least one side (left or right) is open. Win by clearing all tiles. Lose when no free pairs remain and shuffles exhausted.

**Layout**:
- Flat 2D top-down view with layer offset (higher layers shift right+down by 2-3px for depth effect)
- Tiles ~40px wide x 55px tall, total layout ~700-800px wide
- Sidebar/toolbar: remaining tile count, hint, undo, shuffle (3 max), timer, new game
- Selected tile: golden glow border
- Tile face shows suit icon/character

**Features**:
- **Correct free-tile logic**: both layer-blocking AND side-blocking computed correctly
- **Tile set**: 36 unique tiles × 4 copies = 144 (Bamboo 1-9, Circle 1-9, Character 1-9, Winds×4, Dragons×3, Flowers×4, Seasons×4)
- **Solvability**: generate boards in reverse (place pairs, build up) to guarantee winnability
- **Shuffle**: when stuck, offer to shuffle remaining tiles (3 shuffles per game)
- **Hint**: flash a valid matchable pair
- **Undo** with full history
- **Multiple layouts**: Turtle (default), Pyramid, Fortress
- **Tile rendering**: simple SVG icons or Unicode characters for tile faces
- **Z-ordering**: higher-layer tiles render on top (sorted rendering)
- **Match animation**: tiles fade out / fly together on match

**Layout Data**: The Turtle layout is a hardcoded array of `{row, col, layer}` positions (~144 entries). Each standard layout is a separate constant.

**Colors**: Tile face = `bg-amber-50 border-amber-800`, tile shadow = `shadow-md`, selected = `ring-2 ring-yellow-400`, blocked = `opacity-60`, background = `bg-emerald-900`

**Engine functions to test**: `isTileFree(layout, tileIndex, tiles)`, `canMatch(tile1, tile2)`, `findAllMatches(layout, tiles)`, `generateSolvableBoard(layout)`, `shuffleRemainingTiles(layout, tiles)`, `checkGameOver(layout, tiles)`

---

### Game 11: Nonogram (Picross)
**Complexity**: Medium | **Session**: 10-20 min | **Icon**: `Grip`

**Rules**: Grid with clue numbers on rows (left) and columns (top). Clues describe consecutive runs of filled cells. E.g., "3 1" = run of 3 filled, gap, run of 1. Fill cells to match all clues and reveal a picture.

**Layout**:
- Grid with clue region on left and top edges (~25% of width/height)
- Cells ~28-35px each
- Left-click: fill (black). Right-click: mark X (empty). Empty: default
- Completed rows/columns: clues dim or turn green
- Puzzle sizes: 5x5 (easy), 10x10 (medium), 15x15 (hard)

**Features**:
- **Right-click X-marking**: crucial for strategy
- **Click-drag**: fill multiple cells in a row with one gesture
- **Row/column completion detection**: visual feedback when clues are satisfied
- **Error check** (optional toggle): flash if a filled cell contradicts the solution
- **Puzzle library**: 15-20 handcrafted puzzles per size (solutions stored as binary grids)
- **Undo/redo**
- **Timer**
- **Pixel-art reveal**: on completion, show the picture the solution forms with color
- **Puzzle preview**: thumbnail of completed image (hidden during play)

**Colors**: Filled cell = `bg-slate-200`, X-marked = `text-red-400 bg-slate-800`, empty = `bg-slate-700`, completed clue = `text-emerald-400`, active row/col = `bg-slate-600/30`

**Engine functions to test**: `validateRow(row, clues)`, `validateColumn(grid, colIndex, clues)`, `isPuzzleComplete(grid, rowClues, colClues)`, `generateClues(solution)`, `parseNonogramPuzzle(puzzleData)`

---

## Architecture & Modularity

### File Size Rules
- **No file > 300 lines** for game components
- **Engine files** (pure logic) are separate from UI components
- **Each game** gets its own directory under `components/games/`
- **Shared hooks** in `hooks/` for timer, scores, keyboard
- **Shared layout** in `GameLayout.tsx` for consistent game chrome (back button, title, score, timer)

### Directory Structure

```
frontend/src/pages/
├── Games.tsx                              # ~50 lines: lazy-loaded router entry point
└── games/
    ├── index.ts                           # Module exports
    ├── types.ts                           # Shared game types
    ├── constants.ts                       # Game registry (id, name, icon, description, path)
    ├── constants.test.ts                  # Test registry completeness
    ├── hooks/
    │   ├── useGameScores.ts               # localStorage high scores CRUD
    │   ├── useGameScores.test.ts
    │   ├── useGameTimer.ts                # Start/stop/reset timer
    │   ├── useGameTimer.test.ts
    │   └── useKeyboard.ts                 # Keyboard event handler
    ├── components/
    │   ├── GameHub.tsx                     # Hub page with game cards grid (~120 lines)
    │   ├── GameCard.tsx                    # Individual card (~60 lines)
    │   ├── GameLayout.tsx                  # Wrapper: back nav, title, score, timer (~80 lines)
    │   ├── DifficultySelector.tsx          # Shared difficulty picker (~40 lines)
    │   ├── GameOverModal.tsx               # Shared win/lose modal (~60 lines)
    │   └── games/
    │       ├── tic-tac-toe/
    │       │   ├── TicTacToe.tsx           # Game component (~150 lines)
    │       │   ├── TicTacToeBoard.tsx      # Board rendering (~80 lines)
    │       │   ├── ticTacToeEngine.ts      # Pure game logic (~100 lines)
    │       │   └── ticTacToeEngine.test.ts
    │       ├── connect-four/
    │       │   ├── ConnectFour.tsx         # Game component (~180 lines)
    │       │   ├── ConnectFourBoard.tsx    # Board rendering (~120 lines)
    │       │   ├── connectFourEngine.ts    # Pure game logic + AI (~250 lines)
    │       │   └── connectFourEngine.test.ts
    │       ├── twenty-forty-eight/
    │       │   ├── TwentyFortyEight.tsx    # Game component (~200 lines)
    │       │   ├── TileGrid.tsx            # Animated tile rendering (~120 lines)
    │       │   ├── twenFoEiEngine.ts       # Pure game logic (~200 lines)
    │       │   └── twenFoEiEngine.test.ts
    │       ├── minesweeper/
    │       │   ├── Minesweeper.tsx         # Game component (~200 lines)
    │       │   ├── MinesweeperGrid.tsx     # Grid rendering (~120 lines)
    │       │   ├── minesweeperEngine.ts    # Board gen, reveal, flood fill (~250 lines)
    │       │   └── minesweeperEngine.test.ts
    │       ├── hangman/
    │       │   ├── Hangman.tsx             # Game component (~150 lines)
    │       │   ├── HangmanDrawing.tsx      # SVG figure (~80 lines)
    │       │   ├── HangmanKeyboard.tsx     # On-screen keyboard (~60 lines)
    │       │   ├── hangmanEngine.ts        # Word selection, game logic (~80 lines)
    │       │   ├── hangmanEngine.test.ts
    │       │   └── wordLists.ts            # Categorized word lists (~200 lines)
    │       ├── sudoku/
    │       │   ├── Sudoku.tsx              # Game component (~250 lines)
    │       │   ├── SudokuBoard.tsx         # 9x9 grid rendering (~150 lines)
    │       │   ├── SudokuControls.tsx      # Digit pad + toolbar (~80 lines)
    │       │   ├── sudokuEngine.ts         # Generator, solver, validator (~300 lines)
    │       │   └── sudokuEngine.test.ts
    │       ├── wordle/
    │       │   ├── Wordle.tsx              # Game component (~250 lines)
    │       │   ├── WordleBoard.tsx         # 6x5 grid with animations (~120 lines)
    │       │   ├── WordleKeyboard.tsx      # Colored QWERTY keyboard (~80 lines)
    │       │   ├── WordleStats.tsx         # Stats modal with histogram (~100 lines)
    │       │   ├── wordleEngine.ts         # Evaluation, hard mode, daily word (~100 lines)
    │       │   ├── wordleEngine.test.ts
    │       │   ├── answerList.ts           # ~2,300 answer words
    │       │   └── validGuesses.ts         # ~12,000 valid guess words
    │       ├── snake/
    │       │   ├── Snake.tsx               # Game component with canvas (~200 lines)
    │       │   ├── snakeEngine.ts          # Movement, collision, growth (~150 lines)
    │       │   └── snakeEngine.test.ts
    │       ├── ultimate-tic-tac-toe/
    │       │   ├── UltimateTicTacToe.tsx   # Game component (~250 lines)
    │       │   ├── MetaBoard.tsx           # Outer 3x3 rendering (~100 lines)
    │       │   ├── SubBoard.tsx            # Inner 3x3 rendering (~80 lines)
    │       │   ├── ultimateEngine.ts       # Game logic + AI (~300 lines)
    │       │   └── ultimateEngine.test.ts
    │       ├── mahjong/
    │       │   ├── Mahjong.tsx             # Game component (~250 lines)
    │       │   ├── MahjongBoard.tsx        # Tile layout rendering (~200 lines)
    │       │   ├── MahjongTile.tsx         # Individual tile (~60 lines)
    │       │   ├── mahjongEngine.ts        # Free-tile logic, matching (~250 lines)
    │       │   ├── mahjongEngine.test.ts
    │       │   ├── tileSet.ts              # 144 tile definitions (~100 lines)
    │       │   └── layouts.ts              # Turtle, Pyramid layouts (~200 lines)
    │       └── nonogram/
    │           ├── Nonogram.tsx            # Game component (~200 lines)
    │           ├── NonogramGrid.tsx        # Grid with clues (~150 lines)
    │           ├── nonogramEngine.ts       # Validation, clue generation (~120 lines)
    │           ├── nonogramEngine.test.ts
    │           └── puzzles.ts              # Puzzle library (~200 lines)
```

### Shared Types (`types.ts`)

```typescript
export type Difficulty = 'easy' | 'medium' | 'hard' | 'expert'

export interface GameInfo {
  id: string                    // e.g. 'tic-tac-toe'
  name: string                  // e.g. 'Tic-Tac-Toe'
  description: string           // One-liner
  icon: string                  // Lucide icon name
  path: string                  // Route path: '/games/tic-tac-toe'
  difficulty: 'easy' | 'medium' | 'hard'  // Build complexity (shown as tag)
  sessionLength: string         // e.g. '1-2 min'
  category: 'puzzle' | 'strategy' | 'arcade' | 'word'
}

export interface GameScore {
  gameId: string
  score: number
  date: string                  // ISO date
  difficulty?: Difficulty
  metadata?: Record<string, unknown>  // Game-specific (e.g., time, moves)
}
```

### Game Registry (`constants.ts`)

```typescript
import { Grid3X3, CircleDot, Hash, Bomb, PenLine, LetterText, Waypoints, LayoutGrid, Layers, Grip, Table2 } from 'lucide-react'
import type { GameInfo } from './types'

export const GAMES: GameInfo[] = [
  { id: 'tic-tac-toe', name: 'Tic-Tac-Toe', description: 'Classic 3x3 strategy', icon: 'Grid3X3', path: '/games/tic-tac-toe', difficulty: 'easy', sessionLength: '1-2 min', category: 'strategy' },
  { id: 'connect-four', name: 'Connect Four', description: 'Drop discs, line up four', icon: 'CircleDot', path: '/games/connect-four', difficulty: 'medium', sessionLength: '3-5 min', category: 'strategy' },
  { id: '2048', name: '2048', description: 'Slide and merge to 2048', icon: 'Hash', path: '/games/2048', difficulty: 'medium', sessionLength: '5-15 min', category: 'puzzle' },
  { id: 'minesweeper', name: 'Minesweeper', description: 'Clear the minefield', icon: 'Bomb', path: '/games/minesweeper', difficulty: 'medium', sessionLength: '3-15 min', category: 'puzzle' },
  { id: 'hangman', name: 'Hangman', description: 'Guess the word before time runs out', icon: 'PenLine', path: '/games/hangman', difficulty: 'easy', sessionLength: '2-5 min', category: 'word' },
  { id: 'sudoku', name: 'Sudoku', description: 'Fill the 9x9 grid with logic', icon: 'Table2', path: '/games/sudoku', difficulty: 'medium', sessionLength: '5-20 min', category: 'puzzle' },
  { id: 'wordle', name: 'Wordle', description: 'Guess the daily 5-letter word', icon: 'LetterText', path: '/games/wordle', difficulty: 'medium', sessionLength: '5-10 min', category: 'word' },
  { id: 'snake', name: 'Snake', description: 'Eat, grow, survive', icon: 'Waypoints', path: '/games/snake', difficulty: 'easy', sessionLength: '2-10 min', category: 'arcade' },
  { id: 'ultimate-tic-tac-toe', name: 'Ultimate Tic-Tac-Toe', description: 'Tic-tac-toe inception', icon: 'LayoutGrid', path: '/games/ultimate-tic-tac-toe', difficulty: 'hard', sessionLength: '10-20 min', category: 'strategy' },
  { id: 'mahjong', name: 'Mahjong Solitaire', description: 'Match tiles to clear the board', icon: 'Layers', path: '/games/mahjong', difficulty: 'hard', sessionLength: '10-20 min', category: 'puzzle' },
  { id: 'nonogram', name: 'Nonogram', description: 'Solve clues to reveal pixel art', icon: 'Grip', path: '/games/nonogram', difficulty: 'medium', sessionLength: '10-20 min', category: 'puzzle' },
]

// Icon component map for rendering
export const GAME_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  Grid3X3, CircleDot, Hash, Bomb, PenLine, Table2, LetterText, Waypoints, LayoutGrid, Layers, Grip,
}
```

### Routing Pattern (`Games.tsx`)

```tsx
import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { GameHub } from './games/components/GameHub'

// Lazy-load each game for code splitting
const TicTacToe = lazy(() => import('./games/components/games/tic-tac-toe/TicTacToe'))
const ConnectFour = lazy(() => import('./games/components/games/connect-four/ConnectFour'))
// ... etc

export default function Games() {
  return (
    <Suspense fallback={<LoadingSpinner size="lg" text="Loading game..." />}>
      <Routes>
        <Route index element={<GameHub />} />
        <Route path="tic-tac-toe" element={<TicTacToe />} />
        <Route path="connect-four" element={<ConnectFour />} />
        <Route path="2048" element={<TwentyFortyEight />} />
        <Route path="minesweeper" element={<Minesweeper />} />
        <Route path="hangman" element={<Hangman />} />
        <Route path="sudoku" element={<Sudoku />} />
        <Route path="wordle" element={<Wordle />} />
        <Route path="snake" element={<Snake />} />
        <Route path="ultimate-tic-tac-toe" element={<UltimateTicTacToe />} />
        <Route path="mahjong" element={<Mahjong />} />
        <Route path="nonogram" element={<Nonogram />} />
      </Routes>
    </Suspense>
  )
}
```

### GameLayout Wrapper Pattern

```tsx
// Every game uses this wrapper for consistent chrome
import { useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

interface GameLayoutProps {
  title: string
  children: React.ReactNode
  score?: number
  bestScore?: number
  timer?: string
  controls?: React.ReactNode  // Game-specific toolbar
}

export function GameLayout({ title, children, score, bestScore, timer, controls }: GameLayoutProps) {
  const navigate = useNavigate()
  return (
    <div className="max-w-2xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <button onClick={() => navigate('/games')} className="flex items-center space-x-2 text-slate-400 hover:text-white">
          <ArrowLeft className="w-5 h-5" />
          <span className="hidden sm:inline">Back to Games</span>
        </button>
        <h1 className="text-xl font-bold text-white">{title}</h1>
        <div className="flex items-center space-x-4 text-sm">
          {timer && <span className="text-slate-400">{timer}</span>}
          {score !== undefined && <span className="text-white">Score: {score}</span>}
          {bestScore !== undefined && <span className="text-yellow-400">Best: {bestScore}</span>}
        </div>
      </div>
      {/* Game-specific controls */}
      {controls && <div className="mb-4">{controls}</div>}
      {/* Game board */}
      <div className="flex justify-center">{children}</div>
    </div>
  )
}
```

### GameHub Layout

```tsx
// Hub shows game cards in a responsive grid
export function GameHub() {
  const { getHighScore } = useGameScores()

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Games</h1>
        <p className="text-slate-400 text-sm hidden sm:block">Take a break between trades</p>
      </div>

      {/* Category filter pills (optional) */}
      <div className="flex space-x-2 mb-6 overflow-x-auto">
        {['All', 'Puzzle', 'Strategy', 'Word', 'Arcade'].map(cat => (
          <button key={cat} className="px-3 py-1 rounded-full text-sm ...">{cat}</button>
        ))}
      </div>

      {/* Game cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {GAMES.map(game => (
          <GameCard key={game.id} game={game} highScore={getHighScore(game.id)} />
        ))}
      </div>
    </div>
  )
}
```

---

## Implementation Order

Build in this order — each step is independently shippable and testable:

### Phase 0: Scaffolding
1. Create directory structure under `pages/games/`
2. Create `types.ts`, `constants.ts`, `constants.test.ts`
3. Create shared hooks: `useGameScores.ts` + test, `useGameTimer.ts` + test, `useKeyboard.ts`
4. Create shared components: `GameHub.tsx`, `GameCard.tsx`, `GameLayout.tsx`, `DifficultySelector.tsx`, `GameOverModal.tsx`
5. Create `Games.tsx` router entry point
6. Modify `App.tsx`: add `Gamepad2` icon import, lazy import, nav link, route
7. **Validate**: Games nav link visible, hub page renders with empty game cards, click-through to placeholder routes works

### Phase 1: Easy Games (build confidence, establish patterns)
8. **Tic-Tac-Toe**: engine (TDD) → tests pass → UI component → integration
9. **Hangman**: word lists → engine (TDD) → tests pass → SVG drawing → UI component
10. **Snake**: engine (TDD) → tests pass → canvas component → mobile controls

### Phase 2: Medium Games
11. **2048**: engine (TDD) → tests pass → animated tile grid → swipe controls
12. **Connect Four**: engine + AI (TDD) → tests pass → board UI → drop animation
13. **Minesweeper**: engine (TDD) → tests pass → grid UI → right-click/long-press
14. **Wordle**: engine (TDD) → word lists → tests pass → animated board → keyboard → stats
15. **Nonogram**: engine (TDD) → puzzle library → tests pass → grid UI → click-drag

### Phase 3: Hard Games
16. **Sudoku**: generator/solver engine (TDD) → tests pass → board UI → notes mode → controls
17. **Ultimate Tic-Tac-Toe**: engine + AI (TDD) → tests pass → meta-board UI → sub-board UI
18. **Mahjong Solitaire**: tile set → layouts → engine (TDD) → tests pass → board rendering → z-ordering

### Phase 4: Polish
19. Verify all games responsive on mobile (test at 375px, 640px, 1024px widths)
20. Verify all localStorage persistence works (scores, preferences, auto-save)
21. Run full test suite for games: `npx vitest run src/pages/games/`
22. TypeScript check: `npx tsc --noEmit`

---

## TDD Approach Per Game

For EACH game, follow this exact cycle:

```
1. Create `<game>Engine.ts` with function stubs (empty implementations)
2. Create `<game>Engine.test.ts` with all test cases:
   - Happy path tests
   - Edge case tests
   - Error/boundary tests
3. Run tests → confirm they ALL FAIL
4. Implement engine functions one at a time
5. Run tests → confirm each passes as you implement
6. ALL engine tests green → build UI component
7. UI component uses only the tested engine functions
```

**What to test in engine files** (pure functions, no React):
- Board state transitions
- Win/loss/draw detection
- Move validation
- AI move selection
- Score calculation
- Board generation

**What NOT to test** (React rendering, covered by manual testing):
- CSS animations
- Canvas drawing
- Responsive breakpoints
- Touch event handling

---

## Responsive Design Requirements

### Mobile (< 640px)
- Game boards: `max-w-[340px] mx-auto`
- Hub: single-column card grid
- GameLayout: back arrow only (no text), compact score display
- Keyboard games (Wordle, Hangman): on-screen keyboard takes full width
- Snake: swipe controls or floating D-pad
- Minesweeper Expert: horizontal scroll with notice

### Tablet (640-1024px)
- Game boards: `max-w-[450px] mx-auto`
- Hub: 2-column card grid
- Full text labels visible

### Desktop (> 1024px)
- Game boards: `max-w-[500px] mx-auto`
- Hub: 3-column card grid
- Full controls visible

### Mobile Touch Patterns
- **Tap**: primary action (place piece, reveal cell, select)
- **Long-press** (300ms): secondary action (flag in Minesweeper, mark X in Nonogram)
- **Swipe**: directional input (2048, Snake)
- **No right-click**: always provide a tap-based alternative for right-click actions

---

## Validation Gates

```bash
# TypeScript
cd /home/ec2-user/ZenithGrid/frontend && npx tsc --noEmit

# Lint (if eslint configured)
cd /home/ec2-user/ZenithGrid/frontend && npx eslint src/pages/games/ --ext .ts,.tsx

# Unit Tests (games only)
cd /home/ec2-user/ZenithGrid/frontend && npx vitest run src/pages/games/

# Full frontend tests
cd /home/ec2-user/ZenithGrid/frontend && npx vitest run

# Visual verification (dev mode)
# 1. Navigate to /games — hub page loads with all 11 game cards
# 2. Click each game card — game loads without errors
# 3. Play each game through win AND loss states
# 4. Resize browser to 375px width — all games remain playable
# 5. Check localStorage — scores persist across page reloads
```

---

## Error Handling

- **No API calls**: all games are client-side only. No network error handling needed.
- **localStorage**: wrap all reads/writes in try/catch (Safari private mode throws on localStorage)
- **Canvas fallback**: if canvas is unsupported (unlikely), show text message
- **Invalid state**: engine functions should throw on impossible states (e.g., placing piece on occupied cell) — caught by UI layer
- **Browser compatibility**: test on Chrome, Firefox, Safari. CSS animations use standard properties only.

---

## Dependencies

**No new npm dependencies required.** Everything is built with:
- React 19 (useState, useReducer, useEffect, useRef, useCallback)
- react-router-dom 7 (Routes, Route, Link, useNavigate, useLocation)
- lucide-react (icons — already installed, many game-suitable icons available)
- TailwindCSS 3 (all styling)
- Canvas API (Snake game only — built into browsers)
- vitest + @testing-library/react (tests — already configured)

---

## References

- Sudoku generator algorithm: https://en.wikipedia.org/wiki/Sudoku_solving_algorithms
- Minimax algorithm: https://en.wikipedia.org/wiki/Minimax
- Alpha-beta pruning: https://en.wikipedia.org/wiki/Alpha%E2%80%93beta_pruning
- Connect Four AI: https://connect4.gamesolver.org/en/
- Ultimate Tic-Tac-Toe rules: https://en.wikipedia.org/wiki/Ultimate_tic-tac-toe
- Mahjong Solitaire tile matching: https://en.wikipedia.org/wiki/Mahjong_solitaire
- Wordle answer/guess lists: https://github.com/tabatkins/wordle-list
- 2048 game logic: https://play2048.co/
- Nonogram solving: https://en.wikipedia.org/wiki/Nonogram

---

## Quality Checklist

- [x] All necessary context included (nav patterns, test patterns, responsive patterns, state management)
- [x] Validation gates are executable by AI (`npx tsc --noEmit`, `npx vitest run`)
- [x] References existing codebase patterns (App.tsx nav, localStorage, lazy loading, test style)
- [x] Clear implementation path (phased, each game independent)
- [x] Error handling documented (localStorage, canvas, engine throws)
- [x] Modularity enforced (300-line file limit, engine/UI separation, shared components)
- [x] TDD cycle documented with test-first requirement
- [x] Mobile/responsive requirements explicit per breakpoint
- [x] No new dependencies needed
- [x] Each game has testable engine functions listed
