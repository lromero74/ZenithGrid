/**
 * Texas Hold'em engine — pure logic, no React.
 *
 * 2-4 players (1 human + AI). Standard poker rules with blinds,
 * community cards, and best-5-from-7 hand evaluation.
 */

import { createDeck, shuffleDeck, type Card } from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

export type Phase = 'preflop' | 'flop' | 'turn' | 'river' | 'showdown' | 'handOver' | 'gameOver'

export interface HandResult {
  rank: number          // 1-10
  tiebreaker: number[]  // for comparing same-rank hands
  name: string
  cards: Card[]         // the 5 cards making the hand
}

export interface TexasHoldemState {
  hands: Card[][]
  community: Card[]
  deck: Card[]
  pot: number
  bets: number[]
  chips: number[]
  phase: Phase
  currentPlayer: number
  dealerIdx: number
  smallBlind: number
  bigBlind: number
  foldedPlayers: boolean[]
  allInPlayers: boolean[]
  currentBet: number
  message: string
  lastAction: string
  roundBets: number[]
  showdownResults: HandResult[] | null
  actedThisRound: boolean[]
  sbIdx: number
  bbIdx: number
  blindLevel: number
  raiseCount: number
}

// ── Helpers ──────────────────────────────────────────────────────────

/** Convert rank to comparison value (Ace = 14). */
function compareRank(rank: number): number {
  return rank === 1 ? 14 : rank
}

function nextActivePlayer(state: TexasHoldemState, from: number): number {
  const n = state.hands.length
  let next = (from + 1) % n
  let tries = 0
  while (tries < n) {
    if (!state.foldedPlayers[next] && !state.allInPlayers[next] && state.chips[next] > 0) {
      return next
    }
    next = (next + 1) % n
    tries++
  }
  return from // no other active player
}

function nonFoldedPlayers(state: TexasHoldemState): number {
  return state.foldedPlayers.filter(f => !f).length
}

function playersStillActing(state: TexasHoldemState): number {
  return state.foldedPlayers.filter((f, i) => !f && !state.allInPlayers[i] && state.chips[i] > 0).length
}

/** Check if betting round is complete. */
function isBettingRoundComplete(state: TexasHoldemState): boolean {
  const n = state.hands.length
  for (let i = 0; i < n; i++) {
    if (state.foldedPlayers[i] || state.allInPlayers[i]) continue
    if (state.chips[i] === 0) continue
    // Player must have acted AND matched the current bet
    if (!state.actedThisRound[i] || state.bets[i] < state.currentBet) return false
  }
  return true
}

// ── Hand Evaluator ───────────────────────────────────────────────────

/** Get all C(n,5) combinations of 5 cards from n cards. */
function combinations5(cards: Card[]): Card[][] {
  const result: Card[][] = []
  const n = cards.length
  for (let a = 0; a < n - 4; a++)
    for (let b = a + 1; b < n - 3; b++)
      for (let c = b + 1; c < n - 2; c++)
        for (let d = c + 1; d < n - 1; d++)
          for (let e = d + 1; e < n; e++)
            result.push([cards[a], cards[b], cards[c], cards[d], cards[e]])
  return result
}

