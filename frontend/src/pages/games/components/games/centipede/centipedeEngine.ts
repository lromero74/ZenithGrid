/**
 * Centipede game engine — pure functions, no React dependencies.
 *
 * Classic arcade-style centipede game with mushrooms, spiders,
 * and splitting centipede chains.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const CELL_SIZE = 16
export const COLS = 30
export const ROWS = 30
export const GAME_WIDTH = COLS * CELL_SIZE   // 480
export const GAME_HEIGHT = ROWS * CELL_SIZE  // 480

/** Player is restricted to the bottom N rows */
export const PLAYER_ZONE_ROWS = 5

/** Number of mushrooms generated at level start */
const INITIAL_MUSHROOM_COUNT = 35

/** Initial centipede length */
const CENTIPEDE_LENGTH = 12

/** Base horizontal speed in pixels/second */
const BASE_SPEED = 60

/** Speed increase per level in pixels/second */
const SPEED_PER_LEVEL = 10

/** Bullet speed in pixels/second (going upward) */
const BULLET_SPEED = 300

/** Spider spawn interval in seconds */
const SPIDER_SPAWN_INTERVAL = 5

/** Spider lifetime in seconds */
const SPIDER_LIFETIME = 5

/** Spider speed in pixels/second */
const SPIDER_SPEED = 100

/** Minimum interval between shots in seconds */
export const FIRE_COOLDOWN = 0.2

// ---------------------------------------------------------------------------
// Entity interfaces
// ---------------------------------------------------------------------------

export interface Player {
  x: number
  y: number
  lives: number
}

export interface CentipedeSegment {
  x: number
  y: number
  dx: number       // -1 or 1 (horizontal direction)
  dy: number       // 1 (dropping down) or -1 (climbing up)
  isHead: boolean
  speed: number    // pixels per second
  stepAccum: number // time accumulator for grid stepping
}

export interface Mushroom {
  x: number
  y: number
  hp: number   // 1-4, starts at 4
}

export interface Bullet {
  x: number
  y: number
  vy: number   // negative (going up)
}

export interface Spider {
  x: number
  y: number
  dx: number
  dy: number
  alive: boolean
  lifetime: number // seconds remaining
  points: number   // 300, 600, or 900
}

// ---------------------------------------------------------------------------
// Game state
// ---------------------------------------------------------------------------

export interface GameState {
  player: Player
  centipedes: CentipedeSegment[][] // Array of centipede chains
  mushrooms: Mushroom[]
  bullets: Bullet[]
  spider: Spider | null
  score: number
  lives: number
  level: number
  gameOver: boolean
  spiderTimer: number // seconds until next spider spawn
  invulnerable: number // seconds of invulnerability remaining after respawn
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Convert pixel position to grid column */
function toCol(px: number): number {
  return Math.floor(px / CELL_SIZE)
}

/** Convert pixel position to grid row */
function toRow(py: number): number {
  return Math.floor(py / CELL_SIZE)
}

/** Center of a grid cell in pixels */
function cellCenter(col: number): number {
  return col * CELL_SIZE + CELL_SIZE / 2
}

function cellCenterY(row: number): number {
  return row * CELL_SIZE + CELL_SIZE / 2
}

/** Clamp a number between min and max */
function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

/** Distance between two points */
function dist(x1: number, y1: number, x2: number, y2: number): number {
  const dx = x1 - x2
  const dy = y1 - y2
  return Math.sqrt(dx * dx + dy * dy)
}

/** Check if a mushroom exists at this grid position */
function mushroomAt(
  mushrooms: Mushroom[],
  col: number,
  row: number
): Mushroom | undefined {
  return mushrooms.find(
    m => toCol(m.x) === col && toRow(m.y) === row
  )
}

/** Random integer in [min, max] inclusive */
function randInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min
}

// ---------------------------------------------------------------------------
// Mushroom generation
// ---------------------------------------------------------------------------

