/**
 * Tests for pages/charts/helpers.ts
 *
 * Tests pure chart helper functions (no lightweight-charts runtime needed).
 */

import { describe, test, expect } from 'vitest'
import {
  getPriceFormat,
  isBTCPair,
  transformPriceData,
  transformVolumeData,
  extractCandleValues,
  filterIndicators,
  groupIndicatorsByCategory,
} from './helpers'
import { AVAILABLE_INDICATORS } from '../../utils/indicators'

describe('getPriceFormat', () => {
  test('returns 8 decimal precision for BTC pairs', () => {
    const format = getPriceFormat('ETH-BTC')
    expect(format.precision).toBe(8)
    expect(format.minMove).toBe(0.00000001)
  })

  test('returns 2 decimal precision for USD pairs', () => {
    const format = getPriceFormat('BTC-USD')
    expect(format.precision).toBe(2)
    expect(format.minMove).toBe(0.01)
  })

  test('returns 2 decimal for non-BTC pairs', () => {
    const format = getPriceFormat('ETH-USDT')
    expect(format.precision).toBe(2)
  })

  test('type is always "price"', () => {
    expect(getPriceFormat('ETH-BTC').type).toBe('price')
    expect(getPriceFormat('BTC-USD').type).toBe('price')
  })
})

describe('isBTCPair', () => {
  test('returns true for BTC pairs', () => {
    expect(isBTCPair('ETH-BTC')).toBe(true)
    expect(isBTCPair('SOL-BTC')).toBe(true)
  })

  test('returns false for USD pairs', () => {
    expect(isBTCPair('BTC-USD')).toBe(false)
    expect(isBTCPair('ETH-USD')).toBe(false)
  })

  test('returns false for USDT pairs', () => {
    expect(isBTCPair('BTC-USDT')).toBe(false)
  })

  test('handles edge case: "BTC" without suffix', () => {
    expect(isBTCPair('BTC')).toBe(false)
  })
})

describe('transformPriceData', () => {
  const candles = [
    { time: 1000, open: 100, high: 110, low: 90, close: 105, volume: 500 },
    { time: 2000, open: 105, high: 115, low: 95, close: 110, volume: 600 },
  ] as any[]

  test('transforms for candlestick chart', () => {
    const data = transformPriceData(candles, 'candlestick')
    expect(data[0]).toEqual({ time: 1000, open: 100, high: 110, low: 90, close: 105 })
  })

  test('transforms for bar chart', () => {
    const data = transformPriceData(candles, 'bar')
    expect(data[0]).toHaveProperty('open')
    expect(data[0]).toHaveProperty('high')
  })

  test('transforms for line chart', () => {
    const data = transformPriceData(candles, 'line')
    expect(data[0]).toEqual({ time: 1000, value: 105 })
    expect(data[0]).not.toHaveProperty('open')
  })

  test('transforms for baseline chart', () => {
    const data = transformPriceData(candles, 'baseline')
    expect(data[0]).toEqual({ time: 1000, value: 105 })
  })

  test('transforms for area chart', () => {
    const data = transformPriceData(candles, 'area')
    expect(data[0]).toEqual({ time: 1000, value: 105 })
  })

  test('handles empty candles array', () => {
    expect(transformPriceData([], 'candlestick')).toEqual([])
    expect(transformPriceData([], 'line')).toEqual([])
  })

  test('unknown chart type defaults to value-based (line/area)', () => {
    const data = transformPriceData(candles, 'unknown_type')
    expect(data[0]).toEqual({ time: 1000, value: 105 })
    expect(data[0]).not.toHaveProperty('open')
  })
})

