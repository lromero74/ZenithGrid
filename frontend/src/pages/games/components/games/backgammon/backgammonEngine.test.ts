import { describe, test, expect } from 'vitest'
import {
  createBoard,
  rollDice,
  getValidMoves,
  applyMove,
  canBearOff,
  hasValidMoves,
  checkWin,
  getAIMove,
  type BackgammonState,
  type Player,
  type Point,
} from './backgammonEngine'

// ── helpers ────────────────────────────────────────────────────────────

function emptyState(currentPlayer: Player = 'white'): BackgammonState {
  const points: Point[] = Array.from({ length: 24 }, () => ({ count: 0, player: null }))
  return {
    points,
    bar: { white: 0, brown: 0 },
    borneOff: { white: 0, brown: 0 },
    dice: [],
    usedDice: [],
    currentPlayer,
    gamePhase: 'moving',
  }
}

function placeCheckers(
  state: BackgammonState,
  placements: { point: number; count: number; player: Player }[],
): BackgammonState {
  const points = state.points.map(p => ({ ...p }))
  for (const { point, count, player } of placements) {
    points[point] = { count, player }
  }
  return { ...state, points }
}

// ── createBoard ────────────────────────────────────────────────────────

describe('createBoard', () => {
  test('returns standard starting positions', () => {
    const state = createBoard()

    // White checkers
    expect(state.points[0]).toEqual({ count: 2, player: 'white' })
    expect(state.points[11]).toEqual({ count: 5, player: 'white' })
    expect(state.points[16]).toEqual({ count: 3, player: 'white' })
    expect(state.points[18]).toEqual({ count: 5, player: 'white' })

    // Brown checkers
    expect(state.points[5]).toEqual({ count: 5, player: 'brown' })
    expect(state.points[7]).toEqual({ count: 3, player: 'brown' })
    expect(state.points[12]).toEqual({ count: 5, player: 'brown' })
    expect(state.points[23]).toEqual({ count: 2, player: 'brown' })
  })

  test('each player has exactly 15 checkers on the board', () => {
    const state = createBoard()
    let white = 0
    let brown = 0
    for (const pt of state.points) {
      if (pt.player === 'white') white += pt.count
      if (pt.player === 'brown') brown += pt.count
    }
    expect(white).toBe(15)
    expect(brown).toBe(15)
  })

  test('white starts and phase is rolling', () => {
    const state = createBoard()
    expect(state.currentPlayer).toBe('white')
    expect(state.gamePhase).toBe('rolling')
  })

  test('bar and borneOff start at zero', () => {
    const state = createBoard()
    expect(state.bar).toEqual({ white: 0, brown: 0 })
    expect(state.borneOff).toEqual({ white: 0, brown: 0 })
  })

  test('dice start empty', () => {
    const state = createBoard()
    expect(state.dice).toEqual([])
    expect(state.usedDice).toEqual([])
  })

  test('empty points have count 0 and null player', () => {
    const state = createBoard()
    const occupiedIndices = [0, 5, 7, 11, 12, 16, 18, 23]
    for (let i = 0; i < 24; i++) {
      if (!occupiedIndices.includes(i)) {
        expect(state.points[i]).toEqual({ count: 0, player: null })
      }
    }
  })
})

// ── rollDice ───────────────────────────────────────────────────────────

describe('rollDice', () => {
  test('returns exactly 2 values for non-doubles', () => {
    // Roll many times to verify structure
    for (let i = 0; i < 100; i++) {
      const result = rollDice()
      if (result[0] !== result[1]) {
        expect(result).toHaveLength(2)
      }
    }
  })

  test('returns 4 values for doubles', () => {
    for (let i = 0; i < 1000; i++) {
      const result = rollDice()
      if (result[0] === result[1]) {
        expect(result).toHaveLength(4)
        expect(result[2]).toBe(result[0])
        expect(result[3]).toBe(result[0])
        return // found a double, test passes
      }
    }
    // Extremely unlikely (1 - (5/6)^1000 ~ 1) but safeguard
    expect(true).toBe(true)
  })

  test('all values are between 1 and 6', () => {
    for (let i = 0; i < 100; i++) {
      const result = rollDice()
      for (const v of result) {
        expect(v).toBeGreaterThanOrEqual(1)
        expect(v).toBeLessThanOrEqual(6)
      }
    }
  })
})

// ── getValidMoves ──────────────────────────────────────────────────────

