/**
 * Tests for Dino Runner game engine.
 */

import { describe, test, expect } from 'vitest'
import {
  createGame,
  update,
  checkCollision,
  getHitbox,
  getDinoHitbox,
  getObstacleHitbox,
  hitboxesOverlap,
  getSpriteSize,
  getDinoSprite,
  getPteroSprite,
  GROUND_Y,
  GRAVITY,
  JUMP_VELOCITY,
  HOLD_GRAVITY_FACTOR,
  INITIAL_SPEED,
  MAX_SPEED,
  SPEED_INCREMENT,
  CANVAS_WIDTH,
  CANVAS_HEIGHT,
  PIXEL_SCALE,
  DINO_X,
  HITBOX_INSET,
  NIGHT_TOGGLE_INTERVAL,
  PTERO_MIN_SCORE,
  DINO_RUN1,
  DINO_RUN2,
  DINO_JUMP,
  DINO_DUCK1,
  DINO_DEAD,
  CACTUS_SMALL,
  PTERO_UP,
  PTERO_DOWN,
  type GameState,
  type InputState,
  type DinoState,
  type Obstacle,
} from './dinoRunnerEngine'

const NO_INPUT: InputState = { jump: false, duck: false }
const JUMP_INPUT: InputState = { jump: true, duck: false }
const DUCK_INPUT: InputState = { jump: false, duck: true }

// ---------------------------------------------------------------------------
// createGame
// ---------------------------------------------------------------------------

describe('createGame', () => {
  test('returns correct initial state with waiting phase', () => {
    const state = createGame(0)
    expect(state.phase).toBe('waiting')
    expect(state.score).toBe(0)
    expect(state.speed).toBe(INITIAL_SPEED)
    expect(state.frameCount).toBe(0)
    expect(state.obstacles).toEqual([])
    expect(state.nightMode).toBe(false)
    expect(state.nightTransition).toBe(0)
  })

  test('dino starts at ground level', () => {
    const state = createGame(0)
    expect(state.dino.x).toBe(DINO_X)
    expect(state.dino.y).toBe(GROUND_Y)
    expect(state.dino.vy).toBe(0)
    expect(state.dino.ducking).toBe(false)
    expect(state.dino.dead).toBe(false)
  })

  test('preserves high score from argument', () => {
    const state = createGame(500)
    expect(state.highScore).toBe(500)
  })

  test('generates stars for night mode', () => {
    const state = createGame(0)
    expect(state.stars.length).toBe(20)
    state.stars.forEach(star => {
      expect(star.x).toBeGreaterThanOrEqual(0)
      expect(star.x).toBeLessThan(CANVAS_WIDTH)
      expect(star.y).toBeGreaterThanOrEqual(0)
    })
  })
})

// ---------------------------------------------------------------------------
// Jump mechanics
// ---------------------------------------------------------------------------

describe('jump mechanics', () => {
  test('jump input in waiting phase starts the game', () => {
    const state = createGame(0)
    const next = update(state, JUMP_INPUT)
    expect(next.phase).toBe('playing')
    expect(next.dino.vy).toBe(JUMP_VELOCITY)
  })

  test('no input in waiting phase keeps waiting', () => {
    const state = createGame(0)
    const next = update(state, NO_INPUT)
    expect(next.phase).toBe('waiting')
  })

  test('dino rises when vy is negative', () => {
    const state = createGame(0)
    // Start game with jump
    const s1 = update(state, JUMP_INPUT)
    // One more frame
    const s2 = update(s1, NO_INPUT)
    expect(s2.dino.y).toBeLessThan(GROUND_Y)
    expect(s2.dino.vy).toBeGreaterThan(JUMP_VELOCITY) // gravity pulling back
  })

  test('gravity pulls dino back to ground', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT) // start game (sets vy but doesn't move yet)
    state = update(state, NO_INPUT)   // first playing frame — dino lifts off
    expect(state.dino.y).toBeLessThan(GROUND_Y)
    // Run frames until dino lands
    let frames = 0
    while (state.dino.y < GROUND_Y && frames < 200) {
      state = update(state, NO_INPUT)
      frames++
    }
    expect(state.dino.y).toBe(GROUND_Y)
    expect(state.dino.vy).toBe(0)
    expect(frames).toBeGreaterThan(5) // should take several frames
  })

  test('cannot jump while airborne', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT) // start + jump
    state = update(state, NO_INPUT)   // in air
    const airY = state.dino.y
    const airVy = state.dino.vy
    // Try to jump again mid-air
    const next = update(state, JUMP_INPUT)
    // Should not reset vy to jump velocity
    expect(next.dino.vy).not.toBe(JUMP_VELOCITY)
    // vy should be closer to 0 than before (gravity pulls toward ground)
    expect(next.dino.vy).toBeGreaterThan(airVy)
  })
})

