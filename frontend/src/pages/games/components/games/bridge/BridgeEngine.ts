/**
 * Bridge engine — pure logic, no React.
 *
 * 4 players in 2 teams: Player 0 (human) + Player 2 (AI partner)
 * vs Player 1 (AI) + Player 3 (AI).
 *
 * Simplified contract bridge: bidding, declarer/dummy, trick-taking, scoring.
 */

import { createDeck, shuffleDeck, type Card, type Suit } from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

export type Strain = 'clubs' | 'diamonds' | 'hearts' | 'spades' | 'nt'
export type Phase = 'bidding' | 'playing' | 'trickComplete' | 'handOver' | 'gameOver'

export interface Bid {
  player: number
  level: number       // 1-7 for real bids, 0 for pass
  strain: Strain | null // null for pass
}

export interface TrickCard {
  card: Card
  player: number
}

export interface BridgeState {
  hands: Card[][]
  bids: Bid[]
  contract: Bid | null
  declarer: number | null
  dummy: number | null
  currentTrick: TrickCard[]
  tricksWon: number[]       // per player (4)
  teamScores: number[]      // [team0 (players 0+2), team1 (players 1+3)]
  phase: Phase
  currentPlayer: number
  dealer: number
  trumpSuit: Strain | null
  ledSuit: string | null
  message: string
  consecutivePasses: number
  dummyRevealed: boolean
  lastTrickWinner: number | null
}

// ── Constants ────────────────────────────────────────────────────────

export const STRAIN_ORDER: Strain[] = ['clubs', 'diamonds', 'hearts', 'spades', 'nt']
export const PLAYER_NAMES = ['You', 'East', 'Partner', 'West']
export const TEAM_NAMES = ['You & Partner', 'East & West']
export const WINNING_SCORE = 500

// ── Helpers ──────────────────────────────────────────────────────────

/** Card comparison value — Ace is high (14). */
function cardValue(card: Card): number {
  return card.rank === 1 ? 14 : card.rank
}

/** Sort hand by suit then rank for display. */
export function sortHand(hand: Card[]): Card[] {
  const suitOrder: Suit[] = ['clubs', 'diamonds', 'hearts', 'spades']
  return [...hand].sort((a, b) => {
    const si = suitOrder.indexOf(a.suit) - suitOrder.indexOf(b.suit)
    if (si !== 0) return si
    return cardValue(a) - cardValue(b)
  })
}

/** Get team index for a player: 0 = players 0+2, 1 = players 1+3. */
function playerTeam(player: number): number {
  return player % 2
}

/** Get partner index. */
function partnerOf(player: number): number {
  return (player + 2) % 4
}

// ── HCP counting ─────────────────────────────────────────────────────

/** Count high-card points: A=4, K=3, Q=2, J=1. */
export function countHCP(hand: Card[]): number {
  let hcp = 0
  for (const c of hand) {
    if (c.rank === 1) hcp += 4       // Ace
    else if (c.rank === 13) hcp += 3 // King
    else if (c.rank === 12) hcp += 2 // Queen
    else if (c.rank === 11) hcp += 1 // Jack
  }
  return hcp
}

// ── Bid ordering ─────────────────────────────────────────────────────

/** Check if a new bid is strictly higher than the current bid. */
export function isHigherBid(
  newLevel: number, newStrain: Strain,
  currentLevel: number, currentStrain: Strain,
): boolean {
  if (newLevel > currentLevel) return true
  if (newLevel < currentLevel) return false
  // Same level — compare strain
  return STRAIN_ORDER.indexOf(newStrain) > STRAIN_ORDER.indexOf(currentStrain)
}

/** Get the highest non-pass bid from the bid list. */
function getHighestBid(bids: Bid[]): Bid | null {
  let highest: Bid | null = null
  for (const bid of bids) {
    if (bid.level === 0) continue // pass
    if (!highest || isHigherBid(bid.level, bid.strain!, highest.level, highest.strain!)) {
      highest = bid
    }
  }
  return highest
}

// ── Game creation ────────────────────────────────────────────────────

export function createBridgeGame(): BridgeState {
  return dealHand({
    hands: [[], [], [], []],
    bids: [],
    contract: null,
    declarer: null,
    dummy: null,
    currentTrick: [],
    tricksWon: [0, 0, 0, 0],
    teamScores: [0, 0],
    phase: 'bidding',
    currentPlayer: 0,
    dealer: 0,
    trumpSuit: null,
    ledSuit: null,
    message: 'Your bid',
    consecutivePasses: 0,
    dummyRevealed: false,
    lastTrickWinner: null,
  })
}