describe('getValidMoves', () => {
  describe('normal moves', () => {
    test('white moves from higher to lower index', () => {
      const state = placeCheckers(emptyState('white'), [
        { point: 10, count: 2, player: 'white' },
      ])
      state.dice = [3]
      state.usedDice = [false]

      const moves = getValidMoves(state, 3)
      expect(moves).toContainEqual({ from: 10, to: 7 })
    })

    test('brown moves from lower to higher index', () => {
      const state = placeCheckers(emptyState('brown'), [
        { point: 10, count: 2, player: 'brown' },
      ])
      state.dice = [4]
      state.usedDice = [false]

      const moves = getValidMoves(state, 4)
      expect(moves).toContainEqual({ from: 10, to: 14 })
    })

    test('cannot land on point with 2+ opponent checkers', () => {
      const state = placeCheckers(emptyState('white'), [
        { point: 10, count: 1, player: 'white' },
        { point: 7, count: 2, player: 'brown' },
      ])
      state.dice = [3]
      state.usedDice = [false]

      const moves = getValidMoves(state, 3)
      expect(moves).not.toContainEqual({ from: 10, to: 7 })
    })

    test('can hit a single opponent checker (blot)', () => {
      const state = placeCheckers(emptyState('white'), [
        { point: 10, count: 1, player: 'white' },
        { point: 7, count: 1, player: 'brown' },
      ])
      state.dice = [3]
      state.usedDice = [false]

      const moves = getValidMoves(state, 3)
      expect(moves).toContainEqual({ from: 10, to: 7 })
    })

    test('can land on own occupied point', () => {
      const state = placeCheckers(emptyState('white'), [
        { point: 10, count: 2, player: 'white' },
        { point: 7, count: 3, player: 'white' },
      ])
      state.dice = [3]
      state.usedDice = [false]

      const moves = getValidMoves(state, 3)
      expect(moves).toContainEqual({ from: 10, to: 7 })
    })

    test('cannot move off the board without bearing off', () => {
      const state = placeCheckers(emptyState('white'), [
        { point: 2, count: 1, player: 'white' },
        { point: 10, count: 14, player: 'white' }, // not all in home
      ])
      state.dice = [5]
      state.usedDice = [false]

      const moves = getValidMoves(state, 5)
      // point 2 - 5 = -3, can't bear off since not all in home
      expect(moves).not.toContainEqual(expect.objectContaining({ from: 2, to: 'off' }))
    })

    test('white cannot move beyond point 0 without bearing off', () => {
      // White at point 1, die 5 — can't bear off since not all in home
      const state = placeCheckers(emptyState('white'), [
        { point: 1, count: 1, player: 'white' },
        { point: 20, count: 14, player: 'white' }, // not all in home
      ])
      state.dice = [5]
      state.usedDice = [false]

      const moves = getValidMoves(state, 5)
      // point 1 can't bear off (not all in home), but point 20→15 is valid
      expect(moves).not.toContainEqual(expect.objectContaining({ from: 1 }))
      expect(moves).toContainEqual({ from: 20, to: 15 })
    })
  })

  describe('bar entry', () => {
    test('white must enter from bar before making other moves', () => {
      const state = placeCheckers(emptyState('white'), [
        { point: 10, count: 2, player: 'white' },
      ])
      state.bar = { white: 1, brown: 0 }
      state.dice = [3]
      state.usedDice = [false]

      const moves = getValidMoves(state, 3)
      // White enters at 24 - die = 24 - 3 = 21
      expect(moves).toContainEqual({ from: 'bar', to: 21 })
      // Should NOT allow moving from board while on bar
      expect(moves).not.toContainEqual(expect.objectContaining({ from: 10 }))
    })

    test('brown enters from bar at die - 1', () => {
      const state = placeCheckers(emptyState('brown'), [
        { point: 10, count: 2, player: 'brown' },
      ])
      state.bar = { white: 0, brown: 1 }
      state.dice = [4]
      state.usedDice = [false]

      const moves = getValidMoves(state, 4)
      // Brown enters at die - 1 = 3
      expect(moves).toContainEqual({ from: 'bar', to: 3 })
      expect(moves).not.toContainEqual(expect.objectContaining({ from: 10 }))
    })

    test('cannot enter bar if entry point is blocked', () => {
      const state = placeCheckers(emptyState('white'), [
        { point: 21, count: 3, player: 'brown' }, // blocks white entry with die 3
      ])
      state.bar = { white: 1, brown: 0 }
      state.dice = [3]
      state.usedDice = [false]

      const moves = getValidMoves(state, 3)
      expect(moves).toEqual([])
    })

    test('can enter bar by hitting a blot', () => {
      const state = placeCheckers(emptyState('white'), [
        { point: 21, count: 1, player: 'brown' }, // blot at entry point
      ])
      state.bar = { white: 1, brown: 0 }
      state.dice = [3]
      state.usedDice = [false]

      const moves = getValidMoves(state, 3)
      expect(moves).toContainEqual({ from: 'bar', to: 21 })
    })
  })

  describe('bearing off', () => {
    test('can bear off with exact die when all in home', () => {
      const state = placeCheckers(emptyState('white'), [
        { point: 3, count: 5, player: 'white' },
        { point: 2, count: 5, player: 'white' },
        { point: 1, count: 5, player: 'white' },
      ])
      state.dice = [3]
      state.usedDice = [false]

      // White home: 0-5. Point 3 with die 3 → exact bear off (3-3=0 → off, wait.
      // Actually for white: to = from - die. Point 3 - 3 = 0, which is still on the board.
      // Bearing off: point - die < 0, i.e., from = 2, die = 3 → 2-3 = -1 → off
      // Let me use die = 4 to bear off from point 3: 3-4 = -1 → off
      const moves2 = getValidMoves(
        { ...state, dice: [4], usedDice: [false] },
        4,
      )
      expect(moves2).toContainEqual({ from: 3, to: 'off' })
    })

    test('can bear off with exact die value', () => {
      // White at point 2 with die 3 → 2-3 = -1 → bear off
      // But also: point 3 with die 4 → 3-4 = -1 → bear off
      // Let's test: point 4 with die 5 → 4-5 = -1 → bear off
      const state = placeCheckers(emptyState('white'), [
        { point: 4, count: 15, player: 'white' },
      ])
      state.dice = [5]
      state.usedDice = [false]

      const moves = getValidMoves(state, 5)
      expect(moves).toContainEqual({ from: 4, to: 'off' })
    })

    test('can bear off with higher die when no checkers behind', () => {
      // White has checker on point 2 only, die = 6. No checkers on 3,4,5.
      // Can bear off the checker from 2 with die 6.
      const state = placeCheckers(emptyState('white'), [
        { point: 2, count: 5, player: 'white' },
        { point: 1, count: 5, player: 'white' },
        { point: 0, count: 5, player: 'white' },
      ])
      state.dice = [6]
      state.usedDice = [false]

      const moves = getValidMoves(state, 6)
      // Die 6 can bear off from point 5 (exact), but no one's there.
      // Next: highest occupied point with die > point+1 → point 2, die 6 > 3 → bear off
      expect(moves).toContainEqual({ from: 2, to: 'off' })
    })

    test('cannot bear off with higher die when checkers behind', () => {
      // White on point 2, point 4, and point 0. Die = 5.
      // Die 5 from point 2: 2-5=-3 → higher die (needs 3 but got 5).
      // Can't bear off from point 2 with die 5 because point 4 is behind (higher index).
      // CAN move point 4 → 4-5=-1 → exact bear off (point 4 needs die 5).
      const state = placeCheckers(emptyState('white'), [
        { point: 2, count: 5, player: 'white' },
        { point: 4, count: 5, player: 'white' },
        { point: 0, count: 5, player: 'white' },
      ])
      state.dice = [5]
      state.usedDice = [false]

      const moves = getValidMoves(state, 5)
      // Die 5 from point 2 is higher than needed (needs 3), checkers on 4 behind → blocked
      expect(moves).not.toContainEqual({ from: 2, to: 'off' })
      // Die 5 from point 4 is exact (4+1=5) → allowed
      expect(moves).toContainEqual({ from: 4, to: 'off' })
    })

    test('cannot bear off when not all checkers in home', () => {
      const state = placeCheckers(emptyState('white'), [
        { point: 3, count: 10, player: 'white' },
        { point: 10, count: 5, player: 'white' }, // outside home
      ])
      state.dice = [4]
      state.usedDice = [false]

      const moves = getValidMoves(state, 4)
      expect(moves).not.toContainEqual(expect.objectContaining({ to: 'off' }))
    })

    test('brown bears off at the 23 side', () => {
      // Brown home is 18-23. Brown moves low→high. Bear off when to > 23.
      const state = placeCheckers(emptyState('brown'), [
        { point: 20, count: 5, player: 'brown' },
        { point: 21, count: 5, player: 'brown' },
        { point: 22, count: 5, player: 'brown' },
      ])
      state.dice = [4]
      state.usedDice = [false]

      const moves = getValidMoves(state, 4)
      // Point 20 + 4 = 24 > 23 → bear off
      expect(moves).toContainEqual({ from: 20, to: 'off' })
    })
  })
})

