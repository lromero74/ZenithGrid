/**
 * Cribbage VS — two human players compete head-to-head.
 *
 * Host-authoritative: host runs the cribbage engine, broadcasts state.
 * Each player sees their own hand face-up and opponent's hand face-down.
 * First to 121 points wins.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { Wifi } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE, CARD_SIZE_XS } from '../../PlayingCard'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'
import { createDeck, shuffleDeck, type Card, type Suit } from '../../../utils/cardUtils'

// ── Constants ────────────────────────────────────────────────────────

const WIN_SCORE = 121

// ── Types ────────────────────────────────────────────────────────────

interface PegCard {
  card: Card
  player: number
}

type Phase = 'discard' | 'pegging' | 'scoring' | 'gameOver'
type ScoringStep = 'nonDealer' | 'dealer' | 'crib' | 'done'

interface VsCribbageState {
  hands: [Card[], Card[]]
  originalHands: [Card[], Card[]]
  crib: Card[]
  cutCard: Card | null
  pegCards: PegCard[]
  pegTotal: number
  currentPlayer: number
  dealer: number
  scores: [number, number]
  phase: Phase
  message: string
  selectedForCrib: [number[], number[]]   // both players' selections
  cribSubmitted: [boolean, boolean]
  pegHistory: PegCard[]
  canPlay: [boolean, boolean]
  scoringStep: ScoringStep
  lastScoreBreakdown: string
  playedIndices: [Set<number>, Set<number>]  // track pegged card indices per player
}

/** What the guest sees — stripped of opponent's hand and deck. */
interface GuestViewState {
  myHand: Card[]
  oppHandCount: number
  crib: Card[]
  cutCard: Card | null
  pegCards: PegCard[]
  pegTotal: number
  currentPlayer: number
  dealer: number
  scores: [number, number]
  phase: Phase
  message: string
  mySelectedForCrib: number[]
  myCribSubmitted: boolean
  oppCribSubmitted: boolean
  pegHistory: PegCard[]
  canPlay: [boolean, boolean]
  scoringStep: ScoringStep
  lastScoreBreakdown: string
  myPlayedIndices: number[]
  oppPlayedCount: number
  oppHand: Card[]  // shown during scoring
}

// ── Card value helpers ──────────────────────────────────────────────

function pegValue(card: Card): number {
  if (card.rank >= 11) return 10
  return card.rank
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
    hearts: '\u2665', diamonds: '\u2666', clubs: '\u2663', spades: '\u2660',
  }
  return symbols[suit]
}

// ── Scoring helpers ─────────────────────────────────────────────────

function count15s(cards: Card[]): number {
  const values = cards.map(pegValue)
  let combos = 0
  const n = values.length
  for (let mask = 1; mask < (1 << n); mask++) {
    let sum = 0
    for (let i = 0; i < n; i++) {
      if (mask & (1 << i)) sum += values[i]
    }
    if (sum === 15) combos++
  }
  return combos * 2
}

function countPairs(cards: Card[]): number {
  let pairs = 0
  for (let i = 0; i < cards.length; i++) {
    for (let j = i + 1; j < cards.length; j++) {
      if (cards[i].rank === cards[j].rank) pairs++
    }
  }
  return pairs * 2
}

function countRuns(cards: Card[]): number {
  if (cards.length < 3) return 0
  const rankCounts: Map<number, number> = new Map()
  for (const c of cards) rankCounts.set(c.rank, (rankCounts.get(c.rank) || 0) + 1)
  const sortedRanks = [...rankCounts.keys()].sort((a, b) => a - b)
  if (sortedRanks.length < 3) return 0
  let total = 0
  let start = 0
  for (let i = 1; i <= sortedRanks.length; i++) {
    if (i === sortedRanks.length || sortedRanks[i] !== sortedRanks[i - 1] + 1) {
      const len = i - start
      if (len >= 3) {
        let mult = 1
        for (let j = start; j < i; j++) mult *= rankCounts.get(sortedRanks[j])!
        total += len * mult
      }
      start = i
    }
  }
  return total
}

function countFlush(hand: Card[], cutCard: Card, isCrib: boolean): number {
  if (hand.length < 4) return 0
  const suit = hand[0].suit
  if (!hand.every(c => c.suit === suit)) return 0
  if (cutCard.suit === suit) return 5
  if (isCrib) return 0
  return 4
}

function countNobs(hand: Card[], cutCard: Card): number {
  return hand.some(c => c.rank === 11 && c.suit === cutCard.suit) ? 1 : 0
}

