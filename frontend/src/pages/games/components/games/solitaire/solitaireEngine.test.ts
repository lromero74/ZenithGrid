/**
 * Tests for Solitaire (Klondike) engine — written before implementation (TDD).
 */

import { describe, test, expect } from 'vitest'
import {
  createDeck,
  shuffleDeck,
  deal,
  getCardColor,
  canMoveToTableau,
  canMoveToFoundation,
  moveToTableau,
  moveToFoundation,
  drawFromStock,
  checkWin,
  canAutoComplete,
  autoComplete,
  getRankDisplay,
  getSuitSymbol,
  getHint,
  type Card,
  type Suit,
  type SolitaireState,
} from './solitaireEngine'

// ── helpers ──────────────────────────────────────────────────────────

function makeCard(suit: Suit, rank: number, faceUp = true): Card {
  return { suit, rank, faceUp }
}

function makeFoundation(suit: Suit, topRank: number): Card[] {
  const cards: Card[] = []
  for (let r = 1; r <= topRank; r++) {
    cards.push(makeCard(suit, r))
  }
  return cards
}

// ── createDeck ───────────────────────────────────────────────────────

describe('createDeck', () => {
  test('returns 52 cards', () => {
    const deck = createDeck()
    expect(deck).toHaveLength(52)
  })

  test('contains all 4 suits', () => {
    const deck = createDeck()
    const suits = new Set(deck.map(c => c.suit))
    expect(suits).toEqual(new Set(['hearts', 'diamonds', 'clubs', 'spades']))
  })

  test('each suit has ranks 1 through 13', () => {
    const deck = createDeck()
    for (const suit of ['hearts', 'diamonds', 'clubs', 'spades'] as Suit[]) {
      const ranks = deck.filter(c => c.suit === suit).map(c => c.rank).sort((a, b) => a - b)
      expect(ranks).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13])
    }
  })

  test('all cards are face-down', () => {
    const deck = createDeck()
    expect(deck.every(c => !c.faceUp)).toBe(true)
  })
})

// ── shuffleDeck ──────────────────────────────────────────────────────

describe('shuffleDeck', () => {
  test('returns 52 cards with same composition', () => {
    const deck = createDeck()
    const shuffled = shuffleDeck(deck)
    expect(shuffled).toHaveLength(52)
    const deckSorted = [...deck].sort((a, b) => a.suit.localeCompare(b.suit) || a.rank - b.rank)
    const shuffledSorted = [...shuffled].sort((a, b) => a.suit.localeCompare(b.suit) || a.rank - b.rank)
    expect(shuffledSorted).toEqual(deckSorted)
  })

  test('does not mutate the original deck', () => {
    const deck = createDeck()
    const copy = deck.map(c => ({ ...c }))
    shuffleDeck(deck)
    expect(deck).toEqual(copy)
  })

  test('produces a different order (statistical — may rarely fail)', () => {
    const deck = createDeck()
    const shuffled = shuffleDeck(deck)
    // At least some cards should be in different positions
    const samePositionCount = deck.filter(
      (c, i) => c.suit === shuffled[i].suit && c.rank === shuffled[i].rank
    ).length
    expect(samePositionCount).toBeLessThan(52)
  })
})

// ── deal ─────────────────────────────────────────────────────────────

