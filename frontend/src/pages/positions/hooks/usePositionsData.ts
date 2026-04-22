import { useQuery } from '@tanstack/react-query'
import { positionsApi, botsApi, api } from '../../../services/api'
import { useState, useEffect, useMemo } from 'react'
import { calculateUnrealizedPnL } from '../helpers'
import { useMarketPrice } from '../../../hooks/useMarketPrice'

interface UsePositionsDataProps {
  selectedAccountId?: number
}

export const usePositionsData = ({ selectedAccountId }: UsePositionsDataProps) => {
  const [currentPrices, setCurrentPrices] = useState<Record<string, number>>({})
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
    refetchInterval: 5000, // Update every 5 seconds for active deals
    refetchIntervalInBackground: false, // Stop polling when tab is hidden
    refetchOnMount: 'always', // Always fetch fresh data on mount (don't show stale cache)
    staleTime: 0, // Treat cached data as immediately stale
  })

  // Fetch all bots to display bot names (filtered by account)
  const { data: bots } = useQuery({
    queryKey: ['bots', selectedAccountId],
    queryFn: () => botsApi.getAll(undefined, selectedAccountId),
    refetchInterval: 10000,
    refetchIntervalInBackground: false, // Stop polling when tab is hidden
    refetchOnMount: 'always', // Always fetch fresh data on mount
    staleTime: 0, // Treat cached data as immediately stale
  })

  const { price: btcUsdPrice } = useMarketPrice({
    productId: 'BTC-USD',
    refetchInterval: 120000,
    staleTime: 60000,
  })

  // Fetch real-time prices for all open positions
  useEffect(() => {
    if (!isDocumentVisible) return

    const abortController = new AbortController()

    const fetchPrices = async () => {
      if (!allPositions) return

      const openPositions = allPositions.filter(p => p.status === 'open')
      if (openPositions.length === 0) return

      try {
        // Fetch all prices in a single batch request
        const productIds = [...new Set(openPositions.map(p => p.product_id || 'ETH-BTC'))].join(',')
        const response = await api.get('/prices/batch', {
          params: { products: productIds },
          signal: abortController.signal
        })

        const priceMap = response.data.prices || {}

        // Fill in fallback prices for positions that didn't get a price
        openPositions.forEach(position => {
          const productId = position.product_id || 'ETH-BTC'
          if (!priceMap[productId]) {
            priceMap[productId] = position.average_buy_price
          }
        })

        setCurrentPrices(priceMap)
      } catch (err) {
        // Ignore abort errors (they're expected when component unmounts)
        if ((err as any)?.code === 'ERR_CANCELED' || (err as any)?.code === 'ECONNABORTED') {
          return
        }
        console.error('Error fetching batch prices:', err)

        // Fallback to using average buy prices
        const fallbackPrices: Record<string, number> = {}
        openPositions.forEach(position => {
          const productId = position.product_id || 'ETH-BTC'
          fallbackPrices[productId] = position.average_buy_price
        })
        setCurrentPrices(fallbackPrices)
      }
    }

    fetchPrices()
    const interval = setInterval(fetchPrices, 5000) // Update every 5 seconds

    return () => {
      clearInterval(interval)
      abortController.abort() // Cancel any in-flight requests
    }
  }, [allPositions, isDocumentVisible])

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
