/**
 * Hearts engine — pure logic, no React.
 *
 * 4 players: 1 human (South/index 0) + 3 AI.
 * Standard Hearts rules with passing and shoot-the-moon.
 */

import { createDeck, shuffleDeck, type Card, type Suit } from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

export type Phase = 'passing' | 'playing' | 'trickComplete' | 'roundOver' | 'gameOver'

export interface Play {
  player: number
  card: Card
}

export type PassDirection = 'left' | 'right' | 'across' | 'none'

export interface HeartsState {
  hands: Card[][]         // 4 hands, index 0 = human
  currentTrick: Play[]
  completedTricks: Play[][]
  scores: number[]        // cumulative scores
  roundScores: number[]   // current round scores
  phase: Phase
  currentPlayer: number
  leadPlayer: number
  passDirection: PassDirection
  selectedCards: number[] // indices in human hand selected for passing
  heartsBroken: boolean
  roundNumber: number
  message: string
}

// ── Constants ────────────────────────────────────────────────────────

const PASS_DIRECTIONS: PassDirection[] = ['left', 'right', 'across', 'none']
export const GAME_OVER_SCORE = 100
export const PLAYER_NAMES = ['You', 'West', 'North', 'East']

// ── Helpers ──────────────────────────────────────────────────────────

function cardValue(card: Card): number {
  return card.rank === 1 ? 14 : card.rank // Ace is high
}

export function sortHand(hand: Card[]): Card[] {
  const suitOrder: Suit[] = ['clubs', 'diamonds', 'spades', 'hearts']
  return [...hand].sort((a, b) => {
    const si = suitOrder.indexOf(a.suit) - suitOrder.indexOf(b.suit)
    if (si !== 0) return si
    return cardValue(a) - cardValue(b)
  })
}

function isQueenOfSpades(card: Card): boolean {
  return card.suit === 'spades' && card.rank === 12
}

function is2OfClubs(card: Card): boolean {
  return card.suit === 'clubs' && card.rank === 2
}

function pointsForCard(card: Card): number {
  if (card.suit === 'hearts') return 1
  if (isQueenOfSpades(card)) return 13
  return 0
}

function trickPoints(trick: Play[]): number {
  return trick.reduce((sum, p) => sum + pointsForCard(p.card), 0)
}

function trickWinner(trick: Play[]): number {
  const leadSuit = trick[0].card.suit
  let best = trick[0]
  for (let i = 1; i < trick.length; i++) {
    if (trick[i].card.suit === leadSuit && cardValue(trick[i].card) > cardValue(best.card)) {
      best = trick[i]
    }
  }
  return best.player
}

// ── Game creation ────────────────────────────────────────────────────

export function createHeartsGame(): HeartsState {
  return dealRound({
    hands: [[], [], [], []],
    currentTrick: [],
    completedTricks: [],
    scores: [0, 0, 0, 0],
    roundScores: [0, 0, 0, 0],
    phase: 'passing',
    currentPlayer: 0,
    leadPlayer: 0,
    passDirection: 'left',
    selectedCards: [],
    heartsBroken: false,
    roundNumber: 0,
    message: '',
  })
}

function dealRound(state: HeartsState): HeartsState {
  const deck = shuffleDeck(createDeck()).map(c => ({ ...c, faceUp: true }))
  const hands: Card[][] = [[], [], [], []]
  for (let i = 0; i < 52; i++) {
    hands[i % 4].push(deck[i])
  }
  for (let p = 0; p < 4; p++) {
    hands[p] = sortHand(hands[p])
  }

  const passDir = PASS_DIRECTIONS[state.roundNumber % 4]

  if (passDir === 'none') {
    // Find who has 2 of clubs
    const starter = hands.findIndex(h => h.some(is2OfClubs))
    return {
      ...state,
      hands,
      currentTrick: [],
      completedTricks: [],
      roundScores: [0, 0, 0, 0],
      phase: starter === 0 ? 'playing' : 'playing',
      currentPlayer: starter,
      leadPlayer: starter,
      passDirection: passDir,
      selectedCards: [],
      heartsBroken: false,
      message: starter === 0 ? 'You lead — play the 2 of clubs' : `${PLAYER_NAMES[starter]} leads`,
    }
  }

  return {
    ...state,
    hands,
    currentTrick: [],
    completedTricks: [],
    roundScores: [0, 0, 0, 0],
    phase: 'passing',
    passDirection: passDir,
    selectedCards: [],
    heartsBroken: false,
    message: `Pass 3 cards ${passDir}`,
  }
}

// ── Passing ──────────────────────────────────────────────────────────

export function togglePassCard(state: HeartsState, cardIndex: number): HeartsState {
  if (state.phase !== 'passing') return state
  const selected = [...state.selectedCards]
  const idx = selected.indexOf(cardIndex)
  if (idx >= 0) {
    selected.splice(idx, 1)
  } else if (selected.length < 3) {
    selected.push(cardIndex)
  }
  return { ...state, selectedCards: selected }
}

