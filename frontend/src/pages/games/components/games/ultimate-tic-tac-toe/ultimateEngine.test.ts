/**
 * Tests for Ultimate Tic-Tac-Toe engine.
 */

import { describe, test, expect } from 'vitest'
import {
  createBoards,
  createMetaBoard,
  checkSubBoardWinner,
  checkMetaWinner,
  getActiveBoard,
  getValidMoves,
  makeMove,
  type SubBoard,
  type Player,
} from './ultimateEngine'

describe('createBoards', () => {
  test('creates 9 empty sub-boards', () => {
    const boards = createBoards()
    expect(boards).toHaveLength(9)
    boards.forEach(board => {
      expect(board).toHaveLength(9)
      board.forEach(cell => expect(cell).toBeNull())
    })
  })
})

describe('createMetaBoard', () => {
  test('creates empty meta board', () => {
    const meta = createMetaBoard()
    expect(meta).toHaveLength(9)
    meta.forEach(cell => expect(cell).toBeNull())
  })
})

describe('checkSubBoardWinner', () => {
  test('detects horizontal win', () => {
    const board: SubBoard = ['X', 'X', 'X', null, null, null, null, null, null]
    expect(checkSubBoardWinner(board)).toBe('X')
  })

  test('detects vertical win', () => {
    const board: SubBoard = ['O', null, null, 'O', null, null, 'O', null, null]
    expect(checkSubBoardWinner(board)).toBe('O')
  })

  test('detects diagonal win', () => {
    const board: SubBoard = ['X', null, null, null, 'X', null, null, null, 'X']
    expect(checkSubBoardWinner(board)).toBe('X')
  })

  test('returns null for no winner', () => {
    const board: SubBoard = ['X', 'O', 'X', null, null, null, null, null, null]
    expect(checkSubBoardWinner(board)).toBeNull()
  })

  test('returns draw for full board no winner', () => {
    const board: SubBoard = ['X', 'O', 'X', 'X', 'O', 'O', 'O', 'X', 'X']
    expect(checkSubBoardWinner(board)).toBe('draw')
  })
})

describe('checkMetaWinner', () => {
  test('detects meta winner horizontal', () => {
    const meta: (Player | 'draw' | null)[] = ['X', 'X', 'X', null, null, null, null, null, null]
    expect(checkMetaWinner(meta)).toBe('X')
  })

  test('returns null when no meta winner', () => {
    const meta: (Player | 'draw' | null)[] = ['X', 'O', null, null, null, null, null, null, null]
    expect(checkMetaWinner(meta)).toBeNull()
  })

  test('draws are not counted as wins', () => {
    const meta: (Player | 'draw' | null)[] = ['draw', 'draw', 'draw', null, null, null, null, null, null]
    expect(checkMetaWinner(meta)).toBeNull()
  })
})

describe('getActiveBoard', () => {
  test('returns board index from last move cell', () => {
    // Last move was in cell 4 of some board → next must play in board 4
    expect(getActiveBoard(4)).toBe(4)
  })

  test('returns null for first move', () => {
    expect(getActiveBoard(null)).toBeNull()
  })
})

describe('getValidMoves', () => {
  test('all moves valid on first turn', () => {
    const boards = createBoards()
    const meta = createMetaBoard()
    const moves = getValidMoves(boards, meta, null)
    expect(moves).toHaveLength(81) // 9 boards × 9 cells
  })

  test('restricts to active board', () => {
    const boards = createBoards()
    const meta = createMetaBoard()
    const moves = getValidMoves(boards, meta, 4)
    expect(moves).toHaveLength(9) // only board 4
    moves.forEach(([b]) => expect(b).toBe(4))
  })

  test('allows any board when sent to completed board', () => {
    const boards = createBoards()
    const meta = createMetaBoard()
    meta[4] = 'X' // board 4 is won
    const moves = getValidMoves(boards, meta, 4)
    // Should get moves from all incomplete boards
    expect(moves.length).toBeGreaterThan(9)
  })

  test('excludes occupied cells', () => {
    const boards = createBoards()
    const meta = createMetaBoard()
    boards[4][0] = 'X'
    boards[4][1] = 'O'
    const moves = getValidMoves(boards, meta, 4)
    expect(moves).toHaveLength(7) // 9 - 2 occupied
  })
})

describe('makeMove', () => {
  test('places piece and returns new state', () => {
    const boards = createBoards()
    const meta = createMetaBoard()
    const result = makeMove(boards, meta, 0, 4, 'X')
    expect(result.boards[0][4]).toBe('X')
    expect(result.nextActiveBoard).toBe(4)
  })

  test('does not mutate original boards', () => {
    const boards = createBoards()
    const meta = createMetaBoard()
    makeMove(boards, meta, 0, 4, 'X')
    expect(boards[0][4]).toBeNull()
  })

  test('updates meta when sub-board is won', () => {
    const boards = createBoards()
    const meta = createMetaBoard()
    boards[0][0] = 'X'
    boards[0][1] = 'X'
    // Place X at [0][2] to win board 0
    const result = makeMove(boards, meta, 0, 2, 'X')
    expect(result.meta[0]).toBe('X')
  })
})
