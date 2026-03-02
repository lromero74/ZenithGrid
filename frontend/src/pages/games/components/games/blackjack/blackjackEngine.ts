/**
 * Blackjack engine — pure logic, no React.
 *
 * 6-deck shoe, standard Blackjack rules with split (one level).
 */

import { createShoe, type Card } from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

export interface Hand {
  cards: Card[]
  bet: number
  stood: boolean
  doubled: boolean
}

export type Phase = 'betting' | 'playerTurn' | 'dealerTurn' | 'payout'
export type Difficulty = 'easy' | 'hard'

export interface BlackjackState {
  shoe: Card[]
  playerHands: Hand[]
  dealerHand: Card[]
  activeHandIndex: number
  chips: number
  currentBet: number
  phase: Phase
  difficulty: Difficulty
  message: string
}

export interface HandScore {
  total: number
  isSoft: boolean
  isBust: boolean
  isBlackjack: boolean
}

// ── Constants ────────────────────────────────────────────────────────

const SHOE_DECKS = 6
const RESHUFFLE_THRESHOLD = 0.25
export const BET_SIZES = [10, 25, 50, 100]
export const STARTING_CHIPS = 1000

// ── Scoring ──────────────────────────────────────────────────────────

export function scoreHand(cards: Card[]): HandScore {
  let total = 0
  let aces = 0

  for (const card of cards) {
    if (card.rank === 1) {
      aces++
      total += 11
    } else if (card.rank >= 11) {
      total += 10
    } else {
      total += card.rank
    }
  }

  while (total > 21 && aces > 0) {
    total -= 10
    aces--
  }

  return {
    total,
    isSoft: aces > 0,
    isBust: total > 21,
    isBlackjack: cards.length === 2 && total === 21,
  }
}

// ── Shoe management ──────────────────────────────────────────────────

function ensureShoe(shoe: Card[]): Card[] {
  if (shoe.length < SHOE_DECKS * 52 * RESHUFFLE_THRESHOLD) {
    return createShoe(SHOE_DECKS)
  }
  return [...shoe]
}

function drawCard(shoe: Card[]): [Card, Card[]] {
  const remaining = [...shoe]
  const card = { ...remaining.pop()!, faceUp: true }
  return [card, remaining]
}

// ── Game creation ────────────────────────────────────────────────────

export function createBlackjackGame(difficulty: Difficulty = 'easy'): BlackjackState {
  return {
    shoe: createShoe(SHOE_DECKS),
    playerHands: [],
    dealerHand: [],
    activeHandIndex: 0,
    chips: STARTING_CHIPS,
    currentBet: BET_SIZES[0],
    phase: 'betting',
    difficulty,
    message: 'Place your bet',
  }
}

// ── Actions ──────────────────────────────────────────────────────────

export function placeBet(state: BlackjackState, bet: number): BlackjackState {
  if (state.phase !== 'betting') return state
  if (bet > state.chips) return state

  let shoe = ensureShoe(state.shoe)

  // Deal 2 to player, 2 to dealer (one face-down)
  let card: Card
  const playerCards: Card[] = []
  const dealerCards: Card[] = []

  ;[card, shoe] = drawCard(shoe)
  playerCards.push(card)
  ;[card, shoe] = drawCard(shoe)
  dealerCards.push(card)
  ;[card, shoe] = drawCard(shoe)
  playerCards.push(card)
  ;[card, shoe] = drawCard(shoe)
  dealerCards.push({ ...card, faceUp: false }) // dealer hole card face-down

  const playerScore = scoreHand(playerCards)
  const dealerScore = scoreHand(dealerCards.map(c => ({ ...c, faceUp: true })))

  // Check for blackjacks
  if (playerScore.isBlackjack && dealerScore.isBlackjack) {
    return {
      ...state,
      shoe,
      playerHands: [{ cards: playerCards, bet, stood: true, doubled: false }],
      dealerHand: dealerCards.map(c => ({ ...c, faceUp: true })),
      activeHandIndex: 0,
      phase: 'payout',
      message: 'Push — both Blackjack!',
    }
  }

  if (playerScore.isBlackjack) {
    return {
      ...state,
      shoe,
      playerHands: [{ cards: playerCards, bet, stood: true, doubled: false }],
      dealerHand: dealerCards.map(c => ({ ...c, faceUp: true })),
      activeHandIndex: 0,
      chips: state.chips + Math.floor(bet * 1.5),
      phase: 'payout',
      message: 'Blackjack! You win 3:2!',
    }
  }

  if (dealerScore.isBlackjack) {
    return {
      ...state,
      shoe,
      playerHands: [{ cards: playerCards, bet, stood: true, doubled: false }],
      dealerHand: dealerCards.map(c => ({ ...c, faceUp: true })),
      activeHandIndex: 0,
      chips: state.chips - bet,
      phase: 'payout',
      message: `Dealer Blackjack! You lose ${bet} chips.`,
    }
  }

  return {
    ...state,
    shoe,
    playerHands: [{ cards: playerCards, bet, stood: false, doubled: false }],
    dealerHand: dealerCards,
    activeHandIndex: 0,
    currentBet: bet,
    phase: 'playerTurn',
    message: `Your hand: ${playerScore.total}${playerScore.isSoft ? ' (soft)' : ''}`,
  }
}

