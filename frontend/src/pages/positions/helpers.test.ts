/**
 * Tests for pages/positions/helpers.ts
 *
 * Tests calculateUnrealizedPnL and calculateOverallStats.
 * checkSlippageBeforeMarketClose is skipped (requires fetch mock + callback testing).
 */

import { describe, test, expect } from 'vitest'
import { calculateUnrealizedPnL, calculateOverallStats } from './helpers'

describe('calculateUnrealizedPnL', () => {
  test('calculates PnL for open position with current price', () => {
    const position = {
      status: 'open',
      average_buy_price: 0.05,
      total_base_acquired: 10,
      total_quote_spent: 0.5,
      btc_usd_price_at_open: 50000,
    } as any

    const result = calculateUnrealizedPnL(position, 0.06)
    expect(result).not.toBeNull()
    // currentValue = 10 * 0.06 = 0.6; costBasis = 0.5; PnL = 0.1
    expect(result!.btc).toBeCloseTo(0.1)
    expect(result!.percent).toBeCloseTo(20) // 0.1/0.5 * 100
    expect(result!.usd).toBeCloseTo(5000) // 0.1 * 50000
    expect(result!.currentPrice).toBe(0.06)
  })

  test('falls back to average buy price when no current price', () => {
    const position = {
      status: 'open',
      average_buy_price: 0.05,
      total_base_acquired: 10,
      total_quote_spent: 0.5,
      btc_usd_price_at_open: 50000,
    } as any

    const result = calculateUnrealizedPnL(position)
    expect(result).not.toBeNull()
    // Uses avg buy price: value = 10 * 0.05 = 0.5, PnL = 0
    expect(result!.btc).toBeCloseTo(0)
    expect(result!.percent).toBeCloseTo(0)
  })

  test('returns null for non-open position', () => {
    const position = { status: 'closed' } as any
    expect(calculateUnrealizedPnL(position)).toBeNull()
  })

  test('handles zero cost basis', () => {
    const position = {
      status: 'open',
      average_buy_price: 100,
      total_base_acquired: 0,
      total_quote_spent: 0,
      btc_usd_price_at_open: 50000,
    } as any

    const result = calculateUnrealizedPnL(position, 100)
    expect(result).not.toBeNull()
    expect(result!.percent).toBe(0) // No div by zero
  })
})

describe('calculateOverallStats', () => {
  test('calculates stats for multiple positions', () => {
    const positions = [
      {
        product_id: 'ETH-BTC',
        total_quote_spent: 0.5,
        max_quote_allowed: 1.0,
        _cachedPnL: { btc: 0.05, usd: 2500 },
      },
      {
        product_id: 'SOL-BTC',
        total_quote_spent: 0.3,
        max_quote_allowed: 0.5,
        _cachedPnL: { btc: -0.02, usd: -1000 },
      },
    ] as any[]

    const stats = calculateOverallStats(positions)
    expect(stats.activeTrades).toBe(2)
    expect(stats.reservedByQuote.BTC).toBeCloseTo(0.8) // 0.5 + 0.3
    expect(stats.totalBudgetByQuote.BTC).toBeCloseTo(1.5) // 1.0 + 0.5
    expect(stats.uPnL).toBeCloseTo(0.03) // 0.05 - 0.02
    expect(stats.uPnLUSD).toBeCloseTo(1500) // 2500 - 1000
  })

  test('handles empty array', () => {
    const stats = calculateOverallStats([])
    expect(stats.activeTrades).toBe(0)
    expect(stats.uPnL).toBe(0)
    expect(stats.uPnLUSD).toBe(0)
  })

  test('groups by quote currency', () => {
    const positions = [
      {
        product_id: 'ETH-BTC',
        total_quote_spent: 0.5,
        max_quote_allowed: 1.0,
        _cachedPnL: { btc: 0, usd: 0 },
      },
      {
        product_id: 'BTC-USD',
        total_quote_spent: 50000,
        max_quote_allowed: 100000,
        _cachedPnL: { btc: 0, usd: 0 },
      },
    ] as any[]

    const stats = calculateOverallStats(positions)
    expect(stats.reservedByQuote.BTC).toBeCloseTo(0.5)
    expect(stats.reservedByQuote.USD).toBeCloseTo(50000)
  })
})
