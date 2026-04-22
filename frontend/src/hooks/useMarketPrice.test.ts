import { describe, test, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'

import { useMarketPrice } from './useMarketPrice'

vi.mock('../services/api', () => ({
  marketDataApi: {
    getPrice: vi.fn(),
  },
}))

import { marketDataApi } from '../services/api'

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('useMarketPrice', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(marketDataApi.getPrice).mockResolvedValue({ price: 12345.67 })
  })

  test('fetches the requested product price', async () => {
    const { result } = renderHook(
      () => useMarketPrice({ productId: 'BTC-USD' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(marketDataApi.getPrice).toHaveBeenCalledWith('BTC-USD')
    expect(result.current.price).toBe(12345.67)
  })

  test('uses product-specific query keys', async () => {
    renderHook(
      () => useMarketPrice({ productId: 'ETH-USD' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(marketDataApi.getPrice).toHaveBeenCalledWith('ETH-USD')
    })

    expect(vi.mocked(marketDataApi.getPrice)).not.toHaveBeenCalledWith('BTC-USD')
  })
})
