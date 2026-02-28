/**
 * Checkers game engine — pure logic, no React.
 *
 * Handles board state, move validation, captures, king promotion,
 * and AI with minimax + alpha-beta pruning.
 */

export type Player = 'red' | 'black'
export interface Piece { player: Player; isKing: boolean }
export type Cell = Piece | null
export type Board = Cell[][]
export const BOARD_SIZE = 8

export interface Move {
  from: [number, number]
  to: [number, number]
  captures: [number, number][]
  isMultiJump?: boolean
}

/** Create a standard 8x8 checkers board with pieces in starting positions. */
export function createBoard(): Board {
  const board: Board = Array.from({ length: BOARD_SIZE }, () => Array(BOARD_SIZE).fill(null))
  for (let r = 0; r < BOARD_SIZE; r++) {
    for (let c = 0; c < BOARD_SIZE; c++) {
      if ((r + c) % 2 === 1) {
        if (r < 3) board[r][c] = { player: 'red', isKing: false }
        else if (r > 4) board[r][c] = { player: 'black', isKing: false }
      }
    }
  }
  return board
}

/** Clone a board (deep copy of pieces). */
function cloneBoard(board: Board): Board {
  return board.map(row => row.map(cell => cell ? { ...cell } : null))
}

/** Check if a position is within the board. */
function inBounds(r: number, c: number): boolean {
  return r >= 0 && r < BOARD_SIZE && c >= 0 && c < BOARD_SIZE
}

/** Get the diagonal directions a piece can move (non-capture). */
function getMoveDirections(piece: Piece): [number, number][] {
  if (piece.isKing) return [[-1, -1], [-1, 1], [1, -1], [1, 1]]
  // Red moves down (increasing row), black moves up (decreasing row)
  return piece.player === 'red' ? [[1, -1], [1, 1]] : [[-1, -1], [-1, 1]]
}

/** Get valid non-capture moves for a piece at (row, col). */
export function getValidMoves(board: Board, row: number, col: number): Move[] {
  const piece = board[row][col]
  if (!piece) return []

  const moves: Move[] = []
  for (const [dr, dc] of getMoveDirections(piece)) {
    const nr = row + dr
    const nc = col + dc
    if (inBounds(nr, nc) && board[nr][nc] === null) {
      moves.push({ from: [row, col], to: [nr, nc], captures: [] })
    }
  }
  return moves
}

/** Get all capture directions (kings: all 4; regular: forward only). */
function getCaptureDirections(piece: Piece): [number, number][] {
  if (piece.isKing) return [[-1, -1], [-1, 1], [1, -1], [1, 1]]
  return piece.player === 'red' ? [[1, -1], [1, 1]] : [[-1, -1], [-1, 1]]
}

/** Get all capture moves for a piece, including multi-jump chains. */
export function getCaptureMoves(board: Board, row: number, col: number): Move[] {
  const piece = board[row][col]
  if (!piece) return []

  const results: Move[] = []
  findCaptures(board, row, col, piece, [row, col], [], results)
  return results
}

/** Recursive helper to find all capture chains. */
function findCaptures(
  board: Board, row: number, col: number, piece: Piece,
  origin: [number, number], capturedSoFar: [number, number][], results: Move[]
): void {
  const dirs = getCaptureDirections(piece)
  let foundCapture = false

  for (const [dr, dc] of dirs) {
    const midR = row + dr
    const midC = col + dc
    const landR = row + dr * 2
    const landC = col + dc * 2

    if (!inBounds(landR, landC)) continue

    const midPiece = board[midR][midC]
    if (!midPiece || midPiece.player === piece.player) continue
    if (board[landR][landC] !== null) continue

    // Don't jump same piece twice in a chain
    if (capturedSoFar.some(([cr, cc]) => cr === midR && cc === midC)) continue

    foundCapture = true
    const newCaptured: [number, number][] = [...capturedSoFar, [midR, midC]]

    // Temporarily update board for multi-jump detection
    const tempBoard = cloneBoard(board)
    tempBoard[row][col] = null
    tempBoard[midR][midC] = null
    tempBoard[landR][landC] = piece

    findCaptures(tempBoard, landR, landC, piece, origin, newCaptured, results)
  }

  // If no further captures, record the chain (only if we have captures)
  if (!foundCapture && capturedSoFar.length > 0) {
    results.push({
      from: origin,
      to: [row, col],
      captures: [...capturedSoFar],
      isMultiJump: capturedSoFar.length > 1,
    })
  }
}

/** Get all legal moves for a player. Mandatory capture rule enforced. */
export function getAllMoves(board: Board, player: Player): Move[] {
  const captures: Move[] = []
  const regularMoves: Move[] = []

  for (let r = 0; r < BOARD_SIZE; r++) {
    for (let c = 0; c < BOARD_SIZE; c++) {
      const piece = board[r][c]
      if (!piece || piece.player !== player) continue

      const pieceCaptures = getCaptureMoves(board, r, c)
      captures.push(...pieceCaptures)

      if (captures.length === 0) {
        regularMoves.push(...getValidMoves(board, r, c))
      }
    }
  }

  // Mandatory capture: if any captures exist, must take one
  return captures.length > 0 ? captures : regularMoves
}

/** Apply a move to the board. Returns a new board (immutable). */
export function applyMove(board: Board, move: Move): Board {
  const newBoard = cloneBoard(board)
  const piece = newBoard[move.from[0]][move.from[1]]
  if (!piece) return newBoard

  newBoard[move.from[0]][move.from[1]] = null
  newBoard[move.to[0]][move.to[1]] = { ...piece }

  // Remove captured pieces
  for (const [cr, cc] of move.captures) {
    newBoard[cr][cc] = null
  }

  return newBoard
}