export function confirmPass(state: HeartsState): HeartsState {
  if (state.phase !== 'passing' || state.selectedCards.length !== 3) return state

  const passOffset = state.passDirection === 'left' ? 1 : state.passDirection === 'right' ? 3 : 2
  const newHands = state.hands.map(h => [...h])

  // Human passes
  const humanPassing = state.selectedCards.map(i => newHands[0][i])
  newHands[0] = newHands[0].filter((_, i) => !state.selectedCards.includes(i))

  // AI passes (pick 3 highest hearts/spades or random high cards)
  const aiPassing: Card[][] = [[], [], []]
  for (let p = 1; p < 4; p++) {
    const hand = [...newHands[p]]
    const toPass = aiSelectPassCards(hand)
    aiPassing[p - 1] = toPass
    newHands[p] = hand.filter(c => !toPass.includes(c))
  }

  // Distribute passed cards
  const target0 = (0 + passOffset) % 4
  for (const c of humanPassing) newHands[target0].push(c)
  for (let p = 1; p < 4; p++) {
    const target = (p + passOffset) % 4
    for (const c of aiPassing[p - 1]) newHands[target].push(c)
  }

  // Sort all hands
  for (let p = 0; p < 4; p++) {
    newHands[p] = sortHand(newHands[p])
  }

  // Find 2 of clubs
  const starter = newHands.findIndex(h => h.some(is2OfClubs))

  let next: HeartsState = {
    ...state,
    hands: newHands,
    selectedCards: [],
    phase: 'playing',
    currentPlayer: starter,
    leadPlayer: starter,
    message: starter === 0 ? 'You lead — play the 2 of clubs' : `${PLAYER_NAMES[starter]} leads`,
  }

  // If AI starts, play AI turns
  if (starter !== 0) {
    next = runAiTurns(next)
  }

  return next
}

function aiSelectPassCards(hand: Card[]): Card[] {
  // Pass: Queen of spades if we have it, high hearts, then high cards
  const sorted = [...hand].sort((a, b) => {
    if (isQueenOfSpades(a)) return -1
    if (isQueenOfSpades(b)) return 1
    if (a.suit === 'hearts' && b.suit !== 'hearts') return -1
    if (b.suit === 'hearts' && a.suit !== 'hearts') return 1
    return cardValue(b) - cardValue(a)
  })
  return sorted.slice(0, 3)
}

// ── Playing ──────────────────────────────────────────────────────────

export function playCard(state: HeartsState, cardIndex: number): HeartsState {
  if (state.phase !== 'playing' || state.currentPlayer !== 0) return state

  const hand = state.hands[0]
  const card = hand[cardIndex]
  if (!card) return state

  // Validate the play
  if (!isValidPlay(card, hand, state)) return state

  const newHands = state.hands.map(h => [...h])
  newHands[0].splice(cardIndex, 1)

  const newTrick = [...state.currentTrick, { player: 0, card }]
  const heartsBroken = state.heartsBroken || card.suit === 'hearts'

  let next: HeartsState = {
    ...state,
    hands: newHands,
    currentTrick: newTrick,
    heartsBroken,
  }

  if (newTrick.length === 4) {
    return completeTrick(next)
  }

  next.currentPlayer = (next.currentPlayer + 1) % 4
  return runAiTurns(next)
}

function isValidPlay(card: Card, hand: Card[], state: HeartsState): boolean {
  const isFirstTrick = state.completedTricks.length === 0
  const isLeading = state.currentTrick.length === 0

  // First trick must lead 2 of clubs
  if (isFirstTrick && isLeading) {
    return is2OfClubs(card)
  }

  // Must follow lead suit if able
  if (!isLeading) {
    const leadSuit = state.currentTrick[0].card.suit
    const hasSuit = hand.some(c => c.suit === leadSuit)
    if (hasSuit && card.suit !== leadSuit) return false
  }

  // Can't play hearts or Q♠ on first trick (unless only option)
  if (isFirstTrick && !isLeading) {
    if (pointsForCard(card) > 0) {
      const hasNonPoints = hand.some(c => pointsForCard(c) === 0 && c.suit === state.currentTrick[0].card.suit)
      const hasAnySuit = hand.some(c => c.suit === state.currentTrick[0].card.suit)
      if (hasAnySuit && hasNonPoints) return false
      // If void in lead suit, check if they have ANY non-point cards
      if (!hasAnySuit) {
        const hasAnyNonPoint = hand.some(c => pointsForCard(c) === 0)
        if (hasAnyNonPoint) return false
      }
    }
  }

  // Can't lead hearts until broken
  if (isLeading && card.suit === 'hearts' && !state.heartsBroken) {
    const hasNonHearts = hand.some(c => c.suit !== 'hearts')
    if (hasNonHearts) return false
  }

  return true
}

export function getValidPlays(state: HeartsState): number[] {
  if (state.phase !== 'playing' || state.currentPlayer !== 0) return []
  const hand = state.hands[0]
  return hand.map((c, i) => isValidPlay(c, hand, state) ? i : -1).filter(i => i >= 0)
}

// ── AI ───────────────────────────────────────────────────────────────

