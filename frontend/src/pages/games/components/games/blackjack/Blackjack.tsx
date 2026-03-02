/**
 * Blackjack — 6-deck shoe, standard rules with split & double down.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import {
  createBlackjackGame,
  placeBet,
  hit,
  stand,
  doubleDown,
  split,
  newRound,
  scoreHand,
  canSplit,
  canDoubleDown,
  isGameOver,
  BET_SIZES,
  type BlackjackState,
  type Difficulty,
} from './blackjackEngine'

interface SavedState {
  gameState: BlackjackState
  gameStatus: GameStatus
}

export default function Blackjack() {
  const { load, save, clear } = useGameState<SavedState>('blackjack')
  const saved = useRef(load()).current

  const [gameState, setGameState] = useState<BlackjackState>(
    () => saved?.gameState ?? createBlackjackGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selectedBet, setSelectedBet] = useState(BET_SIZES[0])

  // Persist
  useEffect(() => {
    if (gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  // Check for game over (broke)
  useEffect(() => {
    if (isGameOver(gameState)) {
      setGameStatus('lost')
      clear()
    }
  }, [gameState, clear])

  const handleDifficulty = useCallback((d: string) => {
    const newState = createBlackjackGame(d as Difficulty)
    setGameState(newState)
    setGameStatus('playing')
    clear()
  }, [clear])

  const handlePlaceBet = useCallback(() => {
    setGameState(prev => placeBet(prev, selectedBet))
  }, [selectedBet])

  const handleHit = useCallback(() => setGameState(prev => hit(prev)), [])
  const handleStand = useCallback(() => setGameState(prev => stand(prev)), [])
  const handleDouble = useCallback(() => setGameState(prev => doubleDown(prev)), [])
  const handleSplit = useCallback(() => setGameState(prev => split(prev)), [])

  const handleNextRound = useCallback(() => {
    setGameState(prev => newRound(prev))
  }, [])

  const handleNewGame = useCallback(() => {
    const newState = createBlackjackGame(gameState.difficulty)
    setGameState(newState)
    setGameStatus('playing')
    clear()
  }, [gameState.difficulty, clear])

  const dealerScore = scoreHand(gameState.dealerHand.filter(c => c.faceUp))
  const activeHand = gameState.playerHands[gameState.activeHandIndex]
  const activeScore = activeHand ? scoreHand(activeHand.cards) : null

  const controls = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <button
          onClick={() => handleDifficulty('easy')}
          className={`px-3 py-1 rounded text-xs font-medium transition-colors ${gameState.difficulty === 'easy' ? 'bg-emerald-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'}`}
        >
          Easy
        </button>
        <button
          onClick={() => handleDifficulty('hard')}
          className={`px-3 py-1 rounded text-xs font-medium transition-colors ${gameState.difficulty === 'hard' ? 'bg-red-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'}`}
        >
          Hard
        </button>
      </div>
      <span className="text-xs text-yellow-400 font-mono">Chips: {gameState.chips}</span>
    </div>
  )

  return (
    <GameLayout title="Blackjack" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-4">
        {/* Dealer area */}
        <div className="text-center">
          <span className="text-xs text-slate-400 mb-1 block">
            Dealer {gameState.phase === 'payout' ? `(${scoreHand(gameState.dealerHand).total})` : dealerScore.total > 0 ? `(${dealerScore.total})` : ''}
          </span>
          <div className="flex gap-2 justify-center min-h-[5.625rem]">
            {gameState.dealerHand.map((card, i) => (
              <div key={i} className="w-12 h-[4.25rem] sm:w-16 sm:h-[5.625rem]">
                {card.faceUp ? <CardFace card={card} /> : <CardBack />}
              </div>
            ))}
          </div>
        </div>

        {/* Message */}
        <div className="text-center py-2">
          <p className="text-sm text-white font-medium">{gameState.message}</p>
        </div>

        {/* Player hands */}
        <div className="space-y-3">
          {gameState.playerHands.map((hand, hIdx) => {
            const hScore = scoreHand(hand.cards)
            const isActive = hIdx === gameState.activeHandIndex && gameState.phase === 'playerTurn'
            return (
              <div key={hIdx} className={`text-center ${isActive ? '' : 'opacity-60'}`}>
                {gameState.playerHands.length > 1 && (
                  <span className="text-xs text-slate-400 mb-1 block">
                    Hand {hIdx + 1} (Bet: {hand.bet}) — {hScore.total}{hScore.isSoft ? ' soft' : ''}{hScore.isBust ? ' BUST' : ''}
                  </span>
                )}
                <div className="flex gap-2 justify-center">
                  {hand.cards.map((card, i) => (
                    <div key={i} className={`w-12 h-[4.25rem] sm:w-16 sm:h-[5.625rem] ${isActive ? 'ring-1 ring-blue-400/40 rounded-md' : ''}`}>
                      <CardFace card={card} />
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>

        {/* Player score */}
        {activeScore && gameState.phase === 'playerTurn' && gameState.playerHands.length === 1 && (
          <p className="text-xs text-slate-400">
            {activeScore.total}{activeScore.isSoft ? ' (soft)' : ''}
          </p>
        )}

        {/* Betting phase */}
        {gameState.phase === 'betting' && (
          <div className="flex flex-col items-center gap-3">
            <div className="flex gap-2">
              {BET_SIZES.map(bet => (
                <button
                  key={bet}
                  onClick={() => setSelectedBet(bet)}
                  disabled={bet > gameState.chips}
                  className={`px-3 py-1.5 text-xs rounded font-mono transition-colors ${
                    selectedBet === bet
                      ? 'bg-yellow-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  } disabled:opacity-30 disabled:cursor-not-allowed`}
                >
                  {bet}
                </button>
              ))}
            </div>
            <button
              onClick={handlePlaceBet}
              disabled={selectedBet > gameState.chips}
              className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-40"
            >
              Deal ({selectedBet} chips)
            </button>
          </div>
        )}

        {/* Player turn actions */}
        {gameState.phase === 'playerTurn' && (
          <div className="flex gap-2">
            <button onClick={handleHit} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm transition-colors">
              Hit
            </button>
            <button onClick={handleStand} className="px-4 py-2 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm transition-colors">
              Stand
            </button>
            {canDoubleDown(gameState) && (
              <button onClick={handleDouble} className="px-4 py-2 bg-yellow-600 hover:bg-yellow-500 text-white rounded-lg text-sm transition-colors">
                Double
              </button>
            )}
            {canSplit(gameState) && (
              <button onClick={handleSplit} className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-sm transition-colors">
                Split
              </button>
            )}
          </div>
        )}

        {/* Payout — next round */}
        {gameState.phase === 'payout' && !isGameOver(gameState) && (
          <button
            onClick={handleNextRound}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Next Hand
          </button>
        )}

        {/* Game over */}
        {gameStatus === 'lost' && (
          <GameOverModal
            status="lost"
            message="You're out of chips!"
            onPlayAgain={handleNewGame}
          />
        )}
      </div>
    </GameLayout>
  )
}
