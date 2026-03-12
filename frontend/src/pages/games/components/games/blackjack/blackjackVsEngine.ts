/**
 * Blackjack VS engine — shared-table multiplayer logic.
 *
 * Two human players sit at the same table with a shared dealer and shoe.
 * Host is authoritative: owns the shoe, draws cards, broadcasts state.
 * Guest sends action intents; host applies them and syncs back.
 */

import { createShoe, type Card } from '../../../utils/cardUtils'
import {
  scoreHand, ensureShoe, drawCard,
  type Hand, type Difficulty,
  SHOE_DECKS, BET_SIZES, STARTING_CHIPS,
} from './blackjackEngine'

// Re-export for convenience
export { scoreHand, BET_SIZES, STARTING_CHIPS, type Hand, type Difficulty }

// ── Types ────────────────────────────────────────────────────────────

export interface VsPlayer {
  id: number
  name: string
  hands: Hand[]
  activeHandIndex: number
  chips: number
  currentBet: number
  finished: boolean
}

export type VsPhase =
  | 'betting'
  | 'playerTurn'
  | 'dealerTurn'
  | 'payout'

export interface VsBlackjackState {
  shoe: Card[]
  players: VsPlayer[]      // [0] = host, [1] = guest
  dealerHand: Card[]
  dealerChips: number
  activePlayerIndex: number
  phase: VsPhase
  difficulty: Difficulty
  message: string
  betsPlaced: boolean[]
  roundNumber: number
}

// ── Game creation ────────────────────────────────────────────────────

export function createVsGame(
  difficulty: Difficulty,
  hostId: number, hostName: string,
  guestId: number, guestName: string,
): VsBlackjackState {
  return {
    shoe: createShoe(SHOE_DECKS),
    players: [
      { id: hostId, name: hostName, hands: [], activeHandIndex: 0, chips: STARTING_CHIPS, currentBet: BET_SIZES[0], finished: false },
      { id: guestId, name: guestName, hands: [], activeHandIndex: 0, chips: STARTING_CHIPS, currentBet: BET_SIZES[0], finished: false },
    ],
    dealerHand: [],
    dealerChips: STARTING_CHIPS * 5,
    activePlayerIndex: 0,
    phase: 'betting',
    difficulty,
    message: 'Place your bets',
    betsPlaced: [false, false],
    roundNumber: 1,
  }
}

// ── Betting ──────────────────────────────────────────────────────────

export function vsPlaceBet(state: VsBlackjackState, playerIndex: number, amount: number): VsBlackjackState {
  if (state.phase !== 'betting') return state
  if (playerIndex < 0 || playerIndex > 1) return state
  if (state.betsPlaced[playerIndex]) return state

  const player = state.players[playerIndex]
  if (amount > player.chips) return state

  const newPlayers = [...state.players]
  newPlayers[playerIndex] = { ...player, currentBet: amount }

  const newBets = [...state.betsPlaced]
  newBets[playerIndex] = true

  const bothReady = newBets[0] && newBets[1]

  return {
    ...state,
    players: newPlayers,
    betsPlaced: newBets,
    message: bothReady
      ? 'Dealing...'
      : `Waiting for ${newPlayers[newBets[0] ? 1 : 0].name} to bet...`,
  }
}

export function vsBothBetsPlaced(state: VsBlackjackState): boolean {
  return state.betsPlaced[0] && state.betsPlaced[1]
}

// ── Dealing ──────────────────────────────────────────────────────────

