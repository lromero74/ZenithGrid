import { describe, test, expect } from 'vitest'
import {
  createSeededRng,
  getDailySeed,
  getTodayString,
  generatePuzzle,
  createEmptyUserGrid,
  isPuzzleComplete,
  isCellCorrect,
  getWordCells,
  getWordsAtCell,
  seededShuffle,
  type Difficulty,
} from './crosswordEngine'
import { CROSSWORD_THEMES } from './crosswordThemes'

// ── Seeded PRNG ─────────────────────────────────────────────────────

describe('createSeededRng', () => {
  test('produces deterministic sequence from same seed', () => {
    const rng1 = createSeededRng(42)
    const rng2 = createSeededRng(42)
    const seq1 = Array.from({ length: 10 }, () => rng1())
    const seq2 = Array.from({ length: 10 }, () => rng2())
    expect(seq1).toEqual(seq2)
  })

  test('different seeds produce different sequences', () => {
    const rng1 = createSeededRng(42)
    const rng2 = createSeededRng(99)
    const seq1 = Array.from({ length: 5 }, () => rng1())
    const seq2 = Array.from({ length: 5 }, () => rng2())
    expect(seq1).not.toEqual(seq2)
  })

  test('values are in [0, 1) range', () => {
    const rng = createSeededRng(12345)
    for (let i = 0; i < 1000; i++) {
      const v = rng()
      expect(v).toBeGreaterThanOrEqual(0)
      expect(v).toBeLessThan(1)
    }
  })
})

// ── Daily seed ──────────────────────────────────────────────────────

describe('getDailySeed', () => {
  test('same date and difficulty produce same seed', () => {
    expect(getDailySeed('2026-03-09', 'easy')).toBe(getDailySeed('2026-03-09', 'easy'))
  })

  test('different dates produce different seeds', () => {
    expect(getDailySeed('2026-03-09', 'easy')).not.toBe(getDailySeed('2026-03-10', 'easy'))
  })

  test('different difficulties produce different seeds for same date', () => {
    const easy = getDailySeed('2026-03-09', 'easy')
    const medium = getDailySeed('2026-03-09', 'medium')
    const hard = getDailySeed('2026-03-09', 'hard')
    expect(easy).not.toBe(medium)
    expect(medium).not.toBe(hard)
    expect(easy).not.toBe(hard)
  })
})

// ── getTodayString ──────────────────────────────────────────────────

