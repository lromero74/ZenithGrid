import type { CandleData } from './types'
import type { Time } from 'lightweight-charts'
import {
  calculateSMA,
  calculateEMA,
  calculateRSI,
  calculateMACD,
  calculateBollingerBands,
  calculateStochastic,
  calculateHeikinAshi,
} from './calculations'

// ── SMA ──────────────────────────────────────────────────────────────

describe('calculateSMA', () => {
  test('happy path with known values', () => {
    const data = [2, 4, 6, 8, 10]
    const result = calculateSMA(data, 3)
    // First 2 values null, then averages of 3-element windows
    expect(result).toEqual([null, null, 4, 6, 8])
  })

  test('period equals data length returns single value', () => {
    const data = [10, 20, 30]
    const result = calculateSMA(data, 3)
    expect(result).toEqual([null, null, 20])
  })

  test('period of 1 returns original data', () => {
    const data = [5, 10, 15]
    const result = calculateSMA(data, 1)
    expect(result).toEqual([5, 10, 15])
  })

  test('period greater than data length returns all nulls', () => {
    const data = [1, 2]
    const result = calculateSMA(data, 5)
    expect(result).toEqual([null, null])
  })

  test('empty array returns empty array', () => {
    expect(calculateSMA([], 3)).toEqual([])
  })
})

// ── EMA ──────────────────────────────────────────────────────────────

describe('calculateEMA', () => {
  test('happy path returns non-null values after period', () => {
    const data = [22, 24, 23, 25, 26, 28, 27, 29, 30, 28]
    const result = calculateEMA(data, 5)
    // First 4 should be null, 5th is SMA seed
    for (let i = 0; i < 4; i++) expect(result[i]).toBeNull()
    expect(result[4]).toBeCloseTo(24) // SMA of first 5: (22+24+23+25+26)/5 = 24
    // Subsequent values use EMA formula
    expect(result[5]).not.toBeNull()
  })

  test('insufficient data returns all nulls', () => {
    const data = [1, 2, 3]
    const result = calculateEMA(data, 5)
    expect(result).toEqual([null, null, null])
  })

  test('EMA seed equals SMA of first period values', () => {
    const data = [10, 20, 30, 40, 50]
    const result = calculateEMA(data, 3)
    // SMA of first 3: (10+20+30)/3 = 20
    expect(result[2]).toBeCloseTo(20)
  })

  test('single element with period 1', () => {
    const data = [42]
    const result = calculateEMA(data, 1)
    expect(result[0]).toBeCloseTo(42)
  })
})

// ── RSI ──────────────────────────────────────────────────────────────

describe('calculateRSI', () => {
  test('happy path with rising then falling prices', () => {
    // 16 values = 15 changes, period 14 → first RSI at index 15
    const data = [44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
      45.89, 46.03, 45.61, 46.28, 46.28, 46.00]
    const result = calculateRSI(data, 14)
    // First period+1 values should be null
    for (let i = 0; i <= 14; i++) expect(result[i]).toBeNull()
    // RSI should be a number between 0 and 100
    const rsiValue = result[15]
    expect(rsiValue).not.toBeNull()
    expect(rsiValue).toBeGreaterThanOrEqual(0)
    expect(rsiValue).toBeLessThanOrEqual(100)
  })

  test('all gains returns RSI of 100', () => {
    // Steadily increasing prices: all changes are positive
    const data = Array.from({ length: 20 }, (_, i) => 100 + i)
    const result = calculateRSI(data, 14)
    const firstRSI = result.find(v => v !== null)
    expect(firstRSI).toBe(100)
  })

  test('all losses returns RSI near 0', () => {
    // Steadily decreasing prices: all changes are negative
    const data = Array.from({ length: 20 }, (_, i) => 100 - i)
    const result = calculateRSI(data, 14)
    // First non-null RSI — avgGain is 0, avgLoss > 0
    // RS = 0/avgLoss = 0, RSI = 100 - 100/(1+0) = 0
    const nonNullValues = result.filter(v => v !== null) as number[]
    expect(nonNullValues[0]).toBeCloseTo(0, 0)
  })

  test('insufficient data returns all nulls', () => {
    const data = [1, 2, 3]
    const result = calculateRSI(data, 14)
    expect(result.every(v => v === null)).toBe(true)
  })
})

