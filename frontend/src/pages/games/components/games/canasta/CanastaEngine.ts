/**
 * Canasta engine — pure logic, no React.
 *
 * 4 players: 2v2 partnership (Player 0 + Player 2 vs Player 1 + Player 3).
 * Double deck (108 cards) with jokers. Melds of same rank (no runs).
 * Canastas (7+) required to go out. First to 5000 wins.
 */

import { createDoubleDeck, shuffleDeck, type Card } from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

export type Phase = 'draw' | 'meld' | 'discard' | 'roundOver' | 'gameOver'

export interface CanastaMeld {
  cards: Card[]
  rank: number
  team: number
  isCanasta: boolean
  isNatural: boolean
}

export interface CanastaState {
  hands: Card[][]
  teamMelds: CanastaMeld[]
  stock: Card[]
  discardPile: Card[]
  currentPlayer: number
  phase: Phase
  teamScores: number[]
  redThrees: Card[][]
  message: string
  hasDrawn: boolean
  selectedCards: number[]
  teamHasInitialMeld: boolean[]
  pileFrozen: boolean
  meldError?: string
}

// ── Constants ────────────────────────────────────────────────────────

export const WINNING_SCORE = 5000
export const GOING_OUT_BONUS = 100
export const NATURAL_CANASTA_BONUS = 500
export const MIXED_CANASTA_BONUS = 300
export const RED_3_BONUS = 100
export const ALL_RED_3S_BONUS = 800
export const PLAYER_NAMES = ['You', 'East', 'North', 'West']
export const TEAM_NAMES = ['You & North', 'East & West']

// ── Card classification ──────────────────────────────────────────────

export function isWild(card: Card): boolean {
  return card.rank === 0 || card.rank === 2
}

export function isRed3(card: Card): boolean {
  return card.rank === 3 && (card.suit === 'hearts' || card.suit === 'diamonds')
}

export function isBlack3(card: Card): boolean {
  return card.rank === 3 && (card.suit === 'clubs' || card.suit === 'spades')
}

export function cardPoints(card: Card): number {
  if (card.rank === 0) return 50           // Joker
  if (card.rank === 2 || card.rank === 1) return 20  // 2s and Aces
  if (card.rank >= 8) return 10            // 8-K
  return 5                                 // 3-7
}

export function getInitialMeldReq(teamScore: number): number {
  if (teamScore >= 3000) return 120
  if (teamScore >= 1500) return 90
  if (teamScore < 0) return 15
  return 50
}

// ── Helpers ──────────────────────────────────────────────────────────

function teamOf(player: number): number {
  return player % 2 // 0,2 = team 0; 1,3 = team 1
}

function nextPlayer(current: number): number {
  return (current + 1) % 4
}

/** Extract the natural rank from a set of cards (ignoring wilds). */
function naturalRank(cards: Card[]): number {
  for (const card of cards) {
    if (!isWild(card)) return card.rank
  }
  return -1
}

/** Count wild cards in a set. */
function countWilds(cards: Card[]): number {
  return cards.filter(isWild).length
}

/** Count natural (non-wild, non-3) cards in a set. */
function countNaturals(cards: Card[]): number {
  return cards.filter(c => !isWild(c)).length
}

/** Calculate total point value of a set of cards. */
function totalPoints(cards: Card[]): number {
  return cards.reduce((sum, c) => sum + cardPoints(c), 0)
}

function sortHand(hand: Card[]): Card[] {
  return [...hand].sort((a, b) => {
    if (a.rank !== b.rank) return a.rank - b.rank
    if (a.suit < b.suit) return -1
    if (a.suit > b.suit) return 1
    return 0
  })
}

// ── Meld validation ─────────────────────────────────────────────────

export function isValidNewMeld(cards: Card[]): boolean {
  if (cards.length < 3) return false

  const wilds = countWilds(cards)
  const naturals = countNaturals(cards)

  // Must have more naturals than wilds
  if (naturals <= wilds) return false

  // Max 3 wilds
  if (wilds > 3) return false

  // All naturals must be the same rank
  const rank = naturalRank(cards)
  if (rank < 0) return false

  // Cannot meld 3s as a new meld (black 3s only when going out, red 3s auto-play)
  if (rank === 3) return false

  for (const card of cards) {
    if (!isWild(card) && card.rank !== rank) return false
  }

  return true
}

