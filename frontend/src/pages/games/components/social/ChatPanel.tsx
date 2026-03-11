/**
 * Chat Panel — DMs, group chats, and channels.
 *
 * Two-pane layout: channel list on the left, message area on the right.
 * Supports creating DMs/groups, sending/editing/deleting messages,
 * typing indicators, unread badges, infinite scroll for history,
 * emoji reactions, reply/quote, pinned messages, search, @mentions,
 * and online presence indicators.
 */

import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import {
  MessageSquare, Plus, Send, ArrowLeft, Users, Hash,
  ChevronDown, ChevronUp, Pencil, Trash2, X,
  UserPlus, LogOut, Search, Pin, Reply, Smile,
} from 'lucide-react'
import { useAuth } from '../../../../contexts/AuthContext'
import { useFriends, useOnlineFriends } from '../../hooks/useFriends'
import {
  useChatChannels, useChatMessages, useSendMessage,
  useEditMessage, useDeleteMessage, useMarkRead,
  useCreateChannel, useChannelMembers, useAddMember, useRemoveMember,
  useDeleteChannel, useUpdateMemberRole, useToggleReaction,
  useTogglePin, usePinnedMessages, useChatSearch,
} from '../../hooks/useChat'
import { useChatSocket } from '../../hooks/useChatSocket'
import type { ChatChannel, ChatMessage, ChatMember } from '../../hooks/useChat'

// Common emojis for the quick picker
const EMOJI_LIST = ['👍', '👎', '❤️', '😂', '😮', '😢', '😡', '🎉', '🔥', '👀', '💯', '🙏', '👏', '🤔', '😍', '🎮']

// ----- Chat Toast Overlay -----

function ChatToastOverlay({ toasts, onDismiss }: {
  toasts: { id: number; senderName: string; content: string; channelId: number }[]
  onDismiss: (id: number) => void
}) {
  if (toasts.length === 0) return null
  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 max-w-sm">
      {toasts.map(t => (
        <div
          key={t.id}
          className="bg-slate-800 border border-blue-500/50 rounded-lg p-3 shadow-lg cursor-pointer"
          onClick={() => onDismiss(t.id)}
        >
          <p className="text-xs font-medium text-blue-400">{t.senderName}</p>
          <p className="text-xs text-slate-300 mt-0.5 line-clamp-2">{t.content}</p>
        </div>
      ))}
    </div>
  )
}

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

