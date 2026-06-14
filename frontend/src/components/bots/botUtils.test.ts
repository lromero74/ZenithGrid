/**
 * Tests for botUtils.ts
 *
 * Tests pure helper functions: getDefaultFormData, convertProductsToTradingPairs,
 * isParameterVisible, POPULARITY_ORDER, DEFAULT_TRADING_PAIRS
 */

import { describe, test, expect } from 'vitest'
import {
  getDefaultFormData,
  convertProductsToTradingPairs,
  isParameterVisible,
  POPULARITY_ORDER,
  DEFAULT_TRADING_PAIRS,
  calculateSoftCeiling,
  getDCAMultiplier,
} from './botUtils'

describe('getDefaultFormData', () => {
  test('returns default values', () => {
    const data = getDefaultFormData()
    expect(data.name).toBe('')
    expect(data.strategy_type).toBe('')
    expect(data.market_type).toBe('spot')
    expect(data.exchange_type).toBe('cex')
    expect(data.product_ids).toEqual([])
    expect(data.check_interval_seconds).toBe(300)
    expect(data.split_budget_across_pairs).toBe(false)
  })

  test('returns fresh object each call', () => {
    const a = getDefaultFormData()
    const b = getDefaultFormData()
    expect(a).not.toBe(b)
    a.name = 'mutated'
    expect(b.name).toBe('')
  })
})

describe('POPULARITY_ORDER', () => {
  test('BTC is first', () => {
    expect(POPULARITY_ORDER[0]).toBe('BTC')
  })

  test('ETH is second', () => {
    expect(POPULARITY_ORDER[1]).toBe('ETH')
  })

  test('contains common coins', () => {
    expect(POPULARITY_ORDER).toContain('SOL')
    expect(POPULARITY_ORDER).toContain('DOGE')
    expect(POPULARITY_ORDER).toContain('ADA')
  })
})

describe('DEFAULT_TRADING_PAIRS', () => {
  test('includes BTC-USD', () => {
    const btcUsd = DEFAULT_TRADING_PAIRS.find((p) => p.value === 'BTC-USD')
    expect(btcUsd).toBeDefined()
    expect(btcUsd!.group).toBe('USD')
    expect(btcUsd!.base).toBe('BTC')
  })

  test('includes ETH-BTC', () => {
    const ethBtc = DEFAULT_TRADING_PAIRS.find((p) => p.value === 'ETH-BTC')
    expect(ethBtc).toBeDefined()
    expect(ethBtc!.group).toBe('BTC')
  })
})

describe('convertProductsToTradingPairs', () => {
  test('converts products to trading pairs', () => {
    const products = [
      { product_id: 'ETH-BTC', base_currency: 'ETH', quote_currency: 'BTC' },
      { product_id: 'BTC-USD', base_currency: 'BTC', quote_currency: 'USD' },
    ]
    const pairs = convertProductsToTradingPairs(products)
    expect(pairs).toHaveLength(2)
    expect(pairs[0].value).toBe('ETH-BTC') // BTC group comes first
    expect(pairs[0].group).toBe('BTC')
    expect(pairs[1].value).toBe('BTC-USD')
    expect(pairs[1].group).toBe('USD')
  })

  test('sorts by group priority then popularity', () => {
    const products = [
      { product_id: 'ADA-USD', base_currency: 'ADA', quote_currency: 'USD' },
      { product_id: 'ETH-BTC', base_currency: 'ETH', quote_currency: 'BTC' },
      { product_id: 'SOL-BTC', base_currency: 'SOL', quote_currency: 'BTC' },
    ]
    const pairs = convertProductsToTradingPairs(products)
    // BTC group first, within BTC: ETH before SOL (popularity)
    expect(pairs[0].value).toBe('ETH-BTC')
    expect(pairs[1].value).toBe('SOL-BTC')
    expect(pairs[2].value).toBe('ADA-USD')
  })

  test('handles USDT and USDC groups', () => {
    const products = [
      { product_id: 'ETH-USDT', base_currency: 'ETH', quote_currency: 'USDT' },
      { product_id: 'ETH-USDC', base_currency: 'ETH', quote_currency: 'USDC' },
    ]
    const pairs = convertProductsToTradingPairs(products)
    expect(pairs[0].group).toBe('USDC') // USDC before USDT
    expect(pairs[1].group).toBe('USDT')
  })

  test('handles empty array', () => {
    expect(convertProductsToTradingPairs([])).toEqual([])
  })

  test('unlisted coins sort alphabetically', () => {
    const products = [
      { product_id: 'ZZZ-BTC', base_currency: 'ZZZ', quote_currency: 'BTC' },
      { product_id: 'AAA-BTC', base_currency: 'AAA', quote_currency: 'BTC' },
    ]
    const pairs = convertProductsToTradingPairs(products)
    expect(pairs[0].base).toBe('AAA')
    expect(pairs[1].base).toBe('ZZZ')
  })
})