function dealHand(state: BridgeState): BridgeState {
  const deck = shuffleDeck(createDeck()).map(c => ({ ...c, faceUp: true }))
  const hands: Card[][] = [[], [], [], []]
  for (let i = 0; i < 52; i++) {
    hands[i % 4].push(deck[i])
  }
  for (let p = 0; p < 4; p++) {
    hands[p] = sortHand(hands[p])
  }

  const dealer = state.dealer
  const firstBidder = (dealer + 1) % 4

  return {
    ...state,
    hands,
    bids: [],
    contract: null,
    declarer: null,
    dummy: null,
    currentTrick: [],
    tricksWon: [0, 0, 0, 0],
    phase: 'bidding',
    currentPlayer: firstBidder,
    trumpSuit: null,
    ledSuit: null,
    consecutivePasses: 0,
    dummyRevealed: false,
    lastTrickWinner: null,
    message: firstBidder === 0 ? 'Your bid' : `${PLAYER_NAMES[firstBidder]} is bidding...`,
  }
}

// ── Bidding ──────────────────────────────────────────────────────────

export function makeBid(state: BridgeState, level: number, strain: Strain): BridgeState {
  if (state.phase !== 'bidding') return state
  if (level < 1 || level > 7) return state

  // Must be higher than the current highest bid
  const highest = getHighestBid(state.bids)
  if (highest && !isHigherBid(level, strain, highest.level, highest.strain!)) {
    return state
  }

  const bid: Bid = { player: state.currentPlayer, level, strain }
  const bids = [...state.bids, bid]

  const next: BridgeState = {
    ...state,
    bids,
    consecutivePasses: 0,
    currentPlayer: (state.currentPlayer + 1) % 4,
  }

  return advanceBidding(next)
}

export function passBid(state: BridgeState): BridgeState {
  if (state.phase !== 'bidding') return state

  const bid: Bid = { player: state.currentPlayer, level: 0, strain: null }
  const bids = [...state.bids, bid]
  const passes = state.consecutivePasses + 1

  const next: BridgeState = {
    ...state,
    bids,
    consecutivePasses: passes,
    currentPlayer: (state.currentPlayer + 1) % 4,
  }

  // Check if bidding is over
  const highestBid = getHighestBid(bids)

  if (!highestBid && passes === 4) {
    // All 4 passed — redeal
    const newDealer = (state.dealer + 1) % 4
    return dealHand({ ...state, dealer: newDealer, message: 'All passed — redealing...' })
  }

  if (highestBid && passes === 3) {
    // 3 consecutive passes after a bid — bidding complete
    return finalizeBidding(next, highestBid)
  }

  return advanceBidding(next)
}

/** Run AI bidding turns until it's the human's turn or bidding ends. */
function advanceBidding(state: BridgeState): BridgeState {
  let current = state

  while (current.phase === 'bidding' && current.currentPlayer !== 0) {
    const aiAction = chooseAiBid(current)
    if (aiAction) {
      current = makeBidInternal(current, aiAction.level, aiAction.strain!)
    } else {
      current = passBidInternal(current)
    }
  }

  if (current.phase === 'bidding') {
    current = { ...current, message: 'Your bid' }
  }

  return current
}

/** Internal makeBid without AI advancement (prevents infinite recursion). */
function makeBidInternal(state: BridgeState, level: number, strain: Strain): BridgeState {
  const highest = getHighestBid(state.bids)
  if (highest && !isHigherBid(level, strain, highest.level, highest.strain!)) {
    // Fallback to pass if AI's bid is invalid
    return passBidInternal(state)
  }

  const bid: Bid = { player: state.currentPlayer, level, strain }
  const bids = [...state.bids, bid]

  const next: BridgeState = {
    ...state,
    bids,
    consecutivePasses: 0,
    currentPlayer: (state.currentPlayer + 1) % 4,
  }

  // Check for 3 consecutive passes after a bid
  const highestBid = getHighestBid(bids)
  if (highestBid && next.consecutivePasses === 3) {
    return finalizeBidding(next, highestBid)
  }

  return next
}

