/**
 * Gin Rummy engine — pure logic, no React.
 *
 * 2-player (human vs AI). Draw, discard, form melds, knock or go gin.
 */

import { createDeck, shuffleDeck, type Card, type Suit } from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

export type Phase = 'drawing' | 'discarding' | 'knocked' | 'scoring' | 'gameOver'

export interface Meld {
  cards: Card[]
  type: 'set' | 'run'
}

export interface GinRummyState {
  playerHand: Card[]
  aiHand: Card[]
  drawPile: Card[]
  discardPile: Card[]
  phase: Phase
  currentPlayer: 0 | 1  // 0 = human, 1 = AI
  knocker: 0 | 1 | null
  playerScore: number
  aiScore: number
  roundMessage: string
  message: string
  targetScore: number
}

// ── Constants ────────────────────────────────────────────────────────

export const TARGET_SCORE = 100
const GIN_BONUS = 25
const UNDERCUT_BONUS = 25

// ── Card value for deadwood ──────────────────────────────────────────

function deadwoodValue(card: Card): number {
  if (card.rank >= 11) return 10
  if (card.rank === 1) return 1
  return card.rank
}

// ── Meld detection ───────────────────────────────────────────────────

/** Find the best arrangement of melds that minimizes deadwood. */
export function findBestMelds(hand: Card[]): { melds: Meld[]; deadwood: Card[]; deadwoodTotal: number } {
  const allSets = findSets(hand)
  const allRuns = findRuns(hand)
  const allMelds = [...allSets, ...allRuns]

  // Try all combinations of non-overlapping melds
  let best = { melds: [] as Meld[], deadwood: [...hand], deadwoodTotal: hand.reduce((s, c) => s + deadwoodValue(c), 0) }

  function tryMelds(remaining: Card[], usedMelds: Meld[], meldIdx: number) {
    const dw = remaining.reduce((s, c) => s + deadwoodValue(c), 0)
    if (dw < best.deadwoodTotal) {
      best = { melds: [...usedMelds], deadwood: [...remaining], deadwoodTotal: dw }
    }

    for (let i = meldIdx; i < allMelds.length; i++) {
      const meld = allMelds[i]
      // Check if all meld cards are in remaining
      const remCopy = [...remaining]
      let valid = true
      for (const mc of meld.cards) {
        const idx = remCopy.findIndex(c => c.rank === mc.rank && c.suit === mc.suit)
        if (idx === -1) { valid = false; break }
        remCopy.splice(idx, 1)
      }
      if (valid) {
        tryMelds(remCopy, [...usedMelds, meld], i + 1)
      }
    }
  }

  tryMelds(hand, [], 0)
  return best
}

function findSets(hand: Card[]): Meld[] {
  const byRank = new Map<number, Card[]>()
  for (const c of hand) {
    const arr = byRank.get(c.rank) || []
    arr.push(c)
    byRank.set(c.rank, arr)
  }

  const melds: Meld[] = []
  for (const [_, cards] of byRank) {
    if (cards.length >= 3) {
      // 3-of-a-kind
      melds.push({ cards: cards.slice(0, 3), type: 'set' })
      // 4-of-a-kind
      if (cards.length === 4) {
        melds.push({ cards: [...cards], type: 'set' })
      }
    }
  }
  return melds
}

function findRuns(hand: Card[]): Meld[] {
  const melds: Meld[] = []
  const suits: Suit[] = ['hearts', 'diamonds', 'clubs', 'spades']

  for (const suit of suits) {
    const suitCards = hand.filter(c => c.suit === suit).sort((a, b) => a.rank - b.rank)
    if (suitCards.length < 3) continue

    // Find consecutive runs
    for (let start = 0; start < suitCards.length - 2; start++) {
      const run: Card[] = [suitCards[start]]
      for (let j = start + 1; j < suitCards.length; j++) {
        if (suitCards[j].rank === run[run.length - 1].rank + 1) {
          run.push(suitCards[j])
          if (run.length >= 3) {
            melds.push({ cards: [...run], type: 'run' })
          }
        } else {
          break
        }
      }
    }
  }
  return melds
}

// ── Game creation ────────────────────────────────────────────────────

