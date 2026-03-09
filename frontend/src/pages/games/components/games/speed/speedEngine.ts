/**
 * Speed card game engine — pure logic, no side effects.
 *
 * Standard Speed rules:
 * - 52-card deck dealt as: 5-card hand + 15-card draw pile per player,
 *   2 replacement piles of 5 each, 2 center piles of 1 each
 * - Play a card if its rank is ±1 from center pile top (Ace wraps to King)
 * - After playing, auto-draw to refill hand to 5
 * - When neither player can play, flip from replacement piles onto center
 * - When replacement piles are empty and stalled, game is over
 * - First to empty hand + draw pile wins
 */

import { createDeck, shuffleDeck, type Card } from '../../../utils/cardUtils'

// ── Types ───────────────────────────────────────────────────────────

export type Phase = 'ready' | 'playing' | 'stalled' | 'gameOver'
export type AiDifficulty = 'easy' | 'normal' | 'adept'

export interface SpeedState {
  playerHand: Card[]
  playerDrawPile: Card[]
  aiHand: Card[]
  aiDrawPile: Card[]
  centerPiles: [Card[], Card[]]   // each is a stack; top card = last element
  replacementPiles: [Card[], Card[]]  // 5-card piles used to unstick the game
  phase: Phase
  message: string
  difficulty: AiDifficulty
}

// ── Human-modeled AI reaction timing ────────────────────────────────
//
// Speed is a real-time game. AI card play is broken into cognitive stages:
//   1. Scan — scanning hand and center piles for a valid play
//   2. Recognize — identifying the matching card
//   3. Decide — committing to play it
//   4. Act — executing the play
//
// Bounded: never faster than 90th percentile, never slower than 50th percentile.

interface ReactionRange { min: number; max: number }

const SPEED_PLAY_PROFILE: { scan: ReactionRange; recognize: ReactionRange; decide: ReactionRange; act: ReactionRange } = {
  scan:      { min: 80,  max: 250 },
  recognize: { min: 60,  max: 200 },
  decide:    { min: 40,  max: 150 },
  act:       { min: 60,  max: 180 },
}

function difficultyBias(difficulty: AiDifficulty): number {
  switch (difficulty) {
    case 'easy':   return 0.0 + Math.random() * 0.3
    case 'normal': return 0.3 + Math.random() * 0.3
    case 'adept':  return 0.6 + Math.random() * 0.4
  }
}

