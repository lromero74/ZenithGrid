/**
 * Custom hook to get the current market season for styling purposes.
 * Used by components that want to adapt their UI based on market cycle.
 *
 * S4: Updated to import from utils/seasonDetection instead of component file.
 * S14: Removed unused altseason query (parameter removed from determineMarketSeason).
 */

import { useQuery } from '@tanstack/react-query'
import { authFetch } from '../services/api'
import type {
  FearGreedResponse,
  ATHResponse,
  BTCDominanceResponse,
} from '../types'
import { determineMarketSeason, type SeasonInfo, type MarketSeason } from '../utils/seasonDetection'

export function useMarketSeason(): {
  seasonInfo: SeasonInfo | null
  isLoading: boolean
  headerGradient: string
} {
  const { data: fearGreedData, isLoading: fgLoading } = useQuery<FearGreedResponse>({
    queryKey: ['fear-greed'],
    queryFn: async () => {
      const response = await authFetch('/api/news/fear-greed')
      if (!response.ok) throw new Error('Failed to fetch')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  const { data: athData, isLoading: athLoading } = useQuery<ATHResponse>({
    queryKey: ['ath'],
    queryFn: async () => {
      const response = await authFetch('/api/news/ath')
      if (!response.ok) throw new Error('Failed to fetch')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  const { data: btcDominanceData, isLoading: domLoading } = useQuery<BTCDominanceResponse>({
    queryKey: ['btc-dominance'],
    queryFn: async () => {
      const response = await authFetch('/api/news/btc-dominance')
      if (!response.ok) throw new Error('Failed to fetch')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  const isLoading = fgLoading || athLoading || domLoading
  const hasData = fearGreedData || athData || btcDominanceData

  const seasonInfo = hasData
    ? determineMarketSeason(
        fearGreedData?.data?.value,
        athData,
        btcDominanceData
      )
    : null

  const headerGradients: Record<MarketSeason, string> = {
    accumulation: 'from-pink-950/20 via-slate-900 to-slate-900',
    bull: 'from-green-950/20 via-slate-900 to-slate-900',
    distribution: 'from-orange-950/20 via-slate-900 to-slate-900',
    bear: 'from-blue-950/20 via-slate-900 to-slate-900',
  }

  const headerGradient = seasonInfo
    ? headerGradients[seasonInfo.season]
    : 'from-slate-900 via-slate-900 to-slate-900'

  return {
    seasonInfo,
    isLoading,
    headerGradient,
  }
}
