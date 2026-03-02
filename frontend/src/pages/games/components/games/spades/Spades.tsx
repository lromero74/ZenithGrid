/**
 * Spades — 4-player partnership trick-taking card game.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import {
  createSpadesGame,
  placeBid,
  playCard,
  nextRound,
  getValidPlays,
  PLAYER_NAMES,
  TEAM_NAMES,
  type SpadesState,
} from './spadesEngine'

interface SavedState {
  gameState: SpadesState
  gameStatus: GameStatus
}

export default function Spades() {
  const { load, save, clear } = useGameState<SavedState>('spades')
  const saved = useRef(load()).current

  const [gameState, setGameState] = useState<SpadesState>(
    () => saved?.gameState ?? createSpadesGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [selectedBid, setSelectedBid] = useState(3)

  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      setGameStatus(gameState.teamScores[0] > gameState.teamScores[1] ? 'won' : 'lost')
      clear()
    }
  }, [gameState, clear])

  const handleBid = useCallback(() => {
    setGameState(prev => placeBid(prev, selectedBid))
  }, [selectedBid])

  const handlePlay = useCallback((i: number) => {
    setGameState(prev => playCard(prev, i))
  }, [])

  const handleNextRound = useCallback(() => {
    setGameState(prev => nextRound(prev))
  }, [])

  const handleNewGame = useCallback(() => {
    setGameState(createSpadesGame())
    setGameStatus('playing')
    clear()
  }, [clear])

  const validPlays = getValidPlays(gameState)
  const isBidding = gameState.phase === 'bidding'
  const isPlaying = gameState.phase === 'playing' && gameState.currentPlayer === 0
  const bids = gameState.bids

  const controls = (
    <div className="flex items-center justify-between text-xs">
      <div className="flex gap-3">
        <span className="text-blue-400">{TEAM_NAMES[0]}: {gameState.teamScores[0]}</span>
        <span className="text-red-400">{TEAM_NAMES[1]}: {gameState.teamScores[1]}</span>
      </div>
      {bids[0] !== null && (
        <div className="flex gap-2 text-slate-400">
          {PLAYER_NAMES.map((name, i) => (
            <span key={i}>
              {name}: {bids[i] ?? '?'}/{gameState.tricksTaken[i]}
            </span>
          ))}
        </div>
      )}
    </div>
  )

  return (
    <GameLayout title="Spades" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-3">
        {/* North (Partner) */}
        <div className="text-center">
          <span className="text-xs text-blue-400">North (Partner) ({gameState.hands[2].length})</span>
          <div className="flex gap-0.5 justify-center mt-0.5">
            {gameState.hands[2].slice(0, 7).map((_, i) => (
              <div key={i} className="w-5 h-8"><CardBack /></div>
            ))}
            {gameState.hands[2].length > 7 && <span className="text-[0.6rem] text-slate-500 self-center">+{gameState.hands[2].length - 7}</span>}
          </div>
        </div>

        {/* West + Trick area + East */}
        <div className="flex w-full items-center gap-2">
          {/* West (Opponent) */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-red-400">West ({gameState.hands[3].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[3].slice(0, 5).map((_, i) => (
                <div key={i} className="w-8 h-3"><CardBack /></div>
              ))}
            </div>
          </div>

          {/* Trick area */}
          <div className="flex-1 relative h-32 sm:h-40">
            {gameState.currentTrick.map((play) => {
              const positions = [
                'bottom-0 left-1/2 -translate-x-1/2',
                'right-0 top-1/2 -translate-y-1/2',
                'top-0 left-1/2 -translate-x-1/2',
                'left-0 top-1/2 -translate-y-1/2',
              ]
              return (
                <div key={`${play.player}-${play.card.rank}-${play.card.suit}`}
                  className={`absolute ${positions[play.player]} w-10 h-[3.5rem] sm:w-12 sm:h-[4.25rem]`}
                >
                  <CardFace card={play.card} />
                </div>
              )
            })}
            {gameState.spadesBroken && (
              <span className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[0.6rem] text-slate-500">
                Spades broken
              </span>
            )}
          </div>

          {/* East (Opponent) */}
          <div className="text-center w-16 flex-shrink-0">
            <span className="text-[0.6rem] text-red-400">East ({gameState.hands[1].length})</span>
            <div className="flex flex-col items-center gap-0.5 mt-0.5">
              {gameState.hands[1].slice(0, 5).map((_, i) => (
                <div key={i} className="w-8 h-3"><CardBack /></div>
              ))}
            </div>
          </div>
        </div>

        {/* Message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>

        {/* Bidding */}
        {isBidding && (
          <div className="flex flex-col items-center gap-2">
            <div className="flex gap-1 flex-wrap justify-center">
              {Array.from({ length: 14 }, (_, i) => (
                <button
                  key={i}
                  onClick={() => setSelectedBid(i)}
                  className={`w-8 h-8 text-xs rounded transition-colors ${
                    selectedBid === i ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {i === 0 ? 'Nil' : i}
                </button>
              ))}
            </div>
            <button
              onClick={handleBid}
              className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Bid {selectedBid === 0 ? 'Nil' : selectedBid}
            </button>
          </div>
        )}

        {/* Player hand */}
        <div className="flex flex-wrap gap-1 justify-center max-w-md">
          {gameState.hands[0].map((card, i) => {
            const isValid = validPlays.includes(i)
            return (
              <div
                key={`${card.rank}-${card.suit}`}
                className={`w-11 h-[4rem] sm:w-13 sm:h-[4.75rem] transition-transform ${
                  isPlaying && isValid ? 'cursor-pointer hover:-translate-y-1' : 'opacity-40'
                }`}
                onClick={() => isPlaying && isValid && handlePlay(i)}
              >
                <CardFace card={card} />
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
            score={gameState.teamScores[0]}
            message={gameState.message}
            onPlayAgain={handleNewGame}
          />
        )}
      </div>
    </GameLayout>
  )
}
