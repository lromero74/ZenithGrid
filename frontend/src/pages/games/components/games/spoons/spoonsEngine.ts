/**
 * Spoons card game engine — pure logic, no side effects.
 *
 * Rules:
 * - 3 players (1 human + 2 AI), 2 spoons in center
 * - Each player gets 4 cards
 * - Players pass cards around the circle trying to collect 4 of a kind
 * - Dealer draws from draw pile; others pick up the card passed from right
 * - Each player holds 5 cards, discards 1 (passed left)
 * - When someone gets 4 of a kind, they grab a spoon — everyone races!
 * - Player without a spoon gets a letter from S-P-O-O-N-S
 * - 6 letters = eliminated. Last player standing wins.
 *
 * Two modes:
 *   turn-based — sequential draw/discard, classic digital adaptation
 *   real-time  — all players act simultaneously with human-modeled AI timing
 *
 * Three AI difficulties (affect reaction times across all cognitive stages):
 *   easy   — 50th percentile human reactions (slower, more hesitant)
 *   normal — 70th percentile (competent, occasionally fast)
 *   adept  — 90th percentile (quick perception and decisive, but still human)
 */

import { createDeck, shuffleDeck, type Card } from '../../../utils/cardUtils'

// ── Types ───────────────────────────────────────────────────────────

export type Phase =
  | 'drawing'      // Current player draws/picks up a card (now has 5)
  | 'discarding'   // Current player chooses a card to discard (pass left)
  | 'spoonGrab'    // Someone got 4 of a kind — race to grab spoons!
  | 'roundOver'    // Round result shown
  | 'gameOver'     // Only 1 player left

export type GameMode = 'turn-based' | 'real-time'
export type AiDifficulty = 'easy' | 'normal' | 'adept'

export interface PlayerInfo {
  hand: Card[]
  letters: string         // accumulated: '', 'S', 'SP', 'SPO', etc.
  eliminated: boolean
  isHuman: boolean
  name: string
  grabbedSpoon: boolean
  /** Spoon grab delay in ms (set per-round based on difficulty). 0 for human. */
  spoonGrabDelay: number
  /** Card evaluation delay in ms (real-time mode). 0 for human. */
  cardEvalDelay: number
}

export interface SpoonsState {
  players: PlayerInfo[]
  drawPile: Card[]
  discardPile: Card[]
  passedCard: Card | null   // card waiting to be picked up by current player
  currentPlayer: number     // index of active player
  dealer: number
  spoonsRemaining: number
  phase: Phase
  message: string
  spoonGrabber: number | null   // who triggered the grab
  roundLoser: number | null
  roundNumber: number
  mode: GameMode
  difficulty: AiDifficulty
}

// ── Constants ───────────────────────────────────────────────────────

const SPOONS_WORD = 'SPOONS'
const PLAYER_COUNT = 3

// ── Human-modeled reaction time system ──────────────────────────────
//
// Each AI action is broken into 4 cognitive stages:
//   1. Perception  — noticing the stimulus (card appeared, spoon grab triggered)
//   2. Understanding — processing what it means (is this card useful? do I need to grab?)
//   3. Deciding    — choosing an action (which card to discard, whether to grab)
//   4. Acting      — motor execution (reaching, tapping)
//
// Each stage has a range in ms. Difficulty shifts where in the range the AI lands.
// No AI is faster than 90th percentile humans. No AI is slower than 50th percentile.

interface ReactionRange {
  min: number  // 90th percentile (fastest allowed)
  max: number  // 50th percentile (slowest allowed)
}

interface CognitiveProfile {
  perception: ReactionRange
  understanding: ReactionRange
  deciding: ReactionRange
  acting: ReactionRange
}

/** Cognitive stage ranges for spoon grabbing (simpler task — react and grab). */
const SPOON_GRAB_PROFILE: CognitiveProfile = {
  perception:    { min: 80,  max: 200 },   // noticing someone grabbed / you have 4-of-a-kind
  understanding: { min: 50,  max: 150 },   // processing "I need to grab NOW"
  deciding:      { min: 30,  max: 100 },   // committing to the action
  acting:        { min: 100, max: 250 },   // motor execution (reaching for spoon)
}

/** Cognitive stage ranges for card evaluation (complex — pick up, evaluate hand, choose discard). */
const CARD_EVAL_PROFILE: CognitiveProfile = {
  perception:    { min: 100, max: 250 },   // noticing a card is available
  understanding: { min: 200, max: 600 },   // evaluating hand + new card
  deciding:      { min: 150, max: 400 },   // choosing which card to discard
  acting:        { min: 80,  max: 200 },   // executing the discard
}

