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
import { useNavigate, useLocation } from 'react-router-dom'
import { Monitor, ArrowLeft, Swords, Timer, Trophy, Skull, Lock, X, Loader2, DoorOpen } from 'lucide-react'
import { GameLobby } from './GameLobby'
import { SessionGate } from './SessionGate'
import { clearLastGamePath } from '../GameHub'
import { gameSocket } from '../../../../services/gameSocket'
import { useAuth } from '../../../../contexts/AuthContext'
import type { Difficulty } from '../../types'

export interface RoomConfig {
  max_players?: number
  difficulty?: Difficulty
  race_type?: 'first_to_win' | 'survival' | 'best_score'
  [key: string]: unknown
}

export type MultiplayerMode = 'vs' | 'first_to_win' | 'survival' | 'best_score'

const MODE_META: Record<MultiplayerMode, { label: string; defaultDescription: string; icon: typeof Trophy }> = {
  vs:           { label: 'VS Mode',           defaultDescription: 'Head-to-head',              icon: Swords },
  first_to_win: { label: 'Race: First to Win', defaultDescription: 'First to beat the AI wins', icon: Trophy },
  survival:     { label: 'Race: Survival',      defaultDescription: 'Last player standing wins',  icon: Skull },
  best_score:   { label: 'Race: High Score',    defaultDescription: 'Highest score wins',         icon: Timer },
}

export interface MultiplayerConfig {
  gameId: string
  gameName: string
  modes: MultiplayerMode[]
  maxPlayers?: number
  /** Whether this game supports difficulty selection (shows selector in lobby for race mode) */
  hasDifficulty?: boolean
  /** Per-mode descriptions override defaults. Key = mode, value = button subtitle. */
  modeDescriptions?: Partial<Record<MultiplayerMode, string>>
  /** Whether losers can continue playing after the race winner is determined. */
  allowPlayOn?: boolean
  /** Subtitle shown under the "Single Player" button (default: "Solo play"). */
  singlePlayerDescription?: string
}

interface MultiplayerWrapperProps {
  config: MultiplayerConfig
  /** Render the single-player game */
  renderSinglePlayer: () => React.ReactNode
  /** Render the multiplayer game with room context */
  renderMultiplayer: (roomId: string, players: number[], playerNames: Record<number, string>, mode: MultiplayerMode, roomConfig: RoomConfig, onLeave: () => void) => React.ReactNode
}

