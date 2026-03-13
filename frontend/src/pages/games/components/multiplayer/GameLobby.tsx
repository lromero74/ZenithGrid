/**
 * Game Lobby — pre-game room for multiplayer games.
 *
 * Handles room creation, joining, readying up, and game start.
 * Includes friend invite functionality and difficulty selection for race mode.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { Users, Copy, Check, Play, Loader2, UserPlus, Lock, MessageCircle, Send } from 'lucide-react'
import { gameSocket } from '../../../../services/gameSocket'
import { useAuth } from '../../../../contexts/AuthContext'
import { useFriends } from '../../hooks/useFriends'
import type { Difficulty } from '../../types'
import type { RoomConfig, MultiplayerMode } from './MultiplayerWrapper'

export interface LobbyProps {
  gameId: string
  gameName: string
  mode: 'vs' | 'race'
  /** Specific race type for race mode (survival, best_score, first_to_win). Included in room config. */
  raceType?: 'first_to_win' | 'survival' | 'best_score'
  maxPlayers?: number
  /** Show difficulty selector (for race mode games with difficulty) */
  hasDifficulty?: boolean
  /** Available multiplayer modes for this game (host can switch in lobby) */
  availableModes?: MultiplayerMode[]
  selectedMultiplayerMode?: MultiplayerMode
  onModeChange?: (mode: MultiplayerMode) => void
  onGameStart: (roomId: string, players: number[], playerNames: Record<number, string>, config: RoomConfig) => void
  onBack: () => void
  /** Pre-joined room state (from invite acceptance before lobby mounted) */
  initialRoom?: {
    roomId: string
    players: number[]
    playerNames: Record<number, string>
    config: RoomConfig
    hostUserId?: number
  }
}

type LobbyState = 'idle' | 'creating' | 'waiting' | 'joining' | 'ready'

const DIFFICULTY_OPTIONS: { value: Difficulty; label: string; color: string }[] = [
  { value: 'easy', label: 'Easy', color: 'bg-emerald-900/50 text-emerald-400 border-emerald-700/50' },
  { value: 'medium', label: 'Medium', color: 'bg-yellow-900/50 text-yellow-400 border-yellow-700/50' },
  { value: 'hard', label: 'Hard', color: 'bg-red-900/50 text-red-400 border-red-700/50' },
]

const MODE_LABELS: Record<MultiplayerMode, string> = {
  vs: 'VS',
  first_to_win: 'First to Win',
  survival: 'Survival',
  best_score: 'High Score',
}

