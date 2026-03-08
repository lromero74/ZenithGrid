/**
 * Go Fish — ask for ranks, collect books of four.
 */

import { useState, useCallback, useRef, useEffect, useMemo} from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import { getRankDisplay } from '../../../utils/cardUtils'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import {
  createGoFishGame,
  askForRank,
  goFish,
  aiTurn,
  getAskableRanks,
  type GoFishState,
} from './goFishEngine'

interface SavedState {
  gameState: GoFishState
  gameStatus: GameStatus
}

export default function GoFish() {
  const { load, save, clear } = useGameState<SavedState>('go-fish')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('go-fish'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('go-fish')

  const [gameState, setGameState] = useState<GoFishState>(
    () => saved?.gameState ?? createGoFishGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')

  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const humanWon = gameState.books[0].length > gameState.books[1].length
      const tied = gameState.books[0].length === gameState.books[1].length
      if (humanWon) sfx.play('match')
      setGameStatus(tied ? 'draw' : humanWon ? 'won' : 'lost')
      clear()
    }
  }, [gameState, clear])

  // Auto-run AI turn
  useEffect(() => {
    if (gameState.phase === 'aiTurn') {
      const timer = setTimeout(() => {
        setGameState(prev => aiTurn(prev))
      }, 800)
      return () => clearTimeout(timer)
    }
  }, [gameState.phase])

  const handleAsk = useCallback((rank: number) => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('play')
    setGameState(prev => askForRank(prev, rank))
  }, [])

  const handleGoFish = useCallback(() => {
    sfx.play('draw')
    setGameState(prev => goFish(prev))
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createGoFishGame())
    setGameStatus('playing')
    clear()
  }, [clear])

  const askable = getAskableRanks(gameState)

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3 text-xs text-slate-400">
        <span className="text-white">You: {gameState.books[0].length} books</span>
        <span>AI: {gameState.books[1].length} books</span>
      </div>
      <span className="text-xs text-slate-400">
        Pond: {gameState.pond.length} cards
      </span>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Go Fish" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-4">
        {/* AI hand */}
        <div className="text-center">
          <span className="text-xs text-slate-400">AI ({gameState.hands[1].length} cards)</span>
          <div className="flex gap-0.5 justify-center mt-1">
            {gameState.hands[1].slice(0, Math.min(gameState.hands[1].length, 7)).map((_, j) => (
              <div key={j} className="w-6 h-9">
                <CardBack />
              </div>
            ))}
            {gameState.hands[1].length > 7 && (
              <span className="text-xs text-slate-500 self-center ml-1">+{gameState.hands[1].length - 7}</span>
            )}
          </div>
          {gameState.books[1].length > 0 && (
            <div className="text-xs text-slate-400 mt-1">
              Books: {gameState.books[1].map(r => getRankDisplay(r)).join(', ')}
            </div>
          )}
        </div>

        {/* Pond */}
        <div className="flex gap-3 items-center justify-center">
          <div
            className={`${CARD_SIZE} ${gameState.phase === 'goFish' ? 'cursor-pointer' : ''}`}
            onClick={gameState.phase === 'goFish' ? handleGoFish : undefined}
          >
            {gameState.pond.length > 0 ? (
              <CardBack />
            ) : (
              <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">
                Empty
              </div>
            )}
          </div>
          <span className="text-xs text-slate-500">{gameState.pond.length} left</span>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Go Fish button */}
        {gameState.phase === 'goFish' && (
          <button
            onClick={handleGoFish}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Go Fish!
          </button>
        )}

        {/* Player books */}
        {gameState.books[0].length > 0 && (
          <div className="text-xs text-emerald-400">
            Your Books: {gameState.books[0].map(r => getRankDisplay(r)).join(', ')}
          </div>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1.5 justify-center max-w-md">
          {gameState.hands[0].map((card, i) => {
            const isAskable = gameState.phase === 'playerTurn' && askable.includes(card.rank)
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

        {(gameStatus === 'won' || gameStatus === 'lost' || gameStatus === 'draw') && (
          <GameOverModal
            status={gameStatus}
            score={gameState.books[0].length}
            message={gameState.message}
            onPlayAgain={handleNewGame}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
