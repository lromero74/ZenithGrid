import { createDeck, shuffleDeck, type Card } from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

export type Phase = 'play' | 'challenge' | 'reveal' | 'gameOver'

export interface LastPlay {
  player: number
  cards: Card[]
  claimedRank: number
  claimedCount: number
}

export interface CheatState {
  hands: Card[][]
  pile: Card[]
  currentPlayer: number
  requiredRank: number       // 1-13, cycling A→2→...→K→A
  lastPlay: LastPlay | null
  phase: Phase
  playerCount: number
  winner: number | null
  challengeResult: 'honest' | 'bluff' | null
  challengedBy: number | null
  passedPlayers: number[]
}

// ── Helpers ──────────────────────────────────────────────────────────

/** Advance rank: A→2→3→...→K→A */
export function nextRank(rank: number): number {
  return rank >= 13 ? 1 : rank + 1
}

// ── Core API ─────────────────────────────────────────────────────────

/** Create a new Cheat game, dealing 52 cards evenly among players. */
export function createCheatGame(playerCount: number = 4): CheatState {
  const deck = shuffleDeck(createDeck())
  const hands: Card[][] = Array.from({ length: playerCount }, () => [])

  for (let i = 0; i < deck.length; i++) {
    hands[i % playerCount].push({ ...deck[i], faceUp: true })
  }

  return {
    hands,
    pile: [],
    currentPlayer: 0,
    requiredRank: 1, // start with Ace
    lastPlay: null,
    phase: 'play',
    playerCount,
    winner: null,
    challengeResult: null,
    challengedBy: null,
    passedPlayers: [],
  }
}

/** Play 1-4 cards from current player's hand, claiming a rank. */
export function playCards(state: CheatState, cardIndices: number[], claimedRank: number): CheatState {
  if (state.phase !== 'play') return state
  if (cardIndices.length === 0 || cardIndices.length > 4) return state

  const player = state.currentPlayer
  const hand = state.hands[player]
  const sorted = [...cardIndices].sort((a, b) => b - a) // descending for safe removal
  const playedCards: Card[] = cardIndices.map(i => hand[i])

  const newHand = [...hand]
  for (const idx of sorted) {
    newHand.splice(idx, 1)
  }

  const newHands = state.hands.map((h, i) => (i === player ? newHand : h))
  const newPile = [...state.pile, ...playedCards.map(c => ({ ...c, faceUp: false }))]

  return {
    ...state,
    hands: newHands,
    pile: newPile,
    phase: 'challenge',
    lastPlay: {
      player,
      cards: playedCards,
      claimedRank,
      claimedCount: cardIndices.length,
    },
    challengeResult: null,
    challengedBy: null,
    passedPlayers: [],
  }
}

/** A player calls BS on the last play. */
export function callBS(state: CheatState, challengerIndex: number): CheatState {
  if (state.phase !== 'challenge') return state
  if (!state.lastPlay) return state
  if (state.lastPlay.player === challengerIndex) return state // can't challenge yourself

  const { cards, claimedRank } = state.lastPlay
  const wasHonest = cards.every(c => c.rank === claimedRank)

  return {
    ...state,
    phase: 'reveal',
    challengedBy: challengerIndex,
    challengeResult: wasHonest ? 'honest' : 'bluff',
  }
}

/** A player passes on challenging. If all non-playing players pass, advance turn. */
export function passChallenge(state: CheatState, playerIndex: number): CheatState {
  if (state.phase !== 'challenge') return state
  if (!state.lastPlay) return state

  const passed = [...state.passedPlayers, playerIndex]
  // All players except the one who played need to pass
  const needToPass = state.playerCount - 1
  if (passed.length >= needToPass) {
    // Everyone passed — advance to next player
    const nextPlayer = (state.lastPlay.player + 1) % state.playerCount
    // Check if player who played has emptied their hand
    if (state.hands[state.lastPlay.player].length === 0) {
      return {
        ...state,
        phase: 'gameOver',
        winner: state.lastPlay.player,
        passedPlayers: passed,
      }
    }
    return {
      ...state,
      phase: 'play',
      currentPlayer: nextPlayer,
      requiredRank: nextRank(state.requiredRank),
      lastPlay: null,
      passedPlayers: [],
    }
  }

  return { ...state, passedPlayers: passed }
}

