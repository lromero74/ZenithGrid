/**
 * Tests for games constants.
 *
 * Validates the game registry is complete, consistent, and well-formed.
 */

import { describe, test, expect } from 'vitest'
import { GAMES, GAME_ICONS, GAME_CATEGORIES } from './constants'
import type { GameInfo } from './types'

describe('GAMES registry', () => {
  test('contains all 11 games', () => {
    expect(GAMES).toHaveLength(11)
  })

  test('every game has a unique id', () => {
    const ids = GAMES.map((g: GameInfo) => g.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  test('every game has a unique path', () => {
    const paths = GAMES.map((g: GameInfo) => g.path)
    expect(new Set(paths).size).toBe(paths.length)
  })

  test('every game path starts with /games/', () => {
    for (const game of GAMES) {
      expect(game.path).toMatch(/^\/games\//)
    }
  })

  test('every game has a non-empty name and description', () => {
    for (const game of GAMES) {
      expect(game.name.length).toBeGreaterThan(0)
      expect(game.description.length).toBeGreaterThan(0)
    }
  })

  test('every game has a valid difficulty', () => {
    const validDifficulties = ['easy', 'medium', 'hard']
    for (const game of GAMES) {
      expect(validDifficulties).toContain(game.difficulty)
    }
  })

  test('every game has a valid category', () => {
    const validCategories = ['puzzle', 'strategy', 'arcade', 'word']
    for (const game of GAMES) {
      expect(validCategories).toContain(game.category)
    }
  })

  test('every game has a session length string', () => {
    for (const game of GAMES) {
      expect(game.sessionLength).toMatch(/\d+.*min/)
    }
  })

  test('includes expected game ids', () => {
    const ids = GAMES.map((g: GameInfo) => g.id)
    expect(ids).toContain('tic-tac-toe')
    expect(ids).toContain('connect-four')
    expect(ids).toContain('2048')
    expect(ids).toContain('minesweeper')
    expect(ids).toContain('hangman')
    expect(ids).toContain('sudoku')
    expect(ids).toContain('wordle')
    expect(ids).toContain('snake')
    expect(ids).toContain('ultimate-tic-tac-toe')
    expect(ids).toContain('mahjong')
    expect(ids).toContain('nonogram')
  })
})

describe('GAME_ICONS', () => {
  test('has an icon entry for every game icon value', () => {
    for (const game of GAMES) {
      expect(GAME_ICONS).toHaveProperty(game.icon)
    }
  })

  test('every icon entry is a valid React component', () => {
    for (const key of Object.keys(GAME_ICONS)) {
      const icon = GAME_ICONS[key]
      // Lucide icons are forwardRef objects or function components
      expect(typeof icon === 'function' || typeof icon === 'object').toBe(true)
    }
  })
})

describe('GAME_CATEGORIES', () => {
  test('contains all category labels', () => {
    const labels = GAME_CATEGORIES.map(c => c.value)
    expect(labels).toContain('all')
    expect(labels).toContain('puzzle')
    expect(labels).toContain('strategy')
    expect(labels).toContain('word')
    expect(labels).toContain('arcade')
  })

  test('each category has a label', () => {
    for (const cat of GAME_CATEGORIES) {
      expect(cat.label.length).toBeGreaterThan(0)
    }
  })
})