export function vsDeal(state: VsBlackjackState): VsBlackjackState {
  if (state.phase !== 'betting' || !vsBothBetsPlaced(state)) return state

  let shoe = ensureShoe(state.shoe)
  let card: Card
  const playerCards: Card[][] = [[], []]
  const dealerCards: Card[] = []

  // Round 1: one card to each player, then dealer
  for (let p = 0; p < 2; p++) {
    ;[card, shoe] = drawCard(shoe)
    playerCards[p].push(card)
  }
  ;[card, shoe] = drawCard(shoe)
  dealerCards.push(card)

  // Round 2: second card to each player, then dealer (hole card face-down)
  for (let p = 0; p < 2; p++) {
    ;[card, shoe] = drawCard(shoe)
    playerCards[p].push(card)
  }
  ;[card, shoe] = drawCard(shoe)
  dealerCards.push({ ...card, faceUp: false })

  const newPlayers = state.players.map((p, i) => ({
    ...p,
    hands: [{ cards: playerCards[i], bet: p.currentBet, stood: false, doubled: false, result: '' }],
    activeHandIndex: 0,
    finished: false,
  }))

  // Check for blackjacks
  const scores = [scoreHand(playerCards[0]), scoreHand(playerCards[1])]
  const dealerScore = scoreHand(dealerCards.map(c => ({ ...c, faceUp: true })))

  // If dealer has blackjack, skip to payout
  if (dealerScore.isBlackjack) {
    const revealedDealer = dealerCards.map(c => ({ ...c, faceUp: true }))
    const resolvedPlayers = newPlayers.map((p, i) => {
      const result = scores[i].isBlackjack ? 'push' : 'lose'
      return {
        ...p,
        hands: [{ ...p.hands[0], stood: true, result }],
        finished: true,
      }
    })
    return vsResolvePayout({
      ...state, shoe, players: resolvedPlayers, dealerHand: revealedDealer,
      phase: 'payout', activePlayerIndex: 0,
    })
  }

  // Mark blackjack hands as auto-stood
  for (let i = 0; i < 2; i++) {
    if (scores[i].isBlackjack) {
      newPlayers[i] = {
        ...newPlayers[i],
        hands: [{ ...newPlayers[i].hands[0], stood: true, result: 'blackjack' }],
        finished: true,
      }
    }
  }

  // Determine first active player (skip blackjack holders)
  let activeIdx = 0
  if (newPlayers[0].finished && newPlayers[1].finished) {
    // Both have blackjack — go to dealer
    return goToDealer({ ...state, shoe, players: newPlayers, dealerHand: dealerCards, activePlayerIndex: 0 })
  }
  if (newPlayers[0].finished) activeIdx = 1

  const activePlayer = newPlayers[activeIdx]
  const activeScore = scoreHand(activePlayer.hands[0].cards)

  return {
    ...state,
    shoe,
    players: newPlayers,
    dealerHand: dealerCards,
    activePlayerIndex: activeIdx,
    phase: 'playerTurn',
    message: `${activePlayer.name}'s turn — ${activeScore.total}${activeScore.isSoft ? ' (soft)' : ''}`,
  }
}

// ── Player actions ───────────────────────────────────────────────────

export function vsHit(state: VsBlackjackState): VsBlackjackState {
  if (state.phase !== 'playerTurn') return state

  const pIdx = state.activePlayerIndex
  const player = state.players[pIdx]
  const hand = player.hands[player.activeHandIndex]
  if (!hand || hand.stood) return state

  let shoe = [...state.shoe]
  let card: Card
  ;[card, shoe] = drawCard(shoe)

  const newCards = [...hand.cards, card]
  const score = scoreHand(newCards)

  const newHands = [...player.hands]
  newHands[player.activeHandIndex] = { ...hand, cards: newCards }

  if (score.isBust) {
    newHands[player.activeHandIndex] = { ...newHands[player.activeHandIndex], stood: true }
    const newPlayers = [...state.players]
    newPlayers[pIdx] = { ...player, hands: newHands }
    return vsAdvanceHand({ ...state, shoe, players: newPlayers }, 'Bust!')
  }

  if (score.total === 21) {
    newHands[player.activeHandIndex] = { ...newHands[player.activeHandIndex], stood: true }
    const newPlayers = [...state.players]
    newPlayers[pIdx] = { ...player, hands: newHands }
    return vsAdvanceHand({ ...state, shoe, players: newPlayers }, '21!')
  }

  const newPlayers = [...state.players]
  newPlayers[pIdx] = { ...player, hands: newHands }
  return {
    ...state,
    shoe,
    players: newPlayers,
    message: `${player.name}: ${score.total}${score.isSoft ? ' (soft)' : ''}`,
  }
}

export function vsStand(state: VsBlackjackState): VsBlackjackState {
  if (state.phase !== 'playerTurn') return state

  const pIdx = state.activePlayerIndex
  const player = state.players[pIdx]
  const newHands = [...player.hands]
  newHands[player.activeHandIndex] = { ...newHands[player.activeHandIndex], stood: true }

  const newPlayers = [...state.players]
  newPlayers[pIdx] = { ...player, hands: newHands }
  return vsAdvanceHand({ ...state, players: newPlayers }, 'Stand')
}

export function vsDoubleDown(state: VsBlackjackState): VsBlackjackState {
  if (state.phase !== 'playerTurn') return state

  const pIdx = state.activePlayerIndex
  const player = state.players[pIdx]
  const hand = player.hands[player.activeHandIndex]
  if (!hand || hand.cards.length !== 2) return state
  if (hand.bet > player.chips) return state

  let shoe = [...state.shoe]
  let card: Card
  ;[card, shoe] = drawCard(shoe)

  const newCards = [...hand.cards, card]
  const score = scoreHand(newCards)

  const newHands = [...player.hands]
  newHands[player.activeHandIndex] = {
    cards: newCards,
    bet: hand.bet * 2,
    stood: true,
    doubled: true,
    result: '',
  }

  const newPlayers = [...state.players]
  newPlayers[pIdx] = { ...player, hands: newHands }

  const msg = score.isBust ? 'Double Down — Bust!' : `Double Down — ${score.total}`
  return vsAdvanceHand({ ...state, shoe, players: newPlayers }, msg)
}

