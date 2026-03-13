/**
 * Euchre engine — pure logic, no React.
 *
 * 4 players: 2v2 partnership (You+North vs East+West).
 * 24-card deck (9-A). Trump selection via two rounds.
 * Bowers: Right bower (J of trump) = highest, Left bower (J of same color) = 2nd highest.
 */

import {
  createEuchreDeck as _createEuchreDeck,
  shuffleDeck,
  type Card,
  type Suit,
  SUITS,
} from '../../../utils/cardUtils'

// Re-export so tests can import from this module
export const createEuchreDeck = _createEuchreDeck

// ── Types ────────────────────────────────────────────────────────────

export type Phase =
  | 'trumpRound1'
  | 'trumpRound2'
  | 'goAlonePrompt'
  | 'dealerDiscard'
  | 'playing'
  | 'trickComplete'
  | 'handOver'
  | 'gameOver'

export interface Play {
  player: number
  card: Card
}

export interface EuchreState {
  hands: Card[][]
  kitty: Card[]
  flippedCard: Card
  trumpSuit: Suit | null
  makerTeam: number | null       // 0 = team You+North, 1 = team East+West
  phase: Phase
  currentPlayer: number
  dealer: number
  currentTrick: Play[]
  tricksTaken: number[]           // per player (4)
  teamScores: [number, number]
  goingAlone: number | null       // player going alone, or null
  message: string
  ledSuit: Suit | null
}

// ── Constants ────────────────────────────────────────────────────────

export const PLAYER_NAMES = ['You', 'East', 'North', 'West']
export const TEAM_NAMES = ['You & North', 'East & West']
export const WINNING_SCORE = 10

// Same-color suit mapping
const SAME_COLOR: Record<Suit, Suit> = {
  hearts: 'diamonds',
  diamonds: 'hearts',
  clubs: 'spades',
  spades: 'clubs',
}

// ── Suit / Bower helpers ─────────────────────────────────────────────

export function getSameColorSuit(suit: Suit): Suit {
  return SAME_COLOR[suit]
}

export function isRightBower(card: Card, trumpSuit: Suit): boolean {
  return !!trumpSuit && card.rank === 11 && card.suit === trumpSuit
}

export function isLeftBower(card: Card, trumpSuit: Suit): boolean {
  return !!trumpSuit && card.rank === 11 && card.suit === getSameColorSuit(trumpSuit)
}

/**
 * Returns the effective suit of a card when trump is known.
 * Left bower counts as the trump suit, not its printed suit.
 */
export function getEffectiveSuit(card: Card, trumpSuit: Suit): Suit {
  if (isLeftBower(card, trumpSuit)) return trumpSuit
  return card.suit
}

// ── Card strength ────────────────────────────────────────────────────

/** Rank value for ordering: Ace=14, K=13, Q=12, J=11, 10, 9 */
function rankValue(rank: number): number {
  return rank === 1 ? 14 : rank
}

/**
 * Card strength for trick comparison.
 * Right bower=160, Left bower=150, other trump=100+rank, led suit=50+rank, off-suit=0.
 */
export function getCardStrength(card: Card, trumpSuit: Suit, ledSuit: Suit | null): number {
  if (isRightBower(card, trumpSuit)) return 160
  if (isLeftBower(card, trumpSuit)) return 150

  const effectiveSuit = getEffectiveSuit(card, trumpSuit)
  if (effectiveSuit === trumpSuit) return 100 + rankValue(card.rank)
  if (ledSuit && effectiveSuit === ledSuit) return 50 + rankValue(card.rank)
  return 0
}

// ── Playable cards (follow suit) ─────────────────────────────────────

/**
 * Returns indices of cards that can be legally played.
 * Must follow led suit (using effective suit for bowers).
 * If void in led suit, all cards are playable.
 */
export function getPlayableCards(hand: Card[], ledSuit: Suit | null, trumpSuit: Suit): number[] {
  // Leading — any card
  if (!ledSuit) return hand.map((_, i) => i)

  // Check if player has any cards matching the led suit's effective suit
  const followIndices: number[] = []
  for (let i = 0; i < hand.length; i++) {
    if (getEffectiveSuit(hand[i], trumpSuit) === ledSuit) {
      followIndices.push(i)
    }
  }

  // Must follow if possible
  if (followIndices.length > 0) return followIndices
  // Void in led suit — all playable
  return hand.map((_, i) => i)
}