// ── MACD ─────────────────────────────────────────────────────────────

describe('calculateMACD', () => {
  test('MACD line equals fast EMA minus slow EMA', () => {
    // Generate enough data for default MACD (12, 26, 9) — need 26+ points
    const data = Array.from({ length: 40 }, (_, i) => 100 + Math.sin(i / 3) * 10)
    const result = calculateMACD(data)

    const fastEMA = calculateEMA(data, 12)
    const slowEMA = calculateEMA(data, 26)

    // Where both EMAs are non-null, MACD should equal their difference
    for (let i = 0; i < data.length; i++) {
      if (fastEMA[i] !== null && slowEMA[i] !== null) {
        expect(result.macd[i]).toBeCloseTo(fastEMA[i]! - slowEMA[i]!)
      } else {
        expect(result.macd[i]).toBeNull()
      }
    }
  })

  test('histogram equals MACD minus signal', () => {
    const data = Array.from({ length: 50 }, (_, i) => 100 + Math.sin(i / 3) * 10)
    const result = calculateMACD(data)

    for (let i = 0; i < data.length; i++) {
      if (result.macd[i] !== null && result.signal[i] !== null) {
        expect(result.histogram[i]).toBeCloseTo(result.macd[i]! - result.signal[i]!)
      }
    }
  })

  test('short data returns mostly nulls', () => {
    const data = [1, 2, 3, 4, 5]
    const result = calculateMACD(data)
    expect(result.macd.every(v => v === null)).toBe(true)
    expect(result.signal.every(v => v === null)).toBe(true)
    expect(result.histogram.every(v => v === null)).toBe(true)
  })

  test('returns macd, signal, and histogram arrays of correct length', () => {
    const data = Array.from({ length: 50 }, (_, i) => 100 + i)
    const result = calculateMACD(data)
    expect(result.macd).toHaveLength(50)
    expect(result.signal).toHaveLength(50)
    expect(result.histogram).toHaveLength(50)
  })
})

// ── Bollinger Bands ──────────────────────────────────────────────────

describe('calculateBollingerBands', () => {
  test('middle band equals SMA', () => {
    const data = Array.from({ length: 30 }, (_, i) => 100 + i)
    const result = calculateBollingerBands(data, 20, 2)
    const sma = calculateSMA(data, 20)

    for (let i = 0; i < data.length; i++) {
      if (sma[i] !== null) {
        expect(result.middle[i]).toBeCloseTo(sma[i]!)
      }
    }
  })

  test('all same values collapses bands to middle', () => {
    const data = Array(25).fill(100)
    const result = calculateBollingerBands(data, 20, 2)

    // Where bands are non-null, std dev = 0, so upper = middle = lower
    for (let i = 19; i < data.length; i++) {
      expect(result.upper[i]).toBeCloseTo(100)
      expect(result.middle[i]).toBeCloseTo(100)
      expect(result.lower[i]).toBeCloseTo(100)
    }
  })

  test('upper > middle > lower for varying data', () => {
    const data = [10, 20, 30, 10, 20, 30, 10, 20, 30, 10]
    const result = calculateBollingerBands(data, 5, 2)

    for (let i = 0; i < data.length; i++) {
      if (result.upper[i] !== null) {
        expect(result.upper[i]!).toBeGreaterThan(result.middle[i]!)
        expect(result.middle[i]!).toBeGreaterThan(result.lower[i]!)
      }
    }
  })

  test('first period-1 values are null', () => {
    const data = Array.from({ length: 10 }, (_, i) => i + 1)
    const result = calculateBollingerBands(data, 5, 2)
    for (let i = 0; i < 4; i++) {
      expect(result.upper[i]).toBeNull()
      expect(result.middle[i]).toBeNull()
      expect(result.lower[i]).toBeNull()
    }
  })
})

// ── Stochastic Oscillator ────────────────────────────────────────────

