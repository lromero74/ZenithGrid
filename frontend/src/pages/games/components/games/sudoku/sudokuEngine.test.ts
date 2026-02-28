/**
 * Tests for Sudoku game engine.
 */

import { describe, test, expect } from 'vitest'
import {
  createEmptyBoard,
  isValidPlacement,
  solveSudoku,
  generatePuzzle,
  getConflicts,
  getPeers,
} from './sudokuEngine'

describe('createEmptyBoard', () => {
  test('creates 9x9 board of zeros', () => {
    const board = createEmptyBoard()
    expect(board).toHaveLength(9)
    board.forEach(row => {
      expect(row).toHaveLength(9)
      row.forEach(cell => expect(cell).toBe(0))
    })
  })
})

describe('isValidPlacement', () => {
  test('valid placement in empty board', () => {
    const board = createEmptyBoard()
    expect(isValidPlacement(board, 0, 0, 5)).toBe(true)
  })

  test('invalid: same number in row', () => {
    const board = createEmptyBoard()
    board[0][3] = 5
    expect(isValidPlacement(board, 0, 0, 5)).toBe(false)
  })

  test('invalid: same number in column', () => {
    const board = createEmptyBoard()
    board[3][0] = 5
    expect(isValidPlacement(board, 0, 0, 5)).toBe(false)
  })

  test('invalid: same number in 3x3 box', () => {
    const board = createEmptyBoard()
    board[1][1] = 5
    expect(isValidPlacement(board, 0, 0, 5)).toBe(false)
  })

  test('valid: same number in different box', () => {
    const board = createEmptyBoard()
    board[3][3] = 5 // different box
    expect(isValidPlacement(board, 0, 0, 5)).toBe(true)
  })
})

describe('solveSudoku', () => {
  test('solves an empty board', () => {
    const board = createEmptyBoard()
    const solved = solveSudoku(board)
    expect(solved).not.toBeNull()
    // Verify all rows, cols, boxes are valid
    if (solved) {
      for (let r = 0; r < 9; r++) {
        const rowSet = new Set(solved[r])
        expect(rowSet.size).toBe(9)
        expect(rowSet.has(0)).toBe(false)
      }
    }
  })

  test('solves a partial board', () => {
    const board = createEmptyBoard()
    board[0] = [5, 3, 0, 0, 7, 0, 0, 0, 0]
    board[1] = [6, 0, 0, 1, 9, 5, 0, 0, 0]
    board[2] = [0, 9, 8, 0, 0, 0, 0, 6, 0]
    board[3] = [8, 0, 0, 0, 6, 0, 0, 0, 3]
    board[4] = [4, 0, 0, 8, 0, 3, 0, 0, 1]
    board[5] = [7, 0, 0, 0, 2, 0, 0, 0, 6]
    board[6] = [0, 6, 0, 0, 0, 0, 2, 8, 0]
    board[7] = [0, 0, 0, 4, 1, 9, 0, 0, 5]
    board[8] = [0, 0, 0, 0, 8, 0, 0, 7, 9]

    const solved = solveSudoku(board)
    expect(solved).not.toBeNull()
    expect(solved![0][0]).toBe(5) // given
    expect(solved![0][2]).not.toBe(0) // filled
  })

  test('returns null for unsolvable board', () => {
    const board = createEmptyBoard()
    board[0][0] = 1
    board[0][1] = 1 // duplicate in row → unsolvable
    expect(solveSudoku(board)).toBeNull()
  })
})

describe('generatePuzzle', () => {
  test('generates puzzle with correct number of givens (easy)', () => {
    const { puzzle, solution } = generatePuzzle('easy')
    const givens = puzzle.flat().filter(v => v !== 0).length
    expect(givens).toBeGreaterThanOrEqual(36)
    expect(givens).toBeLessThanOrEqual(45)

    // Solution should be fully filled
    expect(solution.flat().every(v => v > 0)).toBe(true)
  })

  test('generates puzzle with fewer givens for hard', () => {
    const { puzzle } = generatePuzzle('hard')
    const givens = puzzle.flat().filter(v => v !== 0).length
    expect(givens).toBeGreaterThanOrEqual(27)
    expect(givens).toBeLessThanOrEqual(35)
  })

  test('puzzle cells are subset of solution', () => {
    const { puzzle, solution } = generatePuzzle('medium')
    for (let r = 0; r < 9; r++) {
      for (let c = 0; c < 9; c++) {
        if (puzzle[r][c] !== 0) {
          expect(puzzle[r][c]).toBe(solution[r][c])
        }
      }
    }
  })
})

describe('getConflicts', () => {
  test('returns empty for valid placement', () => {
    const board = createEmptyBoard()
    board[0][0] = 5
    expect(getConflicts(board, 0, 0)).toHaveLength(0)
  })

  test('returns conflicts for duplicate in row', () => {
    const board = createEmptyBoard()
    board[0][0] = 5
    board[0][5] = 5
    const conflicts = getConflicts(board, 0, 0)
    expect(conflicts.some(([r, c]) => r === 0 && c === 5)).toBe(true)
  })

  test('returns conflicts for duplicate in column', () => {
    const board = createEmptyBoard()
    board[0][0] = 5
    board[5][0] = 5
    const conflicts = getConflicts(board, 0, 0)
    expect(conflicts.some(([r, c]) => r === 5 && c === 0)).toBe(true)
  })

  test('returns conflicts for duplicate in box', () => {
    const board = createEmptyBoard()
    board[0][0] = 5
    board[2][2] = 5
    const conflicts = getConflicts(board, 0, 0)
    expect(conflicts.some(([r, c]) => r === 2 && c === 2)).toBe(true)
  })
})

describe('getPeers', () => {
  test('returns 20 peers for any cell', () => {
    const peers = getPeers(4, 4)
    expect(peers).toHaveLength(20)
  })

  test('does not include the cell itself', () => {
    const peers = getPeers(4, 4)
    expect(peers.some(([r, c]) => r === 4 && c === 4)).toBe(false)
  })

  test('includes row, column, and box peers', () => {
    const peers = getPeers(0, 0)
    // Row peers
    expect(peers.some(([r, c]) => r === 0 && c === 8)).toBe(true)
    // Column peers
    expect(peers.some(([r, c]) => r === 8 && c === 0)).toBe(true)
    // Box peers
    expect(peers.some(([r, c]) => r === 2 && c === 2)).toBe(true)
  })
})
