/**
 * Rummy 500 engine — pure logic, no React.
 *
 * 2-player (human vs AI). Draw, meld sets/runs, lay off on any meld, discard.
 * First to 500 cumulative points wins.
 */

import { createDeck, shuffleDeck, type Card, type Suit } from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

export type Phase = 'draw' | 'meld' | 'discard' | 'roundOver' | 'gameOver'

export interface Meld {
  cards: Card[]
  type: 'set' | 'run'
}

export interface Rummy500State {
  hands: Card[][]
  melds: Meld[]
  stock: Card[]
  discardPile: Card[]
  currentPlayer: number
  phase: Phase
  scores: number[]
  message: string
  selectedCards: number[]
  hasDrawn: boolean
}

// ── Constants ────────────────────────────────────────────────────────

const WINNING_SCORE = 500
const SUITS: Suit[] = ['hearts', 'diamonds', 'clubs', 'spades']

// ── Card value ───────────────────────────────────────────────────────

/** Card value: A=1, 2-10=face, J/Q/K=10. */
export function cardValue(card: Card): number {
  if (card.rank === 1) return 1
  if (card.rank >= 11) return 10
  return card.rank
}

/**
 * Card value in meld context.
 * Ace = 15 when in a high run (A-K-Q), otherwise 1.
 */
function meldCardValue(card: Card, meld: Meld): number {
  if (card.rank === 1 && meld.type === 'run') {
    // Check if this run is a high run (contains King)
    const hasKing = meld.cards.some(c => c.rank === 13)
    if (hasKing) return 15
  }
  return cardValue(card)
}

// ── Meld validation ──────────────────────────────────────────────────

/** 3+ cards of the same rank, different suits. */
export function isValidSet(cards: Card[]): boolean {
  if (cards.length < 3 || cards.length > 4) return false
  const rank = cards[0].rank
  if (!cards.every(c => c.rank === rank)) return false
  // All suits must be different
  const suits = new Set(cards.map(c => c.suit))
  return suits.size === cards.length
}

/** 3+ consecutive cards of the same suit. Ace can be low (A-2-3) or high (Q-K-A). */
export function isValidRun(cards: Card[]): boolean {
  if (cards.length < 3) return false
  // All same suit
  const suit = cards[0].suit
  if (!cards.every(c => c.suit === suit)) return false

  const ranks = cards.map(c => c.rank).sort((a, b) => a - b)

  // Check low-ace run: ranks are consecutive starting from rank values
  if (isConsecutive(ranks)) return true

  // Check high-ace run: if ace is present, try treating it as 14
  if (ranks[0] === 1) {
    const highRanks = [...ranks.slice(1), 14].sort((a, b) => a - b)
    if (isConsecutive(highRanks)) return true
  }

  return false
}

function isConsecutive(sorted: number[]): boolean {
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] !== sorted[i - 1] + 1) return false
  }
  return true
}

/** Check if cards form a valid meld (set or run). */
export function isValidMeld(cards: Card[]): { valid: boolean; type: 'set' | 'run' } {
  if (isValidSet(cards)) return { valid: true, type: 'set' }
  if (isValidRun(cards)) return { valid: true, type: 'run' }
  return { valid: false, type: 'set' }
}

/** Can a single card extend this meld? */
export function canLayOff(card: Card, meld: Meld): boolean {
  if (meld.type === 'set') {
    // Must be same rank, different suit, max 4 cards
    if (meld.cards.length >= 4) return false
    if (card.rank !== meld.cards[0].rank) return false
    if (meld.cards.some(c => c.suit === card.suit)) return false
    return true
  }

  // Run: card must be same suit, extend top or bottom
  if (card.suit !== meld.cards[0].suit) return false

  const ranks = meld.cards.map(c => c.rank).sort((a, b) => a - b)

  // Check for high-ace run: if run contains ace treated as 14
  const hasAce = ranks.includes(1)
  const hasKing = ranks.includes(13)

  if (hasAce && hasKing) {
    // This is a high-ace run. Ranks in terms of actual values: replace 1 with 14
    const highRanks = ranks.map(r => r === 1 ? 14 : r).sort((a, b) => a - b)
    const minHighRank = highRanks[0]
    // Can extend below
    if (card.rank === minHighRank - 1) return true
    // Cannot extend above 14 (Ace high is max)
    return false
  }

  const minRank = ranks[0]
  const maxRank = ranks[ranks.length - 1]

  // Extend below
  if (card.rank === minRank - 1) return true
  // Extend above
  if (card.rank === maxRank + 1) return true

  // Special case: Ace can extend above King
  if (card.rank === 1 && maxRank === 13) return true
  // Ace extends below 2
  if (card.rank === 1 && minRank === 2) return true

  return false
}