function scoreHand(hand: Card[], cutCard: Card, isCrib: boolean): { total: number; breakdown: string } {
  const all = [...hand, cutCard]
  const parts: string[] = []
  const fifteens = count15s(all)
  if (fifteens > 0) parts.push(`15s: ${fifteens}`)
  const pairs = countPairs(all)
  if (pairs > 0) parts.push(`Pairs: ${pairs}`)
  const runs = countRuns(all)
  if (runs > 0) parts.push(`Runs: ${runs}`)
  const flush = countFlush(hand, cutCard, isCrib)
  if (flush > 0) parts.push(`Flush: ${flush}`)
  const nobs = countNobs(hand, cutCard)
  if (nobs > 0) parts.push(`Nobs: ${nobs}`)
  const total = fifteens + pairs + runs + flush + nobs
  return { total, breakdown: parts.length > 0 ? parts.join(', ') : 'No points' }
}

// ── Pegging helpers ─────────────────────────────────────────────────

function canPegCard(card: Card, pegTotal: number): boolean {
  return pegTotal + pegValue(card) <= 31
}

function checkPegRun(pegCards: PegCard[]): number {
  if (pegCards.length < 3) return 0
  for (let len = pegCards.length; len >= 3; len--) {
    const lastN = pegCards.slice(-len).map(pc => pc.card.rank)
    const sorted = [...lastN].sort((a, b) => a - b)
    let isRun = true
    for (let i = 1; i < sorted.length; i++) {
      if (sorted[i] !== sorted[i - 1] + 1) { isRun = false; break }
    }
    if (isRun) return len
  }
  return 0
}

function checkPegPairs(pegCards: PegCard[]): number {
  if (pegCards.length < 2) return 0
  const lastRank = pegCards[pegCards.length - 1].card.rank
  let count = 0
  for (let i = pegCards.length - 1; i >= 0; i--) {
    if (pegCards[i].card.rank === lastRank) count++
    else break
  }
  if (count >= 4) return 12
  if (count >= 3) return 6
  if (count >= 2) return 2
  return 0
}

function calcPegPoints(pegCards: PegCard[], pegTotal: number): { points: number; details: string[] } {
  let points = 0
  const details: string[] = []
  if (pegTotal === 15) { points += 2; details.push('15 for 2') }
  if (pegTotal === 31) { points += 2; details.push('31 for 2') }
  const pairPts = checkPegPairs(pegCards)
  if (pairPts > 0) {
    points += pairPts
    if (pairPts === 12) details.push('Four of a kind for 12')
    else if (pairPts === 6) details.push('Three of a kind for 6')
    else details.push('Pair for 2')
  }
  if (pairPts === 0) {
    const runLen = checkPegRun(pegCards)
    if (runLen > 0) { points += runLen; details.push(`Run of ${runLen} for ${runLen}`) }
  }
  return { points, details }
}

// ── Engine functions ────────────────────────────────────────────────

function createVsCribbageGame(): VsCribbageState {
  const deck = shuffleDeck(createDeck()).map(c => ({ ...c, faceUp: true }))
  const dealer = Math.random() < 0.5 ? 0 : 1
  const hands: [Card[], Card[]] = [deck.slice(0, 6), deck.slice(6, 12)]
  return {
    hands: [hands[0].map(c => ({ ...c })), hands[1].map(c => ({ ...c }))],
    originalHands: [hands[0].map(c => ({ ...c })), hands[1].map(c => ({ ...c }))],
    crib: [],
    cutCard: null,
    pegCards: [],
    pegTotal: 0,
    currentPlayer: dealer === 0 ? 1 : 0,
    dealer,
    scores: [0, 0],
    phase: 'discard',
    message: 'Select 2 cards to send to the crib',
    selectedForCrib: [[], []],
    cribSubmitted: [false, false],
    pegHistory: [],
    canPlay: [true, true],
    scoringStep: 'nonDealer',
    lastScoreBreakdown: '',
    playedIndices: [new Set(), new Set()],
  }
}

