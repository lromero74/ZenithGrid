/**
 * Canasta VS Multiplayer — 2 humans + 2 AI in a 4-player partnership game.
 *
 * Host-authoritative: host runs the engine, broadcasts state.
 * Player 0 (host) = South, Player 1 (guest) = North.
 * Teams: Host(0) + Guest(1) vs AI-East(2) + AI-West(3).
 * Double deck with jokers. Melds of same rank, canastas of 7+.
 * First team to 5,000 wins.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { Wifi, ArrowLeft } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE_COMPACT, CARD_SLOT_V, CARD_SLOT_H } from '../../PlayingCard'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'
import type { GameStatus } from '../../../types'
import { getRankDisplay, getSuitSymbol, getCardColor } from '../../../utils/cardUtils'
import type { Card } from '../../../utils/cardUtils'
import {
  isWild,
  WINNING_SCORE,
} from './CanastaEngine'

// ── Types ────────────────────────────────────────────────────────────

/** VS state wraps the engine state with multiplayer player mapping.
 *  Engine players: 0=host, 1=guest, 2=AI-East, 3=AI-West.
 *  Engine teams: 0 (players 0,2) vs 1 (players 1,3) — but in VS mode
 *  we want humans on the same team, so we remap:
 *    Host(0) + Guest(1) = Team 0 (humans)
 *    AI-East(2) + AI-West(3) = Team 1 (AI)
 *
 *  However the engine uses teamOf(player) = player % 2, meaning
 *  0+2 = team 0 and 1+3 = team 1. To put both humans on the same team,
 *  we embed the engine logic directly with a modified team mapping.
 */

type Phase = 'draw' | 'meld' | 'discard' | 'roundOver' | 'gameOver'

interface CanastaVsMeld {
  cards: Card[]
  rank: number
  team: number
  isCanasta: boolean
  isNatural: boolean
}

interface CanastaVsState {
  hands: Card[][]
  teamMelds: CanastaVsMeld[]
  stock: Card[]
  discardPile: Card[]
  currentPlayer: number
  phase: Phase
  teamScores: number[]
  redThrees: Card[][]
  message: string
  hasDrawn: boolean
  selectedCards: number[][]  // per-player selected cards (for humans)
  teamHasInitialMeld: boolean[]
  pileFrozen: boolean
  roundNumber: number
}

// ── Constants ────────────────────────────────────────────────────────

const AI_DELAY = 800
const SEAT_NAMES = ['South', 'North', 'East', 'West']
const VS_TEAM_NAMES = ['Humans', 'AI Team']

function vsTeamOf(player: number): number {
  // 0,1 = team 0 (humans); 2,3 = team 1 (AI)
  return player < 2 ? 0 : 1
}

function nextPlayer(current: number): number {
  return (current + 1) % 4
}

// ── JokerCard ────────────────────────────────────────────────────────

function JokerCard() {
  return (
    <div className="w-full h-full rounded-md bg-slate-50 border border-slate-300 shadow-md flex flex-col items-center justify-center select-none">
      <span className="text-purple-600 font-bold text-xs">JKR</span>
      <span className="text-2xl">{'\uD83C\uDCCF'}</span>
    </div>
  )
}

// ── GameCard ─────────────────────────────────────────────────────────

function GameCard({ card, selected, onClick, disabled }: {
  card: Card
  selected?: boolean
  onClick?: () => void
  disabled?: boolean
}) {
  return (
    <div
      className={`${CARD_SIZE_COMPACT} transition-transform ${
        !disabled ? 'cursor-pointer hover:-translate-y-1' : 'opacity-40'
      } ${selected ? '-translate-y-2' : ''}`}
      onClick={disabled ? undefined : onClick}
    >
      {card.rank === 0 ? <JokerCard /> : (
        <CardFace card={card} selected={selected} />
      )}
    </div>
  )
}

// ── MeldDisplay ─────────────────────────────────────────────────────

function MeldDisplay({ meld }: { meld: CanastaVsMeld }) {
  const borderClass = meld.isCanasta
    ? meld.isNatural
      ? 'border-yellow-400 bg-yellow-400/10'
      : 'border-slate-400 bg-slate-400/10'
    : 'border-slate-600 bg-slate-800/50'

  return (
    <div className={`inline-flex items-center gap-0.5 p-1 rounded border ${borderClass}`}>
      {meld.cards.slice(0, 4).map((card, i) => (
        <div key={i} className="w-6 h-9 flex-shrink-0">
          {card.rank === 0 ? (
            <div className="w-full h-full rounded-sm bg-slate-50 border border-slate-300 flex items-center justify-center">
              <span className="text-[0.4rem] text-purple-600 font-bold">JKR</span>
            </div>
          ) : (
            <div className={`w-full h-full rounded-sm bg-slate-50 border border-slate-300 flex items-center justify-center text-[0.5rem] font-bold ${
              getCardColor(card) === 'red' ? 'text-red-500' : 'text-slate-900'
            }`}>
              {getRankDisplay(card.rank)}{getSuitSymbol(card.suit)}
            </div>
          )}
        </div>
      ))}
      {meld.cards.length > 4 && (
        <span className="text-[0.5rem] text-slate-400 px-0.5">+{meld.cards.length - 4}</span>
      )}
      {meld.isCanasta && (
        <span className={`text-[0.5rem] font-bold px-0.5 ${
          meld.isNatural ? 'text-yellow-400' : 'text-slate-300'
        }`}>
          {meld.isNatural ? 'NAT' : 'MIX'}
        </span>
      )}
    </div>
  )
}

