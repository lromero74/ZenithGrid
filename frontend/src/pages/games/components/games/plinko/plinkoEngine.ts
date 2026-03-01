/**
 * Plinko game physics engine — deterministic ball-drop simulation.
 *
 * Handles peg layout generation, ball physics, collision detection/resolution,
 * multiplier configuration, and slot mapping.
 */

export const GRAVITY = 0.075
export const RESTITUTION = 0.75
export const DAMPING = 0.85
export const PEG_RADIUS = 5
export const BALL_RADIUS = 8
export const PEG_ROWS = 10
export const BOARD_WIDTH = 400
export const BOARD_HEIGHT = 500
export const SLOT_COUNT = 13

export type RiskLevel = 'low' | 'medium' | 'high'
export type PegLayout = 'classic' | 'pyramid' | 'diamond'

export interface Peg {
  x: number
  y: number
  row: number
}

export interface Ball {
  id: number
  x: number
  y: number
  vx: number
  vy: number
}

let nextBallId = 1

const MULTIPLIERS: Record<RiskLevel, number[]> = {
  low:    [1.5, 1.2, 1.1, 1, 0.8, 0.5, 0.3, 0.5, 0.8, 1, 1.1, 1.2, 1.5],
  medium: [3, 2, 1.5, 1, 0.5, 0.3, 0.2, 0.3, 0.5, 1, 1.5, 2, 3],
  high:   [10, 5, 3, 1.5, 0.5, 0.3, 0.2, 0.3, 0.5, 1.5, 3, 5, 10],
}

/**
 * Generate a peg layout with the given style.
 *
 * Vertical spacing is calculated so the gap between the last peg row
 * and the separator row (at BOARD_HEIGHT - 5) equals the gap between
 * regular peg rows — i.e., PEG_ROWS intervals from startY to separatorY.
 *
 * - classic: Pegs aligned with slot positions — even rows have SLOT_COUNT pegs
 *   at slot centers, odd rows have SLOT_COUNT+1 pegs at slot boundaries
 *   (including edges at x=0 and x=BOARD_WIDTH to prevent edge sticking).
 *   Bottom row (row 9, odd) has boundary pegs; row 8 (even) has center pegs.
 * - pyramid: Fewer pegs at top, expanding toward bottom
 * - diamond: Wide in the middle, narrow at top and bottom
 */
export function generatePegLayout(layout: PegLayout = 'classic'): Peg[] {
  const pegs: Peg[] = []
  const startY = 60
  // Include separator row in spacing so all gaps are equal
  const separatorY = BOARD_HEIGHT - 5
  const rowSpacing = (separatorY - startY) / PEG_ROWS
  const margin = 30 // keep pegs away from edges

  if (layout === 'classic') {
    // Slot-aligned Plinko: pegs tied to slot geometry for proper ball routing.
    // Even rows: SLOT_COUNT pegs at slot centers.
    // Odd rows (including bottom row 9): SLOT_COUNT + 1 pegs at slot boundaries
    // (including edges at x=0 and x=BOARD_WIDTH to prevent edge sticking).
    // Half-slot-width offset between rows creates natural stagger.
    const slotWidth = BOARD_WIDTH / SLOT_COUNT

    for (let row = 0; row < PEG_ROWS; row++) {
      const y = startY + row * rowSpacing
      const isSlotCenterRow = row % 2 === 0

      if (isSlotCenterRow) {
        for (let i = 0; i < SLOT_COUNT; i++) {
          pegs.push({ x: slotWidth * (i + 0.5), y, row })
        }
      } else {
        for (let i = 0; i <= SLOT_COUNT; i++) {
          pegs.push({ x: slotWidth * i, y, row })
        }
      }
    }
  } else if (layout === 'pyramid') {
    // Pyramid: 3 pegs at top growing to 12 at bottom, centered.
    // +1 peg per row with consistent spacing creates natural stagger —
    // each row's pegs sit in the gaps of the row above.
    const maxPegs = 12
    const usableWidth = BOARD_WIDTH - margin * 2
    const spacing = usableWidth / (maxPegs - 1)
    const centerX = BOARD_WIDTH / 2

    for (let row = 0; row < PEG_ROWS; row++) {
      const pegCount = 3 + row
      const y = startY + row * rowSpacing

      for (let col = 0; col < pegCount; col++) {
        const x = centerX + (col - (pegCount - 1) / 2) * spacing
        pegs.push({ x, y, row })
      }
    }
  } else if (layout === 'diamond') {
    // Diamond: narrow top, wide middle, narrow bottom, centered.
    // +2 pegs per row doesn't create natural stagger, so odd rows
    // are offset by half a spacing (same technique as classic).
    const counts = [4, 6, 8, 10, 12, 12, 10, 8, 6, 4]
    const maxPegs = 12
    const usableWidth = BOARD_WIDTH - margin * 2
    const spacing = usableWidth / (maxPegs - 1)
    const centerX = BOARD_WIDTH / 2

    for (let row = 0; row < PEG_ROWS; row++) {
      const pegCount = counts[row]
      const isOffset = row % 2 === 1
      const offset = isOffset ? spacing / 2 : 0
      const y = startY + row * rowSpacing

      for (let col = 0; col < pegCount; col++) {
        const x = centerX + (col - (pegCount - 1) / 2) * spacing + offset
        pegs.push({ x, y, row })
      }
    }
  }

  return pegs
}

