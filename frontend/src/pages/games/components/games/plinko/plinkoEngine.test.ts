import { describe, test, expect } from 'vitest'
import {
  generatePegLayout, getMultipliers, createBall, stepPhysics,
  checkPegCollision, resolveCollision, checkBallCollision, resolveBallCollision,
  getSlotIndex, getDropPositions,
  type Peg, type Ball, type RiskLevel,
  PEG_RADIUS, BALL_RADIUS, GRAVITY, RESTITUTION, DAMPING,
  BOARD_WIDTH, BOARD_HEIGHT, SLOT_COUNT, PEG_ROWS,
} from './plinkoEngine'

describe('generatePegLayout', () => {
  test('classic layout returns 10 rows of pegs', () => {
    const pegs = generatePegLayout('classic')
    const rows = new Set(pegs.map(p => p.row))
    expect(rows.size).toBe(10)
  })

  test('classic layout has alternating 13/14 pegs per row (slot-aligned)', () => {
    const pegs = generatePegLayout('classic')
    for (let row = 0; row < 10; row++) {
      const rowPegs = pegs.filter(p => p.row === row)
      // Even rows: SLOT_COUNT pegs at slot centers
      // Odd rows: SLOT_COUNT + 1 pegs at slot boundaries (including edges)
      expect(rowPegs.length).toBe(row % 2 === 0 ? SLOT_COUNT : SLOT_COUNT + 1)
    }
  })

  test('classic layout rows are staggered', () => {
    const pegs = generatePegLayout('classic')
    const row0 = pegs.filter(p => p.row === 0).sort((a, b) => a.x - b.x)
    const row1 = pegs.filter(p => p.row === 1).sort((a, b) => a.x - b.x)
    expect(row0[0].x).not.toBeCloseTo(row1[0].x, 1)
  })

  test('pyramid layout has row n with n+3 pegs', () => {
    const pegs = generatePegLayout('pyramid')
    for (let row = 0; row < 10; row++) {
      const rowPegs = pegs.filter(p => p.row === row)
      expect(rowPegs.length).toBe(row + 3)
    }
  })

  test('diamond layout is symmetric (starts/ends narrow)', () => {
    const pegs = generatePegLayout('diamond')
    const row0 = pegs.filter(p => p.row === 0)
    const row4 = pegs.filter(p => p.row === 4)
    const row9 = pegs.filter(p => p.row === 9)
    expect(row0.length).toBe(row9.length) // symmetric
    expect(row4.length).toBeGreaterThan(row0.length) // wider in middle
  })

  test('all layouts have non-negative coordinates', () => {
    for (const layout of ['classic', 'pyramid', 'diamond'] as const) {
      const pegs = generatePegLayout(layout)
      for (const peg of pegs) {
        expect(peg.x).toBeGreaterThanOrEqual(0)
        expect(peg.y).toBeGreaterThan(0)
      }
    }
  })

  test('default layout is classic', () => {
    const defaultPegs = generatePegLayout()
    const classicPegs = generatePegLayout('classic')
    expect(defaultPegs.length).toBe(classicPegs.length)
  })
})

describe('getMultipliers', () => {
  test('returns array for each risk level', () => {
    const levels: RiskLevel[] = ['low', 'medium', 'high']
    for (const level of levels) {
      const m = getMultipliers(level)
      expect(Array.isArray(m)).toBe(true)
      expect(m.length).toBeGreaterThan(0)
    }
  })

  test('each array has 13 elements', () => {
    expect(getMultipliers('low').length).toBe(13)
    expect(getMultipliers('medium').length).toBe(13)
    expect(getMultipliers('high').length).toBe(13)
  })

  test('arrays are symmetric', () => {
    const levels: RiskLevel[] = ['low', 'medium', 'high']
    for (const level of levels) {
      const m = getMultipliers(level)
      for (let i = 0; i < m.length; i++) {
        expect(m[i]).toBe(m[m.length - 1 - i])
      }
    }
  })

  test('low risk has smaller spread', () => {
    const low = getMultipliers('low')
    const high = getMultipliers('high')
    const lowMax = Math.max(...low)
    const highMax = Math.max(...high)
    expect(lowMax).toBeLessThan(highMax)
  })

  test('high risk has larger spread', () => {
    const high = getMultipliers('high')
    const highMax = Math.max(...high)
    const highMin = Math.min(...high)
    expect(highMax).toBeGreaterThanOrEqual(10)
    expect(highMin).toBeLessThanOrEqual(0.3)
  })

  test('medium is between low and high', () => {
    const lowMax = Math.max(...getMultipliers('low'))
    const medMax = Math.max(...getMultipliers('medium'))
    const highMax = Math.max(...getMultipliers('high'))
    expect(medMax).toBeGreaterThan(lowMax)
    expect(medMax).toBeLessThan(highMax)
  })
})

