/**
 * Spades engine — pure logic, no React.
 *
 * 4 players: 2v2 partnership (Human+North vs East+West).
 * Spades are always trump. Bidding + bag penalties.
 */

import { createDeck, shuffleDeck, type Card, type Suit } from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

export type Phase = 'bidding' | 'playing' | 'trickComplete' | 'roundOver' | 'gameOver'

export interface Play {
  player: number
  card: Card
}

export interface SpadesState {
  hands: Card[][]
  currentTrick: Play[]
  completedTricks: Play[][]
  bids: (number | null)[]    // null = not yet bid
  tricksTaken: number[]      // per player this round
  teamScores: [number, number]  // [team0(0+2), team1(1+3)]
  teamBags: [number, number]
  phase: Phase
  currentPlayer: number
  leadPlayer: number
  spadesBroken: boolean
  roundNumber: number
  biddingPlayer: number
  message: string
}

// ── Constants ────────────────────────────────────────────────────────

export const WINNING_SCORE = 500
export const LOSING_SCORE = -200
export const BAG_PENALTY_THRESHOLD = 10
export const BAG_PENALTY = -100
export const NIL_BONUS = 100
export const PLAYER_NAMES = ['You', 'East', 'North', 'West']
export const TEAM_NAMES = ['You & North', 'East & West']

// ── Helpers ──────────────────────────────────────────────────────────

function cardValue(card: Card): number {
  return card.rank === 1 ? 14 : card.rank
}

export function sortHand(hand: Card[]): Card[] {
  const suitOrder: Suit[] = ['clubs', 'diamonds', 'hearts', 'spades']
  return [...hand].sort((a, b) => {
    const si = suitOrder.indexOf(a.suit) - suitOrder.indexOf(b.suit)
    if (si !== 0) return si
    return cardValue(a) - cardValue(b)
  })
}

function trickWinner(trick: Play[]): number {
  let best = trick[0]
  for (let i = 1; i < trick.length; i++) {
    const c = trick[i].card
    if (c.suit === 'spades' && best.card.suit !== 'spades') {
      best = trick[i]
    } else if (c.suit === best.card.suit && cardValue(c) > cardValue(best.card)) {
      best = trick[i]
    }
  }
  return best.player
}

// ── Game creation ────────────────────────────────────────────────────

export function createSpadesGame(): SpadesState {
  return dealRound({
    hands: [[], [], [], []],
    currentTrick: [],
    completedTricks: [],
    bids: [null, null, null, null],
    tricksTaken: [0, 0, 0, 0],
    teamScores: [0, 0],
    teamBags: [0, 0],
    phase: 'bidding',
    currentPlayer: 0,
    leadPlayer: 0,
    spadesBroken: false,
    roundNumber: 0,
    biddingPlayer: 0,
    message: '',
  })
}

function dealRound(state: SpadesState): SpadesState {
  const deck = shuffleDeck(createDeck()).map(c => ({ ...c, faceUp: true }))
  const hands: Card[][] = [[], [], [], []]
  for (let i = 0; i < 52; i++) {
    hands[i % 4].push(deck[i])
  }
  for (let p = 0; p < 4; p++) {
    hands[p] = sortHand(hands[p])
  }

  let next: SpadesState = {
    ...state,
    hands,
    currentTrick: [],
    completedTricks: [],
    bids: [null, null, null, null],
    tricksTaken: [0, 0, 0, 0],
    phase: 'bidding',
    spadesBroken: false,
    biddingPlayer: 0,
    currentPlayer: 0,
    message: 'Your bid (0 = Nil)',
  }

  return next
}

// ── Bidding ──────────────────────────────────────────────────────────

export function placeBid(state: SpadesState, bid: number): SpadesState {
  if (state.phase !== 'bidding') return state
  if (state.biddingPlayer !== 0) return state
  if (bid < 0 || bid > 13) return state

  const bids = [...state.bids] as (number | null)[]
  bids[0] = bid

  // AI bids
  for (let p = 1; p < 4; p++) {
    bids[p] = aiBid(state.hands[p])
  }

  // Start playing — player 0 leads first round (dealer's left)
  const leadPlayer = (state.roundNumber * 1) % 4 // rotate lead each round

  let next: SpadesState = {
    ...state,
    bids: bids as number[],
    phase: 'playing',
    currentPlayer: leadPlayer,
    leadPlayer,
    message: `Bids: You=${bid}, East=${bids[1]}, North=${bids[2]}, West=${bids[3]}`,
  }

  // If AI leads, play their turns
  if (leadPlayer !== 0) {
    next = runAiTurns(next)
  }

  return next
}

