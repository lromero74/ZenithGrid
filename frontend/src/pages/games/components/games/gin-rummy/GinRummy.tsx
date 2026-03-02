/**
 * Gin Rummy — 2-player card game vs AI.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import {
  createGinRummyGame,
  drawFromPile,
  drawFromDiscard,
  discard,
  knock,
  newRound,
  canKnock,
  getPlayerDeadwood,
  findBestMelds,
  type GinRummyState,
} from './ginRummyEngine'

interface SavedState {
  gameState: GinRummyState
  gameStatus: GameStatus
}

export default function GinRummy() {
  const { load, save, clear } = useGameState<SavedState>('gin-rummy')
  const saved = useRef(load()).current

  const [gameState, setGameState] = useState<GinRummyState>(
    () => saved?.gameState ?? createGinRummyGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')

  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      setGameStatus(gameState.playerScore >= gameState.targetScore ? 'won' : 'lost')
      clear()
    }
  }, [gameState, clear])

  const handleDrawPile = useCallback(() => setGameState(prev => drawFromPile(prev)), [])
  const handleDrawDiscard = useCallback(() => setGameState(prev => drawFromDiscard(prev)), [])
  const handleDiscard = useCallback((i: number) => setGameState(prev => discard(prev, i)), [])
  const handleKnock = useCallback(() => setGameState(prev => knock(prev)), [])
  const handleNewRound = useCallback(() => setGameState(prev => newRound(prev)), [])

  const handleNewGame = useCallback(() => {
    setGameState(createGinRummyGame())
    setGameStatus('playing')
    clear()
  }, [clear])

  const topDiscard = gameState.discardPile[gameState.discardPile.length - 1]
  const isDrawing = gameState.phase === 'drawing' && gameState.currentPlayer === 0
  const isDiscarding = gameState.phase === 'discarding' && gameState.currentPlayer === 0
  const showKnock = canKnock(gameState)
  const deadwood = gameState.phase === 'discarding' ? getPlayerDeadwood(gameState) : findBestMelds(gameState.playerHand).deadwoodTotal

  // Show AI hand face-up during scoring/gameOver
  const showAiCards = gameState.phase === 'scoring' || gameState.phase === 'gameOver' || gameState.phase === 'knocked'

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3 text-xs">
        <span className="text-white">You: {gameState.playerScore}</span>
        <span className="text-slate-400">AI: {gameState.aiScore}</span>
      </div>
      <span className="text-xs text-slate-400">Deadwood: {deadwood}</span>
    </div>
  )

  return (
    <GameLayout title="Gin Rummy" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-4">
        {/* AI hand */}
        <div className="text-center">
          <span className="text-xs text-slate-400 mb-1 block">AI ({gameState.aiHand.length} cards)</span>
          <div className="flex gap-1 justify-center flex-wrap">
            {gameState.aiHand.map((card, i) => (
              <div key={i} className="w-10 h-[3.5rem] sm:w-12 sm:h-[4.25rem]">
                {showAiCards ? <CardFace card={{ ...card, faceUp: true }} /> : <CardBack />}
              </div>
            ))}
          </div>
        </div>

        {/* Draw pile + Discard pile */}
        <div className="flex gap-4 items-center justify-center">
          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500 block mb-0.5">Draw</span>
            <div
              className={`w-14 h-[5rem] sm:w-16 sm:h-[5.625rem] ${isDrawing ? 'cursor-pointer ring-2 ring-blue-400/50 rounded-md' : ''}`}
              onClick={isDrawing ? handleDrawPile : undefined}
            >
              {gameState.drawPile.length > 0 ? <CardBack /> : (
                <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">Empty</div>
              )}
            </div>
          </div>
          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500 block mb-0.5">Discard</span>
            <div
              className={`w-14 h-[5rem] sm:w-16 sm:h-[5.625rem] ${isDrawing && topDiscard ? 'cursor-pointer ring-2 ring-blue-400/50 rounded-md' : ''}`}
              onClick={isDrawing ? handleDrawDiscard : undefined}
            >
              {topDiscard ? <CardFace card={topDiscard} /> : (
                <div className="w-full h-full rounded-md border border-dashed border-slate-600/50" />
              )}
            </div>
          </div>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

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
          <span className="text-xs text-slate-400 mb-1 block">Your Hand</span>
          <div className="flex gap-1 justify-center flex-wrap">
            {gameState.playerHand.map((card, i) => (
              <div
                key={i}
                className={`w-12 h-[4.25rem] sm:w-14 sm:h-[5rem] transition-transform ${
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
        {gameState.phase === 'scoring' && (
          <div className="text-center space-y-2">
            <p className="text-sm text-emerald-400">{gameState.roundMessage}</p>
            <button
              onClick={handleNewRound}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Next Round
            </button>
          </div>
        )}

        {(gameStatus === 'won' || gameStatus === 'lost') && (
          <GameOverModal
            status={gameStatus}
            score={gameState.playerScore}
            message={gameState.message}
            onPlayAgain={handleNewGame}
          />
        )}
      </div>
    </GameLayout>
  )
}