/** Check if adding cards to an existing meld would still be valid. */
function isValidMeldAddition(meld: CanastaMeld, newCards: Card[]): boolean {
  const allCards = [...meld.cards, ...newCards]
  const wilds = countWilds(allCards)
  const naturals = countNaturals(allCards)

  if (naturals <= wilds) return false
  if (wilds > 3) return false

  // New cards must be same rank or wild
  for (const card of newCards) {
    if (!isWild(card) && card.rank !== meld.rank) return false
  }

  return true
}

/** Update canasta status of a meld. */
function updateMeldStatus(meld: CanastaMeld): CanastaMeld {
  const isCan = meld.cards.length >= 7
  const isNat = isCan && countWilds(meld.cards) === 0
  return { ...meld, isCanasta: isCan, isNatural: isNat }
}

// ── Game creation ───────────────────────────────────────────────────

export function createCanastaGame(): CanastaState {
  const deck = shuffleDeck(createDoubleDeck())
  const hands: Card[][] = [[], [], [], []]
  let idx = 0

  // Deal 11 cards to each player
  for (let i = 0; i < 44; i++) {
    hands[i % 4].push({ ...deck[idx++], faceUp: true })
  }

  // Remaining cards are stock
  const stock = deck.slice(idx + 1).map(c => ({ ...c, faceUp: true }))
  // Top card of stock starts the discard pile
  const discardPile = [{ ...deck[idx], faceUp: true }]

  // Auto-play red 3s from all hands
  const redThrees: Card[][] = [[], [], [], []]
  for (let p = 0; p < 4; p++) {
    let found = true
    while (found) {
      found = false
      const red3Idx = hands[p].findIndex(c => isRed3(c))
      if (red3Idx >= 0) {
        redThrees[p].push(hands[p][red3Idx])
        hands[p].splice(red3Idx, 1)
        // Draw replacements until we get a non-red-3 card
        while (stock.length > 0) {
          const replacement = stock.pop()!
          if (isRed3(replacement)) {
            redThrees[p].push(replacement)
            // Keep drawing — need a non-red-3 replacement
          } else {
            hands[p].push(replacement)
            break
          }
        }
        found = true
      }
    }
    hands[p] = sortHand(hands[p])
  }

  // If discard pile top is a wild or red 3, it freezes the pile
  const topCard = discardPile[0]
  const pileFrozen = isWild(topCard) || isRed3(topCard)

  return {
    hands,
    teamMelds: [],
    stock,
    discardPile,
    currentPlayer: 0,
    phase: 'draw',
    teamScores: [0, 0],
    redThrees,
    message: 'Your turn — draw 2 cards or pick up the pile',
    hasDrawn: false,
    selectedCards: [],
    teamHasInitialMeld: [false, false],
    pileFrozen,
  }
}

// ── Drawing ─────────────────────────────────────────────────────────

export function drawFromStock(state: CanastaState): CanastaState {
  if (state.phase !== 'draw' || state.hasDrawn) return state
  if (state.stock.length === 0) {
    return { ...state, phase: 'roundOver', message: 'Stock exhausted — round over!' }
  }

  const newStock = [...state.stock]
  const newHands = state.hands.map(h => [...h])
  const newRedThrees = state.redThrees.map(r => [...r])
  const player = state.currentPlayer

  // Draw 2 cards, handling red 3s (auto-play and draw replacements)
  let cardsDrawn = 0
  while (cardsDrawn < 2 && newStock.length > 0) {
    const card = newStock.pop()!
    if (isRed3(card)) {
      newRedThrees[player].push(card)
      // Keep drawing replacements until we get a non-red-3 or stock empties
      // (don't count toward the 2 draws)
    } else {
      newHands[player].push(card)
      cardsDrawn++
    }
  }

  newHands[player] = sortHand(newHands[player])

  const roundOver = newStock.length === 0
  const nextPhase: Phase = roundOver && newHands[player].length === 0 ? 'roundOver' : 'meld'
  const msg = player === 0
    ? 'Meld cards or discard'
    : `${PLAYER_NAMES[player]} drew 2 cards`

  return {
    ...state,
    hands: newHands,
    stock: newStock,
    redThrees: newRedThrees,
    phase: nextPhase,
    hasDrawn: true,
    message: msg,
    meldError: undefined,
  }
}