describe('createBall', () => {
  test('has the given x position', () => {
    const ball = createBall(150)
    expect(ball.x).toBe(150)
  })

  test('y starts just above first peg row', () => {
    const ball = createBall(100)
    expect(ball.y).toBe(45)
  })

  test('vx and vy are 0', () => {
    const ball = createBall(200)
    expect(ball.vx).toBe(0)
    expect(ball.vy).toBe(0)
  })

  test('has unique id', () => {
    const ball1 = createBall(100)
    const ball2 = createBall(100)
    expect(ball1.id).not.toBe(ball2.id)
  })
})

describe('stepPhysics', () => {
  test('gravity increases vy', () => {
    const ball = createBall(200)
    const next = stepPhysics(ball)
    expect(next.vy).toBeGreaterThan(ball.vy)
    expect(next.vy).toBeCloseTo(GRAVITY)
  })

  test('position updated by velocity', () => {
    const ball: Ball = { id: 1, x: 100, y: 50, vx: 2, vy: 3 }
    const next = stepPhysics(ball)
    expect(next.x).toBeCloseTo(100 + 2)
    expect(next.y).toBeCloseTo(50 + 3 + GRAVITY)
  })

  test('returns new ball (immutable)', () => {
    const ball = createBall(100)
    const next = stepPhysics(ball)
    expect(next).not.toBe(ball)
  })

  test('original ball not mutated', () => {
    const ball = createBall(100)
    const origY = ball.y
    const origVy = ball.vy
    stepPhysics(ball)
    expect(ball.y).toBe(origY)
    expect(ball.vy).toBe(origVy)
  })

  test('damping is NOT applied in stepPhysics', () => {
    const ball: Ball = { id: 1, x: 100, y: 50, vx: 5, vy: 0 }
    const next = stepPhysics(ball)
    // vx should remain unchanged (no damping)
    expect(next.vx).toBe(5)
  })
})

describe('checkPegCollision', () => {
  test('returns true when ball overlaps peg', () => {
    const ball: Ball = { id: 1, x: 100, y: 100, vx: 0, vy: 0 }
    const peg: Peg = { x: 105, y: 100, row: 0 }
    // distance = 5, radii sum = BALL_RADIUS + PEG_RADIUS = 13
    expect(checkPegCollision(ball, peg)).toBe(true)
  })

  test('returns false when ball is far from peg', () => {
    const ball: Ball = { id: 1, x: 0, y: 0, vx: 0, vy: 0 }
    const peg: Peg = { x: 100, y: 100, row: 0 }
    expect(checkPegCollision(ball, peg)).toBe(false)
  })

  test('returns true at exact touching distance', () => {
    const combinedRadius = BALL_RADIUS + PEG_RADIUS
    const ball: Ball = { id: 1, x: 100, y: 100, vx: 0, vy: 0 }
    const peg: Peg = { x: 100 + combinedRadius, y: 100, row: 0 }
    // distance exactly equals radii sum — should be touching
    expect(checkPegCollision(ball, peg)).toBe(true)
  })

  test('handles negative coordinates', () => {
    const ball: Ball = { id: 1, x: -10, y: -10, vx: 0, vy: 0 }
    const peg: Peg = { x: -5, y: -10, row: 0 }
    // distance = 5, radii sum = 13 → collision
    expect(checkPegCollision(ball, peg)).toBe(true)
  })
})

