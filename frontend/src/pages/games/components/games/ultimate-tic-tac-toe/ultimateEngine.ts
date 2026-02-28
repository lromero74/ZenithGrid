/**
 * Ultimate Tic-Tac-Toe engine — pure logic, no React.
 *
 * Handles board state, move validation, sub-board/meta-board win
 * detection, and active board tracking.
 */

export type Player = 'X' | 'O'
export type CellValue = Player | null
export type SubBoard = CellValue[]
export type MetaCell = Player | 'draw' | null

const WIN_LINES = [
  [0, 1, 2], [3, 4, 5], [6, 7, 8], // rows
  [0, 3, 6], [1, 4, 7], [2, 5, 8], // cols
  [0, 4, 8], [2, 4, 6],            // diagonals
]

/** Create 9 empty sub-boards (each has 9 cells). */
export function createBoards(): SubBoard[] {
  return Array.from({ length: 9 }, () => Array(9).fill(null))
}

/** Create empty meta board. */
export function createMetaBoard(): MetaCell[] {
  return Array(9).fill(null)
}

/** Check if a sub-board has a winner or is drawn. */
export function checkSubBoardWinner(board: SubBoard): Player | 'draw' | null {
  for (const [a, b, c] of WIN_LINES) {
    if (board[a] && board[a] === board[b] && board[b] === board[c]) {
      return board[a] as Player
    }
  }
  if (board.every(cell => cell !== null)) return 'draw'
  return null
}

/** Check if the meta board has a winner. */
export function checkMetaWinner(meta: MetaCell[]): Player | null {
  for (const [a, b, c] of WIN_LINES) {
    if (meta[a] && meta[a] !== 'draw' && meta[a] === meta[b] && meta[b] === meta[c]) {
      return meta[a] as Player
    }
  }
  return null
}

/** Determine active board from last move's cell position. */
export function getActiveBoard(lastCellIndex: number | null): number | null {
  if (lastCellIndex === null) return null
  return lastCellIndex
}

/** Get all valid moves as [boardIndex, cellIndex] pairs. */
export function getValidMoves(
  boards: SubBoard[],
  meta: MetaCell[],
  activeBoard: number | null
): [number, number][] {
  const moves: [number, number][] = []

  if (activeBoard !== null && meta[activeBoard] === null) {
    // Must play in the active board
    for (let cell = 0; cell < 9; cell++) {
      if (boards[activeBoard][cell] === null) {
        moves.push([activeBoard, cell])
      }
    }
  } else {
    // Can play in any non-completed board
    for (let b = 0; b < 9; b++) {
      if (meta[b] !== null) continue
      for (let cell = 0; cell < 9; cell++) {
        if (boards[b][cell] === null) {
          moves.push([b, cell])
        }
      }
    }
  }

  return moves
}

interface MoveResult {
  boards: SubBoard[]
  meta: MetaCell[]
  nextActiveBoard: number | null
  winner: Player | null
  isDraw: boolean
}

/** Make a move and return updated state. */
export function makeMove(
  boards: SubBoard[],
  meta: MetaCell[],
  boardIndex: number,
  cellIndex: number,
  player: Player
): MoveResult {
  // Clone
  const newBoards = boards.map(b => [...b])
  const newMeta = [...meta]

  newBoards[boardIndex][cellIndex] = player

  // Check if this sub-board was won
  const subResult = checkSubBoardWinner(newBoards[boardIndex])
  if (subResult) {
    newMeta[boardIndex] = subResult
  }

  // Check meta winner
  const winner = checkMetaWinner(newMeta)

  // Check meta draw
  const isDraw = !winner && newMeta.every(m => m !== null)

  // Determine next active board
  let nextActiveBoard: number | null = cellIndex
  if (newMeta[cellIndex] !== null) {
    nextActiveBoard = null // opponent can play anywhere
  }

  return { boards: newBoards, meta: newMeta, nextActiveBoard, winner, isDraw }
}

/** Get AI move using simple heuristic (not full minimax — too expensive). */
export function getAIMove(
  boards: SubBoard[],
  meta: MetaCell[],
  activeBoard: number | null,
  player: Player
): [number, number] | null {
  const validMoves = getValidMoves(boards, meta, activeBoard)
  if (validMoves.length === 0) return null

  const opponent: Player = player === 'X' ? 'O' : 'X'

  // 1. Check for immediate sub-board win
  for (const [b, c] of validMoves) {
    const testBoard = [...boards[b]]
    testBoard[c] = player
    const result = checkSubBoardWinner(testBoard)
    if (result === player) {
      // Check if this also wins the meta game
      const testMeta = [...meta]
      testMeta[b] = player
      if (checkMetaWinner(testMeta)) return [b, c] // game-winning move!
      return [b, c]
    }
  }

  // 2. Block opponent sub-board win
  for (const [b, c] of validMoves) {
    const testBoard = [...boards[b]]
    testBoard[c] = opponent
    if (checkSubBoardWinner(testBoard) === opponent) {
      return [b, c]
    }
  }

  // 3. Prefer center of sub-boards, then corners
  const preferred = [4, 0, 2, 6, 8, 1, 3, 5, 7]
  for (const cell of preferred) {
    const move = validMoves.find(([, c]) => c === cell)
    if (move) return move
  }

  // 4. Random valid move
  return validMoves[Math.floor(Math.random() * validMoves.length)]
}
