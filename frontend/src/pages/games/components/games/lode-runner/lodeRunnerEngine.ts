/**
 * Lode Runner game engine — pure functions, no React dependencies.
 *
 * Classic puzzle-platformer: collect all gold, dig holes to trap guards,
 * escape via hidden ladder at the top once all gold is collected.
 */

import { LEVELS, TOTAL_LEVELS as LEVEL_COUNT } from './lodeRunnerLevels'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const COLS = 28
export const ROWS = 16
export const CELL = 24
export const GAME_WIDTH = COLS * CELL   // 672
export const GAME_HEIGHT = ROWS * CELL  // 384

export { TOTAL_LEVELS } from './lodeRunnerLevels'

/** Player movement speed in pixels/second */
const PLAYER_SPEED = 100

/** Guard movement speed in pixels/second */
const GUARD_SPEED = 70

/** Gravity fall speed in pixels/second */
const FALL_SPEED = 160

/** How long a dug brick stays open (seconds) */
const BRICK_OPEN_TIME = 5.0

/** How long a brick takes to fill back in (seconds) */
const BRICK_FILL_TIME = 0.6

/** Cooldown between digs (seconds) */
const DIG_COOLDOWN = 0.4

/** Guard respawn delay (seconds) */
const GUARD_RESPAWN_TIME = 3.0

/** Points per gold collected */
const GOLD_POINTS = 250

/** Points per guard trapped */
const GUARD_TRAP_POINTS = 75

/** Points for completing a level */
const LEVEL_COMPLETE_POINTS = 500

// ---------------------------------------------------------------------------
// Tile types
// ---------------------------------------------------------------------------

export enum Tile {
  Empty = '.',
  Brick = 'B',
  Solid = 'S',
  Ladder = 'H',
  Bar = '-',
  Gold = 'G',
  Player = 'P',
  Enemy = 'E',
  Hidden = 'T',
}

// ---------------------------------------------------------------------------
// Interfaces
// ---------------------------------------------------------------------------

export interface Input {
  left: boolean
  right: boolean
  up: boolean
  down: boolean
  digLeft: boolean
  digRight: boolean
}

export type AnimState = 'standing' | 'running' | 'climbing' | 'hanging' | 'falling' | 'digging'

export interface Entity {
  col: number
  row: number
  x: number
  y: number
  falling: boolean
  facingLeft: boolean
  animState: AnimState
}

export interface Player extends Entity {
  alive: boolean
  digCooldown: number
}

export type GuardState = 'chasing' | 'trapped' | 'climbing_out' | 'dead'

export interface Guard extends Entity {
  state: GuardState
  trapTimer: number
  carriesGold: boolean
  respawnCol: number
  respawnRow: number
  respawnTimer: number
}

export interface DugBrick {
  col: number
  row: number
  timer: number
  phase: 'open' | 'filling'
}

