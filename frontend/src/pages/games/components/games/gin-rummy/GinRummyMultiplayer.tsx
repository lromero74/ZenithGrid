/**
 * Gin Rummy VS — two human players over WebSocket.
 *
 * Host-authoritative: host runs the engine, broadcasts state.
 * Each player sees their own hand face-up and opponent's hand face-down.
 * Draw from stock or discard, form melds, knock or gin.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { Wifi, ArrowLeft } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE } from '../../PlayingCard'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'
import {
  createDeck,
  shuffleDeck,
  type Card,
  type Suit,
} from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

type Phase = 'drawing' | 'discarding' | 'knocked' | 'scoring' | 'gameOver'

interface Meld {
  cards: Card[]
  type: 'set' | 'run'
}

interface GinRummyVsState {
  hands: Card[][]          // [0] = host, [1] = guest
  drawPile: Card[]
  discardPile: Card[]
  phase: Phase
  currentPlayer: 0 | 1
  knocker: 0 | 1 | null
  scores: [number, number]
  roundMessage: string
  message: string
  targetScore: number
}

/** State broadcast to guest — no drawPile contents, no opponent hand details */
interface GuestViewState {
  myHand: Card[]
  opponentHandCount: number
  drawPileCount: number
  discardPile: Card[]
  phase: Phase
  currentPlayer: 0 | 1
  knocker: 0 | 1 | null
  scores: [number, number]
  roundMessage: string
  message: string
  targetScore: number
  // Revealed on scoring/gameOver
  opponentHand?: Card[]
}

// ── Engine logic (inline) ────────────────────────────────────────────

const TARGET_SCORE = 100
const GIN_BONUS = 25
const UNDERCUT_BONUS = 25

function deadwoodValue(card: Card): number {
  if (card.rank >= 11) return 10
  if (card.rank === 1) return 1
  return card.rank
}

