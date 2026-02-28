/**
 * Chess engine — full rules including castling, en passant, promotion,
 * check/checkmate/stalemate detection, and minimax AI with alpha-beta pruning.
 */

export type PieceType = 'pawn' | 'rook' | 'knight' | 'bishop' | 'queen' | 'king'
export type PieceColor = 'white' | 'black'

export interface Piece {
  type: PieceType
  color: PieceColor
}

export interface Move {
  fromRow: number
  fromCol: number
  toRow: number
  toCol: number
  promotion?: PieceType
  castle?: 'kingside' | 'queenside'
  enPassant?: boolean
}

export interface ChessState {
  board: (Piece | null)[][]
  currentPlayer: PieceColor
  castlingRights: {
    whiteKingside: boolean
    whiteQueenside: boolean
    blackKingside: boolean
    blackQueenside: boolean
  }
  enPassantTarget: [number, number] | null
  halfMoveClock: number
  moveHistory: Move[]
  capturedPieces: { white: PieceType[]; black: PieceType[] }
}

const SYMBOLS: Record<PieceColor, Record<PieceType, string>> = {
  white: { king: '♔', queen: '♕', rook: '♖', bishop: '♗', knight: '♘', pawn: '♙' },
  black: { king: '♚', queen: '♛', rook: '♜', bishop: '♝', knight: '♞', pawn: '♟' },
}

const PIECE_VALUES: Record<PieceType, number> = {
  pawn: 100, knight: 320, bishop: 330, rook: 500, queen: 900, king: 20000,
}

// Position bonus tables (simplified) — indexed [row][col] from white's perspective
const PAWN_TABLE = [
  [0,  0,  0,  0,  0,  0,  0,  0],
  [50, 50, 50, 50, 50, 50, 50, 50],
  [10, 10, 20, 30, 30, 20, 10, 10],
  [5,  5, 10, 25, 25, 10,  5,  5],
  [0,  0,  0, 20, 20,  0,  0,  0],
  [5, -5,-10,  0,  0,-10, -5,  5],
  [5, 10, 10,-20,-20, 10, 10,  5],
  [0,  0,  0,  0,  0,  0,  0,  0],
]

const KNIGHT_TABLE = [
  [-50,-40,-30,-30,-30,-30,-40,-50],
  [-40,-20,  0,  0,  0,  0,-20,-40],
  [-30,  0, 10, 15, 15, 10,  0,-30],
  [-30,  5, 15, 20, 20, 15,  5,-30],
  [-30,  0, 15, 20, 20, 15,  0,-30],
  [-30,  5, 10, 15, 15, 10,  5,-30],
  [-40,-20,  0,  5,  5,  0,-20,-40],
  [-50,-40,-30,-30,-30,-30,-40,-50],
]

const BISHOP_TABLE = [
  [-20,-10,-10,-10,-10,-10,-10,-20],
  [-10,  0,  0,  0,  0,  0,  0,-10],
  [-10,  0, 10, 10, 10, 10,  0,-10],
  [-10,  5,  5, 10, 10,  5,  5,-10],
  [-10,  0, 10, 10, 10, 10,  0,-10],
  [-10, 10, 10, 10, 10, 10, 10,-10],
  [-10,  5,  0,  0,  0,  0,  5,-10],
  [-20,-10,-10,-10,-10,-10,-10,-20],
]

const KING_TABLE = [
  [-30,-40,-40,-50,-50,-40,-40,-30],
  [-30,-40,-40,-50,-50,-40,-40,-30],
  [-30,-40,-40,-50,-50,-40,-40,-30],
  [-30,-40,-40,-50,-50,-40,-40,-30],
  [-20,-30,-30,-40,-40,-30,-30,-20],
  [-10,-20,-20,-20,-20,-20,-20,-10],
  [ 20, 20,  0,  0,  0,  0, 20, 20],
  [ 20, 30, 10,  0,  0, 10, 30, 20],
]

function getPositionBonus(piece: Piece, row: number, col: number): number {
  // For black, flip the row
  const r = piece.color === 'white' ? row : 7 - row
  switch (piece.type) {
    case 'pawn': return PAWN_TABLE[r][col]
    case 'knight': return KNIGHT_TABLE[r][col]
    case 'bishop': return BISHOP_TABLE[r][col]
    case 'king': return KING_TABLE[r][col]
    default: return 0
  }
}