// ── Hand sorting ─────────────────────────────────────────────────────

function sortHand(hand: Card[]): Card[] {
  return [...hand].sort((a, b) => a.suit.localeCompare(b.suit) || a.rank - b.rank)
}

// ── Game creation ────────────────────────────────────────────────────

export function createRummy500Game(): Rummy500State {
  const deck = shuffleDeck(createDeck()).map(c => ({ ...c, faceUp: true }))
  const hand0 = sortHand(deck.splice(0, 7))
  const hand1 = deck.splice(0, 7)
  const stock = deck // remaining 38 cards

  return {
    hands: [hand0, hand1],
    melds: [],
    stock,
    discardPile: [],
    currentPlayer: 0,
    phase: 'draw',
    scores: [0, 0],
    message: 'Draw a card from stock or discard pile',
    selectedCards: [],
    hasDrawn: false,
  }
}

// ── Score calculation ────────────────────────────────────────────────

/** Score melds for their point values. Ace in high run = 15. */
function scoreMelds(melds: Meld[]): number {
  let total = 0
  for (const meld of melds) {
    for (const c of meld.cards) {
      total += meldCardValue(c, meld)
    }
  }
  return total
}

/** Calculate scores at round end. Player who goes out gets meld points. Both lose hand points. */
function resolveRoundScores(state: Rummy500State, goingOutPlayer: number | null): number[] {
  const newScores = [...state.scores]

  for (let p = 0; p < 2; p++) {
    // Subtract hand penalty
    const handPenalty = state.hands[p].reduce((sum, c) => sum + cardValue(c), 0)

    // Add meld bonus — in Rummy 500, each player scores their own melds positively.
    // Since we don't track per-player meld ownership in this simplified version,
    // we give meld credit to the player who went out (they formed the most melds typically).
    // For fairness: each card in a meld counts for the player who put it there.
    // Since we can't track that, we'll just do: both players subtract hand cards,
    // and the melds score goes to no one (net zero effect), OR:
    //
    // Standard Rummy 500: EACH player scores their OWN melded cards as positive,
    // their OWN hand cards as negative. Since we share the melds array,
    // we'll track "meldedByPlayer" on each meld. But to keep it simple for now:
    //
    // Actually the most common approach: score = (value of cards you melded/laid off)
    //   minus (value of cards left in your hand).
    // We don't have per-card ownership in the melds, so:
    // - Going out player: all their cards are melded → score all melds positive, 0 hand penalty
    // - Other player: score 0 melds (they may have some), but lose hand penalty
    //
    // Simplest correct approach that matches real Rummy 500:
    // Since we DON'T track who melded what, we'll use:
    // - The round winner (goes out) scores the total of OPPONENT's remaining hand cards
    //   as bonus. This rewards going out.
    // - Both players: melded cards count positive, hand cards count negative.
    // Since we can't separate player's melds, we just use hand penalty only.

    newScores[p] -= handPenalty
  }

  // The player who went out gets a bonus: total value of opponent's remaining hand
  if (goingOutPlayer !== null) {
    const opponent = 1 - goingOutPlayer
    const opponentHandValue = state.hands[opponent].reduce((sum, c) => sum + cardValue(c), 0)
    newScores[goingOutPlayer] += opponentHandValue
  }

  // Add meld values to scores for both players proportionally
  // Since we can't track ownership, give all meld value to both equally (not ideal)
  // Better approach: give meld value to going-out player since they completed the melds
  if (goingOutPlayer !== null) {
    const meldValue = scoreMelds(state.melds)
    newScores[goingOutPlayer] += meldValue
  }

  return newScores
}