function evaluate5(cards: Card[]): HandResult {
  const ranks = cards.map(c => compareRank(c.rank)).sort((a, b) => b - a)
  const suits = cards.map(c => c.suit)
  const isFlush = suits.every(s => s === suits[0])

  // Check straight
  let isStraight = false
  let straightHigh = 0
  // Normal straight check
  if (ranks[0] - ranks[4] === 4 && new Set(ranks).size === 5) {
    isStraight = true
    straightHigh = ranks[0]
  }
  // Wheel: A-2-3-4-5 (ranks sorted: [14, 5, 4, 3, 2])
  if (!isStraight && ranks[0] === 14 && ranks[1] === 5 && ranks[2] === 4 && ranks[3] === 3 && ranks[4] === 2) {
    isStraight = true
    straightHigh = 5
  }

  // Count ranks
  const counts = new Map<number, number>()
  for (const r of ranks) counts.set(r, (counts.get(r) ?? 0) + 1)
  const countValues = Array.from(counts.values()).sort((a, b) => b - a)
  const countEntries = Array.from(counts.entries()).sort((a, b) => {
    if (b[1] !== a[1]) return b[1] - a[1]
    return b[0] - a[0]
  })

  // Royal Flush
  if (isFlush && isStraight && straightHigh === 14) {
    return { rank: 10, tiebreaker: [], name: 'Royal Flush', cards }
  }

  // Straight Flush
  if (isFlush && isStraight) {
    return { rank: 9, tiebreaker: [straightHigh], name: 'Straight Flush', cards }
  }

  // Four of a Kind
  if (countValues[0] === 4) {
    const quadRank = countEntries[0][0]
    const kicker = countEntries[1][0]
    return { rank: 8, tiebreaker: [quadRank, kicker], name: 'Four of a Kind', cards }
  }

  // Full House
  if (countValues[0] === 3 && countValues[1] === 2) {
    const tripRank = countEntries[0][0]
    const pairRank = countEntries[1][0]
    return { rank: 7, tiebreaker: [tripRank, pairRank], name: 'Full House', cards }
  }

  // Flush
  if (isFlush) {
    return { rank: 6, tiebreaker: ranks, name: 'Flush', cards }
  }

  // Straight
  if (isStraight) {
    return { rank: 5, tiebreaker: [straightHigh], name: 'Straight', cards }
  }

  // Three of a Kind
  if (countValues[0] === 3) {
    const tripRank = countEntries[0][0]
    const kickers = countEntries.slice(1).map(e => e[0])
    return { rank: 4, tiebreaker: [tripRank, ...kickers], name: 'Three of a Kind', cards }
  }

  // Two Pair
  if (countValues[0] === 2 && countValues[1] === 2) {
    const pair1 = Math.max(countEntries[0][0], countEntries[1][0])
    const pair2 = Math.min(countEntries[0][0], countEntries[1][0])
    const kicker = countEntries[2][0]
    return { rank: 3, tiebreaker: [pair1, pair2, kicker], name: 'Two Pair', cards }
  }

  // One Pair
  if (countValues[0] === 2) {
    const pairRank = countEntries[0][0]
    const kickers = countEntries.slice(1).map(e => e[0])
    return { rank: 2, tiebreaker: [pairRank, ...kickers], name: 'Pair', cards }
  }

  // High Card
  return { rank: 1, tiebreaker: ranks, name: 'High Card', cards }
}

/** Evaluate the best 5-card hand from 5-7 cards. */
export function evaluateHand(cards: Card[]): HandResult {
  if (cards.length === 5) return evaluate5(cards)

  const combos = combinations5(cards)
  let best: HandResult = evaluate5(combos[0])
  for (let i = 1; i < combos.length; i++) {
    const result = evaluate5(combos[i])
    if (compareHands(result, best) > 0) {
      best = result
    }
  }
  return best
}

/** Compare two hand results. Returns positive if a > b, negative if a < b, 0 if tie. */
function compareHands(a: HandResult, b: HandResult): number {
  if (a.rank !== b.rank) return a.rank - b.rank
  for (let i = 0; i < Math.max(a.tiebreaker.length, b.tiebreaker.length); i++) {
    const av = a.tiebreaker[i] ?? 0
    const bv = b.tiebreaker[i] ?? 0
    if (av !== bv) return av - bv
  }
  return 0
}

// ── Game Creation ────────────────────────────────────────────────────

export function createTexasHoldemGame(playerCount: number = 4): TexasHoldemState {
  return {
    hands: Array.from({ length: playerCount }, () => []),
    community: [],
    deck: [],
    pot: 0,
    bets: new Array(playerCount).fill(0),
    chips: new Array(playerCount).fill(1000),
    phase: 'preflop',
    currentPlayer: 0,
    dealerIdx: 0,
    smallBlind: 10,
    bigBlind: 20,
    foldedPlayers: new Array(playerCount).fill(false),
    allInPlayers: new Array(playerCount).fill(false),
    currentBet: 0,
    message: '',
    lastAction: '',
    roundBets: new Array(playerCount).fill(0),
    showdownResults: null,
    actedThisRound: new Array(playerCount).fill(false),
    sbIdx: 0,
    bbIdx: 0,
    blindLevel: 0,
    raiseCount: 0,
  }
}

