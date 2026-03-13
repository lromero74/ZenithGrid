/**
 * Spades VS Multiplayer — 2 humans + 2 AI in a 4-player partnership game.
 *
 * Host-authoritative: host runs the engine, broadcasts state.
 * Player 0 (host) = South, Player 1 (guest) = North.
 * Teams: Host(0) + Guest(1) vs AI-East(2) + AI-West(3).
 * Spades are always trump.
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

interface Play { player: number; card: Card }

interface SpadesVsState {
  hands: Card[][]
  currentTrick: Play[]
  completedTricks: Play[][]
  bids: (number | null)[]
  tricksTaken: number[]
  teamScores: [number, number]   // [humans, AI]
  teamBags: [number, number]
  phase: 'bidding' | 'playing' | 'roundOver' | 'gameOver'
  currentPlayer: number
  leadPlayer: number
  spadesBroken: boolean
  roundNumber: number
  bidsSubmitted: boolean[]  // which human players have submitted bids
  message: string
}

// ── Constants ────────────────────────────────────────────────────────

const WINNING_SCORE = 500
const LOSING_SCORE = -200
const BAG_PENALTY_THRESHOLD = 10
const BAG_PENALTY = -100
const NIL_BONUS = 100
const AI_DELAY = 800
const SEAT_NAMES = ['South', 'North', 'East', 'West']
const TEAM_NAMES = ['Humans', 'AI Team']

// ── Card helpers ─────────────────────────────────────────────────────

function cardValue(card: Card): number {
  return card.rank === 1 ? 14 : card.rank
}

function sortHand(hand: Card[]): Card[] {
  const suitOrder: Suit[] = ['clubs', 'diamonds', 'hearts', 'spades']
  return [...hand].sort((a, b) => {
    const si = suitOrder.indexOf(a.suit) - suitOrder.indexOf(b.suit)
    if (si !== 0) return si
    return cardValue(a) - cardValue(b)
  })
}

function trickWinner(trick: Play[]): number {
  let best = trick[0]
  for (let i = 1; i < trick.length; i++) {
    const c = trick[i].card
    if (c.suit === 'spades' && best.card.suit !== 'spades') {
      best = trick[i]
    } else if (c.suit === best.card.suit && cardValue(c) > cardValue(best.card)) {
      best = trick[i]
    }
  }
  return best.player
}

// ── Engine ───────────────────────────────────────────────────────────

function createVsSpadesGame(): SpadesVsState {
  return dealRound({
    hands: [[], [], [], []],
    currentTrick: [],
    completedTricks: [],
    bids: [null, null, null, null],
    tricksTaken: [0, 0, 0, 0],
    teamScores: [0, 0],
    teamBags: [0, 0],
    phase: 'bidding',
    currentPlayer: 0,
    leadPlayer: 0,
    spadesBroken: false,
    roundNumber: 0,
    bidsSubmitted: [false, false],
    message: '',
  })
}

function dealRound(state: SpadesVsState): SpadesVsState {
  const deck = shuffleDeck(createDeck()).map(c => ({ ...c, faceUp: true }))
  const hands: Card[][] = [[], [], [], []]
  for (let i = 0; i < 52; i++) hands[i % 4].push(deck[i])
  for (let p = 0; p < 4; p++) hands[p] = sortHand(hands[p])

  return {
    ...state,
    hands,
    currentTrick: [],
    completedTricks: [],
    bids: [null, null, null, null],
    tricksTaken: [0, 0, 0, 0],
    phase: 'bidding',
    spadesBroken: false,
    bidsSubmitted: [false, false],
    currentPlayer: 0,
    message: 'Place your bid',
  }
}

function aiBid(hand: Card[]): number {
  let bid = 0
  const spades = hand.filter(c => c.suit === 'spades')
  for (const s of spades) { if (cardValue(s) >= 12) bid++ }
  for (const c of hand) { if (c.suit !== 'spades' && c.rank === 1) bid++ }
  const suits: Suit[] = ['hearts', 'diamonds', 'clubs']
  for (const suit of suits) {
    const sc = hand.filter(c => c.suit === suit)
    if (sc.length >= 3 && sc.some(c => c.rank === 13)) bid++
  }
  if (spades.length >= 4) bid++
  return Math.max(1, Math.min(bid, 7))
}

function submitBid(state: SpadesVsState, player: number, bid: number): SpadesVsState {
  if (state.phase !== 'bidding') return state
  if (player > 1) return state // only humans bid via this

  const bids = [...state.bids] as (number | null)[]
  bids[player] = bid
  const bidsSubmitted = [...state.bidsSubmitted]
  bidsSubmitted[player] = true

  // Check if both humans have bid
  if (bidsSubmitted[0] && bidsSubmitted[1]) {
    // AI bids
    bids[2] = aiBid(state.hands[2])
    bids[3] = aiBid(state.hands[3])

    const leadPlayer = (state.roundNumber) % 4

    return {
      ...state,
      bids: bids as number[],
      bidsSubmitted,
      phase: 'playing',
      currentPlayer: leadPlayer,
      leadPlayer,
      message: `Bids placed. ${SEAT_NAMES[leadPlayer]} leads.`,
    }
  }

  return {
    ...state,
    bids,
    bidsSubmitted,
    message: `Waiting for ${bidsSubmitted[0] ? SEAT_NAMES[1] : SEAT_NAMES[0]} to bid...`,
  }
}

function isValidPlay(card: Card, hand: Card[], state: SpadesVsState): boolean {
  const isLeading = state.currentTrick.length === 0
  if (isLeading) {
    if (card.suit === 'spades' && !state.spadesBroken) {
      return !hand.some(c => c.suit !== 'spades')
    }
    return true
  }
  const leadSuit = state.currentTrick[0].card.suit
  const hasSuit = hand.some(c => c.suit === leadSuit)
  if (hasSuit) return card.suit === leadSuit
  return true
}

function getValidPlays(state: SpadesVsState, player: number): number[] {
  if (state.phase !== 'playing' || state.currentPlayer !== player) return []
  const hand = state.hands[player]
  return hand.map((c, i) => isValidPlay(c, hand, state) ? i : -1).filter(i => i >= 0)
}

function playCardInState(state: SpadesVsState, player: number, cardIndex: number): SpadesVsState {
  if (state.phase !== 'playing' || state.currentPlayer !== player) return state
  const hand = state.hands[player]
  const card = hand[cardIndex]
  if (!card || !isValidPlay(card, hand, state)) return state

  const newHands = state.hands.map(h => [...h])
  newHands[player].splice(cardIndex, 1)
  const newTrick = [...state.currentTrick, { player, card }]
  const spadesBroken = state.spadesBroken || card.suit === 'spades'

  let next: SpadesVsState = { ...state, hands: newHands, currentTrick: newTrick, spadesBroken }
  if (newTrick.length === 4) return completeTrick(next)
  return { ...next, currentPlayer: (player + 1) % 4 }
}

function completeTrick(state: SpadesVsState): SpadesVsState {
  const winner = trickWinner(state.currentTrick)
  const tricksTaken = [...state.tricksTaken]
  tricksTaken[winner]++
  const completedTricks = [...state.completedTricks, state.currentTrick]

  if (completedTricks.length === 13) {
    return resolveRound({ ...state, currentTrick: [], completedTricks, tricksTaken })
  }

  return {
    ...state,
    currentTrick: [],
    completedTricks,
    tricksTaken,
    currentPlayer: winner,
    leadPlayer: winner,
    phase: 'playing',
    message: `${SEAT_NAMES[winner]} won the trick`,
  }
}

function resolveRound(state: SpadesVsState): SpadesVsState {
  const teamScores: [number, number] = [...state.teamScores]
  const teamBags: [number, number] = [...state.teamBags]
  const bids = state.bids as number[]

  // Team 0 = players 0+1 (humans), Team 1 = players 2+3 (AI)
  for (let team = 0; team < 2; team++) {
    const p1 = team === 0 ? 0 : 2
    const p2 = team === 0 ? 1 : 3
    const teamBid = bids[p1] + bids[p2]
    const teamTricks = state.tricksTaken[p1] + state.tricksTaken[p2]

    let nilBonus = 0
    for (const p of [p1, p2]) {
      if (bids[p] === 0) {
        if (state.tricksTaken[p] === 0) nilBonus += NIL_BONUS
        else nilBonus -= NIL_BONUS
      }
    }

    const nonNilBid = (bids[p1] === 0 ? 0 : bids[p1]) + (bids[p2] === 0 ? 0 : bids[p2])
    const actualBid = nonNilBid || teamBid

    if (teamTricks >= actualBid) {
      const bags = teamTricks - actualBid
      teamScores[team as 0 | 1] += actualBid * 10 + bags
      teamBags[team as 0 | 1] += bags
      if (teamBags[team as 0 | 1] >= BAG_PENALTY_THRESHOLD) {
        teamScores[team as 0 | 1] += BAG_PENALTY
        teamBags[team as 0 | 1] -= BAG_PENALTY_THRESHOLD
      }
    } else {
      teamScores[team as 0 | 1] -= actualBid * 10
    }
    teamScores[team as 0 | 1] += nilBonus
  }

  const gameOver = teamScores[0] >= WINNING_SCORE || teamScores[1] >= WINNING_SCORE ||
                   teamScores[0] <= LOSING_SCORE || teamScores[1] <= LOSING_SCORE

  if (gameOver) {
    const humanWin = teamScores[0] > teamScores[1]
    return {
      ...state, teamScores, teamBags,
      phase: 'gameOver',
      message: humanWin ? 'Your team wins!' : 'AI team wins!',
    }
  }

  return {
    ...state, teamScores, teamBags,
    phase: 'roundOver',
    roundNumber: state.roundNumber + 1,
    message: `Round over! ${TEAM_NAMES[0]}: ${teamScores[0]} | ${TEAM_NAMES[1]}: ${teamScores[1]}`,
  }
}

function nextRound(state: SpadesVsState): SpadesVsState {
  return dealRound(state)
}

function aiChooseCard(hand: Card[], state: SpadesVsState): number {
  const isLeading = state.currentTrick.length === 0
  const valid = hand.map((c, i) => isValidPlay(c, hand, state) ? i : -1).filter(i => i >= 0)
  if (valid.length === 1) return valid[0]

  if (isLeading) {
    const nonSpades = valid.filter(i => hand[i].suit !== 'spades')
    const pool = nonSpades.length > 0 ? nonSpades : valid
    return pool.sort((a, b) => cardValue(hand[b]) - cardValue(hand[a]))[0]
  }

  const leadSuit = state.currentTrick[0].card.suit
  const following = valid.filter(i => hand[i].suit === leadSuit)
  if (following.length > 0) {
    const partnerIdx = (state.currentPlayer + 2) % 4
    const currentWinner = trickWinner([...state.currentTrick])
    if (currentWinner === partnerIdx) {
      return following.sort((a, b) => cardValue(hand[a]) - cardValue(hand[b]))[0]
    }
    return following.sort((a, b) => cardValue(hand[b]) - cardValue(hand[a]))[0]
  }

  const spades = valid.filter(i => hand[i].suit === 'spades')
  if (spades.length > 0) {
    const partnerIdx = (state.currentPlayer + 2) % 4
    const currentWinner = trickWinner([...state.currentTrick])
    if (currentWinner === partnerIdx) {
      const nonSpades = valid.filter(i => hand[i].suit !== 'spades')
      if (nonSpades.length > 0) return nonSpades.sort((a, b) => cardValue(hand[a]) - cardValue(hand[b]))[0]
    }
    return spades.sort((a, b) => cardValue(hand[a]) - cardValue(hand[b]))[0]
  }

  return valid.sort((a, b) => cardValue(hand[a]) - cardValue(hand[b]))[0]
}

// ── Props ────────────────────────────────────────────────────────────

interface Props {
  roomId: string
  players: number[]
  playerNames: Record<number, string>
  onLeave?: () => void
}

// ── Component ────────────────────────────────────────────────────────

export function SpadesMultiplayer({ roomId, players, playerNames, onLeave }: Props) {
  const { user } = useAuth()
  const isHost = players[0] === user?.id
  const myPlayerIndex = isHost ? 0 : 1

  const song = useMemo(() => getSongForGame('spades'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('spades')

  const [gameState, setGameState] = useState<SpadesVsState>(() => createVsSpadesGame())
  const stateRef = useRef(gameState)
  stateRef.current = gameState

  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const [selectedBid, setSelectedBid] = useState(3)

  const myName = playerNames[user?.id ?? 0] ?? 'You'
  const opponentName = playerNames[players[isHost ? 1 : 0]] ?? 'Partner'
  const seatNames = [myName, opponentName, 'AI East', 'AI West']

  // ── Broadcast ──────────────────────────────────────────────────

  const broadcastState = useCallback((state: SpadesVsState) => {
    if (!isHost) return
    const sanitized = {
      ...state,
      hands: state.hands.map((h, i) => i === 1 ? h : []),
    }
    gameSocket.sendAction(roomId, { type: 'state_sync', state: sanitized })
  }, [isHost, roomId])

  useEffect(() => {
    if (!isHost) return
    const state = createVsSpadesGame()
    setGameState(state)
    broadcastState(state)
  }, [isHost]) // eslint-disable-line react-hooks/exhaustive-deps

  const hostApply = useCallback((fn: (s: SpadesVsState) => SpadesVsState) => {
    setGameState(prev => {
      const next = fn(prev)
      broadcastState(next)
      return next
    })
  }, [broadcastState])

  // ── WebSocket ──────────────────────────────────────────────────

  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg: { playerId?: number; action?: Record<string, unknown> }) => {
      if (msg.playerId === user?.id) return
      const action = msg.action
      if (!action) return

      if (action.type === 'state_sync' && !isHost) {
        const synced = action.state as SpadesVsState
        setGameState(prev => ({
          ...synced,
          hands: synced.hands.map((h, i) => {
            if (i === 1 && h.length > 0) return h
            if (i === 1) return prev.hands[1]
            return h
          }),
        }))
        return
      }

      if (isHost) {
        if (action.type === 'submit_bid') {
          hostApply(s => submitBid(s, 1, action.bid as number))
        } else if (action.type === 'play_card') {
          hostApply(s => playCardInState(s, 1, action.cardIndex as number))
        } else if (action.type === 'next_round') {
          hostApply(s => nextRound(s))
        }
      }
    })
    return unsub
  }, [roomId, isHost, user?.id, hostApply])

  // ── AI turns ───────────────────────────────────────────────────

  useEffect(() => {
    if (!isHost) return
    if (gameState.phase !== 'playing') return
    const cp = gameState.currentPlayer
    if (cp !== 2 && cp !== 3) return

    const timer = setTimeout(() => {
      setGameState(prev => {
        let current = prev
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

  // ── Game over ──────────────────────────────────────────────────

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      setGameStatus(gameState.teamScores[0] > gameState.teamScores[1] ? 'won' : 'lost')
    }
  }, [gameState.phase, gameState.teamScores])

  // ── Handlers ───────────────────────────────────────────────────

  const handleBid = useCallback(() => {
    music.init(); sfx.init(); music.start()
    sfx.play('deal')
    if (isHost) {
      hostApply(s => submitBid(s, 0, selectedBid))
    } else {
      gameSocket.sendAction(roomId, { type: 'submit_bid', bid: selectedBid })
      setGameState(prev => submitBid(prev, 1, selectedBid))
    }
  }, [isHost, roomId, hostApply, selectedBid, music, sfx])

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

  // ── Derived ────────────────────────────────────────────────────

  const myHand = gameState.hands[myPlayerIndex]
  const isBidding = gameState.phase === 'bidding' && !gameState.bidsSubmitted[myPlayerIndex]
  const isMyTurn = gameState.phase === 'playing' && gameState.currentPlayer === myPlayerIndex
  const validPlays = isMyTurn ? getValidPlays(gameState, myPlayerIndex) : []

  const opponentIdx = myPlayerIndex === 0 ? 1 : 0

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
      <div className="flex items-center gap-3 text-xs">
        <span className="text-blue-400">{TEAM_NAMES[0]}: {gameState.teamScores[0]}</span>
        <span className="text-red-400">{TEAM_NAMES[1]}: {gameState.teamScores[1]}</span>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Spades -- VS" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-3">
        {/* North (partner/opponent human) */}
        <div className="text-center">
          <span className="text-xs text-blue-400">{seatNames[opponentIdx]} (Partner) ({gameState.hands[opponentIdx].length})</span>
          <div className="flex gap-0.5 justify-center mt-0.5">
            {gameState.hands[opponentIdx].slice(0, 7).map((_, i) => (
              <div key={i} className={CARD_SLOT_V}><CardBack /></div>
            ))}
            {gameState.hands[opponentIdx].length > 7 && (
              <span className="text-[0.6rem] text-slate-500 self-center">+{gameState.hands[opponentIdx].length - 7}</span>
            )}
          </div>
        </div>

        {/* West + Trick + East */}
        <div className="flex w-full items-center gap-2">
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-red-400">AI West ({gameState.hands[3].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[3].slice(0, 5).map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
          </div>

          <div className="flex-1 relative h-36 sm:h-48">
            {gameState.currentTrick.map((play) => {
              const posMap: Record<number, string> = {
                [myPlayerIndex]: 'bottom-0 left-1/2 -translate-x-1/2',
                [opponentIdx]: 'top-0 left-1/2 -translate-x-1/2',
                2: 'right-0 top-1/2 -translate-y-1/2',
                3: 'left-0 top-1/2 -translate-y-1/2',
              }
              return (
                <div key={`${play.player}-${play.card.rank}-${play.card.suit}`}
                  className={`absolute ${posMap[play.player]} ${CARD_SIZE_COMPACT}`}
                >
                  <CardFace card={play.card} />
                </div>
              )
            })}

            {gameState.spadesBroken && gameState.currentTrick.length === 0 && (
              <span className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[0.6rem] text-slate-500">
                Spades broken
              </span>
            )}
          </div>

          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-red-400">AI East ({gameState.hands[2].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[2].slice(0, 5).map((_, i) => (
                <div key={i} className={CARD_SLOT_H}><CardBack /></div>
              ))}
            </div>
          </div>
        </div>

        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Bid/tricks tracker */}
        {gameState.bids[0] !== null && (
          <div className="flex gap-2 text-xs text-slate-400">
            {seatNames.map((name, i) => (
              <span key={i}>
                {name}: {gameState.bids[i] ?? '?'}/{gameState.tricksTaken[i]}
              </span>
            ))}
          </div>
        )}

        {/* Bidding UI */}
        {isBidding && (
          <div className="flex flex-col items-center gap-2">
            <div className="flex gap-1 flex-wrap justify-center">
              {Array.from({ length: 14 }, (_, i) => (
                <button
                  key={i}
                  onClick={() => setSelectedBid(i)}
                  className={`w-8 h-8 text-xs rounded transition-colors ${
                    selectedBid === i ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {i === 0 ? 'Nil' : i}
                </button>
              ))}
            </div>
            <button
              onClick={handleBid}
              className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Bid {selectedBid === 0 ? 'Nil' : selectedBid}
            </button>
          </div>
        )}

        {gameState.phase === 'bidding' && gameState.bidsSubmitted[myPlayerIndex] && (
          <p className="text-xs text-slate-400">Waiting for partner to bid...</p>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1 justify-center max-w-md">
          {myHand.map((card, i) => {
            const isValid = validPlays.includes(i)
            return (
              <div
                key={`${card.rank}-${card.suit}-${i}`}
                className={`${CARD_SIZE_COMPACT} transition-transform ${
                  isMyTurn && isValid ? 'cursor-pointer hover:-translate-y-1' : 'opacity-40'
                }`}
                onClick={() => isMyTurn && isValid && handlePlayCard(i)}
              >
                <CardFace card={card} />
              </div>
            )
          })}
        </div>

        {gameState.phase === 'roundOver' && (
          <button onClick={handleNextRound} className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors">
            Next Round
          </button>
        )}

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