/** Check if a row is the promotion row for a player. */
export function isKingRow(row: number, player: Player): boolean {
  return (player === 'red' && row === 7) || (player === 'black' && row === 0)
}

/** Promote any pieces on their king row. Returns a new board. */
export function promoteKings(board: Board): Board {
  const newBoard = cloneBoard(board)
  for (let c = 0; c < BOARD_SIZE; c++) {
    const topPiece = newBoard[0][c]
    if (topPiece && topPiece.player === 'black' && !topPiece.isKing) {
      newBoard[0][c] = { ...topPiece, isKing: true }
    }
    const bottomPiece = newBoard[7][c]
    if (bottomPiece && bottomPiece.player === 'red' && !bottomPiece.isKing) {
      newBoard[7][c] = { ...bottomPiece, isKing: true }
    }
  }
  return newBoard
}

/** Check if the game is over. Returns the winner or null. */
export function checkGameOver(board: Board): Player | null {
  let redPieces = 0
  let blackPieces = 0

  for (let r = 0; r < BOARD_SIZE; r++) {
    for (let c = 0; c < BOARD_SIZE; c++) {
      const piece = board[r][c]
      if (piece) {
        if (piece.player === 'red') redPieces++
        else blackPieces++
      }
    }
  }

  if (redPieces === 0) return 'black'
  if (blackPieces === 0) return 'red'

  // Check if either player has no valid moves
  const redMoves = getAllMoves(board, 'red')
  if (redMoves.length === 0) return 'black'

  const blackMoves = getAllMoves(board, 'black')
  if (blackMoves.length === 0) return 'red'

  return null
}

/** AI move using minimax with alpha-beta pruning. */
export function getAIMove(board: Board, aiPlayer: Player, depth: number): Move | null {
  const moves = getAllMoves(board, aiPlayer)
  if (moves.length === 0) return null
  if (moves.length === 1) return moves[0]

  const opponent: Player = aiPlayer === 'red' ? 'black' : 'red'

  // Check immediate captures first (prefer longest chain)
  const captures = moves.filter(m => m.captures.length > 0)
  if (captures.length > 0) {
    // Among captures, pick the best via minimax
    let bestScore = -Infinity
    let bestMove = captures[0]
    for (const move of captures) {
      let newBoard = applyMove(board, move)
      newBoard = promoteKings(newBoard)
      const score = minimax(newBoard, depth - 1, -Infinity, Infinity, false, aiPlayer, opponent)
      if (score > bestScore) {
        bestScore = score
        bestMove = move
      }
    }
    return bestMove
  }

  let bestScore = -Infinity
  let bestMove = moves[0]
  for (const move of moves) {
    let newBoard = applyMove(board, move)
    newBoard = promoteKings(newBoard)
    const score = minimax(newBoard, depth - 1, -Infinity, Infinity, false, aiPlayer, opponent)
    if (score > bestScore) {
      bestScore = score
      bestMove = move
    }
  }
  return bestMove
}

function minimax(
  board: Board, depth: number, alpha: number, beta: number,
  isMaximizing: boolean, aiPlayer: Player, opponent: Player,
): number {
  const winner = checkGameOver(board)
  if (winner === aiPlayer) return 1000 + depth
  if (winner === opponent) return -1000 - depth
  if (depth === 0) return evaluateBoard(board, aiPlayer)

  const currentPlayer = isMaximizing ? aiPlayer : opponent
  const moves = getAllMoves(board, currentPlayer)
  if (moves.length === 0) return isMaximizing ? -1000 : 1000

  if (isMaximizing) {
    let maxEval = -Infinity
    for (const move of moves) {
      let newBoard = applyMove(board, move)
      newBoard = promoteKings(newBoard)
      const eval_ = minimax(newBoard, depth - 1, alpha, beta, false, aiPlayer, opponent)
      maxEval = Math.max(maxEval, eval_)
      alpha = Math.max(alpha, eval_)
      if (beta <= alpha) break
    }
    return maxEval
  } else {
    let minEval = Infinity
    for (const move of moves) {
      let newBoard = applyMove(board, move)
      newBoard = promoteKings(newBoard)
      const eval_ = minimax(newBoard, depth - 1, alpha, beta, true, aiPlayer, opponent)
      minEval = Math.min(minEval, eval_)
      beta = Math.min(beta, eval_)
      if (beta <= alpha) break
    }
    return minEval
  }
}

/** Heuristic board evaluation. */
function evaluateBoard(board: Board, aiPlayer: Player): number {
  let score = 0

  for (let r = 0; r < BOARD_SIZE; r++) {
    for (let c = 0; c < BOARD_SIZE; c++) {
      const piece = board[r][c]
      if (!piece) continue

      const value = piece.isKing ? 3 : 1
      const isAI = piece.player === aiPlayer

      // Piece count (kings worth 3x)
      score += isAI ? value : -value

      // Center control bonus
      if (c >= 2 && c <= 5 && r >= 2 && r <= 5) {
        score += isAI ? 0.5 : -0.5
      }

      // Advancement bonus (how far toward king row)
      if (!piece.isKing) {
        const advancement = piece.player === 'red' ? r : (7 - r)
        score += isAI ? advancement * 0.1 : -advancement * 0.1
      }
    }
  }

  return score
}