describe('deal', () => {
  test('creates 7 tableau piles', () => {
    const state = deal(shuffleDeck(createDeck()))
    expect(state.tableau).toHaveLength(7)
  })

  test('pile i has i+1 cards', () => {
    const state = deal(shuffleDeck(createDeck()))
    for (let i = 0; i < 7; i++) {
      expect(state.tableau[i]).toHaveLength(i + 1)
    }
  })

  test('top card of each pile is face-up', () => {
    const state = deal(shuffleDeck(createDeck()))
    for (let i = 0; i < 7; i++) {
      const pile = state.tableau[i]
      expect(pile[pile.length - 1].faceUp).toBe(true)
    }
  })

  test('non-top cards are face-down', () => {
    const state = deal(shuffleDeck(createDeck()))
    for (let i = 0; i < 7; i++) {
      const pile = state.tableau[i]
      for (let j = 0; j < pile.length - 1; j++) {
        expect(pile[j].faceUp).toBe(false)
      }
    }
  })

  test('28 cards in tableau + 24 in stock = 52', () => {
    const state = deal(shuffleDeck(createDeck()))
    const tableauCount = state.tableau.reduce((sum, pile) => sum + pile.length, 0)
    expect(tableauCount).toBe(28)
    expect(state.stock).toHaveLength(24)
    expect(tableauCount + state.stock.length).toBe(52)
  })

  test('waste is empty, foundations are empty, moves is 0', () => {
    const state = deal(shuffleDeck(createDeck()))
    expect(state.waste).toHaveLength(0)
    expect(state.foundations).toHaveLength(4)
    expect(state.foundations.every(f => f.length === 0)).toBe(true)
    expect(state.moves).toBe(0)
  })
})

// ── getCardColor ─────────────────────────────────────────────────────

describe('getCardColor', () => {
  test('hearts are red', () => {
    expect(getCardColor(makeCard('hearts', 5))).toBe('red')
  })

  test('diamonds are red', () => {
    expect(getCardColor(makeCard('diamonds', 10))).toBe('red')
  })

  test('clubs are black', () => {
    expect(getCardColor(makeCard('clubs', 1))).toBe('black')
  })

  test('spades are black', () => {
    expect(getCardColor(makeCard('spades', 13))).toBe('black')
  })
})

// ── canMoveToTableau ─────────────────────────────────────────────────

describe('canMoveToTableau', () => {
  test('accepts King on empty pile', () => {
    expect(canMoveToTableau(makeCard('hearts', 13), [])).toBe(true)
  })

  test('rejects non-King on empty pile', () => {
    expect(canMoveToTableau(makeCard('hearts', 12), [])).toBe(false)
    expect(canMoveToTableau(makeCard('spades', 1), [])).toBe(false)
  })

  test('accepts alternating color + descending rank', () => {
    // Black 7 onto Red 8
    const pile = [makeCard('hearts', 8)]
    expect(canMoveToTableau(makeCard('spades', 7), pile)).toBe(true)
    // Red 3 onto Black 4
    const pile2 = [makeCard('clubs', 4)]
    expect(canMoveToTableau(makeCard('diamonds', 3), pile2)).toBe(true)
  })

  test('rejects same color', () => {
    // Red 7 onto Red 8
    const pile = [makeCard('hearts', 8)]
    expect(canMoveToTableau(makeCard('diamonds', 7), pile)).toBe(false)
    // Black 5 onto Black 6
    const pile2 = [makeCard('clubs', 6)]
    expect(canMoveToTableau(makeCard('spades', 5), pile2)).toBe(false)
  })

  test('rejects wrong rank (not descending by 1)', () => {
    // Black 5 onto Red 8 (should be 7 onto 8)
    const pile = [makeCard('hearts', 8)]
    expect(canMoveToTableau(makeCard('spades', 5), pile)).toBe(false)
    // Black 8 onto Red 8 (same rank)
    expect(canMoveToTableau(makeCard('spades', 8), pile)).toBe(false)
  })

  test('rejects Ace on non-empty pile (no card goes below Ace)', () => {
    const pile = [makeCard('clubs', 2)]
    expect(canMoveToTableau(makeCard('hearts', 1), pile)).toBe(true) // Ace onto 2 with alt color is valid
    const pile2 = [makeCard('hearts', 2)]
    expect(canMoveToTableau(makeCard('diamonds', 1), pile2)).toBe(false) // same color
  })
})

// ── canMoveToFoundation ──────────────────────────────────────────────

