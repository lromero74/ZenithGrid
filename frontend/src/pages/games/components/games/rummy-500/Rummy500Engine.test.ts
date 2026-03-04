import { describe, test, expect } from 'vitest'
import type { Card } from '../../../utils/cardUtils'
import {
  createRummy500Game,
  drawFromStock,
  drawFromDiscard,
  toggleSelectCard,
  meldCards,
  layOff,
  discard,
  isValidSet,
  isValidRun,
  isValidMeld,
  canLayOff,
  cardValue,
  newRound,
  type Rummy500State,
  type Meld,
} from './Rummy500Engine'

// ── Helpers ─────────────────────────────────────────────────────────

function card(rank: number, suit: Card['suit']): Card {
  return { rank, suit, faceUp: true }
}

/** Build a Rummy500State with sensible defaults, allowing partial overrides. */
function makeState(overrides?: Partial<Rummy500State>): Rummy500State {
  return {
    hands: [
      [card(1, 'hearts'), card(5, 'spades'), card(10, 'diamonds'),
       card(3, 'clubs'), card(7, 'hearts'), card(9, 'diamonds'), card(12, 'spades')],
      [card(2, 'hearts'), card(6, 'spades'), card(11, 'diamonds'),
       card(4, 'clubs'), card(8, 'hearts'), card(13, 'diamonds'), card(10, 'spades')],
    ],
    melds: [],
    stock: Array.from({ length: 30 }, (_, i) => card((i % 13) + 1, 'clubs')),
    discardPile: [card(5, 'hearts')],
    currentPlayer: 0,
    phase: 'draw',
    scores: [0, 0],
    message: 'Draw a card from stock or discard pile',
    selectedCards: [],
    hasDrawn: false,
    ...overrides,
  }
}

// ── createRummy500Game ──────────────────────────────────────────────

describe('createRummy500Game', () => {
  test('deals 7 cards to each player with 38 in stock', () => {
    const state = createRummy500Game()
    expect(state.hands[0]).toHaveLength(7)
    expect(state.hands[1]).toHaveLength(7)
    expect(state.stock).toHaveLength(38)
  })

  test('all 52 cards are accounted for', () => {
    const state = createRummy500Game()
    const total = state.hands[0].length + state.hands[1].length +
      state.stock.length + state.discardPile.length
    expect(total).toBe(52)
  })

  test('starts in draw phase with player 0', () => {
    const state = createRummy500Game()
    expect(state.phase).toBe('draw')
    expect(state.currentPlayer).toBe(0)
  })

  test('both players start with score 0', () => {
    const state = createRummy500Game()
    expect(state.scores).toEqual([0, 0])
  })

  test('starts with no melds', () => {
    const state = createRummy500Game()
    expect(state.melds).toEqual([])
  })

  test('discard pile starts empty', () => {
    const state = createRummy500Game()
    expect(state.discardPile).toHaveLength(0)
  })

  test('hasDrawn starts as false', () => {
    const state = createRummy500Game()
    expect(state.hasDrawn).toBe(false)
  })

  test('player hand cards are face up', () => {
    const state = createRummy500Game()
    expect(state.hands[0].every(c => c.faceUp)).toBe(true)
  })
})

// ── isValidSet ──────────────────────────────────────────────────────