export function vsSplit(state: VsBlackjackState): VsBlackjackState {
  if (state.phase !== 'playerTurn') return state

  const pIdx = state.activePlayerIndex
  const player = state.players[pIdx]
  const hand = player.hands[player.activeHandIndex]
  if (!hand || hand.cards.length !== 2) return state
  if (hand.cards[0].rank !== hand.cards[1].rank) return state
  if (hand.bet > player.chips) return state
  if (player.hands.length >= 4) return state

  let shoe = [...state.shoe]
  let card1: Card, card2: Card
  ;[card1, shoe] = drawCard(shoe)
  ;[card2, shoe] = drawCard(shoe)

  const hand1: Hand = { cards: [hand.cards[0], card1], bet: hand.bet, stood: false, doubled: false, result: '' }
  const hand2: Hand = { cards: [hand.cards[1], card2], bet: hand.bet, stood: false, doubled: false, result: '' }

  const newHands = [...player.hands]
  newHands.splice(player.activeHandIndex, 1, hand1, hand2)

  const newPlayers = [...state.players]
  newPlayers[pIdx] = { ...player, hands: newHands }

  const score = scoreHand(hand1.cards)
  return {
    ...state,
    shoe,
    players: newPlayers,
    message: `${player.name} splits! Hand ${player.activeHandIndex + 1}: ${score.total}`,
  }
}

// ── Hand/player advancement ──────────────────────────────────────────

function vsAdvanceHand(state: VsBlackjackState, _msg: string): VsBlackjackState {
  const pIdx = state.activePlayerIndex
  const player = state.players[pIdx]
  const nextHandIdx = player.activeHandIndex + 1

  // More hands for this player?
  if (nextHandIdx < player.hands.length && !player.hands[nextHandIdx].stood) {
    const newPlayers = [...state.players]
    newPlayers[pIdx] = { ...player, activeHandIndex: nextHandIdx }
    const score = scoreHand(player.hands[nextHandIdx].cards)
    return {
      ...state,
      players: newPlayers,
      message: `${player.name} — Hand ${nextHandIdx + 1}: ${score.total}${score.isSoft ? ' (soft)' : ''}`,
    }
  }

  // Mark this player as finished
  const newPlayers = [...state.players]
  newPlayers[pIdx] = { ...player, finished: true }

  // Next player?
  const nextPlayerIdx = pIdx + 1
  if (nextPlayerIdx < 2 && !newPlayers[nextPlayerIdx].finished) {
    const nextPlayer = newPlayers[nextPlayerIdx]
    const score = scoreHand(nextPlayer.hands[0].cards)
    return {
      ...state,
      players: newPlayers,
      activePlayerIndex: nextPlayerIdx,
      message: `${nextPlayer.name}'s turn — ${score.total}${score.isSoft ? ' (soft)' : ''}`,
    }
  }

  // All players done — go to dealer
  return goToDealer({ ...state, players: newPlayers })
}

function goToDealer(state: VsBlackjackState): VsBlackjackState {
  // Check if all hands busted — skip dealer draw
  const allBusted = state.players.every(p =>
    p.hands.every(h => scoreHand(h.cards).isBust)
  )

  if (allBusted) {
    return vsResolvePayout({
      ...state,
      dealerHand: state.dealerHand.map(c => ({ ...c, faceUp: true })),
      phase: 'payout',
    })
  }

  // Flip dealer hole card
  const dealerCards = state.dealerHand.map(c => ({ ...c, faceUp: true }))
  const score = scoreHand(dealerCards)
  return {
    ...state,
    dealerHand: dealerCards,
    phase: 'dealerTurn',
    message: `Dealer shows ${score.total}`,
  }
}

// ── Dealer ───────────────────────────────────────────────────────────