describe('transformVolumeData', () => {
  test('assigns green for up candles', () => {
    const candles = [
      { time: 1000, open: 100, high: 110, low: 90, close: 105, volume: 500 },
    ] as any[]
    const data = transformVolumeData(candles)
    expect(data[0].value).toBe(500)
    expect(data[0].color).toBe('#10b98180') // green (close >= open)
  })

  test('assigns red for down candles', () => {
    const candles = [
      { time: 1000, open: 110, high: 115, low: 95, close: 100, volume: 400 },
    ] as any[]
    const data = transformVolumeData(candles)
    expect(data[0].color).toBe('#ef444480') // red (close < open)
  })

  test('assigns green for doji (close == open)', () => {
    const candles = [
      { time: 1000, open: 100, high: 105, low: 95, close: 100, volume: 300 },
    ] as any[]
    const data = transformVolumeData(candles)
    expect(data[0].color).toBe('#10b98180') // green (close >= open)
  })

  test('handles empty candles', () => {
    expect(transformVolumeData([])).toEqual([])
  })
})

describe('extractCandleValues', () => {
  test('extracts close, high, low arrays', () => {
    const candles = [
      { time: 1, open: 1, high: 3, low: 0.5, close: 2, volume: 100 },
      { time: 2, open: 2, high: 4, low: 1, close: 3, volume: 200 },
    ] as any[]
    const { closes, highs, lows } = extractCandleValues(candles)
    expect(closes).toEqual([2, 3])
    expect(highs).toEqual([3, 4])
    expect(lows).toEqual([0.5, 1])
  })

  test('handles empty array', () => {
    const { closes, highs, lows } = extractCandleValues([])
    expect(closes).toEqual([])
    expect(highs).toEqual([])
    expect(lows).toEqual([])
  })
})

describe('filterIndicators', () => {
  test('returns all indicators for empty search', () => {
    const result = filterIndicators('')
    expect(result.length).toBe(AVAILABLE_INDICATORS.length)
  })

  test('filters by indicator name (case-insensitive)', () => {
    const result = filterIndicators('rsi')
    expect(result.length).toBeGreaterThanOrEqual(1)
    expect(result.some(ind => ind.id === 'rsi')).toBe(true)
  })

  test('filters by category', () => {
    const result = filterIndicators('oscillator')
    expect(result.length).toBeGreaterThanOrEqual(1)
    result.forEach(ind => {
      expect(ind.category.toLowerCase()).toContain('oscillator')
    })
  })

  test('returns empty array for non-matching search', () => {
    const result = filterIndicators('zzzznonexistent')
    expect(result).toEqual([])
  })

  test('matches partial name', () => {
    const result = filterIndicators('moving')
    expect(result.length).toBeGreaterThanOrEqual(2)
    // SMA and EMA should both match
    const ids = result.map(ind => ind.id)
    expect(ids).toContain('sma')
    expect(ids).toContain('ema')
  })

  test('case-insensitive matching', () => {
    const upper = filterIndicators('MACD')
    const lower = filterIndicators('macd')
    expect(upper.length).toBe(lower.length)
    expect(upper.length).toBeGreaterThanOrEqual(1)
  })
})

describe('groupIndicatorsByCategory', () => {
  test('groups all available indicators by category', () => {
    const grouped = groupIndicatorsByCategory(AVAILABLE_INDICATORS)
    // Should have at least Moving Averages and Oscillators
    expect(grouped).toHaveProperty('Moving Averages')
    expect(grouped).toHaveProperty('Oscillators')
  })

  test('each category contains the correct indicators', () => {
    const grouped = groupIndicatorsByCategory(AVAILABLE_INDICATORS)
    const maIds = grouped['Moving Averages'].map(ind => ind.id)
    expect(maIds).toContain('sma')
    expect(maIds).toContain('ema')
  })

  test('total indicators across all groups equals input length', () => {
    const grouped = groupIndicatorsByCategory(AVAILABLE_INDICATORS)
    const totalCount = Object.values(grouped).reduce((sum, arr) => sum + arr.length, 0)
    expect(totalCount).toBe(AVAILABLE_INDICATORS.length)
  })

  test('handles empty array', () => {
    const grouped = groupIndicatorsByCategory([])
    expect(Object.keys(grouped)).toHaveLength(0)
  })

  test('handles single indicator', () => {
    const single = [AVAILABLE_INDICATORS[0]]
    const grouped = groupIndicatorsByCategory(single)
    expect(Object.keys(grouped)).toHaveLength(1)
    expect(Object.values(grouped)[0]).toHaveLength(1)
  })
})
