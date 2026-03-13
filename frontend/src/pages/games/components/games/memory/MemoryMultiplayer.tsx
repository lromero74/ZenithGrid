/**
 * Memory VS Mode — two human players share one board, taking turns
 * flipping cards. A match scores a point and the player keeps going;
 * a mismatch flips the cards back and switches turns.
 *
 * Host-authoritative: the host processes all flips and broadcasts
 * state to the guest via game:action / state_sync messages.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { Wifi } from 'lucide-react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import {
  flipCard, checkMatch, checkGameComplete, getGridDimensions,
  createSeededDeck,
  type Card, type GridSize,
} from './memoryEngine'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import { gameSocket } from '../../../../../services/gameSocket'
import { useAuth } from '../../../../../contexts/AuthContext'
import { createSeededRandom } from '../../../utils/seededRandom'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function hashString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0
  }
  return hash
}

const GRID_COLS: Record<GridSize, number> = { easy: 4, medium: 4, hard: 6 }

const PLAYER_COLORS = [
  { label: 'text-indigo-400', matchBg: 'bg-indigo-900/30', matchBorder: 'border-indigo-500', dot: 'bg-indigo-400' },
  { label: 'text-amber-400', matchBg: 'bg-amber-900/30', matchBorder: 'border-amber-500', dot: 'bg-amber-400' },
] as const

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface MemoryMultiplayerProps {
  roomId: string
  players: number[]
  playerNames?: Record<number, string>
  difficulty?: string
  onLeave?: () => void
}

export function MemoryMultiplayer({
  roomId, players, playerNames = {}, difficulty = 'easy', onLeave,
}: MemoryMultiplayerProps) {
  const { user } = useAuth()
  const isHost = players[0] === user?.id
  const myIndex: 0 | 1 = isHost ? 0 : 1
  const opponentIndex: 0 | 1 = isHost ? 1 : 0

  const myName = playerNames[user?.id ?? 0] || 'You'
  const opponentId = players.find(id => id !== user?.id)
  const opponentName = opponentId ? (playerNames[opponentId] || 'Opponent') : 'Opponent'

  // Generate identical deck from roomId hash (both clients produce the same result)
  const gridSize = (difficulty || 'easy') as GridSize
  const { pairs } = getGridDimensions(gridSize)
  const cols = GRID_COLS[gridSize] ?? 4
  const initialCards = useMemo(() => {
    const seed = hashString(roomId)
    return createSeededDeck(pairs, createSeededRandom(seed))
  }, [roomId, pairs])

  // Music & SFX
  const song = useMemo(() => getSongForGame('memory'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('memory')

  // Game state
  const [cards, setCards] = useState<Card[]>(initialCards)
  const [currentPlayer, setCurrentPlayer] = useState<0 | 1>(0)
  const [scores, setScores] = useState<[number, number]>([0, 0])
  const [flippedIndices, setFlippedIndices] = useState<number[]>([])
  const [locked, setLocked] = useState(false)
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')

  const isMyTurn = currentPlayer === myIndex

  // Refs for stable closure access in WS listener & processFlip
  const cardsRef = useRef(cards)
  cardsRef.current = cards
  const currentPlayerRef = useRef(currentPlayer)
  currentPlayerRef.current = currentPlayer
  const scoresRef = useRef(scores)
  scoresRef.current = scores
  const flippedRef = useRef(flippedIndices)
  flippedRef.current = flippedIndices
  const lockedRef = useRef(locked)
  lockedRef.current = locked
  const gameStatusRef = useRef(gameStatus)
  gameStatusRef.current = gameStatus

  // ----- Host: broadcast state to guest -----
  const broadcastState = useCallback(
    (c: Card[], cp: number, sc: [number, number], fi: number[], lk: boolean) => {
      if (!isHost) return
      gameSocket.sendAction(roomId, {
        type: 'state_sync',
        state: { cards: c, currentPlayer: cp, scores: sc, flippedIndices: fi, locked: lk },
      })
    },
    [isHost, roomId],
  )

  // ----- Host: process a flip (from either player) -----
  // Helper: update both React state AND ref synchronously to prevent
  // stale reads from rapid successive calls before React renders.
  const updateCards = useCallback((c: Card[]) => { cardsRef.current = c; setCards(c) }, [])
  const updateFlipped = useCallback((f: number[]) => { flippedRef.current = f; setFlippedIndices(f) }, [])
  const updateLocked = useCallback((l: boolean) => { lockedRef.current = l; setLocked(l) }, [])
  const updateScores = useCallback((s: [number, number]) => { scoresRef.current = s; setScores(s) }, [])
  const updateCurrentPlayer = useCallback((p: 0 | 1) => { currentPlayerRef.current = p; setCurrentPlayer(p) }, [])

  const processFlip = useCallback(
    (index: number) => {
      if (lockedRef.current) return
      if (gameStatusRef.current !== 'playing') return
      const card = cardsRef.current[index]
      if (card.matched || card.flipped) return

      sfx.play('flip')
      const newCards = flipCard(cardsRef.current, index)
      const newFlipped = [...flippedRef.current, index]
      updateCards(newCards)
      updateFlipped(newFlipped)

      if (newFlipped.length === 2) {
        updateLocked(true)
        const [first, second] = newFlipped
        if (checkMatch(newCards[first], newCards[second])) {
          // Match — score +1, same player continues
          sfx.play('match')
          const matched = newCards.map((c, i) =>
            i === first || i === second
              ? { ...c, matched: true, matchedBy: currentPlayerRef.current }
              : c,
          )
          const newScores: [number, number] = [...scoresRef.current]
          newScores[currentPlayerRef.current]++
          updateCards(matched)
          updateScores(newScores)
          updateFlipped([])
          updateLocked(false)
          broadcastState(matched, currentPlayerRef.current, newScores, [], false)

          if (checkGameComplete(matched)) {
            if (newScores[myIndex] > newScores[opponentIndex]) setGameStatus('won')
            else if (newScores[myIndex] < newScores[opponentIndex]) setGameStatus('lost')
            else setGameStatus('draw')
          }
        } else {
          // No match — show both cards for 800ms, then flip back & switch turn
          sfx.play('mismatch')
          broadcastState(newCards, currentPlayerRef.current, scoresRef.current, newFlipped, true)
          setTimeout(() => {
            const flippedBack = newCards.map((c, i) =>
              i === first || i === second ? { ...c, flipped: false } : c,
            )
            const nextPlayer: 0 | 1 = currentPlayerRef.current === 0 ? 1 : 0
            updateCards(flippedBack)
            updateCurrentPlayer(nextPlayer)
            updateFlipped([])
            updateLocked(false)
            broadcastState(flippedBack, nextPlayer, scoresRef.current, [], false)
          }, 800)
        }
      } else {
        // First card — broadcast immediately so opponent sees it
        broadcastState(newCards, currentPlayerRef.current, scoresRef.current, newFlipped, false)
      }
    },
    [broadcastState, sfx, myIndex, opponentIndex, updateCards, updateFlipped, updateLocked, updateScores, updateCurrentPlayer],
  )

  // ----- Click handler -----
  const handleCardClick = useCallback(
    (index: number) => {
      if (gameStatus !== 'playing') return
      if (lockedRef.current) return
      if (!isMyTurn) return
      const card = cardsRef.current[index]
      if (card.matched || card.flipped) return

      music.init()
      sfx.init()
      music.start()

      if (isHost) {
        processFlip(index)
      } else {
        // Guest sends intent to host
        gameSocket.sendAction(roomId, { type: 'flip', index })
      }
    },
    [gameStatus, isHost, isMyTurn, processFlip, roomId, music, sfx],
  )

  // ----- WS listener -----
  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg: any) => {
      if (msg.playerId === user?.id) return
      const action = msg.action
      if (!action) return

      if (action.type === 'flip' && isHost) {
        // Guest sent a flip — process it on host
        processFlip(action.index as number)
      } else if (action.type === 'state_sync' && !isHost) {
        // Guest receives authoritative state
        const s = action.state
        setCards(s.cards)
        setCurrentPlayer(s.currentPlayer as 0 | 1)
        setScores(s.scores as [number, number])
        setFlippedIndices(s.flippedIndices)
        setLocked(s.locked)

        // Play SFX based on state changes
        if (s.flippedIndices.length === 1 && flippedRef.current.length === 0) {
          sfx.play('flip')
        } else if (s.flippedIndices.length === 2 && flippedRef.current.length === 1) {
          sfx.play('flip')
          // Check if it was a match (cards are already marked matched)
          const [first, second] = s.flippedIndices
          if (s.cards[first].matched && s.cards[second].matched) {
            sfx.play('match')
          }
        } else if (s.flippedIndices.length === 0 && flippedRef.current.length === 2) {
          // Cards flipped back (mismatch resolved) or match cleared
          const prevFirst = flippedRef.current[0]
          if (!s.cards[prevFirst].matched) {
            sfx.play('mismatch')
          }
        }

        if (checkGameComplete(s.cards)) {
          const sc = s.scores as [number, number]
          if (sc[myIndex] > sc[opponentIndex]) setGameStatus('won')
          else if (sc[myIndex] < sc[opponentIndex]) setGameStatus('lost')
          else setGameStatus('draw')
        }
      } else if (action.type === 'request_sync' && isHost) {
        // Reconnecting guest requests state
        broadcastState(
          cardsRef.current, currentPlayerRef.current,
          scoresRef.current, flippedRef.current, lockedRef.current,
        )
      }
    })
    return unsub
  }, [roomId, isHost, user?.id, processFlip, broadcastState, sfx, myIndex, opponentIndex])

  // ----- Render -----
  const turnLabel = isMyTurn ? 'Your turn' : `${opponentName}'s turn`
  const myColor = PLAYER_COLORS[myIndex]
  const oppColor = PLAYER_COLORS[opponentIndex]

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          <Wifi className="w-3.5 h-3.5 text-green-400" />
          <span className="text-xs text-slate-400">VS</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${myColor.dot} ${isMyTurn ? 'animate-pulse' : 'opacity-50'}`} />
          <span className={`text-xs font-medium ${myColor.label}`}>{myName}: {scores[myIndex]}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${oppColor.dot} ${!isMyTurn ? 'animate-pulse' : 'opacity-50'}`} />
          <span className={`text-xs font-medium ${oppColor.label}`}>{opponentName}: {scores[opponentIndex]}</span>
        </div>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Memory — VS" controls={controls}>
      <div className="relative">
        {/* Turn indicator */}
        <p className={`text-center text-sm mb-3 font-medium ${isMyTurn ? myColor.label : oppColor.label}`}>
          {gameStatus === 'playing' ? turnLabel : ''}
        </p>

        {/* Card grid */}
        <div
          className="grid gap-2 mx-auto"
          style={{ gridTemplateColumns: `repeat(${cols}, 1fr)`, maxWidth: cols * 88 }}
        >
          {cards.map((card, index) => {
            const isRevealed = card.flipped || card.matched
            const canClick = gameStatus === 'playing' && isMyTurn && !locked && !card.matched && !card.flipped
            const matchColor = card.matched
              ? (card.matchedBy === myIndex ? myColor : oppColor)
              : null

            return (
              <div
                key={card.id}
                className={canClick ? 'cursor-pointer' : 'cursor-default'}
                style={{ perspective: '600px' }}
                onClick={() => handleCardClick(index)}
              >
                <div
                  className="relative w-16 h-20 sm:w-20 sm:h-24"
                  style={{
                    transformStyle: 'preserve-3d',
                    transform: isRevealed ? 'rotateY(180deg)' : 'none',
                    transition: 'transform 0.4s',
                  }}
                >
                  {/* Back face */}
                  <div
                    className={`absolute inset-0 rounded-lg flex items-center justify-center border-2
                      bg-slate-700 border-slate-600 ${canClick ? 'hover:border-slate-500' : ''} transition-colors`}
                    style={{ backfaceVisibility: 'hidden' }}
                  >
                    <span className="text-slate-500 text-xl">?</span>
                  </div>
                  {/* Front face */}
                  <div
                    className={`absolute inset-0 rounded-lg flex items-center justify-center border-2
                      ${matchColor
                        ? `${matchColor.matchBg} ${matchColor.matchBorder}`
                        : 'bg-white border-slate-300'
                      }`}
                    style={{
                      backfaceVisibility: 'hidden',
                      transform: 'rotateY(180deg)',
                    }}
                  >
                    <span className={`text-3xl ${card.matched ? 'opacity-70' : ''}`}>
                      {card.symbol}
                    </span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Game over */}
        {(gameStatus === 'won' || gameStatus === 'lost' || gameStatus === 'draw') && (
          <GameOverModal
            status={gameStatus}
            message={
              gameStatus === 'draw'
                ? `Tie! Both players found ${scores[0]} pairs`
                : `${scores[myIndex]} - ${scores[opponentIndex]}`
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