export function startHand(state: TexasHoldemState): TexasHoldemState {
  const n = state.hands.length
  const deck = shuffleDeck(createDeck()).map(c => ({ ...c, faceUp: true }))

  // Deal 2 cards each (only to players with chips or who can post blinds)
  const hands: Card[][] = []
  let idx = 0
  for (let i = 0; i < n; i++) {
    if (state.chips[i] > 0) {
      hands.push([deck[idx], deck[idx + 1]])
      idx += 2
    } else {
      hands.push([])
    }
  }

  const remaining = deck.slice(idx)

  // Post blinds
  const bets = new Array(n).fill(0)
  const chips = [...state.chips]
  const foldedPlayers = new Array(n).fill(false)
  const allInPlayers = new Array(n).fill(false)

  // Find SB and BB positions (skip eliminated players)
  let sbPos = (state.dealerIdx + 1) % n
  while (chips[sbPos] <= 0) sbPos = (sbPos + 1) % n
  let bbPos = (sbPos + 1) % n
  while (chips[bbPos] <= 0) bbPos = (bbPos + 1) % n

  // Post small blind
  const sbAmount = Math.min(state.smallBlind, chips[sbPos])
  bets[sbPos] = sbAmount
  chips[sbPos] -= sbAmount
  if (chips[sbPos] === 0) allInPlayers[sbPos] = true

  // Post big blind
  const bbAmount = Math.min(state.bigBlind, chips[bbPos])
  bets[bbPos] = bbAmount
  chips[bbPos] -= bbAmount
  if (chips[bbPos] === 0) allInPlayers[bbPos] = true

  const pot = sbAmount + bbAmount

  // UTG is first to act (left of BB)
  let utg = (bbPos + 1) % n
  while ((chips[utg] <= 0 && !allInPlayers[utg]) || foldedPlayers[utg]) {
    if (hands[utg].length === 0) { foldedPlayers[utg] = true }
    utg = (utg + 1) % n
  }

  // Mark eliminated players as folded
  for (let i = 0; i < n; i++) {
    if (hands[i].length === 0) foldedPlayers[i] = true
  }

  return {
    ...state,
    hands,
    community: [],
    deck: remaining,
    pot,
    bets,
    chips,
    phase: 'preflop',
    currentPlayer: utg,
    foldedPlayers,
    allInPlayers,
    currentBet: state.bigBlind,
    message: 'Pre-flop betting',
    lastAction: '',
    roundBets: [...bets],
    showdownResults: null,
    actedThisRound: new Array(n).fill(false),
    sbIdx: sbPos,
    bbIdx: bbPos,
    raiseCount: 0,
  }
}

// ── Player Actions ───────────────────────────────────────────────────

function afterAction(state: TexasHoldemState): TexasHoldemState {
  // Check if only one non-folded player remains
  if (nonFoldedPlayers(state) === 1) {
    const winner = state.foldedPlayers.findIndex(f => !f)
    const chips = [...state.chips]
    chips[winner] += state.pot
    let bonusMsg = ''
    if (hasBonusHand(state.hands[winner])) {
      chips[winner] += BONUS_AMOUNT
      bonusMsg = ` +${BONUS_AMOUNT} chip bonus!`
    }
    return {
      ...state,
      chips,
      pot: 0,
      phase: 'handOver',
      message: `${winner === 0 ? 'You win' : `Player ${winner + 1} wins`} the pot!${bonusMsg}`,
    }
  }

  // Find next active player
  const next = nextActivePlayer(state, state.currentPlayer)

  // Check if betting round complete
  if (next === state.currentPlayer || isBettingRoundComplete({ ...state, currentPlayer: next })) {
    // All bets settled — check if we should auto-advance to showdown
    if (playersStillActing(state) <= 1) {
      // Everyone is folded or all-in — deal remaining community cards
      return autoComplete(state)
    }
    return advancePhase(state)
  }

  return { ...state, currentPlayer: next }
}

