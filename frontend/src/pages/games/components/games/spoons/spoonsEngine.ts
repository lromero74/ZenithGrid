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
 */

import { createDeck, shuffleDeck, type Card } from '../../../utils/cardUtils'

// ── Types ───────────────────────────────────────────────────────────

export type Phase =
  | 'drawing'      // Current player draws/picks up a card (now has 5)
  | 'discarding'   // Current player chooses a card to discard (pass left)
  | 'spoonGrab'    // Someone got 4 of a kind — race to grab spoons!
  | 'roundOver'    // Round result shown
  | 'gameOver'     // Only 1 player left

export interface PlayerInfo {
  hand: Card[]
  letters: string         // accumulated: '', 'S', 'SP', 'SPO', etc.
  eliminated: boolean
  isHuman: boolean
  name: string
  grabbedSpoon: boolean
  reactionTime: number    // AI spoon grab delay in ms (0 for human)
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
}

// ── Constants ───────────────────────────────────────────────────────

const SPOONS_WORD = 'SPOONS'
const PLAYER_COUNT = 3

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

/** Create a new Spoons game. */
export function createSpoonsGame(): SpoonsState {
  const deck = shuffleDeck(createDeck())

  const players: PlayerInfo[] = []
  let cardIdx = 0
  for (let i = 0; i < PLAYER_COUNT; i++) {
    const hand = deck.slice(cardIdx, cardIdx + 4).map(c => ({ ...c, faceUp: true }))
    cardIdx += 4
    players.push({
      hand,
      letters: '',
      eliminated: false,
      isHuman: i === 0,
      name: i === 0 ? 'You' : `Bot ${i}`,
      grabbedSpoon: false,
      reactionTime: i === 0 ? 0 : 300 + Math.floor(Math.random() * 900),
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

/** Start a new round after round over. */
export function newRound(state: SpoonsState): SpoonsState {
  if (state.phase !== 'roundOver') return state

  const deck = shuffleDeck(createDeck())
  const activePlayers = state.players.filter(p => !p.eliminated)
  const activeCount = activePlayers.length

  const players = state.players.map(p => ({
    ...p,
    hand: [] as Card[],
    grabbedSpoon: false,
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

/** Get AI spoon grab delays for all active AI players. */
export function getAiGrabDelays(state: SpoonsState): Array<{ playerIndex: number; delay: number }> {
  return state.players
    .map((p, i) => ({ playerIndex: i, delay: p.reactionTime }))
    .filter(({ playerIndex }) => {
      const p = state.players[playerIndex]
      return !p.eliminated && !p.isHuman && !p.grabbedSpoon
    })
    .sort((a, b) => a.delay - b.delay)
}

/** Check if it's the human player's turn to act. */
export function isHumanTurn(state: SpoonsState): boolean {
  if (state.phase === 'spoonGrab') return true // Human can always grab during grab phase
  return state.players[state.currentPlayer]?.isHuman ?? false
}
