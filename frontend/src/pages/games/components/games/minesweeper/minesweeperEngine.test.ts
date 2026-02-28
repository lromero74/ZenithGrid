/**
 * Tests for Minesweeper game engine.
 */

import { describe, test, expect } from 'vitest'
import {
  generateBoard,
  revealCell,
  toggleFlag,
  checkWin,
  countAdjacentMines,
  getAdjacentCells,
} from './minesweeperEngine'

describe('generateBoard', () => {
  test('creates board with correct dimensions', () => {
    const board = generateBoard(9, 9, 10, 0, 0)
    expect(board).toHaveLength(9)
    board.forEach(row => expect(row).toHaveLength(9))
  })

  test('places correct number of mines', () => {
    const board = generateBoard(9, 9, 10, 0, 0)
    const mineCount = board.flat().filter(c => c.isMine).length
    expect(mineCount).toBe(10)
  })

  test('safe cell and neighbors have no mines', () => {
    const board = generateBoard(9, 9, 10, 4, 4)
    // Center cell safe
    expect(board[4][4].isMine).toBe(false)
    // All neighbors safe
    for (let dr = -1; dr <= 1; dr++) {
      for (let dc = -1; dc <= 1; dc++) {
        expect(board[4 + dr][4 + dc].isMine).toBe(false)
      }
    }
  })

  test('all cells start hidden and unflagged', () => {
    const board = generateBoard(9, 9, 10, 0, 0)
    board.flat().forEach(cell => {
      expect(cell.isRevealed).toBe(false)
      expect(cell.isFlagged).toBe(false)
    })
  })

  test('adjacent counts are correct', () => {
    const board = generateBoard(9, 9, 10, 0, 0)
    for (let r = 0; r < 9; r++) {
      for (let c = 0; c < 9; c++) {
        if (!board[r][c].isMine) {
          const expected = countAdjacentMines(board, r, c)
          expect(board[r][c].adjacentMines).toBe(expected)
        }
      }
    }
  })
})

describe('getAdjacentCells', () => {
  test('returns 8 neighbors for center cell', () => {
    const adj = getAdjacentCells(4, 4, 9, 9)
    expect(adj).toHaveLength(8)
  })

  test('returns 3 neighbors for corner cell', () => {
    const adj = getAdjacentCells(0, 0, 9, 9)
    expect(adj).toHaveLength(3)
  })

  test('returns 5 neighbors for edge cell', () => {
    const adj = getAdjacentCells(0, 4, 9, 9)
    expect(adj).toHaveLength(5)
  })
})

describe('countAdjacentMines', () => {
  test('counts mines around a cell', () => {
    const board = generateBoard(9, 9, 0, 0, 0) // no mines
    // Manually place mines around (4,4)
    board[3][3].isMine = true
    board[3][4].isMine = true
    expect(countAdjacentMines(board, 4, 4)).toBe(2)
  })
})

describe('revealCell', () => {
  test('reveals a non-mine cell', () => {
    const board = generateBoard(9, 9, 0, 0, 0) // no mines
    const result = revealCell(board, 4, 4)
    expect(result.board[4][4].isRevealed).toBe(true)
    expect(result.hitMine).toBe(false)
  })

  test('returns hitMine=true when revealing a mine', () => {
    const board = generateBoard(9, 9, 0, 0, 0)
    board[4][4].isMine = true
    const result = revealCell(board, 4, 4)
    expect(result.hitMine).toBe(true)
  })

  test('does not reveal flagged cell', () => {
    const board = generateBoard(9, 9, 0, 0, 0)
    board[4][4].isFlagged = true
    const result = revealCell(board, 4, 4)
    expect(result.board[4][4].isRevealed).toBe(false)
  })

  test('does not re-reveal already revealed cell', () => {
    const board = generateBoard(9, 9, 0, 0, 0)
    board[4][4].isRevealed = true
    const result = revealCell(board, 4, 4)
    expect(result.board[4][4].isRevealed).toBe(true)
  })

  test('flood fills blank cells (adjacentMines=0)', () => {
    // Board with no mines → all cells are blank → should reveal everything
    const board = generateBoard(5, 5, 0, 0, 0)
    const result = revealCell(board, 2, 2)
    const revealedCount = result.board.flat().filter(c => c.isRevealed).length
    expect(revealedCount).toBe(25) // all cells revealed
  })
})

describe('toggleFlag', () => {
  test('flags a hidden cell', () => {
    const board = generateBoard(9, 9, 0, 0, 0)
    const result = toggleFlag(board, 4, 4)
    expect(result[4][4].isFlagged).toBe(true)
  })

  test('unflags a flagged cell', () => {
    const board = generateBoard(9, 9, 0, 0, 0)
    board[4][4].isFlagged = true
    const result = toggleFlag(board, 4, 4)
    expect(result[4][4].isFlagged).toBe(false)
  })

  test('does not flag a revealed cell', () => {
    const board = generateBoard(9, 9, 0, 0, 0)
    board[4][4].isRevealed = true
    const result = toggleFlag(board, 4, 4)
    expect(result[4][4].isFlagged).toBe(false)
  })
})

describe('checkWin', () => {
  test('returns true when all non-mine cells revealed', () => {
    const board = generateBoard(3, 3, 1, 0, 0)
    // Reveal all non-mine cells
    board.flat().forEach(cell => {
      if (!cell.isMine) cell.isRevealed = true
    })
    expect(checkWin(board)).toBe(true)
  })

  test('returns false when some non-mine cells hidden', () => {
    const board = generateBoard(3, 3, 1, 0, 0)
    expect(checkWin(board)).toBe(false)
  })
})