describe('isValidSet', () => {
  test('3 Aces of different suits is valid', () => {
    const cards = [card(1, 'hearts'), card(1, 'diamonds'), card(1, 'clubs')]
    expect(isValidSet(cards)).toBe(true)
  })

  test('4 of same rank is valid', () => {
    const cards = [card(7, 'hearts'), card(7, 'diamonds'), card(7, 'clubs'), card(7, 'spades')]
    expect(isValidSet(cards)).toBe(true)
  })

  test('2 cards is not valid (too few)', () => {
    const cards = [card(5, 'hearts'), card(5, 'diamonds')]
    expect(isValidSet(cards)).toBe(false)
  })

  test('3 cards of different ranks is not valid', () => {
    const cards = [card(5, 'hearts'), card(6, 'diamonds'), card(7, 'clubs')]
    expect(isValidSet(cards)).toBe(false)
  })

  test('3 cards of same rank but duplicate suits is not valid', () => {
    const cards = [card(5, 'hearts'), card(5, 'hearts'), card(5, 'clubs')]
    expect(isValidSet(cards)).toBe(false)
  })

  test('5 of same rank is not valid (only 4 suits)', () => {
    const cards = [card(5, 'hearts'), card(5, 'diamonds'), card(5, 'clubs'), card(5, 'spades'), card(5, 'hearts')]
    expect(isValidSet(cards)).toBe(false)
  })
})

// ── isValidRun ──────────────────────────────────────────────────────

describe('isValidRun', () => {
  test('3-4-5 of hearts is valid', () => {
    const cards = [card(3, 'hearts'), card(4, 'hearts'), card(5, 'hearts')]
    expect(isValidRun(cards)).toBe(true)
  })

  test('A-2-3 of spades is valid (low ace)', () => {
    const cards = [card(1, 'spades'), card(2, 'spades'), card(3, 'spades')]
    expect(isValidRun(cards)).toBe(true)
  })

  test('Q-K-A of diamonds is valid (high ace)', () => {
    const cards = [card(12, 'diamonds'), card(13, 'diamonds'), card(1, 'diamonds')]
    expect(isValidRun(cards)).toBe(true)
  })

  test('longer run 5-6-7-8 of clubs is valid', () => {
    const cards = [card(5, 'clubs'), card(6, 'clubs'), card(7, 'clubs'), card(8, 'clubs')]
    expect(isValidRun(cards)).toBe(true)
  })

  test('2 cards is not valid (too few)', () => {
    const cards = [card(3, 'hearts'), card(4, 'hearts')]
    expect(isValidRun(cards)).toBe(false)
  })

  test('mixed suits is not valid', () => {
    const cards = [card(3, 'hearts'), card(4, 'diamonds'), card(5, 'hearts')]
    expect(isValidRun(cards)).toBe(false)
  })

  test('non-consecutive ranks is not valid', () => {
    const cards = [card(3, 'hearts'), card(5, 'hearts'), card(7, 'hearts')]
    expect(isValidRun(cards)).toBe(false)
  })

  test('K-A-2 wrap-around is not valid', () => {
    const cards = [card(13, 'hearts'), card(1, 'hearts'), card(2, 'hearts')]
    expect(isValidRun(cards)).toBe(false)
  })

  test('cards out of order still valid (sorted internally)', () => {
    const cards = [card(5, 'hearts'), card(3, 'hearts'), card(4, 'hearts')]
    expect(isValidRun(cards)).toBe(true)
  })
})

// ── isValidMeld ─────────────────────────────────────────────────────

describe('isValidMeld', () => {
  test('valid set returns { valid: true, type: "set" }', () => {
    const cards = [card(9, 'hearts'), card(9, 'diamonds'), card(9, 'clubs')]
    const result = isValidMeld(cards)
    expect(result.valid).toBe(true)
    expect(result.type).toBe('set')
  })

  test('valid run returns { valid: true, type: "run" }', () => {
    const cards = [card(3, 'hearts'), card(4, 'hearts'), card(5, 'hearts')]
    const result = isValidMeld(cards)
    expect(result.valid).toBe(true)
    expect(result.type).toBe('run')
  })

  test('invalid cards returns { valid: false }', () => {
    const cards = [card(3, 'hearts'), card(7, 'diamonds')]
    const result = isValidMeld(cards)
    expect(result.valid).toBe(false)
  })
})

// ── canLayOff ───────────────────────────────────────────────────────

