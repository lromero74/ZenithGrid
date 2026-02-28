/**
 * Tests for useBotsData hook.
 *
 * Verifies multi-query fetching (bots, strategies, portfolio, aggregate,
 * templates, products), `select` filtering by account, and trading pairs
 * derivation from product data.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { useBotsData } from './useBotsData'
import type { Bot } from '../../../types'

// ---------- Mocks ----------

vi.mock('../../../services/api', () => ({
  botsApi: {
    getAll: vi.fn(),
    getStrategies: vi.fn(),
  },
  templatesApi: {
    getAll: vi.fn(),
  },
  accountApi: {
    getAggregateValue: vi.fn(),
  },
  authFetch: vi.fn(),
  api: {
    get: vi.fn(),
  },
}))

vi.mock('../../../components/bots', () => ({
  convertProductsToTradingPairs: vi.fn(),
  DEFAULT_TRADING_PAIRS: [
    { value: 'BTC-USD', label: 'BTC/USD', group: 'USD', base: 'BTC' },
    { value: 'ETH-USD', label: 'ETH/USD', group: 'USD', base: 'ETH' },
    { value: 'ETH-BTC', label: 'ETH/BTC', group: 'BTC', base: 'ETH' },
  ],
}))

import { botsApi, templatesApi, accountApi, authFetch, api } from '../../../services/api'
import { convertProductsToTradingPairs, DEFAULT_TRADING_PAIRS } from '../../../components/bots'

// ---------- Helpers ----------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

const mockBots: Bot[] = [
  { id: 1, name: 'Bot A', account_id: 1, is_active: true, strategy_type: 'dca_bot_v2', strategy_config: {}, product_id: 'ETH-BTC', reserved_btc_balance: 0, reserved_usd_balance: 0, budget_percentage: 5, created_at: '', updated_at: '', last_signal_check: null, description: null },
  { id: 2, name: 'Bot B', account_id: 2, is_active: false, strategy_type: 'dca_bot_v2', strategy_config: {}, product_id: 'SOL-BTC', reserved_btc_balance: 0, reserved_usd_balance: 0, budget_percentage: 10, created_at: '', updated_at: '', last_signal_check: null, description: null },
  { id: 3, name: 'Bot C', account_id: 1, is_active: true, strategy_type: 'grid_bot', strategy_config: {}, product_id: 'BTC-USD', reserved_btc_balance: 0, reserved_usd_balance: 0, budget_percentage: 15, created_at: '', updated_at: '', last_signal_check: null, description: null },
]

const mockStrategies = [
  { id: 'dca_bot_v2', name: 'DCA Bot', description: 'Dollar cost average', parameters: [] },
]

const mockPortfolio = { total_btc_value: 2.5, total_usd_value: 150000 }

const mockTemplates = [
  { id: 1, name: 'Aggressive', strategy_type: 'dca_bot_v2' },
]

// ---------- Suite ----------

describe('useBotsData', () => {
  beforeEach(() => {
    vi.restoreAllMocks()

    // Set up default mock implementations
    vi.mocked(botsApi.getAll).mockResolvedValue(mockBots)
    vi.mocked(botsApi.getStrategies).mockResolvedValue(mockStrategies as any)
    vi.mocked(templatesApi.getAll).mockResolvedValue(mockTemplates)
    vi.mocked(accountApi.getAggregateValue).mockResolvedValue({ total_btc: 2.5, total_usd: 150000 } as any)
    vi.mocked(authFetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockPortfolio),
    } as Response)
    vi.mocked(api.get).mockResolvedValue({ data: { products: [] } })
    vi.mocked(convertProductsToTradingPairs).mockReturnValue([])
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('fetches bots and returns them', async () => {
    const { result } = renderHook(
      () => useBotsData({ selectedAccount: null, projectionTimeframe: '30d' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.botsLoading).toBe(false)
    })

    // With no selectedAccount, all bots are returned
    expect(result.current.bots).toHaveLength(3)
    expect(botsApi.getAll).toHaveBeenCalledWith('30d')
  })

  test('filters bots by selected account', async () => {
    const { result } = renderHook(
      () => useBotsData({ selectedAccount: { id: 1 }, projectionTimeframe: '30d' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.botsLoading).toBe(false)
    })

    // Only bots with account_id === 1 should be returned
    expect(result.current.bots).toHaveLength(2)
    expect(result.current.bots.every((b: Bot) => b.account_id === 1)).toBe(true)
  })

  test('returns empty array when selected account has no bots', async () => {
    const { result } = renderHook(
      () => useBotsData({ selectedAccount: { id: 999 }, projectionTimeframe: '30d' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.botsLoading).toBe(false)
    })

    expect(result.current.bots).toHaveLength(0)
  })

  test('fetches strategies', async () => {
    const { result } = renderHook(
      () => useBotsData({ selectedAccount: { id: 1 }, projectionTimeframe: '30d' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.strategies).toHaveLength(1)
    })

    expect(result.current.strategies[0].id).toBe('dca_bot_v2')
  })

  test('fetches account-specific portfolio when account is selected', async () => {
    const { result } = renderHook(
      () => useBotsData({ selectedAccount: { id: 1 }, projectionTimeframe: '30d' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.portfolioLoading).toBe(false)
    })

    expect(authFetch).toHaveBeenCalledWith('/api/accounts/1/portfolio')
    expect(result.current.portfolio).toEqual(mockPortfolio)
  })

  test('fetches default portfolio when no account is selected', async () => {
    const { result } = renderHook(
      () => useBotsData({ selectedAccount: null, projectionTimeframe: '30d' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.portfolioLoading).toBe(false)
    })

    expect(authFetch).toHaveBeenCalledWith('/api/account/portfolio')
  })

  test('fetches templates', async () => {
    const { result } = renderHook(
      () => useBotsData({ selectedAccount: { id: 1 }, projectionTimeframe: '30d' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.templates).toHaveLength(1)
    })

    expect(result.current.templates[0].name).toBe('Aggressive')
  })

  test('returns DEFAULT_TRADING_PAIRS when no products data', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} })

    const { result } = renderHook(
      () => useBotsData({ selectedAccount: { id: 1 }, projectionTimeframe: '30d' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.botsLoading).toBe(false)
    })

    expect(result.current.TRADING_PAIRS).toEqual(DEFAULT_TRADING_PAIRS)
  })

  test('converts products to trading pairs when products data is available', async () => {
    const products = [
      { base_currency: 'ETH', quote_currency: 'BTC', product_id: 'ETH-BTC' },
      { base_currency: 'SOL', quote_currency: 'USD', product_id: 'SOL-USD' },
    ]
    const convertedPairs = [
      { value: 'ETH-BTC', label: 'ETH/BTC', group: 'BTC', base: 'ETH' },
      { value: 'SOL-USD', label: 'SOL/USD', group: 'USD', base: 'SOL' },
    ]
    vi.mocked(api.get).mockResolvedValue({ data: { products } })
    vi.mocked(convertProductsToTradingPairs).mockReturnValue(convertedPairs)

    const { result } = renderHook(
      () => useBotsData({ selectedAccount: { id: 1 }, projectionTimeframe: '30d' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.TRADING_PAIRS).toHaveLength(2)
    })

    expect(convertProductsToTradingPairs).toHaveBeenCalledWith(products)
    expect(result.current.TRADING_PAIRS).toEqual(convertedPairs)
  })

  test('passes account_id to products endpoint when account is selected', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { products: [] } })

    renderHook(
      () => useBotsData({ selectedAccount: { id: 5 }, projectionTimeframe: '30d' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/products', { params: { account_id: 5 } })
    })
  })

  test('passes empty params to products endpoint when no account selected', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { products: [] } })

    renderHook(
      () => useBotsData({ selectedAccount: null, projectionTimeframe: '30d' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/products', { params: {} })
    })
  })

  test('fetches aggregate data', async () => {
    const { result } = renderHook(
      () => useBotsData({ selectedAccount: { id: 1 }, projectionTimeframe: '30d' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.aggregateData).toBeDefined()
    })

    expect(accountApi.getAggregateValue).toHaveBeenCalled()
  })

  test('defaults to empty arrays when queries fail', async () => {
    vi.mocked(botsApi.getAll).mockRejectedValue(new Error('Network error'))
    vi.mocked(botsApi.getStrategies).mockRejectedValue(new Error('Network error'))
    vi.mocked(templatesApi.getAll).mockRejectedValue(new Error('Network error'))

    const { result } = renderHook(
      () => useBotsData({ selectedAccount: { id: 1 }, projectionTimeframe: '30d' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.botsLoading).toBe(false)
    })

    // Defaults defined in useQuery: `data: bots = []`
    expect(result.current.bots).toEqual([])
    expect(result.current.strategies).toEqual([])
    expect(result.current.templates).toEqual([])
  })

  test('uses different projection timeframes', async () => {
    const { result } = renderHook(
      () => useBotsData({ selectedAccount: { id: 1 }, projectionTimeframe: '7d' }),
      { wrapper: createWrapper() },
    )

    await waitFor(() => {
      expect(result.current.botsLoading).toBe(false)
    })

    expect(botsApi.getAll).toHaveBeenCalledWith('7d')
  })
})
