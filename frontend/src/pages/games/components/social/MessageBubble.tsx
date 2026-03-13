/**
 * MessageBubble — renders a single chat message with actions.
 *
 * Includes reply-to quotes, pin indicators, emoji reactions,
 * edit/delete/reply/react/pin action buttons, and @mention highlighting.
 */

import { useState } from 'react'
import { Pencil, Trash2, Pin, Reply, Smile } from 'lucide-react'
import { useAuth } from '../../../../contexts/AuthContext'
import type { ChatMessage, ChatMember } from '../../hooks/useChat'

// Must match ALLOWED_EMOJIS in backend/app/services/chat_service.py
const EMOJI_LIST = ['👍', '👎', '❤️', '😂', '😮', '😢', '😡', '🎉', '🔥', '👀', '💯', '🙏', '👏', '🤔', '😍', '🎮']

// ----- Emoji Picker -----

function EmojiPicker({ onSelect, onClose }: {
  onSelect: (emoji: string) => void
  onClose: () => void
}) {
  return (
    <div className="absolute bottom-full right-0 mb-1 bg-slate-800 border border-slate-600/50 rounded-lg p-2 shadow-xl z-10">
      <div className="grid grid-cols-8 gap-0.5">
        {EMOJI_LIST.map(emoji => (
          <button
            key={emoji}
            onClick={() => { onSelect(emoji); onClose() }}
            className="w-7 h-7 flex items-center justify-center text-sm hover:bg-slate-700 rounded transition-colors"
          >
            {emoji}
          </button>
        ))}
      </div>
    </div>
  )
}

// ----- @Mention Renderer -----

export function renderContent(content: string, members: ChatMember[]) {
  if (!content) return null
  const memberNames = members.map(m => m.display_name)
  const regex = new RegExp(`@(${memberNames.map(n => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'g')
  const parts = content.split(regex)
  const nameSet = new Set(memberNames)

  return parts.map((part, i) =>
    nameSet.has(part) ? (
      <span key={i} className="text-blue-400 font-medium">@{part}</span>
    ) : (
      <span key={i}>{part}</span>
    )
  )
}

// ----- Message Bubble -----

export function MessageBubble({ msg, isOwn, onEdit, onDelete, onReply, onReact, onPin, myRole, members, id }: {
  msg: ChatMessage
  isOwn: boolean
  onEdit: (id: number, content: string) => void
  onDelete: (id: number) => void
  onReply: (msg: ChatMessage) => void
  onReact: (messageId: number, emoji: string) => void
  onPin: (messageId: number) => void
  myRole: string
  members: ChatMember[]
  id?: string
}) {
  const { user } = useAuth()
  const [showEmojiPicker, setShowEmojiPicker] = useState(false)

  if (msg.is_deleted) {
    return (
      <div id={id} className="py-1 px-2">
        <p className="text-[10px] text-slate-600 italic">Message deleted</p>
      </div>
    )
  }

  const canDelete = isOwn || myRole === 'owner' || myRole === 'admin'
  const canPin = myRole === 'owner' || myRole === 'admin'
  const time = msg.created_at
    ? new Date(msg.created_at).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
    : ''

  return (
    <div id={id} className="group py-1 px-2 rounded hover:bg-slate-700/20 relative">
      {/* Reply-to quote */}
      {msg.reply_to && (
        <div className="flex items-center gap-1 mb-0.5 pl-2 border-l-2 border-blue-500/40">
          <span className="text-[10px] text-blue-400/70">{msg.reply_to.sender_name}</span>
          <span className="text-[10px] text-slate-500 truncate max-w-[200px]">
            {msg.reply_to.is_deleted ? 'Message deleted' : msg.reply_to.content}
          </span>
        </div>
      )}

      {/* Pin indicator */}
      {msg.is_pinned && (
        <div className="flex items-center gap-0.5 mb-0.5">
          <Pin className="w-2.5 h-2.5 text-yellow-500" />
          <span className="text-[9px] text-yellow-500/70">Pinned</span>
        </div>
      )}

      <div className="flex items-baseline gap-2">
        <span className={`text-xs font-medium ${isOwn ? 'text-blue-400' : 'text-slate-300'}`}>
          {msg.sender_name}
        </span>
        <span className="text-[9px] text-slate-600">{time}</span>
        {msg.edited_at && <span className="text-[9px] text-slate-600">(edited)</span>}

        {/* Actions */}
        <div className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-0.5">
          <button
            onClick={() => onReply(msg)}
            className="p-0.5 text-slate-500 hover:text-slate-300"
            title="Reply"
          >
            <Reply className="w-3 h-3" />
          </button>
          <div className="relative">
            <button
              onClick={() => setShowEmojiPicker(!showEmojiPicker)}
              className="p-0.5 text-slate-500 hover:text-slate-300"
              title="React"
            >
              <Smile className="w-3 h-3" />
            </button>
            {showEmojiPicker && (
              <EmojiPicker
                onSelect={(emoji) => onReact(msg.id, emoji)}
                onClose={() => setShowEmojiPicker(false)}
              />
            )}
          </div>
          {canPin && (
            <button
              onClick={() => onPin(msg.id)}
              className={`p-0.5 ${msg.is_pinned ? 'text-yellow-500' : 'text-slate-500 hover:text-yellow-500'}`}
              title={msg.is_pinned ? 'Unpin' : 'Pin'}
            >
              <Pin className="w-3 h-3" />
            </button>
          )}
          {isOwn && (
            <button
              onClick={() => onEdit(msg.id, msg.content || '')}
              className="p-0.5 text-slate-500 hover:text-slate-300"
              title="Edit"
            >
              <Pencil className="w-3 h-3" />
            </button>
          )}
          {canDelete && (
            <button
              onClick={() => onDelete(msg.id)}
              className="p-0.5 text-slate-500 hover:text-red-400"
              title="Delete"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>
      {msg.content && (
        <p className="text-xs text-slate-200 whitespace-pre-wrap break-words mt-0.5">
          {renderContent(msg.content, members)}
        </p>
      )}
      {msg.media_url && (
        <img
          src={msg.media_url}
          alt="GIF"
          className="mt-1 rounded-lg max-w-[200px] max-h-[150px] object-contain"
          loading="lazy"
        />
      )}

      {/* Reaction pills */}
      {msg.reactions.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {msg.reactions.map(r => (
            <button
              key={r.emoji}
              onClick={() => onReact(msg.id, r.emoji)}
              className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] transition-colors ${
                r.user_ids.includes(user?.id || 0)
                  ? 'bg-blue-600/30 border border-blue-500/50 text-blue-300'
                  : 'bg-slate-700/50 border border-slate-600/30 text-slate-400 hover:bg-slate-600/50'
              }`}
            >
              <span>{r.emoji}</span>
              <span>{r.count}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
