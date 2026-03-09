/**
 * Shalas — card game engine.
 *
 * Pure functions for game state management.
 * Layout: 6 rows on the table, dealt from a standard 52-card deck.
 *
 * Special cards:
 *   10 — Destroyer: removes itself + entire discard pile from game
 *    2 — Wildcard:  player picks reset value (A or 3+), 2 stays on discard
 *    7 — Selector:  pick any table card → discard; 2-player: opponent takes 10 cards
 *    3 — Blocker:   (2-player only) played in response to block 7's penalty
 *    4-of-a-kind — Wild Set: resets discard to Ace, all 4 stay on discard
 *
 * Play rules:
 *   - Cards played must be equal or higher rank than top of discard
 *   - Player must maintain 3 cards in hand (draw after each card played)
 *   - Once hand + draw stack empty, play from table: Row 4 → Row 3 → Row 2
 *   - Win: clear all cards (hand + table)
 *   - Can't play (1-player): shuffle discard, give player 10 cards
 *   - Can't play (2-player): skip turn
 */

import type { Card } from '../../../utils/cardUtils'
import { createDeck, shuffleDeck } from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

export interface PairStack {
  faceDown: Card | null
  faceUp: Card | null
}

export type GamePhase =
  | 'playing'        // normal turn
  | 'choose_wild'    // player must pick reset value for a 2 wildcard
  | 'choose_selector'// player must pick a table card for a 7
  | 'block_chance'   // opponent can play a 3 to block 7 penalty (2-player)
  | 'won'
  | 'lost'

export type PlaySource =
  | { type: 'hand'; index: number }
  | { type: 'pairRow'; stackIndex: number; card: 'faceUp' | 'faceDown' }
  | { type: 'stackRow'; stackIndex: number }
  | { type: 'secondRow'; index: number }

export interface ShalasState {
  /** Row 1 (bottom): player's hand — face-up cards */
  hand: Card[]
  /** Row 2: 4 face-up cards */
  secondRow: Card[]
  /** Row 3: 4 stacks of 5 face-down cards each */
  stackRow: Card[][]
  /** Row 4: 3 stacks, each with 1 face-down + 1 face-up card */
  pairRow: PairStack[]
  /** Draw stack: remaining deck, face-down */
  drawStack: Card[]
  /** Discard pile: face-up */
  discardPile: Card[]
  /** Cards permanently removed from game (by Destroyer) */
  burned: Card[]
  /** Current game phase */
  phase: GamePhase
  /** Status message for UI */
  message: string
  /** 1 or 2 player mode */
  playerCount: 1 | 2
  /** Whose turn: 0 = player, 1 = opponent */
  currentPlayer: number
  /** Opponent's hand (2-player only) */
  opponentHand: Card[]
  /** The effective rank the next card must meet (normally top of discard) */
  effectiveRank: number
  /** True when an Ace is the effective top — blocks Kings (except 4-of-a-kind) */
  aceOnTop: boolean
  /** Pending 4-of-a-kind cards waiting to be played together */
  selectedCards: number[]
}

// ── Constants ────────────────────────────────────────────────────────

const REFILL_THRESHOLD = 3
const REFILL_TARGET = 5
const SELECTOR_PENALTY_COUNT = 10

// ── Game creation ────────────────────────────────────────────────────

/** Create a new Shalas game — shuffle and deal into all positions. */
export function createShalasGame(playerCount: 1 | 2 = 1): ShalasState {
  const deck = shuffleDeck(createDeck())
  let i = 0

  // Row 1: 5 face-up cards (player's hand)
  const hand = deck.slice(i, i + 5).map(c => ({ ...c, faceUp: true }))
  i += 5

  // Row 2: 4 face-up cards
  const secondRow = deck.slice(i, i + 4).map(c => ({ ...c, faceUp: true }))
  i += 4

  // Row 3: 4 stacks of 3 face-down cards
  const stackRow: Card[][] = []
  for (let s = 0; s < 4; s++) {
    stackRow.push(deck.slice(i, i + 3).map(c => ({ ...c, faceUp: false })))
    i += 3
  }

  // Row 4: 3 stacks of (1 face-down + 1 face-up)
  const pairRow: PairStack[] = []
  for (let p = 0; p < 3; p++) {
    pairRow.push({
      faceDown: { ...deck[i], faceUp: false },
      faceUp: { ...deck[i + 1], faceUp: true },
    })
    i += 2
  }

  // Remaining cards → draw stack
  const drawStack = deck.slice(i).map(c => ({ ...c, faceUp: false }))

  return {
    hand,
    secondRow,
    stackRow,
    pairRow,
    drawStack,
    discardPile: [],
    burned: [],
    phase: 'playing',
    message: 'Play a card from your hand',
    playerCount,
    currentPlayer: 0,
    opponentHand: [],
    effectiveRank: 0, // 0 = any card can be played (empty discard)
    aceOnTop: false,
    selectedCards: [],
  }
}

