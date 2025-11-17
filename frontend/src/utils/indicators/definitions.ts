// Available technical indicators with their default settings
import type { IndicatorDefinition } from './types'

export const AVAILABLE_INDICATORS: IndicatorDefinition[] = [
  {
    id: 'sma',
    name: 'Simple Moving Average (SMA)',
    description: 'Smooths price data by calculating average over a period',
    category: 'Moving Averages',
    defaultSettings: { period: 20, color: '#FF9800' }
  },
  {
    id: 'ema',
    name: 'Exponential Moving Average (EMA)',
    description: 'Weighted moving average giving more importance to recent prices',
    category: 'Moving Averages',
    defaultSettings: { period: 12, color: '#9C27B0' }
  },
  {
    id: 'rsi',
    name: 'Relative Strength Index (RSI)',
    description: 'Momentum oscillator measuring speed and magnitude of price changes (0-100)',
    category: 'Oscillators',
    defaultSettings: { period: 14, overbought: 70, oversold: 30, color: '#2196F3' }
  },
  {
    id: 'macd',
    name: 'MACD',
    description: 'Moving Average Convergence Divergence - trend-following momentum indicator',
    category: 'Oscillators',
    defaultSettings: {
      fastPeriod: 12,
      slowPeriod: 26,
      signalPeriod: 9,
      macdColor: '#2196F3',
      signalColor: '#FF5722',
      histogramColor: '#4CAF50'
    }
  },
  {
    id: 'bollinger',
    name: 'Bollinger Bands',
    description: 'Volatility indicator with upper and lower bands around moving average',
    category: 'Volatility',
    defaultSettings: {
      period: 20,
      stdDev: 2,
      upperColor: '#2196F3',
      middleColor: '#FF9800',
      lowerColor: '#2196F3'
    }
  },
  {
    id: 'stochastic',
    name: 'Stochastic Oscillator',
    description: 'Compares closing price to price range over time (0-100)',
    category: 'Oscillators',
    defaultSettings: {
      kPeriod: 14,
      dPeriod: 3,
      kColor: '#2196F3',
      dColor: '#FF5722'
    }
  }
]

export const TIME_INTERVALS = [
  { value: 'ONE_MINUTE', label: '1m' },
  { value: 'FIVE_MINUTE', label: '5m' },
  { value: 'FIFTEEN_MINUTE', label: '15m' },
  { value: 'THIRTY_MINUTE', label: '30m' },
  { value: 'ONE_HOUR', label: '1h' },
  { value: 'TWO_HOUR', label: '2h' },
  { value: 'SIX_HOUR', label: '6h' },
  { value: 'ONE_DAY', label: '1d' }
]