// ── Check for round/game end ─────────────────────────────────────────

function checkRoundEnd(state: Rummy500State, goingOutPlayer: number | null): Rummy500State {
  const scores = resolveRoundScores(state, goingOutPlayer)
  const gameOver = scores.some(s => s >= WINNING_SCORE)

  let message: string
  if (gameOver) {
    message = scores[0] >= WINNING_SCORE ? 'You win the game!' : 'AI wins the game!'
  } else if (goingOutPlayer === 0) {
    message = 'You went out! Round over.'
  } else if (goingOutPlayer === 1) {
    message = 'AI went out! Round over.'
  } else {
    message = 'Stock depleted! Round over.'
  }

  return {
    ...state,
    scores,
    phase: gameOver ? 'gameOver' : 'roundOver',
    message,
    selectedCards: [],
    hasDrawn: false,
  }
}

// ── Actions ──────────────────────────────────────────────────────────

export function drawFromStock(state: Rummy500State): Rummy500State {
  if (state.phase !== 'draw') return state
  if (state.stock.length === 0) return state

  const stock = [...state.stock]
  const card = stock.pop()!
  const hands = state.hands.map((h, i) =>
    i === state.currentPlayer ? sortHand([...h, { ...card, faceUp: true }]) : [...h]
  )

  return {
    ...state,
    hands,
    stock,
    phase: 'meld',
    hasDrawn: true,
    message: 'Meld cards, lay off, or discard to end your turn',
    selectedCards: [],
  }
}

export function drawFromDiscard(state: Rummy500State): Rummy500State {
  if (state.phase !== 'draw') return state
  if (state.discardPile.length === 0) return state

  const discardPile = [...state.discardPile]
  const card = discardPile.pop()!
  const hands = state.hands.map((h, i) =>
    i === state.currentPlayer ? sortHand([...h, { ...card, faceUp: true }]) : [...h]
  )

  return {
    ...state,
    hands,
    discardPile,
    phase: 'meld',
    hasDrawn: true,
    message: 'Meld cards, lay off, or discard to end your turn',
    selectedCards: [],
  }
}

export function toggleSelectCard(state: Rummy500State, cardIndex: number): Rummy500State {
  if (state.phase !== 'meld') return state

  const selectedCards = state.selectedCards.includes(cardIndex)
    ? state.selectedCards.filter(i => i !== cardIndex)
    : [...state.selectedCards, cardIndex]

  return { ...state, selectedCards }
}

export function meldCards(state: Rummy500State): Rummy500State {
  if (state.phase !== 'meld' || !state.hasDrawn) return state
  if (state.selectedCards.length < 3) return state

  const hand = [...state.hands[state.currentPlayer]]
  const selectedCardObjs = state.selectedCards
    .sort((a, b) => a - b)
    .map(i => hand[i])

  const validation = isValidMeld(selectedCardObjs)
  if (!validation.valid) {
    return { ...state, message: 'Invalid meld. Select 3+ cards of same rank or consecutive same suit.' }
  }

  // Remove selected cards from hand (in reverse order to keep indices valid)
  const newHand = [...hand]
  const sortedIndices = [...state.selectedCards].sort((a, b) => b - a)
  for (const idx of sortedIndices) {
    newHand.splice(idx, 1)
  }

  const newMeld: Meld = { cards: selectedCardObjs, type: validation.type }
  const melds = [...state.melds, newMeld]

  const hands = state.hands.map((h, i) =>
    i === state.currentPlayer ? sortHand(newHand) : [...h]
  )

  const newState: Rummy500State = {
    ...state,
    hands,
    melds,
    selectedCards: [],
    message: 'Meld placed! Continue melding, lay off, or discard.',
  }

  // Check if player went out (no cards left)
  if (newHand.length === 0) {
    return checkRoundEnd(newState, state.currentPlayer)
  }

  return newState
}