function aiBid(hand: Card[]): number {
  let bid = 0
  // Count high spades
  const spades = hand.filter(c => c.suit === 'spades')
  for (const s of spades) {
    if (cardValue(s) >= 12) bid++ // Q, K, A of spades
  }
  // Count aces of other suits
  for (const c of hand) {
    if (c.suit !== 'spades' && c.rank === 1) bid++
  }
  // Count kings with 3+ in suit
  const suits: Suit[] = ['hearts', 'diamonds', 'clubs']
  for (const suit of suits) {
    const suitCards = hand.filter(c => c.suit === suit)
    if (suitCards.length >= 3 && suitCards.some(c => c.rank === 13)) bid++
  }
  // Add for length in spades
  if (spades.length >= 4) bid++

  return Math.max(1, Math.min(bid, 7)) // minimum 1, max 7
}

// ── Playing ──────────────────────────────────────────────────────────

export function playCard(state: SpadesState, cardIndex: number): SpadesState {
  if (state.phase !== 'playing' || state.currentPlayer !== 0) return state

  const hand = state.hands[0]
  const card = hand[cardIndex]
  if (!card || !isValidPlay(card, hand, state)) return state

  const newHands = state.hands.map(h => [...h])
  newHands[0].splice(cardIndex, 1)

  const newTrick = [...state.currentTrick, { player: 0, card }]
  const spadesBroken = state.spadesBroken || card.suit === 'spades'

  let next: SpadesState = {
    ...state,
    hands: newHands,
    currentTrick: newTrick,
    spadesBroken,
  }

  if (newTrick.length === 4) {
    return completeTrick(next)
  }

  next.currentPlayer = (next.currentPlayer + 1) % 4
  return runAiTurns(next)
}

function isValidPlay(card: Card, hand: Card[], state: SpadesState): boolean {
  const isLeading = state.currentTrick.length === 0

  if (isLeading) {
    // Can't lead spades until broken
    if (card.suit === 'spades' && !state.spadesBroken) {
      return !hand.some(c => c.suit !== 'spades')
    }
    return true
  }

  // Must follow suit if able
  const leadSuit = state.currentTrick[0].card.suit
  const hasSuit = hand.some(c => c.suit === leadSuit)
  if (hasSuit) return card.suit === leadSuit
  return true
}

export function getValidPlays(state: SpadesState): number[] {
  if (state.phase !== 'playing' || state.currentPlayer !== 0) return []
  const hand = state.hands[0]
  return hand.map((c, i) => isValidPlay(c, hand, state) ? i : -1).filter(i => i >= 0)
}

// ── AI ───────────────────────────────────────────────────────────────

function runAiTurns(state: SpadesState): SpadesState {
  let current = state

  while (current.currentPlayer !== 0 && current.phase === 'playing') {
    const hand = current.hands[current.currentPlayer]
    const card = aiChooseCard(hand, current)

    const newHands = current.hands.map(h => [...h])
    newHands[current.currentPlayer] = newHands[current.currentPlayer].filter(
      c => !(c.rank === card.rank && c.suit === card.suit)
    )

    const newTrick = [...current.currentTrick, { player: current.currentPlayer, card }]
    const spadesBroken = current.spadesBroken || card.suit === 'spades'

    current = {
      ...current,
      hands: newHands,
      currentTrick: newTrick,
      spadesBroken,
    }

    if (newTrick.length === 4) {
      current = completeTrick(current)
      if (current.phase !== 'playing') break
      continue
    }

    current.currentPlayer = (current.currentPlayer + 1) % 4
  }

  if (current.phase === 'playing') {
    current.message = 'Your turn'
  }

  return current
}