/**
 * Generate a total reaction time from a cognitive profile.
 *
 * @param profile  The 4-stage cognitive model
 * @param bias     0.0 = always pick max (50th pctile), 1.0 = always pick min (90th pctile)
 *                 Difficulty maps: easy=0.0-0.3, normal=0.3-0.6, adept=0.6-1.0
 */
function generateReactionTime(profile: CognitiveProfile, bias: number): number {
  let total = 0
  for (const stage of [profile.perception, profile.understanding, profile.deciding, profile.acting]) {
    const range = stage.max - stage.min
    // Bias shifts the center point; randomness adds human-like variance
    const center = stage.max - (range * bias)
    // ±30% variance around the center, clamped to [min, max]
    const variance = range * 0.3 * (Math.random() * 2 - 1)
    const value = Math.max(stage.min, Math.min(stage.max, center + variance))
    total += value
  }
  return Math.round(total)
}

/** Map difficulty to a bias range, then pick a random bias within that range. */
function difficultyBias(difficulty: AiDifficulty): number {
  switch (difficulty) {
    case 'easy':   return 0.0 + Math.random() * 0.3   // 0.0–0.3 (lean slow)
    case 'normal': return 0.3 + Math.random() * 0.3   // 0.3–0.6 (middle)
    case 'adept':  return 0.6 + Math.random() * 0.4   // 0.6–1.0 (lean fast)
  }
}

/** Generate spoon grab delay for an AI player. */
export function generateSpoonGrabDelay(difficulty: AiDifficulty): number {
  return generateReactionTime(SPOON_GRAB_PROFILE, difficultyBias(difficulty))
}

/** Generate card evaluation delay for an AI player. */
export function generateCardEvalDelay(difficulty: AiDifficulty): number {
  return generateReactionTime(CARD_EVAL_PROFILE, difficultyBias(difficulty))
}

// ── Helpers ─────────────────────────────────────────────────────────

/** Check if a hand contains 4 cards of the same rank. */
export function hasFourOfAKind(hand: Card[]): boolean {
  const counts = new Map<number, number>()
  for (const card of hand) {
    counts.set(card.rank, (counts.get(card.rank) ?? 0) + 1)
    if (counts.get(card.rank)! >= 4) return true
  }
  return false
}

/** Get active (non-eliminated) player count. */
export function getActiveCount(players: PlayerInfo[]): number {
  return players.filter(p => !p.eliminated).length
}

/** Get next active player index (skipping eliminated). */
export function getNextActive(players: PlayerInfo[], from: number): number {
  let idx = (from + 1) % players.length
  while (players[idx].eliminated) {
    idx = (idx + 1) % players.length
  }
  return idx
}

/** Get previous active player index (the player passing to current). */
export function getPrevActive(players: PlayerInfo[], from: number): number {
  let idx = (from - 1 + players.length) % players.length
  while (players[idx].eliminated) {
    idx = (idx - 1 + players.length) % players.length
  }
  return idx
}

/** Check if the current player is the dealer (draws from pile instead of passed card). */
function isDealer(state: SpoonsState): boolean {
  return state.currentPlayer === state.dealer
}

/** Get the last active player in the circle (the one who discards to the discard pile). */
function getLastActivePlayer(players: PlayerInfo[], dealer: number): number {
  return getPrevActive(players, dealer)
}

// ── Engine functions ────────────────────────────────────────────────

/** Create a new Spoons game with the given mode and difficulty. */
export function createSpoonsGame(
  mode: GameMode = 'turn-based',
  difficulty: AiDifficulty = 'normal'
): SpoonsState {
  const deck = shuffleDeck(createDeck())

  const players: PlayerInfo[] = []
  let cardIdx = 0
  for (let i = 0; i < PLAYER_COUNT; i++) {
    const hand = deck.slice(cardIdx, cardIdx + 4).map(c => ({ ...c, faceUp: true }))
    cardIdx += 4
    const isHuman = i === 0
    players.push({
      hand,
      letters: '',
      eliminated: false,
      isHuman,
      name: isHuman ? 'You' : `Bot ${i}`,
      grabbedSpoon: false,
      spoonGrabDelay: isHuman ? 0 : generateSpoonGrabDelay(difficulty),
      cardEvalDelay: isHuman ? 0 : generateCardEvalDelay(difficulty),
    })
  }

  const drawPile = deck.slice(cardIdx)

  return {
    players,
    drawPile,
    discardPile: [],
    passedCard: null,
    currentPlayer: 0,
    dealer: 0,
    spoonsRemaining: PLAYER_COUNT - 1,
    phase: 'drawing',
    message: 'Draw a card!',
    spoonGrabber: null,
    roundLoser: null,
    roundNumber: 1,
    mode,
    difficulty,
  }
}