// ── Query helpers ────────────────────────────────────────────────────

/** Get the effective rank that the next card must meet or exceed. */
export function getEffectiveRank(state: ShalasState): number {
  return state.effectiveRank
}

/** Check if a card can be legally played on the discard pile. */
export function canPlay(card: Card, state: ShalasState): boolean {
  // Special cards can always be played
  if (card.rank === 10 || card.rank === 2 || card.rank === 7) return true
  // Empty discard — anything goes
  if (state.effectiveRank === 0) return true
  // Ace is dual: acts as 1 (lowest) AND highest (above King) — always playable
  if (card.rank === 1) return true
  // King cannot be played on an Ace (unless via 4-of-a-kind, handled separately)
  if (card.rank === 13 && state.aceOnTop) return false
  // Normal play: must be >= effective rank
  return card.rank >= state.effectiveRank
}

/** Determine where the player should currently play from. */
export function getActiveSource(state: ShalasState): 'hand' | 'pairRow' | 'stackRow' | 'secondRow' | 'none' {
  // Hand first (while cards remain or draw stack has cards)
  if (state.hand.length > 0) return 'hand'
  // Then table rows top-down: Row 4 → Row 3 → Row 2
  if (state.pairRow.some(p => p.faceUp !== null || p.faceDown !== null)) return 'pairRow'
  if (state.stackRow.some(s => s.length > 0)) return 'stackRow'
  if (state.secondRow.length > 0) return 'secondRow'
  return 'none'
}

/** Check if the player has won (all cards cleared). */
export function checkWin(state: ShalasState): boolean {
  return (
    state.hand.length === 0 &&
    state.drawStack.length === 0 &&
    state.secondRow.length === 0 &&
    state.stackRow.every(s => s.length === 0) &&
    state.pairRow.every(p => p.faceUp === null && p.faceDown === null)
  )
}

/** Check if the player can play any card from their current active source. */
export function hasValidPlay(state: ShalasState): boolean {
  const source = getActiveSource(state)
  if (source === 'none') return false

  if (source === 'hand') {
    // Check for 4-of-a-kind
    if (hasFourOfAKind(state.hand)) return true
    return state.hand.some(c => canPlay(c, state))
  }
  if (source === 'pairRow') {
    for (const p of state.pairRow) {
      if (p.faceUp && canPlay(p.faceUp, state)) return true
      // Face-down cards are blind plays — always allowed
      if (p.faceDown && p.faceUp === null) return true
    }
    return false
  }
  if (source === 'stackRow') {
    // Top card of each stack; face-down = blind play
    for (const s of state.stackRow) {
      if (s.length > 0) return true // blind play always "allowed" (may fail)
    }
    return false
  }
  if (source === 'secondRow') {
    return state.secondRow.some(c => canPlay(c, state))
  }
  return false
}

/** Check if a hand contains 4-of-a-kind. */
export function hasFourOfAKind(cards: Card[]): boolean {
  const counts: Record<number, number> = {}
  for (const c of cards) {
    counts[c.rank] = (counts[c.rank] || 0) + 1
    if (counts[c.rank] >= 4) return true
  }
  return false
}

/** Get ranks that have 4-of-a-kind in the given cards. */
export function getFourOfAKindRanks(cards: Card[]): number[] {
  const counts: Record<number, number> = {}
  for (const c of cards) {
    counts[c.rank] = (counts[c.rank] || 0) + 1
  }
  return Object.entries(counts)
    .filter(([, count]) => count >= 4)
    .map(([rank]) => Number(rank))
}