function generateMushrooms(count: number): Mushroom[] {
  const mushrooms: Mushroom[] = []
  const occupied = new Set<string>()
  // Keep mushrooms out of the bottom player zone and very top row (centipede start)
  const minRow = 2
  const maxRow = ROWS - PLAYER_ZONE_ROWS - 1
  let attempts = 0
  while (mushrooms.length < count && attempts < count * 10) {
    attempts++
    const col = randInt(0, COLS - 1)
    const row = randInt(minRow, maxRow)
    const key = `${col},${row}`
    if (occupied.has(key)) continue
    occupied.add(key)
    mushrooms.push({
      x: cellCenter(col),
      y: cellCenterY(row),
      hp: 4,
    })
  }
  return mushrooms
}

// ---------------------------------------------------------------------------
// Centipede creation
// ---------------------------------------------------------------------------

function createCentipede(
  length: number,
  level: number,
  startRow: number = 0
): CentipedeSegment[] {
  const speed = BASE_SPEED + SPEED_PER_LEVEL * (level - 1)
  const segments: CentipedeSegment[] = []
  // All segments start stacked at the same entry cell — they uncoil as the head moves
  const startCol = 0
  for (let i = 0; i < length; i++) {
    segments.push({
      x: cellCenter(startCol),
      y: cellCenterY(startRow),
      dx: 1,
      dy: 1,
      isHead: i === 0,
      speed,
      stepAccum: 0,
    })
  }
  return segments
}

// ---------------------------------------------------------------------------
// State creation
// ---------------------------------------------------------------------------

export function createInitialState(level: number = 1): GameState {
  const mushrooms = generateMushrooms(INITIAL_MUSHROOM_COUNT)
  const centipede = createCentipede(CENTIPEDE_LENGTH, level, 0)

  return {
    player: {
      x: GAME_WIDTH / 2,
      y: GAME_HEIGHT - CELL_SIZE,
      lives: 3,
    },
    centipedes: [centipede],
    mushrooms,
    bullets: [],
    spider: null,
    score: 0,
    lives: 3,
    level,
    gameOver: false,
    spiderTimer: SPIDER_SPAWN_INTERVAL,
    invulnerable: 0,
  }
}

// ---------------------------------------------------------------------------
// Player movement
// ---------------------------------------------------------------------------

export function movePlayer(
  state: GameState,
  x: number,
  y: number
): GameState {
  const halfCell = CELL_SIZE / 2
  const minY = GAME_HEIGHT - PLAYER_ZONE_ROWS * CELL_SIZE + halfCell
  const maxY = GAME_HEIGHT - halfCell
  const clampedX = clamp(x, halfCell, GAME_WIDTH - halfCell)
  const clampedY = clamp(y, minY, maxY)
  return {
    ...state,
    player: { ...state.player, x: clampedX, y: clampedY },
  }
}

// ---------------------------------------------------------------------------
// Fire bullet
// ---------------------------------------------------------------------------

export function fireBullet(state: GameState): GameState {
  // Only 1 bullet at a time
  if (state.bullets.length > 0) return state
  const bullet: Bullet = {
    x: state.player.x,
    y: state.player.y - CELL_SIZE,
    vy: -BULLET_SPEED,
  }
  return { ...state, bullets: [bullet] }
}

// ---------------------------------------------------------------------------
// Spider management
// ---------------------------------------------------------------------------

function spawnSpider(): Spider {
  const fromLeft = Math.random() < 0.5
  const x = fromLeft ? 0 : GAME_WIDTH
  const minY = GAME_HEIGHT - PLAYER_ZONE_ROWS * CELL_SIZE
  const y = randInt(minY, GAME_HEIGHT - CELL_SIZE)
  const pointOptions = [300, 600, 900]
  return {
    x,
    y,
    dx: fromLeft ? SPIDER_SPEED : -SPIDER_SPEED,
    dy: (Math.random() < 0.5 ? 1 : -1) * SPIDER_SPEED * 0.7,
    alive: true,
    lifetime: SPIDER_LIFETIME,
    points: pointOptions[randInt(0, 2)],
  }
}

