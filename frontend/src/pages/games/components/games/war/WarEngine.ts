/**
 * War card game engine — pure logic, no side effects.
 *
 * Rules:
 * - 52-card deck split evenly (26 each)
 * - Each round: both flip top card, higher rank wins both
 * - Tie → War: 3 face-down + 1 face-up each, highest face-up wins all
 * - If a player can't complete a war (< 4 cards), they lose
 * - Game over when one player has 0 cards or after maxRounds
 * - Ace high (rank 1 compares as 14)
 */

import { createDeck, shuffleDeck, type Card } from '../../../utils/cardUtils'

// ── Types ───────────────────────────────────────────────────────────

export type Phase = 'ready' | 'compare' | 'war' | 'gameOver'

export interface WarState {
  playerDeck: Card[]
  aiDeck: Card[]
  playerCard: Card | null
  aiCard: Card | null
  warPile: Card[]
  phase: Phase
  message: string
  round: number
  maxRounds: number
  playerScore: number
  aiScore: number
}

// ── Helpers ─────────────────────────────────────────────────────────

/** Ace (rank 1) = 14 for comparison, otherwise rank value. */
export function getCompareValue(card: Card): number {
  return card.rank === 1 ? 14 : card.rank
}

function checkGameOver(state: WarState): WarState {
  if (state.playerDeck.length === 0 && state.playerCard === null) {
    return { ...state, phase: 'gameOver', message: 'AI wins — you ran out of cards!' }
  }
  if (state.aiDeck.length === 0 && state.aiCard === null) {
    return { ...state, phase: 'gameOver', message: 'You win — AI ran out of cards!' }
  }
  if (state.round >= state.maxRounds) {
    const pCount = state.playerDeck.length
    const aCount = state.aiDeck.length
    if (pCount > aCount) return { ...state, phase: 'gameOver', message: `You win ${pCount}-${aCount} after ${state.maxRounds} rounds!` }
    if (aCount > pCount) return { ...state, phase: 'gameOver', message: `AI wins ${aCount}-${pCount} after ${state.maxRounds} rounds!` }
    return { ...state, phase: 'gameOver', message: `Draw! Both have ${pCount} cards after ${state.maxRounds} rounds.` }
  }
  return state
}

// ── Engine functions ────────────────────────────────────────────────

/** Create a new War game: shuffle deck, split evenly. */
export function createWarGame(): WarState {
  const deck = shuffleDeck(createDeck())
  return {
    playerDeck: deck.slice(0, 26),
    aiDeck: deck.slice(26),
    playerCard: null,
    aiCard: null,
    warPile: [],
    phase: 'ready',
    message: 'Flip cards to start!',
    round: 0,
    maxRounds: 200,
    playerScore: 0,
    aiScore: 0,
  }
}

/** Both players flip their top card. */
export function flipCards(state: WarState): WarState {
  if (state.phase !== 'ready') return state

  const playerDeck = [...state.playerDeck]
  const aiDeck = [...state.aiDeck]
  const playerCard = { ...playerDeck.shift()!, faceUp: true }
  const aiCard = { ...aiDeck.shift()!, faceUp: true }

  return {
    ...state,
    playerDeck,
    aiDeck,
    playerCard,
    aiCard,
    warPile: [],
    phase: 'compare',
    round: state.round + 1,
    message: 'Compare cards!',
  }
}

/** Compare the two flipped cards. Winner takes both (or start war on tie). */
export function resolveCompare(state: WarState): WarState {
  if (state.phase !== 'compare') return state
  if (!state.playerCard || !state.aiCard) return state

  const pVal = getCompareValue(state.playerCard)
  const aVal = getCompareValue(state.aiCard)

  if (pVal === aVal) {
    // Tie → war
    return {
      ...state,
      phase: 'war',
      message: 'War! Cards are tied!',
    }
  }

  const cardsWon = [state.playerCard, state.aiCard, ...state.warPile]
  const playerWins = pVal > aVal

  const next: WarState = {
    ...state,
    playerDeck: playerWins ? [...state.playerDeck, ...cardsWon] : [...state.playerDeck],
    aiDeck: playerWins ? [...state.aiDeck] : [...state.aiDeck, ...cardsWon],
    playerCard: null,
    aiCard: null,
    warPile: [],
    phase: 'ready',
    playerScore: playerWins ? state.playerScore + cardsWon.length : state.playerScore,
    aiScore: playerWins ? state.aiScore : state.aiScore + cardsWon.length,
    message: playerWins
      ? `You win this round! (+${cardsWon.length} cards)`
      : `AI wins this round! (+${cardsWon.length} cards)`,
  }

  return checkGameOver(next)
}

/** Resolve a war: 3 face-down + 1 face-up each. Handles nested wars on ties. */
export function resolveWar(state: WarState): WarState {
  if (state.phase !== 'war') return state
  if (!state.playerCard || !state.aiCard) return state

  let playerDeck = [...state.playerDeck]
  let aiDeck = [...state.aiDeck]
  let warPile = [state.playerCard, state.aiCard, ...state.warPile]

  // Loop to handle nested wars (tie during war)
  while (true) {
    // Check if either player has enough cards for war (need 4: 3 face-down + 1 face-up)
    if (playerDeck.length < 4) {
      // Player can't complete war — AI wins
      return {
        ...state,
        playerDeck: [],
        aiDeck: [...aiDeck, ...warPile, ...playerDeck],
        playerCard: null,
        aiCard: null,
        warPile: [],
        phase: 'gameOver',
        message: 'AI wins — you couldn\'t complete the war!',
      }
    }
    if (aiDeck.length < 4) {
      // AI can't complete war — player wins
      return {
        ...state,
        playerDeck: [...playerDeck, ...warPile, ...aiDeck],
        aiDeck: [],
        playerCard: null,
        aiCard: null,
        warPile: [],
        phase: 'gameOver',
        message: 'You win — AI couldn\'t complete the war!',
      }
    }

    // Each player puts 3 face-down
    const pFaceDown = playerDeck.splice(0, 3)
    const aFaceDown = aiDeck.splice(0, 3)
    warPile.push(...pFaceDown, ...aFaceDown)

    // Each player flips 1 face-up
    const pCard = { ...playerDeck.shift()!, faceUp: true }
    const aCard = { ...aiDeck.shift()!, faceUp: true }

    const pVal = getCompareValue(pCard)
    const aVal = getCompareValue(aCard)

    if (pVal === aVal) {
      // Another tie — add these to war pile and loop
      warPile.push(pCard, aCard)
      continue
    }

    // We have a winner
    const allCards = [...warPile, pCard, aCard]
    const playerWins = pVal > aVal

    const next: WarState = {
      ...state,
      playerDeck: playerWins ? [...playerDeck, ...allCards] : [...playerDeck],
      aiDeck: playerWins ? [...aiDeck] : [...aiDeck, ...allCards],
      playerCard: null,
      aiCard: null,
      warPile: [],
      phase: 'ready',
      playerScore: playerWins ? state.playerScore + allCards.length : state.playerScore,
      aiScore: playerWins ? state.aiScore : state.aiScore + allCards.length,
      message: playerWins
        ? `You win the war! (+${allCards.length} cards)`
        : `AI wins the war! (+${allCards.length} cards)`,
    }

    return checkGameOver(next)
  }
}
