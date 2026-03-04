/**
 * Cribbage engine — pure logic, no React.
 *
 * 2-player cribbage (1 human + 1 AI). First to 121 wins.
 */

import { createDeck, shuffleDeck, type Card, type Suit } from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

export type Phase = 'discard' | 'pegging' | 'scoring' | 'gameOver'

export interface PegCard {
  card: Card
  player: number
}

export interface CribbageState {
  hands: Card[][]            // [0] = human, [1] = AI (4 cards after discard)
  originalHands: Card[][]    // [0] = human, [1] = AI (for scoring display)
  crib: Card[]
  cutCard: Card | null
  pegCards: PegCard[]        // cards played in current pegging count
  pegTotal: number
  currentPlayer: number
  dealer: number
  scores: number[]
  phase: Phase
  message: string
  selectedForCrib: number[]  // human's selected cards to discard
  pegHistory: PegCard[]      // all cards played in pegging this round
  canPlay: boolean[]         // who can play in current count
  scoringStep: 'nonDealer' | 'dealer' | 'crib' | 'done'
  lastScoreBreakdown: string
}

// ── Constants ────────────────────────────────────────────────────────

const WIN_SCORE = 121

// ── Card value helpers ──────────────────────────────────────────────

/** Peg/counting value: A=1, 2-10=face, J/Q/K=10. */
export function pegValue(card: Card): number {
  if (card.rank >= 11) return 10
  return card.rank
}

// ── Scoring helpers ─────────────────────────────────────────────────

/** Count all subsets of cards that sum to 15. Returns 2 points per combo. */
export function count15s(cards: Card[]): number {
  const values = cards.map(pegValue)
  let combos = 0

  // Enumerate all subsets using bitmask
  const n = values.length
  for (let mask = 1; mask < (1 << n); mask++) {
    let sum = 0
    for (let i = 0; i < n; i++) {
      if (mask & (1 << i)) {
        sum += values[i]
      }
    }
    if (sum === 15) combos++
  }

  return combos * 2
}

/** Count all pairs of same rank. Returns 2 points per pair. */
export function countPairs(cards: Card[]): number {
  let pairs = 0
  for (let i = 0; i < cards.length; i++) {
    for (let j = i + 1; j < cards.length; j++) {
      if (cards[i].rank === cards[j].rank) pairs++
    }
  }
  return pairs * 2
}

/**
 * Count run points. Handles double/triple/quad runs correctly.
 *
 * Algorithm: sort by rank, group consecutive ranks, compute the product
 * of duplicate counts for each rank in the run, times the run length.
 */
export function countRuns(cards: Card[]): number {
  if (cards.length < 3) return 0

  // Get sorted unique ranks and their counts
  const rankCounts: Map<number, number> = new Map()
  for (const c of cards) {
    rankCounts.set(c.rank, (rankCounts.get(c.rank) || 0) + 1)
  }

  const sortedRanks = [...rankCounts.keys()].sort((a, b) => a - b)
  if (sortedRanks.length < 3) {
    // Need at least 3 different ranks for a run
    // Unless we have duplicates — but you still need 3 consecutive ranks minimum
    return 0
  }

  // Find all maximal consecutive sequences of ranks
  let totalRunPoints = 0
  let runStart = 0

  for (let i = 1; i <= sortedRanks.length; i++) {
    // Check if sequence breaks
    if (i === sortedRanks.length || sortedRanks[i] !== sortedRanks[i - 1] + 1) {
      const runLength = i - runStart
      if (runLength >= 3) {
        // Compute multiplier: product of counts for each rank in the run
        let multiplier = 1
        for (let j = runStart; j < i; j++) {
          multiplier *= rankCounts.get(sortedRanks[j])!
        }
        totalRunPoints += runLength * multiplier
      }
      runStart = i
    }
  }

  return totalRunPoints
}