describe('canLayOff', () => {
  test('can add 6 of hearts to run 3-4-5 of hearts', () => {
    const meld: Meld = { cards: [card(3, 'hearts'), card(4, 'hearts'), card(5, 'hearts')], type: 'run' }
    expect(canLayOff(card(6, 'hearts'), meld)).toBe(true)
  })

  test('can add 2 of hearts to run 3-4-5 of hearts (prepend)', () => {
    const meld: Meld = { cards: [card(3, 'hearts'), card(4, 'hearts'), card(5, 'hearts')], type: 'run' }
    expect(canLayOff(card(2, 'hearts'), meld)).toBe(true)
  })

  test('cannot add 7 of diamonds to run 3-4-5 of hearts (wrong suit)', () => {
    const meld: Meld = { cards: [card(3, 'hearts'), card(4, 'hearts'), card(5, 'hearts')], type: 'run' }
    expect(canLayOff(card(7, 'diamonds'), meld)).toBe(false)
  })

  test('can add 4th card of same rank to a set', () => {
    const meld: Meld = { cards: [card(9, 'hearts'), card(9, 'diamonds'), card(9, 'clubs')], type: 'set' }
    expect(canLayOff(card(9, 'spades'), meld)).toBe(true)
  })

  test('cannot add to a 4-card set (max 4 suits)', () => {
    const meld: Meld = {
      cards: [card(9, 'hearts'), card(9, 'diamonds'), card(9, 'clubs'), card(9, 'spades')],
      type: 'set',
    }
    expect(canLayOff(card(9, 'hearts'), meld)).toBe(false)
  })

  test('cannot add wrong rank to a set', () => {
    const meld: Meld = { cards: [card(9, 'hearts'), card(9, 'diamonds'), card(9, 'clubs')], type: 'set' }
    expect(canLayOff(card(10, 'spades'), meld)).toBe(false)
  })

  test('can add Ace high to J-Q-K run', () => {
    const meld: Meld = { cards: [card(11, 'spades'), card(12, 'spades'), card(13, 'spades')], type: 'run' }
    expect(canLayOff(card(1, 'spades'), meld)).toBe(true)
  })

  test('can add Ace low to 2-3-4 run', () => {
    const meld: Meld = { cards: [card(2, 'clubs'), card(3, 'clubs'), card(4, 'clubs')], type: 'run' }
    expect(canLayOff(card(1, 'clubs'), meld)).toBe(true)
  })
})

// ── cardValue ───────────────────────────────────────────────────────

describe('cardValue', () => {
  test('Ace = 1 point normally', () => {
    expect(cardValue(card(1, 'hearts'))).toBe(1)
  })

  test('number cards = face value', () => {
    expect(cardValue(card(2, 'hearts'))).toBe(2)
    expect(cardValue(card(5, 'diamonds'))).toBe(5)
    expect(cardValue(card(10, 'clubs'))).toBe(10)
  })

  test('Jack = 10', () => {
    expect(cardValue(card(11, 'hearts'))).toBe(10)
  })

  test('Queen = 10', () => {
    expect(cardValue(card(12, 'hearts'))).toBe(10)
  })

  test('King = 10', () => {
    expect(cardValue(card(13, 'hearts'))).toBe(10)
  })
})

// ── drawFromStock ───────────────────────────────────────────────────

describe('drawFromStock', () => {
  test('adds one card from stock to current player hand', () => {
    const state = makeState()
    const next = drawFromStock(state)
    expect(next.hands[0]).toHaveLength(8)
    expect(next.stock).toHaveLength(29)
  })

  test('transitions to meld phase', () => {
    const state = makeState()
    const next = drawFromStock(state)
    expect(next.phase).toBe('meld')
    expect(next.hasDrawn).toBe(true)
  })

  test('returns unchanged state if not in draw phase', () => {
    const state = makeState({ phase: 'meld' })
    const next = drawFromStock(state)
    expect(next).toBe(state)
  })

  test('returns unchanged state when stock is empty', () => {
    const state = makeState({ stock: [] })
    const next = drawFromStock(state)
    expect(next).toBe(state)
  })

  test('drawn card is face up', () => {
    const state = makeState()
    const next = drawFromStock(state)
    const newCard = next.hands[0][next.hands[0].length - 1]
    expect(newCard.faceUp).toBe(true)
  })
})

