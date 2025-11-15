import { useEffect, useRef, useState } from 'react'
import { createChart, ColorType, IChartApi, ISeriesApi, Time, LineData } from 'lightweight-charts'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import { BarChart2, Activity, TrendingUp, ChevronDown, X, Settings, Search } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const TIME_INTERVALS = [
  { value: 'ONE_MINUTE', label: '1m' },
  { value: 'FIVE_MINUTE', label: '5m' },
  { value: 'FIFTEEN_MINUTE', label: '15m' },
  { value: 'THIRTY_MINUTE', label: '30m' },
  { value: 'ONE_HOUR', label: '1h' },
  { value: 'TWO_HOUR', label: '2h' },
  { value: 'SIX_HOUR', label: '6h' },
  { value: 'ONE_DAY', label: '1d' },
]

interface CandleData {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface IndicatorConfig {
  id: string
  name: string
  type: string
  enabled: boolean
  settings: Record<string, any>
  color?: string
  series?: ISeriesApi<any>[]
}

// Indicator calculation functions
function calculateSMA(data: number[], period: number): (number | null)[] {
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

function calculateEMA(data: number[], period: number): (number | null)[] {
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

function calculateRSI(data: number[], period: number = 14): (number | null)[] {
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

function calculateMACD(
  data: number[],
  fastPeriod: number = 12,
  slowPeriod: number = 26,
  signalPeriod: number = 9
): { macd: (number | null)[], signal: (number | null)[], histogram: (number | null)[] } {
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

function calculateBollingerBands(
  data: number[],
  period: number = 20,
  stdDev: number = 2
): { upper: (number | null)[], middle: (number | null)[], lower: (number | null)[] } {
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

function calculateStochastic(
  highs: number[],
  lows: number[],
  closes: number[],
  kPeriod: number = 14,
  dPeriod: number = 3
): { k: (number | null)[], d: (number | null)[] } {
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

// Calculate Heikin-Ashi candles from regular candles
function calculateHeikinAshi(candles: CandleData[]): CandleData[] {
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

// Available indicators
const AVAILABLE_INDICATORS = [
  {
    id: 'sma',
    name: 'Simple Moving Average (SMA)',
    category: 'Moving Averages',
    defaultSettings: { period: 20, color: '#FF9800' }
  },
  {
    id: 'ema',
    name: 'Exponential Moving Average (EMA)',
    category: 'Moving Averages',
    defaultSettings: { period: 12, color: '#9C27B0' }
  },
  {
    id: 'rsi',
    name: 'Relative Strength Index (RSI)',
    category: 'Oscillators',
    defaultSettings: { period: 14, overbought: 70, oversold: 30, color: '#2196F3' }
  },
  {
    id: 'macd',
    name: 'MACD',
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
    category: 'Oscillators',
    defaultSettings: {
      kPeriod: 14,
      dPeriod: 3,
      kColor: '#2196F3',
      dColor: '#FF5722'
    }
  },
  {
    id: 'volume',
    name: 'Volume',
    category: 'Volume',
    defaultSettings: { color: '#64748b' }
  }
]

function Charts() {
  // Fetch portfolio to get coins we hold (uses shared cache)
  const { data: portfolio } = useQuery({
    queryKey: ['account-portfolio'],
    queryFn: async () => {
      const response = await fetch('/api/account/portfolio')
      if (!response.ok) throw new Error('Failed to fetch portfolio')
      return response.json()
    },
    refetchInterval: 60000,
    staleTime: 30000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  })

  // Fetch all available products from Coinbase
  const { data: productsData } = useQuery({
    queryKey: ['available-products'],
    queryFn: async () => {
      const response = await fetch('/api/products')
      if (!response.ok) throw new Error('Failed to fetch products')
      return response.json()
    },
    staleTime: 3600000, // Cache for 1 hour (product list rarely changes)
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  })

  // Generate trading pairs from all available products
  const TRADING_PAIRS = (() => {
    if (!productsData?.products) {
      // Fallback to default pairs while loading
      return [
        { value: 'BTC-USD', label: 'BTC/USD', group: 'USD Pairs', inPortfolio: false },
        { value: 'ETH-USD', label: 'ETH/USD', group: 'USD Pairs', inPortfolio: false },
        { value: 'SOL-USD', label: 'SOL/USD', group: 'USD Pairs', inPortfolio: false },
      ]
    }

    // Get list of assets in portfolio
    const portfolioAssets = new Set(
      portfolio?.holdings?.map((h: any) => h.asset) || []
    )

    // Convert products to trading pairs with portfolio indicator
    const pairs = productsData.products.map((product: any) => {
      const base = product.base_currency
      const quote = product.quote_currency
      const inPortfolio = portfolioAssets.has(base)

      return {
        value: product.product_id,
        label: `${base}/${quote}`,
        group: quote === 'USD' ? 'USD Pairs' : 'BTC Pairs',
        inPortfolio: inPortfolio
      }
    })

    return pairs
  })()

  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const mainSeriesRef = useRef<ISeriesApi<any> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const indicatorSeriesRef = useRef<Map<string, ISeriesApi<any>[]>>(new Map())
  const indicatorChartsRef = useRef<Map<string, IChartApi>>(new Map())

  const [selectedPair, setSelectedPair] = useState(() => {
    const saved = localStorage.getItem('chart-selected-pair')
    // Validate saved pair still exists in trading pairs
    return saved || 'BTC-USD'
  })
  const [selectedInterval, setSelectedInterval] = useState(() => {
    return localStorage.getItem('chart-selected-interval') || 'FIFTEEN_MINUTE'
  })
  const [chartType, setChartType] = useState<'candlestick' | 'bar' | 'line' | 'area' | 'baseline'>(() => {
    const saved = localStorage.getItem('chart-type')
    return (saved as any) || 'candlestick'
  })
  const [useHeikinAshi, setUseHeikinAshi] = useState(() => {
    return localStorage.getItem('chart-heikin-ashi') === 'true'
  })
  const [indicators, setIndicators] = useState<IndicatorConfig[]>(() => {
    // Load saved indicators from localStorage
    try {
      const saved = localStorage.getItem('chart-indicators')
      if (saved) {
        return JSON.parse(saved)
      }
    } catch (e) {
      console.error('Failed to load saved indicators:', e)
    }
    return []
  })
  const [showIndicatorModal, setShowIndicatorModal] = useState(false)
  const [indicatorSearch, setIndicatorSearch] = useState('')
  const [editingIndicator, setEditingIndicator] = useState<IndicatorConfig | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [btcPrice, setBtcPrice] = useState<number | null>(null)
  const lastUpdateRef = useRef<string>('')
  const isCleanedUpRef = useRef<boolean>(false)
  const candleDataRef = useRef<CandleData[]>([])

  // Initialize main chart
  useEffect(() => {
    if (!chartContainerRef.current) return

    isCleanedUpRef.current = false

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#1e293b' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: '#334155' },
        horzLines: { color: '#334155' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 500,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        visible: true,
        borderVisible: true,
        borderColor: '#334155',
        autoScale: true,
        scaleMargins: {
          top: 0.1,
          bottom: 0.2,
        },
      },
      leftPriceScale: {
        visible: false,
      },
      crosshair: {
        mode: 1,
      },
    })

    chartRef.current = chart

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: 'volume',
    })

    chart.priceScale('volume').applyOptions({
      scaleMargins: {
        top: 0.85,
        bottom: 0,
      },
    })

    // Ensure the right price scale is visible
    chart.priceScale('right').applyOptions({
      scaleMargins: {
        top: 0.1,
        bottom: 0.2,
      },
    })

    volumeSeriesRef.current = volumeSeries

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
        })
      }
    }

    window.addEventListener('resize', handleResize)

    return () => {
      isCleanedUpRef.current = true
      window.removeEventListener('resize', handleResize)
      if (chartRef.current) {
        chartRef.current.remove()
      }
    }
  }, [])