/** Internal passBid without AI advancement. */
function passBidInternal(state: BridgeState): BridgeState {
  const bid: Bid = { player: state.currentPlayer, level: 0, strain: null }
  const bids = [...state.bids, bid]
  const passes = state.consecutivePasses + 1

  const next: BridgeState = {
    ...state,
    bids,
    consecutivePasses: passes,
    currentPlayer: (state.currentPlayer + 1) % 4,
  }

  const highestBid = getHighestBid(bids)

  if (!highestBid && passes === 4) {
    const newDealer = (state.dealer + 1) % 4
    return dealHand({ ...state, dealer: newDealer, message: 'All passed — redealing...' })
  }

  if (highestBid && passes === 3) {
    return finalizeBidding(next, highestBid)
  }

  return next
}

/** Determine declarer, dummy, and transition to playing phase. */
function finalizeBidding(state: BridgeState, winningBid: Bid): BridgeState {
  const winningTeam = playerTeam(winningBid.player)
  const strain = winningBid.strain!

  // Declarer = first player on winning team to bid this strain
  let declarer = winningBid.player
  for (const bid of state.bids) {
    if (bid.level > 0 && bid.strain === strain && playerTeam(bid.player) === winningTeam) {
      declarer = bid.player
      break
    }
  }

  const dummy = partnerOf(declarer)
  const leader = (declarer + 1) % 4 // left of declarer leads

  const trumpSuit: Strain = strain

  let next: BridgeState = {
    ...state,
    contract: winningBid,
    declarer,
    dummy,
    trumpSuit,
    phase: 'playing',
    currentPlayer: leader,
    dummyRevealed: true,
    message: `Contract: ${winningBid.level}${strainSymbol(strain)} by ${PLAYER_NAMES[declarer]}`,
  }

  // If AI leads, run AI turns
  if (leader !== 0 && leader !== dummy) {
    next = runAiTurns(next)
  }

  return next
}

// ── AI Bidding ───────────────────────────────────────────────────────

function chooseAiBid(state: BridgeState): { level: number; strain: Strain } | null {
  const hand = state.hands[state.currentPlayer]
  const hcp = countHCP(hand)
  const highest = getHighestBid(state.bids)

  if (hcp < 13) return null // pass

  // Find longest suit
  const suitCounts: Record<Suit, number> = { clubs: 0, diamonds: 0, hearts: 0, spades: 0 }
  for (const c of hand) {
    suitCounts[c.suit]++
  }

  let longestSuit: Suit = 'clubs'
  let longestCount = 0
  for (const s of ['spades', 'hearts', 'diamonds', 'clubs'] as Suit[]) {
    if (suitCounts[s] > longestCount) {
      longestCount = suitCounts[s]
      longestSuit = s
    }
  }

  const strain: Strain = longestCount >= 4 ? longestSuit : 'nt'
  let level = 1

  // If partner bid, try to support
  const partner = partnerOf(state.currentPlayer)
  const partnerBid = state.bids.find(b => b.player === partner && b.level > 0)
  if (partnerBid && partnerBid.strain) {
    // Support partner's strain at next level
    const supportLevel = partnerBid.level + 1
    if (supportLevel <= 7) {
      const supportStrain = partnerBid.strain as Strain
      if (!highest || isHigherBid(supportLevel, supportStrain, highest.level, highest.strain!)) {
        return { level: supportLevel, strain: supportStrain }
      }
    }
  }

  // Simple opening bid
  if (highest) {
    // Must bid higher
    if (isHigherBid(level, strain, highest.level, highest.strain!)) {
      return { level, strain }
    }
    // Try next level
    level = highest.level + 1
    if (level <= 3 && hcp >= 13) {
      return { level, strain }
    }
    return null // can't bid high enough, pass
  }

  return { level, strain }
}

// ── Playing ──────────────────────────────────────────────────────────

export function playCard(state: BridgeState, playerIdx: number, cardIndex: number): BridgeState {
  if (state.phase !== 'playing') return state

  // Validate who can play
  const actualPlayer = state.currentPlayer
  if (actualPlayer === state.dummy) {
    // Dummy's turn — only declarer can play dummy's cards
    if (playerIdx !== state.dummy) return state
  } else if (actualPlayer === 0) {
    if (playerIdx !== 0) return state
  } else {
    // AI player — should be handled internally
    return state
  }

  const hand = state.hands[playerIdx]
  if (cardIndex < 0 || cardIndex >= hand.length) return state

  const card = hand[cardIndex]

  // Validate follow suit
  if (!isValidPlay(card, hand, state)) return state

  const newHands = state.hands.map(h => [...h])
  newHands[playerIdx].splice(cardIndex, 1)

  const ledSuit = state.currentTrick.length === 0 ? card.suit : state.ledSuit
  const newTrick: TrickCard[] = [...state.currentTrick, { card, player: actualPlayer }]

  let next: BridgeState = {
    ...state,
    hands: newHands,
    currentTrick: newTrick,
    ledSuit,
  }

  if (newTrick.length === 4) {
    return completeTrick(next)
  }

  next = { ...next, currentPlayer: (actualPlayer + 1) % 4 }

  // Run AI turns (or if it's dummy's turn, skip to declarer control)
  return runAiTurns(next)
}

