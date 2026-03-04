import { describe, test, expect } from 'vitest'
import type { Card } from '../../../utils/cardUtils'
import {
  knock, canKnock, findBestMelds,
  type GinRummyState,
} from './ginRummyEngine'

// ── Helpers ─────────────────────────────────────────────────────────

function card(rank: number, suit: Card['suit']): Card {
  return { rank, suit, faceUp: true }
}

/** Build a discarding-phase state with the given player hand (11 cards). */
function discardingState(playerHand: Card[], overrides?: Partial<GinRummyState>): GinRummyState {
  return {
    playerHand,
    aiHand: Array.from({ length: 10 }, (_, i) => card((i % 13) + 1, 'spades')),
    drawPile: Array.from({ length: 10 }, (_, i) => card((i % 13) + 1, 'clubs')),
    discardPile: [card(13, 'hearts')],
    phase: 'discarding',
    currentPlayer: 0,
    knocker: null,
    playerScore: 0,
    aiScore: 0,
    roundMessage: '',
    message: 'Discard a card',
    targetScore: 100,
    ...overrides,
  }
}

// ── knock() ─────────────────────────────────────────────────────────

describe('knock', () => {
  test('auto-discards worst deadwood card before resolving', () => {
    // 3 melds of 3 (9 cards) + 2 deadwood cards → 11 total
    // Melds: [A♥ 2♥ 3♥]  [A♦ 2♦ 3♦]  [A♣ 2♣ 3♣]
    // Deadwood: 4♠(4pts), K♠(10pts) → worst is K♠
    const hand: Card[] = [
      card(1, 'hearts'), card(2, 'hearts'), card(3, 'hearts'),
      card(1, 'diamonds'), card(2, 'diamonds'), card(3, 'diamonds'),
      card(1, 'clubs'), card(2, 'clubs'), card(3, 'clubs'),
      card(4, 'spades'), card(13, 'spades'),
    ]
    expect(hand).toHaveLength(11)

    const state = discardingState(hand)
    const result = knock(state)

    // Should resolve (phase changes from 'discarding')
    expect(result.phase).not.toBe('discarding')
    // Player hand should be 10 cards after discarding
    expect(result.playerHand).toHaveLength(10)
    // K♠ (worst deadwood) should be in discard pile
    const discardedKing = result.discardPile.find(c => c.rank === 13 && c.suit === 'spades')
    expect(discardedKing).toBeDefined()
    // 4♠ should still be in player hand
    const fourInHand = result.playerHand.find(c => c.rank === 4 && c.suit === 'spades')
    expect(fourInHand).toBeDefined()
  })

  test('returns unchanged state when deadwood > 10 after discarding worst card', () => {
    // All high deadwood, no melds possible → even after discarding worst, deadwood > 10
    // 11 unrelated cards with high values: K♥ Q♥ J♥ 10♥ 9♥ K♦ Q♦ J♦ 10♦ 9♦ 8♦
    // No runs because K=13 Q=12 J=11, not consecutive with 10/9 in meld terms
    // Actually J(11) Q(12) K(13) IS a run! Let's use non-consecutive suits.
    const hand: Card[] = [
      card(13, 'hearts'), card(11, 'diamonds'), card(9, 'clubs'),
      card(7, 'hearts'), card(5, 'diamonds'), card(3, 'clubs'),
      card(12, 'spades'), card(10, 'hearts'), card(8, 'diamonds'),
      card(6, 'clubs'), card(4, 'spades'),
    ]
    expect(hand).toHaveLength(11)

    // Verify no melds form and deadwood is high even after removing worst
    const tempHand = [...hand]
    // Find highest value card — should be one of the face cards (10 pts each)
    // Removing one 10-pt card still leaves plenty of deadwood > 10
    const { deadwoodTotal } = findBestMelds(tempHand)
    expect(deadwoodTotal).toBeGreaterThan(20) // way above 10

    const state = discardingState(hand)
    const result = knock(state)

    // Should return unchanged state (still discarding)
    expect(result.phase).toBe('discarding')
    expect(result.playerHand).toHaveLength(11)
  })

  test('resolves with 10-card hand, not 11', () => {
    // Gin hand: 10 meld cards + 1 deadwood → discard deadwood → 10 cards, 0 deadwood
    const hand: Card[] = [
      card(1, 'hearts'), card(2, 'hearts'), card(3, 'hearts'),
      card(4, 'hearts'), card(5, 'hearts'), card(6, 'hearts'),
      card(7, 'hearts'), card(8, 'hearts'), card(9, 'hearts'),
      card(10, 'hearts'),
      card(5, 'spades'), // deadwood to discard
    ]
    expect(hand).toHaveLength(11)

    const state = discardingState(hand)
    const result = knock(state)

    expect(result.phase).not.toBe('discarding')
    expect(result.playerHand).toHaveLength(10)
    // The 5♠ deadwood should have been discarded
    const fiveSpades = result.playerHand.find(c => c.rank === 5 && c.suit === 'spades')
    expect(fiveSpades).toBeUndefined()
  })

  test('returns unchanged state when not in discarding phase', () => {
    const hand: Card[] = Array.from({ length: 10 }, (_, i) => card(i + 1, 'hearts'))
    const state = discardingState(hand, { phase: 'drawing' })
    const result = knock(state)
    expect(result).toBe(state)
  })

  test('returns unchanged state when not player turn', () => {
    const hand: Card[] = [
      card(1, 'hearts'), card(2, 'hearts'), card(3, 'hearts'),
      card(1, 'diamonds'), card(2, 'diamonds'), card(3, 'diamonds'),
      card(1, 'clubs'), card(2, 'clubs'), card(3, 'clubs'),
      card(4, 'spades'), card(5, 'spades'),
    ]
    const state = discardingState(hand, { currentPlayer: 1 })
    const result = knock(state)
    expect(result).toBe(state)
  })
})