export function createBoard(): ChessState {
  const board: (Piece | null)[][] = Array.from({ length: 8 }, () => Array(8).fill(null))
  const order: PieceType[] = ['rook', 'knight', 'bishop', 'queen', 'king', 'bishop', 'knight', 'rook']

  for (let c = 0; c < 8; c++) {
    board[0][c] = { type: order[c], color: 'black' }
    board[1][c] = { type: 'pawn', color: 'black' }
    board[6][c] = { type: 'pawn', color: 'white' }
    board[7][c] = { type: order[c], color: 'white' }
  }

  return {
    board,
    currentPlayer: 'white',
    castlingRights: {
      whiteKingside: true, whiteQueenside: true,
      blackKingside: true, blackQueenside: true,
    },
    enPassantTarget: null,
    halfMoveClock: 0,
    moveHistory: [],
    capturedPieces: { white: [], black: [] },
  }
}

export function getPieceSymbol(piece: Piece): string {
  return SYMBOLS[piece.color][piece.type]
}

function inBounds(r: number, c: number): boolean {
  return r >= 0 && r < 8 && c >= 0 && c < 8
}

function cloneBoard(board: (Piece | null)[][]): (Piece | null)[][] {
  return board.map(row => row.map(cell => cell ? { ...cell } : null))
}

/** Find king position for a given color. */
function findKing(board: (Piece | null)[][], color: PieceColor): [number, number] {
  for (let r = 0; r < 8; r++)
    for (let c = 0; c < 8; c++)
      if (board[r][c]?.type === 'king' && board[r][c]?.color === color)
        return [r, c]
  return [-1, -1] // should never happen
}

/** Check if a square is attacked by any piece of the given color. */
function isSquareAttacked(board: (Piece | null)[][], row: number, col: number, byColor: PieceColor): boolean {
  // Pawn attacks
  const pawnDir = byColor === 'white' ? 1 : -1
  for (const dc of [-1, 1]) {
    const pr = row + pawnDir
    const pc = col + dc
    if (inBounds(pr, pc) && board[pr][pc]?.type === 'pawn' && board[pr][pc]?.color === byColor)
      return true
  }

  // Knight attacks
  const knightMoves = [[-2,-1],[-2,1],[-1,-2],[-1,2],[1,-2],[1,2],[2,-1],[2,1]]
  for (const [dr, dc] of knightMoves) {
    const nr = row + dr, nc = col + dc
    if (inBounds(nr, nc) && board[nr][nc]?.type === 'knight' && board[nr][nc]?.color === byColor)
      return true
  }

  // King attacks
  for (let dr = -1; dr <= 1; dr++)
    for (let dc = -1; dc <= 1; dc++) {
      if (dr === 0 && dc === 0) continue
      const nr = row + dr, nc = col + dc
      if (inBounds(nr, nc) && board[nr][nc]?.type === 'king' && board[nr][nc]?.color === byColor)
        return true
    }

  // Sliding pieces: rook/queen (horizontal/vertical)
  const straightDirs = [[0,1],[0,-1],[1,0],[-1,0]]
  for (const [dr, dc] of straightDirs) {
    let r = row + dr, c = col + dc
    while (inBounds(r, c)) {
      const p = board[r][c]
      if (p) {
        if (p.color === byColor && (p.type === 'rook' || p.type === 'queen'))
          return true
        break
      }
      r += dr; c += dc
    }
  }

  // Sliding pieces: bishop/queen (diagonal)
  const diagDirs = [[1,1],[1,-1],[-1,1],[-1,-1]]
  for (const [dr, dc] of diagDirs) {
    let r = row + dr, c = col + dc
    while (inBounds(r, c)) {
      const p = board[r][c]
      if (p) {
        if (p.color === byColor && (p.type === 'bishop' || p.type === 'queen'))
          return true
        break
      }
      r += dr; c += dc
    }
  }

  return false
}

export function isInCheck(state: ChessState, player: PieceColor): boolean {
  const [kr, kc] = findKing(state.board, player)
  const opponent = player === 'white' ? 'black' : 'white'
  return isSquareAttacked(state.board, kr, kc, opponent)
}

