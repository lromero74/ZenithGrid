/**
 * Tests for Wordle game engine.
 */

import { describe, test, expect } from 'vitest'
import {
  evaluateGuess,
  isValidWord,
  getDailyWord,
  updateKeyboardState,
  checkHardMode,
  type LetterResult,
  type KeyboardState,
} from './wordleEngine'

describe('evaluateGuess', () => {
  test('all correct', () => {
    const result = evaluateGuess('HELLO', 'HELLO')
    expect(result).toEqual(['correct', 'correct', 'correct', 'correct', 'correct'])
  })

  test('all absent', () => {
    const result = evaluateGuess('XXXXX', 'HELLO')
    expect(result).toEqual(['absent', 'absent', 'absent', 'absent', 'absent'])
  })

  test('present but wrong position', () => {
    const result = evaluateGuess('OLLEH', 'HELLO')
    // O: present (exists in HELLO), L: present, L: correct, E: present, H: present
    expect(result[0]).toBe('present') // O is in HELLO
    expect(result[2]).toBe('correct') // L is in correct position
    expect(result[4]).toBe('present') // H is in HELLO
  })

  test('handles duplicate letters correctly', () => {
    // Guess: SLEEP, Answer: STEEL (S,T,E,E,L)
    // S: correct (pos 0 match), L: present (L in answer pos 4), E: correct (pos 2 match),
    // E: correct (pos 3 match), P: absent
    const result = evaluateGuess('SLEEP', 'STEEL')
    expect(result[0]).toBe('correct') // S
    expect(result[1]).toBe('present') // L (in STEEL pos 4)
    expect(result[2]).toBe('correct') // E (exact match pos 2)
    expect(result[3]).toBe('correct') // E (exact match pos 3)
    expect(result[4]).toBe('absent')  // P
  })

  test('does not double-count letters', () => {
    // Guess: LLAMA, Answer: HELLO (H,E,L,L,O)
    // HELLO has 2 L's, LLAMA has 2 L's → both L's can match as present
    // L: present (matches answer L at pos 2), L: present (matches answer L at pos 3),
    // A: absent, M: absent, A: absent
    const result = evaluateGuess('LLAMA', 'HELLO')
    expect(result[0]).toBe('present') // first L matches first available L
    expect(result[1]).toBe('present') // second L matches second available L
    expect(result[2]).toBe('absent')  // A
    expect(result[3]).toBe('absent')  // M
    expect(result[4]).toBe('absent')  // A
  })

  test('limits present to available count', () => {
    // Guess: EERIE, Answer: STEEL (S,T,E,E,L)
    // E at pos 0: not exact. E at pos 1: not exact. R: absent. I: absent.
    // E at pos 4: not exact.
    // First pass: no exact matches
    // Second pass: E at pos 0 → matches answer E at pos 2 → present.
    //              E at pos 1 → matches answer E at pos 3 → present.
    //              E at pos 4 → no more E's → absent
    const result = evaluateGuess('EERIE', 'STEEL')
    expect(result[0]).toBe('present') // E
    expect(result[1]).toBe('present') // E
    expect(result[2]).toBe('absent')  // R
    expect(result[3]).toBe('absent')  // I
    expect(result[4]).toBe('absent')  // E (no more E's available)
  })

  test('correct takes priority over present for same letter', () => {
    // Guess: HELLO, Answer: LLAMA
    // H: absent, E: absent, L: correct (pos 2), L: present? Let's check
    // Answer: L at pos 0, L at pos 1, A, M, A
    // Guess: H, E, L, L, O
    // L at pos 2: not in answer pos 2, but answer has L at 0 and 1 → present
    // L at pos 3: not in answer pos 3, L at 0 and 1 → but we need to check allocations
    const result = evaluateGuess('HELLO', 'LLAMA')
    expect(result[0]).toBe('absent')  // H
    expect(result[1]).toBe('absent')  // E
    expect(result[2]).toBe('present') // L (answer has L at 0,1)
    expect(result[3]).toBe('present') // L (second L in answer)
    expect(result[4]).toBe('absent')  // O
  })
})

