/**
 * Tests for 2048 game engine.
 */

import { describe, test, expect } from 'vitest'
import {
  createBoard,
  slideRow,
  move,
  addRandomTile,
  hasValidMoves,
  isGameWon,
  countEmpty,
  type Board,
} from './twenFoEiEngine'

describe('createBoard', () => {
  test('creates 4x4 board of zeros', () => {
    const board = createBoard()
    expect(board).toHaveLength(4)
    board.forEach(row => {
      expect(row).toHaveLength(4)
      row.forEach(cell => expect(cell).toBe(0))
    })
  })
})

describe('slideRow', () => {
  test('slides tiles left and merges', () => {
    expect(slideRow([2, 2, 0, 0])).toEqual({ row: [4, 0, 0, 0], score: 4 })
  })

  test('slides multiple merges', () => {
    expect(slideRow([2, 2, 4, 4])).toEqual({ row: [4, 8, 0, 0], score: 12 })
  })

  test('does not merge already-merged tile', () => {
    // [2, 2, 2, 0] → first two merge to 4, third 2 stays separate
    expect(slideRow([2, 2, 2, 0])).toEqual({ row: [4, 2, 0, 0], score: 4 })
  })

  test('handles empty row', () => {
    expect(slideRow([0, 0, 0, 0])).toEqual({ row: [0, 0, 0, 0], score: 0 })
  })

  test('handles full row no merge', () => {
    expect(slideRow([2, 4, 8, 16])).toEqual({ row: [2, 4, 8, 16], score: 0 })
  })

  test('slides scattered tiles', () => {
    expect(slideRow([0, 2, 0, 2])).toEqual({ row: [4, 0, 0, 0], score: 4 })
  })

  test('slides single tile to left', () => {
    expect(slideRow([0, 0, 0, 4])).toEqual({ row: [4, 0, 0, 0], score: 0 })
  })

  test('four same tiles merge into two', () => {
    expect(slideRow([4, 4, 4, 4])).toEqual({ row: [8, 8, 0, 0], score: 16 })
  })
})

describe('move', () => {
  test('moves left', () => {
    const board: Board = [
      [0, 2, 0, 2],
      [0, 0, 0, 0],
      [4, 0, 4, 0],
      [0, 0, 0, 0],
    ]
    const result = move(board, 'left')
    expect(result.board[0]).toEqual([4, 0, 0, 0])
    expect(result.board[2]).toEqual([8, 0, 0, 0])
    expect(result.score).toBe(12)
    expect(result.moved).toBe(true)
  })

  test('moves right', () => {
    const board: Board = [
      [2, 2, 0, 0],
      [0, 0, 0, 0],
      [0, 0, 0, 0],
      [0, 0, 0, 0],
    ]
    const result = move(board, 'right')
    expect(result.board[0]).toEqual([0, 0, 0, 4])
    expect(result.score).toBe(4)
    expect(result.moved).toBe(true)
  })

  test('moves up', () => {
    const board: Board = [
      [2, 0, 0, 0],
      [2, 0, 0, 0],
      [0, 0, 0, 0],
      [0, 0, 0, 0],
    ]
    const result = move(board, 'up')
    expect(result.board[0][0]).toBe(4)
    expect(result.board[1][0]).toBe(0)
    expect(result.score).toBe(4)
    expect(result.moved).toBe(true)
  })

  test('moves down', () => {
    const board: Board = [
      [2, 0, 0, 0],
      [2, 0, 0, 0],
      [0, 0, 0, 0],
      [0, 0, 0, 0],
    ]
    const result = move(board, 'down')
    expect(result.board[3][0]).toBe(4)
    expect(result.board[0][0]).toBe(0)
    expect(result.score).toBe(4)
    expect(result.moved).toBe(true)
  })

  test('returns moved=false when nothing changes', () => {
    const board: Board = [
      [2, 4, 8, 16],
      [0, 0, 0, 0],
      [0, 0, 0, 0],
      [0, 0, 0, 0],
    ]
    const result = move(board, 'left')
    expect(result.moved).toBe(false)
  })

  test('does not mutate original board', () => {
    const board: Board = [
      [2, 2, 0, 0],
      [0, 0, 0, 0],
      [0, 0, 0, 0],
      [0, 0, 0, 0],
    ]
    move(board, 'left')
    expect(board[0]).toEqual([2, 2, 0, 0])
  })
})

describe('addRandomTile', () => {
  test('adds one tile to empty board', () => {
    const board = createBoard()
    const result = addRandomTile(board)
    const nonZero = result.flat().filter(v => v > 0)
    expect(nonZero).toHaveLength(1)
    expect([2, 4]).toContain(nonZero[0])
  })

  test('does not modify original board', () => {
    const board = createBoard()
    addRandomTile(board)
    expect(board.flat().every(v => v === 0)).toBe(true)
  })

  test('returns same board when no empty cells', () => {
    const board: Board = [
      [2, 4, 8, 16],
      [32, 64, 128, 256],
      [512, 1024, 2048, 4],
      [2, 8, 16, 32],
    ]
    const result = addRandomTile(board)
    expect(result).toEqual(board)
  })
})

describe('hasValidMoves', () => {
  test('returns true when empty cells exist', () => {
    const board: Board = [
      [2, 4, 8, 16],
      [32, 0, 128, 256],
      [512, 1024, 2048, 4],
      [2, 8, 16, 32],
    ]
    expect(hasValidMoves(board)).toBe(true)
  })

  test('returns true when horizontal merge possible', () => {
    const board: Board = [
      [2, 4, 8, 16],
      [32, 64, 64, 256],
      [512, 1024, 2048, 4],
      [2, 8, 16, 32],
    ]
    expect(hasValidMoves(board)).toBe(true)
  })

  test('returns true when vertical merge possible', () => {
    const board: Board = [
      [2, 4, 8, 16],
      [32, 4, 128, 256],
      [512, 1024, 2048, 4],
      [2, 8, 16, 32],
    ]
    expect(hasValidMoves(board)).toBe(true)
  })

  test('returns false when no moves left', () => {
    const board: Board = [
      [2, 4, 8, 16],
      [16, 8, 4, 2],
      [2, 4, 8, 16],
      [16, 8, 4, 2],
    ]
    expect(hasValidMoves(board)).toBe(false)
  })
})

describe('isGameWon', () => {
  test('returns true when 2048 tile exists', () => {
    const board: Board = [
      [2, 4, 8, 16],
      [0, 0, 2048, 0],
      [0, 0, 0, 0],
      [0, 0, 0, 0],
    ]
    expect(isGameWon(board)).toBe(true)
  })

  test('returns false when no 2048 tile', () => {
    const board: Board = [
      [2, 4, 8, 16],
      [0, 0, 1024, 0],
      [0, 0, 0, 0],
      [0, 0, 0, 0],
    ]
    expect(isGameWon(board)).toBe(false)
  })
})

describe('countEmpty', () => {
  test('counts empty cells', () => {
    const board: Board = [
      [2, 0, 0, 0],
      [0, 0, 0, 0],
      [0, 0, 4, 0],
      [0, 0, 0, 0],
    ]
    expect(countEmpty(board)).toBe(14)
  })

  test('returns 0 for full board', () => {
    const board: Board = [
      [2, 4, 8, 16],
      [32, 64, 128, 256],
      [512, 1024, 2048, 4],
      [2, 8, 16, 32],
    ]
    expect(countEmpty(board)).toBe(0)
  })
})
