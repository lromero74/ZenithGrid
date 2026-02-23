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