/** Deal remaining community and go to showdown when only all-in players remain. */
function autoComplete(state: TexasHoldemState): TexasHoldemState {
  let current = { ...state }
  while (current.community.length < 5 && current.deck.length > 0) {
    const card = current.deck[0]
    current = {
      ...current,
      community: [...current.community, card],
      deck: current.deck.slice(1),
    }
  }
  return showdown(current)
}

export function fold(state: TexasHoldemState): TexasHoldemState {
  const foldedPlayers = [...state.foldedPlayers]
  foldedPlayers[state.currentPlayer] = true
  const actedThisRound = [...state.actedThisRound]
  actedThisRound[state.currentPlayer] = true
  return afterAction({
    ...state,
    foldedPlayers,
    actedThisRound,
    lastAction: `Player ${state.currentPlayer} folds`,
  })
}

export function check(state: TexasHoldemState): TexasHoldemState {
  const actedThisRound = [...state.actedThisRound]
  actedThisRound[state.currentPlayer] = true
  return afterAction({
    ...state,
    actedThisRound,
    lastAction: `Player ${state.currentPlayer} checks`,
  })
}

export function call(state: TexasHoldemState): TexasHoldemState {
  const player = state.currentPlayer
  const toCall = state.currentBet - state.bets[player]
  const actualCall = Math.min(toCall, state.chips[player])

  const bets = [...state.bets]
  const chips = [...state.chips]
  const roundBets = [...state.roundBets]
  const allInPlayers = [...state.allInPlayers]

  bets[player] += actualCall
  chips[player] -= actualCall
  roundBets[player] += actualCall

  if (chips[player] === 0) allInPlayers[player] = true

  const actedThisRound = [...state.actedThisRound]
  actedThisRound[player] = true

  return afterAction({
    ...state,
    bets,
    chips,
    roundBets,
    allInPlayers,
    actedThisRound,
    pot: state.pot + actualCall,
    lastAction: `Player ${player} calls ${actualCall}`,
  })
}

export function raise(state: TexasHoldemState, amount: number): TexasHoldemState {
  const player = state.currentPlayer
  const additional = amount - state.bets[player]

  const bets = [...state.bets]
  const chips = [...state.chips]
  const roundBets = [...state.roundBets]
  const allInPlayers = [...state.allInPlayers]

  bets[player] = amount
  chips[player] -= additional
  roundBets[player] += additional

  if (chips[player] === 0) allInPlayers[player] = true

  // Raise resets acted flags — all other players must respond
  const actedThisRound = new Array(state.hands.length).fill(false)
  actedThisRound[player] = true

  return afterAction({
    ...state,
    bets,
    chips,
    roundBets,
    allInPlayers,
    actedThisRound,
    pot: state.pot + additional,
    currentBet: amount,
    raiseCount: state.raiseCount + 1,
    lastAction: `Player ${player} raises to ${amount}`,
  })
}

export function allIn(state: TexasHoldemState): TexasHoldemState {
  const player = state.currentPlayer
  const allChips = state.chips[player]
  const totalBet = state.bets[player] + allChips

  const bets = [...state.bets]
  const chips = [...state.chips]
  const roundBets = [...state.roundBets]
  const allInPlayers = [...state.allInPlayers]

  bets[player] = totalBet
  chips[player] = 0
  roundBets[player] += allChips
  allInPlayers[player] = true

  const newCurrentBet = Math.max(state.currentBet, totalBet)

  // If all-in exceeds current bet, it's a raise — reset acted flags
  const actedThisRound = totalBet > state.currentBet
    ? new Array(state.hands.length).fill(false)
    : [...state.actedThisRound]
  actedThisRound[player] = true

  return afterAction({
    ...state,
    bets,
    chips,
    roundBets,
    allInPlayers,
    actedThisRound,
    pot: state.pot + allChips,
    currentBet: newCurrentBet,
    lastAction: `Player ${player} goes all-in for ${allChips}`,
  })
}

// ── Phase Advancement ────────────────────────────────────────────────

