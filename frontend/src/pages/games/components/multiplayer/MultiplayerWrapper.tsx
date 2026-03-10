/**
 * Multiplayer Wrapper — adds multiplayer mode selection and lobby to any game.
 *
 * Wraps an existing game component to add:
 * - Mode selection (single player vs multiplayer)
 * - Game lobby (create/join/ready)
 * - WebSocket game state synchronization
 * - Difficulty enforcement for race mode (both players share the same difficulty)
 */

import { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Users, Monitor, ArrowLeft } from 'lucide-react'
import { GameLobby } from './GameLobby'
import { SessionGate } from './SessionGate'
import { clearLastGamePath } from '../GameHub'
import { gameSocket } from '../../../../services/gameSocket'
import type { Difficulty } from '../../types'

export interface RoomConfig {
  max_players?: number
  difficulty?: Difficulty
  [key: string]: unknown
}

export interface MultiplayerConfig {
  gameId: string
  gameName: string
  modes: ('vs' | 'race')[]
  maxPlayers?: number
  /** Whether this game supports difficulty selection (shows selector in lobby for race mode) */
  hasDifficulty?: boolean
  /** Short description of what "Race" means for this game (shown on button) */
  raceDescription?: string
  /** Whether losers can continue playing after the race winner is determined. */
  allowPlayOn?: boolean
}

interface MultiplayerWrapperProps {
  config: MultiplayerConfig
  /** Render the single-player game */
  renderSinglePlayer: () => React.ReactNode
  /** Render the multiplayer game with room context */
  renderMultiplayer: (roomId: string, players: number[], playerNames: Record<number, string>, mode: 'vs' | 'race', roomConfig: RoomConfig) => React.ReactNode
}

export function MultiplayerWrapper({
  config,
  renderSinglePlayer,
  renderMultiplayer,
}: MultiplayerWrapperProps) {
  const [gameMode, setGameMode] = useState<'select' | 'single' | 'session-check' | 'lobby' | 'playing'>('select')
  const [selectedMode, setSelectedMode] = useState<'vs' | 'race'>(config.modes[0])
  const [roomId, setRoomId] = useState<string | null>(null)
  const [players, setPlayers] = useState<number[]>([])
  const [playerNames, setPlayerNames] = useState<Record<number, string>>({})
  const [roomConfig, setRoomConfig] = useState<RoomConfig>({})

  const handleGameStart = useCallback((rid: string, pids: number[], names: Record<number, string>, cfg: RoomConfig) => {
    setRoomId(rid)
    setPlayers(pids)
    setPlayerNames(names)
    setRoomConfig(cfg)
    setGameMode('playing')
    gameSocket.setActiveRoom(rid)
  }, [])

  // Listen for rejoin success/failure (auto-rejoin after reconnect)
  useEffect(() => {
    const unsubSuccess = gameSocket.on('game:rejoin_success', (msg) => {
      setRoomId(msg.roomId)
      setPlayers(msg.players || [])
      setPlayerNames(msg.playerNames || {})
      setRoomConfig(msg.config || {})
      setSelectedMode(msg.mode === 'vs' ? 'vs' : 'race')
      setGameMode('playing')
    })
    const unsubFailed = gameSocket.on('game:rejoin_failed', (_msg) => {
      // Rejoin failed (window expired or room gone) — reset to select
      gameSocket.setActiveRoom(null)
      setGameMode('select')
    })
    return () => { unsubSuccess(); unsubFailed() }
  }, [])

  const navigate = useNavigate()

  const handleBackToSelect = useCallback(() => {
    gameSocket.setActiveRoom(null)
    setGameMode('select')
    setRoomId(null)
    setPlayers([])
    setPlayerNames({})
    setRoomConfig({})
  }, [])

  const handleBackToHub = useCallback(() => {
    clearLastGamePath()
    navigate('/games')
  }, [navigate])

  // Escape key: go back to games hub from select screen
  useEffect(() => {
    if (gameMode !== 'select') return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleBackToHub()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [gameMode, handleBackToHub])

  // Mode selection screen
  if (gameMode === 'select') {
    return (
      <div className="flex flex-col items-center gap-6 py-12">
        <button
          onClick={handleBackToHub}
          className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-white transition-colors self-start"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Games
        </button>

        <h2 className="text-xl font-bold text-white">{config.gameName}</h2>
        <p className="text-sm text-slate-400">Choose how to play</p>

        <div className="flex flex-col sm:flex-row gap-4">
          <button
            onClick={() => setGameMode('single')}
            className="flex flex-col items-center gap-3 px-8 py-6 bg-slate-800 hover:bg-slate-700 border border-slate-600 hover:border-blue-500/50 rounded-xl transition-all group"
          >
            <Monitor className="w-8 h-8 text-blue-400 group-hover:text-blue-300" />
            <span className="text-white font-medium">Single Player</span>
            <span className="text-xs text-slate-400">Play against AI</span>
          </button>

          <div className="flex flex-col gap-2">
            {config.modes.map(m => (
              <button
                key={m}
                onClick={() => { setSelectedMode(m); setGameMode('session-check') }}
                className="flex flex-col items-center gap-3 px-8 py-6 bg-slate-800 hover:bg-slate-700 border border-slate-600 hover:border-green-500/50 rounded-xl transition-all group"
              >
                <Users className="w-8 h-8 text-green-400 group-hover:text-green-300" />
                <span className="text-white font-medium">
                  {m === 'vs' ? 'VS Mode' : 'Race Mode'}
                </span>
                <span className="text-xs text-slate-400">
                  {m === 'vs' ? 'Head-to-head' : (config.raceDescription ?? 'Race against a friend')}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    )
  }

  // Single player — render the original game
  if (gameMode === 'single') {
    return <>{renderSinglePlayer()}</>
  }

  // Session check — verify no other active sessions before entering multiplayer
  if (gameMode === 'session-check') {
    return (
      <SessionGate
        onProceed={() => setGameMode('lobby')}
        onCancel={() => setGameMode('select')}
      />
    )
  }

  // Lobby — waiting for players
  if (gameMode === 'lobby') {
    return (
      <GameLobby
        gameId={config.gameId}
        gameName={config.gameName}
        mode={selectedMode}
        maxPlayers={config.maxPlayers}
        hasDifficulty={config.hasDifficulty && selectedMode === 'race'}
        onGameStart={handleGameStart}
        onBack={handleBackToSelect}
      />
    )
  }

  // Playing — render multiplayer game
  if (gameMode === 'playing' && roomId) {
    return <>{renderMultiplayer(roomId, players, playerNames, selectedMode, roomConfig)}</>
  }

  return null
}
