import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAccountPortfolio } from '../../../hooks/useAccountPortfolio'
import { authFetch, api } from '../../../services/api'
import { getApiErrorMessage, isCanceledRequest } from '../../../utils/apiError'
import type { CandleData } from '../../../utils/indicators'

export function useChartsData(
  selectedPair: string,
  selectedInterval: string,
  accountId?: number | null,
) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dataVersion, setDataVersion] = useState(0)
  const lastUpdateRef = useRef<string>('')
  const candleDataRef = useRef<CandleData[]>([])

  // Portfolio (held coins) — shared, account-scoped cache entry with the
  // other pages (one 60s poll app-wide instead of one per page)
  const { data: portfolio } = useAccountPortfolio<{
    holdings?: { asset: string }[]
  }>(accountId)

  // Fetch all available products (exchange-aware via account_id)
  const { data: productsData } = useQuery({
    queryKey: ['available-products', accountId],
    queryFn: async () => {
      const url = accountId ? `/api/products?account_id=${accountId}` : '/api/products'
      const response = await authFetch(url)
      if (!response.ok) throw new Error('Failed to fetch products')
      return response.json()
    },
    enabled: accountId !== null,
    staleTime: 3600000, // Cache for 1 hour (product list rarely changes)
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  })

  // Generate trading pairs from all available products
  const TRADING_PAIRS = useMemo(() => {
    if (!productsData?.products) {
      // Fallback to default pairs while loading
      return [
        { value: 'BTC-USD', label: 'BTC/USD', group: 'USD', inPortfolio: false },
        { value: 'ETH-USD', label: 'ETH/USD', group: 'USD', inPortfolio: false },
        { value: 'SOL-USD', label: 'SOL/USD', group: 'USD', inPortfolio: false },
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
        group: quote,
        inPortfolio: inPortfolio
      }
    })

    return pairs
  }, [productsData, portfolio])

  // Fetch and update chart data
  useEffect(() => {
    // Reset tracking state so the data update effect re-applies on new data
    lastUpdateRef.current = ''
    candleDataRef.current = []
    setLoading(true)

    // Guard against a stale in-flight response (from the previous pair/interval)
    // resolving after we've switched — without this it could overwrite the new
    // pair's candles. `cancelled` blocks late state writes; abort() cancels the
    // network request itself.
    let cancelled = false
    const controller = new AbortController()

    const fetchCandles = async () => {
      if (cancelled) return
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
            signal: controller.signal,
          }
        )
        if (cancelled) return

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
        setDataVersion(v => v + 1)
      } catch (err) {
        // Ignore aborts (pair/interval switched) — not a real error.
        if (cancelled || isCanceledRequest(err)) return
        console.error('Error fetching candles:', err)
        setError(getApiErrorMessage(err, 'Failed to load chart data'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchCandles()
    const interval = setInterval(fetchCandles, 30000)

    return () => {
      cancelled = true
      controller.abort()
      clearInterval(interval)
    }
  }, [selectedPair, selectedInterval])

  return {
    portfolio,
    productsData,
    TRADING_PAIRS,
    loading,
    error,
    dataVersion,
    candleDataRef,
    lastUpdateRef,
  }
}