// ── applyMove ──────────────────────────────────────────────────────────

describe('applyMove', () => {
  test('moves checker from one point to another', () => {
    const state = placeCheckers(emptyState('white'), [
      { point: 10, count: 3, player: 'white' },
    ])
    state.dice = [4, 2]
    state.usedDice = [false, false]

    const next = applyMove(state, 10, 6, 0)
    expect(next.points[10].count).toBe(2)
    expect(next.points[6].count).toBe(1)
    expect(next.points[6].player).toBe('white')
  })

  test('marks the die as used', () => {
    const state = placeCheckers(emptyState('white'), [
      { point: 10, count: 3, player: 'white' },
    ])
    state.dice = [4, 2]
    state.usedDice = [false, false]

    const next = applyMove(state, 10, 6, 0)
    expect(next.usedDice[0]).toBe(true)
    expect(next.usedDice[1]).toBe(false)
  })

  test('hitting sends opponent to bar', () => {
    const state = placeCheckers(emptyState('white'), [
      { point: 10, count: 1, player: 'white' },
      { point: 7, count: 1, player: 'brown' }, // blot
    ])
    state.dice = [3, 2]
    state.usedDice = [false, false]

    const next = applyMove(state, 10, 7, 0)
    expect(next.points[7]).toEqual({ count: 1, player: 'white' })
    expect(next.bar.brown).toBe(1)
  })

  test('bearing off increments borneOff count', () => {
    const state = placeCheckers(emptyState('white'), [
      { point: 3, count: 15, player: 'white' },
    ])
    state.dice = [4]
    state.usedDice = [false]

    const next = applyMove(state, 3, 'off', 0)
    expect(next.borneOff.white).toBe(1)
    expect(next.points[3].count).toBe(14)
  })

  test('entering from bar decreases bar count', () => {
    const state = placeCheckers(emptyState('white'), [])
    state.bar = { white: 2, brown: 0 }
    state.dice = [3, 5]
    state.usedDice = [false, false]

    const next = applyMove(state, 'bar', 21, 0)
    expect(next.bar.white).toBe(1)
    expect(next.points[21].count).toBe(1)
    expect(next.points[21].player).toBe('white')
  })

  test('is immutable — original state not modified', () => {
    const state = placeCheckers(emptyState('white'), [
      { point: 10, count: 3, player: 'white' },
    ])
    state.dice = [4, 2]
    state.usedDice = [false, false]

    const origPoints10 = state.points[10].count
    applyMove(state, 10, 6, 0)
    expect(state.points[10].count).toBe(origPoints10)
    expect(state.usedDice[0]).toBe(false)
  })

  test('brown entering from bar', () => {
    const state = placeCheckers(emptyState('brown'), [])
    state.bar = { white: 0, brown: 1 }
    state.dice = [2, 5]
    state.usedDice = [false, false]

    const next = applyMove(state, 'bar', 1, 0)
    expect(next.bar.brown).toBe(0)
    expect(next.points[1].count).toBe(1)
    expect(next.points[1].player).toBe('brown')
  })

  test('point becomes empty when last checker leaves', () => {
    const state = placeCheckers(emptyState('white'), [
      { point: 10, count: 1, player: 'white' },
    ])
    state.dice = [3]
    state.usedDice = [false]

    const next = applyMove(state, 10, 7, 0)
    expect(next.points[10].count).toBe(0)
    expect(next.points[10].player).toBeNull()
  })
})

