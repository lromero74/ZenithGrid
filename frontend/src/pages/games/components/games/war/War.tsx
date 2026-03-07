/**
 * War — 2-player card game. Flip cards, higher rank wins.
 */

import { useState, useCallback, useRef, useEffect, useMemo} from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import {
  createWarGame,
  flipCards,
  resolveCompare,
  resolveWar,
  type WarState,
} from './WarEngine'

interface SavedState {
  gameState: WarState
  gameStatus: GameStatus
}

export default function War() {
  const { load, save, clear } = useGameState<SavedState>('war')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('war'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('war')

  const [gameState, setGameState] = useState<WarState>(
    () => saved?.gameState ?? createWarGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [autoPlay, setAutoPlay] = useState(false)
  const autoPlayRef = useRef(autoPlay)
  autoPlayRef.current = autoPlay

  // Persist state
  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost' && gameStatus !== 'draw') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  // Detect game over
  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const pCount = gameState.playerDeck.length
      const aCount = gameState.aiDeck.length
      if (pCount > aCount) setGameStatus('won')
      else if (aCount > pCount) setGameStatus('lost')
      else setGameStatus('draw')
      clear()
      setAutoPlay(false)
    }
  }, [gameState, clear])

  // Auto-advance: compare → resolve, war → resolve
  useEffect(() => {
    if (gameState.phase === 'compare') {
      sfx.play('flip')
      const timer = setTimeout(() => {
        setGameState(prev => {
          const next = resolveCompare(prev)
          if (next.phase === 'ready') sfx.play('win_round')
          if (next.phase === 'war') sfx.play('war')
          return next
        })
      }, 800)
      return () => clearTimeout(timer)
    }
    if (gameState.phase === 'war') {
      const timer = setTimeout(() => {
        setGameState(prev => {
          const next = resolveWar(prev)
          sfx.play('win_round')
          return next
        })
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [gameState.phase])

  // Auto-play: auto-flip when in ready phase
  useEffect(() => {
    if (autoPlayRef.current && gameState.phase === 'ready' && gameStatus === 'playing') {
      const timer = setTimeout(() => {
        if (autoPlayRef.current) {
          setGameState(prev => flipCards(prev))
        }
      }, 600)
      return () => clearTimeout(timer)
    }
  }, [gameState.phase, gameState.round, gameStatus])

  const handleFlip = useCallback(() => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('flip')
    setGameState(prev => flipCards(prev))
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createWarGame())
    setGameStatus('playing')
    setAutoPlay(false)
    clear()
  }, [clear])

  const toggleAutoPlay = useCallback(() => {
    setAutoPlay(prev => !prev)
  }, [])

  const controls = (
    <div className="flex items-center justify-between text-xs w-full">
      <span className="text-slate-400">Round {gameState.round}/{gameState.maxRounds}</span>
      <button
        onClick={toggleAutoPlay}
        className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
          autoPlay ? 'bg-amber-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
        }`}
      >
        {autoPlay ? 'Auto: ON' : 'Auto: OFF'}
      </button>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="War" controls={controls}>
      <div className="flex flex-col items-center w-full max-w-sm space-y-4">
        {/* AI deck */}
        <div className="text-center">
          <span className="text-xs text-slate-400 mb-1 block">AI ({gameState.aiDeck.length} cards)</span>
          <div className="flex justify-center">
            {gameState.aiDeck.length > 0 ? (
              <div className="w-14 h-[5rem] sm:w-16 sm:h-[5.625rem] relative">
                <CardBack />
                {gameState.aiDeck.length > 1 && (
                  <div className="absolute -top-0.5 -left-0.5 w-14 h-[5rem] sm:w-16 sm:h-[5.625rem] -z-10">
                    <CardBack />
                  </div>
                )}
              </div>
            ) : (
              <div className="w-14 h-[5rem] sm:w-16 sm:h-[5.625rem] border border-dashed border-slate-600 rounded-lg" />
            )}
          </div>
        </div>

        {/* Battle area */}
        <div className="flex items-center gap-6 py-3">
          {/* Player's flipped card */}
          <div className="w-14 h-[5rem] sm:w-16 sm:h-[5.625rem]">
            {gameState.playerCard ? (
              <CardFace card={gameState.playerCard} />
            ) : (
              <div className="w-full h-full border border-dashed border-slate-600 rounded-lg flex items-center justify-center">
                <span className="text-[0.5rem] text-slate-500">You</span>
              </div>
            )}
          </div>

          {/* War pile indicator */}
          {gameState.warPile.length > 0 && (
            <div className="flex flex-col items-center gap-1">
              <div className="flex gap-0.5">
                {gameState.warPile.slice(0, 3).map((_, i) => (
                  <div key={i} className="w-6 h-9">
                    <CardBack />
                  </div>
                ))}
              </div>
              <span className="text-[0.6rem] text-amber-400">{gameState.warPile.length} cards</span>
            </div>
          )}

          {/* VS indicator */}
          {gameState.warPile.length === 0 && (
            <span className="text-lg font-bold text-slate-500">VS</span>
          )}

          {/* AI's flipped card */}
          <div className="w-14 h-[5rem] sm:w-16 sm:h-[5.625rem]">
            {gameState.aiCard ? (
              <CardFace card={gameState.aiCard} />
            ) : (
              <div className="w-full h-full border border-dashed border-slate-600 rounded-lg flex items-center justify-center">
                <span className="text-[0.5rem] text-slate-500">AI</span>
              </div>
            )}
          </div>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center min-h-[1.25rem]">
          {gameState.message}
        </p>

        {/* Flip button */}
        {gameState.phase === 'ready' && gameStatus === 'playing' && !autoPlay && (
          <button
            onClick={handleFlip}
            className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors active:scale-95"
          >
            Flip!
          </button>
        )}

        {/* Player deck */}
        <div className="text-center">
          <div className="flex justify-center">
            {gameState.playerDeck.length > 0 ? (
              <div className="w-14 h-[5rem] sm:w-16 sm:h-[5.625rem] relative">
                <CardBack />
                {gameState.playerDeck.length > 1 && (
                  <div className="absolute -top-0.5 -left-0.5 w-14 h-[5rem] sm:w-16 sm:h-[5.625rem] -z-10">
                    <CardBack />
                  </div>
                )}
              </div>
            ) : (
              <div className="w-14 h-[5rem] sm:w-16 sm:h-[5.625rem] border border-dashed border-slate-600 rounded-lg" />
            )}
          </div>
          <span className="text-xs text-slate-400 mt-1 block">You ({gameState.playerDeck.length} cards)</span>
        </div>

        {/* Game over modal */}
        {(gameStatus === 'won' || gameStatus === 'lost' || gameStatus === 'draw') && (
          <GameOverModal
            status={gameStatus}
            score={gameState.playerDeck.length}
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
