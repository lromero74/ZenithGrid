/**
 * Tests for Checkers game engine.
 */

import { describe, test, expect } from 'vitest'
import {
  createBoard, getValidMoves, getCaptureMoves, getAllMoves,
  applyMove, promoteKings, checkGameOver, getAIMove, isKingRow,
  type Board, type Player, BOARD_SIZE,
} from './checkersEngine'

/** Helper: create an empty board. */
function emptyBoard(): Board {
  return Array.from({ length: BOARD_SIZE }, () => Array(BOARD_SIZE).fill(null))
}

/** Helper: place a piece on a board. */
function placePiece(board: Board, row: number, col: number, player: Player, isKing = false): Board {
  const b = board.map(r => [...r])
  b[row][col] = { player, isKing }
  return b
}

describe('createBoard', () => {
  test('creates 8x8 board', () => {
    const board = createBoard()
    expect(board).toHaveLength(BOARD_SIZE)
    board.forEach(row => expect(row).toHaveLength(BOARD_SIZE))
  })

  test('places 12 red pieces on rows 0-2 (dark squares)', () => {
    const board = createBoard()
    let count = 0
    for (let r = 0; r < 3; r++) {
      for (let c = 0; c < BOARD_SIZE; c++) {
        if ((r + c) % 2 === 1) {
          expect(board[r][c]).toEqual({ player: 'red', isKing: false })
          count++
        } else {
          expect(board[r][c]).toBeNull()
        }
      }
    }
    expect(count).toBe(12)
  })

  test('places 12 black pieces on rows 5-7 (dark squares)', () => {
    const board = createBoard()
    let count = 0
    for (let r = 5; r < 8; r++) {
      for (let c = 0; c < BOARD_SIZE; c++) {
        if ((r + c) % 2 === 1) {
          expect(board[r][c]).toEqual({ player: 'black', isKing: false })
          count++
        } else {
          expect(board[r][c]).toBeNull()
        }
      }
    }
    expect(count).toBe(12)
  })

  test('middle rows (3-4) are empty', () => {
    const board = createBoard()
    for (let r = 3; r < 5; r++) {
      for (let c = 0; c < BOARD_SIZE; c++) {
        expect(board[r][c]).toBeNull()
      }
    }
  })
})

describe('getValidMoves', () => {
  test('red regular piece moves down (increasing row)', () => {
    let board = emptyBoard()
    board = placePiece(board, 2, 3, 'red')
    const moves = getValidMoves(board, 2, 3)
    const targets = moves.map(m => m.to)
    expect(targets).toContainEqual([3, 2])
    expect(targets).toContainEqual([3, 4])
    expect(targets).toHaveLength(2)
  })

  test('black regular piece moves up (decreasing row)', () => {
    let board = emptyBoard()
    board = placePiece(board, 5, 4, 'black')
    const moves = getValidMoves(board, 5, 4)
    const targets = moves.map(m => m.to)
    expect(targets).toContainEqual([4, 3])
    expect(targets).toContainEqual([4, 5])
    expect(targets).toHaveLength(2)
  })

  test('king can move in all 4 diagonals', () => {
    let board = emptyBoard()
    board = placePiece(board, 4, 3, 'red', true)
    const moves = getValidMoves(board, 4, 3)
    const targets = moves.map(m => m.to)
    expect(targets).toContainEqual([3, 2])
    expect(targets).toContainEqual([3, 4])
    expect(targets).toContainEqual([5, 2])
    expect(targets).toContainEqual([5, 4])
    expect(targets).toHaveLength(4)
  })

  test('blocked by own pieces', () => {
    let board = emptyBoard()
    board = placePiece(board, 2, 3, 'red')
    board = placePiece(board, 3, 4, 'red')
    const moves = getValidMoves(board, 2, 3)
    const targets = moves.map(m => m.to)
    expect(targets).toContainEqual([3, 2])
    expect(targets).not.toContainEqual([3, 4])
    expect(targets).toHaveLength(1)
  })

  test('blocked by edge of board', () => {
    let board = emptyBoard()
    board = placePiece(board, 3, 0, 'red')
    const moves = getValidMoves(board, 3, 0)
    const targets = moves.map(m => m.to)
    expect(targets).toContainEqual([4, 1])
    expect(targets).toHaveLength(1)
  })

  test('empty square returns empty array', () => {
    const board = emptyBoard()
    const moves = getValidMoves(board, 3, 3)
    expect(moves).toEqual([])
  })
})