// ── Sorting ──────────────────────────────────────────────────────────

/**
 * Sort hand: trump last, grouped by suit, ascending rank within suit.
 */
export function sortEuchreHand(hand: Card[], trumpSuit: Suit | null): Card[] {
  const suitOrder: Suit[] = ['clubs', 'diamonds', 'hearts', 'spades']

  return [...hand].sort((a, b) => {
    const aEffective = trumpSuit ? getEffectiveSuit(a, trumpSuit) : a.suit
    const bEffective = trumpSuit ? getEffectiveSuit(b, trumpSuit) : b.suit
    const aIsTrump = trumpSuit && aEffective === trumpSuit
    const bIsTrump = trumpSuit && bEffective === trumpSuit

    // Trump goes last
    if (aIsTrump && !bIsTrump) return 1
    if (!aIsTrump && bIsTrump) return -1

    // Group by effective suit
    const si = suitOrder.indexOf(aEffective) - suitOrder.indexOf(bEffective)
    if (si !== 0) return si

    // Within same suit, sort by strength (ascending)
    if (trumpSuit) {
      const aStr = getCardStrength(a, trumpSuit, null)
      const bStr = getCardStrength(b, trumpSuit, null)
      return aStr - bStr
    }
    return rankValue(a.rank) - rankValue(b.rank)
  })
}

// ── Game creation ────────────────────────────────────────────────────

export function createEuchreGame(prevState?: Partial<EuchreState>): EuchreState {
  const deck = shuffleDeck(createEuchreDeck())
  const hands: Card[][] = [[], [], [], []]

  // Deal 5 cards each
  for (let i = 0; i < 20; i++) {
    hands[i % 4].push(deck[i])
  }

  // Remaining 4 cards = kitty; top card is flipped
  const kitty = deck.slice(20)
  const flippedCard = kitty[0]

  const dealer = prevState?.dealer !== undefined ? ((prevState.dealer + 1) % 4) : Math.floor(Math.random() * 4)
  const firstPlayer = (dealer + 1) % 4

  return {
    hands,
    kitty,
    flippedCard,
    trumpSuit: null,
    makerTeam: null,
    phase: 'trumpRound1',
    currentPlayer: firstPlayer,
    dealer,
    currentTrick: [],
    tricksTaken: [0, 0, 0, 0],
    teamScores: prevState?.teamScores ?? [0, 0],
    goingAlone: null,
    message: `${PLAYER_NAMES[firstPlayer]}'s turn to call trump`,
    ledSuit: null,
  }
}

// ── Team helper ──────────────────────────────────────────────────────

function teamOf(player: number): number {
  return player % 2 // 0,2 = team 0; 1,3 = team 1
}

// ── Trump selection round 1 ──────────────────────────────────────────

/**
 * Order up the flipped card as trump. Dealer picks up flipped card.
 * Returns new immutable state.
 */
export function orderUp(state: EuchreState): EuchreState {
  if (state.phase !== 'trumpRound1') return state

  const trumpSuit = state.flippedCard.suit
  const caller = state.currentPlayer
  const makerTeam = teamOf(caller)

  // Dealer picks up the flipped card
  const newHands = state.hands.map(h => [...h])
  newHands[state.dealer] = [...newHands[state.dealer], { ...state.flippedCard }]

  return {
    ...state,
    hands: newHands,
    trumpSuit,
    makerTeam,
    phase: 'goAlonePrompt',
    currentPlayer: caller,
    message: `${PLAYER_NAMES[caller]} ordered up ${trumpSuit}. Go alone?`,
  }
}

/**
 * Pass on trump selection. Advances to next player.
 * After all 4 pass in round 1 -> trumpRound2.
 * In round 2, dealer is stuck (cannot pass — engine keeps them on trumpRound2).
 */
