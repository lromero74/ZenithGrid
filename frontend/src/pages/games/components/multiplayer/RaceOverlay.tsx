/**
 * Race Mode Overlay — shows opponent status during race mode games.
 *
 * Displays whether the opponent is still playing, their score,
 * race result (won/lost/waiting), and level-up announcements.
 *
 * Race types:
 * - first_to_win: First player to beat the AI wins immediately
 * - survival: Last player alive wins (first to die loses)
 * - best_score: Both play until done; highest score/level wins
 *
 * Features:
 * - Play On mode: losers can keep playing after the winner is determined
 * - Spectator State: games can broadcast visual state for spectators
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { Trophy, Skull, Clock, Wifi, TrendingUp, Eye, WifiOff, Pause, ChevronLeft, ChevronRight } from 'lucide-react'
import { gameSocket } from '../../../../services/gameSocket'
import { useAuth } from '../../../../contexts/AuthContext'

// Fallback value — server sends authoritative `reconnectWindowSeconds` in disconnect message
const RECONNECT_WINDOW_SECONDS = 60

interface OpponentStatus {
  finished: boolean
  result?: 'win' | 'loss'
  score?: number
  level?: number | string
  /** How the opponent exited: normal finish, forfeit, or disconnect (abend). */
  exitType?: 'completed' | 'forfeit' | 'abend'
}

/** Transient level-up announcement from opponent. */
interface LevelAnnouncement {
  level: number | string
  label: string
  timestamp: number
}

export type RaceType = 'first_to_win' | 'survival' | 'best_score'

interface RaceModeOptions {
  allowPlayOn?: boolean
  /** Require both players to ready up, then 3-2-1 countdown before game starts. */
  syncStart?: boolean
}

