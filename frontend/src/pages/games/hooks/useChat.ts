/**
 * React Query hooks for the chat API.
 *
 * Provides hooks for channels, messages, membership, reactions,
 * pinned messages, search, and unread counts.
 */

import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from '@tanstack/react-query'
import { api } from '../../../services/api'

// ----- Types -----

export interface ChatChannelLastMessage {
  id: number
  sender_id: number
  sender_name: string
  content: string
  created_at: string | null
}

export interface ChatChannel {
  id: number
  type: 'dm' | 'group' | 'channel'
  name: string | null
  member_count: number
  unread_count: number
  last_message: ChatChannelLastMessage | null
  my_role: 'owner' | 'admin' | 'member'
  updated_at: string | null
}

export interface ChatReaction {
  emoji: string
  count: number
  user_ids: number[]
}

export interface ChatReplyTo {
  id: number
  sender_name: string
  content: string | null
  is_deleted: boolean
}

export interface ChatMessage {
  id: number
  channel_id: number
  sender_id: number
  sender_name: string
  content: string | null
  is_deleted: boolean
  edited_at: string | null
  created_at: string | null
  is_pinned: boolean
  reply_to: ChatReplyTo | null
  reactions: ChatReaction[]
}

export interface ChatMember {
  user_id: number
  display_name: string
  role: 'owner' | 'admin' | 'member'
  joined_at: string | null
}

export interface ChatSearchResult extends ChatMessage {
  channel_name: string | null
  channel_type: string | null
}

// ----- Channel Hooks -----

export function useChatChannels() {
  return useQuery<ChatChannel[]>({
    queryKey: ['chat-channels'],
    queryFn: async () => {
      const { data } = await api.get('/chat/channels')
      return data
    },
    staleTime: 10_000,
  })
}

export function useCreateChannel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: {
      type: 'dm' | 'group' | 'channel'
      name?: string
      member_ids?: number[]
      friend_id?: number
    }) => {
      const { data } = await api.post('/chat/channels', payload)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['chat-channels'] })
    },
  })
}

export function useDeleteChannel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (channelId: number) => {
      const { data } = await api.delete(`/chat/channels/${channelId}`)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['chat-channels'] })
    },
  })
}

export function useUpdateMemberRole() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ channelId, userId, role }: {
      channelId: number; userId: number; role: 'admin' | 'member'
    }) => {
      const { data } = await api.patch(`/chat/channels/${channelId}/roles`, { user_id: userId, role })
      return data
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['chat-members', variables.channelId] })
    },
  })
}

// ----- Message Hooks -----

export function useChatMessages(channelId: number | null) {
  return useInfiniteQuery<ChatMessage[]>({
    queryKey: ['chat-messages', channelId],
    queryFn: async ({ pageParam }) => {
      const params: Record<string, string | number> = { limit: 50 }
      if (pageParam) params.before = pageParam as number
      const { data } = await api.get(`/chat/channels/${channelId}/messages`, { params })
      return data
    },
    initialPageParam: null as number | null,
    getNextPageParam: (lastPage) => {
      if (lastPage.length < 50) return undefined
      return lastPage[0]?.id ?? undefined
    },
    enabled: channelId !== null,
    staleTime: 5_000,
  })
}

export function useSendMessage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ channelId, content, replyToId }: {
      channelId: number; content: string; replyToId?: number
    }) => {
      const { data } = await api.post(`/chat/channels/${channelId}/messages`, {
        content,
        reply_to_id: replyToId ?? null,
      })
      return data
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['chat-messages', variables.channelId] })
      qc.invalidateQueries({ queryKey: ['chat-channels'] })
    },
  })
}

export function useEditMessage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ messageId, content }: { messageId: number; content: string }) => {
      const { data } = await api.patch(`/chat/messages/${messageId}`, { content })
      return data
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['chat-messages', data.channel_id] })
    },
  })
}

export function useDeleteMessage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (messageId: number) => {
      const { data } = await api.delete(`/chat/messages/${messageId}`)
      return data
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['chat-messages', data.channel_id] })
      qc.invalidateQueries({ queryKey: ['chat-channels'] })
    },
  })
}

// ----- Read Tracking -----

export function useMarkRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (channelId: number) => {
      const { data } = await api.post(`/chat/channels/${channelId}/read`)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['chat-channels'] })
      qc.invalidateQueries({ queryKey: ['chat-unread'] })
    },
  })
}

export function useUnreadCounts() {
  return useQuery<Record<string, number>>({
    queryKey: ['chat-unread'],
    queryFn: async () => {
      const { data } = await api.get('/chat/unread')
      return data.counts
    },
    staleTime: 15_000,
    refetchInterval: 30_000,
  })
}

// ----- Membership -----

export function useChannelMembers(channelId: number | null) {
  return useQuery<ChatMember[]>({
    queryKey: ['chat-members', channelId],
    queryFn: async () => {
      const { data } = await api.get(`/chat/channels/${channelId}/members`)
      return data
    },
    enabled: channelId !== null,
    staleTime: 30_000,
  })
}

export function useAddMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ channelId, userId }: { channelId: number; userId: number }) => {
      const { data } = await api.post(`/chat/channels/${channelId}/members`, { user_id: userId })
      return data
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['chat-members', variables.channelId] })
      qc.invalidateQueries({ queryKey: ['chat-channels'] })
    },
  })
}

export function useRemoveMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ channelId, userId }: { channelId: number; userId: number }) => {
      const { data } = await api.delete(`/chat/channels/${channelId}/members/${userId}`)
      return data
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['chat-members', variables.channelId] })
      qc.invalidateQueries({ queryKey: ['chat-channels'] })
    },
  })
}

// ----- Reactions -----

export function useToggleReaction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ messageId, emoji }: { messageId: number; emoji: string }) => {
      const { data } = await api.post(`/chat/messages/${messageId}/reactions`, { emoji })
      return data
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['chat-messages', data.channel_id] })
    },
  })
}

// ----- Pinned Messages -----

export function useTogglePin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (messageId: number) => {
      const { data } = await api.post(`/chat/messages/${messageId}/pin`)
      return data
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['chat-messages', data.channel_id] })
      qc.invalidateQueries({ queryKey: ['chat-pinned', data.channel_id] })
    },
  })
}

export function usePinnedMessages(channelId: number | null) {
  return useQuery<ChatMessage[]>({
    queryKey: ['chat-pinned', channelId],
    queryFn: async () => {
      const { data } = await api.get(`/chat/channels/${channelId}/pinned`)
      return data
    },
    enabled: channelId !== null,
    staleTime: 30_000,
  })
}

// ----- Search -----

export function useChatSearch(query: string, channelId?: number | null) {
  return useQuery<ChatSearchResult[]>({
    queryKey: ['chat-search', query, channelId],
    queryFn: async () => {
      const params: Record<string, string | number> = { q: query }
      if (channelId) params.channel_id = channelId
      const { data } = await api.get('/chat/search', { params })
      return data
    },
    enabled: query.length >= 2,
    staleTime: 10_000,
  })
}