/** Generate raw moves for a piece (without checking if they leave king in check). */
function getRawMoves(state: ChessState, row: number, col: number): Move[] {
  const piece = state.board[row][col]
  if (!piece || piece.color !== state.currentPlayer) return []

  const moves: Move[] = []
  const color = piece.color
  const opponent = color === 'white' ? 'black' : 'white'

  const addMove = (toRow: number, toCol: number, extra?: Partial<Move>) => {
    moves.push({ fromRow: row, fromCol: col, toRow, toCol, ...extra })
  }

  const canMoveTo = (r: number, c: number): boolean => {
    return inBounds(r, c) && board[r][c]?.color !== color
  }

  const board = state.board

  switch (piece.type) {
    case 'pawn': {
      const dir = color === 'white' ? -1 : 1
      const startRow = color === 'white' ? 6 : 1
      const promoRow = color === 'white' ? 0 : 7

      // Forward one
      const f1r = row + dir
      if (inBounds(f1r, col) && !board[f1r][col]) {
        if (f1r === promoRow) {
          for (const promo of ['queen', 'rook', 'bishop', 'knight'] as PieceType[])
            addMove(f1r, col, { promotion: promo })
        } else {
          addMove(f1r, col)
        }

        // Forward two from start
        if (row === startRow) {
          const f2r = row + dir * 2
          if (!board[f2r][col]) addMove(f2r, col)
        }
      }

      // Diagonal captures
      for (const dc of [-1, 1]) {
        const cr = row + dir, cc = col + dc
        if (!inBounds(cr, cc)) continue
        if (board[cr][cc]?.color === opponent) {
          if (cr === promoRow) {
            for (const promo of ['queen', 'rook', 'bishop', 'knight'] as PieceType[])
              addMove(cr, cc, { promotion: promo })
          } else {
            addMove(cr, cc)
          }
        }

        // En passant
        if (state.enPassantTarget && cr === state.enPassantTarget[0] && cc === state.enPassantTarget[1]) {
          addMove(cr, cc, { enPassant: true })
        }
      }
      break
    }

    case 'knight': {
      const offsets = [[-2,-1],[-2,1],[-1,-2],[-1,2],[1,-2],[1,2],[2,-1],[2,1]]
      for (const [dr, dc] of offsets) {
        const nr = row + dr, nc = col + dc
        if (canMoveTo(nr, nc)) addMove(nr, nc)
      }
      break
    }

    case 'bishop': {
      const dirs = [[1,1],[1,-1],[-1,1],[-1,-1]]
      for (const [dr, dc] of dirs) {
        let r = row + dr, c = col + dc
        while (inBounds(r, c)) {
          if (board[r][c]) {
            if (board[r][c]!.color === opponent) addMove(r, c)
            break
          }
          addMove(r, c)
          r += dr; c += dc
        }
      }
      break
    }

    case 'rook': {
      const dirs = [[0,1],[0,-1],[1,0],[-1,0]]
      for (const [dr, dc] of dirs) {
        let r = row + dr, c = col + dc
        while (inBounds(r, c)) {
          if (board[r][c]) {
            if (board[r][c]!.color === opponent) addMove(r, c)
            break
          }
          addMove(r, c)
          r += dr; c += dc
        }
      }
      break
    }

    case 'queen': {
      const dirs = [[0,1],[0,-1],[1,0],[-1,0],[1,1],[1,-1],[-1,1],[-1,-1]]
      for (const [dr, dc] of dirs) {
        let r = row + dr, c = col + dc
        while (inBounds(r, c)) {
          if (board[r][c]) {
            if (board[r][c]!.color === opponent) addMove(r, c)
            break
          }
          addMove(r, c)
          r += dr; c += dc
        }
      }
      break
    }

    case 'king': {
      // Normal king moves
      for (let dr = -1; dr <= 1; dr++)
        for (let dc = -1; dc <= 1; dc++) {
          if (dr === 0 && dc === 0) continue
          const nr = row + dr, nc = col + dc
          if (canMoveTo(nr, nc)) addMove(nr, nc)
        }

      // Castling
      const backRank = color === 'white' ? 7 : 0
      if (row === backRank && col === 4) {
        // Kingside
        const ksRight = color === 'white' ? state.castlingRights.whiteKingside : state.castlingRights.blackKingside
        if (ksRight && !board[backRank][5] && !board[backRank][6] && board[backRank][7]?.type === 'rook') {
          if (!isSquareAttacked(board, backRank, 4, opponent) &&
              !isSquareAttacked(board, backRank, 5, opponent) &&
              !isSquareAttacked(board, backRank, 6, opponent)) {
            addMove(backRank, 6, { castle: 'kingside' })
          }
        }

        // Queenside
        const qsRight = color === 'white' ? state.castlingRights.whiteQueenside : state.castlingRights.blackQueenside
        if (qsRight && !board[backRank][1] && !board[backRank][2] && !board[backRank][3] && board[backRank][0]?.type === 'rook') {
          if (!isSquareAttacked(board, backRank, 4, opponent) &&
              !isSquareAttacked(board, backRank, 3, opponent) &&
              !isSquareAttacked(board, backRank, 2, opponent)) {
            addMove(backRank, 2, { castle: 'queenside' })
          }
        }
      }
      break
    }
  }

  return moves
}