/** Generate AI play delay using human cognitive model. */
export function generateAiPlayDelay(difficulty: AiDifficulty): number {
  const bias = difficultyBias(difficulty)
  let total = 0
  for (const stage of [SPEED_PLAY_PROFILE.scan, SPEED_PLAY_PROFILE.recognize, SPEED_PLAY_PROFILE.decide, SPEED_PLAY_PROFILE.act]) {
    const range = stage.max - stage.min
    const center = stage.max - (range * bias)
    const variance = range * 0.3 * (Math.random() * 2 - 1)
    total += Math.max(stage.min, Math.min(stage.max, center + variance))
  }
  return Math.round(total)
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

function resolveStall(state: SpeedState): SpeedState {
  if (!checkStalled(state)) return state

  // If replacement piles are both empty, game over — fewest cards wins
  if (state.replacementPiles[0].length === 0 && state.replacementPiles[1].length === 0) {
    const pLeft = state.playerHand.length + state.playerDrawPile.length
    const aLeft = state.aiHand.length + state.aiDrawPile.length
    if (pLeft < aLeft) return { ...state, phase: 'gameOver', message: 'You win! Fewer cards remaining!' }
    if (aLeft < pLeft) return { ...state, phase: 'gameOver', message: 'AI wins — fewer cards remaining!' }
    return { ...state, phase: 'gameOver', message: 'Draw! Same cards remaining.' }
  }

  return { ...state, phase: 'stalled', message: 'No moves! Flip from the replacement piles.' }
}

// ── Engine functions ────────────────────────────────────────────────

/** Create a new Speed game with standard deal. */
export function createSpeedGame(difficulty: AiDifficulty = 'normal'): SpeedState {
  const deck = shuffleDeck(createDeck())
  let i = 0

  // Player hand: 5 cards (face-down until flip)
  const playerHand = deck.slice(i, i + 5).map(c => ({ ...c, faceUp: false }))
  i += 5

  // Player draw pile: 15 cards
  const playerDrawPile = deck.slice(i, i + 15).map(c => ({ ...c, faceUp: false }))
  i += 15

  // Replacement pile (left): 5 cards
  const replacementLeft = deck.slice(i, i + 5).map(c => ({ ...c, faceUp: false }))
  i += 5

  // Center pile (left): 1 card (face-down until flip)
  const centerLeft: Card[] = [{ ...deck[i], faceUp: false }]
  i += 1

  // Center pile (right): 1 card (face-down until flip)
  const centerRight: Card[] = [{ ...deck[i], faceUp: false }]
  i += 1

  // Replacement pile (right): 5 cards
  const replacementRight = deck.slice(i, i + 5).map(c => ({ ...c, faceUp: false }))
  i += 5

  // AI draw pile: 15 cards
  const aiDrawPile = deck.slice(i, i + 15).map(c => ({ ...c, faceUp: false }))
  i += 15

  // AI hand: 5 cards (face-down until flip)
  const aiHand = deck.slice(i, i + 5).map(c => ({ ...c, faceUp: false }))

  return {
    playerHand,
    playerDrawPile,
    aiHand,
    aiDrawPile,
    centerPiles: [centerLeft, centerRight],
    replacementPiles: [replacementLeft, replacementRight],
    difficulty,
    phase: 'ready',
    message: 'Ready? Flip the center cards to start!',
  }
}

/** Flip the starting center cards and reveal hands — transitions from 'ready' to 'playing'. */
export function flipStartingCards(state: SpeedState): SpeedState {
  if (state.phase !== 'ready') return state

  return {
    ...state,
    phase: 'playing',
    playerHand: state.playerHand.map(c => ({ ...c, faceUp: true })),
    aiHand: state.aiHand.map(c => ({ ...c, faceUp: true })),
    centerPiles: [
      state.centerPiles[0].map(c => ({ ...c, faceUp: true })),
      state.centerPiles[1].map(c => ({ ...c, faceUp: true })),
    ],
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

  const newHand = state.playerHand.filter((_, i) => i !== handIndex)
  const newPiles: [Card[], Card[]] = [
    pileIndex === 0 ? [...pile, { ...card, faceUp: true }] : [...state.centerPiles[0]],
    pileIndex === 1 ? [...pile, { ...card, faceUp: true }] : [...state.centerPiles[1]],
  ]

  const { hand: filledHand, drawPile: newDrawPile } = refillHand(newHand, [...state.playerDrawPile])

  const next: SpeedState = {
    ...state,
    playerHand: filledHand,
    playerDrawPile: newDrawPile,
    centerPiles: newPiles,
    message: 'Nice play!',
  }

  const afterWin = checkWin(next)
  if (afterWin.phase === 'gameOver') return afterWin

  return resolveStall(afterWin)
}

/** AI plays a card from its hand onto a center pile. */
export function aiPlayCard(state: SpeedState, handIndex: number, pileIndex: number): SpeedState {
  if (state.phase !== 'playing') return state
  if (handIndex < 0 || handIndex >= state.aiHand.length) return state
  if (pileIndex < 0 || pileIndex > 1) return state

  const card = state.aiHand[handIndex]
  const pile = state.centerPiles[pileIndex]
  if (pile.length === 0 || !isPlayable(card, pileTop(pile))) return state

  const newHand = state.aiHand.filter((_, i) => i !== handIndex)
  const newPiles: [Card[], Card[]] = [
    pileIndex === 0 ? [...pile, { ...card, faceUp: true }] : [...state.centerPiles[0]],
    pileIndex === 1 ? [...pile, { ...card, faceUp: true }] : [...state.centerPiles[1]],
  ]

  const { hand: filledHand, drawPile: newDrawPile } = refillHand(newHand, [...state.aiDrawPile])

  const next: SpeedState = {
    ...state,
    aiHand: filledHand,
    aiDrawPile: newDrawPile,
    centerPiles: newPiles,
    message: 'AI played a card!',
  }

  const afterWin = checkWin(next)
  if (afterWin.phase === 'gameOver') return afterWin

  return resolveStall(afterWin)
}

/** Flip new center cards from replacement piles when stalled. */
export function flipCenterCards(state: SpeedState): SpeedState {
  if (state.phase !== 'stalled') return state

  const leftRepl = [...state.replacementPiles[0]]
  const rightRepl = [...state.replacementPiles[1]]
  const leftPile = [...state.centerPiles[0]]
  const rightPile = [...state.centerPiles[1]]

  if (leftRepl.length > 0) {
    leftPile.push({ ...leftRepl.shift()!, faceUp: true })
  }
  if (rightRepl.length > 0) {
    rightPile.push({ ...rightRepl.shift()!, faceUp: true })
  }

  const next: SpeedState = {
    ...state,
    replacementPiles: [leftRepl, rightRepl],
    centerPiles: [leftPile, rightPile],
    phase: 'playing',
    message: 'New cards flipped! Keep playing!',
  }

  return resolveStall(next)
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