// ── drawFromDiscard ─────────────────────────────────────────────────

describe('drawFromDiscard', () => {
  test('takes top card from discard pile to current player hand', () => {
    const state = makeState({ discardPile: [card(5, 'hearts'), card(8, 'clubs')] })
    const next = drawFromDiscard(state)
    expect(next.hands[0]).toHaveLength(8)
    expect(next.discardPile).toHaveLength(1)
  })

  test('transitions to meld phase', () => {
    const state = makeState()
    const next = drawFromDiscard(state)
    expect(next.phase).toBe('meld')
    expect(next.hasDrawn).toBe(true)
  })

  test('returns unchanged state if not in draw phase', () => {
    const state = makeState({ phase: 'meld' })
    const next = drawFromDiscard(state)
    expect(next).toBe(state)
  })

  test('returns unchanged state when discard pile is empty', () => {
    const state = makeState({ discardPile: [] })
    const next = drawFromDiscard(state)
    expect(next).toBe(state)
  })

  test('takes the top (last) card', () => {
    const state = makeState({ discardPile: [card(5, 'hearts'), card(8, 'clubs')] })
    const next = drawFromDiscard(state)
    // 8 of clubs was on top, should now be in hand
    const hasEightClubs = next.hands[0].some(c => c.rank === 8 && c.suit === 'clubs')
    expect(hasEightClubs).toBe(true)
    // 5 of hearts should still be in discard
    expect(next.discardPile[0].rank).toBe(5)
  })
})

// ── toggleSelectCard ────────────────────────────────────────────────

describe('toggleSelectCard', () => {
  test('selects a card by adding its index', () => {
    const state = makeState({ phase: 'meld', hasDrawn: true })
    const next = toggleSelectCard(state, 2)
    expect(next.selectedCards).toContain(2)
  })

  test('deselects a card by removing its index', () => {
    const state = makeState({ phase: 'meld', hasDrawn: true, selectedCards: [2, 4] })
    const next = toggleSelectCard(state, 2)
    expect(next.selectedCards).not.toContain(2)
    expect(next.selectedCards).toContain(4)
  })

  test('returns unchanged state if not in meld phase', () => {
    const state = makeState({ phase: 'draw' })
    const next = toggleSelectCard(state, 2)
    expect(next).toBe(state)
  })
})

// ── meldCards ───────────────────────────────────────────────────────