export function advancePhase(state: TexasHoldemState): TexasHoldemState {
  const n = state.hands.length
  const deck = [...state.deck]
  let community = [...state.community]
  let nextPhase: Phase

  switch (state.phase) {
    case 'preflop':
      community = [...community, deck.shift()!, deck.shift()!, deck.shift()!]
      nextPhase = 'flop'
      break
    case 'flop':
      community = [...community, deck.shift()!]
      nextPhase = 'turn'
      break
    case 'turn':
      community = [...community, deck.shift()!]
      nextPhase = 'river'
      break
    case 'river':
      return showdown(state)
    default:
      return state
  }

  // Flop bonus: add 1000 to pot for special flop patterns
  let flopBonus = 0
  let flopBonusMsg = ''
  if (nextPhase === 'flop' && community.length === 3) {
    const [c1, c2, c3] = community
    const ranks = [compareRank(c1.rank), compareRank(c2.rank), compareRank(c3.rank)].sort((a, b) => a - b)
    const allSameRank = ranks[0] === ranks[1] && ranks[1] === ranks[2]
    const isRun = ranks[2] - ranks[0] === 2 && new Set(ranks).size === 3
    const allSameSuit = c1.suit === c2.suit && c2.suit === c3.suit
    if (allSameRank || isRun || allSameSuit) {
      flopBonus = 1000
      const reason = allSameRank ? 'three of a kind' : isRun ? 'a run' : 'suited flop'
      flopBonusMsg = ` Flop bonus: +1000 pot (${reason})!`
    }
  }

  // Reset round bets, find first active player after dealer
  const bets = new Array(n).fill(0)
  let firstPlayer = (state.dealerIdx + 1) % n
  while (state.foldedPlayers[firstPlayer] || (state.chips[firstPlayer] === 0 && !state.allInPlayers[firstPlayer])) {
    firstPlayer = (firstPlayer + 1) % n
  }
  // Skip all-in players for current player
  while (state.allInPlayers[firstPlayer] || state.foldedPlayers[firstPlayer]) {
    firstPlayer = (firstPlayer + 1) % n
  }

  return {
    ...state,
    deck,
    community,
    phase: nextPhase,
    pot: state.pot + flopBonus,
    bets,
    currentBet: 0,
    currentPlayer: firstPlayer,
    actedThisRound: new Array(n).fill(false),
    raiseCount: 0,
    message: `${nextPhase.charAt(0).toUpperCase() + nextPhase.slice(1)} betting${flopBonusMsg}`,
  }
}

// ── Bonus Hands ─────────────────────────────────────────────────────

const BONUS_HANDS: [number, number][] = [[11, 11], [2, 3], [12, 7], [11, 2]]
const BONUS_AMOUNT = 1000

/** Check if a player's hole cards match a bonus combo (order-independent). */
function hasBonusHand(hand: Card[]): boolean {
  if (hand.length !== 2) return false
  const [a, b] = [hand[0].rank, hand[1].rank]
  return BONUS_HANDS.some(([x, y]) => (a === x && b === y) || (a === y && b === x))
}

// ── Showdown ─────────────────────────────────────────────────────────