describe('isParameterVisible', () => {
  test('returns true when no visible_when', () => {
    const param = { key: 'test', name: 'Test', type: 'number' } as any
    expect(isParameterVisible(param, {})).toBe(true)
  })

  test('returns true when conditions met', () => {
    const param = {
      key: 'test',
      name: 'Test',
      type: 'number',
      visible_when: { mode: 'advanced' },
    } as any
    expect(isParameterVisible(param, { mode: 'advanced' })).toBe(true)
  })

  test('returns false when conditions not met', () => {
    const param = {
      key: 'test',
      name: 'Test',
      type: 'number',
      visible_when: { mode: 'advanced' },
    } as any
    expect(isParameterVisible(param, { mode: 'simple' })).toBe(false)
  })

  test('checks multiple conditions', () => {
    const param = {
      key: 'test',
      name: 'Test',
      type: 'number',
      visible_when: { mode: 'advanced', enabled: true },
    } as any
    expect(isParameterVisible(param, { mode: 'advanced', enabled: true })).toBe(true)
    expect(isParameterVisible(param, { mode: 'advanced', enabled: false })).toBe(false)
  })
})

describe('calculateSoftCeiling', () => {
  // A fixed-mode config: multiplier = base(1) + SO1(1) = 2.0 with 1 safety order.
  const config = {
    safety_order_type: 'fixed',
    max_safety_orders: 1,
    safety_order_volume_scale: 1.0,
  }

  test('happy path: ceiling = floor(budget / (min × multiplier)), clamped to max', () => {
    // budget = 1000 × 50% = 500; multiplier = 2.0; min = 50 → floor(500/100) = 5
    const result = calculateSoftCeiling(config, 1000, 50, 50, 20)
    expect(result).toBe(5)
  })

  test('clamps to maxConcurrentDeals when budget allows more', () => {
    // budget = 100000 × 100% = 100000; min = 1; mult = 2 → 50000, clamped to 20
    expect(calculateSoftCeiling(config, 100000, 100, 1, 20)).toBe(20)
  })

  test('edge: tiny budget floors to at least 1', () => {
    // budget = 10 × 15% = 1.5; min = 1; mult = 2 → floor(0.75) = 0 → max(1, 0) = 1
    expect(calculateSoftCeiling(config, 10, 15, 1, 20)).toBe(1)
  })

  test('failure/guard: worstCaseMin = 0 is not computable → null (never Infinity/max)', () => {
    // Previously: budget/0 = Infinity → clamped to maxConcurrentDeals (e.g. 20).
    // A zero/unknown minimum means we cannot compute a budget-based ceiling.
    expect(calculateSoftCeiling(config, 1000, 50, 0, 20)).toBeNull()
  })

  test('guard: negative worstCaseMin is not computable → null', () => {
    expect(calculateSoftCeiling(config, 1000, 50, -1, 20)).toBeNull()
  })
})

describe('getDCAMultiplier (parity with backend get_total_multiplier)', () => {
  // Expected values are computed by hand from the backend formula in
  // backend/app/strategies/safety_order_calculator.py::get_total_multiplier.
  // This is the one authoritative DCA-multiplier formula; the TS copy must match
  // it (soft-ceiling sizing drift between the two has caused real bugs).

  test('no safety orders → 1.0', () => {
    expect(getDCAMultiplier({ max_safety_orders: 0 })).toBe(1.0)
  })

  test('percentage_of_base, scale 1, 50% of base, 2 SOs → 1 + 0.5*2 = 2.0', () => {
    expect(getDCAMultiplier({
      max_safety_orders: 2, safety_order_volume_scale: 1.0,
      safety_order_type: 'percentage_of_base', safety_order_percentage: 50,
    })).toBeCloseTo(2.0, 6)
  })

  test('percentage_of_base, scale 1, 100% of base, 5 SOs → 1 + 1*5 = 6.0', () => {
    expect(getDCAMultiplier({
      max_safety_orders: 5, safety_order_volume_scale: 1.0,
      safety_order_type: 'percentage_of_base', safety_order_percentage: 100,
    })).toBeCloseTo(6.0, 6)
  })

  test('percentage_of_base, scale 1.62, 100%, 2 SOs → 1 + (1.62^2-1)/0.62 = 3.62', () => {
    expect(getDCAMultiplier({
      max_safety_orders: 2, safety_order_volume_scale: 1.62,
      safety_order_type: 'percentage_of_base', safety_order_percentage: 100,
    })).toBeCloseTo(3.62, 2)
  })

  test('fixed, scale 1, 1 SO → 2.0', () => {
    expect(getDCAMultiplier({
      max_safety_orders: 1, safety_order_volume_scale: 1.0, safety_order_type: 'fixed',
    })).toBeCloseTo(2.0, 6)
  })

  test('fixed, scale 1, 5 SOs → 2 + 4 = 6.0', () => {
    expect(getDCAMultiplier({
      max_safety_orders: 5, safety_order_volume_scale: 1.0, safety_order_type: 'fixed',
    })).toBeCloseTo(6.0, 6)
  })

  test('fixed, scale 2, 5 SOs → 2 + 2*(2^4-1)/1 = 32.0', () => {
    expect(getDCAMultiplier({
      max_safety_orders: 5, safety_order_volume_scale: 2.0, safety_order_type: 'fixed',
    })).toBeCloseTo(32.0, 6)
  })
})
