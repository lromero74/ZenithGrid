/**
 * Multiplayer Wrapper — adds multiplayer mode selection and lobby to any game.
 *
 * Wraps an existing game component to add:
 * - Mode selection (single player vs multiplayer)
 * - Game lobby (create/join/ready)
 * - WebSocket game state synchronization
 */

import { useState, useCallback } from 'react'
import { Users, Monitor } from 'lucide-react'
import { GameLobby } from './GameLobby'

export interface MultiplayerConfig {
  gameId: string
  gameName: string
  modes: ('vs' | 'race')[]
  maxPlayers?: number
}

interface MultiplayerWrapperProps {
  config: MultiplayerConfig
  /** Render the single-player game */
  renderSinglePlayer: () => React.ReactNode
  /** Render the multiplayer game with room context */
  renderMultiplayer: (roomId: string, players: number[], playerNames: Record<number, string>, mode: 'vs' | 'race') => React.ReactNode
}

export function MultiplayerWrapper({
  config,
  renderSinglePlayer,
  renderMultiplayer,
}: MultiplayerWrapperProps) {
  const [gameMode, setGameMode] = useState<'select' | 'single' | 'lobby' | 'playing'>('select')
  const [selectedMode, setSelectedMode] = useState<'vs' | 'race'>(config.modes[0])
  const [roomId, setRoomId] = useState<string | null>(null)
  const [players, setPlayers] = useState<number[]>([])
  const [playerNames, setPlayerNames] = useState<Record<number, string>>({})

  const handleGameStart = useCallback((rid: string, pids: number[], names: Record<number, string>) => {
    setRoomId(rid)
    setPlayers(pids)
    setPlayerNames(names)
    setGameMode('playing')
  }, [])

  const handleBackToSelect = useCallback(() => {
    setGameMode('select')
    setRoomId(null)
    setPlayers([])
    setPlayerNames({})
  }, [])

  // Mode selection screen
  if (gameMode === 'select') {
    return (
      <div className="flex flex-col items-center gap-6 py-12">
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
                onClick={() => { setSelectedMode(m); setGameMode('lobby') }}
                className="flex flex-col items-center gap-3 px-8 py-6 bg-slate-800 hover:bg-slate-700 border border-slate-600 hover:border-green-500/50 rounded-xl transition-all group"
              >
                <Users className="w-8 h-8 text-green-400 group-hover:text-green-300" />
                <span className="text-white font-medium">
                  {m === 'vs' ? 'VS Mode' : 'Race Mode'}
                </span>
                <span className="text-xs text-slate-400">
                  {m === 'vs' ? 'Head-to-head' : 'First to win / Last to lose'}
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

  // Lobby — waiting for players
  if (gameMode === 'lobby') {
    return (
      <GameLobby
        gameId={config.gameId}
        gameName={config.gameName}
        mode={selectedMode}
        maxPlayers={config.maxPlayers}
        onGameStart={handleGameStart}
        onBack={handleBackToSelect}
      />
    )
  }

  // Playing — render multiplayer game
  if (gameMode === 'playing' && roomId) {
    return <>{renderMultiplayer(roomId, players, playerNames, selectedMode)}</>
  }

  return null
}
