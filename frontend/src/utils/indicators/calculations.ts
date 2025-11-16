// Technical indicator calculation functions
import type { CandleData, MACDResult, BollingerBandsResult, StochasticResult } from './types'

/**
 * Calculate Simple Moving Average (SMA)
 * @param data Array of price values
 * @param period Number of periods for the moving average
 * @returns Array of SMA values (null for insufficient data points)
 */
export function calculateSMA(data: number[], period: number): (number | null)[] {
  const result: (number | null)[] = []
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(null)
    } else {
      const sum = data.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0)
      result.push(sum / period)
    }
  }
  return result
}

/**
 * Calculate Exponential Moving Average (EMA)
 * @param data Array of price values
 * @param period Number of periods for the moving average
 * @returns Array of EMA values (null for insufficient data points)
 */
export function calculateEMA(data: number[], period: number): (number | null)[] {
  const result: (number | null)[] = []
  const multiplier = 2 / (period + 1)

  if (data.length < period) return data.map(() => null)

  const initialSMA = data.slice(0, period).reduce((a, b) => a + b, 0) / period
  for (let i = 0; i < period - 1; i++) {
    result.push(null)
  }

  let ema = initialSMA
  result[period - 1] = ema

  for (let i = period; i < data.length; i++) {
    ema = (data[i] - ema) * multiplier + ema
    result.push(ema)
  }

  return result
}

/**
 * Calculate Relative Strength Index (RSI)
 * @param data Array of price values
 * @param period Number of periods (default: 14)
 * @returns Array of RSI values (null for insufficient data points)
 */
export function calculateRSI(data: number[], period: number = 14): (number | null)[] {
  const result: (number | null)[] = []

  if (data.length < period + 1) {
    return data.map(() => null)
  }

  const changes: number[] = []
  for (let i = 1; i < data.length; i++) {
    changes.push(data[i] - data[i - 1])
  }

  const gains = changes.map(c => c > 0 ? c : 0)
  const losses = changes.map(c => c < 0 ? -c : 0)

  let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period
  let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period

  result.push(null) // First value
  for (let i = 0; i < period; i++) {
    result.push(null)
  }

  for (let i = period; i < changes.length; i++) {
    if (avgLoss === 0) {
      result.push(100)
    } else {
      const rs = avgGain / avgLoss
      const rsi = 100 - (100 / (1 + rs))
      result.push(rsi)
    }

    avgGain = (avgGain * (period - 1) + gains[i]) / period
    avgLoss = (avgLoss * (period - 1) + losses[i]) / period
  }

  return result
}

/**
 * Calculate MACD (Moving Average Convergence Divergence)
 * @param data Array of price values
 * @param fastPeriod Fast EMA period (default: 12)
 * @param slowPeriod Slow EMA period (default: 26)
 * @param signalPeriod Signal line period (default: 9)
 * @returns Object containing MACD line, signal line, and histogram
 */
export function calculateMACD(
  data: number[],
  fastPeriod: number = 12,
  slowPeriod: number = 26,
  signalPeriod: number = 9
): MACDResult {
  const fastEMA = calculateEMA(data, fastPeriod)
  const slowEMA = calculateEMA(data, slowPeriod)

  const macdLine: (number | null)[] = []
  for (let i = 0; i < data.length; i++) {
    if (fastEMA[i] !== null && slowEMA[i] !== null) {
      macdLine.push(fastEMA[i]! - slowEMA[i]!)
    } else {
      macdLine.push(null)
    }
  }

  const macdValues = macdLine.filter(v => v !== null) as number[]
  const signalEMA = calculateEMA(macdValues, signalPeriod)

  const signalLine: (number | null)[] = []
  let signalIndex = 0
  for (let i = 0; i < macdLine.length; i++) {
    if (macdLine[i] !== null) {
      signalLine.push(signalEMA[signalIndex] ?? null)
      signalIndex++
    } else {
      signalLine.push(null)
    }
  }

  const histogram: (number | null)[] = []
  for (let i = 0; i < macdLine.length; i++) {
    if (macdLine[i] !== null && signalLine[i] !== null) {
      histogram.push(macdLine[i]! - signalLine[i]!)
    } else {
      histogram.push(null)
    }
  }

  return { macd: macdLine, signal: signalLine, histogram }
}

