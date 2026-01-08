import { Time } from 'lightweight-charts'
import { AVAILABLE_INDICATORS, type CandleData } from '../../utils/indicators'

/**
 * Determine price format based on trading pair.
 * BTC pairs need higher precision (8 decimals) vs USD pairs (2 decimals).
 */
export function getPriceFormat(selectedPair: string) {
  const isBTCPair = selectedPair.endsWith('-BTC')
  return isBTCPair
    ? { type: 'price' as const, precision: 8, minMove: 0.00000001 }
    : { type: 'price' as const, precision: 2, minMove: 0.01 }
}

/**
 * Check if a trading pair is a BTC-denominated pair.
 */
export function isBTCPair(pair: string): boolean {
  return pair.endsWith('-BTC')
}

/**
 * Transform candle data into chart-ready price data based on chart type.
 */
export function transformPriceData(displayCandles: CandleData[], chartType: string) {
  return displayCandles.map((c) => {
    if (chartType === 'candlestick' || chartType === 'bar') {
      return {
        time: c.time as Time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }
    } else if (chartType === 'baseline') {
      return {
        time: c.time as Time,
        value: c.close,
      }
    } else {
      // line, area
      return {
        time: c.time as Time,
        value: c.close,
      }
    }
  })
}

/**
 * Transform candle data into volume histogram data.
 */
export function transformVolumeData(displayCandles: CandleData[]) {
  return displayCandles.map((c) => ({
    time: c.time as Time,
    value: c.volume,
    color: c.close >= c.open ? '#10b98180' : '#ef444480',
  }))
}

/**
 * Extract close, high, and low price arrays from candle data.
 * Used for indicator calculations.
 */
export function extractCandleValues(candles: CandleData[]) {
  return {
    closes: candles.map(c => c.close),
    highs: candles.map(c => c.high),
    lows: candles.map(c => c.low),
  }
}

/**
 * Filter indicators by search term (matches name or category).
 */
export function filterIndicators(indicatorSearch: string) {
  return AVAILABLE_INDICATORS.filter(ind =>
    ind.name.toLowerCase().includes(indicatorSearch.toLowerCase()) ||
    ind.category.toLowerCase().includes(indicatorSearch.toLowerCase())
  )
}

/**
 * Group indicators by category for display in the add indicator modal.
 */
export function groupIndicatorsByCategory(indicators: typeof AVAILABLE_INDICATORS) {
  return indicators.reduce((acc, ind) => {
    if (!acc[ind.category]) acc[ind.category] = []
    acc[ind.category].push(ind)
    return acc
  }, {} as Record<string, typeof AVAILABLE_INDICATORS>)
}
