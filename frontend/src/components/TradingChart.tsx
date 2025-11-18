import { useEffect, useRef, useState } from 'react'
import { createChart, IChartApi, ISeriesApi, ColorType, Time } from 'lightweight-charts'
import { TrendingUp, BarChart3, Activity } from 'lucide-react'
import type { Candle } from '../types'

// Types for lightweight-charts v5
type CandlestickData = {
  time: Time
  open: number
  high: number
  low: number
  close: number
}

type LineData = {
  time: Time
  value: number
}

type HistogramData = {
  time: Time
  value: number
  color?: string
}

interface TradingChartProps {
  productId?: string
}

export default function TradingChart({ productId = 'ETH-BTC' }: TradingChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candlestickSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const macdChartRef = useRef<IChartApi | null>(null)
  const macdContainerRef = useRef<HTMLDivElement>(null)

  const [timeframe, setTimeframe] = useState('FIVE_MINUTE')
  const [showVolume, setShowVolume] = useState(true)
  const [showMACD, setShowMACD] = useState(true)
  const [loading, setLoading] = useState(true)

  // Fetch candle data
  const fetchCandles = async (interval: string) => {
    setLoading(true)
    try {
      const response = await fetch(
        `/api/candles?product_id=${productId}&granularity=${interval}&limit=300`
      )

      if (!response.ok) {
        // API error (401, 500, etc) - likely missing credentials
        console.warn('Cannot fetch candles - check Coinbase API credentials in Settings')
        return []
      }

      const data = await response.json()
      return (data.candles || []) as Candle[]
    } catch (error) {
      console.error('Failed to fetch candles:', error)
      return []
    } finally {
      setLoading(false)
    }
  }

  // Calculate MACD
  const calculateMACD = (candles: Candle[], fastPeriod = 12, slowPeriod = 26, signalPeriod = 9) => {
    const closePrices = candles.map(c => c.close)

    // Calculate EMAs
    const calculateEMA = (data: number[], period: number): number[] => {
      const ema: number[] = []
      const multiplier = 2 / (period + 1)

      // First EMA is just the SMA
      let sum = 0
      for (let i = 0; i < period; i++) {
        sum += data[i]
      }
      ema[period - 1] = sum / period

      // Calculate remaining EMAs
      for (let i = period; i < data.length; i++) {
        ema[i] = (data[i] - ema[i - 1]) * multiplier + ema[i - 1]
      }

      return ema
    }

    const fastEMA = calculateEMA(closePrices, fastPeriod)
    const slowEMA = calculateEMA(closePrices, slowPeriod)

    // MACD line = fast EMA - slow EMA
    const macdLine: number[] = []
    for (let i = 0; i < closePrices.length; i++) {
      if (fastEMA[i] !== undefined && slowEMA[i] !== undefined) {
        macdLine[i] = fastEMA[i] - slowEMA[i]
      }
    }

    // Signal line = EMA of MACD line
    const signalLine = calculateEMA(macdLine.filter(v => v !== undefined), signalPeriod)

    // Histogram = MACD - Signal
    const histogram: HistogramData[] = []
    const macdLineData: LineData[] = []
    const signalLineData: LineData[] = []

    for (let i = slowPeriod - 1; i < candles.length; i++) {
      const time = candles[i].time as any
      const macdValue = macdLine[i]
      const signalValue = signalLine[i - (slowPeriod - 1)]

      if (macdValue !== undefined && signalValue !== undefined) {
        const histValue = macdValue - signalValue
        histogram.push({
          time,
          value: histValue,
          color: histValue >= 0 ? 'rgba(38, 166, 154, 0.5)' : 'rgba(239, 83, 80, 0.5)'
        })
        macdLineData.push({ time, value: macdValue })
        signalLineData.push({ time, value: signalValue })
      }
    }

    return { histogram, macdLine: macdLineData, signalLine: signalLineData }
  }

  // Initialize charts
  useEffect(() => {
    if (!chartContainerRef.current) return

    // Main price chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0f172a' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 400,
      rightPriceScale: {
        borderColor: '#334155',
      },
      timeScale: {
        borderColor: '#334155',
        timeVisible: true,
        secondsVisible: false,
      },
    })

    chartRef.current = chart

    // Candlestick series
    const candlestickSeries = chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    })
    candlestickSeriesRef.current = candlestickSeries as any

    // Volume series
    const volumeSeries = chart.addHistogramSeries({
      color: '#26a69a',
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: 'volume',
    })
    volumeSeriesRef.current = volumeSeries as any
    chart.priceScale('volume').applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    })
    volumeSeriesRef.current = volumeSeries

    // MACD chart
    if (macdContainerRef.current) {
      const macdChart = createChart(macdContainerRef.current, {
        layout: {
          background: { type: ColorType.Solid, color: '#0f172a' },
          textColor: '#94a3b8',
        },
        grid: {
          vertLines: { color: '#1e293b' },
          horzLines: { color: '#1e293b' },
        },
        width: macdContainerRef.current.clientWidth,
        height: 150,
        rightPriceScale: {
          borderColor: '#334155',
        },
        timeScale: {
          borderColor: '#334155',
          visible: false,
        },
      })
      macdChartRef.current = macdChart
    }

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
      if (macdContainerRef.current && macdChartRef.current) {
        macdChartRef.current.applyOptions({ width: macdContainerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      if (macdChartRef.current) {
        macdChartRef.current.remove()
      }
    }
  }, [])

  // Load data when timeframe changes
  useEffect(() => {
    const loadData = async () => {
      const candles = await fetchCandles(timeframe)
      if (candles.length === 0) return

      // Update candlestick data
      const candleData: CandlestickData[] = candles.map(c => ({
        time: c.time as any,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
      candlestickSeriesRef.current?.setData(candleData)

      // Update volume data
      if (showVolume) {
        const volumeData: HistogramData[] = candles.map(c => ({
          time: c.time as any,
          value: c.volume,
          color: c.close >= c.open ? 'rgba(38, 166, 154, 0.4)' : 'rgba(239, 83, 80, 0.4)',
        }))
        volumeSeriesRef.current?.setData(volumeData)
      }

      // Update MACD
      if (showMACD && macdChartRef.current) {
        const { histogram, macdLine, signalLine } = calculateMACD(candles)

        // Clear previous series
        macdChartRef.current = createChart(macdContainerRef.current!, {
          layout: {
            background: { type: ColorType.Solid, color: '#0f172a' },
            textColor: '#94a3b8',
          },
          grid: {
            vertLines: { color: '#1e293b' },
            horzLines: { color: '#1e293b' },
          },
          width: macdContainerRef.current!.clientWidth,
          height: 150,
          rightPriceScale: {
            borderColor: '#334155',
          },
          timeScale: {
            borderColor: '#334155',
            visible: false,
          },
        })

        const histogramSeries = macdChartRef.current.addHistogramSeries({
          priceFormat: {
            type: 'price',
            precision: 8,
            minMove: 0.00000001,
          },
        })
        histogramSeries.setData(histogram)

        const macdSeries = macdChartRef.current.addLineSeries({
          color: '#2196f3',
          lineWidth: 2,
          priceFormat: {
            type: 'price',
            precision: 8,
            minMove: 0.00000001,
          },
        })
        macdSeries.setData(macdLine)

        const signalSeries = macdChartRef.current.addLineSeries({
          color: '#ff6b6b',
          lineWidth: 2,
          priceFormat: {
            type: 'price',
            precision: 8,
            minMove: 0.00000001,
          },
        })
        signalSeries.setData(signalLine)
      }
    }

    loadData()
  }, [timeframe, showVolume, showMACD])

  return (
    <div className="space-y-4">
      {/* Chart Controls */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center space-x-2">
          <h3 className="text-xl font-bold">
            {productId} Chart
          </h3>
          {loading && <span className="text-sm text-slate-400">Loading...</span>}
        </div>

        {/* Timeframe Selector */}
        <div className="flex items-center space-x-2">
          {[
            { label: '1m', value: 'ONE_MINUTE' },
            { label: '5m', value: 'FIVE_MINUTE' },
            { label: '15m', value: 'FIFTEEN_MINUTE' },
            { label: '30m', value: 'THIRTY_MINUTE' },
            { label: '1h', value: 'ONE_HOUR' },
            { label: '2h', value: 'TWO_HOUR' },
            { label: '6h', value: 'SIX_HOUR' },
            { label: '1D', value: 'ONE_DAY' },
          ].map((tf) => (
            <button
              key={tf.value}
              onClick={() => setTimeframe(tf.value)}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                timeframe === tf.value
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              {tf.label}
            </button>
          ))}
        </div>

        {/* Indicator Toggles */}
        <div className="flex items-center space-x-3">
          <button
            onClick={() => setShowVolume(!showVolume)}
            className={`flex items-center space-x-1 px-3 py-1 rounded text-sm font-medium transition-colors ${
              showVolume
                ? 'bg-green-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            <span>Volume</span>
          </button>
          <button
            onClick={() => setShowMACD(!showMACD)}
            className={`flex items-center space-x-1 px-3 py-1 rounded text-sm font-medium transition-colors ${
              showMACD
                ? 'bg-purple-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            <Activity className="w-4 h-4" />
            <span>MACD</span>
          </button>
        </div>
      </div>

      {/* Main Price Chart */}
      <div className="card p-0">
        <div ref={chartContainerRef} />
      </div>

      {/* MACD Indicator Chart */}
      {showMACD && (
        <div className="card p-0">
          <div className="px-4 py-2 bg-slate-800/50 border-b border-slate-700">
            <p className="text-sm font-medium text-slate-300">MACD (12, 26, 9)</p>
          </div>
          <div ref={macdContainerRef} />
        </div>
      )}
    </div>
  )
}