function findSets(hand: Card[]): Meld[] {
  const byRank = new Map<number, Card[]>()
  for (const c of hand) {
    const arr = byRank.get(c.rank) || []
    arr.push(c)
    byRank.set(c.rank, arr)
  }
  const melds: Meld[] = []
  for (const [, cards] of byRank) {
    if (cards.length >= 3) {
      melds.push({ cards: cards.slice(0, 3), type: 'set' })
      if (cards.length === 4) melds.push({ cards: [...cards], type: 'set' })
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
    for (let start = 0; start < suitCards.length - 2; start++) {
      const run: Card[] = [suitCards[start]]
      for (let j = start + 1; j < suitCards.length; j++) {
        if (suitCards[j].rank === run[run.length - 1].rank + 1) {
          run.push(suitCards[j])
          if (run.length >= 3) melds.push({ cards: [...run], type: 'run' })
        } else break
      }
    }
  }
  return melds
}

function findBestMelds(hand: Card[]): { melds: Meld[]; deadwood: Card[]; deadwoodTotal: number } {
  const allMelds = [...findSets(hand), ...findRuns(hand)]
  let best = { melds: [] as Meld[], deadwood: [...hand], deadwoodTotal: hand.reduce((s, c) => s + deadwoodValue(c), 0) }

  function tryMelds(remaining: Card[], usedMelds: Meld[], meldIdx: number) {
    const dw = remaining.reduce((s, c) => s + deadwoodValue(c), 0)
    if (dw < best.deadwoodTotal) {
      best = { melds: [...usedMelds], deadwood: [...remaining], deadwoodTotal: dw }
    }
    for (let i = meldIdx; i < allMelds.length; i++) {
      const meld = allMelds[i]
      const remCopy = [...remaining]
      let valid = true
      for (const mc of meld.cards) {
        const idx = remCopy.findIndex(c => c.rank === mc.rank && c.suit === mc.suit)
        if (idx === -1) { valid = false; break }
        remCopy.splice(idx, 1)
      }
      if (valid) tryMelds(remCopy, [...usedMelds, meld], i + 1)
    }
  }

  tryMelds(hand, [], 0)
  return best
}

function findWorstDeadwoodCard(hand: Card[]): number {
  const { deadwood } = findBestMelds(hand)
  if (deadwood.length === 0) return hand.length - 1
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

function sortHand(hand: Card[]): Card[] {
  return [...hand].sort((a, b) => a.suit.localeCompare(b.suit) || a.rank - b.rank)
}

function createGame(): GinRummyVsState {
  const deck = shuffleDeck(createDeck()).map(c => ({ ...c, faceUp: true }))
  const hand0 = deck.splice(0, 10)
  const hand1 = deck.splice(0, 10)
  const firstDiscard = deck.pop()!
  return {
    hands: [sortHand(hand0), sortHand(hand1)],
    drawPile: deck,
    discardPile: [firstDiscard],
    phase: 'drawing',
    currentPlayer: 0,
    knocker: null,
    scores: [0, 0],
    roundMessage: '',
    message: 'Draw from the pile or discard pile',
    targetScore: TARGET_SCORE,
  }
}

function resolveKnock(state: GinRummyVsState): GinRummyVsState {
  const knockerHand = state.hands[state.knocker!]
  const defenderHand = state.hands[state.knocker === 0 ? 1 : 0]

  const knockerMelds = findBestMelds(knockerHand)
  const defenderMelds = findBestMelds(defenderHand)

  const isGin = knockerMelds.deadwoodTotal === 0

  let points: number
  let winner: 0 | 1

  if (isGin) {
    points = defenderMelds.deadwoodTotal + GIN_BONUS
    winner = state.knocker!
  } else if (defenderMelds.deadwoodTotal <= knockerMelds.deadwoodTotal) {
    points = knockerMelds.deadwoodTotal - defenderMelds.deadwoodTotal + UNDERCUT_BONUS
    winner = state.knocker === 0 ? 1 : 0
  } else {
    points = defenderMelds.deadwoodTotal - knockerMelds.deadwoodTotal
    winner = state.knocker!
  }

  const scores: [number, number] = [...state.scores] as [number, number]
  scores[winner] += points

  const gameOver = scores[0] >= state.targetScore || scores[1] >= state.targetScore

  return {
    ...state,
    scores,
    knocker: state.knocker,
    phase: gameOver ? 'gameOver' : 'scoring',
    roundMessage: isGin
      ? `Gin! +${points} points`
      : defenderMelds.deadwoodTotal <= knockerMelds.deadwoodTotal
        ? `Undercut! +${points} points`
        : `Knock wins! +${points} points`,
    message: gameOver
      ? `Game over! Final: ${scores[0]} - ${scores[1]}`
      : `Round over: +${points} points`,
  }
}

function canKnock(hand: Card[]): boolean {
  if (hand.length !== 11) return false
  const tempHand = [...hand]
  const worstIdx = findWorstDeadwoodCard(tempHand)
  tempHand.splice(worstIdx, 1)
  return findBestMelds(tempHand).deadwoodTotal <= 10
}

function getDeadwoodAfterDiscard(hand: Card[]): number {
  if (hand.length !== 11) return findBestMelds(hand).deadwoodTotal
  const tempHand = [...hand]
  const worstIdx = findWorstDeadwoodCard(tempHand)
  tempHand.splice(worstIdx, 1)
  return findBestMelds(tempHand).deadwoodTotal
}

// ── Props ────────────────────────────────────────────────────────────

interface Props {
  roomId: string
  players: number[]
  playerNames: Record<number, string>
  onLeave?: () => void
}

// ── Component ────────────────────────────────────────────────────────

export function GinRummyMultiplayer({ roomId, players, playerNames, onLeave }: Props) {
  const { user } = useAuth()

  const song = useMemo(() => getSongForGame('gin-rummy'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('gin-rummy')

  const isHost = players[0] === user?.id
  const myPlayerIndex: 0 | 1 = isHost ? 0 : 1
  const opponentPlayerIndex: 0 | 1 = isHost ? 1 : 0
  const myName = playerNames[user?.id ?? 0] ?? 'You'
  const opponentId = players.find(id => id !== user?.id)
  const opponentName = opponentId ? (playerNames[opponentId] ?? 'Opponent') : 'Opponent'

  // Host holds full game state
  const [gameState, setGameState] = useState<GinRummyVsState | null>(null)
  const gameStateRef = useRef<GinRummyVsState | null>(null)
  useEffect(() => { gameStateRef.current = gameState }, [gameState])

  // Guest holds view state
  const [guestView, setGuestView] = useState<GuestViewState | null>(null)

  // ── Build guest view from host state ────────────────────────────

  const buildGuestView = useCallback((state: GinRummyVsState, forPlayer: 0 | 1): GuestViewState => {
    const opponent = forPlayer === 0 ? 1 : 0
    const showCards = state.phase === 'scoring' || state.phase === 'gameOver' || state.phase === 'knocked'
    return {
      myHand: state.hands[forPlayer],
      opponentHandCount: state.hands[opponent].length,
      drawPileCount: state.drawPile.length,
      discardPile: state.discardPile,
      phase: state.phase,
      currentPlayer: state.currentPlayer,
      knocker: state.knocker,
      scores: state.scores,
      roundMessage: state.roundMessage,
      message: state.message,
      targetScore: state.targetScore,
      opponentHand: showCards ? state.hands[opponent] : undefined,
    }
  }, [])

  // ── Host: create game on mount ─────────────────────────────────

  useEffect(() => {
    if (!isHost) return
    const state = createGame()
    setGameState(state)
    // Send guest their view
    gameSocket.sendAction(roomId, { type: 'gr_sync', view: buildGuestView(state, 1) })
  }, [isHost, roomId, buildGuestView])

  // ── Host: broadcast after state change ─────────────────────────

  const broadcastAndSet = useCallback((state: GinRummyVsState) => {
    setGameState(state)
    gameSocket.sendAction(roomId, { type: 'gr_sync', view: buildGuestView(state, 1) })
  }, [roomId, buildGuestView])

  // ── Host: process action ───────────────────────────────────────

  const processAction = useCallback((action: Record<string, unknown>, fromPlayer: 0 | 1) => {
    const current = gameStateRef.current
    if (!current) return

    switch (action.type) {
      case 'gr_draw_stock': {
        if (current.phase !== 'drawing' || current.currentPlayer !== fromPlayer) return
        if (current.drawPile.length === 0) return
        const drawPile = [...current.drawPile]
        const card = drawPile.pop()!
        const hands = current.hands.map((h, i) =>
          i === fromPlayer ? sortHand([...h, { ...card, faceUp: true }]) : [...h]
        )
        broadcastAndSet({
          ...current,
          hands,
          drawPile,
          phase: 'discarding',
          message: 'Discard a card',
        })
        break
      }
      case 'gr_draw_discard': {
        if (current.phase !== 'drawing' || current.currentPlayer !== fromPlayer) return
        if (current.discardPile.length === 0) return
        const discardPile = [...current.discardPile]
        const card = discardPile.pop()!
        const hands = current.hands.map((h, i) =>
          i === fromPlayer ? sortHand([...h, { ...card, faceUp: true }]) : [...h]
        )
        broadcastAndSet({
          ...current,
          hands,
          discardPile,
          phase: 'discarding',
          message: 'Discard a card',
        })
        break
      }
      case 'gr_discard': {
        if (current.phase !== 'discarding' || current.currentPlayer !== fromPlayer) return
        const cardIndex = action.cardIndex as number
        const hand = [...current.hands[fromPlayer]]
        if (cardIndex < 0 || cardIndex >= hand.length) return
        const card = hand.splice(cardIndex, 1)[0]
        const discardPile = [...current.discardPile, card]
        const hands = current.hands.map((h, i) => i === fromPlayer ? sortHand(hand) : [...h])
        const nextPlayer: 0 | 1 = fromPlayer === 0 ? 1 : 0

        // Check for stalemate
        if (current.drawPile.length === 0) {
          broadcastAndSet({
            ...current,
            hands,
            discardPile,
            phase: 'scoring',
            roundMessage: 'Draw — no cards remaining',
            message: 'Round ended in a draw',
          })
          return
        }

        broadcastAndSet({
          ...current,
          hands,
          discardPile,
          currentPlayer: nextPlayer,
          phase: 'drawing',
          message: 'Draw from the pile or discard pile',
        })
        break
      }
      case 'gr_knock': {
        if (current.phase !== 'discarding' || current.currentPlayer !== fromPlayer) return
        const hand = [...current.hands[fromPlayer]]
        if (hand.length !== 11) return
        const worstIdx = findWorstDeadwoodCard(hand)
        const discarded = hand.splice(worstIdx, 1)[0]
        const discardPile = [...current.discardPile, discarded]

        const { deadwoodTotal } = findBestMelds(hand)
        if (deadwoodTotal > 10) return

        const hands = current.hands.map((h, i) => i === fromPlayer ? sortHand(hand) : [...h])
        broadcastAndSet(resolveKnock({
          ...current,
          hands,
          discardPile,
          knocker: fromPlayer,
        }))
        break
      }
      case 'gr_new_round': {
        if (current.phase !== 'scoring') return
        const fresh = createGame()
        broadcastAndSet({
          ...fresh,
          scores: current.scores,
        })
        break
      }
    }
  }, [broadcastAndSet])

  // ── Send action (guest sends to host, host processes directly) ─

  const sendAction = useCallback((action: Record<string, unknown>) => {
    music.init()
    sfx.init()
    music.start()

    if (isHost) {
      processAction(action, myPlayerIndex)
    } else {
      gameSocket.sendAction(roomId, action)
    }
  }, [isHost, roomId, myPlayerIndex, processAction, music, sfx])

  // ── WebSocket listener ─────────────────────────────────────────

  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg: any) => {
      if (msg.roomId !== roomId) return
      const action = msg.action
      if (!action) return

      // Guest receives state sync
      if (action.type === 'gr_sync' && !isHost) {
        setGuestView(action.view)
        return
      }

      // Host receives guest's actions
      if (isHost && action.type?.startsWith('gr_') && action.type !== 'gr_sync') {
        const fromPlayer: 0 | 1 = msg.playerId === players[0] ? 0 : 1
        processAction(action, fromPlayer)
      }
    })
    return unsub
  }, [roomId, isHost, players, processAction])

  // ── Derive view data ───────────────────────────────────────────

  const view: GuestViewState | null = isHost && gameState
    ? buildGuestView(gameState, 0)
    : guestView

  if (!view) {
    return (
      <div className="flex items-center justify-center py-12">
        <span className="text-slate-400 text-sm">Waiting for game to start...</span>
      </div>
    )
  }

  const isMyTurn = view.currentPlayer === myPlayerIndex
  const isDrawing = view.phase === 'drawing' && isMyTurn
  const isDiscarding = view.phase === 'discarding' && isMyTurn
  const topDiscard = view.discardPile[view.discardPile.length - 1]
  const showKnock = isMyTurn && view.phase === 'discarding' && canKnock(view.myHand)
  const deadwood = view.phase === 'discarding'
    ? getDeadwoodAfterDiscard(view.myHand)
    : findBestMelds(view.myHand).deadwoodTotal
  const showOpponentCards = view.phase === 'scoring' || view.phase === 'gameOver' || view.phase === 'knocked'

  const gameOver = view.phase === 'gameOver'
  const iWon = gameOver && view.scores[myPlayerIndex] >= view.targetScore

  // ── Handlers ───────────────────────────────────────────────────

  const handleDrawPile = useCallback(() => {
    sfx.play('deal')
    sendAction({ type: 'gr_draw_stock' })
  }, [sfx, sendAction])

  const handleDrawDiscard = useCallback(() => {
    sfx.play('deal')
    sendAction({ type: 'gr_draw_discard' })
  }, [sfx, sendAction])

  const handleDiscard = useCallback((i: number) => {
    sfx.play('place')
    sendAction({ type: 'gr_discard', cardIndex: i })
  }, [sfx, sendAction])

  const handleKnock = useCallback(() => {
    sfx.play('place')
    sendAction({ type: 'gr_knock' })
  }, [sfx, sendAction])

  const handleNewRound = useCallback(() => {
    sendAction({ type: 'gr_new_round' })
  }, [sendAction])

  // ── Turn label ─────────────────────────────────────────────────

  const turnLabel = view.phase === 'scoring'
    ? ''
    : isMyTurn
      ? (view.phase === 'drawing' ? 'Your turn — draw a card' : 'Your turn — discard a card')
      : `${opponentName}'s turn`

  // ── Controls ───────────────────────────────────────────────────

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        {onLeave && (
          <button
            onClick={onLeave}
            className="flex items-center gap-1 px-3 py-1.5 text-xs rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
          >
            <ArrowLeft className="w-3 h-3" /> Leave
          </button>
        )}
        <Wifi className="w-3.5 h-3.5 text-green-400" />
        <span className="text-xs text-slate-400">VS Mode</span>
      </div>
      <div className="flex items-center gap-3 text-xs">
        <span className="text-white">{myName}: {view.scores[myPlayerIndex]}</span>
        <span className="text-slate-400">{opponentName}: {view.scores[opponentPlayerIndex]}</span>
        <span className="text-slate-400">DW: {deadwood}</span>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  // ── Render ─────────────────────────────────────────────────────

  return (
    <GameLayout title="Gin Rummy — VS" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-4">
        {/* Opponent hand */}
        <div className="text-center">
          <span className="text-xs text-slate-400 mb-1 block">
            {opponentName} ({view.opponentHandCount} cards)
          </span>
          <div className="flex gap-1 justify-center flex-wrap">
            {showOpponentCards && view.opponentHand
              ? view.opponentHand.map((card, i) => (
                  <div key={i} className={CARD_SIZE}>
                    <CardFace card={{ ...card, faceUp: true }} />
                  </div>
                ))
              : Array.from({ length: Math.min(view.opponentHandCount, 10) }).map((_, i) => (
                  <div key={i} className={CARD_SIZE}>
                    <CardBack />
                  </div>
                ))
            }
          </div>
        </div>

        {/* Draw pile + Discard pile */}
        <div className="flex gap-4 items-center justify-center">
          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500 block mb-0.5">Draw ({view.drawPileCount})</span>
            <div
              className={`${CARD_SIZE} ${isDrawing ? 'cursor-pointer ring-2 ring-blue-400/50 rounded-md' : ''}`}
              onClick={isDrawing ? handleDrawPile : undefined}
            >
              {view.drawPileCount > 0 ? <CardBack /> : (
                <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">Empty</div>
              )}
            </div>
          </div>
          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500 block mb-0.5">Discard</span>
            <div
              className={`${CARD_SIZE} ${isDrawing && topDiscard ? 'cursor-pointer ring-2 ring-blue-400/50 rounded-md' : ''}`}
              onClick={isDrawing ? handleDrawDiscard : undefined}
            >
              {topDiscard ? <CardFace card={topDiscard} /> : (
                <div className="w-full h-full rounded-md border border-dashed border-slate-600/50" />
              )}
            </div>
          </div>
        </div>

        {/* Turn indicator */}
        {view.phase !== 'scoring' && view.phase !== 'gameOver' && (
          <div className={`text-center py-1.5 px-4 rounded-lg text-xs font-medium ${
            isMyTurn
              ? 'bg-emerald-900/40 border border-emerald-700/50 text-emerald-300'
              : 'bg-amber-900/40 border border-amber-700/50 text-amber-300'
          }`}>
            {turnLabel}
          </div>
        )}

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{view.message}</p>

        {/* Knock button */}
        {showKnock && (
          <button
            onClick={handleKnock}
            className="px-4 py-2 bg-yellow-600 hover:bg-yellow-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            {deadwood === 0 ? 'Gin!' : `Knock (${deadwood} deadwood)`}
          </button>
        )}

        {/* Player hand */}
        <div className="text-center">
          <span className="text-xs text-slate-400 mb-1 block">{myName}&apos;s Hand</span>
          <div className="flex gap-1 justify-center flex-wrap">
            {view.myHand.map((card, i) => (
              <div
                key={i}
                className={`${CARD_SIZE} transition-transform ${
                  isDiscarding ? 'cursor-pointer hover:-translate-y-1' : ''
                }`}
                onClick={() => isDiscarding && handleDiscard(i)}
              >
                <CardFace card={card} />
              </div>
            ))}
          </div>
        </div>

        {/* Round over */}
        {view.phase === 'scoring' && (
          <div className="text-center space-y-2">
            <p className="text-sm text-emerald-400">{view.roundMessage}</p>
            <button
              onClick={handleNewRound}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Next Round
            </button>
          </div>
        )}

        {/* Game over */}
        {gameOver && (
          <GameOverModal
            status={iWon ? 'won' : 'lost'}
            score={view.scores[myPlayerIndex]}
            message={`${myName}: ${view.scores[myPlayerIndex]} — ${opponentName}: ${view.scores[opponentPlayerIndex]}`}
            onPlayAgain={onLeave ?? (() => {})}
            playAgainText="Return to Lobby"
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
