/**
 * Tests for pages/positions/helpers.ts
 *
 * Tests calculateUnrealizedPnL and calculateOverallStats.
 * checkSlippageBeforeMarketClose is skipped (requires fetch mock + callback testing).
 */

import { describe, test, expect } from 'vitest'
import { calculateUnrealizedPnL, calculateOverallStats } from './helpers'

describe('calculateUnrealizedPnL', () => {
  test('calculates PnL for BTC-quoted position with current price', () => {
    const position = {
      status: 'open',
      product_id: 'ETH-BTC',
      average_buy_price: 0.05,
      total_base_acquired: 10,
      total_quote_spent: 0.5,
      btc_usd_price_at_open: 50000,
    } as any

    const result = calculateUnrealizedPnL(position, 0.06, 67000)
    expect(result).not.toBeNull()
    // currentValue = 10 * 0.06 = 0.6; costBasis = 0.5; PnL = 0.1
    expect(result!.quote).toBeCloseTo(0.1)
    expect(result!.quoteCurrency).toBe('BTC')
    expect(result!.percent).toBeCloseTo(20) // 0.1/0.5 * 100
    expect(result!.usd).toBeCloseTo(6700) // 0.1 * 67000 (live BTC price)
    expect(result!.currentPrice).toBe(0.06)
  })

  test('falls back to average buy price when no current price', () => {
    const position = {
      status: 'open',
      product_id: 'ETH-BTC',
      average_buy_price: 0.05,
      total_base_acquired: 10,
      total_quote_spent: 0.5,
      btc_usd_price_at_open: 50000,
    } as any

    const result = calculateUnrealizedPnL(position)
    expect(result).not.toBeNull()
    // Uses avg buy price: value = 10 * 0.05 = 0.5, PnL = 0
    expect(result!.quote).toBeCloseTo(0)
    expect(result!.percent).toBeCloseTo(0)
  })

  test('returns null for non-open position', () => {
    const position = { status: 'closed' } as any
    expect(calculateUnrealizedPnL(position)).toBeNull()
  })

  test('handles zero cost basis', () => {
    const position = {
      status: 'open',
      product_id: 'ETH-BTC',
      average_buy_price: 100,
      total_base_acquired: 0,
      total_quote_spent: 0,
      btc_usd_price_at_open: 50000,
    } as any

    const result = calculateUnrealizedPnL(position, 100)
    expect(result).not.toBeNull()
    expect(result!.percent).toBe(0) // No div by zero
  })

  test('USD-quoted position PnL is already in USD', () => {
    // BTC-USD with $100 profit should NOT be multiplied by btc_usd_price
    const position = {
      status: 'open',
      product_id: 'BTC-USD',
      average_buy_price: 60000,
      total_base_acquired: 1,
      total_quote_spent: 60000,
      btc_usd_price_at_open: 60000,
    } as any

    // Current BTC price is $60100 → $100 profit
    const result = calculateUnrealizedPnL(position, 60100, 60100)
    expect(result).not.toBeNull()
    expect(result!.quote).toBeCloseTo(100)
    expect(result!.quoteCurrency).toBe('USD')
    expect(result!.usd).toBeCloseTo(100) // NOT 100 * 60100 = $6M!
  })

  test('BTC-quoted position uses live btcUsdPrice for USD conversion', () => {
    const position = {
      status: 'open',
      product_id: 'ETH-BTC',
      average_buy_price: 0.05,
      total_base_acquired: 10,
      total_quote_spent: 0.5,
      btc_usd_price_at_open: 50000,
    } as any

    // PnL = 0.1 BTC, live BTC price = 67000
    const result = calculateUnrealizedPnL(position, 0.06, 67000)
    expect(result).not.toBeNull()
    expect(result!.usd).toBeCloseTo(6700) // 0.1 * 67000 (live price, not 50000 at-open)
  })

  test('BTC-quoted falls back to btc_usd_price_at_open when no live price', () => {
    const position = {
      status: 'open',
      product_id: 'ETH-BTC',
      average_buy_price: 0.05,
      total_base_acquired: 10,
      total_quote_spent: 0.5,
      btc_usd_price_at_open: 50000,
    } as any

    const result = calculateUnrealizedPnL(position, 0.06) // no btcUsdPrice
    expect(result).not.toBeNull()
    expect(result!.usd).toBeCloseTo(5000) // 0.1 * 50000 (fallback)
  })

  test('returns quoteCurrency extracted from product_id', () => {
    const btcQuoted = {
      status: 'open', product_id: 'ETH-BTC',
      average_buy_price: 1, total_base_acquired: 1, total_quote_spent: 1, btc_usd_price_at_open: 50000,
    } as any
    const usdQuoted = {
      status: 'open', product_id: 'BTC-USD',
      average_buy_price: 1, total_base_acquired: 1, total_quote_spent: 1, btc_usd_price_at_open: 50000,
    } as any
    const usdcQuoted = {
      status: 'open', product_id: 'ETH-USDC',
      average_buy_price: 1, total_base_acquired: 1, total_quote_spent: 1, btc_usd_price_at_open: 50000,
    } as any

    expect(calculateUnrealizedPnL(btcQuoted)!.quoteCurrency).toBe('BTC')
    expect(calculateUnrealizedPnL(usdQuoted)!.quoteCurrency).toBe('USD')
    expect(calculateUnrealizedPnL(usdcQuoted)!.quoteCurrency).toBe('USDC')
  })

  test('unknown quote currency returns zero USD', () => {
    const position = {
      status: 'open',
      product_id: 'BTC-XYZ',
      average_buy_price: 100,
      total_base_acquired: 2,
      total_quote_spent: 200,
      btc_usd_price_at_open: 50000,
    } as any

    const result = calculateUnrealizedPnL(position, 110) // 20 XYZ profit
    expect(result).not.toBeNull()
    expect(result!.quote).toBeCloseTo(20)
    expect(result!.quoteCurrency).toBe('XYZ')
    expect(result!.usd).toBe(0) // No conversion available
  })
})