export interface GameState {
  grid: Tile[][]          // immutable base grid (restart-safe)
  goldMap: boolean[][]    // separate gold tracking
  player: Player
  guards: Guard[]
  dugBricks: DugBrick[]
  goldRemaining: number
  level: number
  lives: number
  score: number
  gameOver: boolean
  levelComplete: boolean
  escapeRevealed: boolean
  won: boolean
  animTime: number
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function cellCenter(col: number, row: number): { x: number; y: number } {
  return { x: col * CELL + CELL / 2, y: row * CELL + CELL / 2 }
}

function posToCell(x: number, y: number): { col: number; row: number } {
  return {
    col: Math.round((x - CELL / 2) / CELL),
    row: Math.round((y - CELL / 2) / CELL),
  }
}

function inBounds(col: number, row: number): boolean {
  return col >= 0 && col < COLS && row >= 0 && row < ROWS
}

function tileAt(state: GameState, col: number, row: number): Tile {
  if (!inBounds(col, row)) return Tile.Solid
  return state.grid[row][col]
}

/** Check if a brick at (col, row) is currently dug open */
function isDugOpen(state: GameState, col: number, row: number): boolean {
  return state.dugBricks.some(
    db => db.col === col && db.row === row && db.phase === 'open'
  )
}

/** Is a tile solid (blocks movement)? */
function isSolid(state: GameState, col: number, row: number): boolean {
  if (!inBounds(col, row)) return true
  const t = state.grid[row][col]
  if (t === Tile.Brick) return !isDugOpen(state, col, row)
  return t === Tile.Solid
}

/** Can an entity stand/walk on the tile at (col, row)? */
function isPassable(state: GameState, col: number, row: number): boolean {
  return !isSolid(state, col, row)
}

/** Is entity supported (not falling)? */
function isSupported(state: GameState, col: number, row: number): boolean {
  // On a ladder
  const t = tileAt(state, col, row)
  if (t === Tile.Ladder) return true
  // On a revealed hidden ladder
  if (t === Tile.Hidden && state.escapeRevealed) return true
  // On a bar
  if (t === Tile.Bar) return true
  // Standing on solid ground below
  if (isSolid(state, col, row + 1)) return true
  // Standing on top of a ladder below
  const below = tileAt(state, col, row + 1)
  if (below === Tile.Ladder) return true
  if (below === Tile.Hidden && state.escapeRevealed) return true
  // Standing on a trapped guard
  if (state.guards.some(g => g.state === 'trapped' && g.col === col && g.row === row + 1)) return true
  return false
}

/** Is the tile at (col, row) climbable as a ladder? */
function isLadder(state: GameState, col: number, row: number): boolean {
  if (!inBounds(col, row)) return false
  const t = state.grid[row][col]
  if (t === Tile.Ladder) return true
  if (t === Tile.Hidden && state.escapeRevealed) return true
  return false
}

function isBar(state: GameState, col: number, row: number): boolean {
  if (!inBounds(col, row)) return false
  return state.grid[row][col] === Tile.Bar
}

/** Aligned to cell center within tolerance */
function isAligned(entity: Entity, tolerance: number = 2): boolean {
  const { x: cx, y: cy } = cellCenter(entity.col, entity.row)
  return Math.abs(entity.x - cx) <= tolerance && Math.abs(entity.y - cy) <= tolerance
}

/** Snap to cell center */
function snapToCell(entity: Entity): Entity {
  const { x, y } = cellCenter(entity.col, entity.row)
  return { ...entity, x, y }
}

// ---------------------------------------------------------------------------
// Level loading
// ---------------------------------------------------------------------------

export function loadLevel(levelNum: number): GameState {
  const idx = Math.min(levelNum - 1, LEVEL_COUNT - 1)
  const levelDef = LEVELS[idx]

  const grid: Tile[][] = []
  const goldMap: boolean[][] = []
  let playerCol = 1, playerRow = 14
  const enemies: { col: number; row: number }[] = []
  let goldCount = 0

  for (let r = 0; r < ROWS; r++) {
    const gridRow: Tile[] = []
    const goldRow: boolean[] = []
    const line = levelDef[r] || ''
    for (let c = 0; c < COLS; c++) {
      const ch = (line[c] || '.') as Tile
      let tile = ch
      let hasGold = false

      switch (ch) {
        case Tile.Player:
          playerCol = c
          playerRow = r
          tile = Tile.Empty
          break
        case Tile.Enemy:
          enemies.push({ col: c, row: r })
          tile = Tile.Empty
          break
        case Tile.Gold:
          hasGold = true
          goldCount++
          tile = Tile.Empty
          break
        default:
          break
      }
      gridRow.push(tile)
      goldRow.push(hasGold)
    }
    grid.push(gridRow)
    goldMap.push(goldRow)
  }

  const { x: px, y: py } = cellCenter(playerCol, playerRow)
  const player: Player = {
    col: playerCol,
    row: playerRow,
    x: px,
    y: py,
    falling: false,
    facingLeft: false,
    animState: 'standing' as AnimState,
    alive: true,
    digCooldown: 0,
  }

  const guards: Guard[] = enemies.map(e => {
    const { x, y } = cellCenter(e.col, e.row)
    return {
      col: e.col,
      row: e.row,
      x, y,
      falling: false,
      facingLeft: false,
      animState: 'standing' as AnimState,
      state: 'chasing' as GuardState,
      trapTimer: 0,
      carriesGold: false,
      respawnCol: e.col,
      respawnRow: 0,
      respawnTimer: 0,
    }
  })

  return {
    grid,
    goldMap,
    player,
    guards,
    dugBricks: [],
    goldRemaining: goldCount,
    level: levelNum,
    lives: 3,
    score: 0,
    gameOver: false,
    levelComplete: false,
    escapeRevealed: false,
    won: false,
    animTime: 0,
  }
}

// ---------------------------------------------------------------------------
// Player movement
// ---------------------------------------------------------------------------

function movePlayer(state: GameState, input: Input, dt: number): GameState {
  let p = { ...state.player }
  if (!p.alive) return state

  // Reduce dig cooldown
  p.digCooldown = Math.max(0, p.digCooldown - dt)

  // Check gravity — but only when aligned to cell center.
  // This lets the player finish a horizontal step before falling,
  // so they can run off edges like in classic Lode Runner.
  const supported = isSupported(state, p.col, p.row)
  if (!supported && !p.falling && isAligned(p as Entity, 2)) {
    p.falling = true
  }

  if (p.falling) {
    // Snap x to column center — falls are strictly vertical
    p.x = cellCenter(p.col, 0).x
    p.y += FALL_SPEED * dt
    const { row } = posToCell(p.x, p.y)
    p.row = row
    if (isSupported(state, p.col, p.row)) {
      p.falling = false
      const snapped = snapToCell(p as Entity) as Entity
      p = { ...p, x: snapped.x, y: snapped.y }
    }
    p.animState = 'falling'
    return { ...state, player: p }
  }

  // Only accept new movement when aligned to cell
  if (!isAligned(p as Entity, 2)) {
    // Continue moving toward current cell center
    const { x: cx, y: cy } = cellCenter(p.col, p.row)
    const dx = cx - p.x
    const dy = cy - p.y
    const dist = Math.sqrt(dx * dx + dy * dy)
    if (dist > 1) {
      const step = Math.min(PLAYER_SPEED * dt, dist)
      p.x += (dx / dist) * step
      p.y += (dy / dist) * step
    } else {
      p.x = cx
      p.y = cy
    }
    const ct = tileAt(state, p.col, p.row)
    if (ct === Tile.Ladder || (ct === Tile.Hidden && state.escapeRevealed)) p.animState = 'climbing'
    else if (ct === Tile.Bar) p.animState = 'hanging'
    else p.animState = 'running'
    return { ...state, player: p }
  }

  // Snap to cell center before accepting new input
  const snapped = snapToCell(p as Entity) as Entity
  p.x = snapped.x
  p.y = snapped.y

  // Determine target cell
  let targetCol = p.col
  let targetRow = p.row

  if (input.left) {
    p.facingLeft = true
    targetCol = p.col - 1
  } else if (input.right) {
    p.facingLeft = false
    targetCol = p.col + 1
  } else if (input.up) {
    if (isLadder(state, p.col, p.row)) {
      targetRow = p.row - 1
    }
  } else if (input.down) {
    if (isLadder(state, p.col, p.row) || isLadder(state, p.col, p.row + 1)) {
      targetRow = p.row + 1
    }
  }

  // Validate target
  if (targetCol !== p.col || targetRow !== p.row) {
    if (inBounds(targetCol, targetRow) && isPassable(state, targetCol, targetRow)) {
      // Horizontal: must be supported or moving along bar, or target has support
      if (targetRow === p.row) {
        // Moving horizontally — allowed if on ladder, bar, or solid ground
        if (supported || isBar(state, targetCol, targetRow)) {
          p.col = targetCol
          p.row = targetRow
        }
      } else {
        // Vertical movement (ladders)
        p.col = targetCol
        p.row = targetRow
      }
    }
  }

  // Dig
  if ((input.digLeft || input.digRight) && p.digCooldown <= 0) {
    const digCol = input.digLeft ? p.col - 1 : p.col + 1
    const digRow = p.row + 1
    if (
      inBounds(digCol, digRow) &&
      tileAt(state, digCol, digRow) === Tile.Brick &&
      !isDugOpen(state, digCol, digRow) &&
      isPassable(state, digCol, p.row) // can't dig through solid above
    ) {
      const newDug: DugBrick = {
        col: digCol,
        row: digRow,
        timer: BRICK_OPEN_TIME,
        phase: 'open',
      }
      p.digCooldown = DIG_COOLDOWN
      p.animState = 'digging'
      return {
        ...state,
        player: p,
        dugBricks: [...state.dugBricks, newDug],
      }
    }
  }

  // Animate toward target cell
  if (p.col !== Math.round((p.x - CELL / 2) / CELL) ||
      p.row !== Math.round((p.y - CELL / 2) / CELL)) {
    const { x: tx, y: ty } = cellCenter(p.col, p.row)
    const dx = tx - p.x
    const dy = ty - p.y
    const dist = Math.sqrt(dx * dx + dy * dy)
    if (dist > 1) {
      const step = Math.min(PLAYER_SPEED * dt, dist)
      p.x += (dx / dist) * step
      p.y += (dy / dist) * step
    } else {
      p.x = tx
      p.y = ty
    }
  }

  // Determine animation state
  const tile = tileAt(state, p.col, p.row)
  const ladderHere = tile === Tile.Ladder || (tile === Tile.Hidden && state.escapeRevealed)
  if (ladderHere) p.animState = 'climbing'
  else if (tile === Tile.Bar) p.animState = 'hanging'
  else if (input.left || input.right) p.animState = 'running'
  else p.animState = 'standing'

  return { ...state, player: p }
}

// ---------------------------------------------------------------------------
// Guard AI
// ---------------------------------------------------------------------------

function updateGuards(state: GameState, dt: number): GameState {
  const guards = state.guards.map(g => {
    let guard = { ...g }

    // Handle dead/respawning guards
    if (guard.state === 'dead') {
      guard.respawnTimer -= dt
      if (guard.respawnTimer <= 0) {
        // Respawn at top of level
        const spawnCol = guard.respawnCol
        const spawnRow = guard.respawnRow
        const { x, y } = cellCenter(spawnCol, spawnRow)
        return {
          ...guard,
          col: spawnCol,
          row: spawnRow,
          x, y,
          state: 'chasing' as GuardState,
          falling: false,
          trapTimer: 0,
          carriesGold: false,
        }
      }
      return guard
    }

    // Handle trapped guards
    if (guard.state === 'trapped') {
      guard.trapTimer -= dt
      if (guard.trapTimer <= 0) {
        // Try to climb out (move up one cell)
        guard.state = 'climbing_out'
      }
      guard.animState = 'standing'
      return guard
    }

    // Handle climbing out
    if (guard.state === 'climbing_out') {
      const targetRow = guard.row - 1
      if (inBounds(guard.col, targetRow) && isPassable(state, guard.col, targetRow)) {
        const { y: ty } = cellCenter(guard.col, targetRow)
        guard.y -= GUARD_SPEED * dt
        if (guard.y <= ty) {
          guard.row = targetRow
          guard.y = ty
          guard.state = 'chasing'
          guard.falling = false
        }
      } else {
        // Can't climb out — stay trapped, die when brick fills
        guard.state = 'trapped'
        guard.trapTimer = 0.5
      }
      guard.animState = 'climbing'
      return guard
    }

    // Chasing — gravity first (only when aligned, so guards finish
    // horizontal steps before falling — matches classic Lode Runner)
    const supported = isSupported(state, guard.col, guard.row)
    if (!supported && !guard.falling && isAligned(guard as Entity, 2)) {
      guard.falling = true
    }

    if (guard.falling) {
      // Snap x to column center — falls are strictly vertical
      guard.x = cellCenter(guard.col, 0).x
      guard.y += FALL_SPEED * dt
      const { row } = posToCell(guard.x, guard.y)
      guard.row = row

      // Check if fallen into a dug hole
      if (isDugOpen(state, guard.col, guard.row) &&
          isSolid({ ...state, dugBricks: [] }, guard.col, guard.row)) {
        const snapped = snapToCell(guard as Entity)
        guard = {
          ...guard,
          x: snapped.x, y: snapped.y,
          falling: false,
          state: 'trapped',
          trapTimer: BRICK_OPEN_TIME - 1.5,
        }
        return guard
      }

      if (isSupported(state, guard.col, guard.row)) {
        guard.falling = false
        const snapped = snapToCell(guard as Entity)
        guard = { ...guard, x: snapped.x, y: snapped.y }
      }
      guard.animState = 'falling'
      return guard
    }

    // Only make decisions when aligned to cell
    if (!isAligned(guard as Entity, 2)) {
      const { x: cx, y: cy } = cellCenter(guard.col, guard.row)
      const dx = cx - guard.x
      const dy = cy - guard.y
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist > 1) {
        const step = Math.min(GUARD_SPEED * dt, dist)
        guard.x += (dx / dist) * step
        guard.y += (dy / dist) * step
      } else {
        guard.x = cx
        guard.y = cy
      }
      const gt = tileAt(state, guard.col, guard.row)
      if (gt === Tile.Ladder || (gt === Tile.Hidden && state.escapeRevealed)) guard.animState = 'climbing'
      else if (gt === Tile.Bar) guard.animState = 'hanging'
      else guard.animState = 'running'
      return guard
    }

    // Snap and decide next move
    const snapped = snapToCell(guard as Entity)
    guard.x = snapped.x
    guard.y = snapped.y

    const p = state.player
    let bestCol = guard.col
    let bestRow = guard.row

    // Simple chase heuristic
    const onLadder = isLadder(state, guard.col, guard.row)

    if (onLadder && guard.row !== p.row) {
      // On ladder, move toward player's row
      if (p.row < guard.row && isPassable(state, guard.col, guard.row - 1)) {
        bestRow = guard.row - 1
      } else if (p.row > guard.row) {
        if (isLadder(state, guard.col, guard.row + 1) || isPassable(state, guard.col, guard.row + 1)) {
          bestRow = guard.row + 1
        }
      }
    } else {
      // Move horizontally toward player
      if (p.col < guard.col) {
        if (isPassable(state, guard.col - 1, guard.row) && supported) {
          bestCol = guard.col - 1
          guard.facingLeft = true
        }
      } else if (p.col > guard.col) {
        if (isPassable(state, guard.col + 1, guard.row) && supported) {
          bestCol = guard.col + 1
          guard.facingLeft = false
        }
      }

      // If can't move horizontally or already on same col, try ladders
      if (bestCol === guard.col && bestRow === guard.row) {
        if (p.row < guard.row && isLadder(state, guard.col, guard.row) &&
            isPassable(state, guard.col, guard.row - 1)) {
          bestRow = guard.row - 1
        } else if (p.row > guard.row &&
                   (isLadder(state, guard.col, guard.row) || isLadder(state, guard.col, guard.row + 1)) &&
                   isPassable(state, guard.col, guard.row + 1)) {
          bestRow = guard.row + 1
        }
      }
    }

    if (bestCol !== guard.col || bestRow !== guard.row) {
      guard.col = bestCol
      guard.row = bestRow
    }

    // Animate toward target cell
    const { x: tx, y: ty } = cellCenter(guard.col, guard.row)
    const adx = tx - guard.x
    const ady = ty - guard.y
    const adist = Math.sqrt(adx * adx + ady * ady)
    if (adist > 1) {
      const step = Math.min(GUARD_SPEED * dt, adist)
      guard.x += (adx / adist) * step
      guard.y += (ady / adist) * step
    } else {
      guard.x = tx
      guard.y = ty
    }

    // Determine guard animation state
    const gt = tileAt(state, guard.col, guard.row)
    const guardOnLadder = gt === Tile.Ladder || (gt === Tile.Hidden && state.escapeRevealed)
    if (guardOnLadder) guard.animState = 'climbing'
    else if (gt === Tile.Bar) guard.animState = 'hanging'
    else if (bestCol !== g.col || bestRow !== g.row) guard.animState = 'running'
    else guard.animState = 'standing'

    return guard
  })