// ── canBearOff ─────────────────────────────────────────────────────────

describe('canBearOff', () => {
  test('returns true when all white checkers in home (0-5)', () => {
    const state = placeCheckers(emptyState('white'), [
      { point: 0, count: 5, player: 'white' },
      { point: 3, count: 5, player: 'white' },
      { point: 5, count: 5, player: 'white' },
    ])
    expect(canBearOff(state, 'white')).toBe(true)
  })

  test('returns true when some already borne off', () => {
    const state = placeCheckers(emptyState('white'), [
      { point: 0, count: 5, player: 'white' },
      { point: 3, count: 5, player: 'white' },
    ])
    state.borneOff = { white: 5, brown: 0 }
    expect(canBearOff(state, 'white')).toBe(true)
  })

  test('returns false when white checker outside home', () => {
    const state = placeCheckers(emptyState('white'), [
      { point: 0, count: 5, player: 'white' },
      { point: 3, count: 5, player: 'white' },
      { point: 10, count: 5, player: 'white' }, // outside home
    ])
    expect(canBearOff(state, 'white')).toBe(false)
  })

  test('returns false when white has checkers on bar', () => {
    const state = placeCheckers(emptyState('white'), [
      { point: 0, count: 5, player: 'white' },
      { point: 3, count: 5, player: 'white' },
      { point: 5, count: 4, player: 'white' },
    ])
    state.bar = { white: 1, brown: 0 }
    expect(canBearOff(state, 'white')).toBe(false)
  })

  test('returns true when all brown checkers in home (18-23)', () => {
    const state = placeCheckers(emptyState('brown'), [
      { point: 18, count: 5, player: 'brown' },
      { point: 20, count: 5, player: 'brown' },
      { point: 23, count: 5, player: 'brown' },
    ])
    expect(canBearOff(state, 'brown')).toBe(true)
  })

  test('returns false when brown has checker outside home', () => {
    const state = placeCheckers(emptyState('brown'), [
      { point: 18, count: 5, player: 'brown' },
      { point: 10, count: 5, player: 'brown' }, // outside
      { point: 23, count: 5, player: 'brown' },
    ])
    expect(canBearOff(state, 'brown')).toBe(false)
  })
})