describe('calculateStochastic', () => {
  test('happy path returns %K between 0 and 100', () => {
    const highs = [130, 132, 131, 133, 135, 134, 136, 138, 137, 139, 140, 141, 142, 143, 144, 145]
    const lows = [120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135]
    const closes = [125, 128, 127, 130, 132, 131, 133, 135, 134, 136, 137, 138, 139, 140, 141, 142]
    const result = calculateStochastic(highs, lows, closes, 14, 3)

    const kValues = result.k.filter(v => v !== null) as number[]
    kValues.forEach(v => {
      expect(v).toBeGreaterThanOrEqual(0)
      expect(v).toBeLessThanOrEqual(100)
    })
  })

  test('flat market returns %K of 50', () => {
    // All highs = lows = closes → highestHigh === lowestLow → returns 50
    const flat = Array(20).fill(100)
    const result = calculateStochastic(flat, flat, flat, 14, 3)

    const kValues = result.k.filter(v => v !== null) as number[]
    kValues.forEach(v => expect(v).toBe(50))
  })

  test('close at highest high returns %K of 100', () => {
    // When close equals the highest high in the lookback period
    const highs = Array(20).fill(100)
    const lows = Array(20).fill(50)
    const closes = Array(20).fill(100)
    const result = calculateStochastic(highs, lows, closes, 14, 3)

    const kValues = result.k.filter(v => v !== null) as number[]
    kValues.forEach(v => expect(v).toBe(100))
  })

  test('first kPeriod-1 values are null', () => {
    const data = Array.from({ length: 20 }, (_, i) => i + 100)
    const result = calculateStochastic(data, data, data, 14, 3)
    for (let i = 0; i < 13; i++) {
      expect(result.k[i]).toBeNull()
    }
  })
})

// ── Heikin-Ashi ──────────────────────────────────────────────────────

describe('calculateHeikinAshi', () => {
  const mkCandle = (o: number, h: number, l: number, c: number, t: number): CandleData => ({
    time: t as Time,
    open: o, high: h, low: l, close: c, volume: 100,
  })

  test('happy path verifies HA formulas', () => {
    const candles: CandleData[] = [
      mkCandle(100, 110, 90, 105, 1),
      mkCandle(106, 115, 95, 112, 2),
    ]
    const result = calculateHeikinAshi(candles)

    // First candle
    const ha0Close = (100 + 110 + 90 + 105) / 4 // 101.25
    const ha0Open = (100 + 105) / 2 // 102.5
    const ha0High = Math.max(110, ha0Open, ha0Close) // 110
    const ha0Low = Math.min(90, ha0Open, ha0Close) // 90
    expect(result[0].close).toBeCloseTo(ha0Close)
    expect(result[0].open).toBeCloseTo(ha0Open)
    expect(result[0].high).toBeCloseTo(ha0High)
    expect(result[0].low).toBeCloseTo(ha0Low)

    // Second candle uses previous HA open/close
    const ha1Close = (106 + 115 + 95 + 112) / 4 // 107
    const ha1Open = (ha0Open + ha0Close) / 2 // (102.5 + 101.25) / 2 = 101.875
    const ha1High = Math.max(115, ha1Open, ha1Close) // 115
    const ha1Low = Math.min(95, ha1Open, ha1Close) // 95
    expect(result[1].close).toBeCloseTo(ha1Close)
    expect(result[1].open).toBeCloseTo(ha1Open)
    expect(result[1].high).toBeCloseTo(ha1High)
    expect(result[1].low).toBeCloseTo(ha1Low)
  })

  test('empty array returns empty array', () => {
    expect(calculateHeikinAshi([])).toEqual([])
  })

  test('single candle', () => {
    const candles = [mkCandle(100, 110, 90, 105, 1)]
    const result = calculateHeikinAshi(candles)
    expect(result).toHaveLength(1)
    expect(result[0].close).toBeCloseTo((100 + 110 + 90 + 105) / 4)
    expect(result[0].open).toBeCloseTo((100 + 105) / 2)
  })

  test('preserves time and volume', () => {
    const candles = [mkCandle(100, 110, 90, 105, 1000)]
    const result = calculateHeikinAshi(candles)
    expect(result[0].time).toBe(1000)
    expect(result[0].volume).toBe(100)
  })

  test('output length matches input length', () => {
    const candles = Array.from({ length: 10 }, (_, i) =>
      mkCandle(100 + i, 110 + i, 90 + i, 105 + i, i)
    )
    expect(calculateHeikinAshi(candles)).toHaveLength(10)
  })
})
