/**
 * Tests for Tic-Tac-Toe game engine.
 *
 * Tests board logic, win detection, draw detection, and AI (minimax).
 */

import { describe, test, expect } from 'vitest'
import {
  createBoard,
  checkWinner,
  isBoardFull,
  getAIMove,
  type Board,
  type Player,
} from './ticTacToeEngine'

describe('createBoard', () => {
  test('returns a 3x3 board of nulls', () => {
    const board = createBoard()
    expect(board).toHaveLength(9)
    expect(board.every(cell => cell === null)).toBe(true)
  })

  test('returns a new array each call', () => {
    const a = createBoard()
    const b = createBoard()
    expect(a).not.toBe(b)
  })
})

describe('checkWinner', () => {
  test('detects horizontal win for X (top row)', () => {
    const board: Board = ['X', 'X', 'X', null, null, null, null, null, null]
    expect(checkWinner(board)).toEqual({ winner: 'X', line: [0, 1, 2] })
  })

  test('detects horizontal win for O (middle row)', () => {
    const board: Board = [null, null, null, 'O', 'O', 'O', null, null, null]
    expect(checkWinner(board)).toEqual({ winner: 'O', line: [3, 4, 5] })
  })

  test('detects horizontal win (bottom row)', () => {
    const board: Board = [null, null, null, null, null, null, 'X', 'X', 'X']
    expect(checkWinner(board)).toEqual({ winner: 'X', line: [6, 7, 8] })
  })

  test('detects vertical win (left column)', () => {
    const board: Board = ['O', null, null, 'O', null, null, 'O', null, null]
    expect(checkWinner(board)).toEqual({ winner: 'O', line: [0, 3, 6] })
  })

  test('detects vertical win (center column)', () => {
    const board: Board = [null, 'X', null, null, 'X', null, null, 'X', null]
    expect(checkWinner(board)).toEqual({ winner: 'X', line: [1, 4, 7] })
  })

  test('detects vertical win (right column)', () => {
    const board: Board = [null, null, 'O', null, null, 'O', null, null, 'O']
    expect(checkWinner(board)).toEqual({ winner: 'O', line: [2, 5, 8] })
  })

  test('detects diagonal win (top-left to bottom-right)', () => {
    const board: Board = ['X', null, null, null, 'X', null, null, null, 'X']
    expect(checkWinner(board)).toEqual({ winner: 'X', line: [0, 4, 8] })
  })

  test('detects diagonal win (top-right to bottom-left)', () => {
    const board: Board = [null, null, 'O', null, 'O', null, 'O', null, null]
    expect(checkWinner(board)).toEqual({ winner: 'O', line: [2, 4, 6] })
  })

  test('returns null when no winner', () => {
    const board: Board = ['X', 'O', 'X', null, null, null, null, null, null]
    expect(checkWinner(board)).toBeNull()
  })

  test('returns null on empty board', () => {
    expect(checkWinner(createBoard())).toBeNull()
  })
})

describe('isBoardFull', () => {
  test('returns false for empty board', () => {
    expect(isBoardFull(createBoard())).toBe(false)
  })

  test('returns false for partially filled board', () => {
    const board: Board = ['X', 'O', null, null, null, null, null, null, null]
    expect(isBoardFull(board)).toBe(false)
  })

  test('returns true for full board', () => {
    const board: Board = ['X', 'O', 'X', 'X', 'O', 'O', 'O', 'X', 'X']
    expect(isBoardFull(board)).toBe(true)
  })
})

describe('getAIMove (easy)', () => {
  test('returns a valid empty cell index', () => {
    const board: Board = ['X', null, null, null, null, null, null, null, null]
    const move = getAIMove(board, 'O', 'easy')
    expect(move).toBeGreaterThanOrEqual(0)
    expect(move).toBeLessThan(9)
    expect(board[move]).toBeNull()
  })

  test('returns the only available cell', () => {
    const board: Board = ['X', 'O', 'X', 'X', 'O', 'O', 'O', 'X', null]
    const move = getAIMove(board, 'O', 'easy')
    expect(move).toBe(8)
  })
})

describe('getAIMove (hard / minimax)', () => {
  test('takes winning move when available', () => {
    // O can win by playing index 5 (middle row). No other immediate win exists.
    const board: Board = [null, 'X', null, 'O', 'O', null, 'X', null, null]
    const move = getAIMove(board, 'O', 'hard')
    expect(move).toBe(5) // O completes middle row
  })

  test('blocks opponent winning move', () => {
    // X is about to win with index 2 — O must block
    const board: Board = ['X', 'X', null, 'O', null, null, null, null, null]
    const move = getAIMove(board, 'O', 'hard')
    expect(move).toBe(2)
  })

  test('returns valid move on empty board', () => {
    const move = getAIMove(createBoard(), 'X', 'hard')
    expect(move).toBeGreaterThanOrEqual(0)
    expect(move).toBeLessThan(9)
  })

  test('never loses as X (minimax is unbeatable)', () => {
    // Simulate a full game: X (minimax) vs O (minimax) should always draw
    const board = createBoard()
    let currentPlayer: Player = 'X'
    while (!checkWinner(board) && !isBoardFull(board)) {
      const move = getAIMove(board, currentPlayer, 'hard')
      board[move] = currentPlayer
      currentPlayer = currentPlayer === 'X' ? 'O' : 'X'
    }
    // Two perfect players always draw
    expect(checkWinner(board)).toBeNull()
    expect(isBoardFull(board)).toBe(true)
  })
})