// ---------------------------------------------------------------------------
// Variable jump height
// ---------------------------------------------------------------------------

describe('variable jump height', () => {
  test('holding jump produces higher peak than tap', () => {
    // Tap: jump once, then release
    let tapState = createGame(0)
    tapState = update(tapState, JUMP_INPUT)
    let tapMinY = tapState.dino.y
    for (let i = 0; i < 100; i++) {
      tapState = update(tapState, NO_INPUT)
      tapMinY = Math.min(tapMinY, tapState.dino.y)
    }

    // Hold: keep holding jump
    let holdState = createGame(0)
    holdState = update(holdState, JUMP_INPUT)
    let holdMinY = holdState.dino.y
    for (let i = 0; i < 100; i++) {
      holdState = update(holdState, JUMP_INPUT)
      holdMinY = Math.min(holdMinY, holdState.dino.y)
    }

    // Holding jump should reach higher (lower y value)
    expect(holdMinY).toBeLessThan(tapMinY)
  })

  test('hold gravity factor reduces gravity while rising with jump held', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT) // start game + initial jump
    const vyAfterStart = state.dino.vy

    // Frame with jump held: gravity reduced
    const holdFrame = update(state, JUMP_INPUT)
    const expectedVyHold = vyAfterStart + GRAVITY * HOLD_GRAVITY_FACTOR
    expect(holdFrame.dino.vy).toBeCloseTo(expectedVyHold, 5)

    // Frame without jump: full gravity
    const releaseFrame = update(state, NO_INPUT)
    const expectedVyRelease = vyAfterStart + GRAVITY
    expect(releaseFrame.dino.vy).toBeCloseTo(expectedVyRelease, 5)
  })
})

// ---------------------------------------------------------------------------
// Duck mechanics
// ---------------------------------------------------------------------------

describe('duck mechanics', () => {
  test('ducking flag set when duck input and on ground', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT) // start game
    // Run until landed
    for (let i = 0; i < 100; i++) {
      state = update(state, NO_INPUT)
      if (state.dino.y >= GROUND_Y) break
    }
    const ducked = update(state, DUCK_INPUT)
    expect(ducked.dino.ducking).toBe(true)
  })

  test('ducking changes the sprite to duck sprite', () => {
    const dino: DinoState = {
      x: DINO_X, y: GROUND_Y, vy: 0,
      ducking: true, dead: false, frame: 0,
    }
    const sprite = getDinoSprite(dino)
    expect(sprite).toBe(DINO_DUCK1)
    // Duck sprite is wider and shorter
    expect(sprite[0].length).toBe(14) // 14w
    expect(sprite.length).toBe(7)     // 7h
  })

  test('not ducking while airborne', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT) // start + jump
    state = update(state, NO_INPUT)   // in air
    const ducked = update(state, DUCK_INPUT)
    // Dino is airborne — ducking should not activate
    expect(ducked.dino.ducking).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Speed increase
// ---------------------------------------------------------------------------

describe('speed increase', () => {
  test('speed increments each frame', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT) // start
    const initialSpeed = state.speed
    state = update(state, NO_INPUT)
    expect(state.speed).toBeGreaterThan(initialSpeed)
    expect(state.speed).toBeCloseTo(initialSpeed + SPEED_INCREMENT, 8)
  })

  test('speed caps at MAX_SPEED', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT)
    // Manually set speed near max
    state = { ...state, speed: MAX_SPEED - 0.001 }
    state = update(state, NO_INPUT)
    expect(state.speed).toBe(MAX_SPEED)
  })
})

// ---------------------------------------------------------------------------
// Obstacle spawning
// ---------------------------------------------------------------------------

describe('obstacle spawning', () => {
  test('obstacles spawn when nextObstacleDistance reaches 0', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT) // start
    // Force spawn by setting distance to 0
    state = { ...state, nextObstacleDistance: 0 }
    state = update(state, NO_INPUT)
    expect(state.obstacles.length).toBeGreaterThanOrEqual(1)
  })

  test('obstacles removed when off-screen', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT)
    // Add an obstacle that's already off-screen
    state = {
      ...state,
      obstacles: [{ type: 'cactus-small', x: -100, y: GROUND_Y, frame: 0 }],
    }
    state = update(state, NO_INPUT)
    expect(state.obstacles.length).toBe(0)
  })

  test('obstacles move left each frame at current speed', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT)
    const obsX = 400
    state = {
      ...state,
      obstacles: [{ type: 'cactus-small', x: obsX, y: GROUND_Y, frame: 0 }],
      nextObstacleDistance: 9999, // prevent new spawns
    }
    const next = update(state, NO_INPUT)
    expect(next.obstacles[0].x).toBeCloseTo(obsX - next.speed, 1)
  })
})

