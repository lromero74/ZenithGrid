import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'

import { useAccountValueSummary } from './useAccountValueSummary'

vi.mock('../services/api', () => ({
  accountValueSummaryApi: {
    get: vi.fn(),
  },
}))

import { accountValueSummaryApi } from '../services/api'

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('useAccountValueSummary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(accountValueSummaryApi.get).mockResolvedValue({
      account_id: 7,
      total_usd_value: 1073.69,
      total_btc_value: 0.0112,
      btc_usd_price: 95842.12,
      as_of: '2026-04-21T00:00:00',
      is_stale: true,
      is_refreshing: false,
    } as any)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  test('fetches account-specific summary when account is selected', async () => {
    const { result } = renderHook(
      () => useAccountValueSummary({ selectedAccount: { id: 7 } as any }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(accountValueSummaryApi.get).toHaveBeenCalledWith(7)
    expect(result.current.summary?.total_usd_value).toBe(1073.69)
  })

  test('does not fetch when selected account is missing', async () => {
    const { result } = renderHook(
      () => useAccountValueSummary({ selectedAccount: null }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(accountValueSummaryApi.get).not.toHaveBeenCalled()
    expect(result.current.summary).toBeUndefined()
  })
})