  return { ...state, guards }
}

// ---------------------------------------------------------------------------
// Brick regeneration
// ---------------------------------------------------------------------------

function updateBricks(state: GameState, dt: number): GameState {
  let score = state.score
  const updatedBricks: DugBrick[] = []
  let guards = [...state.guards]

  for (const db of state.dugBricks) {
    const brick = { ...db }
    brick.timer -= dt

    if (brick.phase === 'open' && brick.timer <= 0) {
      brick.phase = 'filling'
      brick.timer = BRICK_FILL_TIME
    }

    if (brick.phase === 'filling' && brick.timer <= 0) {
      // Brick has regenerated — kill any guard still inside
      guards = guards.map(g => {
        if (g.col === brick.col && g.row === brick.row &&
            (g.state === 'trapped' || g.state === 'climbing_out')) {
          score += GUARD_TRAP_POINTS
          // Drop gold if carrying
          if (g.carriesGold) {
            // Gold appears at top of the hole
            const newGoldMap = state.goldMap.map(r => [...r])
            const goldRow = Math.max(0, brick.row - 1)
            newGoldMap[goldRow][brick.col] = true
            state = { ...state, goldMap: newGoldMap, goldRemaining: state.goldRemaining + 1 }
          }
          return {
            ...g,
            state: 'dead' as GuardState,
            respawnTimer: GUARD_RESPAWN_TIME,
          }
        }
        return g
      })
      // Brick fully regenerated — remove from list
      continue
    }

    updatedBricks.push(brick)
  }

  return { ...state, dugBricks: updatedBricks, guards, score }
}