// ── Picking up discard pile ─────────────────────────────────────────

export function pickupDiscardPile(state: CanastaState, meldCardIndices: number[]): CanastaState {
  if (state.phase !== 'draw' || state.hasDrawn) return state
  if (state.discardPile.length === 0) return state

  const topCard = state.discardPile[state.discardPile.length - 1]

  // Cannot pick up pile if top card is a black 3
  if (isBlack3(topCard)) return { ...state, meldError: 'Cannot pick up pile — top card is a black 3' }

  const player = state.currentPlayer
  const team = teamOf(player)
  const hand = state.hands[player]

  // Get the cards from hand that will form a meld with the top card
  const meldCards = meldCardIndices.map(i => hand[i]).filter(Boolean)

  // For frozen pile or no initial meld: need a natural pair matching top card
  const needNaturalPair = state.pileFrozen || !state.teamHasInitialMeld[team]
  if (needNaturalPair) {
    const naturalMatches = meldCards.filter(c => !isWild(c) && c.rank === topCard.rank)
    if (naturalMatches.length < 2) {
      const reason = state.pileFrozen ? 'Pile is frozen' : 'First meld'
      return { ...state, meldError: `${reason} — need 2 natural cards matching the top card (no wilds)` }
    }
  } else {
    // Normal pile: need 2 cards that can form a meld with the top card
    const combined = [...meldCards, topCard]
    if (combined.length < 3) return { ...state, meldError: 'Need at least 2 cards to pick up the pile' }
    if (!isValidNewMeld(combined)) return { ...state, meldError: 'Selected cards do not form a valid meld with the top card' }
  }

  // Check initial meld requirement if team hasn't melded yet
  if (!state.teamHasInitialMeld[team]) {
    const combined = [...meldCards, topCard]
    const meldPts = totalPoints(combined)
    const req = getInitialMeldReq(state.teamScores[team])
    if (meldPts < req) {
      return { ...state, meldError: `Initial meld needs ${req}+ points (you have ${meldPts})` }
    }
  }

  // Pick up the pile
  const newHands = state.hands.map(h => [...h])
  // Remove melded cards from hand
  const indicesToRemove = new Set(meldCardIndices)
  newHands[player] = newHands[player].filter((_, i) => !indicesToRemove.has(i))
  // Add all discard pile cards EXCEPT the top card to hand (top card goes to meld)
  const restOfPile = state.discardPile.slice(0, -1)
  newHands[player].push(...restOfPile)
  newHands[player] = sortHand(newHands[player])

  // Create the meld from meldCards + top card
  const newMeldCards = [...meldCards, topCard]
  const rank = naturalRank(newMeldCards)
  const newMeld: CanastaMeld = updateMeldStatus({
    cards: newMeldCards,
    rank,
    team,
    isCanasta: false,
    isNatural: false,
  })

  // Check if this meld can be added to an existing team meld of same rank
  const existingIdx = state.teamMelds.findIndex(m => m.team === team && m.rank === rank)
  let newTeamMelds: CanastaMeld[]
  if (existingIdx >= 0) {
    newTeamMelds = state.teamMelds.map((m, i) => {
      if (i !== existingIdx) return m
      return updateMeldStatus({
        ...m,
        cards: [...m.cards, ...newMeldCards],
      })
    })
  } else {
    newTeamMelds = [...state.teamMelds, newMeld]
  }

  const newInitialMeld = [...state.teamHasInitialMeld]
  newInitialMeld[team] = true

  return {
    ...state,
    hands: newHands,
    discardPile: [],
    teamMelds: newTeamMelds,
    phase: 'meld',
    hasDrawn: true,
    pileFrozen: false,
    teamHasInitialMeld: newInitialMeld,
    message: player === 0 ? 'Picked up pile — meld cards or discard' : `${PLAYER_NAMES[player]} picked up the pile`,
    selectedCards: [],
    meldError: undefined,
  }
}

// ── Melding ─────────────────────────────────────────────────────────

