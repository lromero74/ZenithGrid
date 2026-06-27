/**
 * useRaceMode — multiplayer race-mode hook (opponent status, sync-start
 * countdown, spectating, reconnect handling). Extracted from RaceOverlay so the
 * component file only exports components (keeps Fast Refresh happy).
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { gameSocket, type GameActionMessage, type LobbyMessage } from '../../../../services/gameSocket'
import { useAuth } from '../../../../contexts/AuthContext'

// Fallback value — server sends authoritative `reconnectWindowSeconds` in disconnect message
const RECONNECT_WINDOW_SECONDS = 60

export interface OpponentStatus {
  finished: boolean
  result?: 'win' | 'loss'
  score?: number
  level?: number | string
  /** How the opponent exited: normal finish, forfeit, or disconnect (abend). */
  exitType?: 'completed' | 'forfeit' | 'abend'
}

/** Transient level-up announcement from opponent. */
export interface LevelAnnouncement {
  level: number | string
  label: string
  timestamp: number
}

export type RaceType = 'first_to_win' | 'survival' | 'best_score'

export interface RaceModeOptions {
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
  const [playerStates, setPlayerStates] = useState<Record<number, unknown>>({})
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
    const unsub = gameSocket.on<GameActionMessage<{ type?: string; seed?: number; score?: number; level?: number | string; label?: string; result?: string }>>('game:action', (msg) => {
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
          level: action.level ?? 0,
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
    const unsubDisconnect = gameSocket.on<LobbyMessage>('game:player_disconnect', (msg) => {
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
    const unsub = gameSocket.on<LobbyMessage>('connection', (msg) => {
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
    const unsub = gameSocket.on<LobbyMessage>('game:player_state', (msg) => {
      if (msg.state && msg.playerId) {
        const pid = msg.playerId
        setPlayerStates(prev => ({ ...prev, [pid]: msg.state }))
        // Auto-select first available spectate target
        setSpectateTarget(prev => prev ?? pid)
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
  }, [playerStates])

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
    localScore: localScoreRef.current,
    // Sync-start
    gameStarted, countdownValue, gameSeed, localReady, sendReady,
  }
}
