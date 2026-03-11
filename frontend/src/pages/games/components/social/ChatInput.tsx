/**
 * ChatInput — message compose box with @mention autocomplete.
 *
 * Features: reply preview, edit mode, @mention dropdown with
 * keyboard navigation (arrow keys, Tab/Enter to select, Escape to cancel),
 * character limit indicator, and Shift+Enter for newlines.
 */

import { useState, useRef, useEffect, useMemo } from 'react'
import { Send, Reply, X } from 'lucide-react'
import { useSendMessage, useEditMessage } from '../../hooks/useChat'
import type { ChatMessage, ChatMember } from '../../hooks/useChat'

const MAX_MESSAGE_LENGTH = 2000
const CHAR_WARN_THRESHOLD = 1800

export function ChatInput({ channelId, onTyping, editingMessage, onCancelEdit, replyingTo, onCancelReply, members }: {
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
  const isOverLimit = charCount > MAX_MESSAGE_LENGTH

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
            maxLength={MAX_MESSAGE_LENGTH}
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
      {charCount > CHAR_WARN_THRESHOLD && (
        <p className={`text-[9px] mt-0.5 text-right ${isOverLimit ? 'text-red-400' : 'text-slate-500'}`}>
          {charCount}/{MAX_MESSAGE_LENGTH}
        </p>
      )}
    </div>
  )
}