/** Count flush points. */
export function countFlush(hand: Card[], cutCard: Card, isCrib: boolean): number {
  if (hand.length < 4) return 0

  const suit = hand[0].suit
  const allHandSame = hand.every(c => c.suit === suit)

  if (!allHandSame) return 0

  // Check if cut card matches
  if (cutCard.suit === suit) return 5

  // 4-card flush only counts in hand, not in crib
  if (isCrib) return 0
  return 4
}

/** Count nobs: Jack in hand matching cut card's suit = 1 point. */
export function countNobs(hand: Card[], cutCard: Card): number {
  return hand.some(c => c.rank === 11 && c.suit === cutCard.suit) ? 1 : 0
}

/** Score a hand (4 cards) with a cut card. Returns total and breakdown. */
export function scoreHand(
  hand: Card[],
  cutCard: Card,
  isCrib: boolean
): { total: number; breakdown: string } {
  const allFive = [...hand, cutCard]
  const parts: string[] = []

  const fifteens = count15s(allFive)
  if (fifteens > 0) parts.push(`15s: ${fifteens}`)

  const pairs = countPairs(allFive)
  if (pairs > 0) parts.push(`Pairs: ${pairs}`)

  const runs = countRuns(allFive)
  if (runs > 0) parts.push(`Runs: ${runs}`)

  const flush = countFlush(hand, cutCard, isCrib)
  if (flush > 0) parts.push(`Flush: ${flush}`)

  const nobs = countNobs(hand, cutCard)
  if (nobs > 0) parts.push(`Nobs: ${nobs}`)

  const total = fifteens + pairs + runs + flush + nobs

  return {
    total,
    breakdown: parts.length > 0 ? parts.join(', ') : 'No points',
  }
}

// ── Game creation ────────────────────────────────────────────────────

export function createCribbageGame(): CribbageState {
  const deck = shuffleDeck(createDeck()).map(c => ({ ...c, faceUp: true }))
  const dealer = Math.random() < 0.5 ? 0 : 1

  const hands: Card[][] = [
    deck.slice(0, 6),
    deck.slice(6, 12),
  ]

  return {
    hands: hands.map(h => [...h]),
    originalHands: hands.map(h => [...h]),
    crib: [],
    cutCard: null,
    pegCards: [],
    pegTotal: 0,
    currentPlayer: dealer === 0 ? 1 : 0, // non-dealer plays first in pegging
    dealer,
    scores: [0, 0],
    phase: 'discard',
    message: 'Select 2 cards to send to the crib',
    selectedForCrib: [],
    pegHistory: [],
    canPlay: [true, true],
    scoringStep: 'nonDealer',
    lastScoreBreakdown: '',
  }
}

// ── Discard phase ────────────────────────────────────────────────────

export function toggleCribSelection(state: CribbageState, cardIndex: number): CribbageState {
  if (state.phase !== 'discard') return state

  const selected = [...state.selectedForCrib]
  const idx = selected.indexOf(cardIndex)

  if (idx >= 0) {
    // Deselect
    selected.splice(idx, 1)
  } else if (selected.length < 2) {
    // Select (max 2)
    selected.push(cardIndex)
  } else {
    // Already 2 selected — ignore
    return state
  }

  return {
    ...state,
    selectedForCrib: selected,
    message: selected.length === 2
      ? 'Press "Send to Crib" to continue'
      : 'Select 2 cards to send to the crib',
  }
}

