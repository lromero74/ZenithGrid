import { useEffect, useRef, useState } from 'react'
import { X, BarChart2, Search, Settings } from 'lucide-react'
import { createChart, ColorType, IChartApi, ISeriesApi, Time, LineStyle } from 'lightweight-charts'
import axios from 'axios'
import type { Position, Trade } from '../types'
import {
  calculateSMA,
  calculateEMA,
  calculateRSI,
  calculateMACD,
  calculateBollingerBands,
  calculateStochastic,
} from '../utils/indicators/calculations'
import type { CandleData, IndicatorConfig } from '../utils/indicators/types'
import { AVAILABLE_INDICATORS } from '../utils/indicators/definitions'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

interface LightweightChartModalProps {
  isOpen: boolean
  onClose: () => void
  symbol: string
  position?: Position | null
}

const TIMEFRAMES = [
  { label: '1m', value: 'ONE_MINUTE' },
  { label: '5m', value: 'FIVE_MINUTE' },
  { label: '15m', value: 'FIFTEEN_MINUTE' },
  { label: '30m', value: 'THIRTY_MINUTE' },
  { label: '1h', value: 'ONE_HOUR' },
  { label: '2h', value: 'TWO_HOUR' },
  { label: '6h', value: 'SIX_HOUR' },
  { label: '1d', value: 'ONE_DAY' },
]

