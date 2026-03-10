/**
 * React hooks for session management API calls.
 *
 * Uses React Query for caching and the api service for HTTP requests.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../../services/api'

export interface SessionInfo {
  session_id: string
  ip_address: string | null
  user_agent: string | null
  created_at: string | null
}

export function useOtherSessions() {
  return useQuery<SessionInfo[]>({
    queryKey: ['other-sessions'],
    queryFn: async () => {
      const { data } = await api.get('/sessions/active')
      return data
    },
    staleTime: 10_000,
  })
}

export function useTerminateSessions() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (sessionIds: string[]) => {
      const { data } = await api.post('/sessions/terminate', { session_ids: sessionIds })
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['other-sessions'] })
    },
  })
}

export function useTerminateAllOtherSessions() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post('/sessions/terminate-others')
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['other-sessions'] })
    },
  })
}