function runAiTurns(state: HeartsState): HeartsState {
  let current = state

  while (current.currentPlayer !== 0 && current.phase === 'playing') {
    const hand = current.hands[current.currentPlayer]
    const card = aiChooseCard(hand, current)

    const newHands = current.hands.map(h => [...h])
    newHands[current.currentPlayer] = newHands[current.currentPlayer].filter(
      c => !(c.rank === card.rank && c.suit === card.suit)
    )

    const newTrick = [...current.currentTrick, { player: current.currentPlayer, card }]
    const heartsBroken = current.heartsBroken || card.suit === 'hearts'

    current = {
      ...current,
      hands: newHands,
      currentTrick: newTrick,
      heartsBroken,
    }

    if (newTrick.length === 4) {
      current = completeTrick(current)
      if (current.phase !== 'playing') break
      // If next lead player is AI, continue
      continue
    }

    current.currentPlayer = (current.currentPlayer + 1) % 4
  }

  if (current.phase === 'playing') {
    current.message = 'Your turn'
  }

  return current
}

function aiChooseCard(hand: Card[], state: HeartsState): Card {
  const isLeading = state.currentTrick.length === 0
  const isFirstTrick = state.completedTricks.length === 0

  // Must play 2 of clubs on first lead
  if (isFirstTrick && isLeading) {
    return hand.find(is2OfClubs)!
  }

  // Get valid cards
  const valid = hand.filter(c => isValidPlay(c, hand, state))
  if (valid.length === 1) return valid[0]

  if (isLeading) {
    // Lead lowest non-heart card (or lowest heart if forced)
    const nonHearts = valid.filter(c => c.suit !== 'hearts')
    const pool = nonHearts.length > 0 ? nonHearts : valid
    return pool.sort((a, b) => cardValue(a) - cardValue(b))[0]
  }

  const leadSuit = state.currentTrick[0].card.suit
  const following = valid.filter(c => c.suit === leadSuit)

  if (following.length > 0) {
    // Following suit — play highest card that won't win, or lowest if must win
    const currentBest = state.currentTrick
      .filter(p => p.card.suit === leadSuit)
      .reduce((best, p) => cardValue(p.card) > cardValue(best.card) ? p : best)

    // Play highest card below the current winner
    const safeCards = following.filter(c => cardValue(c) < cardValue(currentBest.card))
    if (safeCards.length > 0) {
      return safeCards.sort((a, b) => cardValue(b) - cardValue(a))[0]
    }
    // Must win — play lowest winning card
    return following.sort((a, b) => cardValue(a) - cardValue(b))[0]
  }

  // Void in lead suit — dump dangerous cards
  const qos = valid.find(isQueenOfSpades)
  if (qos) return qos

  const hearts = valid.filter(c => c.suit === 'hearts')
  if (hearts.length > 0) return hearts.sort((a, b) => cardValue(b) - cardValue(a))[0]

  // Dump highest card
  return valid.sort((a, b) => cardValue(b) - cardValue(a))[0]
}

// ── Trick & Round resolution ─────────────────────────────────────────

function completeTrick(state: HeartsState): HeartsState {
  const winner = trickWinner(state.currentTrick)
  const points = trickPoints(state.currentTrick)

  const roundScores = [...state.roundScores]
  roundScores[winner] += points

  const completedTricks = [...state.completedTricks, state.currentTrick]

  // Check if round is over (all 13 tricks played)
  if (completedTricks.length === 13) {
    return resolveRound({
      ...state,
      currentTrick: [],
      completedTricks,
      roundScores,
      phase: 'trickComplete',
    })
  }

  let next: HeartsState = {
    ...state,
    currentTrick: [],
    completedTricks,
    roundScores,
    currentPlayer: winner,
    leadPlayer: winner,
    phase: 'playing',
    message: winner === 0 ? 'You won the trick — lead next' : `${PLAYER_NAMES[winner]} won the trick`,
  }

  // If winner is AI, auto-play
  if (winner !== 0) {
    next = runAiTurns(next)
  }

  return next
}

function resolveRound(state: HeartsState): HeartsState {
  const roundScores = [...state.roundScores]

  // Check for shoot the moon
  const moonShooter = roundScores.findIndex(s => s === 26)
  if (moonShooter >= 0) {
    for (let i = 0; i < 4; i++) {
      roundScores[i] = i === moonShooter ? 0 : 26
    }
  }

  const scores = state.scores.map((s, i) => s + roundScores[i])

  // Check for game over
  const maxScore = Math.max(...scores)
  if (maxScore >= GAME_OVER_SCORE) {
    const minScore = Math.min(...scores)
    const winner = scores.indexOf(minScore)
    return {
      ...state,
      scores,
      roundScores,
      phase: 'gameOver',
      message: winner === 0 ? 'You win!' : `${PLAYER_NAMES[winner]} wins!`,
    }
  }

  const moonMsg = moonShooter >= 0
    ? ` ${PLAYER_NAMES[moonShooter]} shot the moon!`
    : ''

  return {
    ...state,
    scores,
    roundScores,
    phase: 'roundOver',
    roundNumber: state.roundNumber + 1,
    message: `Round over!${moonMsg}`,
  }
}

export function nextRound(state: HeartsState): HeartsState {
  return dealRound(state)
}