// ── checkWin ───────────────────────────────────────────────────────────

describe('checkWin', () => {
  test('white wins with 15 borne off', () => {
    const state = emptyState()
    state.borneOff = { white: 15, brown: 0 }
    expect(checkWin(state)).toBe('white')
  })

  test('brown wins with 15 borne off', () => {
    const state = emptyState()
    state.borneOff = { white: 0, brown: 15 }
    expect(checkWin(state)).toBe('brown')
  })

  test('returns null when no one has 15 borne off', () => {
    const state = emptyState()
    state.borneOff = { white: 10, brown: 12 }
    expect(checkWin(state)).toBeNull()
  })

  test('returns null at game start', () => {
    const state = createBoard()
    expect(checkWin(state)).toBeNull()
  })
})

// ── hasValidMoves ──────────────────────────────────────────────────────

describe('hasValidMoves', () => {
  test('returns true when moves are available', () => {
    const state = placeCheckers(emptyState('white'), [
      { point: 10, count: 2, player: 'white' },
    ])
    state.dice = [3, 4]
    state.usedDice = [false, false]

    expect(hasValidMoves(state)).toBe(true)
  })

  test('returns false when all dice are used', () => {
    const state = placeCheckers(emptyState('white'), [
      { point: 10, count: 2, player: 'white' },
    ])
    state.dice = [3, 4]
    state.usedDice = [true, true]

    expect(hasValidMoves(state)).toBe(false)
  })

  test('returns false when completely blocked', () => {
    // White checker on point 6, all reachable points blocked by brown
    const state = placeCheckers(emptyState('white'), [
      { point: 6, count: 1, player: 'white' },
      { point: 5, count: 2, player: 'brown' },
      { point: 4, count: 2, player: 'brown' },
      { point: 3, count: 2, player: 'brown' },
      { point: 2, count: 2, player: 'brown' },
      { point: 1, count: 2, player: 'brown' },
      { point: 0, count: 2, player: 'brown' },
    ])
    state.dice = [1, 2]
    state.usedDice = [false, false]

    expect(hasValidMoves(state)).toBe(false)
  })

  test('returns false when on bar and all entry points blocked', () => {
    const state = placeCheckers(emptyState('white'), [
      { point: 23, count: 2, player: 'brown' },
      { point: 22, count: 2, player: 'brown' },
      { point: 21, count: 2, player: 'brown' },
      { point: 20, count: 2, player: 'brown' },
      { point: 19, count: 2, player: 'brown' },
      { point: 18, count: 2, player: 'brown' },
    ])
    state.bar = { white: 1, brown: 0 }
    state.dice = [1, 2]
    state.usedDice = [false, false]

    expect(hasValidMoves(state)).toBe(false)
  })
})

