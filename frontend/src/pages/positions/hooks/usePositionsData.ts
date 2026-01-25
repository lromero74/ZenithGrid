import { useQuery } from '@tanstack/react-query'
import { positionsApi, botsApi } from '../../../services/api'
import { useState, useEffect, useMemo } from 'react'
import type { Position } from '../../../types'
import { API_BASE_URL } from '../../../config/api'
import axios from 'axios'
import { calculateUnrealizedPnL } from '../helpers'

interface UsePositionsDataProps {
  selectedAccountId?: number
}

export const usePositionsData = ({ selectedAccountId }: UsePositionsDataProps) => {
  const [currentPrices, setCurrentPrices] = useState<Record<string, number>>({})

  // Fetch all open positions (filtered by account)
  const { data: allPositions, refetch: refetchPositions } = useQuery({
    queryKey: ['positions', 'open', selectedAccountId],
    queryFn: () => positionsApi.getAll('open', 100),
    refetchInterval: 5000, // Update every 5 seconds for active deals
    refetchOnMount: 'always', // Always fetch fresh data on mount (don't show stale cache)
    staleTime: 0, // Treat cached data as immediately stale
    select: (data) => {
      if (!selectedAccountId) return data
      // Filter by account_id
      return data.filter((p: Position) => p.account_id === selectedAccountId)
    },
  })

  // Fetch all bots to display bot names (filtered by account)
  const { data: bots } = useQuery({
    queryKey: ['bots', selectedAccountId],
    queryFn: () => botsApi.getAll(),
    refetchInterval: 10000,
    refetchOnMount: 'always', // Always fetch fresh data on mount
    staleTime: 0, // Treat cached data as immediately stale
    select: (data) => {
      if (!selectedAccountId) return data
      // Filter by account_id
      return data.filter((bot: any) => bot.account_id === selectedAccountId)
    },
  })

  // Fetch portfolio for BTC/USD price (account-specific)
  const { data: portfolio } = useQuery({
    queryKey: ['account-portfolio', selectedAccountId],
    queryFn: async () => {
      if (selectedAccountId) {
        const response = await fetch(`/api/accounts/${selectedAccountId}/portfolio`)
        if (!response.ok) throw new Error('Failed to fetch portfolio')
        return response.json()
      }
      const response = await fetch('/api/account/portfolio')
      if (!response.ok) throw new Error('Failed to fetch portfolio')
      return response.json()
    },
    refetchInterval: 120000,
    staleTime: 60000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  })

  const totalBtcValue = portfolio?.total_btc_value || 0
  const totalUsdValue = portfolio?.total_usd_value || 0
  const btcUsdPrice = totalBtcValue > 0 ? totalUsdValue / totalBtcValue : 0

  // Fetch real-time prices for all open positions
  useEffect(() => {
    const abortController = new AbortController()

    const fetchPrices = async () => {
      if (!allPositions) return

      const openPositions = allPositions.filter(p => p.status === 'open')
      if (openPositions.length === 0) return

      try {
        // Fetch all prices in a single batch request
        const productIds = openPositions.map(p => p.product_id || 'ETH-BTC').join(',')
        const response = await axios.get(`${API_BASE_URL}/api/prices/batch`, {
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
        if (axios.isCancel(err) || (err as any)?.code === 'ECONNABORTED') {
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
  }, [allPositions])

  // Memoize P&L calculations to avoid recalculating on every render
  // This is a major performance optimization - reduces 5 calculations per position to 1
  const positionsWithPnL = useMemo(() => {
    if (!allPositions) return []

    return allPositions.map(position => {
      const currentPrice = currentPrices[position.product_id || 'ETH-BTC']
      const pnl = calculateUnrealizedPnL(position, currentPrice)

      return {
        ...position,
        _cachedPnL: pnl // Cache the P&L calculation result
      }
    })
  }, [allPositions, currentPrices])

  return {
    allPositions,
    positionsWithPnL,
    bots,
    portfolio,
    btcUsdPrice,
    currentPrices,
    refetchPositions,
  }
}