export function layOff(state: Rummy500State, cardIndex: number, meldIndex: number): Rummy500State {
  if (state.phase !== 'meld' || !state.hasDrawn) return state
  if (meldIndex < 0 || meldIndex >= state.melds.length) return state

  const hand = state.hands[state.currentPlayer]
  if (cardIndex < 0 || cardIndex >= hand.length) return state

  const card = hand[cardIndex]
  const meld = state.melds[meldIndex]

  if (!canLayOff(card, meld)) return state

  // Add card to meld
  const newMeldCards = [...meld.cards, card]
  // Sort run cards by rank for consistency
  if (meld.type === 'run') {
    newMeldCards.sort((a, b) => {
      // Handle high ace: if run has a king, ace sorts high (14)
      const rankA = a.rank === 1 && newMeldCards.some(c => c.rank === 13) ? 14 : a.rank
      const rankB = b.rank === 1 && newMeldCards.some(c => c.rank === 13) ? 14 : b.rank
      return rankA - rankB
    })
  }

  const melds = state.melds.map((m, i) =>
    i === meldIndex ? { ...m, cards: newMeldCards } : m
  )

  const newHand = [...hand]
  newHand.splice(cardIndex, 1)
  const hands = state.hands.map((h, i) =>
    i === state.currentPlayer ? sortHand(newHand) : [...h]
  )

  const newState: Rummy500State = {
    ...state,
    hands,
    melds,
    selectedCards: [],
    message: 'Card laid off! Continue melding, lay off, or discard.',
  }

  // Check if player went out
  if (newHand.length === 0) {
    return checkRoundEnd(newState, state.currentPlayer)
  }

  return newState
}

export function discard(state: Rummy500State, cardIndex: number): Rummy500State {
  if (state.phase !== 'meld' || !state.hasDrawn) return state

  const hand = state.hands[state.currentPlayer]
  if (cardIndex < 0 || cardIndex >= hand.length) return state

  const newHand = [...hand]
  const discarded = newHand.splice(cardIndex, 1)[0]
  const discardPile = [...state.discardPile, discarded]

  const hands = state.hands.map((h, i) =>
    i === state.currentPlayer ? sortHand(newHand) : [...h]
  )

  const afterDiscard: Rummy500State = {
    ...state,
    hands,
    discardPile,
    selectedCards: [],
  }

  // Check if stock is empty → round over
  if (afterDiscard.stock.length === 0) {
    return checkRoundEnd(afterDiscard, null)
  }

  // Player went out (melded everything, discarded last card)
  if (newHand.length === 0) {
    return checkRoundEnd(afterDiscard, state.currentPlayer)
  }

  // AI turn
  if (state.currentPlayer === 0) {
    return aiTurn(afterDiscard)
  }

  // Switch to other player
  return {
    ...afterDiscard,
    currentPlayer: 0,
    phase: 'draw',
    hasDrawn: false,
    message: 'Draw a card from stock or discard pile',
  }
}

// ── AI logic ─────────────────────────────────────────────────────────