export function createGinRummyGame(): GinRummyState {
  const deck = shuffleDeck(createDeck()).map(c => ({ ...c, faceUp: true }))
  const playerHand = deck.splice(0, 10)
  const aiHand = deck.splice(0, 10)
  const firstDiscard = deck.pop()!
  const drawPile = deck

  return {
    playerHand: sortHand(playerHand),
    aiHand,
    drawPile,
    discardPile: [firstDiscard],
    phase: 'drawing',
    currentPlayer: 0,
    knocker: null,
    playerScore: 0,
    aiScore: 0,
    roundMessage: '',
    message: 'Draw from the pile or discard pile',
    targetScore: TARGET_SCORE,
  }
}

function sortHand(hand: Card[]): Card[] {
  return [...hand].sort((a, b) => a.suit.localeCompare(b.suit) || a.rank - b.rank)
}

// ── Actions ──────────────────────────────────────────────────────────

export function drawFromPile(state: GinRummyState): GinRummyState {
  if (state.phase !== 'drawing' || state.currentPlayer !== 0) return state
  if (state.drawPile.length === 0) return state

  const drawPile = [...state.drawPile]
  const card = drawPile.pop()!
  const playerHand = sortHand([...state.playerHand, { ...card, faceUp: true }])

  return {
    ...state,
    playerHand,
    drawPile,
    phase: 'discarding',
    message: 'Discard a card',
  }
}

export function drawFromDiscard(state: GinRummyState): GinRummyState {
  if (state.phase !== 'drawing' || state.currentPlayer !== 0) return state
  if (state.discardPile.length === 0) return state

  const discardPile = [...state.discardPile]
  const card = discardPile.pop()!
  const playerHand = sortHand([...state.playerHand, { ...card, faceUp: true }])

  return {
    ...state,
    playerHand,
    discardPile,
    phase: 'discarding',
    message: 'Discard a card',
  }
}

export function discard(state: GinRummyState, cardIndex: number): GinRummyState {
  if (state.phase !== 'discarding' || state.currentPlayer !== 0) return state
  if (cardIndex < 0 || cardIndex >= state.playerHand.length) return state

  const playerHand = [...state.playerHand]
  const card = playerHand.splice(cardIndex, 1)[0]
  const discardPile = [...state.discardPile, card]

  // AI turn
  return aiTurn({
    ...state,
    playerHand: sortHand(playerHand),
    discardPile,
    currentPlayer: 1,
  })
}

export function knock(state: GinRummyState): GinRummyState {
  if (state.phase !== 'discarding' || state.currentPlayer !== 0) return state
  const { deadwoodTotal } = findBestMelds(state.playerHand)
  if (deadwoodTotal > 10 && state.playerHand.length <= 10) return state

  return resolveKnock({ ...state, knocker: 0 })
}

export function getPlayerDeadwood(state: GinRummyState): number {
  // During discarding phase, player has 11 cards — show deadwood for current 11
  return findBestMelds(state.playerHand).deadwoodTotal
}

export function canKnock(state: GinRummyState): boolean {
  if (state.phase !== 'discarding' || state.currentPlayer !== 0) return false
  if (state.playerHand.length > 11) return false
  // Need to discard first to get to 10 cards, but check if any discard would allow knock
  // Simplified: allow knock if current deadwood <= 10 (player still has 11 cards, will discard)
  const { deadwoodTotal } = findBestMelds(state.playerHand)
  return deadwoodTotal <= 10
}

// ── AI ───────────────────────────────────────────────────────────────