function isValidPlay(card: Card, hand: Card[], state: BridgeState): boolean {
  if (state.currentTrick.length === 0) return true // leading

  const ledSuit = state.ledSuit
  if (!ledSuit) return true

  const hasSuit = hand.some(c => c.suit === ledSuit)
  if (hasSuit) return card.suit === ledSuit
  return true // void — can play anything
}

export function getValidPlays(state: BridgeState, playerIdx: number): number[] {
  if (state.phase !== 'playing') return []

  const actualPlayer = state.currentPlayer
  let handIdx: number

  if (actualPlayer === state.dummy) {
    handIdx = state.dummy
  } else if (actualPlayer === 0) {
    handIdx = 0
  } else {
    return []
  }

  if (playerIdx !== handIdx) return []

  const hand = state.hands[handIdx]
  return hand.map((c, i) => isValidPlay(c, hand, state) ? i : -1).filter(i => i >= 0)
}

// ── AI Playing ───────────────────────────────────────────────────────

function runAiTurns(state: BridgeState): BridgeState {
  let current = state

  while (current.phase === 'playing') {
    const cp = current.currentPlayer

    // If it's the human's turn, stop
    if (cp === 0) break

    // If it's dummy's turn, the declarer (human=0 or AI) controls
    if (cp === current.dummy) {
      if (current.declarer === 0) {
        // Human declarer controls dummy — stop for human input
        break
      }
      // AI declarer controls dummy
      const dummyCard = aiChooseCard(current.hands[cp], current)
      current = executeAiPlay(current, cp, dummyCard)
      continue
    }

    // Regular AI player
    const chosenCard = aiChooseCard(current.hands[cp], current)
    current = executeAiPlay(current, cp, chosenCard)
  }

  if (current.phase === 'playing') {
    const cp = current.currentPlayer
    if (cp === 0) {
      current = { ...current, message: 'Your turn — play a card' }
    } else if (cp === current.dummy && current.declarer === 0) {
      current = { ...current, message: "Your turn — play dummy's card" }
    }
  }

  return current
}

function executeAiPlay(state: BridgeState, playerIdx: number, card: Card): BridgeState {
  const newHands = state.hands.map(h => [...h])
  newHands[playerIdx] = newHands[playerIdx].filter(
    c => !(c.rank === card.rank && c.suit === card.suit)
  )

  const ledSuit = state.currentTrick.length === 0 ? card.suit : state.ledSuit
  const newTrick: TrickCard[] = [...state.currentTrick, { card, player: state.currentPlayer }]

  let next: BridgeState = {
    ...state,
    hands: newHands,
    currentTrick: newTrick,
    ledSuit,
  }

  if (newTrick.length === 4) {
    return completeTrick(next)
  }

  next = { ...next, currentPlayer: (state.currentPlayer + 1) % 4 }
  return next
}