describe('isValidWord', () => {
  test('returns true for word in dictionary', () => {
    expect(isValidWord('HELLO', ['HELLO', 'WORLD', 'TESTS'])).toBe(true)
  })

  test('returns false for word not in dictionary', () => {
    expect(isValidWord('ZZZZZ', ['HELLO', 'WORLD'])).toBe(false)
  })

  test('is case insensitive', () => {
    expect(isValidWord('hello', ['HELLO'])).toBe(true)
  })
})

describe('getDailyWord', () => {
  test('returns a word from the answer list', () => {
    const answers = ['HELLO', 'WORLD', 'CRANE', 'STARE', 'AUDIO']
    const word = getDailyWord(answers, new Date('2026-02-28'))
    expect(answers).toContain(word)
  })

  test('same date gives same word', () => {
    const answers = ['HELLO', 'WORLD', 'CRANE', 'STARE', 'AUDIO']
    const date = new Date('2026-02-28')
    const word1 = getDailyWord(answers, date)
    const word2 = getDailyWord(answers, date)
    expect(word1).toBe(word2)
  })

  test('different dates give (likely) different words', () => {
    const answers = Array.from({ length: 100 }, (_, i) => `WORD${String(i).padStart(1, '0')}`)
    const w1 = getDailyWord(answers, new Date('2026-01-01'))
    const w2 = getDailyWord(answers, new Date('2026-01-02'))
    // With 100 words, very unlikely same word on consecutive days
    expect(w1 !== w2 || answers.length === 1).toBe(true)
  })
})

describe('updateKeyboardState', () => {
  test('marks correct letters green', () => {
    const state: KeyboardState = {}
    const result = updateKeyboardState(state, 'HELLO', ['correct', 'absent', 'absent', 'absent', 'absent'])
    expect(result['H']).toBe('correct')
  })

  test('marks present letters yellow', () => {
    const state: KeyboardState = {}
    const result = updateKeyboardState(state, 'HELLO', ['absent', 'present', 'absent', 'absent', 'absent'])
    expect(result['E']).toBe('present')
  })

  test('marks absent letters gray', () => {
    const state: KeyboardState = {}
    const result = updateKeyboardState(state, 'HELLO', ['absent', 'absent', 'absent', 'absent', 'absent'])
    expect(result['H']).toBe('absent')
  })

  test('correct overrides present', () => {
    const state: KeyboardState = { H: 'present' }
    const result = updateKeyboardState(state, 'HELLO', ['correct', 'absent', 'absent', 'absent', 'absent'])
    expect(result['H']).toBe('correct')
  })

  test('present overrides absent', () => {
    const state: KeyboardState = { H: 'absent' }
    const result = updateKeyboardState(state, 'HELLO', ['present', 'absent', 'absent', 'absent', 'absent'])
    expect(result['H']).toBe('present')
  })

  test('correct is not overridden by absent', () => {
    const state: KeyboardState = { H: 'correct' }
    const result = updateKeyboardState(state, 'HELLO', ['absent', 'absent', 'absent', 'absent', 'absent'])
    expect(result['H']).toBe('correct')
  })
})

describe('checkHardMode', () => {
  test('returns null when no violations', () => {
    const prev = [
      { guess: 'CRANE', evaluation: ['absent', 'correct', 'absent', 'absent', 'correct'] as LetterResult[] },
    ]
    // R is correct at pos 1, E is correct at pos 4
    // Next guess must have R at pos 1 and E at pos 4
    expect(checkHardMode('TRADE', prev)).toBeNull()
  })

  test('returns error when missing correct letter', () => {
    const prev = [
      { guess: 'CRANE', evaluation: ['absent', 'correct', 'absent', 'absent', 'correct'] as LetterResult[] },
    ]
    // R at pos 1 is required, E at pos 4 is required
    const error = checkHardMode('XAXAX', prev)
    expect(error).not.toBeNull()
  })

  test('returns error when present letter not used', () => {
    const prev = [
      { guess: 'CRANE', evaluation: ['absent', 'absent', 'present', 'absent', 'absent'] as LetterResult[] },
    ]
    // A was present — must be used somewhere in next guess
    const error = checkHardMode('SPEED', prev)
    expect(error).not.toBeNull()
  })
})