// ── getAIMove ──────────────────────────────────────────────────────────

describe('getAIMove', () => {
  test('returns null when no valid moves', () => {
    const state = placeCheckers(emptyState('brown'), [
      { point: 17, count: 1, player: 'brown' },
      { point: 18, count: 2, player: 'white' },
      { point: 19, count: 2, player: 'white' },
      { point: 20, count: 2, player: 'white' },
      { point: 21, count: 2, player: 'white' },
      { point: 22, count: 2, player: 'white' },
      { point: 23, count: 2, player: 'white' },
    ])
    state.dice = [1, 2]
    state.usedDice = [false, false]

    expect(getAIMove(state)).toBeNull()
  })

  test('prioritizes entering from bar', () => {
    const state = placeCheckers(emptyState('brown'), [
      { point: 10, count: 5, player: 'brown' },
    ])
    state.bar = { white: 0, brown: 1 }
    state.dice = [3, 5]
    state.usedDice = [false, false]

    const move = getAIMove(state)
    expect(move).not.toBeNull()
    expect(move!.from).toBe('bar')
  })

  test('returns a valid move', () => {
    const state = placeCheckers(emptyState('brown'), [
      { point: 10, count: 5, player: 'brown' },
      { point: 15, count: 5, player: 'brown' },
      { point: 20, count: 5, player: 'brown' },
    ])
    state.dice = [3, 5]
    state.usedDice = [false, false]

    const move = getAIMove(state)
    expect(move).not.toBeNull()

    // Verify the move is actually valid
    const allMoves: { from: number | 'bar'; to: number | 'off'; dieIndex: number }[] = []
    state.dice.forEach((die, idx) => {
      if (!state.usedDice[idx]) {
        const valid = getValidMoves(state, die)
        valid.forEach(m => allMoves.push({ ...m, dieIndex: idx }))
      }
    })
    expect(allMoves).toContainEqual(move)
  })
})

// ── edge cases ─────────────────────────────────────────────────────────

describe('edge cases', () => {
  test('multiple checkers on bar', () => {
    const state = placeCheckers(emptyState('white'), [])
    state.bar = { white: 3, brown: 0 }
    state.dice = [2, 5]
    state.usedDice = [false, false]

    const moves2 = getValidMoves(state, 2)
    expect(moves2).toContainEqual({ from: 'bar', to: 22 })

    const moves5 = getValidMoves(state, 5)
    expect(moves5).toContainEqual({ from: 'bar', to: 19 })
  })

  test('bearing off with exactly 0 checkers left results in win', () => {
    const state = placeCheckers(emptyState('white'), [
      { point: 0, count: 1, player: 'white' },
    ])
    state.borneOff = { white: 14, brown: 0 }
    state.dice = [1]
    state.usedDice = [false]

    // Bear off last checker
    const next = applyMove(state, 0, 'off', 0)
    expect(next.borneOff.white).toBe(15)
    expect(checkWin(next)).toBe('white')
  })

  test('hitting from bar entry', () => {
    const state = placeCheckers(emptyState('white'), [
      { point: 21, count: 1, player: 'brown' }, // blot at entry point
    ])
    state.bar = { white: 1, brown: 0 }
    state.dice = [3]
    state.usedDice = [false]

    const next = applyMove(state, 'bar', 21, 0)
    expect(next.bar.white).toBe(0)
    expect(next.bar.brown).toBe(1)
    expect(next.points[21]).toEqual({ count: 1, player: 'white' })
  })

  test('doubles provide 4 moves', () => {
    const state = placeCheckers(emptyState('white'), [
      { point: 20, count: 5, player: 'white' },
    ])
    state.dice = [3, 3, 3, 3]
    state.usedDice = [false, false, false, false]

    // Use first die
    let next = applyMove(state, 20, 17, 0)
    expect(next.usedDice).toEqual([true, false, false, false])

    // Use second die
    next = applyMove(next, 20, 17, 1)
    expect(next.usedDice).toEqual([true, true, false, false])

    // Use third die
    next = applyMove(next, 20, 17, 2)
    expect(next.usedDice).toEqual([true, true, true, false])

    // Use fourth die
    next = applyMove(next, 20, 17, 3)
    expect(next.usedDice).toEqual([true, true, true, true])
  })
})
