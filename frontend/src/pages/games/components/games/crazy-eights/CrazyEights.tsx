/**
 * Crazy Eights — match rank or suit, 8s are wild.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import { SUITS, getSuitSymbol, type Suit } from '../../../utils/cardUtils'
import type { GameStatus } from '../../../types'
import {
  createCrazyEightsGame,
  playCard,
  drawCard,
  chooseSuit,
  newRound,
  getHumanPlayableCards,
  type CrazyEightsState,
} from './crazyEightsEngine'

interface SavedState {
  gameState: CrazyEightsState
  gameStatus: GameStatus
}

export default function CrazyEights() {
  const { load, save, clear } = useGameState<SavedState>('crazy-eights')
  const saved = useRef(load()).current

  const [gameState, setGameState] = useState<CrazyEightsState>(
    () => saved?.gameState ?? createCrazyEightsGame(2)
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')

  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const humanWon = gameState.scores[0] >= gameState.targetScore
      setGameStatus(humanWon ? 'won' : 'lost')
      clear()
    }
  }, [gameState, clear])

  const handlePlay = useCallback((cardIdx: number) => {
    setGameState(prev => playCard(prev, cardIdx))
  }, [])

  const handleDraw = useCallback(() => {
    setGameState(prev => drawCard(prev))
  }, [])

  const handleChooseSuit = useCallback((suit: Suit) => {
    setGameState(prev => chooseSuit(prev, suit))
  }, [])

  const handleNewRound = useCallback(() => {
    setGameState(prev => newRound(prev))
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createCrazyEightsGame(gameState.playerCount))
    setGameStatus('playing')
    clear()
  }, [gameState.playerCount, clear])

  const playable = getHumanPlayableCards(gameState)
  const topDiscard = gameState.discardPile[gameState.discardPile.length - 1]

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2 text-xs text-slate-400">
        {gameState.scores.map((s, i) => (
          <span key={i} className={i === 0 ? 'text-white' : ''}>
            {i === 0 ? 'You' : `P${i + 1}`}: {s}
          </span>
        ))}
      </div>
      <span className="text-xs text-slate-400">
        Current suit: <span className={`font-bold ${gameState.currentSuit === 'hearts' || gameState.currentSuit === 'diamonds' ? 'text-red-400' : 'text-white'}`}>
          {getSuitSymbol(gameState.currentSuit)}
        </span>
      </span>
    </div>
  )

  return (
    <GameLayout title="Crazy Eights" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-4">
        {/* AI hands (card counts) */}
        <div className="flex gap-4 justify-center">
          {gameState.hands.slice(1).map((hand, i) => (
            <div key={i} className="text-center">
              <span className="text-xs text-slate-400">Player {i + 2}</span>
              <div className="flex gap-0.5 justify-center mt-1">
                {hand.slice(0, Math.min(hand.length, 7)).map((_, j) => (
                  <div key={j} className="w-6 h-9">
                    <CardBack />
                  </div>
                ))}
                {hand.length > 7 && (
                  <span className="text-xs text-slate-500 self-center ml-1">+{hand.length - 7}</span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Draw pile + Discard pile */}
        <div className="flex gap-4 items-center justify-center">
          <div
            className="w-14 h-[5rem] sm:w-16 sm:h-[5.625rem] cursor-pointer"
            onClick={handleDraw}
          >
            {gameState.drawPile.length > 0 ? (
              <CardBack />
            ) : (
              <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">
                Empty
              </div>
            )}
          </div>
          <div className="w-14 h-[5rem] sm:w-16 sm:h-[5.625rem]">
            {topDiscard && <CardFace card={topDiscard} />}
          </div>
          <span className="text-xs text-slate-500">{gameState.drawPile.length} left</span>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Suit picker */}
        {gameState.phase === 'choosingSuit' && (
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
          {gameState.hands[0].map((card, i) => {
            const isPlayable = playable.includes(i)
            return (
              <div
                key={i}
                className={`w-12 h-[4.25rem] sm:w-14 sm:h-[5rem] transition-transform ${
                  isPlayable ? 'cursor-pointer hover:-translate-y-1' : 'opacity-50'
                }`}
                onClick={() => isPlayable && handlePlay(i)}
              >
                <CardFace card={card} />
              </div>
            )
          })}
        </div>

        {/* Round over */}
        {gameState.phase === 'roundOver' && (
          <button
            onClick={handleNewRound}
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
