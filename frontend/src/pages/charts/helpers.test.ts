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
} from './helpers'

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