export function pass(state: EuchreState): EuchreState {
  if (state.phase !== 'trumpRound1' && state.phase !== 'trumpRound2') return state

  const nextPlayer = (state.currentPlayer + 1) % 4
  const leftOfDealer = (state.dealer + 1) % 4

  if (state.phase === 'trumpRound1') {
    // If we've gone all the way around (next player would be left of dealer again)
    if (nextPlayer === leftOfDealer) {
      return {
        ...state,
        phase: 'trumpRound2',
        currentPlayer: leftOfDealer,
        message: `All passed. ${PLAYER_NAMES[leftOfDealer]} must name a suit (not ${state.flippedCard.suit}).`,
      }
    }
    return {
      ...state,
      currentPlayer: nextPlayer,
      message: `${PLAYER_NAMES[state.currentPlayer]} passed. ${PLAYER_NAMES[nextPlayer]}'s turn.`,
    }
  }

  // trumpRound2 — dealer is stuck, cannot pass
  if (state.currentPlayer === state.dealer) {
    // Dealer is stuck — auto-pick a suit (first available that isn't flipped)
    const available = SUITS.filter(s => s !== state.flippedCard.suit)
    const chosen = aiPickTrumpSuit(state.hands[state.dealer], state.flippedCard.suit)
      ?? available[0]

    return {
      ...state,
      trumpSuit: chosen,
      makerTeam: teamOf(state.dealer),
      phase: 'goAlonePrompt',
      currentPlayer: state.dealer,
      message: `${PLAYER_NAMES[state.dealer]} was stuck and named ${chosen} as trump. Go alone?`,
    }
  }

  return {
    ...state,
    currentPlayer: nextPlayer,
    message: `${PLAYER_NAMES[state.currentPlayer]} passed. ${PLAYER_NAMES[nextPlayer]}'s turn.`,
  }
}

// ── Trump selection round 2 ──────────────────────────────────────────

/**
 * Name a trump suit in round 2. Cannot name the flipped card's suit.
 */
export function nameTrump(state: EuchreState, suit: Suit): EuchreState {
  if (state.phase !== 'trumpRound2') return state
  if (suit === state.flippedCard.suit) return state // rejected

  const caller = state.currentPlayer

  return {
    ...state,
    trumpSuit: suit,
    makerTeam: teamOf(caller),
    phase: 'goAlonePrompt',
    currentPlayer: caller,
    message: `${PLAYER_NAMES[caller]} named ${suit} as trump. Go alone?`,
  }
}

// ── Dealer discard ───────────────────────────────────────────────────

/**
 * Dealer discards one card (index) after picking up the flipped card.
 * Transitions to playing phase.
 */
export function dealerDiscard(state: EuchreState, cardIndex: number): EuchreState {
  if (state.phase !== 'dealerDiscard') return state
  if (state.currentPlayer !== state.dealer) return state

  const dealerHand = [...state.hands[state.dealer]]
  if (cardIndex < 0 || cardIndex >= dealerHand.length) return state

  dealerHand.splice(cardIndex, 1)

  const newHands = state.hands.map(h => [...h])
  newHands[state.dealer] = dealerHand

  // Sort all hands now that trump is known
  for (let p = 0; p < 4; p++) {
    newHands[p] = sortEuchreHand(newHands[p], state.trumpSuit)
  }

  // Find first player to lead (left of dealer, skipping partner if going alone)
  let leader = (state.dealer + 1) % 4
  if (state.goingAlone !== null && partnerOf(state.goingAlone) === leader) {
    leader = (leader + 1) % 4
  }

  return {
    ...state,
    hands: newHands,
    phase: 'playing',
    currentPlayer: leader,
    message: `${PLAYER_NAMES[leader]} leads.`,
    ledSuit: null,
    currentTrick: [],
  }
}

// ── Going alone decision ─────────────────────────────────────────────

/**
 * After trump is called, the caller decides whether to go alone.
 * If going alone, their partner sits out the hand.
 * Transitions to dealerDiscard (if round 1) or playing (if round 2).
 */
