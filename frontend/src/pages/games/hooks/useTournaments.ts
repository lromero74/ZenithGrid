/**
 * React Query hooks for the tournaments API.
 *
 * Provides hooks for listing, creating, joining, leaving, starting,
 * archiving, and vote-deleting tournaments.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../../services/api'

export type TournamentStatus = 'pending' | 'active' | 'finished' | 'archived'

export interface TournamentPlayer {
  user_id: number
  display_name: string
  total_score: number
  placement: number | null
  joined_at: string | null
}

export interface Tournament {
  id: number
  name: string
  status: TournamentStatus
  game_ids: string[]
  creator_id: number
  creator_name: string
  player_count: number
  created_at: string | null
  started_at: string | null
}

export interface TournamentDetail extends Tournament {
  finished_at: string | null
  config: Record<string, unknown> | null
  players: TournamentPlayer[]
}

export interface TournamentStanding {
  rank: number
  user_id: number
  display_name: string
  total_score: number
  placement: number | null
}

export interface TournamentCreate {
  name: string
  game_ids: string[]
  config?: Record<string, unknown> | null
}

// ----- List Tournaments -----

export function useTournaments() {
  return useQuery<Tournament[]>({
    queryKey: ['tournaments'],
    queryFn: async () => {
      const { data } = await api.get('/tournaments')
      return data
    },
    staleTime: 30_000,
  })
}

// ----- Tournament Detail -----

export function useTournamentDetail(id: number | null) {
  return useQuery<TournamentDetail>({
    queryKey: ['tournament-detail', id],
    queryFn: async () => {
      const { data } = await api.get(`/tournaments/${id}`)
      return data
    },
    enabled: id !== null,
    staleTime: 15_000,
  })
}

// ----- Tournament Standings -----

export function useTournamentStandings(id: number | null) {
  return useQuery<TournamentStanding[]>({
    queryKey: ['tournament-standings', id],
    queryFn: async () => {
      const { data } = await api.get(`/tournaments/${id}/standings`)
      return data
    },
    enabled: id !== null,
    staleTime: 15_000,
  })
}

// ----- Create Tournament -----

export function useCreateTournament() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: TournamentCreate) => {
      const { data } = await api.post('/tournaments', payload)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tournaments'] })
    },
  })
}

// ----- Join Tournament -----

export function useJoinTournament() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (tournamentId: number) => {
      const { data } = await api.post(`/tournaments/${tournamentId}/join`)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tournaments'] })
      qc.invalidateQueries({ queryKey: ['tournament-detail'] })
    },
  })
}

// ----- Leave Tournament -----

export function useLeaveTournament() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (tournamentId: number) => {
      const { data } = await api.post(`/tournaments/${tournamentId}/leave`)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tournaments'] })
      qc.invalidateQueries({ queryKey: ['tournament-detail'] })
    },
  })
}

// ----- Start Tournament -----

export function useStartTournament() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (tournamentId: number) => {
      const { data } = await api.post(`/tournaments/${tournamentId}/start`)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tournaments'] })
      qc.invalidateQueries({ queryKey: ['tournament-detail'] })
    },
  })
}

// ----- Archive Tournament -----

export function useArchiveTournament() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (tournamentId: number) => {
      const { data } = await api.post(`/tournaments/${tournamentId}/archive`)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tournaments'] })
      qc.invalidateQueries({ queryKey: ['tournament-detail'] })
    },
  })
}

// ----- Vote Delete Tournament -----

export function useVoteDeleteTournament() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (tournamentId: number) => {
      const { data } = await api.post(`/tournaments/${tournamentId}/vote-delete`)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tournaments'] })
      qc.invalidateQueries({ queryKey: ['tournament-detail'] })
    },
  })
}
