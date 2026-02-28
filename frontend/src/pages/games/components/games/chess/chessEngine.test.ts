import { describe, test, expect } from 'vitest'
import {
  createBoard, getPieceSymbol, getValidMoves, isInCheck, isCheckmate,
  isStalemate, applyMove, getAIMove,
  type ChessState, type PieceType, type Move,
} from './chessEngine'

describe('createBoard', () => {
  test('returns 8x8 board', () => {
    const state = createBoard()
    expect(state.board.length).toBe(8)
    state.board.forEach(row => expect(row.length).toBe(8))
  })

  test('white starts', () => {
    const state = createBoard()
    expect(state.currentPlayer).toBe('white')
  })

  test('has 16 white pieces', () => {
    const state = createBoard()
    let count = 0
    for (const row of state.board)
      for (const cell of row)
        if (cell?.color === 'white') count++
    expect(count).toBe(16)
  })

  test('has 16 black pieces', () => {
    const state = createBoard()
    let count = 0
    for (const row of state.board)
      for (const cell of row)
        if (cell?.color === 'black') count++
    expect(count).toBe(16)
  })

  test('white pawns on row 6', () => {
    const state = createBoard()
    for (let c = 0; c < 8; c++) {
      expect(state.board[6][c]?.type).toBe('pawn')
      expect(state.board[6][c]?.color).toBe('white')
    }
  })

  test('black pawns on row 1', () => {
    const state = createBoard()
    for (let c = 0; c < 8; c++) {
      expect(state.board[1][c]?.type).toBe('pawn')
      expect(state.board[1][c]?.color).toBe('black')
    }
  })

  test('back ranks have correct piece order', () => {
    const state = createBoard()
    const order: PieceType[] = ['rook', 'knight', 'bishop', 'queen', 'king', 'bishop', 'knight', 'rook']
    for (let c = 0; c < 8; c++) {
      expect(state.board[7][c]?.type).toBe(order[c])
      expect(state.board[7][c]?.color).toBe('white')
      expect(state.board[0][c]?.type).toBe(order[c])
      expect(state.board[0][c]?.color).toBe('black')
    }
  })

  test('middle rows are empty', () => {
    const state = createBoard()
    for (let r = 2; r <= 5; r++)
      for (let c = 0; c < 8; c++)
        expect(state.board[r][c]).toBeNull()
  })

  test('all castling rights true initially', () => {
    const state = createBoard()
    expect(state.castlingRights.whiteKingside).toBe(true)
    expect(state.castlingRights.whiteQueenside).toBe(true)
    expect(state.castlingRights.blackKingside).toBe(true)
    expect(state.castlingRights.blackQueenside).toBe(true)
  })
})

describe('getPieceSymbol', () => {
  test('white king', () => expect(getPieceSymbol({ type: 'king', color: 'white' })).toBe('♔'))
  test('white queen', () => expect(getPieceSymbol({ type: 'queen', color: 'white' })).toBe('♕'))
  test('white rook', () => expect(getPieceSymbol({ type: 'rook', color: 'white' })).toBe('♖'))
  test('white bishop', () => expect(getPieceSymbol({ type: 'bishop', color: 'white' })).toBe('♗'))
  test('white knight', () => expect(getPieceSymbol({ type: 'knight', color: 'white' })).toBe('♘'))
  test('white pawn', () => expect(getPieceSymbol({ type: 'pawn', color: 'white' })).toBe('♙'))
  test('black king', () => expect(getPieceSymbol({ type: 'king', color: 'black' })).toBe('♚'))
  test('black queen', () => expect(getPieceSymbol({ type: 'queen', color: 'black' })).toBe('♛'))
  test('black rook', () => expect(getPieceSymbol({ type: 'rook', color: 'black' })).toBe('♜'))
  test('black bishop', () => expect(getPieceSymbol({ type: 'bishop', color: 'black' })).toBe('♝'))
  test('black knight', () => expect(getPieceSymbol({ type: 'knight', color: 'black' })).toBe('♞'))
  test('black pawn', () => expect(getPieceSymbol({ type: 'pawn', color: 'black' })).toBe('♟'))
})