export function setGoingAlone(state: EuchreState, alone: boolean): EuchreState {
  if (state.phase !== 'goAlonePrompt') return state

  const caller = state.currentPlayer
  const goingAlone = alone ? caller : null

  // Determine if we came from round 1 (dealer needs to discard) or round 2
  // If dealer has 6 cards, we came from round 1 (orderUp added a card)
  const dealerNeedsDiscard = state.hands[state.dealer].length === 6
  const leftOfDealer = (state.dealer + 1) % 4

  if (dealerNeedsDiscard) {
    return {
      ...state,
      goingAlone,
      phase: 'dealerDiscard',
      currentPlayer: state.dealer,
      message: alone
        ? `${PLAYER_NAMES[caller]} is going alone! ${PLAYER_NAMES[state.dealer]} must discard.`
        : `${PLAYER_NAMES[state.dealer]} must discard.`,
    }
  }

  // Round 2 — go straight to playing
  // Sort all hands now that trump is known
  const newHands = state.hands.map(h => [...h])
  for (let p = 0; p < 4; p++) {
    newHands[p] = sortEuchreHand(newHands[p], state.trumpSuit)
  }

  // Find first player to lead (left of dealer, skipping partner if going alone)
  let leader = leftOfDealer
  if (goingAlone !== null && partnerOf(goingAlone) === leader) {
    leader = (leader + 1) % 4
  }

  return {
    ...state,
    hands: newHands,
    goingAlone,
    phase: 'playing',
    currentPlayer: leader,
    message: alone
      ? `${PLAYER_NAMES[caller]} is going alone! ${PLAYER_NAMES[leader]} leads.`
      : `${PLAYER_NAMES[leader]} leads.`,
    ledSuit: null,
    currentTrick: [],
  }
}

/**
 * Returns the partner of a given player.
 */
export function partnerOf(player: number): number {
  return (player + 2) % 4
}

/**
 * AI decides whether to go alone. Goes alone with both bowers + at least one other trump.
 */
export function aiShouldGoAlone(hand: Card[], trumpSuit: Suit): boolean {
  const hasRight = hand.some(c => isRightBower(c, trumpSuit))
  const hasLeft = hand.some(c => isLeftBower(c, trumpSuit))
  if (!hasRight || !hasLeft) return false

  // Count total trump (including bowers)
  let trumpCount = 0
  for (const c of hand) {
    if (getEffectiveSuit(c, trumpSuit) === trumpSuit) trumpCount++
  }

  // Go alone with both bowers + at least one more trump (3+ trump total)
  return trumpCount >= 3
}

// ── Playing cards ────────────────────────────────────────────────────

/**
 * Returns the next player, skipping the sitting-out partner if going alone.
 */
function nextPlayer(current: number, goingAlone: number | null): number {
  let next = (current + 1) % 4
  if (goingAlone !== null && next === partnerOf(goingAlone)) {
    next = (next + 1) % 4
  }
  return next
}

/**
 * Returns how many players are active in a trick (3 if going alone, 4 otherwise).
 */
function trickSize(goingAlone: number | null): number {
  return goingAlone !== null ? 3 : 4
}

/**
 * Play a card at the given hand index for the current player.
 * Validates follow-suit rules. Returns same state ref if invalid.
 * Does NOT auto-advance AI — the React component drives AI turns via advanceAi().
 */
export function playCard(state: EuchreState, cardIndex: number): EuchreState {
  if (state.phase !== 'playing') return state

  const player = state.currentPlayer
  const hand = state.hands[player]
  const card = hand[cardIndex]
  if (!card) return state

  // Validate follow suit
  const playable = getPlayableCards(hand, state.ledSuit, state.trumpSuit!)
  if (!playable.includes(cardIndex)) return state

  const newHands = state.hands.map(h => [...h])
  newHands[player] = [...hand]
  newHands[player].splice(cardIndex, 1)

  // Determine led suit (first card of trick)
  const ledSuit = state.currentTrick.length === 0
    ? getEffectiveSuit(card, state.trumpSuit!)
    : state.ledSuit

  const newTrick = [...state.currentTrick, { player, card }]

  const next: EuchreState = {
    ...state,
    hands: newHands,
    currentTrick: newTrick,
    ledSuit,
  }

  // If trick is complete (3 cards if going alone, 4 otherwise), resolve it
  if (newTrick.length === trickSize(state.goingAlone)) {
    return completeTrick(next)
  }

  // Advance to next player (skipping sitting-out partner)
  return { ...next, currentPlayer: nextPlayer(player, state.goingAlone) }
}