function submitCribForPlayer(state: VsCribbageState, playerIdx: number, selectedIndices: number[]): VsCribbageState {
  if (state.phase !== 'discard') return state
  if (selectedIndices.length !== 2) return state
  if (state.cribSubmitted[playerIdx]) return state

  const newSelected: [number[], number[]] = [
    playerIdx === 0 ? selectedIndices : state.selectedForCrib[0],
    playerIdx === 1 ? selectedIndices : state.selectedForCrib[1],
  ]
  const newSubmitted: [boolean, boolean] = [
    playerIdx === 0 ? true : state.cribSubmitted[0],
    playerIdx === 1 ? true : state.cribSubmitted[1],
  ]

  let next: VsCribbageState = { ...state, selectedForCrib: newSelected, cribSubmitted: newSubmitted }

  // If both have submitted, proceed
  if (newSubmitted[0] && newSubmitted[1]) {
    const discards0 = newSelected[0].sort((a, b) => b - a).map(i => state.hands[0][i])
    const hand0 = state.hands[0].filter((_, i) => !newSelected[0].includes(i))
    const discards1 = newSelected[1].sort((a, b) => b - a).map(i => state.hands[1][i])
    const hand1 = state.hands[1].filter((_, i) => !newSelected[1].includes(i))

    const crib = [...discards0, ...discards1]

    // Cut card
    const usedCards = new Set([...state.hands[0], ...state.hands[1]].map(c => `${c.rank}-${c.suit}`))
    const deck = shuffleDeck(createDeck()).filter(c => !usedCards.has(`${c.rank}-${c.suit}`))
    const cutCard = { ...deck[0], faceUp: true }

    const scores: [number, number] = [...state.scores] as [number, number]
    let message = ''

    // His Heels
    if (cutCard.rank === 11) {
      scores[state.dealer] += 2
      message = 'His Heels! Jack cut — dealer gets 2 points. '
      if (scores[state.dealer] >= WIN_SCORE) {
        return {
          ...next,
          hands: [hand0, hand1],
          originalHands: [hand0, hand1],
          crib, cutCard, scores,
          phase: 'gameOver',
          message: `Player ${state.dealer + 1} wins with His Heels!`,
        }
      }
    }

    const nonDealer = state.dealer === 0 ? 1 : 0

    next = {
      ...next,
      hands: [hand0, hand1],
      originalHands: [hand0, hand1],
      crib, cutCard,
      pegCards: [],
      pegTotal: 0,
      currentPlayer: nonDealer,
      scores,
      phase: 'pegging',
      message: message + `Player ${nonDealer + 1}'s turn to play a card`,
      pegHistory: [],
      canPlay: [true, true],
      playedIndices: [new Set(), new Set()],
    }
  } else {
    next = { ...next, message: 'Waiting for opponent to discard...' }
  }

  return next
}

function getPlayableHandCards(state: VsCribbageState, player: number): Card[] {
  return state.hands[player].filter((_, i) => !state.playedIndices[player].has(i))
}

function vsPlayPegCard(state: VsCribbageState, player: number, cardIndex: number): VsCribbageState {
  if (state.phase !== 'pegging') return state
  if (state.currentPlayer !== player) return state
  if (state.playedIndices[player].has(cardIndex)) return state

  const card = state.hands[player][cardIndex]
  if (!card || !canPegCard(card, state.pegTotal)) return state

  const newTotal = state.pegTotal + pegValue(card)
  const pegEntry: PegCard = { card, player }
  const newPegCards = [...state.pegCards, pegEntry]
  const newPegHistory = [...state.pegHistory, pegEntry]

  const newPlayed: [Set<number>, Set<number>] = [new Set(state.playedIndices[0]), new Set(state.playedIndices[1])]
  newPlayed[player].add(cardIndex)

  const { points, details } = calcPegPoints(newPegCards, newTotal)
  const scores: [number, number] = [...state.scores] as [number, number]
  scores[player] += points

  if (scores[player] >= WIN_SCORE) {
    return {
      ...state, scores,
      pegCards: newPegCards, pegTotal: newTotal, pegHistory: newPegHistory,
      playedIndices: newPlayed,
      phase: 'gameOver', message: `Player ${player + 1} wins!`,
    }
  }

  let message = `Player ${player + 1} plays ${rankName(card.rank)}${suitSymbol(card.suit)}`
  if (details.length > 0) message += ` — ${details.join(', ')}`

  let nextPegCards = newPegCards
  let nextPegTotal = newTotal
  let nextCanPlay: [boolean, boolean] = [...state.canPlay] as [boolean, boolean]

  if (newTotal === 31) {
    nextPegCards = []
    nextPegTotal = 0
    nextCanPlay = [true, true]
  }

  // Find next player
  const opponent = player === 0 ? 1 : 0
  const oppRemaining = state.hands[opponent].filter((_, i) => !newPlayed[opponent].has(i))
  const oppPlayable = oppRemaining.filter(c => canPegCard(c, nextPegTotal))
  const myRemaining = state.hands[player].filter((_, i) => !newPlayed[player].has(i))
  const myPlayable = myRemaining.filter(c => canPegCard(c, nextPegTotal))

  let nextPlayer = opponent
  if (oppPlayable.length === 0 && myPlayable.length === 0) {
    // Both stuck — check if all cards played
    if (oppRemaining.length === 0 && myRemaining.length === 0) {
      // Award last card if not 31
      if (nextPegTotal > 0 && nextPegTotal < 31) {
        scores[player] += 1
        message += ' — Last card: +1'
        if (scores[player] >= WIN_SCORE) {
          return {
            ...state, scores,
            pegCards: nextPegCards, pegTotal: nextPegTotal, pegHistory: newPegHistory,
            playedIndices: newPlayed,
            phase: 'gameOver', message: `Player ${player + 1} wins!`,
          }
        }
      }
      return {
        ...state, scores,
        pegCards: [], pegTotal: 0, pegHistory: newPegHistory,
        playedIndices: newPlayed,
        phase: 'scoring', scoringStep: 'nonDealer',
        message: message + ' — Scoring phase',
        canPlay: [true, true],
      }
    }
    // Reset count — Go point
    if (nextPegTotal > 0 && nextPegTotal < 31 && nextPegCards.length > 0) {
      const lastPlayer = nextPegCards[nextPegCards.length - 1].player
      scores[lastPlayer] += 1
      message += ` — Go! +1 for Player ${lastPlayer + 1}`
      if (scores[lastPlayer] >= WIN_SCORE) {
        return {
          ...state, scores,
          pegCards: nextPegCards, pegTotal: nextPegTotal, pegHistory: newPegHistory,
          playedIndices: newPlayed,
          phase: 'gameOver', message: `Player ${lastPlayer + 1} wins!`,
        }
      }
    }
    nextPegCards = []
    nextPegTotal = 0
    nextCanPlay = [true, true]
    // Next player is non-dealer or whoever has cards
    const nonDealer = state.dealer === 0 ? 1 : 0
    if (getPlayableHandCards({ ...state, playedIndices: newPlayed } as VsCribbageState, nonDealer).length > 0) {
      nextPlayer = nonDealer
    } else {
      nextPlayer = state.dealer
    }
  } else if (oppPlayable.length === 0) {
    nextPlayer = player  // Opponent can't play, continue
    nextCanPlay[opponent] = false
  }

  return {
    ...state,
    pegCards: nextPegCards, pegTotal: nextPegTotal, pegHistory: newPegHistory,
    playedIndices: newPlayed, scores, message,
    currentPlayer: nextPlayer, canPlay: nextCanPlay,
  }
}

