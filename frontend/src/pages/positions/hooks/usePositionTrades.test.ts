/**
 * Tests for usePositionTrades hook
 *
 * Verifies paginated trade history fetch via React Query,
 * loading states, enabled/disabled query conditions, and data return.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { usePositionTrades } from './usePositionTrades'

vi.mock('../../../services/api', () => ({
  positionsApi: {
    getTrades: vi.fn(),
  },
}))

import { positionsApi } from '../../../services/api'

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
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('usePositionTrades trades query', () => {
  test('fetches trades when selectedPosition is set', async () => {
    const mockTrades = [
      { id: 1, position_id: 5, side: 'buy', price: 100, base_amount: 0.5, quote_amount: 50, timestamp: '2025-01-01', trade_type: 'buy', order_id: 'o1' },
      { id: 2, position_id: 5, side: 'sell', price: 110, base_amount: 0.5, quote_amount: 55, timestamp: '2025-01-02', trade_type: 'sell', order_id: 'o2' },
    ]
    vi.mocked(positionsApi.getTrades).mockResolvedValue(mockTrades as any)

    const { result } = renderHook(
      () => usePositionTrades({
        selectedPosition: 5,
        tradeHistoryPosition: null,
        showTradeHistoryModal: false,
      }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.trades).toBeDefined()
    })

    expect(positionsApi.getTrades).toHaveBeenCalledWith(5)
    expect(result.current.trades).toEqual(mockTrades)
  })

  test('does not fetch trades when selectedPosition is null', () => {
    const { result } = renderHook(
      () => usePositionTrades({
        selectedPosition: null,
        tradeHistoryPosition: null,
        showTradeHistoryModal: false,
      }),
      { wrapper: createWrapper() }
    )

    expect(positionsApi.getTrades).not.toHaveBeenCalled()
    expect(result.current.trades).toBeUndefined()
  })
})

describe('usePositionTrades tradeHistory query', () => {
  test('fetches trade history when modal is open and position is set', async () => {
    const mockHistory = [
      { id: 10, position_id: 8, side: 'buy', price: 200, base_amount: 1, quote_amount: 200, timestamp: '2025-01-01', trade_type: 'buy', order_id: 'o10' },
    ]
    vi.mocked(positionsApi.getTrades).mockResolvedValue(mockHistory as any)

    const { result } = renderHook(
      () => usePositionTrades({
        selectedPosition: null,
        tradeHistoryPosition: { id: 8, product_id: 'ETH-USD' },
        showTradeHistoryModal: true,
      }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.tradeHistory).toBeDefined()
    })

    expect(positionsApi.getTrades).toHaveBeenCalledWith(8)
    expect(result.current.tradeHistory).toEqual(mockHistory)
  })

  test('does not fetch trade history when modal is closed', () => {
    const { result } = renderHook(
      () => usePositionTrades({
        selectedPosition: null,
        tradeHistoryPosition: { id: 8, product_id: 'ETH-USD' },
        showTradeHistoryModal: false,
      }),
      { wrapper: createWrapper() }
    )

    expect(result.current.tradeHistory).toBeUndefined()
    expect(result.current.isLoadingTradeHistory).toBe(false)
  })

  test('does not fetch trade history when tradeHistoryPosition is null', () => {
    const { result } = renderHook(
      () => usePositionTrades({
        selectedPosition: null,
        tradeHistoryPosition: null,
        showTradeHistoryModal: true,
      }),
      { wrapper: createWrapper() }
    )

    expect(result.current.tradeHistory).toBeUndefined()
  })

  test('isLoadingTradeHistory reflects loading state', async () => {
    let resolveGetTrades: (value: any) => void
    vi.mocked(positionsApi.getTrades).mockImplementation(
      () => new Promise(resolve => { resolveGetTrades = resolve })
    )

    const { result } = renderHook(
      () => usePositionTrades({
        selectedPosition: null,
        tradeHistoryPosition: { id: 3, product_id: 'SOL-USD' },
        showTradeHistoryModal: true,
      }),
      { wrapper: createWrapper() }
    )

    // Should be loading while the promise is unresolved
    await waitFor(() => {
      expect(result.current.isLoadingTradeHistory).toBe(true)
    })

    // Resolve and verify loading clears
    resolveGetTrades!([{ id: 1 }])

    await waitFor(() => {
      expect(result.current.isLoadingTradeHistory).toBe(false)
    })
  })
})

describe('usePositionTrades both queries', () => {
  test('both trades and tradeHistory can be active simultaneously', async () => {
    const tradesForExpanded = [{ id: 1, position_id: 5, side: 'buy' }]
    const tradesForModal = [{ id: 2, position_id: 10, side: 'sell' }]

    vi.mocked(positionsApi.getTrades).mockImplementation(((id: number) => {
      if (id === 5) return Promise.resolve(tradesForExpanded)
      if (id === 10) return Promise.resolve(tradesForModal)
      return Promise.resolve([])
    }) as any)

    const { result } = renderHook(
      () => usePositionTrades({
        selectedPosition: 5,
        tradeHistoryPosition: { id: 10, product_id: 'BTC-USD' },
        showTradeHistoryModal: true,
      }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.trades).toBeDefined()
      expect(result.current.tradeHistory).toBeDefined()
    })

    expect(result.current.trades).toEqual(tradesForExpanded)
    expect(result.current.tradeHistory).toEqual(tradesForModal)
  })

  test('returns all expected properties', () => {
    const { result } = renderHook(
      () => usePositionTrades({
        selectedPosition: null,
        tradeHistoryPosition: null,
        showTradeHistoryModal: false,
      }),
      { wrapper: createWrapper() }
    )

    expect(result.current).toHaveProperty('trades')
    expect(result.current).toHaveProperty('tradeHistory')
    expect(result.current).toHaveProperty('isLoadingTradeHistory')
  })
})