describe('getCaptureMoves', () => {
  test('single jump over opponent', () => {
    let board = emptyBoard()
    board = placePiece(board, 2, 3, 'red')
    board = placePiece(board, 3, 4, 'black')
    const captures = getCaptureMoves(board, 2, 3)
    expect(captures).toHaveLength(1)
    expect(captures[0].to).toEqual([4, 5])
    expect(captures[0].captures).toContainEqual([3, 4])
  })

  test('multi-jump chain', () => {
    let board = emptyBoard()
    board = placePiece(board, 0, 1, 'red')
    board = placePiece(board, 1, 2, 'black')
    board = placePiece(board, 3, 4, 'black')
    const captures = getCaptureMoves(board, 0, 1)
    // Should find multi-jump: (0,1) -> (2,3) -> (4,5)
    const multiJump = captures.find(m => m.captures.length === 2)
    expect(multiJump).toBeDefined()
    expect(multiJump!.to).toEqual([4, 5])
    expect(multiJump!.captures).toContainEqual([1, 2])
    expect(multiJump!.captures).toContainEqual([3, 4])
  })

  test('king backward capture', () => {
    let board = emptyBoard()
    board = placePiece(board, 4, 3, 'red', true)
    board = placePiece(board, 3, 2, 'black')
    const captures = getCaptureMoves(board, 4, 3)
    const backward = captures.find(m => m.to[0] === 2 && m.to[1] === 1)
    expect(backward).toBeDefined()
    expect(backward!.captures).toContainEqual([3, 2])
  })

  test('no capture over own piece', () => {
    let board = emptyBoard()
    board = placePiece(board, 2, 3, 'red')
    board = placePiece(board, 3, 4, 'red')
    const captures = getCaptureMoves(board, 2, 3)
    expect(captures).toHaveLength(0)
  })

  test('no capture when landing square is occupied', () => {
    let board = emptyBoard()
    board = placePiece(board, 2, 3, 'red')
    board = placePiece(board, 3, 4, 'black')
    board = placePiece(board, 4, 5, 'black') // landing spot blocked
    const captures = getCaptureMoves(board, 2, 3)
    // Can't jump to (4,5) because it's occupied
    const jumpTo45 = captures.find(m => m.to[0] === 4 && m.to[1] === 5)
    expect(jumpTo45).toBeUndefined()
  })
})

describe('getAllMoves', () => {
  test('returns only captures when captures available (mandatory capture)', () => {
    let board = emptyBoard()
    board = placePiece(board, 2, 3, 'red')
    board = placePiece(board, 3, 4, 'black')
    const moves = getAllMoves(board, 'red')
    // All returned moves should be captures
    expect(moves.length).toBeGreaterThan(0)
    moves.forEach(m => expect(m.captures.length).toBeGreaterThan(0))
  })

  test('returns regular moves when no captures available', () => {
    let board = emptyBoard()
    board = placePiece(board, 2, 3, 'red')
    const moves = getAllMoves(board, 'red')
    expect(moves.length).toBeGreaterThan(0)
    moves.forEach(m => expect(m.captures).toHaveLength(0))
  })

  test('returns empty array when no moves available', () => {
    let board = emptyBoard()
    // Red piece stuck in corner, blocked
    board = placePiece(board, 7, 0, 'red')
    const moves = getAllMoves(board, 'red')
    expect(moves).toHaveLength(0)
  })
})