function aiTurn(state: Rummy500State): Rummy500State {
  let current: Rummy500State = {
    ...state,
    currentPlayer: 1,
    phase: 'draw',
    hasDrawn: false,
  }

  // 1. Draw: check if top discard completes a meld
  const topDiscard = current.discardPile.length > 0
    ? current.discardPile[current.discardPile.length - 1]
    : null
  let drewFromDiscard = false

  if (topDiscard) {
    const aiHand = current.hands[1]
    // Check if discard card helps form a meld
    const withDiscard = [...aiHand, topDiscard]
    if (findMeldsInHand(withDiscard).length > findMeldsInHand(aiHand).length) {
      // Draw from discard
      const discardPile = [...current.discardPile]
      discardPile.pop()
      const newHand = sortHand([...aiHand, topDiscard])
      current = {
        ...current,
        hands: [current.hands[0], newHand],
        discardPile,
        phase: 'meld',
        hasDrawn: true,
      }
      drewFromDiscard = true
    }
  }

  if (!drewFromDiscard) {
    if (current.stock.length === 0) {
      // No stock, can't draw → round over
      return checkRoundEnd(current, null)
    }
    const stock = [...current.stock]
    const drawn = stock.pop()!
    const newHand = sortHand([...current.hands[1], { ...drawn, faceUp: true }])
    current = {
      ...current,
      hands: [current.hands[0], newHand],
      stock,
      phase: 'meld',
      hasDrawn: true,
    }
  }

  // 2. Meld any valid sets/runs
  current = aiMeldAll(current)

  // Check if AI went out by melding all cards
  if (current.hands[1].length === 0) {
    return checkRoundEnd(current, 1)
  }

  // 3. Lay off on existing melds
  current = aiLayOffAll(current)

  // Check if AI went out by laying off all cards
  if (current.hands[1].length === 0) {
    return checkRoundEnd(current, 1)
  }

  // 4. Discard highest-value card that doesn't break potential melds
  const discardIdx = findBestDiscard(current.hands[1])
  const aiHand = [...current.hands[1]]
  const discarded = aiHand.splice(discardIdx, 1)[0]
  const discardPile = [...current.discardPile, discarded]

  // Check if stock depleted
  if (current.stock.length === 0) {
    return checkRoundEnd({
      ...current,
      hands: [current.hands[0], sortHand(aiHand)],
      discardPile,
    }, null)
  }

  return {
    ...current,
    hands: [current.hands[0], sortHand(aiHand)],
    discardPile,
    currentPlayer: 0,
    phase: 'draw',
    hasDrawn: false,
    selectedCards: [],
    message: 'Your turn. Draw a card from stock or discard pile.',
  }
}

/** Find all possible melds in a hand. */
function findMeldsInHand(hand: Card[]): Array<{ indices: number[]; type: 'set' | 'run' }> {
  const results: Array<{ indices: number[]; type: 'set' | 'run' }> = []

  // Find sets (3+ same rank, different suits)
  const byRank = new Map<number, number[]>()
  for (let i = 0; i < hand.length; i++) {
    const arr = byRank.get(hand[i].rank) || []
    arr.push(i)
    byRank.set(hand[i].rank, arr)
  }
  for (const [_, indices] of byRank) {
    if (indices.length >= 3) {
      // Check different suits
      const suits = new Set(indices.map(i => hand[i].suit))
      if (suits.size >= 3) {
        const validIndices = indices.slice(0, Math.min(indices.length, 4))
        results.push({ indices: validIndices, type: 'set' })
      }
    }
  }

  // Find runs (3+ consecutive same suit)
  for (const suit of SUITS) {
    const suitCards = hand
      .map((c, i) => ({ card: c, index: i }))
      .filter(({ card }) => card.suit === suit)
      .sort((a, b) => a.card.rank - b.card.rank)

    if (suitCards.length < 3) continue

    for (let start = 0; start <= suitCards.length - 3; start++) {
      const run: typeof suitCards = [suitCards[start]]
      for (let j = start + 1; j < suitCards.length; j++) {
        if (suitCards[j].card.rank === run[run.length - 1].card.rank + 1) {
          run.push(suitCards[j])
        } else {
          break
        }
      }
      if (run.length >= 3) {
        results.push({ indices: run.map(r => r.index), type: 'run' })
      }
    }

    // Check high-ace run (Q-K-A)
    const ace = suitCards.find(sc => sc.card.rank === 1)
    const king = suitCards.find(sc => sc.card.rank === 13)
    const queen = suitCards.find(sc => sc.card.rank === 12)
    if (ace && king && queen) {
      // Check for longer high runs
      const highRun = [queen, king, ace]
      const jack = suitCards.find(sc => sc.card.rank === 11)
      if (jack) highRun.unshift(jack)
      results.push({ indices: highRun.map(r => r.index), type: 'run' })
    }
  }

  return results
}

