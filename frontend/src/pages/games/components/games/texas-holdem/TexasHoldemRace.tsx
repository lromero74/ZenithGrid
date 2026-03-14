/**
 * Texas Hold'em Race Mode — "first to double chips" multiplayer.
 *
 * Both players play their own AI table simultaneously.
 * First player to double their starting chips (reach 2000) wins the race.
 * If a player busts, they lose.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { GameLayout } from '../../GameLayout'
import { GameOverModal } from '../../GameOverModal'
import { CardFace } from '../../PlayingCard'
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
import { useRaceMode, RaceOverlay } from '../../multiplayer/RaceOverlay'

const RACE_TARGET = 2000 // double starting chips

interface TexasHoldemRaceProps {
  roomId: string
  players: number[]
  onLeave?: () => void
}

/** Format a lastAction string to use "P2/P3/P4" instead of "Player 1/2/3". */
function formatAction(action: string): string {
  return action.replace(/Player (\d+)/g, (_, n) => `P${Number(n) + 1}`)
}

export function TexasHoldemRace({ roomId, onLeave }: TexasHoldemRaceProps) {
  const { opponentStatus, raceResult, localScore, localFinished, opponentLevelUp, reportFinish, reportScore, leaveRoom } = useRaceMode(roomId, 'first_to_win')

  const song = useMemo(() => getSongForGame('texas-holdem'), [])
  const music = useGameMusic(song)
  const sfx = useGameSFX('texas-holdem')

  const [gameState, setGameState] = useState<TexasHoldemState>(() =>
    startHand(createTexasHoldemGame(4))
  )
  const [gameStatus, setGameStatus] = useState<GameStatus>('playing')
  const [raiseAmount, setRaiseAmount] = useState(40)
  const [aiActionText, setAiActionText] = useState<string | null>(null)
  const gameStartTime = useRef(Date.now())

  // Report chip count periodically
  useEffect(() => {
    const interval = setInterval(() => {
      if (gameStatus === 'playing') {
        reportScore(gameState.chips[0])
      }
    }, 2000)
    return () => clearInterval(interval)
  }, [reportScore, gameState.chips, gameStatus])

  // Blinds increase
  useEffect(() => {
    if (gameStatus !== 'playing') return
    const timer = setInterval(() => {
      const elapsed = Date.now() - gameStartTime.current
      const level = Math.floor(elapsed / (10 * 60 * 1000))
      setGameState(prev => {
        if (prev.blindLevel === level) return prev
        return setBlinds(prev, level)
      })
    }, 5000)
    return () => clearInterval(timer)
  }, [gameStatus])

  // Check race win condition: doubled chips
  useEffect(() => {
    if (gameStatus !== 'playing') return
    if (gameState.chips[0] >= RACE_TARGET && !localFinished) {
      sfx.play('win')
      setGameStatus('won')
      reportFinish('win', gameState.chips[0])
    }
  }, [gameState.chips, gameStatus, localFinished, reportFinish, sfx])

  // Check game over (busted)
  useEffect(() => {
    if (gameState.phase === 'gameOver') {
      const humanWon = gameState.chips[0] > 0
      if (!humanWon && !localFinished) {
        setGameStatus('lost')
        reportFinish('loss', gameState.chips[0])
      }
    }
  }, [gameState, localFinished, reportFinish])

  // Auto-run AI turns
  useEffect(() => {
    if (gameState.currentPlayer !== 0 && gameState.phase !== 'handOver' && gameState.phase !== 'gameOver' && gameState.phase !== 'showdown') {
      const timer = setTimeout(() => {
        setGameState(prev => {
          const next = aiAction(prev)
          setAiActionText(formatAction(next.lastAction))
          return next
        })
      }, 1500)
      return () => clearTimeout(timer)
    }
  }, [gameState.currentPlayer, gameState.phase])

  // Clear AI action text
  useEffect(() => {
    if (!aiActionText) return
    if (gameState.currentPlayer === 0 || gameState.phase === 'handOver' || gameState.phase === 'gameOver') {
      const timer = setTimeout(() => setAiActionText(null), 2000)
      return () => clearTimeout(timer)
    }
  }, [aiActionText, gameState.currentPlayer, gameState.phase])

  const validActions = gameState.currentPlayer === 0 ? getValidActions(gameState) : []
  const minRaise = getMinRaise(gameState)

  const handleAction = useCallback((actionFn: (s: TexasHoldemState, ...args: any[]) => TexasHoldemState, ...args: any[]) => {
    music.init()
    sfx.init()
    music.start()
    sfx.play('chip')
    setGameState(prev => actionFn(prev, ...args))
  }, [music, sfx])

  const handleNextHand = useCallback(() => {
    sfx.play('shuffle')
    setGameState(prev => startHand(nextHand(prev)))
  }, [sfx])

  const chipProgress = Math.min(100, Math.round((gameState.chips[0] / RACE_TARGET) * 100))

  const controls = (
    <div className="flex items-center justify-between text-xs">
      <div className="flex items-center gap-2">
        <span className="text-slate-400">Race to {RACE_TARGET} chips!</span>
        <div className="w-24 h-2 bg-slate-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-green-500 transition-all"
            style={{ width: `${chipProgress}%` }}
          />
        </div>
        <span className="text-green-400 font-mono">{gameState.chips[0]}</span>
      </div>
      <MusicToggle music={music} sfx={sfx} />
    </div>
  )

  return (
    <GameLayout title="Texas Hold'em — Race" controls={controls}>
      <div className="relative flex flex-col items-center gap-3">
        <RaceOverlay
          raceResult={raceResult}
          localScore={localScore}
        opponentScore={opponentStatus.score}
          opponentFinished={opponentStatus.finished}
          opponentLevelUp={opponentLevelUp}
          onDismiss={onLeave}
        onBackToLobby={onLeave}
        onLeaveGame={leaveRoom}
        />

        {/* Community cards */}
        <div className="flex gap-1 items-center min-h-[60px]">
          {gameState.community.map((card, i) => (
            <CardFace key={i} card={card} />
          ))}
          {Array.from({ length: 5 - gameState.community.length }).map((_, i) => (
            <div key={`empty-${i}`} className="w-10 h-14 border border-dashed border-slate-600/30 rounded" />
          ))}
        </div>

        {/* Pot */}
        <div className="text-xs text-yellow-400">Pot: {gameState.pot}</div>

        {/* AI action text */}
        {aiActionText && (
          <div className="text-xs text-slate-400 italic">{aiActionText}</div>
        )}

        {/* Player's hole cards */}
        <div className="flex gap-1">
          {gameState.hands[0]?.map((card, i) => (
            <CardFace key={i} card={card} />
          ))}
        </div>

        {/* Player chips */}
        <div className="text-xs text-slate-300">
          Your chips: <span className="text-green-400 font-mono">{gameState.chips[0]}</span>
          {' | '}Bet: <span className="text-yellow-400">{gameState.bets[0]}</span>
        </div>

        {/* Action buttons */}
        {gameState.currentPlayer === 0 && gameStatus === 'playing' && (
          <div className="flex gap-2 flex-wrap justify-center">
            {validActions.includes('fold') && (
              <button onClick={() => handleAction(fold)} className="px-3 py-1.5 bg-red-700/50 hover:bg-red-600/50 text-red-300 rounded text-xs">
                Fold
              </button>
            )}
            {validActions.includes('check') && (
              <button onClick={() => handleAction(check)} className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded text-xs">
                Check
              </button>
            )}
            {validActions.includes('call') && (
              <button onClick={() => handleAction(call)} className="px-3 py-1.5 bg-green-700/50 hover:bg-green-600/50 text-green-300 rounded text-xs">
                Call {gameState.currentBet - gameState.bets[0]}
              </button>
            )}
            {validActions.includes('raise') && (
              <div className="flex items-center gap-1">
                <button onClick={() => handleAction(raiseAction, raiseAmount)} className="px-3 py-1.5 bg-blue-700/50 hover:bg-blue-600/50 text-blue-300 rounded text-xs">
                  Raise {raiseAmount}
                </button>
                <input
                  type="range"
                  min={minRaise}
                  max={gameState.chips[0]}
                  value={raiseAmount}
                  onChange={e => setRaiseAmount(Number(e.target.value))}
                  className="w-20 h-1"
                />
              </div>
            )}
            {validActions.includes('allIn') && (
              <button onClick={() => handleAction(allIn)} className="px-3 py-1.5 bg-yellow-700/50 hover:bg-yellow-600/50 text-yellow-300 rounded text-xs">
                All In
              </button>
            )}
          </div>
        )}

        {/* Next hand */}
        {gameState.phase === 'handOver' && gameStatus === 'playing' && (
          <button onClick={handleNextHand} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm">
            Next Hand
          </button>
        )}

        {(gameStatus === 'won' || gameStatus === 'lost') && !raceResult && (
          <GameOverModal
            status={gameStatus}
            score={gameState.chips[0]}
            onPlayAgain={() => {}}
            music={music}
            sfx={sfx}
          />
        )}
      </div>
    </GameLayout>
  )
}
