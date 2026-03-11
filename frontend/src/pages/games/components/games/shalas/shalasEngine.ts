/**
 * Shalas — card game engine.
 *
 * Pure functions for game state management.
 * Layout: 6 rows on the table, dealt from a standard 52-card deck.
 *
 * Special cards:
 *   10 — Destroyer: removes itself + entire discard pile from game
 *    2 — Wildcard:  player picks reset value (A or 3+), 2 stays on discard
 *    7 — Selector:  pick any table card → discard
 *                   2-player: ALSO can push entire discard pile to opponent's hand
 *    3 — Blocker:   (2-player only) blocks the 7's discard pile push
 *    2 — also acts as 3 (blocker) or 7 (pusher) in 2-player
 *    4-of-a-kind — Wild Set: resets discard; also acts as 3 or 7 in 2-player
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
  | 'playing'          // normal turn
  | 'choose_wild'      // player must pick reset value for a 2 wildcard
  | 'choose_selector'  // player must pick a table card for a 7
  | 'choose_seven_action' // 2-player: player chooses pick-table vs push-discard after 7
  | 'block_chance'     // opponent can play a 3/2/4oak to block discard push (2-player)
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

  // Deal opponent hand for 2-player mode
  const opponentHand: Card[] = playerCount === 2
    ? drawStack.splice(-5).map(c => ({ ...c, faceUp: true }))
    : []

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
    opponentHand,
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
    // Check for any playable single card
    if (state.hand.some(c => canPlay(c, state))) return true
    // Check for a consecutive run starting at a playable rank
    const ranks = state.hand.map(c => c.rank).sort((a, b) => a - b)
    const uniqueRanks = [...new Set(ranks)]
    for (let i = 0; i < uniqueRanks.length; i++) {
      if (canPlay({ rank: uniqueRanks[i], suit: 'hearts', faceUp: true }, state)) {
        // Found a playable starting rank — valid
        return true
      }
    }
    return false
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

/** Check if card indices form a consecutive ascending run (e.g., 3,4,5 or 9,10,J,Q,K). */
export function isConsecutiveRun(hand: Card[], indices: number[]): boolean {
  if (indices.length < 2) return false
  const ranks = indices.map(i => hand[i].rank).sort((a, b) => a - b)
  for (let i = 1; i < ranks.length; i++) {
    if (ranks[i] !== ranks[i - 1] + 1) return false
  }
  return true
}

/** Play one or more cards from hand by indices.
 *  Supports same-rank groups AND consecutive runs (e.g., 4,5,6,7). */