/** Resolve a challenge: give pile to loser, advance turn. */
export function resolveChallenge(state: CheatState): CheatState {
  if (state.phase !== 'reveal') return state
  if (!state.lastPlay || state.challengedBy === null || !state.challengeResult) return state

  const loser = state.challengeResult === 'bluff' ? state.lastPlay.player : state.challengedBy
  const pileCards = state.pile.map(c => ({ ...c, faceUp: true }))

  const newHands = state.hands.map((h, i) =>
    i === loser ? [...h, ...pileCards] : [...h]
  )

  const nextPlayer = (state.lastPlay.player + 1) % state.playerCount

  // Check for winner (empty hand after resolution)
  const winnerIdx = newHands.findIndex(h => h.length === 0)

  if (winnerIdx !== -1) {
    return {
      ...state,
      hands: newHands,
      pile: [],
      phase: 'gameOver',
      winner: winnerIdx,
      currentPlayer: nextPlayer,
      requiredRank: nextRank(state.requiredRank),
    }
  }

  return {
    ...state,
    hands: newHands,
    pile: [],
    phase: 'play',
    currentPlayer: nextPlayer,
    requiredRank: nextRank(state.requiredRank),
    lastPlay: null,
    challengeResult: null,
    challengedBy: null,
    passedPlayers: [],
  }
}

// ── AI ───────────────────────────────────────────────────────────────

/** AI plays its turn: selects cards and claims the required rank. */
export function aiPlayTurn(state: CheatState): CheatState {
  if (state.phase !== 'play') return state

  const player = state.currentPlayer
  const hand = state.hands[player]
  const rank = state.requiredRank

  // Find cards matching the required rank
  const matchingIndices = hand
    .map((c, i) => (c.rank === rank ? i : -1))
    .filter(i => i !== -1)

  if (matchingIndices.length > 0) {
    // Play honest — play all matching cards (up to 4)
    const toPlay = matchingIndices.slice(0, 4)
    return playCards(state, toPlay, rank)
  }

  // Must bluff — play 1 random card
  const bluffCount = Math.min(1 + Math.floor(Math.random() * 2), hand.length) // 1-2 cards
  const indices: number[] = []
  const available = hand.map((_, i) => i)
  for (let i = 0; i < bluffCount; i++) {
    const pick = Math.floor(Math.random() * available.length)
    indices.push(available[pick])
    available.splice(pick, 1)
  }

  return playCards(state, indices, rank)
}

/** AI decides whether to call BS or pass. */
export function aiDecideChallenge(state: CheatState, aiPlayer: number): CheatState {
  if (state.phase !== 'challenge') return state
  if (!state.lastPlay) return state
  if (state.lastPlay.player === aiPlayer) return passChallenge(state, aiPlayer)

  // Heuristics for calling BS
  const claimedCount = state.lastPlay.claimedCount
  const pileSize = state.pile.length
  let callProbability = 0.15 // base chance

  // More suspicious if claiming 3-4 cards
  if (claimedCount >= 3) callProbability += 0.25
  // More likely to call when pile is large (higher stakes)
  if (pileSize >= 8) callProbability += 0.15
  // If AI holds cards of the claimed rank, opponent is more likely bluffing
  const aiHand = state.hands[aiPlayer]
  const aiHasRank = aiHand.filter(c => c.rank === state.lastPlay!.claimedRank).length
  if (aiHasRank >= 2) callProbability += 0.3
  if (aiHasRank >= 3) callProbability += 0.2

  if (Math.random() < callProbability) {
    return callBS(state, aiPlayer)
  }

  return passChallenge(state, aiPlayer)
}
