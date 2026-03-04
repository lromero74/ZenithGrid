/**
 * Dino Runner game engine — pure functions, no React dependencies.
 *
 * Pixel-art endless runner inspired by Chrome's T-Rex game.
 * All game logic is pure: no side effects, no canvas references, fully testable.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DinoState {
  x: number
  y: number
  vy: number
  ducking: boolean
  dead: boolean
  frame: number
}

export type ObstacleType = 'cactus-small' | 'cactus-tall' | 'cactus-group' | 'pterodactyl'

export interface Obstacle {
  type: ObstacleType
  x: number
  y: number
  frame: number
}

export interface Cloud {
  x: number
  y: number
  speed: number
}

export interface Star {
  x: number
  y: number
}

export interface InputState {
  jump: boolean
  duck: boolean
}

export interface Hitbox {
  x: number
  y: number
  w: number
  h: number
}

export interface GameState {
  dino: DinoState
  obstacles: Obstacle[]
  clouds: Cloud[]
  stars: Star[]
  ground: { offset: number }
  score: number
  highScore: number
  speed: number
  phase: 'waiting' | 'playing' | 'dead'
  nightMode: boolean
  nightTransition: number
  frameCount: number
  nextObstacleDistance: number
  milestoneFlash: number
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const CANVAS_WIDTH = 600
export const CANVAS_HEIGHT = 200
export const PIXEL_SCALE = 3
export const GROUND_Y = CANVAS_HEIGHT - 40
export const GRAVITY = 0.6
export const JUMP_VELOCITY = -11
export const HOLD_GRAVITY_FACTOR = 0.6
export const INITIAL_SPEED = 6
export const SPEED_INCREMENT = 0.002
export const MAX_SPEED = 14
export const MIN_OBSTACLE_GAP = 300
export const NIGHT_TOGGLE_INTERVAL = 700
export const NIGHT_TRANSITION_FRAMES = 30
export const PTERO_MIN_SCORE = 300
export const MILESTONE_INTERVAL = 100
export const HITBOX_INSET = 0.8
export const DINO_X = 50

// ---------------------------------------------------------------------------
// Color Palette
// ---------------------------------------------------------------------------

export const PALETTE: Record<number, string> = {
  0: 'transparent',
  1: '#2d5a1e',  // dark green — outline
  2: '#4a8c2a',  // medium green — body fill
  3: '#7ec850',  // light green — belly/highlights
  4: '#ffffff',  // white — eye
  5: '#1a1a1a',  // black — pupil, mouth
  6: '#5c3d1a',  // dark brown — cactus outline
  7: '#8c6b3a',  // medium brown — cactus fill
  8: '#c4a055',  // light brown — ground highlights
  9: '#cc3333',  // red — pterodactyl accents
  10: '#555555', // dark gray — pterodactyl body
  11: '#e67300', // orange — eye detail
}

// ---------------------------------------------------------------------------
// Sprite Data — 2D number arrays (0 = transparent, 1+ = palette index)
// ---------------------------------------------------------------------------

/** Dino run frame 1 — right leg forward (10w x 12h) */
export const DINO_RUN1: number[][] = [
  [0, 0, 0, 0, 1, 1, 1, 1, 0, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 0],
  [0, 0, 0, 1, 2, 4, 5, 2, 1, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 0],
  [0, 0, 1, 1, 1, 2, 5, 1, 0, 0],
  [0, 1, 1, 2, 2, 2, 1, 0, 0, 0],
  [0, 0, 1, 2, 3, 2, 1, 0, 0, 0],
  [0, 0, 1, 2, 3, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 2, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 0, 1, 0, 0, 0, 0],
  [0, 0, 1, 1, 0, 0, 1, 0, 0, 0],
  [0, 0, 1, 0, 0, 0, 1, 1, 0, 0],
]

/** Dino run frame 2 — left leg forward (10w x 12h) */
export const DINO_RUN2: number[][] = [
  [0, 0, 0, 0, 1, 1, 1, 1, 0, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 0],
  [0, 0, 0, 1, 2, 4, 5, 2, 1, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 0],
  [0, 0, 1, 1, 1, 2, 5, 1, 0, 0],
  [0, 1, 1, 2, 2, 2, 1, 0, 0, 0],
  [0, 0, 1, 2, 3, 2, 1, 0, 0, 0],
  [0, 0, 1, 2, 3, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 2, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 0, 1, 0, 0, 0, 0],
  [0, 0, 0, 1, 0, 1, 1, 0, 0, 0],
  [0, 0, 0, 1, 1, 0, 1, 0, 0, 0],
]