/**
 * Advance one AI turn. Returns updated state.
 * Called repeatedly by the React component with timeouts.
 * Skips partner if going alone.
 */
export function advanceAi(state: EuchreState): EuchreState {
  if (state.phase !== 'playing' || state.currentPlayer === 0) return state
  // Skip sitting-out partner
  if (state.goingAlone !== null && state.currentPlayer === partnerOf(state.goingAlone)) return state

  const player = state.currentPlayer
  const hand = state.hands[player]
  if (hand.length === 0) return state

  const cardIdx = aiChooseCard(hand, state)
  return playCard({ ...state }, cardIdx)
}

// ── Trick resolution ─────────────────────────────────────────────────

function trickWinner(trick: Play[], trumpSuit: Suit, ledSuit: Suit): number {
  let bestPlayer = trick[0].player
  let bestStrength = getCardStrength(trick[0].card, trumpSuit, ledSuit)

  for (let i = 1; i < trick.length; i++) {
    const s = getCardStrength(trick[i].card, trumpSuit, ledSuit)
    if (s > bestStrength) {
      bestStrength = s
      bestPlayer = trick[i].player
    }
  }

  return bestPlayer
}

function completeTrick(state: EuchreState): EuchreState {
  const winner = trickWinner(state.currentTrick, state.trumpSuit!, state.ledSuit!)
  const tricksTaken = [...state.tricksTaken]
  tricksTaken[winner]++

  const totalTricks = tricksTaken.reduce((a, b) => a + b, 0)

  // Hand over — all 5 tricks played
  if (totalTricks === 5) {
    return resolveHand({ ...state, tricksTaken, currentTrick: [], ledSuit: null }, winner)
  }

  let next: EuchreState = {
    ...state,
    tricksTaken,
    currentTrick: [],
    ledSuit: null,
    currentPlayer: winner,
    phase: 'playing',
    message: winner === 0
      ? 'You won the trick -- lead next'
      : `${PLAYER_NAMES[winner]} won the trick`,
  }

  // If winner is AI, auto-play
  if (winner !== 0) {
    next = runAiTurns(next)
  }

  return next
}

// ── Hand scoring ─────────────────────────────────────────────────────

function resolveHand(state: EuchreState, _lastWinner: number): EuchreState {
  const teamScores: [number, number] = [...state.teamScores]
  const makerTeam = state.makerTeam!
  const defenderTeam = makerTeam === 0 ? 1 : 0

  const makerTricks = state.tricksTaken.reduce((total, taken, player) => {
    return teamOf(player) === makerTeam ? total + taken : total
  }, 0)

  let points = 0
  let msg = ''

  if (makerTricks === 5) {
    // March
    if (state.goingAlone !== null) {
      points = 4
      msg = `${TEAM_NAMES[makerTeam]} march going alone! +4 points`
    } else {
      points = 2
      msg = `${TEAM_NAMES[makerTeam]} march! +2 points`
    }
    teamScores[makerTeam] += points
  } else if (makerTricks >= 3) {
    // Makers win
    points = 1
    teamScores[makerTeam] += points
    msg = `${TEAM_NAMES[makerTeam]} take ${makerTricks} tricks. +1 point`
  } else {
    // Euchre
    points = 2
    teamScores[defenderTeam] += points
    msg = `Euchre! ${TEAM_NAMES[defenderTeam]} get +2 points`
  }

  // Check game over
  if (teamScores[0] >= WINNING_SCORE || teamScores[1] >= WINNING_SCORE) {
    const winner = teamScores[0] >= WINNING_SCORE ? 0 : 1
    return {
      ...state,
      teamScores,
      phase: 'gameOver',
      message: `${TEAM_NAMES[winner]} win the game! Final: ${teamScores[0]}-${teamScores[1]}`,
    }
  }

  return {
    ...state,
    teamScores,
    phase: 'handOver',
    message: msg + ` | Score: ${teamScores[0]}-${teamScores[1]}`,
  }
}

// ── New hand (next deal) ─────────────────────────────────────────────

export function nextHand(state: EuchreState): EuchreState {
  return createEuchreGame({
    dealer: state.dealer,
    teamScores: state.teamScores,
  })
}

// ── AI ───────────────────────────────────────────────────────────────