/** AI chooses 2 cards to discard to crib. */
function aiDiscardToCrib(hand: Card[], isDealer: boolean): { kept: Card[]; discarded: Card[] } {
  // Simple strategy: evaluate all C(6,2) = 15 possible discards
  // Pick the one that maximizes remaining hand potential
  let bestKept: Card[] = hand.slice(0, 4)
  let bestDiscarded: Card[] = hand.slice(4, 6)
  let bestScore = -Infinity

  for (let i = 0; i < hand.length; i++) {
    for (let j = i + 1; j < hand.length; j++) {
      const discarded = [hand[i], hand[j]]
      const kept = hand.filter((_, idx) => idx !== i && idx !== j)

      // Estimate hand value without cut card (use a dummy mid-range card)
      // Score the kept hand with a dummy cut for rough estimation
      let handEstimate = 0
      // Check pairs and runs in kept hand
      handEstimate += countPairs(kept)
      handEstimate += countRuns(kept)

      // If dealer, discarding complementary cards to crib is good
      // If not dealer, avoid sending good cards to opponent's crib
      let cribAdjust = 0
      const dv0 = pegValue(discarded[0])
      const dv1 = pegValue(discarded[1])

      if (isDealer) {
        // Dealer wants to maximize crib value
        if (dv0 + dv1 === 15) cribAdjust += 4
        if (discarded[0].rank === discarded[1].rank) cribAdjust += 2
        if (dv0 === 5 || dv1 === 5) cribAdjust += 2
      } else {
        // Non-dealer wants to minimize crib value
        if (dv0 + dv1 === 15) cribAdjust -= 4
        if (discarded[0].rank === discarded[1].rank) cribAdjust -= 2
        if (dv0 === 5 || dv1 === 5) cribAdjust -= 2
      }

      const totalEstimate = handEstimate + cribAdjust
      if (totalEstimate > bestScore) {
        bestScore = totalEstimate
        bestKept = kept
        bestDiscarded = discarded
      }
    }
  }

  return { kept: bestKept, discarded: bestDiscarded }
}

export function submitCrib(state: CribbageState): CribbageState {
  if (state.phase !== 'discard') return state
  if (state.selectedForCrib.length !== 2) return state

  // Human discards
  const humanDiscards = state.selectedForCrib
    .sort((a, b) => b - a)
    .map(i => state.hands[0][i])
  const humanHand = state.hands[0].filter((_, i) => !state.selectedForCrib.includes(i))

  // AI discards
  const aiResult = aiDiscardToCrib(state.hands[1], state.dealer === 1)

  const crib = [...humanDiscards, ...aiResult.discarded]

  // Build remaining deck (exclude all dealt cards)
  const usedCards = new Set(
    [...state.hands[0], ...state.hands[1]].map(c => `${c.rank}-${c.suit}`)
  )
  const deck = shuffleDeck(createDeck())
    .filter(c => !usedCards.has(`${c.rank}-${c.suit}`))

  const cutCard = { ...deck[0], faceUp: true }

  // His Heels: if cut card is a Jack, dealer gets 2 points
  const scores = [...state.scores]
  let message = ''
  if (cutCard.rank === 11) {
    scores[state.dealer] += 2
    message = 'His Heels! Jack cut — dealer gets 2 points. '
    if (scores[state.dealer] >= WIN_SCORE) {
      return {
        ...state,
        hands: [humanHand, aiResult.kept],
        originalHands: [humanHand, aiResult.kept],
        crib,
        cutCard,
        scores,
        phase: 'gameOver',
        message: `${state.dealer === 0 ? 'You win' : 'AI wins'} with His Heels!`,
        selectedForCrib: [],
      }
    }
  }

  const nonDealer = state.dealer === 0 ? 1 : 0

  return {
    ...state,
    hands: [humanHand, aiResult.kept],
    originalHands: [humanHand, aiResult.kept],
    crib,
    cutCard,
    pegCards: [],
    pegTotal: 0,
    currentPlayer: nonDealer, // non-dealer plays first
    scores,
    phase: 'pegging',
    message: message + (nonDealer === 0 ? 'Your turn to play a card' : "AI's turn..."),
    selectedForCrib: [],
    pegHistory: [],
    canPlay: [true, true],
  }
}

// ── Pegging phase ────────────────────────────────────────────────────

/** Check if a card can be played without exceeding 31. */
function canPegCard(card: Card, pegTotal: number): boolean {
  return pegTotal + pegValue(card) <= 31
}