export function useRaceMode(roomId: string, raceType: RaceType, options?: RaceModeOptions) {
  const { user } = useAuth()
  const allowPlayOn = options?.allowPlayOn ?? false
  const syncStart = options?.syncStart ?? false

  const [opponentStatus, setOpponentStatus] = useState<OpponentStatus>({ finished: false })
  const [raceResult, setRaceResult] = useState<'won' | 'lost' | 'tied' | null>(null)
  const [localFinished, setLocalFinished] = useState(false)
  const [opponentLevelUp, setOpponentLevelUp] = useState<LevelAnnouncement | null>(null)
  const [playOnActive, setPlayOnActive] = useState(false)
  /** Per-player visual state for spectating (keyed by playerId). */
  const [playerStates, setPlayerStates] = useState<Record<number, any>>({})
  /** Which player the spectator is currently watching (playerId). */
  const [spectateTarget, setSpectateTarget] = useState<number | null>(null)
  const [opponentDisconnected, setOpponentDisconnected] = useState(false)
  /** Countdown seconds remaining for opponent to reconnect (null = not paused). */
  const [reconnectCountdown, setReconnectCountdown] = useState<number | null>(null)
  /** Whether we (the local player) are currently disconnected. */
  const [selfDisconnected, setSelfDisconnected] = useState(!gameSocket.connected)

  /** Deferred result — set when local player finishes but we want spectator flow first. */
  const [pendingResult, setPendingResult] = useState<'won' | 'lost' | 'tied' | null>(null)

  // Sync-start state
  const [localReady, setLocalReady] = useState(false)
  const [opponentReady, setOpponentReady] = useState(false)
  const [countdownValue, setCountdownValue] = useState<number | null>(null)
  const [gameSeed, setGameSeed] = useState<number | null>(null)
  /** True when the game can begin accepting input (immediately if no syncStart). */
  const [gameStarted, setGameStarted] = useState(!syncStart)

  // Refs to avoid stale closures in reportFinish
  const opponentStatusRef = useRef(opponentStatus)
  opponentStatusRef.current = opponentStatus
  const localFinishedRef = useRef(localFinished)
  const raceResultRef = useRef(raceResult)
  raceResultRef.current = raceResult
  localFinishedRef.current = localFinished
  const localScoreRef = useRef<number | undefined>(undefined)
  const allowPlayOnRef = useRef(allowPlayOn)
  allowPlayOnRef.current = allowPlayOn

  /** When allowPlayOn is true, defer showing the full result overlay. */
  const setRaceResultWithPlayOn = useCallback((result: 'won' | 'lost' | 'tied') => {
    setRaceResult(result)
    if (allowPlayOnRef.current && result !== 'tied') {
      setPlayOnActive(true)
    }
  }, [])

  useEffect(() => {
    const unsub = gameSocket.on('game:action', (msg) => {
      const action = msg.action
      if (!action) return
      // Filter self-echoes — the backend broadcasts game:action to all players
      // including the sender. Without this, our own race_finished message gets
      // re-processed as if the opponent sent it.
      if (msg.playerId === user?.id) return

      // Sync-start actions
      if (action.type === 'race_ready') {
        setOpponentReady(true)
      }
      if (action.type === 'race_countdown') {
        setGameSeed(action.seed as number)
        setCountdownValue(3)
      }

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
        const oppScore = action.score as number | undefined
        setOpponentStatus({ finished: true, result: oppResult, score: oppScore })

        // Determine race winner based on type
        if (raceType === 'first_to_win' && oppResult === 'win' && !localFinishedRef.current) {
          setRaceResultWithPlayOn('lost')
        }
        if (raceType === 'survival' && oppResult === 'loss' && !localFinishedRef.current) {
          // Opponent died while we're still alive — we win
          setRaceResultWithPlayOn('won')
        }
        if (raceType === 'survival' && oppResult === 'loss' && localFinishedRef.current) {
          // We were spectating (died first), opponent just died too — finalize our loss.
          // Guard: don't overwrite a 'won' result (near-simultaneous deaths can race).
          if (raceResultRef.current !== 'won') {
            setRaceResult('lost')
            setPendingResult(null)
          }
        }
        if (raceType === 'best_score' && localFinishedRef.current) {
          // Both done now — compare scores
          resolveHighestScore(localScoreRef.current, oppScore)
        }
      }
    })
    return unsub
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomId, raceType, setRaceResultWithPlayOn, user?.id])

  // Listen for forfeit, disconnect, and reconnect events
  useEffect(() => {
    const unsubForfeit = gameSocket.on('game:player_forfeit', (_msg) => {
      // Opponent forfeited — they lose, we win
      setOpponentStatus({ finished: true, result: 'loss', exitType: 'forfeit' })
      if (!localFinishedRef.current) {
        setRaceResultWithPlayOn('won')
      }
    })
    const unsubDisconnect = gameSocket.on('game:player_disconnect', (msg) => {
      // Opponent disconnected — game paused, start reconnect countdown
      setOpponentDisconnected(true)
      setOpponentStatus(prev => ({ ...prev, exitType: 'abend' }))
      const window = msg.reconnectWindowSeconds ?? RECONNECT_WINDOW_SECONDS
      setReconnectCountdown(window)
    })
    const unsubReconnect = gameSocket.on('game:player_reconnected', (_msg) => {
      // Opponent reconnected — resume game
      setOpponentDisconnected(false)
      setReconnectCountdown(null)
      setOpponentStatus(prev => {
        const { exitType: _, ...rest } = prev
        return rest
      })
    })
    return () => { unsubForfeit(); unsubDisconnect(); unsubReconnect() }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomId, setRaceResultWithPlayOn])

  // Reconnect countdown timer
  useEffect(() => {
    if (reconnectCountdown === null || reconnectCountdown <= 0) return
    const timer = setTimeout(() => {
      setReconnectCountdown(prev => (prev !== null && prev > 0) ? prev - 1 : null)
    }, 1000)
    return () => clearTimeout(timer)
  }, [reconnectCountdown])

  // Track own connection state — debounce disconnect to avoid flash
  // during brief reconnection cycles
  useEffect(() => {
    let disconnectTimer: ReturnType<typeof setTimeout> | null = null
    const unsub = gameSocket.on('connection', (msg) => {
      if (msg.connected) {
        // Reconnected — clear any pending disconnect and immediately show connected
        if (disconnectTimer) { clearTimeout(disconnectTimer); disconnectTimer = null }
        setSelfDisconnected(false)
      } else {
        // Disconnected — wait 1.5s before showing overlay to avoid flash
        disconnectTimer = setTimeout(() => {
          setSelfDisconnected(true)
          disconnectTimer = null
        }, 1500)
      }
    })
    return () => { unsub(); if (disconnectTimer) clearTimeout(disconnectTimer) }
  }, [])

  // Listen for spectator state from all players
  useEffect(() => {
    const unsub = gameSocket.on('game:player_state', (msg) => {
      if (msg.state && msg.playerId) {
        setPlayerStates(prev => ({ ...prev, [msg.playerId]: msg.state }))
        // Auto-select first available spectate target
        setSpectateTarget(prev => prev ?? msg.playerId)
      }
    })
    return unsub
  }, [roomId])

  function resolveHighestScore(myScore: number | undefined, oppScore: number | undefined) {
    const mine = myScore ?? 0
    const theirs = oppScore ?? 0
    if (mine > theirs) setRaceResultWithPlayOn('won')
    else if (theirs > mine) setRaceResultWithPlayOn('lost')
    else {
      setRaceResult('tied')
      // Ties don't activate play-on
    }
  }

  // Auto-dismiss level-up announcements after 3 seconds
  useEffect(() => {
    if (!opponentLevelUp) return
    const timer = setTimeout(() => setOpponentLevelUp(null), 3000)
    return () => clearTimeout(timer)
  }, [opponentLevelUp])

  const reportFinish = useCallback((result: 'win' | 'loss', score?: number) => {
    setLocalFinished(true)
    localScoreRef.current = score
    gameSocket.sendAction(roomId, { type: 'race_finished', result, score })

    const opp = opponentStatusRef.current

    if (raceType === 'first_to_win') {
      if (result === 'win' && !opp.finished) {
        setRaceResultWithPlayOn('won')
      }
      if (result === 'loss' && opp.finished && opp.result === 'win') {
        setRaceResultWithPlayOn('lost')
      }
    }

    if (raceType === 'survival' && result === 'loss') {
      if (!opp.finished) {
        // I died first, opponent still playing — defer result for spectator flow
        setPendingResult('lost')
      } else if (opp.result === 'loss') {
        // Both dead — whoever died second wins (that's me, since opp already finished)
        setRaceResultWithPlayOn('won')
      }
    }

    if (raceType === 'best_score') {
      if (opp.finished) {
        // Both done — compare
        resolveHighestScore(score, opp.score)
      }
      // Otherwise wait for opponent to finish
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomId, raceType, setRaceResultWithPlayOn])

  const reportScore = useCallback((score: number) => {
    gameSocket.sendAction(roomId, { type: 'race_status', score })
  }, [roomId])

  /** Report a level-up to the opponent. label is the display text (e.g., "Level 5", "Snake length: 12"). */
  const reportLevel = useCallback((level: number | string, label?: string) => {
    gameSocket.sendAction(roomId, {
      type: 'race_level_up',
      level,
      label: label || `Level ${level}`,
    })
  }, [roomId])

  /** Intentionally forfeit the game — counts as a loss in scoring/tournaments. */
  const forfeit = useCallback(() => {
    gameSocket.send({ type: 'game:forfeit', roomId })
    setLocalFinished(true)
    setRaceResult('lost')
  }, [roomId])

  /** Leave the room individually (e.g. spectating loser exits mid-game without disrupting opponent). */
  const leaveRoom = useCallback(() => {
    gameSocket.send({ type: 'game:leave', roomId })
  }, [roomId])

  /** Broadcast visual game state for spectators. Sends immediately. */
  const broadcastState = useCallback((state: object) => {
    gameSocket.sendState(roomId, state)
  }, [roomId])

  /**
   * Throttled state broadcast for real-time games (arcade, etc.).
   * Limits sends to at most once per `intervalMs` (default 500ms).
   * Event-driven games should use `broadcastState` directly instead.
   */
  const lastBroadcastRef = useRef(0)
  const throttledBroadcast = useCallback((state: object, intervalMs = 500) => {
    const now = Date.now()
    if (now - lastBroadcastRef.current >= intervalMs) {
      lastBroadcastRef.current = now
      gameSocket.sendState(roomId, state)
    }
  }, [roomId])

  /** Dismiss play-on mode and show final results. */
  const dismissPlayOn = useCallback(() => {
    setPlayOnActive(false)
  }, [])

  /** Finalize a pending/deferred result (e.g., after spectating). */
  const finalizeResult = useCallback(() => {
    if (pendingResult) {
      setRaceResult(pendingResult)
      setPendingResult(null)
    }
  }, [pendingResult])

  // isSpectating: local player finished but race isn't over yet (others still playing)
  const isSpectating = localFinished && (playOnActive || (raceResult === 'lost' && !opponentStatus.finished))

  // Backwards-compat: spectatorState = state of the currently-watched player
  const spectatorState = spectateTarget !== null ? playerStates[spectateTarget] ?? null : null

  // List of active player IDs that can be spectated (have sent state recently)
  const spectatablePlayers = useMemo(() => {
    return Object.keys(playerStates).map(Number)
  }, [playerStates, spectateTarget])

  /** Page to the next spectate target. */
  const spectateNext = useCallback(() => {
    if (spectatablePlayers.length <= 1) return
    const idx = spectatablePlayers.indexOf(spectateTarget ?? 0)
    const next = (idx + 1) % spectatablePlayers.length
    setSpectateTarget(spectatablePlayers[next])
  }, [spectatablePlayers, spectateTarget])

  /** Page to the previous spectate target. */
  const spectatePrev = useCallback(() => {
    if (spectatablePlayers.length <= 1) return
    const idx = spectatablePlayers.indexOf(spectateTarget ?? 0)
    const prev = (idx - 1 + spectatablePlayers.length) % spectatablePlayers.length
    setSpectateTarget(spectatablePlayers[prev])
  }, [spectatablePlayers, spectateTarget])

  // ── Sync-start: ready-up and countdown ──────────────────────────────

  /** Signal that the local player is ready. Host triggers countdown when both ready. */
  const sendReady = useCallback(() => {
    setLocalReady(true)
    gameSocket.sendAction(roomId, { type: 'race_ready' })
  }, [roomId])

  // Host: when both players are ready, generate seed and broadcast countdown
  useEffect(() => {
    if (!syncStart || !localReady || !opponentReady) return
    // Only host triggers — host is always players[0], but we don't have players here.
    // Instead, use a tie-breaker: lower user ID triggers. Both will get the countdown.
    // Actually, simpler: both set opponentReady, but only the one who RECEIVES
    // race_ready (i.e., the other player was already ready) triggers.
    // The cleanest approach: check if countdownValue is already set (from receiving race_countdown).
    if (countdownValue !== null) return
    // Generate seed and broadcast countdown
    const seed = Math.floor(Math.random() * 0xFFFFFFFF)
    setGameSeed(seed)
    setCountdownValue(3)
    gameSocket.sendAction(roomId, { type: 'race_countdown', seed })
  }, [syncStart, localReady, opponentReady, countdownValue, roomId])

  // Countdown timer: 3 → 2 → 1 → 0 (game starts)
  useEffect(() => {
    if (countdownValue === null || countdownValue <= 0) return
    const timer = setTimeout(() => {
      setCountdownValue(prev => (prev !== null && prev > 0) ? prev - 1 : null)
    }, 1000)
    return () => clearTimeout(timer)
  }, [countdownValue])

  // When countdown reaches 0, start the game
  useEffect(() => {
    if (countdownValue === 0 && !gameStarted) {
      setGameStarted(true)
      // Clear countdown display after a brief "GO!" moment
      const timer = setTimeout(() => setCountdownValue(null), 600)
      return () => clearTimeout(timer)
    }
  }, [countdownValue, gameStarted])

  // Track active room for auto-rejoin on reconnect
  useEffect(() => {
    gameSocket.setActiveRoom(roomId)
    return () => { gameSocket.setActiveRoom(null) }
  }, [roomId])

  return {
    opponentStatus, raceResult, localFinished, opponentLevelUp, opponentDisconnected,
    reconnectCountdown, selfDisconnected, pendingResult,
    reportFinish, reportScore, reportLevel, forfeit, finalizeResult, leaveRoom,
    playOnActive, isSpectating, spectatorState, playerStates, spectateTarget, spectatablePlayers,
    spectateNext, spectatePrev, broadcastState, throttledBroadcast, dismissPlayOn,
    // Sync-start
    gameStarted, countdownValue, gameSeed, localReady, sendReady,
  }
}

