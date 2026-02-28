import { describe, test, expect } from 'vitest'
import {
  getGridDimensions, createDeck, flipCard, checkMatch,
  checkGameComplete, countMoves,
  type Card,
} from './memoryEngine'

describe('getGridDimensions', () => {
  test('easy returns 4x3 with 6 pairs', () => {
    const dim = getGridDimensions('easy')
    expect(dim).toEqual({ rows: 3, cols: 4, pairs: 6 })
  })

  test('medium returns 4x4 with 8 pairs', () => {
    const dim = getGridDimensions('medium')
    expect(dim).toEqual({ rows: 4, cols: 4, pairs: 8 })
  })

  test('hard returns 6x4 with 12 pairs', () => {
    const dim = getGridDimensions('hard')
    expect(dim).toEqual({ rows: 4, cols: 6, pairs: 12 })
  })
})

describe('createDeck', () => {
  test('creates correct number of cards for given pair count', () => {
    const deck = createDeck(6)
    expect(deck.length).toBe(12)
  })

  test('each symbol appears exactly twice', () => {
    const deck = createDeck(8)
    const counts = new Map<string, number>()
    for (const card of deck) {
      counts.set(card.symbol, (counts.get(card.symbol) ?? 0) + 1)
    }
    for (const [, count] of counts) {
      expect(count).toBe(2)
    }
  })

  test('all cards start face down and unmatched', () => {
    const deck = createDeck(6)
    for (const card of deck) {
      expect(card.flipped).toBe(false)
      expect(card.matched).toBe(false)
    }
  })

  test('each card has a unique id', () => {
    const deck = createDeck(8)
    const ids = new Set(deck.map(c => c.id))
    expect(ids.size).toBe(16)
  })

  test('deck is shuffled (not in sequential pair order)', () => {
    // Run multiple times — at least one should be shuffled
    let foundShuffled = false
    for (let attempt = 0; attempt < 10; attempt++) {
      const deck = createDeck(6)
      const symbols = deck.map(c => c.symbol)
      // If sequential, pairs would be adjacent: [A,A,B,B,C,C,...]
      const isSequential = symbols.every((s, i) =>
        i % 2 === 0 ? symbols[i + 1] === s : true
      )
      if (!isSequential) {
        foundShuffled = true
        break
      }
    }
    expect(foundShuffled).toBe(true)
  })

  test('uses valid emoji symbols', () => {
    const deck = createDeck(12)
    for (const card of deck) {
      expect(card.symbol.length).toBeGreaterThan(0)
    }
  })

  test('single pair creates 2 cards', () => {
    const deck = createDeck(1)
    expect(deck.length).toBe(2)
    expect(deck[0].symbol).toBe(deck[1].symbol)
  })
})

describe('flipCard', () => {
  test('flips an unflipped card', () => {
    const cards: Card[] = [
      { id: 0, symbol: 'A', flipped: false, matched: false },
      { id: 1, symbol: 'B', flipped: false, matched: false },
    ]
    const result = flipCard(cards, 0)
    expect(result[0].flipped).toBe(true)
    expect(result[1].flipped).toBe(false)
  })

  test('does not flip an already matched card', () => {
    const cards: Card[] = [
      { id: 0, symbol: 'A', flipped: true, matched: true },
    ]
    const result = flipCard(cards, 0)
    expect(result[0].flipped).toBe(true)
    expect(result[0].matched).toBe(true)
  })

  test('returns a new array (immutable)', () => {
    const cards: Card[] = [
      { id: 0, symbol: 'A', flipped: false, matched: false },
    ]
    const result = flipCard(cards, 0)
    expect(result).not.toBe(cards)
    expect(result[0]).not.toBe(cards[0])
  })

  test('does not mutate the original array', () => {
    const cards: Card[] = [
      { id: 0, symbol: 'A', flipped: false, matched: false },
    ]
    flipCard(cards, 0)
    expect(cards[0].flipped).toBe(false)
  })

  test('flips a flipped (but unmatched) card back down', () => {
    const cards: Card[] = [
      { id: 0, symbol: 'A', flipped: true, matched: false },
    ]
    const result = flipCard(cards, 0)
    expect(result[0].flipped).toBe(false)
  })
})

describe('checkMatch', () => {
  test('returns true for matching symbols', () => {
    const card1: Card = { id: 0, symbol: 'X', flipped: true, matched: false }
    const card2: Card = { id: 1, symbol: 'X', flipped: true, matched: false }
    expect(checkMatch(card1, card2)).toBe(true)
  })

  test('returns false for different symbols', () => {
    const card1: Card = { id: 0, symbol: 'X', flipped: true, matched: false }
    const card2: Card = { id: 1, symbol: 'Y', flipped: true, matched: false }
    expect(checkMatch(card1, card2)).toBe(false)
  })
})

describe('checkGameComplete', () => {
  test('returns true when all cards are matched', () => {
    const cards: Card[] = [
      { id: 0, symbol: 'A', flipped: true, matched: true },
      { id: 1, symbol: 'A', flipped: true, matched: true },
      { id: 2, symbol: 'B', flipped: true, matched: true },
      { id: 3, symbol: 'B', flipped: true, matched: true },
    ]
    expect(checkGameComplete(cards)).toBe(true)
  })

  test('returns false when some cards are unmatched', () => {
    const cards: Card[] = [
      { id: 0, symbol: 'A', flipped: true, matched: true },
      { id: 1, symbol: 'A', flipped: true, matched: true },
      { id: 2, symbol: 'B', flipped: false, matched: false },
      { id: 3, symbol: 'B', flipped: false, matched: false },
    ]
    expect(checkGameComplete(cards)).toBe(false)
  })

  test('returns true for empty deck', () => {
    expect(checkGameComplete([])).toBe(true)
  })

  test('returns false when only one card is unmatched', () => {
    const cards: Card[] = [
      { id: 0, symbol: 'A', flipped: true, matched: true },
      { id: 1, symbol: 'A', flipped: false, matched: false },
    ]
    expect(checkGameComplete(cards)).toBe(false)
  })
})

describe('countMoves', () => {
  test('0 flips = 0 moves', () => {
    expect(countMoves(0)).toBe(0)
  })

  test('1 flip = 0 moves (incomplete pair)', () => {
    expect(countMoves(1)).toBe(0)
  })

  test('2 flips = 1 move', () => {
    expect(countMoves(2)).toBe(1)
  })

  test('10 flips = 5 moves', () => {
    expect(countMoves(10)).toBe(5)
  })

  test('odd number rounds down', () => {
    expect(countMoves(7)).toBe(3)
  })
})