/** Check for pegging runs: last N cards in pegCards form a run when sorted. */
function checkPegRun(pegCards: PegCard[]): number {
  if (pegCards.length < 3) return 0

  // Check from longest possible run down to 3
  for (let len = pegCards.length; len >= 3; len--) {
    const lastN = pegCards.slice(-len).map(pc => pc.card.rank)
    const sorted = [...lastN].sort((a, b) => a - b)
    let isRun = true
    for (let i = 1; i < sorted.length; i++) {
      if (sorted[i] !== sorted[i - 1] + 1) {
        isRun = false
        break
      }
    }
    if (isRun) return len
  }

  return 0
}

/** Check for pegging pairs/trips/quads at the end of pegCards. */
function checkPegPairs(pegCards: PegCard[]): number {
  if (pegCards.length < 2) return 0

  const lastRank = pegCards[pegCards.length - 1].card.rank
  let count = 0

  // Count consecutive same-rank cards from the end
  for (let i = pegCards.length - 1; i >= 0; i--) {
    if (pegCards[i].card.rank === lastRank) {
      count++
    } else {
      break
    }
  }

  // Pairs scoring: 2=2pts, 3=6pts, 4=12pts
  if (count >= 4) return 12
  if (count >= 3) return 6
  if (count >= 2) return 2
  return 0
}

/** Calculate pegging points for the card just played. */
function calcPegPoints(pegCards: PegCard[], pegTotal: number): { points: number; details: string[] } {
  let points = 0
  const details: string[] = []

  // Check for 15
  if (pegTotal === 15) {
    points += 2
    details.push('15 for 2')
  }

  // Check for 31
  if (pegTotal === 31) {
    points += 2
    details.push('31 for 2')
  }

  // Check for pairs/trips/quads
  const pairPts = checkPegPairs(pegCards)
  if (pairPts > 0) {
    points += pairPts
    if (pairPts === 12) details.push('Four of a kind for 12')
    else if (pairPts === 6) details.push('Three of a kind for 6')
    else details.push('Pair for 2')
  }

  // Check for runs (only if not a pair — pairs and runs are mutually exclusive in context)
  // Actually they are NOT mutually exclusive. But in pegging, a run check looks at the last N
  // cards in sequence. If the last 2 are a pair, the last 3 can't be a run (two same ranks).
  // So pairs and runs are effectively mutually exclusive in pegging.
  if (pairPts === 0) {
    const runLen = checkPegRun(pegCards)
    if (runLen > 0) {
      points += runLen
      details.push(`Run of ${runLen} for ${runLen}`)
    }
  }

  return { points, details }
}

/** Handle transition when all pegging cards are played or both say go. */
function checkPeggingComplete(state: CribbageState): CribbageState {
  const totalPlayed = state.pegHistory.length

  // All 8 cards played
  if (totalPlayed >= 8 || (getPlayableHandCards(state, 0).length === 0 && getPlayableHandCards(state, 1).length === 0)) {
    // Check if truly all cards played
    const humanRemaining = getPlayableHandCards(state, 0)
    const aiRemaining = getPlayableHandCards(state, 1)

    if (humanRemaining.length === 0 && aiRemaining.length === 0) {
      // Award last card point if count is not 31 (31 already scored)
      const scores = [...state.scores]
      let message = state.message
      if (state.pegTotal > 0 && state.pegTotal < 31 && state.pegHistory.length > 0) {
        const lastPlayer = state.pegHistory[state.pegHistory.length - 1].player
        scores[lastPlayer] += 1
        message = `Last card: +1 point. `
        if (scores[lastPlayer] >= WIN_SCORE) {
          return {
            ...state,
            scores,
            phase: 'gameOver',
            message: `${lastPlayer === 0 ? 'You win' : 'AI wins'}!`,
          }
        }
      }

      return {
        ...state,
        scores,
        phase: 'scoring',
        scoringStep: 'nonDealer',
        message: message + 'Scoring phase — click Continue to see scores',
        pegTotal: 0,
        pegCards: [],
      }
    }
  }

  return state
}

