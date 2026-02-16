import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { authFetch, api } from '../../../services/api'
import type { CandleData } from '../../../utils/indicators'

export function useChartsData(
  selectedPair: string,
  selectedInterval: string,
  chartType: string,
  useHeikinAshi: boolean,
  indicators: any[],
  accountId?: number | null,
) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const lastUpdateRef = useRef<string>('')
  const candleDataRef = useRef<CandleData[]>([])

  // Fetch portfolio to get coins we hold (uses shared cache)
  const { data: portfolio } = useQuery({
    queryKey: ['account-portfolio'],
    queryFn: async () => {
      const response = await authFetch('/api/account/portfolio')
      if (!response.ok) throw new Error('Failed to fetch portfolio')
      return response.json()
    },
    refetchInterval: 60000,
    staleTime: 30000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  })

  // Fetch all available products (exchange-aware via account_id)
  const { data: productsData } = useQuery({
    queryKey: ['available-products', accountId],
    queryFn: async () => {
      const url = accountId ? `/api/products?account_id=${accountId}` : '/api/products'
      const response = await authFetch(url)
      if (!response.ok) throw new Error('Failed to fetch products')
      return response.json()
    },
    staleTime: 3600000, // Cache for 1 hour (product list rarely changes)
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  })

  // Generate trading pairs from all available products
  const TRADING_PAIRS = (() => {
    if (!productsData?.products) {
      // Fallback to default pairs while loading
      return [
        { value: 'BTC-USD', label: 'BTC/USD', group: 'USD Pairs', inPortfolio: false },
        { value: 'ETH-USD', label: 'ETH/USD', group: 'USD Pairs', inPortfolio: false },
        { value: 'SOL-USD', label: 'SOL/USD', group: 'USD Pairs', inPortfolio: false },
      ]
    }

    // Get list of assets in portfolio
    const portfolioAssets = new Set(
      portfolio?.holdings?.map((h: any) => h.asset) || []
    )

    // Convert products to trading pairs with portfolio indicator
    const pairs = productsData.products.map((product: any) => {
      const base = product.base_currency
      const quote = product.quote_currency
      const inPortfolio = portfolioAssets.has(base)

      return {
        value: product.product_id,
        label: `${base}/${quote}`,
        group: quote === 'USD' ? 'USD Pairs' : 'BTC Pairs',
        inPortfolio: inPortfolio
      }
    })

    return pairs
  })()

  // Fetch and update chart data
  useEffect(() => {
    const fetchCandles = async () => {
      const isInitialLoad = lastUpdateRef.current === ''
      setLoading(isInitialLoad)
      setError(null)

      try {
        const response = await api.get<{ candles: CandleData[] }>(
          '/candles',
          {
            params: {
              product_id: selectedPair,
              granularity: selectedInterval,
              limit: 300,
            },
          }
        )

        const { candles, product_id: returnedProductId } = response.data as { candles: CandleData[], product_id?: string }

        if (!candles || candles.length === 0) {
          setError('No data available for this pair')
          return
        }

        // Warn if we got data for a different pair than requested
        if (returnedProductId && returnedProductId !== selectedPair) {
          console.warn(`WARNING: Requested ${selectedPair} but got data for ${returnedProductId}`)
          setError(`No data available for ${selectedPair}. Showing ${returnedProductId} instead.`)
        }

        candleDataRef.current = candles
        // Note: lastUpdateRef is managed by Charts.tsx to track what's been rendered
      } catch (err: any) {
        console.error('Error fetching candles:', err)
        setError(err.response?.data?.detail || 'Failed to load chart data')
      } finally {
        setLoading(false)
      }
    }

    fetchCandles()
    const interval = setInterval(fetchCandles, 30000)

    return () => clearInterval(interval)
  }, [selectedPair, selectedInterval, chartType, indicators, useHeikinAshi])

  return {
    portfolio,
    productsData,
    TRADING_PAIRS,
    loading,
    error,
    candleDataRef,
    lastUpdateRef,
  }
}
