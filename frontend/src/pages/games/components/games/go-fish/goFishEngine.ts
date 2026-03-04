import { createDeck, shuffleDeck, type Card } from '../../../utils/cardUtils'
import { getRankDisplay } from '../../../utils/cardUtils'

export type Phase = 'playerTurn' | 'aiTurn' | 'goFish' | 'gameOver'

export interface GoFishState {
  hands: Card[][]        // [0] = human, [1] = AI
  books: number[][]      // [0] = human books (rank numbers), [1] = AI books
  pond: Card[]
  phase: Phase
  currentPlayer: number  // 0 = human, 1 = AI
  message: string
  lastAskedRank: number | null
  drawnCard: Card | null // card drawn during Go Fish (for UI highlight)
  aiMemory: number[]     // ranks the human has asked for
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Count occurrences of each rank in a hand. */
function rankCounts(hand: Card[]): Map<number, number> {
  const counts = new Map<number, number>()
  for (const c of hand) {
    counts.set(c.rank, (counts.get(c.rank) ?? 0) + 1)
  }
  return counts
}

/** Check if the game should end: all 13 books made, or pond empty + a player has no cards. */
function isGameOver(state: GoFishState): boolean {
  const totalBooks = state.books[0].length + state.books[1].length
  if (totalBooks >= 13) return true
  if (state.pond.length === 0 && (state.hands[0].length === 0 || state.hands[1].length === 0)) return true
  return false
}

/** Build the game-over message. */
function gameOverMessage(state: GoFishState): string {
  const p0 = state.books[0].length
  const p1 = state.books[1].length
  if (p0 > p1) return `You win with ${p0} books to ${p1}!`
  if (p1 > p0) return `AI wins with ${p1} books to ${p0}.`
  return `It's a tie — ${p0} books each!`
}

/** Apply book checking to a player's hand and book list, returning updated state. */
function applyBookCheck(state: GoFishState, player: number): GoFishState {
  const { hand, newBooks } = checkForBooks(state.hands[player])
  if (newBooks.length === 0) return state
  const hands = state.hands.map((h, i) => (i === player ? hand : h))
  const books = state.books.map((b, i) => (i === player ? [...b, ...newBooks] : b))
  const next: GoFishState = { ...state, hands, books }
  if (isGameOver(next)) {
    return { ...next, phase: 'gameOver', message: gameOverMessage(next) }
  }
  return next
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Create a new Go Fish game with 7 cards dealt to each player. */
export function createGoFishGame(): GoFishState {
  const deck = shuffleDeck(createDeck())
  const humanHand = deck.slice(0, 7).map(c => ({ ...c, faceUp: true }))
  const aiHand = deck.slice(7, 14).map(c => ({ ...c, faceUp: false }))
  const pond = deck.slice(14)

  return {
    hands: [humanHand, aiHand],
    books: [[], []],
    pond,
    phase: 'playerTurn',
    currentPlayer: 0,
    message: 'Your turn — tap a card to ask for that rank.',
    lastAskedRank: null,
    drawnCard: null,
    aiMemory: [],
  }
}

/**
 * Human asks the AI for a specific rank.
 * If AI has cards of that rank, they transfer and human gets another turn.
 * Otherwise, transition to goFish phase.
 */
export function askForRank(state: GoFishState, rank: number): GoFishState {
  if (state.phase !== 'playerTurn') return state

  // Guard: human must hold the rank
  const hasRank = state.hands[0].some(c => c.rank === rank)
  if (!hasRank) return state

  const rankName = getRankDisplay(rank)

  // Track in AI memory
  const aiMemory = state.aiMemory.includes(rank) ? state.aiMemory : [...state.aiMemory, rank]

  // Check if AI has cards of that rank
  const aiMatches = state.hands[1].filter(c => c.rank === rank)
  if (aiMatches.length > 0) {
    // Transfer cards to human (make them faceUp)
    const transferred = aiMatches.map(c => ({ ...c, faceUp: true }))
    const newHumanHand = [...state.hands[0], ...transferred]
    const newAiHand = state.hands[1].filter(c => c.rank !== rank)
    let next: GoFishState = {
      ...state,
      hands: [newHumanHand, newAiHand],
      phase: 'playerTurn',
      currentPlayer: 0,
      message: `You got ${aiMatches.length} ${rankName}${aiMatches.length > 1 ? 's' : ''} from AI! Go again.`,
      lastAskedRank: null,
      drawnCard: null,
      aiMemory,
    }
    next = applyBookCheck(next, 0)
    // If hand is empty after books but game not over, and pond has cards, draw
    if (next.phase !== 'gameOver' && next.hands[0].length === 0 && next.pond.length > 0) {
      const drawn = { ...next.pond[0], faceUp: true }
      next = { ...next, hands: [[drawn], next.hands[1]], pond: next.pond.slice(1) }
      next = applyBookCheck(next, 0)
    }
    if (next.phase !== 'gameOver' && next.hands[0].length === 0) {
      return { ...next, phase: 'aiTurn', currentPlayer: 1, message: 'You have no cards. AI\'s turn.' }
    }
    return next
  }

  // AI doesn't have the rank — Go Fish
  return {
    ...state,
    phase: 'goFish',
    lastAskedRank: rank,
    drawnCard: null,
    message: `AI says "Go Fish!" — draw a card from the pond.`,
    aiMemory,
  }
}

/**
 * Draw a card from the pond after a failed ask.
 * If drawn card matches the asked rank, player gets another turn.
 */
export function goFish(state: GoFishState): GoFishState {
  if (state.phase !== 'goFish') return state

  const player = state.currentPlayer

  // Empty pond — pass turn or end game
  if (state.pond.length === 0) {
    if (isGameOver(state)) {
      return { ...state, phase: 'gameOver', message: gameOverMessage(state) }
    }
    const nextPlayer = 1 - player
    const nextPhase: Phase = nextPlayer === 0 ? 'playerTurn' : 'aiTurn'
    return { ...state, phase: nextPhase, currentPlayer: nextPlayer, message: 'Pond is empty! Turn passes.' }
  }

  // Draw top card from pond
  const drawnCard = { ...state.pond[0], faceUp: player === 0 }
  const newPond = state.pond.slice(1)
  const newHands = state.hands.map((h, i) => (i === player ? [...h, drawnCard] : h))

  const rankName = getRankDisplay(drawnCard.rank)
  const matchedAsk = drawnCard.rank === state.lastAskedRank

  let next: GoFishState = {
    ...state,
    hands: newHands,
    pond: newPond,
    drawnCard,
    lastAskedRank: null,
  }

  // Check for books after drawing
  next = applyBookCheck(next, player)
  if (next.phase === 'gameOver') return next

  if (matchedAsk) {
    // Lucky draw — same player goes again
    const phase: Phase = player === 0 ? 'playerTurn' : 'aiTurn'
    const msg = player === 0
      ? `You drew ${rankName} — that's what you asked for! Go again.`
      : `AI drew what it asked for! AI goes again.`
    next = { ...next, phase, currentPlayer: player, message: msg }
  } else {
    // Turn passes
    const nextPlayer = 1 - player
    const phase: Phase = nextPlayer === 0 ? 'playerTurn' : 'aiTurn'
    const msg = player === 0
      ? `You drew a ${rankName}. AI's turn.`
      : `AI drew a card. Your turn!`
    next = { ...next, phase, currentPlayer: nextPlayer, message: msg }
  }

  // Handle empty hand after drawing (books may have emptied it)
  if (next.hands[next.currentPlayer].length === 0 && next.pond.length > 0 && next.phase !== 'gameOver') {
    const drawn2 = { ...next.pond[0], faceUp: next.currentPlayer === 0 }
    const hands2 = next.hands.map((h, i) => (i === next.currentPlayer ? [drawn2] : h))
    next = { ...next, hands: hands2, pond: next.pond.slice(1) }
    next = applyBookCheck(next, next.currentPlayer)
  }

  if (isGameOver(next)) {
    return { ...next, phase: 'gameOver', message: gameOverMessage(next) }
  }

  return next
}

/**
 * AI takes its turn: picks a rank, asks the human, handles the result.
 * Loops for consecutive turns (successful asks / lucky draws).
 */
export function aiTurn(state: GoFishState): GoFishState {
  if (state.phase !== 'aiTurn') return state

  let current = { ...state }
  let iterations = 0
  const maxIterations = 52 // safety valve

  while (current.phase === 'aiTurn' && iterations < maxIterations) {
    iterations++

    // If AI hand is empty and pond has cards, draw one
    if (current.hands[1].length === 0) {
      if (current.pond.length > 0) {
        const drawn = { ...current.pond[0], faceUp: false }
        current = {
          ...current,
          hands: [current.hands[0], [drawn]],
          pond: current.pond.slice(1),
        }
        current = applyBookCheck(current, 1)
        if (current.phase === 'gameOver') return current
      } else {
        // No cards and no pond — game should be over
        if (isGameOver(current)) {
          return { ...current, phase: 'gameOver', message: gameOverMessage(current) }
        }
        return { ...current, phase: 'playerTurn', currentPlayer: 0, message: 'AI has no cards. Your turn!' }
      }
    }

    const chosenRank = aiChooseRank(current)
    if (chosenRank === null) {
      // AI has no cards to ask about
      return { ...current, phase: 'playerTurn', currentPlayer: 0, message: 'Your turn!' }
    }

    const rankName = getRankDisplay(chosenRank)

    // Check if human has the rank
    const humanMatches = current.hands[0].filter(c => c.rank === chosenRank)
    if (humanMatches.length > 0) {
      // Transfer cards to AI (make them faceDown)
      const transferred = humanMatches.map(c => ({ ...c, faceUp: false }))
      const newAiHand = [...current.hands[1], ...transferred]
      const newHumanHand = current.hands[0].filter(c => c.rank !== chosenRank)
      current = {
        ...current,
        hands: [newHumanHand, newAiHand],
        phase: 'aiTurn',
        currentPlayer: 1,
        message: `AI asked for ${rankName}s and got ${humanMatches.length}! AI goes again.`,
        drawnCard: null,
      }
      current = applyBookCheck(current, 1)
      if (current.phase === 'gameOver') return current
      // AI gets another turn — loop continues
      current = { ...current, phase: 'aiTurn' }
    } else {
      // Human doesn't have it — AI goes fishing
      current = { ...current, message: `AI asked for ${rankName}s. You say "Go Fish!"` }
      if (current.pond.length === 0) {
        if (isGameOver(current)) {
          return { ...current, phase: 'gameOver', message: gameOverMessage(current) }
        }
        return { ...current, phase: 'playerTurn', currentPlayer: 0, message: `AI asked for ${rankName}s. Pond is empty! Your turn.` }
      }
      // AI draws from pond
      const drawnCard = { ...current.pond[0], faceUp: false }
      const newPond = current.pond.slice(1)
      const newAiHand = [...current.hands[1], drawnCard]
      current = {
        ...current,
        hands: [current.hands[0], newAiHand],
        pond: newPond,
        drawnCard: null,
      }
      current = applyBookCheck(current, 1)
      if (current.phase === 'gameOver') return current

      if (drawnCard.rank === chosenRank) {
        // Lucky draw — AI goes again
        current = { ...current, phase: 'aiTurn', currentPlayer: 1, message: `AI asked for ${rankName}s, fished, and got lucky! AI goes again.` }
      } else {
        // Turn passes to human
        current = { ...current, phase: 'playerTurn', currentPlayer: 0, message: `AI asked for ${rankName}s and fished. Your turn!` }
      }
    }
  }

  return current
}

/**
 * Extract completed books (4 of a kind) from a hand.
 * Returns the remaining hand and list of newly completed book ranks.
 */
export function checkForBooks(hand: Card[]): { hand: Card[]; newBooks: number[] } {
  const counts = rankCounts(hand)
  const newBooks: number[] = []
  for (const [rank, count] of counts) {
    if (count >= 4) {
      newBooks.push(rank)
    }
  }
  if (newBooks.length === 0) return { hand, newBooks: [] }
  const remaining = hand.filter(c => !newBooks.includes(c.rank))
  return { hand: remaining, newBooks }
}

/** Get the ranks in the human player's hand that they can ask for. */
export function getAskableRanks(state: GoFishState): number[] {
  const seen = new Set<number>()
  for (const c of state.hands[0]) {
    seen.add(c.rank)
  }
  return Array.from(seen)
}

// ---------------------------------------------------------------------------
// AI Strategy
// ---------------------------------------------------------------------------

/** AI picks a rank to ask for based on strategy + memory. */
function aiChooseRank(state: GoFishState): number | null {
  const aiHand = state.hands[1]
  if (aiHand.length === 0) return null

  const counts = rankCounts(aiHand)
  const ranks = Array.from(counts.keys())

  // Priority 1: ranks with 3 cards (close to a book)
  const threes = ranks.filter(r => counts.get(r)! >= 3)
  if (threes.length > 0) return threes[0]

  // Priority 2: ranks with 2 cards
  const twos = ranks.filter(r => counts.get(r)! === 2)
  if (twos.length > 0) return twos[0]

  // Priority 3: ranks the human has asked for (from memory) that AI also holds
  const remembered = state.aiMemory.filter(r => counts.has(r))
  if (remembered.length > 0) return remembered[0]

  // Priority 4: random from hand
  return ranks[Math.floor(Math.random() * ranks.length)]
}
