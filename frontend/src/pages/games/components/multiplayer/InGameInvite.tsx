/**
 * In-Game Invite — lets the host invite friends to replace AI mid-game.
 *
 * Shared component usable by any multiplayer game with AI seats.
 * Renders as a small button + dropdown panel.
 */

import { useState } from 'react'
import { UserPlus, X } from 'lucide-react'
import { gameSocket } from '../../../../services/gameSocket'
import { useFriends } from '../../hooks/useFriends'

interface InGameInviteProps {
  roomId: string
  /** Number of open AI seats that can be filled by humans */
  openSeats: number
}

export function InGameInvite({ roomId, openSeats }: InGameInviteProps) {
  const [open, setOpen] = useState(false)
  const { data: friends = [], isLoading } = useFriends()
  const [invited, setInvited] = useState<Set<number>>(new Set())

  if (openSeats <= 0) return null

  const handleInvite = (friendId: number) => {
    gameSocket.send({
      type: 'game:invite',
      roomId,
      targetUserId: friendId,
    })
    setInvited(prev => new Set(prev).add(friendId))
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-600/80 hover:bg-purple-500 text-white rounded-lg text-xs font-medium transition-colors"
        title={`Invite a friend (${openSeats} seat${openSeats > 1 ? 's' : ''} open)`}
      >
        <UserPlus className="w-3.5 h-3.5" />
        Invite ({openSeats})
      </button>
    )
  }

  return (
    <div className="absolute top-2 right-2 z-30 bg-slate-800/95 rounded-lg border border-slate-600 p-3 w-56 shadow-xl">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-slate-300">
          Invite Friend ({openSeats} seat{openSeats > 1 ? 's' : ''})
        </span>
        <button onClick={() => setOpen(false)} className="text-slate-500 hover:text-slate-300">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {isLoading ? (
        <p className="text-xs text-slate-500 py-2">Loading friends...</p>
      ) : friends.length === 0 ? (
        <p className="text-xs text-slate-500 py-2">No friends added yet.</p>
      ) : (
        <div className="space-y-1 max-h-36 overflow-y-auto">
          {friends.map(f => (
            <div key={f.id} className="flex items-center justify-between py-1 px-2 rounded hover:bg-slate-700/30">
              <span className="text-sm text-slate-200 truncate">{f.display_name}</span>
              {invited.has(f.id) ? (
                <span className="text-[10px] text-green-400 shrink-0">Invited</span>
              ) : (
                <button
                  onClick={() => handleInvite(f.id)}
                  className="px-2 py-0.5 rounded text-[10px] bg-purple-600/20 text-purple-400 hover:bg-purple-600/40 shrink-0"
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