describe('canMoveToFoundation', () => {
  test('accepts Ace on empty foundation', () => {
    expect(canMoveToFoundation(makeCard('hearts', 1), [])).toBe(true)
  })

  test('rejects non-Ace on empty foundation', () => {
    expect(canMoveToFoundation(makeCard('hearts', 2), [])).toBe(false)
    expect(canMoveToFoundation(makeCard('spades', 13), [])).toBe(false)
  })

  test('accepts same suit ascending rank', () => {
    const foundation = makeFoundation('hearts', 3)
    expect(canMoveToFoundation(makeCard('hearts', 4), foundation)).toBe(true)
  })

  test('rejects different suit', () => {
    const foundation = makeFoundation('hearts', 3)
    expect(canMoveToFoundation(makeCard('diamonds', 4), foundation)).toBe(false)
  })

  test('rejects wrong rank (not ascending by 1)', () => {
    const foundation = makeFoundation('hearts', 3)
    expect(canMoveToFoundation(makeCard('hearts', 5), foundation)).toBe(false)
    expect(canMoveToFoundation(makeCard('hearts', 2), foundation)).toBe(false)
  })

  test('accepts King on foundation with Queen on top', () => {
    const foundation = makeFoundation('spades', 12)
    expect(canMoveToFoundation(makeCard('spades', 13), foundation)).toBe(true)
  })
})

// ── drawFromStock ────────────────────────────────────────────────────

describe('drawFromStock', () => {
  test('moves top card from stock to waste face-up', () => {
    const state: SolitaireState = {
      tableau: [[], [], [], [], [], [], []],
      foundations: [[], [], [], []],
      stock: [makeCard('hearts', 5, false), makeCard('clubs', 3, false)],
      waste: [],
      moves: 0,
    }
    const next = drawFromStock(state)
    expect(next.stock).toHaveLength(1)
    expect(next.waste).toHaveLength(1)
    expect(next.waste[0].faceUp).toBe(true)
    expect(next.waste[0].rank).toBe(3) // top of stock (last element)
    expect(next.moves).toBe(1)
  })

  test('recycles waste to stock when stock is empty', () => {
    const state: SolitaireState = {
      tableau: [[], [], [], [], [], [], []],
      foundations: [[], [], [], []],
      stock: [],
      waste: [makeCard('hearts', 1), makeCard('clubs', 2), makeCard('spades', 3)],
      moves: 5,
    }
    const next = drawFromStock(state)
    expect(next.stock).toHaveLength(3)
    expect(next.waste).toHaveLength(0)
    // Recycled cards should be face-down
    expect(next.stock.every(c => !c.faceUp)).toBe(true)
    // Order should be reversed (waste top becomes stock bottom)
    expect(next.stock[0].rank).toBe(3)
    expect(next.stock[2].rank).toBe(1)
    expect(next.moves).toBe(6)
  })

  test('does not mutate original state', () => {
    const state: SolitaireState = {
      tableau: [[], [], [], [], [], [], []],
      foundations: [[], [], [], []],
      stock: [makeCard('hearts', 5, false), makeCard('clubs', 3, false)],
      waste: [],
      moves: 0,
    }
    const stockCopy = [...state.stock]
    drawFromStock(state)
    expect(state.stock).toEqual(stockCopy)
    expect(state.waste).toHaveLength(0)
  })
})

// ── moveToTableau ────────────────────────────────────────────────────