/** Get cards remaining in a player's hand (not yet played in pegging). */
function getPlayableHandCards(state: CribbageState, player: number): Card[] {
  const played = new Set(
    state.pegHistory
      .filter(pc => pc.player === player)
      .map(pc => `${pc.card.rank}-${pc.card.suit}`)
  )
  return state.hands[player].filter(c => !played.has(`${c.rank}-${c.suit}`))
}

/** Get indices into the original hand for unplayed cards that can be pegged. */
function getHumanPlayableIndices(state: CribbageState): number[] {
  const playedSet = new Set(
    state.pegHistory
      .filter(pc => pc.player === 0)
      .map(pc => `${pc.card.rank}-${pc.card.suit}`)
  )
  const indices: number[] = []
  for (let i = 0; i < state.hands[0].length; i++) {
    const c = state.hands[0][i]
    if (!playedSet.has(`${c.rank}-${c.suit}`) && canPegCard(c, state.pegTotal)) {
      indices.push(i)
    }
  }
  return indices
}

/** AI plays a peg card. Returns updated state. */
function aiPegTurn(state: CribbageState): CribbageState {
  const remaining = getPlayableHandCards(state, 1)
  const playable = remaining.filter(c => canPegCard(c, state.pegTotal))

  if (playable.length === 0) {
    // AI says go
    return {
      ...state,
      canPlay: [state.canPlay[0], false],
      message: 'AI says "Go"',
    }
  }

  // AI strategy: try to make 15 or 31, avoid making 5 or 21
  let bestCard = playable[0]
  let bestScore = -100

  for (const c of playable) {
    const newTotal = state.pegTotal + pegValue(c)
    let cardScore = 0

    // Reward hitting 15 or 31
    if (newTotal === 15) cardScore += 10
    if (newTotal === 31) cardScore += 10

    // Avoid leaving total at 5 or 21 (opponent can make 15/31 with a 10)
    if (newTotal === 5 || newTotal === 21) cardScore -= 5

    // Check if we'd make a pair
    if (state.pegCards.length > 0 &&
        state.pegCards[state.pegCards.length - 1].card.rank === c.rank) {
      cardScore += 5
    }

    // Prefer playing lower cards to keep options open
    cardScore -= pegValue(c) * 0.1

    if (cardScore > bestScore) {
      bestScore = cardScore
      bestCard = c
    }
  }

  // Play the chosen card
  const newTotal = state.pegTotal + pegValue(bestCard)
  const pegEntry: PegCard = { card: bestCard, player: 1 }
  const newPegCards = [...state.pegCards, pegEntry]
  const newPegHistory = [...state.pegHistory, pegEntry]

  // Calculate pegging points
  const { points, details } = calcPegPoints(newPegCards, newTotal)
  const scores = [...state.scores]
  scores[1] += points

  if (scores[1] >= WIN_SCORE) {
    return {
      ...state,
      scores,
      pegCards: newPegCards,
      pegTotal: newTotal,
      pegHistory: newPegHistory,
      phase: 'gameOver',
      message: 'AI wins!',
    }
  }

  let message = `AI plays ${rankName(bestCard.rank)}${suitSymbol(bestCard.suit)}`
  if (details.length > 0) message += ` — ${details.join(', ')}`

  let nextState: CribbageState = {
    ...state,
    pegCards: newPegCards,
    pegTotal: newTotal,
    pegHistory: newPegHistory,
    scores,
    message,
    canPlay: [state.canPlay[0], true],
  }

  // If 31, reset count
  if (newTotal === 31) {
    nextState = {
      ...nextState,
      pegCards: [],
      pegTotal: 0,
      canPlay: [true, true],
    }
  }

  return nextState
}