function updateSpider(spider: Spider, dt: number): Spider {
  let { x, y, dx, dy, lifetime } = spider
  x += dx * dt
  y += dy * dt
  lifetime -= dt

  // Bounce off horizontal edges
  if (x < CELL_SIZE / 2) { x = CELL_SIZE / 2; dx = Math.abs(dx) }
  if (x > GAME_WIDTH - CELL_SIZE / 2) {
    x = GAME_WIDTH - CELL_SIZE / 2
    dx = -Math.abs(dx)
  }

  // Bounce within bottom area
  const minY = GAME_HEIGHT - (PLAYER_ZONE_ROWS + 3) * CELL_SIZE
  const maxY = GAME_HEIGHT - CELL_SIZE / 2
  if (y < minY) { y = minY; dy = Math.abs(dy) }
  if (y > maxY) { y = maxY; dy = -Math.abs(dy) }

  return { ...spider, x, y, dx, dy, lifetime }
}

// ---------------------------------------------------------------------------
// Centipede movement
// ---------------------------------------------------------------------------

function moveCentipedeChain(
  chain: CentipedeSegment[],
  mushrooms: Mushroom[],
  dt: number
): CentipedeSegment[] {
  if (chain.length === 0) return chain

  const head = chain[0]
  const stepInterval = CELL_SIZE / head.speed
  const accum = head.stepAccum + dt

  // How many full grid steps this frame?
  const steps = Math.floor(accum / stepInterval)
  const leftover = accum - steps * stepInterval

  // Deep-copy so we can mutate
  let segs = chain.map(s => ({ ...s }))

  for (let step = 0; step < steps; step++) {
    // Save every segment's position/direction before the step
    const prev = segs.map(s => ({ x: s.x, y: s.y, dx: s.dx, dy: s.dy }))

    // --- Move the head one grid cell ---
    const h = segs[0]
    const nextCol = toCol(h.x) + h.dx
    const curRow = toRow(h.y)

    // Check if next horizontal cell is blocked (wall or mushroom)
    const blocked =
      nextCol < 0 ||
      nextCol >= COLS ||
      !!mushroomAt(mushrooms, nextCol, curRow)

    if (blocked) {
      // Reverse horizontal direction
      h.dx = -h.dx
      // Try to move one row in the current vertical direction
      const nextRow = curRow + h.dy
      if (nextRow < 0 || nextRow >= ROWS) {
        // Can't go further vertically — reverse dy
        h.dy = -h.dy
        const altRow = curRow + h.dy
        h.y = cellCenterY(clamp(altRow, 0, ROWS - 1))
      } else {
        h.y = cellCenterY(nextRow)
      }
      // x stays in the same column (just reversed dx)
    } else {
      h.x = cellCenter(nextCol)
    }

    // --- Body segments follow: each adopts its predecessor's old position/direction ---
    for (let i = 1; i < segs.length; i++) {
      segs[i].x = prev[i - 1].x
      segs[i].y = prev[i - 1].y
      segs[i].dx = prev[i - 1].dx
      segs[i].dy = prev[i - 1].dy
    }
  }

  // Store leftover accumulator on the head
  segs[0].stepAccum = leftover
  // Ensure head/body flags
  segs[0].isHead = true
  for (let i = 1; i < segs.length; i++) {
    segs[i].isHead = false
    segs[i].stepAccum = 0
  }

  return segs
}

// ---------------------------------------------------------------------------
// Collision detection
// ---------------------------------------------------------------------------

function checkBulletMushroomCollisions(
  bullets: Bullet[],
  mushrooms: Mushroom[]
): { bullets: Bullet[]; mushrooms: Mushroom[]; scoreAdd: number } {
  const remainingBullets: Bullet[] = []
  let updatedMushrooms = [...mushrooms]
  let scoreAdd = 0

  for (const bullet of bullets) {
    let hit = false
    const newMushrooms: Mushroom[] = []
    for (const mush of updatedMushrooms) {
      if (!hit && dist(bullet.x, bullet.y, mush.x, mush.y) < CELL_SIZE) {
        hit = true
        if (mush.hp > 1) {
          newMushrooms.push({ ...mush, hp: mush.hp - 1 })
        } else {
          scoreAdd += 1 // fully destroyed mushroom
        }
      } else {
        newMushrooms.push(mush)
      }
    }
    updatedMushrooms = newMushrooms
    if (!hit) {
      remainingBullets.push(bullet)
    }
  }

  return { bullets: remainingBullets, mushrooms: updatedMushrooms, scoreAdd }
}

