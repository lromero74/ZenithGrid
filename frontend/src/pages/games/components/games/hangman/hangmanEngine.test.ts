/**
 * Tests for Hangman game engine.
 */

import { describe, test, expect } from 'vitest'
import {
  selectWord,
  getDisplayWord,
  processGuess,
  isGameWon,
  isGameLost,
  getWrongGuesses,
} from './hangmanEngine'
import { CATEGORIES, WORD_LISTS, MAX_WRONG_GUESSES } from './wordLists'

describe('selectWord', () => {
  test('returns a word from the specified category', () => {
    const word = selectWord('crypto')
    expect(WORD_LISTS.crypto).toContain(word)
  })

  test('returns a word from each category', () => {
    for (const cat of CATEGORIES) {
      const word = selectWord(cat)
      expect(WORD_LISTS[cat]).toContain(word)
    }
  })

  test('returns uppercase word', () => {
    const word = selectWord('animals')
    expect(word).toBe(word.toUpperCase())
  })
})

describe('getDisplayWord', () => {
  test('shows underscores for all letters when no guesses', () => {
    expect(getDisplayWord('HELLO', new Set())).toBe('_ _ _ _ _')
  })

  test('reveals guessed letters', () => {
    expect(getDisplayWord('HELLO', new Set(['H', 'L']))).toBe('H _ L L _')
  })

  test('reveals full word when all letters guessed', () => {
    expect(getDisplayWord('HI', new Set(['H', 'I']))).toBe('H I')
  })

  test('handles single character word', () => {
    expect(getDisplayWord('A', new Set(['A']))).toBe('A')
  })
})

describe('processGuess', () => {
  test('returns true for correct guess', () => {
    expect(processGuess('HELLO', 'H')).toBe(true)
  })

  test('returns false for incorrect guess', () => {
    expect(processGuess('HELLO', 'Z')).toBe(false)
  })

  test('is case-insensitive', () => {
    expect(processGuess('HELLO', 'h')).toBe(true)
  })
})

describe('isGameWon', () => {
  test('returns false when letters remain hidden', () => {
    expect(isGameWon('HELLO', new Set(['H', 'E']))).toBe(false)
  })

  test('returns true when all letters guessed', () => {
    expect(isGameWon('HELLO', new Set(['H', 'E', 'L', 'O']))).toBe(true)
  })

  test('returns true even with extra guesses', () => {
    expect(isGameWon('HI', new Set(['H', 'I', 'Z', 'X']))).toBe(true)
  })
})

describe('isGameLost', () => {
  test('returns false when under max wrong guesses', () => {
    expect(isGameLost(MAX_WRONG_GUESSES - 1)).toBe(false)
  })

  test('returns true at max wrong guesses', () => {
    expect(isGameLost(MAX_WRONG_GUESSES)).toBe(true)
  })

  test('returns true above max wrong guesses', () => {
    expect(isGameLost(MAX_WRONG_GUESSES + 1)).toBe(true)
  })
})

describe('getWrongGuesses', () => {
  test('returns 0 when all guesses correct', () => {
    expect(getWrongGuesses('HELLO', new Set(['H', 'E', 'L', 'O']))).toBe(0)
  })

  test('counts only wrong guesses', () => {
    expect(getWrongGuesses('HELLO', new Set(['H', 'Z', 'X']))).toBe(2)
  })

  test('returns 0 with no guesses', () => {
    expect(getWrongGuesses('HELLO', new Set())).toBe(0)
  })
})