// ── Engine helpers (adapted for VS team mapping) ─────────────────────

/**
 * We re-use the CanastaEngine functions but post-process the state
 * to use our VS team mapping. The engine internally uses player%2 teams,
 * but we want 0+1 vs 2+3. So we use the engine as-is for the core game
 * mechanics (draw, meld, discard, etc.) but override team assignments.
 *
 * Actually, since the engine's teamOf() is baked into meldCards/pickupDiscardPile/etc,
 * we need to inline the logic with our own team mapping. Let's use the engine
 * functions but remap state before/after calls.
 *
 * Simpler approach: Use the engine directly. The engine has player%2 teams.
 * In the engine, host(0) is team 0 with player 2, and guest(1) is team 1 with player 3.
 * For VS mode we want host+guest together. Since modifying the engine would break
 * single player, we embed the game logic here with vsTeamOf().
 */

import {
  isRed3,
  isBlack3,
  cardPoints,
  getInitialMeldReq,
  isValidNewMeld,
  GOING_OUT_BONUS,
  NATURAL_CANASTA_BONUS,
  MIXED_CANASTA_BONUS,
  RED_3_BONUS,
  ALL_RED_3S_BONUS,
} from './CanastaEngine'

import { createDoubleDeck, shuffleDeck } from '../../../utils/cardUtils'

function sortHand(hand: Card[]): Card[] {
  return [...hand].sort((a, b) => {
    if (a.rank !== b.rank) return a.rank - b.rank
    if (a.suit < b.suit) return -1
    if (a.suit > b.suit) return 1
    return 0
  })
}

function naturalRank(cards: Card[]): number {
  for (const card of cards) {
    if (!isWild(card)) return card.rank
  }
  return -1
}

function countWilds(cards: Card[]): number {
  return cards.filter(isWild).length
}

function countNaturals(cards: Card[]): number {
  return cards.filter(c => !isWild(c)).length
}

function totalPoints(cards: Card[]): number {
  return cards.reduce((sum, c) => sum + cardPoints(c), 0)
}

function updateMeldStatus(meld: CanastaVsMeld): CanastaVsMeld {
  const isCan = meld.cards.length >= 7
  const isNat = isCan && countWilds(meld.cards) === 0
  return { ...meld, isCanasta: isCan, isNatural: isNat }
}

function isValidMeldAddition(meld: CanastaVsMeld, newCards: Card[]): boolean {
  const allCards = [...meld.cards, ...newCards]
  const wilds = countWilds(allCards)
  const naturals = countNaturals(allCards)
  if (naturals <= wilds) return false
  if (wilds > 3) return false
  for (const card of newCards) {
    if (!isWild(card) && card.rank !== meld.rank) return false
  }
  return true
}

// ── VS Game creation ────────────────────────────────────────────────

function createVsCanastaGame(prevScores?: number[]): CanastaVsState {
  const deck = shuffleDeck(createDoubleDeck())
  const hands: Card[][] = [[], [], [], []]
  let idx = 0

  for (let i = 0; i < 44; i++) {
    hands[i % 4].push({ ...deck[idx++], faceUp: true })
  }

  const stock = deck.slice(idx + 1).map(c => ({ ...c, faceUp: true }))
  const discardPile = [{ ...deck[idx], faceUp: true }]

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

  const topCard = discardPile[0]
  const pileFrozen = isWild(topCard) || isRed3(topCard)

  return {
    hands,
    teamMelds: [],
    stock,
    discardPile,
    currentPlayer: 0,
    phase: 'draw',
    teamScores: prevScores ? [...prevScores] : [0, 0],
    redThrees,
    message: `${SEAT_NAMES[0]}'s turn — draw or pick up pile`,
    hasDrawn: false,
    selectedCards: [[], [], [], []],
    teamHasInitialMeld: [false, false],
    pileFrozen,
    roundNumber: 0,
  }
}

// ── Drawing ─────────────────────────────────────────────────────────

