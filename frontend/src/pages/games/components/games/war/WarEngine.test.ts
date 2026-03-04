import { describe, test, expect } from 'vitest'
import type { Card } from '../../../utils/cardUtils'
import {
  createWarGame,
  flipCards,
  resolveCompare,
  resolveWar,
  getCompareValue,
  type WarState,
} from './WarEngine'

// ── Helpers ─────────────────────────────────────────────────────────

function card(rank: number, suit: Card['suit'], faceUp = false): Card {
  return { rank, suit, faceUp }
}

/** Build a custom WarState for testing specific scenarios. */
function makeState(overrides: Partial<WarState> = {}): WarState {
  return {
    playerDeck: [],
    aiDeck: [],
    playerCard: null,
    aiCard: null,
    warPile: [],
    phase: 'ready',
    message: '',
    round: 0,
    maxRounds: 200,
    playerScore: 0,
    aiScore: 0,
    ...overrides,
  }
}

// ── getCompareValue ─────────────────────────────────────────────────

describe('getCompareValue', () => {
  test('ace (rank 1) returns 14', () => {
    expect(getCompareValue(card(1, 'hearts'))).toBe(14)
  })

  test('king (rank 13) returns 13', () => {
    expect(getCompareValue(card(13, 'spades'))).toBe(13)
  })

  test('numbered card returns its rank', () => {
    expect(getCompareValue(card(7, 'diamonds'))).toBe(7)
  })
})

// ── createWarGame ───────────────────────────────────────────────────

describe('createWarGame', () => {
  test('creates a game with 26 cards each', () => {
    const state = createWarGame()
    expect(state.playerDeck).toHaveLength(26)
    expect(state.aiDeck).toHaveLength(26)
  })

  test('uses all 52 unique cards', () => {
    const state = createWarGame()
    const allCards = [...state.playerDeck, ...state.aiDeck]
    expect(allCards).toHaveLength(52)
    const uniqueKeys = new Set(allCards.map(c => `${c.rank}-${c.suit}`))
    expect(uniqueKeys.size).toBe(52)
  })

  test('starts in ready phase with round 0', () => {
    const state = createWarGame()
    expect(state.phase).toBe('ready')
    expect(state.round).toBe(0)
    expect(state.playerCard).toBeNull()
    expect(state.aiCard).toBeNull()
    expect(state.warPile).toHaveLength(0)
  })

  test('scores start at 0', () => {
    const state = createWarGame()
    expect(state.playerScore).toBe(0)
    expect(state.aiScore).toBe(0)
  })
})

// ── flipCards ───────────────────────────────────────────────────────

describe('flipCards', () => {
  test('takes top card from each deck and sets phase to compare', () => {
    const state = makeState({
      playerDeck: [card(10, 'hearts'), card(5, 'clubs')],
      aiDeck: [card(7, 'diamonds'), card(3, 'spades')],
      phase: 'ready',
      round: 0,
    })
    const result = flipCards(state)
    expect(result.phase).toBe('compare')
    expect(result.playerCard?.rank).toBe(10)
    expect(result.aiCard?.rank).toBe(7)
    expect(result.playerDeck).toHaveLength(1)
    expect(result.aiDeck).toHaveLength(1)
    expect(result.round).toBe(1)
  })

  test('flipped cards are face up', () => {
    const state = makeState({
      playerDeck: [card(4, 'hearts')],
      aiDeck: [card(9, 'clubs')],
      phase: 'ready',
    })
    const result = flipCards(state)
    expect(result.playerCard?.faceUp).toBe(true)
    expect(result.aiCard?.faceUp).toBe(true)
  })

  test('does nothing if not in ready phase', () => {
    const state = makeState({ phase: 'compare' })
    const result = flipCards(state)
    expect(result).toEqual(state)
  })
})

// ── resolveCompare ──────────────────────────────────────────────────

describe('resolveCompare', () => {
  test('higher rank wins both cards — player wins', () => {
    const state = makeState({
      playerDeck: [card(2, 'clubs')],
      aiDeck: [card(3, 'spades')],
      playerCard: card(10, 'hearts', true),
      aiCard: card(7, 'diamonds', true),
      phase: 'compare',
    })
    const result = resolveCompare(state)
    expect(result.phase).toBe('ready')
    // Player had 1 card in deck + wins 2 = 3
    expect(result.playerDeck).toHaveLength(3)
    expect(result.aiDeck).toHaveLength(1)
    expect(result.playerCard).toBeNull()
    expect(result.aiCard).toBeNull()
  })

  test('higher rank wins both cards — AI wins', () => {
    const state = makeState({
      playerDeck: [card(2, 'clubs')],
      aiDeck: [card(3, 'spades')],
      playerCard: card(4, 'hearts', true),
      aiCard: card(12, 'diamonds', true),
      phase: 'compare',
    })
    const result = resolveCompare(state)
    expect(result.phase).toBe('ready')
    expect(result.aiDeck).toHaveLength(3)
    expect(result.playerDeck).toHaveLength(1)
  })

  test('ace beats king', () => {
    const state = makeState({
      playerDeck: [],
      aiDeck: [],
      playerCard: card(1, 'hearts', true),
      aiCard: card(13, 'spades', true),
      phase: 'compare',
    })
    const result = resolveCompare(state)
    // Player wins — ace is 14, king is 13
    expect(result.playerDeck).toHaveLength(2)
    expect(result.aiDeck).toHaveLength(0)
  })

  test('tie triggers war phase', () => {
    const state = makeState({
      playerDeck: [card(2, 'hearts'), card(3, 'hearts'), card(4, 'hearts'), card(5, 'hearts')],
      aiDeck: [card(2, 'clubs'), card(3, 'clubs'), card(4, 'clubs'), card(5, 'clubs')],
      playerCard: card(8, 'diamonds', true),
      aiCard: card(8, 'spades', true),
      phase: 'compare',
    })
    const result = resolveCompare(state)
    expect(result.phase).toBe('war')
    expect(result.message).toContain('War')
  })

  test('does nothing if not in compare phase', () => {
    const state = makeState({ phase: 'ready' })
    const result = resolveCompare(state)
    expect(result).toEqual(state)
  })

  test('player winning sets game over if AI has no cards left', () => {
    const state = makeState({
      playerDeck: [],
      aiDeck: [],
      playerCard: card(10, 'hearts', true),
      aiCard: card(5, 'spades', true),
      phase: 'compare',
    })
    const result = resolveCompare(state)
    expect(result.phase).toBe('gameOver')
  })
})