function aiChooseCard(hand: Card[], state: BridgeState): Card {
  const valid = hand.filter(c => isValidPlay(c, hand, state))
  if (valid.length === 1) return valid[0]

  const isLeading = state.currentTrick.length === 0

  if (isLeading) {
    // Lead with highest non-trump
    const trumpSuitStr = state.trumpSuit === 'nt' ? null : state.trumpSuit
    const nonTrump = trumpSuitStr ? valid.filter(c => c.suit !== trumpSuitStr) : valid
    const pool = nonTrump.length > 0 ? nonTrump : valid
    return pool.sort((a, b) => cardValue(b) - cardValue(a))[0]
  }

  const ledSuit = state.ledSuit
  const following = ledSuit ? valid.filter(c => c.suit === ledSuit) : valid

  if (following.length > 0) {
    // Check if partner is winning
    const currentWinnerPlayer = trickWinner(state.currentTrick, state.trumpSuit)
    const partnerIdx = partnerOf(state.currentPlayer)
    const partnerWinning = currentWinnerPlayer === partnerIdx

    if (partnerWinning) {
      // Play lowest
      return following.sort((a, b) => cardValue(a) - cardValue(b))[0]
    }

    // Try to win with lowest winning card
    const bestSoFar = getBestCard(state.currentTrick, state.trumpSuit)
    if (bestSoFar) {
      const winners = following.filter(c => cardValue(c) > cardValue(bestSoFar) && c.suit === bestSoFar.suit)
      if (winners.length > 0) {
        return winners.sort((a, b) => cardValue(a) - cardValue(b))[0]
      }
    }

    // Can't win — play lowest
    return following.sort((a, b) => cardValue(a) - cardValue(b))[0]
  }

  // Void in led suit — trump if possible
  const trumpSuitStr = state.trumpSuit === 'nt' ? null : state.trumpSuit
  if (trumpSuitStr) {
    const trumpCards = valid.filter(c => c.suit === trumpSuitStr)
    if (trumpCards.length > 0) {
      const currentWinnerPlayer = trickWinner(state.currentTrick, state.trumpSuit)
      const partnerIdx = partnerOf(state.currentPlayer)
      if (currentWinnerPlayer === partnerIdx) {
        // Don't trump partner — discard lowest
        const nonTrump = valid.filter(c => c.suit !== trumpSuitStr)
        if (nonTrump.length > 0) return nonTrump.sort((a, b) => cardValue(a) - cardValue(b))[0]
      }
      return trumpCards.sort((a, b) => cardValue(a) - cardValue(b))[0]
    }
  }

  // Discard lowest
  return valid.sort((a, b) => cardValue(a) - cardValue(b))[0]
}

function getBestCard(trick: TrickCard[], trumpSuit: Strain | null): Card | null {
  if (trick.length === 0) return null
  const winnerIdx = trickWinner(trick, trumpSuit)
  return trick.find(t => t.player === winnerIdx)?.card ?? null
}

// ── Trick resolution ─────────────────────────────────────────────────

function trickWinner(trick: TrickCard[], trumpSuit: Strain | null): number {
  if (trick.length === 0) return 0

  const ledSuit = trick[0].card.suit
  const trumpStr = trumpSuit === 'nt' ? null : trumpSuit as Suit | null

  let best = trick[0]

  for (let i = 1; i < trick.length; i++) {
    const c = trick[i].card
    const bestCard = best.card

    if (trumpStr) {
      // Trump beats non-trump
      if (c.suit === trumpStr && bestCard.suit !== trumpStr) {
        best = trick[i]
        continue
      }
      // Both trump — higher wins
      if (c.suit === trumpStr && bestCard.suit === trumpStr) {
        if (cardValue(c) > cardValue(bestCard)) {
          best = trick[i]
        }
        continue
      }
      // Current best is trump, challenger is not — best stays
      if (bestCard.suit === trumpStr && c.suit !== trumpStr) {
        continue
      }
    }

    // No trump involved — must match led suit and be higher
    if (c.suit === ledSuit && (bestCard.suit !== ledSuit || cardValue(c) > cardValue(bestCard))) {
      best = trick[i]
    }
  }

  return best.player
}

function completeTrick(state: BridgeState): BridgeState {
  const winner = trickWinner(state.currentTrick, state.trumpSuit)
  const tricksWon = [...state.tricksWon]
  tricksWon[winner]++

  const totalTricks = tricksWon.reduce((a, b) => a + b, 0)

  if (totalTricks === 13) {
    return resolveHand({ ...state, currentTrick: [], tricksWon, lastTrickWinner: winner })
  }

  let next: BridgeState = {
    ...state,
    currentTrick: [],
    tricksWon,
    currentPlayer: winner,
    ledSuit: null,
    lastTrickWinner: winner,
    phase: 'playing',
    message: winner === 0 ? 'You won the trick — lead next'
      : winner === state.dummy ? `${PLAYER_NAMES[winner]} (dummy) won — ${state.declarer === 0 ? 'you lead' : PLAYER_NAMES[state.declarer!] + ' leads'}`
        : `${PLAYER_NAMES[winner]} won the trick`,
  }

  // If winner is dummy, it's actually dummy's turn but declarer controls
  if (winner !== 0 && !(winner === state.dummy && state.declarer === 0)) {
    next = runAiTurns(next)
  }

  return next
}

// ── Hand resolution & scoring ────────────────────────────────────────

