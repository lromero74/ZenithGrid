/**
 * Hearts — 4-player trick-taking card game.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import {
  createHeartsGame,
  togglePassCard,
  confirmPass,
  playCard,
  nextRound,
  getValidPlays,
  PLAYER_NAMES,
  type HeartsState,
} from './heartsEngine'

interface SavedState {
  gameState: HeartsState
  gameStatus: GameStatus
}

export default function Hearts() {
  const { load, save, clear } = useGameState<SavedState>('hearts')
  const saved = useRef(load()).current

  const [gameState, setGameState] = useState<HeartsState>(
    () => saved?.gameState ?? createHeartsGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')

  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const humanScore = gameState.scores[0]
      const minScore = Math.min(...gameState.scores)
      setGameStatus(humanScore === minScore ? 'won' : 'lost')
      clear()
    }
  }, [gameState, clear])

  const handleTogglePass = useCallback((i: number) => {
    setGameState(prev => togglePassCard(prev, i))
  }, [])

  const handleConfirmPass = useCallback(() => {
    setGameState(prev => confirmPass(prev))
  }, [])

  const handlePlay = useCallback((i: number) => {
    setGameState(prev => playCard(prev, i))
  }, [])

  const handleNextRound = useCallback(() => {
    setGameState(prev => nextRound(prev))
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createHeartsGame())
    setGameStatus('playing')
    clear()
  }, [clear])

  const validPlays = getValidPlays(gameState)
  const isPassing = gameState.phase === 'passing'
  const isPlaying = gameState.phase === 'playing' && gameState.currentPlayer === 0

  const controls = (
    <div className="flex items-center justify-between text-xs">
      <div className="flex gap-3">
        {PLAYER_NAMES.map((name, i) => (
          <span key={i} className={i === 0 ? 'text-white' : 'text-slate-400'}>
            {name}: {gameState.scores[i]}
            {gameState.roundScores[i] > 0 ? ` (+${gameState.roundScores[i]})` : ''}
          </span>
        ))}
      </div>
      {gameState.heartsBroken && (
        <span className="text-red-400 text-xs">Hearts broken</span>
      )}
    </div>
  )

  return (
    <GameLayout title="Hearts" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-3">
        {/* North (AI) */}
        <div className="text-center">
          <span className="text-xs text-slate-400">North ({gameState.hands[2].length})</span>
          <div className="flex gap-0.5 justify-center mt-0.5">
            {gameState.hands[2].slice(0, 7).map((_, i) => (
              <div key={i} className="w-5 h-8"><CardBack /></div>
            ))}
            {gameState.hands[2].length > 7 && <span className="text-[0.6rem] text-slate-500 self-center">+{gameState.hands[2].length - 7}</span>}
          </div>
        </div>

        {/* West + Trick area + East */}
        <div className="flex w-full items-center gap-2">
          {/* West */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-slate-400">West ({gameState.hands[1].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[1].slice(0, 5).map((_, i) => (
                <div key={i} className="w-8 h-3"><CardBack /></div>
              ))}
            </div>
          </div>

          {/* Trick area */}
          <div className="flex-1 relative h-32 sm:h-40">
            {/* Center trick cards */}
            {gameState.currentTrick.map((play) => {
              const positions = [
                'bottom-0 left-1/2 -translate-x-1/2',  // South (0)
                'left-0 top-1/2 -translate-y-1/2',     // West (1)
                'top-0 left-1/2 -translate-x-1/2',     // North (2)
                'right-0 top-1/2 -translate-y-1/2',    // East (3)
              ]
              return (
                <div key={`${play.player}-${play.card.rank}-${play.card.suit}`}
                  className={`absolute ${positions[play.player]} w-10 h-[3.5rem] sm:w-12 sm:h-[4.25rem]`}
                >
                  <CardFace card={play.card} />
                </div>
              )
            })}
          </div>

          {/* East */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-slate-400">East ({gameState.hands[3].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[3].slice(0, 5).map((_, i) => (
                <div key={i} className="w-8 h-3"><CardBack /></div>
              ))}
            </div>
          </div>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Passing controls */}
        {isPassing && (
          <button
            onClick={handleConfirmPass}
            disabled={gameState.selectedCards.length !== 3}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Pass 3 Cards {gameState.passDirection}
          </button>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1 justify-center max-w-md">
          {gameState.hands[0].map((card, i) => {
            const isValid = isPassing || validPlays.includes(i)
            const isSelected = gameState.selectedCards.includes(i)
            return (
              <div
                key={`${card.rank}-${card.suit}`}
                className={`w-11 h-[4rem] sm:w-13 sm:h-[4.75rem] transition-transform ${
                  isValid ? 'cursor-pointer hover:-translate-y-1' : 'opacity-40'
                } ${isSelected ? '-translate-y-2' : ''}`}
                onClick={() => {
                  if (isPassing) handleTogglePass(i)
                  else if (isPlaying && validPlays.includes(i)) handlePlay(i)
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

        {(gameStatus === 'won' || gameStatus === 'lost') && (
          <GameOverModal
            status={gameStatus}
            score={gameState.scores[0]}
            message={gameState.message}
            onPlayAgain={handleNewGame}
          />
        )}
      </div>
    </GameLayout>
  )
}
