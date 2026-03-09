/**
 * Crossword puzzle engine — pure logic, no side effects.
 *
 * Generates themed crossword puzzles deterministically from a date + difficulty seed.
 * Uses Mulberry32 PRNG for reproducibility and an intersection-based word placement
 * algorithm to build grids.
 */

import type { ThemeBank, ThemeEntry } from './crosswordThemes'

// ── Types ───────────────────────────────────────────────────────────

export type Difficulty = 'easy' | 'medium' | 'hard'
export type Direction = 'across' | 'down'

export interface PlacedWord {
  word: string
  clue: string
  row: number
  col: number
  direction: Direction
  number: number
}

export interface CrosswordCell {
  letter: string          // solution letter ('' for black cells)
  number: number | null   // clue number if word starts here
  isBlack: boolean
}

export interface CrosswordPuzzle {
  grid: CrosswordCell[][]
  width: number
  height: number
  placedWords: PlacedWord[]
  theme: string
  difficulty: Difficulty
  dateStr: string
}

// ── Seeded PRNG ─────────────────────────────────────────────────────

/** Mulberry32 — fast, deterministic 32-bit PRNG. Returns floats in [0, 1). */
export function createSeededRng(seed: number): () => number {
  let s = seed | 0
  return () => {
    s = (s + 0x6D2B79F5) | 0
    let t = Math.imul(s ^ (s >>> 15), 1 | s)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Generate a seed from date + difficulty using djb2 hash. */
export function getDailySeed(dateStr: string, difficulty: Difficulty): number {
  const input = `${dateStr}-${difficulty}`
  let hash = 5381
  for (let i = 0; i < input.length; i++) {
    hash = ((hash << 5) + hash + input.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

/** Get today's date as YYYY-MM-DD. */
export function getTodayString(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// ── Difficulty config ───────────────────────────────────────────────

interface DifficultyConfig {
  minWords: number
  maxWords: number
  minLength: number
  maxLength: number
}

const DIFFICULTY_CONFIG: Record<Difficulty, DifficultyConfig> = {
  easy:   { minWords: 5,  maxWords: 7,  minLength: 3, maxLength: 6  },
  medium: { minWords: 7,  maxWords: 10, minLength: 4, maxLength: 8  },
  hard:   { minWords: 10, maxWords: 14, minLength: 4, maxLength: 12 },
}

// ── Helpers ─────────────────────────────────────────────────────────

/** Seeded Fisher-Yates shuffle (mutates in place, returns same array). */
export function seededShuffle<T>(arr: T[], rng: () => number): T[] {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]]
  }
  return arr
}

// ── Placement algorithm ─────────────────────────────────────────────

interface Placement {
  word: string
  clue: string
  row: number
  col: number
  direction: Direction
}

/**
 * Check if a word can be placed at a position without conflicts.
 * Rules:
 * 1. Every cell the word occupies must either be empty or contain the same letter.
 * 2. Cells adjacent perpendicular to the word (and not an intersection) must be empty.
 * 3. The cell before the first letter and after the last must be empty.
 */
function isValidPlacement(
  word: string,
  row: number,
  col: number,
  direction: Direction,
  occupied: Map<string, string>,
): boolean {
  for (let i = 0; i < word.length; i++) {
    const r = direction === 'down' ? row + i : row
    const c = direction === 'across' ? col + i : col
    const key = `${r},${c}`
    const existing = occupied.get(key)

    if (existing !== undefined && existing !== word[i]) return false

    // If this cell is currently empty, check perpendicular neighbors
    if (existing === undefined) {
      if (direction === 'across') {
        if (occupied.has(`${r - 1},${c}`) || occupied.has(`${r + 1},${c}`)) return false
      } else {
        if (occupied.has(`${r},${c - 1}`) || occupied.has(`${r},${c + 1}`)) return false
      }
    }
  }

  // Check cell before start
  const beforeR = direction === 'down' ? row - 1 : row
  const beforeC = direction === 'across' ? col - 1 : col
  if (occupied.has(`${beforeR},${beforeC}`)) return false

  // Check cell after end
  const afterR = direction === 'down' ? row + word.length : row
  const afterC = direction === 'across' ? col + word.length : col
  if (occupied.has(`${afterR},${afterC}`)) return false

  return true
}

/** Find a valid placement for a candidate word crossing existing placed words. */
function findBestPlacement(
  candidate: ThemeEntry,
  placed: Placement[],
  occupied: Map<string, string>,
  rng: () => number,
): Placement | null {
  const valid: Placement[] = []

  for (const existing of placed) {
    const newDir: Direction = existing.direction === 'across' ? 'down' : 'across'

    for (let ei = 0; ei < existing.word.length; ei++) {
      for (let ci = 0; ci < candidate.word.length; ci++) {
        if (existing.word[ei] !== candidate.word[ci]) continue

        let newRow: number, newCol: number
        if (newDir === 'down') {
          newRow = existing.row - ci
          newCol = existing.col + ei
        } else {
          newRow = existing.row + ei
          newCol = existing.col - ci
        }

        if (isValidPlacement(candidate.word, newRow, newCol, newDir, occupied)) {
          valid.push({
            word: candidate.word,
            clue: candidate.clue,
            row: newRow,
            col: newCol,
            direction: newDir,
          })
        }
      }
    }
  }

  if (valid.length === 0) return null
  return valid[Math.floor(rng() * valid.length)]
}

/** Place words onto a virtual grid using intersection-based placement. */
function placeWords(
  candidates: ThemeEntry[],
  targetCount: number,
  rng: () => number,
): Placement[] {
  const placed: Placement[] = []
  const occupied = new Map<string, string>()

  if (candidates.length === 0) return placed

  // Place first word horizontally at origin
  const first = candidates[0]
  placed.push({ word: first.word, clue: first.clue, row: 0, col: 0, direction: 'across' })
  for (let i = 0; i < first.word.length; i++) {
    occupied.set(`0,${i}`, first.word[i])
  }

  for (let ci = 1; ci < candidates.length && placed.length < targetCount; ci++) {
    const best = findBestPlacement(candidates[ci], placed, occupied, rng)
    if (best) {
      placed.push(best)
      for (let i = 0; i < best.word.length; i++) {
        const r = best.direction === 'down' ? best.row + i : best.row
        const c = best.direction === 'across' ? best.col + i : best.col
        occupied.set(`${r},${c}`, best.word[i])
      }
    }
  }

  return placed
}

// ── Grid building ───────────────────────────────────────────────────

/** Build the final puzzle grid from placed words. */
function buildGrid(
  placements: Placement[],
  theme: string,
  difficulty: Difficulty,
  dateStr: string,
): CrosswordPuzzle {
  if (placements.length === 0) {
    return { grid: [], width: 0, height: 0, placedWords: [], theme, difficulty, dateStr }
  }

  // Find bounding box
  let minRow = Infinity, maxRow = -Infinity, minCol = Infinity, maxCol = -Infinity
  for (const p of placements) {
    for (let i = 0; i < p.word.length; i++) {
      const r = p.direction === 'down' ? p.row + i : p.row
      const c = p.direction === 'across' ? p.col + i : p.col
      minRow = Math.min(minRow, r)
      maxRow = Math.max(maxRow, r)
      minCol = Math.min(minCol, c)
      maxCol = Math.max(maxCol, c)
    }
  }

  const height = maxRow - minRow + 1
  const width = maxCol - minCol + 1

  // Normalize placements to 0-based coordinates
  const normalized = placements.map(p => ({
    ...p,
    row: p.row - minRow,
    col: p.col - minCol,
  }))

  // Create grid (all black initially)
  const grid: CrosswordCell[][] = Array.from({ length: height }, () =>
    Array.from({ length: width }, () => ({ letter: '', number: null, isBlack: true })),
  )

  // Fill letters
  for (const p of normalized) {
    for (let i = 0; i < p.word.length; i++) {
      const r = p.direction === 'down' ? p.row + i : p.row
      const c = p.direction === 'across' ? p.col + i : p.col
      grid[r][c].letter = p.word[i]
      grid[r][c].isBlack = false
    }
  }

  // Assign clue numbers (top-to-bottom, left-to-right)
  let clueNum = 1
  const startCells = new Map<string, number>()

  for (let r = 0; r < height; r++) {
    for (let c = 0; c < width; c++) {
      if (grid[r][c].isBlack) continue
      const startsAcross = normalized.some(p => p.direction === 'across' && p.row === r && p.col === c)
      const startsDown = normalized.some(p => p.direction === 'down' && p.row === r && p.col === c)
      if (startsAcross || startsDown) {
        grid[r][c].number = clueNum
        startCells.set(`${r},${c}`, clueNum)
        clueNum++
      }
    }
  }

  const placedWords: PlacedWord[] = normalized.map(p => ({
    word: p.word,
    clue: p.clue,
    row: p.row,
    col: p.col,
    direction: p.direction,
    number: startCells.get(`${p.row},${p.col}`) ?? 0,
  }))

  return { grid, width, height, placedWords, theme, difficulty, dateStr }
}

// ── Public API ──────────────────────────────────────────────────────

/** Generate a crossword puzzle deterministically from date + difficulty. */
export function generatePuzzle(
  dateStr: string,
  difficulty: Difficulty,
  themes: ThemeBank,
): CrosswordPuzzle {
  const seed = getDailySeed(dateStr, difficulty)
  const rng = createSeededRng(seed)
  const config = DIFFICULTY_CONFIG[difficulty]

  // Select theme
  const themeKeys = Object.keys(themes)
  const themeIndex = Math.floor(rng() * themeKeys.length)
  const themeName = themeKeys[themeIndex]
  const themeWords = themes[themeName]

  // Filter by difficulty length constraints
  const eligible = themeWords.filter(
    wc => wc.word.length >= config.minLength && wc.word.length <= config.maxLength,
  )

  // Shuffle and take candidate pool (2x target for fallback)
  const targetCount = config.minWords + Math.floor(rng() * (config.maxWords - config.minWords + 1))
  const shuffled = seededShuffle([...eligible], rng)
  const candidates = shuffled.slice(0, Math.min(targetCount * 2, shuffled.length))

  // Sort longest first for better grid connectivity
  candidates.sort((a, b) => b.word.length - a.word.length)

  const placements = placeWords(candidates, targetCount, rng)
  return buildGrid(placements, themeName, difficulty, dateStr)
}

/** Create an empty user input grid matching puzzle dimensions. */
export function createEmptyUserGrid(puzzle: CrosswordPuzzle): string[][] {
  return Array.from({ length: puzzle.height }, () =>
    Array.from({ length: puzzle.width }, () => ''),
  )
}

/** Check if a specific cell's input matches the solution. */
export function isCellCorrect(puzzle: CrosswordPuzzle, row: number, col: number, input: string): boolean {
  return puzzle.grid[row][col].letter === input.toUpperCase()
}

/** Check if the entire puzzle is solved correctly. */
export function isPuzzleComplete(puzzle: CrosswordPuzzle, userGrid: string[][]): boolean {
  for (let r = 0; r < puzzle.height; r++) {
    for (let c = 0; c < puzzle.width; c++) {
      if (puzzle.grid[r][c].isBlack) continue
      if (userGrid[r]?.[c]?.toUpperCase() !== puzzle.grid[r][c].letter) return false
    }
  }
  return true
}

/** Get the cells belonging to a specific word. */
export function getWordCells(word: PlacedWord): [number, number][] {
  const cells: [number, number][] = []
  for (let i = 0; i < word.word.length; i++) {
    const r = word.direction === 'down' ? word.row + i : word.row
    const c = word.direction === 'across' ? word.col + i : word.col
    cells.push([r, c])
  }
  return cells
}

/** Find which placed word(s) a cell belongs to. */
export function getWordsAtCell(puzzle: CrosswordPuzzle, row: number, col: number): PlacedWord[] {
  return puzzle.placedWords.filter(w =>
    getWordCells(w).some(([r, c]) => r === row && c === col),
  )
}