// ── Actions ──────────────────────────────────────────────────────────

/** Draw cards from draw stack — when hand drops below 3, refill to 5. */
function refillHand(state: ShalasState): ShalasState {
  if (state.drawStack.length === 0) return state
  if (state.hand.length >= REFILL_THRESHOLD) return state
  const hand = [...state.hand]
  const drawStack = [...state.drawStack]
  while (hand.length < REFILL_TARGET && drawStack.length > 0) {
    const card = drawStack.pop()!
    hand.push({ ...card, faceUp: true })
  }
  return { ...state, hand, drawStack }
}

/** Manually draw one card from the draw stack into hand. */
export function drawOneCard(state: ShalasState): ShalasState {
  if (state.phase !== 'playing') return state
  if (state.drawStack.length === 0) return { ...state, message: 'Draw stack is empty' }
  const drawStack = [...state.drawStack]
  const card = drawStack.pop()!
  const hand = [...state.hand, { ...card, faceUp: true }]
  return { ...state, hand, drawStack, message: 'Drew a card' }
}

/** Play one or more same-rank cards from hand by indices. */
export function playFromHand(state: ShalasState, cardIndices: number[]): ShalasState {
  if (state.phase !== 'playing') return state
  if (cardIndices.length === 0) return state

  // Validate all indices
  for (const idx of cardIndices) {
    if (idx < 0 || idx >= state.hand.length) return state
  }

  // All selected cards must be the same rank
  const rank = state.hand[cardIndices[0]].rank
  if (!cardIndices.every(i => state.hand[i].rank === rank)) {
    return { ...state, message: 'All selected cards must be the same rank' }
  }

  // 4-of-a-kind: automatic wild set
  if (cardIndices.length >= 4) {
    const cards = cardIndices.slice(0, 4).map(i => ({ ...state.hand[i], faceUp: true }))
    const hand = state.hand.filter((_, i) => !cardIndices.slice(0, 4).includes(i))
    const discardPile = [...state.discardPile, ...cards]

    let next: ShalasState = {
      ...state,
      hand,
      discardPile,
      effectiveRank: 1, // reset to Ace
      aceOnTop: true,
      message: '4-of-a-kind! Discard reset to Ace',
    }
    next = refillHand(next)
    next = checkEndOfTurn(next)
    return next
  }

  // Normal play (1-3 cards of the same rank)
  const card = state.hand[cardIndices[0]]
  if (!canPlay(card, state)) {
    // Penalty: played card(s) + entire discard pile go to hand
    const playedCards = cardIndices.map(i => ({ ...state.hand[i], faceUp: true }))
    const remainingHand = state.hand.filter((_, i) => !cardIndices.includes(i))
    const pickUp = [...state.discardPile, ...playedCards].map(c => ({ ...c, faceUp: true }))
    return {
      ...state,
      hand: [...remainingHand, ...pickUp],
      discardPile: [],
      effectiveRank: 0,
      aceOnTop: false,
      message: `Can't play ${rankName(card.rank)} — picked up the discard pile`,
    }
  }

  const playedCards = cardIndices.map(i => ({ ...state.hand[i], faceUp: true }))
  const hand = state.hand.filter((_, i) => !cardIndices.includes(i))

  // For special cards (10, 2, 7) only the first triggers the effect;
  // extras of the same rank are just normal plays alongside it.
  // Place all cards, but resolve based on the first card's rank.
  return resolvePlay(
    { ...state, hand },
    playedCards[0],
    playedCards.slice(1),
  )
}

