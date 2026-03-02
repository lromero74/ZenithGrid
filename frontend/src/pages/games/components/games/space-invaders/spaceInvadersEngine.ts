/**
 * Space Invaders — pure game logic engine.
 *
 * No React or DOM dependencies. Exports types, constants, and
 * pure functions for game state creation and updates.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const GAME_WIDTH = 480
export const GAME_HEIGHT = 560

export const ALIEN_COLS = 11
export const ALIEN_ROWS = 5
export const ALIEN_POINTS: number[] = [30, 20, 20, 10, 10]

const PLAYER_SPEED = 200
const PLAYER_BULLET_SPEED = -400
const ALIEN_BULLET_SPEED = 200
const ALIEN_STEP_X = 4
const ALIEN_STEP_DOWN = 16
const MAX_ALIEN_BULLETS = 3
const UFO_SPEED = 100
const UFO_SPAWN_MIN = 15
const UFO_SPAWN_MAX = 30
const UFO_POINT_OPTIONS = [50, 100, 150, 200, 300]

// ---------------------------------------------------------------------------
// Entity interfaces
// ---------------------------------------------------------------------------

export interface Player {
  x: number
  y: number
  width: number
  height: number
}

export interface Alien {
  x: number
  y: number
  width: number
  height: number
  type: number // 0-4 row type
  alive: boolean
  frame: number // 0 or 1 for animation
}

export interface Bullet {
  x: number
  y: number
  width: number
  height: number
  dy: number // negative = up (player), positive = down (alien)
}

export interface BunkerBlock {
  x: number
  y: number
  width: number
  height: number
  alive: boolean
}

export interface UFO {
  x: number
  y: number
  dx: number
  alive: boolean
  points: number
}

// ---------------------------------------------------------------------------
// Game state
// ---------------------------------------------------------------------------

export interface GameState {
  player: Player
  aliens: Alien[]
  playerBullets: Bullet[]
  alienBullets: Bullet[]
  bunkers: BunkerBlock[][]
  ufo: UFO | null
  score: number
  lives: number
  wave: number
  alienDirection: number
  alienStepDown: boolean
  alienSpeed: number
  moveTimer: number
  gameOver: boolean
  /** Accumulator for alien fire cooldown */
  fireTimer: number
  /** Seconds until next UFO spawn */
  ufoTimer: number
}

// ---------------------------------------------------------------------------
// Bunker creation
// ---------------------------------------------------------------------------

/**
 * Creates a classic arch-shaped bunker centered at `centerX` with its
 * base at `baseY`. The bunker is built from small 4x4 blocks.
 */
export function createBunker(centerX: number, baseY: number): BunkerBlock[] {
  const blocks: BunkerBlock[] = []
  const bw = 4
  const bh = 4

  // Bunker is 11 blocks wide (44px) x 8 blocks tall (32px)
  // with an arch cut out of the bottom center (3 blocks wide x 3 tall)
  const cols = 11
  const rows = 8
  const startX = centerX - Math.floor(cols / 2) * bw
  const startY = baseY - rows * bh

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      // Skip corners for rounded top
      if (r === 0 && (c === 0 || c === cols - 1)) continue
      // Skip arch opening: bottom 3 rows, middle 3 columns
      if (r >= rows - 3 && c >= 4 && c <= 6) continue

      blocks.push({
        x: startX + c * bw,
        y: startY + r * bh,
        width: bw,
        height: bh,
        alive: true,
      })
    }
  }

  return blocks
}

// ---------------------------------------------------------------------------
// State creation
// ---------------------------------------------------------------------------

