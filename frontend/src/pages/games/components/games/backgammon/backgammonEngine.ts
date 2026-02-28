// ── Types ──────────────────────────────────────────────────────────────

export type Player = 'white' | 'brown'

export interface Point {
  count: number
  player: Player | null
}

export interface BackgammonState {
  points: Point[]       // 24 points, index 0-23
  bar: { white: number; brown: number }
  borneOff: { white: number; brown: number }
  dice: number[]
  usedDice: boolean[]
  currentPlayer: Player
  gamePhase: 'rolling' | 'moving' | 'gameOver'
}

// ── Board Setup ────────────────────────────────────────────────────────

export function createBoard(): BackgammonState {
  const points: Point[] = Array.from({ length: 24 }, () => ({ count: 0, player: null }))

  // White: moves 23→0, bears off at 0 side
  points[0] = { count: 2, player: 'white' }
  points[11] = { count: 5, player: 'white' }
  points[16] = { count: 3, player: 'white' }
  points[18] = { count: 5, player: 'white' }

  // Brown: moves 0→23, bears off at 23 side
  points[5] = { count: 5, player: 'brown' }
  points[7] = { count: 3, player: 'brown' }
  points[12] = { count: 5, player: 'brown' }
  points[23] = { count: 2, player: 'brown' }

  return {
    points,
    bar: { white: 0, brown: 0 },
    borneOff: { white: 0, brown: 0 },
    dice: [],
    usedDice: [],
    currentPlayer: 'white',
    gamePhase: 'rolling',
  }
}

// ── Dice ───────────────────────────────────────────────────────────────

export function rollDice(): number[] {
  const d1 = Math.floor(Math.random() * 6) + 1
  const d2 = Math.floor(Math.random() * 6) + 1
  if (d1 === d2) return [d1, d1, d1, d1]
  return [d1, d2]
}

// ── Helpers ────────────────────────────────────────────────────────────

export function canBearOff(state: BackgammonState, player: Player): boolean {
  if (state.bar[player] > 0) return false

  if (player === 'white') {
    // White home: points 0-5
    for (let i = 6; i < 24; i++) {
      if (state.points[i].player === 'white' && state.points[i].count > 0) return false
    }
  } else {
    // Brown home: points 18-23
    for (let i = 0; i < 18; i++) {
      if (state.points[i].player === 'brown' && state.points[i].count > 0) return false
    }
  }
  return true
}

function isBlocked(point: Point, player: Player): boolean {
  return point.player !== null && point.player !== player && point.count >= 2
}

// ── Valid Moves ────────────────────────────────────────────────────────

export function getValidMoves(
  state: BackgammonState,
  dieValue: number,
): { from: number | 'bar'; to: number | 'off' }[] {
  const player = state.currentPlayer
  const moves: { from: number | 'bar'; to: number | 'off' }[] = []

  // If player has checkers on bar, must enter first
  if (state.bar[player] > 0) {
    let entryPoint: number
    if (player === 'white') {
      entryPoint = 24 - dieValue // white enters at 24-die (opponent's home)
    } else {
      entryPoint = dieValue - 1 // brown enters at die-1
    }

    if (entryPoint >= 0 && entryPoint <= 23 && !isBlocked(state.points[entryPoint], player)) {
      moves.push({ from: 'bar', to: entryPoint })
    }
    return moves // Must enter from bar first
  }

  const bearingOff = canBearOff(state, player)

  for (let i = 0; i < 24; i++) {
    const pt = state.points[i]
    if (pt.player !== player || pt.count === 0) continue

    let target: number
    if (player === 'white') {
      target = i - dieValue // white moves high→low
    } else {
      target = i + dieValue // brown moves low→high
    }

    // Check bearing off
    if (player === 'white' && target < 0) {
      if (!bearingOff) continue
      // Exact bear off: target < 0
      if (target === -1 * dieValue + i) {
        // Check if we need exact die or can use higher die
        // Can always bear off if die takes us past 0
        // But with higher die, must be no checkers on higher points
        if (target < -1) {
          // Higher die than needed — only allowed if no checkers on higher points
          let hasHigher = false
          for (let j = i + 1; j <= 5; j++) {
            if (state.points[j].player === 'white' && state.points[j].count > 0) {
              hasHigher = true
              break
            }
          }
          if (hasHigher) continue
        }
        moves.push({ from: i, to: 'off' })
      }
      continue
    }

    if (player === 'brown' && target > 23) {
      if (!bearingOff) continue
      if (target > 24) {
        // Higher die — only allowed if no checkers on lower points (further from home)
        let hasLower = false
        for (let j = i - 1; j >= 18; j--) {
          if (state.points[j].player === 'brown' && state.points[j].count > 0) {
            hasLower = true
            break
          }
        }
        if (hasLower) continue
      }
      moves.push({ from: i, to: 'off' })
      continue
    }

    // Normal move — check target is on board and not blocked
    if (target >= 0 && target <= 23 && !isBlocked(state.points[target], player)) {
      moves.push({ from: i, to: target })
    }
  }

  return moves
}