function checkBulletCentipedeCollisions(
  bullets: Bullet[],
  centipedes: CentipedeSegment[][],
  mushrooms: Mushroom[]
): {
  bullets: Bullet[]
  centipedes: CentipedeSegment[][]
  mushrooms: Mushroom[]
  scoreAdd: number
} {
  const remainingBullets: Bullet[] = []
  let updatedCentipedes = [...centipedes]
  const newMushrooms = [...mushrooms]
  let scoreAdd = 0

  for (const bullet of bullets) {
    let hit = false

    const nextCentipedes: CentipedeSegment[][] = []
    for (const chain of updatedCentipedes) {
      if (hit) {
        nextCentipedes.push(chain)
        continue
      }
      let hitIdx = -1
      for (let i = 0; i < chain.length; i++) {
        if (dist(bullet.x, bullet.y, chain[i].x, chain[i].y) < CELL_SIZE) {
          hitIdx = i
          break
        }
      }
      if (hitIdx >= 0) {
        hit = true
        const killed = chain[hitIdx]
        scoreAdd += killed.isHead ? 100 : 10

        // Leave a mushroom at the killed segment's position
        const col = toCol(killed.x)
        const row = toRow(killed.y)
        if (!mushroomAt(newMushrooms, col, row)) {
          newMushrooms.push({
            x: cellCenter(col),
            y: cellCenterY(row),
            hp: 4,
          })
        }

        // Split the chain
        const front = chain.slice(0, hitIdx)
        const back = chain.slice(hitIdx + 1)
        if (front.length > 0) {
          front[0] = { ...front[0], isHead: true, stepAccum: 0 }
          nextCentipedes.push(front)
        }
        if (back.length > 0) {
          back[0] = { ...back[0], isHead: true, stepAccum: 0, dy: killed.dy }
          nextCentipedes.push(back)
        }
      } else {
        nextCentipedes.push(chain)
      }
    }
    updatedCentipedes = nextCentipedes
    if (!hit) {
      remainingBullets.push(bullet)
    }
  }

  return {
    bullets: remainingBullets,
    centipedes: updatedCentipedes,
    mushrooms: newMushrooms,
    scoreAdd,
  }
}

function checkBulletSpiderCollision(
  bullets: Bullet[],
  spider: Spider | null
): { bullets: Bullet[]; spider: Spider | null; scoreAdd: number } {
  if (!spider || !spider.alive) {
    return { bullets, spider, scoreAdd: 0 }
  }
  const remainingBullets: Bullet[] = []
  let updatedSpider: Spider | null = spider
  let scoreAdd = 0
  let hit = false

  for (const bullet of bullets) {
    if (!hit && dist(bullet.x, bullet.y, spider.x, spider.y) < CELL_SIZE) {
      hit = true
      scoreAdd = spider.points
      updatedSpider = null
    } else {
      remainingBullets.push(bullet)
    }
  }

  return { bullets: remainingBullets, spider: updatedSpider, scoreAdd }
}

// ---------------------------------------------------------------------------
// Spider eats mushrooms
// ---------------------------------------------------------------------------

function spiderEatMushrooms(
  spider: Spider,
  mushrooms: Mushroom[]
): Mushroom[] {
  return mushrooms.filter(
    m => dist(spider.x, spider.y, m.x, m.y) >= CELL_SIZE
  )
}

// ---------------------------------------------------------------------------
// Player collision
// ---------------------------------------------------------------------------

