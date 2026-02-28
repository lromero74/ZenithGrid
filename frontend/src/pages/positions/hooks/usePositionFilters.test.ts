/**
 * Tests for usePositionFilters hook
 *
 * Verifies localStorage persistence, filter/sort logic across multiple dimensions,
 * default values, memoized filtering, and the clearFilters action.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { usePositionFilters } from './usePositionFilters'
import type { Position } from '../../../types'

function makePosition(overrides: Partial<Position & { _cachedPnL?: any }> = {}): Position & { _cachedPnL?: any } {
  return {
    id: 1,
    status: 'open',
    bot_id: 1,
    product_id: 'ETH-USD',
    opened_at: '2025-01-01T00:00:00Z',
    closed_at: null,
    initial_quote_balance: 100,
    max_quote_allowed: 200,
    total_quote_spent: 50,
    total_base_acquired: 0.5,
    average_buy_price: 100,
    sell_price: null,
    total_quote_received: null,
    profit_quote: null,
    profit_percentage: null,
    trade_count: 1,
    ...overrides,
  }
}

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('usePositionFilters default values', () => {
  test('returns default filter values when localStorage is empty', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: [] })
    )

    expect(result.current.filterBot).toBe('all')
    expect(result.current.filterMarket).toBe('all')
    expect(result.current.filterPair).toBe('all')
    expect(result.current.sortBy).toBe('created')
    expect(result.current.sortOrder).toBe('desc')
  })

  test('returns empty openPositions for empty input', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: [] })
    )

    expect(result.current.openPositions).toEqual([])
    expect(result.current.uniquePairs).toEqual([])
  })
})

describe('usePositionFilters localStorage persistence', () => {
  test('restores filterBot from localStorage', () => {
    localStorage.setItem('zenith-positions-filter-bot', '5')

    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: [] })
    )

    expect(result.current.filterBot).toBe(5)
  })

  test('restores filterMarket from localStorage', () => {
    localStorage.setItem('zenith-positions-filter-market', 'BTC')

    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: [] })
    )

    expect(result.current.filterMarket).toBe('BTC')
  })

  test('restores filterPair from localStorage', () => {
    localStorage.setItem('zenith-positions-filter-pair', 'SOL-USD')

    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: [] })
    )

    expect(result.current.filterPair).toBe('SOL-USD')
  })

  test('restores sortBy from localStorage', () => {
    localStorage.setItem('zenith-positions-sort-by', 'pnl')

    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: [] })
    )

    expect(result.current.sortBy).toBe('pnl')
  })

  test('restores sortOrder from localStorage', () => {
    localStorage.setItem('zenith-positions-sort-order', 'asc')

    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: [] })
    )

    expect(result.current.sortOrder).toBe('asc')
  })

  test('persists filterBot to localStorage when changed', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: [] })
    )

    act(() => { result.current.setFilterBot(3) })

    expect(localStorage.getItem('zenith-positions-filter-bot')).toBe('3')
  })

  test('persists sortBy to localStorage when changed', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: [] })
    )

    act(() => { result.current.setSortBy('invested') })

    expect(localStorage.getItem('zenith-positions-sort-by')).toBe('invested')
  })

  test('returns default for "all" string in filterBot localStorage', () => {
    localStorage.setItem('zenith-positions-filter-bot', 'all')

    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: [] })
    )

    expect(result.current.filterBot).toBe('all')
  })
})

describe('usePositionFilters filtering logic', () => {
  const positions = [
    makePosition({ id: 1, status: 'open', bot_id: 1, product_id: 'ETH-USD' }),
    makePosition({ id: 2, status: 'open', bot_id: 2, product_id: 'SOL-USD' }),
    makePosition({ id: 3, status: 'open', bot_id: 1, product_id: 'ETH-BTC' }),
    makePosition({ id: 4, status: 'closed', bot_id: 1, product_id: 'ETH-USD', closed_at: '2025-02-01T00:00:00Z' }),
  ]

  test('filters to only open positions', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: positions })
    )

    const ids = result.current.openPositions.map(p => p.id)
    expect(ids).not.toContain(4)
    expect(ids).toHaveLength(3)
  })

  test('filters by bot_id', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: positions })
    )

    act(() => { result.current.setFilterBot(2) })

    const ids = result.current.openPositions.map(p => p.id)
    expect(ids).toEqual([2])
  })

  test('filters by USD market', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: positions })
    )

    act(() => { result.current.setFilterMarket('USD') })

    const ids = result.current.openPositions.map(p => p.id)
    expect(ids).toContain(1)
    expect(ids).toContain(2)
    expect(ids).not.toContain(3) // ETH-BTC should be excluded
  })

  test('filters by BTC market', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: positions })
    )

    act(() => { result.current.setFilterMarket('BTC') })

    const ids = result.current.openPositions.map(p => p.id)
    expect(ids).toEqual([3])
  })

  test('filters by specific pair', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: positions })
    )

    act(() => { result.current.setFilterPair('SOL-USD') })

    const ids = result.current.openPositions.map(p => p.id)
    expect(ids).toEqual([2])
  })

  test('combines bot filter and market filter', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: positions })
    )

    act(() => {
      result.current.setFilterBot(1)
      result.current.setFilterMarket('USD')
    })

    const ids = result.current.openPositions.map(p => p.id)
    expect(ids).toEqual([1])
  })
})

describe('usePositionFilters sorting logic', () => {
  const positions = [
    makePosition({
      id: 1, status: 'open', opened_at: '2025-01-01T00:00:00Z',
      total_quote_spent: 100, product_id: 'BTC-USD', bot_id: 2,
      _cachedPnL: { percent: 5 },
    }),
    makePosition({
      id: 2, status: 'open', opened_at: '2025-03-01T00:00:00Z',
      total_quote_spent: 50, product_id: 'ETH-USD', bot_id: 1,
      _cachedPnL: { percent: -2 },
    }),
    makePosition({
      id: 3, status: 'open', opened_at: '2025-02-01T00:00:00Z',
      total_quote_spent: 200, product_id: 'SOL-USD', bot_id: 3,
      _cachedPnL: { percent: 10 },
    }),
  ]

  test('sorts by created date descending by default', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: positions })
    )

    const ids = result.current.openPositions.map(p => p.id)
    expect(ids).toEqual([2, 3, 1]) // newest first
  })

  test('sorts by created date ascending', () => {
    localStorage.setItem('zenith-positions-sort-order', 'asc')

    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: positions })
    )

    const ids = result.current.openPositions.map(p => p.id)
    expect(ids).toEqual([1, 3, 2]) // oldest first
  })

  test('sorts by pnl descending', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: positions })
    )

    act(() => { result.current.setSortBy('pnl') })

    const ids = result.current.openPositions.map(p => p.id)
    expect(ids).toEqual([3, 1, 2]) // highest pnl first
  })

  test('sorts by invested descending', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: positions })
    )

    act(() => { result.current.setSortBy('invested') })

    const ids = result.current.openPositions.map(p => p.id)
    expect(ids).toEqual([3, 1, 2]) // highest invested first
  })

  test('sorts by pair alphabetically descending', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: positions })
    )

    act(() => { result.current.setSortBy('pair') })

    // desc: SOL > ETH > BTC
    const ids = result.current.openPositions.map(p => p.id)
    expect(ids).toEqual([3, 2, 1])
  })

  test('sorts by bot_id ascending', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: positions })
    )

    act(() => {
      result.current.setSortBy('bot')
      result.current.setSortOrder('asc')
    })

    const ids = result.current.openPositions.map(p => p.id)
    expect(ids).toEqual([2, 1, 3]) // bot 1, 2, 3
  })
})

describe('usePositionFilters uniquePairs', () => {
  test('returns unique pairs from open positions only', () => {
    const positions = [
      makePosition({ id: 1, status: 'open', product_id: 'ETH-USD' }),
      makePosition({ id: 2, status: 'open', product_id: 'ETH-USD' }),
      makePosition({ id: 3, status: 'open', product_id: 'SOL-USD' }),
      makePosition({ id: 4, status: 'closed', product_id: 'BTC-USD', closed_at: '2025-01-01' }),
    ]

    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: positions })
    )

    expect(result.current.uniquePairs).toHaveLength(2)
    expect(result.current.uniquePairs).toContain('ETH-USD')
    expect(result.current.uniquePairs).toContain('SOL-USD')
    expect(result.current.uniquePairs).not.toContain('BTC-USD')
  })

  test('defaults product_id to ETH-BTC when missing', () => {
    const positions = [
      makePosition({ id: 1, status: 'open', product_id: undefined }),
    ]

    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: positions })
    )

    expect(result.current.uniquePairs).toContain('ETH-BTC')
  })
})

describe('usePositionFilters clearFilters', () => {
  test('resets bot, market, and pair filters to all', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: [] })
    )

    act(() => {
      result.current.setFilterBot(5)
      result.current.setFilterMarket('USD')
      result.current.setFilterPair('ETH-USD')
    })

    expect(result.current.filterBot).toBe(5)
    expect(result.current.filterMarket).toBe('USD')
    expect(result.current.filterPair).toBe('ETH-USD')

    act(() => { result.current.clearFilters() })

    expect(result.current.filterBot).toBe('all')
    expect(result.current.filterMarket).toBe('all')
    expect(result.current.filterPair).toBe('all')
  })

  test('clearFilters does not reset sort settings', () => {
    const { result } = renderHook(() =>
      usePositionFilters({ positionsWithPnL: [] })
    )

    act(() => {
      result.current.setSortBy('pnl')
      result.current.setSortOrder('asc')
    })

    act(() => { result.current.clearFilters() })

    expect(result.current.sortBy).toBe('pnl')
    expect(result.current.sortOrder).toBe('asc')
  })
})