// ── resolveWar ──────────────────────────────────────────────────────

describe('resolveWar', () => {
  test('war: each player puts 3 face-down + 1 face-up, higher wins all', () => {
    const pDeck = [
      card(2, 'hearts'), card(3, 'hearts'), card(4, 'hearts'), card(10, 'diamonds'),
    ]
    const aDeck = [
      card(2, 'clubs'), card(3, 'clubs'), card(4, 'clubs'), card(6, 'spades'),
    ]
    const state = makeState({
      playerDeck: pDeck,
      aiDeck: aDeck,
      playerCard: card(8, 'diamonds', true),
      aiCard: card(8, 'spades', true),
      warPile: [],
      phase: 'war',
    })
    const result = resolveWar(state)
    // Player's face-up is 10♦ (value 10), AI's is 6♠ (value 6) → player wins
    // Total cards in play: 2 flipped + 8 war cards = 10
    expect(result.playerDeck).toHaveLength(10)
    expect(result.aiDeck).toHaveLength(0)
    expect(result.phase).toBe('gameOver') // AI has 0 cards
  })

  test('player with insufficient cards for war loses immediately', () => {
    // Player has only 2 cards, needs 4 (3 face-down + 1 face-up) for war
    const state = makeState({
      playerDeck: [card(2, 'hearts'), card(3, 'hearts')],
      aiDeck: [card(2, 'clubs'), card(3, 'clubs'), card(4, 'clubs'), card(9, 'spades')],
      playerCard: card(8, 'diamonds', true),
      aiCard: card(8, 'spades', true),
      phase: 'war',
    })
    const result = resolveWar(state)
    expect(result.phase).toBe('gameOver')
    expect(result.message).toContain('AI')
  })

  test('AI with insufficient cards for war loses immediately', () => {
    const state = makeState({
      playerDeck: [card(2, 'hearts'), card(3, 'hearts'), card(4, 'hearts'), card(9, 'diamonds')],
      aiDeck: [card(2, 'clubs')],
      playerCard: card(8, 'diamonds', true),
      aiCard: card(8, 'spades', true),
      phase: 'war',
    })
    const result = resolveWar(state)
    expect(result.phase).toBe('gameOver')
    expect(result.message).toContain('You')
  })

  test('war tie triggers another war (double war)', () => {
    // Both face-up cards tie again → another war round
    const pDeck = [
      card(2, 'hearts'), card(3, 'hearts'), card(4, 'hearts'), card(7, 'diamonds'),
      card(5, 'hearts'), card(6, 'hearts'), card(9, 'hearts'), card(13, 'diamonds'),
    ]
    const aDeck = [
      card(2, 'clubs'), card(3, 'clubs'), card(4, 'clubs'), card(7, 'spades'),
      card(5, 'clubs'), card(6, 'clubs'), card(9, 'clubs'), card(10, 'spades'),
    ]
    const state = makeState({
      playerDeck: pDeck,
      aiDeck: aDeck,
      playerCard: card(8, 'diamonds', true),
      aiCard: card(8, 'spades', true),
      warPile: [],
      phase: 'war',
    })
    // First war: both flip 7 → tie → another war
    // Second war: player flips K(13), AI flips 10 → player wins
    const result = resolveWar(state)
    // Player wins all 18 cards (2 initial + 8 first war + 8 second war)
    expect(result.playerDeck).toHaveLength(18)
    expect(result.aiDeck).toHaveLength(0)
  })

  test('does nothing if not in war phase', () => {
    const state = makeState({ phase: 'ready' })
    const result = resolveWar(state)
    expect(result).toEqual(state)
  })
})

// ── Game over conditions ────────────────────────────────────────────

describe('game over conditions', () => {
  test('game ends after max rounds — player with more cards wins', () => {
    const state = makeState({
      playerDeck: [card(10, 'hearts'), card(5, 'clubs')],
      aiDeck: [card(3, 'spades')],
      phase: 'ready',
      round: 199,
      maxRounds: 200,
    })
    // Flip should be round 200 (the max)
    const flipped = flipCards(state)
    expect(flipped.round).toBe(200)
    const result = resolveCompare(flipped)
    // After resolving, even if the game could continue, max rounds should end it
    // The winner is whoever has more cards
    expect(result.phase).toBe('gameOver')
  })

  test('game ends when one player has all 52 cards', () => {
    // Player has 51 cards, AI has 1. Player wins the flip → gets all 52.
    const playerDeck = Array.from({ length: 51 }, (_, i) =>
      card((i % 13) + 1, (['hearts', 'diamonds', 'clubs', 'spades'] as const)[Math.floor(i / 13)])
    )
    // Give AI just one card that's lower
    const state = makeState({
      playerDeck: playerDeck.slice(1),
      aiDeck: [],
      playerCard: card(10, 'hearts', true),
      aiCard: card(3, 'diamonds', true),
      phase: 'compare',
    })
    const result = resolveCompare(state)
    expect(result.phase).toBe('gameOver')
    expect(result.message).toContain('You')
  })
})