/** Spectator bar — shown when the local player is eliminated and others are still playing. */
export function SpectatorBar({
  spectateTarget,
  spectatablePlayers,
  playerNames,
  onPrev,
  onNext,
  onDismiss,
}: {
  spectateTarget: number | null
  spectatablePlayers: number[]
  playerNames?: Record<number, string>
  onPrev: () => void
  onNext: () => void
  onDismiss?: () => void
}) {
  if (spectatablePlayers.length === 0) return null

  const targetName = spectateTarget !== null
    ? (playerNames?.[spectateTarget] ?? `Player ${spectateTarget}`)
    : 'Unknown'
  const idx = spectatablePlayers.indexOf(spectateTarget ?? 0)
  const showPaging = spectatablePlayers.length > 1

  return (
    <div className="fixed top-2 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 px-3 py-2 bg-indigo-900/90 border border-indigo-500/50 rounded-lg text-sm">
      <Eye className="w-4 h-4 text-indigo-300 shrink-0" />
      {showPaging && (
        <button onClick={onPrev} className="p-0.5 hover:bg-indigo-700 rounded transition-colors">
          <ChevronLeft className="w-4 h-4 text-indigo-300" />
        </button>
      )}
      <span className="text-indigo-200">
        Spectating: <span className="font-medium text-white">{targetName}</span>
        {showPaging && (
          <span className="text-indigo-400 ml-1 text-xs">({idx + 1}/{spectatablePlayers.length})</span>
        )}
      </span>
      {showPaging && (
        <button onClick={onNext} className="p-0.5 hover:bg-indigo-700 rounded transition-colors">
          <ChevronRight className="w-4 h-4 text-indigo-300" />
        </button>
      )}
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="ml-2 px-2.5 py-1 text-xs bg-indigo-700 hover:bg-indigo-600 text-white rounded transition-colors"
        >
          Leave
        </button>
      )}
    </div>
  )
}