/** Play the face-up card from a pair stack. */
export function playFromPairRow(state: ShalasState, stackIndex: number, position: 'faceUp' | 'faceDown'): ShalasState {
  if (state.phase !== 'playing') return state
  if (getActiveSource(state) !== 'pairRow') return state

  const pair = state.pairRow[stackIndex]
  if (!pair) return state

  // Extract the card before mutating the row
  let card: Card | undefined
  if (position === 'faceUp' && pair.faceUp) {
    card = pair.faceUp
  } else if (position === 'faceDown' && pair.faceUp === null && pair.faceDown) {
    card = pair.faceDown
  }
  if (!card) return state

  const playedCard: Card = { suit: card.suit, rank: card.rank, faceUp: true }
  const newPairRow = state.pairRow.map((p, i) => {
    if (i !== stackIndex) return p
    if (position === 'faceUp') return { ...p, faceUp: null }
    return { ...p, faceDown: null }
  })

  // Face-down is a blind play — if it can't be played, it goes to discard anyway
  // but player takes a penalty (picks up discard) — actually per rules, face-down
  // cards from table are always playable. They're revealed and placed.
  if (!canPlay(playedCard, state) && position === 'faceDown') {
    // Blind play failed — card goes on discard, player picks up the pile
    const discardPile = [...state.discardPile, playedCard]
    return {
      ...state,
      pairRow: newPairRow,
      hand: [...state.hand, ...discardPile.map(c => ({ ...c, faceUp: true }))],
      discardPile: [],
      effectiveRank: 0,
      aceOnTop: false,
      message: 'Blind play failed! You picked up the discard pile',
    }
  }

  if (!canPlay(playedCard, state)) {
    const discardPile = [...state.discardPile, playedCard]
    return {
      ...state,
      pairRow: newPairRow,
      hand: [...state.hand, ...discardPile.map(c => ({ ...c, faceUp: true }))],
      discardPile: [],
      effectiveRank: 0,
      aceOnTop: false,
      message: `Can't play ${rankName(playedCard.rank)} — picked up the discard pile`,
    }
  }

  return resolvePlay({ ...state, pairRow: newPairRow }, playedCard)
}

/** Play the top card from a face-down stack (Row 3). */
export function playFromStackRow(state: ShalasState, stackIndex: number): ShalasState {
  if (state.phase !== 'playing') return state
  if (getActiveSource(state) !== 'stackRow') return state

  const stack = state.stackRow[stackIndex]
  if (!stack || stack.length === 0) return state

  const card = { ...stack[stack.length - 1], faceUp: true }
  const newStackRow = state.stackRow.map((s, i) =>
    i === stackIndex ? s.slice(0, -1) : s
  )

  // Blind play — if it fails, player picks up discard
  if (!canPlay(card, state)) {
    const discardPile = [...state.discardPile, card]
    return {
      ...state,
      stackRow: newStackRow,
      hand: [...state.hand, ...discardPile.map(c => ({ ...c, faceUp: true }))],
      discardPile: [],
      effectiveRank: 0,
      aceOnTop: false,
      message: 'Blind play failed! You picked up the discard pile',
    }
  }

  return resolvePlay({ ...state, stackRow: newStackRow }, card)
}

/** Play a card from Row 2 (4 face-up cards). */
export function playFromSecondRow(state: ShalasState, cardIndex: number): ShalasState {
  if (state.phase !== 'playing') return state
  if (getActiveSource(state) !== 'secondRow') return state

  const card = state.secondRow[cardIndex]
  if (!card) return state
  if (!canPlay(card, state)) {
    const secondRow = state.secondRow.filter((_, i) => i !== cardIndex)
    const pickUp = [...state.discardPile, { ...card, faceUp: true }].map(c => ({ ...c, faceUp: true }))
    return {
      ...state,
      secondRow,
      hand: [...state.hand, ...pickUp],
      discardPile: [],
      effectiveRank: 0,
      aceOnTop: false,
      message: `Can't play ${rankName(card.rank)} — picked up the discard pile`,
    }
  }

  const secondRow = state.secondRow.filter((_, i) => i !== cardIndex)
  return resolvePlay({ ...state, secondRow }, { ...card, faceUp: true })
}

/** Resolve a played card — handle special card effects.
 *  extraCards: additional same-rank cards played alongside the primary card. */
