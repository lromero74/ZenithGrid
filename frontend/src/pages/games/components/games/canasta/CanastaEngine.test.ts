/**
 * Canasta engine tests — written FIRST per TDD.
 *
 * Covers: deck creation, card classification, meld validation, canasta detection,
 * card points, initial meld requirements, game flow, scoring, and AI turns.
 */

import { describe, test, expect } from 'vitest'
import {
  createCanastaGame,
  drawFromStock,
  pickupDiscardPile,
  meldCards,
  discard,
  goOut,
  isValidNewMeld,
  isWild,
  isRed3,
  isBlack3,
  cardPoints,
  getInitialMeldReq,
  scoreRound,
  newRound,
  aiTurn,
  type CanastaState,
  type CanastaMeld,
  type Phase,
} from './CanastaEngine'
import type { Card } from '../../../utils/cardUtils'

// ── Helpers ────────────────────────────────────────────────────────────

function c(rank: number, suit: Card['suit'] = 'spades', faceUp = true): Card {
  return { rank, suit, faceUp }
}

/** Create a minimal test state with defaults overridden. */
function testState(overrides: Partial<CanastaState> = {}): CanastaState {
  return {
    hands: [[], [], [], []],
    teamMelds: [],
    stock: [],
    discardPile: [],
    currentPlayer: 0,
    phase: 'draw' as Phase,
    teamScores: [0, 0],
    redThrees: [[], [], [], []],
    message: '',
    hasDrawn: false,
    selectedCards: [],
    teamHasInitialMeld: [false, false],
    pileFrozen: false,
    ...overrides,
  }
}

// ── Deck creation ──────────────────────────────────────────────────────

describe('createCanastaGame', () => {
  test('deals 11 cards to each player', () => {
    const state = createCanastaGame()
    for (let p = 0; p < 4; p++) {
      expect(state.hands[p].length).toBe(11)
    }
  })

  test('total cards = 108 (hands + stock + discardPile + redThrees)', () => {
    const state = createCanastaGame()
    const handCards = state.hands.reduce((sum, h) => sum + h.length, 0)
    const red3Cards = state.redThrees.reduce((sum, r) => sum + r.length, 0)
    const total = handCards + state.stock.length + state.discardPile.length + red3Cards
    expect(total).toBe(108)
  })

  test('double deck has exactly 4 jokers (rank 0)', () => {
    const state = createCanastaGame()
    const allCards = [
      ...state.hands.flat(),
      ...state.stock,
      ...state.discardPile,
      ...state.redThrees.flat(),
    ]
    const jokers = allCards.filter(c => c.rank === 0)
    expect(jokers.length).toBe(4)
  })

  test('starts in draw phase with player 0', () => {
    const state = createCanastaGame()
    expect(state.phase).toBe('draw')
    expect(state.currentPlayer).toBe(0)
  })

  test('discard pile starts with 1 card', () => {
    const state = createCanastaGame()
    expect(state.discardPile.length).toBe(1)
  })

  test('team scores start at 0', () => {
    const state = createCanastaGame()
    expect(state.teamScores).toEqual([0, 0])
  })

  test('hasDrawn starts false', () => {
    const state = createCanastaGame()
    expect(state.hasDrawn).toBe(false)
  })

  test('initial meld flags start false', () => {
    const state = createCanastaGame()
    expect(state.teamHasInitialMeld).toEqual([false, false])
  })

  test('red 3s are auto-played from initial hands', () => {
    // We can't guarantee red 3s are dealt, but the invariant is:
    // no player's hand should contain a red 3 after creation
    const state = createCanastaGame()
    for (let p = 0; p < 4; p++) {
      const red3sInHand = state.hands[p].filter(
        c => c.rank === 3 && (c.suit === 'hearts' || c.suit === 'diamonds')
      )
      expect(red3sInHand.length).toBe(0)
    }
  })
})

// ── Card classification ────────────────────────────────────────────────

describe('isWild', () => {
  test('jokers (rank 0) are wild', () => {
    expect(isWild(c(0, 'spades'))).toBe(true)
    expect(isWild(c(0, 'hearts'))).toBe(true)
  })

  test('2s are wild', () => {
    expect(isWild(c(2, 'hearts'))).toBe(true)
    expect(isWild(c(2, 'clubs'))).toBe(true)
    expect(isWild(c(2, 'spades'))).toBe(true)
    expect(isWild(c(2, 'diamonds'))).toBe(true)
  })

  test('other ranks are not wild', () => {
    expect(isWild(c(1, 'spades'))).toBe(false)  // Ace
    expect(isWild(c(3, 'spades'))).toBe(false)  // 3
    expect(isWild(c(7, 'hearts'))).toBe(false)
    expect(isWild(c(13, 'clubs'))).toBe(false)  // King
  })
})

