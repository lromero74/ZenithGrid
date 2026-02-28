/**
 * Memory card matching game engine — pure functions, immutable state.
 *
 * Handles deck creation, card flipping, match checking, and game
 * completion detection. No side effects or randomness dependencies
 * beyond initial shuffle.
 */

export interface Card {
  id: number
  symbol: string
  flipped: boolean
  matched: boolean
}

export type GridSize = 'easy' | 'medium' | 'hard'

const SYMBOLS = [
  '\u{1F436}', '\u{1F431}', '\u{1F42D}', '\u{1F439}', '\u{1F430}',
  '\u{1F98A}', '\u{1F43B}', '\u{1F43C}', '\u{1F428}', '\u{1F42F}',
  '\u{1F981}', '\u{1F42E}', '\u{1F437}', '\u{1F438}', '\u{1F435}',
  '\u{1F414}', '\u{1F427}', '\u{1F426}', '\u{1F984}', '\u{1F41D}',
]

const GRID_CONFIG: Record<GridSize, { rows: number; cols: number; pairs: number }> = {
  easy:   { rows: 3, cols: 4, pairs: 6 },
  medium: { rows: 4, cols: 4, pairs: 8 },
  hard:   { rows: 4, cols: 6, pairs: 12 },
}

/** Get grid dimensions and pair count for a difficulty level. */
export function getGridDimensions(size: GridSize): { rows: number; cols: number; pairs: number } {
  return GRID_CONFIG[size]
}

/** Fisher-Yates shuffle (in-place on a new copy). */
function shuffle<T>(arr: T[]): T[] {
  const a = [...arr]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

/** Create a shuffled deck of card pairs using emoji symbols. */
export function createDeck(pairCount: number): Card[] {
  const selectedSymbols = SYMBOLS.slice(0, pairCount)
  const cards: Card[] = []

  for (let i = 0; i < pairCount; i++) {
    const symbol = selectedSymbols[i % selectedSymbols.length]
    cards.push(
      { id: i * 2,     symbol, flipped: false, matched: false },
      { id: i * 2 + 1, symbol, flipped: false, matched: false },
    )
  }

  return shuffle(cards)
}

/** Flip a card at the given index. Skips already-matched cards. Returns new array. */
export function flipCard(cards: Card[], index: number): Card[] {
  return cards.map((card, i) => {
    if (i !== index) return { ...card }
    if (card.matched) return { ...card }
    return { ...card, flipped: !card.flipped }
  })
}

/** Check if two cards have the same symbol. */
export function checkMatch(card1: Card, card2: Card): boolean {
  return card1.symbol === card2.symbol
}

/** Check if all cards in the deck are matched. */
export function checkGameComplete(cards: Card[]): boolean {
  return cards.every(card => card.matched)
}

/** Convert total flip count to move count (every 2 flips = 1 move). */
export function countMoves(flippedCount: number): number {
  return Math.floor(flippedCount / 2)
}