/**
 * Get multiplier array for a given risk level. Returns 13 symmetric values.
 */
export function getMultipliers(risk: RiskLevel): number[] {
  return MULTIPLIERS[risk]
}

/**
 * Create a new ball at the given x position, released just off the top of
 * the visible board with no velocity.  Gravity alone accelerates it down
 * into the pegs.
 */
export function createBall(dropX: number): Ball {
  return {
    id: nextBallId++,
    x: dropX,
    y: -BALL_RADIUS,
    vx: 0,
    vy: 0,
  }
}

/**
 * Apply one physics step: gravity accelerates vy, position updated by velocity.
 * Returns a new Ball (immutable).
 */
export function stepPhysics(ball: Ball): Ball {
  const vy = ball.vy + GRAVITY
  return {
    id: ball.id,
    x: ball.x + ball.vx,
    y: ball.y + vy,
    vx: ball.vx,
    vy,
  }
}

/**
 * Check if a ball overlaps a peg (euclidean distance <= sum of radii).
 */
export function checkPegCollision(ball: Ball, peg: Peg): boolean {
  const dx = ball.x - peg.x
  const dy = ball.y - peg.y
  const dist = Math.sqrt(dx * dx + dy * dy)
  return dist <= BALL_RADIUS + PEG_RADIUS
}

/**
 * Resolve a collision with reflection physics + Galton rotation.
 *
 * Restores the v2.70.5 approach that felt like real plinko: velocity is
 * reflected off the peg surface (real bounce), then rotated by a random
 * angle in a 50/50 coin-flip direction.  This couples lateral and vertical
 * motion naturally — faster impacts produce bigger bounces.
 *
 * The 50/50 direction preserves the binomial B(10, 0.5) bell-curve
 * distribution.  Minimum speed floors prevent the ball from dying at
 * lower rows (where cumulative restitution loss would otherwise kill it).
 *
 * Physics:
 * 1. Push ball outside peg (with clearance to prevent re-collision)
 * 2. Reflect velocity along collision normal (real bounce)
 * 3. Apply restitution + damping for energy loss
 * 4. Rotate reflected velocity by 50/50 random angle (9°–30°) for Galton spread
 * 5. Enforce minimum lateral speed (0.72) so the ball stays lively;
 *    gravity alone handles all downward acceleration
 */
