/**
 * Race Mode Overlay — shows opponent status during race mode games.
 *
 * Displays whether the opponent is still playing, their score,
 * race result (won/lost/waiting), and level-up announcements.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { Trophy, Skull, Clock, Wifi, X, TrendingUp } from 'lucide-react'
import { gameSocket } from '../../../../services/gameSocket'

interface OpponentStatus {
  finished: boolean
  result?: 'win' | 'loss'
  score?: number
  level?: number | string
}

/** Transient level-up announcement from opponent. */
interface LevelAnnouncement {
  level: number | string
  label: string
  timestamp: number
}

export function useRaceMode(roomId: string, raceType: 'first_to_win' | 'last_to_lose') {
  const [opponentStatus, setOpponentStatus] = useState<OpponentStatus>({ finished: false })
  const [raceResult, setRaceResult] = useState<'won' | 'lost' | null>(null)
  const [localFinished, setLocalFinished] = useState(false)
  const [opponentLevelUp, setOpponentLevelUp] = useState<LevelAnnouncement | null>(null)

  // Refs to avoid stale closures in reportFinish
  const opponentStatusRef = useRef(opponentStatus)
  opponentStatusRef.current = opponentStatus
  const localFinishedRef = useRef(localFinished)
  localFinishedRef.current = localFinished

  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg) => {
      const action = msg.action
      if (!action) return

      if (action.type === 'race_status') {
        setOpponentStatus({ finished: false, score: action.score })
      }

      if (action.type === 'race_level_up') {
        const announcement: LevelAnnouncement = {
          level: action.level,
          label: action.label || `Level ${action.level}`,
          timestamp: Date.now(),
        }
        setOpponentLevelUp(announcement)
        setOpponentStatus(prev => ({ ...prev, level: action.level }))
      }

      if (action.type === 'race_finished') {
        const oppResult = action.result as 'win' | 'loss'
        setOpponentStatus({ finished: true, result: oppResult, score: action.score })

        // Determine race winner
        if (raceType === 'first_to_win' && oppResult === 'win' && !localFinishedRef.current) {
          setRaceResult('lost')
        }
        if (raceType === 'last_to_lose' && oppResult === 'loss' && !localFinishedRef.current) {
          setRaceResult('won')
        }
      }
    })
    return unsub
  }, [roomId, raceType])

  // Auto-dismiss level-up announcements after 3 seconds
  useEffect(() => {
    if (!opponentLevelUp) return
    const timer = setTimeout(() => setOpponentLevelUp(null), 3000)
    return () => clearTimeout(timer)
  }, [opponentLevelUp])

  const reportFinish = useCallback((result: 'win' | 'loss', score?: number) => {
    setLocalFinished(true)
    gameSocket.sendAction(roomId, { type: 'race_finished', result, score })

    const opp = opponentStatusRef.current
    if (raceType === 'first_to_win' && result === 'win' && !opp.finished) {
      setRaceResult('won')
    }
    if (raceType === 'first_to_win' && result === 'loss') {
      if (opp.finished && opp.result === 'win') {
        setRaceResult('lost')
      }
    }
    if (raceType === 'last_to_lose' && result === 'loss') {
      if (!opp.finished) {
        setRaceResult('lost')
      } else if (opp.result === 'loss') {
        setRaceResult('won')
      }
    }
  }, [roomId, raceType])

  const reportScore = useCallback((score: number) => {
    gameSocket.sendAction(roomId, { type: 'race_status', score })
  }, [roomId])

  /** Report a level-up to the opponent. label is the display text (e.g., "Level 5", "Reached 2048"). */
  const reportLevel = useCallback((level: number | string, label?: string) => {
    gameSocket.sendAction(roomId, {
      type: 'race_level_up',
      level,
      label: label || `Level ${level}`,
    })
  }, [roomId])

  return {
    opponentStatus, raceResult, localFinished, opponentLevelUp,
    reportFinish, reportScore, reportLevel,
  }
}

export function RaceOverlay({
  raceResult,
  opponentScore,
  opponentFinished,
  opponentLevelUp,
  onDismiss,
}: {
  raceResult: 'won' | 'lost' | null
  opponentScore?: number
  opponentFinished: boolean
  opponentLevelUp?: LevelAnnouncement | null
  onDismiss?: () => void
}) {
  // Race result banner
  if (raceResult) {
    return (
      <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60">
        <div className={`relative flex flex-col items-center gap-3 px-8 py-6 rounded-xl border ${
          raceResult === 'won'
            ? 'bg-green-900/90 border-green-500/50'
            : 'bg-red-900/90 border-red-500/50'
        }`}>
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="absolute top-2 right-2 text-slate-400 hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
          )}
          {raceResult === 'won' ? (
            <Trophy className="w-10 h-10 text-yellow-400" />
          ) : (
            <Skull className="w-10 h-10 text-red-400" />
          )}
          <span className={`text-2xl font-bold ${
            raceResult === 'won' ? 'text-green-300' : 'text-red-300'
          }`}>
            {raceResult === 'won' ? 'You Win the Race!' : 'You Lost the Race!'}
          </span>
        </div>
      </div>
    )
  }

  return (
    <>
      {/* Opponent level-up announcement toast */}
      {opponentLevelUp && (
        <div className="fixed top-12 right-2 z-30 flex items-center gap-2 px-3 py-2 bg-amber-900/90 border border-amber-500/50 rounded-lg text-xs animate-bounce">
          <TrendingUp className="w-3.5 h-3.5 text-amber-400" />
          <span className="text-amber-200 font-medium">
            Opponent: {opponentLevelUp.label}
          </span>
        </div>
      )}

      {/* Opponent status bar */}
      <div className="fixed top-2 right-2 z-30 flex items-center gap-2 px-3 py-1.5 bg-slate-800/90 border border-slate-600/50 rounded-lg text-xs">
        <Wifi className="w-3 h-3 text-green-400" />
        <span className="text-slate-400">Opponent:</span>
        {opponentFinished ? (
          <span className="text-yellow-400">Finished</span>
        ) : (
          <>
            <Clock className="w-3 h-3 text-blue-400 animate-pulse" />
            <span className="text-slate-300">Playing</span>
          </>
        )}
        {opponentScore !== undefined && (
          <span className="text-slate-300 font-mono">{opponentScore}</span>
        )}
      </div>
    </>
  )
}