function vsSayGo(state: VsCribbageState, player: number): VsCribbageState {
  if (state.phase !== 'pegging') return state
  if (state.currentPlayer !== player) return state

  const newCanPlay: [boolean, boolean] = [...state.canPlay] as [boolean, boolean]
  newCanPlay[player] = false
  const opponent = player === 0 ? 1 : 0

  const oppRemaining = getPlayableHandCards(state, opponent)
  const oppPlayable = oppRemaining.filter(c => canPegCard(c, state.pegTotal))

  if (oppPlayable.length > 0) {
    return { ...state, canPlay: newCanPlay, currentPlayer: opponent, message: `Player ${player + 1} says Go` }
  }

  // Neither can play — handle reset
  const scores: [number, number] = [...state.scores] as [number, number]
  let message = ''

  if (state.pegTotal > 0 && state.pegTotal < 31 && state.pegCards.length > 0) {
    const lastPlayer = state.pegCards[state.pegCards.length - 1].player
    scores[lastPlayer] += 1
    message = `Go! +1 for Player ${lastPlayer + 1}. `
    if (scores[lastPlayer] >= WIN_SCORE) {
      return { ...state, scores, phase: 'gameOver', message: `Player ${lastPlayer + 1} wins!` }
    }
  }

  const p0Left = getPlayableHandCards(state, 0)
  const p1Left = getPlayableHandCards(state, 1)

  if (p0Left.length === 0 && p1Left.length === 0) {
    return {
      ...state, scores, phase: 'scoring', scoringStep: 'nonDealer',
      pegTotal: 0, pegCards: [],
      message: message + 'Scoring phase — click Continue',
    }
  }

  const nonDealer = state.dealer === 0 ? 1 : 0
  let nextPlayer: number
  if (p0Left.length > 0 && p1Left.length > 0) nextPlayer = nonDealer
  else if (p0Left.length > 0) nextPlayer = 0
  else nextPlayer = 1

  return {
    ...state, scores,
    pegCards: [], pegTotal: 0,
    canPlay: [true, true], currentPlayer: nextPlayer,
    message: message + 'Count resets to 0.',
  }
}

function vsContinueScoring(state: VsCribbageState): VsCribbageState {
  if (state.phase !== 'scoring') return state
  const nonDealer = state.dealer === 0 ? 1 : 0
  const scores: [number, number] = [...state.scores] as [number, number]

  switch (state.scoringStep) {
    case 'nonDealer': {
      const hand = state.originalHands[nonDealer]
      const result = scoreHand(hand, state.cutCard!, false)
      scores[nonDealer] += result.total
      const who = `Player ${nonDealer + 1}`
      if (scores[nonDealer] >= WIN_SCORE) {
        return { ...state, scores, phase: 'gameOver', message: `${who} wins! Hand: ${result.total} (${result.breakdown})`, lastScoreBreakdown: result.breakdown }
      }
      return { ...state, scores, scoringStep: 'dealer', message: `${who}'s hand: ${result.total} (${result.breakdown})`, lastScoreBreakdown: result.breakdown }
    }
    case 'dealer': {
      const hand = state.originalHands[state.dealer]
      const result = scoreHand(hand, state.cutCard!, false)
      scores[state.dealer] += result.total
      const who = `Player ${state.dealer + 1}`
      if (scores[state.dealer] >= WIN_SCORE) {
        return { ...state, scores, phase: 'gameOver', message: `${who} wins! Hand: ${result.total} (${result.breakdown})`, lastScoreBreakdown: result.breakdown }
      }
      return { ...state, scores, scoringStep: 'crib', message: `${who}'s hand: ${result.total} (${result.breakdown})`, lastScoreBreakdown: result.breakdown }
    }
    case 'crib': {
      const result = scoreHand(state.crib, state.cutCard!, true)
      scores[state.dealer] += result.total
      const who = `Player ${state.dealer + 1}`
      if (scores[state.dealer] >= WIN_SCORE) {
        return { ...state, scores, phase: 'gameOver', message: `${who} wins! Crib: ${result.total} (${result.breakdown})`, lastScoreBreakdown: result.breakdown }
      }
      return { ...state, scores, scoringStep: 'done', message: `${who}'s crib: ${result.total} (${result.breakdown})`, lastScoreBreakdown: result.breakdown }
    }
    case 'done':
      return state
  }
}

