/**
 * Tic-Tac-Toe game engine — pure functions, no React dependencies.
 *
 * Board is a flat array of 9 cells (indices 0-8):
 *   0 | 1 | 2
 *   ---------
 *   3 | 4 | 5
 *   ---------
 *   6 | 7 | 8
 */

export type Player = 'X' | 'O'
export type Cell = Player | null
export type Board = Cell[]
export type Difficulty = 'easy' | 'hard'

export interface WinResult {
  winner: Player
  line: [number, number, number]
}

const WIN_LINES: [number, number, number][] = [
  [0, 1, 2], [3, 4, 5], [6, 7, 8], // rows
  [0, 3, 6], [1, 4, 7], [2, 5, 8], // columns
  [0, 4, 8], [2, 4, 6],            // diagonals
]

export function createBoard(): Board {
  return Array(9).fill(null)
}

export function checkWinner(board: Board): WinResult | null {
  for (const line of WIN_LINES) {
    const [a, b, c] = line
    if (board[a] && board[a] === board[b] && board[a] === board[c]) {
      return { winner: board[a] as Player, line }
    }
  }
  return null
}

export function isBoardFull(board: Board): boolean {
  return board.every(cell => cell !== null)
}

function getEmptyCells(board: Board): number[] {
  return board.reduce<number[]>((acc, cell, i) => {
    if (cell === null) acc.push(i)
    return acc
  }, [])
}

function minimax(board: Board, isMaximizing: boolean, aiPlayer: Player, depth: number): number {
  const opponent: Player = aiPlayer === 'X' ? 'O' : 'X'
  const result = checkWinner(board)

  // Prefer faster wins (higher score) and slower losses (less negative)
  if (result) return result.winner === aiPlayer ? 10 - depth : depth - 10
  if (isBoardFull(board)) return 0

  const emptyCells = getEmptyCells(board)

  if (isMaximizing) {
    let best = -Infinity
    for (const i of emptyCells) {
      board[i] = aiPlayer
      best = Math.max(best, minimax(board, false, aiPlayer, depth + 1))
      board[i] = null
    }
    return best
  } else {
    let best = Infinity
    for (const i of emptyCells) {
      board[i] = opponent
      best = Math.min(best, minimax(board, true, aiPlayer, depth + 1))
      board[i] = null
    }
    return best
  }
}

export function getAIMove(board: Board, aiPlayer: Player, difficulty: Difficulty): number {
  const emptyCells = getEmptyCells(board)
  if (emptyCells.length === 0) return -1

  if (difficulty === 'easy') {
    return emptyCells[Math.floor(Math.random() * emptyCells.length)]
  }

  // Hard mode: minimax
  let bestScore = -Infinity
  let bestMove = emptyCells[0]

  for (const i of emptyCells) {
    board[i] = aiPlayer
    const score = minimax(board, false, aiPlayer, 0)
    board[i] = null
    if (score > bestScore) {
      bestScore = score
      bestMove = i
    }
  }

  return bestMove
}