export function showdown(state: TexasHoldemState): TexasHoldemState {
  const n = state.hands.length
  const results: HandResult[] = []

  for (let i = 0; i < n; i++) {
    if (state.foldedPlayers[i] || state.hands[i].length === 0) {
      results.push({ rank: 0, tiebreaker: [], name: 'Folded', cards: [] })
    } else {
      const allCards = [...state.hands[i], ...state.community]
      results.push(evaluateHand(allCards))
    }
  }

  // Find winner(s)
  let bestRank = 0
  let bestTiebreaker: number[] = []
  const winners: number[] = []

  for (let i = 0; i < n; i++) {
    if (state.foldedPlayers[i]) continue
    const r = results[i]
    const cmp = compareHands(r, { rank: bestRank, tiebreaker: bestTiebreaker, name: '', cards: [] })
    if (cmp > 0) {
      bestRank = r.rank
      bestTiebreaker = r.tiebreaker
      winners.length = 0
      winners.push(i)
    } else if (cmp === 0 && bestRank > 0) {
      winners.push(i)
    }
  }

  // Distribute pot
  const chips = [...state.chips]
  if (winners.length === 1) {
    chips[winners[0]] += state.pot
  } else {
    const share = Math.floor(state.pot / winners.length)
    const remainder = state.pot - share * winners.length
    for (const w of winners) {
      chips[w] += share
    }
    if (remainder > 0) chips[winners[0]] += remainder
  }

  // Bonus for special hole cards
  let bonusMsg = ''
  for (const w of winners) {
    if (hasBonusHand(state.hands[w])) {
      chips[w] += BONUS_AMOUNT
      const name = w === 0 ? 'You' : `Player ${w + 1}`
      bonusMsg += ` ${name} earned a ${BONUS_AMOUNT} chip bonus!`
    }
  }

  const winnerNames = winners.map(w => w === 0 ? 'You' : `Player ${w + 1}`).join(', ')
  const winnerHand = results[winners[0]]

  return {
    ...state,
    chips,
    pot: 0,
    phase: 'handOver',
    showdownResults: results,
    message: `${winnerNames} win${winners.length === 1 && winners[0] !== 0 ? 's' : ''} with ${winnerHand.name}!${bonusMsg}`,
  }
}

// ── Valid Actions ────────────────────────────────────────────────────

export function getValidActions(state: TexasHoldemState): string[] {
  const player = state.currentPlayer
  const toCall = state.currentBet - state.bets[player]
  const actions: string[] = ['fold']

  if (toCall <= 0) {
    actions.push('check')
  }

  if (toCall > 0 && state.chips[player] >= toCall) {
    actions.push('call')
  }

  const minRaise = getMinRaise(state)
  if (state.chips[player] > toCall && state.chips[player] + state.bets[player] >= minRaise) {
    actions.push('raise')
  }

  actions.push('allIn')

  return actions
}

export function getMinRaise(state: TexasHoldemState): number {
  return state.currentBet + state.bigBlind
}

// ── AI ───────────────────────────────────────────────────────────────

function aiHandStrength(hand: Card[], community: Card[]): number {
  if (community.length === 0) {
    // Pre-flop: Sklansky-inspired hand ranking
    const r1 = compareRank(hand[0].rank)
    const r2 = compareRank(hand[1].rank)
    const paired = r1 === r2
    const suited = hand[0].suit === hand[1].suit
    const high = Math.max(r1, r2)
    const low = Math.min(r1, r2)
    const gap = high - low

    let score = high
    if (paired) score += high >= 10 ? 20 : 15      // premium pairs score higher
    if (suited) score += 4
    if (gap <= 1) score += 3                         // connectors
    else if (gap <= 2) score += 2                    // one-gappers
    else if (gap <= 3) score += 1                    // two-gappers
    if (high >= 12 && low >= 10) score += 5          // broadway
    if (high === 14) score += 3                      // ace bonus
    return score
  }

  const result = evaluateHand([...hand, ...community])
  // Weight hand rank heavily, add tiebreaker for differentiation
  return result.rank * 12 + (result.tiebreaker[0] ?? 0) / 10
}

/** Estimate draw potential (flush/straight draws). */
function aiDrawStrength(hand: Card[], community: Card[]): number {
  if (community.length === 0 || community.length >= 5) return 0
  const allCards = [...hand, ...community]

  // Flush draw: 4 cards of same suit
  const suitCounts = new Map<string, number>()
  for (const c of allCards) suitCounts.set(c.suit, (suitCounts.get(c.suit) ?? 0) + 1)
  const maxSuit = Math.max(...suitCounts.values())
  let draw = 0
  if (maxSuit === 4) draw += 8  // flush draw

  // Straight draw: count unique ranks in sequence
  const ranks = [...new Set(allCards.map(c => compareRank(c.rank)))].sort((a, b) => a - b)
  for (let i = 0; i < ranks.length - 3; i++) {
    const span = ranks[Math.min(i + 3, ranks.length - 1)] - ranks[i]
    if (span <= 4) { draw += 6; break }  // open-ended or gutshot
  }

  return draw
}

