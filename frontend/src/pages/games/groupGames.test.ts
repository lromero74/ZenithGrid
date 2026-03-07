/**
 * Tests for the groupGames utility function.
 *
 * Validates all group-by options: none, category, difficulty, A-Z, recently played.
 */

import { describe, test, expect } from 'vitest'
import { groupGames } from './groupGames'
import type { GameInfo } from './types'

const SAMPLE_GAMES: GameInfo[] = [
  { id: 'chess', name: 'Chess', description: '', icon: '', path: '/games/chess', difficulty: 'hard', sessionLength: '', category: 'strategy' },
  { id: 'snake', name: 'Snake', description: '', icon: '', path: '/games/snake', difficulty: 'easy', sessionLength: '', category: 'arcade' },
  { id: 'sudoku', name: 'Sudoku', description: '', icon: '', path: '/games/sudoku', difficulty: 'medium', sessionLength: '', category: 'puzzle' },
  { id: 'hangman', name: 'Hangman', description: '', icon: '', path: '/games/hangman', difficulty: 'easy', sessionLength: '', category: 'word' },
  { id: 'mahjong', name: 'Mahjong', description: '', icon: '', path: '/games/mahjong', difficulty: 'hard', sessionLength: '', category: 'puzzle' },
]

const CARD_GAMES: GameInfo[] = [
  { id: 'hearts', name: 'Hearts', description: '', icon: '', path: '/games/hearts', difficulty: 'hard', sessionLength: '', category: 'cards', subcategory: 'Trick-Taking' },
  { id: 'solitaire', name: 'Solitaire', description: '', icon: '', path: '/games/solitaire', difficulty: 'medium', sessionLength: '', category: 'cards', subcategory: 'Solitaire' },
  { id: 'gin-rummy', name: 'Gin Rummy', description: '', icon: '', path: '/games/gin-rummy', difficulty: 'medium', sessionLength: '', category: 'cards', subcategory: 'Rummy' },
  { id: 'blackjack', name: 'Blackjack', description: '', icon: '', path: '/games/blackjack', difficulty: 'easy', sessionLength: '', category: 'cards', subcategory: 'Casino' },
]

describe('groupGames', () => {
  test('none returns single group with empty label', () => {
    const result = groupGames(SAMPLE_GAMES, 'none')
    expect(result).toHaveLength(1)
    expect(result[0].label).toBe('')
    expect(result[0].games).toHaveLength(5)
  })

  test('none preserves original order', () => {
    const result = groupGames(SAMPLE_GAMES, 'none')
    expect(result[0].games.map(g => g.id)).toEqual(['chess', 'snake', 'sudoku', 'hangman', 'mahjong'])
  })

  test('does not mutate input array', () => {
    const original = [...SAMPLE_GAMES]
    groupGames(SAMPLE_GAMES, 'category')
    expect(SAMPLE_GAMES).toEqual(original)
  })

  test('handles empty games array', () => {
    expect(groupGames([], 'a-z')).toEqual([])
    expect(groupGames([], 'category')).toEqual([])
  })

  describe('category grouping', () => {
    test('groups by category with correct labels', () => {
      const result = groupGames(SAMPLE_GAMES, 'category')
      const labels = result.map(g => g.label)
      expect(labels).toEqual(['Arcade', 'Puzzle', 'Strategy', 'Word'])
    })

    test('sorts games alphabetically within each category', () => {
      const result = groupGames(SAMPLE_GAMES, 'category')
      const puzzleGroup = result.find(g => g.label === 'Puzzle')!
      expect(puzzleGroup.games.map(g => g.name)).toEqual(['Mahjong', 'Sudoku'])
    })

    test('isCardsView groups by subcategory instead', () => {
      const result = groupGames(CARD_GAMES, 'category', { isCardsView: true })
      const labels = result.map(g => g.label)
      expect(labels).toEqual(['Casino', 'Rummy', 'Solitaire', 'Trick-Taking'])
    })
  })

  describe('difficulty grouping', () => {
    test('groups in easy → medium → hard order', () => {
      const result = groupGames(SAMPLE_GAMES, 'difficulty')
      const labels = result.map(g => g.label)
      expect(labels).toEqual(['Easy', 'Medium', 'Hard'])
    })

    test('sorts games alphabetically within difficulty', () => {
      const result = groupGames(SAMPLE_GAMES, 'difficulty')
      const easyGroup = result.find(g => g.label === 'Easy')!
      expect(easyGroup.games.map(g => g.name)).toEqual(['Hangman', 'Snake'])
    })
  })

  describe('a-z grouping', () => {
    test('groups by first letter', () => {
      const result = groupGames(SAMPLE_GAMES, 'a-z')
      const labels = result.map(g => g.label)
      expect(labels).toEqual(['C', 'H', 'M', 'S'])
    })

    test('S group contains Snake and Sudoku sorted', () => {
      const result = groupGames(SAMPLE_GAMES, 'a-z')
      const sGroup = result.find(g => g.label === 'S')!
      expect(sGroup.games.map(g => g.name)).toEqual(['Snake', 'Sudoku'])
    })
  })

  describe('recent grouping', () => {
    test('splits into Recently Played and Everything Else', () => {
      const recentlyPlayed = { 'chess': 2000, 'snake': 3000 }
      const result = groupGames(SAMPLE_GAMES, 'recent', { recentlyPlayed })
      expect(result).toHaveLength(2)
      expect(result[0].label).toBe('Recently Played')
      expect(result[1].label).toBe('Everything Else')
    })

    test('sorts recently played by most recent first', () => {
      const recentlyPlayed = { 'chess': 2000, 'snake': 3000, 'sudoku': 1000 }
      const result = groupGames(SAMPLE_GAMES, 'recent', { recentlyPlayed })
      expect(result[0].games.map(g => g.id)).toEqual(['snake', 'chess', 'sudoku'])
    })

    test('everything else is sorted alphabetically', () => {
      const recentlyPlayed = { 'chess': 2000 }
      const result = groupGames(SAMPLE_GAMES, 'recent', { recentlyPlayed })
      const restGroup = result.find(g => g.label === 'Everything Else')!
      expect(restGroup.games.map(g => g.name)).toEqual(['Hangman', 'Mahjong', 'Snake', 'Sudoku'])
    })

    test('no recently played returns single Everything Else group', () => {
      const result = groupGames(SAMPLE_GAMES, 'recent', { recentlyPlayed: {} })
      expect(result).toHaveLength(1)
      expect(result[0].label).toBe('Everything Else')
    })

    test('all recently played returns single Recently Played group', () => {
      const recentlyPlayed: Record<string, number> = {}
      for (const g of SAMPLE_GAMES) recentlyPlayed[g.id] = Date.now()
      const result = groupGames(SAMPLE_GAMES, 'recent', { recentlyPlayed })
      expect(result).toHaveLength(1)
      expect(result[0].label).toBe('Recently Played')
    })
  })

  test('handles single game', () => {
    const single = [SAMPLE_GAMES[0]]
    const result = groupGames(single, 'category')
    expect(result).toHaveLength(1)
    expect(result[0].label).toBe('Strategy')
    expect(result[0].games).toHaveLength(1)
  })
})