function vsNewRound(state: VsCribbageState): VsCribbageState {
  const newDealer = state.dealer === 0 ? 1 : 0
  const deck = shuffleDeck(createDeck()).map(c => ({ ...c, faceUp: true }))
  const hands: [Card[], Card[]] = [deck.slice(0, 6), deck.slice(6, 12)]
  return {
    hands: [hands[0].map(c => ({ ...c })), hands[1].map(c => ({ ...c }))],
    originalHands: [hands[0].map(c => ({ ...c })), hands[1].map(c => ({ ...c }))],
    crib: [],
    cutCard: null,
    pegCards: [],
    pegTotal: 0,
    currentPlayer: newDealer === 0 ? 1 : 0,
    dealer: newDealer,
    scores: [...state.scores] as [number, number],
    phase: 'discard',
    message: 'Select 2 cards to send to the crib',
    selectedForCrib: [[], []],
    cribSubmitted: [false, false],
    pegHistory: [],
    canPlay: [true, true],
    scoringStep: 'nonDealer',
    lastScoreBreakdown: '',
    playedIndices: [new Set(), new Set()],
  }
}

// ── Guest view builder ──────────────────────────────────────────────

function toGuestView(state: VsCribbageState, guestIdx: number): GuestViewState {
  const oppIdx = guestIdx === 0 ? 1 : 0
  const showOppCards = state.phase === 'scoring' || state.phase === 'gameOver'
  return {
    myHand: state.hands[guestIdx],
    oppHandCount: state.hands[oppIdx].length,
    oppHand: showOppCards ? state.hands[oppIdx] : [],
    crib: state.crib,
    cutCard: state.cutCard,
    pegCards: state.pegCards,
    pegTotal: state.pegTotal,
    currentPlayer: state.currentPlayer,
    dealer: state.dealer,
    scores: state.scores,
    phase: state.phase,
    message: state.message,
    mySelectedForCrib: state.selectedForCrib[guestIdx],
    myCribSubmitted: state.cribSubmitted[guestIdx],
    oppCribSubmitted: state.cribSubmitted[oppIdx],
    pegHistory: state.pegHistory,
    canPlay: state.canPlay,
    scoringStep: state.scoringStep,
    lastScoreBreakdown: state.lastScoreBreakdown,
    myPlayedIndices: [...state.playedIndices[guestIdx]],
    oppPlayedCount: state.playedIndices[oppIdx].size,
  }
}

// ── Component ────────────────────────────────────────────────────────

interface Props {
  roomId: string
  players: number[]
  playerNames: Record<number, string>
  onLeave?: () => void
}