function runAiTurns(state: EuchreState): EuchreState {
  let current = { ...state }

  while (current.currentPlayer !== 0 && current.phase === 'playing') {
    const player = current.currentPlayer

    // Skip sitting-out partner
    if (current.goingAlone !== null && player === partnerOf(current.goingAlone)) {
      current = { ...current, currentPlayer: nextPlayer(player, current.goingAlone) }
      continue
    }

    const hand = current.hands[player]
    if (hand.length === 0) break

    const cardIdx = aiChooseCard(hand, current)
    const card = hand[cardIdx]

    const newHands = current.hands.map(h => [...h])
    newHands[player] = [...hand]
    newHands[player].splice(cardIdx, 1)

    const ledSuit = current.currentTrick.length === 0
      ? getEffectiveSuit(card, current.trumpSuit!)
      : current.ledSuit

    const newTrick = [...current.currentTrick, { player, card }]

    current = {
      ...current,
      hands: newHands,
      currentTrick: newTrick,
      ledSuit,
    }

    if (newTrick.length === trickSize(current.goingAlone)) {
      current = completeTrick(current)
      if (current.phase !== 'playing') break
      // After trick completion, winner leads next — if it's AI, continue
      continue
    }

    current = { ...current, currentPlayer: nextPlayer(player, current.goingAlone) }
  }

  if (current.phase === 'playing' && current.currentPlayer === 0) {
    current = { ...current, message: 'Your turn' }
  }

  return current
}

function aiChooseCard(hand: Card[], state: EuchreState): number {
  const trumpSuit = state.trumpSuit!
  const playable = getPlayableCards(hand, state.ledSuit, trumpSuit)
  if (playable.length === 1) return playable[0]

  const isLeading = state.currentTrick.length === 0

  if (isLeading) {
    // Lead with right bower if available
    const rbIdx = playable.find(i => isRightBower(hand[i], trumpSuit))
    if (rbIdx !== undefined) return rbIdx

    // Lead with aces of non-trump suits
    const aceIdx = playable.find(i => hand[i].rank === 1 && getEffectiveSuit(hand[i], trumpSuit) !== trumpSuit)
    if (aceIdx !== undefined) return aceIdx

    // Lead with highest non-trump
    const nonTrump = playable.filter(i => getEffectiveSuit(hand[i], trumpSuit) !== trumpSuit)
    if (nonTrump.length > 0) {
      return nonTrump.sort((a, b) => rankValue(hand[b].rank) - rankValue(hand[a].rank))[0]
    }

    // All trump — play highest
    return playable.sort((a, b) =>
      getCardStrength(hand[b], trumpSuit, state.ledSuit) - getCardStrength(hand[a], trumpSuit, state.ledSuit)
    )[0]
  }

  // Following — check if partner is winning
  const partnerIdx = (state.currentPlayer + 2) % 4
  const currentWinner = findCurrentWinner(state.currentTrick, trumpSuit, state.ledSuit!)
  const partnerWinning = currentWinner === partnerIdx

  if (partnerWinning) {
    // Play lowest card
    return playable.sort((a, b) =>
      getCardStrength(hand[a], trumpSuit, state.ledSuit) - getCardStrength(hand[b], trumpSuit, state.ledSuit)
    )[0]
  }

  // Try to win with lowest winning card
  const winningStrength = findWinningStrength(state.currentTrick, trumpSuit, state.ledSuit!)
  const winners = playable.filter(i => getCardStrength(hand[i], trumpSuit, state.ledSuit) > winningStrength)

  if (winners.length > 0) {
    // Play lowest winning card
    return winners.sort((a, b) =>
      getCardStrength(hand[a], trumpSuit, state.ledSuit) - getCardStrength(hand[b], trumpSuit, state.ledSuit)
    )[0]
  }

  // Can't win — play lowest
  return playable.sort((a, b) =>
    getCardStrength(hand[a], trumpSuit, state.ledSuit) - getCardStrength(hand[b], trumpSuit, state.ledSuit)
  )[0]
}

