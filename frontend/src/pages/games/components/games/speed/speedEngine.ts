/**
 * Speed card game engine — pure logic, no side effects.
 *
 * Rules:
 * - 52-card deck split evenly (26 each)
 * - Each player has a 5-card hand and a draw pile
 * - 2 center piles with 1 starting card each
 * - Play a card if its rank is ±1 from center pile top (Ace wraps to King)
 * - After playing, auto-draw to refill hand to 5
 * - When neither player can play, flip new center cards from draw piles
 * - First to empty hand + draw pile wins
 */

import { createDeck, shuffleDeck, type Card } from '../../../utils/cardUtils'

// ── Types ───────────────────────────────────────────────────────────

export type Phase = 'playing' | 'stalled' | 'gameOver'

export interface SpeedState {
  playerHand: Card[]
  playerDrawPile: Card[]
  aiHand: Card[]
  aiDrawPile: Card[]
  centerPiles: [Card[], Card[]]   // each is a stack; top card = last element
  phase: Phase
  message: string
}

export interface Move {
  handIndex: number
  pileIndex: number
}

// ── Helpers ─────────────────────────────────────────────────────────

/** Check if a card can be played on a center pile's top card (rank ±1, ace wraps). */
export function isPlayable(card: Card, topCard: Card): boolean {
  const diff = Math.abs(card.rank - topCard.rank)
  return diff === 1 || diff === 12
}

/** Get the top card of a center pile. */
function pileTop(pile: Card[]): Card {
  return pile[pile.length - 1]
}

/** Refill a hand from a draw pile up to 5 cards. Returns new hand and draw pile. */
function refillHand(hand: Card[], drawPile: Card[]): { hand: Card[]; drawPile: Card[] } {
  const newHand = [...hand]
  const newDraw = [...drawPile]
  while (newHand.length < 5 && newDraw.length > 0) {
    newHand.push({ ...newDraw.shift()!, faceUp: true })
  }
  return { hand: newHand, drawPile: newDraw }
}

/** Get all valid moves for a given hand against center piles. */
export function getPlayableMoves(hand: Card[], centerPiles: [Card[], Card[]]): Move[] {
  const moves: Move[] = []
  for (let hi = 0; hi < hand.length; hi++) {
    for (let pi = 0; pi < 2; pi++) {
      if (centerPiles[pi].length > 0 && isPlayable(hand[hi], pileTop(centerPiles[pi]))) {
        moves.push({ handIndex: hi, pileIndex: pi })
      }
    }
  }
  return moves
}

/** Check if neither player has any playable moves. */
export function checkStalled(state: SpeedState): boolean {
  const playerMoves = getPlayableMoves(state.playerHand, state.centerPiles)
  const aiMoves = getPlayableMoves(state.aiHand, state.centerPiles)
  return playerMoves.length === 0 && aiMoves.length === 0
}

function checkWin(state: SpeedState): SpeedState {
  if (state.playerHand.length === 0 && state.playerDrawPile.length === 0) {
    return { ...state, phase: 'gameOver', message: 'You win! You emptied your cards first!' }
  }
  if (state.aiHand.length === 0 && state.aiDrawPile.length === 0) {
    return { ...state, phase: 'gameOver', message: 'AI wins — it emptied its cards first!' }
  }
  return state
}

// ── Engine functions ────────────────────────────────────────────────

/** Create a new Speed game: shuffle deck, split, deal hands, flip center cards. */
export function createSpeedGame(): SpeedState {
  const deck = shuffleDeck(createDeck())
  const half1 = deck.slice(0, 26)
  const half2 = deck.slice(26)

  // Deal 5-card hands from each half
  const playerHand = half1.slice(0, 5).map(c => ({ ...c, faceUp: true }))
  const aiHand = half2.slice(0, 5).map(c => ({ ...c, faceUp: true }))

  // Remaining go to draw piles
  const playerDrawPile = half1.slice(5)
  const aiDrawPile = half2.slice(5)

  // Flip 1 card from each draw pile onto center piles
  const centerLeft: Card[] = [{ ...playerDrawPile.shift()!, faceUp: true }]
  const centerRight: Card[] = [{ ...aiDrawPile.shift()!, faceUp: true }]

  return {
    playerHand,
    playerDrawPile,
    aiHand,
    aiDrawPile,
    centerPiles: [centerLeft, centerRight],
    phase: 'playing',
    message: 'Play a card!',
  }
}

