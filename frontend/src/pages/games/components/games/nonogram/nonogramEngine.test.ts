/**
 * Tests for Nonogram (Picross) game engine.
 */

import { describe, test, expect } from 'vitest'
import {
  generateClues,
  validateRow,
  validateColumn,
  isPuzzleComplete,
  type CellState,
  type Grid,
} from './nonogramEngine'

describe('generateClues', () => {
  test('generates row clues from solution', () => {
    const solution = [
      [1, 1, 0, 1, 1],
      [0, 0, 0, 0, 0],
      [1, 1, 1, 1, 1],
    ]
    const { rowClues } = generateClues(solution)
    expect(rowClues[0]).toEqual([2, 2])
    expect(rowClues[1]).toEqual([0])
    expect(rowClues[2]).toEqual([5])
  })

  test('generates column clues from solution', () => {
    const solution = [
      [1, 0, 1],
      [1, 0, 0],
      [1, 0, 1],
    ]
    const { colClues } = generateClues(solution)
    expect(colClues[0]).toEqual([3])
    expect(colClues[1]).toEqual([0])
    expect(colClues[2]).toEqual([1, 1])
  })

  test('handles all-empty row', () => {
    const solution = [[0, 0, 0]]
    const { rowClues } = generateClues(solution)
    expect(rowClues[0]).toEqual([0])
  })

  test('handles all-filled row', () => {
    const solution = [[1, 1, 1, 1]]
    const { rowClues } = generateClues(solution)
    expect(rowClues[0]).toEqual([4])
  })

  test('handles single cell filled', () => {
    const solution = [[0, 1, 0]]
    const { rowClues } = generateClues(solution)
    expect(rowClues[0]).toEqual([1])
  })
})

describe('validateRow', () => {
  test('valid row matches clues', () => {
    const row: CellState[] = ['filled', 'filled', 'empty', 'filled']
    expect(validateRow(row, [2, 1])).toBe(true)
  })

  test('invalid row does not match clues', () => {
    const row: CellState[] = ['filled', 'empty', 'empty', 'filled']
    expect(validateRow(row, [2, 1])).toBe(false)
  })

  test('empty row matches [0] clue', () => {
    const row: CellState[] = ['empty', 'empty', 'empty']
    expect(validateRow(row, [0])).toBe(true)
  })

  test('full row matches [n] clue', () => {
    const row: CellState[] = ['filled', 'filled', 'filled']
    expect(validateRow(row, [3])).toBe(true)
  })

  test('row with unknowns treated as empty for validation', () => {
    const row: CellState[] = ['filled', 'unknown', 'filled']
    // unknowns are empty for validation → [1, 1]
    expect(validateRow(row, [1, 1])).toBe(true)
  })
})

describe('validateColumn', () => {
  test('valid column matches clues', () => {
    const grid: Grid = [
      ['filled', 'empty'],
      ['filled', 'empty'],
      ['empty', 'filled'],
    ]
    expect(validateColumn(grid, 0, [2])).toBe(true)
    expect(validateColumn(grid, 1, [1])).toBe(true)
  })

  test('invalid column does not match', () => {
    const grid: Grid = [
      ['filled', 'empty'],
      ['empty', 'empty'],
      ['filled', 'empty'],
    ]
    expect(validateColumn(grid, 0, [2])).toBe(false)
  })
})

describe('isPuzzleComplete', () => {
  test('returns true when all rows and cols match', () => {
    const grid: Grid = [
      ['filled', 'empty', 'filled'],
      ['empty', 'empty', 'empty'],
      ['filled', 'filled', 'filled'],
    ]
    const rowClues = [[1, 1], [0], [3]]
    const colClues = [[1, 1], [1], [1, 1]]
    expect(isPuzzleComplete(grid, rowClues, colClues)).toBe(true)
  })

  test('returns false when incomplete', () => {
    const grid: Grid = [
      ['filled', 'empty', 'unknown'],
      ['empty', 'empty', 'empty'],
      ['filled', 'filled', 'filled'],
    ]
    const rowClues = [[1, 1], [0], [3]]
    const colClues = [[1, 1], [1], [1, 1]]
    expect(isPuzzleComplete(grid, rowClues, colClues)).toBe(false)
  })
})