/** Get all legal moves for a piece, filtering out moves that leave own king in check. */
export function getValidMoves(state: ChessState, row: number, col: number): Move[] {
  const raw = getRawMoves(state, row, col)
  return raw.filter(move => {
    const next = applyMoveUnchecked(state, move)
    return !isInCheck(next, state.currentPlayer)
  })
}

/** Apply a move without legality validation (for internal use). */
function applyMoveUnchecked(state: ChessState, move: Move): ChessState {
  const board = cloneBoard(state.board)
  const piece = board[move.fromRow][move.fromCol]!
  const captured = board[move.toRow][move.toCol]
  const capturedPieces = {
    white: [...state.capturedPieces.white],
    black: [...state.capturedPieces.black],
  }

  // Handle en passant capture
  if (move.enPassant) {
    const capturedRow = piece.color === 'white' ? move.toRow + 1 : move.toRow - 1
    const epPiece = board[capturedRow][move.toCol]
    if (epPiece) capturedPieces[piece.color].push(epPiece.type)
    board[capturedRow][move.toCol] = null
  }

  // Track captured piece
  if (captured) {
    capturedPieces[piece.color].push(captured.type)
  }

  // Move piece
  board[move.fromRow][move.fromCol] = null
  if (move.promotion) {
    board[move.toRow][move.toCol] = { type: move.promotion, color: piece.color }
  } else {
    board[move.toRow][move.toCol] = piece
  }

  // Handle castling — move the rook
  if (move.castle) {
    const backRank = move.fromRow
    if (move.castle === 'kingside') {
      board[backRank][5] = board[backRank][7]
      board[backRank][7] = null
    } else {
      board[backRank][3] = board[backRank][0]
      board[backRank][0] = null
    }
  }

  // Update castling rights
  const cr = { ...state.castlingRights }
  if (piece.type === 'king') {
    if (piece.color === 'white') { cr.whiteKingside = false; cr.whiteQueenside = false }
    else { cr.blackKingside = false; cr.blackQueenside = false }
  }
  if (piece.type === 'rook') {
    if (piece.color === 'white') {
      if (move.fromRow === 7 && move.fromCol === 7) cr.whiteKingside = false
      if (move.fromRow === 7 && move.fromCol === 0) cr.whiteQueenside = false
    } else {
      if (move.fromRow === 0 && move.fromCol === 7) cr.blackKingside = false
      if (move.fromRow === 0 && move.fromCol === 0) cr.blackQueenside = false
    }
  }
  // If a rook is captured, remove its castling right
  if (captured?.type === 'rook') {
    if (move.toRow === 0 && move.toCol === 0) cr.blackQueenside = false
    if (move.toRow === 0 && move.toCol === 7) cr.blackKingside = false
    if (move.toRow === 7 && move.toCol === 0) cr.whiteQueenside = false
    if (move.toRow === 7 && move.toCol === 7) cr.whiteKingside = false
  }

  // En passant target
  let enPassantTarget: [number, number] | null = null
  if (piece.type === 'pawn' && Math.abs(move.toRow - move.fromRow) === 2) {
    enPassantTarget = [(move.fromRow + move.toRow) / 2, move.fromCol]
  }

  // Half-move clock
  const halfMoveClock = (piece.type === 'pawn' || captured) ? 0 : state.halfMoveClock + 1

  return {
    board,
    currentPlayer: state.currentPlayer === 'white' ? 'black' : 'white',
    castlingRights: cr,
    enPassantTarget,
    halfMoveClock,
    moveHistory: [...state.moveHistory, move],
    capturedPieces,
  }
}

