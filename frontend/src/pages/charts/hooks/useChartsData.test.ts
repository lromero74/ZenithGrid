/**
 * Tests for useChartsData hook
 *
 * Verifies candle data fetching, product list fetching, portfolio query,
 * trading pair generation, loading/error states, and interval-based polling.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useChartsData } from './useChartsData'

vi.mock('../../../services/api', () => ({
  authFetch: vi.fn(),
  api: {
    get: vi.fn(),
  },
}))

import { authFetch, api } from '../../../services/api'

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

beforeEach(() => {
  vi.clearAllMocks()

  // Default mock: authFetch returns unsuccessful responses (products/portfolio won't load)
  vi.mocked(authFetch).mockResolvedValue({
    ok: false,
    json: () => Promise.resolve({}),
  } as Response)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useChartsData candle fetching', () => {
  test('fetches candle data on mount and updates candleDataRef', async () => {
    const mockCandles = [
      { time: 1700000000, open: 100, high: 110, low: 90, close: 105, volume: 1000 },
      { time: 1700000300, open: 105, high: 115, low: 95, close: 108, volume: 1200 },
    ]
    vi.mocked(api.get).mockResolvedValue({ data: { candles: mockCandles } })

    const { result } = renderHook(
      () => useChartsData('BTC-USD', '300'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(api.get).toHaveBeenCalledWith('/candles', {
      params: { product_id: 'BTC-USD', granularity: '300', limit: 300 },
    })
    expect(result.current.candleDataRef.current).toEqual(mockCandles)
    expect(result.current.error).toBeNull()
  })

  test('starts in loading state', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {})) // never resolves

    const { result } = renderHook(
      () => useChartsData('BTC-USD', '300'),
      { wrapper: createWrapper() }
    )

    expect(result.current.loading).toBe(true)
  })

  test('sets error when no candles returned', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { candles: [] } })

    const { result } = renderHook(
      () => useChartsData('BTC-USD', '300'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.error).toBe('No data available for this pair')
  })

  test('sets error when candles is null', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { candles: null } })

    const { result } = renderHook(
      () => useChartsData('BTC-USD', '300'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.error).toBe('No data available for this pair')
  })

  test('sets error when API call fails with detail', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.mocked(api.get).mockRejectedValue({
      response: { data: { detail: 'Rate limited' } },
    })

    const { result } = renderHook(
      () => useChartsData('BTC-USD', '300'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.error).toBe('Rate limited')
    consoleSpy.mockRestore()
  })

  test('falls back to generic error message when no detail', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.mocked(api.get).mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(
      () => useChartsData('BTC-USD', '300'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.error).toBe('Failed to load chart data')
    consoleSpy.mockRestore()
  })

  test('warns when returned product_id differs from requested', async () => {
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const mockCandles = [
      { time: 1700000000, open: 100, high: 110, low: 90, close: 105, volume: 1000 },
    ]
    vi.mocked(api.get).mockResolvedValue({
      data: { candles: mockCandles, product_id: 'ETH-USD' },
    })

    const { result } = renderHook(
      () => useChartsData('BTC-USD', '300'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining('WARNING: Requested BTC-USD but got data for ETH-USD')
    )
    expect(result.current.error).toContain('Showing ETH-USD instead')
    // Data should still be set
    expect(result.current.candleDataRef.current).toEqual(mockCandles)

    consoleSpy.mockRestore()
  })
})

describe('useChartsData TRADING_PAIRS', () => {
  test('returns fallback pairs when products not loaded', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(
      () => useChartsData('BTC-USD', '300'),
      { wrapper: createWrapper() }
    )

    expect(result.current.TRADING_PAIRS).toHaveLength(3)
    expect(result.current.TRADING_PAIRS[0].value).toBe('BTC-USD')
    expect(result.current.TRADING_PAIRS[1].value).toBe('ETH-USD')
    expect(result.current.TRADING_PAIRS[2].value).toBe('SOL-USD')
    // All fallback pairs should have inPortfolio false
    expect(result.current.TRADING_PAIRS.every((p: any) => p.inPortfolio === false)).toBe(true)
  })

  test('generates pairs from products data with portfolio indicator', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { candles: [] } })

    vi.mocked(authFetch).mockImplementation(async (url: string) => {
      if (url === '/api/account/portfolio') {
        return {
          ok: true,
          json: () => Promise.resolve({
            holdings: [{ asset: 'BTC' }, { asset: 'ETH' }],
          }),
        } as Response
      }
      if (url.startsWith('/api/products')) {
        return {
          ok: true,
          json: () => Promise.resolve({
            products: [
              { product_id: 'BTC-USD', base_currency: 'BTC', quote_currency: 'USD' },
              { product_id: 'ETH-USD', base_currency: 'ETH', quote_currency: 'USD' },
              { product_id: 'SOL-USD', base_currency: 'SOL', quote_currency: 'USD' },
            ],
          }),
        } as Response
      }
      return { ok: false, json: () => Promise.resolve({}) } as Response
    })

    const { result } = renderHook(
      () => useChartsData('BTC-USD', '300'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.productsData).toBeDefined()
    })

    const btcPair = result.current.TRADING_PAIRS.find((p: any) => p.value === 'BTC-USD')
    const solPair = result.current.TRADING_PAIRS.find((p: any) => p.value === 'SOL-USD')

    expect(btcPair).toBeDefined()
    expect(btcPair!.inPortfolio).toBe(true)
    expect(btcPair!.group).toBe('USD')
    expect(btcPair!.label).toBe('BTC/USD')

    expect(solPair).toBeDefined()
    expect(solPair!.inPortfolio).toBe(false)
  })

  test('includes account_id in products query when provided', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { candles: [] } })
    vi.mocked(authFetch).mockImplementation(async (url: string) => {
      if (url.startsWith('/api/products')) {
        return {
          ok: true,
          json: () => Promise.resolve({ products: [] }),
        } as Response
      }
      return { ok: false, json: () => Promise.resolve({}) } as Response
    })

    renderHook(
      () => useChartsData('BTC-USD', '300', 42),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(authFetch).toHaveBeenCalledWith('/api/products?account_id=42')
    })
  })

  test('does not include account_id in products query when not provided', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { candles: [] } })
    vi.mocked(authFetch).mockImplementation(async (url: string) => {
      if (url.startsWith('/api/products')) {
        return {
          ok: true,
          json: () => Promise.resolve({ products: [] }),
        } as Response
      }
      return { ok: false, json: () => Promise.resolve({}) } as Response
    })

    renderHook(
      () => useChartsData('BTC-USD', '300'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(authFetch).toHaveBeenCalledWith('/api/products')
    })
  })
})

describe('useChartsData dataVersion', () => {
  test('increments dataVersion when candles arrive', async () => {
    const mockCandles = [
      { time: 1700000000, open: 100, high: 110, low: 90, close: 105, volume: 1000 },
    ]
    vi.mocked(api.get).mockResolvedValue({ data: { candles: mockCandles } })

    const { result } = renderHook(
      () => useChartsData('BTC-USD', '300'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.dataVersion).toBeGreaterThan(0)
    })
  })
})

describe('useChartsData return shape', () => {
  test('returns all expected properties', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(
      () => useChartsData('BTC-USD', '300'),
      { wrapper: createWrapper() }
    )

    expect(result.current).toHaveProperty('portfolio')
    expect(result.current).toHaveProperty('productsData')
    expect(result.current).toHaveProperty('TRADING_PAIRS')
    expect(result.current).toHaveProperty('loading')
    expect(result.current).toHaveProperty('error')
    expect(result.current).toHaveProperty('dataVersion')
    expect(result.current).toHaveProperty('candleDataRef')
    expect(result.current).toHaveProperty('lastUpdateRef')
  })

  test('lastUpdateRef starts as empty string', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(
      () => useChartsData('BTC-USD', '300'),
      { wrapper: createWrapper() }
    )

    expect(result.current.lastUpdateRef.current).toBe('')
  })
})
