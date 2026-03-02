/**
 * Video Poker (Jacks or Better) engine — pure logic, no React.
 */

import { createDeck, shuffleDeck, type Card } from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

export type Phase = 'betting' | 'dealt' | 'drawing' | 'result'

export interface VideoPokerState {
  hand: Card[]
  held: boolean[]
  deck: Card[]
  credits: number
  bet: number
  phase: Phase
  lastResult: HandResult | null
  message: string
}

export interface HandResult {
  name: string
  multiplier: number
}

// ── Constants ────────────────────────────────────────────────────────

export const STARTING_CREDITS = 100
export const MAX_BET = 5
export const MIN_BET = 1

// Pay table (multiplier per 1 credit bet, except Royal Flush at max bet = 800)
const PAY_TABLE: { name: string; multiplier: number; maxBetMultiplier?: number }[] = [
  { name: 'Royal Flush', multiplier: 250, maxBetMultiplier: 800 },
  { name: 'Straight Flush', multiplier: 50 },
  { name: 'Four of a Kind', multiplier: 25 },
  { name: 'Full House', multiplier: 9 },
  { name: 'Flush', multiplier: 6 },
  { name: 'Straight', multiplier: 4 },
  { name: 'Three of a Kind', multiplier: 3 },
  { name: 'Two Pair', multiplier: 2 },
  { name: 'Jacks or Better', multiplier: 1 },
]

export function getPayTable(): typeof PAY_TABLE {
  return PAY_TABLE
}

// ── Hand evaluation ──────────────────────────────────────────────────

function getRankCounts(cards: Card[]): Map<number, number> {
  const counts = new Map<number, number>()
  for (const c of cards) {
    counts.set(c.rank, (counts.get(c.rank) || 0) + 1)
  }
  return counts
}

function isFlush(cards: Card[]): boolean {
  return cards.every(c => c.suit === cards[0].suit)
}

function isStraight(cards: Card[]): boolean {
  const ranks = cards.map(c => c.rank).sort((a, b) => a - b)
  // Check normal straight
  for (let i = 1; i < ranks.length; i++) {
    if (ranks[i] !== ranks[i - 1] + 1) {
      // Check ace-high straight: A(1), 10, J, Q, K
      if (ranks[0] === 1 && ranks[1] === 10 && ranks[2] === 11 && ranks[3] === 12 && ranks[4] === 13) {
        return true
      }
      return false
    }
  }
  return true
}

function isRoyalFlush(cards: Card[]): boolean {
  if (!isFlush(cards)) return false
  const ranks = cards.map(c => c.rank).sort((a, b) => a - b)
  return ranks[0] === 1 && ranks[1] === 10 && ranks[2] === 11 && ranks[3] === 12 && ranks[4] === 13
}

export function evaluateHand(cards: Card[], bet: number): HandResult | null {
  if (cards.length !== 5) return null

  const counts = getRankCounts(cards)
  const values = Array.from(counts.values()).sort((a, b) => b - a)
  const flush = isFlush(cards)
  const straight = isStraight(cards)

  if (isRoyalFlush(cards)) {
    const mult = bet >= MAX_BET ? 800 : 250
    return { name: 'Royal Flush', multiplier: mult }
  }
  if (straight && flush) return { name: 'Straight Flush', multiplier: 50 }
  if (values[0] === 4) return { name: 'Four of a Kind', multiplier: 25 }
  if (values[0] === 3 && values[1] === 2) return { name: 'Full House', multiplier: 9 }
  if (flush) return { name: 'Flush', multiplier: 6 }
  if (straight) return { name: 'Straight', multiplier: 4 }
  if (values[0] === 3) return { name: 'Three of a Kind', multiplier: 3 }
  if (values[0] === 2 && values[1] === 2) return { name: 'Two Pair', multiplier: 2 }

  // Jacks or Better: pair of J, Q, K, or A
  if (values[0] === 2) {
    for (const [rank, count] of counts) {
      if (count === 2 && (rank >= 11 || rank === 1)) {
        return { name: 'Jacks or Better', multiplier: 1 }
      }
    }
  }

  return null
}

// ── Game creation ────────────────────────────────────────────────────

export function createVideoPokerGame(): VideoPokerState {
  return {
    hand: [],
    held: [false, false, false, false, false],
    deck: [],
    credits: STARTING_CREDITS,
    bet: 1,
    phase: 'betting',
    lastResult: null,
    message: 'Set your bet and deal',
  }
}

// ── Actions ──────────────────────────────────────────────────────────

export function setBet(state: VideoPokerState, bet: number): VideoPokerState {
  if (state.phase !== 'betting') return state
  const clamped = Math.max(MIN_BET, Math.min(MAX_BET, bet))
  return { ...state, bet: clamped }
}

export function deal(state: VideoPokerState): VideoPokerState {
  if (state.phase !== 'betting') return state
  if (state.bet > state.credits) return state

  const deck = shuffleDeck(createDeck())
  const hand = deck.splice(0, 5).map(c => ({ ...c, faceUp: true }))

  return {
    ...state,
    hand,
    held: [false, false, false, false, false],
    deck,
    credits: state.credits - state.bet,
    phase: 'dealt',
    lastResult: null,
    message: 'Hold cards you want to keep, then Draw',
  }
}

export function toggleHold(state: VideoPokerState, index: number): VideoPokerState {
  if (state.phase !== 'dealt') return state
  if (index < 0 || index > 4) return state

  const held = [...state.held]
  held[index] = !held[index]
  return { ...state, held }
}

export function draw(state: VideoPokerState): VideoPokerState {
  if (state.phase !== 'dealt') return state

  const deck = [...state.deck]
  const hand = state.hand.map((card, i) => {
    if (state.held[i]) return { ...card }
    return { ...deck.pop()!, faceUp: true }
  })

  const result = evaluateHand(hand, state.bet)
  const winnings = result ? result.multiplier * state.bet : 0

  return {
    ...state,
    hand,
    deck,
    credits: state.credits + winnings,
    phase: 'result',
    lastResult: result,
    message: result ? `${result.name}! +${winnings} credits` : 'No win',
  }
}

export function newHand(state: VideoPokerState): VideoPokerState {
  return {
    ...state,
    hand: [],
    held: [false, false, false, false, false],
    deck: [],
    phase: 'betting',
    lastResult: null,
    message: 'Set your bet and deal',
  }
}

export function isGameOver(state: VideoPokerState): boolean {
  return state.credits <= 0 && state.phase === 'result'
}
