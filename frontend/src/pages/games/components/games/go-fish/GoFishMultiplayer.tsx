/**
 * Go Fish VS — two human players over WebSocket.
 *
 * Host-authoritative: host runs the engine, broadcasts state.
 * Each player sees their own hand face-up and opponent's hand face-down.
 * Ask for ranks, collect books of four.
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
  getRankDisplay,
  type Card,
} from '../../../utils/cardUtils'

// ── Types ────────────────────────────────────────────────────────────

type Phase = 'playing' | 'goFish' | 'gameOver'

interface GoFishVsState {
  hands: Card[][]         // [0] = host, [1] = guest
  books: number[][]       // [0] = host books (rank numbers), [1] = guest books
  pond: Card[]
  phase: Phase
  currentPlayer: 0 | 1
  message: string
  lastAskedRank: number | null
}

interface GuestViewState {
  myHand: Card[]
  opponentHandCount: number
  myBooks: number[]
  opponentBooks: number[]
  pondCount: number
  phase: Phase
  currentPlayer: 0 | 1
  message: string
  lastAskedRank: number | null
  /** Whether this player must "Go Fish" (draw) */
  mustFish: boolean
}

// ── Engine logic (inline) ────────────────────────────────────────────

function createGame(): GoFishVsState {
  const deck = shuffleDeck(createDeck())
  const hand0 = deck.slice(0, 7).map(c => ({ ...c, faceUp: true }))
  const hand1 = deck.slice(7, 14).map(c => ({ ...c, faceUp: true }))
  const pond = deck.slice(14)

  return {
    hands: [hand0, hand1],
    books: [[], []],
    pond,
    phase: 'playing',
    currentPlayer: 0,
    message: 'Your turn — tap a card to ask for that rank.',
    lastAskedRank: null,
  }
}

function checkForBooks(hand: Card[]): { hand: Card[]; newBooks: number[] } {
  const counts = new Map<number, number>()
  for (const c of hand) counts.set(c.rank, (counts.get(c.rank) ?? 0) + 1)
  const newBooks: number[] = []
  for (const [rank, count] of counts) {
    if (count >= 4) newBooks.push(rank)
  }
  if (newBooks.length === 0) return { hand, newBooks: [] }
  return { hand: hand.filter(c => !newBooks.includes(c.rank)), newBooks }
}

function applyBookCheck(state: GoFishVsState, player: number): GoFishVsState {
  const { hand, newBooks } = checkForBooks(state.hands[player])
  if (newBooks.length === 0) return state
  const hands = state.hands.map((h, i) => (i === player ? hand : h))
  const books = state.books.map((b, i) => (i === player ? [...b, ...newBooks] : b))
  const next: GoFishVsState = { ...state, hands, books }
  if (isGameOver(next)) {
    return { ...next, phase: 'gameOver', message: gameOverMessage(next) }
  }
  return next
}

function isGameOver(state: GoFishVsState): boolean {
  const totalBooks = state.books[0].length + state.books[1].length
  if (totalBooks >= 13) return true
  if (state.pond.length === 0 && (state.hands[0].length === 0 || state.hands[1].length === 0)) return true
  return false
}

function gameOverMessage(state: GoFishVsState): string {
  const p0 = state.books[0].length
  const p1 = state.books[1].length
  if (p0 > p1) return `Player 1 wins with ${p0} books to ${p1}!`
  if (p1 > p0) return `Player 2 wins with ${p1} books to ${p0}.`
  return `It's a tie — ${p0} books each!`
}

function getAskableRanks(hand: Card[]): number[] {
  const seen = new Set<number>()
  for (const c of hand) seen.add(c.rank)
  return Array.from(seen)
}

/** Refill hand if empty and pond has cards */
function refillIfEmpty(state: GoFishVsState, player: number): GoFishVsState {
  if (state.hands[player].length === 0 && state.pond.length > 0 && state.phase !== 'gameOver') {
    const drawn = { ...state.pond[0], faceUp: true }
    const hands = state.hands.map((h, i) => (i === player ? [drawn] : h))
    const pond = state.pond.slice(1)
    let next = { ...state, hands, pond }
    next = applyBookCheck(next, player)
    return next
  }
  return state
}

// ── Props ────────────────────────────────────────────────────────────

interface Props {
  roomId: string
  players: number[]
  playerNames: Record<number, string>
  onLeave?: () => void
}

// ── Component ────────────────────────────────────────────────────────