/** Current player draws a card (from draw pile if dealer, from passed card otherwise). */
export function drawCard(state: SpoonsState): SpoonsState {
  if (state.phase !== 'drawing') return state

  const players = state.players.map(p => ({ ...p, hand: [...p.hand] }))
  const drawPile = [...state.drawPile]
  let card: Card | null = null

  if (isDealer(state)) {
    // Dealer draws from draw pile
    if (drawPile.length === 0) {
      // Reshuffle discard pile as new draw pile
      const reshuffled = shuffleDeck([...state.discardPile])
      drawPile.push(...reshuffled)
    }
    if (drawPile.length > 0) {
      card = { ...drawPile.shift()!, faceUp: true }
    }
  } else {
    // Pick up the passed card
    card = state.passedCard
  }

  if (!card) return state

  players[state.currentPlayer].hand.push(card)

  const playerName = players[state.currentPlayer].name
  return {
    ...state,
    players,
    drawPile,
    passedCard: null,
    discardPile: isDealer(state) ? state.discardPile : [...state.discardPile],
    phase: 'discarding',
    message: players[state.currentPlayer].isHuman
      ? 'Choose a card to discard'
      : `${playerName} is choosing...`,
  }
}

/** Current player discards a card (index in their 5-card hand). */
export function discardCard(state: SpoonsState, cardIndex: number): SpoonsState {
  if (state.phase !== 'discarding') return state
  const player = state.players[state.currentPlayer]
  if (cardIndex < 0 || cardIndex >= player.hand.length) return state

  const players = state.players.map(p => ({ ...p, hand: [...p.hand] }))
  const discarded = players[state.currentPlayer].hand.splice(cardIndex, 1)[0]

  // Check if this player now has 4 of a kind
  if (hasFourOfAKind(players[state.currentPlayer].hand)) {
    return {
      ...state,
      players,
      passedCard: null,
      discardPile: [...state.discardPile, discarded],
      phase: 'spoonGrab',
      message: `${players[state.currentPlayer].name} got 4 of a kind! Grab a spoon!`,
      spoonGrabber: state.currentPlayer,
    }
  }

  // Determine where the discarded card goes
  const lastPlayer = getLastActivePlayer(state.players, state.dealer)
  const nextPlayer = getNextActive(state.players, state.currentPlayer)

  if (state.currentPlayer === lastPlayer) {
    // Last player's discard goes to the discard pile
    return {
      ...state,
      players,
      passedCard: null,
      discardPile: [...state.discardPile, discarded],
      currentPlayer: state.dealer,
      phase: 'drawing',
      message: players[state.dealer].isHuman
        ? 'Draw a card!'
        : `${players[state.dealer].name}'s turn...`,
    }
  } else {
    // Pass card to next player
    return {
      ...state,
      players,
      passedCard: { ...discarded, faceUp: true },
      discardPile: [...state.discardPile],
      currentPlayer: nextPlayer,
      phase: 'drawing',
      message: players[nextPlayer].isHuman
        ? 'Pick up the passed card!'
        : `${players[nextPlayer].name}'s turn...`,
    }
  }
}

/** A player grabs a spoon. */
export function grabSpoon(state: SpoonsState, playerIndex: number): SpoonsState {
  if (state.phase !== 'spoonGrab') return state
  if (state.players[playerIndex].eliminated) return state
  if (state.players[playerIndex].grabbedSpoon) return state
  if (state.spoonsRemaining <= 0) return state

  const players = state.players.map(p => ({ ...p, hand: [...p.hand] }))
  players[playerIndex].grabbedSpoon = true
  const remaining = state.spoonsRemaining - 1

  // Check if all spoons grabbed (someone lost)
  if (remaining === 0) {
    // Find the loser (active player who didn't grab)
    const loserIdx = players.findIndex(p => !p.eliminated && !p.grabbedSpoon)
    if (loserIdx === -1) return { ...state, players, spoonsRemaining: remaining }

    // Assign a letter
    const nextLetterIdx = players[loserIdx].letters.length
    const nextLetter = SPOONS_WORD[nextLetterIdx] ?? ''
    players[loserIdx].letters += nextLetter

    // Check elimination
    if (players[loserIdx].letters.length >= SPOONS_WORD.length) {
      players[loserIdx].eliminated = true
    }

    // Check game over (only 1 player left)
    const activeCount = getActiveCount(players)
    if (activeCount <= 1) {
      const winner = players.find(p => !p.eliminated)
      return {
        ...state,
        players,
        spoonsRemaining: remaining,
        phase: 'gameOver',
        message: winner ? `${winner.name} win${winner.isHuman ? '' : 's'}!` : 'Game Over!',
        roundLoser: loserIdx,
      }
    }

    return {
      ...state,
      players,
      spoonsRemaining: remaining,
      phase: 'roundOver',
      message: `${players[loserIdx].name} ${players[loserIdx].eliminated ? 'spelled SPOONS and is out!' : `got the letter "${nextLetter}"`}`,
      roundLoser: loserIdx,
    }
  }

  return {
    ...state,
    players,
    spoonsRemaining: remaining,
    message: `${players[playerIndex].name} grabbed a spoon!`,
  }
}

