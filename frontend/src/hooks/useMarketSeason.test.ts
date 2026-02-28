/**
 * Tests for useMarketSeason hook.
 *
 * Verifies the three API calls (fear-greed, ath, btc-dominance),
 * determineMarketSeason integration, and headerGradient derivation per season.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { useMarketSeason } from './useMarketSeason'

// ---------- Mocks ----------

vi.mock('../services/api', () => ({
  authFetch: vi.fn(),
}))

// Mock seasonDetection so we control what season is returned
vi.mock('../utils/seasonDetection', () => ({
  determineMarketSeason: vi.fn(),
}))

import { authFetch } from '../services/api'
import { determineMarketSeason } from '../utils/seasonDetection'

// ---------- Helpers ----------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

function mockFetchResponses(
  fearGreed: object | null,
  ath: object | null,
  btcDominance: object | null,
) {
  vi.mocked(authFetch).mockImplementation(async (url: string) => {
    if (url === '/api/news/fear-greed') {
      if (!fearGreed) return { ok: false, json: () => Promise.resolve(null) } as Response
      return { ok: true, json: () => Promise.resolve(fearGreed) } as Response
    }
    if (url === '/api/news/ath') {
      if (!ath) return { ok: false, json: () => Promise.resolve(null) } as Response
      return { ok: true, json: () => Promise.resolve(ath) } as Response
    }
    if (url === '/api/news/btc-dominance') {
      if (!btcDominance) return { ok: false, json: () => Promise.resolve(null) } as Response
      return { ok: true, json: () => Promise.resolve(btcDominance) } as Response
    }
    return { ok: false, json: () => Promise.resolve(null) } as Response
  })
}

// ---------- Suite ----------

describe('useMarketSeason', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('returns null seasonInfo and isLoading=true initially', () => {
    // Never resolve the fetch to keep it loading
    vi.mocked(authFetch).mockImplementation(() => new Promise(() => {}))
    const { result } = renderHook(() => useMarketSeason(), { wrapper: createWrapper() })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.seasonInfo).toBeNull()
  })

  test('calls all three API endpoints', async () => {
    const fearGreed = { data: { value: 65 }, cached_at: '', cache_expires_at: '' }
    const ath = { current_price: 95000, ath: 100000, ath_date: '2025-01-01', days_since_ath: 30, drawdown_pct: 5, recovery_pct: 95, cached_at: '' }
    const btcDom = { btc_dominance: 55, eth_dominance: 15, others_dominance: 30, total_market_cap: 3e12, cached_at: '' }

    mockFetchResponses(fearGreed, ath, btcDom)
    vi.mocked(determineMarketSeason).mockReturnValue({
      season: 'bull', name: 'Summer', subtitle: 'Bull Market',
      description: 'Prices rising', progress: 50, confidence: 70,
      icon: {} as any, color: 'text-green-400',
      bgGradient: 'from-green-900/30 to-emerald-900/20',
      signals: ['50 days post-halving'],
    })

    renderHook(() => useMarketSeason(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(vi.mocked(authFetch)).toHaveBeenCalledWith('/api/news/fear-greed')
      expect(vi.mocked(authFetch)).toHaveBeenCalledWith('/api/news/ath')
      expect(vi.mocked(authFetch)).toHaveBeenCalledWith('/api/news/btc-dominance')
    })
  })

  test('passes correct arguments to determineMarketSeason', async () => {
    const fearGreed = { data: { value: 72 }, cached_at: '', cache_expires_at: '' }
    const ath = { current_price: 90000, ath: 100000, ath_date: '2025-01-01', days_since_ath: 60, drawdown_pct: 10, recovery_pct: 90, cached_at: '' }
    const btcDom = { btc_dominance: 48, eth_dominance: 18, others_dominance: 34, total_market_cap: 3e12, cached_at: '' }

    mockFetchResponses(fearGreed, ath, btcDom)
    vi.mocked(determineMarketSeason).mockReturnValue({
      season: 'distribution', name: 'Fall', subtitle: 'Distribution Phase',
      description: 'Peak euphoria', progress: 30, confidence: 80,
      icon: {} as any, color: 'text-orange-400',
      bgGradient: 'from-orange-900/30 to-red-900/20',
      signals: [],
    })

    const { result } = renderHook(() => useMarketSeason(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.seasonInfo).not.toBeNull()
    })

    expect(vi.mocked(determineMarketSeason)).toHaveBeenCalledWith(72, ath, btcDom)
  })

  test('returns bull headerGradient when season is bull', async () => {
    const fearGreed = { data: { value: 60 }, cached_at: '', cache_expires_at: '' }
    const ath = { current_price: 95000, ath: 100000, ath_date: '2025-01-01', days_since_ath: 30, drawdown_pct: 5, recovery_pct: 95, cached_at: '' }
    const btcDom = { btc_dominance: 50, eth_dominance: 15, others_dominance: 35, total_market_cap: 3e12, cached_at: '' }

    mockFetchResponses(fearGreed, ath, btcDom)
    vi.mocked(determineMarketSeason).mockReturnValue({
      season: 'bull', name: 'Summer', subtitle: 'Bull Market',
      description: 'Prices rising', progress: 50, confidence: 70,
      icon: {} as any, color: 'text-green-400',
      bgGradient: 'from-green-900/30 to-emerald-900/20',
      signals: [],
    })

    const { result } = renderHook(() => useMarketSeason(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.headerGradient).toBe('from-green-950/20 via-slate-900 to-slate-900')
    })
  })

  test('returns accumulation headerGradient when season is accumulation', async () => {
    const fearGreed = { data: { value: 25 }, cached_at: '', cache_expires_at: '' }
    mockFetchResponses(fearGreed, null, null)
    vi.mocked(determineMarketSeason).mockReturnValue({
      season: 'accumulation', name: 'Spring', subtitle: 'Accumulation Phase',
      description: 'Smart money buying', progress: 40, confidence: 60,
      icon: {} as any, color: 'text-pink-400',
      bgGradient: 'from-pink-900/30 to-rose-900/20',
      signals: [],
    })

    const { result } = renderHook(() => useMarketSeason(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.headerGradient).toBe('from-pink-950/20 via-slate-900 to-slate-900')
    })
  })

  test('returns bear headerGradient when season is bear', async () => {
    const fearGreed = { data: { value: 15 }, cached_at: '', cache_expires_at: '' }
    mockFetchResponses(fearGreed, null, null)
    vi.mocked(determineMarketSeason).mockReturnValue({
      season: 'bear', name: 'Winter', subtitle: 'Bear Market',
      description: 'Prices falling', progress: 60, confidence: 50,
      icon: {} as any, color: 'text-blue-400',
      bgGradient: 'from-blue-900/30 to-slate-900/20',
      signals: [],
    })

    const { result } = renderHook(() => useMarketSeason(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.headerGradient).toBe('from-blue-950/20 via-slate-900 to-slate-900')
    })
  })

  test('returns distribution headerGradient when season is distribution', async () => {
    const fearGreed = { data: { value: 75 }, cached_at: '', cache_expires_at: '' }
    mockFetchResponses(fearGreed, null, null)
    vi.mocked(determineMarketSeason).mockReturnValue({
      season: 'distribution', name: 'Fall', subtitle: 'Distribution Phase',
      description: 'Peak euphoria', progress: 20, confidence: 75,
      icon: {} as any, color: 'text-orange-400',
      bgGradient: 'from-orange-900/30 to-red-900/20',
      signals: [],
    })

    const { result } = renderHook(() => useMarketSeason(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.headerGradient).toBe('from-orange-950/20 via-slate-900 to-slate-900')
    })
  })

  test('returns default gradient when no data is available', async () => {
    // All endpoints fail
    vi.mocked(authFetch).mockResolvedValue({
      ok: false,
      json: () => Promise.resolve(null),
    } as Response)

    const { result } = renderHook(() => useMarketSeason(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    // No data = null seasonInfo = default gradient
    expect(result.current.seasonInfo).toBeNull()
    expect(result.current.headerGradient).toBe('from-slate-900 via-slate-900 to-slate-900')
  })

  test('isLoading is false once all queries complete', async () => {
    const fearGreed = { data: { value: 50 }, cached_at: '', cache_expires_at: '' }
    const ath = { current_price: 95000, ath: 100000, ath_date: '2025-01-01', days_since_ath: 30, drawdown_pct: 5, recovery_pct: 95, cached_at: '' }
    const btcDom = { btc_dominance: 50, eth_dominance: 15, others_dominance: 35, total_market_cap: 3e12, cached_at: '' }

    mockFetchResponses(fearGreed, ath, btcDom)
    vi.mocked(determineMarketSeason).mockReturnValue({
      season: 'bull', name: 'Summer', subtitle: 'Bull Market',
      description: 'Prices rising', progress: 50, confidence: 70,
      icon: {} as any, color: 'text-green-400',
      bgGradient: 'from-green-900/30 to-emerald-900/20',
      signals: [],
    })

    const { result } = renderHook(() => useMarketSeason(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
  })

  test('computes seasonInfo when only partial data is available (fear-greed only)', async () => {
    const fearGreed = { data: { value: 30 }, cached_at: '', cache_expires_at: '' }

    // Only fear-greed succeeds; ath + btc-dominance fail
    vi.mocked(authFetch).mockImplementation(async (url: string) => {
      if (url === '/api/news/fear-greed') {
        return { ok: true, json: () => Promise.resolve(fearGreed) } as Response
      }
      return { ok: false, json: () => Promise.resolve(null) } as Response
    })

    vi.mocked(determineMarketSeason).mockReturnValue({
      season: 'accumulation', name: 'Spring', subtitle: 'Accumulation Phase',
      description: 'Smart money buying', progress: 40, confidence: 55,
      icon: {} as any, color: 'text-pink-400',
      bgGradient: 'from-pink-900/30 to-rose-900/20',
      signals: ['Fear & Greed at 30'],
    })

    const { result } = renderHook(() => useMarketSeason(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.seasonInfo).not.toBeNull()
    })

    // fearGreed data is present, so hasData is true, determineMarketSeason should be called
    expect(vi.mocked(determineMarketSeason)).toHaveBeenCalledWith(30, undefined, undefined)
    expect(result.current.seasonInfo?.season).toBe('accumulation')
  })
})