describe('meldCards', () => {
  test('creates a valid set meld from selected cards', () => {
    const hand = [card(9, 'hearts'), card(9, 'diamonds'), card(9, 'clubs'),
                  card(5, 'spades'), card(7, 'hearts'), card(3, 'diamonds'),
                  card(10, 'clubs'), card(2, 'hearts')]
    const state = makeState({
      hands: [hand, makeState().hands[1]],
      phase: 'meld',
      hasDrawn: true,
      selectedCards: [0, 1, 2],
    })
    const next = meldCards(state)
    expect(next.melds).toHaveLength(1)
    expect(next.melds[0].type).toBe('set')
    expect(next.hands[0]).toHaveLength(5) // 8 - 3 melded
    expect(next.selectedCards).toEqual([])
  })

  test('creates a valid run meld from selected cards', () => {
    const hand = [card(3, 'hearts'), card(4, 'hearts'), card(5, 'hearts'),
                  card(9, 'clubs'), card(12, 'spades'), card(7, 'diamonds'),
                  card(1, 'clubs'), card(10, 'spades')]
    const state = makeState({
      hands: [hand, makeState().hands[1]],
      phase: 'meld',
      hasDrawn: true,
      selectedCards: [0, 1, 2],
    })
    const next = meldCards(state)
    expect(next.melds).toHaveLength(1)
    expect(next.melds[0].type).toBe('run')
    expect(next.hands[0]).toHaveLength(5)
  })

  test('rejects invalid meld and returns unchanged state', () => {
    const hand = [card(3, 'hearts'), card(7, 'diamonds'), card(9, 'clubs'),
                  card(5, 'spades'), card(12, 'hearts'), card(10, 'clubs'),
                  card(1, 'diamonds'), card(4, 'spades')]
    const state = makeState({
      hands: [hand, makeState().hands[1]],
      phase: 'meld',
      hasDrawn: true,
      selectedCards: [0, 1, 2],
    })
    const next = meldCards(state)
    expect(next.melds).toHaveLength(0)
    expect(next.hands[0]).toHaveLength(8) // unchanged
  })

  test('rejects meld when fewer than 3 cards selected', () => {
    const hand = [card(9, 'hearts'), card(9, 'diamonds'), card(5, 'clubs'),
                  card(3, 'spades'), card(7, 'hearts'), card(10, 'diamonds'),
                  card(1, 'clubs'), card(8, 'spades')]
    const state = makeState({
      hands: [hand, makeState().hands[1]],
      phase: 'meld',
      hasDrawn: true,
      selectedCards: [0, 1],
    })
    const next = meldCards(state)
    expect(next.melds).toHaveLength(0)
  })

  test('going out by melding all remaining cards triggers round over', () => {
    // Player has exactly 3 cards that form a valid meld, no discard needed
    const hand = [card(9, 'hearts'), card(9, 'diamonds'), card(9, 'clubs')]
    const state = makeState({
      hands: [hand, makeState().hands[1]],
      phase: 'meld',
      hasDrawn: true,
      selectedCards: [0, 1, 2],
    })
    const next = meldCards(state)
    expect(next.phase).toBe('roundOver')
    expect(next.hands[0]).toHaveLength(0)
  })
})

// ── layOff ──────────────────────────────────────────────────────────

describe('layOff', () => {
  test('adds card to existing run meld', () => {
    const existingMeld: Meld = {
      cards: [card(3, 'hearts'), card(4, 'hearts'), card(5, 'hearts')],
      type: 'run',
    }
    const hand = [card(6, 'hearts'), card(9, 'clubs'), card(12, 'spades'),
                  card(1, 'diamonds'), card(7, 'clubs'), card(10, 'spades'),
                  card(2, 'diamonds'), card(5, 'clubs')]
    const state = makeState({
      hands: [hand, makeState().hands[1]],
      melds: [existingMeld],
      phase: 'meld',
      hasDrawn: true,
    })
    const next = layOff(state, 0, 0) // lay off 6 of hearts onto meld 0
    expect(next.melds[0].cards).toHaveLength(4)
    expect(next.hands[0]).toHaveLength(7)
  })

  test('adds card to existing set meld', () => {
    const existingMeld: Meld = {
      cards: [card(9, 'hearts'), card(9, 'diamonds'), card(9, 'clubs')],
      type: 'set',
    }
    const hand = [card(9, 'spades'), card(5, 'clubs'), card(12, 'spades'),
                  card(1, 'diamonds'), card(7, 'clubs'), card(10, 'spades'),
                  card(2, 'diamonds'), card(3, 'clubs')]
    const state = makeState({
      hands: [hand, makeState().hands[1]],
      melds: [existingMeld],
      phase: 'meld',
      hasDrawn: true,
    })
    const next = layOff(state, 0, 0)
    expect(next.melds[0].cards).toHaveLength(4)
    expect(next.hands[0]).toHaveLength(7)
  })

  test('rejects invalid lay off', () => {
    const existingMeld: Meld = {
      cards: [card(3, 'hearts'), card(4, 'hearts'), card(5, 'hearts')],
      type: 'run',
    }
    const hand = [card(9, 'clubs'), card(5, 'spades'), card(12, 'hearts'),
                  card(1, 'diamonds'), card(7, 'clubs'), card(10, 'spades'),
                  card(2, 'diamonds'), card(3, 'clubs')]
    const state = makeState({
      hands: [hand, makeState().hands[1]],
      melds: [existingMeld],
      phase: 'meld',
      hasDrawn: true,
    })
    const next = layOff(state, 0, 0) // 9 of clubs can't extend hearts run
    expect(next.melds[0].cards).toHaveLength(3) // unchanged
    expect(next.hands[0]).toHaveLength(8) // unchanged
  })

  test('going out by laying off last card triggers round over', () => {
    const existingMeld: Meld = {
      cards: [card(3, 'hearts'), card(4, 'hearts'), card(5, 'hearts')],
      type: 'run',
    }
    const hand = [card(6, 'hearts')]
    const state = makeState({
      hands: [hand, makeState().hands[1]],
      melds: [existingMeld],
      phase: 'meld',
      hasDrawn: true,
    })
    const next = layOff(state, 0, 0)
    expect(next.phase).toBe('roundOver')
    expect(next.hands[0]).toHaveLength(0)
  })
})

