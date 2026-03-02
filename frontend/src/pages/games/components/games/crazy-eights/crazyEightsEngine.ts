/**
 * Crazy Eights engine — pure logic, no React.
 *
 * 2-4 players (1 human + AI opponents). First to empty hand wins.
 * 8s are wild — player picks a new suit.
 */

import { createDeck, shuffleDeck, type Card, type Suit } from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

export type Phase = 'playing' | 'choosingSuit' | 'roundOver' | 'gameOver'

export interface CrazyEightsState {
  hands: Card[][]
  drawPile: Card[]
  discardPile: Card[]
  currentPlayer: number
  currentSuit: Suit
  phase: Phase
  playerCount: number
  scores: number[]
  message: string
  targetScore: number
}

// ── Constants ────────────────────────────────────────────────────────

export const TARGET_SCORE = 200

function cardPoints(card: Card): number {
  if (card.rank === 8) return 50
  if (card.rank >= 11 || card.rank === 1) return 10
  return card.rank
}

// ── Game creation ────────────────────────────────────────────────────

export function createCrazyEightsGame(playerCount: number = 2): CrazyEightsState {
  const deck = shuffleDeck(createDeck()).map(c => ({ ...c, faceUp: true }))
  const cardsPerPlayer = playerCount <= 2 ? 7 : 5
  const hands: Card[][] = []

  let idx = 0
  for (let p = 0; p < playerCount; p++) {
    hands.push(deck.slice(idx, idx + cardsPerPlayer))
    idx += cardsPerPlayer
  }

  // First discard — if it's an 8, reshuffle (simplification: just pick another)
  let discardIdx = idx
  while (deck[discardIdx].rank === 8 && discardIdx < deck.length - 1) discardIdx++
  const firstDiscard = deck[discardIdx]
  const drawPile = [...deck.slice(idx, discardIdx), ...deck.slice(discardIdx + 1)]

  return {
    hands,
    drawPile,
    discardPile: [firstDiscard],
    currentPlayer: 0,
    currentSuit: firstDiscard.suit,
    phase: 'playing',
    playerCount,
    scores: new Array(playerCount).fill(0),
    message: 'Your turn — play a card or draw',
    targetScore: TARGET_SCORE,
  }
}

// ── Helpers ──────────────────────────────────────────────────────────

function topDiscard(state: CrazyEightsState): Card {
  return state.discardPile[state.discardPile.length - 1]
}

export function canPlayCard(card: Card, state: CrazyEightsState): boolean {
  if (card.rank === 8) return true
  const top = topDiscard(state)
  return card.suit === state.currentSuit || card.rank === top.rank
}

function getPlayableCards(hand: Card[], state: CrazyEightsState): number[] {
  return hand.map((c, i) => canPlayCard(c, state) ? i : -1).filter(i => i >= 0)
}

function reshuffleDrawPile(state: CrazyEightsState): Card[] {
  if (state.drawPile.length > 0) return [...state.drawPile]
  // Keep top discard, shuffle the rest back
  const top = state.discardPile[state.discardPile.length - 1]
  const reshuffled = shuffleDeck(state.discardPile.slice(0, -1))
  state.discardPile.splice(0, state.discardPile.length, top)
  return reshuffled
}

// ── Actions ──────────────────────────────────────────────────────────

export function playCard(state: CrazyEightsState, cardIndex: number): CrazyEightsState {
  if (state.phase !== 'playing') return state
  if (state.currentPlayer !== 0) return state

  const hand = [...state.hands[0]]
  const card = hand[cardIndex]
  if (!card || !canPlayCard(card, state)) return state

  hand.splice(cardIndex, 1)
  const newHands = [...state.hands]
  newHands[0] = hand
  const newDiscard = [...state.discardPile, card]

  // Check if human won the round
  if (hand.length === 0) {
    return scoreRound({ ...state, hands: newHands, discardPile: newDiscard }, 0)
  }

  // If played an 8, let human choose suit
  if (card.rank === 8) {
    return {
      ...state,
      hands: newHands,
      discardPile: newDiscard,
      phase: 'choosingSuit',
      message: 'Choose a suit',
    }
  }

  return advanceTurn({
    ...state,
    hands: newHands,
    discardPile: newDiscard,
    currentSuit: card.suit,
  })
}

export function chooseSuit(state: CrazyEightsState, suit: Suit): CrazyEightsState {
  if (state.phase !== 'choosingSuit') return state
  return advanceTurn({ ...state, currentSuit: suit, phase: 'playing' })
}