describe('pawn moves', () => {
  test('white pawn can move forward one from start', () => {
    const state = createBoard()
    const moves = getValidMoves(state, 6, 4) // e2 pawn
    expect(moves.some(m => m.toRow === 5 && m.toCol === 4)).toBe(true)
  })

  test('white pawn can move forward two from start', () => {
    const state = createBoard()
    const moves = getValidMoves(state, 6, 4) // e2 pawn
    expect(moves.some(m => m.toRow === 4 && m.toCol === 4)).toBe(true)
  })

  test('white pawn cannot move forward two if blocked', () => {
    const state = createBoard()
    state.board[5][4] = { type: 'pawn', color: 'black' }
    const moves = getValidMoves(state, 6, 4)
    expect(moves.some(m => m.toRow === 4 && m.toCol === 4)).toBe(false)
    expect(moves.some(m => m.toRow === 5 && m.toCol === 4)).toBe(false)
  })

  test('white pawn can capture diagonally', () => {
    const state = createBoard()
    state.board[5][3] = { type: 'pawn', color: 'black' }
    const moves = getValidMoves(state, 6, 4) // e2 pawn
    expect(moves.some(m => m.toRow === 5 && m.toCol === 3)).toBe(true)
  })

  test('white pawn cannot capture own piece diagonally', () => {
    const state = createBoard()
    state.board[5][3] = { type: 'pawn', color: 'white' }
    const moves = getValidMoves(state, 6, 4)
    expect(moves.some(m => m.toRow === 5 && m.toCol === 3)).toBe(false)
  })

  test('black pawn moves down the board', () => {
    const state = createBoard()
    state.currentPlayer = 'black'
    const moves = getValidMoves(state, 1, 4) // e7 pawn
    expect(moves.some(m => m.toRow === 2 && m.toCol === 4)).toBe(true)
    expect(moves.some(m => m.toRow === 3 && m.toCol === 4)).toBe(true)
  })
})

describe('knight moves', () => {
  test('knight has correct moves from initial position', () => {
    const state = createBoard()
    const moves = getValidMoves(state, 7, 1) // b1 knight
    expect(moves.length).toBe(2)
    expect(moves.some(m => m.toRow === 5 && m.toCol === 0)).toBe(true) // a3
    expect(moves.some(m => m.toRow === 5 && m.toCol === 2)).toBe(true) // c3
  })

  test('knight has up to 8 moves from center', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: false, whiteQueenside: false, blackKingside: false, blackQueenside: false },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    state.board[4][4] = { type: 'knight', color: 'white' }
    state.board[0][0] = { type: 'king', color: 'white' }
    state.board[0][7] = { type: 'king', color: 'black' }
    const moves = getValidMoves(state, 4, 4)
    expect(moves.length).toBe(8)
  })
})

describe('rook moves', () => {
  test('rook blocked at start', () => {
    const state = createBoard()
    const moves = getValidMoves(state, 7, 0) // a1 rook
    expect(moves.length).toBe(0) // blocked by own pieces
  })

  test('rook moves in open file', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: false, whiteQueenside: false, blackKingside: false, blackQueenside: false },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    state.board[4][4] = { type: 'rook', color: 'white' }
    state.board[0][0] = { type: 'king', color: 'white' }
    state.board[7][7] = { type: 'king', color: 'black' }
    const moves = getValidMoves(state, 4, 4)
    // 7 up + 3 down + 4 left + 3 right = 14 (minus any that leave king in check)
    expect(moves.length).toBe(14)
  })
})

describe('bishop moves', () => {
  test('bishop blocked at start', () => {
    const state = createBoard()
    const moves = getValidMoves(state, 7, 2) // c1 bishop
    expect(moves.length).toBe(0)
  })

  test('bishop moves diagonally in open board', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: false, whiteQueenside: false, blackKingside: false, blackQueenside: false },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    state.board[4][4] = { type: 'bishop', color: 'white' }
    state.board[7][0] = { type: 'king', color: 'white' }
    state.board[0][7] = { type: 'king', color: 'black' }
    const moves = getValidMoves(state, 4, 4)
    expect(moves.length).toBe(13) // 4 diagonals
  })
})

