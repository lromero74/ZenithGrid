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

import { useState, useEffect } from 'react'
import { Trophy, Skull, Clock, Wifi, TrendingUp, Eye, WifiOff, Pause, ChevronLeft, ChevronRight } from 'lucide-react'
import { LevelAnnouncement } from './useRaceMode'


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
  localScore,
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
  localScore?: number
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

  // Auto-enter spectate mode once spectator data is available after skull dismissal.
  // Declared here (before any early return) to keep Hook call order stable.
  useEffect(() => {
    const hasSpectatorProps = spectatablePlayers !== undefined && spectatablePlayers.length > 0
    const readyToSpectate = localFinished && !raceResult && skullDismissed && !spectateMode && hasSpectatorProps
    if (readyToSpectate) {
      setSpectateMode(true)
    }
  }, [localFinished, raceResult, skullDismissed, spectateMode, spectatablePlayers])

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
  const showSkullOverlay = localFinished && !raceResult && !skullDismissed
  const showSpectatorBar = spectateMode && !raceResult

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
          {(localScore !== undefined || opponentScore !== undefined) && (
            <div className="flex items-center gap-6 mt-1 text-sm">
              <div className="text-center">
                <p className="text-slate-400 text-xs">You</p>
                <p className={`font-bold text-lg font-mono ${isWin ? 'text-green-300' : isTie ? 'text-yellow-300' : 'text-red-300'}`}>
                  {localScore !== undefined ? localScore.toLocaleString() : '—'}
                </p>
              </div>
              <span className="text-slate-500 text-xs">vs</span>
              <div className="text-center">
                <p className="text-slate-400 text-xs">{opponentName || 'Opponent'}</p>
                <p className={`font-bold text-lg font-mono ${!isWin && !isTie ? 'text-green-300' : isTie ? 'text-yellow-300' : 'text-red-300'}`}>
                  {opponentScore !== undefined ? opponentScore.toLocaleString() : '—'}
                </p>
              </div>
            </div>
          )}
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
