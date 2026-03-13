/**
 * Crazy Eights VS — two human players over WebSocket.
 *
 * Host-authoritative: host runs the engine, broadcasts state.
 * Each player sees their own hand face-up and opponent's hand face-down.
 * Match suit or rank, 8s are wild.
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
  SUITS,
  getSuitSymbol,
  type Card,
  type Suit,
} from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

type Phase = 'playing' | 'choosingSuit' | 'roundOver' | 'gameOver'

interface CrazyEightsVsState {
  hands: Card[][]          // [0] = host, [1] = guest
  drawPile: Card[]
  discardPile: Card[]
  currentPlayer: 0 | 1
  currentSuit: Suit
  phase: Phase
  scores: [number, number]
  message: string
  targetScore: number
  /** Track who played an 8 (for suit choosing) */
  suitChooser: 0 | 1 | null
}

interface GuestViewState {
  myHand: Card[]
  opponentHandCount: number
  drawPileCount: number
  discardPile: Card[]
  currentPlayer: 0 | 1
  currentSuit: Suit
  phase: Phase
  scores: [number, number]
  message: string
  targetScore: number
  suitChooser: 0 | 1 | null
}

// ── Engine logic (inline) ────────────────────────────────────────────

const TARGET_SCORE = 200

function cardPoints(card: Card): number {
  if (card.rank === 8) return 50
  if (card.rank >= 11 || card.rank === 1) return 10
  return card.rank
}

function canPlayCard(card: Card, topDiscard: Card, currentSuit: Suit): boolean {
  if (card.rank === 8) return true
  return card.suit === currentSuit || card.rank === topDiscard.rank
}

function getPlayableIndices(hand: Card[], topDiscard: Card, currentSuit: Suit): number[] {
  return hand.map((c, i) => canPlayCard(c, topDiscard, currentSuit) ? i : -1).filter(i => i >= 0)
}

function createGame(): CrazyEightsVsState {
  const deck = shuffleDeck(createDeck()).map(c => ({ ...c, faceUp: true }))
  const hands: Card[][] = [deck.splice(0, 7), deck.splice(0, 7)]

  // Find a non-8 starter
  let discardIdx = 0
  while (deck[discardIdx].rank === 8 && discardIdx < deck.length - 1) discardIdx++
  const firstDiscard = deck[discardIdx]
  const drawPile = [...deck.slice(0, discardIdx), ...deck.slice(discardIdx + 1)]

  return {
    hands,
    drawPile,
    discardPile: [firstDiscard],
    currentPlayer: 0,
    currentSuit: firstDiscard.suit,
    phase: 'playing',
    scores: [0, 0],
    message: 'Your turn — play a card or draw',
    targetScore: TARGET_SCORE,
    suitChooser: null,
  }
}

function reshuffleDrawPile(state: CrazyEightsVsState): Card[] {
  if (state.drawPile.length > 0) return [...state.drawPile]
  const reshuffled = shuffleDeck(state.discardPile.slice(0, -1).map(c => ({ ...c, faceUp: true })))
  return reshuffled.length > 0 ? reshuffled : []
}

function scoreRound(state: CrazyEightsVsState, winner: 0 | 1): CrazyEightsVsState {
  const loser: 0 | 1 = winner === 0 ? 1 : 0
  let points = 0
  for (const card of state.hands[loser]) {
    points += cardPoints(card)
  }
  const scores: [number, number] = [...state.scores] as [number, number]
  scores[winner] += points

  if (scores[winner] >= state.targetScore) {
    return { ...state, scores, phase: 'gameOver', message: `Game over! ${scores[0]} - ${scores[1]}` }
  }
  return { ...state, scores, phase: 'roundOver', message: `Round won! +${points} points` }
}

// ── Props ────────────────────────────────────────────────────────────

interface Props {
  roomId: string
  players: number[]
  playerNames: Record<number, string>
  onLeave?: () => void
}

// ── Component ────────────────────────────────────────────────────────

