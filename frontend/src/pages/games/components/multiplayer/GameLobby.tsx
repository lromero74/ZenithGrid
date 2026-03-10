/**
 * Game Lobby — pre-game room for multiplayer games.
 *
 * Handles room creation, joining, readying up, and game start.
 * Shown before the actual game begins.
 */

import { useState, useEffect, useCallback } from 'react'
import { Users, Copy, Check, Play, Loader2 } from 'lucide-react'
import { gameSocket } from '../../../../services/gameSocket'
import { useAuth } from '../../../../contexts/AuthContext'
// useFriends will be used for invite UI in a future phase

export interface LobbyProps {
  gameId: string
  gameName: string
  mode: 'vs' | 'race'
  maxPlayers?: number
  onGameStart: (roomId: string, players: number[]) => void
  onBack: () => void
}

type LobbyState = 'idle' | 'creating' | 'waiting' | 'joining' | 'ready'

export function GameLobby({ gameId, gameName, mode, maxPlayers = 2, onGameStart, onBack }: LobbyProps) {
  const { user, getAccessToken } = useAuth()
  const [lobbyState, setLobbyState] = useState<LobbyState>('idle')
  const [roomId, setRoomId] = useState<string | null>(null)
  const [players, setPlayers] = useState<number[]>([])
  const [readyPlayers, setReadyPlayers] = useState<number[]>([])
  const [isReady, setIsReady] = useState(false)
  const [isHost, setIsHost] = useState(false)
  const [joinCode, setJoinCode] = useState('')
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Connect WebSocket
  useEffect(() => {
    const token = getAccessToken()
    if (token && !gameSocket.connected) {
      gameSocket.connect(token)
    }
  }, [getAccessToken])

  // Listen for game messages
  useEffect(() => {
    const unsubs = [
      gameSocket.on('game:created', (msg) => {
        setRoomId(msg.roomId)
        setPlayers(msg.players)
        setLobbyState('waiting')
        setIsHost(true)
      }),
      gameSocket.on('game:joined', (msg) => {
        setRoomId(msg.roomId)
        setPlayers(msg.players)
        setLobbyState('waiting')
      }),
      gameSocket.on('game:player_joined', (msg) => {
        setPlayers(msg.players)
      }),
      gameSocket.on('game:player_left', (msg) => {
        setPlayers(msg.players)
      }),
      gameSocket.on('game:player_ready', (msg) => {
        setReadyPlayers(msg.readyPlayers)
      }),
      gameSocket.on('game:started', (msg) => {
        onGameStart(msg.roomId, msg.players)
      }),
      gameSocket.on('game:room_closed', () => {
        setLobbyState('idle')
        setRoomId(null)
        setError('Room was closed by the host')
      }),
      gameSocket.on('game:error', (msg) => {
        setError(msg.error)
      }),
    ]
    return () => unsubs.forEach(fn => fn())
  }, [onGameStart])

  const createRoom = useCallback(() => {
    setError(null)
    setLobbyState('creating')
    gameSocket.createRoom(gameId, mode, { max_players: maxPlayers })
  }, [gameId, mode, maxPlayers])

  const joinRoom = useCallback(() => {
    if (!joinCode.trim()) return
    setError(null)
    setLobbyState('joining')
    gameSocket.joinRoom(joinCode.trim())
  }, [joinCode])

  const toggleReady = useCallback(() => {
    if (!roomId) return
    gameSocket.sendReady(roomId)
    setIsReady(true)
  }, [roomId])

  const startGame = useCallback(() => {
    if (!roomId) return
    gameSocket.startGame(roomId)
  }, [roomId])

  const copyRoomId = useCallback(() => {
    if (!roomId) return
    navigator.clipboard.writeText(roomId)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [roomId])

  const leaveRoom = useCallback(() => {
    if (roomId) gameSocket.leaveRoom(roomId)
    setLobbyState('idle')
    setRoomId(null)
    setPlayers([])
    setReadyPlayers([])
    setIsReady(false)
    setIsHost(false)
  }, [roomId])

  const allReady = players.length >= 2 && readyPlayers.length === players.length

  // Pre-game lobby
  if (lobbyState === 'idle') {
    return (
      <div className="flex flex-col items-center gap-6 py-8">
        <h2 className="text-xl font-bold text-white">{gameName} — Multiplayer</h2>
        <p className="text-sm text-slate-400">
          Mode: <span className="text-blue-400 font-medium">{mode === 'vs' ? 'VS' : 'Race'}</span>
        </p>

        {error && (
          <p className="text-sm text-red-400 bg-red-900/20 px-3 py-1.5 rounded">{error}</p>
        )}

        <div className="flex flex-col sm:flex-row gap-3">
          <button
            onClick={createRoom}
            className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors"
          >
            Create Room
          </button>

          <div className="flex gap-2">
            <input
              type="text"
              value={joinCode}
              onChange={e => setJoinCode(e.target.value)}
              placeholder="Room code"
              className="px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-blue-500 w-32"
            />
            <button
              onClick={joinRoom}
              disabled={!joinCode.trim()}
              className="px-4 py-2 bg-green-600 hover:bg-green-500 disabled:bg-slate-600 disabled:text-slate-400 text-white rounded-lg font-medium transition-colors"
            >
              Join
            </button>
          </div>
        </div>

        <button
          onClick={onBack}
          className="text-sm text-slate-400 hover:text-slate-200 transition-colors"
        >
          Back to single player
        </button>
      </div>
    )
  }

  // Waiting room
  return (
    <div className="flex flex-col items-center gap-4 py-8">
      <h2 className="text-xl font-bold text-white">{gameName} — Lobby</h2>

      {/* Room code */}
      {roomId && (
        <div className="flex items-center gap-2 bg-slate-800 px-4 py-2 rounded-lg border border-slate-600">
          <span className="text-xs text-slate-400">Room:</span>
          <span className="text-sm font-mono text-blue-400">{roomId}</span>
          <button onClick={copyRoomId} className="p-1 text-slate-400 hover:text-white">
            {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>
      )}

      {error && (
        <p className="text-sm text-red-400 bg-red-900/20 px-3 py-1.5 rounded">{error}</p>
      )}

      {/* Players */}
      <div className="bg-slate-800/50 rounded-lg p-4 w-full max-w-sm">
        <div className="flex items-center gap-2 mb-3">
          <Users className="w-4 h-4 text-slate-400" />
          <span className="text-sm text-slate-300">Players ({players.length}/{maxPlayers})</span>
        </div>
        <div className="space-y-2">
          {players.map(pid => (
            <div key={pid} className="flex items-center justify-between px-3 py-1.5 bg-slate-700/30 rounded">
              <span className="text-sm text-slate-200">
                {pid === user?.id ? 'You' : `Player ${pid}`}
                {pid === players[0] && <span className="text-xs text-yellow-400 ml-1">(Host)</span>}
              </span>
              {readyPlayers.includes(pid) ? (
                <span className="text-xs text-green-400">Ready</span>
              ) : (
                <span className="text-xs text-slate-500">Waiting</span>
              )}
            </div>
          ))}
          {Array.from({ length: maxPlayers - players.length }).map((_, i) => (
            <div key={`empty-${i}`} className="flex items-center px-3 py-1.5 bg-slate-700/10 rounded border border-dashed border-slate-600/30">
              <span className="text-xs text-slate-600">Waiting for player...</span>
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3">
        {!isReady && (
          <button
            onClick={toggleReady}
            className="px-5 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg font-medium transition-colors"
          >
            Ready
          </button>
        )}
        {isHost && allReady && (
          <button
            onClick={startGame}
            className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors"
          >
            <Play className="w-4 h-4" /> Start Game
          </button>
        )}
        <button
          onClick={leaveRoom}
          className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm transition-colors"
        >
          Leave
        </button>
      </div>

      {lobbyState === 'creating' && !roomId && (
        <div className="flex items-center gap-2 text-slate-400 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" /> Creating room...
        </div>
      )}
    </div>
  )
}
