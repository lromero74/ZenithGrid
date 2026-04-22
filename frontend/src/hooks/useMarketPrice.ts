import { useQuery } from '@tanstack/react-query'

import { marketDataApi } from '../services/api'

const DEFAULT_REFETCH_INTERVAL_MS = 60_000
const DEFAULT_STALE_TIME_MS = 30_000

interface UseMarketPriceArgs {
  productId: string
  refetchInterval?: number
  staleTime?: number
}

export function useMarketPrice({
  productId,
  refetchInterval = DEFAULT_REFETCH_INTERVAL_MS,
  staleTime = DEFAULT_STALE_TIME_MS,
}: UseMarketPriceArgs) {
  const query = useQuery({
    queryKey: ['market-price', productId],
    queryFn: () => marketDataApi.getPrice(productId),
    refetchInterval,
    staleTime,
    refetchOnWindowFocus: false,
  })

  return {
    price: query.data?.price || 0,
    data: query.data,
    isLoading: query.isLoading,
  }
}