/** Dino jump — legs tucked (10w x 12h) */
export const DINO_JUMP: number[][] = [
  [0, 0, 0, 0, 1, 1, 1, 1, 0, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 0],
  [0, 0, 0, 1, 2, 4, 5, 2, 1, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 0],
  [0, 0, 1, 1, 1, 2, 5, 1, 0, 0],
  [0, 1, 1, 2, 2, 2, 1, 0, 0, 0],
  [0, 0, 1, 2, 3, 2, 1, 0, 0, 0],
  [0, 0, 1, 2, 3, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 2, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 2, 1, 1, 0, 0, 0],
  [0, 0, 0, 0, 1, 1, 0, 0, 0, 0],
  [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
]

/** Dino duck frame 1 (14w x 7h) */
export const DINO_DUCK1: number[][] = [
  [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0],
  [0, 0, 0, 0, 0, 0, 0, 1, 2, 4, 5, 2, 1, 0],
  [0, 0, 0, 0, 0, 0, 0, 1, 2, 2, 2, 2, 5, 1],
  [1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 1, 0, 0],
  [0, 0, 1, 2, 3, 3, 2, 2, 2, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 1, 0, 0, 0, 0],
  [0, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0],
]

/** Dino duck frame 2 (14w x 7h) */
export const DINO_DUCK2: number[][] = [
  [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0],
  [0, 0, 0, 0, 0, 0, 0, 1, 2, 4, 5, 2, 1, 0],
  [0, 0, 0, 0, 0, 0, 0, 1, 2, 2, 2, 2, 5, 1],
  [1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 1, 0, 0],
  [0, 0, 1, 2, 3, 3, 2, 2, 2, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 1, 0, 0, 0, 0],
  [0, 0, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0],
]

/** Dino dead — X-eyes (10w x 12h) */
export const DINO_DEAD: number[][] = [
  [0, 0, 0, 0, 1, 1, 1, 1, 0, 0],
  [0, 0, 0, 1, 2, 2, 2, 2, 1, 0],
  [0, 0, 0, 1, 5, 4, 5, 2, 1, 0],
  [0, 0, 0, 1, 4, 5, 4, 2, 1, 0],
  [0, 0, 1, 1, 1, 2, 5, 5, 1, 0],
  [0, 1, 1, 2, 2, 2, 1, 0, 0, 0],
  [0, 0, 1, 2, 3, 2, 1, 0, 0, 0],
  [0, 0, 1, 2, 3, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 2, 2, 1, 0, 0, 0],
  [0, 0, 0, 1, 0, 1, 0, 0, 0, 0],
  [0, 0, 1, 1, 0, 0, 1, 0, 0, 0],
  [0, 0, 1, 0, 0, 0, 1, 1, 0, 0],
]

/** Cactus small (5w x 10h) */
export const CACTUS_SMALL: number[][] = [
  [0, 0, 6, 0, 0],
  [0, 0, 7, 0, 0],
  [6, 0, 7, 0, 0],
  [7, 6, 7, 0, 0],
  [7, 0, 7, 0, 6],
  [6, 0, 7, 6, 7],
  [0, 0, 7, 0, 6],
  [0, 0, 7, 0, 0],
  [0, 0, 7, 0, 0],
  [0, 6, 7, 6, 0],
]

/** Cactus tall (5w x 14h) */
export const CACTUS_TALL: number[][] = [
  [0, 0, 6, 0, 0],
  [0, 0, 7, 0, 0],
  [0, 0, 7, 0, 0],
  [0, 0, 7, 0, 0],
  [6, 0, 7, 0, 0],
  [7, 6, 7, 0, 0],
  [7, 0, 7, 0, 6],
  [6, 0, 7, 6, 7],
  [0, 0, 7, 0, 6],
  [0, 0, 7, 0, 0],
  [0, 0, 7, 0, 0],
  [0, 0, 7, 0, 0],
  [0, 0, 7, 0, 0],
  [0, 6, 7, 6, 0],
]

/** Cactus group — cluster of 3 (11w x 10h) */
export const CACTUS_GROUP: number[][] = [
  [0, 0, 6, 0, 0, 0, 6, 0, 0, 0, 0],
  [0, 0, 7, 0, 0, 0, 7, 0, 0, 6, 0],
  [6, 0, 7, 0, 6, 0, 7, 0, 0, 7, 0],
  [7, 6, 7, 0, 7, 6, 7, 0, 6, 7, 0],
  [6, 0, 7, 0, 6, 0, 7, 0, 7, 7, 6],
  [0, 0, 7, 0, 0, 0, 7, 0, 6, 7, 0],
  [0, 0, 7, 0, 0, 0, 7, 0, 0, 7, 0],
  [0, 0, 7, 0, 0, 0, 7, 0, 0, 7, 0],
  [0, 0, 7, 0, 0, 0, 7, 0, 0, 7, 0],
  [0, 6, 7, 6, 0, 6, 7, 6, 6, 7, 6],
]

/** Pterodactyl wing up (12w x 8h) */
export const PTERO_UP: number[][] = [
  [0, 0, 0, 0, 0, 10, 0, 0, 0, 0, 0, 0],
  [0, 0, 0, 0, 10, 10, 0, 0, 0, 0, 0, 0],
  [0, 0, 0, 10, 10, 10, 0, 0, 0, 0, 0, 0],
  [0, 0, 10, 10, 10, 10, 10, 10, 10, 10, 10, 0],
  [0, 10, 10, 10, 10, 10, 10, 10, 10,  9, 10, 10],
  [10, 0, 0, 0, 10, 10, 10, 10, 11,  9, 10, 10],
  [0, 0, 0, 0, 0, 10, 10, 10, 10, 10, 10, 0],
  [0, 0, 0, 0, 0, 0, 10, 10, 0, 0, 0, 0],
]

/** Pterodactyl wing down (12w x 8h) */
export const PTERO_DOWN: number[][] = [
  [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  [0, 0, 10, 10, 10, 10, 10, 10, 10, 10, 10, 0],
  [0, 10, 10, 10, 10, 10, 10, 10, 10,  9, 10, 10],
  [10, 0, 0, 10, 10, 10, 10, 10, 11,  9, 10, 10],
  [0, 0, 0, 0, 10, 10, 10, 10, 10, 10, 10, 0],
  [0, 0, 0, 0, 10, 10, 0, 0, 0, 0, 0, 0],
]

/** Cloud (16w x 5h) */
export const CLOUD: number[][] = [
  [0, 0, 0, 4, 4, 0, 0, 0, 0, 4, 4, 0, 0, 0, 0, 0],
  [0, 0, 4, 4, 4, 4, 0, 0, 4, 4, 4, 4, 4, 0, 0, 0],
  [0, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 0, 0],
  [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 0],
  [0, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
]

// ---------------------------------------------------------------------------
// Sprite size helpers
// ---------------------------------------------------------------------------

export function getSpriteSize(sprite: number[][]): { w: number; h: number } {
  return { w: sprite[0].length, h: sprite.length }
}

/** Get the right dino sprite for the current state. */
export function getDinoSprite(dino: DinoState): number[][] {
  if (dino.dead) return DINO_DEAD
  if (dino.ducking) return dino.frame % 10 < 5 ? DINO_DUCK1 : DINO_DUCK2
  if (dino.y < GROUND_Y) return DINO_JUMP
  return dino.frame % 10 < 5 ? DINO_RUN1 : DINO_RUN2
}

/** Get the right pterodactyl sprite for animation frame. */
export function getPteroSprite(frame: number): number[][] {
  return frame % 20 < 10 ? PTERO_UP : PTERO_DOWN
}

/** Get obstacle sprite by type. */
export function getObstacleSprite(obs: Obstacle): number[][] {
  switch (obs.type) {
    case 'cactus-small': return CACTUS_SMALL
    case 'cactus-tall': return CACTUS_TALL
    case 'cactus-group': return CACTUS_GROUP
    case 'pterodactyl': return getPteroSprite(obs.frame)
  }
}

// ---------------------------------------------------------------------------
// Hitbox helpers
// ---------------------------------------------------------------------------

/** Get the inset hitbox for collision detection (80% of visual size). */
export function getHitbox(x: number, y: number, w: number, h: number): Hitbox {
  const insetX = w * (1 - HITBOX_INSET) / 2
  const insetY = h * (1 - HITBOX_INSET) / 2
  return {
    x: x + insetX,
    y: y + insetY,
    w: w * HITBOX_INSET,
    h: h * HITBOX_INSET,
  }
}

/** Get the dino hitbox in canvas pixels. */
export function getDinoHitbox(dino: DinoState): Hitbox {
  const sprite = getDinoSprite(dino)
  const size = getSpriteSize(sprite)
  return getHitbox(
    dino.x,
    dino.y - size.h * PIXEL_SCALE + PIXEL_SCALE,
    size.w * PIXEL_SCALE,
    size.h * PIXEL_SCALE,
  )
}

/** Get an obstacle hitbox in canvas pixels. */
export function getObstacleHitbox(obs: Obstacle): Hitbox {
  const sprite = getObstacleSprite(obs)
  const size = getSpriteSize(sprite)
  const w = size.w * PIXEL_SCALE
  const h = size.h * PIXEL_SCALE
  // Obstacles are anchored at bottom-left at (obs.x, obs.y)
  return getHitbox(obs.x, obs.y - h, w, h)
}

/** Check if two hitboxes overlap. */
export function hitboxesOverlap(a: Hitbox, b: Hitbox): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x &&
         a.y < b.y + b.h && a.y + a.h > b.y
}

/** Check if the dino collides with an obstacle. */
export function checkCollision(dino: DinoState, obstacle: Obstacle): boolean {
  return hitboxesOverlap(getDinoHitbox(dino), getObstacleHitbox(obstacle))
}

// ---------------------------------------------------------------------------
// Random obstacle generation helpers
// ---------------------------------------------------------------------------

function randomObstacleGap(speed: number): number {
  const base = Math.max(MIN_OBSTACLE_GAP, 500 - speed * 15)
  return base + Math.random() * 200
}

function randomObstacleType(score: number): ObstacleType {
  const types: ObstacleType[] = ['cactus-small', 'cactus-tall', 'cactus-group']
  if (score >= PTERO_MIN_SCORE) types.push('pterodactyl')
  return types[Math.floor(Math.random() * types.length)]
}

function getObstacleY(type: ObstacleType): number {
  if (type === 'pterodactyl') {
    // Random height: ground level or head height
    const heights = [GROUND_Y, GROUND_Y - 40, GROUND_Y - 70]
    return heights[Math.floor(Math.random() * heights.length)]
  }
  return GROUND_Y
}

// ---------------------------------------------------------------------------
// Game creation
// ---------------------------------------------------------------------------

export function createGame(highScore: number): GameState {
  return {
    dino: {
      x: DINO_X,
      y: GROUND_Y,
      vy: 0,
      ducking: false,
      dead: false,
      frame: 0,
    },
    obstacles: [],
    clouds: [],
    stars: generateStars(),
    ground: { offset: 0 },
    score: 0,
    highScore,
    speed: INITIAL_SPEED,
    phase: 'waiting',
    nightMode: false,
    nightTransition: 0,
    frameCount: 0,
    nextObstacleDistance: 400,
    milestoneFlash: 0,
  }
}

function generateStars(): Star[] {
  const stars: Star[] = []
  for (let i = 0; i < 20; i++) {
    stars.push({
      x: Math.random() * CANVAS_WIDTH,
      y: Math.random() * (GROUND_Y - 40),
    })
  }
  return stars
}

// ---------------------------------------------------------------------------
// Main update loop
// ---------------------------------------------------------------------------

export function update(state: GameState, input: InputState): GameState {
  if (state.phase === 'dead') return state

  // Waiting phase — start on jump
  if (state.phase === 'waiting') {
    if (input.jump) {
      return {
        ...state,
        phase: 'playing',
        dino: {
          ...state.dino,
          vy: JUMP_VELOCITY,
        },
      }
    }
    return state
  }

  // Playing phase
  let dino = { ...state.dino }
  let { speed, score, highScore, nightMode, nightTransition,
        nextObstacleDistance, milestoneFlash } = state
  let frameCount = state.frameCount + 1

  // --- Dino physics ---
  const onGround = dino.y >= GROUND_Y

  // Jump input
  if (input.jump && onGround && dino.vy >= 0) {
    dino.vy = JUMP_VELOCITY
  }

  // Variable jump height: if holding jump while rising, reduce gravity
  const effectiveGravity = (input.jump && dino.vy < 0)
    ? GRAVITY * HOLD_GRAVITY_FACTOR
    : GRAVITY

  if (!onGround || dino.vy < 0) {
    dino.vy += effectiveGravity
    dino.y += dino.vy
  }

  // Land on ground
  if (dino.y >= GROUND_Y) {
    dino.y = GROUND_Y
    dino.vy = 0
  }

  // Ducking (only on ground)
  dino.ducking = input.duck && onGround

  // Animation frame
  dino.frame = frameCount

  // --- Speed ---
  speed = Math.min(MAX_SPEED, speed + SPEED_INCREMENT)

  // --- Score ---
  const prevScore = score
  score += speed * 0.1
  const prevMilestone = Math.floor(prevScore / MILESTONE_INTERVAL)
  const currMilestone = Math.floor(score / MILESTONE_INTERVAL)
  if (currMilestone > prevMilestone) {
    milestoneFlash = 20
  }
  if (milestoneFlash > 0) milestoneFlash--

  // High score
  if (score > highScore) highScore = score

  // --- Day/Night cycle ---
  const prevNightToggle = Math.floor(prevScore / NIGHT_TOGGLE_INTERVAL)
  const currNightToggle = Math.floor(score / NIGHT_TOGGLE_INTERVAL)
  if (currNightToggle > prevNightToggle) {
    nightMode = !nightMode
  }
  // Smooth transition
  if (nightMode && nightTransition < 1) {
    nightTransition = Math.min(1, nightTransition + 1 / NIGHT_TRANSITION_FRAMES)
  } else if (!nightMode && nightTransition > 0) {
    nightTransition = Math.max(0, nightTransition - 1 / NIGHT_TRANSITION_FRAMES)
  }

  // --- Obstacles ---
  let obstacles = state.obstacles.map(obs => ({
    ...obs,
    x: obs.x - speed,
    frame: obs.frame + 1,
  }))

  // Remove off-screen
  obstacles = obstacles.filter(obs => obs.x > -60)

  // Spawn new obstacles
  nextObstacleDistance -= speed
  if (nextObstacleDistance <= 0) {
    const type = randomObstacleType(score)
    obstacles.push({
      type,
      x: CANVAS_WIDTH + 10,
      y: getObstacleY(type),
      frame: 0,
    })
    nextObstacleDistance = randomObstacleGap(speed)
  }

  // --- Collision detection ---
  for (const obs of obstacles) {
    if (checkCollision(dino, obs)) {
      dino.dead = true
      return {
        ...state,
        dino,
        obstacles,
        score,
        highScore: Math.max(highScore, score),
        speed,
        phase: 'dead',
        nightMode,
        nightTransition,
        frameCount,
        nextObstacleDistance,
        milestoneFlash: 0,
        ground: { offset: (state.ground.offset + speed) % 12 },
      }
    }
  }

  // --- Clouds ---
  let clouds = state.clouds.map(c => ({
    ...c,
    x: c.x - c.speed,
  }))
  clouds = clouds.filter(c => c.x > -60)
  if (frameCount % 120 === 0 && clouds.length < 5) {
    clouds.push({
      x: CANVAS_WIDTH + 20,
      y: 20 + Math.random() * 60,
      speed: 1 + Math.random() * 1.5,
    })
  }

  // --- Ground scroll ---
  const groundOffset = (state.ground.offset + speed) % 12

  return {
    ...state,
    dino,
    obstacles,
    clouds,
    ground: { offset: groundOffset },
    score,
    highScore,
    speed,
    phase: 'playing',
    nightMode,
    nightTransition,
    frameCount,
    nextObstacleDistance,
    milestoneFlash,
  }
}