describe('resolveCollision', () => {
  test('ball moves away from peg', () => {
    const ball: Ball = { id: 1, x: 100, y: 100, vx: 2, vy: 3 }
    const peg: Peg = { x: 105, y: 100, row: 0 }
    const resolved = resolveCollision(ball, peg)
    const dx = resolved.x - peg.x
    const dy = resolved.y - peg.y
    const dist = Math.sqrt(dx * dx + dy * dy)
    expect(dist).toBeGreaterThanOrEqual(BALL_RADIUS + PEG_RADIUS - 0.01)
  })

  test('velocity direction changes', () => {
    const ball: Ball = { id: 1, x: 100, y: 100, vx: 2, vy: 3 }
    const peg: Peg = { x: 105, y: 100, row: 0 }
    const resolved = resolveCollision(ball, peg)
    // At least one velocity component should have changed
    expect(resolved.vx !== ball.vx || resolved.vy !== ball.vy).toBe(true)
  })

  test('returns new ball (immutable)', () => {
    const ball: Ball = { id: 1, x: 100, y: 100, vx: 2, vy: 3 }
    const peg: Peg = { x: 105, y: 100, row: 0 }
    const resolved = resolveCollision(ball, peg)
    expect(resolved).not.toBe(ball)
  })

  test('Galton deflection: lateral speed is always non-zero', () => {
    const ball: Ball = { id: 1, x: 100, y: 100, vx: 0, vy: 2 }
    const peg: Peg = { x: 100, y: 105, row: 0 }
    for (let i = 0; i < 20; i++) {
      const resolved = resolveCollision(ball, peg)
      expect(Math.abs(resolved.vx)).toBeGreaterThan(0)
    }
  })

  test('bounce physics: ball bounces upward when hitting peg from above', () => {
    const ball: Ball = { id: 1, x: 100, y: 95, vx: 0, vy: 3 }
    const peg: Peg = { x: 100, y: 100, row: 0 }
    // Ball directly above peg, moving down — reflected + rotated should bounce up
    let sawUpward = false
    for (let i = 0; i < 30; i++) {
      const resolved = resolveCollision(ball, peg)
      if (resolved.vy < 0) sawUpward = true
    }
    expect(sawUpward).toBe(true) // should bounce upward at least some of the time
  })

  test('bounce physics: speed floor prevents ball death', () => {
    // Simulate a very slow ball (as if after many bounces)
    const ball: Ball = { id: 1, x: 100, y: 100, vx: 0.1, vy: 0.2 }
    const peg: Peg = { x: 100, y: 105, row: 0 }
    for (let i = 0; i < 20; i++) {
      const resolved = resolveCollision(ball, peg)
      // Speed floor ensures lateral speed stays alive
      expect(Math.abs(resolved.vx)).toBeGreaterThanOrEqual(0.7)
    }
  })

  test('Galton deflection: lateral speed within expected range', () => {
    const ball: Ball = { id: 1, x: 100, y: 100, vx: 0, vy: 2 }
    const peg: Peg = { x: 100, y: 105, row: 0 }
    for (let i = 0; i < 50; i++) {
      const resolved = resolveCollision(ball, peg)
      const absVx = Math.abs(resolved.vx)
      // Rotation-based: reflected velocity rotated by 9°–30°, with 0.72 floor
      expect(absVx).toBeGreaterThanOrEqual(0.7)
      expect(absVx).toBeLessThanOrEqual(2.5) // rotation of fast ball can produce higher speeds
    }
  })
})

describe('checkBallCollision', () => {
  test('returns true when balls overlap', () => {
    const a: Ball = { id: 1, x: 100, y: 100, vx: 0, vy: 0 }
    const b: Ball = { id: 2, x: 110, y: 100, vx: 0, vy: 0 }
    // distance = 10, threshold = 2 * BALL_RADIUS = 16
    expect(checkBallCollision(a, b)).toBe(true)
  })

  test('returns false when balls are far apart', () => {
    const a: Ball = { id: 1, x: 0, y: 0, vx: 0, vy: 0 }
    const b: Ball = { id: 2, x: 100, y: 100, vx: 0, vy: 0 }
    expect(checkBallCollision(a, b)).toBe(false)
  })

  test('returns false at exactly 2*BALL_RADIUS distance (strict <)', () => {
    const a: Ball = { id: 1, x: 100, y: 100, vx: 0, vy: 0 }
    const b: Ball = { id: 2, x: 100 + BALL_RADIUS * 2, y: 100, vx: 0, vy: 0 }
    expect(checkBallCollision(a, b)).toBe(false)
  })

  test('returns true when balls are at the same position', () => {
    const a: Ball = { id: 1, x: 100, y: 100, vx: 0, vy: 0 }
    const b: Ball = { id: 2, x: 100, y: 100, vx: 0, vy: 0 }
    expect(checkBallCollision(a, b)).toBe(true)
  })
})

