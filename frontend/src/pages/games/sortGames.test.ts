/**
 * Tests for the sortGames pure utility function.
 *
 * Validates all sort options: alphabetical, difficulty, category, recently played.
 */

import { describe, test, expect } from 'vitest'
import { sortGames } from './sortGames'
import type { GameInfo } from './types'

const SAMPLE_GAMES: GameInfo[] = [
  { id: 'chess', name: 'Chess', description: '', icon: '', path: '/games/chess', difficulty: 'hard', sessionLength: '', category: 'strategy' },
  { id: 'snake', name: 'Snake', description: '', icon: '', path: '/games/snake', difficulty: 'easy', sessionLength: '', category: 'arcade' },
  { id: 'sudoku', name: 'Sudoku', description: '', icon: '', path: '/games/sudoku', difficulty: 'medium', sessionLength: '', category: 'puzzle' },
  { id: 'hangman', name: 'Hangman', description: '', icon: '', path: '/games/hangman', difficulty: 'easy', sessionLength: '', category: 'word' },
  { id: 'mahjong', name: 'Mahjong', description: '', icon: '', path: '/games/mahjong', difficulty: 'hard', sessionLength: '', category: 'puzzle' },
]

describe('sortGames', () => {
  test('default returns same order as input', () => {
    const result = sortGames(SAMPLE_GAMES, 'default')
    expect(result.map(g => g.id)).toEqual(['chess', 'snake', 'sudoku', 'hangman', 'mahjong'])
  })

  test('default does not mutate input array', () => {
    const original = [...SAMPLE_GAMES]
    sortGames(SAMPLE_GAMES, 'default')
    expect(SAMPLE_GAMES).toEqual(original)
  })

  test('a-z sorts alphabetically by name', () => {
    const result = sortGames(SAMPLE_GAMES, 'a-z')
    expect(result.map(g => g.name)).toEqual(['Chess', 'Hangman', 'Mahjong', 'Snake', 'Sudoku'])
  })

  test('z-a sorts reverse alphabetically by name', () => {
    const result = sortGames(SAMPLE_GAMES, 'z-a')
    expect(result.map(g => g.name)).toEqual(['Sudoku', 'Snake', 'Mahjong', 'Hangman', 'Chess'])
  })

  test('difficulty sorts easy → medium → hard', () => {
    const result = sortGames(SAMPLE_GAMES, 'difficulty')
    expect(result.map(g => g.difficulty)).toEqual(['easy', 'easy', 'medium', 'hard', 'hard'])
  })

  test('category sorts alphabetically by category', () => {
    const result = sortGames(SAMPLE_GAMES, 'category')
    const categories = result.map(g => g.category)
    expect(categories).toEqual(['arcade', 'puzzle', 'puzzle', 'strategy', 'word'])
  })

  test('recent sorts by most recently played first', () => {
    const recentlyPlayed = {
      'sudoku': 1000,
      'snake': 3000,
      'chess': 2000,
    }
    const result = sortGames(SAMPLE_GAMES, 'recent', recentlyPlayed)
    // snake(3000) > chess(2000) > sudoku(1000) > hangman(0) > mahjong(0)
    expect(result[0].id).toBe('snake')
    expect(result[1].id).toBe('chess')
    expect(result[2].id).toBe('sudoku')
  })

  test('recent puts never-played games last', () => {
    const recentlyPlayed = { 'hangman': 5000 }
    const result = sortGames(SAMPLE_GAMES, 'recent', recentlyPlayed)
    expect(result[0].id).toBe('hangman')
  })

  test('recent with empty map returns original order', () => {
    const result = sortGames(SAMPLE_GAMES, 'recent', {})
    // All timestamps are 0, stable sort preserves original order
    expect(result.map(g => g.id)).toEqual(SAMPLE_GAMES.map(g => g.id))
  })

  test('does not mutate input array for any sort', () => {
    const original = SAMPLE_GAMES.map(g => g.id)
    for (const sort of ['a-z', 'z-a', 'difficulty', 'category', 'recent'] as const) {
      sortGames(SAMPLE_GAMES, sort)
      expect(SAMPLE_GAMES.map(g => g.id)).toEqual(original)
    }
  })

  test('handles empty games array', () => {
    expect(sortGames([], 'a-z')).toEqual([])
    expect(sortGames([], 'recent', { 'chess': 100 })).toEqual([])
  })

  test('handles single game', () => {
    const single = [SAMPLE_GAMES[0]]
    expect(sortGames(single, 'a-z')).toEqual(single)
  })
})