function checkPlayerHit(
  player: Player,
  centipedes: CentipedeSegment[][],
  spider: Spider | null
): boolean {
  const hitDist = CELL_SIZE * 0.8
  for (const chain of centipedes) {
    for (const seg of chain) {
      if (dist(player.x, player.y, seg.x, seg.y) < hitDist) {
        return true
      }
    }
  }
  if (spider && spider.alive) {
    if (dist(player.x, player.y, spider.x, spider.y) < hitDist) {
      return true
    }
  }
  return false
}

// ---------------------------------------------------------------------------
// Main update
// ---------------------------------------------------------------------------

export function updateGame(state: GameState, dt: number): GameState {
  if (state.gameOver) return state

  let {
    player, centipedes, mushrooms, bullets, spider,
    score, lives, level, spiderTimer, invulnerable,
  } = state

  // Tick invulnerability
  if (invulnerable > 0) {
    invulnerable = Math.max(0, invulnerable - dt)
  }

  // Move bullets
  bullets = bullets
    .map(b => ({ ...b, y: b.y + b.vy * dt }))
    .filter(b => b.y > -CELL_SIZE)

  // Move centipedes
  centipedes = centipedes.map(chain =>
    moveCentipedeChain(chain, mushrooms, dt)
  )

  // Bullet vs mushroom
  const bmResult = checkBulletMushroomCollisions(bullets, mushrooms)
  bullets = bmResult.bullets
  mushrooms = bmResult.mushrooms
  score += bmResult.scoreAdd

  // Bullet vs centipede
  const bcResult = checkBulletCentipedeCollisions(
    bullets, centipedes, mushrooms
  )
  bullets = bcResult.bullets
  centipedes = bcResult.centipedes
  mushrooms = bcResult.mushrooms
  score += bcResult.scoreAdd

  // Bullet vs spider
  const bsResult = checkBulletSpiderCollision(bullets, spider)
  bullets = bsResult.bullets
  spider = bsResult.spider
  score += bsResult.scoreAdd

  // Spider logic
  spiderTimer -= dt
  if (!spider && spiderTimer <= 0) {
    spider = spawnSpider()
    spiderTimer = SPIDER_SPAWN_INTERVAL
  }
  if (spider) {
    spider = updateSpider(spider, dt)
    mushrooms = spiderEatMushrooms(spider, mushrooms)
    if (spider.lifetime <= 0) {
      spider = null
    }
  }

  // Player collision
  if (invulnerable <= 0 && checkPlayerHit(player, centipedes, spider)) {
    lives -= 1
    player = { ...player, lives }
    if (lives <= 0) {
      return {
        ...state,
        player,
        centipedes,
        mushrooms,
        bullets,
        spider,
        score,
        lives,
        level,
        gameOver: true,
        spiderTimer,
        invulnerable: 0,
      }
    }
    // Respawn at bottom center with brief invulnerability
    player = {
      ...player,
      x: GAME_WIDTH / 2,
      y: GAME_HEIGHT - CELL_SIZE,
    }
    invulnerable = 2.0 // 2 seconds of invulnerability
  }

  return {
    ...state,
    player,
    centipedes,
    mushrooms,
    bullets,
    spider,
    score,
    lives,
    level,
    spiderTimer,
    invulnerable,
  }
}

// ---------------------------------------------------------------------------
// Level transition
// ---------------------------------------------------------------------------

/** Check if all centipede segments have been cleared */
export function isLevelClear(state: GameState): boolean {
  return state.centipedes.every(chain => chain.length === 0)
}

export function nextLevel(state: GameState): GameState {
  const newLevel = state.level + 1
  const centipede = createCentipede(CENTIPEDE_LENGTH, newLevel, 0)

  // Restore damaged mushrooms to full HP
  const restoredMushrooms = state.mushrooms.map(m => ({
    ...m,
    hp: 4,
  }))

  return {
    ...state,
    centipedes: [centipede],
    mushrooms: restoredMushrooms,
    bullets: [],
    spider: null,
    level: newLevel,
    spiderTimer: SPIDER_SPAWN_INTERVAL,
    invulnerable: 1.0,
  }
}