export function playFromHand(state: ShalasState, cardIndices: number[]): ShalasState {
  if (state.phase !== 'playing') return state
  if (cardIndices.length === 0) return state

  // Validate all indices
  for (const idx of cardIndices) {
    if (idx < 0 || idx >= state.hand.length) return state
  }

  const allSameRank = cardIndices.every(i => state.hand[i].rank === state.hand[cardIndices[0]].rank)
  const isRun = !allSameRank && isConsecutiveRun(state.hand, cardIndices)

  if (!allSameRank && !isRun) {
    return { ...state, message: 'Select same-rank cards or a consecutive run' }
  }

  // ── Consecutive run play ──────────────────────────────────────────
  if (isRun) {
    // Sort by rank ascending — play lowest first
    const sorted = [...cardIndices].sort((a, b) => state.hand[a].rank - state.hand[b].rank)
    const lowestCard = state.hand[sorted[0]]
    const highestCard = state.hand[sorted[sorted.length - 1]]

    // The lowest card in the run must be playable
    if (!canPlay(lowestCard, state)) {
      const playedCards = sorted.map(i => ({ ...state.hand[i], faceUp: true }))
      const remainingHand = state.hand.filter((_, i) => !cardIndices.includes(i))
      const pickUp = [...state.discardPile, ...playedCards].map(c => ({ ...c, faceUp: true }))
      return {
        ...state,
        hand: [...remainingHand, ...pickUp],
        discardPile: [],
        effectiveRank: 0,
        aceOnTop: false,
        message: `Can't play run starting at ${rankName(lowestCard.rank)} — picked up the discard pile`,
      }
    }

    // Play all cards in the run onto discard — no special effects trigger in runs
    const playedCards = sorted.map(i => ({ ...state.hand[i], faceUp: true }))
    const hand = state.hand.filter((_, i) => !cardIndices.includes(i))
    const discardPile = [...state.discardPile, ...playedCards]
    const isAce = highestCard.rank === 1

    let next: ShalasState = {
      ...state,
      hand,
      discardPile,
      effectiveRank: highestCard.rank,
      aceOnTop: isAce,
      message: `Run! Played ${rankName(lowestCard.rank)}–${rankName(highestCard.rank)}`,
    }
    next = refillHand(next)
    next = checkEndOfTurn(next)
    return next
  }

  // ── Same-rank play (existing logic) ───────────────────────────────
  const rank = state.hand[cardIndices[0]].rank

  // 4-of-a-kind from hand: wild set — player chooses the new rank
  if (cardIndices.length >= 4) {
    const cards = cardIndices.slice(0, 4).map(i => ({ ...state.hand[i], faceUp: true }))
    const hand = state.hand.filter((_, i) => !cardIndices.slice(0, 4).includes(i))
    const discardPile = [...state.discardPile, ...cards]

    let next: ShalasState = {
      ...state,
      hand,
      discardPile,
      aceOnTop: false,
      phase: 'choose_wild',
      message: '4-of-a-kind Wild Set! Choose the reset value (A, or 3–K)',
    }
    next = refillHand(next)
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
      message: `Can't play ${rankName(rank)} — picked up the discard pile`,
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

/** Count how many consecutive cards of the given rank sit on top of the discard pile. */
function countMatchingOnTop(discardPile: Card[], rank: number): number {
  let count = 0
  for (let i = discardPile.length - 1; i >= 0; i--) {
    if (discardPile[i].rank === rank) count++
    else break
  }
  return count
}

/** Resolve a played card — handle special card effects.
 *  extraCards: additional same-rank cards played alongside the primary card. */
function resolvePlay(state: ShalasState, card: Card, extraCards: Card[] = []): ShalasState {
  const allPlayed = [card, ...extraCards]

  // ── Cross-discard 4-of-a-kind: cards being played + matching top of discard ─
  // If together they form 4+, it's a wild set — player chooses the new rank.
  // Does NOT apply to special cards (2, 7, 10) — their abilities take priority.
  if (card.rank !== 2 && card.rank !== 7 && card.rank !== 10) {
    const topMatching = countMatchingOnTop(state.discardPile, card.rank)
    if (topMatching + allPlayed.length >= 4) {
      const discardPile = [...state.discardPile, ...allPlayed]
      let next: ShalasState = {
        ...state,
        discardPile,
        aceOnTop: false,
        phase: 'choose_wild',
        message: `4-of-a-kind ${rankName(card.rank)}s! Choose the reset value (A, or 3–K)`,
      }
      next = refillHand(next)
      return next
    }
  }

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

  // ── 7: Selector — in 2-player, choose between table pick or discard push
  if (card.rank === 7) {
    const discardPile = [...state.discardPile, ...allPlayed]
    let next: ShalasState = {
      ...state,
      discardPile,
      effectiveRank: 7,
      aceOnTop: false,
      phase: state.playerCount === 2 ? 'choose_seven_action' : 'choose_selector',
      message: state.playerCount === 2
        ? 'Selector! Pick a table card OR push the discard pile to your opponent'
        : 'Selector! Pick any card from the table to discard',
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

/** Complete the wildcard choice — set effective rank.
 *  If the chosen rank is 7 (Selector) or 10 (Destroyer), the 2 also
 *  triggers that card's special ability. */
export function chooseWildValue(state: ShalasState, rank: number): ShalasState {
  if (state.phase !== 'choose_wild') return state
  // Valid choices: 1 (Ace) or 3–13
  if (rank !== 1 && (rank < 3 || rank > 13)) return state

  // Wildcard mimics the 10 Destroyer
  if (rank === 10 && state.discardPile.length > 0) {
    let next: ShalasState = {
      ...state,
      burned: [...state.burned, ...state.discardPile],
      discardPile: [],
      effectiveRank: 0,
      aceOnTop: false,
      phase: 'playing',
      message: 'Wildcard → Destroyer! Discard pile cleared',
    }
    next = checkEndOfTurn(next)
    return next
  }

  // Wildcard mimics the 7 Selector
  if (rank === 7) {
    return {
      ...state,
      effectiveRank: 7,
      aceOnTop: false,
      phase: state.playerCount === 2 ? 'choose_seven_action' : 'choose_selector',
      message: state.playerCount === 2
        ? 'Wildcard → Selector! Pick a table card OR push the discard pile'
        : 'Wildcard → Selector! Pick any card from the table to discard',
    }
  }

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

  next = checkEndOfTurn(next)
  return next
}

/** Handle the 7's choice in 2-player: pick a table card or push the discard pile. */
export function chooseSevenAction(state: ShalasState, action: 'pick_table' | 'push_discard'): ShalasState {
  if (state.phase !== 'choose_seven_action') return state

  if (action === 'pick_table') {
    return {
      ...state,
      phase: 'choose_selector',
      message: 'Pick any card from the table to discard',
    }
  }

  // Push discard pile to opponent — switch turn to defender for blocking
  const defender = state.currentPlayer === 0 ? 1 : 0
  return {
    ...state,
    currentPlayer: defender,
    phase: 'block_chance',
    message: 'Discard pile push! Play a 3 to block, or accept',
  }
}

/** Block the discard pile push with a 3, 2 (wildcard), or 4-of-a-kind.
 *  Called by the defender during block_chance phase.
 *  cardIndices: indices in the defender's hand (state.hand after applyAsPlayer). */
export function blockPush(state: ShalasState, cardIndices: number[]): ShalasState {
  if (state.phase !== 'block_chance') return state
  if (cardIndices.length === 0) return state

  if (cardIndices.length === 1) {
    const card = state.hand[cardIndices[0]]
    if (!card || (card.rank !== 3 && card.rank !== 2)) {
      return { ...state, message: 'Only a 3 or 2 can block' }
    }
  } else if (cardIndices.length >= 4) {
    const rank = state.hand[cardIndices[0]]?.rank
    if (!rank || !cardIndices.slice(0, 4).every(i => state.hand[i]?.rank === rank)) {
      return { ...state, message: 'Must be 4-of-a-kind to block' }
    }
  } else {
    return { ...state, message: 'Play a 3, 2, or 4-of-a-kind to block' }
  }

  const usedIndices = cardIndices.length >= 4 ? cardIndices.slice(0, 4) : cardIndices
  const blockerCards = usedIndices.map(i => ({ ...state.hand[i], faceUp: true }))
  const hand = state.hand.filter((_, i) => !usedIndices.includes(i))
  const discardPile = [...state.discardPile, ...blockerCards]
  const topRank = blockerCards[blockerCards.length - 1].rank

  // Defender keeps the turn after blocking (attacker already used their turn)
  return {
    ...state,
    hand,
    discardPile,
    effectiveRank: topRank,
    aceOnTop: topRank === 1,
    phase: 'playing',
    message: blockerCards.length >= 4
      ? 'Blocked with 4-of-a-kind!'
      : `Blocked with a ${rankName(blockerCards[0].rank)}!`,
  }
}

/** Defender accepts the discard pile push — entire pile goes to their hand.
 *  Called by the defender during block_chance phase. */
export function acceptPush(state: ShalasState): ShalasState {
  if (state.phase !== 'block_chance') return state

  const pileSize = state.discardPile.length
  const hand = [
    ...state.hand,
    ...state.discardPile.map(c => ({ ...c, faceUp: true })),
  ]

  // Defender keeps the turn after accepting (attacker already used their turn)
  return {
    ...state,
    hand,
    discardPile: [],
    effectiveRank: 0,
    aceOnTop: false,
    phase: 'playing',
    message: `Took ${pileSize} cards from the discard pile`,
  }
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

  // In 2-player, switch turns (both directions)
  if (state.playerCount === 2) {
    const next = state.currentPlayer === 0 ? 1 : 0
    return { ...state, currentPlayer: next }
  }

  return state
}

// ── Multiplayer helpers ──────────────────────────────────────────────

/** Swap hand/opponentHand — used so engine functions (which operate on `hand`)
 *  can be used for player 1 by swapping before and after. */
function swapPerspective(state: ShalasState): ShalasState {
  return { ...state, hand: state.opponentHand, opponentHand: state.hand }
}

/** Apply an engine action from the perspective of a given player.
 *  Player 0 uses state directly; player 1 swaps hand/opponentHand first. */
export function applyAsPlayer(
  state: ShalasState,
  playerIndex: number,
  action: (s: ShalasState) => ShalasState,
): ShalasState {
  if (playerIndex === 0) return action(state)
  const swapped = swapPerspective(state)
  const result = action(swapped)
  return swapPerspective(result)
}

/** Get display name for a rank. */
export function rankName(rank: number): string {
  if (rank === 1) return 'Ace'
  if (rank === 11) return 'Jack'
  if (rank === 12) return 'Queen'
  if (rank === 13) return 'King'
  return String(rank)
}