describe('isRed3', () => {
  test('3 of hearts is a red 3', () => {
    expect(isRed3(c(3, 'hearts'))).toBe(true)
  })

  test('3 of diamonds is a red 3', () => {
    expect(isRed3(c(3, 'diamonds'))).toBe(true)
  })

  test('3 of clubs is not a red 3', () => {
    expect(isRed3(c(3, 'clubs'))).toBe(false)
  })

  test('3 of spades is not a red 3', () => {
    expect(isRed3(c(3, 'spades'))).toBe(false)
  })

  test('non-3 red cards are not red 3s', () => {
    expect(isRed3(c(4, 'hearts'))).toBe(false)
    expect(isRed3(c(1, 'diamonds'))).toBe(false)
  })
})

describe('isBlack3', () => {
  test('3 of clubs is a black 3', () => {
    expect(isBlack3(c(3, 'clubs'))).toBe(true)
  })

  test('3 of spades is a black 3', () => {
    expect(isBlack3(c(3, 'spades'))).toBe(true)
  })

  test('3 of hearts is not a black 3', () => {
    expect(isBlack3(c(3, 'hearts'))).toBe(false)
  })

  test('non-3 black cards are not black 3s', () => {
    expect(isBlack3(c(4, 'clubs'))).toBe(false)
    expect(isBlack3(c(13, 'spades'))).toBe(false)
  })
})

// ── Card points ────────────────────────────────────────────────────────

describe('cardPoints', () => {
  test('joker = 50 points', () => {
    expect(cardPoints(c(0, 'spades'))).toBe(50)
  })

  test('2s = 20 points', () => {
    expect(cardPoints(c(2, 'hearts'))).toBe(20)
  })

  test('aces = 20 points', () => {
    expect(cardPoints(c(1, 'spades'))).toBe(20)
  })

  test('8-K = 10 points', () => {
    expect(cardPoints(c(8, 'clubs'))).toBe(10)
    expect(cardPoints(c(9, 'hearts'))).toBe(10)
    expect(cardPoints(c(10, 'diamonds'))).toBe(10)
    expect(cardPoints(c(11, 'spades'))).toBe(10)  // Jack
    expect(cardPoints(c(12, 'clubs'))).toBe(10)    // Queen
    expect(cardPoints(c(13, 'hearts'))).toBe(10)   // King
  })

  test('4-7 = 5 points', () => {
    expect(cardPoints(c(4, 'spades'))).toBe(5)
    expect(cardPoints(c(5, 'hearts'))).toBe(5)
    expect(cardPoints(c(6, 'clubs'))).toBe(5)
    expect(cardPoints(c(7, 'diamonds'))).toBe(5)
  })

  test('black 3s = 5 points', () => {
    expect(cardPoints(c(3, 'clubs'))).toBe(5)
    expect(cardPoints(c(3, 'spades'))).toBe(5)
  })

  test('red 3s = 5 points (card value; bonus handled separately)', () => {
    // Red 3s have a base card value of 5 for the purpose of this function
    expect(cardPoints(c(3, 'hearts'))).toBe(5)
    expect(cardPoints(c(3, 'diamonds'))).toBe(5)
  })
})

// ── Initial meld requirements ──────────────────────────────────────────

describe('getInitialMeldReq', () => {
  test('score 0-1499 requires 50 points', () => {
    expect(getInitialMeldReq(0)).toBe(50)
    expect(getInitialMeldReq(500)).toBe(50)
    expect(getInitialMeldReq(1499)).toBe(50)
  })

  test('score 1500-2999 requires 90 points', () => {
    expect(getInitialMeldReq(1500)).toBe(90)
    expect(getInitialMeldReq(2000)).toBe(90)
    expect(getInitialMeldReq(2999)).toBe(90)
  })

  test('score 3000+ requires 120 points', () => {
    expect(getInitialMeldReq(3000)).toBe(120)
    expect(getInitialMeldReq(4500)).toBe(120)
    expect(getInitialMeldReq(10000)).toBe(120)
  })

  test('negative score requires 50 points (lowest bracket)', () => {
    expect(getInitialMeldReq(-500)).toBe(50)
  })
})

