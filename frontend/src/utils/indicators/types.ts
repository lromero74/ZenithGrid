// Indicator type definitions

export interface CandleData {
  time: string | number
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

export interface IndicatorSettings {
  period?: number
  color?: string
  overbought?: number
  oversold?: number
  fastPeriod?: number
  slowPeriod?: number
  signalPeriod?: number
  macdColor?: string
  signalColor?: string
  histogramColor?: string
  stdDev?: number
  upperColor?: string
  middleColor?: string
  lowerColor?: string
  kPeriod?: number
  dPeriod?: number
  kColor?: string
  dColor?: string
}

export interface IndicatorDefinition {
  id: string
  name: string
  category: string
  defaultSettings: IndicatorSettings
}

export interface MACDResult {
  macd: (number | null)[]
  signal: (number | null)[]
  histogram: (number | null)[]
}

export interface BollingerBandsResult {
  upper: (number | null)[]
  middle: (number | null)[]
  lower: (number | null)[]
}

export interface StochasticResult {
  k: (number | null)[]
  d: (number | null)[]
}