function renderContent(content: string, members: ChatMember[]) {
  if (!content) return null
  const memberNames = members.map(m => m.display_name)
  // Match @Name patterns
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

// ----- New Chat Dialog -----

function NewChatDialog({ onClose, onCreated }: {
  onClose: () => void
  onCreated: (channelId: number) => void
}) {
  const [mode, setMode] = useState<'dm' | 'group'>('dm')
  const [groupName, setGroupName] = useState('')
  const [selectedFriends, setSelectedFriends] = useState<number[]>([])
  const { data: friends = [] } = useFriends()
  const createChannel = useCreateChannel()

  const toggleFriend = (id: number) => {
    setSelectedFriends(prev =>
      prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id]
    )
  }

  const handleCreate = async () => {
    try {
      let result
      if (mode === 'dm') {
        if (selectedFriends.length !== 1) return
        result = await createChannel.mutateAsync({
          type: 'dm',
          friend_id: selectedFriends[0],
        })
      } else {
        if (!groupName.trim()) return
        result = await createChannel.mutateAsync({
          type: 'group',
          name: groupName.trim(),
          member_ids: selectedFriends,
        })
      }
      onCreated(result.id)
    } catch {
      // error handled by mutation
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-slate-200">New Chat</h4>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-xs">Cancel</button>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => { setMode('dm'); setSelectedFriends([]) }}
          className={`px-3 py-1 rounded text-xs ${mode === 'dm' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400'}`}
        >
          Direct Message
        </button>
        <button
          onClick={() => { setMode('group'); setSelectedFriends([]) }}
          className={`px-3 py-1 rounded text-xs ${mode === 'group' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400'}`}
        >
          Group Chat
        </button>
      </div>

      {mode === 'group' && (
        <input
          type="text"
          value={groupName}
          onChange={e => setGroupName(e.target.value)}
          placeholder="Group name..."
          maxLength={100}
          className="w-full bg-slate-900/50 border border-slate-600/50 rounded text-xs text-slate-200 py-1.5 px-2 placeholder:text-slate-500 focus:outline-none focus:border-blue-500/50"
        />
      )}

      <div>
        <p className="text-[10px] text-slate-500 mb-1">
          {mode === 'dm' ? 'Select a friend:' : 'Select friends:'}
        </p>
        <div className="flex flex-wrap gap-1 max-h-32 overflow-y-auto">
          {friends.map((f: { id: number; display_name: string }) => (
            <button
              key={f.id}
              onClick={() => {
                if (mode === 'dm') setSelectedFriends([f.id])
                else toggleFriend(f.id)
              }}
              className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                selectedFriends.includes(f.id)
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700/60 text-slate-400 hover:bg-slate-600'
              }`}
            >
              {f.display_name}
            </button>
          ))}
          {friends.length === 0 && (
            <p className="text-[10px] text-slate-500">No friends yet. Add friends first!</p>
          )}
        </div>
      </div>

      <button
        onClick={handleCreate}
        disabled={
          createChannel.isPending ||
          (mode === 'dm' && selectedFriends.length !== 1) ||
          (mode === 'group' && !groupName.trim())
        }
        className="w-full py-1.5 rounded text-xs font-medium bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {createChannel.isPending ? 'Creating...' : mode === 'dm' ? 'Open Chat' : 'Create Group'}
      </button>
    </div>
  )
}

// ----- Channel List -----

function ChannelListItem({ channel, isActive, onClick }: {
  channel: ChatChannel
  isActive: boolean
  onClick: () => void
}) {
  const Icon = channel.type === 'dm' ? MessageSquare : channel.type === 'group' ? Users : Hash

  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2 py-1.5 px-2 rounded text-left transition-colors ${
        isActive ? 'bg-blue-600/20 text-blue-300' : 'text-slate-300 hover:bg-slate-700/40'
      }`}
    >
      <Icon className="w-3.5 h-3.5 shrink-0 text-slate-400" />
      <span className="text-xs truncate flex-1">{channel.name || 'Chat'}</span>
      {channel.unread_count > 0 && (
        <span className="bg-blue-500 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-full">
          {channel.unread_count > 99 ? '99+' : channel.unread_count}
        </span>
      )}
    </button>
  )
}

// ----- Message Bubble -----

function MessageBubble({ msg, isOwn, onEdit, onDelete, onReply, onReact, onPin, myRole, members }: {
  msg: ChatMessage
  isOwn: boolean
  onEdit: (id: number, content: string) => void
  onDelete: (id: number) => void
  onReply: (msg: ChatMessage) => void
  onReact: (messageId: number, emoji: string) => void
  onPin: (messageId: number) => void
  myRole: string
  members: ChatMember[]
}) {
  const { user } = useAuth()
  const [showEmojiPicker, setShowEmojiPicker] = useState(false)

  if (msg.is_deleted) {
    return (
      <div className="py-1 px-2">
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
    <div className="group py-1 px-2 rounded hover:bg-slate-700/20 relative">
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
      <p className="text-xs text-slate-200 whitespace-pre-wrap break-words mt-0.5">
        {renderContent(msg.content || '', members)}
      </p>

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

// ----- Message Input with @mention autocomplete -----

function ChatInput({ channelId, onTyping, editingMessage, onCancelEdit, replyingTo, onCancelReply, members }: {
  channelId: number
  onTyping: () => void
  editingMessage: { id: number; content: string } | null
  onCancelEdit: () => void
  replyingTo: ChatMessage | null
  onCancelReply: () => void
  members: ChatMember[]
}) {
  const [text, setText] = useState('')
  const [mentionQuery, setMentionQuery] = useState<string | null>(null)
  const [mentionIndex, setMentionIndex] = useState(0)
  const sendMessage = useSendMessage()
  const editMessage = useEditMessage()
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (editingMessage) {
      setText(editingMessage.content)
      inputRef.current?.focus()
    }
  }, [editingMessage])

  // Filter members for @mention autocomplete
  const mentionSuggestions = useMemo(() => {
    if (mentionQuery === null) return []
    return members
      .filter(m => m.display_name.toLowerCase().includes(mentionQuery.toLowerCase()))
      .slice(0, 5)
  }, [mentionQuery, members])

  const insertMention = (name: string) => {
    if (!inputRef.current) return
    const cursor = inputRef.current.selectionStart
    const beforeCursor = text.slice(0, cursor)
    const atIndex = beforeCursor.lastIndexOf('@')
    if (atIndex === -1) return
    const after = text.slice(cursor)
    const newText = beforeCursor.slice(0, atIndex) + `@${name} ` + after
    setText(newText)
    setMentionQuery(null)
    inputRef.current.focus()
  }

  const handleSend = async () => {
    const content = text.trim()
    if (!content) return

    try {
      if (editingMessage) {
        await editMessage.mutateAsync({ messageId: editingMessage.id, content })
        onCancelEdit()
      } else {
        await sendMessage.mutateAsync({
          channelId,
          content,
          replyToId: replyingTo?.id,
        })
        onCancelReply()
      }
      setText('')
    } catch {
      // error handled by mutation
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Handle mention autocomplete navigation
    if (mentionSuggestions.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setMentionIndex(i => Math.min(i + 1, mentionSuggestions.length - 1))
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setMentionIndex(i => Math.max(i - 1, 0))
        return
      }
      if (e.key === 'Tab' || e.key === 'Enter') {
        if (mentionSuggestions[mentionIndex]) {
          e.preventDefault()
          insertMention(mentionSuggestions[mentionIndex].display_name)
          return
        }
      }
      if (e.key === 'Escape') {
        setMentionQuery(null)
        return
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
    if (e.key === 'Escape') {
      if (editingMessage) { onCancelEdit(); setText('') }
      else if (replyingTo) onCancelReply()
    }
  }

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value
    setText(val)
    onTyping()

    // Detect @mention trigger
    const cursor = e.target.selectionStart
    const beforeCursor = val.slice(0, cursor)
    const atMatch = beforeCursor.match(/@(\w*)$/)
    if (atMatch) {
      setMentionQuery(atMatch[1])
      setMentionIndex(0)
    } else {
      setMentionQuery(null)
    }
  }

  const charCount = text.length
  const isOverLimit = charCount > 2000

  return (
    <div className="border-t border-slate-700/50 p-2">
      {/* Reply preview */}
      {replyingTo && (
        <div className="flex items-center justify-between mb-1 px-1 py-0.5 bg-slate-700/30 rounded">
          <div className="flex items-center gap-1 min-w-0">
            <Reply className="w-3 h-3 text-blue-400 shrink-0" />
            <span className="text-[10px] text-blue-400 shrink-0">{replyingTo.sender_name}</span>
            <span className="text-[10px] text-slate-500 truncate">
              {(replyingTo.content || '').slice(0, 60)}
            </span>
          </div>
          <button onClick={onCancelReply} className="text-slate-500 hover:text-slate-300 shrink-0 ml-1">
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      {/* Edit indicator */}
      {editingMessage && (
        <div className="flex items-center justify-between mb-1 px-1">
          <span className="text-[10px] text-blue-400">Editing message</span>
          <button onClick={() => { onCancelEdit(); setText('') }} className="text-slate-500 hover:text-slate-300">
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      <div className="relative">
        {/* @Mention autocomplete dropdown */}
        {mentionSuggestions.length > 0 && (
          <div className="absolute bottom-full left-0 mb-1 bg-slate-800 border border-slate-600/50 rounded-lg shadow-xl z-10 w-48">
            {mentionSuggestions.map((m, i) => (
              <button
                key={m.user_id}
                onClick={() => insertMention(m.display_name)}
                className={`w-full text-left px-2 py-1 text-xs transition-colors ${
                  i === mentionIndex ? 'bg-blue-600/30 text-blue-300' : 'text-slate-300 hover:bg-slate-700'
                }`}
              >
                @{m.display_name}
              </button>
            ))}
          </div>
        )}

        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={text}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Type a message... (@ to mention)"
            maxLength={2000}
            rows={1}
            className="flex-1 bg-slate-900/50 border border-slate-600/50 rounded text-xs text-slate-200 py-1.5 px-2 placeholder:text-slate-500 focus:outline-none focus:border-blue-500/50 resize-none max-h-20 overflow-y-auto"
            style={{ minHeight: '32px' }}
          />
          <button
            onClick={handleSend}
            disabled={!text.trim() || isOverLimit || sendMessage.isPending || editMessage.isPending}
            className="p-1.5 rounded bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      {charCount > 1800 && (
        <p className={`text-[9px] mt-0.5 text-right ${isOverLimit ? 'text-red-400' : 'text-slate-500'}`}>
          {charCount}/2000
        </p>
      )}
    </div>
  )
}

// ----- Channel Header -----

function ChannelHeader({ channel, onBack, onShowMembers, onShowSearch, onShowPinned, pinnedCount }: {
  channel: ChatChannel
  onBack: () => void
  onShowMembers: () => void
  onShowSearch: () => void
  onShowPinned: () => void
  pinnedCount: number
}) {
  const Icon = channel.type === 'dm' ? MessageSquare : channel.type === 'group' ? Users : Hash

  return (
    <div className="flex items-center gap-2 p-2 border-b border-slate-700/50">
      <button onClick={onBack} className="p-0.5 text-slate-400 hover:text-slate-200 sm:hidden">
        <ArrowLeft className="w-4 h-4" />
      </button>
      <Icon className="w-4 h-4 text-slate-400 shrink-0" />
      <h3 className="text-sm font-medium text-slate-200 truncate flex-1">{channel.name || 'Chat'}</h3>
      <div className="flex items-center gap-1">
        <button onClick={onShowSearch} className="p-1 text-slate-400 hover:text-slate-200" title="Search">
          <Search className="w-3.5 h-3.5" />
        </button>
        {pinnedCount > 0 && (
          <button onClick={onShowPinned} className="p-1 text-yellow-500/70 hover:text-yellow-500 relative" title="Pinned">
            <Pin className="w-3.5 h-3.5" />
            <span className="absolute -top-0.5 -right-0.5 bg-yellow-500 text-black text-[8px] font-bold w-3.5 h-3.5 rounded-full flex items-center justify-center">
              {pinnedCount}
            </span>
          </button>
        )}
        {channel.type !== 'dm' && (
          <button onClick={onShowMembers} className="p-1 text-slate-400 hover:text-slate-200" title="Members">
            <Users className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  )
}

// ----- Search Panel -----

function SearchPanel({ channelId, onClose, onJumpTo }: {
  channelId: number
  onClose: () => void
  onJumpTo: (messageId: number) => void
}) {
  const [query, setQuery] = useState('')
  const { data: results = [], isLoading } = useChatSearch(query, channelId)

  return (
    <div className="p-2 space-y-2 border-b border-slate-700/50">
      <div className="flex items-center gap-2">
        <Search className="w-3.5 h-3.5 text-slate-400 shrink-0" />
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search messages..."
          autoFocus
          className="flex-1 bg-slate-900/50 border border-slate-600/50 rounded text-xs text-slate-200 py-1 px-2 placeholder:text-slate-500 focus:outline-none focus:border-blue-500/50"
        />
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      {query.length >= 2 && (
        <div className="max-h-32 overflow-y-auto space-y-0.5">
          {isLoading ? (
            <p className="text-[10px] text-slate-500 py-1">Searching...</p>
          ) : results.length === 0 ? (
            <p className="text-[10px] text-slate-500 py-1">No results found</p>
          ) : (
            results.map(r => (
              <button
                key={r.id}
                onClick={() => onJumpTo(r.id)}
                className="w-full text-left px-2 py-1 rounded hover:bg-slate-700/30 transition-colors"
              >
                <div className="flex items-baseline gap-1">
                  <span className="text-[10px] font-medium text-slate-300">{r.sender_name}</span>
                  <span className="text-[9px] text-slate-600">
                    {r.created_at ? new Date(r.created_at).toLocaleDateString() : ''}
                  </span>
                </div>
                <p className="text-[10px] text-slate-400 truncate">{r.content}</p>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}

// ----- Pinned Messages Panel -----

function PinnedPanel({ channelId, onClose }: {
  channelId: number
  onClose: () => void
}) {
  const { data: pinned = [] } = usePinnedMessages(channelId)

  return (
    <div className="p-2 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          <Pin className="w-3.5 h-3.5 text-yellow-500" />
          <h4 className="text-xs font-medium text-slate-300">Pinned Messages ({pinned.length})</h4>
        </div>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-xs">Close</button>
      </div>
      <div className="max-h-48 overflow-y-auto space-y-1">
        {pinned.length === 0 ? (
          <p className="text-[10px] text-slate-500 py-2">No pinned messages</p>
        ) : (
          pinned.map(msg => (
            <div key={msg.id} className="px-2 py-1 bg-slate-700/20 rounded">
              <div className="flex items-baseline gap-1">
                <span className="text-[10px] font-medium text-slate-300">{msg.sender_name}</span>
                <span className="text-[9px] text-slate-600">
                  {msg.created_at ? new Date(msg.created_at).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }) : ''}
                </span>
              </div>
              <p className="text-[10px] text-slate-400">{msg.content}</p>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

// ----- Members Panel -----

function MembersPanel({ channelId, channel, onClose, onDeleted }: {
  channelId: number
  channel: ChatChannel
  onClose: () => void
  onDeleted: () => void
}) {
  const { user } = useAuth()
  const { data: members = [] } = useChannelMembers(channelId)
  const { data: friends = [] } = useFriends()
  const { data: onlineFriends = [] } = useOnlineFriends()
  const addMember = useAddMember()
  const removeMember = useRemoveMember()
  const deleteChannel = useDeleteChannel()
  const updateRole = useUpdateMemberRole()
  const [showAdd, setShowAdd] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const isOwner = channel.my_role === 'owner'
  const canManage = isOwner || channel.my_role === 'admin'
  const memberIds = new Set(members.map(m => m.user_id))
  const onlineIds = new Set(onlineFriends.map((f: { id: number }) => f.id))

  const availableFriends = friends.filter((f: { id: number }) => !memberIds.has(f.id))

  const handleDelete = async () => {
    try {
      await deleteChannel.mutateAsync(channelId)
      onDeleted()
    } catch {
      // error handled by mutation
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-medium text-slate-300">Members ({members.length})</h4>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-xs">Close</button>
      </div>

      <div className="space-y-0.5 max-h-40 overflow-y-auto">
        {members.map(m => (
          <div key={m.user_id} className="flex items-center justify-between py-0.5 px-1">
            <div className="flex items-center gap-1">
              {/* Online presence dot */}
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                onlineIds.has(m.user_id) || m.user_id === user?.id
                  ? 'bg-green-500' : 'bg-slate-600'
              }`} />
              <span className="text-xs text-slate-300">{m.display_name}</span>
              {m.role !== 'member' && (
                <span className="text-[9px] text-slate-500">({m.role})</span>
              )}
              {m.user_id === user?.id && (
                <span className="text-[9px] text-slate-600">(you)</span>
              )}
            </div>
            <div className="flex items-center gap-1">
              {isOwner && m.user_id !== user?.id && (
                <button
                  onClick={() => updateRole.mutate({
                    channelId,
                    userId: m.user_id,
                    role: m.role === 'admin' ? 'member' : 'admin',
                  })}
                  className={`text-[9px] px-1.5 py-0.5 rounded transition-colors ${
                    m.role === 'admin'
                      ? 'bg-yellow-600/20 text-yellow-400 hover:bg-yellow-600/40'
                      : 'bg-slate-700/40 text-slate-500 hover:bg-slate-600/40 hover:text-slate-300'
                  }`}
                  title={m.role === 'admin' ? 'Demote to member' : 'Promote to admin'}
                >
                  {m.role === 'admin' ? 'Admin' : 'Make Admin'}
                </button>
              )}
              {canManage && m.user_id !== user?.id && (
                <button
                  onClick={() => removeMember.mutate({ channelId, userId: m.user_id })}
                  className="text-slate-500 hover:text-red-400 p-0.5"
                  title="Remove"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {channel.type !== 'dm' && !isOwner && (
        <button
          onClick={() => removeMember.mutate({ channelId, userId: user!.id })}
          className="flex items-center gap-1 px-2 py-1 rounded text-[10px] bg-red-600/20 text-red-400 hover:bg-red-600/40"
        >
          <LogOut className="w-3 h-3" /> Leave
        </button>
      )}

      {isOwner && channel.type !== 'dm' && (
        !confirmDelete ? (
          <button
            onClick={() => setConfirmDelete(true)}
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] bg-red-600/20 text-red-400 hover:bg-red-600/40"
          >
            <Trash2 className="w-3 h-3" /> Delete Group
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-red-400">Delete this group?</span>
            <button
              onClick={handleDelete}
              disabled={deleteChannel.isPending}
              className="px-2 py-0.5 rounded text-[10px] bg-red-600 text-white hover:bg-red-500 disabled:opacity-40"
            >
              {deleteChannel.isPending ? '...' : 'Yes'}
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="px-2 py-0.5 rounded text-[10px] bg-slate-700 text-slate-300 hover:bg-slate-600"
            >
              No
            </button>
          </div>
        )
      )}

      {canManage && channel.type !== 'dm' && (
        <>
          {!showAdd ? (
            <button
              onClick={() => setShowAdd(true)}
              className="flex items-center gap-1 px-2 py-1 rounded text-[10px] bg-green-600/20 text-green-400 hover:bg-green-600/40"
            >
              <UserPlus className="w-3 h-3" /> Add Member
            </button>
          ) : (
            <div className="space-y-1">
              <p className="text-[10px] text-slate-500">Add a friend:</p>
              <div className="flex flex-wrap gap-1 max-h-20 overflow-y-auto">
                {availableFriends.map((f: { id: number; display_name: string }) => (
                  <button
                    key={f.id}
                    onClick={() => addMember.mutate({ channelId, userId: f.id })}
                    className="px-2 py-0.5 rounded text-[10px] bg-slate-700/60 text-slate-400 hover:bg-slate-600"
                  >
                    {f.display_name}
                  </button>
                ))}
                {availableFriends.length === 0 && (
                  <p className="text-[10px] text-slate-600">All friends are already members</p>
                )}
              </div>
              <button onClick={() => setShowAdd(false)} className="text-[10px] text-slate-500 hover:text-slate-300">
                Cancel
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ----- Main Chat Panel -----

export function ChatPanel() {
  const { user } = useAuth()
  const { data: channels = [], isLoading } = useChatChannels()
  const [activeChannelId, setActiveChannelId] = useState<number | null>(null)
  const [showNewChat, setShowNewChat] = useState(false)
  const [showMembers, setShowMembers] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const [showPinned, setShowPinned] = useState(false)
  const [editingMessage, setEditingMessage] = useState<{ id: number; content: string } | null>(null)
  const [replyingTo, setReplyingTo] = useState<ChatMessage | null>(null)
  const [isOpen, setIsOpen] = useState(true)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)

  const { typingNames, sendTyping, toasts, dismissToast } = useChatSocket(activeChannelId)
  const toggleReaction = useToggleReaction()
  const togglePin = useTogglePin()

  const activeChannel = useMemo(
    () => channels.find(c => c.id === activeChannelId) || null,
    [channels, activeChannelId]
  )

  const {
    data: messagePages,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useChatMessages(activeChannelId)

  const messages = useMemo(
    () => messagePages?.pages.flat() ?? [],
    [messagePages]
  )

  const { data: members = [] } = useChannelMembers(activeChannelId)
  const { data: pinnedMessages = [] } = usePinnedMessages(activeChannelId)

  const markRead = useMarkRead()
  const deleteMessage = useDeleteMessage()

  // Mark as read when viewing a channel
  useEffect(() => {
    if (activeChannelId && activeChannel && activeChannel.unread_count > 0) {
      markRead.mutate(activeChannelId)
    }
  }, [activeChannelId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-scroll to bottom on new messages
  const prevMessageCount = useRef(0)
  useEffect(() => {
    if (messages.length > prevMessageCount.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
    prevMessageCount.current = messages.length
  }, [messages.length])

  // Load older messages on scroll to top
  const handleScroll = useCallback(() => {
    const container = messagesContainerRef.current
    if (!container) return
    if (container.scrollTop < 50 && hasNextPage && !isFetchingNextPage) {
      fetchNextPage()
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  const handleTyping = useCallback(() => {
    if (activeChannelId) sendTyping(activeChannelId)
  }, [activeChannelId, sendTyping])

  const totalUnread = useMemo(
    () => channels.reduce((sum, c) => sum + c.unread_count, 0),
    [channels]
  )

  const handleReact = useCallback((messageId: number, emoji: string) => {
    toggleReaction.mutate({ messageId, emoji })
  }, [toggleReaction])

  const handlePin = useCallback((messageId: number) => {
    togglePin.mutate(messageId)
  }, [togglePin])

  return (
    <>
      <ChatToastOverlay toasts={toasts} onDismiss={dismissToast} />

      <div className="bg-slate-800/60 rounded-lg border border-slate-700/50">
        {/* Toggle header */}
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-700/30 rounded-lg transition-colors"
        >
          <div className="flex items-center gap-2">
            <MessageSquare className="w-4 h-4 text-blue-400" />
            <span className="text-sm font-medium text-slate-200">Chat</span>
            {totalUnread > 0 && (
              <span className="bg-blue-500 text-white text-xs px-1.5 py-0.5 rounded-full">
                {totalUnread > 99 ? '99+' : totalUnread}
              </span>
            )}
          </div>
          {isOpen ? (
            <ChevronUp className="w-4 h-4 text-slate-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-slate-400" />
          )}
        </button>

        {isOpen && (
          <div className="px-3 pb-3">
            {showNewChat ? (
              <NewChatDialog
                onClose={() => setShowNewChat(false)}
                onCreated={(id) => {
                  setShowNewChat(false)
                  setActiveChannelId(id)
                }}
              />
            ) : activeChannelId && activeChannel ? (
              /* Active channel view */
              <div>
                <ChannelHeader
                  channel={activeChannel}
                  onBack={() => {
                    setActiveChannelId(null)
                    setShowMembers(false)
                    setShowSearch(false)
                    setShowPinned(false)
                    setEditingMessage(null)
                    setReplyingTo(null)
                  }}
                  onShowMembers={() => {
                    setShowMembers(!showMembers)
                    setShowSearch(false)
                    setShowPinned(false)
                  }}
                  onShowSearch={() => {
                    setShowSearch(!showSearch)
                    setShowMembers(false)
                    setShowPinned(false)
                  }}
                  onShowPinned={() => {
                    setShowPinned(!showPinned)
                    setShowMembers(false)
                    setShowSearch(false)
                  }}
                  pinnedCount={pinnedMessages.length}
                />

                {/* Search panel */}
                {showSearch && (
                  <SearchPanel
                    channelId={activeChannelId}
                    onClose={() => setShowSearch(false)}
                    onJumpTo={() => setShowSearch(false)}
                  />
                )}

                {/* Pinned messages panel */}
                {showPinned ? (
                  <PinnedPanel
                    channelId={activeChannelId}
                    onClose={() => setShowPinned(false)}
                  />
                ) : showMembers ? (
                  <div className="p-2">
                    <MembersPanel
                      channelId={activeChannelId}
                      channel={activeChannel}
                      onClose={() => setShowMembers(false)}
                      onDeleted={() => {
                        setActiveChannelId(null)
                        setShowMembers(false)
                      }}
                    />
                  </div>
                ) : (
                  <>
                    {/* Messages area */}
                    <div
                      ref={messagesContainerRef}
                      onScroll={handleScroll}
                      className="h-64 overflow-y-auto space-y-0.5 py-2"
                    >
                      {isFetchingNextPage && (
                        <p className="text-[10px] text-slate-500 text-center py-1">Loading older...</p>
                      )}
                      {messages.length === 0 ? (
                        <p className="text-xs text-slate-500 text-center py-8">
                          No messages yet. Say hello!
                        </p>
                      ) : (
                        messages.map(msg => (
                          <MessageBubble
                            key={msg.id}
                            msg={msg}
                            isOwn={msg.sender_id === user?.id}
                            myRole={activeChannel.my_role}
                            members={members}
                            onEdit={(id, content) => setEditingMessage({ id, content })}
                            onDelete={(id) => deleteMessage.mutate(id)}
                            onReply={(m) => setReplyingTo(m)}
                            onReact={handleReact}
                            onPin={handlePin}
                          />
                        ))
                      )}
                      <div ref={messagesEndRef} />
                    </div>

                    {/* Typing indicator */}
                    {typingNames.length > 0 && (
                      <p className="text-[10px] text-slate-500 px-2 py-0.5">
                        {typingNames.join(', ')} {typingNames.length === 1 ? 'is' : 'are'} typing...
                      </p>
                    )}

                    {/* Input */}
                    <ChatInput
                      channelId={activeChannelId}
                      onTyping={handleTyping}
                      editingMessage={editingMessage}
                      onCancelEdit={() => setEditingMessage(null)}
                      replyingTo={replyingTo}
                      onCancelReply={() => setReplyingTo(null)}
                      members={members}
                    />
                  </>
                )}
              </div>
            ) : (
              /* Channel list view */
              <>
                <button
                  onClick={() => setShowNewChat(true)}
                  className="w-full flex items-center justify-center gap-1 py-1.5 mb-2 rounded text-xs bg-blue-600/20 text-blue-400 hover:bg-blue-600/40 transition-colors"
                >
                  <Plus className="w-3 h-3" /> New Chat
                </button>

                {isLoading ? (
                  <p className="text-xs text-slate-500 py-2">Loading...</p>
                ) : channels.length === 0 ? (
                  <p className="text-xs text-slate-500 py-2">No chats yet. Start a conversation!</p>
                ) : (
                  <div className="space-y-0.5 max-h-64 overflow-y-auto">
                    {channels.map(ch => (
                      <ChannelListItem
                        key={ch.id}
                        channel={ch}
                        isActive={ch.id === activeChannelId}
                        onClick={() => setActiveChannelId(ch.id)}
                      />
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </>
  )
}
