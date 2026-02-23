/**
 * Tests for positionUtils.ts
 *
 * Tests pure helper functions for position price formatting and fee calculations.
 */

import { describe, test, expect } from 'vitest'
import {
  SELL_FEE_RATE,
  EXCHANGE_FEE_RATES,
  getSellFeeRate,
  getFeeAdjustedProfitMultiplier,
  getTakeProfitPercent,
  getQuoteCurrency,
  getBaseCurrency,
  formatPrice,
  formatBaseAmount,
  formatQuoteAmount,
} from './positionUtils'

describe('SELL_FEE_RATE', () => {
  test('default is Coinbase rate', () => {
    expect(SELL_FEE_RATE).toBe(0.006)
  })
})

describe('EXCHANGE_FEE_RATES', () => {
  test('contains expected exchanges', () => {
    expect(EXCHANGE_FEE_RATES.coinbase).toBe(0.006)
    expect(EXCHANGE_FEE_RATES.bybit).toBe(0.001)
    expect(EXCHANGE_FEE_RATES.mt5_bridge).toBe(0.0005)
  })
})

describe('getSellFeeRate', () => {
  test('returns coinbase rate by default', () => {
    expect(getSellFeeRate()).toBe(0.006)
    expect(getSellFeeRate(undefined)).toBe(0.006)
  })

  test('returns exchange-specific rate', () => {
    expect(getSellFeeRate('bybit')).toBe(0.001)
  })

  test('returns default for unknown exchange', () => {
    expect(getSellFeeRate('unknown')).toBe(SELL_FEE_RATE)
  })
})

describe('getFeeAdjustedProfitMultiplier', () => {
  test('calculates for 2% profit on coinbase', () => {
    const multiplier = getFeeAdjustedProfitMultiplier(2)
    // (1.02) / (1 - 0.006) = 1.02 / 0.994 ~ 1.02615
    expect(multiplier).toBeCloseTo(1.02615, 4)
  })

  test('calculates for 0% profit', () => {
    const multiplier = getFeeAdjustedProfitMultiplier(0)
    // 1.0 / (1 - 0.006) = 1.006036...
    expect(multiplier).toBeCloseTo(1 / 0.994, 5)
  })

  test('uses exchange-specific fee', () => {
    const multiplier = getFeeAdjustedProfitMultiplier(2, 'bybit')
    // (1.02) / (1 - 0.001) = 1.02 / 0.999 ~ 1.02102
    expect(multiplier).toBeCloseTo(1.02102, 4)
  })
})

describe('getTakeProfitPercent', () => {
  test('reads from position snapshot', () => {
    const position = {
      strategy_config_snapshot: { take_profit_percentage: 3.5 },
    } as any
    expect(getTakeProfitPercent(position, null)).toBe(3.5)
  })

  test('falls back to min_profit_percentage', () => {
    const position = {
      strategy_config_snapshot: { min_profit_percentage: 1.5 },
    } as any
    expect(getTakeProfitPercent(position, null)).toBe(1.5)
  })

  test('falls back to bot config', () => {
    const position = { strategy_config_snapshot: undefined } as any
    const bot = { strategy_config: { take_profit_percentage: 4.0 } }
    expect(getTakeProfitPercent(position, bot)).toBe(4.0)
  })

  test('returns 2.0 default when nothing configured', () => {
    const position = {} as any
    expect(getTakeProfitPercent(position, null)).toBe(2.0)
  })
})

describe('getQuoteCurrency', () => {
  test('returns BTC for BTC pair', () => {
    const result = getQuoteCurrency('ETH-BTC')
    expect(result.symbol).toBe('BTC')
    expect(result.decimals).toBe(8)
  })

  test('returns USD for USD pair', () => {
    const result = getQuoteCurrency('BTC-USD')
    expect(result.symbol).toBe('USD')
    expect(result.decimals).toBe(2)
  })

  test('defaults to BTC when no separator', () => {
    const result = getQuoteCurrency('')
    expect(result.symbol).toBe('BTC')
  })
})

describe('getBaseCurrency', () => {
  test('returns base currency', () => {
    const result = getBaseCurrency('ETH-BTC')
    expect(result.symbol).toBe('ETH')
    expect(result.decimals).toBe(6)
  })
})

describe('formatPrice', () => {
  test('formats USD price', () => {
    expect(formatPrice(50000, 'BTC-USD')).toBe('$50000.00')
  })

  test('formats BTC price', () => {
    expect(formatPrice(0.05, 'ETH-BTC')).toBe('0.05000000 BTC')
  })
})

describe('formatBaseAmount', () => {
  test('formats with base currency symbol', () => {
    expect(formatBaseAmount(1.5, 'ETH-BTC')).toBe('1.500000 ETH')
  })
})

describe('formatQuoteAmount', () => {
  test('formats BTC amounts', () => {
    expect(formatQuoteAmount(0.001, 'ETH-BTC')).toBe('0.00100000 BTC')
  })

  test('formats USD amounts', () => {
    expect(formatQuoteAmount(100.5, 'BTC-USD')).toBe('100.50 USD')
  })
})
