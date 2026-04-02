/**
 * Tests for usePositionsData hook
 *
 * Verifies:
 * - Returns correct shape when queries resolve
 * - refetchIntervalInBackground: false is set on interval-driven queries
 *   so they stop polling when the browser tab is hidden
 */

import { describe, test, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { positionsApi } from '../../../services/api'
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
  authFetch: vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ total_btc_value: 0, total_usd_value: 0 }),
  }),
  api: {
    get: vi.fn().mockResolvedValue({ data: { prices: {} } }),
  },
}))

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
    vi.mocked(positionsApi.getAll).mockResolvedValue([])
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

  test('interval-driven queries have refetchIntervalInBackground: false', () => {
    // Verify that the positions and bots queries are configured to stop polling
    // when the browser tab is hidden — preventing unnecessary network traffic
    // every 5s when the user is on a different page.
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    renderHook(() => usePositionsData({}), { wrapper: makeWrapper(qc) })

    const queries = qc.getQueryCache().getAll()

    // Find all high-frequency queries (≤30s interval) registered on their observers.
    // These are the ones most impactful when running in background (5s positions, 10s bots).
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
