/**
 * Tests for Connect Four game engine.
 */

import { describe, test, expect } from 'vitest'
import {
  createBoard,
  dropDisc,
  checkWinner,
  getValidColumns,
  isBoardFull,
  getAIMove,
  type Board,
  type Player,
  ROWS,
  COLS,
} from './connectFourEngine'

describe('createBoard', () => {
  test('creates 6x7 board of nulls', () => {
    const board = createBoard()
    expect(board).toHaveLength(ROWS)
    board.forEach(row => {
      expect(row).toHaveLength(COLS)
      row.forEach(cell => expect(cell).toBeNull())
    })
  })
})

describe('dropDisc', () => {
  test('drops disc to bottom of empty column', () => {
    const board = createBoard()
    const result = dropDisc(board, 3, 'red')
    expect(result.board[5][3]).toBe('red')
    expect(result.row).toBe(5)
  })

  test('stacks discs in same column', () => {
    let board = createBoard()
    board = dropDisc(board, 3, 'red').board
    const result = dropDisc(board, 3, 'yellow')
    expect(result.board[5][3]).toBe('red')
    expect(result.board[4][3]).toBe('yellow')
    expect(result.row).toBe(4)
  })

  test('returns row -1 for full column', () => {
    let board = createBoard()
    for (let i = 0; i < ROWS; i++) {
      board = dropDisc(board, 0, 'red').board
    }
    const result = dropDisc(board, 0, 'yellow')
    expect(result.row).toBe(-1)
  })

  test('does not mutate original board', () => {
    const board = createBoard()
    dropDisc(board, 3, 'red')
    expect(board[5][3]).toBeNull()
  })
})

describe('checkWinner', () => {
  test('detects horizontal win', () => {
    const board = createBoard()
    board[5][0] = 'red'; board[5][1] = 'red'; board[5][2] = 'red'; board[5][3] = 'red'
    const result = checkWinner(board)
    expect(result).not.toBeNull()
    expect(result!.player).toBe('red')
    expect(result!.cells).toHaveLength(4)
  })

  test('detects vertical win', () => {
    const board = createBoard()
    board[5][0] = 'yellow'; board[4][0] = 'yellow'; board[3][0] = 'yellow'; board[2][0] = 'yellow'
    const result = checkWinner(board)
    expect(result).not.toBeNull()
    expect(result!.player).toBe('yellow')
  })

  test('detects diagonal-down win', () => {
    const board = createBoard()
    board[2][0] = 'red'; board[3][1] = 'red'; board[4][2] = 'red'; board[5][3] = 'red'
    expect(checkWinner(board)!.player).toBe('red')
  })

  test('detects diagonal-up win', () => {
    const board = createBoard()
    board[5][0] = 'red'; board[4][1] = 'red'; board[3][2] = 'red'; board[2][3] = 'red'
    expect(checkWinner(board)!.player).toBe('red')
  })

  test('returns null when no winner', () => {
    const board = createBoard()
    board[5][0] = 'red'; board[5][1] = 'red'; board[5][2] = 'red'
    expect(checkWinner(board)).toBeNull()
  })

  test('returns null on empty board', () => {
    expect(checkWinner(createBoard())).toBeNull()
  })
})

describe('getValidColumns', () => {
  test('all columns valid on empty board', () => {
    expect(getValidColumns(createBoard())).toEqual([0, 1, 2, 3, 4, 5, 6])
  })

  test('excludes full columns', () => {
    let board = createBoard()
    for (let i = 0; i < ROWS; i++) {
      board = dropDisc(board, 0, 'red').board
    }
    const valid = getValidColumns(board)
    expect(valid).not.toContain(0)
    expect(valid).toHaveLength(6)
  })
})

describe('isBoardFull', () => {
  test('returns false on empty board', () => {
    expect(isBoardFull(createBoard())).toBe(false)
  })

  test('returns true when all cells filled', () => {
    const board: Board = Array.from({ length: ROWS }, () =>
      Array.from({ length: COLS }, () => 'red' as Player)
    )
    expect(isBoardFull(board)).toBe(true)
  })
})

describe('getAIMove', () => {
  test('returns a valid column', () => {
    const board = createBoard()
    const col = getAIMove(board, 'yellow', 2)
    expect(col).toBeGreaterThanOrEqual(0)
    expect(col).toBeLessThan(COLS)
    expect(getValidColumns(board)).toContain(col)
  })

  test('takes immediate winning move', () => {
    const board = createBoard()
    // Yellow has 3 in a row on bottom
    board[5][0] = 'yellow'; board[5][1] = 'yellow'; board[5][2] = 'yellow'
    const col = getAIMove(board, 'yellow', 4)
    expect(col).toBe(3) // win at column 3
  })

  test('blocks opponent winning move', () => {
    const board = createBoard()
    // Red has 3 in a row on bottom
    board[5][0] = 'red'; board[5][1] = 'red'; board[5][2] = 'red'
    const col = getAIMove(board, 'yellow', 4)
    expect(col).toBe(3) // block at column 3
  })
})