export function GoFishMultiplayer({ roomId, players, playerNames, onLeave }: Props) {
  const { user } = useAuth()

  const song = useMemo(() => getSongForGame('go-fish'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('go-fish')

  const isHost = players[0] === user?.id
  const myPlayerIndex: 0 | 1 = isHost ? 0 : 1
  const myName = playerNames[user?.id ?? 0] ?? 'You'
  const opponentId = players.find(id => id !== user?.id)
  const opponentName = opponentId ? (playerNames[opponentId] ?? 'Opponent') : 'Opponent'

  const [gameState, setGameState] = useState<GoFishVsState | null>(null)
  const gameStateRef = useRef<GoFishVsState | null>(null)
  useEffect(() => { gameStateRef.current = gameState }, [gameState])

  const [guestView, setGuestView] = useState<GuestViewState | null>(null)

  // ── Build guest view ────────────────────────────────────────────

  const buildGuestView = useCallback((state: GoFishVsState, forPlayer: 0 | 1): GuestViewState => {
    const opponent = forPlayer === 0 ? 1 : 0
    return {
      myHand: state.hands[forPlayer],
      opponentHandCount: state.hands[opponent].length,
      myBooks: state.books[forPlayer],
      opponentBooks: state.books[opponent],
      pondCount: state.pond.length,
      phase: state.phase,
      currentPlayer: state.currentPlayer,
      message: state.message,
      lastAskedRank: state.lastAskedRank,
      mustFish: state.phase === 'goFish' && state.currentPlayer === forPlayer,
    }
  }, [])

  // ── Host: create game ──────────────────────────────────────────

  useEffect(() => {
    if (!isHost) return
    const state = createGame()
    setGameState(state)
    gameSocket.sendAction(roomId, { type: 'gf_sync', view: buildGuestView(state, 1) })
  }, [isHost, roomId, buildGuestView])

  const broadcastAndSet = useCallback((state: GoFishVsState) => {
    setGameState(state)
    gameSocket.sendAction(roomId, { type: 'gf_sync', view: buildGuestView(state, 1) })
  }, [roomId, buildGuestView])

  // ── Process actions ────────────────────────────────────────────

  const processAction = useCallback((action: Record<string, unknown>, fromPlayer: 0 | 1) => {
    const current = gameStateRef.current
    if (!current) return

    switch (action.type) {
      case 'gf_ask_rank': {
        if (current.phase !== 'playing' || current.currentPlayer !== fromPlayer) return
        const rank = action.rank as number
        // Verify the asking player holds the rank
        if (!current.hands[fromPlayer].some(c => c.rank === rank)) return

        const opponent: 0 | 1 = fromPlayer === 0 ? 1 : 0
        const rankName = getRankDisplay(rank)
        const opMatches = current.hands[opponent].filter(c => c.rank === rank)

        if (opMatches.length > 0) {
          // Transfer cards
          const transferred = opMatches.map(c => ({ ...c, faceUp: true }))
          const newAskerHand = [...current.hands[fromPlayer], ...transferred]
          const newOpponentHand = current.hands[opponent].filter(c => c.rank !== rank)
          const hands = current.hands.map((h, i) =>
            i === fromPlayer ? newAskerHand : i === opponent ? newOpponentHand : h
          )
          let next: GoFishVsState = {
            ...current,
            hands,
            phase: 'playing',
            currentPlayer: fromPlayer,
            message: `Got ${opMatches.length} ${rankName}${opMatches.length > 1 ? 's' : ''}! Go again.`,
            lastAskedRank: null,
          }
          next = applyBookCheck(next, fromPlayer)
          if (next.phase !== 'gameOver') {
            next = refillIfEmpty(next, fromPlayer)
          }
          if (next.phase !== 'gameOver' && next.hands[fromPlayer].length === 0) {
            // No cards, pass turn
            const nextPlayer: 0 | 1 = fromPlayer === 0 ? 1 : 0
            next = { ...next, phase: 'playing', currentPlayer: nextPlayer, message: 'No cards left. Turn passes.' }
            next = refillIfEmpty(next, nextPlayer)
          }
          if (isGameOver(next) && next.phase !== 'gameOver') {
            next = { ...next, phase: 'gameOver', message: gameOverMessage(next) }
          }
          broadcastAndSet(next)
        } else {
          // Go Fish!
          broadcastAndSet({
            ...current,
            phase: 'goFish',
            lastAskedRank: rank,
            message: `Go Fish! No ${rankName}s.`,
          })
        }
        break
      }
      case 'gf_go_fish': {
        if (current.phase !== 'goFish' || current.currentPlayer !== fromPlayer) return

        if (current.pond.length === 0) {
          if (isGameOver(current)) {
            broadcastAndSet({ ...current, phase: 'gameOver', message: gameOverMessage(current) })
          } else {
            const nextPlayer: 0 | 1 = fromPlayer === 0 ? 1 : 0
            broadcastAndSet({
              ...current,
              phase: 'playing',
              currentPlayer: nextPlayer,
              message: 'Pond is empty! Turn passes.',
              lastAskedRank: null,
            })
          }
          return
        }

        const drawnCard = { ...current.pond[0], faceUp: true }
        const newPond = current.pond.slice(1)
        const hands = current.hands.map((h, i) =>
          i === fromPlayer ? [...h, drawnCard] : [...h]
        )
        const matchedAsk = drawnCard.rank === current.lastAskedRank

        let next: GoFishVsState = { ...current, hands, pond: newPond, lastAskedRank: null }
        next = applyBookCheck(next, fromPlayer)

        if (next.phase === 'gameOver') {
          broadcastAndSet(next)
          return
        }

        if (matchedAsk) {
          // Lucky draw — same player goes again
          next = { ...next, phase: 'playing', currentPlayer: fromPlayer, message: `Drew ${getRankDisplay(drawnCard.rank)} — go again!` }
        } else {
          const nextPlayer: 0 | 1 = fromPlayer === 0 ? 1 : 0
          next = { ...next, phase: 'playing', currentPlayer: nextPlayer, message: `Drew a card. Turn passes.` }
        }

        // Handle empty hand
        next = refillIfEmpty(next, next.currentPlayer)
        if (isGameOver(next) && next.phase !== 'gameOver') {
          next = { ...next, phase: 'gameOver', message: gameOverMessage(next) }
        }

        broadcastAndSet(next)
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

      if (action.type === 'gf_sync' && !isHost) {
        setGuestView(action.view)
        return
      }

      if (isHost && action.type?.startsWith('gf_') && action.type !== 'gf_sync') {
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
  const askable = view.phase === 'playing' && isMyTurn ? getAskableRanks(view.myHand) : []
  const mustFish = view.mustFish

  const gameOver = view.phase === 'gameOver'
  const iWon = gameOver && view.myBooks.length > view.opponentBooks.length
  const isTie = gameOver && view.myBooks.length === view.opponentBooks.length

  // ── Handlers ───────────────────────────────────────────────────

  const handleAsk = useCallback((rank: number) => {
    sfx.play('place')
    sendAction({ type: 'gf_ask_rank', rank })
  }, [sfx, sendAction])

  const handleGoFish = useCallback(() => {
    sfx.play('flip')
    sendAction({ type: 'gf_go_fish' })
  }, [sfx, sendAction])

  // ── Turn label ─────────────────────────────────────────────────

  const turnLabel = mustFish
    ? 'Go Fish! Draw from the pond.'
    : isMyTurn
      ? 'Your turn — tap a card to ask for that rank'
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
        <span className="text-white">{myName}: {view.myBooks.length} books</span>
        <span className="text-slate-400">{opponentName}: {view.opponentBooks.length} books</span>
        <span className="text-slate-400">Pond: {view.pondCount}</span>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  // ── Render ─────────────────────────────────────────────────────

  return (
    <GameLayout title="Go Fish — VS" controls={controls}>
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
          {view.opponentBooks.length > 0 && (
            <div className="text-xs text-slate-400 mt-1">
              Books: {view.opponentBooks.map(r => getRankDisplay(r)).join(', ')}
            </div>
          )}
        </div>

        {/* Pond */}
        <div className="flex gap-3 items-center justify-center">
          <div
            className={`${CARD_SIZE} ${mustFish ? 'cursor-pointer ring-2 ring-blue-400/50 rounded-md' : ''}`}
            onClick={mustFish ? handleGoFish : undefined}
          >
            {view.pondCount > 0 ? (
              <CardBack />
            ) : (
              <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">
                Empty
              </div>
            )}
          </div>
          <span className="text-xs text-slate-500">{view.pondCount} left</span>
        </div>

        {/* Turn indicator */}
        {view.phase !== 'gameOver' && (
          <div className={`text-center py-1.5 px-4 rounded-lg text-xs font-medium ${
            isMyTurn || mustFish
              ? 'bg-emerald-900/40 border border-emerald-700/50 text-emerald-300'
              : 'bg-amber-900/40 border border-amber-700/50 text-amber-300'
          }`}>
            {turnLabel}
          </div>
        )}

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{view.message}</p>

        {/* Go Fish button */}
        {mustFish && view.pondCount > 0 && (
          <button
            onClick={handleGoFish}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Go Fish!
          </button>
        )}

        {/* Player books */}
        {view.myBooks.length > 0 && (
          <div className="text-xs text-emerald-400">
            Your Books: {view.myBooks.map(r => getRankDisplay(r)).join(', ')}
          </div>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1.5 justify-center max-w-md">
          {view.myHand.map((card, i) => {
            const isAskable = askable.includes(card.rank)
            return (
              <div
                key={i}
                className={`${CARD_SIZE} transition-transform ${
                  isAskable ? 'cursor-pointer hover:-translate-y-1' : 'opacity-60'
                }`}
                onClick={() => isAskable && handleAsk(card.rank)}
              >
                <CardFace card={card} />
              </div>
            )
          })}
        </div>

        {/* Game over */}
        {gameOver && (
          <GameOverModal
            status={isTie ? 'draw' : iWon ? 'won' : 'lost'}
            score={view.myBooks.length}
            message={`${myName}: ${view.myBooks.length} books — ${opponentName}: ${view.opponentBooks.length} books`}
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