describe('king moves', () => {
  test('king has no moves at start (blocked by own pieces)', () => {
    const state = createBoard()
    const moves = getValidMoves(state, 7, 4) // e1 king
    expect(moves.length).toBe(0)
  })
})

describe('isInCheck', () => {
  test('returns false at start', () => {
    const state = createBoard()
    expect(isInCheck(state, 'white')).toBe(false)
    expect(isInCheck(state, 'black')).toBe(false)
  })

  test('detects rook check', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: false, whiteQueenside: false, blackKingside: false, blackQueenside: false },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    state.board[4][4] = { type: 'king', color: 'white' }
    state.board[4][0] = { type: 'rook', color: 'black' }
    state.board[0][0] = { type: 'king', color: 'black' }
    expect(isInCheck(state, 'white')).toBe(true)
  })

  test('detects knight check', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: false, whiteQueenside: false, blackKingside: false, blackQueenside: false },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    state.board[4][4] = { type: 'king', color: 'white' }
    state.board[2][3] = { type: 'knight', color: 'black' }
    state.board[0][0] = { type: 'king', color: 'black' }
    expect(isInCheck(state, 'white')).toBe(true)
  })

  test('detects pawn check', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: false, whiteQueenside: false, blackKingside: false, blackQueenside: false },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    state.board[4][4] = { type: 'king', color: 'white' }
    state.board[3][3] = { type: 'pawn', color: 'black' } // black pawn attacks diag down
    state.board[0][0] = { type: 'king', color: 'black' }
    expect(isInCheck(state, 'white')).toBe(true)
  })
})

describe('isCheckmate', () => {
  test('back rank mate', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: false, whiteQueenside: false, blackKingside: false, blackQueenside: false },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    // White king on h1, white pawns on f2, g2, h2 block escape
    state.board[7][7] = { type: 'king', color: 'white' }
    state.board[6][5] = { type: 'pawn', color: 'white' }
    state.board[6][6] = { type: 'pawn', color: 'white' }
    state.board[6][7] = { type: 'pawn', color: 'white' }
    // Black rook on a1 delivers mate
    state.board[7][0] = { type: 'rook', color: 'black' }
    state.board[0][0] = { type: 'king', color: 'black' }
    expect(isCheckmate(state, 'white')).toBe(true)
  })

  test('not checkmate if can block', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: false, whiteQueenside: false, blackKingside: false, blackQueenside: false },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    state.board[7][7] = { type: 'king', color: 'white' }
    state.board[6][5] = { type: 'pawn', color: 'white' }
    state.board[6][6] = { type: 'pawn', color: 'white' }
    state.board[6][7] = { type: 'pawn', color: 'white' }
    state.board[7][0] = { type: 'rook', color: 'black' }
    // White has a rook that can block
    state.board[5][3] = { type: 'rook', color: 'white' }
    state.board[0][0] = { type: 'king', color: 'black' }
    expect(isCheckmate(state, 'white')).toBe(false)
  })
})

describe('isStalemate', () => {
  test('king with no moves and not in check', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: false, whiteQueenside: false, blackKingside: false, blackQueenside: false },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    // White king in corner, black queen covers all escape squares
    state.board[0][0] = { type: 'king', color: 'white' }
    state.board[2][1] = { type: 'queen', color: 'black' }
    state.board[7][7] = { type: 'king', color: 'black' }
    expect(isStalemate(state, 'white')).toBe(true)
  })

  test('not stalemate if has legal moves', () => {
    const state = createBoard()
    expect(isStalemate(state, 'white')).toBe(false)
  })
})

