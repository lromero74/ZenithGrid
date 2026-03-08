/**
 * Texas Hold'em — poker with community cards.
 */

import { useState, useCallback, useRef, useEffect, useMemo} from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace, CardBack, CARD_SIZE } from '../../PlayingCard'
import { useGameState } from '../../../hooks/useGameState'
import type { GameStatus } from '../../../types'
import { useGameMusic } from '../../../audio/useGameMusic'
import { useGameSFX } from '../../../audio/useGameSFX'
import { getSongForGame } from '../../../audio/songRegistry'
import { MusicToggle } from '../../MusicToggle'
import {
  createTexasHoldemGame,
  startHand,
  fold,
  check,
  call,
  raise as raiseAction,
  allIn,
  getValidActions,
  getMinRaise,
  aiAction,
  nextHand,
  setBlinds,
  type TexasHoldemState,
} from './TexasHoldemEngine'

interface SavedState {
  gameState: TexasHoldemState
  gameStatus: GameStatus
  gameStartTime: number
}

/** Format a lastAction string to use "P2/P3/P4" instead of "Player 1/2/3". */
function formatAction(action: string): string {
  return action.replace(/Player (\d+)/g, (_, n) => `P${Number(n) + 1}`)
}

export default function TexasHoldem() {
  const { load, save, clear } = useGameState<SavedState>('texas-holdem')
  const saved = useRef(load()).current

  // Music
  const song = useMemo(() => getSongForGame('texas-holdem'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('texas-holdem')

  const [gameState, setGameState] = useState<TexasHoldemState>(() => {
    if (saved?.gameState) return saved.gameState
    return startHand(createTexasHoldemGame(4))
  })
  const [gameStatus, setGameStatus] = useState<GameStatus>(saved?.gameStatus ?? 'playing')
  const [raiseAmount, setRaiseAmount] = useState(40)
  const [gameStartTime, setGameStartTime] = useState(() => saved?.gameStartTime ?? Date.now())

  // Shows the last AI action text for 2 seconds
  const [aiActionText, setAiActionText] = useState<string | null>(null)

  // Blinds increase every 10 minutes: level 0 = 10/20, level 1 = 20/40, etc.
  useEffect(() => {
    if (gameStatus !== 'playing') return
    const timer = setInterval(() => {
      const elapsed = Date.now() - gameStartTime
      const level = Math.floor(elapsed / (10 * 60 * 1000))
      setGameState(prev => {
        if (prev.blindLevel === level) return prev
        return setBlinds(prev, level)
      })
    }, 5000) // check every 5s
    return () => clearInterval(timer)
  }, [gameStartTime, gameStatus])

  useEffect(() => {
    if (gameStatus !== 'won' && gameStatus !== 'lost') {
      save({ gameState, gameStatus, gameStartTime })
    }
  }, [gameState, gameStatus, gameStartTime, save])

  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const humanWon = gameState.chips[0] > 0
      if (humanWon) sfx.play('win')
      setGameStatus(humanWon ? 'won' : 'lost')
      clear()
    }
  }, [gameState, clear])

  // Auto-run AI turns — 2s delay, shows decision text
  useEffect(() => {
    if (gameState.currentPlayer !== 0 && gameState.phase !== 'handOver' && gameState.phase !== 'gameOver' && gameState.phase !== 'showdown') {
      const timer = setTimeout(() => {
        setGameState(prev => {
          const next = aiAction(prev)
          setAiActionText(formatAction(next.lastAction))
          return next
        })
      }, 2000)
      return () => clearTimeout(timer)
    }
  }, [gameState.currentPlayer, gameState.phase])

  // Clear AI action text after 2s (so it shows while next AI "thinks")
  useEffect(() => {
    if (!aiActionText) return
    // Clear when it becomes the human's turn or hand is over
    if (gameState.currentPlayer === 0 || gameState.phase === 'handOver' || gameState.phase === 'gameOver') {
      const timer = setTimeout(() => setAiActionText(null), 2000)
      return () => clearTimeout(timer)
    }
  }, [aiActionText, gameState.currentPlayer, gameState.phase])

  // SFX when community cards are revealed
  useEffect(() => {
    if (gameState.community.length > 0) sfx.play('reveal')
  }, [gameState.community.length])

  // Update raise slider min
  useEffect(() => {
    const min = getMinRaise(gameState)
    setRaiseAmount(Math.min(min, gameState.chips[0] + gameState.bets[0]))
  }, [gameState.phase, gameState.currentBet])

  const handleFold = useCallback(() => { music.init(); sfx.init(); music.start(); sfx.play('fold'); setGameState(prev => fold(prev)) }, [])
  const handleCheck = useCallback(() => { music.init(); sfx.init(); music.start(); setGameState(prev => check(prev)) }, [])
  const handleCall = useCallback(() => { music.init(); sfx.init(); music.start(); sfx.play('bet'); setGameState(prev => call(prev)) }, [])
  const handleRaise = useCallback(() => {
    sfx.play('bet')
    setGameState(prev => raiseAction(prev, raiseAmount))
  }, [raiseAmount])
  const handleAllIn = useCallback(() => setGameState(prev => allIn(prev)), [])
  const handleNextHand = useCallback(() => { sfx.play('deal'); setGameState(prev => nextHand(prev)) }, [])
  const handleNewGame = useCallback(() => {
    setGameState(startHand(createTexasHoldemGame(4)))
    setGameStatus('playing')
    setAiActionText(null)
    setGameStartTime(Date.now())
    clear()
  }, [clear])

  const validActions = gameState.currentPlayer === 0 ? getValidActions(gameState) : []
  const toCall = gameState.currentBet - gameState.bets[0]
  const isPlayerTurn = gameState.currentPlayer === 0 && gameState.phase !== 'handOver' && gameState.phase !== 'gameOver'

  const controls = (
    <div className="flex items-center justify-between text-xs">
      <span className="text-slate-400">Pot: <span className="text-yellow-400 font-bold">{gameState.pot}</span></span>
      <span className="text-slate-400">Blinds: {gameState.smallBlind}/{gameState.bigBlind}</span>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Texas Hold'em" controls={controls}>
      <div className="relative flex flex-col items-center w-full max-w-xl space-y-3">
        {/* AI players */}
        <div className="flex gap-4 justify-center flex-wrap">
          {gameState.hands.slice(1).map((hand, i) => {
            const pi = i + 1
            const folded = gameState.foldedPlayers[pi]
            const isAllIn = gameState.allInPlayers[pi]
            const showCards = gameState.phase === 'handOver' && gameState.showdownResults && !folded
            const isDealer = gameState.dealerIdx === pi
            const isSB = gameState.sbIdx === pi
            const isBB = gameState.bbIdx === pi
            return (
              <div key={pi} className={`text-center ${folded ? 'opacity-40' : ''}`}>
                <div className="flex items-center justify-center gap-1 mb-0.5">
                  <span className="text-xs text-slate-400">
                    P{pi + 1}
                  </span>
                  {isDealer && <span className="text-[0.6rem] bg-white text-slate-900 font-bold rounded-full w-4 h-4 flex items-center justify-center">D</span>}
                  {isSB && <span className="text-[0.6rem] bg-blue-500 text-white font-bold rounded-full px-1">SB</span>}
                  {isBB && <span className="text-[0.6rem] bg-amber-500 text-white font-bold rounded-full px-1">BB</span>}
                  {isAllIn && <span className="text-[0.6rem] text-red-400">(All-In)</span>}
                  {folded && <span className="text-[0.6rem] text-slate-500">(Fold)</span>}
                </div>
                <div className="text-xs text-yellow-400">{gameState.chips[pi]}</div>
                <div className="flex gap-0.5 justify-center mt-1">
                  {hand.map((c, j) => (
                    <div key={j} className="w-10 h-14 sm:w-12 sm:h-[4rem]">
                      {showCards ? <CardFace card={c} /> : <CardBack />}
                    </div>
                  ))}
                </div>
                {gameState.bets[pi] > 0 && (
                  <span className="text-xs text-blue-400">Bet: {gameState.bets[pi]}</span>
                )}
              </div>
            )
          })}
        </div>

        {/* Community cards */}
        <div className="flex gap-1.5 justify-center min-h-[5.625rem]">
          {gameState.community.map((card, i) => (
            <div key={i} className={CARD_SIZE}>
              <CardFace card={card} />
            </div>
          ))}
          {Array.from({ length: 5 - gameState.community.length }).map((_, i) => (
            <div key={`e${i}`} className={`${CARD_SIZE} rounded-md border border-dashed border-slate-700/50`} />
          ))}
        </div>

        {/* AI action display */}
        {aiActionText && (
          <p className="text-sm text-blue-400 font-medium text-center">{aiActionText}</p>
        )}
        {gameState.currentPlayer !== 0 && gameState.phase !== 'handOver' && gameState.phase !== 'gameOver' && (
          <p className="text-xs text-slate-500 text-center animate-pulse">
            P{gameState.currentPlayer + 1} is thinking...
          </p>
        )}

        {/* Phase / status message */}
        <p className="text-sm text-white font-medium text-center">{gameState.message}</p>
        {gameState.showdownResults && gameState.phase === 'handOver' && (
          <div className="text-xs text-slate-400 text-center">
            {gameState.showdownResults.map((r, i) => (
              !gameState.foldedPlayers[i] && r.name !== 'Folded' ? (
                <div key={i}>{i === 0 ? 'You' : `P${i + 1}`}: {r.name}</div>
              ) : null
            ))}
          </div>
        )}

        {/* Player hand */}
        <div className="flex gap-2 justify-center">
          {gameState.hands[0].map((card, i) => (
            <div key={i} className={CARD_SIZE}>
              <CardFace card={card} />
            </div>
          ))}
        </div>
        <div className="flex items-center justify-center gap-1.5 text-xs text-slate-400">
          <span>You</span>
          {gameState.dealerIdx === 0 && <span className="text-[0.6rem] bg-white text-slate-900 font-bold rounded-full w-4 h-4 flex items-center justify-center">D</span>}
          {gameState.sbIdx === 0 && <span className="text-[0.6rem] bg-blue-500 text-white font-bold rounded-full px-1">SB</span>}
          {gameState.bbIdx === 0 && <span className="text-[0.6rem] bg-amber-500 text-white font-bold rounded-full px-1">BB</span>}
          <span>— Chips: <span className="text-white font-bold">{gameState.chips[0]}</span></span>
          {gameState.bets[0] > 0 && <span>Bet: <span className="text-blue-400">{gameState.bets[0]}</span></span>}
        </div>

        {/* Action buttons */}
        {isPlayerTurn && !gameState.foldedPlayers[0] && (
          <div className="flex flex-col items-center gap-2">
            <div className="flex gap-2 flex-wrap justify-center">
              {validActions.includes('fold') && (
                <button onClick={handleFold} className="px-3 py-1.5 bg-red-700 hover:bg-red-600 text-white rounded-lg text-sm transition-colors">
                  Fold
                </button>
              )}
              {validActions.includes('check') && (
                <button onClick={handleCheck} className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm transition-colors">
                  Check
                </button>
              )}
              {validActions.includes('call') && (
                <button onClick={handleCall} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm transition-colors">
                  Call {toCall}
                </button>
              )}
              {validActions.includes('raise') && (
                <button onClick={handleRaise} className="px-3 py-1.5 bg-green-700 hover:bg-green-600 text-white rounded-lg text-sm transition-colors">
                  Raise {raiseAmount}
                </button>
              )}
              {validActions.includes('allIn') && (
                <button onClick={handleAllIn} className="px-3 py-1.5 bg-yellow-700 hover:bg-yellow-600 text-white rounded-lg text-sm transition-colors">
                  All-In
                </button>
              )}
            </div>
            {validActions.includes('raise') && (
              <input
                type="range"
                min={getMinRaise(gameState)}
                max={gameState.chips[0] + gameState.bets[0]}
                step={gameState.bigBlind}
                value={raiseAmount}
                onChange={e => setRaiseAmount(Number(e.target.value))}
                className="w-48"
              />
            )}
          </div>
        )}

        {/* Hand over / New game */}
        <div className="flex gap-2 justify-center">
          {gameState.phase === 'handOver' && (
            <button
              onClick={handleNextHand}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Next Hand
            </button>
          )}
          {gameStatus === 'playing' && (
            <button
              onClick={handleNewGame}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-xs transition-colors"
            >
              New Game
            </button>
          )}
        </div>

        {(gameStatus === 'won' || gameStatus === 'lost') && (
          <GameOverModal
            status={gameStatus}
            score={gameState.chips[0]}
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