/** Apply a move, returning new state. Immutable. */
export function applyMove(state: ChessState, move: Move): ChessState {
  return applyMoveUnchecked(state, move)
}

export function isCheckmate(state: ChessState, player: PieceColor): boolean {
  if (!isInCheck(state, player)) return false
  return !hasAnyLegalMove(state, player)
}

export function isStalemate(state: ChessState, player: PieceColor): boolean {
  if (isInCheck(state, player)) return false
  return !hasAnyLegalMove(state, player)
}

export function isDraw(state: ChessState): boolean {
  if (state.halfMoveClock >= 100) return true
  return isStalemate(state, state.currentPlayer)
}

function hasAnyLegalMove(state: ChessState, player: PieceColor): boolean {
  const checkState = { ...state, currentPlayer: player }
  for (let r = 0; r < 8; r++)
    for (let c = 0; c < 8; c++)
      if (state.board[r][c]?.color === player) {
        const moves = getValidMoves(checkState, r, c)
        if (moves.length > 0) return true
      }
  return false
}

/** Evaluate board position. Positive = good for white, negative = good for black. */
function evaluate(state: ChessState): number {
  let score = 0
  for (let r = 0; r < 8; r++)
    for (let c = 0; c < 8; c++) {
      const piece = state.board[r][c]
      if (!piece) continue
      const value = PIECE_VALUES[piece.type] + getPositionBonus(piece, r, c)
      score += piece.color === 'white' ? value : -value
    }
  return score
}

/** Get all legal moves for a player, ordered for better alpha-beta pruning. */
function getAllMoves(state: ChessState): Move[] {
  const moves: Move[] = []
  for (let r = 0; r < 8; r++)
    for (let c = 0; c < 8; c++)
      if (state.board[r][c]?.color === state.currentPlayer)
        moves.push(...getValidMoves(state, r, c))

  // Move ordering: captures first (MVV-LVA), then others
  moves.sort((a, b) => {
    const aCap = state.board[a.toRow][a.toCol]
    const bCap = state.board[b.toRow][b.toCol]
    const aVal = aCap ? PIECE_VALUES[aCap.type] : 0
    const bVal = bCap ? PIECE_VALUES[bCap.type] : 0
    return bVal - aVal
  })

  return moves
}

/** Minimax with alpha-beta pruning. */
function minimax(state: ChessState, depth: number, alpha: number, beta: number, maximizing: boolean): number {
  if (depth === 0) return evaluate(state)

  const player = maximizing ? 'white' : 'black'
  if (isCheckmate(state, player)) return maximizing ? -99999 : 99999
  if (isDraw(state)) return 0

  const moves = getAllMoves(state)
  if (moves.length === 0) return evaluate(state)

  if (maximizing) {
    let maxEval = -Infinity
    for (const move of moves) {
      const next = applyMove(state, move)
      const score = minimax(next, depth - 1, alpha, beta, false)
      maxEval = Math.max(maxEval, score)
      alpha = Math.max(alpha, score)
      if (beta <= alpha) break
    }
    return maxEval
  } else {
    let minEval = Infinity
    for (const move of moves) {
      const next = applyMove(state, move)
      const score = minimax(next, depth - 1, alpha, beta, true)
      minEval = Math.min(minEval, score)
      beta = Math.min(beta, score)
      if (beta <= alpha) break
    }
    return minEval
  }
}

/** Get best AI move for the current player at given depth. */
export function getAIMove(state: ChessState, depth: number): Move | null {
  const moves = getAllMoves(state)
  if (moves.length === 0) return null

  const maximizing = state.currentPlayer === 'white'
  let bestMove = moves[0]
  let bestScore = maximizing ? -Infinity : Infinity

  for (const move of moves) {
    const next = applyMove(state, move)
    const score = minimax(next, depth - 1, -Infinity, Infinity, !maximizing)
    if (maximizing ? score > bestScore : score < bestScore) {
      bestScore = score
      bestMove = move
    }
  }

  return bestMove
}
