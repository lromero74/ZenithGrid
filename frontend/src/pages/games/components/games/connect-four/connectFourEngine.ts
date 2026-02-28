/**
 * Connect Four game engine — pure logic, no React.
 *
 * Handles board state, disc dropping, win detection,
 * and AI with minimax + alpha-beta pruning.
 */

export type Player = 'red' | 'yellow'
export type Cell = Player | null
export type Board = Cell[][]

export const ROWS = 6
export const COLS = 7

export interface WinResult {
  player: Player
  cells: [number, number][]
}

export interface DropResult {
  board: Board
  row: number // -1 if column is full
}

/** Create an empty 6x7 board. */
export function createBoard(): Board {
  return Array.from({ length: ROWS }, () => Array(COLS).fill(null))
}

/** Clone a board. */
function cloneBoard(board: Board): Board {
  return board.map(row => [...row])
}

/** Drop a disc into a column. Returns new board and the row it landed on. */
export function dropDisc(board: Board, col: number, player: Player): DropResult {
  const newBoard = cloneBoard(board)
  for (let r = ROWS - 1; r >= 0; r--) {
    if (newBoard[r][col] === null) {
      newBoard[r][col] = player
      return { board: newBoard, row: r }
    }
  }
  return { board: newBoard, row: -1 }
}

/** Check for a winner. Returns winning player and cells, or null. */
export function checkWinner(board: Board): WinResult | null {
  const directions = [
    [0, 1],  // horizontal
    [1, 0],  // vertical
    [1, 1],  // diagonal down-right
    [1, -1], // diagonal down-left
  ]

  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const player = board[r][c]
      if (!player) continue

      for (const [dr, dc] of directions) {
        const cells: [number, number][] = [[r, c]]
        let valid = true
        for (let i = 1; i < 4; i++) {
          const nr = r + dr * i
          const nc = c + dc * i
          if (nr < 0 || nr >= ROWS || nc < 0 || nc >= COLS || board[nr][nc] !== player) {
            valid = false
            break
          }
          cells.push([nr, nc])
        }
        if (valid) return { player, cells }
      }
    }
  }
  return null
}

/** Get columns that aren't full. */
export function getValidColumns(board: Board): number[] {
  const valid: number[] = []
  for (let c = 0; c < COLS; c++) {
    if (board[0][c] === null) valid.push(c)
  }
  return valid
}

/** Check if the board is completely full. */
export function isBoardFull(board: Board): boolean {
  return board[0].every(cell => cell !== null)
}

/** AI move using minimax with alpha-beta pruning. */
export function getAIMove(board: Board, aiPlayer: Player, depth: number): number {
  const opponent: Player = aiPlayer === 'red' ? 'yellow' : 'red'
  const validCols = getValidColumns(board)
  if (validCols.length === 0) return -1

  // Check immediate wins/blocks first
  for (const col of validCols) {
    const { board: b } = dropDisc(board, col, aiPlayer)
    if (checkWinner(b)) return col
  }
  for (const col of validCols) {
    const { board: b } = dropDisc(board, col, opponent)
    if (checkWinner(b)) return col
  }

  let bestScore = -Infinity
  let bestCol = validCols[Math.floor(validCols.length / 2)] // prefer center

  for (const col of validCols) {
    const { board: newBoard, row } = dropDisc(board, col, aiPlayer)
    if (row === -1) continue
    const score = minimax(newBoard, depth - 1, -Infinity, Infinity, false, aiPlayer)
    if (score > bestScore) {
      bestScore = score
      bestCol = col
    }
  }
  return bestCol
}

function minimax(
  board: Board, depth: number, alpha: number, beta: number,
  isMaximizing: boolean, aiPlayer: Player
): number {
  const winner = checkWinner(board)
  if (winner) return winner.player === aiPlayer ? 1000 + depth : -1000 - depth
  if (isBoardFull(board) || depth === 0) return evaluateBoard(board, aiPlayer)

  const validCols = getValidColumns(board)
  const player: Player = isMaximizing ? aiPlayer : (aiPlayer === 'red' ? 'yellow' : 'red')

  if (isMaximizing) {
    let maxEval = -Infinity
    for (const col of validCols) {
      const { board: newBoard, row } = dropDisc(board, col, player)
      if (row === -1) continue
      const eval_ = minimax(newBoard, depth - 1, alpha, beta, false, aiPlayer)
      maxEval = Math.max(maxEval, eval_)
      alpha = Math.max(alpha, eval_)
      if (beta <= alpha) break
    }
    return maxEval
  } else {
    let minEval = Infinity
    for (const col of validCols) {
      const { board: newBoard, row } = dropDisc(board, col, player)
      if (row === -1) continue
      const eval_ = minimax(newBoard, depth - 1, alpha, beta, true, aiPlayer)
      minEval = Math.min(minEval, eval_)
      beta = Math.min(beta, eval_)
      if (beta <= alpha) break
    }
    return minEval
  }
}

/** Heuristic board evaluation for non-terminal states. */
function evaluateBoard(board: Board, aiPlayer: Player): number {
  let score = 0
  const opponent: Player = aiPlayer === 'red' ? 'yellow' : 'red'

  // Score center column control
  for (let r = 0; r < ROWS; r++) {
    if (board[r][3] === aiPlayer) score += 3
    if (board[r][3] === opponent) score -= 3
  }

  // Score windows of 4
  const scoreWindow = (window: Cell[]) => {
    const ai = window.filter(c => c === aiPlayer).length
    const opp = window.filter(c => c === opponent).length
    const empty = window.filter(c => c === null).length

    if (ai === 3 && empty === 1) return 5
    if (ai === 2 && empty === 2) return 2
    if (opp === 3 && empty === 1) return -4
    return 0
  }

  // Horizontal
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c <= COLS - 4; c++) {
      score += scoreWindow([board[r][c], board[r][c+1], board[r][c+2], board[r][c+3]])
    }
  }
  // Vertical
  for (let r = 0; r <= ROWS - 4; r++) {
    for (let c = 0; c < COLS; c++) {
      score += scoreWindow([board[r][c], board[r+1][c], board[r+2][c], board[r+3][c]])
    }
  }
  // Diagonal down-right
  for (let r = 0; r <= ROWS - 4; r++) {
    for (let c = 0; c <= COLS - 4; c++) {
      score += scoreWindow([board[r][c], board[r+1][c+1], board[r+2][c+2], board[r+3][c+3]])
    }
  }
  // Diagonal down-left
  for (let r = 0; r <= ROWS - 4; r++) {
    for (let c = 3; c < COLS; c++) {
      score += scoreWindow([board[r][c], board[r+1][c-1], board[r+2][c-2], board[r+3][c-3]])
    }
  }

  return score
}
