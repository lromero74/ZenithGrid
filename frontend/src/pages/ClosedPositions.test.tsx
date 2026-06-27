import { describe, test, expect, beforeEach, vi } from 'vitest'
import { render } from '@testing-library/react'
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import ClosedPositions from './ClosedPositions'
import { positionsApi, orderHistoryApi } from '../services/api'

const storageState = new Map<string, string>()

Object.defineProperty(globalThis, 'localStorage', {
  value: {
    getItem: vi.fn((key: string) => storageState.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      storageState.set(key, String(value))
    }),
    removeItem: vi.fn((key: string) => {
      storageState.delete(key)
    }),
  },
  configurable: true,
})

vi.mock('../services/api', () => ({
  positionsApi: {
    getAll: vi.fn().mockResolvedValue([]),
  },
  botsApi: {
    getAll: vi.fn().mockResolvedValue([]),
  },
  orderHistoryApi: {
    getFailedPaginated: vi.fn().mockResolvedValue({
      items: [],
      total: 0,
      total_pages: 1,
    }),
  },
  authFetch: vi.fn(),
}))

vi.mock('../contexts/AccountContext', () => ({
  useAccount: vi.fn(() => ({
    selectedAccount: {
      id: 7,
      name: 'Paper',
      type: 'cex',
      is_paper_trading: true,
    },
  })),
  getChainName: vi.fn(() => 'Ethereum'),
}))

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    user: {
      last_seen_history_count: 0,
      last_seen_failed_count: 0,
    },
    getAccessToken: vi.fn(),
    updateUser: vi.fn(),
  })),
}))

vi.mock('../hooks/useMarketPrice', () => ({
  useMarketPrice: vi.fn(() => ({ price: 0 })),
}))

vi.mock('../components/shared/LoadingSpinner', () => ({
  LoadingSpinner: () => React.createElement('div', null, 'Loading'),
}))

vi.mock('./positions/components/FilterPanel', () => ({
  FilterPanel: () => React.createElement('div', null, 'Filter Panel'),
}))

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })

  render(
    <QueryClientProvider client={queryClient}>
      <ClosedPositions />
    </QueryClientProvider>
  )

  return queryClient
}

describe('ClosedPositions polling policy', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    storageState.clear()
  })

  test('failed order polling does not refresh in hidden tabs or on window focus', () => {
    localStorage.setItem('zenith-history-tab', 'failed')
    const queryClient = renderPage()
    const queries = queryClient.getQueryCache().getAll()

    const observerOptions = queries
      .filter((query) => JSON.stringify(query.queryKey) === JSON.stringify(['order-history-failed-paginated', 7, 1]))
      .flatMap((query) => query.observers.map((observer: { options: { refetchInterval?: unknown; refetchIntervalInBackground?: unknown; refetchOnWindowFocus?: unknown } }) => observer.options))

    expect(observerOptions).toHaveLength(1)
    expect(observerOptions[0].refetchInterval).toBe(60000)
    expect(observerOptions[0].refetchIntervalInBackground).toBe(false)
    expect(observerOptions[0].refetchOnWindowFocus).toBe(false)
  })

  test('only fetches the visible history tab', () => {
    renderPage()

    expect(positionsApi.getAll).toHaveBeenCalledWith('closed', 500, 7)
    expect(orderHistoryApi.getFailedPaginated).not.toHaveBeenCalled()
  })

  test('switches network work to failed orders when the failed tab is active', () => {
    localStorage.setItem('zenith-history-tab', 'failed')
    renderPage()

    expect(positionsApi.getAll).not.toHaveBeenCalled()
    expect(orderHistoryApi.getFailedPaginated).toHaveBeenCalledWith(1, 25, undefined, 7)
  })
})