/** Countdown overlay — 3-2-1-GO! shown during sync start. */
export function CountdownOverlay({
  countdownValue,
  localReady,
  onReady,
  onLeave,
  onBackToLobby,
}: {
  countdownValue: number | null
  localReady: boolean
  onReady: () => void
  /** Fully leave the game (navigate away). */
  onLeave?: () => void
  /** Return to room lobby without destroying the room. */
  onBackToLobby?: () => void
}) {
  // Before ready: show Ready button
  if (!localReady) {
    return (
      <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/60">
        <div className="flex flex-col items-center gap-4">
          <button
            onClick={onReady}
            className="px-10 py-4 text-2xl font-bold rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white transition-all animate-pulse shadow-lg shadow-emerald-900/50"
          >
            Ready!
          </button>
          <span className="text-sm text-slate-400">Press when you're ready to start</span>
          <div className="flex items-center gap-4 mt-2">
            {onBackToLobby && (
              <button onClick={onBackToLobby} className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors">
                Back to Lobby
              </button>
            )}
            {onLeave && (
              <button onClick={onLeave} className="text-xs text-slate-500 hover:text-slate-300 transition-colors">
                Leave game
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  // Ready but waiting for opponent
  if (countdownValue === null) {
    return (
      <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/60">
        <div className="flex flex-col items-center gap-3">
          <Clock className="w-8 h-8 text-amber-400 animate-spin" />
          <span className="text-lg font-medium text-white">Waiting for opponent...</span>
          <div className="flex items-center gap-4 mt-2">
            {onBackToLobby && (
              <button onClick={onBackToLobby} className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors">
                Back to Lobby
              </button>
            )}
            {onLeave && (
              <button onClick={onLeave} className="text-xs text-slate-500 hover:text-slate-300 transition-colors">
                Leave game
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  // Countdown: 3, 2, 1, GO!
  const label = countdownValue > 0 ? String(countdownValue) : 'GO!'
  const color = countdownValue > 0 ? 'text-white' : 'text-emerald-400'
  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/60">
      <span
        key={countdownValue}
        className={`text-8xl font-black ${color} animate-ping`}
        style={{ animationDuration: '0.6s', animationIterationCount: 1 }}
      >
        {label}
      </span>
    </div>
  )
}

export function RaceOverlay({
  // Core race state
  raceResult,
  opponentScore,
  opponentFinished,
  opponentLevelUp,
  opponentName,
  onDismiss,
  // Play-on props
  playOnActive,
  isLoser,
  onDismissPlayOn,
  // Connection props
  opponentDisconnected,
  reconnectCountdown,
  selfDisconnected,
  // Spectator props — pass these to enable spectate-or-leave on elimination
  localFinished,
  spectatablePlayers,
  spectateTarget,
  playerNames,
  onSpectatePrev,
  onSpectateNext,
  onLeaveGame,
  onBackToLobby,
}: {
  // -- Core race state --
  raceResult: 'won' | 'lost' | 'tied' | null
  opponentScore?: number
  opponentFinished: boolean
  opponentLevelUp?: LevelAnnouncement | null
  opponentName?: string
  onDismiss?: () => void
  // -- Play-on props --
  playOnActive?: boolean
  isLoser?: boolean
  onDismissPlayOn?: () => void
  // -- Connection props --
  opponentDisconnected?: boolean
  onForfeit?: () => void
  reconnectCountdown?: number | null
  selfDisconnected?: boolean
  // -- Spectator props --
  localFinished?: boolean
  spectatablePlayers?: number[]
  spectateTarget?: number | null
  playerNames?: Record<number, string>
  onSpectatePrev?: () => void
  onSpectateNext?: () => void
  /** Called when a spectating player wants to leave mid-game (individual leave, doesn't reset room). */
  onLeaveGame?: () => void
  /** Return to room lobby without destroying the room (for rematch). */
  onBackToLobby?: () => void
}) {
  const [spectateMode, setSpectateMode] = useState(false)
  /** Whether the initial skull/loss overlay has been dismissed (transitions to spectate choice). */
  const [skullDismissed, setSkullDismissed] = useState(false)
  /** Brief win toast shown to winner who is still playing — auto-dismisses */
  const [winToastVisible, setWinToastVisible] = useState(false)

  // Reset spectate mode and skull when race result arrives
  useEffect(() => {
    if (raceResult) { setSpectateMode(false); setSkullDismissed(false) }
    // Show auto-dismiss toast for winner still playing
    if (raceResult === 'won' && !localFinished) {
      setWinToastVisible(true)
      const timer = setTimeout(() => setWinToastVisible(false), 3000)
      return () => clearTimeout(timer)
    }
  }, [raceResult, localFinished])
  // Self-disconnected overlay — shown when we lose connection
  if (selfDisconnected) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
        <div className="flex flex-col items-center gap-4 px-8 py-6 bg-slate-800/95 border border-slate-600/50 rounded-xl max-w-sm text-center">
          <WifiOff className="w-10 h-10 text-red-400 animate-pulse" />
          <span className="text-lg font-bold text-white">Connection Lost</span>
          <span className="text-sm text-slate-300">
            Reconnecting automatically... Your game is paused and waiting for you.
          </span>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Clock className="w-3.5 h-3.5 animate-spin" />
            <span>Attempting to reconnect</span>
          </div>
        </div>
      </div>
    )
  }

  // Opponent disconnected — game paused with reconnect countdown
  if (opponentDisconnected && !raceResult) {
    const timeLeft = reconnectCountdown ?? 0
    const expired = timeLeft <= 0
    return (
      <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/50">
        <div className="flex flex-col items-center gap-4 px-8 py-6 bg-slate-800/95 border border-slate-600/50 rounded-xl max-w-sm text-center">
          <Pause className="w-10 h-10 text-amber-400" />
          <span className="text-lg font-bold text-white">Game Paused</span>
          {expired ? (
            <>
              <span className="text-sm text-slate-300">
                {opponentName || 'Opponent'} did not reconnect in time.
                No result recorded — the game is abandoned.
              </span>
              {onDismiss && (
                <button
                  onClick={onDismiss}
                  className="px-4 py-2 text-sm bg-slate-600 hover:bg-slate-500 text-white rounded-lg transition-colors"
                >
                  Back to Lobby
                </button>
              )}
            </>
          ) : (
            <>
              <span className="text-sm text-slate-300">
                {opponentName || 'Opponent'} lost connection.
                Waiting for them to reconnect...
              </span>
              <div className="flex items-center gap-2 px-4 py-2 bg-slate-700/80 rounded-lg">
                <Clock className="w-4 h-4 text-amber-400" />
                <span className="text-2xl font-mono font-bold text-amber-300">{timeLeft}s</span>
              </div>
              <span className="text-xs text-slate-500">
                Game will be abandoned if opponent doesn't reconnect
              </span>
            </>
          )}
        </div>
      </div>
    )
  }

  // Elimination spectator flow: player finished, race not over yet
  // Show skull immediately — don't gate on hasSpectatorProps
  const hasSpectatorProps = spectatablePlayers !== undefined && spectatablePlayers.length > 0
  const showSkullOverlay = localFinished && !raceResult && !skullDismissed
  // After skull dismissed, auto-enter spectate mode once data arrives
  const readyToSpectate = localFinished && !raceResult && skullDismissed && !spectateMode && hasSpectatorProps
  const showSpectatorBar = spectateMode && !raceResult

  // Auto-enter spectate mode once spectator data is available after skull dismissal
  useEffect(() => {
    if (readyToSpectate) {
      setSpectateMode(true)
    }
  }, [readyToSpectate])

  // Step 1: Skull result — "You Lost!" with a dismiss button
  if (showSkullOverlay) {
    return (
      <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/60">
        <div className="flex flex-col items-center gap-3 px-8 py-6 bg-red-900/90 border border-red-500/50 rounded-xl max-w-sm text-center">
          <Skull className="w-10 h-10 text-red-400" />
          <span className="text-2xl font-bold text-red-300">You Lost!</span>
          <button
            onClick={() => setSkullDismissed(true)}
            className="mt-2 px-5 py-2 text-sm font-medium rounded-lg bg-slate-700 hover:bg-slate-600 text-white transition-colors"
          >
            Continue
          </button>
        </div>
      </div>
    )
  }

  // Step 2: Waiting for spectator data after skull dismissed (before spectateMode kicks in)
  if (localFinished && !raceResult && skullDismissed && !spectateMode) {
    return (
      <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/60">
        <div className="flex flex-col items-center gap-4 px-8 py-6 bg-slate-800/95 border border-slate-600/50 rounded-xl max-w-sm text-center">
          <Eye className="w-10 h-10 text-indigo-400" />
          <span className="text-lg font-bold text-white">Other players are still going</span>
          <span className="text-sm text-slate-300">Loading spectator view...</span>
          {onLeaveGame && (
            <button
              onClick={onLeaveGame}
              className="px-4 py-2 text-sm bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
            >
              Leave
            </button>
          )}
        </div>
      </div>
    )
  }

  if (showSpectatorBar) {
    return (
      <SpectatorBar
        spectateTarget={spectateTarget ?? null}
        spectatablePlayers={spectatablePlayers ?? []}
        playerNames={playerNames}
        onPrev={onSpectatePrev ?? (() => {})}
        onNext={onSpectateNext ?? (() => {})}
        onDismiss={onLeaveGame ?? onDismiss}
      />
    )
  }

  // Play-on mode: winner spectating the loser
  if (playOnActive && raceResult && !isLoser) {
    return (
      <>
        {/* Spectator bar for the winner */}
        <div className="fixed top-2 left-1/2 -translate-x-1/2 z-40 flex items-center gap-3 px-4 py-2 bg-indigo-900/90 border border-indigo-500/50 rounded-lg text-sm">
          <Eye className="w-4 h-4 text-indigo-300" />
          <span className="text-indigo-200">
            You won! Watching {opponentName || 'opponent'} play...
          </span>
          {onDismissPlayOn && (
            <button
              onClick={onDismissPlayOn}
              className="ml-2 px-2.5 py-1 text-xs bg-indigo-700 hover:bg-indigo-600 text-white rounded transition-colors"
            >
              View Final Results
            </button>
          )}
        </div>

        {/* Still show opponent score if available */}
        {opponentScore !== undefined && (
          <div className="fixed top-2 right-2 z-30 flex items-center gap-2 px-3 py-1.5 bg-slate-800/90 border border-slate-600/50 rounded-lg text-xs">
            <Wifi className="w-3 h-3 text-green-400" />
            <span className="text-slate-400">Opponent score:</span>
            <span className="text-slate-300 font-mono">{opponentScore}</span>
          </div>
        )}
      </>
    )
  }

  // Play-on mode: loser still playing
  if (playOnActive && raceResult && isLoser) {
    return (
      <>
        {/* Non-blocking banner for the loser */}
        <div className="fixed top-2 left-1/2 -translate-x-1/2 z-40 flex items-center gap-3 px-4 py-2 bg-amber-900/90 border border-amber-500/50 rounded-lg text-sm">
          <Trophy className="w-4 h-4 text-amber-400" />
          <span className="text-amber-200">
            {opponentName || 'Opponent'} won the race! Keep playing to finish your game.
          </span>
          {onDismissPlayOn && (
            <button
              onClick={onDismissPlayOn}
              className="ml-2 px-2.5 py-1 text-xs bg-amber-700 hover:bg-amber-600 text-white rounded transition-colors"
            >
              View Final Results
            </button>
          )}
        </div>

        {/* Opponent level-up announcement toast */}
        {opponentLevelUp && (
          <div className="fixed top-14 right-2 z-30 flex items-center gap-2 px-3 py-2 bg-amber-900/90 border border-amber-500/50 rounded-lg text-xs animate-bounce">
            <TrendingUp className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-amber-200 font-medium">
              Opponent: {opponentLevelUp.label}
            </span>
          </div>
        )}
      </>
    )
  }

  // Winner still playing — show non-blocking toast, don't interrupt gameplay
  if (raceResult === 'won' && !localFinished && !playOnActive) {
    return (
      <>
        {winToastVisible && (
          <div className="fixed top-2 left-1/2 -translate-x-1/2 z-40 flex items-center gap-3 px-5 py-3 bg-green-900/90 border border-green-500/50 rounded-lg text-sm animate-fade-in">
            <Trophy className="w-5 h-5 text-yellow-400" />
            <span className="text-green-200 font-medium">
              You won! {opponentName || 'Opponent'} is out.
            </span>
          </div>
        )}
        {/* Still show opponent status bar */}
        <div className="fixed top-2 right-2 z-30 flex items-center gap-2 px-3 py-1.5 bg-slate-800/90 border border-slate-600/50 rounded-lg text-xs">
          <Trophy className="w-3 h-3 text-yellow-400" />
          <span className="text-green-400">You won the race!</span>
        </div>
      </>
    )
  }

  // Full-screen race result overlay (shown when player has finished playing)
  if (raceResult && !playOnActive) {
    const isWin = raceResult === 'won'
    const isTie = raceResult === 'tied'
    return (
      <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/60">
        <div className={`relative flex flex-col items-center gap-3 px-8 py-6 rounded-xl border ${
          isWin
            ? 'bg-green-900/90 border-green-500/50'
            : isTie
              ? 'bg-yellow-900/90 border-yellow-500/50'
              : 'bg-red-900/90 border-red-500/50'
        }`}>
          {isWin ? (
            <Trophy className="w-10 h-10 text-yellow-400" />
          ) : isTie ? (
            <Trophy className="w-10 h-10 text-yellow-600" />
          ) : (
            <Skull className="w-10 h-10 text-red-400" />
          )}
          <span className={`text-2xl font-bold ${
            isWin ? 'text-green-300' : isTie ? 'text-yellow-300' : 'text-red-300'
          }`}>
            {isWin ? 'You Win the Race!' : isTie ? 'It\'s a Tie!' : 'You Lost the Race!'}
          </span>
          <div className="flex items-center gap-3 mt-2">
            {onBackToLobby && (
              <button
                onClick={onBackToLobby}
                className="px-5 py-2 text-sm font-medium rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
              >
                Back to Lobby
              </button>
            )}
            <button
              onClick={onLeaveGame ?? onDismiss}
              className="px-5 py-2 text-sm font-medium rounded-lg bg-slate-700 hover:bg-slate-600 text-white transition-colors"
            >
              Leave
            </button>
          </div>
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