describe('resolveBallCollision', () => {
  test('balls are pushed apart', () => {
    const a: Ball = { id: 1, x: 100, y: 100, vx: 2, vy: 0 }
    const b: Ball = { id: 2, x: 110, y: 100, vx: -2, vy: 0 }
    const [ra, rb] = resolveBallCollision(a, b)
    const dx = ra.x - rb.x
    const dy = ra.y - rb.y
    const dist = Math.sqrt(dx * dx + dy * dy)
    expect(dist).toBeGreaterThanOrEqual(BALL_RADIUS * 2 - 0.01)
  })

  test('velocities change after collision', () => {
    const a: Ball = { id: 1, x: 100, y: 100, vx: 3, vy: 0 }
    const b: Ball = { id: 2, x: 110, y: 100, vx: -1, vy: 0 }
    const [ra, rb] = resolveBallCollision(a, b)
    expect(ra.vx !== a.vx || rb.vx !== b.vx).toBe(true)
  })

  test('returns new balls (immutable)', () => {
    const a: Ball = { id: 1, x: 100, y: 100, vx: 2, vy: 0 }
    const b: Ball = { id: 2, x: 110, y: 100, vx: -2, vy: 0 }
    const [ra, rb] = resolveBallCollision(a, b)
    expect(ra).not.toBe(a)
    expect(rb).not.toBe(b)
  })

  test('preserves ball ids', () => {
    const a: Ball = { id: 42, x: 100, y: 100, vx: 2, vy: 0 }
    const b: Ball = { id: 99, x: 110, y: 100, vx: -2, vy: 0 }
    const [ra, rb] = resolveBallCollision(a, b)
    expect(ra.id).toBe(42)
    expect(rb.id).toBe(99)
  })

  test('does not resolve if balls are moving apart', () => {
    const a: Ball = { id: 1, x: 100, y: 100, vx: -2, vy: 0 }
    const b: Ball = { id: 2, x: 110, y: 100, vx: 2, vy: 0 }
    const [ra, rb] = resolveBallCollision(a, b)
    // Should return unchanged balls
    expect(ra).toBe(a)
    expect(rb).toBe(b)
  })
})

describe('getSlotIndex', () => {
  test('maps center x to middle slot', () => {
    const idx = getSlotIndex(BOARD_WIDTH / 2, BOARD_WIDTH)
    expect(idx).toBe(6) // middle of 0-12
  })

  test('maps leftmost x to slot 0', () => {
    const idx = getSlotIndex(0, BOARD_WIDTH)
    expect(idx).toBe(0)
  })

  test('maps rightmost x to last slot', () => {
    const idx = getSlotIndex(BOARD_WIDTH, BOARD_WIDTH)
    expect(idx).toBe(SLOT_COUNT - 1)
  })

  test('clamps out-of-bounds to 0 or max', () => {
    expect(getSlotIndex(-50, BOARD_WIDTH)).toBe(0)
    expect(getSlotIndex(BOARD_WIDTH + 100, BOARD_WIDTH)).toBe(SLOT_COUNT - 1)
  })
})

describe('getDropPositions', () => {
  test('returns array of given count', () => {
    const positions = getDropPositions(5)
    expect(positions.length).toBe(5)
  })

  test('all positions are positive', () => {
    const positions = getDropPositions(5)
    for (const pos of positions) {
      expect(pos).toBeGreaterThan(0)
    }
  })

  test('positions are evenly spaced', () => {
    const positions = getDropPositions(5)
    const diffs: number[] = []
    for (let i = 1; i < positions.length; i++) {
      diffs.push(positions[i] - positions[i - 1])
    }
    // All diffs should be roughly equal
    for (const d of diffs) {
      expect(d).toBeCloseTo(diffs[0], 1)
    }
  })
})

describe('constants', () => {
  test('GRAVITY is 0.15', () => expect(GRAVITY).toBe(0.15))
  test('RESTITUTION is 0.75', () => expect(RESTITUTION).toBe(0.75))
  test('DAMPING is 0.85', () => expect(DAMPING).toBe(0.85))
  test('PEG_RADIUS is 5', () => expect(PEG_RADIUS).toBe(5))
  test('BALL_RADIUS is 8', () => expect(BALL_RADIUS).toBe(8))
  test('PEG_ROWS is 10', () => expect(PEG_ROWS).toBe(10))
  test('BOARD_WIDTH is 400', () => expect(BOARD_WIDTH).toBe(400))
  test('BOARD_HEIGHT is 500', () => expect(BOARD_HEIGHT).toBe(500))
  test('SLOT_COUNT is 13', () => expect(SLOT_COUNT).toBe(13))
})