export function meldCards(
  state: CanastaState,
  cardIndices: number[],
  targetMeldIdx?: number,
): CanastaState {
  if (state.phase !== 'meld' || !state.hasDrawn) return state

  const player = state.currentPlayer
  const team = teamOf(player)
  const hand = state.hands[player]
  const cards = cardIndices.map(i => hand[i]).filter(Boolean)

  if (cards.length === 0) return state

  let newTeamMelds: CanastaMeld[]
  let newInitialMeld = [...state.teamHasInitialMeld]

  if (targetMeldIdx !== undefined) {
    // Adding to existing meld
    const meld = state.teamMelds[targetMeldIdx]
    if (!meld || meld.team !== team) return { ...state, meldError: 'Cannot add to that meld' }
    if (!isValidMeldAddition(meld, cards)) return { ...state, meldError: 'Invalid meld addition — need more naturals than wilds' }

    newTeamMelds = state.teamMelds.map((m, i) => {
      if (i !== targetMeldIdx) return m
      return updateMeldStatus({
        ...m,
        cards: [...m.cards, ...cards],
      })
    })
  } else {
    // New meld
    if (!isValidNewMeld(cards)) return { ...state, meldError: 'Invalid meld — need 3+ same-rank cards with more naturals than wilds' }

    // Check initial meld requirement
    if (!state.teamHasInitialMeld[team]) {
      const req = getInitialMeldReq(state.teamScores[team])
      // Calculate total points of this meld
      const meldPts = totalPoints(cards)
      if (meldPts < req) {
        return { ...state, meldError: `Initial meld needs ${req}+ points (you have ${meldPts})` }
      }
      newInitialMeld[team] = true
    }

    const rank = naturalRank(cards)
    // Check if team already has a meld of this rank
    const existingIdx = state.teamMelds.findIndex(m => m.team === team && m.rank === rank)
    if (existingIdx >= 0) {
      // Add to existing
      if (!isValidMeldAddition(state.teamMelds[existingIdx], cards)) {
        return { ...state, meldError: 'Invalid meld addition — need more naturals than wilds' }
      }
      newTeamMelds = state.teamMelds.map((m, i) => {
        if (i !== existingIdx) return m
        return updateMeldStatus({
          ...m,
          cards: [...m.cards, ...cards],
        })
      })
    } else {
      const newMeld = updateMeldStatus({
        cards,
        rank,
        team,
        isCanasta: false,
        isNatural: false,
      })
      newTeamMelds = [...state.teamMelds, newMeld]
    }
  }

  // Remove melded cards from hand
  const newHands = state.hands.map(h => [...h])
  const indicesToRemove = new Set(cardIndices)
  newHands[player] = newHands[player].filter((_, i) => !indicesToRemove.has(i))

  return {
    ...state,
    hands: newHands,
    teamMelds: newTeamMelds,
    teamHasInitialMeld: newInitialMeld,
    message: player === 0 ? 'Melded! Meld more or discard' : `${PLAYER_NAMES[player]} melded`,
    selectedCards: [],
    meldError: undefined,
  }
}

// ── Discarding ──────────────────────────────────────────────────────

export function discard(state: CanastaState, cardIndex: number): CanastaState {
  if (!state.hasDrawn) return state

  const player = state.currentPlayer
  const hand = state.hands[player]
  const card = hand[cardIndex]
  if (!card) return state

  const newHands = state.hands.map(h => [...h])
  newHands[player].splice(cardIndex, 1)

  const newDiscardPile = [...state.discardPile, card]

  // Discarding a wild freezes the pile
  const newPileFrozen = state.pileFrozen || isWild(card)

  const next = nextPlayer(player)

  // Check if player went out (hand empty and has canasta)
  if (newHands[player].length === 0) {
    const team = teamOf(player)
    const hasCanasta = state.teamMelds.some(m => m.team === team && m.isCanasta)
    if (hasCanasta) {
      return resolveRound({
        ...state,
        hands: newHands,
        discardPile: newDiscardPile,
        pileFrozen: newPileFrozen,
      }, player)
    }
  }

  // Check if stock is empty — round over
  if (state.stock.length === 0 && newHands[player].length === 0) {
    return resolveRound({
      ...state,
      hands: newHands,
      discardPile: newDiscardPile,
      pileFrozen: newPileFrozen,
    }, player)
  }

  return {
    ...state,
    hands: newHands,
    discardPile: newDiscardPile,
    pileFrozen: newPileFrozen,
    currentPlayer: next,
    phase: 'draw',
    hasDrawn: false,
    selectedCards: [],
    message: next === 0 ? 'Your turn — draw 2 cards or pick up the pile' : `${PLAYER_NAMES[next]}'s turn`,
  }
}