describe('getTodayString', () => {
  test('returns YYYY-MM-DD format', () => {
    const today = getTodayString()
    expect(today).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})

// ── seededShuffle ───────────────────────────────────────────────────

describe('seededShuffle', () => {
  test('produces deterministic order from same seed', () => {
    const arr1 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    const arr2 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    const rng1 = createSeededRng(42)
    const rng2 = createSeededRng(42)
    seededShuffle(arr1, rng1)
    seededShuffle(arr2, rng2)
    expect(arr1).toEqual(arr2)
  })

  test('preserves all elements', () => {
    const arr = [1, 2, 3, 4, 5]
    const rng = createSeededRng(99)
    seededShuffle(arr, rng)
    expect(arr.sort()).toEqual([1, 2, 3, 4, 5])
  })
})

// ── generatePuzzle ──────────────────────────────────────────────────

describe('generatePuzzle', () => {
  test('same date+difficulty always produces identical puzzle', () => {
    const p1 = generatePuzzle('2026-03-09', 'medium', CROSSWORD_THEMES)
    const p2 = generatePuzzle('2026-03-09', 'medium', CROSSWORD_THEMES)
    expect(p1.placedWords.length).toBe(p2.placedWords.length)
    expect(p1.width).toBe(p2.width)
    expect(p1.height).toBe(p2.height)
    expect(p1.theme).toBe(p2.theme)
    for (let i = 0; i < p1.placedWords.length; i++) {
      expect(p1.placedWords[i].word).toBe(p2.placedWords[i].word)
      expect(p1.placedWords[i].row).toBe(p2.placedWords[i].row)
      expect(p1.placedWords[i].col).toBe(p2.placedWords[i].col)
      expect(p1.placedWords[i].direction).toBe(p2.placedWords[i].direction)
    }
  })

  test('easy puzzle has 5-7 words (or fewer if insufficient intersections)', () => {
    // Test across multiple dates to find one that works well
    let found = false
    for (let d = 1; d <= 30; d++) {
      const dateStr = `2026-01-${String(d).padStart(2, '0')}`
      const puzzle = generatePuzzle(dateStr, 'easy', CROSSWORD_THEMES)
      if (puzzle.placedWords.length >= 3) {
        expect(puzzle.placedWords.length).toBeLessThanOrEqual(7)
        found = true
        break
      }
    }
    expect(found).toBe(true)
  })

  test('hard puzzle has more words than easy', () => {
    let easyTotal = 0, hardTotal = 0
    for (let d = 1; d <= 10; d++) {
      const dateStr = `2026-02-${String(d).padStart(2, '0')}`
      easyTotal += generatePuzzle(dateStr, 'easy', CROSSWORD_THEMES).placedWords.length
      hardTotal += generatePuzzle(dateStr, 'hard', CROSSWORD_THEMES).placedWords.length
    }
    expect(hardTotal).toBeGreaterThan(easyTotal)
  })

  test('all placed words have valid grid cells', () => {
    const puzzle = generatePuzzle('2026-03-09', 'medium', CROSSWORD_THEMES)
    for (const w of puzzle.placedWords) {
      const cells = getWordCells(w)
      expect(cells.length).toBe(w.word.length)
      for (const [r, c] of cells) {
        expect(r).toBeGreaterThanOrEqual(0)
        expect(r).toBeLessThan(puzzle.height)
        expect(c).toBeGreaterThanOrEqual(0)
        expect(c).toBeLessThan(puzzle.width)
        expect(puzzle.grid[r][c].isBlack).toBe(false)
      }
    }
  })

  test('grid letters match placed words', () => {
    const puzzle = generatePuzzle('2026-03-09', 'hard', CROSSWORD_THEMES)
    for (const w of puzzle.placedWords) {
      const cells = getWordCells(w)
      for (let i = 0; i < w.word.length; i++) {
        const [r, c] = cells[i]
        expect(puzzle.grid[r][c].letter).toBe(w.word[i])
      }
    }
  })

  test('different dates produce different puzzles', () => {
    const p1 = generatePuzzle('2026-03-09', 'medium', CROSSWORD_THEMES)
    const p2 = generatePuzzle('2026-03-10', 'medium', CROSSWORD_THEMES)
    // They could theoretically have the same theme, but placed words should differ
    const words1 = p1.placedWords.map(w => w.word).sort().join(',')
    const words2 = p2.placedWords.map(w => w.word).sort().join(',')
    // Very unlikely to be identical
    expect(words1 === words2 && p1.theme === p2.theme).toBe(false)
  })

  test('generates puzzles for all three difficulties without errors', () => {
    const difficulties: Difficulty[] = ['easy', 'medium', 'hard']
    for (const diff of difficulties) {
      const puzzle = generatePuzzle('2026-06-15', diff, CROSSWORD_THEMES)
      expect(puzzle.placedWords.length).toBeGreaterThan(0)
      expect(puzzle.width).toBeGreaterThan(0)
      expect(puzzle.height).toBeGreaterThan(0)
    }
  })
})

// ── isPuzzleComplete ────────────────────────────────────────────────

describe('isPuzzleComplete', () => {
  test('returns true when all cells match solution', () => {
    const puzzle = generatePuzzle('2026-03-09', 'easy', CROSSWORD_THEMES)
    // Create a user grid that matches the solution exactly
    const userGrid = puzzle.grid.map(row => row.map(cell => cell.isBlack ? '' : cell.letter))
    expect(isPuzzleComplete(puzzle, userGrid)).toBe(true)
  })

  test('returns false when any cell is empty', () => {
    const puzzle = generatePuzzle('2026-03-09', 'easy', CROSSWORD_THEMES)
    const userGrid = createEmptyUserGrid(puzzle)
    expect(isPuzzleComplete(puzzle, userGrid)).toBe(false)
  })

  test('returns false when any cell has wrong letter', () => {
    const puzzle = generatePuzzle('2026-03-09', 'easy', CROSSWORD_THEMES)
    const userGrid = puzzle.grid.map(row => row.map(cell => cell.isBlack ? '' : cell.letter))
    // Find a non-black cell and change its letter
    for (let r = 0; r < puzzle.height; r++) {
      for (let c = 0; c < puzzle.width; c++) {
        if (!puzzle.grid[r][c].isBlack) {
          userGrid[r][c] = userGrid[r][c] === 'A' ? 'B' : 'A'
          expect(isPuzzleComplete(puzzle, userGrid)).toBe(false)
          return
        }
      }
    }
  })
})

// ── isCellCorrect ───────────────────────────────────────────────────

describe('isCellCorrect', () => {
  test('returns true for correct letter', () => {
    const puzzle = generatePuzzle('2026-03-09', 'easy', CROSSWORD_THEMES)
    for (let r = 0; r < puzzle.height; r++) {
      for (let c = 0; c < puzzle.width; c++) {
        if (!puzzle.grid[r][c].isBlack) {
          expect(isCellCorrect(puzzle, r, c, puzzle.grid[r][c].letter)).toBe(true)
          return
        }
      }
    }
  })

  test('returns false for wrong letter', () => {
    const puzzle = generatePuzzle('2026-03-09', 'easy', CROSSWORD_THEMES)
    for (let r = 0; r < puzzle.height; r++) {
      for (let c = 0; c < puzzle.width; c++) {
        if (!puzzle.grid[r][c].isBlack) {
          const wrong = puzzle.grid[r][c].letter === 'A' ? 'B' : 'A'
          expect(isCellCorrect(puzzle, r, c, wrong)).toBe(false)
          return
        }
      }
    }
  })
})

// ── getWordsAtCell ──────────────────────────────────────────────────

describe('getWordsAtCell', () => {
  test('returns correct words for a cell', () => {
    const puzzle = generatePuzzle('2026-03-09', 'medium', CROSSWORD_THEMES)
    if (puzzle.placedWords.length === 0) return
    const word = puzzle.placedWords[0]
    const cells = getWordCells(word)
    const [r, c] = cells[0]
    const found = getWordsAtCell(puzzle, r, c)
    expect(found.some(w => w.word === word.word)).toBe(true)
  })

  test('returns empty array for black cell', () => {
    const puzzle = generatePuzzle('2026-03-09', 'medium', CROSSWORD_THEMES)
    // Find a black cell
    for (let r = 0; r < puzzle.height; r++) {
      for (let c = 0; c < puzzle.width; c++) {
        if (puzzle.grid[r][c].isBlack) {
          expect(getWordsAtCell(puzzle, r, c)).toEqual([])
          return
        }
      }
    }
  })
})

// ── createEmptyUserGrid ─────────────────────────────────────────────

describe('createEmptyUserGrid', () => {
  test('creates grid matching puzzle dimensions', () => {
    const puzzle = generatePuzzle('2026-03-09', 'easy', CROSSWORD_THEMES)
    const grid = createEmptyUserGrid(puzzle)
    expect(grid.length).toBe(puzzle.height)
    expect(grid[0].length).toBe(puzzle.width)
  })

  test('all cells are empty strings', () => {
    const puzzle = generatePuzzle('2026-03-09', 'easy', CROSSWORD_THEMES)
    const grid = createEmptyUserGrid(puzzle)
    for (const row of grid) {
      for (const cell of row) {
        expect(cell).toBe('')
      }
    }
  })
})