// ---------------------------------------------------------------------------
// Collision detection
// ---------------------------------------------------------------------------

function checkCollisions(state: GameState): GameState {
  const p = state.player
  if (!p.alive) return state

  // Gold collection
  if (state.goldMap[p.row]?.[p.col]) {
    const newGoldMap = state.goldMap.map(r => [...r])
    newGoldMap[p.row][p.col] = false
    const remaining = state.goldRemaining - 1
    const escaped = remaining === 0
    return {
      ...state,
      goldMap: newGoldMap,
      goldRemaining: remaining,
      score: state.score + GOLD_POINTS,
      escapeRevealed: escaped || state.escapeRevealed,
    }
  }

  // Guard collision
  for (const g of state.guards) {
    if (g.state === 'dead' || g.state === 'trapped') continue
    const dx = Math.abs(p.x - g.x)
    const dy = Math.abs(p.y - g.y)
    if (dx < CELL * 0.7 && dy < CELL * 0.7) {
      // Player caught by guard
      return {
        ...state,
        player: { ...p, alive: false },
      }
    }
  }

  // Escape check — player reaches row 0 with all gold collected
  if (state.escapeRevealed && p.row <= 0) {
    return {
      ...state,
      levelComplete: true,
      score: state.score + LEVEL_COMPLETE_POINTS,
    }
  }

  // Guard gold pickup (guards walk over gold and carry it)
  let newGoldMap = state.goldMap
  let newRemaining = state.goldRemaining
  const newGuards = state.guards.map(g => {
    if (g.state !== 'chasing' || g.carriesGold) return g
    if (newGoldMap[g.row]?.[g.col]) {
      newGoldMap = newGoldMap.map(r => [...r])
      newGoldMap[g.row][g.col] = false
      newRemaining--
      return { ...g, carriesGold: true }
    }
    return g
  })

  if (newRemaining !== state.goldRemaining) {
    return { ...state, goldMap: newGoldMap, goldRemaining: newRemaining, guards: newGuards }
  }

  return state
}

// ---------------------------------------------------------------------------
// Main update
// ---------------------------------------------------------------------------

export function updateGame(state: GameState, dt: number, input: Input): GameState {
  if (state.gameOver || state.levelComplete || state.won) return state

  let s = { ...state, animTime: state.animTime + dt }

  // Player death handling
  if (!s.player.alive) {
    s.lives--
    if (s.lives <= 0) {
      return { ...s, gameOver: true }
    }
    // Respawn: reload level but keep score/lives
    const reloaded = loadLevel(s.level)
    return {
      ...reloaded,
      lives: s.lives,
      score: s.score,
    }
  }

  // Update player
  s = movePlayer(s, input, dt)

  // Update guards
  s = updateGuards(s, dt)

  // Update brick regen
  s = updateBricks(s, dt)

  // Collisions
  s = checkCollisions(s)

  return s
}

// ---------------------------------------------------------------------------
// Level transition
// ---------------------------------------------------------------------------

export function nextLevel(state: GameState): GameState {
  const nextLvl = state.level + 1
  if (nextLvl > LEVEL_COUNT) {
    return { ...state, won: true }
  }
  const fresh = loadLevel(nextLvl)
  return {
    ...fresh,
    lives: state.lives,
    score: state.score,
  }
}