function findCurrentWinner(trick: Play[], trumpSuit: Suit, ledSuit: Suit): number {
  let bestPlayer = trick[0].player
  let bestStrength = getCardStrength(trick[0].card, trumpSuit, ledSuit)
  for (let i = 1; i < trick.length; i++) {
    const s = getCardStrength(trick[i].card, trumpSuit, ledSuit)
    if (s > bestStrength) {
      bestStrength = s
      bestPlayer = trick[i].player
    }
  }
  return bestPlayer
}

function findWinningStrength(trick: Play[], trumpSuit: Suit, ledSuit: Suit): number {
  let best = 0
  for (const play of trick) {
    const s = getCardStrength(play.card, trumpSuit, ledSuit)
    if (s > best) best = s
  }
  return best
}

// ── AI trump decisions ───────────────────────────────────────────────

/**
 * Count how many cards of a suit the hand has (counting bowers).
 */
function countSuitCards(hand: Card[], suit: Suit): number {
  let count = 0
  for (const c of hand) {
    if (c.suit === suit) count++
    else if (c.rank === 11 && c.suit === getSameColorSuit(suit)) count++ // left bower
  }
  return count
}

/**
 * AI decides whether to order up (round 1).
 * Orders up with 3+ cards of trump suit (counting bowers).
 */
export function aiShouldOrderUp(hand: Card[], flippedSuit: Suit): boolean {
  return countSuitCards(hand, flippedSuit) >= 3
}

/**
 * AI picks a trump suit for round 2 (not the flipped suit).
 */
function aiPickTrumpSuit(hand: Card[], excludeSuit: Suit): Suit | null {
  let bestSuit: Suit | null = null
  let bestCount = 0

  for (const suit of SUITS) {
    if (suit === excludeSuit) continue
    const count = countSuitCards(hand, suit)
    if (count > bestCount) {
      bestCount = count
      bestSuit = suit
    }
  }

  return bestSuit
}

/**
 * AI auto-plays trump selection. Called by the React component.
 * Returns updated state after AI players act in trump selection phases.
 */
export function aiTrumpSelection(state: EuchreState): EuchreState {
  let current = { ...state }

  while (current.currentPlayer !== 0 &&
         (current.phase === 'trumpRound1' || current.phase === 'trumpRound2' || current.phase === 'goAlonePrompt')) {
    const player = current.currentPlayer
    const hand = current.hands[player]

    if (current.phase === 'goAlonePrompt') {
      // AI decides whether to go alone
      const alone = current.trumpSuit ? aiShouldGoAlone(hand, current.trumpSuit) : false
      current = setGoingAlone(current, alone)
      // If dealer needs to discard and is AI
      if (current.phase === 'dealerDiscard' && current.currentPlayer !== 0) {
        current = aiDealerDiscard(current)
      }
      return current
    }

    if (current.phase === 'trumpRound1') {
      if (aiShouldOrderUp(hand, current.flippedCard.suit)) {
        current = orderUp(current)
        // orderUp now goes to goAlonePrompt, handle it if AI
        continue
      } else {
        current = pass(current)
      }
    } else {
      // trumpRound2
      const suit = aiPickTrumpSuit(hand, current.flippedCard.suit)
      if (suit) {
        current = nameTrump(current, suit)
        // nameTrump now goes to goAlonePrompt, handle it if AI
        continue
      } else {
        current = pass(current)
      }
    }
  }

  return current
}

/**
 * AI dealer discards weakest non-trump card.
 */
export function aiDealerDiscard(state: EuchreState): EuchreState {
  if (state.phase !== 'dealerDiscard') return state

  const hand = state.hands[state.dealer]
  const trumpSuit = state.trumpSuit!

  // Find weakest non-trump card
  let weakestIdx = 0
  let weakestStr = Infinity

  for (let i = 0; i < hand.length; i++) {
    const eff = getEffectiveSuit(hand[i], trumpSuit)
    const str = getCardStrength(hand[i], trumpSuit, null)
    if (eff !== trumpSuit && str < weakestStr) {
      weakestStr = str
      weakestIdx = i
    }
  }

  // If all trump, discard lowest
  if (weakestStr === Infinity) {
    for (let i = 0; i < hand.length; i++) {
      const str = getCardStrength(hand[i], trumpSuit, null)
      if (str < weakestStr) {
        weakestStr = str
        weakestIdx = i
      }
    }
  }

  return dealerDiscard(state, weakestIdx)
}