function aiChooseCard(hand: Card[], state: SpadesState): Card {
  const isLeading = state.currentTrick.length === 0
  const valid = hand.filter(c => isValidPlay(c, hand, state))
  if (valid.length === 1) return valid[0]

  if (isLeading) {
    // Lead with non-spade, preferring aces/kings
    const nonSpades = valid.filter(c => c.suit !== 'spades')
    const pool = nonSpades.length > 0 ? nonSpades : valid
    return pool.sort((a, b) => cardValue(b) - cardValue(a))[0]
  }

  const leadSuit = state.currentTrick[0].card.suit
  const following = valid.filter(c => c.suit === leadSuit)

  if (following.length > 0) {
    // Try to play highest non-winning card or lowest winning
    const currentWinner = trickWinner([...state.currentTrick])
    const partnerIdx = (state.currentPlayer + 2) % 4
    const partnerWinning = currentWinner === partnerIdx

    if (partnerWinning) {
      // Partner is winning — play lowest
      return following.sort((a, b) => cardValue(a) - cardValue(b))[0]
    }
    // Try to win with lowest winning card
    return following.sort((a, b) => cardValue(b) - cardValue(a))[0]
  }

  // Void in lead suit — trump with lowest spade if possible
  const spades = valid.filter(c => c.suit === 'spades')
  if (spades.length > 0) {
    // Check if partner winning
    const currentWinner = trickWinner([...state.currentTrick])
    const partnerIdx = (state.currentPlayer + 2) % 4
    if (currentWinner === partnerIdx) {
      // Don't trump partner — play lowest non-spade
      const nonSpades = valid.filter(c => c.suit !== 'spades')
      if (nonSpades.length > 0) return nonSpades.sort((a, b) => cardValue(a) - cardValue(b))[0]
    }
    return spades.sort((a, b) => cardValue(a) - cardValue(b))[0]
  }

  // No spades, can't follow — play lowest
  return valid.sort((a, b) => cardValue(a) - cardValue(b))[0]
}

// ── Trick & Round resolution ─────────────────────────────────────────

function completeTrick(state: SpadesState): SpadesState {
  const winner = trickWinner(state.currentTrick)
  const tricksTaken = [...state.tricksTaken]
  tricksTaken[winner]++

  const completedTricks = [...state.completedTricks, state.currentTrick]

  if (completedTricks.length === 13) {
    return resolveRound({ ...state, currentTrick: [], completedTricks, tricksTaken })
  }

  let next: SpadesState = {
    ...state,
    currentTrick: [],
    completedTricks,
    tricksTaken,
    currentPlayer: winner,
    leadPlayer: winner,
    phase: 'playing',
    message: winner === 0 ? 'You won the trick — lead next' : `${PLAYER_NAMES[winner]} won the trick`,
  }

  if (winner !== 0) {
    next = runAiTurns(next)
  }

  return next
}

function resolveRound(state: SpadesState): SpadesState {
  const teamScores: [number, number] = [...state.teamScores]
  const teamBags: [number, number] = [...state.teamBags]
  const bids = state.bids as number[]

  for (let team = 0; team < 2; team++) {
    const p1 = team === 0 ? 0 : 1
    const p2 = team === 0 ? 2 : 3
    const teamBid = bids[p1] + bids[p2]
    const teamTricks = state.tricksTaken[p1] + state.tricksTaken[p2]

    // Handle nil bids
    let nilBonus = 0
    for (const p of [p1, p2]) {
      if (bids[p] === 0) {
        if (state.tricksTaken[p] === 0) {
          nilBonus += NIL_BONUS
        } else {
          nilBonus -= NIL_BONUS
        }
      }
    }

    const nonNilBid = (bids[p1] === 0 ? 0 : bids[p1]) + (bids[p2] === 0 ? 0 : bids[p2])
    const actualTeamBid = nonNilBid || teamBid

    if (teamTricks >= actualTeamBid) {
      const bags = teamTricks - actualTeamBid
      teamScores[team as 0 | 1] += actualTeamBid * 10 + bags
      teamBags[team as 0 | 1] += bags

      // Bag penalty
      if (teamBags[team as 0 | 1] >= BAG_PENALTY_THRESHOLD) {
        teamScores[team as 0 | 1] += BAG_PENALTY
        teamBags[team as 0 | 1] -= BAG_PENALTY_THRESHOLD
      }
    } else {
      teamScores[team as 0 | 1] -= actualTeamBid * 10
    }

    teamScores[team as 0 | 1] += nilBonus
  }

  // Check game over
  const gameOver = teamScores[0] >= WINNING_SCORE || teamScores[1] >= WINNING_SCORE ||
                   teamScores[0] <= LOSING_SCORE || teamScores[1] <= LOSING_SCORE

  if (gameOver) {
    const humanWin = teamScores[0] > teamScores[1]
    return {
      ...state,
      teamScores,
      teamBags,
      phase: 'gameOver',
      message: humanWin ? 'Your team wins!' : 'Opponents win!',
    }
  }

  return {
    ...state,
    teamScores,
    teamBags,
    phase: 'roundOver',
    roundNumber: state.roundNumber + 1,
    message: `Round over! Scores: ${TEAM_NAMES[0]} ${teamScores[0]} | ${TEAM_NAMES[1]} ${teamScores[1]}`,
  }
}

export function nextRound(state: SpadesState): SpadesState {
  return dealRound(state)
}