export function MultiplayerWrapper({
  config,
  renderSinglePlayer,
  renderMultiplayer,
}: MultiplayerWrapperProps) {
  const { user } = useAuth()
  const location = useLocation()
  const canMultiplayer = user?.permissions?.includes('games:multiplayer') ?? false
  const joiningFriend = (location.state as any)?.joiningFriend === true

  const [gameMode, setGameMode] = useState<'select' | 'single' | 'session-check' | 'lobby' | 'playing' | 'joining'>(
    joiningFriend ? 'joining' : 'select'
  )
  const [showLockedModal, setShowLockedModal] = useState(false)
  const [selectedMultiplayerMode, setSelectedMultiplayerMode] = useState<MultiplayerMode>(config.modes[0])
  // Derived: lobby/backend uses 'vs' | 'race'; race subtypes go into roomConfig.race_type
  const selectedMode: 'vs' | 'race' = selectedMultiplayerMode === 'vs' ? 'vs' : 'race'
  const [roomId, setRoomId] = useState<string | null>(null)
  const [players, setPlayers] = useState<number[]>([])
  const [playerNames, setPlayerNames] = useState<Record<number, string>>({})
  const [roomConfig, setRoomConfig] = useState<RoomConfig>({})
  const [hostUserId, setHostUserId] = useState<number | undefined>(undefined)

  const handleGameStart = useCallback((rid: string, pids: number[], names: Record<number, string>, cfg: RoomConfig) => {
    setRoomId(rid)
    setPlayers(pids)
    setPlayerNames(names)
    setRoomConfig(cfg)
    // Ensure mode is synced from config (backend now always includes mode in config)
    if (cfg.mode === 'vs') {
      setSelectedMultiplayerMode('vs')
    } else if (cfg.race_type) {
      setSelectedMultiplayerMode(cfg.race_type as MultiplayerMode)
    }
    setGameMode('playing')
    gameSocket.setActiveRoom(rid)
  }, [])

  // When joining a friend's game, check for a buffered join result first
  // (the game:joined response may have arrived before this component mounted).
  // If not buffered yet, subscribe to game:joined so we catch it when it arrives.
  useEffect(() => {
    if (gameMode !== 'joining') return
    const applyJoin = (msg: any) => {
      setRoomId(msg.roomId)
      setPlayers(msg.players || [])
      setPlayerNames(msg.playerNames || {})
      setRoomConfig(msg.config || {})
      const mode = msg.config?.mode === 'vs' ? 'vs' : (msg.config?.race_type || 'first_to_win')
      setSelectedMultiplayerMode(mode as MultiplayerMode)
      setGameMode('lobby')
      gameSocket.setActiveRoom(msg.roomId)
    }
    const pending = gameSocket.consumeJoinResult()
    if (pending) { applyJoin(pending); return }
    // Not buffered yet — listen for it live
    const unsub = gameSocket.on('game:joined', applyJoin)
    const timer = setTimeout(() => setGameMode('select'), 10000)
    return () => { unsub(); clearTimeout(timer) }
  }, [gameMode])

  // On mount, check if we're already in a room (e.g. navigated away and back)
  useEffect(() => {
    if (gameMode !== 'select') return
    const unsubInfo = gameSocket.on('game:room_info', (msg) => {
      // Only restore if this room is for our game
      if (msg.gameId !== config.gameId) return
      setRoomId(msg.roomId)
      setPlayers(msg.players || [])
      setPlayerNames(msg.playerNames || {})
      setRoomConfig(msg.config || {})
      setHostUserId(msg.hostUserId)
      const mode = msg.config?.mode === 'vs' ? 'vs' : (msg.config?.race_type || 'first_to_win')
      setSelectedMultiplayerMode(mode as MultiplayerMode)
      if (msg.status === 'playing') {
        setGameMode('playing')
      } else {
        setGameMode('lobby')
      }
      gameSocket.setActiveRoom(msg.roomId)
    })
    // If no room exists, clear any stale active room
    const unsubNoRoom = gameSocket.on('game:no_room', () => {
      gameSocket.setActiveRoom(null)
    })
    // Ask the backend if we're in a room
    if (gameSocket.connected) {
      gameSocket.send({ type: 'game:check_room' })
    }
    return () => { unsubInfo(); unsubNoRoom() }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Listen for rejoin success/failure (auto-rejoin after reconnect)
  // Also listen for game:joined — when accepting an invite, the join response
  // may arrive before GameLobby is mounted. Catch it here and enter lobby.
  useEffect(() => {
    const unsubSuccess = gameSocket.on('game:rejoin_success', (msg) => {
      setRoomId(msg.roomId)
      setPlayers(msg.players || [])
      setPlayerNames(msg.playerNames || {})
      setRoomConfig(msg.config || {})
      setSelectedMultiplayerMode(msg.mode === 'vs' ? 'vs' : (msg.config?.race_type || 'first_to_win'))
      setGameMode('playing')
    })
    const unsubFailed = gameSocket.on('game:rejoin_failed', (_msg) => {
      // Rejoin failed (window expired or room gone) — reset to select
      gameSocket.setActiveRoom(null)
      setGameMode('select')
    })
    const unsubLobbyReset = gameSocket.on('game:lobby_reset', (msg) => {
      // Other player (or self) triggered back-to-lobby — transition to lobby
      setRoomId(msg.roomId)
      setPlayers(msg.players || [])
      setPlayerNames(msg.playerNames || {})
      setRoomConfig(msg.config || {})
      setHostUserId(msg.hostUserId)
      setGameMode('lobby')
    })
    const unsubJoined = gameSocket.on('game:joined', (msg) => {
      // Invite acceptance or join_friend: join response arrived before lobby mounted
      if (gameMode !== 'lobby') {
        setRoomId(msg.roomId)
        setPlayers(msg.players || [])
        setPlayerNames(msg.playerNames || {})
        setRoomConfig(msg.config || {})
        const mode = msg.config?.mode === 'vs' ? 'vs' : (msg.config?.race_type || 'first_to_win')
        setSelectedMultiplayerMode(mode as MultiplayerMode)
        setGameMode('lobby')
        // Track room for reconnection if user navigates away and comes back
        gameSocket.setActiveRoom(msg.roomId)
      }
    })
    // Handle "already in a room" — backend sends existing room info instead of error
    const unsubAlready = gameSocket.on('game:already_in_room', (msg) => {
      // Only restore if this room is for our game
      if (msg.gameId !== config.gameId) return
      setRoomId(msg.roomId)
      setPlayers(msg.players || [])
      setPlayerNames(msg.playerNames || {})
      setRoomConfig(msg.config || {})
      setHostUserId(msg.hostUserId)
      const mode = msg.mode === 'vs' ? 'vs' : (msg.config?.race_type || 'first_to_win')
      setSelectedMultiplayerMode(mode as MultiplayerMode)
      if (msg.status === 'playing') {
        setGameMode('playing')
      } else {
        setGameMode('lobby')
      }
      gameSocket.setActiveRoom(msg.roomId)
    })
    // Listen for individual leave confirmation (e.g. leaving mid-game while opponent plays)
    const unsubLeft = gameSocket.on('game:left', (_msg) => {
      gameSocket.setActiveRoom(null)
      setGameMode('select')
      setRoomId(null)
      setPlayers([])
      setPlayerNames({})
      setRoomConfig({})
      setHostUserId(undefined)
    })
    // Listen for room closed (host left)
    const unsubClosed = gameSocket.on('game:room_closed', (_msg) => {
      gameSocket.setActiveRoom(null)
      setGameMode('select')
      setRoomId(null)
      setPlayers([])
      setPlayerNames({})
      setRoomConfig({})
      setHostUserId(undefined)
    })
    return () => { unsubSuccess(); unsubFailed(); unsubLobbyReset(); unsubJoined(); unsubAlready(); unsubLeft(); unsubClosed() }
  }, [gameMode])

  const navigate = useNavigate()

  const handleBackToSelect = useCallback(() => {
    gameSocket.setActiveRoom(null)
    setGameMode('select')
    setRoomId(null)
    setPlayers([])
    setPlayerNames({})
    setRoomConfig({})
    setHostUserId(undefined)
  }, [])

  // Return to lobby after a game ends (keeps room intact for rematch)
  const handleBackToLobby = useCallback(() => {
    gameSocket.send({ type: 'game:back_to_lobby' })
    setGameMode('lobby')
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
            <span className="text-xs text-slate-400">{config.singlePlayerDescription ?? 'Solo play'}</span>
          </button>

          <div className="flex flex-col gap-2">
            {config.modes.map(m => {
              const meta = MODE_META[m]
              const Icon = meta.icon
              const description = config.modeDescriptions?.[m] ?? meta.defaultDescription
              const isVs = m === 'vs'
              return (
                <button
                  key={m}
                  onClick={() => {
                    if (!canMultiplayer) { setShowLockedModal(true); return }
                    setSelectedMultiplayerMode(m); setGameMode('session-check')
                  }}
                  className={`flex flex-col items-center gap-3 px-8 py-6 bg-slate-800 hover:bg-slate-700 border border-slate-600 ${
                    isVs ? 'hover:border-purple-500/50' : 'hover:border-green-500/50'
                  } rounded-xl transition-all group relative`}
                >
                  {!canMultiplayer && <Lock className="w-3.5 h-3.5 text-slate-500 absolute top-3 right-3" />}
                  <Icon className={`w-8 h-8 ${isVs ? 'text-purple-400 group-hover:text-purple-300' : 'text-green-400 group-hover:text-green-300'}`} />
                  <span className="text-white font-medium">{meta.label}</span>
                  <span className="text-xs text-slate-400">{description}</span>
                </button>
              )
            })}
          </div>

          {/* Multiplayer locked modal */}
          {showLockedModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowLockedModal(false)}>
              <div className="relative flex flex-col items-center gap-4 px-8 py-6 bg-slate-800 border border-slate-600 rounded-xl max-w-sm text-center" onClick={e => e.stopPropagation()}>
                <button onClick={() => setShowLockedModal(false)} className="absolute top-2 right-2 text-slate-400 hover:text-white">
                  <X className="w-4 h-4" />
                </button>
                <Lock className="w-8 h-8 text-amber-400" />
                <p className="text-white font-medium">Multiplayer requires a registered account</p>
                <p className="text-sm text-slate-400">
                  Create a free account to play with friends, join tournaments, and track your stats.
                </p>
                <a
                  href="/login"
                  className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors"
                >
                  Sign Up Free
                </a>
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  // Joining friend's game — waiting for game:joined response
  if (gameMode === 'joining') {
    return (
      <div className="flex flex-col items-center gap-4 py-20">
        <Loader2 className="w-8 h-8 text-blue-400 animate-spin" />
        <p className="text-sm text-slate-300">Joining game...</p>
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
        raceType={selectedMode === 'race' ? (selectedMultiplayerMode as 'first_to_win' | 'survival' | 'best_score') : undefined}
        maxPlayers={config.maxPlayers}
        hasDifficulty={config.hasDifficulty ?? false}
        availableModes={config.modes}
        selectedMultiplayerMode={selectedMultiplayerMode}
        onModeChange={(m) => {
          setSelectedMultiplayerMode(m)
        }}
        onGameStart={handleGameStart}
        onBack={handleBackToSelect}
        initialRoom={roomId ? { roomId, players, playerNames, config: roomConfig, hostUserId } : undefined}
      />
    )
  }

  // Playing — render multiplayer game
  if (gameMode === 'playing' && roomId) {
    return (
      <div className="relative">
        {renderMultiplayer(roomId, players, playerNames, selectedMultiplayerMode, roomConfig, handleBackToLobby)}
        <button
          onClick={() => {
            gameSocket.leaveRoom(roomId)
            gameSocket.setActiveRoom(null)
            setGameMode('select')
            setRoomId(null)
            setPlayers([])
            setPlayerNames({})
            setRoomConfig({})
          }}
          className="fixed top-2 right-2 z-40 flex items-center gap-1 px-2 py-1 text-xs bg-slate-800/80 hover:bg-red-900/80 border border-slate-600/50 hover:border-red-500/50 text-slate-400 hover:text-red-300 rounded-lg backdrop-blur-sm transition-all opacity-40 hover:opacity-100"
          title="Leave game"
        >
          <DoorOpen className="w-3.5 h-3.5" />
          Leave
        </button>
      </div>
    )
  }

  return null
}
