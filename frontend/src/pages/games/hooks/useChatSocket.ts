/**
 * WebSocket listener for real-time chat events.
 *
 * Registers listeners on gameSocket for chat:message, chat:typing,
 * chat:read_receipt, chat:message_edited, chat:message_deleted,
 * chat:reaction_updated, and chat:pin_updated.
 * Invalidates React Query caches and fires toast notifications.
 */

import { useEffect, useRef, useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { gameSocket } from '../../../services/gameSocket'
import { useAuth } from '../../../contexts/AuthContext'
import type { ChatMessage } from './useChat'

interface ChatToast {
  id: number
  senderName: string
  content: string
  channelId: number
  duration: number
}

/**
 * Hook that listens for real-time chat events and updates caches.
 *
 * @param activeChannelId - The channel currently being viewed (no toast for it)
 * @returns typing indicators and toast state
 */
export function useChatSocket(activeChannelId: number | null) {
  const qc = useQueryClient()
  const { user } = useAuth()
  const userId = user?.id
  const [typingUsers, setTypingUsers] = useState<Map<number, { name: string; expires: number }>>(new Map())
  const [toasts, setToasts] = useState<ChatToast[]>([])
  const activeChannelRef = useRef(activeChannelId)
  activeChannelRef.current = activeChannelId

  // Incoming message
  useEffect(() => {
    const unsub = gameSocket.on('chat:message', (msg: ChatMessage) => {
      qc.invalidateQueries({ queryKey: ['chat-messages', msg.channel_id] })
      qc.invalidateQueries({ queryKey: ['chat-channels'] })
      qc.invalidateQueries({ queryKey: ['chat-unread'] })

      // Clear typing indicator for this sender
      setTypingUsers(prev => {
        const next = new Map(prev)
        next.delete(msg.sender_id)
        return next
      })

      // Toast if not from self and not viewing this channel
      if (msg.sender_id !== userId && msg.channel_id !== activeChannelRef.current) {
        const wordCount = (msg.content || '').split(/\s+/).length
        const duration = Math.max(3000, Math.min(10000, wordCount * 200))
        const toast: ChatToast = {
          id: msg.id,
          senderName: msg.sender_name,
          content: (msg.content || '').slice(0, 100),
          channelId: msg.channel_id,
          duration,
        }
        setToasts(prev => [...prev.slice(-4), toast])
      }
    })
    return unsub
  }, [qc, userId])

  // Typing indicator
  useEffect(() => {
    const unsub = gameSocket.on('chat:typing', (msg: { channelId: number; userId: number; displayName: string }) => {
      if (msg.userId === userId) return
      setTypingUsers(prev => {
        const next = new Map(prev)
        next.set(msg.userId, { name: msg.displayName, expires: Date.now() + 3000 })
        return next
      })
    })
    return unsub
  }, [userId])

  // Clear expired typing indicators
  useEffect(() => {
    const interval = setInterval(() => {
      setTypingUsers(prev => {
        const now = Date.now()
        let changed = false
        const next = new Map(prev)
        for (const [uid, info] of next) {
          if (info.expires < now) {
            next.delete(uid)
            changed = true
          }
        }
        return changed ? next : prev
      })
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  // Read receipt
  useEffect(() => {
    const unsub = gameSocket.on('chat:read_receipt', () => {
      qc.invalidateQueries({ queryKey: ['chat-channels'] })
    })
    return unsub
  }, [qc])

  // Message edited
  useEffect(() => {
    const unsub = gameSocket.on('chat:message_edited', (msg: { channel_id: number }) => {
      qc.invalidateQueries({ queryKey: ['chat-messages', msg.channel_id] })
    })
    return unsub
  }, [qc])

  // Message deleted
  useEffect(() => {
    const unsub = gameSocket.on('chat:message_deleted', (msg: { channelId: number }) => {
      qc.invalidateQueries({ queryKey: ['chat-messages', msg.channelId] })
      qc.invalidateQueries({ queryKey: ['chat-channels'] })
    })
    return unsub
  }, [qc])

  // Reaction updated
  useEffect(() => {
    const unsub = gameSocket.on('chat:reaction_updated', (msg: { channelId: number }) => {
      qc.invalidateQueries({ queryKey: ['chat-messages', msg.channelId] })
    })
    return unsub
  }, [qc])

  // Pin updated
  useEffect(() => {
    const unsub = gameSocket.on('chat:pin_updated', (msg: { channelId: number }) => {
      qc.invalidateQueries({ queryKey: ['chat-messages', msg.channelId] })
      qc.invalidateQueries({ queryKey: ['chat-pinned', msg.channelId] })
    })
    return unsub
  }, [qc])

  // Auto-dismiss toasts
  useEffect(() => {
    if (toasts.length === 0) return
    const oldest = toasts[0]
    const timer = setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== oldest.id))
    }, oldest.duration)
    return () => clearTimeout(timer)
  }, [toasts])

  const dismissToast = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  // Get typing names for the active channel
  const typingNames = activeChannelId
    ? Array.from(typingUsers.values()).map(t => t.name)
    : []

  // Send typing indicator
  const sendTyping = useCallback((channelId: number) => {
    gameSocket.send({ type: 'chat:typing', channelId })
  }, [])

  return {
    typingNames,
    sendTyping,
    toasts,
    dismissToast,
  }
}