function resolveHand(state: BridgeState): BridgeState {
  const contract = state.contract!
  const declarer = state.declarer!
  const declarerTeam = playerTeam(declarer)

  // Count tricks for declaring team
  const p1 = declarerTeam === 0 ? 0 : 1
  const p2 = declarerTeam === 0 ? 2 : 3
  const tricksTaken = state.tricksWon[p1] + state.tricksWon[p2]

  const { points, breakdown } = scoreHand(contract, tricksTaken, declarerTeam)

  const teamScores = [...state.teamScores]
  teamScores[declarerTeam] += points

  // Check for game over
  const gameOver = teamScores[0] >= WINNING_SCORE || teamScores[1] >= WINNING_SCORE

  if (gameOver) {
    const humanWin = teamScores[0] > teamScores[1]
    return {
      ...state,
      teamScores,
      phase: 'gameOver',
      message: humanWin
        ? `You win! ${breakdown}`
        : `Opponents win! ${breakdown}`,
    }
  }

  return {
    ...state,
    teamScores,
    phase: 'handOver',
    message: `${breakdown} | Scores: ${TEAM_NAMES[0]} ${teamScores[0]} — ${TEAM_NAMES[1]} ${teamScores[1]}`,
  }
}

// ── Scoring ──────────────────────────────────────────────────────────

export function scoreHand(
  contract: Bid,
  tricksTaken: number,
  _declarerTeam: number,
): { points: number; breakdown: string } {
  const level = contract.level
  const strain = contract.strain!
  const needed = 6 + level

  if (tricksTaken < needed) {
    // Failed contract — undertricks
    const under = needed - tricksTaken
    const points = under * -50
    return { points, breakdown: `Down ${under} (${points})` }
  }

  // Contract made
  const overtricks = tricksTaken - needed

  // Trick points (for contracted tricks only)
  let trickPoints = 0
  if (strain === 'clubs' || strain === 'diamonds') {
    trickPoints = level * 20
  } else if (strain === 'hearts' || strain === 'spades') {
    trickPoints = level * 30
  } else {
    // NT: 40 first + 30 each after
    trickPoints = 40 + (level - 1) * 30
  }

  // Game/partial bonus
  let bonus = 0
  let bonusLabel = ''
  if (trickPoints >= 100) {
    bonus = 300
    bonusLabel = ' + game bonus 300'
  } else {
    bonus = 50
    bonusLabel = ' + partial bonus 50'
  }

  // Overtrick points (same per-trick value)
  let overtrickPoints = 0
  if (overtricks > 0) {
    if (strain === 'clubs' || strain === 'diamonds') {
      overtrickPoints = overtricks * 20
    } else if (strain === 'hearts' || strain === 'spades') {
      overtrickPoints = overtricks * 30
    } else {
      overtrickPoints = overtricks * 30
    }
  }

  // Slam bonuses
  let slamBonus = 0
  let slamLabel = ''
  if (level === 7 && tricksTaken >= 13) {
    slamBonus = 1000
    slamLabel = ' + grand slam 1000'
  } else if (level === 6 && tricksTaken >= 12) {
    slamBonus = 500
    slamLabel = ' + small slam 500'
  }

  const points = trickPoints + bonus + overtrickPoints + slamBonus
  const made = overtricks > 0 ? `Made ${level}+${overtricks}` : `Made ${level}`
  const breakdown = `${made}: ${trickPoints} tricks${bonusLabel}${overtrickPoints > 0 ? ` + ${overtrickPoints} overtricks` : ''}${slamLabel} = ${points}`

  return { points, breakdown }
}

// ── Next hand ────────────────────────────────────────────────────────

export function nextHand(state: BridgeState): BridgeState {
  const newDealer = (state.dealer + 1) % 4
  return dealHand({
    ...state,
    dealer: newDealer,
  })
}

// ── Display helpers ──────────────────────────────────────────────────

export function strainSymbol(strain: Strain): string {
  switch (strain) {
    case 'clubs': return '\u2663'
    case 'diamonds': return '\u2666'
    case 'hearts': return '\u2665'
    case 'spades': return '\u2660'
    case 'nt': return 'NT'
  }
}

export function strainName(strain: Strain): string {
  switch (strain) {
    case 'clubs': return 'Clubs'
    case 'diamonds': return 'Diamonds'
    case 'hearts': return 'Hearts'
    case 'spades': return 'Spades'
    case 'nt': return 'No Trump'
  }
}

export function formatBid(bid: Bid): string {
  if (bid.level === 0) return 'Pass'
  return `${bid.level}${strainSymbol(bid.strain!)}`
}