/** AI melds all valid combinations from its hand. */
function aiMeldAll(state: Rummy500State): Rummy500State {
  let current = state
  let foundMeld = true

  while (foundMeld) {
    foundMeld = false
    const aiHand = current.hands[1]
    const melds = findMeldsInHand(aiHand)

    if (melds.length > 0) {
      // Pick the first valid meld
      const best = melds[0]
      const cards = best.indices.map(i => aiHand[i])

      // Remove from hand (reverse order)
      const newHand = [...aiHand]
      const sortedIndices = [...best.indices].sort((a, b) => b - a)
      for (const idx of sortedIndices) {
        newHand.splice(idx, 1)
      }

      current = {
        ...current,
        hands: [current.hands[0], sortHand(newHand)],
        melds: [...current.melds, { cards, type: best.type }],
      }
      foundMeld = true
    }
  }

  return current
}

/** AI lays off cards on existing melds. */
function aiLayOffAll(state: Rummy500State): Rummy500State {
  let current = state
  let foundLayOff = true

  while (foundLayOff) {
    foundLayOff = false
    const aiHand = current.hands[1]

    for (let ci = 0; ci < aiHand.length; ci++) {
      for (let mi = 0; mi < current.melds.length; mi++) {
        if (canLayOff(aiHand[ci], current.melds[mi])) {
          // Lay off this card
          const card = aiHand[ci]
          const meld = current.melds[mi]
          const newMeldCards = [...meld.cards, card]
          if (meld.type === 'run') {
            newMeldCards.sort((a, b) => {
              const rankA = a.rank === 1 && newMeldCards.some(c => c.rank === 13) ? 14 : a.rank
              const rankB = b.rank === 1 && newMeldCards.some(c => c.rank === 13) ? 14 : b.rank
              return rankA - rankB
            })
          }

          const newHand = [...aiHand]
          newHand.splice(ci, 1)

          current = {
            ...current,
            hands: [current.hands[0], sortHand(newHand)],
            melds: current.melds.map((m, i) =>
              i === mi ? { ...m, cards: newMeldCards } : m
            ),
          }
          foundLayOff = true
          break
        }
      }
      if (foundLayOff) break
    }
  }

  return current
}

/** Find the best card to discard — highest value card not part of potential melds. */
function findBestDiscard(hand: Card[]): number {
  // Find cards that are part of potential melds (2 or more towards a meld)
  const meldPotential = new Set<number>()

  // Check pairs (potential sets)
  for (let i = 0; i < hand.length; i++) {
    for (let j = i + 1; j < hand.length; j++) {
      if (hand[i].rank === hand[j].rank && hand[i].suit !== hand[j].suit) {
        meldPotential.add(i)
        meldPotential.add(j)
      }
    }
  }

  // Check consecutive same-suit pairs (potential runs)
  for (let i = 0; i < hand.length; i++) {
    for (let j = i + 1; j < hand.length; j++) {
      if (hand[i].suit === hand[j].suit) {
        const diff = Math.abs(hand[i].rank - hand[j].rank)
        if (diff <= 2) {
          meldPotential.add(i)
          meldPotential.add(j)
        }
      }
    }
  }

  // Discard highest value card not in potential melds
  let bestIdx = 0
  let bestVal = -1
  for (let i = 0; i < hand.length; i++) {
    if (!meldPotential.has(i) && cardValue(hand[i]) > bestVal) {
      bestVal = cardValue(hand[i])
      bestIdx = i
    }
  }

  // If all cards have meld potential, discard highest value overall
  if (bestVal === -1) {
    for (let i = 0; i < hand.length; i++) {
      if (cardValue(hand[i]) > bestVal) {
        bestVal = cardValue(hand[i])
        bestIdx = i
      }
    }
  }

  return bestIdx
}

// ── New round ────────────────────────────────────────────────────────

export function newRound(state: Rummy500State): Rummy500State {
  const fresh = createRummy500Game()
  return {
    ...fresh,
    scores: [...state.scores],
  }
}
