/**
 * War VS — two human players compete head-to-head.
 *
 * Host-authoritative: host runs the game engine, broadcasts state.
 * Both flip simultaneously, higher card wins. On tie: war.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { Wifi } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE } from '../../PlayingCard'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'
import { createDeck, shuffleDeck, type Card } from '../../../utils/cardUtils'

// ── Types ───────────────────────────────────────────────────────────

type VsPhase = 'ready' | 'compare' | 'war' | 'gameOver'

interface VsWarState {
  decks: [Card[], Card[]]           // [0] = player 0, [1] = player 1
  flippedCards: [Card | null, Card | null]
  warPile: Card[]
  phase: VsPhase
  message: string
  round: number
  maxRounds: number
  flipped: [boolean, boolean]       // who has pressed flip this round
}

// ── Sync state: strip hidden info for guest ─────────────────────────

interface GuestViewState {
  deckCounts: [number, number]
  flippedCards: [Card | null, Card | null]
  warPile: number
  phase: VsPhase
  message: string
  round: number
  maxRounds: number
  flipped: [boolean, boolean]
}

function toGuestView(state: VsWarState): GuestViewState {
  return {
    deckCounts: [state.decks[0].length, state.decks[1].length],
    flippedCards: state.flippedCards,
    warPile: state.warPile.length,
    phase: state.phase,
    message: state.message,
    round: state.round,
    maxRounds: state.maxRounds,
    flipped: state.flipped,
  }
}

// ── Engine functions (inline, pure) ─────────────────────────────────

function getCompareValue(card: Card): number {
  return card.rank === 1 ? 14 : card.rank
}

function createVsWarGame(): VsWarState {
  const deck = shuffleDeck(createDeck())
  return {
    decks: [deck.slice(0, 26), deck.slice(26)],
    flippedCards: [null, null],
    warPile: [],
    phase: 'ready',
    message: 'Both players flip to start!',
    round: 0,
    maxRounds: 200,
    flipped: [false, false],
  }
}

/** Both players have flipped — reveal cards and enter compare. */
function flipBoth(state: VsWarState): VsWarState {
  const d0 = [...state.decks[0]]
  const d1 = [...state.decks[1]]

  if (d0.length === 0 || d1.length === 0) {
    return checkGameOver(state)
  }

  const c0 = { ...d0.shift()!, faceUp: true }
  const c1 = { ...d1.shift()!, faceUp: true }

  return {
    ...state,
    decks: [d0, d1],
    flippedCards: [c0, c1],
    phase: 'compare',
    round: state.round + 1,
    message: 'Compare cards!',
    flipped: [false, false],
  }
}

function resolveCompare(state: VsWarState): VsWarState {
  if (state.phase !== 'compare') return state
  const [c0, c1] = state.flippedCards
  if (!c0 || !c1) return state

  const v0 = getCompareValue(c0)
  const v1 = getCompareValue(c1)

  if (v0 === v1) {
    return { ...state, phase: 'war', message: 'War! Cards are tied!' }
  }

  const cardsWon = [c0, c1, ...state.warPile]
  const p0wins = v0 > v1

  const next: VsWarState = {
    ...state,
    decks: [
      p0wins ? [...state.decks[0], ...cardsWon] : [...state.decks[0]],
      p0wins ? [...state.decks[1]] : [...state.decks[1], ...cardsWon],
    ],
    flippedCards: [null, null],
    warPile: [],
    phase: 'ready',
    flipped: [false, false],
    message: p0wins
      ? `Player 1 wins! (+${cardsWon.length} cards)`
      : `Player 2 wins! (+${cardsWon.length} cards)`,
  }

  return checkGameOver(next)
}