/** Player plays a card from their hand onto a center pile. */
export function playCard(state: SpeedState, handIndex: number, pileIndex: number): SpeedState {
  if (state.phase !== 'playing') return state
  if (handIndex < 0 || handIndex >= state.playerHand.length) return state
  if (pileIndex < 0 || pileIndex > 1) return state

  const card = state.playerHand[handIndex]
  const pile = state.centerPiles[pileIndex]
  if (pile.length === 0 || !isPlayable(card, pileTop(pile))) return state

  // Remove card from hand
  const newHand = state.playerHand.filter((_, i) => i !== handIndex)

  // Add card to center pile
  const newPiles: [Card[], Card[]] = [
    pileIndex === 0 ? [...pile, { ...card, faceUp: true }] : [...state.centerPiles[0]],
    pileIndex === 1 ? [...pile, { ...card, faceUp: true }] : [...state.centerPiles[1]],
  ]

  // Refill hand from draw pile
  const { hand: filledHand, drawPile: newDrawPile } = refillHand(newHand, [...state.playerDrawPile])

  const next: SpeedState = {
    ...state,
    playerHand: filledHand,
    playerDrawPile: newDrawPile,
    centerPiles: newPiles,
    message: 'Nice play!',
  }

  // Check for win
  const afterWin = checkWin(next)
  if (afterWin.phase === 'gameOver') return afterWin

  // Check for stall
  if (checkStalled(afterWin)) {
    // If both draw piles are empty and stalled, game over
    if (afterWin.playerDrawPile.length === 0 && afterWin.aiDrawPile.length === 0) {
      const pLeft = afterWin.playerHand.length + afterWin.playerDrawPile.length
      const aLeft = afterWin.aiHand.length + afterWin.aiDrawPile.length
      if (pLeft < aLeft) return { ...afterWin, phase: 'gameOver', message: 'You win! Fewer cards remaining!' }
      if (aLeft < pLeft) return { ...afterWin, phase: 'gameOver', message: 'AI wins — fewer cards remaining!' }
      return { ...afterWin, phase: 'gameOver', message: 'Draw! Same cards remaining.' }
    }
    return { ...afterWin, phase: 'stalled', message: 'No moves! Flip new center cards.' }
  }

  return afterWin
}

/** AI plays a card from its hand onto a center pile. */
export function aiPlayCard(state: SpeedState, handIndex: number, pileIndex: number): SpeedState {
  if (state.phase !== 'playing') return state
  if (handIndex < 0 || handIndex >= state.aiHand.length) return state
  if (pileIndex < 0 || pileIndex > 1) return state

  const card = state.aiHand[handIndex]
  const pile = state.centerPiles[pileIndex]
  if (pile.length === 0 || !isPlayable(card, pileTop(pile))) return state

  // Remove card from AI hand
  const newHand = state.aiHand.filter((_, i) => i !== handIndex)

  // Add card to center pile
  const newPiles: [Card[], Card[]] = [
    pileIndex === 0 ? [...pile, { ...card, faceUp: true }] : [...state.centerPiles[0]],
    pileIndex === 1 ? [...pile, { ...card, faceUp: true }] : [...state.centerPiles[1]],
  ]

  // Refill AI hand from draw pile
  const { hand: filledHand, drawPile: newDrawPile } = refillHand(newHand, [...state.aiDrawPile])

  const next: SpeedState = {
    ...state,
    aiHand: filledHand,
    aiDrawPile: newDrawPile,
    centerPiles: newPiles,
    message: 'AI played a card!',
  }

  // Check for win
  const afterWin = checkWin(next)
  if (afterWin.phase === 'gameOver') return afterWin

  // Check for stall
  if (checkStalled(afterWin)) {
    if (afterWin.playerDrawPile.length === 0 && afterWin.aiDrawPile.length === 0) {
      const pLeft = afterWin.playerHand.length + afterWin.playerDrawPile.length
      const aLeft = afterWin.aiHand.length + afterWin.aiDrawPile.length
      if (pLeft < aLeft) return { ...afterWin, phase: 'gameOver', message: 'You win! Fewer cards remaining!' }
      if (aLeft < pLeft) return { ...afterWin, phase: 'gameOver', message: 'AI wins — fewer cards remaining!' }
      return { ...afterWin, phase: 'gameOver', message: 'Draw! Same cards remaining.' }
    }
    return { ...afterWin, phase: 'stalled', message: 'No moves! Flip new center cards.' }
  }

  return afterWin
}

/** Flip new center cards when stalled. Each player flips from their draw pile. */
export function flipCenterCards(state: SpeedState): SpeedState {
  if (state.phase !== 'stalled') return state

  const playerDraw = [...state.playerDrawPile]
  const aiDraw = [...state.aiDrawPile]
  const leftPile = [...state.centerPiles[0]]
  const rightPile = [...state.centerPiles[1]]

  // Each player flips a card onto their side
  if (playerDraw.length > 0) {
    leftPile.push({ ...playerDraw.shift()!, faceUp: true })
  }
  if (aiDraw.length > 0) {
    rightPile.push({ ...aiDraw.shift()!, faceUp: true })
  }

  const next: SpeedState = {
    ...state,
    playerDrawPile: playerDraw,
    aiDrawPile: aiDraw,
    centerPiles: [leftPile, rightPile],
    phase: 'playing',
    message: 'New cards flipped! Keep playing!',
  }

  // Check for stall again after flipping
  if (checkStalled(next)) {
    if (next.playerDrawPile.length === 0 && next.aiDrawPile.length === 0) {
      const pLeft = next.playerHand.length
      const aLeft = next.aiHand.length
      if (pLeft < aLeft) return { ...next, phase: 'gameOver', message: 'You win! Fewer cards remaining!' }
      if (aLeft < pLeft) return { ...next, phase: 'gameOver', message: 'AI wins — fewer cards remaining!' }
      return { ...next, phase: 'gameOver', message: 'Draw! Same cards remaining.' }
    }
    return { ...next, phase: 'stalled', message: 'Still stalled! Flip again.' }
  }

  return next
}

/** Get a random valid move for the AI, or null if none available. */
export function getAiMove(state: SpeedState): Move | null {
  if (state.phase !== 'playing') return null
  const moves = getPlayableMoves(state.aiHand, state.centerPiles)
  if (moves.length === 0) return null
  return moves[Math.floor(Math.random() * moves.length)]
}

/** Get valid moves for the human player. */
export function getPlayerMoves(state: SpeedState): Move[] {
  if (state.phase !== 'playing') return []
  return getPlayableMoves(state.playerHand, state.centerPiles)
}