/** Start a new round after round over. Regenerates AI reaction times. */
export function newRound(state: SpoonsState): SpoonsState {
  if (state.phase !== 'roundOver') return state

  const deck = shuffleDeck(createDeck())
  const activePlayers = state.players.filter(p => !p.eliminated)
  const activeCount = activePlayers.length

  const players = state.players.map(p => ({
    ...p,
    hand: [] as Card[],
    grabbedSpoon: false,
    // Regenerate AI reaction times each round for natural variance
    spoonGrabDelay: p.isHuman ? 0 : generateSpoonGrabDelay(state.difficulty),
    cardEvalDelay: p.isHuman ? 0 : generateCardEvalDelay(state.difficulty),
  }))

  // Deal 4 cards to each active player
  let cardIdx = 0
  for (const player of players) {
    if (!player.eliminated) {
      player.hand = deck.slice(cardIdx, cardIdx + 4).map(c => ({ ...c, faceUp: true }))
      cardIdx += 4
    }
  }

  // Rotate dealer to next active player
  const newDealer = getNextActive(players, state.dealer)

  return {
    ...state,
    players,
    drawPile: deck.slice(cardIdx),
    discardPile: [],
    passedCard: null,
    currentPlayer: newDealer,
    dealer: newDealer,
    spoonsRemaining: activeCount - 1,
    phase: 'drawing',
    message: players[newDealer].isHuman
      ? 'Draw a card!'
      : `${players[newDealer].name}'s turn...`,
    spoonGrabber: null,
    roundLoser: null,
    roundNumber: state.roundNumber + 1,
  }
}

/** AI decides which card to discard from a 5-card hand. Returns card index. */
export function aiDiscard(hand: Card[]): number {
  // Strategy: keep the rank that appears most often, discard the least useful
  const rankCounts = new Map<number, number>()
  for (const card of hand) {
    rankCounts.set(card.rank, (rankCounts.get(card.rank) ?? 0) + 1)
  }

  // Find the rank with the highest count (the set we're building toward)
  let bestRank = hand[0].rank
  let bestCount = 0
  for (const [rank, count] of rankCounts) {
    if (count > bestCount) {
      bestCount = count
      bestRank = rank
    }
  }

  // Discard a card that's NOT part of the best set
  // Prefer discarding the rank with the lowest count
  let discardIdx = 0
  let worstCount = Infinity
  for (let i = 0; i < hand.length; i++) {
    const count = rankCounts.get(hand[i].rank) ?? 0
    if (hand[i].rank !== bestRank && count < worstCount) {
      worstCount = count
      discardIdx = i
    }
  }

  // If all cards are the same rank (shouldn't happen with 5 cards, 4 suits), just discard last
  if (worstCount === Infinity) discardIdx = hand.length - 1

  return discardIdx
}

/** Get AI spoon grab delays for all active AI players. Uses per-player delays. */
export function getAiGrabDelays(state: SpoonsState): Array<{ playerIndex: number; delay: number }> {
  return state.players
    .map((p, i) => ({ playerIndex: i, delay: p.spoonGrabDelay }))
    .filter(({ playerIndex }) => {
      const p = state.players[playerIndex]
      return !p.eliminated && !p.isHuman && !p.grabbedSpoon
    })
    .sort((a, b) => a.delay - b.delay)
}

/** Get AI card evaluation delays for real-time mode. */
export function getAiCardEvalDelays(state: SpoonsState): Array<{ playerIndex: number; delay: number }> {
  return state.players
    .map((p, i) => ({ playerIndex: i, delay: p.cardEvalDelay }))
    .filter(({ playerIndex }) => {
      const p = state.players[playerIndex]
      return !p.eliminated && !p.isHuman
    })
    .sort((a, b) => a.delay - b.delay)
}

/** Check if it's the human player's turn to act. */
export function isHumanTurn(state: SpoonsState): boolean {
  if (state.phase === 'spoonGrab') return true // Human can always grab during grab phase
  return state.players[state.currentPlayer]?.isHuman ?? false
}
