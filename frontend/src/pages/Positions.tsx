import { useQuery } from '@tanstack/react-query'
import { positionsApi, botsApi } from '../services/api'
import { format } from 'date-fns'
import { useState, useEffect, useRef } from 'react'
import { formatDateTime, formatDateTimeCompact } from '../utils/dateFormat'
import {
  TrendingUp,
  TrendingDown,
  ChevronDown,
  ChevronUp,
  X,
  Plus,
  AlertCircle,
  BarChart3,
  Brain,
  Activity,
  Settings,
  Search,
  BarChart2
} from 'lucide-react'
import { createChart, ColorType, IChartApi, ISeriesApi, Time } from 'lightweight-charts'
import axios from 'axios'
import type { Position, Trade } from '../types'
import PositionLogsModal from '../components/PositionLogsModal'
import {
  calculateSMA,
  calculateEMA,
  calculateRSI,
  calculateMACD,
  calculateBollingerBands,
  calculateStochastic,
  calculateHeikinAshi,
  AVAILABLE_INDICATORS,
  TIME_INTERVALS,
  type CandleData
} from '../utils/indicators'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface IndicatorConfig {
  id: string
  name: string
  type: string
  enabled: boolean
  settings: Record<string, any>
  color?: string
  series?: ISeriesApi<any>[]
}

type LineData = {
  time: Time
  value: number
}