describe('calculateOverallStats', () => {
  test('calculates stats for multiple BTC-quoted positions', () => {
    const positions = [
      {
        product_id: 'ETH-BTC',
        total_quote_spent: 0.5,
        max_quote_allowed: 1.0,
        _cachedPnL: { quote: 0.05, quoteCurrency: 'BTC', usd: 2500 },
      },
      {
        product_id: 'SOL-BTC',
        total_quote_spent: 0.3,
        max_quote_allowed: 0.5,
        _cachedPnL: { quote: -0.02, quoteCurrency: 'BTC', usd: -1000 },
      },
    ] as any[]

    const stats = calculateOverallStats(positions)
    expect(stats.activeTrades).toBe(2)
    expect(stats.reservedByQuote.BTC).toBeCloseTo(0.8) // 0.5 + 0.3
    expect(stats.totalBudgetByQuote.BTC).toBeCloseTo(1.5) // 1.0 + 0.5
    expect(stats.uPnLByQuote.BTC).toBeCloseTo(0.03) // 0.05 - 0.02
    expect(stats.uPnLUSD).toBeCloseTo(1500) // 2500 - 1000
  })

  test('handles empty array', () => {
    const stats = calculateOverallStats([])
    expect(stats.activeTrades).toBe(0)
    expect(stats.uPnLUSD).toBe(0)
    expect(Object.keys(stats.uPnLByQuote)).toHaveLength(0)
  })

  test('groups by quote currency', () => {
    const positions = [
      {
        product_id: 'ETH-BTC',
        total_quote_spent: 0.5,
        max_quote_allowed: 1.0,
        _cachedPnL: { quote: 0, quoteCurrency: 'BTC', usd: 0 },
      },
      {
        product_id: 'BTC-USD',
        total_quote_spent: 50000,
        max_quote_allowed: 100000,
        _cachedPnL: { quote: 0, quoteCurrency: 'USD', usd: 0 },
      },
    ] as any[]

    const stats = calculateOverallStats(positions)
    expect(stats.reservedByQuote.BTC).toBeCloseTo(0.5)
    expect(stats.reservedByQuote.USD).toBeCloseTo(50000)
  })

  test('mixed currencies have correct USD total', () => {
    // 1 BTC-quoted (+0.05 BTC at $67k = $3350) + 1 USD-quoted (+$100)
    const positions = [
      {
        product_id: 'ETH-BTC',
        total_quote_spent: 0.5,
        max_quote_allowed: 1.0,
        _cachedPnL: { quote: 0.05, quoteCurrency: 'BTC', usd: 3350 },
      },
      {
        product_id: 'BTC-USD',
        total_quote_spent: 60000,
        max_quote_allowed: 100000,
        _cachedPnL: { quote: 100, quoteCurrency: 'USD', usd: 100 },
      },
    ] as any[]

    const stats = calculateOverallStats(positions)
    expect(stats.uPnLUSD).toBeCloseTo(3450) // 3350 + 100
  })

  test('uPnLByQuote separates currencies', () => {
    const positions = [
      {
        product_id: 'ETH-BTC',
        total_quote_spent: 0.5,
        max_quote_allowed: 1.0,
        _cachedPnL: { quote: 0.05, quoteCurrency: 'BTC', usd: 3350 },
      },
      {
        product_id: 'BTC-USD',
        total_quote_spent: 60000,
        max_quote_allowed: 100000,
        _cachedPnL: { quote: 100, quoteCurrency: 'USD', usd: 100 },
      },
    ] as any[]

    const stats = calculateOverallStats(positions)
    expect(stats.uPnLByQuote['BTC']).toBeCloseTo(0.05)
    expect(stats.uPnLByQuote['USD']).toBeCloseTo(100)
  })
})