function resolveWar(state: VsWarState): VsWarState {
  if (state.phase !== 'war') return state
  const [c0, c1] = state.flippedCards
  if (!c0 || !c1) return state

  const d0 = [...state.decks[0]]
  const d1 = [...state.decks[1]]
  let warPile = [c0, c1, ...state.warPile]

  while (true) {
    if (d0.length < 4) {
      return {
        ...state,
        decks: [[], [...d1, ...warPile, ...d0]],
        flippedCards: [null, null],
        warPile: [],
        phase: 'gameOver',
        message: 'Player 2 wins — Player 1 couldn\'t complete the war!',
        flipped: [false, false],
      }
    }
    if (d1.length < 4) {
      return {
        ...state,
        decks: [[...d0, ...warPile, ...d1], []],
        flippedCards: [null, null],
        warPile: [],
        phase: 'gameOver',
        message: 'Player 1 wins — Player 2 couldn\'t complete the war!',
        flipped: [false, false],
      }
    }

    const faceDown0 = d0.splice(0, 3)
    const faceDown1 = d1.splice(0, 3)
    warPile.push(...faceDown0, ...faceDown1)

    const wc0 = { ...d0.shift()!, faceUp: true }
    const wc1 = { ...d1.shift()!, faceUp: true }

    const wv0 = getCompareValue(wc0)
    const wv1 = getCompareValue(wc1)

    if (wv0 === wv1) {
      warPile.push(wc0, wc1)
      continue
    }

    const allCards = [...warPile, wc0, wc1]
    const p0wins = wv0 > wv1

    const next: VsWarState = {
      ...state,
      decks: [
        p0wins ? [...d0, ...allCards] : [...d0],
        p0wins ? [...d1] : [...d1, ...allCards],
      ],
      flippedCards: [null, null],
      warPile: [],
      phase: 'ready',
      flipped: [false, false],
      message: p0wins
        ? `Player 1 wins the war! (+${allCards.length} cards)`
        : `Player 2 wins the war! (+${allCards.length} cards)`,
    }

    return checkGameOver(next)
  }
}

function checkGameOver(state: VsWarState): VsWarState {
  const [d0, d1] = state.decks
  if (d0.length === 0 && state.flippedCards[0] === null) {
    return { ...state, phase: 'gameOver', message: 'Player 2 wins — Player 1 ran out of cards!' }
  }
  if (d1.length === 0 && state.flippedCards[1] === null) {
    return { ...state, phase: 'gameOver', message: 'Player 1 wins — Player 2 ran out of cards!' }
  }
  if (state.round >= state.maxRounds) {
    if (d0.length > d1.length) return { ...state, phase: 'gameOver', message: `Player 1 wins ${d0.length}-${d1.length}!` }
    if (d1.length > d0.length) return { ...state, phase: 'gameOver', message: `Player 2 wins ${d1.length}-${d0.length}!` }
    return { ...state, phase: 'gameOver', message: `Draw! Both have ${d0.length} cards.` }
  }
  return state
}

// ── Component ────────────────────────────────────────────────────────

interface Props {
  roomId: string
  players: number[]
  playerNames: Record<number, string>
  onLeave?: () => void
}