// ── Apply Move ─────────────────────────────────────────────────────────

export function applyMove(
  state: BackgammonState,
  from: number | 'bar',
  to: number | 'off',
  dieIndex: number,
): BackgammonState {
  const points = state.points.map(p => ({ ...p }))
  const bar = { ...state.bar }
  const borneOff = { ...state.borneOff }
  const usedDice = [...state.usedDice]
  const player = state.currentPlayer

  // Remove checker from source
  if (from === 'bar') {
    bar[player]--
  } else {
    points[from] = { ...points[from], count: points[from].count - 1 }
    if (points[from].count === 0) {
      points[from] = { count: 0, player: null }
    }
  }

  // Place checker at destination
  if (to === 'off') {
    borneOff[player]++
  } else {
    const target = points[to]
    const opponent: Player = player === 'white' ? 'brown' : 'white'

    // Hit opponent blot
    if (target.player === opponent && target.count === 1) {
      bar[opponent]++
      points[to] = { count: 1, player }
    } else {
      points[to] = {
        count: (target.player === player ? target.count : 0) + 1,
        player,
      }
    }
  }

  usedDice[dieIndex] = true

  return {
    ...state,
    points,
    bar,
    borneOff,
    usedDice,
  }
}

// ── Has Valid Moves ────────────────────────────────────────────────────

export function hasValidMoves(state: BackgammonState): boolean {
  for (let i = 0; i < state.dice.length; i++) {
    if (state.usedDice[i]) continue
    const moves = getValidMoves(state, state.dice[i])
    if (moves.length > 0) return true
  }
  return false
}

// ── Check Win ──────────────────────────────────────────────────────────

export function checkWin(state: BackgammonState): Player | null {
  if (state.borneOff.white >= 15) return 'white'
  if (state.borneOff.brown >= 15) return 'brown'
  return null
}

// ── AI ─────────────────────────────────────────────────────────────────

export function getAIMove(
  state: BackgammonState,
): { from: number | 'bar'; to: number | 'off'; dieIndex: number } | null {
  // Collect all valid moves across unused dice
  const candidates: { from: number | 'bar'; to: number | 'off'; dieIndex: number; score: number }[] = []

  for (let i = 0; i < state.dice.length; i++) {
    if (state.usedDice[i]) continue
    const moves = getValidMoves(state, state.dice[i])
    for (const m of moves) {
      candidates.push({ ...m, dieIndex: i, score: scoreAIMove(state, m) })
    }
  }

  if (candidates.length === 0) return null

  // Sort by score descending, pick the best
  candidates.sort((a, b) => b.score - a.score)
  const { from, to, dieIndex } = candidates[0]
  return { from, to, dieIndex }
}

function scoreAIMove(
  state: BackgammonState,
  move: { from: number | 'bar'; to: number | 'off' },
): number {
  let score = 0
  const player = state.currentPlayer

  // 1. Entering from bar is top priority
  if (move.from === 'bar') score += 100

  // 2. Bearing off is great
  if (move.to === 'off') score += 80

  // 3. Hitting opponent blot
  if (typeof move.to === 'number') {
    const target = state.points[move.to]
    const opponent: Player = player === 'white' ? 'brown' : 'white'
    if (target.player === opponent && target.count === 1) {
      score += 50
    }

    // 4. Building a point (landing where we already have 1+ checker)
    if (target.player === player && target.count >= 1) {
      score += 30
    }
  }

  // 5. Avoid leaving blots (if source will become empty and there's only 1 checker)
  if (typeof move.from === 'number') {
    const src = state.points[move.from]
    if (src.count === 2) {
      // Moving leaves a blot — penalize slightly
      score -= 15
    }

    // 6. Advance toward home
    if (player === 'brown' && typeof move.to === 'number') {
      score += (move.to - move.from) // positive = advancing
    } else if (player === 'white' && typeof move.to === 'number') {
      score += (move.from - move.to) // positive = advancing toward 0
    }
  }

  return score
}