function rankName(rank: number): string {
  if (rank === 1) return 'A'
  if (rank === 11) return 'J'
  if (rank === 12) return 'Q'
  if (rank === 13) return 'K'
  return String(rank)
}

function suitSymbol(suit: Suit): string {
  const symbols: Record<Suit, string> = {
    hearts: '\u2665',
    diamonds: '\u2666',
    clubs: '\u2663',
    spades: '\u2660',
  }
  return symbols[suit]
}

export function playPegCard(state: CribbageState, cardIndex: number): CribbageState {
  if (state.phase !== 'pegging') return state
  if (state.currentPlayer !== 0) return state

  const card = state.hands[0][cardIndex]
  if (!card) return state

  // Check if card was already played
  const playedSet = new Set(
    state.pegHistory
      .filter(pc => pc.player === 0)
      .map(pc => `${pc.card.rank}-${pc.card.suit}`)
  )
  if (playedSet.has(`${card.rank}-${card.suit}`)) return state

  // Check if card would exceed 31
  if (!canPegCard(card, state.pegTotal)) return state

  const newTotal = state.pegTotal + pegValue(card)
  const pegEntry: PegCard = { card, player: 0 }
  const newPegCards = [...state.pegCards, pegEntry]
  const newPegHistory = [...state.pegHistory, pegEntry]

  // Calculate pegging points
  const { points, details } = calcPegPoints(newPegCards, newTotal)
  const scores = [...state.scores]
  scores[0] += points

  if (scores[0] >= WIN_SCORE) {
    return {
      ...state,
      scores,
      pegCards: newPegCards,
      pegTotal: newTotal,
      pegHistory: newPegHistory,
      phase: 'gameOver',
      message: 'You win!',
    }
  }

  let message = `You play ${rankName(card.rank)}${suitSymbol(card.suit)}`
  if (details.length > 0) message += ` — ${details.join(', ')}`

  let nextState: CribbageState = {
    ...state,
    pegCards: newPegCards,
    pegTotal: newTotal,
    pegHistory: newPegHistory,
    scores,
    message,
    currentPlayer: 1,
    canPlay: [true, state.canPlay[1]],
  }

  // If 31, reset count
  if (newTotal === 31) {
    nextState = {
      ...nextState,
      pegCards: [],
      pegTotal: 0,
      canPlay: [true, true],
    }
  }

  // Check if pegging is complete
  nextState = checkPeggingComplete(nextState)
  if (nextState.phase !== 'pegging') return nextState

  // AI takes turn(s) — it may play multiple cards if human can't play
  nextState = runAiPegTurns(nextState)

  return nextState
}

/** Let AI take pegging turns until it's human's turn again or pegging ends. */
function runAiPegTurns(state: CribbageState): CribbageState {
  let current = { ...state }

  while (current.phase === 'pegging' && current.currentPlayer === 1) {
    const aiRemaining = getPlayableHandCards(current, 1)
    const aiPlayable = aiRemaining.filter(c => canPegCard(c, current.pegTotal))

    if (aiPlayable.length === 0) {
      // AI can't play
      current = {
        ...current,
        canPlay: [current.canPlay[0], false],
      }

      // Check if human can play
      const humanPlayable = getHumanPlayableIndices(current)
      if (humanPlayable.length === 0) {
        // Neither can play — award go point, reset count
        current = handleGoReset(current)
        if (current.phase !== 'pegging') return current
        continue
      } else {
        // Human's turn
        current = {
          ...current,
          currentPlayer: 0,
          message: current.message + ' — Your turn',
        }
        return current
      }
    }

    // AI plays
    current = aiPegTurn(current)
    if (current.phase !== 'pegging') return current

    // Check if pegging complete
    current = checkPeggingComplete(current)
    if (current.phase !== 'pegging') return current

    // Check if human can play
    const humanPlayable = getHumanPlayableIndices(current)
    if (humanPlayable.length > 0) {
      current = {
        ...current,
        currentPlayer: 0,
      }
      return current
    }

    // Human can't play — check if AI can continue
    const aiStillPlayable = getPlayableHandCards(current, 1).filter(c => canPegCard(c, current.pegTotal))
    if (aiStillPlayable.length === 0) {
      // Neither can play — handle go
      current = handleGoReset(current)
      if (current.phase !== 'pegging') return current
    }
    // Otherwise AI loops again
  }

  return current
}