export function vsDealerStep(state: VsBlackjackState): VsBlackjackState {
  if (state.phase !== 'dealerTurn') return state

  const score = scoreHand(state.dealerHand)
  const hitSoft17 = state.difficulty === 'hard'
  const mustHit = score.total < 17 || (hitSoft17 && score.total === 17 && score.isSoft)

  if (!mustHit) return vsResolvePayout(state)

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

export function vsDealerMustHit(state: VsBlackjackState): boolean {
  const score = scoreHand(state.dealerHand)
  const hitSoft17 = state.difficulty === 'hard'
  return score.total < 17 || (hitSoft17 && score.total === 17 && score.isSoft)
}

// ── Payout ───────────────────────────────────────────────────────────

export function vsResolvePayout(state: VsBlackjackState): VsBlackjackState {
  const dealerScore = scoreHand(state.dealerHand)
  let totalDealerDelta = 0

  const newPlayers = state.players.map(player => {
    let chipDelta = 0
    const results: string[] = []
    const updatedHands = player.hands.map((hand, i) => {
      const pScore = scoreHand(hand.cards)
      const prefix = player.hands.length > 1 ? `H${i + 1}: ` : ''
      let result = hand.result  // preserve 'blackjack' from deal

      if (result === 'blackjack') {
        // Natural blackjack pays 3:2
        chipDelta += Math.floor(hand.bet * 1.5)
        results.push(`${prefix}Blackjack! (+${Math.floor(hand.bet * 1.5)})`)
      } else if (pScore.isBust) {
        chipDelta -= hand.bet
        result = 'bust'
        results.push(`${prefix}Bust (-${hand.bet})`)
      } else if (dealerScore.isBust) {
        chipDelta += hand.bet
        result = 'win'
        results.push(`${prefix}Win! (+${hand.bet})`)
      } else if (pScore.total > dealerScore.total) {
        chipDelta += hand.bet
        result = 'win'
        results.push(`${prefix}Win! (+${hand.bet})`)
      } else if (pScore.total < dealerScore.total) {
        chipDelta -= hand.bet
        result = 'lose'
        results.push(`${prefix}Lose (-${hand.bet})`)
      } else {
        result = 'push'
        results.push(`${prefix}Push`)
      }
      return { ...hand, stood: true, result }
    })

    // Split bonus
    if (player.hands.length >= 2) {
      const allWon = updatedHands.every(h => h.result === 'win' || h.result === 'blackjack')
      if (allWon) {
        chipDelta += 100
        results.push('Split bonus! (+100)')
      }
    }

    totalDealerDelta -= chipDelta

    return {
      ...player,
      hands: updatedHands,
      chips: player.chips + chipDelta,
      finished: true,
    }
  })

  // Build message
  const msgs = newPlayers.map(p => {
    const handResults = p.hands.map(h => {
      if (h.result === 'blackjack') return 'BJ!'
      if (h.result === 'win') return `+${h.bet}`
      if (h.result === 'lose') return `-${h.bet}`
      if (h.result === 'bust') return 'Bust'
      return 'Push'
    }).join(', ')
    return `${p.name}: ${handResults}`
  })

  return {
    ...state,
    players: newPlayers,
    dealerChips: state.dealerChips + totalDealerDelta,
    phase: 'payout',
    message: msgs.join(' | '),
  }
}

// ── Round management ─────────────────────────────────────────────────

export function vsNewRound(state: VsBlackjackState): VsBlackjackState {
  return {
    ...state,
    players: state.players.map(p => ({
      ...p,
      hands: [],
      activeHandIndex: 0,
      finished: false,
    })),
    dealerHand: [],
    activePlayerIndex: 0,
    phase: 'betting',
    betsPlaced: [false, false],
    roundNumber: state.roundNumber + 1,
    message: 'Place your bets',
  }
}

// ── Queries ──────────────────────────────────────────────────────────

export function vsIsGameOver(state: VsBlackjackState): boolean {
  if (state.phase !== 'payout') return false
  return state.players.some(p => p.chips <= 0) || state.dealerChips <= 0
}

export function vsGetWinner(state: VsBlackjackState): number | null {
  if (!vsIsGameOver(state)) return null
  // Player with more chips wins; if both bust out somehow, higher chips wins
  if (state.players[0].chips <= 0 && state.players[1].chips <= 0) return null
  if (state.players[0].chips <= 0) return 1
  if (state.players[1].chips <= 0) return 0
  if (state.dealerChips <= 0) {
    // Both beat the dealer — higher chips wins
    return state.players[0].chips >= state.players[1].chips ? 0 : 1
  }
  return null
}

export function vsCanSplit(state: VsBlackjackState): boolean {
  if (state.phase !== 'playerTurn') return false
  const player = state.players[state.activePlayerIndex]
  const hand = player.hands[player.activeHandIndex]
  if (!hand || hand.cards.length !== 2) return false
  if (hand.cards[0].rank !== hand.cards[1].rank) return false
  if (hand.bet > player.chips) return false
  if (player.hands.length >= 4) return false
  return true
}

export function vsCanDoubleDown(state: VsBlackjackState): boolean {
  if (state.phase !== 'playerTurn') return false
  const player = state.players[state.activePlayerIndex]
  const hand = player.hands[player.activeHandIndex]
  if (!hand || hand.cards.length !== 2) return false
  if (hand.bet > player.chips) return false
  return true
}
