/**
 * Game Invite Notification — global listener for incoming game invites.
 *
 * Renders as a toast overlay when a friend sends a game invite.
 * Accepts both lobby invites (pre-game) and mid-game invites.
 * On accept, navigates the user to the game and joins the room.
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { UserPlus, X } from 'lucide-react'
import { gameSocket } from '../../../../services/gameSocket'
import { useAuth } from '../../../../contexts/AuthContext'

interface PendingInvite {
  roomId: string
  gameId: string
  mode: string
  fromDisplayName: string
  midGame: boolean
  receivedAt: number
}

/** Render this once at the Games page level to listen for invites. */
export function GameInviteNotification() {
  const auth = useAuth()
  const navigate = useNavigate()
  const [invite, setInvite] = useState<PendingInvite | null>(null)

  // Connect WS if not already
  useEffect(() => {
    try {
      const token = auth?.getAccessToken?.()
      if (token && !gameSocket.connected) {
        gameSocket.connect(token)
      }
    } catch { /* auth not ready */ }
  }, [auth])

  // Listen for incoming invites
  useEffect(() => {
    const unsub = gameSocket.on('game:invite', (msg) => {
      setInvite({
        roomId: msg.roomId,
        gameId: msg.gameId,
        mode: msg.mode,
        fromDisplayName: msg.fromDisplayName,
        midGame: msg.midGame || false,
        receivedAt: Date.now(),
      })
    })
    return unsub
  }, [])

  // Auto-dismiss after 30 seconds
  useEffect(() => {
    if (!invite) return
    const timer = setTimeout(() => setInvite(null), 30_000)
    return () => clearTimeout(timer)
  }, [invite])

  const handleAccept = useCallback(() => {
    if (!invite) return

    if (invite.midGame) {
      gameSocket.midJoinRoom(invite.roomId)
    } else {
      gameSocket.joinRoom(invite.roomId)
    }

    // Navigate to the game
    navigate(`/games/${invite.gameId}`)
    setInvite(null)
  }, [invite, navigate])

  const handleDecline = useCallback(() => {
    setInvite(null)
  }, [])

  if (!invite) return null

  return (
    <div className="fixed top-4 right-4 z-50 animate-in slide-in-from-right">
      <div className="bg-slate-800 border border-purple-500/50 rounded-xl shadow-2xl p-4 w-80">
        <div className="flex items-start gap-3">
          <div className="p-2 bg-purple-600/20 rounded-lg shrink-0">
            <UserPlus className="w-5 h-5 text-purple-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white">Game Invite</p>
            <p className="text-xs text-slate-400 mt-0.5">
              <span className="text-purple-400 font-medium">{invite.fromDisplayName}</span>
              {' '}invited you to{' '}
              {invite.midGame ? 'join an in-progress ' : 'play '}
              <span className="text-white font-medium">
                {invite.gameId.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
              </span>
              {invite.midGame && <span className="text-yellow-400"> (replacing AI)</span>}
            </p>

            <div className="flex gap-2 mt-3">
              <button
                onClick={handleAccept}
                className="flex-1 px-3 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-xs font-medium transition-colors"
              >
                Accept
              </button>
              <button
                onClick={handleDecline}
                className="flex-1 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-xs font-medium transition-colors"
              >
                Decline
              </button>
            </div>
          </div>
          <button onClick={handleDecline} className="text-slate-500 hover:text-slate-300 shrink-0">
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