/** Handle when neither player can play: award go point, reset count. */
function handleGoReset(state: CribbageState): CribbageState {
  const scores = [...state.scores]
  let message = ''

  // Award 1 point for last card (go) if not already at 31
  if (state.pegTotal > 0 && state.pegTotal < 31 && state.pegCards.length > 0) {
    const lastPlayer = state.pegCards[state.pegCards.length - 1].player
    scores[lastPlayer] += 1
    message = `Go! +1 point for ${lastPlayer === 0 ? 'you' : 'AI'}. `

    if (scores[lastPlayer] >= WIN_SCORE) {
      return {
        ...state,
        scores,
        phase: 'gameOver',
        message: `${lastPlayer === 0 ? 'You win' : 'AI wins'}!`,
      }
    }
  }

  // Reset count, check if anyone has cards left
  const humanRemaining = getPlayableHandCards(state, 0)
  const aiRemaining = getPlayableHandCards(state, 1)

  if (humanRemaining.length === 0 && aiRemaining.length === 0) {
    // All cards played — move to scoring
    return {
      ...state,
      scores,
      phase: 'scoring',
      scoringStep: 'nonDealer',
      pegTotal: 0,
      pegCards: [],
      message: message + 'All cards played. Click Continue to see scores.',
    }
  }

  // Reset count, continue pegging
  const nonDealer = state.dealer === 0 ? 1 : 0
  // Give priority to whoever has cards
  let nextPlayer: number
  if (humanRemaining.length > 0 && aiRemaining.length > 0) {
    nextPlayer = nonDealer // non-dealer priority
  } else if (humanRemaining.length > 0) {
    nextPlayer = 0
  } else {
    nextPlayer = 1
  }

  const resetState: CribbageState = {
    ...state,
    scores,
    pegCards: [],
    pegTotal: 0,
    canPlay: [true, true],
    currentPlayer: nextPlayer,
    message: message + 'Count resets to 0.',
  }

  // If AI goes next, let it play
  if (nextPlayer === 1) {
    return runAiPegTurns(resetState)
  }

  return resetState
}

export function sayGo(state: CribbageState): CribbageState {
  if (state.phase !== 'pegging') return state
  if (state.currentPlayer !== 0) return state

  // Human says go — mark them as can't play
  let current: CribbageState = {
    ...state,
    canPlay: [false, state.canPlay[1]],
  }

  // Check if AI can play
  const aiPlayable = getPlayableHandCards(current, 1).filter(c => canPegCard(c, current.pegTotal))
  if (aiPlayable.length > 0) {
    // AI continues playing
    current = { ...current, currentPlayer: 1 }
    return runAiPegTurns(current)
  }

  // Neither can play — handle go reset
  return handleGoReset(current)
}

// ── Scoring phase ────────────────────────────────────────────────────

