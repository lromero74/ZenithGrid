/**
 * 2048 game engine — pure logic, no React.
 *
 * Handles board state, sliding, merging, random tile placement,
 * and win/loss detection.
 */

export type Board = number[][]
export type MoveDirection = 'left' | 'right' | 'up' | 'down'

export interface SlideResult {
  row: number[]
  score: number
}

export interface MoveResult {
  board: Board
  score: number
  moved: boolean
}

/** Create a blank 4x4 board. */
export function createBoard(): Board {
  return Array.from({ length: 4 }, () => Array(4).fill(0))
}

/** Slide a single row left, merging adjacent equal tiles. */
export function slideRow(row: number[]): SlideResult {
  // Compact: remove zeros
  const compact = row.filter(v => v !== 0)
  const result: number[] = []
  let score = 0

  let i = 0
  while (i < compact.length) {
    if (i + 1 < compact.length && compact[i] === compact[i + 1]) {
      const merged = compact[i] * 2
      result.push(merged)
      score += merged
      i += 2
    } else {
      result.push(compact[i])
      i += 1
    }
  }

  // Pad with zeros
  while (result.length < 4) result.push(0)

  return { row: result, score }
}

/** Deep-clone a board. */
function cloneBoard(board: Board): Board {
  return board.map(row => [...row])
}

/** Rotate board 90 degrees clockwise. */
function rotateRight(board: Board): Board {
  const n = board.length
  const rotated = createBoard()
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      rotated[c][n - 1 - r] = board[r][c]
    }
  }
  return rotated
}

/** Rotate board 90 degrees counter-clockwise. */
function rotateLeft(board: Board): Board {
  const n = board.length
  const rotated = createBoard()
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      rotated[n - 1 - c][r] = board[r][c]
    }
  }
  return rotated
}

/** Move all tiles in a direction, returning new board + score + whether anything moved. */
export function move(board: Board, direction: MoveDirection): MoveResult {
  let working = cloneBoard(board)
  let totalScore = 0

  // Transform so we always slide left
  if (direction === 'right') {
    working = working.map(row => [...row].reverse())
  } else if (direction === 'up') {
    working = rotateLeft(working)
  } else if (direction === 'down') {
    working = rotateRight(working)
  }

  // Slide all rows left
  for (let r = 0; r < 4; r++) {
    const { row, score } = slideRow(working[r])
    working[r] = row
    totalScore += score
  }

  // Undo transform
  if (direction === 'right') {
    working = working.map(row => [...row].reverse())
  } else if (direction === 'up') {
    working = rotateRight(working)
  } else if (direction === 'down') {
    working = rotateLeft(working)
  }

  // Check if anything actually moved
  const moved = board.some((row, r) =>
    row.some((cell, c) => cell !== working[r][c])
  )

  return { board: working, score: totalScore, moved }
}

/** Add a random tile (90% = 2, 10% = 4) to a random empty cell. */
export function addRandomTile(board: Board): Board {
  const empties: [number, number][] = []
  for (let r = 0; r < 4; r++) {
    for (let c = 0; c < 4; c++) {
      if (board[r][c] === 0) empties.push([r, c])
    }
  }
  if (empties.length === 0) return board

  const result = cloneBoard(board)
  const [row, col] = empties[Math.floor(Math.random() * empties.length)]
  result[row][col] = Math.random() < 0.9 ? 2 : 4
  return result
}

/** Check if any valid moves remain. */
export function hasValidMoves(board: Board): boolean {
  for (let r = 0; r < 4; r++) {
    for (let c = 0; c < 4; c++) {
      if (board[r][c] === 0) return true
      // Check right neighbor
      if (c < 3 && board[r][c] === board[r][c + 1]) return true
      // Check bottom neighbor
      if (r < 3 && board[r][c] === board[r + 1][c]) return true
    }
  }
  return false
}

/** Check if any tile has reached 2048. */
export function isGameWon(board: Board): boolean {
  return board.some(row => row.some(cell => cell >= 2048))
}

/** Count empty cells on the board. */
export function countEmpty(board: Board): number {
  return board.flat().filter(v => v === 0).length
}