function aiTurn(state: GinRummyState): GinRummyState {
  // AI draws
  const topDiscard = state.discardPile.length > 0 ? state.discardPile[state.discardPile.length - 1] : null
  let aiHand = [...state.aiHand]
  let drawPile = [...state.drawPile]
  let discardPile = [...state.discardPile]

  // Check if discard pile card helps melds
  let drawFromDiscardPile = false
  if (topDiscard) {
    const withDiscard = [...aiHand, topDiscard]
    const before = findBestMelds(aiHand).deadwoodTotal
    const after = findBestMelds(withDiscard).deadwoodTotal
    if (after < before - 3) drawFromDiscardPile = true
  }

  if (drawFromDiscardPile && discardPile.length > 0) {
    aiHand.push(discardPile.pop()!)
  } else if (drawPile.length > 0) {
    aiHand.push({ ...drawPile.pop()!, faceUp: true })
  } else {
    // No cards to draw — stalemate
    return {
      ...state,
      phase: 'scoring',
      roundMessage: 'Draw — no cards remaining',
      message: 'Round ended in a draw',
    }
  }

  // AI decides to knock?
  const bestBefore = findBestMelds(aiHand)
  if (bestBefore.deadwoodTotal <= 10) {
    // AI knocks — discard worst deadwood card first
    const worstIdx = findWorstDeadwoodCard(aiHand)
    const discarded = aiHand.splice(worstIdx, 1)[0]
    discardPile.push(discarded)

    if (bestBefore.deadwoodTotal === 0) {
      return resolveKnock({
        ...state,
        aiHand,
        drawPile,
        discardPile,
        knocker: 1,
      })
    }

    return resolveKnock({
      ...state,
      aiHand,
      drawPile,
      discardPile,
      knocker: 1,
    })
  }

  // AI discards highest deadwood card
  const discardIdx = findWorstDeadwoodCard(aiHand)
  discardPile.push(aiHand.splice(discardIdx, 1)[0])

  return {
    ...state,
    aiHand,
    drawPile,
    discardPile,
    currentPlayer: 0,
    phase: 'drawing',
    message: 'Your turn — draw from the pile or discard pile',
  }
}

function findWorstDeadwoodCard(hand: Card[]): number {
  const { deadwood } = findBestMelds(hand)
  if (deadwood.length === 0) return hand.length - 1

  // Find the highest-value deadwood card in the full hand
  let worstIdx = 0
  let worstVal = 0
  for (let i = 0; i < hand.length; i++) {
    const isDead = deadwood.some(d => d.rank === hand[i].rank && d.suit === hand[i].suit)
    if (isDead && deadwoodValue(hand[i]) > worstVal) {
      worstVal = deadwoodValue(hand[i])
      worstIdx = i
    }
  }
  return worstIdx
}

// ── Scoring ──────────────────────────────────────────────────────────

function resolveKnock(state: GinRummyState): GinRummyState {
  const knockerHand = state.knocker === 0 ? state.playerHand : state.aiHand
  const defenderHand = state.knocker === 0 ? state.aiHand : state.playerHand

  const knockerMelds = findBestMelds(knockerHand)
  const defenderMelds = findBestMelds(defenderHand)

  const isGin = knockerMelds.deadwoodTotal === 0
  const knockerName = state.knocker === 0 ? 'You' : 'AI'
  const defenderName = state.knocker === 0 ? 'AI' : 'You'

  let points: number
  let winner: 0 | 1
  let msg: string

  if (isGin) {
    points = defenderMelds.deadwoodTotal + GIN_BONUS
    winner = state.knocker!
    msg = `${knockerName} went Gin! +${points} points`
  } else if (defenderMelds.deadwoodTotal <= knockerMelds.deadwoodTotal) {
    // Undercut
    points = knockerMelds.deadwoodTotal - defenderMelds.deadwoodTotal + UNDERCUT_BONUS
    winner = state.knocker === 0 ? 1 : 0
    msg = `${defenderName} undercut${defenderName === 'You' ? '' : 's'}! +${points} points`
  } else {
    points = defenderMelds.deadwoodTotal - knockerMelds.deadwoodTotal
    winner = state.knocker!
    msg = `${knockerName} knock${knockerName === 'You' ? '' : 's'} and win${knockerName === 'You' ? '' : 's'}! +${points} points`
  }

  const playerScore = state.playerScore + (winner === 0 ? points : 0)
  const aiScore = state.aiScore + (winner === 1 ? points : 0)

  const gameOver = playerScore >= state.targetScore || aiScore >= state.targetScore

  return {
    ...state,
    playerHand: state.playerHand,
    aiHand: state.aiHand.map(c => ({ ...c, faceUp: true })),
    playerScore,
    aiScore,
    knocker: state.knocker,
    phase: gameOver ? 'gameOver' : 'scoring',
    roundMessage: msg,
    message: gameOver
      ? (playerScore >= state.targetScore ? 'You win the game!' : 'AI wins the game!')
      : msg,
  }
}

export function newRound(state: GinRummyState): GinRummyState {
  const fresh = createGinRummyGame()
  return {
    ...fresh,
    playerScore: state.playerScore,
    aiScore: state.aiScore,
  }
}