export function CrazyEightsMultiplayer({ roomId, players, playerNames, onLeave }: Props) {
  const { user } = useAuth()

  const song = useMemo(() => getSongForGame('crazy-eights'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('crazy-eights')

  const isHost = players[0] === user?.id
  const myPlayerIndex: 0 | 1 = isHost ? 0 : 1
  const opponentPlayerIndex: 0 | 1 = isHost ? 1 : 0
  const myName = playerNames[user?.id ?? 0] ?? 'You'
  const opponentId = players.find(id => id !== user?.id)
  const opponentName = opponentId ? (playerNames[opponentId] ?? 'Opponent') : 'Opponent'

  const [gameState, setGameState] = useState<CrazyEightsVsState | null>(null)
  const gameStateRef = useRef<CrazyEightsVsState | null>(null)
  useEffect(() => { gameStateRef.current = gameState }, [gameState])

  const [guestView, setGuestView] = useState<GuestViewState | null>(null)

  // ── Build guest view ────────────────────────────────────────────

  const buildGuestView = useCallback((state: CrazyEightsVsState, forPlayer: 0 | 1): GuestViewState => {
    const opponent = forPlayer === 0 ? 1 : 0
    return {
      myHand: state.hands[forPlayer],
      opponentHandCount: state.hands[opponent].length,
      drawPileCount: state.drawPile.length,
      discardPile: state.discardPile,
      currentPlayer: state.currentPlayer,
      currentSuit: state.currentSuit,
      phase: state.phase,
      scores: state.scores,
      message: state.message,
      targetScore: state.targetScore,
      suitChooser: state.suitChooser,
    }
  }, [])

  // ── Host: create game ──────────────────────────────────────────

  useEffect(() => {
    if (!isHost) return
    const state = createGame()
    setGameState(state)
    gameSocket.sendAction(roomId, { type: 'ce_sync', view: buildGuestView(state, 1) })
  }, [isHost, roomId, buildGuestView])

  const broadcastAndSet = useCallback((state: CrazyEightsVsState) => {
    setGameState(state)
    gameSocket.sendAction(roomId, { type: 'ce_sync', view: buildGuestView(state, 1) })
  }, [roomId, buildGuestView])

  // ── Process actions ────────────────────────────────────────────

  const processAction = useCallback((action: Record<string, unknown>, fromPlayer: 0 | 1) => {
    const current = gameStateRef.current
    if (!current) return

    switch (action.type) {
      case 'ce_play_card': {
        if (current.phase !== 'playing' || current.currentPlayer !== fromPlayer) return
        const cardIndex = action.cardIndex as number
        const hand = [...current.hands[fromPlayer]]
        const card = hand[cardIndex]
        if (!card) return
        const topCard = current.discardPile[current.discardPile.length - 1]
        if (!canPlayCard(card, topCard, current.currentSuit)) return

        hand.splice(cardIndex, 1)
        const hands = current.hands.map((h, i) => i === fromPlayer ? hand : [...h]) as Card[][]
        const discardPile = [...current.discardPile, card]

        // Empty hand => round won
        if (hand.length === 0) {
          broadcastAndSet(scoreRound({ ...current, hands, discardPile }, fromPlayer))
          return
        }

        // 8 played => choose suit
        if (card.rank === 8) {
          broadcastAndSet({
            ...current,
            hands,
            discardPile,
            phase: 'choosingSuit',
            suitChooser: fromPlayer,
            message: 'Choose a suit',
          })
          return
        }

        // Normal play => advance turn
        const nextPlayer: 0 | 1 = fromPlayer === 0 ? 1 : 0
        broadcastAndSet({
          ...current,
          hands,
          discardPile,
          currentPlayer: nextPlayer,
          currentSuit: card.suit,
          phase: 'playing',
          suitChooser: null,
          message: 'Play a card or draw',
        })
        break
      }
      case 'ce_draw_card': {
        if (current.phase !== 'playing' || current.currentPlayer !== fromPlayer) return
        let drawPile = reshuffleDrawPile(current)

        if (drawPile.length === 0) {
          // No cards to draw — pass turn
          const nextPlayer: 0 | 1 = fromPlayer === 0 ? 1 : 0
          broadcastAndSet({
            ...current,
            drawPile: [],
            discardPile: [current.discardPile[current.discardPile.length - 1]],
            currentPlayer: nextPlayer,
            phase: 'playing',
            message: 'No cards to draw. Turn passes.',
          })
          return
        }

        const card = drawPile.pop()!
        const hands = current.hands.map((h, i) =>
          i === fromPlayer ? [...h, { ...card, faceUp: true }] : [...h]
        ) as Card[][]

        // Update discard pile if reshuffle happened
        const discardPile = drawPile !== current.drawPile && current.drawPile.length === 0
          ? [current.discardPile[current.discardPile.length - 1]]
          : [...current.discardPile]

        broadcastAndSet({
          ...current,
          hands,
          drawPile,
          discardPile,
          phase: 'playing',
          message: 'Drew a card.',
        })
        break
      }
      case 'ce_choose_suit': {
        if (current.phase !== 'choosingSuit' || current.suitChooser !== fromPlayer) return
        const suit = action.suit as Suit
        const nextPlayer: 0 | 1 = fromPlayer === 0 ? 1 : 0
        broadcastAndSet({
          ...current,
          currentSuit: suit,
          currentPlayer: nextPlayer,
          phase: 'playing',
          suitChooser: null,
          message: 'Play a card or draw',
        })
        break
      }
      case 'ce_new_round': {
        if (current.phase !== 'roundOver') return
        const fresh = createGame()
        broadcastAndSet({ ...fresh, scores: current.scores })
        break
      }
    }
  }, [broadcastAndSet])

  // ── Send action ────────────────────────────────────────────────

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

      if (action.type === 'ce_sync' && !isHost) {
        setGuestView(action.view)
        return
      }

      if (isHost && action.type?.startsWith('ce_') && action.type !== 'ce_sync') {
        const fromPlayer: 0 | 1 = msg.playerId === players[0] ? 0 : 1
        processAction(action, fromPlayer)
      }
    })
    return unsub
  }, [roomId, isHost, players, processAction])

  // ── Derive view ────────────────────────────────────────────────

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
  const topDiscard = view.discardPile[view.discardPile.length - 1]
  const canChooseSuit = view.phase === 'choosingSuit' && view.suitChooser === myPlayerIndex
  const playable = view.phase === 'playing' && isMyTurn && topDiscard
    ? getPlayableIndices(view.myHand, topDiscard, view.currentSuit)
    : []

  const gameOver = view.phase === 'gameOver'
  const iWon = gameOver && view.scores[myPlayerIndex] >= view.targetScore

  // ── Handlers ───────────────────────────────────────────────────

  const handlePlay = useCallback((cardIdx: number) => {
    sfx.play('place')
    sendAction({ type: 'ce_play_card', cardIndex: cardIdx })
  }, [sfx, sendAction])

  const handleDraw = useCallback(() => {
    sfx.play('flip')
    sendAction({ type: 'ce_draw_card' })
  }, [sfx, sendAction])

  const handleChooseSuit = useCallback((suit: Suit) => {
    sfx.play('place')
    sendAction({ type: 'ce_choose_suit', suit })
  }, [sfx, sendAction])

  const handleNewRound = useCallback(() => {
    sendAction({ type: 'ce_new_round' })
  }, [sendAction])

  // ── Turn label ─────────────────────────────────────────────────

  const turnLabel = canChooseSuit
    ? 'Choose a suit'
    : isMyTurn
      ? 'Your turn — play a card or draw'
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
        <span className={`font-bold ${view.currentSuit === 'hearts' || view.currentSuit === 'diamonds' ? 'text-red-400' : 'text-white'}`}>
          {getSuitSymbol(view.currentSuit)}
        </span>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  // ── Render ─────────────────────────────────────────────────────

  return (
    <GameLayout title="Crazy Eights — VS" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-4">
        {/* Opponent hand (card backs) */}
        <div className="text-center">
          <span className="text-xs text-slate-400">{opponentName} ({view.opponentHandCount} cards)</span>
          <div className="flex gap-0.5 justify-center mt-1">
            {Array.from({ length: Math.min(view.opponentHandCount, 7) }).map((_, j) => (
              <div key={j} className="w-6 h-9">
                <CardBack />
              </div>
            ))}
            {view.opponentHandCount > 7 && (
              <span className="text-xs text-slate-500 self-center ml-1">+{view.opponentHandCount - 7}</span>
            )}
          </div>
        </div>

        {/* Draw pile + Discard pile */}
        <div className="flex gap-4 items-center justify-center">
          <div
            className={`${CARD_SIZE} ${isMyTurn && view.phase === 'playing' ? 'cursor-pointer' : ''}`}
            onClick={isMyTurn && view.phase === 'playing' ? handleDraw : undefined}
          >
            {view.drawPileCount > 0 ? (
              <CardBack />
            ) : (
              <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">
                Empty
              </div>
            )}
          </div>
          <div className={CARD_SIZE}>
            {topDiscard && <CardFace card={topDiscard} />}
          </div>
          <span className="text-xs text-slate-500">{view.drawPileCount} left</span>
        </div>

        {/* Turn indicator */}
        {view.phase !== 'roundOver' && view.phase !== 'gameOver' && (
          <div className={`text-center py-1.5 px-4 rounded-lg text-xs font-medium ${
            isMyTurn || canChooseSuit
              ? 'bg-emerald-900/40 border border-emerald-700/50 text-emerald-300'
              : 'bg-amber-900/40 border border-amber-700/50 text-amber-300'
          }`}>
            {turnLabel}
          </div>
        )}

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{view.message}</p>

        {/* Suit picker */}
        {canChooseSuit && (
          <div className="flex gap-3 justify-center">
            {SUITS.map(suit => (
              <button
                key={suit}
                onClick={() => handleChooseSuit(suit)}
                className={`w-12 h-12 rounded-lg border-2 text-2xl flex items-center justify-center transition-colors ${
                  suit === 'hearts' || suit === 'diamonds'
                    ? 'border-red-500 hover:bg-red-500/20 text-red-400'
                    : 'border-slate-400 hover:bg-slate-600/40 text-white'
                }`}
              >
                {getSuitSymbol(suit)}
              </button>
            ))}
          </div>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1.5 justify-center max-w-md">
          {view.myHand.map((card, i) => {
            const isPlayable = playable.includes(i)
            return (
              <div
                key={i}
                className={`${CARD_SIZE} transition-transform ${
                  isPlayable ? 'cursor-pointer hover:-translate-y-1' : view.phase === 'playing' && isMyTurn ? 'opacity-50' : ''
                }`}
                onClick={() => isPlayable && handlePlay(i)}
              >
                <CardFace card={card} />
              </div>
            )
          })}
        </div>

        {/* Round over */}
        {view.phase === 'roundOver' && (
          <button
            onClick={handleNewRound}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Next Round
          </button>
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
