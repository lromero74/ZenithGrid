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
  result: string  // '', 'win', 'lose', 'push', 'bust', 'blackjack'
}

export type Phase = 'betting' | 'playerTurn' | 'aiTurn' | 'dealerTurn' | 'payout'
export type Difficulty = 'easy' | 'hard'

export interface AiPlayer {
  cards: Card[]
  stood: boolean
  result: string  // '', 'win', 'lose', 'push', 'bust', 'blackjack'
  chips: number
  bet: number
}

export interface BlackjackState {
  shoe: Card[]
  playerHands: Hand[]
  dealerHand: Card[]
  aiPlayers: AiPlayer[]
  aiChips: number[]
  numOpponents: number
  activeHandIndex: number
  activeAiIndex: number
  chips: number
  dealerChips: number
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

export const SHOE_DECKS = 6
export const RESHUFFLE_THRESHOLD = 0.25
export const BET_SIZES = [10, 25, 50, 100, 500]
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

export function ensureShoe(shoe: Card[]): Card[] {
  if (shoe.length < SHOE_DECKS * 52 * RESHUFFLE_THRESHOLD) {
    return createShoe(SHOE_DECKS)
  }
  return [...shoe]
}

export function drawCard(shoe: Card[]): [Card, Card[]] {
  const remaining = [...shoe]
  const card = { ...remaining.pop()!, faceUp: true }
  return [card, remaining]
}

// ── Game creation ────────────────────────────────────────────────────

export function createBlackjackGame(difficulty: Difficulty = 'easy', numOpponents = 0): BlackjackState {
  return {
    shoe: createShoe(SHOE_DECKS),
    playerHands: [],
    dealerHand: [],
    aiPlayers: [],
    aiChips: new Array(numOpponents).fill(STARTING_CHIPS),
    numOpponents,
    activeHandIndex: 0,
    activeAiIndex: 0,
    chips: STARTING_CHIPS,
    dealerChips: STARTING_CHIPS * 5,
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

  // Deal 2 to player, AI opponents, and dealer (one face-down)
  let card: Card
  const playerCards: Card[] = []
  const dealerCards: Card[] = []
  const aiPlayers: AiPlayer[] = []

  // Initialize AI player hands
  for (let i = 0; i < state.numOpponents; i++) {
    const aiBet = Math.min(BET_SIZES[Math.floor(Math.random() * BET_SIZES.length)], state.aiChips[i] || STARTING_CHIPS)
    aiPlayers.push({ cards: [], stood: false, result: '', chips: state.aiChips[i] ?? STARTING_CHIPS, bet: aiBet })
  }

  // Round 1: one card each (player, AIs, dealer)
  ;[card, shoe] = drawCard(shoe)
  playerCards.push(card)
  for (let i = 0; i < aiPlayers.length; i++) {
    ;[card, shoe] = drawCard(shoe)
    aiPlayers[i] = { ...aiPlayers[i], cards: [...aiPlayers[i].cards, card] }
  }
  ;[card, shoe] = drawCard(shoe)
  dealerCards.push(card)

  // Round 2: second card each
  ;[card, shoe] = drawCard(shoe)
  playerCards.push(card)
  for (let i = 0; i < aiPlayers.length; i++) {
    ;[card, shoe] = drawCard(shoe)
    aiPlayers[i] = { ...aiPlayers[i], cards: [...aiPlayers[i].cards, card] }
  }
  ;[card, shoe] = drawCard(shoe)
  dealerCards.push({ ...card, faceUp: false }) // dealer hole card face-down

  const playerScore = scoreHand(playerCards)
  const dealerScore = scoreHand(dealerCards.map(c => ({ ...c, faceUp: true })))

  // Check for blackjacks
  if (playerScore.isBlackjack && dealerScore.isBlackjack) {
    return {
      ...state,
      shoe,
      playerHands: [{ cards: playerCards, bet, stood: true, doubled: false, result: 'push' }],
      dealerHand: dealerCards.map(c => ({ ...c, faceUp: true })),
      aiPlayers,
      activeHandIndex: 0,
      phase: 'payout',
      message: 'Push — both Blackjack!',
    }
  }

  if (playerScore.isBlackjack) {
    return {
      ...state,
      shoe,
      playerHands: [{ cards: playerCards, bet, stood: true, doubled: false, result: 'blackjack' }],
      dealerHand: dealerCards.map(c => ({ ...c, faceUp: true })),
      aiPlayers,
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
      playerHands: [{ cards: playerCards, bet, stood: true, doubled: false, result: '' }],
      dealerHand: dealerCards.map(c => ({ ...c, faceUp: true })),
      aiPlayers,
      activeHandIndex: 0,
      chips: state.chips - bet,
      phase: 'payout',
      message: `Dealer Blackjack! You lose ${bet} chips.`,
    }
  }

  return {
    ...state,
    shoe,
    playerHands: [{ cards: playerCards, bet, stood: false, doubled: false, result: '' }],
    dealerHand: dealerCards,
    aiPlayers,
    activeHandIndex: 0,
    activeAiIndex: 0,
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
    result: '',
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

  const hand1: Hand = { cards: [hand.cards[0], card1], bet: hand.bet, stood: false, doubled: false, result: '' }
  const hand2: Hand = { cards: [hand.cards[1], card2], bet: hand.bet, stood: false, doubled: false, result: '' }

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

  // All hands done — AI opponents play next, or dealer
  if (state.numOpponents > 0) {
    return { ...state, phase: 'aiTurn', activeAiIndex: 0, message: `P2 is playing...` }
  }
  return playDealer(state)
}

function playDealer(state: BlackjackState): BlackjackState {
  // Check if all player hands busted — skip straight to payout
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

  // Flip dealer hole card and enter dealerTurn phase (cards drawn one-by-one by UI)
  const dealerCards = state.dealerHand.map(c => ({ ...c, faceUp: true }))
  const score = scoreHand(dealerCards)
  return {
    ...state,
    dealerHand: dealerCards,
    phase: 'dealerTurn',
    message: `Dealer shows ${score.total}`,
  }
}

/** AI opponent takes one action (hit or stand). Called repeatedly by the component. */
export function aiStep(state: BlackjackState): BlackjackState {
  if (state.phase !== 'aiTurn') return state
  const idx = state.activeAiIndex
  if (idx >= state.aiPlayers.length) return playDealer(state)

  const ai = state.aiPlayers[idx]
  const score = scoreHand(ai.cards)

  // Already stood or busted — move to next AI
  if (ai.stood || score.isBust) {
    const nextIdx = idx + 1
    if (nextIdx >= state.aiPlayers.length) return playDealer(state)
    return { ...state, activeAiIndex: nextIdx, message: `P${nextIdx + 2} is playing...` }
  }

  // Basic strategy: hit on 16 or less, stand on 17+
  if (score.total >= 17) {
    const newAi = [...state.aiPlayers]
    newAi[idx] = { ...ai, stood: true }
    const nextIdx = idx + 1
    if (nextIdx >= newAi.length) return playDealer({ ...state, aiPlayers: newAi })
    return { ...state, aiPlayers: newAi, activeAiIndex: nextIdx, message: `P${nextIdx + 2} is playing...` }
  }

  // Hit
  let shoe = [...state.shoe]
  let card: Card
  ;[card, shoe] = drawCard(shoe)
  const newCards = [...ai.cards, card]
  const newScore = scoreHand(newCards)

  const newAi = [...state.aiPlayers]
  newAi[idx] = { ...ai, cards: newCards, stood: newScore.isBust || newScore.total >= 17 }

  if (newScore.isBust) {
    const nextIdx = idx + 1
    if (nextIdx >= newAi.length) return playDealer({ ...state, shoe, aiPlayers: newAi })
    return { ...state, shoe, aiPlayers: newAi, activeAiIndex: nextIdx, message: `P${nextIdx + 2} is playing...` }
  }

  return { ...state, shoe, aiPlayers: newAi, message: `P${idx + 2} hits — ${newScore.total}` }
}

/** Draw one card for the dealer. Returns updated state still in dealerTurn or advances to payout. */
export function dealerStep(state: BlackjackState): BlackjackState {
  if (state.phase !== 'dealerTurn') return state

  const score = scoreHand(state.dealerHand)
  const hitSoft17 = state.difficulty === 'hard'
  const mustHit = score.total < 17 || (hitSoft17 && score.total === 17 && score.isSoft)

  if (!mustHit) return resolvePayout(state)

  let shoe = [...state.shoe]
  let card: Card
  ;[card, shoe] = drawCard(shoe)
  const dealerCards = [...state.dealerHand, card]
  const newScore = scoreHand(dealerCards)

  return {
    ...state,
    shoe,
    dealerHand: dealerCards,
    message: `Dealer draws — ${newScore.total}${newScore.isBust ? ' BUST!' : ''}`,
  }
}

/** Check if dealer still needs to draw. */
export function dealerMustHit(state: BlackjackState): boolean {
  const score = scoreHand(state.dealerHand)
  const hitSoft17 = state.difficulty === 'hard'
  return score.total < 17 || (hitSoft17 && score.total === 17 && score.isSoft)
}

function resolvePayout(state: BlackjackState): BlackjackState {
  const score = scoreHand(state.dealerHand)

  let chipDelta = 0
  const results: string[] = []
  const updatedHands = [...state.playerHands]

  for (let i = 0; i < updatedHands.length; i++) {
    const hand = updatedHands[i]
    const pScore = scoreHand(hand.cards)
    const prefix = updatedHands.length > 1 ? `Hand ${i + 1}: ` : ''
    let result = ''

    if (pScore.isBust) {
      chipDelta -= hand.bet
      result = 'bust'
      results.push(`${prefix}Bust (-${hand.bet})`)
    } else if (score.isBust) {
      chipDelta += hand.bet
      result = 'win'
      results.push(`${prefix}Dealer bust! (+${hand.bet})`)
    } else if (pScore.total > score.total) {
      chipDelta += hand.bet
      result = 'win'
      results.push(`${prefix}Win! (+${hand.bet})`)
    } else if (pScore.total < score.total) {
      chipDelta -= hand.bet
      result = 'lose'
      results.push(`${prefix}Lose (-${hand.bet})`)
    } else {
      result = 'push'
      results.push(`${prefix}Push`)
    }
    updatedHands[i] = { ...hand, result }
  }

  // Split bonus: +100 for winning both hands after a split
  if (state.playerHands.length >= 2) {
    const allWon = state.playerHands.every(h => {
      const ps = scoreHand(h.cards)
      return !ps.isBust && (score.isBust || ps.total > score.total)
    })
    if (allWon) {
      chipDelta += 100
      results.push('Split bonus! (+100)')
    }
  }

  // Resolve AI results and update their chips
  const newAiChips = [...state.aiChips]
  const newAi = state.aiPlayers.map((ai, idx) => {
    const aiScore = scoreHand(ai.cards)
    let result = ''
    if (aiScore.isBust) result = 'bust'
    else if (score.isBust) result = 'win'
    else if (aiScore.total > score.total) result = 'win'
    else if (aiScore.total < score.total) result = 'lose'
    else result = 'push'
    if (result === 'win') newAiChips[idx] = (newAiChips[idx] ?? STARTING_CHIPS) + ai.bet
    else if (result === 'lose' || result === 'bust') newAiChips[idx] = (newAiChips[idx] ?? STARTING_CHIPS) - ai.bet
    return { ...ai, result, chips: newAiChips[idx] }
  })

  // Dealer chip delta is the inverse of all player/AI changes
  let dealerDelta = -chipDelta
  for (const ai of newAi) {
    if (ai.result === 'win') dealerDelta -= ai.bet
    else if (ai.result === 'lose' || ai.result === 'bust') dealerDelta += ai.bet
  }

  return {
    ...state,
    playerHands: updatedHands,
    aiPlayers: newAi,
    aiChips: newAiChips,
    phase: 'payout',
    chips: state.chips + chipDelta,
    dealerChips: (state.dealerChips ?? STARTING_CHIPS * 5) + dealerDelta,
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
  if (state.phase !== 'payout') return false
  return state.chips <= 0 || (state.dealerChips ?? 1) <= 0
}

export function didPlayerWin(state: BlackjackState): boolean {
  return state.phase === 'payout' && (state.dealerChips ?? 1) <= 0
}

export function newRound(state: BlackjackState): BlackjackState {
  // Keep previous round's cards visible until the player places a new bet
  return {
    ...state,
    phase: 'betting',
    message: 'Place your bet',
  }
}