export function WarMultiplayer({ roomId, players, playerNames, onLeave }: Props) {
  const { user } = useAuth()
  const isHost = players[0] === user?.id
  const myIdx = isHost ? 0 : 1

  const myName = playerNames[players[myIdx]] ?? (myIdx === 0 ? 'Player 1' : 'Player 2')
  const oppName = playerNames[players[myIdx === 0 ? 1 : 0]] ?? (myIdx === 0 ? 'Player 2' : 'Player 1')

  const [gameState, setGameState] = useState<VsWarState>(() => createVsWarGame())
  const stateRef = useRef(gameState)
  stateRef.current = gameState

  // Guest-side view (deck counts, not full decks)
  const [guestView, setGuestView] = useState<GuestViewState | null>(null)

  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')

  const song = useMemo(() => getSongForGame('war'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('war')

  // ── Host: broadcast state after every change ─────────────────────

  const broadcastState = useCallback((state: VsWarState) => {
    if (!isHost) return
    gameSocket.sendAction(roomId, {
      type: 'state_sync',
      state: toGuestView(state),
    })
  }, [isHost, roomId])

  // ── Flip action ──────────────────────────────────────────────────

  const handleFlip = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('flip')

    if (isHost) {
      setGameState(prev => {
        const flipped: [boolean, boolean] = [true, prev.flipped[1]]
        if (flipped[0] && flipped[1]) {
          const next = flipBoth({ ...prev, flipped })
          broadcastState(next)
          return next
        }
        const waiting = { ...prev, flipped, message: `Waiting for ${oppName} to flip...` }
        broadcastState(waiting)
        return waiting
      })
    } else {
      gameSocket.sendAction(roomId, { type: 'flip' })
    }
  }, [isHost, roomId, broadcastState, music, sfx, oppName])

  // ── WebSocket listener ───────────────────────────────────────────

  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg: { playerId?: number; action?: Record<string, unknown> }) => {
      if (msg.playerId === user?.id) return
      const action = msg.action
      if (!action) return

      if (action.type === 'state_sync') {
        if (!isHost) {
          setGuestView(action.state as GuestViewState)
          const syncedPhase = (action.state as GuestViewState).phase
          if (syncedPhase === 'compare') sfx.play('flip')
        }
        return
      }

      if (isHost) {
        if (action.type === 'flip') {
          sfx.play('flip')
          setGameState(prev => {
            const flipped: [boolean, boolean] = [prev.flipped[0], true]
            if (flipped[0] && flipped[1]) {
              const next = flipBoth({ ...prev, flipped })
              broadcastState(next)
              return next
            }
            const waiting = { ...prev, flipped, message: `Waiting for ${myName} to flip...` }
            broadcastState(waiting)
            return waiting
          })
        }
      }
    })
    return unsub
  }, [roomId, isHost, user?.id, broadcastState, sfx, myName])

  // ── Auto-resolve: compare -> ready/war, war -> ready ─────────────

  useEffect(() => {
    if (!isHost) return
    if (gameState.phase === 'compare') {
      const timer = setTimeout(() => {
        setGameState(prev => {
          const next = resolveCompare(prev)
          if (next.phase === 'ready') sfx.play('win')
          if (next.phase === 'war') sfx.play('deal')
          broadcastState(next)
          return next
        })
      }, 1200)
      return () => clearTimeout(timer)
    }
    if (gameState.phase === 'war') {
      const timer = setTimeout(() => {
        setGameState(prev => {
          const next = resolveWar(prev)
          sfx.play('win')
          broadcastState(next)
          return next
        })
      }, 1500)
      return () => clearTimeout(timer)
    }
  }, [isHost, gameState.phase, gameState.round, broadcastState, sfx])

  // ── Game over detection ──────────────────────────────────────────

  const currentPhase = isHost ? gameState.phase : (guestView?.phase ?? gameState.phase)

  useEffect(() => {
    if (currentPhase !== 'gameOver') return
    const msg = isHost ? gameState.message : (guestView?.message ?? '')
    // Determine if we won based on message containing our player number
    const myPlayerLabel = `Player ${myIdx + 1}`
    if (msg.includes(`${myPlayerLabel} wins`)) {
      setGameStatus('won')
    } else if (msg.includes('Draw')) {
      setGameStatus('draw')
    } else {
      setGameStatus('lost')
    }
  }, [currentPhase, isHost, gameState.message, guestView?.message, myIdx])

  // ── Derived state ────────────────────────────────────────────────

  const myDeckCount = isHost
    ? gameState.decks[myIdx].length
    : (guestView?.deckCounts[myIdx] ?? 26)
  const oppDeckCount = isHost
    ? gameState.decks[myIdx === 0 ? 1 : 0].length
    : (guestView?.deckCounts[myIdx === 0 ? 1 : 0] ?? 26)

  const flippedCards = isHost ? gameState.flippedCards : (guestView?.flippedCards ?? [null, null])
  const myFlipped = flippedCards[myIdx]
  const oppFlipped = flippedCards[myIdx === 0 ? 1 : 0]

  const phase = isHost ? gameState.phase : (guestView?.phase ?? 'ready')
  const message = isHost ? gameState.message : (guestView?.message ?? 'Waiting for host...')
  const round = isHost ? gameState.round : (guestView?.round ?? 0)
  const maxRounds = isHost ? gameState.maxRounds : (guestView?.maxRounds ?? 200)
  const hasFlipped = isHost ? gameState.flipped[myIdx] : (guestView?.flipped[myIdx] ?? false)

  const warPileCount = isHost ? gameState.warPile.length : (guestView?.warPile ?? 0)

  // ── Render ───────────────────────────────────────────────────────

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <Wifi className="w-3.5 h-3.5 text-green-400" />
        <span className="text-xs text-slate-400">VS Mode</span>
        <span className="text-xs text-slate-400">Round {round}/{maxRounds}</span>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="War — VS" controls={controls}>
      <div className="flex flex-col items-center w-full max-w-sm space-y-4">

        {/* Opponent deck */}
        <div className="text-center">
          <span className="text-xs text-slate-400 mb-1 block">
            {oppName} ({oppDeckCount} cards)
          </span>
          <div className="flex justify-center">
            {oppDeckCount > 0 ? (
              <div className={`${CARD_SIZE} relative`}>
                <CardBack />
                {oppDeckCount > 1 && (
                  <div className={`absolute -top-0.5 -left-0.5 ${CARD_SIZE} -z-10`}>
                    <CardBack />
                  </div>
                )}
              </div>
            ) : (
              <div className={`${CARD_SIZE} border border-dashed border-slate-600 rounded-lg`} />
            )}
          </div>
        </div>

        {/* Battle area */}
        <div className="flex items-center gap-6 py-3">
          {/* My flipped card */}
          <div className={CARD_SIZE}>
            {myFlipped ? (
              <CardFace card={myFlipped} />
            ) : (
              <div className="w-full h-full border border-dashed border-slate-600 rounded-lg flex items-center justify-center">
                <span className="text-[0.5rem] text-slate-500">You</span>
              </div>
            )}
          </div>

          {/* War pile indicator */}
          {warPileCount > 0 ? (
            <div className="flex flex-col items-center gap-1">
              <div className="flex gap-0.5">
                {Array.from({ length: Math.min(3, warPileCount) }).map((_, i) => (
                  <div key={i} className="w-6 h-9">
                    <CardBack />
                  </div>
                ))}
              </div>
              <span className="text-[0.6rem] text-amber-400">{warPileCount} cards</span>
            </div>
          ) : (
            <span className="text-lg font-bold text-slate-500">VS</span>
          )}

          {/* Opponent's flipped card */}
          <div className={CARD_SIZE}>
            {oppFlipped ? (
              <CardFace card={oppFlipped} />
            ) : (
              <div className="w-full h-full border border-dashed border-slate-600 rounded-lg flex items-center justify-center">
                <span className="text-[0.5rem] text-slate-500">{oppName}</span>
              </div>
            )}
          </div>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center min-h-[1.25rem]">
          {message}
        </p>

        {/* Flip button */}
        {phase === 'ready' && gameStatus === 'playing' && !hasFlipped && (
          <button
            onClick={handleFlip}
            className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors active:scale-95"
          >
            Flip!
          </button>
        )}

        {phase === 'ready' && gameStatus === 'playing' && hasFlipped && (
          <p className="text-xs text-slate-400">Waiting for {oppName} to flip...</p>
        )}

        {/* My deck */}
        <div className="text-center">
          <div className="flex justify-center">
            {myDeckCount > 0 ? (
              <div className={`${CARD_SIZE} relative`}>
                <CardBack />
                {myDeckCount > 1 && (
                  <div className={`absolute -top-0.5 -left-0.5 ${CARD_SIZE} -z-10`}>
                    <CardBack />
                  </div>
                )}
              </div>
            ) : (
              <div className={`${CARD_SIZE} border border-dashed border-slate-600 rounded-lg`} />
            )}
          </div>
          <span className="text-xs text-blue-400 mt-1 block">
            {myName} ({myDeckCount} cards)
          </span>
        </div>

        {/* Game over modal */}
        {(gameStatus === 'won' || gameStatus === 'lost' || gameStatus === 'draw') && (
          <GameOverModal
            status={gameStatus}
            score={myDeckCount}
            message={
              gameStatus === 'won'
                ? `You win! ${oppName} ran out of cards.`
                : gameStatus === 'lost'
                  ? `${oppName} wins!`
                  : 'Draw!'
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