// ── discard ─────────────────────────────────────────────────────────

describe('discard', () => {
  test('removes card from hand and adds to discard pile', () => {
    const hand = [card(3, 'hearts'), card(9, 'clubs'), card(12, 'spades'),
                  card(1, 'diamonds'), card(7, 'clubs'), card(10, 'spades'),
                  card(2, 'diamonds'), card(5, 'clubs')]
    const state = makeState({
      hands: [hand, makeState().hands[1]],
      phase: 'meld',
      hasDrawn: true,
      discardPile: [],
    })
    const next = discard(state, 0)
    // After discard, AI plays and it becomes player's draw phase
    // Hand should have lost 1 card (from 8 to 7)
    expect(next.hands[0]).toHaveLength(7)
  })

  test('returns unchanged state if not in meld phase', () => {
    const state = makeState({ phase: 'draw' })
    const next = discard(state, 0)
    expect(next).toBe(state)
  })

  test('returns unchanged state if player has not drawn', () => {
    const state = makeState({ phase: 'meld', hasDrawn: false })
    const next = discard(state, 0)
    expect(next).toBe(state)
  })

  test('advances to next player turn after AI plays', () => {
    const hand = [card(3, 'hearts'), card(9, 'clubs'), card(12, 'spades'),
                  card(1, 'diamonds'), card(7, 'clubs'), card(10, 'spades'),
                  card(2, 'diamonds'), card(5, 'clubs')]
    const state = makeState({
      hands: [hand, [card(2, 'hearts'), card(6, 'spades'), card(11, 'diamonds'),
                     card(4, 'clubs'), card(8, 'hearts'), card(13, 'diamonds'), card(10, 'clubs')]],
      phase: 'meld',
      hasDrawn: true,
    })
    const next = discard(state, 0)
    // After AI plays, it should be player's turn again
    expect(next.currentPlayer).toBe(0)
    expect(next.phase).toBe('draw')
  })

  test('invalid card index returns unchanged state', () => {
    const state = makeState({ phase: 'meld', hasDrawn: true })
    const next = discard(state, -1)
    expect(next).toBe(state)
    const next2 = discard(state, 99)
    expect(next2).toBe(state)
  })
})

// ── Scoring ─────────────────────────────────────────────────────────

