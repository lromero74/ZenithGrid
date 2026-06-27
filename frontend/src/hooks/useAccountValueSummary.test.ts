import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'

import { useAccountValueSummary } from './useAccountValueSummary'
import type { AccountValueSummary } from '../services/api'

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
    vi.useRealTimers()
    vi.mocked(accountValueSummaryApi.get).mockResolvedValue({
      account_id: 7,
      total_usd_value: 1073.69,
      total_btc_value: 0.0112,
      btc_usd_price: 95842.12,
      as_of: '2026-04-21T00:00:00',
      is_stale: true,
      is_refreshing: false,
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  test('fetches account-specific summary when account is selected', async () => {
    const { result } = renderHook(
      () => useAccountValueSummary({ selectedAccount: { id: 7 } }),
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

  test('polls again quickly while stale summary is refreshing', async () => {
    vi.useRealTimers()
    vi.mocked(accountValueSummaryApi.get)
      .mockResolvedValueOnce({
        account_id: 7,
        total_usd_value: 1073.69,
        total_btc_value: 0.0112,
        btc_usd_price: 95842.12,
        as_of: '2026-04-21T00:00:00',
        is_stale: true,
        is_refreshing: true,
      })
      .mockResolvedValueOnce({
        account_id: 7,
        total_usd_value: 1100.0,
        total_btc_value: 0.0115,
        btc_usd_price: 95842.12,
        as_of: '2026-04-21T00:00:05',
        is_stale: false,
        is_refreshing: false,
      })

    const { result } = renderHook(
      () => useAccountValueSummary({ selectedAccount: { id: 7 } }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.summary?.is_refreshing).toBe(true)
    })

    await waitFor(() => {
      expect(accountValueSummaryApi.get).toHaveBeenCalledTimes(2)
      expect(result.current.summary?.total_usd_value).toBe(1100.0)
    }, { timeout: 7000 })
  }, 8000)

  test('keeps stale summary visible while quick refresh is in flight', async () => {
    vi.useRealTimers()
    let resolveFresh: ((value: AccountValueSummary) => void) | undefined

    vi.mocked(accountValueSummaryApi.get)
      .mockResolvedValueOnce({
        account_id: 7,
        total_usd_value: 1073.69,
        total_btc_value: 0.0112,
        btc_usd_price: 95842.12,
        as_of: '2026-04-21T00:00:00',
        is_stale: true,
        is_refreshing: true,
      })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveFresh = resolve
          }) as Promise<AccountValueSummary>,
      )

    const { result } = renderHook(
      () => useAccountValueSummary({ selectedAccount: { id: 7 } }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.summary?.total_usd_value).toBe(1073.69)
    })

    await waitFor(() => {
      expect(accountValueSummaryApi.get).toHaveBeenCalledTimes(2)
    }, { timeout: 7000 })

    expect(result.current.summary?.total_usd_value).toBe(1073.69)
    expect(result.current.isLoading).toBe(false)

    resolveFresh?.({
      account_id: 7,
      total_usd_value: 1111.11,
      total_btc_value: 0.0116,
      btc_usd_price: 95842.12,
      as_of: '2026-04-21T00:00:10',
      is_stale: false,
      is_refreshing: false,
    })

    await waitFor(() => {
      expect(result.current.summary?.total_usd_value).toBe(1111.11)
    })
  }, 8000)
})