// ── canKnock() ──────────────────────────────────────────────────────

describe('canKnock', () => {
  test('returns true when discarding worst card yields deadwood <= 10', () => {
    // Same hand as knock test: 9 meld cards + 4♠(4) + K♠(10) = 14 deadwood with 11 cards
    // After discarding K♠: 4 deadwood with 10 cards → can knock
    const hand: Card[] = [
      card(1, 'hearts'), card(2, 'hearts'), card(3, 'hearts'),
      card(1, 'diamonds'), card(2, 'diamonds'), card(3, 'diamonds'),
      card(1, 'clubs'), card(2, 'clubs'), card(3, 'clubs'),
      card(4, 'spades'), card(13, 'spades'),
    ]
    const state = discardingState(hand)
    expect(canKnock(state)).toBe(true)
  })

  test('returns false when no discard can bring deadwood <= 10', () => {
    // All high cards, no melds → deadwood always > 10 with 10 cards
    const hand: Card[] = [
      card(13, 'hearts'), card(11, 'diamonds'), card(9, 'clubs'),
      card(7, 'hearts'), card(5, 'diamonds'), card(3, 'clubs'),
      card(12, 'spades'), card(10, 'hearts'), card(8, 'diamonds'),
      card(6, 'clubs'), card(4, 'spades'),
    ]
    const state = discardingState(hand)
    expect(canKnock(state)).toBe(false)
  })

  test('returns false when not in discarding phase', () => {
    const hand: Card[] = Array.from({ length: 11 }, (_, i) => card(i + 1, 'hearts'))
    const state = discardingState(hand, { phase: 'drawing' })
    expect(canKnock(state)).toBe(false)
  })

  test('returns false when not player turn', () => {
    const hand: Card[] = [
      card(1, 'hearts'), card(2, 'hearts'), card(3, 'hearts'),
      card(1, 'diamonds'), card(2, 'diamonds'), card(3, 'diamonds'),
      card(1, 'clubs'), card(2, 'clubs'), card(3, 'clubs'),
      card(4, 'spades'), card(5, 'spades'),
    ]
    const state = discardingState(hand, { currentPlayer: 1 })
    expect(canKnock(state)).toBe(false)
  })

  test('returns false when hand is not 11 cards', () => {
    const hand: Card[] = Array.from({ length: 10 }, (_, i) => card(i + 1, 'hearts'))
    const state = discardingState(hand)
    expect(canKnock(state)).toBe(false)
  })
})