export function hit(state: BlackjackState): BlackjackState {
  if (state.phase !== 'playerTurn') return state

  const hand = state.playerHands[state.activeHandIndex]
  if (!hand || hand.stood) return state

  let shoe = [...state.shoe]
  let card: Card
  ;[card, shoe] = drawCard(shoe)

  const newCards = [...hand.cards, card]
  const score = scoreHand(newCards)

  const newHands = [...state.playerHands]
  newHands[state.activeHandIndex] = { ...hand, cards: newCards }

  if (score.isBust) {
    newHands[state.activeHandIndex] = { ...newHands[state.activeHandIndex], stood: true }
    // Move to next hand or dealer turn
    return advanceHand({ ...state, shoe, playerHands: newHands }, 'Bust!')
  }

  if (score.total === 21) {
    newHands[state.activeHandIndex] = { ...newHands[state.activeHandIndex], stood: true }
    return advanceHand({ ...state, shoe, playerHands: newHands }, '21!')
  }

  return {
    ...state,
    shoe,
    playerHands: newHands,
    message: `Your hand: ${score.total}${score.isSoft ? ' (soft)' : ''}`,
  }
}

export function stand(state: BlackjackState): BlackjackState {
  if (state.phase !== 'playerTurn') return state

  const newHands = [...state.playerHands]
  newHands[state.activeHandIndex] = { ...newHands[state.activeHandIndex], stood: true }

  return advanceHand({ ...state, playerHands: newHands }, 'Stand')
}

export function doubleDown(state: BlackjackState): BlackjackState {
  if (state.phase !== 'playerTurn') return state

  const hand = state.playerHands[state.activeHandIndex]
  if (!hand || hand.cards.length !== 2) return state
  if (hand.bet > state.chips) return state // can't afford double

  let shoe = [...state.shoe]
  let card: Card
  ;[card, shoe] = drawCard(shoe)

  const newCards = [...hand.cards, card]
  const score = scoreHand(newCards)

  const newHands = [...state.playerHands]
  newHands[state.activeHandIndex] = {
    cards: newCards,
    bet: hand.bet * 2,
    stood: true,
    doubled: true,
  }

  const msg = score.isBust ? 'Double Down — Bust!' : `Double Down — ${score.total}`
  return advanceHand({ ...state, shoe, playerHands: newHands }, msg)
}

export function split(state: BlackjackState): BlackjackState {
  if (state.phase !== 'playerTurn') return state

  const hand = state.playerHands[state.activeHandIndex]
  if (!hand || hand.cards.length !== 2) return state
  if (hand.cards[0].rank !== hand.cards[1].rank) return state
  if (hand.bet > state.chips) return state // can't afford split
  if (state.playerHands.length >= 4) return state // max 4 hands

  let shoe = [...state.shoe]
  let card1: Card, card2: Card
  ;[card1, shoe] = drawCard(shoe)
  ;[card2, shoe] = drawCard(shoe)

  const hand1: Hand = { cards: [hand.cards[0], card1], bet: hand.bet, stood: false, doubled: false }
  const hand2: Hand = { cards: [hand.cards[1], card2], bet: hand.bet, stood: false, doubled: false }

  const newHands = [...state.playerHands]
  newHands.splice(state.activeHandIndex, 1, hand1, hand2)

  const score = scoreHand(hand1.cards)
  return {
    ...state,
    shoe,
    playerHands: newHands,
    message: `Split! Hand ${state.activeHandIndex + 1}: ${score.total}`,
  }
}