// ---------------------------------------------------------------------------
// Collision detection
// ---------------------------------------------------------------------------

describe('collision detection', () => {
  test('no collision when obstacle is far away', () => {
    const dino: DinoState = {
      x: DINO_X, y: GROUND_Y, vy: 0,
      ducking: false, dead: false, frame: 0,
    }
    const obs: Obstacle = { type: 'cactus-small', x: 500, y: GROUND_Y, frame: 0 }
    expect(checkCollision(dino, obs)).toBe(false)
  })

  test('collision when dino overlaps cactus at ground level', () => {
    const dino: DinoState = {
      x: DINO_X, y: GROUND_Y, vy: 0,
      ducking: false, dead: false, frame: 0,
    }
    // Place cactus right at dino position
    const obs: Obstacle = { type: 'cactus-small', x: DINO_X, y: GROUND_Y, frame: 0 }
    expect(checkCollision(dino, obs)).toBe(true)
  })

  test('no collision when dino jumps over cactus', () => {
    const dino: DinoState = {
      x: DINO_X, y: GROUND_Y - 80, vy: 0,
      ducking: false, dead: false, frame: 0,
    }
    const obs: Obstacle = { type: 'cactus-small', x: DINO_X + 5, y: GROUND_Y, frame: 0 }
    expect(checkCollision(dino, obs)).toBe(false)
  })

  test('collision triggers death in update', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT) // start
    // Place cactus right at dino position
    state = {
      ...state,
      obstacles: [{ type: 'cactus-small', x: DINO_X, y: GROUND_Y, frame: 0 }],
      dino: { ...state.dino, y: GROUND_Y, vy: 0 },
    }
    // Need to be on ground for collision to register
    const next = update(state, NO_INPUT)
    expect(next.phase).toBe('dead')
    expect(next.dino.dead).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// Hitbox helpers
// ---------------------------------------------------------------------------

describe('hitbox helpers', () => {
  test('getHitbox insets by HITBOX_INSET factor', () => {
    const hb = getHitbox(100, 50, 30, 40)
    expect(hb.w).toBeCloseTo(30 * HITBOX_INSET)
    expect(hb.h).toBeCloseTo(40 * HITBOX_INSET)
    expect(hb.x).toBeGreaterThan(100)
    expect(hb.y).toBeGreaterThan(50)
  })

  test('hitboxesOverlap detects overlap', () => {
    const a = { x: 0, y: 0, w: 10, h: 10 }
    const b = { x: 5, y: 5, w: 10, h: 10 }
    expect(hitboxesOverlap(a, b)).toBe(true)
  })

  test('hitboxesOverlap returns false for non-overlapping', () => {
    const a = { x: 0, y: 0, w: 10, h: 10 }
    const b = { x: 20, y: 20, w: 10, h: 10 }
    expect(hitboxesOverlap(a, b)).toBe(false)
  })

  test('hitboxesOverlap returns false for edge-touching', () => {
    const a = { x: 0, y: 0, w: 10, h: 10 }
    const b = { x: 10, y: 0, w: 10, h: 10 }
    expect(hitboxesOverlap(a, b)).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Scoring
// ---------------------------------------------------------------------------

describe('scoring', () => {
  test('score increments proportional to speed', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT) // start
    const scoreBefore = state.score
    state = update(state, NO_INPUT)
    // Score should increase by approximately speed * 0.1
    expect(state.score).toBeGreaterThan(scoreBefore)
    expect(state.score - scoreBefore).toBeCloseTo(state.speed * 0.1, 0)
  })

  test('high score updates when score exceeds it', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT)
    // Run a few frames to accumulate score
    for (let i = 0; i < 10; i++) {
      state = update(state, NO_INPUT)
    }
    expect(state.highScore).toBeGreaterThan(0)
    expect(state.highScore).toBeGreaterThanOrEqual(state.score)
  })

  test('milestone flash triggers at 100-point intervals', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT)
    // Set score just below milestone
    state = { ...state, score: 99.5 }
    // Update until we cross 100
    state = update(state, NO_INPUT)
    if (state.score >= 100) {
      expect(state.milestoneFlash).toBeGreaterThan(0)
    }
  })
})

// ---------------------------------------------------------------------------
// Day/night cycle
// ---------------------------------------------------------------------------

