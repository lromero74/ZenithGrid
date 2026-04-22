import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, waitFor, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { MemoryRouter } from 'react-router-dom'

import Dashboard from './Dashboard'

vi.mock('../services/api', () => ({
  botsApi: {
    getAll: vi.fn(),
    getStats: vi.fn(),
    stop: vi.fn(),
    start: vi.fn(),
  },
  positionsApi: {
    getAll: vi.fn(),
  },
  authFetch: vi.fn(),
  transfersApi: {
    getRecentSummary: vi.fn(),
  },
}))

vi.mock('../contexts/AccountContext', () => ({
  useAccount: vi.fn(),
  getChainName: vi.fn(() => 'Ethereum'),
}))

vi.mock('../contexts/NotificationContext', () => ({
  useNotifications: vi.fn(() => ({
    addToast: vi.fn(),
  })),
}))

vi.mock('../hooks/usePermission', () => ({
  usePermission: vi.fn(() => true),
}))

vi.mock('../hooks/useAccountValueSummary', () => ({
  useAccountValueSummary: vi.fn(() => ({
    summary: {
      total_usd_value: 1234.56,
      total_btc_value: 0.012345,
      is_stale: false,
      is_refreshing: false,
    },
  })),
}))

vi.mock('../components/trading/AccountValueChart', () => ({
  AccountValueChart: () => React.createElement('div', null, 'Account Value Chart'),
}))

vi.mock('../components/trading/MarketSentimentCards', () => ({
  MarketSentimentCards: () => React.createElement('div', null, 'Market Sentiment'),
}))

import { botsApi, positionsApi, authFetch, transfersApi } from '../services/api'
import { useAccount } from '../contexts/AccountContext'

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      MemoryRouter,
      undefined,
      React.createElement(QueryClientProvider, { client: queryClient }, children),
    )
  }
}

describe('Dashboard startup query deferral', () => {
  beforeEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()

    vi.mocked(useAccount).mockReturnValue({
      selectedAccount: {
        id: 7,
        name: 'Paper',
        type: 'cex',
        is_paper_trading: true,
      },
    } as any)

    vi.mocked(botsApi.getAll).mockResolvedValue([
      {
        id: 101,
        name: 'Momentum Bot',
        is_active: true,
        account_id: 7,
        product_id: 'ETH-USD',
        strategy_type: 'grid',
      },
    ] as any)
    vi.mocked(botsApi.getStats).mockResolvedValue({
      open_positions: 1,
      max_concurrent_deals: 3,
      total_profit_quote: 12.34,
      quote_currency: 'USD',
    } as any)
    vi.mocked(positionsApi.getAll).mockImplementation(async (status?: string) => {
      if (status === 'open') {
        return [
          {
            id: 1,
            account_id: 7,
            status: 'open',
            opened_at: '2026-04-22T00:00:00Z',
            total_quote_spent: 100,
            product_id: 'ETH-USD',
          },
        ] as any
      }
      return [
        {
          id: 2,
          account_id: 7,
          status: 'closed',
          opened_at: '2026-04-21T00:00:00Z',
          profit_usd: 10,
          profit_quote: 10,
          profit_percentage: 10,
          total_quote_spent: 100,
          product_id: 'ETH-USD',
        },
      ] as any
    })
    vi.mocked(authFetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ reserved_usd: 0, reserved_btc: 0 }),
    } as any)
    vi.mocked(transfersApi.getRecentSummary).mockResolvedValue({
      last_30d_net_deposits_usd: 0,
    } as any)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  test('keeps non-critical dashboard queries off the first render critical path', async () => {
    render(<Dashboard onNavigate={vi.fn()} />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(botsApi.getAll).toHaveBeenCalled()
      expect(positionsApi.getAll).toHaveBeenCalledWith('open', 100, 7)
      expect(positionsApi.getAll).toHaveBeenCalledWith('closed', 1000, 7)
    })

    expect(transfersApi.getRecentSummary).not.toHaveBeenCalled()
    expect(authFetch).not.toHaveBeenCalledWith('/api/account-value/reservations?account_id=7')
    expect(botsApi.getStats).not.toHaveBeenCalled()
  })

  test('starts deferred dashboard queries shortly after first paint', async () => {
    render(<Dashboard onNavigate={vi.fn()} />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText('Momentum Bot')).toBeInTheDocument()
    })

    await waitFor(() => {
      expect(transfersApi.getRecentSummary).toHaveBeenCalled()
      expect(authFetch).toHaveBeenCalledWith('/api/account-value/reservations?account_id=7')
      expect(botsApi.getStats).toHaveBeenCalledWith(101)
    }, { timeout: 4000 })
  }, 5000)

  test('keeps prop guard status deferred and gated to prop-firm accounts', async () => {
    vi.mocked(useAccount).mockReturnValue({
      selectedAccount: {
        id: 7,
        name: 'Paper',
        type: 'cex',
        is_paper_trading: true,
        prop_firm: null,
      },
    } as any)

    render(<Dashboard onNavigate={vi.fn()} />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(transfersApi.getRecentSummary).toHaveBeenCalled()
    }, { timeout: 4000 })

    expect(authFetch).not.toHaveBeenCalledWith('/api/propguard/7/status')
  }, 5000)
})