export function CribbageMultiplayer({ roomId, players, playerNames, onLeave }: Props) {
  const { user } = useAuth()
  const isHost = players[0] === user?.id
  const myIdx = isHost ? 0 : 1
  const oppIdx = myIdx === 0 ? 1 : 0

  const myName = playerNames[players[myIdx]] ?? `Player ${myIdx + 1}`
  const oppName = playerNames[players[oppIdx]] ?? `Player ${oppIdx + 1}`

  const [gameState, setGameState] = useState<VsCribbageState>(() => createVsCribbageGame())
  const stateRef = useRef(gameState)
  stateRef.current = gameState

  const [guestView, setGuestView] = useState<GuestViewState | null>(null)
  const [selectedForCrib, setSelectedForCrib] = useState<number[]>([])
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')

  const song = useMemo(() => getSongForGame('cribbage'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('cribbage')

  // ── Host: broadcast state ─────────────────────────────────────────

  const broadcastState = useCallback((state: VsCribbageState) => {
    if (!isHost) return
    // Send guest-specific view (player index 1)
    gameSocket.sendAction(roomId, {
      type: 'state_sync',
      state: toGuestView(state, 1),
    })
  }, [isHost, roomId])

  // ── Helper: host applies and broadcasts ───────────────────────────

  const hostApply = useCallback((fn: (s: VsCribbageState) => VsCribbageState) => {
    setGameState(prev => {
      const next = fn(prev)
      broadcastState(next)
      return next
    })
  }, [broadcastState])

  // ── Discard handlers ──────────────────────────────────────────────

  const handleToggleSelect = useCallback((idx: number) => {
    music.init()
    sfx.init()
    music.start()
    setSelectedForCrib(prev => {
      if (prev.includes(idx)) return prev.filter(i => i !== idx)
      if (prev.length < 2) return [...prev, idx]
      return prev
    })
  }, [music, sfx])

  const handleSubmitCrib = useCallback(() => {
    if (selectedForCrib.length !== 2) return
    sfx.play('place')

    if (isHost) {
      hostApply(s => submitCribForPlayer(s, 0, selectedForCrib))
    } else {
      gameSocket.sendAction(roomId, { type: 'submit_crib', indices: selectedForCrib })
    }
    setSelectedForCrib([])
  }, [isHost, selectedForCrib, roomId, hostApply, sfx])

  // ── Pegging handlers ──────────────────────────────────────────────

  const handlePlayCard = useCallback((cardIndex: number) => {
    sfx.play('place')
    if (isHost) {
      hostApply(s => vsPlayPegCard(s, 0, cardIndex))
    } else {
      gameSocket.sendAction(roomId, { type: 'peg_card', cardIndex })
    }
  }, [isHost, roomId, hostApply, sfx])

  const handleSayGo = useCallback(() => {
    sfx.play('deal')
    if (isHost) {
      hostApply(s => vsSayGo(s, 0))
    } else {
      gameSocket.sendAction(roomId, { type: 'go' })
    }
  }, [isHost, roomId, hostApply, sfx])

  // ── Scoring handlers ──────────────────────────────────────────────

  const handleContinueScoring = useCallback(() => {
    sfx.play('deal')
    if (isHost) {
      hostApply(vsContinueScoring)
    } else {
      gameSocket.sendAction(roomId, { type: 'continue_scoring' })
    }
  }, [isHost, roomId, hostApply, sfx])

  const handleNewRound = useCallback(() => {
    if (isHost) {
      hostApply(vsNewRound)
      setSelectedForCrib([])
    } else {
      gameSocket.sendAction(roomId, { type: 'new_round' })
      setSelectedForCrib([])
    }
  }, [isHost, roomId, hostApply])

  // ── WebSocket listener ────────────────────────────────────────────

  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg: { playerId?: number; action?: Record<string, unknown> }) => {
      if (msg.playerId === user?.id) return
      const action = msg.action
      if (!action) return

      if (action.type === 'state_sync') {
        if (!isHost) {
          setGuestView(action.state as GuestViewState)
        }
        return
      }

      if (isHost) {
        if (action.type === 'submit_crib') {
          const indices = action.indices as number[]
          sfx.play('place')
          hostApply(s => submitCribForPlayer(s, 1, indices))
        } else if (action.type === 'peg_card') {
          sfx.play('place')
          hostApply(s => vsPlayPegCard(s, 1, action.cardIndex as number))
        } else if (action.type === 'go') {
          sfx.play('deal')
          hostApply(s => vsSayGo(s, 1))
        } else if (action.type === 'continue_scoring') {
          sfx.play('deal')
          hostApply(vsContinueScoring)
        } else if (action.type === 'new_round') {
          hostApply(vsNewRound)
          setSelectedForCrib([])
        }
      }
    })
    return unsub
  }, [roomId, isHost, user?.id, hostApply, sfx])

  // ── Game over detection ───────────────────────────────────────────

  const currentPhase = isHost ? gameState.phase : (guestView?.phase ?? 'discard')

  useEffect(() => {
    if (currentPhase !== 'gameOver') return
    const scores = isHost ? gameState.scores : (guestView?.scores ?? [0, 0])
    if (scores[myIdx] >= WIN_SCORE) setGameStatus('won')
    else setGameStatus('lost')
  }, [currentPhase, isHost, gameState.scores, guestView?.scores, myIdx])

  // ── Derived state ─────────────────────────────────────────────────

  const phase = isHost ? gameState.phase : (guestView?.phase ?? 'discard')
  const message = isHost ? gameState.message : (guestView?.message ?? 'Waiting for host...')
  const scores = isHost ? gameState.scores : (guestView?.scores ?? [0, 0] as [number, number])
  const dealer = isHost ? gameState.dealer : (guestView?.dealer ?? 0)
  const currentPlayer = isHost ? gameState.currentPlayer : (guestView?.currentPlayer ?? 0)
  const pegTotal = isHost ? gameState.pegTotal : (guestView?.pegTotal ?? 0)
  const pegCards = isHost ? gameState.pegCards : (guestView?.pegCards ?? [])
  const pegHistory = isHost ? gameState.pegHistory : (guestView?.pegHistory ?? [])
  const cutCard = isHost ? gameState.cutCard : (guestView?.cutCard ?? null)
  const crib = isHost ? gameState.crib : (guestView?.crib ?? [])
  const scoringStep = isHost ? gameState.scoringStep : (guestView?.scoringStep ?? 'nonDealer')
  const lastScoreBreakdown = isHost ? gameState.lastScoreBreakdown : (guestView?.lastScoreBreakdown ?? '')

  const myHand = isHost ? gameState.hands[0] : (guestView?.myHand ?? [])
  const oppHandCount = isHost ? gameState.hands[1].length : (guestView?.oppHandCount ?? 0)
  const oppHand = isHost ? gameState.hands[1] : (guestView?.oppHand ?? [])
  const showOppCards = phase === 'scoring' || phase === 'gameOver'

  const myCribSubmitted = isHost ? gameState.cribSubmitted[0] : (guestView?.myCribSubmitted ?? false)
  const oppCribSubmitted = isHost ? gameState.cribSubmitted[1] : (guestView?.oppCribSubmitted ?? false)

  const myPlayedIndices = isHost
    ? new Set(gameState.playedIndices[0])
    : new Set(guestView?.myPlayedIndices ?? [])

  const isMyTurn = currentPlayer === myIdx
  const isScoring = phase === 'scoring'

  // Get playable card indices for pegging
  const myPeggableIndices: number[] = useMemo(() => {
    if (phase !== 'pegging' || !isMyTurn) return []
    const indices: number[] = []
    for (let i = 0; i < myHand.length; i++) {
      if (!myPlayedIndices.has(i) && canPegCard(myHand[i], pegTotal)) {
        indices.push(i)
      }
    }
    return indices
  }, [phase, isMyTurn, myHand, myPlayedIndices, pegTotal])

  const mustGo = useMemo(() => {
    if (phase !== 'pegging' || !isMyTurn) return false
    const remaining = myHand.filter((_, i) => !myPlayedIndices.has(i))
    if (remaining.length === 0) return false
    return remaining.every(c => !canPegCard(c, pegTotal))
  }, [phase, isMyTurn, myHand, myPlayedIndices, pegTotal])

  // ── Render ────────────────────────────────────────────────────────

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <Wifi className="w-3.5 h-3.5 text-green-400" />
        <span className="text-xs text-slate-400">VS Mode</span>
      </div>
      <div className="flex items-center gap-4 text-xs">
        <span className="text-white font-medium">
          {myName}: <span className="text-blue-400">{scores[myIdx]}</span>/121
        </span>
        <span className="text-slate-400">
          {oppName}: <span className="text-red-400">{scores[oppIdx]}</span>/121
        </span>
      </div>
      <span className="text-xs text-slate-400">
        Dealer: {dealer === myIdx ? myName : oppName}
      </span>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Cribbage — VS" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-3">

        {/* Score bars */}
        <div className="w-full flex gap-2 items-center">
          <div className="flex-1">
            <div className="text-[0.6rem] text-blue-400 mb-0.5">{myName}</div>
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div className="h-full bg-blue-500 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, (scores[myIdx] / 121) * 100)}%` }} />
            </div>
          </div>
          <div className="flex-1">
            <div className="text-[0.6rem] text-red-400 mb-0.5">{oppName}</div>
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div className="h-full bg-red-500 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, (scores[oppIdx] / 121) * 100)}%` }} />
            </div>
          </div>
        </div>

        {/* Opponent hand */}
        <div className="text-center">
          <span className="text-xs text-slate-400">{oppName}&apos;s Hand</span>
          <div className="flex gap-1 justify-center mt-1">
            {showOppCards ? (
              oppHand.map((card, i) => (
                <div key={i} className={CARD_SIZE}>
                  <CardFace card={card} />
                </div>
              ))
            ) : (
              Array.from({ length: oppHandCount }).map((_, i) => (
                <div key={i} className={CARD_SIZE}>
                  <CardBack />
                </div>
              ))
            )}
          </div>
        </div>

        {/* Cut card + pegging area */}
        <div className="flex gap-4 items-start justify-center">
          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500">Cut</span>
            <div className={CARD_SIZE}>
              {cutCard ? (
                <CardFace card={cutCard} />
              ) : (
                <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">--</div>
              )}
            </div>
          </div>

          {phase === 'pegging' && (
            <div className="text-center">
              <span className="text-[0.6rem] text-slate-500">
                Count: <span className="text-white font-bold">{pegTotal}</span>/31
              </span>
              <div className="flex gap-0.5 mt-1 flex-wrap justify-center max-w-[12rem]">
                {pegCards.map((pc, i) => (
                  <div key={i}
                    className={`${CARD_SIZE_XS} ${
                      pc.player === myIdx ? 'ring-1 ring-blue-500/50' : 'ring-1 ring-red-500/50'
                    } rounded`}>
                    <CardFace card={pc.card} />
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500">
              Crib ({dealer === myIdx ? 'Yours' : `${oppName}'s`})
            </span>
            <div className={CARD_SIZE}>
              {crib.length > 0 ? (
                (scoringStep === 'crib' || scoringStep === 'done' || phase === 'gameOver') ? (
                  <div className="flex -space-x-8">
                    {crib.slice(0, 2).map((c, i) => (
                      <div key={i} className={CARD_SIZE}><CardFace card={c} /></div>
                    ))}
                  </div>
                ) : <CardBack />
              ) : (
                <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">--</div>
              )}
            </div>
          </div>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center min-h-[2.5rem]">{message}</p>

        {/* Scoring breakdown */}
        {isScoring && lastScoreBreakdown && (
          <p className="text-xs text-slate-400 text-center">{lastScoreBreakdown}</p>
        )}

        {/* Action buttons */}
        <div className="flex gap-2 justify-center">
          {phase === 'discard' && !myCribSubmitted && selectedForCrib.length === 2 && (
            <button onClick={handleSubmitCrib}
              className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors">
              Send to Crib
            </button>
          )}

          {phase === 'discard' && myCribSubmitted && !oppCribSubmitted && (
            <p className="text-xs text-slate-400">Waiting for {oppName} to discard...</p>
          )}

          {phase === 'pegging' && isMyTurn && mustGo && (
            <button onClick={handleSayGo}
              className="px-5 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-sm font-medium transition-colors">
              Go
            </button>
          )}

          {phase === 'pegging' && !isMyTurn && (
            <p className="text-xs text-slate-400">{oppName}&apos;s turn...</p>
          )}

          {isScoring && scoringStep !== 'done' && (
            <button onClick={handleContinueScoring}
              className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors">
              Continue
            </button>
          )}

          {isScoring && scoringStep === 'done' && (
            <button onClick={handleNewRound}
              className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors">
              Next Round
            </button>
          )}
        </div>

        {/* Peg history */}
        {phase === 'pegging' && pegHistory.length > 0 && (
          <div className="w-full">
            <span className="text-[0.6rem] text-slate-500">Pegging History</span>
            <div className="flex gap-0.5 overflow-x-auto py-1">
              {pegHistory.map((pc, i) => (
                <div key={i} className="flex-shrink-0 text-center">
                  <div className={`text-[0.5rem] ${pc.player === myIdx ? 'text-blue-400' : 'text-red-400'}`}>
                    {pc.player === myIdx ? 'You' : oppName}
                  </div>
                  <div className="text-[0.6rem] text-white">
                    {rankName(pc.card.rank)}{suitSymbol(pc.card.suit)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* My hand */}
        <div className="text-center">
          <span className="text-xs text-blue-400">Your Hand</span>
          <div className="flex flex-wrap gap-1.5 justify-center mt-1 max-w-md">
            {myHand.map((card, i) => {
              const isSelected = selectedForCrib.includes(i)
              const isPlayable = myPeggableIndices.includes(i)
              const played = myPlayedIndices.has(i)

              const clickable = phase === 'discard' && !myCribSubmitted
                ? true
                : phase === 'pegging' && isPlayable

              return (
                <div key={i}
                  className={`${CARD_SIZE} transition-all duration-150 ${
                    played ? 'opacity-30 pointer-events-none' : ''
                  } ${clickable && !played ? 'cursor-pointer hover:-translate-y-1' : ''
                  } ${!clickable && !played && phase === 'pegging' ? 'opacity-50' : ''
                  } ${isSelected ? '-translate-y-2' : ''}`}
                  onClick={() => {
                    if (played) return
                    if (phase === 'discard' && !myCribSubmitted) handleToggleSelect(i)
                    else if (phase === 'pegging' && isPlayable) handlePlayCard(i)
                  }}>
                  <CardFace card={card} selected={isSelected} />
                </div>
              )
            })}
          </div>
        </div>

        {/* Hints */}
        {phase === 'discard' && !myCribSubmitted && (
          <p className="text-xs text-slate-500 text-center">
            Select 2 cards to discard to the {dealer === myIdx ? 'your' : `${oppName}'s`} crib
          </p>
        )}

        {phase === 'pegging' && isMyTurn && !mustGo && (
          <p className="text-xs text-slate-500 text-center">
            Click a card to play it. Need {31 - pegTotal} or less.
          </p>
        )}

        {/* Game over modal */}
        {(gameStatus === 'won' || gameStatus === 'lost') && (
          <GameOverModal
            status={gameStatus}
            score={scores[myIdx]}
            message={
              gameStatus === 'won'
                ? `You win! ${scores[myIdx]} to ${scores[oppIdx]}.`
                : `${oppName} wins! ${scores[oppIdx]} to ${scores[myIdx]}.`
            }
            onPlayAgain={onLeave || (() => {})}
            playAgainText={onLeave ? 'Back to Lobby' : undefined}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