export function GameLobby({ gameId, gameName, mode, raceType, maxPlayers = 2, hasDifficulty, availableModes, selectedMultiplayerMode, onModeChange, onGameStart, onBack, initialRoom }: LobbyProps) {
  const { user, getAccessToken } = useAuth()
  const [lobbyState, setLobbyState] = useState<LobbyState>(initialRoom ? 'waiting' : 'idle')
  const [roomId, setRoomId] = useState<string | null>(initialRoom?.roomId ?? null)
  const [players, setPlayers] = useState<number[]>(initialRoom?.players ?? [])
  const [playerNames, setPlayerNames] = useState<Record<number, string>>(initialRoom?.playerNames ?? {})
  const [readyPlayers, setReadyPlayers] = useState<number[]>([])
  const [isReady, setIsReady] = useState(false)
  const [isHost, setIsHost] = useState(
    initialRoom ? (initialRoom.hostUserId != null ? initialRoom.hostUserId === user?.id : initialRoom.players[0] === user?.id) : false
  )
  const [joinCode, setJoinCode] = useState('')
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showInvite, setShowInvite] = useState(false)
  const [difficulty, setDifficulty] = useState<Difficulty>(initialRoom?.config?.difficulty as Difficulty ?? 'medium')
  const [roomConfig, setRoomConfig] = useState<RoomConfig>(initialRoom?.config ?? {})

  // Lobby chat
  const [chatMessages, setChatMessages] = useState<Array<{ playerId: number; name: string; text: string }>>([])
  const [chatInput, setChatInput] = useState('')
  const chatEndRef = useRef<HTMLDivElement>(null)

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
        if (msg.playerNames) setPlayerNames(msg.playerNames)
        setLobbyState('waiting')
        setIsHost(true)
      }),
      gameSocket.on('game:joined', (msg) => {
        setRoomId(msg.roomId)
        setPlayers(msg.players)
        if (msg.playerNames) setPlayerNames(msg.playerNames)
        if (msg.config) {
          setRoomConfig(msg.config)
          // Lock difficulty to host's choice
          if (msg.config.difficulty) setDifficulty(msg.config.difficulty)
        }
        setLobbyState('waiting')
      }),
      gameSocket.on('game:player_joined', (msg) => {
        setPlayers(msg.players)
        if (msg.playerNames) setPlayerNames(msg.playerNames)
      }),
      gameSocket.on('game:player_left', (msg) => {
        setPlayers(msg.players)
        if (msg.playerNames) setPlayerNames(msg.playerNames)
      }),
      gameSocket.on('game:player_ready', (msg) => {
        setReadyPlayers(msg.readyPlayers)
      }),
      gameSocket.on('game:started', (msg) => {
        const cfg = msg.config || roomConfig
        onGameStart(msg.roomId, msg.players, msg.playerNames || {}, cfg)
      }),
      gameSocket.on('game:lobby_reset', (msg) => {
        // Game ended — room reset to lobby for rematch
        setRoomId(msg.roomId)
        setPlayers(msg.players || [])
        if (msg.playerNames) setPlayerNames(msg.playerNames)
        if (msg.config) setRoomConfig(msg.config)
        setReadyPlayers([])
        setIsReady(false)
        setIsHost(msg.hostUserId === user?.id)
        setLobbyState('waiting')
      }),
      gameSocket.on('game:room_closed', () => {
        setLobbyState('idle')
        setRoomId(null)
        setError('Room was closed by the host')
      }),
      gameSocket.on('game:already_in_room', (msg) => {
        // User was already in a room — show that lobby instead of erroring
        setRoomId(msg.roomId)
        setPlayers(msg.players)
        if (msg.playerNames) setPlayerNames(msg.playerNames)
        if (msg.config) {
          setRoomConfig(msg.config)
          if (msg.config.difficulty) setDifficulty(msg.config.difficulty)
        }
        setIsHost(msg.isHost ?? false)
        setReadyPlayers(msg.readyPlayers ?? [])
        setLobbyState('waiting')
        setError(null)
      }),
      gameSocket.on('game:config_updated', (msg) => {
        if (msg.config) {
          setRoomConfig(msg.config)
          if (msg.config.difficulty) setDifficulty(msg.config.difficulty)
          // Sync mode changes from host
          if (msg.config.mode && onModeChange) {
            const m = msg.config.mode === 'vs' ? 'vs' : (msg.config.race_type || 'first_to_win')
            onModeChange(m as MultiplayerMode)
          }
        }
      }),
      gameSocket.on('game:chat', (msg) => {
        setChatMessages(prev => [...prev.slice(-49), { playerId: msg.playerId, name: msg.playerName, text: msg.text }])
      }),
      gameSocket.on('game:error', (msg) => {
        setError(msg.error)
      }),
    ]
    return () => unsubs.forEach(fn => fn())
  }, [onGameStart, roomConfig])

  const createRoom = useCallback(() => {
    setError(null)
    setLobbyState('creating')
    const config: RoomConfig = { max_players: maxPlayers }
    if (hasDifficulty) config.difficulty = difficulty
    if (raceType) config.race_type = raceType
    setRoomConfig(config)
    gameSocket.createRoom(gameId, mode, config)
  }, [gameId, mode, raceType, maxPlayers, hasDifficulty, difficulty])

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
    setPlayerNames({})
    setReadyPlayers([])
    setIsReady(false)
    setIsHost(false)
    setRoomConfig({})
    setChatMessages([])
  }, [roomId])

  const sendChat = useCallback(() => {
    const text = chatInput.trim()
    if (!text || !roomId) return
    gameSocket.send({ type: 'game:chat', roomId, text })
    setChatInput('')
  }, [chatInput, roomId])

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages])

  const getDisplayName = (pid: number) => {
    if (pid === user?.id) return 'You'
    return playerNames[pid] || `Player ${pid}`
  }

  const allReady = players.length >= 2 && readyPlayers.length === players.length

  // Pre-game lobby
  if (lobbyState === 'idle') {
    return (
      <div className="flex flex-col items-center gap-6 py-8">
        <h2 className="text-xl font-bold text-white">{gameName} — Multiplayer</h2>
        <p className="text-sm text-slate-400">
          Mode: <span className="text-blue-400 font-medium">{mode === 'vs' ? 'VS' : 'Race'}</span>
        </p>

        {/* Difficulty selector (host picks before creating) */}
        {hasDifficulty && (
          <div className="flex flex-col items-center gap-2">
            <span className="text-xs text-slate-400">Difficulty (shared with opponent)</span>
            <div className="flex gap-2">
              {DIFFICULTY_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => setDifficulty(opt.value)}
                  className={`px-3 py-1 rounded-full text-xs border transition-colors ${
                    difficulty === opt.value ? opt.color : 'bg-slate-800 text-slate-500 border-slate-700'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        )}

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
          Back
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

      {/* Difficulty selector (host can change, guest sees locked) */}
      {hasDifficulty && difficulty && (
        isHost ? (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-400">Difficulty:</span>
            {DIFFICULTY_OPTIONS.map(opt => (
              <button
                key={opt.value}
                onClick={() => {
                  setDifficulty(opt.value)
                  if (roomId) gameSocket.updateConfig(roomId, { difficulty: opt.value })
                }}
                className={`px-2.5 py-1 rounded-full border text-xs font-medium transition-colors ${
                  difficulty === opt.value ? opt.color : 'bg-slate-800 text-slate-500 border-slate-700 hover:border-slate-500'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        ) : (
          <div className="flex items-center gap-2 text-xs">
            <Lock className="w-3 h-3 text-slate-400" />
            <span className="text-slate-400">Difficulty:</span>
            <span className={`px-2 py-0.5 rounded-full ${
              DIFFICULTY_OPTIONS.find(o => o.value === difficulty)?.color ?? 'text-slate-300'
            }`}>
              {difficulty.charAt(0).toUpperCase() + difficulty.slice(1)}
            </span>
            <span className="text-slate-500">(set by host)</span>
          </div>
        )
      )}

      {/* Mode selector (host can change, guest sees label) */}
      {availableModes && availableModes.length > 1 && selectedMultiplayerMode && (
        isHost ? (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-400">Mode:</span>
            {availableModes.map(m => (
              <button
                key={m}
                onClick={() => {
                  if (onModeChange) onModeChange(m)
                  const modeVal = m === 'vs' ? 'vs' : 'race'
                  const updates: Record<string, string> = { mode: modeVal }
                  if (m !== 'vs') updates.race_type = m
                  if (roomId) gameSocket.updateConfig(roomId, updates)
                }}
                className={`px-2.5 py-1 rounded-full border text-xs font-medium transition-colors ${
                  selectedMultiplayerMode === m
                    ? 'bg-blue-900/50 text-blue-400 border-blue-700/50'
                    : 'bg-slate-800 text-slate-500 border-slate-700 hover:border-slate-500'
                }`}
              >
                {MODE_LABELS[m]}
              </button>
            ))}
          </div>
        ) : (
          <div className="flex items-center gap-2 text-xs">
            <Lock className="w-3 h-3 text-slate-400" />
            <span className="text-slate-400">Mode:</span>
            <span className="px-2 py-0.5 rounded-full bg-blue-900/50 text-blue-400 border border-blue-700/50">
              {MODE_LABELS[selectedMultiplayerMode]}
            </span>
            <span className="text-slate-500">(set by host)</span>
          </div>
        )
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
                {getDisplayName(pid)}
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

      {/* Lobby chat */}
      <div className="bg-slate-800/50 rounded-lg border border-slate-700/50 w-full max-w-sm">
        <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-slate-700/50">
          <MessageCircle className="w-3 h-3 text-slate-500" />
          <span className="text-[10px] text-slate-500 uppercase tracking-wide">Chat</span>
        </div>
        <div className="h-24 overflow-y-auto px-3 py-1.5 space-y-0.5">
          {chatMessages.length === 0 && (
            <p className="text-[10px] text-slate-600 italic pt-1">No messages yet</p>
          )}
          {chatMessages.map((msg, i) => (
            <div key={i} className="text-xs">
              <span className={`font-medium ${msg.playerId === user?.id ? 'text-blue-400' : 'text-amber-400'}`}>
                {msg.playerId === user?.id ? 'You' : msg.name}
              </span>
              <span className="text-slate-400">: {msg.text}</span>
            </div>
          ))}
          <div ref={chatEndRef} />
        </div>
        <div className="flex items-center gap-1 px-2 py-1.5 border-t border-slate-700/50">
          <input
            type="text"
            value={chatInput}
            onChange={e => setChatInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') sendChat() }}
            placeholder="Say something..."
            maxLength={500}
            className="flex-1 bg-transparent text-xs text-slate-200 placeholder-slate-600 outline-none px-1"
          />
          <button
            onClick={sendChat}
            disabled={!chatInput.trim()}
            className="p-1 text-slate-500 hover:text-blue-400 disabled:opacity-30 transition-colors"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
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
        {isHost && players.length < maxPlayers && roomId && (
          <button
            onClick={() => setShowInvite(!showInvite)}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-sm font-medium transition-colors"
          >
            <UserPlus className="w-4 h-4" /> Invite Friend
          </button>
        )}
        <button
          onClick={leaveRoom}
          className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm transition-colors"
        >
          Leave
        </button>
      </div>

      {/* Friend invite panel */}
      {showInvite && roomId && (
        <FriendInvitePanel roomId={roomId} onClose={() => setShowInvite(false)} />
      )}

      {lobbyState === 'creating' && !roomId && (
        <div className="flex items-center gap-2 text-slate-400 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" /> Creating room...
        </div>
      )}
    </div>
  )
}

// ----- Friend Invite Panel -----

function FriendInvitePanel({ roomId, onClose }: { roomId: string; onClose: () => void }) {
  const { data: friends = [], isLoading } = useFriends()
  const [invited, setInvited] = useState<Set<number>>(new Set())

  const handleInvite = (friendId: number) => {
    gameSocket.send({
      type: 'game:invite',
      roomId,
      targetUserId: friendId,
    })
    setInvited(prev => new Set(prev).add(friendId))
  }

  return (
    <div className="bg-slate-800/80 rounded-lg border border-slate-600 p-3 w-full max-w-sm">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-slate-300">Invite a Friend</span>
        <button onClick={onClose} className="text-xs text-slate-500 hover:text-slate-300">Close</button>
      </div>

      {isLoading ? (
        <p className="text-xs text-slate-500 py-2">Loading friends...</p>
      ) : friends.length === 0 ? (
        <div className="text-xs text-slate-500 py-2">
          <p>No friends yet.</p>
          <p className="mt-1">Share the room code: <span className="font-mono text-blue-400">{roomId}</span></p>
        </div>
      ) : (
        <div className="space-y-1 max-h-32 overflow-y-auto">
          {friends.map(f => (
            <div key={f.id} className="flex items-center justify-between py-1 px-2 rounded hover:bg-slate-700/30">
              <span className="text-sm text-slate-200">{f.display_name}</span>
              {invited.has(f.id) ? (
                <span className="text-[10px] text-green-400">Invited</span>
              ) : (
                <button
                  onClick={() => handleInvite(f.id)}
                  className="px-2 py-0.5 rounded text-[10px] bg-purple-600/20 text-purple-400 hover:bg-purple-600/40"
                >
                  Invite
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