/**
 * Calculate Bollinger Bands
 * @param data Array of price values
 * @param period Number of periods (default: 20)
 * @param stdDev Number of standard deviations (default: 2)
 * @returns Object containing upper, middle, and lower bands
 */
export function calculateBollingerBands(
  data: number[],
  period: number = 20,
  stdDev: number = 2
): BollingerBandsResult {
  const middle = calculateSMA(data, period)
  const upper: (number | null)[] = []
  const lower: (number | null)[] = []

  for (let i = 0; i < data.length; i++) {
    if (i < period - 1 || middle[i] === null) {
      upper.push(null)
      lower.push(null)
    } else {
      const subset = data.slice(i - period + 1, i + 1)
      const mean = middle[i]!
      const variance = subset.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / period
      const std = Math.sqrt(variance)
      upper.push(mean + stdDev * std)
      lower.push(mean - stdDev * std)
    }
  }

  return { upper, middle, lower }
}

/**
 * Calculate Stochastic Oscillator
 * @param highs Array of high prices
 * @param lows Array of low prices
 * @param closes Array of close prices
 * @param kPeriod %K period (default: 14)
 * @param dPeriod %D period (default: 3)
 * @returns Object containing %K and %D lines
 */
export function calculateStochastic(
  highs: number[],
  lows: number[],
  closes: number[],
  kPeriod: number = 14,
  dPeriod: number = 3
): StochasticResult {
  const kLine: (number | null)[] = []

  for (let i = 0; i < closes.length; i++) {
    if (i < kPeriod - 1) {
      kLine.push(null)
    } else {
      const highestHigh = Math.max(...highs.slice(i - kPeriod + 1, i + 1))
      const lowestLow = Math.min(...lows.slice(i - kPeriod + 1, i + 1))
      const currentClose = closes[i]

      if (highestHigh === lowestLow) {
        kLine.push(50)
      } else {
        const k = ((currentClose - lowestLow) / (highestHigh - lowestLow)) * 100
        kLine.push(k)
      }
    }
  }

  const kValues = kLine.filter(v => v !== null) as number[]
  const dSMA = calculateSMA(kValues, dPeriod)

  const dLine: (number | null)[] = []
  let dIndex = 0
  for (let i = 0; i < kLine.length; i++) {
    if (kLine[i] !== null && i >= kPeriod - 1 + dPeriod - 1) {
      dLine.push(dSMA[dIndex] ?? null)
      dIndex++
    } else {
      dLine.push(null)
    }
  }

  return { k: kLine, d: dLine }
}

/**
 * Calculate Heikin-Ashi candles from regular candles
 * @param candles Array of regular candlestick data
 * @returns Array of Heikin-Ashi candlestick data
 */
export function calculateHeikinAshi(candles: CandleData[]): CandleData[] {
  if (candles.length === 0) return []

  const haCandles: CandleData[] = []
  let prevHAOpen = candles[0].open
  let prevHAClose = candles[0].close

  candles.forEach((candle, i) => {
    // HA Close = (Open + High + Low + Close) / 4
    const haClose = (candle.open + candle.high + candle.low + candle.close) / 4

    // HA Open = (Previous HA Open + Previous HA Close) / 2
    const haOpen = i === 0 ? (candle.open + candle.close) / 2 : (prevHAOpen + prevHAClose) / 2

    // HA High = Max(High, HA Open, HA Close)
    const haHigh = Math.max(candle.high, haOpen, haClose)

    // HA Low = Min(Low, HA Open, HA Close)
    const haLow = Math.min(candle.low, haOpen, haClose)

    haCandles.push({
      time: candle.time,
      open: haOpen,
      high: haHigh,
      low: haLow,
      close: haClose,
      volume: candle.volume
    })

    prevHAOpen = haOpen
    prevHAClose = haClose
  })

  return haCandles
}
