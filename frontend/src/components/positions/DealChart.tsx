import { useRef, useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { createChart, ColorType, IChartApi, ISeriesApi, Time } from 'lightweight-charts'
import { api } from '../../services/api'
import {
  BarChart3,
  BarChart2,
  Activity,
  Settings,
  X
} from 'lucide-react'
import { botsApi } from '../../services/api'
import {
  calculateSMA,
  calculateEMA,
  calculateBollingerBands,
  calculateHeikinAshi,
  AVAILABLE_INDICATORS,
  TIME_INTERVALS,
  type CandleData
} from '../../utils/indicators'
import type { Position, Trade } from '../../types'
import {
  getTakeProfitPercent,
  getFeeAdjustedProfitMultiplier,
  formatPrice,
  type IndicatorConfig
} from './positionUtils'
import { AddIndicatorModal, IndicatorSettingsModal } from './IndicatorModals'

type LineData = {
  time: Time
  value: number
}

interface DealChartProps {
  position: Position
  productId: string
  currentPrice?: number
  trades?: Trade[]
}

// Deal Chart Component with full Charts page functionality
export function DealChart({ position, productId: initialProductId, currentPrice, trades }: DealChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mainSeriesRef = useRef<ISeriesApi<any> | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const indicatorSeriesRef = useRef<Map<string, ISeriesApi<any>[]>>(new Map())
  const indicatorChartsRef = useRef<Map<string, IChartApi>>(new Map())
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const positionLinesRef = useRef<ISeriesApi<any>[]>([])
  const candleDataRef = useRef<CandleData[]>([])
  const isCleanedUpRef = useRef<boolean>(false)
  const lastUpdateRef = useRef<string>('')

  // Persist chart settings across deal cards via localStorage
  const SETTINGS_KEY = 'deal-chart-settings'

  // State for chart controls (pair is always position-specific, settings are shared)
  const [selectedPair, setSelectedPair] = useState(initialProductId)
  const [timeframe, setTimeframe] = useState(() => {
    try { const s = JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}'); return s.timeframe || 'FIFTEEN_MINUTE' } catch { return 'FIFTEEN_MINUTE' }
  })
  const [chartData, setChartData] = useState<CandleData[]>([])
  const [chartType, setChartType] = useState<'candlestick' | 'bar' | 'line' | 'area' | 'baseline'>(() => {
    try { return JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}').chartType || 'candlestick' } catch { return 'candlestick' }
  })
  const [useHeikinAshi, setUseHeikinAshi] = useState(() => {
    try { return JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}').useHeikinAshi ?? false } catch { return false }
  })
  const [indicators, setIndicators] = useState<IndicatorConfig[]>(() => {
    try { return JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}').indicators || [] } catch { return [] }
  })
  const [showIndicatorModal, setShowIndicatorModal] = useState(false)
  const [indicatorSearch, setIndicatorSearch] = useState('')
  const [editingIndicator, setEditingIndicator] = useState<IndicatorConfig | null>(null)

  // Persist chart settings (not pair) to localStorage on change
  useEffect(() => {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify({
      timeframe, chartType, useHeikinAshi, indicators,
    }))
  }, [timeframe, chartType, useHeikinAshi, indicators])

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
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return (botData as any).pairs || []
    },
    enabled: !!position.bot_id,
  })

  // Fill gaps in candle data with synthetic candles for position entry
  const fillCandleGaps = (candles: CandleData[], position: Position) => {
    if (!candles.length) return candles

    const openedTime = Math.floor(new Date(position.opened_at).getTime() / 1000)
    const entryPrice = position.average_buy_price

    // Check if we need to add a synthetic candle for the entry time
    const hasExactCandle = candles.some(c => c.time === openedTime)
    if (hasExactCandle) return candles

    // Find where to insert the synthetic candle
    const insertIndex = candles.findIndex(c => Number(c.time) > openedTime)

    if (insertIndex === -1) {
      // Entry is after all candles, add to end
      return [...candles, {
        time: openedTime,
        open: entryPrice,
        high: entryPrice,
        low: entryPrice,
        close: entryPrice,
        volume: 0
      }]
    } else if (insertIndex === 0) {
      // Entry is before all candles, add to beginning
      return [{
        time: openedTime,
        open: entryPrice,
        high: entryPrice,
        low: entryPrice,
        close: entryPrice,
        volume: 0
      }, ...candles]
    } else {
      // Entry is in the middle, insert synthetic candle
      const newCandles = [...candles]
      newCandles.splice(insertIndex, 0, {
        time: openedTime as Time,
        open: entryPrice,
        high: entryPrice,
        low: entryPrice,
        close: entryPrice,
        volume: 0
      })
      return newCandles
    }
  }

  // Fetch candle data
  useEffect(() => {
    const fetchCandles = async () => {
      try {
        const response = await api.get('/candles', {
          params: {
            product_id: selectedPair,
            granularity: timeframe,
            limit: 300,
          },
        })
        let candles = response.data.candles || []

        // Add synthetic candle for position entry if needed
        if (position) {
          candles = fillCandleGaps(candles, position)
        }

        setChartData(candles)
        candleDataRef.current = candles
      } catch (err) {
        console.error('Error fetching candles:', err)
      }
    }
    fetchCandles()
  }, [selectedPair, timeframe, position])

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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
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

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const newSeries: ISeriesApi<any>[] = []

      if (indicator.type === 'sma') {
        const smaValues = calculateSMA(closes, indicator.settings.period as number)
        const smaData: LineData[] = []
        candles.forEach((c, i) => {
          if (smaValues[i] !== null) {
            smaData.push({ time: c.time as Time, value: smaValues[i]! })
          }
        })
        const series = chartRef.current!.addLineSeries({
          color: indicator.settings.color as string,
          lineWidth: 2,
          title: `SMA(${indicator.settings.period})`,
          priceFormat: priceFormat,
        })
        series.setData(smaData)
        newSeries.push(series)
      }

      if (indicator.type === 'ema') {
        const emaValues = calculateEMA(closes, indicator.settings.period as number)
        const emaData: LineData[] = []
        candles.forEach((c, i) => {
          if (emaValues[i] !== null) {
            emaData.push({ time: c.time as Time, value: emaValues[i]! })
          }
        })
        const series = chartRef.current!.addLineSeries({
          color: indicator.settings.color as string,
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
          indicator.settings.period as number,
          indicator.settings.stdDev as number
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
          color: indicator.settings.upperColor as string,
          lineWidth: 1,
          lastValueVisible: false,
          priceLineVisible: false,
          priceFormat: priceFormat,
        })
        const middleLineSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.middleColor as string,
          lineWidth: 1,
          lastValueVisible: false,
          priceLineVisible: false,
          priceFormat: priceFormat,
        })
        const lowerLineSeries = chartRef.current!.addLineSeries({
          color: indicator.settings.lowerColor as string,
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
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      mainSeriesRef.current.setData(priceData as any)

      // Render indicators
      if (indicators.length > 0) {
        renderIndicators(chartData)
      }

      // Remove previous position line series before adding new ones
      for (const series of positionLinesRef.current) {
        try {
          chartRef.current.removeSeries(series)
        } catch {
          // Series may already be removed
        }
      }
      positionLinesRef.current = []

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
      positionLinesRef.current.push(entryLineSeries)

      // Take Profit line - uses configured profit target with fee adjustment
      const configuredTakeProfit = getTakeProfitPercent(position, bot)
      const takeProfitMultiplier = getFeeAdjustedProfitMultiplier(configuredTakeProfit)
      const takeProfitPrice = position.average_buy_price * takeProfitMultiplier
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
      positionLinesRef.current.push(takeProfitSeries)

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
        positionLinesRef.current.push(stopLossSeries)
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
          positionLinesRef.current.push(soSeries)

          cumulativeDeviation += priceDeviation * Math.pow(stepScale, i)
        }
      }

      // Add markers
      if (chartType === 'candlestick' || chartType === 'bar') {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
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

        // Entry marker (base order)
        const openedTime = Math.floor(new Date(position.opened_at).getTime() / 1000)
        const nearestCandle = chartData.reduce((prev, curr) =>
          Math.abs(Number(curr.time) - openedTime) < Math.abs(Number(prev.time) - openedTime) ? curr : prev
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

        // DCA markers (safety orders)
        if (trades && trades.length > 0) {
          const positionTrades = trades.filter(t => t.position_id === position.id)
          const dcaTrades = positionTrades
            .filter(t => t.side === 'buy' && t.trade_type === 'dca')
            .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())

          dcaTrades.forEach((trade, index) => {
            const tradeTime = Math.floor(new Date(trade.timestamp).getTime() / 1000)
            const nearestCandle = chartData.reduce((prev, curr) =>
              Math.abs(Number(curr.time) - tradeTime) < Math.abs(Number(prev.time) - tradeTime) ? curr : prev
            )

            if (nearestCandle) {
              markers.push({
                time: nearestCandle.time as Time,
                position: 'belowBar',
                color: '#f97316', // Orange for DCA
                shape: 'arrowUp',
                text: `DCA${index + 1}`,
              })
            }
          })
        }

        mainSeriesRef.current.setMarkers(markers)
      }

      chartRef.current.timeScale().fitContent()
    } catch (e) {
      return
    }
  }, [chartData, chartType, useHeikinAshi, indicators, position, bot, selectedPair, trades])

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


  // Calculate gain/loss info (matches the main position P&L calculation)
  const calculateGainLoss = () => {
    const currentPriceValue = currentPrice || (chartData.length > 0 ? chartData[chartData.length - 1].close : 0)
    const entryPrice = position.average_buy_price
    // Use configured take profit with fee adjustment
    const configuredTakeProfit = getTakeProfitPercent(position, bot)
    const profitTarget = entryPrice * getFeeAdjustedProfitMultiplier(configuredTakeProfit)

    // Use the same calculation as calculateUnrealizedPnL for consistency
    const currentValue = position.total_base_acquired * currentPriceValue
    const costBasis = position.total_quote_spent
    const profitLoss = currentValue - costBasis
    const profitLossPercent = (profitLoss / costBasis) * 100
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

      {/* Indicator Modals */}
      <AddIndicatorModal
        isOpen={showIndicatorModal}
        onClose={() => setShowIndicatorModal(false)}
        onAddIndicator={addIndicator}
        indicatorSearch={indicatorSearch}
        onSearchChange={setIndicatorSearch}
      />

      <IndicatorSettingsModal
        indicator={editingIndicator}
        onClose={() => setEditingIndicator(null)}
        onUpdateSettings={updateIndicatorSettings}
      />
    </div>
  )
}