describe('day/night cycle', () => {
  test('starts in day mode', () => {
    const state = createGame(0)
    expect(state.nightMode).toBe(false)
    expect(state.nightTransition).toBe(0)
  })

  test('toggles night mode at score intervals', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT)
    // Set score just below toggle point
    state = { ...state, score: NIGHT_TOGGLE_INTERVAL - 0.5 }
    // Update until we cross the threshold
    let crossed = false
    for (let i = 0; i < 5; i++) {
      state = update(state, NO_INPUT)
      if (state.nightMode) { crossed = true; break }
    }
    expect(crossed).toBe(true)
  })

  test('night transition progresses gradually', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT)
    state = { ...state, nightMode: true, nightTransition: 0 }
    state = update(state, NO_INPUT)
    expect(state.nightTransition).toBeGreaterThan(0)
    expect(state.nightTransition).toBeLessThanOrEqual(1)
  })
})

// ---------------------------------------------------------------------------
// Game over
// ---------------------------------------------------------------------------

describe('game over', () => {
  test('no updates after death', () => {
    const deadState: GameState = {
      ...createGame(0),
      phase: 'dead',
      score: 42,
    }
    const next = update(deadState, JUMP_INPUT)
    expect(next).toBe(deadState) // exact same reference
  })
})

// ---------------------------------------------------------------------------
// Pterodactyl spawning
// ---------------------------------------------------------------------------

describe('pterodactyl spawning', () => {
  test('pterodactyl type not available before PTERO_MIN_SCORE', () => {
    // We can't easily test randomObstacleType directly (it's not exported),
    // but we can verify no pterodactyls spawn at low score by running many frames
    let state = createGame(0)
    state = update(state, JUMP_INPUT)
    // Force many spawns at low score
    for (let i = 0; i < 50; i++) {
      state = { ...state, nextObstacleDistance: 0, score: 10 }
      state = update(state, NO_INPUT)
    }
    const pteros = state.obstacles.filter(o => o.type === 'pterodactyl')
    // With score=10, no pterodactyls should spawn
    expect(pteros.length).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// Ground scrolling
// ---------------------------------------------------------------------------

describe('ground scrolling', () => {
  test('ground offset increases each frame', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT) // start
    const prev = state.ground.offset
    state = update(state, NO_INPUT)
    expect(state.ground.offset).not.toBe(prev)
  })

  test('ground offset wraps around', () => {
    let state = createGame(0)
    state = update(state, JUMP_INPUT)
    // Run many frames
    for (let i = 0; i < 100; i++) {
      state = update(state, NO_INPUT)
    }
    expect(state.ground.offset).toBeGreaterThanOrEqual(0)
    expect(state.ground.offset).toBeLessThan(12)
  })
})

// ---------------------------------------------------------------------------
// Sprite helpers
// ---------------------------------------------------------------------------

describe('sprite helpers', () => {
  test('getSpriteSize returns correct dimensions', () => {
    expect(getSpriteSize(DINO_RUN1)).toEqual({ w: 10, h: 12 })
    expect(getSpriteSize(DINO_DUCK1)).toEqual({ w: 14, h: 7 })
    expect(getSpriteSize(CACTUS_SMALL)).toEqual({ w: 5, h: 10 })
    expect(getSpriteSize(PTERO_UP)).toEqual({ w: 12, h: 8 })
  })

  test('getDinoSprite returns dead sprite when dead', () => {
    const dino: DinoState = { x: 0, y: GROUND_Y, vy: 0, ducking: false, dead: true, frame: 0 }
    expect(getDinoSprite(dino)).toBe(DINO_DEAD)
  })

  test('getDinoSprite returns jump sprite when airborne', () => {
    const dino: DinoState = { x: 0, y: GROUND_Y - 50, vy: -5, ducking: false, dead: false, frame: 0 }
    expect(getDinoSprite(dino)).toBe(DINO_JUMP)
  })

  test('getDinoSprite alternates run frames on ground', () => {
    const dino0: DinoState = { x: 0, y: GROUND_Y, vy: 0, ducking: false, dead: false, frame: 0 }
    const dino5: DinoState = { ...dino0, frame: 5 }
    expect(getDinoSprite(dino0)).toBe(DINO_RUN1)
    expect(getDinoSprite(dino5)).toBe(DINO_RUN2)
  })

  test('getPteroSprite alternates wing frames', () => {
    expect(getPteroSprite(0)).toBe(PTERO_UP)
    expect(getPteroSprite(10)).toBe(PTERO_DOWN)
    expect(getPteroSprite(20)).toBe(PTERO_UP)
  })
})

// ---------------------------------------------------------------------------
// Immutability
// ---------------------------------------------------------------------------

describe('immutability', () => {
  test('update does not mutate the input state', () => {
    const state = createGame(0)
    const stateJson = JSON.stringify(state)
    update(state, JUMP_INPUT)
    expect(JSON.stringify(state)).toBe(stateJson)
  })
})