describe('moveToTableau', () => {
  test('moves cards from one tableau pile to another', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 8)],
        [makeCard('clubs', 6, false), makeCard('spades', 7)],
        [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [],
      waste: [],
      moves: 0,
    }
    // Move spades 7 from pile 1 to pile 0 (on top of hearts 8)
    const next = moveToTableau(state, 'tableau', 1, 0, 1)
    expect(next.tableau[0]).toHaveLength(2)
    expect(next.tableau[0][1].rank).toBe(7)
    expect(next.tableau[0][1].suit).toBe('spades')
    expect(next.tableau[1]).toHaveLength(1)
    // The newly exposed card should be flipped face-up
    expect(next.tableau[1][0].faceUp).toBe(true)
    expect(next.moves).toBe(1)
  })

  test('moves multiple cards (stack) between tableau piles', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 8), makeCard('spades', 7), makeCard('diamonds', 6)],
        [makeCard('clubs', 9)],
        [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [],
      waste: [],
      moves: 2,
    }
    // Move 3 cards (8,7,6) from pile 0 to pile 1 (on top of clubs 9)
    const next = moveToTableau(state, 'tableau', 0, 1, 3)
    expect(next.tableau[0]).toHaveLength(0)
    expect(next.tableau[1]).toHaveLength(4)
    expect(next.tableau[1][1].rank).toBe(8)
    expect(next.moves).toBe(3)
  })

  test('moves card from waste to tableau', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 8)],
        [], [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [],
      waste: [makeCard('spades', 7)],
      moves: 0,
    }
    const next = moveToTableau(state, 'waste', 0, 0, 1)
    expect(next.tableau[0]).toHaveLength(2)
    expect(next.tableau[0][1].rank).toBe(7)
    expect(next.waste).toHaveLength(0)
    expect(next.moves).toBe(1)
  })

  test('does not mutate original state', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 8)],
        [makeCard('spades', 7)],
        [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [],
      waste: [],
      moves: 0,
    }
    const origLen0 = state.tableau[0].length
    const origLen1 = state.tableau[1].length
    moveToTableau(state, 'tableau', 1, 0, 1)
    expect(state.tableau[0]).toHaveLength(origLen0)
    expect(state.tableau[1]).toHaveLength(origLen1)
  })
})

// ── moveToFoundation ─────────────────────────────────────────────────

describe('moveToFoundation', () => {
  test('moves Ace from tableau to empty foundation', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 1)],
        [], [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [],
      waste: [],
      moves: 0,
    }
    const next = moveToFoundation(state, 'tableau', 0, 0)
    expect(next.foundations[0]).toHaveLength(1)
    expect(next.foundations[0][0].rank).toBe(1)
    expect(next.tableau[0]).toHaveLength(0)
    expect(next.moves).toBe(1)
  })

  test('moves card from waste to foundation', () => {
    const state: SolitaireState = {
      tableau: [[], [], [], [], [], [], []],
      foundations: [makeFoundation('hearts', 5), [], [], []],
      stock: [],
      waste: [makeCard('hearts', 6)],
      moves: 3,
    }
    const next = moveToFoundation(state, 'waste', 0, 0)
    expect(next.foundations[0]).toHaveLength(6)
    expect(next.foundations[0][5].rank).toBe(6)
    expect(next.waste).toHaveLength(0)
    expect(next.moves).toBe(4)
  })

  test('flips newly exposed tableau card', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('clubs', 5, false), makeCard('hearts', 1)],
        [], [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [],
      waste: [],
      moves: 0,
    }
    const next = moveToFoundation(state, 'tableau', 0, 0)
    expect(next.tableau[0]).toHaveLength(1)
    expect(next.tableau[0][0].faceUp).toBe(true)
  })

  test('does not mutate original state', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 1)],
        [], [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [],
      waste: [],
      moves: 0,
    }
    moveToFoundation(state, 'tableau', 0, 0)
    expect(state.tableau[0]).toHaveLength(1)
    expect(state.foundations[0]).toHaveLength(0)
  })
})

// ── checkWin ─────────────────────────────────────────────────────────

describe('checkWin', () => {
  test('returns true when all foundations have 13 cards', () => {
    const state: SolitaireState = {
      tableau: [[], [], [], [], [], [], []],
      foundations: [
        makeFoundation('hearts', 13),
        makeFoundation('diamonds', 13),
        makeFoundation('clubs', 13),
        makeFoundation('spades', 13),
      ],
      stock: [],
      waste: [],
      moves: 50,
    }
    expect(checkWin(state)).toBe(true)
  })

  test('returns false when foundations are incomplete', () => {
    const state: SolitaireState = {
      tableau: [[], [], [], [], [], [], []],
      foundations: [
        makeFoundation('hearts', 13),
        makeFoundation('diamonds', 12),
        makeFoundation('clubs', 13),
        makeFoundation('spades', 13),
      ],
      stock: [],
      waste: [],
      moves: 40,
    }
    expect(checkWin(state)).toBe(false)
  })

  test('returns false when foundations are empty', () => {
    const state: SolitaireState = {
      tableau: [[], [], [], [], [], [], []],
      foundations: [[], [], [], []],
      stock: [],
      waste: [],
      moves: 0,
    }
    expect(checkWin(state)).toBe(false)
  })
})

