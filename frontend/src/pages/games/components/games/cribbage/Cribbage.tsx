/**
 * Cribbage — 2-player card game. First to 121 wins.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import { getRankDisplay, getSuitSymbol } from '../../../utils/cardUtils'
import type { GameStatus } from '../../../types'
import {
  createCribbageGame,
  toggleCribSelection,
  submitCrib,
  playPegCard,
  sayGo,
  continueScoring,
  newRound,
  getHumanPeggableCards,
  humanMustGo,
  isCardPlayed,
  type CribbageState,
} from './CribbageEngine'

interface SavedState {
  gameState: CribbageState
  gameStatus: GameStatus
}

export default function Cribbage() {
  const { load, save, clear } = useGameState<SavedState>('cribbage')
  const saved = useRef(load()).current

  const [gameState, setGameState] = useState<CribbageState>(
    () => saved?.gameState ?? createCribbageGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')

  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      setGameStatus(gameState.scores[0] >= 121 ? 'won' : 'lost')
      clear()
    }
  }, [gameState, clear])

  const handleToggleSelect = useCallback((idx: number) => {
    setGameState(prev => toggleCribSelection(prev, idx))
  }, [])

  const handleSubmitCrib = useCallback(() => {
    setGameState(prev => submitCrib(prev))
  }, [])

  const handlePlayCard = useCallback((idx: number) => {
    setGameState(prev => playPegCard(prev, idx))
  }, [])

  const handleSayGo = useCallback(() => {
    setGameState(prev => sayGo(prev))
  }, [])

  const handleContinueScoring = useCallback(() => {
    setGameState(prev => continueScoring(prev))
  }, [])

  const handleNewRound = useCallback(() => {
    setGameState(prev => newRound(prev))
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createCribbageGame())
    setGameStatus('playing')
    clear()
  }, [clear])

  const peggable = getHumanPeggableCards(gameState)
  const mustGo = humanMustGo(gameState)
  const isScoring = gameState.phase === 'scoring'
  const showAiCards = isScoring || gameState.phase === 'gameOver'

  // Score board display
  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-4 text-xs">
        <span className="text-white font-medium">
          You: <span className="text-blue-400">{gameState.scores[0]}</span>/121
        </span>
        <span className="text-slate-400">
          AI: <span className="text-red-400">{gameState.scores[1]}</span>/121
        </span>
      </div>
      <span className="text-xs text-slate-400">
        Dealer: {gameState.dealer === 0 ? 'You' : 'AI'}
      </span>
    </div>
  )

  return (
    <GameLayout title="Cribbage" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-3">

        {/* Cribbage board (score visualization) */}
        <div className="w-full flex gap-2 items-center">
          <div className="flex-1">
            <div className="text-[0.6rem] text-blue-400 mb-0.5">You</div>
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, (gameState.scores[0] / 121) * 100)}%` }}
              />
            </div>
          </div>
          <div className="flex-1">
            <div className="text-[0.6rem] text-red-400 mb-0.5">AI</div>
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-red-500 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, (gameState.scores[1] / 121) * 100)}%` }}
              />
            </div>
          </div>
        </div>

        {/* AI hand */}
        <div className="text-center">
          <span className="text-xs text-slate-400">AI Hand</span>
          <div className="flex gap-1 justify-center mt-1">
            {gameState.hands[1].map((card, i) => {
              const played = isCardPlayed(gameState, 1, i)
              return (
                <div
                  key={i}
                  className={`w-14 h-[5rem] sm:w-16 sm:h-[5.625rem] ${played ? 'opacity-30' : ''}`}
                >
                  {showAiCards ? <CardFace card={card} /> : <CardBack />}
                </div>
              )
            })}
          </div>
        </div>

        {/* Cut card + pegging area */}
        <div className="flex gap-4 items-start justify-center">
          {/* Cut card */}
          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500">Cut</span>
            <div className="w-14 h-[5rem] sm:w-16 sm:h-[5.625rem]">
              {gameState.cutCard ? (
                <CardFace card={gameState.cutCard} />
              ) : (
                <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">
                  --
                </div>
              )}
            </div>
          </div>

          {/* Pegging area */}
          {gameState.phase === 'pegging' && (
            <div className="text-center">
              <span className="text-[0.6rem] text-slate-500">
                Count: <span className="text-white font-bold">{gameState.pegTotal}</span>/31
              </span>
              <div className="flex gap-0.5 mt-1 flex-wrap justify-center max-w-[12rem]">
                {gameState.pegCards.map((pc, i) => (
                  <div
                    key={i}
                    className={`w-10 h-14 sm:w-11 sm:h-[3.75rem] ${
                      pc.player === 0 ? 'ring-1 ring-blue-500/50' : 'ring-1 ring-red-500/50'
                    } rounded`}
                  >
                    <CardFace card={pc.card} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Crib */}
          <div className="text-center">
            <span className="text-[0.6rem] text-slate-500">
              Crib ({gameState.dealer === 0 ? 'Yours' : "AI's"})
            </span>
            <div className="w-14 h-[5rem] sm:w-16 sm:h-[5.625rem]">
              {gameState.crib.length > 0 ? (
                gameState.scoringStep === 'crib' || gameState.scoringStep === 'done' || gameState.phase === 'gameOver' ? (
                  <div className="flex -space-x-8">
                    {gameState.crib.slice(0, 2).map((c, i) => (
                      <div key={i} className="w-14 h-[5rem] sm:w-16 sm:h-[5.625rem]">
                        <CardFace card={c} />
                      </div>
                    ))}
                  </div>
                ) : (
                  <CardBack />
                )
              ) : (
                <div className="w-full h-full rounded-md border border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs">
                  --
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center min-h-[2.5rem]">
          {gameState.message}
        </p>

        {/* Scoring breakdown */}
        {isScoring && gameState.lastScoreBreakdown && (
          <p className="text-xs text-slate-400 text-center">{gameState.lastScoreBreakdown}</p>
        )}

        {/* Action buttons */}
        <div className="flex gap-2 justify-center">
          {/* Send to Crib button */}
          {gameState.phase === 'discard' && gameState.selectedForCrib.length === 2 && (
            <button
              onClick={handleSubmitCrib}
              className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Send to Crib
            </button>
          )}

          {/* Go button */}
          {gameState.phase === 'pegging' && gameState.currentPlayer === 0 && mustGo && (
            <button
              onClick={handleSayGo}
              className="px-5 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Go
            </button>
          )}

          {/* Continue scoring */}
          {isScoring && gameState.scoringStep !== 'done' && (
            <button
              onClick={handleContinueScoring}
              className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Continue
            </button>
          )}

          {/* Next Round */}
          {isScoring && gameState.scoringStep === 'done' && (
            <button
              onClick={handleNewRound}
              className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Next Round
            </button>
          )}
        </div>

        {/* Peg history (scrollable) */}
        {gameState.phase === 'pegging' && gameState.pegHistory.length > 0 && (
          <div className="w-full">
            <span className="text-[0.6rem] text-slate-500">Pegging History</span>
            <div className="flex gap-0.5 overflow-x-auto py-1">
              {gameState.pegHistory.map((pc, i) => (
                <div
                  key={i}
                  className="flex-shrink-0 text-center"
                >
                  <div className={`text-[0.5rem] ${pc.player === 0 ? 'text-blue-400' : 'text-red-400'}`}>
                    {pc.player === 0 ? 'You' : 'AI'}
                  </div>
                  <div className="text-[0.6rem] text-white">
                    {getRankDisplay(pc.card.rank)}{getSuitSymbol(pc.card.suit)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Player hand */}
        <div className="text-center">
          <span className="text-xs text-slate-400">Your Hand</span>
          <div className="flex flex-wrap gap-1.5 justify-center mt-1 max-w-md">
            {gameState.hands[0].map((card, i) => {
              const isSelected = gameState.selectedForCrib.includes(i)
              const isPlayable = peggable.includes(i)
              const played = isCardPlayed(gameState, 0, i)

              // During discard: all cards clickable for selection
              // During pegging: only playable cards clickable
              const clickable = gameState.phase === 'discard'
                ? true
                : gameState.phase === 'pegging' && isPlayable

              return (
                <div
                  key={i}
                  className={`w-14 h-[5rem] sm:w-16 sm:h-[5.625rem] transition-all duration-150 ${
                    played ? 'opacity-30 pointer-events-none' : ''
                  } ${
                    clickable && !played ? 'cursor-pointer hover:-translate-y-1' : ''
                  } ${
                    !clickable && !played && gameState.phase === 'pegging' ? 'opacity-50' : ''
                  } ${
                    isSelected ? '-translate-y-2' : ''
                  }`}
                  onClick={() => {
                    if (played) return
                    if (gameState.phase === 'discard') handleToggleSelect(i)
                    else if (gameState.phase === 'pegging' && isPlayable) handlePlayCard(i)
                  }}
                >
                  <CardFace card={card} selected={isSelected} />
                </div>
              )
            })}
          </div>
        </div>

        {/* Discard hint */}
        {gameState.phase === 'discard' && (
          <p className="text-xs text-slate-500 text-center">
            Select 2 cards to discard to the {gameState.dealer === 0 ? 'your' : "AI's"} crib
          </p>
        )}

        {/* Pegging value helper */}
        {gameState.phase === 'pegging' && gameState.currentPlayer === 0 && (
          <p className="text-xs text-slate-500 text-center">
            Click a card to play it. Need {31 - gameState.pegTotal} or less to play.
          </p>
        )}

        {/* Game Over Modal */}
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
