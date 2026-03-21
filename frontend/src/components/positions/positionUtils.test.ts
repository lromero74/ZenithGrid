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
  calculateSOLevels,
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

// ─── calculateSOLevels ────────────────────────────────────────────────────────

const basePosition = {
  id: 1,
  status: 'open',
  product_id: 'ETH-BTC',
  direction: 'long',
  average_buy_price: 100,
  first_buy_price: 100,
  last_buy_price: 100,
  trade_count: 1,  // just the base order — no SOs filled yet
  opened_at: '2024-01-01T00:00:00Z',
  closed_at: null,
  initial_quote_balance: 0.1,
  max_quote_allowed: 0.5,
  total_quote_spent: 0.1,
  total_base_acquired: 1.0,
  sell_price: null,
  total_quote_received: null,
  profit_quote: null,
  profit_percentage: null,
  strategy_config_snapshot: {
    price_deviation: 2.0,
    safety_order_step_scale: 1.0,
    max_safety_orders: 3,
    dca_target_reference: 'average_price',
  },
} as any

describe('calculateSOLevels', () => {
  test('returns empty array when no strategy_config_snapshot', () => {
    const pos = { ...basePosition, strategy_config_snapshot: undefined }
    expect(calculateSOLevels(pos)).toEqual([])
  })

  test('returns empty array when no price_deviation configured', () => {
    const pos = { ...basePosition, strategy_config_snapshot: { max_safety_orders: 3 } }
    expect(calculateSOLevels(pos)).toEqual([])
  })

  test('returns empty array when no max_safety_orders configured', () => {
    const pos = { ...basePosition, strategy_config_snapshot: { price_deviation: 2.0 } }
    expect(calculateSOLevels(pos)).toEqual([])
  })

  test('linear spacing — average_price reference — no fills', () => {
    const levels = calculateSOLevels(basePosition)
    expect(levels).toHaveLength(3)
    // SO1: 100 * (1 - 2%) = 98
    expect(levels[0]).toEqual({ soNumber: 1, triggerPrice: 98 })
    // SO2: 100 * (1 - 4%) = 96
    expect(levels[1]).toEqual({ soNumber: 2, triggerPrice: 96 })
    // SO3: 100 * (1 - 6%) = 94
    expect(levels[2]).toEqual({ soNumber: 3, triggerPrice: 94 })
  })

  test('skips already-filled SOs (trade_count 2 = 1 base + 1 SO fill)', () => {
    const pos = {
      ...basePosition,
      trade_count: 2,
      average_buy_price: 99,
      last_buy_price: 98,
    }
    const levels = calculateSOLevels(pos)
    expect(levels).toHaveLength(2)
    expect(levels[0].soNumber).toBe(2)
    expect(levels[1].soNumber).toBe(3)
    // Both calculated from new average_buy_price=99 at absolute SO numbers 2,3
    expect(levels[0].triggerPrice).toBeCloseTo(99 * 0.96)  // 1 - 4%
    expect(levels[1].triggerPrice).toBeCloseTo(99 * 0.94)  // 1 - 6%
  })

  test('all SOs filled returns empty array', () => {
    const pos = { ...basePosition, trade_count: 4 }  // base + 3 SOs
    expect(calculateSOLevels(pos)).toEqual([])
  })

  test('base_order reference uses first_buy_price', () => {
    const pos = {
      ...basePosition,
      trade_count: 2,
      average_buy_price: 99,
      first_buy_price: 100,
      last_buy_price: 98,
      strategy_config_snapshot: {
        ...basePosition.strategy_config_snapshot,
        dca_target_reference: 'base_order',
      },
    }
    const levels = calculateSOLevels(pos)
    expect(levels[0].soNumber).toBe(2)
    // SO2 from first_buy_price=100: total_deviation = 2*2 = 4%, trigger = 100*0.96 = 96
    expect(levels[0].triggerPrice).toBeCloseTo(96)
  })

  test('last_buy reference uses last_buy_price', () => {
    const pos = {
      ...basePosition,
      trade_count: 2,
      average_buy_price: 99,
      first_buy_price: 100,
      last_buy_price: 98,
      strategy_config_snapshot: {
        ...basePosition.strategy_config_snapshot,
        dca_target_reference: 'last_buy',
      },
    }
    const levels = calculateSOLevels(pos)
    expect(levels[0].soNumber).toBe(2)
    // SO2 from last_buy=98: total_deviation = 2*2 = 4%, trigger = 98*0.96 = 94.08
    expect(levels[0].triggerPrice).toBeCloseTo(94.08)
  })

  test('geometric step_scale — SO levels widen as orders increase', () => {
    const pos = {
      ...basePosition,
      strategy_config_snapshot: {
        price_deviation: 2.0,
        safety_order_step_scale: 1.5,
        max_safety_orders: 3,
        dca_target_reference: 'average_price',
      },
    }
    const levels = calculateSOLevels(pos)
    // SO1: dev = 2*(1.5^1-1)/(1.5-1) = 2*0.5/0.5 = 2% → 98
    expect(levels[0].triggerPrice).toBeCloseTo(98)
    // SO2: dev = 2*(1.5^2-1)/(1.5-1) = 2*1.25/0.5 = 5% → 95
    expect(levels[1].triggerPrice).toBeCloseTo(95)
    // SO3: dev = 2*(1.5^3-1)/(1.5-1) = 2*2.375/0.5 = 9.5% → 90.5
    expect(levels[2].triggerPrice).toBeCloseTo(90.5)
  })

  test('geometric step_scale levels are further apart than linear', () => {
    const linearLevels = calculateSOLevels(basePosition)
    const geomPos = {
      ...basePosition,
      strategy_config_snapshot: {
        ...basePosition.strategy_config_snapshot,
        safety_order_step_scale: 1.5,
      },
    }
    const geomLevels = calculateSOLevels(geomPos)
    // With scale > 1, SO3 trigger should be lower (further from entry) than linear
    expect(geomLevels[2].triggerPrice).toBeLessThan(linearLevels[2].triggerPrice)
  })

  test('short direction — SO levels go UP from reference', () => {
    const pos = { ...basePosition, direction: 'short' }
    const levels = calculateSOLevels(pos)
    // SO1: 100 * (1 + 2%) = 102
    expect(levels[0]).toEqual({ soNumber: 1, triggerPrice: 102 })
    // SO2: 100 * (1 + 4%) = 104
    expect(levels[1]).toEqual({ soNumber: 2, triggerPrice: 104 })
    expect(levels[2]).toEqual({ soNumber: 3, triggerPrice: 106 })
  })

  test('defaults direction to long when not set', () => {
    const pos = { ...basePosition, direction: undefined }
    const levels = calculateSOLevels(pos)
    expect(levels[0].triggerPrice).toBeLessThan(100)  // goes down for long
  })

  test('falls back to average_buy_price when first_buy_price missing for base_order ref', () => {
    const pos = {
      ...basePosition,
      first_buy_price: null,
      strategy_config_snapshot: {
        ...basePosition.strategy_config_snapshot,
        dca_target_reference: 'base_order',
      },
    }
    const levels = calculateSOLevels(pos)
    // Falls back to average_buy_price=100
    expect(levels[0].triggerPrice).toBeCloseTo(98)
  })
})
