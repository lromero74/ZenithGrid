/**
 * Tests for usePositionsData hook
 *
 * Verifies:
 * - Returns correct shape when queries resolve
 * - refetchIntervalInBackground: false is set on interval-driven queries
 *   so they stop polling when the browser tab is hidden
 */

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { positionsApi, botsApi } from '../../../services/api'
import { usePositionsData } from './usePositionsData'

// ---------------------------------------------------------------------------
// Mock API modules
// ---------------------------------------------------------------------------

vi.mock('../../../services/api', () => ({
  positionsApi: {
    getAll: vi.fn().mockResolvedValue([]),
  },
  botsApi: {
    getAll: vi.fn().mockResolvedValue([]),
  },
  marketDataApi: {
    getPrice: vi.fn().mockResolvedValue({ price: 0 }),
  },
  api: {
    get: vi.fn().mockResolvedValue({ data: { prices: {} } }),
  },
}))

import { api, marketDataApi } from '../../../services/api'

// ---------------------------------------------------------------------------
// Wrapper with fresh QueryClient per test
// ---------------------------------------------------------------------------

function makeWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('usePositionsData', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
    vi.mocked(positionsApi.getAll).mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  test('returns expected shape on mount', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const { result } = renderHook(
      () => usePositionsData({}),
      { wrapper: makeWrapper(qc) }
    )

    expect(result.current).toHaveProperty('positionsWithPnL')
    expect(result.current).toHaveProperty('bots')
    expect(result.current).toHaveProperty('btcUsdPrice')
    expect(result.current).toHaveProperty('currentPrices')
    expect(result.current).toHaveProperty('refetchPositions')
    expect(Array.isArray(result.current.positionsWithPnL)).toBe(true)
  })

  test('positionsWithPnL is empty when no positions returned', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const { result } = renderHook(
      () => usePositionsData({}),
      { wrapper: makeWrapper(qc) }
    )

    await waitFor(() => {
      expect(result.current.positionsWithPnL).toEqual([])
    })
  })

  test('positionsWithPnL attaches _cachedPnL to each position', async () => {
    vi.mocked(positionsApi.getAll).mockResolvedValue([
      {
        id: 1, status: 'open', bot_id: 1, product_id: 'ETH-USD',
        opened_at: '2025-01-01T00:00:00Z', closed_at: null,
        initial_quote_balance: 100, max_quote_allowed: 200,
        total_quote_spent: 50, total_base_acquired: 0.5,
        average_buy_price: 2000, sell_price: null,
        total_quote_received: null, profit_quote: null,
        profit_percentage: null, trade_count: 1,
      },
    ] as any)

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const { result } = renderHook(
      () => usePositionsData({}),
      { wrapper: makeWrapper(qc) }
    )

    await waitFor(() => {
      expect(result.current.positionsWithPnL).toHaveLength(1)
    })

    expect(result.current.positionsWithPnL[0]).toHaveProperty('_cachedPnL')
    expect(result.current.positionsWithPnL[0].id).toBe(1)
  })

  test('btcUsdPrice is 0 when portfolio has no BTC value', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const { result } = renderHook(
      () => usePositionsData({}),
      { wrapper: makeWrapper(qc) }
    )

    expect(result.current.btcUsdPrice).toBe(0)
  })

  test('fetches direct BTC/USD market price instead of account portfolio', async () => {
    vi.mocked(marketDataApi.getPrice).mockResolvedValue({ price: 98765.43 } as any)

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const { result } = renderHook(
      () => usePositionsData({ selectedAccountId: 42 }),
      { wrapper: makeWrapper(qc) }
    )

    await waitFor(() => {
      expect(result.current.btcUsdPrice).toBe(98765.43)
    })

    expect(marketDataApi.getPrice).toHaveBeenCalledWith('BTC-USD')
  })

  test('requests bots scoped to the selected account when available', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })

    renderHook(
      () => usePositionsData({ selectedAccountId: 42 }),
      { wrapper: makeWrapper(qc) }
    )

    await waitFor(() => {
      expect(botsApi.getAll).toHaveBeenCalledWith(undefined, 42)
    })
  })

  test('backs off open-position polling when there are no active deals', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    renderHook(() => usePositionsData({}), { wrapper: makeWrapper(qc) })

    const positionsQuery = qc.getQueryCache().find({ queryKey: ['positions', 'open', undefined] })
    const observerOptions = positionsQuery?.observers[0]?.options as any

    expect(typeof observerOptions.refetchInterval).toBe('function')
    expect(observerOptions.refetchInterval(positionsQuery)).toBe(30000)
  })

  test('keeps fast open-position polling when active deals exist', async () => {
    vi.mocked(positionsApi.getAll).mockResolvedValue([
      {
        id: 1, status: 'open', bot_id: 1, product_id: 'ETH-USD',
        opened_at: '2025-01-01T00:00:00Z', closed_at: null,
        initial_quote_balance: 100, max_quote_allowed: 200,
        total_quote_spent: 50, total_base_acquired: 0.5,
        average_buy_price: 2000, sell_price: null,
        total_quote_received: null, profit_quote: null,
        profit_percentage: null, trade_count: 1,
      },
    ] as any)

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    renderHook(() => usePositionsData({}), { wrapper: makeWrapper(qc) })

    await waitFor(() => {
      expect(positionsApi.getAll).toHaveBeenCalled()
    })

    const positionsQuery = qc.getQueryCache().find({ queryKey: ['positions', 'open', undefined] })
    const observerOptions = positionsQuery?.observers[0]?.options as any

    expect(observerOptions.refetchInterval(positionsQuery)).toBe(5000)
  })

  test('does not keep bot metadata on a hot polling loop', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    renderHook(() => usePositionsData({}), { wrapper: makeWrapper(qc) })

    const botsQuery = qc.getQueryCache().find({ queryKey: ['bots', undefined] })
    const observerOptions = botsQuery?.observers[0]?.options as any

    expect(observerOptions.refetchInterval).toBeUndefined()
    expect(observerOptions.staleTime).toBe(300000)
    expect(observerOptions.refetchOnWindowFocus).toBe(false)
  })

  test('deduplicates product ids before requesting batch prices', async () => {
    vi.mocked(positionsApi.getAll).mockResolvedValue([
      {
        id: 1, status: 'open', bot_id: 1, product_id: 'ETH-USD',
        opened_at: '2025-01-01T00:00:00Z', closed_at: null,
        initial_quote_balance: 100, max_quote_allowed: 200,
        total_quote_spent: 50, total_base_acquired: 0.5,
        average_buy_price: 2000, sell_price: null,
        total_quote_received: null, profit_quote: null,
        profit_percentage: null, trade_count: 1,
      },
      {
        id: 2, status: 'open', bot_id: 2, product_id: 'ETH-USD',
        opened_at: '2025-01-01T00:00:00Z', closed_at: null,
        initial_quote_balance: 200, max_quote_allowed: 300,
        total_quote_spent: 75, total_base_acquired: 0.75,
        average_buy_price: 2100, sell_price: null,
        total_quote_received: null, profit_quote: null,
        profit_percentage: null, trade_count: 1,
      },
      {
        id: 3, status: 'open', bot_id: 3, product_id: 'BTC-USD',
        opened_at: '2025-01-01T00:00:00Z', closed_at: null,
        initial_quote_balance: 300, max_quote_allowed: 400,
        total_quote_spent: 125, total_base_acquired: 0.001,
        average_buy_price: 60000, sell_price: null,
        total_quote_received: null, profit_quote: null,
        profit_percentage: null, trade_count: 1,
      },
    ] as any)

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    renderHook(
      () => usePositionsData({}),
      { wrapper: makeWrapper(qc) }
    )

    await waitFor(() => {
      expect(vi.mocked(api.get)).toHaveBeenCalled()
    })

    expect(vi.mocked(api.get)).toHaveBeenCalledWith('/prices/batch', {
      params: { products: 'ETH-USD,BTC-USD' },
      signal: expect.any(AbortSignal),
    })
  })

  test('stops batch price polling while the tab is hidden', async () => {
    vi.useFakeTimers()
    const originalVisibilityState = Object.getOwnPropertyDescriptor(document, 'visibilityState')
    const openPositions = [
      {
        id: 1, status: 'open', bot_id: 1, product_id: 'ETH-USD',
        opened_at: '2025-01-01T00:00:00Z', closed_at: null,
        initial_quote_balance: 100, max_quote_allowed: 200,
        total_quote_spent: 50, total_base_acquired: 0.5,
        average_buy_price: 2000, sell_price: null,
        total_quote_received: null, profit_quote: null,
        profit_percentage: null, trade_count: 1,
      },
    ] as any

    let visibilityState: DocumentVisibilityState = 'hidden'
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => visibilityState,
    })

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    qc.setQueryData(['positions', 'open', undefined], openPositions)
    renderHook(
      () => usePositionsData({}),
      { wrapper: makeWrapper(qc) }
    )

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000)
    })
    expect(vi.mocked(api.get)).not.toHaveBeenCalled()
    expect(document.visibilityState).toBe('hidden')

    if (originalVisibilityState) {
      Object.defineProperty(document, 'visibilityState', originalVisibilityState)
    }
  })

  test('interval-driven queries have refetchIntervalInBackground: false', () => {
    // Verify that the positions and bots queries are configured to stop polling
    // when the browser tab is hidden — preventing unnecessary network traffic
    // every 5s when the user is on a different page.
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    renderHook(() => usePositionsData({}), { wrapper: makeWrapper(qc) })

    const queries = qc.getQueryCache().getAll()

    // Find all high-frequency numeric queries (≤30s interval) registered on their observers.
    // These are the ones most impactful when running in background.
    const highFrequencyObserverOptions = queries.flatMap(q =>
      q.observers
        .map((obs: any) => obs.options)
        .filter((opts: any) => typeof opts?.refetchInterval === 'number' && opts.refetchInterval <= 30_000)
    )

    expect(highFrequencyObserverOptions.length).toBeGreaterThan(0)

    highFrequencyObserverOptions.forEach((opts: any) => {
      expect(
        opts.refetchIntervalInBackground,
        `Query with refetchInterval=${opts.refetchInterval}ms should have refetchIntervalInBackground: false`
      ).toBe(false)
    })
  })
})