export function createInitialState(wave: number = 1): GameState {
  const player: Player = {
    x: GAME_WIDTH / 2 - 20,
    y: GAME_HEIGHT - 40,
    width: 40,
    height: 20,
  }

  // Create alien formation
  const aliens: Alien[] = []
  const alienWidth = 30
  const alienHeight = 24
  const gapX = 6
  const gapY = 8
  const formationWidth = ALIEN_COLS * (alienWidth + gapX) - gapX
  const startX = (GAME_WIDTH - formationWidth) / 2
  const startY = 60

  for (let row = 0; row < ALIEN_ROWS; row++) {
    for (let col = 0; col < ALIEN_COLS; col++) {
      aliens.push({
        x: startX + col * (alienWidth + gapX),
        y: startY + row * (alienHeight + gapY),
        width: alienWidth,
        height: alienHeight,
        type: row,
        alive: true,
        frame: 0,
      })
    }
  }

  // 4 bunkers evenly spaced
  const bunkerY = GAME_HEIGHT - 100
  const bunkerSpacing = GAME_WIDTH / 5
  const bunkers: BunkerBlock[][] = []
  for (let i = 0; i < 4; i++) {
    bunkers.push(createBunker(bunkerSpacing * (i + 1), bunkerY))
  }

  const aliveCount = ALIEN_ROWS * ALIEN_COLS
  const baseSpeed = Math.max(0.4, 0.8 - (wave - 1) * 0.05)

  return {
    player,
    aliens,
    playerBullets: [],
    alienBullets: [],
    bunkers,
    ufo: null,
    score: 0,
    lives: 3,
    wave,
    alienDirection: 1,
    alienStepDown: false,
    alienSpeed: 0.1 + (baseSpeed - 0.1) * (aliveCount / (ALIEN_ROWS * ALIEN_COLS)),
    moveTimer: 0,
    gameOver: false,
    fireTimer: 0,
    ufoTimer: UFO_SPAWN_MIN + Math.random() * (UFO_SPAWN_MAX - UFO_SPAWN_MIN),
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function getAliveCount(aliens: Alien[]): number {
  let count = 0
  for (const a of aliens) {
    if (a.alive) count++
  }
  return count
}

function rectsOverlap(
  ax: number, ay: number, aw: number, ah: number,
  bx: number, by: number, bw: number, bh: number,
): boolean {
  return ax < bx + bw && ax + aw > bx && ay < by + bh && ay + ah > by
}

/**
 * Returns the indices of aliens that are the bottommost alive alien
 * in each column (i.e., eligible to fire).
 */
function getBottomAliens(aliens: Alien[]): number[] {
  // Map column index -> bottommost alive alien index in the flat array
  const colBottom = new Map<number, number>()

  for (let i = 0; i < aliens.length; i++) {
    const a = aliens[i]
    if (!a.alive) continue
    const col = i % ALIEN_COLS
    const existing = colBottom.get(col)
    if (existing === undefined || a.y > aliens[existing].y) {
      colBottom.set(col, i)
    }
  }

  return Array.from(colBottom.values())
}

// ---------------------------------------------------------------------------
// Player bullet
// ---------------------------------------------------------------------------

export function firePlayerBullet(state: GameState): GameState {
  // Max 1 player bullet on screen at a time
  if (state.playerBullets.length > 0) return state

  const bullet: Bullet = {
    x: state.player.x + state.player.width / 2 - 1,
    y: state.player.y - 8,
    width: 2,
    height: 8,
    dy: PLAYER_BULLET_SPEED,
  }

  return { ...state, playerBullets: [bullet] }
}

// ---------------------------------------------------------------------------
// Main update
// ---------------------------------------------------------------------------

export function updateGame(
  state: GameState,
  dt: number,
  playerDx: number,
): GameState {
  if (state.gameOver) return state

  // Deep-copy mutable arrays to keep pure function semantics
  let {
    player, aliens, playerBullets, alienBullets,
    bunkers, ufo, score, lives, wave,
    alienDirection, alienStepDown, alienSpeed,
    moveTimer, fireTimer, ufoTimer,
  } = state

  // Shallow clone entities that will be mutated
  player = { ...player }
  aliens = aliens.map(a => ({ ...a }))
  playerBullets = playerBullets.map(b => ({ ...b }))
  alienBullets = alienBullets.map(b => ({ ...b }))
  bunkers = bunkers.map(bunker => bunker.map(bl => ({ ...bl })))

  // -----------------------------------------------------------------------
  // Move player
  // -----------------------------------------------------------------------
  player.x += playerDx * PLAYER_SPEED * dt
  player.x = Math.max(0, Math.min(GAME_WIDTH - player.width, player.x))

  // -----------------------------------------------------------------------
  // Move player bullets
  // -----------------------------------------------------------------------
  for (const b of playerBullets) {
    b.y += b.dy * dt
  }
  playerBullets = playerBullets.filter(b => b.y + b.height > 0)

  // -----------------------------------------------------------------------
  // Move alien bullets
  // -----------------------------------------------------------------------
  for (const b of alienBullets) {
    b.y += b.dy * dt
  }
  alienBullets = alienBullets.filter(b => b.y < GAME_HEIGHT)

  // -----------------------------------------------------------------------
  // Move alien formation
  // -----------------------------------------------------------------------
  const aliveCount = getAliveCount(aliens)
  const totalAliens = ALIEN_ROWS * ALIEN_COLS
  const baseSpeed = Math.max(0.4, 0.8 - (wave - 1) * 0.05)
  alienSpeed = 0.1 + (baseSpeed - 0.1) * (aliveCount / totalAliens)
  moveTimer += dt

  if (moveTimer >= alienSpeed) {
    moveTimer -= alienSpeed

    // Toggle animation frame
    for (const a of aliens) {
      if (a.alive) a.frame = a.frame === 0 ? 1 : 0
    }

    if (alienStepDown) {
      // Step down
      for (const a of aliens) {
        if (a.alive) a.y += ALIEN_STEP_DOWN
      }
      alienDirection = -alienDirection
      alienStepDown = false
    } else {
      // Move horizontally
      for (const a of aliens) {
        if (a.alive) a.x += ALIEN_STEP_X * alienDirection
      }

      // Check if any alive alien hit the edge
      let hitEdge = false
      for (const a of aliens) {
        if (!a.alive) continue
        if (a.x + a.width >= GAME_WIDTH - 4 || a.x <= 4) {
          hitEdge = true
          break
        }
      }
      if (hitEdge) {
        alienStepDown = true
      }
    }
  }

  // -----------------------------------------------------------------------
  // Alien firing
  // -----------------------------------------------------------------------
  fireTimer -= dt
  if (fireTimer <= 0 && alienBullets.length < MAX_ALIEN_BULLETS && aliveCount > 0) {
    const bottomAliens = getBottomAliens(aliens)
    if (bottomAliens.length > 0) {
      const shooterIdx = bottomAliens[Math.floor(Math.random() * bottomAliens.length)]
      const shooter = aliens[shooterIdx]
      alienBullets.push({
        x: shooter.x + shooter.width / 2 - 1.5,
        y: shooter.y + shooter.height,
        width: 3,
        height: 10,
        dy: ALIEN_BULLET_SPEED,
      })
    }
    fireTimer = 1 + Math.random()
  }

  // -----------------------------------------------------------------------
  // UFO logic
  // -----------------------------------------------------------------------
  ufoTimer -= dt
  if (!ufo && ufoTimer <= 0) {
    const goingRight = Math.random() < 0.5
    ufo = {
      x: goingRight ? -40 : GAME_WIDTH + 40,
      y: 24,
      dx: goingRight ? UFO_SPEED : -UFO_SPEED,
      alive: true,
      points: UFO_POINT_OPTIONS[Math.floor(Math.random() * UFO_POINT_OPTIONS.length)],
    }
    ufoTimer = UFO_SPAWN_MIN + Math.random() * (UFO_SPAWN_MAX - UFO_SPAWN_MIN)
  }

  if (ufo) {
    ufo = { ...ufo }
    ufo.x += ufo.dx * dt
    // Remove if off screen
    if (ufo.x < -60 || ufo.x > GAME_WIDTH + 60) {
      ufo = null
    }
  }

  // -----------------------------------------------------------------------
  // Collisions: player bullets vs aliens
  // -----------------------------------------------------------------------
  const survivingPlayerBullets: Bullet[] = []

  for (const b of playerBullets) {
    let hit = false

    for (const a of aliens) {
      if (!a.alive) continue
      if (rectsOverlap(b.x, b.y, b.width, b.height, a.x, a.y, a.width, a.height)) {
        a.alive = false
        score += ALIEN_POINTS[a.type]
        hit = true
        break
      }
    }

    // Player bullet vs UFO
    if (!hit && ufo && ufo.alive) {
      if (rectsOverlap(b.x, b.y, b.width, b.height, ufo.x, ufo.y, 36, 16)) {
        score += ufo.points
        ufo = null
        hit = true
      }
    }

    // Player bullet vs bunker blocks
    if (!hit) {
      for (const bunker of bunkers) {
        for (const bl of bunker) {
          if (!bl.alive) continue
          if (rectsOverlap(b.x, b.y, b.width, b.height, bl.x, bl.y, bl.width, bl.height)) {
            bl.alive = false
            hit = true
            break
          }
        }
        if (hit) break
      }
    }

    if (!hit) survivingPlayerBullets.push(b)
  }
  playerBullets = survivingPlayerBullets

  // -----------------------------------------------------------------------
  // Collisions: alien bullets vs player
  // -----------------------------------------------------------------------
  const survivingAlienBullets: Bullet[] = []
  let playerHit = false

  for (const b of alienBullets) {
    let hit = false

    // vs player
    if (!playerHit && rectsOverlap(
      b.x, b.y, b.width, b.height,
      player.x, player.y, player.width, player.height,
    )) {
      playerHit = true
      hit = true
    }

    // vs bunker blocks
    if (!hit) {
      for (const bunker of bunkers) {
        for (const bl of bunker) {
          if (!bl.alive) continue
          if (rectsOverlap(b.x, b.y, b.width, b.height, bl.x, bl.y, bl.width, bl.height)) {
            bl.alive = false
            hit = true
            break
          }
        }
        if (hit) break
      }
    }

    if (!hit) survivingAlienBullets.push(b)
  }
  alienBullets = survivingAlienBullets

  if (playerHit) {
    lives--
    // Clear all bullets on player death
    playerBullets = []
    alienBullets = []
    // Re-center player
    player.x = GAME_WIDTH / 2 - player.width / 2
  }

  // -----------------------------------------------------------------------
  // Aliens passing through / destroying bunker blocks
  // -----------------------------------------------------------------------
  for (const a of aliens) {
    if (!a.alive) continue
    for (const bunker of bunkers) {
      for (const bl of bunker) {
        if (!bl.alive) continue
        if (rectsOverlap(a.x, a.y, a.width, a.height, bl.x, bl.y, bl.width, bl.height)) {
          bl.alive = false
        }
      }
    }
  }

  // -----------------------------------------------------------------------
  // Game over checks
  // -----------------------------------------------------------------------
  let gameOver = false

  // Lives exhausted
  if (lives <= 0) {
    gameOver = true
  }

  // Aliens reached bottom (player row)
  for (const a of aliens) {
    if (a.alive && a.y + a.height >= player.y) {
      gameOver = true
      break
    }
  }

  return {
    player,
    aliens,
    playerBullets,
    alienBullets,
    bunkers,
    ufo,
    score,
    lives,
    wave,
    alienDirection,
    alienStepDown,
    alienSpeed,
    moveTimer,
    gameOver,
    fireTimer,
    ufoTimer,
  }
}