export function drawCard(state: CrazyEightsState): CrazyEightsState {
  if (state.phase !== 'playing') return state
  if (state.currentPlayer !== 0) return state

  let drawPile = reshuffleDrawPile(state)
  if (drawPile.length === 0) {
    // No cards to draw — pass turn
    return advanceTurn({ ...state, drawPile })
  }

  const card = drawPile.pop()!
  const newHands = [...state.hands]
  newHands[0] = [...newHands[0], { ...card, faceUp: true }]

  return {
    ...state,
    hands: newHands,
    drawPile,
    message: `Drew a card. ${canPlayCard(card, state) ? 'You can play it!' : 'Play a card or draw again.'}`,
  }
}

function advanceTurn(state: CrazyEightsState): CrazyEightsState {
  let current = { ...state, phase: 'playing' as Phase }
  let nextPlayer = (current.currentPlayer + 1) % current.playerCount

  // AI players take turns
  while (nextPlayer !== 0) {
    current = aiTurn({ ...current, currentPlayer: nextPlayer })
    if (current.phase === 'roundOver' || current.phase === 'gameOver') return current
    nextPlayer = (nextPlayer + 1) % current.playerCount
  }

  return {
    ...current,
    currentPlayer: 0,
    message: 'Your turn — play a card or draw',
  }
}

function aiTurn(state: CrazyEightsState): CrazyEightsState {
  const playerIdx = state.currentPlayer
  const hand = [...state.hands[playerIdx]]
  const playable = getPlayableCards(hand, state)

  if (playable.length === 0) {
    // AI draws
    let drawPile = reshuffleDrawPile(state)
    if (drawPile.length === 0) return state // pass

    const card = drawPile.pop()!
    const newHands = [...state.hands]
    newHands[playerIdx] = [...hand, { ...card, faceUp: true }]

    // Check if drawn card is playable
    if (canPlayCard(card, { ...state, drawPile })) {
      newHands[playerIdx] = newHands[playerIdx].filter((_, i) => i !== newHands[playerIdx].length - 1)
      const newDiscard = [...state.discardPile, card]
      if (newHands[playerIdx].length === 0) {
        return scoreRound({ ...state, hands: newHands, discardPile: newDiscard, drawPile }, playerIdx)
      }
      const newSuit = card.rank === 8 ? pickBestSuit(newHands[playerIdx]) : card.suit
      return { ...state, hands: newHands, discardPile: newDiscard, drawPile, currentSuit: newSuit }
    }

    return { ...state, hands: newHands, drawPile }
  }

  // AI plays: prefer non-8 cards, save 8s for last
  let chosenIdx = playable.find(i => hand[i].rank !== 8) ?? playable[0]
  const card = hand[chosenIdx]
  hand.splice(chosenIdx, 1)

  const newHands = [...state.hands]
  newHands[playerIdx] = hand
  const newDiscard = [...state.discardPile, card]

  if (hand.length === 0) {
    return scoreRound({ ...state, hands: newHands, discardPile: newDiscard }, playerIdx)
  }

  const newSuit = card.rank === 8 ? pickBestSuit(hand) : card.suit
  return { ...state, hands: newHands, discardPile: newDiscard, currentSuit: newSuit }
}

function pickBestSuit(hand: Card[]): Suit {
  const counts: Record<Suit, number> = { hearts: 0, diamonds: 0, clubs: 0, spades: 0 }
  for (const c of hand) {
    if (c.rank !== 8) counts[c.suit]++
  }
  return (Object.entries(counts) as [Suit, number][]).sort((a, b) => b[1] - a[1])[0][0]
}

function scoreRound(state: CrazyEightsState, winner: number): CrazyEightsState {
  let points = 0
  for (let p = 0; p < state.playerCount; p++) {
    if (p === winner) continue
    for (const card of state.hands[p]) {
      points += cardPoints(card)
    }
  }

  const scores = [...state.scores]
  scores[winner] += points

  const winnerName = winner === 0 ? 'You' : `Player ${winner + 1}`

  if (scores[winner] >= state.targetScore) {
    return {
      ...state,
      scores,
      phase: 'gameOver',
      message: `${winnerName} win${winner === 0 ? '' : 's'} the game with ${scores[winner]} points!`,
    }
  }

  return {
    ...state,
    scores,
    phase: 'roundOver',
    message: `${winnerName} win${winner === 0 ? '' : 's'} the round! +${points} points`,
  }
}

export function newRound(state: CrazyEightsState): CrazyEightsState {
  const fresh = createCrazyEightsGame(state.playerCount)
  return { ...fresh, scores: state.scores }
}

// ── Queries ──────────────────────────────────────────────────────────

export function getHumanPlayableCards(state: CrazyEightsState): number[] {
  if (state.currentPlayer !== 0 || state.phase !== 'playing') return []
  return getPlayableCards(state.hands[0], state)
}