// Deal Chart Component with full Charts page functionality
function DealChart({ position, productId: initialProductId, currentPrice }: { position: Position, productId: string, currentPrice?: number }) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const mainSeriesRef = useRef<ISeriesApi<any> | null>(null)
  const indicatorSeriesRef = useRef<Map<string, ISeriesApi<any>[]>>(new Map())
  const indicatorChartsRef = useRef<Map<string, IChartApi>>(new Map())
  const candleDataRef = useRef<CandleData[]>([])
  const isCleanedUpRef = useRef<boolean>(false)
  const lastUpdateRef = useRef<string>('')

  // State for chart controls
  const [selectedPair, setSelectedPair] = useState(initialProductId)
  const [timeframe, setTimeframe] = useState('FIFTEEN_MINUTE')
  const [chartData, setChartData] = useState<CandleData[]>([])
  const [chartType, setChartType] = useState<'candlestick' | 'bar' | 'line' | 'area' | 'baseline'>('candlestick')
  const [useHeikinAshi, setUseHeikinAshi] = useState(false)
  const [indicators, setIndicators] = useState<IndicatorConfig[]>([])
  const [showIndicatorModal, setShowIndicatorModal] = useState(false)
  const [indicatorSearch, setIndicatorSearch] = useState('')
  const [editingIndicator, setEditingIndicator] = useState<IndicatorConfig | null>(null)

  // Fetch bot configuration
  const { data: bot } = useQuery({
    queryKey: ['bot', position.bot_id],
    queryFn: () => position.bot_id ? botsApi.getById(position.bot_id) : null,
    enabled: !!position.bot_id,
  })

  // Fetch bot pairs for pair selector
  const { data: botPairs } = useQuery({
    queryKey: ['bot-pairs', position.bot_id],
    queryFn: async () => {
      if (!position.bot_id) return []
      const botData = await botsApi.getById(position.bot_id)
      return (botData as any).pairs || []
    },
    enabled: !!position.bot_id,
  })

  // Fetch candle data
  useEffect(() => {
    const fetchCandles = async () => {
      try {
        const response = await axios.get(`${API_BASE}/api/candles`, {
          params: {
            product_id: selectedPair,
            granularity: timeframe,
            limit: 300,
          },
        })
        const candles = response.data.candles || []
        setChartData(candles)
        candleDataRef.current = candles
      } catch (err) {
        console.error('Error fetching candles:', err)
      }
    }
    fetchCandles()
  }, [selectedPair, timeframe])

  // Initialize main chart
  useEffect(() => {
    if (!chartContainerRef.current) return

    isCleanedUpRef.current = false

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
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: '#334155',
        scaleMargins: {
          top: 0.1,
          bottom: 0.2,
        },
        autoScale: true,
      },
    })

    chartRef.current = chart

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
    lastUpdateRef.current = ''
  }

  // Remove indicator
  const removeIndicator = (indicatorId: string) => {
    const series = indicatorSeriesRef.current.get(indicatorId)
    if (series) {
      series.forEach(s => {
        try {
          if (chartRef.current) {
            chartRef.current.removeSeries(s)
          }
        } catch (e) {
          // Series may have already been removed
        }
      })
      indicatorSeriesRef.current.delete(indicatorId)
    }

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
    if (!chartRef.current || !candles.length || isCleanedUpRef.current) return

    const isBTCPair = selectedPair.endsWith('-BTC')
    const priceFormat = isBTCPair
      ? { type: 'price' as const, precision: 8, minMove: 0.00000001 }
      : { type: 'price' as const, precision: 2, minMove: 0.01 }

    const closes = candles.map(c => c.close)
    // Highs/lows would be used for Stochastic indicator when implemented
    // const highs = candles.map(c => c.high)
    // const lows = candles.map(c => c.low)

    indicators.forEach(indicator => {
      if (!indicator.enabled) return

      // Remove old series
      const oldSeries = indicatorSeriesRef.current.get(indicator.id)
      if (oldSeries) {
        oldSeries.forEach(series => {
          try {
            if (indicator.type === 'rsi' || indicator.type === 'macd' || indicator.type === 'stochastic') {
              const indicatorChart = indicatorChartsRef.current.get(indicator.id)
              if (indicatorChart) {
                indicatorChart.removeSeries(series)
              }
            } else {
              if (chartRef.current) {
                chartRef.current.removeSeries(series)
              }
            }
          } catch (e) {
            // Series may have already been removed
          }
        })
        indicatorSeriesRef.current.delete(indicator.id)
      }

      const newSeries: ISeriesApi<any>[] = []

      if (indicator.type === 'sma') {
        const smaValues = calculateSMA(closes, indicator.settings.period)
        const smaData: LineData[] = []
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
        const emaData: LineData[] = []
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

        const upperLineData: LineData[] = []
        const middleLineData: LineData[] = []
        const lowerLineData: LineData[] = []

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

      // Save series to ref
      if (newSeries.length > 0) {
        indicatorSeriesRef.current.set(indicator.id, newSeries)
      }
    })
  }

  // Update chart with data, indicators, and position lines
  useEffect(() => {
    if (!chartRef.current || !mainSeriesRef.current || chartData.length === 0 || isCleanedUpRef.current) return

    const displayCandles = useHeikinAshi ? calculateHeikinAshi(chartData) : chartData

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

    try {
      mainSeriesRef.current.setData(priceData as any)

      // Render indicators
      if (indicators.length > 0) {
        renderIndicators(chartData)
      }

      // Add entry/profit/loss lines
      const isBTCPair = selectedPair.endsWith('-BTC')
      const priceFormat = isBTCPair
        ? { type: 'price' as const, precision: 8, minMove: 0.00000001 }
        : { type: 'price' as const, precision: 2, minMove: 0.01 }

      // Entry price line
      const entryLineSeries = chartRef.current.addLineSeries({
        color: '#3b82f6',
        lineWidth: 2,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        title: 'Entry',
        priceFormat: priceFormat,
      })

      const entryLineData = chartData.map((c) => ({
        time: c.time as Time,
        value: position.average_buy_price,
      }))

      entryLineSeries.setData(entryLineData)

      // Take Profit line
      const takeProfitPrice = position.average_buy_price * 1.02
      const takeProfitSeries = chartRef.current.addLineSeries({
        color: '#10b981',
        lineWidth: 2,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        title: 'TP',
        priceFormat: priceFormat,
      })

      takeProfitSeries.setData(chartData.map((c) => ({
        time: c.time as Time,
        value: takeProfitPrice,
      })))

      // Stop Loss line (only if position is open)
      if (position.status === 'open') {
        const stopLossPrice = position.average_buy_price * 0.98
        const stopLossSeries = chartRef.current.addLineSeries({
          color: '#ef4444',
          lineWidth: 2,
          lineStyle: 2,
          priceLineVisible: false,
          lastValueVisible: true,
          title: 'SL',
          priceFormat: priceFormat,
        })

        stopLossSeries.setData(chartData.map((c) => ({
          time: c.time as Time,
          value: stopLossPrice,
        })))
      }

      // Safety Order price levels
      if (bot && position.status === 'open') {
        const config = bot.strategy_config
        const priceDeviation = config.price_deviation || 2.0
        const stepScale = config.safety_order_step_scale || 1.0
        const maxSafetyOrders = config.max_safety_orders || 5

        let cumulativeDeviation = priceDeviation
        for (let i = 0; i < maxSafetyOrders; i++) {
          const soPrice = position.average_buy_price * (1 - cumulativeDeviation / 100)

          const soSeries = chartRef.current.addLineSeries({
            color: '#64748b',
            lineWidth: 1,
            lineStyle: 2,
            priceLineVisible: false,
            lastValueVisible: false,
            title: `SO${i + 1}`,
            priceFormat: priceFormat,
          })

          soSeries.setData(chartData.map((c) => ({
            time: c.time as Time,
            value: soPrice,
          })))

          cumulativeDeviation += priceDeviation * Math.pow(stepScale, i)
        }
      }

      // Add markers
      if (chartType === 'candlestick' || chartType === 'bar') {
        const markers: any[] = []

        // Current price marker
        if (chartData.length > 0) {
          const lastCandle = chartData[chartData.length - 1]
          markers.push({
            time: lastCandle.time as Time,
            position: 'inBar',
            color: '#3b82f6',
            shape: 'circle',
            text: 'Now',
          })
        }

        // Entry marker
        const openedTime = Math.floor(new Date(position.opened_at).getTime() / 1000)
        const nearestCandle = chartData.reduce((prev, curr) =>
          Math.abs(curr.time - openedTime) < Math.abs(prev.time - openedTime) ? curr : prev
        )

        if (nearestCandle) {
          markers.push({
            time: nearestCandle.time as Time,
            position: 'belowBar',
            color: '#10b981',
            shape: 'arrowUp',
            text: 'Entry',
          })
        }

        mainSeriesRef.current.setMarkers(markers)
      }

      chartRef.current.timeScale().fitContent()
    } catch (e) {
      return
    }
  }, [chartData, chartType, useHeikinAshi, indicators, position, bot, selectedPair])

  // Create oscillator indicator charts
  useEffect(() => {
    const oscillators = indicators.filter(i => ['rsi', 'macd', 'stochastic'].includes(i.type))

    oscillators.forEach(indicator => {
      if (indicatorChartsRef.current.has(indicator.id)) return

      const container = document.getElementById(`deal-indicator-chart-${indicator.id}`)
      if (!container) return

      const chart = createChart(container, {
        layout: {
          background: { type: ColorType.Solid, color: '#0f172a' },
          textColor: '#94a3b8',
        },
        grid: {
          vertLines: { color: '#1e293b' },
          horzLines: { color: '#1e293b' },
        },
        width: container.clientWidth,
        height: 150,
        timeScale: {
          timeVisible: true,
          secondsVisible: false,
          visible: false,
        },
      })

      indicatorChartsRef.current.set(indicator.id, chart)
    })

    const existingOscillatorIds = new Set(oscillators.map(i => i.id))
    indicatorChartsRef.current.forEach((chart, id) => {
      if (!existingOscillatorIds.has(id)) {
        try {
          chart.remove()
        } catch (e) {
          // Chart may have already been removed
        }
        indicatorChartsRef.current.delete(id)
      }
    })
  }, [indicators])

  const filteredIndicators = AVAILABLE_INDICATORS.filter(ind =>
    ind.name.toLowerCase().includes(indicatorSearch.toLowerCase()) ||
    ind.category.toLowerCase().includes(indicatorSearch.toLowerCase())
  )

  // Calculate gain/loss info
  const calculateGainLoss = () => {
    const currentPriceValue = currentPrice || (chartData.length > 0 ? chartData[chartData.length - 1].close : 0)
    const entryPrice = position.average_buy_price
    const profitTarget = entryPrice * 1.02
    const profitLoss = currentPriceValue - entryPrice
    const profitLossPercent = ((currentPriceValue - entryPrice) / entryPrice) * 100
    const toTargetPercent = ((profitTarget - currentPriceValue) / currentPriceValue) * 100

    return {
      currentPrice: currentPriceValue,
      entryPrice,
      profitTarget,
      profitLoss,
      profitLossPercent,
      toTargetPercent,
      isProfit: profitLoss > 0
    }
  }

  const gainLoss = calculateGainLoss()

  return (
    <div className="space-y-3">
      {/* Chart Controls */}
      <div className="bg-slate-800 rounded-lg p-3 space-y-3">
        {/* Pair Selector */}
        <div className="flex items-center gap-3 flex-wrap">
          <h4 className="font-semibold text-white flex items-center gap-2">
            <BarChart3 size={18} />
            Chart
          </h4>

          <select
            value={selectedPair}
            onChange={(e) => setSelectedPair(e.target.value)}
            className="bg-slate-700 text-white px-3 py-1.5 rounded text-sm font-medium border border-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {botPairs && botPairs.length > 0 ? (
              botPairs.map((pair: string) => (
                <option key={pair} value={pair}>
                  {pair.replace('-', '/')}
                </option>
              ))
            ) : (
              <option value={initialProductId}>{initialProductId.replace('-', '/')}</option>
            )}
          </select>

          <div className="w-px h-6 bg-slate-600" />

          {/* Chart Type Buttons */}
          <div className="flex gap-1">
            <button
              onClick={() => setChartType('candlestick')}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                chartType === 'candlestick'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
              title="Candlestick"
            >
              <BarChart2 size={14} />
            </button>
            <button
              onClick={() => setChartType('bar')}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
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
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
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
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
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
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                chartType === 'baseline'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
              title="Baseline"
            >
              Base
            </button>
          </div>

          <div className="w-px h-6 bg-slate-600" />

          {/* Heikin-Ashi Toggle */}
          <button
            onClick={() => setUseHeikinAshi(!useHeikinAshi)}
            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
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
            className="bg-slate-700 text-slate-300 hover:bg-slate-600 px-2 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1"
          >
            <Activity size={14} />
            Indicators
          </button>

          <div className="flex-1" />

          {/* Time Interval Buttons */}
          <div className="flex gap-1">
            {TIME_INTERVALS.map((interval) => (
              <button
                key={interval.value}
                onClick={() => setTimeframe(interval.value)}
                className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                  timeframe === interval.value
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {interval.label}
              </button>
            ))}
          </div>
        </div>

        {/* Active Indicators */}
        {indicators.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            {indicators.map((indicator) => (
              <div
                key={indicator.id}
                className="flex items-center gap-1.5 bg-slate-700 px-2 py-1 rounded text-xs"
              >
                <span className="text-white font-medium">{indicator.name}</span>
                <button
                  onClick={() => setEditingIndicator(indicator)}
                  className="text-slate-400 hover:text-white transition-colors"
                >
                  <Settings size={12} />
                </button>
                <button
                  onClick={() => removeIndicator(indicator.id)}
                  className="text-slate-400 hover:text-red-400 transition-colors"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Gain/Loss Line */}
      <div className={`rounded-lg p-3 ${gainLoss.isProfit ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'}`}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div>
            <p className="text-slate-400 text-xs mb-0.5">Entry Price</p>
            <p className="text-white font-semibold">{formatPrice(gainLoss.entryPrice, position.product_id || 'ETH-BTC')}</p>
          </div>
          <div>
            <p className="text-slate-400 text-xs mb-0.5">Current Price</p>
            <p className="text-white font-semibold">{formatPrice(gainLoss.currentPrice, position.product_id || 'ETH-BTC')}</p>
          </div>
          <div>
            <p className="text-slate-400 text-xs mb-0.5">Profit/Loss</p>
            <p className={`font-semibold ${gainLoss.isProfit ? 'text-green-400' : 'text-red-400'}`}>
              {gainLoss.isProfit ? '+' : ''}{gainLoss.profitLossPercent.toFixed(2)}%
            </p>
          </div>
          <div>
            <p className="text-slate-400 text-xs mb-0.5">To Target (2%)</p>
            <p className="text-slate-300 font-semibold">
              {gainLoss.toTargetPercent.toFixed(2)}%
            </p>
          </div>
        </div>
      </div>

      {/* Chart Container */}
      <div className="bg-slate-900 rounded-lg border border-slate-700 p-2">
        <div ref={chartContainerRef} />
      </div>

      {/* Oscillator Indicator Panels */}
      {indicators.filter(i => ['rsi', 'macd', 'stochastic'].includes(i.type)).map((indicator) => (
        <div key={indicator.id} className="bg-slate-900 rounded-lg border border-slate-700 p-2">
          <div className="flex items-center justify-between mb-2 px-2">
            <h5 className="text-xs font-semibold text-slate-300">{indicator.name}</h5>
          </div>
          <div
            id={`deal-indicator-chart-${indicator.id}`}
            style={{ height: '150px' }}
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
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Positions() {
  const [selectedPosition, setSelectedPosition] = useState<number | null>(null)
  const [showAddFundsModal, setShowAddFundsModal] = useState(false)
  const [addFundsAmount, setAddFundsAmount] = useState('')
  const [addFundsPositionId, setAddFundsPositionId] = useState<number | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [currentPrices, setCurrentPrices] = useState<Record<string, number>>({})
  const [showLogsModal, setShowLogsModal] = useState(false)
  const [logsModalPosition, setLogsModalPosition] = useState<Position | null>(null)

  // Filtering and sorting state (like 3Commas)
  const [filterBot, setFilterBot] = useState<number | 'all'>('all')
  const [filterMarket, setFilterMarket] = useState<'all' | 'USD' | 'BTC'>('all')
  const [filterPair, setFilterPair] = useState<string>('all')
  const [sortBy, setSortBy] = useState<'created' | 'pnl' | 'invested' | 'pair'>('created')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

  const { data: allPositions } = useQuery({
    queryKey: ['positions'],
    queryFn: () => positionsApi.getAll(undefined, 100),
    refetchInterval: 5000, // Update every 5 seconds for active deals
  })

  // Fetch all bots to display bot names
  const { data: bots } = useQuery({
    queryKey: ['bots'],
    queryFn: botsApi.getAll,
    refetchInterval: 10000,
  })

  // Fetch real-time prices for all open positions
  useEffect(() => {
    const abortController = new AbortController()

    const fetchPrices = async () => {
      if (!allPositions) return

      const openPositions = allPositions.filter(p => p.status === 'open')
      const pricePromises = openPositions.map(async (position) => {
        try {
          // Use candles API (more reliable than ticker for getting current price)
          const response = await axios.get(`${API_BASE}/api/candles`, {
            params: {
              product_id: position.product_id || 'ETH-BTC',
              granularity: 'ONE_MINUTE',
              limit: 1
            },
            signal: abortController.signal
          })
          const candles = response.data.candles || []
          if (candles.length > 0) {
            return { product_id: position.product_id || 'ETH-BTC', price: candles[0].close }
          }
          // Fallback to ticker if no candles
          const tickerResponse = await axios.get(`${API_BASE}/api/ticker/${position.product_id || 'ETH-BTC'}`, {
            signal: abortController.signal
          })
          return { product_id: position.product_id || 'ETH-BTC', price: tickerResponse.data.price }
        } catch (err) {
          // Ignore abort errors (they're expected when component unmounts)
          if (axios.isCancel(err) || (err as any)?.code === 'ECONNABORTED') {
            return { product_id: position.product_id || 'ETH-BTC', price: position.average_buy_price }
          }
          console.error(`Error fetching price for ${position.product_id}:`, err)
          return { product_id: position.product_id || 'ETH-BTC', price: position.average_buy_price }
        }
      })

      const prices = await Promise.all(pricePromises)
      const priceMap = prices.reduce((acc, { product_id, price }) => {
        acc[product_id] = price
        return acc
      }, {} as Record<string, number>)

      setCurrentPrices(priceMap)
    }

    fetchPrices()
    const interval = setInterval(fetchPrices, 5000) // Update every 5 seconds

    return () => {
      clearInterval(interval)
      abortController.abort() // Cancel any in-flight requests
    }
  }, [allPositions])

  const { data: trades } = useQuery({
    queryKey: ['position-trades', selectedPosition],
    queryFn: () => positionsApi.getTrades(selectedPosition!),
    enabled: selectedPosition !== null,
  })

  // Calculate unrealized P&L for open position (needed for sorting)
  const calculateUnrealizedPnL = (position: Position, currentPrice?: number) => {
    if (position.status !== 'open') return null

    // Use real-time price if available, otherwise fall back to average buy price
    const price = currentPrice || position.average_buy_price
    const currentValue = position.total_base_acquired * price
    const costBasis = position.total_quote_spent
    const unrealizedPnL = currentValue - costBasis
    const unrealizedPnLPercent = (unrealizedPnL / costBasis) * 100

    return {
      btc: unrealizedPnL,
      percent: unrealizedPnLPercent,
      usd: unrealizedPnL * (position.btc_usd_price_at_open || 0),
      currentPrice: price
    }
  }

  // Apply filters and sorting (like 3Commas)
  const openPositions = allPositions?.filter(p => {
    if (p.status !== 'open') return false

    // Filter by bot
    if (filterBot !== 'all' && p.bot_id !== filterBot) return false

    // Filter by market (USD-based or BTC-based)
    if (filterMarket !== 'all') {
      const quoteCurrency = (p.product_id || 'ETH-BTC').split('-')[1]
      if (filterMarket === 'USD' && quoteCurrency !== 'USD') return false
      if (filterMarket === 'BTC' && quoteCurrency !== 'BTC') return false
    }

    // Filter by specific pair
    if (filterPair !== 'all' && p.product_id !== filterPair) return false

    return true
  }).sort((a, b) => {
    let aVal: any, bVal: any

    switch (sortBy) {
      case 'created':
        aVal = new Date(a.opened_at).getTime()
        bVal = new Date(b.opened_at).getTime()
        break
      case 'pnl':
        const aPnl = calculateUnrealizedPnL(a, currentPrices[a.product_id || 'ETH-BTC'])?.percent || 0
        const bPnl = calculateUnrealizedPnL(b, currentPrices[b.product_id || 'ETH-BTC'])?.percent || 0
        aVal = aPnl
        bVal = bPnl
        break
      case 'invested':
        aVal = a.total_quote_spent
        bVal = b.total_quote_spent
        break
      case 'pair':
        aVal = a.product_id || 'ETH-BTC'
        bVal = b.product_id || 'ETH-BTC'
        break
      default:
        aVal = 0
        bVal = 0
    }

    if (sortOrder === 'asc') {
      return aVal > bVal ? 1 : -1
    } else {
      return aVal < bVal ? 1 : -1
    }
  }) || []

  // Get unique pairs for filter dropdown
  const uniquePairs = Array.from(new Set(allPositions?.filter(p => p.status === 'open').map(p => p.product_id || 'ETH-BTC') || []))

  const formatCrypto = (amount: number, decimals: number = 8) => {
    return amount.toFixed(decimals)
  }

  const handleClosePosition = async (positionId: number) => {
    if (!confirm('Are you sure you want to close this position at market price? This action cannot be undone.')) {
      return
    }

    setIsProcessing(true)
    try {
      const result = await positionsApi.close(positionId)
      alert(`Position closed successfully!\nProfit: ${result.profit_btc.toFixed(8)} BTC (${result.profit_percentage.toFixed(2)}%)`)
      // Refetch positions
      window.location.reload()
    } catch (err: any) {
      alert(`Error closing position: ${err.response?.data?.detail || err.message}`)
    } finally {
      setIsProcessing(false)
    }
  }

  const openAddFundsModal = (positionId: number, position: Position) => {
    const remaining = position.max_quote_allowed - position.total_quote_spent
    setAddFundsPositionId(positionId)
    setAddFundsAmount(remaining.toFixed(8))
    setShowAddFundsModal(true)
  }

  const handleAddFunds = async () => {
    if (!addFundsPositionId) return

    const amount = parseFloat(addFundsAmount)
    if (isNaN(amount) || amount <= 0) {
      alert('Please enter a valid amount')
      return
    }

    setIsProcessing(true)
    try {
      const result = await positionsApi.addFunds(addFundsPositionId, amount)
      alert(`Funds added successfully!\nAcquired: ${result.eth_acquired.toFixed(6)} ETH at price ${result.price.toFixed(8)}`)
      setShowAddFundsModal(false)
      setAddFundsAmount('')
      // Refetch positions
      window.location.reload()
    } catch (err: any) {
      alert(`Error adding funds: ${err.response?.data?.detail || err.message}`)
    } finally {
      setIsProcessing(false)
    }
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value)
  }

  const getQuoteCurrency = (productId: string) => {
    const quote = productId?.split('-')[1] || 'BTC'
    return {
      symbol: quote,
      decimals: quote === 'USD' ? 2 : 8
    }
  }

  const formatPrice = (price: number, productId: string) => {
    const { symbol, decimals } = getQuoteCurrency(productId)
    if (symbol === 'USD') {
      return `$${price.toFixed(decimals)}`
    }
    return `${price.toFixed(decimals)} ${symbol}`
  }

  const formatQuoteAmount = (amount: number, productId: string) => {
    const { symbol, decimals } = getQuoteCurrency(productId)
    return `${amount.toFixed(decimals)} ${symbol}`
  }

  const togglePosition = (positionId: number) => {
    if (selectedPosition === positionId) {
      setSelectedPosition(null)
    } else {
      setSelectedPosition(positionId)
    }
  }

  // Calculate safety orders from trades
  const getSafetyOrders = (positionTrades: Trade[] | undefined) => {
    if (!positionTrades) return []

    const buyTrades = positionTrades.filter(t => t.side === 'buy').sort((a, b) =>
      new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    )

    return buyTrades.map((trade, index) => ({
      orderNumber: index,
      type: index === 0 ? 'Base Order' : `Safety Order ${index}`,
      quoteAmount: trade.quote_amount,
      baseAmount: trade.base_amount,
      price: trade.price,
      timestamp: trade.timestamp,
      filled: true
    }))
  }

  // Calculate unrealized P&L for open position
  return (
    <div className="space-y-6">
      {/* Active Deals Section */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-3xl font-bold text-white">Active Deals</h2>
          <div className="flex items-center gap-2">
            <div className="bg-green-500/20 text-green-400 px-3 py-1 rounded-full text-sm font-medium">
              {openPositions.length} Active
            </div>
          </div>
        </div>

        {/* Filters and Sorting (like 3Commas) */}
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-4 mb-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-300">Filters & Sorting</h3>
            <button
              onClick={() => {
                setFilterBot('all')
                setFilterMarket('all')
                setFilterPair('all')
                setSortBy('created')
                setSortOrder('desc')
              }}
              className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded transition-colors flex items-center gap-2"
            >
              <X className="w-4 h-4" />
              Clear Filters
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
            {/* Bot Filter */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-2">Bot</label>
              <select
                value={filterBot}
                onChange={(e) => setFilterBot(e.target.value === 'all' ? 'all' : parseInt(e.target.value))}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="all">All Bots</option>
                {bots?.map(bot => (
                  <option key={bot.id} value={bot.id}>{bot.name}</option>
                ))}
              </select>
            </div>

            {/* Market Filter */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-2">Market</label>
              <select
                value={filterMarket}
                onChange={(e) => setFilterMarket(e.target.value as 'all' | 'USD' | 'BTC')}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="all">All Markets</option>
                <option value="USD">USD-based</option>
                <option value="BTC">BTC-based</option>
              </select>
            </div>

            {/* Pair Filter */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-2">Pair</label>
              <select
                value={filterPair}
                onChange={(e) => setFilterPair(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="all">All Pairs</option>
                {uniquePairs.map(pair => (
                  <option key={pair} value={pair}>{pair}</option>
                ))}
              </select>
            </div>

            {/* Sort By */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-2">Sort By</label>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as 'created' | 'pnl' | 'invested' | 'pair')}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="created">Created Date</option>
                <option value="pnl">PnL %</option>
                <option value="invested">Invested</option>
                <option value="pair">Pair</option>
              </select>
            </div>

            {/* Sort Order */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-2">Order</label>
              <select
                value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value as 'asc' | 'desc')}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="desc">Descending</option>
                <option value="asc">Ascending</option>
              </select>
            </div>
          </div>
        </div>

        {openPositions.length === 0 ? (
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-12 text-center">
            <BarChart3 className="w-16 h-16 text-slate-600 mx-auto mb-4" />
            <p className="text-slate-400 text-lg">No active deals</p>
            <p className="text-slate-500 text-sm mt-2">Start a bot to open new positions</p>
          </div>
        ) : (
          <div className="space-y-4">
            {openPositions.map((position) => {
              const currentPrice = currentPrices[position.product_id || 'ETH-BTC']
              const pnl = calculateUnrealizedPnL(position, currentPrice)
              const safetyOrders = selectedPosition === position.id ? getSafetyOrders(trades) : []
              const fundsUsedPercent = (position.total_quote_spent / position.max_quote_allowed) * 100

              return (
                <div key={position.id} className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
                  {/* Deal Header */}
                  <div
                    className="p-6 cursor-pointer hover:bg-slate-750 transition-colors"
                    onClick={() => togglePosition(position.id)}
                  >
                    <div className="flex items-start justify-between">
                      {/* Left: Deal Info */}
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-4">
                          <h3 className="text-xl font-bold text-white">Deal #{position.id}</h3>
                          {bots && position.bot_id && (
                            <span className="bg-emerald-500/20 text-emerald-400 px-2 py-1 rounded text-xs font-medium">
                              {bots.find(b => b.id === position.bot_id)?.name || `Bot #${position.bot_id}`}
                            </span>
                          )}
                          <span className="bg-purple-500/20 text-purple-400 px-2 py-1 rounded text-xs font-medium">
                            {position.product_id || 'ETH-BTC'}
                          </span>
                          <span className="bg-blue-500/20 text-blue-400 px-2 py-1 rounded text-xs font-medium">
                            ACTIVE
                          </span>
                        </div>

                        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                          {/* Current P&L */}
                          <div>
                            <p className="text-slate-400 text-xs mb-1">Current Profit</p>
                            {pnl && (
                              <div>
                                <div className="flex items-center gap-1">
                                  {pnl.btc >= 0 ? (
                                    <TrendingUp className="w-4 h-4 text-green-500" />
                                  ) : (
                                    <TrendingDown className="w-4 h-4 text-red-500" />
                                  )}
                                  <span className={`text-lg font-bold ${pnl.btc >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    {pnl.percent >= 0 ? '+' : ''}{pnl.percent.toFixed(2)}%
                                  </span>
                                </div>
                                <p className={`text-sm ${pnl.btc >= 0 ? 'text-green-400/70' : 'text-red-400/70'}`}>
                                  {pnl.btc >= 0 ? '+' : ''}{formatQuoteAmount(pnl.btc, position.product_id || 'ETH-BTC')}
                                </p>
                              </div>
                            )}
                          </div>

                          {/* Current Price */}
                          <div>
                            <p className="text-slate-400 text-xs mb-1">Current Price</p>
                            {pnl && (
                              <div>
                                <p className="text-white font-semibold">{formatPrice(pnl.currentPrice, position.product_id || 'ETH-BTC')}</p>
                                <p className={`text-xs ${pnl.btc >= 0 ? 'text-green-400/70' : 'text-red-400/70'}`}>
                                  {pnl.btc >= 0 ? '▲' : '▼'} {Math.abs(pnl.percent).toFixed(2)}%
                                </p>
                              </div>
                            )}
                          </div>

                          {/* Invested */}
                          <div>
                            <p className="text-slate-400 text-xs mb-1">Invested</p>
                            <p className="text-white font-semibold">{formatQuoteAmount(position.total_quote_spent, position.product_id || 'ETH-BTC')}</p>
                            <p className="text-slate-400 text-xs">{position.trade_count} orders filled</p>
                          </div>

                          {/* Average Price */}
                          <div>
                            <p className="text-slate-400 text-xs mb-1">Avg Entry Price</p>
                            <p className="text-white font-semibold">{formatPrice(position.average_buy_price, position.product_id || 'ETH-BTC')}</p>
                          </div>

                          {/* Opened */}
                          <div>
                            <p className="text-slate-400 text-xs mb-1">Opened</p>
                            <p className="text-white font-semibold text-sm">
                              {formatDateTimeCompact(position.opened_at)}
                            </p>
                          </div>
                        </div>

                        {/* Funds Usage Bar */}
                        <div className="mt-4">
                          <div className="flex items-center justify-between text-xs mb-1">
                            <span className="text-slate-400">Funds Used</span>
                            <span className="text-slate-300">
                              {formatQuoteAmount(position.total_quote_spent, position.product_id || 'ETH-BTC')} / {formatQuoteAmount(position.max_quote_allowed, position.product_id || 'ETH-BTC')}
                              <span className="text-slate-400 ml-1">({fundsUsedPercent.toFixed(0)}%)</span>
                            </span>
                          </div>
                          <div className="w-full bg-slate-700 rounded-full h-2">
                            <div
                              className="bg-blue-500 h-2 rounded-full transition-all"
                              style={{ width: `${Math.min(fundsUsedPercent, 100)}%` }}
                            />
                          </div>
                        </div>

                        {/* Price Position Bar */}
                        {pnl && (
                          <div className="mt-4">
                            <div className="flex items-center justify-between text-xs mb-1">
                              <span className="text-slate-400">Price Movement</span>
                              <span className="text-slate-300">
                                Target: {formatPrice(position.average_buy_price * 1.02, position.product_id || 'ETH-BTC')}
                              </span>
                            </div>
                            <div className="relative w-full h-2 bg-slate-700 rounded-full overflow-hidden">
                              {(() => {
                                const entryPrice = position.average_buy_price
                                const currentPriceValue = pnl.currentPrice
                                const targetPrice = entryPrice * 1.02

                                // Calculate range for visualization (show from -5% to +5% of entry)
                                const minPrice = entryPrice * 0.95
                                const maxPrice = entryPrice * 1.05
                                const priceRange = maxPrice - minPrice

                                // Calculate positions as percentages
                                const entryPosition = ((entryPrice - minPrice) / priceRange) * 100
                                const currentPosition = ((currentPriceValue - minPrice) / priceRange) * 100
                                const targetPosition = ((targetPrice - minPrice) / priceRange) * 100

                                const isProfit = currentPriceValue >= entryPrice
                                const fillStart = Math.min(entryPosition, currentPosition)
                                const fillWidth = Math.abs(currentPosition - entryPosition)

                                return (
                                  <>
                                    {/* Fill between entry and current price */}
                                    <div
                                      className={`absolute h-full ${isProfit ? 'bg-green-500' : 'bg-red-500'}`}
                                      style={{
                                        left: `${Math.max(0, Math.min(100, fillStart))}%`,
                                        width: `${Math.max(0, Math.min(100 - fillStart, fillWidth))}%`
                                      }}
                                    />

                                    {/* Entry Price Marker (Cost Basis) */}
                                    <div
                                      className="absolute top-0 bottom-0 w-0.5 bg-yellow-400"
                                      style={{ left: `${Math.max(0, Math.min(100, entryPosition))}%` }}
                                      title={`Entry: ${formatPrice(entryPrice)}`}
                                    />

                                    {/* Current Price Marker */}
                                    <div
                                      className={`absolute top-0 bottom-0 w-1 ${isProfit ? 'bg-green-300' : 'bg-red-300'}`}
                                      style={{ left: `${Math.max(0, Math.min(100, currentPosition))}%` }}
                                      title={`Current: ${formatPrice(currentPriceValue)}`}
                                    />

                                    {/* Target Price Marker */}
                                    <div
                                      className="absolute top-0 bottom-0 w-0.5 bg-blue-400"
                                      style={{ left: `${Math.max(0, Math.min(100, targetPosition))}%` }}
                                      title={`Target: ${formatPrice(targetPrice)}`}
                                    />
                                  </>
                                )
                              })()}
                            </div>
                            <div className="flex items-center justify-between text-[10px] mt-1 text-slate-500">
                              <span>-5%</span>
                              <div className="flex gap-3">
                                <span className="text-yellow-400">● Avg Entry</span>
                                <span className={pnl.btc >= 0 ? 'text-green-400' : 'text-red-400'}>● Current</span>
                                <span className="text-blue-400">● Target</span>
                              </div>
                              <span>+5%</span>
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Right: Expand Icon */}
                      <div className="ml-4">
                        {selectedPosition === position.id ? (
                          <ChevronUp className="w-5 h-5 text-slate-400" />
                        ) : (
                          <ChevronDown className="w-5 h-5 text-slate-400" />
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Expanded Details */}
                  {selectedPosition === position.id && (
                    <div className="border-t border-slate-700 bg-slate-900/50">
                      <div className="p-6 space-y-6">
                        {/* Safety Order Ladder */}
                        <div>
                          <h4 className="font-semibold text-white mb-3 flex items-center gap-2">
                            <BarChart3 size={18} />
                            Safety Order Ladder
                          </h4>
                          {safetyOrders.length > 0 ? (
                            <div className="space-y-2">
                              {safetyOrders.map((order, index) => (
                                <div
                                  key={index}
                                  className="bg-slate-800 border border-slate-700 rounded-lg p-3 flex items-center justify-between"
                                >
                                  <div className="flex items-center gap-3">
                                    <div className={`w-2 h-2 rounded-full ${order.filled ? 'bg-green-500' : 'bg-slate-600'}`} />
                                    <div>
                                      <p className="text-sm font-medium text-white">{order.type}</p>
                                      <p className="text-xs text-slate-400">
                                        {formatDateTimeCompact(order.timestamp)}
                                      </p>
                                    </div>
                                  </div>
                                  <div className="text-right">
                                    <p className="text-sm text-white font-mono">{formatQuoteAmount(order.quoteAmount, position.product_id || 'ETH-BTC')}</p>
                                    <p className="text-xs text-slate-400">@ {formatPrice(order.price, position.product_id || 'ETH-BTC')}</p>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="text-slate-400 text-sm">Loading order details...</p>
                          )}
                        </div>

                        {/* Deal Chart */}
                        <DealChart
                          position={position}
                          productId={position.product_id || "ETH-BTC"}
                          currentPrice={currentPrice}
                        />

                        {/* Position Details Grid */}
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
                            <p className="text-slate-400 text-xs mb-1">Total Acquired</p>
                            <p className="text-white font-semibold">
                              {formatCrypto(position.total_base_acquired, 6)} {(position.product_id || 'ETH-BTC').split('-')[0]}
                            </p>
                          </div>
                          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
                            <p className="text-slate-400 text-xs mb-1">Max Funds</p>
                            <p className="text-white font-semibold">
                              {formatCrypto(position.max_quote_allowed, 8)} {(position.product_id || 'ETH-BTC').split('-')[1]}
                            </p>
                          </div>
                          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
                            <p className="text-slate-400 text-xs mb-1">Remaining</p>
                            <p className="text-white font-semibold">
                              {formatCrypto(position.max_quote_allowed - position.total_quote_spent, 8)} {(position.product_id || 'ETH-BTC').split('-')[1]}
                            </p>
                          </div>
                        </div>

                        {/* Action Buttons */}
                        <div className="flex gap-3">
                          <button
                            className="flex-1 bg-purple-600 hover:bg-purple-700 text-white px-4 py-3 rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
                            onClick={(e) => {
                              e.stopPropagation()
                              setLogsModalPosition(position)
                              setShowLogsModal(true)
                            }}
                          >
                            <Brain size={18} />
                            View AI Logs
                          </button>
                          <button
                            className="flex-1 bg-red-600 hover:bg-red-700 text-white px-4 py-3 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleClosePosition(position.id)
                            }}
                            disabled={isProcessing}
                          >
                            <AlertCircle size={18} />
                            {isProcessing ? 'Processing...' : 'Close Position'}
                          </button>
                          <button
                            className="flex-1 bg-blue-600 hover:bg-blue-700 text-white px-4 py-3 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            onClick={(e) => {
                              e.stopPropagation()
                              openAddFundsModal(position.id, position)
                            }}
                            disabled={isProcessing}
                          >
                            <Plus size={18} />
                            Add Funds
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Add Funds Modal */}
      {showAddFundsModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg w-full max-w-md">
            <div className="p-6 border-b border-slate-700">
              <div className="flex items-center justify-between">
                <h3 className="text-xl font-bold text-white">Add Funds to Position</h3>
                <button
                  onClick={() => setShowAddFundsModal(false)}
                  className="text-slate-400 hover:text-white transition-colors"
                >
                  <X size={24} />
                </button>
              </div>
            </div>

            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Amount (BTC)
                </label>
                <input
                  type="number"
                  step="0.00000001"
                  value={addFundsAmount}
                  onChange={(e) => setAddFundsAmount(e.target.value)}
                  className="w-full bg-slate-700 border border-slate-600 rounded px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="0.00000000"
                  disabled={isProcessing}
                />
                <p className="text-xs text-slate-400 mt-1">
                  This will execute a manual safety order at current market price
                </p>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setShowAddFundsModal(false)}
                  className="flex-1 bg-slate-700 hover:bg-slate-600 text-white px-4 py-3 rounded-lg font-medium transition-colors"
                  disabled={isProcessing}
                >
                  Cancel
                </button>
                <button
                  onClick={handleAddFunds}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 text-white px-4 py-3 rounded-lg font-medium transition-colors disabled:opacity-50"
                  disabled={isProcessing}
                >
                  {isProcessing ? 'Adding...' : 'Add Funds'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Position AI Logs Modal */}
      {logsModalPosition && (
        <PositionLogsModal
          botId={logsModalPosition.bot_id}
          productId={logsModalPosition.product_id || 'ETH-BTC'}
          positionOpenedAt={logsModalPosition.opened_at}
          isOpen={showLogsModal}
          onClose={() => {
            setShowLogsModal(false)
            setLogsModalPosition(null)
          }}
        />
      )}
    </div>
  )
}
