/**
 * Tests for useAccountPortfolio — the single shared portfolio query.
 *
 * Portfolio data was previously fetched by three page-level queries with
 * mismatched keys/endpoints (Portfolio, Bots, Charts), tripling the API load.
 * This hook gives every consumer one cache entry per account (plus an
 * isolated 'live' flavor for the Portfolio page's force-fresh view).
 */

import { describe, test, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'

vi.mock('../services/api', () => ({
  authFetch: vi.fn(),
}))

import { authFetch } from '../services/api'
import { useAccountPortfolio } from './useAccountPortfolio'

const mockPortfolio = { total_btc_value: 2.5, total_usd_value: 150000, holdings: [] }

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

function mockFetchOk() {
  vi.mocked(authFetch).mockResolvedValue({
    ok: true,
    json: async () => mockPortfolio,
  } as unknown as Response)
}

beforeEach(() => {
  vi.clearAllMocks()
  mockFetchOk()
})

describe('useAccountPortfolio', () => {
  test('fetches the account-scoped endpoint and returns data', async () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useAccountPortfolio(7), { wrapper })

    await waitFor(() => expect(result.current.data).toEqual(mockPortfolio))
    expect(authFetch).toHaveBeenCalledWith('/api/accounts/7/portfolio')
  })

  test('two consumers share ONE fetch (deduplicated cache entry)', async () => {
    const wrapper = createWrapper()
    const first = renderHook(() => useAccountPortfolio(7), { wrapper })
    const second = renderHook(() => useAccountPortfolio(7), { wrapper })

    await waitFor(() => expect(first.result.current.data).toEqual(mockPortfolio))
    await waitFor(() => expect(second.result.current.data).toEqual(mockPortfolio))

    expect(vi.mocked(authFetch)).toHaveBeenCalledTimes(1)
  })

  test('live flavor forces fresh data and uses an isolated cache entry', async () => {
    const wrapper = createWrapper()
    const cached = renderHook(() => useAccountPortfolio(7), { wrapper })
    const live = renderHook(() => useAccountPortfolio(7, { live: true }), { wrapper })

    await waitFor(() => expect(cached.result.current.data).toEqual(mockPortfolio))
    await waitFor(() => expect(live.result.current.data).toEqual(mockPortfolio))

    const urls = vi.mocked(authFetch).mock.calls.map((c) => c[0])
    expect(urls).toContain('/api/accounts/7/portfolio')
    expect(urls).toContain('/api/accounts/7/portfolio?force_fresh=true')
    expect(urls).toHaveLength(2)
  })

  test('falls back to the default-account endpoint without an account id', async () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useAccountPortfolio(null), { wrapper })

    await waitFor(() => expect(result.current.data).toEqual(mockPortfolio))
    expect(authFetch).toHaveBeenCalledWith('/api/account/portfolio')
  })

  test('failed response surfaces as an error', async () => {
    vi.mocked(authFetch).mockResolvedValue({
      ok: false,
      json: async () => ({}),
    } as unknown as Response)

    const wrapper = createWrapper()
    const { result } = renderHook(() => useAccountPortfolio(7), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})