export function aiAction(state: TexasHoldemState): TexasHoldemState {
  const player = state.currentPlayer
  const actions = getValidActions(state)
  const hand = state.hands[player]
  const strength = aiHandStrength(hand, state.community)
  const draws = aiDrawStrength(hand, state.community)
  const effectiveStrength = strength + draws
  const toCall = state.currentBet - state.bets[player]
  const potOdds = state.pot > 0 ? toCall / (state.pot + toCall) : 0

  // After 3+ raises in a round, AI commits all-in with any reasonable hand
  if (state.raiseCount >= 3 && effectiveStrength > 15) {
    return allIn(state)
  }

  // Very strong hand or monster draw: raise aggressively or all-in
  if (effectiveStrength > 35) {
    // Slow-play occasionally with monster hands post-flop
    if (state.community.length > 0 && Math.random() < 0.15) {
      if (actions.includes('call') && toCall > 0) return call(state)
      if (actions.includes('check')) return check(state)
    }
    if (actions.includes('raise')) {
      const multiplier = effectiveStrength > 50 ? 4 : 3
      const raiseAmount = Math.min(
        state.currentBet + state.bigBlind * multiplier,
        state.bets[player] + state.chips[player]
      )
      return raise(state, Math.max(raiseAmount, getMinRaise(state)))
    }
    if (actions.includes('call')) return call(state)
    if (actions.includes('check')) return check(state)
  }

  // Strong hand: raise
  if (effectiveStrength > 25 || (effectiveStrength > 20 && Math.random() < 0.25)) {
    if (actions.includes('raise')) {
      const raiseAmount = Math.min(
        state.currentBet + state.bigBlind * 2,
        state.bets[player] + state.chips[player]
      )
      return raise(state, Math.max(raiseAmount, getMinRaise(state)))
    }
    if (actions.includes('call')) return call(state)
    if (actions.includes('check')) return check(state)
  }

  // Medium hand: call if pot odds are right
  if (effectiveStrength > 14 || (toCall <= state.bigBlind * 2 && effectiveStrength > 10)) {
    // Consider pot odds — only call if the price is right
    if (potOdds < 0.4 || effectiveStrength > 18) {
      if (actions.includes('call')) return call(state)
      if (actions.includes('check')) return check(state)
    }
  }

  // Check if free
  if (actions.includes('check')) return check(state)

  // Weak hand with small bet: sometimes call (but less often)
  if (toCall <= state.bigBlind && Math.random() < 0.35) {
    if (actions.includes('call')) return call(state)
  }

  // Bluff raise occasionally with nothing (post-flop only)
  if (state.community.length >= 3 && Math.random() < 0.08 && actions.includes('raise')) {
    const raiseAmount = Math.min(
      state.currentBet + state.bigBlind * 2,
      state.bets[player] + state.chips[player]
    )
    return raise(state, Math.max(raiseAmount, getMinRaise(state)))
  }

  // Fold
  return fold(state)
}

// ── New Hand / Game Flow ─────────────────────────────────────────────

export function nextHand(state: TexasHoldemState): TexasHoldemState {
  // Check if game is over (only 1 player with chips)
  const playersWithChips = state.chips.filter(c => c > 0).length
  if (playersWithChips <= 1) {
    const winner = state.chips.findIndex(c => c > 0)
    return {
      ...state,
      phase: 'gameOver',
      message: winner === 0 ? 'You win the tournament!' : `Player ${winner + 1} wins the tournament.`,
    }
  }

  // Advance dealer
  let newDealer = (state.dealerIdx + 1) % state.hands.length
  while (state.chips[newDealer] <= 0) newDealer = (newDealer + 1) % state.hands.length

  return startHand({ ...state, dealerIdx: newDealer })
}

/** Increase blinds to the given level (0 = 10/20, 1 = 20/40, 2 = 40/80, ...). */
export function setBlinds(state: TexasHoldemState, level: number): TexasHoldemState {
  const sb = 10 * Math.pow(2, level)
  const bb = 20 * Math.pow(2, level)
  return { ...state, smallBlind: sb, bigBlind: bb, blindLevel: level }
}