function resolvePlay(state: ShalasState, card: Card, extraCards: Card[] = []): ShalasState {
  const allPlayed = [card, ...extraCards]

  // ── 10: Destroyer (only if discard pile has cards) ──────────────
  if (card.rank === 10 && state.discardPile.length > 0) {
    const burned = [...state.burned, ...allPlayed, ...state.discardPile]
    let next: ShalasState = {
      ...state,
      discardPile: [],
      burned,
      effectiveRank: 0,
      aceOnTop: false,
      message: `Destroyer! ${allPlayed.length > 1 ? allPlayed.length + ' tens + discard' : 'Discard'} pile cleared`,
    }
    next = refillHand(next)
    next = checkEndOfTurn(next)
    return next
  }

  // ── 2: Wildcard — enter choose_wild phase ──────────────────────
  if (card.rank === 2) {
    const discardPile = [...state.discardPile, ...allPlayed]
    let next: ShalasState = {
      ...state,
      discardPile,
      aceOnTop: false,
      phase: 'choose_wild',
      message: 'Wildcard! Choose the reset value (A, or 3–K)',
    }
    next = refillHand(next)
    return next
  }

  // ── 7: Selector — enter choose_selector phase ──────────────────
  if (card.rank === 7) {
    const discardPile = [...state.discardPile, ...allPlayed]
    let next: ShalasState = {
      ...state,
      discardPile,
      effectiveRank: 7,
      aceOnTop: false,
      phase: 'choose_selector',
      message: 'Selector! Pick any card from the table to discard',
    }
    next = refillHand(next)
    return next
  }

  // ── Ace: dual rank — highest card, but resets effective to 1 ───
  const isAce = card.rank === 1
  // ── Normal card(s) ─────────────────────────────────────────────
  const discardPile = [...state.discardPile, ...allPlayed]
  let next: ShalasState = {
    ...state,
    discardPile,
    effectiveRank: card.rank,
    aceOnTop: isAce,
    message: allPlayed.length > 1
      ? `Played ${allPlayed.length} × ${rankName(card.rank)}`
      : `Played ${rankName(card.rank)}`,
  }
  next = refillHand(next)
  next = checkEndOfTurn(next)
  return next
}

/** Complete the wildcard choice — set effective rank. */
export function chooseWildValue(state: ShalasState, rank: number): ShalasState {
  if (state.phase !== 'choose_wild') return state
  // Valid choices: 1 (Ace) or 3–13
  if (rank !== 1 && (rank < 3 || rank > 13)) return state

  let next: ShalasState = {
    ...state,
    effectiveRank: rank,
    aceOnTop: rank === 1,
    phase: 'playing',
    message: `Wildcard set to ${rankName(rank)}`,
  }
  next = checkEndOfTurn(next)
  return next
}

/** Complete the 7 selector — pick a table card to move to discard. */
export function chooseSelectorTarget(state: ShalasState, source: PlaySource): ShalasState {
  if (state.phase !== 'choose_selector') return state

  let card: Card | null = null
  let next = { ...state }

  if (source.type === 'hand') {
    // Can pick from own hand too
    card = state.hand[source.index]
    if (card) next.hand = state.hand.filter((_, i) => i !== source.index)
  } else if (source.type === 'secondRow') {
    card = state.secondRow[source.index]
    if (card) next.secondRow = state.secondRow.filter((_, i) => i !== source.index)
  } else if (source.type === 'stackRow') {
    const stack = state.stackRow[source.stackIndex]
    if (stack.length > 0) {
      card = stack[stack.length - 1]
      next.stackRow = state.stackRow.map((s, i) =>
        i === source.stackIndex ? s.slice(0, -1) : s
      )
    }
  } else if (source.type === 'pairRow') {
    const pair = state.pairRow[source.stackIndex]
    if (source.card === 'faceUp' && pair.faceUp) {
      card = pair.faceUp
      next.pairRow = state.pairRow.map((p, i) =>
        i === source.stackIndex ? { ...p, faceUp: null } : p
      )
    } else if (source.card === 'faceDown' && pair.faceDown) {
      card = pair.faceDown
      next.pairRow = state.pairRow.map((p, i) =>
        i === source.stackIndex ? { ...p, faceDown: null } : p
      )
    }
  }

  if (!card) return { ...state, message: 'No card there — pick another' }

  const playedCard = { ...card, faceUp: true }

  // If the selected card is a 10 and discard has cards, auto-trigger Destroyer
  if (playedCard.rank === 10 && next.discardPile.length > 0) {
    next.burned = [...state.burned, playedCard, ...next.discardPile]
    next.discardPile = []
    next.effectiveRank = 0
    next.aceOnTop = false
    next.phase = 'playing'
    next.message = 'Selector picked a 10 — Destroyer! Discard pile cleared'
    next = checkEndOfTurn(next)
    return next
  }

  next.discardPile = [...next.discardPile, playedCard]
  next.effectiveRank = playedCard.rank
  next.aceOnTop = playedCard.rank === 1
  next.phase = 'playing'
  next.message = `Selector moved ${rankName(playedCard.rank)} to discard`

  // 2-player: opponent takes 10 cards from discard → enter block_chance
  if (state.playerCount === 2) {
    next.phase = 'block_chance'
    next.message = 'Opponent can play a 3 to block the penalty...'
    return next
  }

  next = checkEndOfTurn(next)
  return next
}