// ── Going out ───────────────────────────────────────────────────────

export function goOut(state: CanastaState): CanastaState {
  if (state.phase !== 'meld' || !state.hasDrawn) return state

  const player = state.currentPlayer
  const team = teamOf(player)

  // Must have at least one canasta
  const hasCanasta = state.teamMelds.some(m => m.team === team && m.isCanasta)
  if (!hasCanasta) return state

  // Must be able to get rid of all hand cards (meld or they're already empty)
  if (state.hands[player].length > 0) return state

  return resolveRound(state, player)
}

// ── Round resolution ────────────────────────────────────────────────

function resolveRound(state: CanastaState, goingOutPlayer: number): CanastaState {
  const roundScores = scoreRound(state)
  const goingOutTeam = teamOf(goingOutPlayer)
  roundScores[goingOutTeam] += GOING_OUT_BONUS

  const newScores = [
    state.teamScores[0] + roundScores[0],
    state.teamScores[1] + roundScores[1],
  ]

  const gameOver = newScores[0] >= WINNING_SCORE || newScores[1] >= WINNING_SCORE

  if (gameOver) {
    const winner = newScores[0] >= newScores[1] ? 0 : 1
    return {
      ...state,
      teamScores: newScores,
      phase: 'gameOver',
      message: winner === 0 ? 'Your team wins!' : 'Opponents win!',
    }
  }

  return {
    ...state,
    teamScores: newScores,
    phase: 'roundOver',
    message: `Round over! ${TEAM_NAMES[0]}: ${newScores[0]} | ${TEAM_NAMES[1]}: ${newScores[1]}`,
  }
}

// ── Scoring ─────────────────────────────────────────────────────────

export function scoreRound(state: CanastaState): number[] {
  const scores = [0, 0]

  // Meld card points + canasta bonuses
  for (const meld of state.teamMelds) {
    scores[meld.team] += totalPoints(meld.cards)
    if (meld.isCanasta) {
      scores[meld.team] += meld.isNatural ? NATURAL_CANASTA_BONUS : MIXED_CANASTA_BONUS
    }
  }

  // Red 3 bonuses/penalties
  for (let team = 0; team < 2; team++) {
    const p1 = team === 0 ? 0 : 1
    const p2 = team === 0 ? 2 : 3
    const teamRed3Count = state.redThrees[p1].length + state.redThrees[p2].length

    if (teamRed3Count > 0) {
      const hasMelds = state.teamHasInitialMeld[team] ||
        state.teamMelds.some(m => m.team === team)

      if (hasMelds) {
        // Bonus
        if (teamRed3Count === 4) {
          scores[team] += ALL_RED_3S_BONUS
        } else {
          scores[team] += teamRed3Count * RED_3_BONUS
        }
      } else {
        // Penalty
        if (teamRed3Count === 4) {
          scores[team] -= ALL_RED_3S_BONUS
        } else {
          scores[team] -= teamRed3Count * RED_3_BONUS
        }
      }
    }
  }

  // Subtract unmelded hand cards
  for (let p = 0; p < 4; p++) {
    const team = teamOf(p)
    scores[team] -= totalPoints(state.hands[p])
  }

  return scores
}

// ── New round ───────────────────────────────────────────────────────

export function newRound(state: CanastaState): CanastaState {
  const fresh = createCanastaGame()
  return {
    ...fresh,
    teamScores: [...state.teamScores],
  }
}

// ── AI ──────────────────────────────────────────────────────────────