describe('applyMove', () => {
  test('moves piece to destination', () => {
    const state = createBoard()
    const move: Move = { fromRow: 6, fromCol: 4, toRow: 4, toCol: 4 } // e2-e4
    const next = applyMove(state, move)
    expect(next.board[4][4]?.type).toBe('pawn')
    expect(next.board[4][4]?.color).toBe('white')
    expect(next.board[6][4]).toBeNull()
  })

  test('switches player', () => {
    const state = createBoard()
    const move: Move = { fromRow: 6, fromCol: 4, toRow: 4, toCol: 4 }
    const next = applyMove(state, move)
    expect(next.currentPlayer).toBe('black')
  })

  test('captures add to captured list', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: false, whiteQueenside: false, blackKingside: false, blackQueenside: false },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    state.board[4][4] = { type: 'rook', color: 'white' }
    state.board[4][0] = { type: 'bishop', color: 'black' }
    state.board[0][0] = { type: 'king', color: 'white' }
    state.board[7][7] = { type: 'king', color: 'black' }
    const move: Move = { fromRow: 4, fromCol: 4, toRow: 4, toCol: 0 }
    const next = applyMove(state, move)
    expect(next.capturedPieces.white).toContain('bishop')
  })

  test('is immutable', () => {
    const state = createBoard()
    const move: Move = { fromRow: 6, fromCol: 4, toRow: 4, toCol: 4 }
    const next = applyMove(state, move)
    expect(next).not.toBe(state)
    expect(next.board).not.toBe(state.board)
    // Original state unchanged
    expect(state.board[6][4]?.type).toBe('pawn')
  })

  test('sets en passant target after double pawn push', () => {
    const state = createBoard()
    const move: Move = { fromRow: 6, fromCol: 4, toRow: 4, toCol: 4 }
    const next = applyMove(state, move)
    expect(next.enPassantTarget).toEqual([5, 4])
  })

  test('pawn promotion sets piece type', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: false, whiteQueenside: false, blackKingside: false, blackQueenside: false },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    state.board[1][0] = { type: 'pawn', color: 'white' }
    state.board[7][4] = { type: 'king', color: 'white' }
    state.board[0][4] = { type: 'king', color: 'black' }
    const move: Move = { fromRow: 1, fromCol: 0, toRow: 0, toCol: 0, promotion: 'queen' }
    const next = applyMove(state, move)
    expect(next.board[0][0]?.type).toBe('queen')
    expect(next.board[0][0]?.color).toBe('white')
  })
})

describe('castling', () => {
  test('white kingside castling', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: true, whiteQueenside: true, blackKingside: true, blackQueenside: true },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    state.board[7][4] = { type: 'king', color: 'white' }
    state.board[7][7] = { type: 'rook', color: 'white' }
    state.board[0][4] = { type: 'king', color: 'black' }

    const moves = getValidMoves(state, 7, 4)
    const castleMove = moves.find(m => m.castle === 'kingside')
    expect(castleMove).toBeDefined()

    const next = applyMove(state, castleMove!)
    expect(next.board[7][6]?.type).toBe('king')
    expect(next.board[7][5]?.type).toBe('rook')
    expect(next.board[7][4]).toBeNull()
    expect(next.board[7][7]).toBeNull()
  })

  test('white queenside castling', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: true, whiteQueenside: true, blackKingside: true, blackQueenside: true },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    state.board[7][4] = { type: 'king', color: 'white' }
    state.board[7][0] = { type: 'rook', color: 'white' }
    state.board[0][4] = { type: 'king', color: 'black' }

    const moves = getValidMoves(state, 7, 4)
    const castleMove = moves.find(m => m.castle === 'queenside')
    expect(castleMove).toBeDefined()

    const next = applyMove(state, castleMove!)
    expect(next.board[7][2]?.type).toBe('king')
    expect(next.board[7][3]?.type).toBe('rook')
  })

  test('cannot castle through check', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: true, whiteQueenside: true, blackKingside: true, blackQueenside: true },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    state.board[7][4] = { type: 'king', color: 'white' }
    state.board[7][7] = { type: 'rook', color: 'white' }
    state.board[0][4] = { type: 'king', color: 'black' }
    // Black rook attacks f1 (square king passes through)
    state.board[0][5] = { type: 'rook', color: 'black' }

    const moves = getValidMoves(state, 7, 4)
    expect(moves.find(m => m.castle === 'kingside')).toBeUndefined()
  })

  test('cannot castle when in check', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: true, whiteQueenside: true, blackKingside: true, blackQueenside: true },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    state.board[7][4] = { type: 'king', color: 'white' }
    state.board[7][7] = { type: 'rook', color: 'white' }
    state.board[0][4] = { type: 'king', color: 'black' }
    // Black rook attacks e1 (king's square)
    state.board[0][4] = { type: 'king', color: 'black' }
    state.board[3][4] = { type: 'rook', color: 'black' }

    const moves = getValidMoves(state, 7, 4)
    expect(moves.find(m => m.castle)).toBeUndefined()
  })
})