// ── canAutoComplete ──────────────────────────────────────────────────

describe('canAutoComplete', () => {
  test('returns true when all tableau cards are face-up and stock/waste empty', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 3), makeCard('spades', 2)],
        [makeCard('clubs', 1)],
        [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [],
      waste: [],
      moves: 10,
    }
    expect(canAutoComplete(state)).toBe(true)
  })

  test('returns false when stock is not empty', () => {
    const state: SolitaireState = {
      tableau: [[makeCard('hearts', 1)], [], [], [], [], [], []],
      foundations: [[], [], [], []],
      stock: [makeCard('clubs', 2, false)],
      waste: [],
      moves: 5,
    }
    expect(canAutoComplete(state)).toBe(false)
  })

  test('returns false when waste is not empty', () => {
    const state: SolitaireState = {
      tableau: [[makeCard('hearts', 1)], [], [], [], [], [], []],
      foundations: [[], [], [], []],
      stock: [],
      waste: [makeCard('clubs', 2)],
      moves: 5,
    }
    expect(canAutoComplete(state)).toBe(false)
  })

  test('returns false when a tableau card is face-down', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 3, false), makeCard('spades', 2)],
        [], [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [],
      waste: [],
      moves: 10,
    }
    expect(canAutoComplete(state)).toBe(false)
  })

  test('returns true when tableau is completely empty', () => {
    const state: SolitaireState = {
      tableau: [[], [], [], [], [], [], []],
      foundations: [
        makeFoundation('hearts', 13),
        makeFoundation('diamonds', 13),
        makeFoundation('clubs', 13),
        makeFoundation('spades', 13),
      ],
      stock: [],
      waste: [],
      moves: 50,
    }
    expect(canAutoComplete(state)).toBe(true)
  })
})

// ── autoComplete ─────────────────────────────────────────────────────

describe('autoComplete', () => {
  test('moves all remaining tableau cards to foundations', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 13)],
        [makeCard('diamonds', 13)],
        [makeCard('clubs', 13)],
        [makeCard('spades', 13)],
        [], [], [],
      ],
      foundations: [
        makeFoundation('hearts', 12),
        makeFoundation('diamonds', 12),
        makeFoundation('clubs', 12),
        makeFoundation('spades', 12),
      ],
      stock: [],
      waste: [],
      moves: 40,
    }
    const result = autoComplete(state)
    expect(checkWin(result)).toBe(true)
    expect(result.tableau.every(p => p.length === 0)).toBe(true)
  })

  test('handles multiple cards per pile in correct order', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 13), makeCard('hearts', 12)],
        [], [], [], [], [], [],
      ],
      foundations: [
        makeFoundation('hearts', 11),
        makeFoundation('diamonds', 13),
        makeFoundation('clubs', 13),
        makeFoundation('spades', 13),
      ],
      stock: [],
      waste: [],
      moves: 45,
    }
    const result = autoComplete(state)
    expect(checkWin(result)).toBe(true)
  })

  test('does not mutate original state', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 13)],
        [], [], [], [], [], [],
      ],
      foundations: [
        makeFoundation('hearts', 12),
        makeFoundation('diamonds', 13),
        makeFoundation('clubs', 13),
        makeFoundation('spades', 13),
      ],
      stock: [],
      waste: [],
      moves: 40,
    }
    autoComplete(state)
    expect(state.tableau[0]).toHaveLength(1)
    expect(state.foundations[0]).toHaveLength(12)
  })
})

// ── getRankDisplay ───────────────────────────────────────────────────