export function continueScoring(state: CribbageState): CribbageState {
  if (state.phase !== 'scoring') return state

  const nonDealer = state.dealer === 0 ? 1 : 0
  const scores = [...state.scores]

  switch (state.scoringStep) {
    case 'nonDealer': {
      // Score non-dealer's hand
      const hand = state.originalHands[nonDealer]
      const result = scoreHand(hand, state.cutCard!, false)
      scores[nonDealer] += result.total

      const who = nonDealer === 0 ? 'Your' : "AI's"

      if (scores[nonDealer] >= WIN_SCORE) {
        return {
          ...state,
          scores,
          phase: 'gameOver',
          message: `${nonDealer === 0 ? 'You win' : 'AI wins'}! ${who} hand: ${result.total} points (${result.breakdown})`,
          lastScoreBreakdown: result.breakdown,
        }
      }

      return {
        ...state,
        scores,
        scoringStep: 'dealer',
        message: `${who} hand: ${result.total} points (${result.breakdown})`,
        lastScoreBreakdown: result.breakdown,
      }
    }

    case 'dealer': {
      // Score dealer's hand
      const hand = state.originalHands[state.dealer]
      const result = scoreHand(hand, state.cutCard!, false)
      scores[state.dealer] += result.total

      const who = state.dealer === 0 ? 'Your' : "AI's"

      if (scores[state.dealer] >= WIN_SCORE) {
        return {
          ...state,
          scores,
          phase: 'gameOver',
          message: `${state.dealer === 0 ? 'You win' : 'AI wins'}! ${who} hand: ${result.total} points (${result.breakdown})`,
          lastScoreBreakdown: result.breakdown,
        }
      }

      return {
        ...state,
        scores,
        scoringStep: 'crib',
        message: `${who} hand: ${result.total} points (${result.breakdown})`,
        lastScoreBreakdown: result.breakdown,
      }
    }

    case 'crib': {
      // Score the crib (belongs to dealer)
      const result = scoreHand(state.crib, state.cutCard!, true)
      scores[state.dealer] += result.total

      const who = state.dealer === 0 ? 'Your' : "AI's"

      if (scores[state.dealer] >= WIN_SCORE) {
        return {
          ...state,
          scores,
          phase: 'gameOver',
          message: `${state.dealer === 0 ? 'You win' : 'AI wins'}! ${who} crib: ${result.total} points (${result.breakdown})`,
          lastScoreBreakdown: result.breakdown,
        }
      }

      return {
        ...state,
        scores,
        scoringStep: 'done',
        message: `${who} crib: ${result.total} points (${result.breakdown})`,
        lastScoreBreakdown: result.breakdown,
      }
    }

    case 'done':
      return state
  }
}

// ── New round ────────────────────────────────────────────────────────

export function newRound(state: CribbageState): CribbageState {
  const newDealer = state.dealer === 0 ? 1 : 0
  const deck = shuffleDeck(createDeck()).map(c => ({ ...c, faceUp: true }))

  const hands: Card[][] = [
    deck.slice(0, 6),
    deck.slice(6, 12),
  ]

  return {
    hands: hands.map(h => [...h]),
    originalHands: hands.map(h => [...h]),
    crib: [],
    cutCard: null,
    pegCards: [],
    pegTotal: 0,
    currentPlayer: newDealer === 0 ? 1 : 0,
    dealer: newDealer,
    scores: [...state.scores],
    phase: 'discard',
    message: 'Select 2 cards to send to the crib',
    selectedForCrib: [],
    pegHistory: [],
    canPlay: [true, true],
    scoringStep: 'nonDealer',
    lastScoreBreakdown: '',
  }
}

// ── Query helpers (for React component) ─────────────────────────────

/** Get indices of cards the human can play in pegging. */
export function getHumanPeggableCards(state: CribbageState): number[] {
  if (state.phase !== 'pegging' || state.currentPlayer !== 0) return []
  return getHumanPlayableIndices(state)
}

/** Check if human must say Go (has cards but none playable under 31). */
export function humanMustGo(state: CribbageState): boolean {
  if (state.phase !== 'pegging' || state.currentPlayer !== 0) return false
  const remaining = getPlayableHandCards(state, 0)
  if (remaining.length === 0) return false
  return remaining.every(c => !canPegCard(c, state.pegTotal))
}

/** Check if a card was already played in pegging. */
export function isCardPlayed(state: CribbageState, player: number, cardIndex: number): boolean {
  const card = state.hands[player][cardIndex]
  if (!card) return false
  return state.pegHistory.some(
    pc => pc.player === player && pc.card.rank === card.rank && pc.card.suit === card.suit
  )
}