describe('en passant', () => {
  test('white can capture en passant', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: false, whiteQueenside: false, blackKingside: false, blackQueenside: false },
      enPassantTarget: [2, 3],  // black pawn just moved d7-d5, ep target is d6
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    state.board[3][4] = { type: 'pawn', color: 'white' }  // white pawn on e5
    state.board[3][3] = { type: 'pawn', color: 'black' }  // black pawn on d5
    state.board[7][4] = { type: 'king', color: 'white' }
    state.board[0][4] = { type: 'king', color: 'black' }

    const moves = getValidMoves(state, 3, 4)
    const epMove = moves.find(m => m.enPassant)
    expect(epMove).toBeDefined()
    expect(epMove!.toRow).toBe(2)
    expect(epMove!.toCol).toBe(3)
  })

  test('en passant removes captured pawn', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: false, whiteQueenside: false, blackKingside: false, blackQueenside: false },
      enPassantTarget: [2, 3],
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    state.board[3][4] = { type: 'pawn', color: 'white' }
    state.board[3][3] = { type: 'pawn', color: 'black' }
    state.board[7][4] = { type: 'king', color: 'white' }
    state.board[0][4] = { type: 'king', color: 'black' }

    const move: Move = { fromRow: 3, fromCol: 4, toRow: 2, toCol: 3, enPassant: true }
    const next = applyMove(state, move)
    expect(next.board[3][3]).toBeNull()  // captured pawn removed
    expect(next.board[2][3]?.type).toBe('pawn')
    expect(next.board[2][3]?.color).toBe('white')
  })
})

describe('pin detection', () => {
  test('pinned piece cannot move away from pin line', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'white',
      castlingRights: { whiteKingside: false, whiteQueenside: false, blackKingside: false, blackQueenside: false },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    // White king on e1, white bishop on e3, black rook on e8 — bishop pinned
    state.board[7][4] = { type: 'king', color: 'white' }
    state.board[5][4] = { type: 'bishop', color: 'white' }
    state.board[0][4] = { type: 'rook', color: 'black' }
    state.board[0][0] = { type: 'king', color: 'black' }

    const moves = getValidMoves(state, 5, 4) // bishop is pinned
    expect(moves.length).toBe(0) // bishop can't move without exposing king
  })
})

describe('getAIMove', () => {
  test('returns a valid move', () => {
    const state = createBoard()
    state.currentPlayer = 'black'
    const move = getAIMove(state, 2)
    expect(move).not.toBeNull()
    if (move) {
      expect(move.fromRow).toBeGreaterThanOrEqual(0)
      expect(move.fromRow).toBeLessThan(8)
    }
  })

  test('captures when available', () => {
    const state: ChessState = {
      board: Array.from({ length: 8 }, () => Array(8).fill(null)),
      currentPlayer: 'black',
      castlingRights: { whiteKingside: false, whiteQueenside: false, blackKingside: false, blackQueenside: false },
      enPassantTarget: null,
      halfMoveClock: 0,
      moveHistory: [],
      capturedPieces: { white: [], black: [] },
    }
    state.board[4][4] = { type: 'queen', color: 'white' }  // free queen
    state.board[3][3] = { type: 'pawn', color: 'black' }   // can capture
    state.board[7][4] = { type: 'king', color: 'white' }
    state.board[0][4] = { type: 'king', color: 'black' }

    const move = getAIMove(state, 2)
    expect(move).not.toBeNull()
    // AI should capture the queen
    expect(move!.toRow).toBe(4)
    expect(move!.toCol).toBe(4)
  })
})