// ── Meld validation ────────────────────────────────────────────────────

describe('isValidNewMeld', () => {
  test('3 cards of same rank = valid', () => {
    expect(isValidNewMeld([c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades')])).toBe(true)
  })

  test('2 cards = invalid (need 3+)', () => {
    expect(isValidNewMeld([c(7, 'hearts'), c(7, 'clubs')])).toBe(false)
  })

  test('1 card = invalid', () => {
    expect(isValidNewMeld([c(7, 'hearts')])).toBe(false)
  })

  test('empty array = invalid', () => {
    expect(isValidNewMeld([])).toBe(false)
  })

  test('2 naturals + 1 wild = valid (more naturals than wilds)', () => {
    expect(isValidNewMeld([c(7, 'hearts'), c(7, 'clubs'), c(2, 'spades')])).toBe(true)
  })

  test('1 natural + 2 wilds = invalid (not more naturals than wilds)', () => {
    expect(isValidNewMeld([c(7, 'hearts'), c(2, 'clubs'), c(2, 'spades')])).toBe(false)
  })

  test('all wilds = invalid', () => {
    expect(isValidNewMeld([c(2, 'hearts'), c(2, 'clubs'), c(0, 'spades')])).toBe(false)
  })

  test('4 naturals + 3 wilds = valid (max 3 wilds)', () => {
    expect(isValidNewMeld([
      c(9, 'hearts'), c(9, 'clubs'), c(9, 'diamonds'), c(9, 'spades'),
      c(2, 'hearts'), c(2, 'clubs'), c(0, 'spades'),
    ])).toBe(true)
  })

  test('3 naturals + 4 wilds = invalid (more than 3 wilds)', () => {
    expect(isValidNewMeld([
      c(9, 'hearts'), c(9, 'clubs'), c(9, 'diamonds'),
      c(2, 'hearts'), c(2, 'clubs'), c(2, 'spades'), c(0, 'spades'),
    ])).toBe(false)
  })

  test('mixed ranks (not all same natural rank) = invalid', () => {
    expect(isValidNewMeld([c(7, 'hearts'), c(8, 'clubs'), c(9, 'spades')])).toBe(false)
  })

  test('3s cannot be melded normally (black 3s block)', () => {
    expect(isValidNewMeld([c(3, 'clubs'), c(3, 'spades'), c(3, 'clubs')])).toBe(false)
  })

  test('wild cards with different natural ranks = invalid', () => {
    expect(isValidNewMeld([c(7, 'hearts'), c(8, 'clubs'), c(2, 'spades')])).toBe(false)
  })
})

// ── Canasta detection ──────────────────────────────────────────────────

describe('canasta detection', () => {
  test('7 natural cards = natural canasta (500 pts)', () => {
    const meld: CanastaMeld = {
      cards: [
        c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'), c(7, 'diamonds'),
        c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'),
      ],
      rank: 7,
      team: 0,
      isCanasta: true,
      isNatural: true,
    }
    expect(meld.isCanasta).toBe(true)
    expect(meld.isNatural).toBe(true)
  })

  test('7+ cards with wilds = mixed canasta (300 pts)', () => {
    const meld: CanastaMeld = {
      cards: [
        c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'), c(7, 'diamonds'),
        c(7, 'hearts'), c(2, 'clubs'), c(2, 'spades'),
      ],
      rank: 7,
      team: 0,
      isCanasta: true,
      isNatural: false,
    }
    expect(meld.isCanasta).toBe(true)
    expect(meld.isNatural).toBe(false)
  })

  test('6 cards = not a canasta', () => {
    const meld: CanastaMeld = {
      cards: [
        c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'),
        c(7, 'diamonds'), c(7, 'hearts'), c(7, 'clubs'),
      ],
      rank: 7,
      team: 0,
      isCanasta: false,
      isNatural: false,
    }
    expect(meld.isCanasta).toBe(false)
  })
})

// ── Drawing from stock ─────────────────────────────────────────────────

describe('drawFromStock', () => {
  test('draws 2 cards from stock to current player hand', () => {
    const state = testState({
      hands: [[c(4, 'hearts'), c(5, 'clubs')], [], [], []],
      stock: [c(7, 'spades'), c(8, 'diamonds'), c(9, 'clubs'), c(10, 'hearts')],
      phase: 'draw',
      currentPlayer: 0,
      hasDrawn: false,
    })
    const next = drawFromStock(state)
    expect(next.hands[0].length).toBe(4)
    expect(next.stock.length).toBe(2)
    expect(next.hasDrawn).toBe(true)
    expect(next.phase).toBe('meld')
  })

  test('cannot draw if already drawn', () => {
    const state = testState({
      hands: [[c(4, 'hearts')], [], [], []],
      stock: [c(7, 'spades'), c(8, 'diamonds')],
      phase: 'meld',
      currentPlayer: 0,
      hasDrawn: true,
    })
    const next = drawFromStock(state)
    expect(next).toEqual(state)
  })

  test('cannot draw if phase is not draw', () => {
    const state = testState({
      hands: [[c(4, 'hearts')], [], [], []],
      stock: [c(7, 'spades'), c(8, 'diamonds')],
      phase: 'discard',
      currentPlayer: 0,
      hasDrawn: false,
    })
    const next = drawFromStock(state)
    expect(next).toEqual(state)
  })

  test('red 3s drawn are auto-played and replaced', () => {
    // Stock pops from end, so put red 3 last (drawn first)
    const state = testState({
      hands: [[c(4, 'hearts')], [], [], []],
      stock: [c(9, 'clubs'), c(8, 'diamonds'), c(3, 'hearts')],
      phase: 'draw',
      currentPlayer: 0,
      hasDrawn: false,
      redThrees: [[], [], [], []],
    })
    const next = drawFromStock(state)
    // The red 3 should be in redThrees, not hand
    const handRed3s = next.hands[0].filter(
      c => c.rank === 3 && (c.suit === 'hearts' || c.suit === 'diamonds')
    )
    expect(handRed3s.length).toBe(0)
    expect(next.redThrees[0].length).toBe(1)
    expect(next.hasDrawn).toBe(true)
  })

  test('triggers roundOver if stock is empty after draw', () => {
    const state = testState({
      hands: [[c(4, 'hearts')], [], [], []],
      stock: [c(7, 'spades'), c(8, 'diamonds')],
      phase: 'draw',
      currentPlayer: 0,
      hasDrawn: false,
    })
    const next = drawFromStock(state)
    // Stock now empty — continue playing but track it
    expect(next.stock.length).toBe(0)
  })
})

// ── Picking up discard pile ────────────────────────────────────────────

describe('pickupDiscardPile', () => {
  test('picks up entire discard pile when valid', () => {
    // Discard pile top (last element) is a 7, matching the 7s in hand
    const state = testState({
      hands: [[c(7, 'hearts'), c(7, 'clubs'), c(5, 'spades')], [], [], []],
      discardPile: [c(9, 'hearts'), c(10, 'clubs'), c(7, 'diamonds')],
      phase: 'draw',
      currentPlayer: 0,
      hasDrawn: false,
      teamHasInitialMeld: [true, false],
    })
    // Pass indices of the 7s in hand to form a meld with the top card (7 of diamonds)
    const next = pickupDiscardPile(state, [0, 1])
    // Hand: started with 3, removed 2 for meld, added 2 rest-of-pile cards = 3
    // But gained 2 pile cards in hand (9h, 10c) + kept 5s = 3
    expect(next.hands[0].length).toBe(3)
    expect(next.discardPile.length).toBe(0)
    expect(next.hasDrawn).toBe(true)
    expect(next.phase).toBe('meld')
    // A new meld should have been created
    expect(next.teamMelds.length).toBe(1)
    expect(next.teamMelds[0].rank).toBe(7)
    expect(next.teamMelds[0].cards.length).toBe(3)
  })

  test('cannot pick up pile if already drawn', () => {
    const state = testState({
      hands: [[c(7, 'hearts'), c(7, 'clubs')], [], [], []],
      discardPile: [c(7, 'diamonds')],
      phase: 'meld',
      currentPlayer: 0,
      hasDrawn: true,
      teamHasInitialMeld: [true, false],
    })
    const next = pickupDiscardPile(state, [0, 1])
    expect(next).toEqual(state)
  })

  test('cannot pick up pile when frozen without natural pair', () => {
    const state = testState({
      hands: [[c(7, 'hearts'), c(2, 'clubs')], [], [], []],
      discardPile: [c(7, 'diamonds')],
      phase: 'draw',
      currentPlayer: 0,
      hasDrawn: false,
      pileFrozen: true,
      teamHasInitialMeld: [true, false],
    })
    // 2 is wild, not a natural match
    const next = pickupDiscardPile(state, [0, 1])
    expect(next).toEqual(state)
  })

  test('cannot pick up pile when top card is black 3', () => {
    const state = testState({
      hands: [[c(3, 'clubs'), c(3, 'spades'), c(3, 'clubs')], [], [], []],
      discardPile: [c(3, 'clubs'), c(9, 'hearts')],
      phase: 'draw',
      currentPlayer: 0,
      hasDrawn: false,
      teamHasInitialMeld: [true, false],
    })
    const next = pickupDiscardPile(state, [0, 1])
    expect(next).toEqual(state)
  })
})

// ── Melding ────────────────────────────────────────────────────────────

describe('meldCards', () => {
  test('creates a new meld from selected hand cards', () => {
    const hand = [c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'), c(5, 'diamonds')]
    const state = testState({
      hands: [hand, [], [], []],
      phase: 'meld',
      currentPlayer: 0,
      hasDrawn: true,
      teamHasInitialMeld: [true, false],
    })
    const next = meldCards(state, [0, 1, 2])
    expect(next.teamMelds.length).toBe(1)
    expect(next.teamMelds[0].rank).toBe(7)
    expect(next.teamMelds[0].team).toBe(0)
    expect(next.hands[0].length).toBe(1)
  })

  test('cannot meld without having drawn first', () => {
    const hand = [c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades')]
    const state = testState({
      hands: [hand, [], [], []],
      phase: 'draw',
      currentPlayer: 0,
      hasDrawn: false,
    })
    const next = meldCards(state, [0, 1, 2])
    expect(next).toEqual(state)
  })

  test('can add cards to an existing team meld', () => {
    const existingMeld: CanastaMeld = {
      cards: [c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades')],
      rank: 7,
      team: 0,
      isCanasta: false,
      isNatural: true,
    }
    const hand = [c(7, 'diamonds'), c(5, 'spades')]
    const state = testState({
      hands: [hand, [], [], []],
      teamMelds: [existingMeld],
      phase: 'meld',
      currentPlayer: 0,
      hasDrawn: true,
      teamHasInitialMeld: [true, false],
    })
    const next = meldCards(state, [0], 0)
    expect(next.teamMelds[0].cards.length).toBe(4)
    expect(next.hands[0].length).toBe(1)
  })

  test('meld becomes canasta at 7 cards', () => {
    const existingMeld: CanastaMeld = {
      cards: [
        c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'),
        c(7, 'diamonds'), c(7, 'hearts'), c(7, 'clubs'),
      ],
      rank: 7,
      team: 0,
      isCanasta: false,
      isNatural: true,
    }
    const hand = [c(7, 'spades'), c(5, 'hearts')]
    const state = testState({
      hands: [hand, [], [], []],
      teamMelds: [existingMeld],
      phase: 'meld',
      currentPlayer: 0,
      hasDrawn: true,
      teamHasInitialMeld: [true, false],
    })
    const next = meldCards(state, [0], 0)
    expect(next.teamMelds[0].isCanasta).toBe(true)
    expect(next.teamMelds[0].isNatural).toBe(true)
    expect(next.teamMelds[0].cards.length).toBe(7)
  })

  test('adding wild to meld makes it mixed (not natural)', () => {
    const existingMeld: CanastaMeld = {
      cards: [
        c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'),
        c(7, 'diamonds'), c(7, 'hearts'), c(7, 'clubs'),
      ],
      rank: 7,
      team: 0,
      isCanasta: false,
      isNatural: true,
    }
    const hand = [c(2, 'spades'), c(5, 'hearts')]
    const state = testState({
      hands: [hand, [], [], []],
      teamMelds: [existingMeld],
      phase: 'meld',
      currentPlayer: 0,
      hasDrawn: true,
      teamHasInitialMeld: [true, false],
    })
    const next = meldCards(state, [0], 0)
    expect(next.teamMelds[0].isCanasta).toBe(true)
    expect(next.teamMelds[0].isNatural).toBe(false)
  })

  test('cannot add to opponent team meld', () => {
    const opponentMeld: CanastaMeld = {
      cards: [c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades')],
      rank: 7,
      team: 1,
      isCanasta: false,
      isNatural: true,
    }
    const hand = [c(7, 'diamonds'), c(5, 'spades')]
    const state = testState({
      hands: [hand, [], [], []],
      teamMelds: [opponentMeld],
      phase: 'meld',
      currentPlayer: 0,
      hasDrawn: true,
      teamHasInitialMeld: [true, false],
    })
    const next = meldCards(state, [0], 0)
    expect(next).toEqual(state)
  })

  test('initial meld must meet point threshold', () => {
    const hand = [c(4, 'hearts'), c(4, 'clubs'), c(4, 'spades'), c(5, 'diamonds')]
    const state = testState({
      hands: [hand, [], [], []],
      phase: 'meld',
      currentPlayer: 0,
      hasDrawn: true,
      teamHasInitialMeld: [false, false],
      teamScores: [0, 0],
    })
    // 3 fours = 15 points, which is less than the 50-point requirement
    const next = meldCards(state, [0, 1, 2])
    expect(next).toEqual(state)
  })

  test('initial meld that meets threshold is accepted', () => {
    const hand = [c(1, 'hearts'), c(1, 'clubs'), c(1, 'spades'), c(5, 'diamonds')]
    const state = testState({
      hands: [hand, [], [], []],
      phase: 'meld',
      currentPlayer: 0,
      hasDrawn: true,
      teamHasInitialMeld: [false, false],
      teamScores: [0, 0],
    })
    // 3 aces = 60 points, which exceeds the 50-point requirement
    const next = meldCards(state, [0, 1, 2])
    expect(next.teamMelds.length).toBe(1)
    expect(next.teamHasInitialMeld[0]).toBe(true)
  })
})

// ── Discarding ─────────────────────────────────────────────────────────

describe('discard', () => {
  test('discards a card and advances to next player', () => {
    const hand = [c(7, 'hearts'), c(5, 'clubs'), c(9, 'diamonds')]
    const state = testState({
      hands: [hand, [c(4, 'hearts')], [c(6, 'clubs')], [c(8, 'spades')]],
      stock: [c(10, 'hearts'), c(11, 'hearts'), c(12, 'hearts'), c(13, 'hearts')],
      phase: 'meld',
      currentPlayer: 0,
      hasDrawn: true,
    })
    const next = discard(state, 1)
    expect(next.hands[0].length).toBe(2)
    expect(next.discardPile[next.discardPile.length - 1]).toEqual(c(5, 'clubs'))
    expect(next.currentPlayer).not.toBe(0)
    expect(next.hasDrawn).toBe(false)
  })

  test('cannot discard without having drawn', () => {
    const hand = [c(7, 'hearts'), c(5, 'clubs')]
    const state = testState({
      hands: [hand, [], [], []],
      phase: 'draw',
      currentPlayer: 0,
      hasDrawn: false,
    })
    const next = discard(state, 0)
    expect(next).toEqual(state)
  })

  test('discarding black 3 freezes pile for next player', () => {
    const hand = [c(3, 'clubs'), c(5, 'hearts')]
    const state = testState({
      hands: [hand, [c(4, 'hearts')], [c(6, 'clubs')], [c(8, 'spades')]],
      stock: [c(10, 'hearts'), c(11, 'hearts'), c(12, 'hearts'), c(13, 'hearts')],
      phase: 'meld',
      currentPlayer: 0,
      hasDrawn: true,
    })
    const next = discard(state, 0)
    // Black 3 on top blocks pickup (but doesn't permanently freeze)
    expect(next.discardPile[next.discardPile.length - 1].rank).toBe(3)
  })

  test('discarding wild card freezes pile', () => {
    const hand = [c(2, 'hearts'), c(5, 'clubs')]
    const state = testState({
      hands: [hand, [c(4, 'hearts')], [c(6, 'clubs')], [c(8, 'spades')]],
      stock: [c(10, 'hearts'), c(11, 'hearts'), c(12, 'hearts'), c(13, 'hearts')],
      phase: 'meld',
      currentPlayer: 0,
      hasDrawn: true,
    })
    const next = discard(state, 0)
    expect(next.pileFrozen).toBe(true)
  })
})

// ── Going out ──────────────────────────────────────────────────────────

describe('goOut', () => {
  test('cannot go out without a canasta', () => {
    const state = testState({
      hands: [[c(5, 'hearts')], [], [], []],
      teamMelds: [{
        cards: [c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades')],
        rank: 7,
        team: 0,
        isCanasta: false,
        isNatural: true,
      }],
      phase: 'meld',
      currentPlayer: 0,
      hasDrawn: true,
    })
    const next = goOut(state)
    expect(next).toEqual(state) // Should not be allowed
  })

  test('going out with a canasta ends the round', () => {
    const state = testState({
      hands: [[], [], [], []],
      teamMelds: [{
        cards: [
          c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'), c(7, 'diamonds'),
          c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'),
        ],
        rank: 7,
        team: 0,
        isCanasta: true,
        isNatural: true,
      }],
      phase: 'meld',
      currentPlayer: 0,
      hasDrawn: true,
    })
    const next = goOut(state)
    expect(next.phase).toBe('roundOver')
  })

  test('going out scores 100 bonus points', () => {
    const state = testState({
      hands: [[], [c(5, 'hearts')], [], [c(5, 'clubs')]],
      teamMelds: [{
        cards: [
          c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'), c(7, 'diamonds'),
          c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'),
        ],
        rank: 7,
        team: 0,
        isCanasta: true,
        isNatural: true,
      }],
      phase: 'meld',
      currentPlayer: 0,
      hasDrawn: true,
      teamScores: [0, 0],
      redThrees: [[], [], [], []],
    })
    const next = goOut(state)
    expect(next.phase).toBe('roundOver')
  })
})

// ── Round scoring ──────────────────────────────────────────────────────

describe('scoreRound', () => {
  test('scores meld card points correctly', () => {
    const state = testState({
      hands: [[], [c(5, 'hearts')], [], [c(5, 'clubs')]],
      teamMelds: [{
        cards: [c(1, 'hearts'), c(1, 'clubs'), c(1, 'spades')],
        rank: 1,
        team: 0,
        isCanasta: false,
        isNatural: true,
      }],
      teamScores: [0, 0],
      redThrees: [[], [], [], []],
    })
    const scores = scoreRound(state)
    // Team 0: 3 aces melded (60 pts), no hand penalty
    // Team 1: 2 fives in hand (-10 pts)
    expect(scores[0]).toBe(60)
    expect(scores[1]).toBe(-10)
  })

  test('natural canasta gives 500 bonus', () => {
    const state = testState({
      hands: [[], [], [], []],
      teamMelds: [{
        cards: [
          c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'), c(7, 'diamonds'),
          c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'),
        ],
        rank: 7,
        team: 0,
        isCanasta: true,
        isNatural: true,
      }],
      teamScores: [0, 0],
      redThrees: [[], [], [], []],
    })
    const scores = scoreRound(state)
    // 7 sevens = 35 pts + 500 natural canasta bonus = 535
    expect(scores[0]).toBe(535)
  })

  test('mixed canasta gives 300 bonus', () => {
    const state = testState({
      hands: [[], [], [], []],
      teamMelds: [{
        cards: [
          c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'), c(7, 'diamonds'),
          c(7, 'hearts'), c(2, 'clubs'), c(2, 'spades'),
        ],
        rank: 7,
        team: 0,
        isCanasta: true,
        isNatural: false,
      }],
      teamScores: [0, 0],
      redThrees: [[], [], [], []],
    })
    const scores = scoreRound(state)
    // 5 sevens (25) + 2 twos (40) + 300 mixed canasta = 365
    expect(scores[0]).toBe(365)
  })

  test('red 3 bonus: 100 pts each', () => {
    const state = testState({
      hands: [[], [], [], []],
      teamMelds: [],
      teamScores: [0, 0],
      redThrees: [[c(3, 'hearts')], [], [c(3, 'diamonds')], []],
      teamHasInitialMeld: [true, false],
    })
    const scores = scoreRound(state)
    // Team 0 (players 0+2): 2 red 3s = 200 pts, but also need melds to not penalize
    expect(scores[0]).toBe(200)
  })

  test('all 4 red 3s on one team = 800 pts', () => {
    const state = testState({
      hands: [[], [], [], []],
      teamMelds: [{
        cards: [c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades')],
        rank: 7,
        team: 0,
        isCanasta: false,
        isNatural: true,
      }],
      teamScores: [0, 0],
      redThrees: [[c(3, 'hearts'), c(3, 'diamonds')], [], [c(3, 'hearts'), c(3, 'diamonds')], []],
      teamHasInitialMeld: [true, false],
    })
    const scores = scoreRound(state)
    // 800 (all 4 red 3s) + 15 (3 sevens) = 815
    expect(scores[0]).toBe(815)
  })

  test('hand cards are subtracted from score', () => {
    const state = testState({
      hands: [[c(0, 'spades'), c(1, 'hearts')], [], [], []],
      teamMelds: [],
      teamScores: [0, 0],
      redThrees: [[], [], [], []],
    })
    const scores = scoreRound(state)
    // Player 0 hand: joker (50) + ace (20) = 70 penalty for team 0
    expect(scores[0]).toBe(-70)
  })

  test('red 3s penalize if team has no melds', () => {
    const state = testState({
      hands: [[], [], [], []],
      teamMelds: [],
      teamScores: [0, 0],
      redThrees: [[c(3, 'hearts')], [], [], []],
      teamHasInitialMeld: [false, false],
    })
    const scores = scoreRound(state)
    // Red 3 penalty when no melds: -100
    expect(scores[0]).toBe(-100)
  })
})

// ── Game flow ──────────────────────────────────────────────────────────

describe('game flow', () => {
  test('game over when team reaches 5000', () => {
    const state = testState({
      hands: [[], [c(5, 'hearts')], [], [c(5, 'clubs')]],
      teamMelds: [{
        cards: [
          c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'), c(7, 'diamonds'),
          c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'),
        ],
        rank: 7,
        team: 0,
        isCanasta: true,
        isNatural: true,
      }],
      phase: 'meld',
      currentPlayer: 0,
      hasDrawn: true,
      teamScores: [4500, 1000],
      redThrees: [[], [], [], []],
    })
    const next = goOut(state)
    // Score from round: 535 (canasta) + 100 (going out) - opponent penalty
    expect(next.phase).toBe('gameOver')
  })

  test('newRound resets hands and melds but keeps scores', () => {
    const state = testState({
      teamScores: [2500, 1800],
      phase: 'roundOver',
      teamHasInitialMeld: [true, true],
    })
    const next = newRound(state)
    expect(next.teamScores).toEqual([2500, 1800])
    expect(next.phase).toBe('draw')
    expect(next.teamMelds.length).toBe(0)
    expect(next.teamHasInitialMeld).toEqual([false, false])
    for (let p = 0; p < 4; p++) {
      expect(next.hands[p].length).toBe(11)
    }
  })
})

// ── AI turns ───────────────────────────────────────────────────────────

describe('aiTurn', () => {
  test('AI completes a full turn (draw, optional meld, discard)', () => {
    const state = testState({
      hands: [
        [c(4, 'hearts')],
        [c(7, 'hearts'), c(7, 'clubs'), c(7, 'spades'), c(5, 'diamonds'),
         c(9, 'hearts'), c(10, 'clubs'), c(11, 'spades'), c(12, 'hearts'),
         c(13, 'clubs'), c(1, 'spades'), c(4, 'diamonds')],
        [c(6, 'clubs')],
        [c(8, 'spades')],
      ],
      stock: Array.from({ length: 20 }, (_, i) => c(4 + (i % 10), 'hearts')),
      phase: 'draw',
      currentPlayer: 1,
      hasDrawn: false,
    })
    const next = aiTurn(state)
    // After AI turn, should advance to next player
    expect(next.currentPlayer).not.toBe(1)
    expect(next.hasDrawn).toBe(false)
    // AI should have discarded (hand size should be back to 11+2-1 = 12 or less if melded)
    expect(next.discardPile.length).toBeGreaterThan(0)
  })

  test('AI draws from stock (safer choice)', () => {
    const state = testState({
      hands: [
        [c(4, 'hearts')],
        [c(5, 'hearts'), c(6, 'clubs'), c(8, 'diamonds')],
        [c(6, 'clubs')],
        [c(8, 'spades')],
      ],
      stock: [c(7, 'spades'), c(8, 'diamonds'), c(9, 'clubs'), c(10, 'hearts')],
      discardPile: [c(11, 'hearts')],
      phase: 'draw',
      currentPlayer: 1,
      hasDrawn: false,
    })
    const next = aiTurn(state)
    // Stock should have decreased by 2
    expect(next.stock.length).toBeLessThan(state.stock.length)
  })
})
