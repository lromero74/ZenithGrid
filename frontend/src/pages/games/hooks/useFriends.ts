/**
 * React hooks for friends system API calls.
 *
 * Uses React Query for caching and the api service for HTTP requests.
 */

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../../services/api'

export interface Friend {
  id: number
  display_name: string
}

export interface FriendRequestItem {
  id: number
  from_user_id: number
  from_display_name: string
  created_at: string | null
}

export interface BlockedUserItem {
  user_id: number
  display_name: string
}

export interface UserSearchResult {
  id: number
  display_name: string
}

// ----- Friends List -----

export function useFriends() {
  return useQuery<Friend[]>({
    queryKey: ['friends'],
    queryFn: async () => {
      const { data } = await api.get('/friends')
      return data
    },
    staleTime: 30_000,
  })
}

// ----- Friend Requests -----

export function useFriendRequests() {
  return useQuery<FriendRequestItem[]>({
    queryKey: ['friend-requests'],
    queryFn: async () => {
      const { data } = await api.get('/friends/requests')
      return data
    },
    staleTime: 15_000,
  })
}

export function useSendFriendRequest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (displayName: string) => {
      const { data } = await api.post('/friends/request', { display_name: displayName })
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['friend-requests'] })
      qc.invalidateQueries({ queryKey: ['sent-friend-requests'] })
    },
  })
}

export interface SentRequestItem {
  id: number
  to_user_id: number
  to_display_name: string
  created_at: string | null
}

export function useSentFriendRequests() {
  return useQuery<SentRequestItem[]>({
    queryKey: ['sent-friend-requests'],
    queryFn: async () => {
      const { data } = await api.get('/friends/requests/sent')
      return data
    },
    staleTime: 15_000,
  })
}

export function useCancelSentRequest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (requestId: number) => {
      const { data } = await api.delete(`/friends/requests/sent/${requestId}`)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sent-friend-requests'] })
    },
  })
}

export function useAcceptFriendRequest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (requestId: number) => {
      const { data } = await api.post(`/friends/requests/${requestId}/accept`)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['friends'] })
      qc.invalidateQueries({ queryKey: ['friend-requests'] })
    },
  })
}

export function useRejectFriendRequest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (requestId: number) => {
      const { data } = await api.delete(`/friends/requests/${requestId}`)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['friend-requests'] })
    },
  })
}

// ----- Remove Friend -----

export function useRemoveFriend() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (friendId: number) => {
      const { data } = await api.delete(`/friends/${friendId}`)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['friends'] })
    },
  })
}

// ----- Block / Unblock -----

export function useBlockUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (userId: number) => {
      const { data } = await api.post('/friends/block', { user_id: userId })
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['friends'] })
      qc.invalidateQueries({ queryKey: ['blocked-users'] })
      qc.invalidateQueries({ queryKey: ['friend-requests'] })
    },
  })
}

export function useUnblockUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (userId: number) => {
      const { data } = await api.delete(`/friends/block/${userId}`)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['blocked-users'] })
    },
  })
}

export function useBlockedUsers() {
  return useQuery<BlockedUserItem[]>({
    queryKey: ['blocked-users'],
    queryFn: async () => {
      const { data } = await api.get('/friends/blocked')
      return data
    },
    staleTime: 60_000,
  })
}

// ----- User Search (debounced) -----

function useDebouncedValue(value: string, delayMs: number): string {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

export function useUserSearch(query: string) {
  const debouncedQuery = useDebouncedValue(query, 300)
  return useQuery<UserSearchResult[]>({
    queryKey: ['user-search', debouncedQuery],
    queryFn: async () => {
      if (!debouncedQuery || debouncedQuery.length < 1) return []
      const { data } = await api.get('/users/search', { params: { q: debouncedQuery } })
      return data
    },
    enabled: debouncedQuery.length >= 1,
    staleTime: 10_000,
  })
}

// ----- Display Name -----

export function useCheckDisplayName(name: string) {
  return useQuery<{ available: boolean; name?: string; reason?: string }>({
    queryKey: ['display-name-check', name],
    queryFn: async () => {
      const { data } = await api.get('/users/display-name/check', { params: { name } })
      return data
    },
    enabled: name.length >= 3,
    staleTime: 5_000,
  })
}

export interface OnlineFriendInfo {
  id: number
  display_name?: string | null
  game_id?: string | null
  room_id?: string | null
  room_status?: string | null  // "waiting" or "playing"
  player_count?: number | null
  max_players?: number | null
  mode?: string | null  // "vs" or "race"
}

/** Get online friends with game room info. Polls every 30s. */
export function useOnlineFriends() {
  return useQuery<OnlineFriendInfo[]>({
    queryKey: ['online-friends'],
    queryFn: async () => {
      const { data } = await api.get('/friends/online')
      return data
    },
    refetchInterval: 30_000,
    staleTime: 15_000,
  })
}

export function useSetDisplayName() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (displayName: string) => {
      const { data } = await api.put('/users/display-name', { display_name: displayName })
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['display-name-check'] })
    },
  })
}