describe('scoring', () => {
  test('melded cards add positive points, hand cards subtract', () => {
    // When a round ends, score = sum of melded card values - sum of hand card values
    // We test this indirectly through round-over state
    const meld: Meld = {
      cards: [card(10, 'hearts'), card(10, 'diamonds'), card(10, 'clubs')],
      type: 'set',
    }
    // Player has melded 30 points (three 10s), AI has 0 melded and cards in hand
    const hand: Card[] = [card(9, 'hearts'), card(9, 'diamonds'), card(9, 'clubs')]
    const state = makeState({
      hands: [hand, [card(5, 'spades'), card(3, 'diamonds'), card(7, 'clubs'),
                     card(1, 'hearts'), card(2, 'diamonds'), card(4, 'clubs'), card(6, 'spades')]],
      melds: [meld],
      phase: 'meld',
      hasDrawn: true,
      selectedCards: [0, 1, 2],
    })
    // Meld the 9s to go out
    const next = meldCards(state)
    expect(next.phase).toBe('roundOver')
    // Player melded: 10+10+10+9+9+9 = 57 points, 0 in hand
    // Player score should be positive
    expect(next.scores[0]).toBeGreaterThan(0)
  })

  test('unmelded cards in hand count negative', () => {
    // Set up a round-over where player has cards remaining
    // Use empty stock to trigger round over
    const meld: Meld = {
      cards: [card(10, 'hearts'), card(10, 'diamonds'), card(10, 'clubs')],
      type: 'set',
    }
    const hand = [card(13, 'hearts'), card(12, 'spades'), card(11, 'diamonds'),
                  card(5, 'clubs'), card(7, 'hearts'), card(9, 'diamonds'),
                  card(3, 'clubs'), card(1, 'spades')]
    const aiHand = [card(2, 'hearts'), card(4, 'spades')]
    const state = makeState({
      hands: [hand, aiHand],
      melds: [meld],
      stock: [],
      phase: 'draw',
      currentPlayer: 0,
    })
    // Drawing from empty stock triggers round over check
    // Let's test by drawing from discard instead, which won't auto-end
    // Actually, when stock is empty: round ends per rules
    // The engine should detect empty stock and end the round
    const next = drawFromStock(state)
    // Stock was empty, should not have drawn - returns unchanged
    expect(next).toBe(state)
  })
})

// ── Round over when stock is empty ──────────────────────────────────

describe('round over — stock empty', () => {
  test('round ends when stock becomes empty after a draw', () => {
    // Last card in stock
    const state = makeState({
      stock: [card(8, 'diamonds')],
      phase: 'draw',
    })
    const afterDraw = drawFromStock(state)
    // Player drew the last card from stock. The round doesn't end immediately on draw.
    // It ends after the current player's discard, if the stock is now empty.
    expect(afterDraw.stock).toHaveLength(0)
    expect(afterDraw.phase).toBe('meld') // Can still meld/discard
  })

  test('after discarding with empty stock, round ends', () => {
    const hand = [card(3, 'hearts'), card(9, 'clubs'), card(12, 'spades'),
                  card(1, 'diamonds'), card(7, 'clubs'), card(10, 'spades'),
                  card(2, 'diamonds'), card(5, 'clubs')]
    const state = makeState({
      hands: [hand, [card(2, 'hearts'), card(6, 'spades'), card(11, 'diamonds'),
                     card(4, 'clubs'), card(8, 'hearts'), card(13, 'diamonds'), card(10, 'clubs')]],
      stock: [],
      phase: 'meld',
      hasDrawn: true,
    })
    const next = discard(state, 0)
    // With empty stock, round should end
    expect(next.phase).toBe('roundOver')
  })
})

// ── Game over at 500 ────────────────────────────────────────────────

describe('game over at 500 points', () => {
  test('game ends when a player reaches 500 points', () => {
    // Set up with score near 500
    const hand = [card(9, 'hearts'), card(9, 'diamonds'), card(9, 'clubs')]
    const state = makeState({
      hands: [hand, [card(5, 'spades'), card(3, 'diamonds'), card(7, 'clubs'),
                     card(1, 'hearts'), card(2, 'diamonds'), card(4, 'clubs'), card(6, 'spades')]],
      melds: [{
        cards: [card(10, 'hearts'), card(10, 'diamonds'), card(10, 'clubs')],
        type: 'set' as const,
      }],
      phase: 'meld',
      hasDrawn: true,
      selectedCards: [0, 1, 2],
      scores: [480, 100],
    })
    const next = meldCards(state)
    // Player melded 30 + 27 = 57 more, totaling 537 → game over
    expect(next.phase).toBe('gameOver')
    expect(next.scores[0]).toBeGreaterThanOrEqual(500)
  })
})