describe('getRankDisplay', () => {
  test('returns A for Ace', () => {
    expect(getRankDisplay(1)).toBe('A')
  })

  test('returns number string for 2-10', () => {
    for (let r = 2; r <= 10; r++) {
      expect(getRankDisplay(r)).toBe(String(r))
    }
  })

  test('returns J for Jack', () => {
    expect(getRankDisplay(11)).toBe('J')
  })

  test('returns Q for Queen', () => {
    expect(getRankDisplay(12)).toBe('Q')
  })

  test('returns K for King', () => {
    expect(getRankDisplay(13)).toBe('K')
  })
})

// ── getSuitSymbol ────────────────────────────────────────────────────

describe('getSuitSymbol', () => {
  test('returns correct symbol for each suit', () => {
    expect(getSuitSymbol('hearts')).toBe('♥')
    expect(getSuitSymbol('diamonds')).toBe('♦')
    expect(getSuitSymbol('clubs')).toBe('♣')
    expect(getSuitSymbol('spades')).toBe('♠')
  })
})

// ── getHint ─────────────────────────────────────────────────────────

describe('getHint', () => {
  test('suggests tableau-to-foundation when Ace is on tableau', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 1)],
        [], [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [],
      waste: [],
      moves: 0,
    }
    const hint = getHint(state)
    expect(hint).not.toBeNull()
    expect(hint!.type).toBe('tableau-to-foundation')
    expect(hint!.fromPile).toBe(0)
  })

  test('suggests waste-to-foundation when waste card fits', () => {
    const state: SolitaireState = {
      tableau: [[], [], [], [], [], [], []],
      foundations: [makeFoundation('hearts', 3), [], [], []],
      stock: [],
      waste: [makeCard('hearts', 4)],
      moves: 5,
    }
    const hint = getHint(state)
    expect(hint).not.toBeNull()
    expect(hint!.type).toBe('waste-to-foundation')
    expect(hint!.toPile).toBe(0)
  })

  test('suggests tableau-to-tableau when valid move exists', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 8, false), makeCard('spades', 7)],
        [makeCard('diamonds', 8)],
        [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [],
      waste: [],
      moves: 0,
    }
    const hint = getHint(state)
    expect(hint).not.toBeNull()
    expect(hint!.type).toBe('tableau-to-tableau')
    expect(hint!.fromPile).toBe(0)
    expect(hint!.toPile).toBe(1)
  })

  test('suggests waste-to-tableau when no foundation moves exist', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 8)],
        [], [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [],
      waste: [makeCard('spades', 7)],
      moves: 0,
    }
    const hint = getHint(state)
    expect(hint).not.toBeNull()
    expect(hint!.type).toBe('waste-to-tableau')
    expect(hint!.toPile).toBe(0)
  })

  test('suggests draw-stock when no card moves available', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 5)],
        [makeCard('hearts', 3)],
        [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [makeCard('clubs', 10, false)],
      waste: [],
      moves: 0,
    }
    const hint = getHint(state)
    expect(hint).not.toBeNull()
    expect(hint!.type).toBe('draw-stock')
  })

  test('returns null when no moves available at all', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 5)],
        [makeCard('hearts', 3)],
        [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [],
      waste: [],
      moves: 10,
    }
    const hint = getHint(state)
    expect(hint).toBeNull()
  })

  test('prioritizes foundation moves over tableau moves', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 1)],
        [makeCard('diamonds', 8)],
        [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [],
      waste: [makeCard('spades', 7)],
      moves: 0,
    }
    const hint = getHint(state)
    expect(hint).not.toBeNull()
    expect(hint!.type).toBe('tableau-to-foundation')
  })

  test('does not suggest moving lone King to empty pile', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 13)],
        [],
        [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [],
      waste: [],
      moves: 0,
    }
    const hint = getHint(state)
    expect(hint).toBeNull()
  })

  test('suggests recycling waste when stock is empty but waste has cards', () => {
    const state: SolitaireState = {
      tableau: [
        [makeCard('hearts', 5)],
        [], [], [], [], [], [],
      ],
      foundations: [[], [], [], []],
      stock: [],
      waste: [makeCard('clubs', 10)],
      moves: 5,
    }
    const hint = getHint(state)
    expect(hint).not.toBeNull()
    expect(hint!.type).toBe('draw-stock')
  })
})
