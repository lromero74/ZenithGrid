/**
 * Video Poker (Jacks or Better) — hold/draw poker against the machine.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import {
  createVideoPokerGame,
  deal,
  toggleHold,
  draw,
  newHand,
  setBet,
  isGameOver,
  getPayTable,
  MAX_BET,
  MIN_BET,
  type VideoPokerState,
} from './videoPokerEngine'

interface SavedState {
  gameState: VideoPokerState
  gameStatus: GameStatus
}

export default function VideoPoker() {
  const { load, save, clear } = useGameState<SavedState>('video-poker')
  const saved = useRef(load()).current

  const [gameState, setGameState] = useState<VideoPokerState>(
    () => saved?.gameState ?? createVideoPokerGame()
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')

  useEffect(() => {
    if (gameStatus !== 'lost') {
      save({ gameState, gameStatus })
    }
  }, [gameState, gameStatus, save])

  useEffect(() => {
    if (isGameOver(gameState)) {
      setGameStatus('lost')
      clear()
    }
  }, [gameState, clear])

  const handleBetChange = useCallback((delta: number) => {
    setGameState(prev => setBet(prev, prev.bet + delta))
  }, [])

  const handleDeal = useCallback(() => setGameState(prev => deal(prev)), [])
  const handleToggle = useCallback((i: number) => setGameState(prev => toggleHold(prev, i)), [])
  const handleDraw = useCallback(() => setGameState(prev => draw(prev)), [])
  const handleNewHand = useCallback(() => setGameState(prev => newHand(prev)), [])

  const handleNewGame = useCallback(() => {
    setGameState(createVideoPokerGame())
    setGameStatus('playing')
    clear()
  }, [clear])

  const payTable = getPayTable()

  const controls = (
    <div className="flex items-center justify-between">
      <span className="text-xs text-slate-400">Jacks or Better</span>
      <span className="text-xs text-yellow-400 font-mono">Credits: {gameState.credits}</span>
    </div>
  )

  return (
    <GameLayout title="Video Poker" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-lg space-y-4">
        {/* Pay table */}
        <div className="w-full bg-slate-800/50 rounded-lg p-2 text-[0.6rem] sm:text-xs">
          <div className="grid grid-cols-6 gap-x-2 gap-y-0.5 text-center">
            <div className="text-slate-500 font-semibold text-left col-span-1">Hand</div>
            {[1, 2, 3, 4, 5].map(b => (
              <div key={b} className={`font-mono ${b === gameState.bet ? 'text-yellow-400 font-bold' : 'text-slate-500'}`}>
                {b}x
              </div>
            ))}
            {payTable.map(row => (
              <div key={row.name} className="contents">
                <div className={`text-left truncate ${gameState.lastResult?.name === row.name ? 'text-emerald-400 font-bold' : 'text-slate-400'}`}>
                  {row.name}
                </div>
                {[1, 2, 3, 4, 5].map(b => {
                  const mult = row.name === 'Royal Flush' && b === 5 ? 800 : row.multiplier
                  return (
                    <div key={b} className={`font-mono ${
                      gameState.lastResult?.name === row.name && b === gameState.bet
                        ? 'text-emerald-400 font-bold' : 'text-slate-500'
                    }`}>
                      {mult * b}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>

        {/* Cards */}
        <div className="flex gap-2 justify-center">
          {gameState.phase === 'betting' ? (
            // Show 5 card backs
            Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="w-14 h-[5rem] sm:w-16 sm:h-[5.625rem]">
                <CardBack />
              </div>
            ))
          ) : (
            gameState.hand.map((card, i) => (
              <div key={i} className="flex flex-col items-center gap-1">
                <div
                  className={`w-14 h-[5rem] sm:w-16 sm:h-[5.625rem] cursor-pointer ${gameState.phase === 'dealt' ? 'hover:opacity-80' : ''}`}
                  onClick={() => handleToggle(i)}
                >
                  <CardFace card={card} held={gameState.held[i]} />
                </div>
                {gameState.held[i] && (
                  <span className="text-[0.6rem] text-cyan-400 font-bold">HELD</span>
                )}
              </div>
            ))
          )}
        </div>

        {/* Message */}
        <p className={`text-sm font-medium ${gameState.lastResult ? 'text-emerald-400' : 'text-white'}`}>
          {gameState.message}
        </p>

        {/* Controls */}
        <div className="flex items-center gap-3">
          {gameState.phase === 'betting' && (
            <>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleBetChange(-1)}
                  disabled={gameState.bet <= MIN_BET}
                  className="px-2 py-1 text-xs bg-slate-700 text-slate-300 rounded hover:bg-slate-600 disabled:opacity-40"
                >
                  -
                </button>
                <span className="text-sm text-white font-mono w-8 text-center">Bet {gameState.bet}</span>
                <button
                  onClick={() => handleBetChange(1)}
                  disabled={gameState.bet >= MAX_BET || gameState.bet >= gameState.credits}
                  className="px-2 py-1 text-xs bg-slate-700 text-slate-300 rounded hover:bg-slate-600 disabled:opacity-40"
                >
                  +
                </button>
              </div>
              <button
                onClick={handleDeal}
                disabled={gameState.bet > gameState.credits}
                className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-40"
              >
                Deal
              </button>
            </>
          )}
          {gameState.phase === 'dealt' && (
            <button
              onClick={handleDraw}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Draw
            </button>
          )}
          {gameState.phase === 'result' && !isGameOver(gameState) && (
            <button
              onClick={handleNewHand}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              New Hand
            </button>
          )}
        </div>

        {gameStatus === 'lost' && (
          <GameOverModal
            status="lost"
            message="You're out of credits!"
            onPlayAgain={handleNewGame}
          />
        )}
      </div>
    </GameLayout>
  )
}