  // Save chart settings to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('chart-indicators', JSON.stringify(indicators))
    } catch (e) {
      console.error('Failed to save indicators:', e)
    }
  }, [indicators])

  useEffect(() => {
    localStorage.setItem('chart-selected-pair', selectedPair)
  }, [selectedPair])

  useEffect(() => {
    localStorage.setItem('chart-selected-interval', selectedInterval)
  }, [selectedInterval])

  useEffect(() => {
    localStorage.setItem('chart-type', chartType)
  }, [chartType])

  useEffect(() => {
    localStorage.setItem('chart-heikin-ashi', useHeikinAshi.toString())
  }, [useHeikinAshi])

  // Cleanup indicator charts when component unmounts
  useEffect(() => {
    return () => {
      indicatorChartsRef.current.forEach(chart => {
        try {
          chart.remove()
        } catch (e) {
          // Chart may have already been removed
        }
      })
      indicatorChartsRef.current.clear()
    }
  }, [])

  // Update chart type when changed
  useEffect(() => {
    if (!chartRef.current || isCleanedUpRef.current) return

    if (mainSeriesRef.current) {
      try {
        chartRef.current.removeSeries(mainSeriesRef.current)
      } catch (e) {
        // Series may have already been removed
      }
      mainSeriesRef.current = null
    }

    // Determine price format based on trading pair
    const isBTCPair = selectedPair.endsWith('-BTC')
    const priceFormat = isBTCPair
      ? { type: 'price' as const, precision: 8, minMove: 0.00000001 }
      : { type: 'price' as const, precision: 2, minMove: 0.01 }

    if (chartType === 'candlestick') {
      mainSeriesRef.current = chartRef.current.addCandlestickSeries({
        upColor: '#10b981',
        downColor: '#ef4444',
        borderUpColor: '#10b981',
        borderDownColor: '#ef4444',
        wickUpColor: '#10b981',
        wickDownColor: '#ef4444',
        priceScaleId: 'right',
        priceFormat: priceFormat,
      })
    } else if (chartType === 'bar') {
      mainSeriesRef.current = chartRef.current.addBarSeries({
        upColor: '#10b981',
        downColor: '#ef4444',
        openVisible: true,
        thinBars: false,
        priceScaleId: 'right',
        priceFormat: priceFormat,
      })
    } else if (chartType === 'line') {
      mainSeriesRef.current = chartRef.current.addLineSeries({
        color: '#2196F3',
        lineWidth: 2,
        priceScaleId: 'right',
        priceFormat: priceFormat,
      })
    } else if (chartType === 'area') {
      mainSeriesRef.current = chartRef.current.addAreaSeries({
        topColor: '#2196F380',
        bottomColor: '#2196F310',
        lineColor: '#2196F3',
        lineWidth: 2,
        priceScaleId: 'right',
        priceFormat: priceFormat,
      })
    } else if (chartType === 'baseline') {
      mainSeriesRef.current = chartRef.current.addBaselineSeries({
        topLineColor: '#10b981',
        topFillColor1: '#10b98140',
        topFillColor2: '#10b98120',
        bottomLineColor: '#ef4444',
        bottomFillColor1: '#ef444440',
        bottomFillColor2: '#ef444420',
        lineWidth: 2,
        priceScaleId: 'right',
        priceFormat: priceFormat,
      })
    }

    lastUpdateRef.current = ''
  }, [chartType, selectedPair])

  // Add indicator
  const addIndicator = (indicatorType: string) => {
    const template = AVAILABLE_INDICATORS.find(i => i.id === indicatorType)
    if (!template) return

    const newIndicator: IndicatorConfig = {
      id: `${indicatorType}-${Date.now()}`,
      name: template.name,
      type: indicatorType,
      enabled: true,
      settings: { ...template.defaultSettings },
      series: []
    }

    setIndicators(prev => [...prev, newIndicator])
    setShowIndicatorModal(false)
    lastUpdateRef.current = '' // Trigger refresh
  }

  // Remove indicator
  const removeIndicator = (indicatorId: string) => {
    // Remove series from charts
    const series = indicatorSeriesRef.current.get(indicatorId)
    if (series) {
      series.forEach(s => {
        try {
          // Try to remove from main chart first
          if (chartRef.current) {
            chartRef.current.removeSeries(s)
          }
        } catch (e) {
          // Series may have already been removed or belongs to indicator chart
        }
      })
      indicatorSeriesRef.current.delete(indicatorId)
    }

    // Remove indicator chart if it exists
    const indicatorChart = indicatorChartsRef.current.get(indicatorId)
    if (indicatorChart) {
      try {
        indicatorChart.remove()
      } catch (e) {
        // Chart may have already been removed
      }
      indicatorChartsRef.current.delete(indicatorId)
    }

    setIndicators(prev => prev.filter(i => i.id !== indicatorId))
  }

  // Update indicator settings
  const updateIndicatorSettings = (indicatorId: string, newSettings: Record<string, any>) => {
    setIndicators(prev =>
      prev.map(ind =>
        ind.id === indicatorId ? { ...ind, settings: { ...ind.settings, ...newSettings } } : ind
      )
    )
    setEditingIndicator(null)
  }

  // Render indicators
  const renderIndicators = (candles: CandleData[]) => {
    if (!chartRef.current || !candles.length) {
      console.log('renderIndicators: missing requirements', {
        hasChart: !!chartRef.current,
        candlesLength: candles.length
      })
      return
    }

    console.log('renderIndicators: rendering', indicators.length, 'indicators')

    // Determine price format based on trading pair
    const isBTCPair = selectedPair.endsWith('-BTC')
    const priceFormat = isBTCPair
      ? { type: 'price' as const, precision: 8, minMove: 0.00000001 }
      : { type: 'price' as const, precision: 2, minMove: 0.01 }

    const closes = candles.map(c => c.close)
    const highs = candles.map(c => c.high)
    const lows = candles.map(c => c.low)

    indicators.forEach(indicator => {
      if (!indicator.enabled) return

      console.log('Rendering indicator:', indicator.type, indicator.id)

      // Remove old series for this indicator
      const oldSeries = indicatorSeriesRef.current.get(indicator.id)
      if (oldSeries && oldSeries.length > 0) {
        oldSeries.forEach(series => {
          if (!series) return

          try {
            if (indicator.type === 'rsi' || indicator.type === 'macd' || indicator.type === 'stochastic') {
              // Remove from indicator's specific chart
              const indicatorChart = indicatorChartsRef.current.get(indicator.id)
              if (indicatorChart) {
                indicatorChart.removeSeries(series)
              }
            } else {
              // Remove from main chart
              if (chartRef.current) {
                chartRef.current.removeSeries(series)
              }
            }
          } catch (e) {
            // Series may have already been removed, ignore
          }
        })
        // Clear the old series from the ref
        indicatorSeriesRef.current.delete(indicator.id)
      }

      const newSeries: ISeriesApi<any>[] = []

      if (indicator.type === 'sma') {
        const smaValues = calculateSMA(closes, indicator.settings.period)
        const smaData: LineData<Time>[] = []
        candles.forEach((c, i) => {
          if (smaValues[i] !== null) {
            smaData.push({ time: c.time as Time, value: smaValues[i]! })
          }
        })
        const series = chartRef.current!.addLineSeries({
          color: indicator.settings.color,
          lineWidth: 2,
          title: `SMA(${indicator.settings.period})`,
          priceFormat: priceFormat,
        })
        series.setData(smaData)
        newSeries.push(series)
      }

      if (indicator.type === 'ema') {
        const emaValues = calculateEMA(closes, indicator.settings.period)
        const emaData: LineData<Time>[] = []
        candles.forEach((c, i) => {
          if (emaValues[i] !== null) {
            emaData.push({ time: c.time as Time, value: emaValues[i]! })
          }
        })
        const series = chartRef.current!.addLineSeries({
          color: indicator.settings.color,
          lineWidth: 2,
          title: `EMA(${indicator.settings.period})`,
          priceFormat: priceFormat,
        })
        series.setData(emaData)
        newSeries.push(series)
      }

      if (indicator.type === 'bollinger') {
        const { upper, middle, lower } = calculateBollingerBands(
          closes,
          indicator.settings.period,
          indicator.settings.stdDev
        )

        const upperLineData: LineData<Time>[] = []
        const middleLineData: LineData<Time>[] = []
        const lowerLineData: LineData<Time>[] = []

        candles.forEach((c, i) => {
          if (upper[i] !== null && lower[i] !== null && middle[i] !== null) {
            upperLineData.push({ time: c.time as Time, value: upper[i]! })
            middleLineData.push({ time: c.time as Time, value: middle[i]! })
            lowerLineData.push({ time: c.time as Time, value: lower[i]! })
          }
        })

        const upperLineSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.upperColor,
          lineWidth: 1,
          lastValueVisible: false,
          priceLineVisible: false,
          priceFormat: priceFormat,
        })
        const middleLineSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.middleColor,
          lineWidth: 1,
          lastValueVisible: false,
          priceLineVisible: false,
          priceFormat: priceFormat,
        })
        const lowerLineSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.lowerColor,
          lineWidth: 1,
          lastValueVisible: false,
          priceLineVisible: false,
          priceFormat: priceFormat,
        })

        upperLineSeries.setData(upperLineData)
        middleLineSeries.setData(middleLineData)
        lowerLineSeries.setData(lowerLineData)

        newSeries.push(upperLineSeries, middleLineSeries, lowerLineSeries)
      }

      if (indicator.type === 'rsi') {
        const indicatorChart = indicatorChartsRef.current.get(indicator.id)
        if (!indicatorChart) {
          console.log(`Chart not found for RSI indicator ${indicator.id}`)
          return
        }

        console.log('RSI: Chart found, calculating values...')

        const rsiValues = calculateRSI(closes, indicator.settings.period)
        const rsiData: LineData<Time>[] = []
        candles.forEach((c, i) => {
          if (rsiValues[i] !== null) {
            rsiData.push({ time: c.time as Time, value: rsiValues[i]! })
          }
        })

        console.log('RSI data points:', rsiData.length, 'Sample values:', rsiData.slice(0, 3).map(d => d.value))

        // Add overbought zone shading (70-100)
        const overboughtFillData: any[] = candles.map(c => ({
          time: c.time as Time,
          value: 100,
        }))
        const overboughtFillSeries = indicatorChart.addBaselineSeries({
          baseValue: { type: 'price', price: indicator.settings.overbought },
          topLineColor: 'transparent',
          topFillColor1: '#ef444410',
          topFillColor2: '#ef444408',
          bottomLineColor: 'transparent',
          bottomFillColor1: 'transparent',
          bottomFillColor2: 'transparent',
          lastValueVisible: false,
          priceLineVisible: false,
        })
        overboughtFillSeries.setData(overboughtFillData)

        // Add oversold zone shading (0-30)
        const oversoldFillData: any[] = candles.map(c => ({
          time: c.time as Time,
          value: 0,
        }))
        const oversoldFillSeries = indicatorChart.addBaselineSeries({
          baseValue: { type: 'price', price: indicator.settings.oversold },
          topLineColor: 'transparent',
          topFillColor1: 'transparent',
          topFillColor2: 'transparent',
          bottomLineColor: 'transparent',
          bottomFillColor1: '#10b98108',
          bottomFillColor2: '#10b98110',
          lastValueVisible: false,
          priceLineVisible: false,
        })
        oversoldFillSeries.setData(oversoldFillData)

        const rsiSeries = indicatorChart.addLineSeries({
          color: indicator.settings.color,
          lineWidth: 2,
          title: `RSI(${indicator.settings.period})`,
        })
        rsiSeries.setData(rsiData)

        // Add overbought/oversold reference lines
        const overboughtData: LineData<Time>[] = candles.map(c => ({
          time: c.time as Time,
          value: indicator.settings.overbought
        }))
        const oversoldData: LineData<Time>[] = candles.map(c => ({
          time: c.time as Time,
          value: indicator.settings.oversold
        }))

        const obSeries = indicatorChart.addLineSeries({
          color: '#ef444440',
          lineWidth: 1,
          lineStyle: 2,
          lastValueVisible: false,
          priceLineVisible: false,
        })
        const osSeries = indicatorChart.addLineSeries({
          color: '#10b98140',
          lineWidth: 1,
          lineStyle: 2,
          lastValueVisible: false,
          priceLineVisible: false,
        })

        obSeries.setData(overboughtData)
        osSeries.setData(oversoldData)

        console.log('RSI: All series created and data set')
        newSeries.push(overboughtFillSeries, oversoldFillSeries, rsiSeries, obSeries, osSeries)
      }

      if (indicator.type === 'macd') {
        const indicatorChart = indicatorChartsRef.current.get(indicator.id)
        if (!indicatorChart) {
          console.log(`Chart not found for MACD indicator ${indicator.id}`)
          return
        }

        console.log('MACD: Chart found, calculating values...')

        const { macd, signal, histogram } = calculateMACD(
          closes,
          indicator.settings.fastPeriod,
          indicator.settings.slowPeriod,
          indicator.settings.signalPeriod
        )

        const macdData: LineData<Time>[] = []
        const signalData: LineData<Time>[] = []
        const histogramData: any[] = []

        candles.forEach((c, i) => {
          if (macd[i] !== null) {
            macdData.push({ time: c.time as Time, value: macd[i]! })
          }
          if (signal[i] !== null) {
            signalData.push({ time: c.time as Time, value: signal[i]! })
          }
          if (histogram[i] !== null) {
            histogramData.push({
              time: c.time as Time,
              value: histogram[i]!,
              color: histogram[i]! >= 0 ? '#10b981' : '#ef4444'
            })
          }
        })

        const macdSeries = indicatorChart.addLineSeries({
          color: indicator.settings.macdColor,
          lineWidth: 2,
          title: 'MACD',
        })
        const signalSeries = indicatorChart.addLineSeries({
          color: indicator.settings.signalColor,
          lineWidth: 2,
          title: 'Signal',
        })
        const histSeries = indicatorChart.addHistogramSeries({
          title: 'Histogram',
        })

        macdSeries.setData(macdData)
        signalSeries.setData(signalData)
        histSeries.setData(histogramData)

        console.log('MACD: All series created and data set. MACD points:', macdData.length, 'Signal points:', signalData.length, 'Histogram points:', histogramData.length)
        newSeries.push(macdSeries, signalSeries, histSeries)
      }

      if (indicator.type === 'stochastic') {
        const indicatorChart = indicatorChartsRef.current.get(indicator.id)
        if (!indicatorChart) {
          console.log(`Chart not found for Stochastic indicator ${indicator.id}`)
          return
        }

        const { k, d } = calculateStochastic(
          highs,
          lows,
          closes,
          indicator.settings.kPeriod,
          indicator.settings.dPeriod
        )

        const kData: LineData<Time>[] = []
        const dData: LineData<Time>[] = []

        candles.forEach((c, i) => {
          if (k[i] !== null) {
            kData.push({ time: c.time as Time, value: k[i]! })
          }
          if (d[i] !== null) {
            dData.push({ time: c.time as Time, value: d[i]! })
          }
        })

        const kSeries = indicatorChart.addLineSeries({
          color: indicator.settings.kColor,
          lineWidth: 2,
          title: `%K(${indicator.settings.kPeriod})`,
        })
        const dSeries = indicatorChart.addLineSeries({
          color: indicator.settings.dColor,
          lineWidth: 2,
          title: `%D(${indicator.settings.dPeriod})`,
        })

        kSeries.setData(kData)
        dSeries.setData(dData)

        newSeries.push(kSeries, dSeries)
      }

      // Save series to ref
      if (newSeries.length > 0) {
        indicatorSeriesRef.current.set(indicator.id, newSeries)
        console.log(`Saved ${newSeries.length} series for ${indicator.type} ${indicator.id}`)
      } else {
        console.warn(`No series created for ${indicator.type} ${indicator.id}`)
      }
    })

    console.log('renderIndicators: Complete. Total indicators rendered:', indicators.length)
  }

  // Reset last update when pair or interval changes
  useEffect(() => {
    lastUpdateRef.current = ''
  }, [selectedPair, selectedInterval])

  // Create and manage charts for oscillator indicators
  useEffect(() => {
    const oscillators = indicators.filter(i => ['rsi', 'macd', 'stochastic'].includes(i.type))

    oscillators.forEach(indicator => {
      // Check if chart already exists
      if (indicatorChartsRef.current.has(indicator.id)) return

      // Get container element
      const container = document.getElementById(`indicator-chart-${indicator.id}`)
      if (!container) {
        console.log(`Container not found for indicator ${indicator.id}`)
        return
      }

      console.log(`Creating chart for ${indicator.type} indicator ${indicator.id}`)

      // Create chart
      const chart = createChart(container, {
        layout: {
          background: { type: ColorType.Solid, color: '#1e293b' },
          textColor: '#94a3b8',
        },
        grid: {
          vertLines: { color: '#334155' },
          horzLines: { color: '#334155' },
        },
        width: container.clientWidth,
        height: 200,
        timeScale: {
          timeVisible: true,
          secondsVisible: false,
          visible: false,
        },
      })

      // Sync time scale with main chart (only after both charts have data)
      if (chartRef.current) {
        chartRef.current.timeScale().subscribeVisibleTimeRangeChange((timeRange) => {
          if (timeRange) {
            try {
              chart.timeScale().setVisibleRange(timeRange)
            } catch (e) {
              // Chart may not have data yet, ignore
            }
          }
        })
      }

      indicatorChartsRef.current.set(indicator.id, chart)
    })

    // Remove charts for indicators that no longer exist
    const existingOscillatorIds = new Set(oscillators.map(i => i.id))
    indicatorChartsRef.current.forEach((chart, id) => {
      if (!existingOscillatorIds.has(id)) {
        console.log(`Removing chart for indicator ${id}`)
        try {
          chart.remove()
        } catch (e) {
          // Chart may have already been removed
        }
        indicatorChartsRef.current.delete(id)
      }
    })
  }, [indicators])

  // Render indicators when indicator list changes
  useEffect(() => {
    if (candleDataRef.current.length > 0 && chartRef.current && !isCleanedUpRef.current) {
      console.log('Indicators useEffect triggered - rendering indicators')
      // Small delay to ensure DOM elements are ready
      setTimeout(() => {
        renderIndicators(candleDataRef.current)
      }, 50)
    }
  }, [indicators])

  // Fetch and update chart data
  useEffect(() => {
    const fetchCandles = async () => {
      if (!mainSeriesRef.current || !volumeSeriesRef.current || isCleanedUpRef.current) return

      const isInitialLoad = lastUpdateRef.current === ''
      setLoading(isInitialLoad)
      setError(null)

      try {
        const response = await axios.get<{ candles: CandleData[] }>(
          `${API_BASE}/api/candles`,
          {
            params: {
              product_id: selectedPair,
              granularity: selectedInterval,
              limit: 300,
            },
          }
        )

        const { candles, product_id: returnedProductId } = response.data

        console.log(`Requested: ${selectedPair}, Received: ${returnedProductId || 'unknown'}, Candles: ${candles?.length || 0}`)

        if (!candles || candles.length === 0) {
          setError('No data available for this pair')
          return
        }

        // Warn if we got data for a different pair than requested
        if (returnedProductId && returnedProductId !== selectedPair) {
          console.warn(`WARNING: Requested ${selectedPair} but got data for ${returnedProductId}`)
          setError(`No data available for ${selectedPair}. Showing ${returnedProductId} instead.`)
        }

        candleDataRef.current = candles

        const latestCandleKey = candles.length > 0
          ? `${candles[candles.length - 1].time}_${candles[candles.length - 1].close}_${useHeikinAshi}`
          : ''

        if (latestCandleKey !== lastUpdateRef.current) {
          // Apply Heikin-Ashi transformation if enabled
          const displayCandles = useHeikinAshi ? calculateHeikinAshi(candles) : candles

          const priceData = displayCandles.map((c) => {
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
              return {
                time: c.time as Time,
                value: c.close,
              }
            }
          })

          const volumeData = displayCandles.map((c) => ({
            time: c.time as Time,
            value: c.volume,
            color: c.close >= c.open ? '#10b98180' : '#ef444480',
          }))

          if (mainSeriesRef.current && volumeSeriesRef.current && !isCleanedUpRef.current) {
            try {
              mainSeriesRef.current.setData(priceData as any)
              volumeSeriesRef.current.setData(volumeData)

              // Render indicators with the new candle data
              if (indicators.length > 0) {
                console.log('Fetched candles, now rendering indicators...')
                renderIndicators(candles)
              }

              if (isInitialLoad && chartRef.current && !isCleanedUpRef.current) {
                chartRef.current.timeScale().fitContent()
              }

              lastUpdateRef.current = latestCandleKey
            } catch (e) {
              return
            }
          }
        }
      } catch (err: any) {
        console.error('Error fetching candles:', err)
        setError(err.response?.data?.detail || 'Failed to load chart data')
      } finally {
        setLoading(false)
      }
    }

    fetchCandles()
    const interval = setInterval(fetchCandles, 30000)

    return () => clearInterval(interval)
  }, [selectedPair, selectedInterval, chartType, indicators, useHeikinAshi])

  const filteredIndicators = AVAILABLE_INDICATORS.filter(ind =>
    ind.name.toLowerCase().includes(indicatorSearch.toLowerCase()) ||
    ind.category.toLowerCase().includes(indicatorSearch.toLowerCase())
  )

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Charts</h1>
      </div>

      {/* Toolbar */}
      <div className="bg-slate-800 rounded-lg p-3 flex items-center gap-3 flex-wrap">
        {/* Pair Selector */}
        <select
          value={selectedPair}
          onChange={(e) => setSelectedPair(e.target.value)}
          className="bg-slate-700 text-white px-3 py-2 rounded text-sm font-medium border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <optgroup label="USD Pairs">
            {TRADING_PAIRS.filter(p => p.group === 'USD Pairs').map((pair) => (
              <option key={pair.value} value={pair.value}>
                {pair.inPortfolio ? '• ' : ''}{pair.label}
              </option>
            ))}
          </optgroup>
          <optgroup label="BTC Pairs">
            {TRADING_PAIRS.filter(p => p.group === 'BTC Pairs').map((pair) => (
              <option key={pair.value} value={pair.value}>
                {pair.inPortfolio ? '• ' : ''}{pair.label}
              </option>
            ))}
          </optgroup>
        </select>

        <div className="w-px h-6 bg-slate-600" />

        {/* Chart Type Buttons */}
        <div className="flex gap-1">
          <button
            onClick={() => setChartType('candlestick')}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              chartType === 'candlestick'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
            title="Candlestick"
          >
            <BarChart2 size={16} />
          </button>
          <button
            onClick={() => setChartType('bar')}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              chartType === 'bar'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
            title="Bar"
          >
            Bar
          </button>
          <button
            onClick={() => setChartType('line')}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              chartType === 'line'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
            title="Line"
          >
            Line
          </button>
          <button
            onClick={() => setChartType('area')}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              chartType === 'area'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
            title="Area"
          >
            Area
          </button>
          <button
            onClick={() => setChartType('baseline')}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              chartType === 'baseline'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
            title="Baseline"
          >
            Baseline
          </button>
        </div>

        <div className="w-px h-6 bg-slate-600" />

        {/* Heikin-Ashi Toggle */}
        <button
          onClick={() => setUseHeikinAshi(!useHeikinAshi)}
          className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
            useHeikinAshi
              ? 'bg-purple-600 text-white'
              : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
          }`}
          title="Heikin-Ashi Candles"
        >
          HA
        </button>

        <div className="w-px h-6 bg-slate-600" />

        {/* Indicators Button */}
        <button
          onClick={() => setShowIndicatorModal(true)}
          className="bg-slate-700 text-slate-300 hover:bg-slate-600 px-3 py-1.5 rounded text-sm font-medium transition-colors flex items-center gap-2"
        >
          <Activity size={16} />
          Indicators
        </button>

        <div className="flex-1" />

        {/* Time Interval Buttons */}
        <div className="flex gap-1">
          {TIME_INTERVALS.map((interval) => (
            <button
              key={interval.value}
              onClick={() => setSelectedInterval(interval.value)}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                selectedInterval === interval.value
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              {interval.label}
            </button>
          ))}
        </div>
      </div>

      {/* Active Indicators Legend */}
      {indicators.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-3 flex items-center gap-3 flex-wrap">
          {indicators.map((indicator) => (
            <div
              key={indicator.id}
              className="flex items-center gap-2 bg-slate-700 px-3 py-1.5 rounded text-sm"
            >
              <span className="text-white font-medium">{indicator.name}</span>
              <button
                onClick={() => setEditingIndicator(indicator)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <Settings size={14} />
              </button>
              <button
                onClick={() => removeIndicator(indicator.id)}
                className="text-slate-400 hover:text-red-400 transition-colors"
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Chart Container */}
      <div className="bg-slate-800 rounded-lg p-4">
        {loading && (
          <div className="text-center py-8">
            <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-500 border-r-transparent"></div>
            <p className="mt-2 text-slate-400">Loading chart data...</p>
          </div>
        )}

        {error && (
          <div className="bg-red-500/10 border border-red-500 rounded p-4 text-red-400">
            {error}
          </div>
        )}

        <div ref={chartContainerRef} className={loading || error ? 'hidden' : ''} />
      </div>

      {/* Oscillator Indicator Panels */}
      {indicators.filter(i => ['rsi', 'macd', 'stochastic'].includes(i.type)).map((indicator) => (
        <div key={indicator.id} className="bg-slate-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-slate-300">{indicator.name}</h3>
          </div>
          <div
            id={`indicator-chart-${indicator.id}`}
            style={{ height: '200px' }}
          />
        </div>
      ))}

      {/* Indicator Modal */}
      {showIndicatorModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-white">Add Indicator</h2>
              <button
                onClick={() => setShowIndicatorModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X size={24} />
              </button>
            </div>

            {/* Search */}
            <div className="mb-4 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400" size={20} />
              <input
                type="text"
                placeholder="Search indicators..."
                value={indicatorSearch}
                onChange={(e) => setIndicatorSearch(e.target.value)}
                className="w-full bg-slate-700 text-white pl-10 pr-4 py-2 rounded border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Indicator List */}
            <div className="space-y-2">
              {Object.entries(
                filteredIndicators.reduce((acc, ind) => {
                  if (!acc[ind.category]) acc[ind.category] = []
                  acc[ind.category].push(ind)
                  return acc
                }, {} as Record<string, typeof AVAILABLE_INDICATORS>)
              ).map(([category, categoryIndicators]) => (
                <div key={category}>
                  <div className="text-xs font-semibold text-slate-400 mb-2 mt-4 first:mt-0">
                    {category}
                  </div>
                  {categoryIndicators.map((indicator) => (
                    <button
                      key={indicator.id}
                      onClick={() => addIndicator(indicator.id)}
                      className="w-full text-left bg-slate-700 hover:bg-slate-600 text-white px-4 py-3 rounded transition-colors"
                    >
                      {indicator.name}
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Indicator Settings Modal */}
      {editingIndicator && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 max-w-md w-full mx-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-white">
                {editingIndicator.name} Settings
              </h2>
              <button
                onClick={() => setEditingIndicator(null)}
                className="text-slate-400 hover:text-white"
              >
                <X size={24} />
              </button>
            </div>

            <div className="space-y-4">
              {editingIndicator.type === 'sma' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Period
                    </label>
                    <input
                      type="number"
                      value={editingIndicator.settings.period}
                      onChange={(e) =>
                        updateIndicatorSettings(editingIndicator.id, {
                          period: parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Color
                    </label>
                    <input
                      type="color"
                      value={editingIndicator.settings.color}
                      onChange={(e) =>
                        updateIndicatorSettings(editingIndicator.id, {
                          color: e.target.value,
                        })
                      }
                      className="w-full h-10 bg-slate-700 rounded border border-slate-600"
                    />
                  </div>
                </>
              )}

              {editingIndicator.type === 'ema' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Period
                    </label>
                    <input
                      type="number"
                      value={editingIndicator.settings.period}
                      onChange={(e) =>
                        updateIndicatorSettings(editingIndicator.id, {
                          period: parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Color
                    </label>
                    <input
                      type="color"
                      value={editingIndicator.settings.color}
                      onChange={(e) =>
                        updateIndicatorSettings(editingIndicator.id, {
                          color: e.target.value,
                        })
                      }
                      className="w-full h-10 bg-slate-700 rounded border border-slate-600"
                    />
                  </div>
                </>
              )}

              {editingIndicator.type === 'rsi' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Period
                    </label>
                    <input
                      type="number"
                      value={editingIndicator.settings.period}
                      onChange={(e) =>
                        updateIndicatorSettings(editingIndicator.id, {
                          period: parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Overbought Level
                    </label>
                    <input
                      type="number"
                      value={editingIndicator.settings.overbought}
                      onChange={(e) =>
                        updateIndicatorSettings(editingIndicator.id, {
                          overbought: parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Oversold Level
                    </label>
                    <input
                      type="number"
                      value={editingIndicator.settings.oversold}
                      onChange={(e) =>
                        updateIndicatorSettings(editingIndicator.id, {
                          oversold: parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                    />
                  </div>
                </>
              )}

              {editingIndicator.type === 'bollinger' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Period
                    </label>
                    <input
                      type="number"
                      value={editingIndicator.settings.period}
                      onChange={(e) =>
                        updateIndicatorSettings(editingIndicator.id, {
                          period: parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Standard Deviation
                    </label>
                    <input
                      type="number"
                      step="0.1"
                      value={editingIndicator.settings.stdDev}
                      onChange={(e) =>
                        updateIndicatorSettings(editingIndicator.id, {
                          stdDev: parseFloat(e.target.value),
                        })
                      }
                      className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                    />
                  </div>
                </>
              )}

              {editingIndicator.type === 'macd' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Fast Period
                    </label>
                    <input
                      type="number"
                      value={editingIndicator.settings.fastPeriod}
                      onChange={(e) =>
                        updateIndicatorSettings(editingIndicator.id, {
                          fastPeriod: parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Slow Period
                    </label>
                    <input
                      type="number"
                      value={editingIndicator.settings.slowPeriod}
                      onChange={(e) =>
                        updateIndicatorSettings(editingIndicator.id, {
                          slowPeriod: parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      Signal Period
                    </label>
                    <input
                      type="number"
                      value={editingIndicator.settings.signalPeriod}
                      onChange={(e) =>
                        updateIndicatorSettings(editingIndicator.id, {
                          signalPeriod: parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                    />
                  </div>
                </>
              )}

              {editingIndicator.type === 'stochastic' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      %K Period
                    </label>
                    <input
                      type="number"
                      value={editingIndicator.settings.kPeriod}
                      onChange={(e) =>
                        updateIndicatorSettings(editingIndicator.id, {
                          kPeriod: parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">
                      %D Period
                    </label>
                    <input
                      type="number"
                      value={editingIndicator.settings.dPeriod}
                      onChange={(e) =>
                        updateIndicatorSettings(editingIndicator.id, {
                          dPeriod: parseInt(e.target.value),
                        })
                      }
                      className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600"
                    />
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Charts
