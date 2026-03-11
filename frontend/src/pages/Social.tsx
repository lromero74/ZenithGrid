/**
 * Social page — friends, game history, and tournaments.
 *
 * Centralizes social/multiplayer features. Chat has its own dedicated page.
 */

import { FriendsPanel } from './games/components/social/FriendsPanel'
import { GameHistory } from './games/components/social/GameHistory'
import { Tournaments } from './games/components/social/Tournaments'
import { GameInviteNotification } from './games/components/multiplayer/GameInviteNotification'

export default function Social() {
  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-white">Social</h1>
        <p className="text-slate-400 text-sm">Friends, game history, and tournaments</p>
      </div>

      <FriendsPanel defaultOpen />
      <GameHistory defaultOpen />
      <Tournaments defaultOpen />

      {/* Listen for game invites on this page too */}
      <GameInviteNotification />
    </div>
  )
}