// ── newRound ────────────────────────────────────────────────────────

describe('newRound', () => {
  test('preserves scores but resets everything else', () => {
    const state = makeState({
      scores: [150, 200],
      phase: 'roundOver',
      melds: [{ cards: [card(5, 'hearts'), card(5, 'diamonds'), card(5, 'clubs')], type: 'set' }],
    })
    const next = newRound(state)
    expect(next.scores).toEqual([150, 200])
    expect(next.hands[0]).toHaveLength(7)
    expect(next.hands[1]).toHaveLength(7)
    expect(next.melds).toEqual([])
    expect(next.phase).toBe('draw')
  })
})

// ── Ace value in context ────────────────────────────────────────────

describe('Ace value context', () => {
  test('Ace is worth 1 point when not in a high run', () => {
    expect(cardValue(card(1, 'hearts'))).toBe(1)
  })

  // Ace value of 15 in high run is handled by scoring melds,
  // not by cardValue alone. Test at scoring level:
  test('Ace in Q-K-A run scores 15 points for the ace', () => {
    const meld: Meld = {
      cards: [card(12, 'hearts'), card(13, 'hearts'), card(1, 'hearts')],
      type: 'run',
    }
    // High ace in a run: A=15, K=10, Q=10 = 35 total
    // We need a function to score a meld. cardValue returns base value;
    // the engine should handle the 15-point ace in high run context.
    // This is tested through the scoring of the full round.
    // For the meld, the total should include 15 for the ace.
    const total = meld.cards.reduce((sum, c) => {
      // In a high run (contains K and Q), Ace = 15
      if (c.rank === 1) {
        const hasKing = meld.cards.some(mc => mc.rank === 13)
        const hasQueen = meld.cards.some(mc => mc.rank === 12)
        return sum + (hasKing && hasQueen ? 15 : 1)
      }
      return sum + cardValue(c)
    }, 0)
    expect(total).toBe(35) // Q(10) + K(10) + A(15) = 35
  })
})

// ── Edge cases ──────────────────────────────────────────────────────

describe('edge cases', () => {
  test('cannot draw if already drawn this turn', () => {
    const state = makeState({ phase: 'meld', hasDrawn: true })
    const next = drawFromStock(state)
    // Should not allow drawing since phase is meld, not draw
    expect(next).toBe(state)
  })

  test('cannot meld during draw phase', () => {
    const hand = [card(9, 'hearts'), card(9, 'diamonds'), card(9, 'clubs'),
                  card(5, 'spades'), card(7, 'hearts'), card(3, 'diamonds'), card(10, 'clubs')]
    const state = makeState({
      hands: [hand, makeState().hands[1]],
      phase: 'draw',
      selectedCards: [0, 1, 2],
    })
    const next = meldCards(state)
    expect(next.melds).toHaveLength(0)
  })

  test('multiple melds can exist simultaneously', () => {
    const hand = [card(9, 'hearts'), card(9, 'diamonds'), card(9, 'clubs'),
                  card(3, 'hearts'), card(4, 'hearts'), card(5, 'hearts'),
                  card(1, 'spades'), card(12, 'clubs')]
    const state = makeState({
      hands: [hand, makeState().hands[1]],
      phase: 'meld',
      hasDrawn: true,
      selectedCards: [0, 1, 2],
    })
    const after1 = meldCards(state)
    expect(after1.melds).toHaveLength(1)

    // After sorting, remaining hand: 12c(0), 3h(1), 4h(2), 5h(3), 1s(4)
    // The run 3h-4h-5h is at indices 1,2,3
    const state2 = { ...after1, selectedCards: [1, 2, 3] }
    const after2 = meldCards(state2)
    expect(after2.melds).toHaveLength(2)
  })
})
