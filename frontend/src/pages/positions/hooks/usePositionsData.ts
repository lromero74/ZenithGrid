import { useQuery } from '@tanstack/react-query'
import { positionsApi, botsApi, api } from '../../../services/api'
import { useState, useEffect, useMemo } from 'react'
import { calculateUnrealizedPnL } from '../helpers'
import { useMarketPrice } from '../../../hooks/useMarketPrice'

interface UsePositionsDataProps {
  selectedAccountId?: number
}

const ACTIVE_POSITIONS_REFETCH_INTERVAL_MS = 5000
const IDLE_POSITIONS_REFETCH_INTERVAL_MS = 30000
const BOTS_STALE_TIME_MS = 300000

export const usePositionsData = ({ selectedAccountId }: UsePositionsDataProps) => {
  const [isDocumentVisible, setIsDocumentVisible] = useState(() => document.visibilityState !== 'hidden')

  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsDocumentVisible(document.visibilityState !== 'hidden')
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [])

  // Fetch open positions for the selected account.
  // Passing account_id to the backend avoids fetching all accounts' positions
  // and hitting the limit — especially important when the user has many open
  // positions across multiple accounts.
  const { data: allPositions, refetch: refetchPositions } = useQuery({
    queryKey: ['positions', 'open', selectedAccountId],
    queryFn: () => positionsApi.getAll('open', 1000, selectedAccountId),
    refetchInterval: (query) => ((query.state.data?.length || 0) > 0
      ? ACTIVE_POSITIONS_REFETCH_INTERVAL_MS
      : IDLE_POSITIONS_REFETCH_INTERVAL_MS),
    refetchIntervalInBackground: false, // Stop polling when tab is hidden
    refetchOnMount: 'always', // Always fetch fresh data on mount (don't show stale cache)
    staleTime: 0, // Treat cached data as immediately stale
  })

  // Fetch all bots to display bot names (filtered by account)
  const { data: bots } = useQuery({
    queryKey: ['bots', selectedAccountId],
    queryFn: () => botsApi.getAll(undefined, selectedAccountId),
    staleTime: BOTS_STALE_TIME_MS,
    refetchOnWindowFocus: false,
  })

  const { price: btcUsdPrice } = useMarketPrice({
    productId: 'BTC-USD',
    refetchInterval: 120000,
    staleTime: 60000,
  })

  const openPositions = useMemo(
    () => (allPositions || []).filter((position) => position.status === 'open'),
    [allPositions]
  )

  const batchPriceProducts = useMemo(
    () => [...new Set(openPositions.map((position) => position.product_id || 'ETH-BTC'))],
    [openPositions]
  )

  const { data: batchPrices = {} } = useQuery({
    queryKey: ['position-batch-prices', selectedAccountId, batchPriceProducts],
    enabled: isDocumentVisible && batchPriceProducts.length > 0,
    queryFn: async ({ signal }) => {
      try {
        const response = await api.get('/prices/batch', {
          params: { products: batchPriceProducts.join(',') },
          signal,
        })
        return response.data?.prices || {}
      } catch (err) {
        if ((err as any)?.code === 'ERR_CANCELED' || (err as any)?.code === 'ECONNABORTED') {
          return {}
        }
        console.error('Error fetching batch prices:', err)
        return {}
      }
    },
    refetchInterval: ACTIVE_POSITIONS_REFETCH_INTERVAL_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
    staleTime: 0,
  })

  const currentPrices = useMemo(() => {
    if (openPositions.length === 0) return {}

    const priceMap = { ...batchPrices }
    openPositions.forEach((position) => {
      const productId = position.product_id || 'ETH-BTC'
      if (!priceMap[productId]) {
        priceMap[productId] = position.average_buy_price
      }
    })
    return priceMap
  }, [batchPrices, openPositions])

  // Memoize P&L calculations to avoid recalculating on every render
  // This is a major performance optimization - reduces 5 calculations per position to 1
  const positionsWithPnL = useMemo(() => {
    if (!allPositions) return []

    return allPositions.map(position => {
      const currentPrice = currentPrices[position.product_id || 'ETH-BTC']
      const pnl = calculateUnrealizedPnL(position, currentPrice, btcUsdPrice)

      return {
        ...position,
        _cachedPnL: pnl // Cache the P&L calculation result
      }
    })
  }, [allPositions, currentPrices, btcUsdPrice])

  return {
    allPositions,
    positionsWithPnL,
    bots,
    btcUsdPrice,
    currentPrices,
    refetchPositions,
  }
}
