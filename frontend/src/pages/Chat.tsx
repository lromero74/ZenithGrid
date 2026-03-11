/**
 * Chat page — dedicated page for messaging.
 *
 * Full-featured chat with DMs, group chats, channels, reactions,
 * reply/quote, search, @mentions, pinned messages, and presence.
 */

import { ChatPanel } from './games/components/social/ChatPanel'
import { GameInviteNotification } from './games/components/multiplayer/GameInviteNotification'

export default function Chat() {
  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-white">Chat</h1>
        <p className="text-slate-400 text-sm">Messages, group chats, and channels</p>
      </div>

      <ChatPanel />

      <GameInviteNotification />
    </div>
  )
}