export function aiTurn(state: CanastaState): CanastaState {
  const player = state.currentPlayer
  if (player === 0) return state

  // 1. Draw phase
  let current = drawFromStock(state)
  if (current.phase === 'roundOver' || current.phase === 'gameOver') return current

  // 2. Meld phase — try to meld any valid groups
  current = aiAttemptMelds(current)

  // 3. Try going out
  const team = teamOf(player)
  const hasCanasta = current.teamMelds.some(m => m.team === team && m.isCanasta)
  if (hasCanasta && current.hands[player].length === 0) {
    return goOut(current)
  }

  // If hand has 1 card and team has canasta, go out by melding+discarding
  // is handled by discard check

  // 4. Discard — pick lowest-value card that isn't part of a potential meld
  if (current.hands[player].length === 0) {
    // Already went out via melding — resolve
    if (hasCanasta) {
      return goOut(current)
    }
    // Shouldn't happen normally, but safety: end turn
    return {
      ...current,
      currentPlayer: nextPlayer(player),
      phase: 'draw',
      hasDrawn: false,
      message: nextPlayer(player) === 0
        ? 'Your turn — draw 2 cards or pick up the pile'
        : `${PLAYER_NAMES[nextPlayer(player)]}'s turn`,
    }
  }

  const discardIdx = aiChooseDiscard(current)
  return discard(current, discardIdx)
}

function aiAttemptMelds(state: CanastaState): CanastaState {
  const player = state.currentPlayer
  const team = teamOf(player)
  let current = state

  // Try to add to existing team melds first
  let changed = true
  while (changed) {
    changed = false
    const hand = current.hands[player]
    for (const meld of current.teamMelds) {
      if (meld.team !== team) continue
      for (let i = hand.length - 1; i >= 0; i--) {
        const card = hand[i]
        if (!isWild(card) && card.rank === meld.rank) {
          const next = meldCards(current, [i], current.teamMelds.indexOf(meld))
          if (next !== current) {
            current = next
            changed = true
            break
          }
        }
      }
      if (changed) break
    }
  }

  // Try new melds — group by rank
  changed = true
  while (changed) {
    changed = false
    const hand = current.hands[player]
    const rankGroups = new Map<number, number[]>()
    for (let i = 0; i < hand.length; i++) {
      const card = hand[i]
      if (isWild(card) || isRed3(card) || isBlack3(card)) continue
      const indices = rankGroups.get(card.rank) || []
      indices.push(i)
      rankGroups.set(card.rank, indices)
    }

    for (const [, indices] of rankGroups) {
      if (indices.length >= 3) {
        // Already has a team meld for this rank? Add to it instead
        const existingMeldIdx = current.teamMelds.findIndex(
          m => m.team === team && m.rank === current.hands[player][indices[0]].rank
        )
        if (existingMeldIdx >= 0) {
          const next = meldCards(current, indices, existingMeldIdx)
          if (next !== current) {
            current = next
            changed = true
            break
          }
        } else {
          const next = meldCards(current, indices.slice(0, 3))
          if (next !== current) {
            current = next
            changed = true
            break
          }
        }
      }
    }
  }

  return current
}

function aiChooseDiscard(state: CanastaState): number {
  const player = state.currentPlayer
  const hand = state.hands[player]
  if (hand.length === 0) return -1

  // Count rank frequency — prefer discarding singletons
  const rankCounts = new Map<number, number>()
  for (const card of hand) {
    if (!isWild(card)) {
      rankCounts.set(card.rank, (rankCounts.get(card.rank) || 0) + 1)
    }
  }

  // Prefer discarding:
  // 1. Black 3s (block opponent pickup)
  // 2. Singletons of low value
  // 3. Lowest-value card that isn't part of a pair

  let bestIdx = 0
  let bestScore = Infinity

  for (let i = 0; i < hand.length; i++) {
    const card = hand[i]
    // Don't discard wilds (they freeze pile and are valuable)
    if (isWild(card)) continue

    let score = cardPoints(card) * 10
    const count = rankCounts.get(card.rank) || 0

    // Black 3s are great discards (block opponent)
    if (isBlack3(card)) {
      score = -100
    } else if (count === 1) {
      // Singleton — good to discard
      score = cardPoints(card)
    } else if (count === 2) {
      // Pair — might want to keep
      score = cardPoints(card) * 20
    } else {
      // 3+ — keep for melding
      score = cardPoints(card) * 50
    }

    if (score < bestScore) {
      bestScore = score
      bestIdx = i
    }
  }

  return bestIdx
}