function vsDrawFromStock(state: CanastaVsState): CanastaVsState {
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
      // Keep drawing — red 3s don't count toward the 2 draws
    } else {
      newHands[player].push(card)
      cardsDrawn++
    }
  }

  newHands[player] = sortHand(newHands[player])
  const roundOver = newStock.length === 0
  const nextPhase: Phase = roundOver && newHands[player].length === 0 ? 'roundOver' : 'meld'

  return {
    ...state,
    hands: newHands,
    stock: newStock,
    redThrees: newRedThrees,
    phase: nextPhase,
    hasDrawn: true,
    message: `${SEAT_NAMES[player]} drew 2 cards`,
  }
}

// ── Picking up discard pile ─────────────────────────────────────────

function vsPickupDiscardPile(state: CanastaVsState, player: number, meldCardIndices: number[]): CanastaVsState {
  if (state.phase !== 'draw' || state.hasDrawn) return state
  if (state.currentPlayer !== player) return state
  if (state.discardPile.length === 0) return state

  const topCard = state.discardPile[state.discardPile.length - 1]
  if (isBlack3(topCard)) return state

  const team = vsTeamOf(player)
  const hand = state.hands[player]
  const meldCards2 = meldCardIndices.map(i => hand[i]).filter(Boolean)

  const needNaturalPair = state.pileFrozen || !state.teamHasInitialMeld[team]
  if (needNaturalPair) {
    const naturalMatches = meldCards2.filter(c => !isWild(c) && c.rank === topCard.rank)
    if (naturalMatches.length < 2) return state
  } else {
    const combined = [...meldCards2, topCard]
    if (combined.length < 3) return state
    if (!isValidNewMeld(combined)) return state
  }

  if (!state.teamHasInitialMeld[team]) {
    const combined = [...meldCards2, topCard]
    const meldPts = totalPoints(combined)
    const req = getInitialMeldReq(state.teamScores[team])
    if (meldPts < req) return state
  }

  const newHands = state.hands.map(h => [...h])
  const indicesToRemove = new Set(meldCardIndices)
  newHands[player] = newHands[player].filter((_, i) => !indicesToRemove.has(i))
  const restOfPile = state.discardPile.slice(0, -1)
  newHands[player].push(...restOfPile)
  newHands[player] = sortHand(newHands[player])

  const newMeldCards = [...meldCards2, topCard]
  const rank = naturalRank(newMeldCards)
  const newMeld = updateMeldStatus({
    cards: newMeldCards,
    rank,
    team,
    isCanasta: false,
    isNatural: false,
  })

  const existingIdx = state.teamMelds.findIndex(m => m.team === team && m.rank === rank)
  let newTeamMelds: CanastaVsMeld[]
  if (existingIdx >= 0) {
    newTeamMelds = state.teamMelds.map((m, i) => {
      if (i !== existingIdx) return m
      return updateMeldStatus({ ...m, cards: [...m.cards, ...newMeldCards] })
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
    message: `${SEAT_NAMES[player]} picked up the pile`,
    selectedCards: state.selectedCards.map(() => []),
  }
}

// ── Melding ─────────────────────────────────────────────────────────

function vsMeldCards(state: CanastaVsState, player: number, cardIndices: number[], targetMeldIdx?: number): CanastaVsState {
  if (state.phase !== 'meld' || !state.hasDrawn) return state
  if (state.currentPlayer !== player) return state

  const team = vsTeamOf(player)
  const hand = state.hands[player]
  const cards = cardIndices.map(i => hand[i]).filter(Boolean)
  if (cards.length === 0) return state

  let newTeamMelds: CanastaVsMeld[]
  let newInitialMeld = [...state.teamHasInitialMeld]

  if (targetMeldIdx !== undefined) {
    const meld = state.teamMelds[targetMeldIdx]
    if (!meld || meld.team !== team) return state
    if (!isValidMeldAddition(meld, cards)) return state

    newTeamMelds = state.teamMelds.map((m, i) => {
      if (i !== targetMeldIdx) return m
      return updateMeldStatus({ ...m, cards: [...m.cards, ...cards] })
    })
  } else {
    if (!isValidNewMeld(cards)) return state

    if (!state.teamHasInitialMeld[team]) {
      const req = getInitialMeldReq(state.teamScores[team])
      const meldPts = totalPoints(cards)
      if (meldPts < req) return state
      newInitialMeld[team] = true
    }

    const rank = naturalRank(cards)
    const existingIdx = state.teamMelds.findIndex(m => m.team === team && m.rank === rank)
    if (existingIdx >= 0) {
      if (!isValidMeldAddition(state.teamMelds[existingIdx], cards)) return state
      newTeamMelds = state.teamMelds.map((m, i) => {
        if (i !== existingIdx) return m
        return updateMeldStatus({ ...m, cards: [...m.cards, ...cards] })
      })
    } else {
      const newMeld = updateMeldStatus({ cards, rank, team, isCanasta: false, isNatural: false })
      newTeamMelds = [...state.teamMelds, newMeld]
    }
  }

  const newHands = state.hands.map(h => [...h])
  const indicesToRemove = new Set(cardIndices)
  newHands[player] = newHands[player].filter((_, i) => !indicesToRemove.has(i))

  return {
    ...state,
    hands: newHands,
    teamMelds: newTeamMelds,
    teamHasInitialMeld: newInitialMeld,
    message: `${SEAT_NAMES[player]} melded`,
    selectedCards: state.selectedCards.map(() => []),
  }
}

// ── Discarding ──────────────────────────────────────────────────────

function vsDiscard(state: CanastaVsState, player: number, cardIndex: number): CanastaVsState {
  if (!state.hasDrawn) return state
  if (state.currentPlayer !== player) return state

  const hand = state.hands[player]
  const card = hand[cardIndex]
  if (!card) return state

  const newHands = state.hands.map(h => [...h])
  newHands[player].splice(cardIndex, 1)
  const newDiscardPile = [...state.discardPile, card]
  const newPileFrozen = state.pileFrozen || isWild(card)
  const next = nextPlayer(player)

  // Check going out
  if (newHands[player].length === 0) {
    const team = vsTeamOf(player)
    const hasCanasta = state.teamMelds.some(m => m.team === team && m.isCanasta)
    if (hasCanasta) {
      return vsResolveRound({
        ...state, hands: newHands, discardPile: newDiscardPile, pileFrozen: newPileFrozen,
      }, player)
    }
  }

  if (state.stock.length === 0 && newHands[player].length === 0) {
    return vsResolveRound({
      ...state, hands: newHands, discardPile: newDiscardPile, pileFrozen: newPileFrozen,
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
    selectedCards: state.selectedCards.map(() => []),
    message: `${SEAT_NAMES[next]}'s turn`,
  }
}

// ── Going out ───────────────────────────────────────────────────────

function vsGoOut(state: CanastaVsState, player: number): CanastaVsState {
  if (state.phase !== 'meld' || !state.hasDrawn) return state
  if (state.currentPlayer !== player) return state

  const team = vsTeamOf(player)
  const hasCanasta = state.teamMelds.some(m => m.team === team && m.isCanasta)
  if (!hasCanasta) return state
  if (state.hands[player].length > 0) return state

  return vsResolveRound(state, player)
}

// ── Round resolution ────────────────────────────────────────────────

function vsScoreRound(state: CanastaVsState): number[] {
  const scores = [0, 0]

  for (const meld of state.teamMelds) {
    scores[meld.team] += totalPoints(meld.cards)
    if (meld.isCanasta) {
      scores[meld.team] += meld.isNatural ? NATURAL_CANASTA_BONUS : MIXED_CANASTA_BONUS
    }
  }

  // Red 3 bonuses
  for (let team = 0; team < 2; team++) {
    const teamPlayers = team === 0 ? [0, 1] : [2, 3]
    const teamRed3Count = teamPlayers.reduce((sum, p) => sum + state.redThrees[p].length, 0)

    if (teamRed3Count > 0) {
      const hasMelds = state.teamHasInitialMeld[team] || state.teamMelds.some(m => m.team === team)
      if (hasMelds) {
        scores[team] += teamRed3Count === 4 ? ALL_RED_3S_BONUS : teamRed3Count * RED_3_BONUS
      } else {
        scores[team] -= teamRed3Count === 4 ? ALL_RED_3S_BONUS : teamRed3Count * RED_3_BONUS
      }
    }
  }

  // Subtract unmelded hand cards
  for (let p = 0; p < 4; p++) {
    const team = vsTeamOf(p)
    scores[team] -= totalPoints(state.hands[p])
  }

  return scores
}

function vsResolveRound(state: CanastaVsState, goingOutPlayer: number): CanastaVsState {
  const roundScores = vsScoreRound(state)
  const goingOutTeam = vsTeamOf(goingOutPlayer)
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
      message: winner === 0 ? 'Your team wins!' : 'AI team wins!',
    }
  }

  return {
    ...state,
    teamScores: newScores,
    phase: 'roundOver',
    message: `Round over! ${VS_TEAM_NAMES[0]}: ${newScores[0]} | ${VS_TEAM_NAMES[1]}: ${newScores[1]}`,
  }
}

// ── AI ──────────────────────────────────────────────────────────────

function vsAiTurn(state: CanastaVsState): CanastaVsState {
  const player = state.currentPlayer
  if (player < 2) return state // not AI

  // Draw
  let current = vsDrawFromStock(state)
  if (current.phase === 'roundOver' || current.phase === 'gameOver') return current

  // Meld — try adding to existing team melds first
  current = vsAiAttemptMelds(current)

  // Try going out
  const team = vsTeamOf(player)
  const hasCanasta = current.teamMelds.some(m => m.team === team && m.isCanasta)
  if (hasCanasta && current.hands[player].length === 0) {
    return vsGoOut(current, player)
  }

  // Discard
  if (current.hands[player].length === 0) {
    if (hasCanasta) return vsGoOut(current, player)
    return {
      ...current,
      currentPlayer: nextPlayer(player),
      phase: 'draw',
      hasDrawn: false,
      message: `${SEAT_NAMES[nextPlayer(player)]}'s turn`,
    }
  }

  const discardIdx = vsAiChooseDiscard(current)
  return vsDiscard(current, player, discardIdx)
}

function vsAiAttemptMelds(state: CanastaVsState): CanastaVsState {
  const player = state.currentPlayer
  const team = vsTeamOf(player)
  let current = state

  // Add to existing team melds
  let changed = true
  while (changed) {
    changed = false
    const hand = current.hands[player]
    for (const meld of current.teamMelds) {
      if (meld.team !== team) continue
      for (let i = hand.length - 1; i >= 0; i--) {
        const card = hand[i]
        if (!isWild(card) && card.rank === meld.rank) {
          const meldIdx = current.teamMelds.indexOf(meld)
          const next = vsMeldCards(current, player, [i], meldIdx)
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

  // Try new melds
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
        const existingMeldIdx = current.teamMelds.findIndex(
          m => m.team === team && m.rank === current.hands[player][indices[0]].rank
        )
        if (existingMeldIdx >= 0) {
          const next = vsMeldCards(current, player, indices, existingMeldIdx)
          if (next !== current) { current = next; changed = true; break }
        } else {
          const next = vsMeldCards(current, player, indices.slice(0, 3))
          if (next !== current) { current = next; changed = true; break }
        }
      }
    }
  }

  return current
}

function vsAiChooseDiscard(state: CanastaVsState): number {
  const player = state.currentPlayer
  const hand = state.hands[player]
  if (hand.length === 0) return -1

  const rankCounts = new Map<number, number>()
  for (const card of hand) {
    if (!isWild(card)) {
      rankCounts.set(card.rank, (rankCounts.get(card.rank) || 0) + 1)
    }
  }

  let bestIdx = 0
  let bestScore = Infinity

  for (let i = 0; i < hand.length; i++) {
    const card = hand[i]
    if (isWild(card)) continue

    let score: number
    if (isBlack3(card)) {
      score = -100
    } else {
      const count = rankCounts.get(card.rank) || 0
      if (count === 1) score = cardPoints(card)
      else if (count === 2) score = cardPoints(card) * 20
      else score = cardPoints(card) * 50
    }

    if (score < bestScore) {
      bestScore = score
      bestIdx = i
    }
  }

  return bestIdx
}

// ── Props ────────────────────────────────────────────────────────────

interface Props {
  roomId: string
  players: number[]
  playerNames: Record<number, string>
  onLeave?: () => void
}

// ── Component ────────────────────────────────────────────────────────

export function CanastaMultiplayer({ roomId, players, playerNames, onLeave }: Props) {
  const { user } = useAuth()
  const isHost = players[0] === user?.id
  const myPlayerIndex = isHost ? 0 : 1

  const song = useMemo(() => getSongForGame('canasta'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('canasta')

  const [gameState, setGameState] = useState<CanastaVsState>(() => createVsCanastaGame())
  const stateRef = useRef(gameState)
  stateRef.current = gameState

  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const [selectedCards, setSelectedCards] = useState<number[]>([])

  const myName = playerNames[user?.id ?? 0] ?? 'You'
  const opponentName = playerNames[players[isHost ? 1 : 0]] ?? 'Opponent'
  const seatNames = [myName, opponentName, 'AI East', 'AI West']

  // ── Broadcast (host strips hidden info) ─────────────────────────

  const broadcastState = useCallback((state: CanastaVsState) => {
    if (!isHost) return
    const sanitized = {
      ...state,
      hands: state.hands.map((h, i) => i === 1 ? h : []),
    }
    gameSocket.sendAction(roomId, { type: 'state_sync', state: sanitized })
  }, [isHost, roomId])

  // Host: initialize and broadcast
  useEffect(() => {
    if (!isHost) return
    const state = createVsCanastaGame()
    setGameState(state)
    broadcastState(state)
  }, [isHost]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Host action processing ─────────────────────────────────────

  const hostApply = useCallback((fn: (s: CanastaVsState) => CanastaVsState) => {
    setGameState(prev => {
      const next = fn(prev)
      broadcastState(next)
      return next
    })
  }, [broadcastState])

  // ── WebSocket listener ─────────────────────────────────────────

  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg: { playerId?: number; action?: Record<string, unknown> }) => {
      if (msg.playerId === user?.id) return
      const action = msg.action
      if (!action) return

      if (action.type === 'state_sync' && !isHost) {
        const syncedState = action.state as CanastaVsState
        setGameState(prev => ({
          ...syncedState,
          hands: syncedState.hands.map((h, i) => {
            if (i === 1 && h.length > 0) return h
            if (i === 1) return prev.hands[1]
            return h
          }),
        }))
        return
      }

      // Host processes guest actions
      if (isHost) {
        if (action.type === 'draw') {
          hostApply(s => {
            if (s.currentPlayer !== 1) return s
            return vsDrawFromStock(s)
          })
        } else if (action.type === 'pickup_pile') {
          hostApply(s => {
            if (s.currentPlayer !== 1) return s
            return vsPickupDiscardPile(s, 1, action.cardIndices as number[])
          })
        } else if (action.type === 'meld') {
          hostApply(s => {
            if (s.currentPlayer !== 1) return s
            return vsMeldCards(s, 1, action.cardIndices as number[], action.targetMeldIdx as number | undefined)
          })
        } else if (action.type === 'discard') {
          hostApply(s => {
            if (s.currentPlayer !== 1) return s
            return vsDiscard(s, 1, action.cardIndex as number)
          })
        } else if (action.type === 'go_out') {
          hostApply(s => {
            if (s.currentPlayer !== 1) return s
            return vsGoOut(s, 1)
          })
        } else if (action.type === 'next_round') {
          hostApply(s => {
            if (s.phase !== 'roundOver') return s
            return createVsCanastaGame(s.teamScores)
          })
        }
      }
    })
    return unsub
  }, [roomId, isHost, user?.id, hostApply])

  // ── AI turns (host only) ───────────────────────────────────────

  useEffect(() => {
    if (!isHost) return
    if (gameState.phase === 'gameOver' || gameState.phase === 'roundOver') return
    const cp = gameState.currentPlayer
    if (cp !== 2 && cp !== 3) return

    const timer = setTimeout(() => {
      setGameState(prev => {
        if (prev.currentPlayer < 2) return prev
        if (prev.phase === 'gameOver' || prev.phase === 'roundOver') return prev

        let current = prev
        // Run all consecutive AI turns
        while (current.currentPlayer >= 2 &&
               current.phase !== 'gameOver' &&
               current.phase !== 'roundOver') {
          current = vsAiTurn(current)
        }
        broadcastState(current)
        return current
      })
    }, AI_DELAY)

    return () => clearTimeout(timer)
  }, [isHost, gameState.phase, gameState.currentPlayer, broadcastState])

  // ── Detect game over ──────────────────────────────────────────

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const won = gameState.teamScores[0] > gameState.teamScores[1]
      if (won) sfx.play('gin')
      setGameStatus(won ? 'won' : 'lost')
    }
  }, [gameState.phase]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Handlers ──────────────────────────────────────────────────

  const handleDraw = useCallback(() => {
    music.init(); sfx.init(); music.start()
    if (isHost) {
      hostApply(s => {
        if (s.currentPlayer !== 0) return s
        return vsDrawFromStock(s)
      })
    } else {
      gameSocket.sendAction(roomId, { type: 'draw' })
    }
    setSelectedCards([])
  }, [isHost, roomId, hostApply, music, sfx])

  const handlePickupPile = useCallback(() => {
    if (selectedCards.length < 2) return
    sfx.play('meld')
    if (isHost) {
      hostApply(s => {
        if (s.currentPlayer !== 0) return s
        return vsPickupDiscardPile(s, 0, selectedCards)
      })
    } else {
      gameSocket.sendAction(roomId, { type: 'pickup_pile', cardIndices: selectedCards })
    }
    setSelectedCards([])
  }, [isHost, roomId, hostApply, sfx, selectedCards])

  const handleMeld = useCallback(() => {
    if (selectedCards.length === 0) return
    sfx.play('meld')

    const player = myPlayerIndex
    const team = vsTeamOf(player)
    const hand = gameState.hands[player]
    const cards = selectedCards.map(i => hand[i]).filter(Boolean)
    const naturalCard = cards.find(c => !isWild(c))
    const rank = naturalCard?.rank

    let targetMeldIdx: number | undefined
    if (rank !== undefined) {
      const existing = gameState.teamMelds.findIndex(m => m.team === team && m.rank === rank)
      if (existing >= 0) targetMeldIdx = existing
    }

    if (isHost) {
      hostApply(s => {
        if (s.currentPlayer !== 0) return s
        return vsMeldCards(s, 0, selectedCards, targetMeldIdx)
      })
    } else {
      gameSocket.sendAction(roomId, { type: 'meld', cardIndices: selectedCards, targetMeldIdx })
    }
    setSelectedCards([])
  }, [isHost, roomId, hostApply, sfx, selectedCards, myPlayerIndex, gameState])

  const handleDiscard = useCallback(() => {
    if (selectedCards.length !== 1) return
    sfx.play('place')
    if (isHost) {
      hostApply(s => {
        if (s.currentPlayer !== 0) return s
        return vsDiscard(s, 0, selectedCards[0])
      })
    } else {
      gameSocket.sendAction(roomId, { type: 'discard', cardIndex: selectedCards[0] })
    }
    setSelectedCards([])
  }, [isHost, roomId, hostApply, sfx, selectedCards])

  const handleGoOut = useCallback(() => {
    sfx.play('knock')
    if (isHost) {
      hostApply(s => {
        if (s.currentPlayer !== 0) return s
        return vsGoOut(s, 0)
      })
    } else {
      gameSocket.sendAction(roomId, { type: 'go_out' })
    }
  }, [isHost, roomId, hostApply, sfx])

  const handleNextRound = useCallback(() => {
    if (isHost) {
      hostApply(s => {
        if (s.phase !== 'roundOver') return s
        return createVsCanastaGame(s.teamScores)
      })
    } else {
      gameSocket.sendAction(roomId, { type: 'next_round' })
    }
    setSelectedCards([])
  }, [isHost, roomId, hostApply])

  const toggleCardSelection = useCallback((index: number) => {
    setSelectedCards(prev =>
      prev.includes(index) ? prev.filter(i => i !== index) : [...prev, index]
    )
  }, [])

  // ── Derived state ─────────────────────────────────────────────

  const myHand = gameState.hands[myPlayerIndex] ?? []
  const isMyTurn = gameState.currentPlayer === myPlayerIndex
  const canDraw = isMyTurn && gameState.phase === 'draw' && !gameState.hasDrawn
  const canMeld = isMyTurn && gameState.phase === 'meld' && gameState.hasDrawn
  const canDiscard = isMyTurn && gameState.hasDrawn && selectedCards.length === 1
  const canPickup = isMyTurn && gameState.phase === 'draw' && !gameState.hasDrawn
  const canGoOut = isMyTurn && gameState.phase === 'meld' && gameState.hasDrawn &&
    myHand.length === 0 &&
    gameState.teamMelds.some(m => m.team === vsTeamOf(myPlayerIndex) && m.isCanasta)

  const team0Melds = gameState.teamMelds.filter(m => m.team === 0)
  const team1Melds = gameState.teamMelds.filter(m => m.team === 1)

  // Other player indices for layout: opponent=1-myIdx, AI East=2, AI West=3
  const opponentIdx = myPlayerIndex === 0 ? 1 : 0

  // ── Render ────────────────────────────────────────────────────

  const controls = (
    <div className="flex items-center justify-between text-xs">
      <div className="flex gap-3">
        <span className="text-blue-400">{VS_TEAM_NAMES[0]}: {gameState.teamScores[0]}</span>
        <span className="text-red-400">{VS_TEAM_NAMES[1]}: {gameState.teamScores[1]}</span>
      </div>
      <div className="flex gap-2 text-slate-400">
        <span>Stock: {gameState.stock.length}</span>
        <span>Pile: {gameState.discardPile.length}</span>
        {gameState.pileFrozen && <span className="text-cyan-400">Frozen</span>}
      </div>
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1 text-emerald-400">
          <Wifi className="w-3 h-3" />
          <span className="text-[0.6rem]">VS</span>
        </div>
        {onLeave && (
          <button onClick={onLeave} className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-white">
            <ArrowLeft className="w-4 h-4" />
          </button>
        )}
        <MusicToggle music={music} sfx={sfx} />
      </div>
    </div>
  )

  return (
    <GameLayout title="Canasta" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-2">

        {/* Opponent (North) */}
        <div className="text-center">
          <span className="text-xs text-blue-400">
            {seatNames[opponentIdx]} (Partner) ({gameState.hands[opponentIdx].length})
          </span>
          <div className="flex gap-0.5 justify-center mt-0.5">
            {gameState.hands[opponentIdx].slice(0, 7).map((_, i) => (
              <div key={i} className={CARD_SLOT_V}><CardBack /></div>
            ))}
            {gameState.hands[opponentIdx].length > 7 && (
              <span className="text-[0.6rem] text-slate-500 self-center">+{gameState.hands[opponentIdx].length - 7}</span>
            )}
          </div>
          {gameState.redThrees[opponentIdx].length > 0 && (
            <div className="flex gap-0.5 justify-center mt-0.5">
              {gameState.redThrees[opponentIdx].map((card, i) => (
                <div key={i} className={CARD_SLOT_V}>
                  <CardFace card={card} />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* AI West + Center + AI East */}
        <div className="flex w-full items-center gap-2">
          {/* AI West */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-red-400">AI West ({gameState.hands[3].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[3].slice(0, 5).map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
            {gameState.redThrees[3].length > 0 && (
              <div className="flex gap-0.5 justify-center mt-0.5">
                {gameState.redThrees[3].map((card, i) => (
                  <div key={i} className={CARD_SLOT_V}>
                    <CardFace card={card} />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Center: Stock + Discard */}
          <div className="flex-1 flex items-center justify-center gap-3 h-36 sm:h-48">
            <div className="text-center">
              {gameState.stock.length > 0 ? (
                <div className={CARD_SIZE_COMPACT}><CardBack /></div>
              ) : (
                <div className={`${CARD_SIZE_COMPACT} border border-dashed border-slate-600 rounded-md flex items-center justify-center`}>
                  <span className="text-[0.6rem] text-slate-600">Empty</span>
                </div>
              )}
              <span className="text-[0.55rem] text-slate-500 mt-0.5">{gameState.stock.length}</span>
            </div>

            <div className="text-center">
              {gameState.discardPile.length > 0 ? (
                <div className={`${CARD_SIZE_COMPACT} ${gameState.pileFrozen ? 'ring-2 ring-cyan-400' : ''}`}>
                  {(() => {
                    const topCard = gameState.discardPile[gameState.discardPile.length - 1]
                    return topCard.rank === 0 ? <JokerCard /> : <CardFace card={topCard} />
                  })()}
                </div>
              ) : (
                <div className={`${CARD_SIZE_COMPACT} border border-dashed border-slate-600 rounded-md flex items-center justify-center`}>
                  <span className="text-[0.6rem] text-slate-600">Empty</span>
                </div>
              )}
              <span className="text-[0.55rem] text-slate-500 mt-0.5">
                {gameState.discardPile.length}
                {gameState.pileFrozen ? ' (frozen)' : ''}
              </span>
            </div>
          </div>

          {/* AI East */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-red-400">AI East ({gameState.hands[2].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[2].slice(0, 5).map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
            {gameState.redThrees[2].length > 0 && (
              <div className="flex gap-0.5 justify-center mt-0.5">
                {gameState.redThrees[2].map((card, i) => (
                  <div key={i} className={CARD_SLOT_V}>
                    <CardFace card={card} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Team melds */}
        {(team0Melds.length > 0 || team1Melds.length > 0) && (
          <div className="w-full space-y-1">
            {team0Melds.length > 0 && (
              <div>
                <span className="text-[0.6rem] text-blue-400">Your team's melds:</span>
                <div className="flex flex-wrap gap-1 mt-0.5">
                  {team0Melds.map((meld, i) => (
                    <MeldDisplay key={i} meld={meld} />
                  ))}
                </div>
              </div>
            )}
            {team1Melds.length > 0 && (
              <div>
                <span className="text-[0.6rem] text-red-400">AI team melds:</span>
                <div className="flex flex-wrap gap-1 mt-0.5">
                  {team1Melds.map((meld, i) => (
                    <MeldDisplay key={i} meld={meld} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Message + turn indicator */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Red 3s for current player */}
        {gameState.redThrees[myPlayerIndex].length > 0 && (
          <div className="flex gap-1 justify-center">
            <span className="text-[0.6rem] text-red-400 self-center mr-1">Red 3s:</span>
            {gameState.redThrees[myPlayerIndex].map((card, i) => (
              <div key={i} className="w-8 h-12">
                <CardFace card={card} />
              </div>
            ))}
          </div>
        )}

        {/* Action buttons */}
        {isMyTurn && gameState.phase !== 'roundOver' && gameState.phase !== 'gameOver' && (
          <div className="flex flex-wrap gap-2 justify-center">
            {canDraw && (
              <button
                onClick={handleDraw}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-medium transition-colors"
              >
                Draw 2
              </button>
            )}
            {canPickup && (
              <button
                onClick={handlePickupPile}
                disabled={selectedCards.length < 2}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  selectedCards.length >= 2
                    ? 'bg-amber-600 hover:bg-amber-500 text-white'
                    : 'bg-slate-700 text-slate-500 cursor-not-allowed'
                }`}
              >
                Pick Up Pile
              </button>
            )}
            {canMeld && selectedCards.length >= 1 && (
              <button
                onClick={handleMeld}
                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-medium transition-colors"
              >
                Meld Selected
              </button>
            )}
            {canDiscard && (
              <button
                onClick={handleDiscard}
                className="px-3 py-1.5 bg-orange-600 hover:bg-orange-500 text-white rounded-lg text-xs font-medium transition-colors"
              >
                Discard
              </button>
            )}
            {canGoOut && (
              <button
                onClick={handleGoOut}
                className="px-3 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-xs font-medium transition-colors"
              >
                Go Out
              </button>
            )}
          </div>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1 justify-center max-w-md">
          {myHand.map((card, i) => (
            <GameCard
              key={`${card.rank}-${card.suit}-${i}`}
              card={card}
              selected={selectedCards.includes(i)}
              onClick={() => toggleCardSelection(i)}
              disabled={!isMyTurn || gameState.phase === 'roundOver' || gameState.phase === 'gameOver'}
            />
          ))}
        </div>

        {/* Round over */}
        {gameState.phase === 'roundOver' && (
          <button
            onClick={handleNextRound}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Next Round
          </button>
        )}

        {/* Game over */}
        {(gameStatus === 'won' || gameStatus === 'lost') && (
          <GameOverModal
            status={gameStatus}
            score={gameState.teamScores[0]}
            message={gameState.message}
            onPlayAgain={onLeave || (() => {})}
            playAgainText="Back to Lobby"
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