function advanceHand(state: BlackjackState, _msg: string): BlackjackState {
  const nextIdx = state.activeHandIndex + 1
  if (nextIdx < state.playerHands.length && !state.playerHands[nextIdx].stood) {
    const score = scoreHand(state.playerHands[nextIdx].cards)
    return {
      ...state,
      activeHandIndex: nextIdx,
      message: `Hand ${nextIdx + 1}: ${score.total}${score.isSoft ? ' (soft)' : ''}`,
    }
  }

  // All hands done — dealer plays
  return playDealer(state)
}

function playDealer(state: BlackjackState): BlackjackState {
  // Check if all player hands busted
  const allBusted = state.playerHands.every(h => scoreHand(h.cards).isBust)
  if (allBusted) {
    const totalLoss = state.playerHands.reduce((sum, h) => sum + h.bet, 0)
    return {
      ...state,
      dealerHand: state.dealerHand.map(c => ({ ...c, faceUp: true })),
      phase: 'payout',
      chips: state.chips - totalLoss,
      message: `All hands bust! You lose ${totalLoss} chips.`,
    }
  }

  // Flip dealer hole card
  let dealerCards = state.dealerHand.map(c => ({ ...c, faceUp: true }))
  let shoe = [...state.shoe]

  // Dealer hits until 17+ (hard mode: hits soft 17)
  let score = scoreHand(dealerCards)
  const hitSoft17 = state.difficulty === 'hard'

  while (score.total < 17 || (hitSoft17 && score.total === 17 && score.isSoft)) {
    let card: Card
    ;[card, shoe] = drawCard(shoe)
    dealerCards = [...dealerCards, card]
    score = scoreHand(dealerCards)
  }

  // Calculate payouts
  let chipDelta = 0
  const results: string[] = []

  for (let i = 0; i < state.playerHands.length; i++) {
    const hand = state.playerHands[i]
    const pScore = scoreHand(hand.cards)
    const prefix = state.playerHands.length > 1 ? `Hand ${i + 1}: ` : ''

    if (pScore.isBust) {
      chipDelta -= hand.bet
      results.push(`${prefix}Bust (-${hand.bet})`)
    } else if (score.isBust) {
      chipDelta += hand.bet
      results.push(`${prefix}Dealer bust! (+${hand.bet})`)
    } else if (pScore.total > score.total) {
      chipDelta += hand.bet
      results.push(`${prefix}Win! (+${hand.bet})`)
    } else if (pScore.total < score.total) {
      chipDelta -= hand.bet
      results.push(`${prefix}Lose (-${hand.bet})`)
    } else {
      results.push(`${prefix}Push`)
    }
  }

  return {
    ...state,
    shoe,
    dealerHand: dealerCards,
    phase: 'payout',
    chips: state.chips + chipDelta,
    message: results.join(' | '),
  }
}

// ── Queries ──────────────────────────────────────────────────────────

export function canSplit(state: BlackjackState): boolean {
  if (state.phase !== 'playerTurn') return false
  const hand = state.playerHands[state.activeHandIndex]
  if (!hand || hand.cards.length !== 2) return false
  if (hand.cards[0].rank !== hand.cards[1].rank) return false
  if (hand.bet > state.chips) return false
  if (state.playerHands.length >= 4) return false
  return true
}

export function canDoubleDown(state: BlackjackState): boolean {
  if (state.phase !== 'playerTurn') return false
  const hand = state.playerHands[state.activeHandIndex]
  if (!hand || hand.cards.length !== 2) return false
  if (hand.bet > state.chips) return false
  return true
}

export function isGameOver(state: BlackjackState): boolean {
  return state.chips <= 0 && state.phase === 'payout'
}

export function newRound(state: BlackjackState): BlackjackState {
  return {
    ...state,
    playerHands: [],
    dealerHand: [],
    activeHandIndex: 0,
    phase: 'betting',
    message: 'Place your bet',
  }
}
