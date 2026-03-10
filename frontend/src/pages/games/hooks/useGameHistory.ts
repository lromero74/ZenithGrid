/**
 * React Query hooks for the game history API.
 *
 * Provides hooks for listing past games, viewing details, and updating
 * visibility/privacy settings.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../../services/api'

export interface GameHistoryItem {
  id: number
  game_id: string
  mode: string
  result: 'win' | 'loss' | 'draw'
  score: number | null
  opponent_names: string[]
  finished_at: string | null
  duration_seconds: number | null
  tournament_id: number | null
}

export interface GameHistoryPage {
  items: GameHistoryItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface GameHistoryDetail {
  id: number
  room_id: string
  game_id: string
  mode: string
  started_at: string | null
  finished_at: string | null
  result_data: Record<string, unknown> | null
  tournament_id: number | null
  players: {
    user_id: number
    display_name: string
    placement: number | null
    score: number | null
    is_winner: boolean
    stats: Record<string, unknown> | null
  }[]
}

export type VisibilityOption = 'all_friends' | 'opponents_only' | 'private'

export interface VisibilityUpdate {
  default_visibility: VisibilityOption
  game_overrides?: Record<string, VisibilityOption> | null
}

// ----- Game History List (paginated, optional game filter) -----

export function useGameHistory(gameId?: string, page = 1, pageSize = 20) {
  return useQuery<GameHistoryPage>({
    queryKey: ['game-history', gameId, page, pageSize],
    queryFn: async () => {
      const offset = (page - 1) * pageSize
      const params: Record<string, string | number> = { limit: pageSize, offset }
      if (gameId) params.game_id = gameId
      const { data } = await api.get('/game-history', { params })
      return data
    },
    staleTime: 30_000,
  })
}

// ----- Single Game History Detail -----

export function useGameHistoryDetail(id: number | null) {
  return useQuery<GameHistoryDetail>({
    queryKey: ['game-history-detail', id],
    queryFn: async () => {
      const { data } = await api.get(`/game-history/${id}`)
      return data
    },
    enabled: id !== null,
    staleTime: 60_000,
  })
}

// ----- Update Visibility / Privacy -----

export function useUpdateVisibility() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (update: VisibilityUpdate) => {
      const { data } = await api.put('/game-history/visibility', update)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['game-history'] })
      qc.invalidateQueries({ queryKey: ['game-history-detail'] })
    },
  })
}
