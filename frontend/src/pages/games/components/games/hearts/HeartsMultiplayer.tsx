/**
 * Hearts VS Multiplayer — 2 humans + 2 AI in a 4-player Hearts game.
 *
 * Host-authoritative: host runs the engine, broadcasts state.
 * Player 0 (host) = South, Player 1 (guest) = North, AI = East (2) and West (3).
 * No partnerships — everyone plays for themselves.
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
import {
  createDeck, shuffleDeck, type Card, type Suit,
} from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

interface Play {
  player: number
  card: Card
}

type PassDirection = 'left' | 'right' | 'across' | 'none'

type Phase = 'passing' | 'playing' | 'trickComplete' | 'roundOver' | 'gameOver'

interface HeartsVsState {
  hands: Card[][]         // 4 hands
  currentTrick: Play[]
  completedTricks: Play[][]
  scores: number[]
  roundScores: number[]
  phase: Phase
  currentPlayer: number
  leadPlayer: number
  passDirection: PassDirection
  selectedCards: number[][] // per-player pass selections
  heartsBroken: boolean
  roundNumber: number
  message: string
}

// ── Constants ────────────────────────────────────────────────────────

const PASS_DIRECTIONS: PassDirection[] = ['left', 'right', 'across', 'none']
const GAME_OVER_SCORE = 100
const AI_DELAY = 800
// Seat mapping: 0=South(host), 1=North(guest), 2=East(AI), 3=West(AI)
const SEAT_NAMES = ['South', 'North', 'East', 'West']

// ── Card helpers ─────────────────────────────────────────────────────

function cardValue(card: Card): number {
  return card.rank === 1 ? 14 : card.rank
}

function sortHand(hand: Card[]): Card[] {
  const suitOrder: Suit[] = ['clubs', 'diamonds', 'spades', 'hearts']
  return [...hand].sort((a, b) => {
    const si = suitOrder.indexOf(a.suit) - suitOrder.indexOf(b.suit)
    if (si !== 0) return si
    return cardValue(a) - cardValue(b)
  })
}

function isQueenOfSpades(card: Card): boolean {
  return card.suit === 'spades' && card.rank === 12
}

function is2OfClubs(card: Card): boolean {
  return card.suit === 'clubs' && card.rank === 2
}

function pointsForCard(card: Card): number {
  if (card.suit === 'hearts') return 1
  if (isQueenOfSpades(card)) return 13
  return 0
}

function trickPoints(trick: Play[]): number {
  return trick.reduce((sum, p) => sum + pointsForCard(p.card), 0)
}

function trickWinner(trick: Play[]): number {
  const leadSuit = trick[0].card.suit
  let best = trick[0]
  for (let i = 1; i < trick.length; i++) {
    if (trick[i].card.suit === leadSuit && cardValue(trick[i].card) > cardValue(best.card)) {
      best = trick[i]
    }
  }
  return best.player
}

// ── Game engine ──────────────────────────────────────────────────────

function createVsHeartsGame(): HeartsVsState {
  return dealRound({
    hands: [[], [], [], []],
    currentTrick: [],
    completedTricks: [],
    scores: [0, 0, 0, 0],
    roundScores: [0, 0, 0, 0],
    phase: 'passing',
    currentPlayer: 0,
    leadPlayer: 0,
    passDirection: 'left',
    selectedCards: [[], [], [], []],
    heartsBroken: false,
    roundNumber: 0,
    message: '',
  })
}

function dealRound(state: HeartsVsState): HeartsVsState {
  const deck = shuffleDeck(createDeck()).map(c => ({ ...c, faceUp: true }))
  const hands: Card[][] = [[], [], [], []]
  for (let i = 0; i < 52; i++) {
    hands[i % 4].push(deck[i])
  }
  for (let p = 0; p < 4; p++) {
    hands[p] = sortHand(hands[p])
  }

  const passDir = PASS_DIRECTIONS[state.roundNumber % 4]

  if (passDir === 'none') {
    const starter = hands.findIndex(h => h.some(is2OfClubs))
    return {
      ...state,
      hands,
      currentTrick: [],
      completedTricks: [],
      roundScores: [0, 0, 0, 0],
      phase: 'playing',
      currentPlayer: starter,
      leadPlayer: starter,
      passDirection: passDir,
      selectedCards: [[], [], [], []],
      heartsBroken: false,
      message: `${SEAT_NAMES[starter]} leads`,
    }
  }

  return {
    ...state,
    hands,
    currentTrick: [],
    completedTricks: [],
    roundScores: [0, 0, 0, 0],
    phase: 'passing',
    passDirection: passDir,
    selectedCards: [[], [], [], []],
    heartsBroken: false,
    message: `Pass 3 cards ${passDir}`,
  }
}

function togglePassCard(state: HeartsVsState, player: number, cardIndex: number): HeartsVsState {
  if (state.phase !== 'passing') return state
  const selected = [...state.selectedCards]
  selected[player] = [...selected[player]]
  const idx = selected[player].indexOf(cardIndex)
  if (idx >= 0) {
    selected[player].splice(idx, 1)
  } else if (selected[player].length < 3) {
    selected[player].push(cardIndex)
  }
  return { ...state, selectedCards: selected }
}

function aiSelectPassCards(hand: Card[]): number[] {
  const indexed = hand.map((c, i) => ({ card: c, index: i }))
  indexed.sort((a, b) => {
    if (isQueenOfSpades(a.card)) return -1
    if (isQueenOfSpades(b.card)) return 1
    if (a.card.suit === 'hearts' && b.card.suit !== 'hearts') return -1
    if (b.card.suit === 'hearts' && a.card.suit !== 'hearts') return 1
    return cardValue(b.card) - cardValue(a.card)
  })
  return indexed.slice(0, 3).map(x => x.index)
}

function confirmPass(state: HeartsVsState): HeartsVsState {
  if (state.phase !== 'passing') return state
  // Check both humans have selected 3
  if (state.selectedCards[0].length !== 3 || state.selectedCards[1].length !== 3) return state

  const passOffset = state.passDirection === 'left' ? 1 : state.passDirection === 'right' ? 3 : 2
  const newHands = state.hands.map(h => [...h])

  // Collect passing cards for all players
  const passing: Card[][] = [[], [], [], []]
  // Human players use their selections
  for (const p of [0, 1]) {
    passing[p] = state.selectedCards[p].map(i => newHands[p][i])
    newHands[p] = newHands[p].filter((_, i) => !state.selectedCards[p].includes(i))
  }
  // AI players auto-select
  for (const p of [2, 3]) {
    const aiIndices = aiSelectPassCards(newHands[p])
    passing[p] = aiIndices.map(i => newHands[p][i])
    newHands[p] = newHands[p].filter((_, i) => !aiIndices.includes(i))
  }

  // Distribute
  for (let p = 0; p < 4; p++) {
    const target = (p + passOffset) % 4
    for (const c of passing[p]) newHands[target].push(c)
  }

  for (let p = 0; p < 4; p++) {
    newHands[p] = sortHand(newHands[p])
  }

  const starter = newHands.findIndex(h => h.some(is2OfClubs))

  return {
    ...state,
    hands: newHands,
    selectedCards: [[], [], [], []],
    phase: 'playing',
    currentPlayer: starter,
    leadPlayer: starter,
    message: `${SEAT_NAMES[starter]} leads`,
  }
}

function isValidPlay(card: Card, hand: Card[], state: HeartsVsState): boolean {
  const isFirstTrick = state.completedTricks.length === 0
  const isLeading = state.currentTrick.length === 0

  if (isFirstTrick && isLeading) return is2OfClubs(card)

  if (!isLeading) {
    const leadSuit = state.currentTrick[0].card.suit
    const hasSuit = hand.some(c => c.suit === leadSuit)
    if (hasSuit && card.suit !== leadSuit) return false
  }

  if (isFirstTrick && !isLeading) {
    if (pointsForCard(card) > 0) {
      const leadSuit = state.currentTrick[0].card.suit
      const hasAnySuit = hand.some(c => c.suit === leadSuit)
      if (hasAnySuit) {
        const hasNonPoints = hand.some(c => pointsForCard(c) === 0 && c.suit === leadSuit)
        if (hasNonPoints) return false
      } else {
        const hasAnyNonPoint = hand.some(c => pointsForCard(c) === 0)
        if (hasAnyNonPoint) return false
      }
    }
  }

  if (isLeading && card.suit === 'hearts' && !state.heartsBroken) {
    const hasNonHearts = hand.some(c => c.suit !== 'hearts')
    if (hasNonHearts) return false
  }

  return true
}

function getValidPlays(state: HeartsVsState, player: number): number[] {
  if (state.phase !== 'playing' || state.currentPlayer !== player) return []
  const hand = state.hands[player]
  return hand.map((c, i) => isValidPlay(c, hand, state) ? i : -1).filter(i => i >= 0)
}

function playCardInState(state: HeartsVsState, player: number, cardIndex: number): HeartsVsState {
  if (state.phase !== 'playing' || state.currentPlayer !== player) return state
  const hand = state.hands[player]
  const card = hand[cardIndex]
  if (!card || !isValidPlay(card, hand, state)) return state

  const newHands = state.hands.map(h => [...h])
  newHands[player].splice(cardIndex, 1)

  const newTrick = [...state.currentTrick, { player, card }]
  const heartsBroken = state.heartsBroken || card.suit === 'hearts'

  let next: HeartsVsState = {
    ...state,
    hands: newHands,
    currentTrick: newTrick,
    heartsBroken,
  }

  if (newTrick.length === 4) {
    return completeTrick(next)
  }

  next = { ...next, currentPlayer: (player + 1) % 4 }
  return next
}

function completeTrick(state: HeartsVsState): HeartsVsState {
  const winner = trickWinner(state.currentTrick)
  const points = trickPoints(state.currentTrick)
  const roundScores = [...state.roundScores]
  roundScores[winner] += points
  const completedTricks = [...state.completedTricks, state.currentTrick]

  if (completedTricks.length === 13) {
    return resolveRound({ ...state, currentTrick: [], completedTricks, roundScores })
  }

  return {
    ...state,
    currentTrick: [],
    completedTricks,
    roundScores,
    currentPlayer: winner,
    leadPlayer: winner,
    phase: 'playing',
    message: `${SEAT_NAMES[winner]} won the trick`,
  }
}

function resolveRound(state: HeartsVsState): HeartsVsState {
  const roundScores = [...state.roundScores]
  const moonShooter = roundScores.findIndex(s => s === 26)
  if (moonShooter >= 0) {
    for (let i = 0; i < 4; i++) {
      roundScores[i] = i === moonShooter ? 0 : 26
    }
  }

  const scores = state.scores.map((s, i) => s + roundScores[i])
  const maxScore = Math.max(...scores)

  if (maxScore >= GAME_OVER_SCORE) {
    const minScore = Math.min(...scores)
    const winner = scores.indexOf(minScore)
    return {
      ...state, scores, roundScores,
      phase: 'gameOver',
      message: `${SEAT_NAMES[winner]} wins with ${minScore} points!`,
    }
  }

  const moonMsg = moonShooter >= 0 ? ` ${SEAT_NAMES[moonShooter]} shot the moon!` : ''
  return {
    ...state, scores, roundScores,
    phase: 'roundOver',
    roundNumber: state.roundNumber + 1,
    message: `Round over!${moonMsg}`,
  }
}

function nextRound(state: HeartsVsState): HeartsVsState {
  return dealRound(state)
}

// AI card choice
function aiChooseCard(hand: Card[], state: HeartsVsState): number {
  const isLeading = state.currentTrick.length === 0
  const isFirstTrick = state.completedTricks.length === 0

  if (isFirstTrick && isLeading) {
    return hand.findIndex(is2OfClubs)
  }

  const validIndices = hand.map((c, i) => isValidPlay(c, hand, state) ? i : -1).filter(i => i >= 0)
  if (validIndices.length === 1) return validIndices[0]

  if (isLeading) {
    const nonHearts = validIndices.filter(i => hand[i].suit !== 'hearts')
    const pool = nonHearts.length > 0 ? nonHearts : validIndices
    return pool.sort((a, b) => cardValue(hand[a]) - cardValue(hand[b]))[0]
  }

  const leadSuit = state.currentTrick[0].card.suit
  const following = validIndices.filter(i => hand[i].suit === leadSuit)

  if (following.length > 0) {
    const currentBest = state.currentTrick
      .filter(p => p.card.suit === leadSuit)
      .reduce((best, p) => cardValue(p.card) > cardValue(best.card) ? p : best)
    const safe = following.filter(i => cardValue(hand[i]) < cardValue(currentBest.card))
    if (safe.length > 0) return safe.sort((a, b) => cardValue(hand[b]) - cardValue(hand[a]))[0]
    return following.sort((a, b) => cardValue(hand[a]) - cardValue(hand[b]))[0]
  }

  // Void - dump dangerous cards
  const qosIdx = validIndices.find(i => isQueenOfSpades(hand[i]))
  if (qosIdx !== undefined) return qosIdx
  const heartIndices = validIndices.filter(i => hand[i].suit === 'hearts')
  if (heartIndices.length > 0) return heartIndices.sort((a, b) => cardValue(hand[b]) - cardValue(hand[a]))[0]
  return validIndices.sort((a, b) => cardValue(hand[b]) - cardValue(hand[a]))[0]
}

// ── Props ────────────────────────────────────────────────────────────

interface Props {
  roomId: string
  players: number[]
  playerNames: Record<number, string>
  onLeave?: () => void
}

// ── Component ────────────────────────────────────────────────────────

export function HeartsMultiplayer({ roomId, players, playerNames, onLeave }: Props) {
  const { user } = useAuth()
  const isHost = players[0] === user?.id
  const myPlayerIndex = isHost ? 0 : 1

  const song = useMemo(() => getSongForGame('hearts'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('hearts')

  const [gameState, setGameState] = useState<HeartsVsState>(() => createVsHeartsGame())
  const stateRef = useRef(gameState)
  stateRef.current = gameState

  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')

  const myName = playerNames[user?.id ?? 0] ?? 'You'
  const opponentName = playerNames[players[isHost ? 1 : 0]] ?? 'Opponent'
  const seatNames = [myName, opponentName, 'AI East', 'AI West']
  // Remap: from my perspective, seat 0 = me (South), seat 1 = opponent (North)
  // But in the state, 0=host, 1=guest, 2=AI East, 3=AI West

  // ── Broadcast (host strips hidden info) ─────────────────────────

  const broadcastState = useCallback((state: HeartsVsState) => {
    if (!isHost) return
    // Strip AI and opponent hands from guest view
    const sanitized = {
      ...state,
      hands: state.hands.map((h, i) => i === 1 ? h : []), // only send guest their hand
    }
    gameSocket.sendAction(roomId, { type: 'state_sync', state: sanitized })
  }, [isHost, roomId])

  // Host: initialize and broadcast
  useEffect(() => {
    if (!isHost) return
    const state = createVsHeartsGame()
    setGameState(state)
    broadcastState(state)
  }, [isHost]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Host action processing ─────────────────────────────────────

  const hostApply = useCallback((fn: (s: HeartsVsState) => HeartsVsState) => {
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
        const syncedState = action.state as HeartsVsState
        // Guest merges: keeps own hand from sync, but host already sent it
        setGameState(prev => ({
          ...syncedState,
          // Merge host's full state with guest's hand
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
        if (action.type === 'toggle_pass') {
          hostApply(s => togglePassCard(s, 1, action.cardIndex as number))
        } else if (action.type === 'confirm_pass') {
          hostApply(s => confirmPass(s))
        } else if (action.type === 'play_card') {
          hostApply(s => playCardInState(s, 1, action.cardIndex as number))
        } else if (action.type === 'next_round') {
          hostApply(s => nextRound(s))
        }
      }
    })
    return unsub
  }, [roomId, isHost, user?.id, hostApply])

  // ── AI turns (host only) ───────────────────────────────────────

  useEffect(() => {
    if (!isHost) return
    if (gameState.phase !== 'playing') return
    const cp = gameState.currentPlayer
    if (cp !== 2 && cp !== 3) return // not AI's turn

    const timer = setTimeout(() => {
      setGameState(prev => {
        if (prev.phase !== 'playing') return prev
        let current = prev
        // Run AI turns until it's a human's turn
        while ((current.currentPlayer === 2 || current.currentPlayer === 3) && current.phase === 'playing') {
          const hand = current.hands[current.currentPlayer]
          const cardIdx = aiChooseCard(hand, current)
          current = playCardInState(current, current.currentPlayer, cardIdx)
        }
        broadcastState(current)
        return current
      })
    }, AI_DELAY)
    return () => clearTimeout(timer)
  }, [isHost, gameState.phase, gameState.currentPlayer, gameState.currentTrick.length, broadcastState])

  // ── Game over detection ────────────────────────────────────────

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      // Find winner (lowest score)
      const minScore = Math.min(...gameState.scores)
      const winnerIdx = gameState.scores.indexOf(minScore)
      if (winnerIdx === myPlayerIndex) {
        setGameStatus('won')
      } else {
        setGameStatus('lost')
      }
    }
  }, [gameState.phase, gameState.scores, myPlayerIndex])

  // ── Handlers ───────────────────────────────────────────────────

  const handleTogglePass = useCallback((cardIndex: number) => {
    music.init()
    sfx.init()
    music.start()
    if (isHost) {
      hostApply(s => togglePassCard(s, 0, cardIndex))
    } else {
      gameSocket.sendAction(roomId, { type: 'toggle_pass', cardIndex })
      setGameState(prev => togglePassCard(prev, 1, cardIndex))
    }
  }, [isHost, roomId, hostApply, music, sfx])

  const handleConfirmPass = useCallback(() => {
    sfx.play('deal')
    if (isHost) {
      hostApply(s => confirmPass(s))
    } else {
      gameSocket.sendAction(roomId, { type: 'confirm_pass' })
    }
  }, [isHost, roomId, hostApply, sfx])

  const handlePlayCard = useCallback((cardIndex: number) => {
    sfx.play('place')
    if (isHost) {
      hostApply(s => playCardInState(s, 0, cardIndex))
    } else {
      gameSocket.sendAction(roomId, { type: 'play_card', cardIndex })
    }
  }, [isHost, roomId, hostApply, sfx])

  const handleNextRound = useCallback(() => {
    sfx.play('deal')
    if (isHost) {
      hostApply(s => nextRound(s))
    } else {
      gameSocket.sendAction(roomId, { type: 'next_round' })
    }
  }, [isHost, roomId, hostApply, sfx])

  // ── Derived state ──────────────────────────────────────────────

  const myHand = gameState.hands[myPlayerIndex]
  const isPassing = gameState.phase === 'passing'
  const isMyTurn = gameState.phase === 'playing' && gameState.currentPlayer === myPlayerIndex
  const validPlays = isMyTurn ? getValidPlays(gameState, myPlayerIndex) : []
  const myPassSelected = gameState.selectedCards[myPlayerIndex]

  // ── Render ─────────────────────────────────────────────────────

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        {onLeave && (
          <button onClick={onLeave} className="flex items-center gap-1 px-3 py-1.5 text-xs rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors">
            <ArrowLeft className="w-3 h-3" /> Leave
          </button>
        )}
        <Wifi className="w-3.5 h-3.5 text-green-400" />
        <span className="text-xs text-slate-400">VS Mode</span>
      </div>
      <div className="flex items-center gap-2 text-xs text-slate-400">
        {seatNames.map((name, i) => (
          <span key={i} className={i === myPlayerIndex ? 'text-blue-400' : ''}>
            {name}: {gameState.scores[i]}{gameState.roundScores[i] > 0 ? ` (+${gameState.roundScores[i]})` : ''}
          </span>
        ))}
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  // Position mapping: myPlayer=South(bottom), opponent=North(top), AI=East(right),West(left)
  const opponentIdx = myPlayerIndex === 0 ? 1 : 0
  const eastIdx = 2
  const westIdx = 3

  return (
    <GameLayout title="Hearts -- VS" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-3">
        {/* North (opponent) */}
        <div className="text-center">
          <span className="text-xs text-slate-400">{seatNames[opponentIdx]} ({gameState.hands[opponentIdx].length})</span>
          <div className="flex gap-0.5 justify-center mt-0.5">
            {gameState.hands[opponentIdx].slice(0, 7).map((_, i) => (
              <div key={i} className={CARD_SLOT_V}><CardBack /></div>
            ))}
            {gameState.hands[opponentIdx].length > 7 && (
              <span className="text-[0.6rem] text-slate-500 self-center">+{gameState.hands[opponentIdx].length - 7}</span>
            )}
          </div>
        </div>

        {/* West + Trick area + East */}
        <div className="flex w-full items-center gap-2">
          {/* West (AI) */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-slate-400">{seatNames[westIdx]} ({gameState.hands[westIdx].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[westIdx].slice(0, 5).map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
          </div>

          {/* Trick area */}
          <div className="flex-1 relative h-36 sm:h-48">
            {gameState.currentTrick.map((play) => {
              // Map player index to visual position
              const posMap: Record<number, string> = {
                [myPlayerIndex]: 'bottom-0 left-1/2 -translate-x-1/2',
                [opponentIdx]: 'top-0 left-1/2 -translate-x-1/2',
                [eastIdx]: 'right-0 top-1/2 -translate-y-1/2',
                [westIdx]: 'left-0 top-1/2 -translate-y-1/2',
              }
              return (
                <div key={`${play.player}-${play.card.rank}-${play.card.suit}`}
                  className={`absolute ${posMap[play.player]} ${CARD_SIZE_COMPACT}`}
                >
                  <CardFace card={play.card} />
                </div>
              )
            })}

            {/* Turn indicator */}
            {gameState.phase === 'playing' && gameState.currentTrick.length === 0 && (
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-center">
                <span className="text-[0.6rem] text-slate-500">
                  {isMyTurn ? 'Your turn' : `${seatNames[gameState.currentPlayer]}'s turn`}
                </span>
              </div>
            )}
          </div>

          {/* East (AI) */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-slate-400">{seatNames[eastIdx]} ({gameState.hands[eastIdx].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[eastIdx].slice(0, 5).map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
          </div>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Hearts broken indicator */}
        {gameState.heartsBroken && (
          <span className="text-red-400 text-xs">Hearts broken</span>
        )}

        {/* Passing controls */}
        {isPassing && (
          <button
            onClick={handleConfirmPass}
            disabled={myPassSelected.length !== 3}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Pass 3 Cards {gameState.passDirection}
          </button>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1 justify-center max-w-md">
          {myHand.map((card, i) => {
            const isValid = isPassing || validPlays.includes(i)
            const isSelected = isPassing && myPassSelected.includes(i)
            return (
              <div
                key={`${card.rank}-${card.suit}-${i}`}
                className={`${CARD_SIZE_COMPACT} transition-transform ${
                  isValid ? 'cursor-pointer hover:-translate-y-1' : 'opacity-40'
                } ${isSelected ? '-translate-y-2' : ''}`}
                onClick={() => {
                  if (isPassing) handleTogglePass(i)
                  else if (isMyTurn && validPlays.includes(i)) handlePlayCard(i)
                }}
              >
                <CardFace card={card} selected={isSelected} />
              </div>
            )
          })}
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
            score={gameState.scores[myPlayerIndex]}
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
