/**
 * Social page — friends, game history, and tournaments.
 *
 * Centralizes social/multiplayer features. Chat has its own dedicated page.
 */

import { FriendsPanel } from './games/components/social/FriendsPanel'
import { GameHistory } from './games/components/social/GameHistory'
import { Tournaments } from './games/components/social/Tournaments'
import { GameInviteNotification } from './games/components/multiplayer/GameInviteNotification'
import { useHasPermission } from '../hooks/usePermission'
import { Lock } from 'lucide-react'

export default function Social() {
  const canChat = useHasPermission('social:chat')

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-white">Social</h1>
        <p className="text-slate-400 text-sm">Friends, game history, and tournaments</p>
      </div>

      {canChat ? (
        <>
          <FriendsPanel defaultOpen />
          <GameHistory defaultOpen />
          <Tournaments defaultOpen />
          <GameInviteNotification />
        </>
      ) : (
        <div className="flex flex-col items-center gap-4 py-12 bg-slate-800/50 border border-slate-700 rounded-xl">
          <Lock className="w-8 h-8 text-amber-400" />
          <p className="text-white font-medium">Social features require a registered account</p>
          <p className="text-sm text-slate-400 text-center max-w-sm">
            Create a free account to add friends, view game history, and join tournaments.
          </p>
          <a
            href="/login"
            className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Sign Up Free
          </a>
        </div>
      )}
    </div>
  )
}