/** Opponent blocks the 7 penalty with a 3. */
export function blockWithThree(state: ShalasState): ShalasState {
  if (state.phase !== 'block_chance') return state

  // Find a 3 in opponent's hand
  const threeIndex = state.opponentHand.findIndex(c => c.rank === 3)
  if (threeIndex === -1) return { ...state, message: 'No 3 to block with' }

  const opponentHand = state.opponentHand.filter((_, i) => i !== threeIndex)
  const discardPile = [...state.discardPile, { ...state.opponentHand[threeIndex], faceUp: true }]

  let next: ShalasState = {
    ...state,
    opponentHand,
    discardPile,
    phase: 'playing',
    message: 'Blocked! Opponent played a 3',
  }
  next = checkEndOfTurn(next)
  return next
}

/** Opponent doesn't block — takes the penalty cards. */
export function acceptSelectorPenalty(state: ShalasState): ShalasState {
  if (state.phase !== 'block_chance') return state

  const cardsToTake = state.discardPile.slice(-SELECTOR_PENALTY_COUNT)
  const discardPile = state.discardPile.slice(0, -SELECTOR_PENALTY_COUNT)
  const opponentHand = [
    ...state.opponentHand,
    ...cardsToTake.map(c => ({ ...c, faceUp: true })),
  ]

  const newTopRank = discardPile.length > 0
    ? discardPile[discardPile.length - 1].rank
    : 0
  let next: ShalasState = {
    ...state,
    opponentHand,
    discardPile,
    effectiveRank: newTopRank,
    aceOnTop: newTopRank === 1,
    phase: 'playing',
    message: `Opponent takes ${cardsToTake.length} cards`,
  }
  next = checkEndOfTurn(next)
  return next
}

/** Handle "can't play" scenario. */
export function cantPlay(state: ShalasState): ShalasState {
  if (state.phase !== 'playing') return state

  if (state.playerCount === 1) {
    // 1-player: shuffle discard pile, give player 10 cards
    const shuffled = shuffleDeck(state.discardPile)
    const cardsToTake = shuffled.slice(0, 10).map(c => ({ ...c, faceUp: true }))
    const remaining = shuffled.slice(10)

    const newTopRank = remaining.length > 0 ? remaining[remaining.length - 1].rank : 0
    return {
      ...state,
      hand: [...state.hand, ...cardsToTake],
      discardPile: remaining,
      effectiveRank: newTopRank,
      aceOnTop: newTopRank === 1,
      message: `No valid play — took ${cardsToTake.length} cards from shuffled discard`,
    }
  }

  // 2-player: skip turn
  return {
    ...state,
    currentPlayer: state.currentPlayer === 0 ? 1 : 0,
    aceOnTop: state.aceOnTop,
    message: 'No valid play — turn skipped',
  }
}

// ── Internal helpers ─────────────────────────────────────────────────

/** Check win/loss and advance turn after a play. */
function checkEndOfTurn(state: ShalasState): ShalasState {
  if (checkWin(state)) {
    return { ...state, phase: 'won', message: 'You win! All cards cleared!' }
  }

  // In 2-player, switch turns
  if (state.playerCount === 2 && state.currentPlayer === 0) {
    return { ...state, currentPlayer: 1, message: "Opponent's turn" }
  }

  return state
}

/** Get display name for a rank. */
export function rankName(rank: number): string {
  if (rank === 1) return 'Ace'
  if (rank === 11) return 'Jack'
  if (rank === 12) return 'Queen'
  if (rank === 13) return 'King'
  return String(rank)
}