export default function LightweightChartModal({
  isOpen,
  onClose,
  symbol,
  position
}: LightweightChartModalProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const mainSeriesRef = useRef<ISeriesApi<any> | null>(null)
  const indicatorSeriesRef = useRef<Map<string, ISeriesApi<any>[]>>(new Map())
  const indicatorChartsRef = useRef<Map<string, IChartApi>>(new Map())
  const positionLinesRef = useRef<ISeriesApi<any>[]>([])
  const candleDataRef = useRef<CandleData[]>([])
  const isCleanedUpRef = useRef<boolean>(false)

  const [timeframe, setTimeframe] = useState('FIFTEEN_MINUTE')
  const [chartData, setChartData] = useState<CandleData[]>([])
  const [chartType, setChartType] = useState<'candlestick' | 'bar' | 'line' | 'area' | 'baseline'>('candlestick')
  const [useHeikinAshi, setUseHeikinAshi] = useState(false)
  const [indicators, setIndicators] = useState<IndicatorConfig[]>([])
  const [showIndicatorModal, setShowIndicatorModal] = useState(false)
  const [indicatorSearch, setIndicatorSearch] = useState('')
  const [editingIndicator, setEditingIndicator] = useState<IndicatorConfig | null>(null)

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = 'unset'
    }

    return () => {
      document.body.style.overflow = 'unset'
    }
  }, [isOpen])

  // Fetch candle data
  useEffect(() => {
    if (!isOpen || !symbol) return

    const fetchCandles = async () => {
      try {
        const response = await axios.get(`${API_BASE}/api/candles`, {
          params: {
            product_id: symbol,
            granularity: timeframe,
            limit: 300,
          },
        })

        const candles = response.data.candles || []
        const formattedCandles = candles
          .map((c: any) => ({
            // API returns 'time' as Unix timestamp, not 'start' as ISO string
            time: (typeof c.time === 'number' ? c.time : Math.floor(new Date(c.start || c.time).getTime() / 1000)) as Time,
            open: parseFloat(c.open),
            high: parseFloat(c.high),
            low: parseFloat(c.low),
            close: parseFloat(c.close),
            volume: parseFloat(c.volume || 0),
          }))
          .filter((c: CandleData) =>
            !isNaN(c.time as number) &&
            !isNaN(c.open) &&
            !isNaN(c.high) &&
            !isNaN(c.low) &&
            !isNaN(c.close)
          )
          .sort((a: CandleData, b: CandleData) => (a.time as number) - (b.time as number))

        candleDataRef.current = formattedCandles
        setChartData(formattedCandles)
      } catch (error) {
        console.error('Error fetching candles:', error)
      }
    }

    fetchCandles()
  }, [isOpen, symbol, timeframe])

  // Initialize chart
  useEffect(() => {
    if (!isOpen || !chartContainerRef.current || chartData.length === 0) return
    if (chartRef.current) return // Already initialized

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
      height: 500,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: '#334155',
        scaleMargins: { top: 0.1, bottom: 0.2 },
        autoScale: true,
      },
    })

    chartRef.current = chart

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chart) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      isCleanedUpRef.current = true
      window.removeEventListener('resize', handleResize)
      if (chartRef.current) {
        chartRef.current.remove()
        chartRef.current = null
      }
    }
  }, [isOpen, chartData])

  // Render main chart series
  useEffect(() => {
    if (!chartRef.current || isCleanedUpRef.current) return
    if (chartData.length === 0) return

    // Remove existing main series
    if (mainSeriesRef.current) {
      try {
        chartRef.current.removeSeries(mainSeriesRef.current)
      } catch (e) {
        // Series might already be removed
      }
      mainSeriesRef.current = null
    }

    const isBTCPair = symbol.endsWith('-BTC')
    const priceFormat = isBTCPair
      ? { type: 'price' as const, precision: 8, minMove: 0.00000001 }
      : { type: 'price' as const, precision: 2, minMove: 0.01 }

    let data = chartData

    // Apply Heikin-Ashi if enabled
    if (useHeikinAshi) {
      data = calculateHeikinAshi(chartData)
    }

    // Create appropriate series based on chart type
    if (chartType === 'candlestick') {
      const series = chartRef.current.addCandlestickSeries({
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderVisible: false,
        wickUpColor: '#26a69a',
        wickDownColor: '#ef5350',
        priceFormat,
        priceScaleId: 'right',
      })
      series.setData(data)
      mainSeriesRef.current = series
    } else if (chartType === 'bar') {
      const series = chartRef.current.addBarSeries({
        upColor: '#26a69a',
        downColor: '#ef5350',
        priceFormat,
        priceScaleId: 'right',
      })
      series.setData(data)
      mainSeriesRef.current = series
    } else if (chartType === 'line') {
      const series = chartRef.current.addLineSeries({
        color: '#2196F3',
        lineWidth: 2,
        priceFormat,
        priceScaleId: 'right',
      })
      series.setData(data.map(d => ({ time: d.time, value: d.close })))
      mainSeriesRef.current = series
    } else if (chartType === 'area') {
      const series = chartRef.current.addAreaSeries({
        topColor: 'rgba(33, 150, 243, 0.56)',
        bottomColor: 'rgba(33, 150, 243, 0.04)',
        lineColor: 'rgba(33, 150, 243, 1)',
        lineWidth: 2,
        priceFormat,
        priceScaleId: 'right',
      })
      series.setData(data.map(d => ({ time: d.time, value: d.close })))
      mainSeriesRef.current = series
    } else if (chartType === 'baseline') {
      const baseValue = position?.average_buy_price || data[0]?.close || 0
      const series = chartRef.current.addBaselineSeries({
        baseValue: { type: 'price', price: baseValue },
        topLineColor: '#26a69a',
        topFillColor1: 'rgba(38, 166, 154, 0.28)',
        topFillColor2: 'rgba(38, 166, 154, 0.05)',
        bottomLineColor: '#ef5350',
        bottomFillColor1: 'rgba(239, 83, 80, 0.05)',
        bottomFillColor2: 'rgba(239, 83, 80, 0.28)',
        priceFormat,
        priceScaleId: 'right',
      })
      series.setData(data.map(d => ({ time: d.time, value: d.close })))
      mainSeriesRef.current = series
    }

    // Ensure right price scale is visible and properly configured
    chartRef.current.priceScale('right').applyOptions({
      borderColor: '#334155',
      visible: true,
    })

    // Add position reference lines if we have position data
    if (position && mainSeriesRef.current) {
      addPositionLines()
    }

    // Add markers
    if (position && mainSeriesRef.current) {
      addMarkers()
    }

    chartRef.current.timeScale().fitContent()
  }, [chartData, chartType, useHeikinAshi, position, symbol])

  // Render indicators on chart
  useEffect(() => {
    if (!chartRef.current || chartData.length === 0 || !mainSeriesRef.current) return
    if (indicators.length === 0) return  // Only run if we have indicators to render

    // Clear existing indicator series
    indicatorSeriesRef.current.forEach((seriesList) => {
      seriesList.forEach((series) => {
        try {
          chartRef.current?.removeSeries(series)
        } catch (e) {
          // Series may already be removed
        }
      })
    })
    indicatorSeriesRef.current.clear()

    // Render each indicator
    indicators.forEach((indicator) => {
      const closes = chartData.map(c => c.close)
      const highs = chartData.map(c => c.high)
      const lows = chartData.map(c => c.low)

      if (indicator.type === 'sma') {
        const period = indicator.settings.period || 20
        const smaValues = calculateSMA(closes, period)
        const smaData = chartData
          .map((c, i) => ({ time: c.time, value: smaValues[i] ?? 0 }))
          .filter((d, i) => smaValues[i] !== null)

        const smaSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.color || '#FF9800',
          lineWidth: 2,
          title: `SMA(${period})`,
          priceScaleId: 'right',
        })
        smaSeries.setData(smaData)
        indicatorSeriesRef.current.set(indicator.id, [smaSeries])

      } else if (indicator.type === 'ema') {
        const period = indicator.settings.period || 12
        const emaValues = calculateEMA(closes, period)
        const emaData = chartData
          .map((c, i) => ({ time: c.time, value: emaValues[i] ?? 0 }))
          .filter((d, i) => emaValues[i] !== null)

        const emaSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.color || '#9C27B0',
          lineWidth: 2,
          title: `EMA(${period})`,
          priceScaleId: 'right',
        })
        emaSeries.setData(emaData)
        indicatorSeriesRef.current.set(indicator.id, [emaSeries])

      } else if (indicator.type === 'bollinger') {
        const period = indicator.settings.period || 20
        const stdDev = indicator.settings.stdDev || 2
        const bands = calculateBollingerBands(closes, period, stdDev)

        const upperData = chartData
          .map((c, i) => ({ time: c.time, value: bands.upper[i] ?? 0 }))
          .filter((d, i) => bands.upper[i] !== null)
        const middleData = chartData
          .map((c, i) => ({ time: c.time, value: bands.middle[i] ?? 0 }))
          .filter((d, i) => bands.middle[i] !== null)
        const lowerData = chartData
          .map((c, i) => ({ time: c.time, value: bands.lower[i] ?? 0 }))
          .filter((d, i) => bands.lower[i] !== null)

        const upperSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.upperColor || '#2196F3',
          lineWidth: 1,
          title: `BB Upper(${period})`,
          priceScaleId: 'right',
        })
        upperSeries.setData(upperData)

        const middleSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.middleColor || '#FF9800',
          lineWidth: 1,
          title: `BB Middle(${period})`,
          priceScaleId: 'right',
        })
        middleSeries.setData(middleData)

        const lowerSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.lowerColor || '#2196F3',
          lineWidth: 1,
          title: `BB Lower(${period})`,
          priceScaleId: 'right',
        })
        lowerSeries.setData(lowerData)

        indicatorSeriesRef.current.set(indicator.id, [upperSeries, middleSeries, lowerSeries])

      } else if (indicator.type === 'rsi') {
        const period = indicator.settings.period || 14
        const rsiValues = calculateRSI(closes, period)
        const rsiData = chartData
          .map((c, i) => ({ time: c.time, value: rsiValues[i] ?? 0 }))
          .filter((d, i) => rsiValues[i] !== null)

        const rsiSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.color || '#2196F3',
          lineWidth: 2,
          title: `RSI(${period})`,
          priceScaleId: 'rsi',
        })
        rsiSeries.setData(rsiData)

        // Configure RSI scale with 0-100 range and positioned at bottom
        chartRef.current!.priceScale('rsi').applyOptions({
          scaleMargins: { top: 0.8, bottom: 0 },
          borderColor: '#334155',
          visible: true,
          autoScale: false,  // Don't auto-scale, use fixed range
        })

        // Add horizontal lines for overbought/oversold levels
        const overbought = indicator.settings.overbought || 70
        const oversold = indicator.settings.oversold || 30

        const overboughtSeries = chartRef.current!.addLineSeries({
          color: 'rgba(239, 83, 80, 0.5)',
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          priceScaleId: 'rsi',
          lastValueVisible: false,
          priceLineVisible: false,
        })
        overboughtSeries.setData(chartData.map(c => ({ time: c.time, value: overbought })))

        const oversoldSeries = chartRef.current!.addLineSeries({
          color: 'rgba(38, 166, 154, 0.5)',
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          priceScaleId: 'rsi',
          lastValueVisible: false,
          priceLineVisible: false,
        })
        oversoldSeries.setData(chartData.map(c => ({ time: c.time, value: oversold })))

        indicatorSeriesRef.current.set(indicator.id, [rsiSeries, overboughtSeries, oversoldSeries])

      } else if (indicator.type === 'macd') {
        const fastPeriod = indicator.settings.fastPeriod || 12
        const slowPeriod = indicator.settings.slowPeriod || 26
        const signalPeriod = indicator.settings.signalPeriod || 9
        const macdResult = calculateMACD(closes, fastPeriod, slowPeriod, signalPeriod)

        const macdData = chartData
          .map((c, i) => ({ time: c.time, value: macdResult.macd[i] ?? 0 }))
          .filter((d, i) => macdResult.macd[i] !== null)
        const signalData = chartData
          .map((c, i) => ({ time: c.time, value: macdResult.signal[i] ?? 0 }))
          .filter((d, i) => macdResult.signal[i] !== null)
        const histogramData = chartData
          .map((c, i) => ({ time: c.time, value: macdResult.histogram[i] ?? 0 }))
          .filter((d, i) => macdResult.histogram[i] !== null)

        // MACD line
        const macdSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.macdColor || '#2196F3',
          lineWidth: 2,
          title: 'MACD',
          priceScaleId: 'macd',
        })
        macdSeries.setData(macdData)

        // Signal line
        const signalSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.signalColor || '#FF5722',
          lineWidth: 2,
          title: 'Signal',
          priceScaleId: 'macd',
        })
        signalSeries.setData(signalData)

        // Histogram (as line series for now - lightweight-charts doesn't have native histogram)
        const histogramSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.histogramColor || '#4CAF50',
          lineWidth: 2,
          title: 'Histogram',
          priceScaleId: 'macd',
        })
        histogramSeries.setData(histogramData)

        // Configure MACD scale positioned above RSI if present
        chartRef.current!.priceScale('macd').applyOptions({
          scaleMargins: { top: 0.6, bottom: 0.2 },
          borderColor: '#334155',
          visible: true,
        })

        indicatorSeriesRef.current.set(indicator.id, [macdSeries, signalSeries, histogramSeries])
      }
      // Note: Stochastic would need a separate pane as well
    })

    // Ensure right price scale remains visible after adding indicators
    if (chartRef.current) {
      chartRef.current.priceScale('right').applyOptions({
        borderColor: '#334155',
        visible: true,
      })
    }
  }, [indicators, chartData, chartType, useHeikinAshi])

  // Add position reference lines
  const addPositionLines = () => {
    if (!chartRef.current || !position) return

    // Clear existing position lines
    positionLinesRef.current.forEach(series => {
      try {
        chartRef.current?.removeSeries(series)
      } catch (e) {
        // Series may already be removed
      }
    })
    positionLinesRef.current = []

    const avgBuyPrice = position.average_buy_price

    // Get profit target from strategy config (min_profit_percentage or take_profit_percentage)
    const profitTarget = position.strategy_config_snapshot?.min_profit_percentage
      || position.strategy_config_snapshot?.take_profit_percentage
      || position.bot_config?.min_profit_percentage
      || position.bot_config?.take_profit_percentage
      || 2.0  // Default to 2% if not configured
    const targetPrice = avgBuyPrice * (1 + profitTarget / 100)

    // Entry price line (orange)
    const entrySeries = chartRef.current.addLineSeries({
      color: '#f59e0b',
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
      title: 'Entry',
      priceLineVisible: false,
      lastValueVisible: false,
    })
    const entryData = chartData.map(d => ({ time: d.time, value: avgBuyPrice }))
    entrySeries.setData(entryData)
    positionLinesRef.current.push(entrySeries)

    // Target price line (green)
    const targetSeries = chartRef.current.addLineSeries({
      color: '#10b981',
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
      title: `Target (${profitTarget}%)`,
      priceLineVisible: false,
      lastValueVisible: false,
    })
    const targetData = chartData.map(d => ({ time: d.time, value: targetPrice }))
    targetSeries.setData(targetData)
    positionLinesRef.current.push(targetSeries)

    // Safety order lines (blue) if configured
    if (position.bot_config?.safety_order_step_percentage && position.bot_config?.max_safety_orders) {
      const stepPercentage = position.bot_config.safety_order_step_percentage
      const maxSOs = Math.min(position.bot_config.max_safety_orders, 5) // Limit to 5 lines

      for (let i = 1; i <= maxSOs; i++) {
        const deviation = stepPercentage * i
        const soPrice = avgBuyPrice * (1 - deviation / 100)

        const soSeries = chartRef.current!.addLineSeries({
          color: '#3b82f6',
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          title: `SO${i}`,
          priceLineVisible: false,
          lastValueVisible: false,
        })
        const soData = chartData.map(d => ({ time: d.time, value: soPrice }))
        soSeries.setData(soData)
        positionLinesRef.current.push(soSeries)
      }
    }
  }

  // Add markers for entry and current price
  const addMarkers = () => {
    if (!mainSeriesRef.current || !position || chartData.length === 0) return

    const markers: any[] = []

    // Entry marker
    if (position.opened_at) {
      const openedTime = Math.floor(new Date(position.opened_at).getTime() / 1000)
      const nearestCandle = chartData.reduce((prev, curr) =>
        Math.abs((curr.time as number) - openedTime) < Math.abs((prev.time as number) - openedTime) ? curr : prev
      )

      if (nearestCandle) {
        markers.push({
          time: nearestCandle.time,
          position: 'belowBar' as const,
          color: '#10b981',
          shape: 'arrowUp' as const,
          text: 'Entry',
        })
      }
    }

    // Current price marker
    const lastCandle = chartData[chartData.length - 1]
    if (lastCandle) {
      markers.push({
        time: lastCandle.time,
        position: 'inBar' as const,
        color: '#3b82f6',
        shape: 'circle' as const,
        text: 'Now',
      })
    }

    mainSeriesRef.current.setMarkers(markers)
  }

  // Calculate Heikin-Ashi candles
  const calculateHeikinAshi = (candles: CandleData[]): CandleData[] => {
    if (candles.length === 0) return []

    const haCandles: CandleData[] = []
    let prevHA = { ...candles[0] }

    for (const candle of candles) {
      const haClose = (candle.open + candle.high + candle.low + candle.close) / 4
      const haOpen = (prevHA.open + prevHA.close) / 2
      const haHigh = Math.max(candle.high, haOpen, haClose)
      const haLow = Math.min(candle.low, haOpen, haClose)

      const haCandle = {
        time: candle.time,
        open: haOpen,
        high: haHigh,
        low: haLow,
        close: haClose,
      }

      haCandles.push(haCandle)
      prevHA = haCandle
    }

    return haCandles
  }

  // Filter indicators by search
  const filteredIndicators = AVAILABLE_INDICATORS.filter(ind =>
    ind.name.toLowerCase().includes(indicatorSearch.toLowerCase()) ||
    ind.description.toLowerCase().includes(indicatorSearch.toLowerCase())
  )

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 rounded-lg w-full h-full max-w-[95vw] max-h-[95vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div className="flex items-center gap-4">
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <BarChart2 size={24} />
              Chart
            </h2>
            <div className="text-sm text-slate-400">{symbol}</div>

            {position && (() => {
              const profitTarget = position.strategy_config_snapshot?.min_profit_percentage
                || position.strategy_config_snapshot?.take_profit_percentage
                || position.bot_config?.min_profit_percentage
                || position.bot_config?.take_profit_percentage
                || 2.0
              const targetPrice = position.average_buy_price * (1 + profitTarget / 100)

              return (
                <div className="flex items-center gap-3 text-xs">
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-0.5 bg-orange-500"></div>
                    <span className="text-slate-400">Entry:</span>
                    <span className="text-orange-400 font-semibold">{position.average_buy_price?.toFixed(8)}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-0.5 bg-green-500"></div>
                    <span className="text-slate-400">Target ({profitTarget}%):</span>
                    <span className="text-green-400 font-semibold">{targetPrice?.toFixed(8)}</span>
                  </div>
                  {position.bot_config?.safety_order_step_percentage && (
                    <div className="flex items-center gap-1.5">
                      <div className="w-3 h-0.5 bg-blue-500"></div>
                      <span className="text-slate-400">Next SO:</span>
                      <span className="text-blue-400 font-semibold">
                        {(position.average_buy_price * (1 - position.bot_config.safety_order_step_percentage / 100))?.toFixed(8)}
                      </span>
                    </div>
                  )}
                </div>
              )
            })()}
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors p-2"
          >
            <X size={24} />
          </button>
        </div>

        {/* Chart Controls */}
        <div className="flex items-center gap-3 p-3 border-b border-slate-700 flex-wrap">
          {/* Timeframe Selector */}
          <div className="flex gap-1">
            {TIMEFRAMES.map(tf => (
              <button
                key={tf.value}
                onClick={() => setTimeframe(tf.value)}
                className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                  timeframe === tf.value
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {tf.label}
              </button>
            ))}
          </div>

          <div className="w-px h-6 bg-slate-600" />

          {/* Chart Type Selector */}
          <div className="flex gap-1">
            {['candlestick', 'bar', 'line', 'area', 'baseline'].map(type => (
              <button
                key={type}
                onClick={() => setChartType(type as any)}
                className={`px-2 py-1 rounded text-xs font-medium transition-colors capitalize ${
                  chartType === type
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {type === 'candlestick' ? <BarChart2 size={14} /> : type}
              </button>
            ))}
          </div>

          <div className="w-px h-6 bg-slate-600" />

          {/* Heikin-Ashi Toggle */}
          <button
            onClick={() => setUseHeikinAshi(!useHeikinAshi)}
            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
              useHeikinAshi
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            Heikin-Ashi
          </button>

          {/* Indicators Button */}
          <button
            onClick={() => setShowIndicatorModal(true)}
            className="px-2 py-1 rounded text-xs font-medium transition-colors bg-slate-700 text-slate-300 hover:bg-slate-600"
          >
            Indicators ({indicators.length})
          </button>
        </div>

        {/* Chart Container */}
        <div className="flex-1 relative p-4 overflow-hidden">
          <div ref={chartContainerRef} className="w-full h-full" />
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-slate-700 text-xs text-slate-500">
          <p>
            💡 Full-featured chart with position markers and reference lines. Add indicators, change timeframes, and analyze your trades.
          </p>
        </div>
      </div>

      {/* Indicator Modal */}
      {showIndicatorModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]">
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
                  {categoryIndicators.map((ind) => {
                    const alreadyAdded = indicators.some(i => i.type === ind.id)
                    return (
                      <button
                        key={ind.id}
                        onClick={() => {
                          if (alreadyAdded) {
                            // Remove indicator
                            setIndicators(indicators.filter(i => i.type !== ind.id))
                          } else {
                            // Add indicator with default settings
                            const newIndicator: IndicatorConfig = {
                              id: `${ind.id}-${Date.now()}`,
                              type: ind.id,
                              settings: ind.defaultSettings
                            }
                            setIndicators([...indicators, newIndicator])
                          }
                          setShowIndicatorModal(false)
                        }}
                        className={`w-full text-left p-3 rounded transition-colors mb-2 ${
                          alreadyAdded
                            ? 'bg-blue-600 hover:bg-blue-700'
                            : 'bg-slate-700 hover:bg-slate-600'
                        }`}
                      >
                        <div className="font-semibold text-white flex items-center justify-between">
                          {ind.name}
                          {alreadyAdded && <span className="text-xs">✓ Added</span>}
                        </div>
                        <div className="text-xs text-slate-400">{ind.description}</div>
                      </button>
                    )
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
