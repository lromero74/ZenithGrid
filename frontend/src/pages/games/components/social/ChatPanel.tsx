/**
 * Chat Panel — DMs, group chats, and channels.
 *
 * Orchestrates the channel list, active channel view, and sub-panels
 * (search, pinned, members). Sub-components are extracted into separate files.
 */

import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import {
  MessageSquare, Plus, ArrowLeft, Users, Hash, ShieldCheck,
  ChevronDown, ChevronUp, Search, Pin, X,
} from 'lucide-react'
import { useAuth } from '../../../../contexts/AuthContext'
import {
  useChatChannels, useChatMessages, useMarkRead,
  useDeleteMessage, useChannelMembers, useToggleReaction,
  useTogglePin, usePinnedMessages, useChatSearch,
} from '../../hooks/useChat'
import { useChatSocket } from '../../hooks/useChatSocket'
import type { ChatChannel, ChatMessage } from '../../hooks/useChat'
import { MessageBubble } from './MessageBubble'
import { ChatInput } from './ChatInput'
import { MembersPanel } from './MembersPanel'
import { NewChatDialog } from './NewChatDialog'

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

// ----- Channel List Item -----

function ChannelListItem({ channel, isActive, onClick }: {
  channel: ChatChannel
  isActive: boolean
  onClick: () => void
}) {
  const Icon = channel.type === 'admin_dm' ? ShieldCheck : channel.type === 'dm' ? MessageSquare : channel.type === 'group' ? Users : Hash

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

// ----- Channel Header -----

function ChannelHeader({ channel, onBack, onShowMembers, onShowSearch, onShowPinned, pinnedCount }: {
  channel: ChatChannel
  onBack: () => void
  onShowMembers: () => void
  onShowSearch: () => void
  onShowPinned: () => void
  pinnedCount: number
}) {
  const Icon = channel.type === 'admin_dm' ? ShieldCheck : channel.type === 'dm' ? MessageSquare : channel.type === 'group' ? Users : Hash

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
        {channel.type !== 'dm' && channel.type !== 'admin_dm' && (
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
    () => (messagePages?.pages.flat() ?? []).sort((a, b) => a.id - b.id),
    [messagePages]
  )

  const { data: members = [] } = useChannelMembers(activeChannelId)
  const { data: pinnedMessages = [] } = usePinnedMessages(activeChannelId)

  const markRead = useMarkRead()
  const deleteMessage = useDeleteMessage()

  // Mark as read when viewing a channel or when new messages arrive while viewing
  useEffect(() => {
    if (activeChannelId && activeChannel && activeChannel.unread_count > 0) {
      markRead.mutate(activeChannelId)
    }
  }, [activeChannelId, activeChannel?.unread_count]) // eslint-disable-line react-hooks/exhaustive-deps

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

  // Jump to a specific message by scrolling it into view (S17 fix)
  const handleJumpTo = useCallback((messageId: number) => {
    setShowSearch(false)
    // Brief delay to let search panel close before scrolling
    setTimeout(() => {
      const el = document.getElementById(`msg-${messageId}`)
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        el.classList.add('bg-blue-500/20')
        setTimeout(() => el.classList.remove('bg-blue-500/20'), 2000)
      }
    }, 100)
  }, [])

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
                    onJumpTo={handleJumpTo}
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
                            id={`msg-${msg.id}`}
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