describe('applyMove', () => {
  test('piece moves to new position', () => {
    let board = emptyBoard()
    board = placePiece(board, 2, 3, 'red')
    const move = { from: [2, 3] as [number, number], to: [3, 4] as [number, number], captures: [] }
    const newBoard = applyMove(board, move)
    expect(newBoard[2][3]).toBeNull()
    expect(newBoard[3][4]).toEqual({ player: 'red', isKing: false })
  })

  test('captured pieces are removed', () => {
    let board = emptyBoard()
    board = placePiece(board, 2, 3, 'red')
    board = placePiece(board, 3, 4, 'black')
    const move = {
      from: [2, 3] as [number, number],
      to: [4, 5] as [number, number],
      captures: [[3, 4] as [number, number]],
    }
    const newBoard = applyMove(board, move)
    expect(newBoard[3][4]).toBeNull() // captured piece removed
    expect(newBoard[4][5]).toEqual({ player: 'red', isKing: false })
    expect(newBoard[2][3]).toBeNull()
  })

  test('does not mutate original board', () => {
    let board = emptyBoard()
    board = placePiece(board, 2, 3, 'red')
    const move = { from: [2, 3] as [number, number], to: [3, 4] as [number, number], captures: [] }
    applyMove(board, move)
    expect(board[2][3]).toEqual({ player: 'red', isKing: false })
  })
})

describe('isKingRow / promoteKings', () => {
  test('row 7 is king row for red', () => {
    expect(isKingRow(7, 'red')).toBe(true)
    expect(isKingRow(6, 'red')).toBe(false)
  })

  test('row 0 is king row for black', () => {
    expect(isKingRow(0, 'black')).toBe(true)
    expect(isKingRow(1, 'black')).toBe(false)
  })

  test('red piece on row 7 gets promoted to king', () => {
    let board = emptyBoard()
    board = placePiece(board, 7, 2, 'red', false)
    const promoted = promoteKings(board)
    expect(promoted[7][2]).toEqual({ player: 'red', isKing: true })
  })

  test('black piece on row 0 gets promoted to king', () => {
    let board = emptyBoard()
    board = placePiece(board, 0, 1, 'black', false)
    const promoted = promoteKings(board)
    expect(promoted[0][1]).toEqual({ player: 'black', isKing: true })
  })

  test('piece not on king row stays regular', () => {
    let board = emptyBoard()
    board = placePiece(board, 3, 2, 'red', false)
    const promoted = promoteKings(board)
    expect(promoted[3][2]).toEqual({ player: 'red', isKing: false })
  })
})

describe('checkGameOver', () => {
  test('returns "black" when red has no pieces', () => {
    let board = emptyBoard()
    board = placePiece(board, 5, 4, 'black')
    expect(checkGameOver(board)).toBe('black')
  })

  test('returns "red" when black has no pieces', () => {
    let board = emptyBoard()
    board = placePiece(board, 2, 3, 'red')
    expect(checkGameOver(board)).toBe('red')
  })

  test('returns player when opponent has no valid moves', () => {
    let board = emptyBoard()
    // Black piece stuck at edge with no moves
    board = placePiece(board, 0, 7, 'black')
    board = placePiece(board, 3, 2, 'red')
    // Black at (0,7) can only move up (decreasing row) but is at row 0, so no moves
    expect(checkGameOver(board)).toBe('red')
  })

  test('returns null when game continues', () => {
    const board = createBoard()
    expect(checkGameOver(board)).toBeNull()
  })
})

describe('getAIMove', () => {
  test('returns a valid move from getAllMoves', () => {
    const board = createBoard()
    const allMoves = getAllMoves(board, 'black')
    const aiMove = getAIMove(board, 'black', 2)
    expect(aiMove).not.toBeNull()
    // The AI move should be one of the valid moves
    const match = allMoves.find(m =>
      m.from[0] === aiMove!.from[0] && m.from[1] === aiMove!.from[1] &&
      m.to[0] === aiMove!.to[0] && m.to[1] === aiMove!.to[1]
    )
    expect(match).toBeDefined()
  })

  test('takes captures when available', () => {
    let board = emptyBoard()
    board = placePiece(board, 4, 3, 'black')
    board = placePiece(board, 3, 2, 'red')
    const aiMove = getAIMove(board, 'black', 2)
    expect(aiMove).not.toBeNull()
    expect(aiMove!.captures.length).toBeGreaterThan(0)
  })

  test('returns null when no moves available', () => {
    let board = emptyBoard()
    // Black has no pieces
    board = placePiece(board, 3, 2, 'red')
    const aiMove = getAIMove(board, 'black', 2)
    expect(aiMove).toBeNull()
  })
})
