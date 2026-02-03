/**
 * Custom hook to get the current market season for styling purposes.
 * Used by components that want to adapt their UI based on market cycle.
 */

import { useQuery } from '@tanstack/react-query'
import type {
  FearGreedResponse,
  ATHResponse,
  AltseasonIndexResponse,
  BTCDominanceResponse,
} from '../types'
import { determineMarketSeason, type SeasonInfo, type MarketSeason } from '../components/MarketSentimentCards'

export function useMarketSeason(): {
  seasonInfo: SeasonInfo | null
  isLoading: boolean
  headerGradient: string
} {
  // Fetch the metrics needed to determine season
  const { data: fearGreedData, isLoading: fgLoading } = useQuery<FearGreedResponse>({
    queryKey: ['fear-greed'],
    queryFn: async () => {
      const response = await fetch('/api/news/fear-greed')
      if (!response.ok) throw new Error('Failed to fetch')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  const { data: athData, isLoading: athLoading } = useQuery<ATHResponse>({
    queryKey: ['ath'],
    queryFn: async () => {
      const response = await fetch('/api/news/ath')
      if (!response.ok) throw new Error('Failed to fetch')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  const { data: altseasonData, isLoading: altLoading } = useQuery<AltseasonIndexResponse>({
    queryKey: ['altseason-index'],
    queryFn: async () => {
      const response = await fetch('/api/news/altseason-index')
      if (!response.ok) throw new Error('Failed to fetch')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  const { data: btcDominanceData, isLoading: domLoading } = useQuery<BTCDominanceResponse>({
    queryKey: ['btc-dominance'],
    queryFn: async () => {
      const response = await fetch('/api/news/btc-dominance')
      if (!response.ok) throw new Error('Failed to fetch')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  const isLoading = fgLoading || athLoading || altLoading || domLoading
  const hasData = fearGreedData || athData || altseasonData || btcDominanceData

  const seasonInfo = hasData
    ? determineMarketSeason(
        fearGreedData?.data?.value,
        athData,
        altseasonData,
        btcDominanceData
      )
    : null

  // Generate a subtle header gradient based on season
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