export function resolveCollision(ball: Ball, peg: Peg): Ball {
  const dx = ball.x - peg.x
  const dy = ball.y - peg.y
  const dist = Math.sqrt(dx * dx + dy * dy) || 0.01
  const minDist = BALL_RADIUS + PEG_RADIUS

  // Normal vector from peg to ball
  const nx = dx / dist
  const ny = dy / dist

  // Push ball outside peg with clearance for bounce travel
  const newX = peg.x + nx * (minDist + 1)
  const newY = peg.y + ny * (minDist + 1)

  // Reflect velocity along collision normal, apply energy loss
  const dot = ball.vx * nx + ball.vy * ny
  const rvx = (ball.vx - 2 * dot * nx) * RESTITUTION * DAMPING
  const rvy = (ball.vy - 2 * dot * ny) * RESTITUTION * DAMPING

  // Galton rotation: 50/50 coin flip picks direction, random magnitude (9°–30°)
  // ensures meaningful lateral deflection at every peg — just like real plinko.
  const direction = Math.random() < 0.5 ? 1 : -1
  const angle = direction * (0.15 + Math.random() * 0.37)
  const cos = Math.cos(angle)
  const sin = Math.sin(angle)

  let vx = rvx * cos - rvy * sin
  let vy = rvx * sin + rvy * cos

  // Lateral speed floor: prevent the ball from losing all horizontal motion
  // due to cumulative energy loss across 10 rows.
  if (Math.abs(vx) < 0.72) {
    vx = direction * (0.72 + Math.random() * 0.36)
  }

  // If ball is above the peg, clamp any residual downward vy to zero.
  // The Galton rotation can swing the reflected (upward) velocity back
  // toward downward — gravity alone should handle all descent.
  if (newY < peg.y && vy > 0) {
    vy = 0
  }

  return {
    id: ball.id,
    x: newX,
    y: newY,
    vx,
    vy,
  }
}

/**
 * Map a ball's x position to a slot index (0 to SLOT_COUNT-1), clamped.
 */
export function getSlotIndex(ballX: number, boardWidth: number): number {
  const idx = Math.floor((ballX / boardWidth) * SLOT_COUNT)
  return Math.max(0, Math.min(SLOT_COUNT - 1, idx))
}

/**
 * Check if two balls overlap (distance < 2 × BALL_RADIUS).
 */
export function checkBallCollision(a: Ball, b: Ball): boolean {
  const dx = a.x - b.x
  const dy = a.y - b.y
  const dist = Math.sqrt(dx * dx + dy * dy)
  return dist < BALL_RADIUS * 2
}

/**
 * Resolve elastic collision between two balls.
 * Swaps velocity components along the collision normal.
 * Returns a tuple of [updatedA, updatedB].
 */
export function resolveBallCollision(a: Ball, b: Ball): [Ball, Ball] {
  const dx = a.x - b.x
  const dy = a.y - b.y
  const dist = Math.sqrt(dx * dx + dy * dy) || 0.01
  const minDist = BALL_RADIUS * 2

  // Normal vector from b to a
  const nx = dx / dist
  const ny = dy / dist

  // Relative velocity of a w.r.t. b along normal
  const dvx = a.vx - b.vx
  const dvy = a.vy - b.vy
  const relVelAlongNormal = dvx * nx + dvy * ny

  // Don't resolve if balls are moving apart
  if (relVelAlongNormal > 0) return [a, b]

  // Elastic collision (equal mass): swap normal velocity components
  const impulse = relVelAlongNormal

  // Push balls apart to avoid overlap
  const overlap = minDist - dist
  const pushX = (nx * overlap) / 2
  const pushY = (ny * overlap) / 2

  return [
    {
      id: a.id,
      x: a.x + pushX,
      y: a.y + pushY,
      vx: (a.vx - impulse * nx) * RESTITUTION,
      vy: (a.vy - impulse * ny) * RESTITUTION,
    },
    {
      id: b.id,
      x: b.x - pushX,
      y: b.y - pushY,
      vx: (b.vx + impulse * nx) * RESTITUTION,
      vy: (b.vy + impulse * ny) * RESTITUTION,
    },
  ]
}

/**
 * Generate evenly spaced drop positions across the top of the board.
 */
export function getDropPositions(count: number): number[] {
  const spacing = BOARD_WIDTH / (count + 1)
  const positions: number[] = []
  for (let i = 1; i <= count; i++) {
    positions.push(spacing * i)
  }
  return positions
}
