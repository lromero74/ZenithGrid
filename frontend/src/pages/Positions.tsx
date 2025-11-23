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
  BarChart2,
  Minus
} from 'lucide-react'
import { createChart, ColorType, IChartApi, ISeriesApi, Time } from 'lightweight-charts'
import axios from 'axios'
import type { Position, Trade } from '../types'
import PositionLogsModal from '../components/PositionLogsModal'
import TradingViewChartModal from '../components/TradingViewChartModal'
import LightweightChartModal from '../components/LightweightChartModal'
import { LimitCloseModal } from '../components/LimitCloseModal'
import CoinIcon from '../components/CoinIcon'
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
import { API_BASE_URL } from '../config/api'

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

// Utility functions for price formatting
const getQuoteCurrency = (productId: string) => {
  const quote = productId?.split('-')[1] || 'BTC'
  return {
    symbol: quote,
    decimals: quote === 'USD' ? 2 : 8
  }
}

const getBaseCurrency = (productId: string) => {
  const base = productId?.split('-')[0] || 'ETH'
  return {
    symbol: base,
    decimals: 6  // Most altcoins use 6 decimals for display
  }
}

const formatPrice = (price: number, productId: string = 'ETH-BTC') => {
  const { symbol, decimals } = getQuoteCurrency(productId)
  if (symbol === 'USD') {
    return `$${price.toFixed(decimals)}`
  }
  return `${price.toFixed(decimals)} ${symbol}`
}

const formatBaseAmount = (amount: number, productId: string = 'ETH-BTC') => {
  const { symbol, decimals } = getBaseCurrency(productId)
  return `${amount.toFixed(decimals)} ${symbol}`
}

const formatQuoteAmount = (amount: number, productId: string) => {
  const { symbol, decimals } = getQuoteCurrency(productId)
  return `${amount.toFixed(decimals)} ${symbol}`
}

// Deal Chart Component with full Charts page functionality
function DealChart({ position, productId: initialProductId, currentPrice, trades }: { position: Position, productId: string, currentPrice?: number, trades?: Trade[] }) {
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

  // Fill gaps in candle data with synthetic candles for position entry
  const fillCandleGaps = (candles: CandleData[], position: Position) => {
    if (!candles.length) return candles

    const openedTime = Math.floor(new Date(position.opened_at).getTime() / 1000)
    const entryPrice = position.average_buy_price

    // Check if we need to add a synthetic candle for the entry time
    const hasExactCandle = candles.some(c => c.time === openedTime)
    if (hasExactCandle) return candles

    // Find where to insert the synthetic candle
    const insertIndex = candles.findIndex(c => c.time > openedTime)

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
        time: openedTime,
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
        const response = await axios.get(`${API_BASE_URL}/api/candles`, {
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

        // Entry marker (base order)
        const openedTime = Math.floor(new Date(position.opened_at).getTime() / 1000)
        const nearestCandle = chartData.reduce((prev, curr) =>
          Math.abs(curr.time - openedTime) < Math.abs(prev.time - openedTime) ? curr : prev
        )

        console.log(`Entry arrow: openedTime=${openedTime}, nearestCandle.time=${nearestCandle?.time}, diff=${Math.abs((nearestCandle?.time || 0) - openedTime)}s, price=${nearestCandle?.close}`)

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
              Math.abs(curr.time - tradeTime) < Math.abs(prev.time - tradeTime) ? curr : prev
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

  const filteredIndicators = AVAILABLE_INDICATORS.filter(ind =>
    ind.name.toLowerCase().includes(indicatorSearch.toLowerCase()) ||
    ind.category.toLowerCase().includes(indicatorSearch.toLowerCase())
  )

  // Calculate gain/loss info (matches the main position P&L calculation)
  const calculateGainLoss = () => {
    const currentPriceValue = currentPrice || (chartData.length > 0 ? chartData[chartData.length - 1].close : 0)
    const entryPrice = position.average_buy_price
    const profitTarget = entryPrice * 1.02

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
                      className="w-full text-left bg-slate-700 hover:bg-slate-600 text-white px-2 sm:px-4 py-2 sm:py-3 rounded transition-colors"
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

// AI Sentiment Icon Component
function AISentimentIcon({ botId, productId }: { botId: number, productId: string }) {
  const { data: aiLog } = useQuery({
    queryKey: ['ai-sentiment', botId, productId],
    queryFn: async () => {
      const response = await axios.get(`/api/bots/${botId}/logs`, {
        params: { product_id: productId, limit: 1 }
      })
      return response.data[0] || null
    },
    refetchInterval: 30000, // Refresh every 30 seconds
    enabled: !!botId && !!productId,
  })

  if (!aiLog || !aiLog.decision) return null

  const decision = aiLog.decision.toLowerCase()
  const confidence = aiLog.confidence || 0

  // Map decision to icon and color
  const getIcon = () => {
    switch (decision) {
      case 'buy':
        return <TrendingUp size={14} className="text-green-400" />
      case 'sell':
        return <TrendingDown size={14} className="text-red-400" />
      case 'hold':
        return <Minus size={14} className="text-yellow-400" />
      default:
        return null
    }
  }

  const getTooltip = () => {
    return `AI: ${decision.toUpperCase()} (${confidence.toFixed(0)}%)\n${aiLog.thinking || ''}`
  }

  return (
    <div
      className="flex items-center gap-1 cursor-help"
      title={getTooltip()}
    >
      {getIcon()}
      <span className="text-[10px] text-slate-400">{confidence.toFixed(0)}%</span>
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
  const [showChartModal, setShowChartModal] = useState(false)
  const [chartModalSymbol, setChartModalSymbol] = useState<string>('')
  const [chartModalPosition, setChartModalPosition] = useState<Position | null>(null)
  const [showLightweightChart, setShowLightweightChart] = useState(false)
  const [lightweightChartSymbol, setLightweightChartSymbol] = useState<string>('')
  const [lightweightChartPosition, setLightweightChartPosition] = useState<Position | null>(null)
  const [showCloseConfirm, setShowCloseConfirm] = useState(false)
  const [closeConfirmPositionId, setCloseConfirmPositionId] = useState<number | null>(null)
  const [showLimitCloseModal, setShowLimitCloseModal] = useState(false)
  const [limitClosePosition, setLimitClosePosition] = useState<Position | null>(null)
  const [showNotesModal, setShowNotesModal] = useState(false)
  const [editingNotesPositionId, setEditingNotesPositionId] = useState<number | null>(null)
  const [notesText, setNotesText] = useState('')

  // Filtering and sorting state (like 3Commas)
  const [filterBot, setFilterBot] = useState<number | 'all'>('all')
  const [filterMarket, setFilterMarket] = useState<'all' | 'USD' | 'BTC'>('all')
  const [filterPair, setFilterPair] = useState<string>('all')
  const [sortBy, setSortBy] = useState<'created' | 'pnl' | 'invested' | 'pair'>('created')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

  const { data: allPositions, refetch: refetchPositions } = useQuery({
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

  // Fetch portfolio for BTC/USD price
  const { data: portfolio } = useQuery({
    queryKey: ['account-portfolio'],
    queryFn: async () => {
      const response = await fetch('/api/account/portfolio')
      if (!response.ok) throw new Error('Failed to fetch portfolio')
      return response.json()
    },
    refetchInterval: 120000,
    staleTime: 60000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  })

  const totalBtcValue = portfolio?.total_btc_value || 0
  const totalUsdValue = portfolio?.total_usd_value || 0
  const btcUsdPrice = totalBtcValue > 0 ? totalUsdValue / totalBtcValue : 0

  // Fetch real-time prices for all open positions
  useEffect(() => {
    const abortController = new AbortController()

    const fetchPrices = async () => {
      if (!allPositions) return

      const openPositions = allPositions.filter(p => p.status === 'open')
      if (openPositions.length === 0) return

      try {
        // Fetch all prices in a single batch request
        const productIds = openPositions.map(p => p.product_id || 'ETH-BTC').join(',')
        const response = await axios.get(`${API_BASE_URL}/api/prices/batch`, {
          params: { products: productIds },
          signal: abortController.signal
        })

        const priceMap = response.data.prices || {}

        // Fill in fallback prices for positions that didn't get a price
        openPositions.forEach(position => {
          const productId = position.product_id || 'ETH-BTC'
          if (!priceMap[productId]) {
            priceMap[productId] = position.average_buy_price
          }
        })

        setCurrentPrices(priceMap)
      } catch (err) {
        // Ignore abort errors (they're expected when component unmounts)
        if (axios.isCancel(err) || (err as any)?.code === 'ECONNABORTED') {
          return
        }
        console.error('Error fetching batch prices:', err)

        // Fallback to using average buy prices
        const fallbackPrices: Record<string, number> = {}
        openPositions.forEach(position => {
          const productId = position.product_id || 'ETH-BTC'
          fallbackPrices[productId] = position.average_buy_price
        })
        setCurrentPrices(fallbackPrices)
      }
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

    // Prevent division by zero for new positions with no trades yet
    const unrealizedPnLPercent = costBasis > 0 ? (unrealizedPnL / costBasis) * 100 : 0

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

  const handleClosePosition = async () => {
    if (!closeConfirmPositionId) return

    setIsProcessing(true)
    try {
      const result = await positionsApi.close(closeConfirmPositionId)
      setShowCloseConfirm(false)
      setCloseConfirmPositionId(null)
      // Refetch positions instead of full page reload
      refetchPositions()
      // Show success notification
      alert(`Position closed successfully!\nProfit: ${result.profit_quote.toFixed(8)} (${result.profit_percentage.toFixed(2)}%)`)
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
      setShowAddFundsModal(false)
      setAddFundsAmount('')
      // Refetch positions instead of full page reload
      refetchPositions()
      alert(`Funds added successfully!\nAcquired: ${result.eth_acquired.toFixed(6)} ETH at price ${result.price.toFixed(8)}`)
    } catch (err: any) {
      alert(`Error adding funds: ${err.response?.data?.detail || err.message}`)
    } finally {
      setIsProcessing(false)
    }
  }

  const openNotesModal = (position: Position) => {
    setEditingNotesPositionId(position.id)
    setNotesText(position.notes || '')
    setShowNotesModal(true)
  }

  const handleSaveNotes = async () => {
    if (!editingNotesPositionId) return

    setIsProcessing(true)
    try {
      await axios.patch(`${API_BASE_URL}/api/positions/${editingNotesPositionId}/notes`, {
        notes: notesText
      })
      setShowNotesModal(false)
      setEditingNotesPositionId(null)
      setNotesText('')
      // Refetch positions to show updated notes
      refetchPositions()
    } catch (err: any) {
      alert(`Error saving notes: ${err.response?.data?.detail || err.message}`)
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

    return buyTrades.map((trade, index) => {
      let orderType = 'Base Order'
      if (index > 0) {
        // Safety orders - distinguish manual vs automatic (3Commas style)
        const isManual = trade.trade_type === 'manual_safety_order'
        orderType = `Safety Order ${index}${isManual ? ' (Manual)' : ''}`
      }

      return {
        orderNumber: index,
        type: orderType,
        quoteAmount: trade.quote_amount,
        baseAmount: trade.base_amount,
        price: trade.price,
        timestamp: trade.timestamp,
        filled: true
      }
    })
  }

  // Calculate overall statistics
  const calculateOverallStats = () => {
    const totalFundsLocked = openPositions.reduce((sum, pos) => sum + pos.total_quote_spent, 0)
    const totalUPnL = openPositions.reduce((sum, pos) => {
      const currentPrice = currentPrices[pos.product_id || 'ETH-BTC']
      const pnl = calculateUnrealizedPnL(pos, currentPrice)
      return sum + (pnl?.btc || 0)
    }, 0)
    const totalUPnLUSD = openPositions.reduce((sum, pos) => {
      const currentPrice = currentPrices[pos.product_id || 'ETH-BTC']
      const pnl = calculateUnrealizedPnL(pos, currentPrice)
      return sum + (pnl?.usd || 0)
    }, 0)

    return {
      activeTrades: openPositions.length,
      fundsLocked: totalFundsLocked,
      uPnL: totalUPnL,
      uPnLUSD: totalUPnLUSD
    }
  }

  const stats = calculateOverallStats()

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

        {/* Overall Stats Panel - 3Commas Style */}
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-6 mb-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Overall Stats */}
            <div>
              <h3 className="text-sm font-semibold text-slate-300 mb-3">Overall stats</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-slate-400">Active trades:</span>
                  <span className="text-white font-medium">{stats.activeTrades}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Funds locked in DCA bot trades:</span>
                  <span className="text-white font-medium">{stats.fundsLocked.toFixed(8)} BTC</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">uPnL of active Bot trades:</span>
                  <span className={`font-medium ${stats.uPnL >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {stats.uPnL >= 0 ? '+' : ''}{stats.uPnL.toFixed(8)} BTC
                  </span>
                </div>
              </div>
            </div>

            {/* Completed Trades Profit (placeholder for now) */}
            <div>
              <h3 className="text-sm font-semibold text-slate-300 mb-3">Completed trades profit</h3>
              <div className="space-y-2 text-sm">
                <div className="text-slate-400">Coming soon...</div>
              </div>
            </div>

            {/* Balances */}
            <div>
              <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center justify-between">
                Balances
                <button className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1">
                  🔄 Refresh
                </button>
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between text-slate-400">
                  <span>Reserved</span>
                  <span>Available</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-300">BTC</span>
                  <div className="flex gap-4">
                    <span className="text-white">{stats.fundsLocked.toFixed(8)}</span>
                    <span className="text-white">-</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Filters - 3Commas Style (Account, Bot, Pair) */}
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-4 mb-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-300">Filters</h3>
            <button
              onClick={() => {
                setFilterBot('all')
                setFilterMarket('all')
                setFilterPair('all')
              }}
              className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded transition-colors flex items-center gap-2"
            >
              <X className="w-4 h-4" />
              Clear
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Account Filter (Market in our case) */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-2">Account</label>
              <select
                value={filterMarket}
                onChange={(e) => setFilterMarket(e.target.value as 'all' | 'USD' | 'BTC')}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="all">All</option>
                <option value="USD">USD Markets</option>
                <option value="BTC">BTC Markets</option>
              </select>
            </div>

            {/* Bot Filter */}
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-2">Bot</label>
              <select
                value={filterBot}
                onChange={(e) => setFilterBot(e.target.value === 'all' ? 'all' : parseInt(e.target.value))}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="all">All</option>
                {bots?.map(bot => (
                  <option key={bot.id} value={bot.id}>{bot.name}</option>
                ))}
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
                <option value="all">All</option>
                {uniquePairs.map(pair => (
                  <option key={pair} value={pair}>{pair}</option>
                ))}
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
          <div className="space-y-2">
            {/* Column Headers - 3Commas Style */}
            <div className="bg-slate-800/50 rounded-lg border border-slate-700/50 px-4 py-2">
              <div className="grid grid-cols-12 gap-4 items-center text-xs text-slate-400">
                <div
                  className="col-span-2 flex items-center gap-1 cursor-pointer hover:text-slate-300"
                  onClick={() => {
                    if (sortBy === 'bot') {
                      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
                    } else {
                      setSortBy('bot' as any)
                      setSortOrder('asc')
                    }
                  }}
                >
                  <span>Bot</span>
                  {sortBy === 'bot' && <span>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  {sortBy !== 'bot' && <span className="opacity-30">↕</span>}
                </div>
                <div
                  className="col-span-2 flex items-center gap-1 cursor-pointer hover:text-slate-300"
                  onClick={() => {
                    if (sortBy === 'pair') {
                      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
                    } else {
                      setSortBy('pair')
                      setSortOrder('asc')
                    }
                  }}
                >
                  <span>Pair</span>
                  {sortBy === 'pair' && <span>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  {sortBy !== 'pair' && <span className="opacity-30">↕</span>}
                </div>
                <div
                  className="col-span-4 flex items-center gap-1 cursor-pointer hover:text-slate-300"
                  onClick={() => {
                    if (sortBy === 'pnl') {
                      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
                    } else {
                      setSortBy('pnl')
                      setSortOrder('desc')
                    }
                  }}
                >
                  <span className="flex items-center gap-1">
                    <span className="w-4 h-4 rounded-full bg-slate-600 flex items-center justify-center text-[9px]">?</span>
                    uPnL
                  </span>
                  {sortBy === 'pnl' && <span>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  {sortBy !== 'pnl' && <span className="opacity-30">↕</span>}
                </div>
                <div
                  className="col-span-2 flex items-center gap-1 cursor-pointer hover:text-slate-300"
                  onClick={() => {
                    if (sortBy === 'invested') {
                      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
                    } else {
                      setSortBy('invested')
                      setSortOrder('desc')
                    }
                  }}
                >
                  <span>Volume</span>
                  {sortBy === 'invested' && <span>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  {sortBy !== 'invested' && <span className="opacity-30">↕</span>}
                </div>
                <div className="col-span-1 flex items-center gap-1 text-slate-500">
                  <span>Status</span>
                </div>
                <div
                  className="col-span-1 flex items-center gap-1 cursor-pointer hover:text-slate-300"
                  onClick={() => {
                    if (sortBy === 'created') {
                      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
                    } else {
                      setSortBy('created')
                      setSortOrder('desc')
                    }
                  }}
                >
                  <span>Created</span>
                  {sortBy === 'created' && <span>{sortOrder === 'asc' ? '↑' : '↓'}</span>}
                  {sortBy !== 'created' && <span className="opacity-30">↕</span>}
                </div>
              </div>
            </div>

            {/* Group positions by bot */}
            {openPositions.map((position) => {
              const currentPrice = currentPrices[position.product_id || 'ETH-BTC']
              const pnl = calculateUnrealizedPnL(position, currentPrice)
              const safetyOrders = selectedPosition === position.id ? getSafetyOrders(trades) : []
              const fundsUsedPercent = (position.total_quote_spent / position.max_quote_allowed) * 100

              const bot = bots?.find(b => b.id === position.bot_id)
              const strategyConfig = position.strategy_config_snapshot || bot?.strategy_config || {}

              return (
                <div key={position.id} className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
                  {/* Deal Row - 3Commas Style Horizontal Layout */}
                  <div
                    className="p-4 cursor-pointer hover:bg-slate-750 transition-colors"
                    onClick={() => togglePosition(position.id)}
                  >
                    <div className="grid grid-cols-12 gap-4 items-start text-sm">
                      {/* Column 1: Bot Info + Strategy (2 cols) */}
                      <div className="col-span-2">
                        <div className="text-white font-semibold mb-1">
                          {bot?.name || `Bot #${position.bot_id || 'N/A'}`}
                        </div>
                        <div className="text-[10px] text-slate-400 space-y-0.5">
                          {bot?.strategy_type && (
                            <div>[{bot.strategy_type.toUpperCase()}]</div>
                          )}
                          {strategyConfig.take_profit_percent && (
                            <div>MP: {strategyConfig.take_profit_percent}%</div>
                          )}
                          {strategyConfig.base_order_size && (
                            <div>BO: {strategyConfig.base_order_size}</div>
                          )}
                        </div>
                      </div>

                      {/* Column 2: Pair + Exchange (1.5 cols) */}
                      <div className="col-span-2 flex items-start gap-2">
                        <CoinIcon
                          symbol={position.product_id?.split('-')[0] || 'BTC'}
                          size="sm"
                        />
                        <div className="flex-1">
                          <div className="flex items-center gap-1.5">
                            <span
                              className="text-white font-semibold cursor-pointer hover:opacity-80 transition-opacity"
                              onClick={() => {
                                setChartModalSymbol(position.product_id || 'ETH-BTC')
                                setChartModalPosition(position)
                                setShowChartModal(true)
                              }}
                            >
                              {position.product_id || 'ETH-BTC'}
                            </span>
                            <BarChart2
                              size={14}
                              className="text-slate-400 hover:text-blue-400 cursor-pointer transition-colors"
                              onClick={() => {
                                setLightweightChartSymbol(position.product_id || 'ETH-BTC')
                                setLightweightChartPosition(position)
                                setShowLightweightChart(true)
                              }}
                            />
                            {/* AI Sentiment Indicator */}
                            {position.bot_id && (
                              <AISentimentIcon
                                botId={position.bot_id}
                                productId={position.product_id || 'ETH-BTC'}
                              />
                            )}
                            {/* Error Indicator (like 3Commas) */}
                            {position.last_error_message && (
                              <div
                                className="flex items-center cursor-help"
                                title={`Error: ${position.last_error_message}\n${position.last_error_timestamp ? `Time: ${formatDateTime(position.last_error_timestamp)}` : ''}`}
                              >
                                <AlertCircle size={14} className="text-red-400" />
                              </div>
                            )}
                          </div>
                          <div className="text-[10px] text-slate-400">My Coinbase Advanced</div>
                        </div>
                      </div>

                      {/* Column 3: uPnL + Price Bar (4 cols) */}
                      <div className="col-span-4">
                        {pnl && (
                          <div>
                            <div className="mb-1">
                              <span className="text-[10px] text-blue-400">Filled {fundsUsedPercent.toFixed(2)}%</span>
                            </div>
                            {/* Price Bar - 3Commas Style */}
                            <div className="relative w-full pt-6 pb-6">
                              <div className="relative w-full h-2 bg-slate-700 rounded-full">
                                {(() => {
                                  const entryPrice = position.average_buy_price

                                  // Don't render price markers for new positions with no fills yet
                                  if (!entryPrice || entryPrice === 0) {
                                    return null
                                  }

                                  const currentPriceValue = pnl.currentPrice
                                  const targetPrice = entryPrice * 1.02

                                  const defaultMin = entryPrice * 0.95
                                  const defaultMax = entryPrice * 1.05
                                  const minPrice = Math.min(defaultMin, currentPriceValue * 0.98)
                                  const maxPrice = Math.max(defaultMax, targetPrice * 1.01, currentPriceValue * 1.02)
                                  const priceRange = maxPrice - minPrice

                                  const entryPosition = ((entryPrice - minPrice) / priceRange) * 100
                                  const currentPosition = ((currentPriceValue - minPrice) / priceRange) * 100
                                  const targetPosition = ((targetPrice - minPrice) / priceRange) * 100

                                  const isProfit = currentPriceValue >= entryPrice
                                  const fillStart = Math.min(entryPosition, currentPosition)
                                  const fillWidth = Math.abs(currentPosition - entryPosition)

                                  // Collision detection - if labels are too close (< 15%), stagger them
                                  const buyCurrentGap = Math.abs(currentPosition - entryPosition)
                                  const currentTargetGap = Math.abs(targetPosition - currentPosition)
                                  const buyTargetGap = Math.abs(targetPosition - entryPosition)

                                  // Determine positioning: top or bottom
                                  let buyPos = 'top'
                                  let currentPos = 'top'
                                  let targetPos = 'top'

                                  // If buy and current are close, put current below
                                  if (buyCurrentGap < 15) {
                                    currentPos = 'bottom'
                                  }

                                  // If current and target are close, alternate
                                  if (currentTargetGap < 15) {
                                    if (currentPos === 'top') {
                                      targetPos = 'bottom'
                                    } else {
                                      targetPos = 'top'
                                    }
                                  }

                                  // If buy and target are close but current is far, alternate them
                                  if (buyTargetGap < 15 && buyCurrentGap >= 15 && currentTargetGap >= 15) {
                                    targetPos = 'bottom'
                                  }

                                  return (
                                    <>
                                      {/* Fill color between entry and current */}
                                      <div
                                        className={`absolute h-full rounded-full ${isProfit ? 'bg-green-500' : 'bg-red-500'}`}
                                        style={{
                                          left: `${Math.max(0, Math.min(100, fillStart))}%`,
                                          width: `${Math.max(0, Math.min(100 - fillStart, fillWidth))}%`
                                        }}
                                      />

                                      {/* Buy Price */}
                                      <div
                                        className="absolute flex flex-col items-center"
                                        style={{
                                          left: `${Math.max(0, Math.min(100, entryPosition))}%`,
                                          transform: 'translateX(-50%)',
                                          ...(buyPos === 'top' ? { bottom: '100%' } : { top: '100%' })
                                        }}
                                      >
                                        {buyPos === 'bottom' && <div className="w-px h-3 bg-slate-400" />}
                                        <div className={`text-[9px] text-slate-400 whitespace-nowrap ${buyPos === 'top' ? 'mb-0.5' : 'mt-0.5'}`}>
                                          Buy {formatPrice(entryPrice, position.product_id || 'ETH-BTC')}
                                        </div>
                                        {buyPos === 'top' && <div className="w-px h-3 bg-slate-400" />}
                                      </div>

                                      {/* Current Price */}
                                      <div
                                        className="absolute flex flex-col items-center"
                                        style={{
                                          left: `${Math.max(0, Math.min(100, currentPosition))}%`,
                                          transform: 'translateX(-50%)',
                                          ...(currentPos === 'top' ? { bottom: '100%' } : { top: '100%' })
                                        }}
                                      >
                                        {currentPos === 'bottom' && <div className={`w-px h-3 ${isProfit ? 'bg-green-400' : 'bg-red-400'}`} />}
                                        <div className={`text-[9px] whitespace-nowrap font-semibold ${isProfit ? 'text-green-400' : 'text-red-400'} ${currentPos === 'top' ? 'mb-0.5' : 'mt-0.5'}`}>
                                          {pnl.percent >= 0 ? '+' : ''}{pnl.percent.toFixed(2)}% {formatPrice(currentPriceValue, position.product_id || 'ETH-BTC')}
                                        </div>
                                        {currentPos === 'top' && <div className={`w-px h-3 ${isProfit ? 'bg-green-400' : 'bg-red-400'}`} />}
                                      </div>

                                      {/* Target Price (MP) */}
                                      <div
                                        className="absolute flex flex-col items-center"
                                        style={{
                                          left: `${Math.max(0, Math.min(100, targetPosition))}%`,
                                          transform: 'translateX(-50%)',
                                          ...(targetPos === 'top' ? { bottom: '100%' } : { top: '100%' })
                                        }}
                                      >
                                        {targetPos === 'bottom' && <div className="w-px h-3 bg-emerald-400" />}
                                        <div className={`text-[9px] text-emerald-400 whitespace-nowrap ${targetPos === 'top' ? 'mb-0.5' : 'mt-0.5'}`}>
                                          MP {formatPrice(targetPrice, position.product_id || 'ETH-BTC')}
                                        </div>
                                        {targetPos === 'top' && <div className="w-px h-3 bg-emerald-400" />}
                                      </div>

                                      {/* DCA Level Tick Marks (only for non-AI bots with fixed DCA targets) */}
                                      {(() => {
                                        // Skip DCA tick marks for AI-controlled bots (they make dynamic DCA decisions)
                                        if (bot?.strategy_type === 'ai_autonomous') return null

                                        const minPriceDropForDCA = strategyConfig.min_price_drop_for_dca
                                        const maxDCAOrders = strategyConfig.max_safety_orders || 3

                                        if (!minPriceDropForDCA || position.status !== 'open') return null

                                        // Calculate completed DCAs (trade_count - 1 for initial trade)
                                        const completedDCAs = Math.max(0, (position.trade_count || 0) - 1)

                                        const dcaLevels = []
                                        const maxDCA = Math.min(maxDCAOrders, 3) // Limit to 3 to avoid clutter

                                        // Only show unfilled DCAs (start from completedDCAs + 1)
                                        for (let i = completedDCAs + 1; i <= maxDCA; i++) {
                                          const dropPercentage = minPriceDropForDCA * i
                                          const dcaPrice = entryPrice * (1 - dropPercentage / 100)
                                          const dcaPosition = ((dcaPrice - minPrice) / priceRange) * 100

                                          // Only show if visible on the bar (between 0-100%)
                                          if (dcaPosition >= 0 && dcaPosition <= 100) {
                                            dcaLevels.push(
                                              <div
                                                key={`dca-${i}`}
                                                className="absolute flex flex-col items-center"
                                                style={{
                                                  left: `${dcaPosition}%`,
                                                  transform: 'translateX(-50%)',
                                                  top: '100%'
                                                }}
                                              >
                                                <div className="w-px h-2 bg-purple-400" />
                                                <div className="text-[8px] text-purple-400 whitespace-nowrap mt-0.5">
                                                  DCA{i}
                                                </div>
                                              </div>
                                            )
                                          }
                                        }

                                        return dcaLevels
                                      })()}
                                    </>
                                  )
                                })()}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Column 4: Volume (2 cols) */}
                      <div className="col-span-2">
                        <div className="text-[10px] space-y-0.5">
                          <div className="text-white">
                            {formatQuoteAmount(position.total_quote_spent, position.product_id || 'ETH-BTC')}
                            {getQuoteCurrency(position.product_id || 'ETH-BTC').symbol === 'BTC' && btcUsdPrice > 0 && (
                              <span className="text-slate-400">
                                {' '}(${(position.total_quote_spent * btcUsdPrice).toLocaleString(undefined, { maximumFractionDigits: 2 })})
                              </span>
                            )}
                          </div>
                          <div className="text-slate-400">{formatBaseAmount(position.total_base_acquired, position.product_id || 'ETH-BTC')}</div>
                          {pnl && pnl.usd !== undefined && (
                            <div className={pnl.btc >= 0 ? 'text-green-400' : 'text-red-400'}>
                              {pnl.btc >= 0 ? '+' : ''}${Math.abs(pnl.usd).toFixed(2)}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Column 5: Avg. O (Averaging Orders) - Like 3Commas (1 col) */}
                      <div className="col-span-1">
                        <div className="text-[10px] space-y-0.5">
                          <div className="text-slate-400">
                            Completed: {(() => {
                              // Calculate DCA count from trade_count (total trades - 1 initial = DCA count)
                              // If trades array is available, use it for more detail
                              if (trades && trades.length > 0) {
                                const positionTrades = trades.filter(t => t.position_id === position.id && t.side === 'buy') || []
                                const autoSO = positionTrades.filter(t => t.trade_type === 'dca').length
                                const manualSO = positionTrades.filter(t => t.trade_type === 'manual_safety_order').length

                                if (manualSO > 0) {
                                  return `${autoSO} (+${manualSO})`
                                }
                                return autoSO
                              }

                              // Fallback: use trade_count from position (trade_count - 1 = DCA count)
                              const dcaCount = Math.max(0, (position.trade_count || 0) - 1)
                              return dcaCount
                            })()}
                          </div>
                          <div className="text-slate-400">Active: {position.pending_orders_count || 0}</div>
                          <div className="text-slate-400">
                            Max: {bot?.strategy_type === 'ai_autonomous' ? 'None' : (position.strategy_config_snapshot?.max_safety_orders || 0)}
                          </div>
                        </div>
                      </div>

                      {/* Column 6: Created (1 col) */}
                      <div className="col-span-1">
                        <div className="text-[10px] space-y-0.5">
                          <div className="text-slate-400">ID: {position.id}</div>
                          <div className="text-slate-400">Start: {formatDateTimeCompact(position.opened_at)}</div>
                        </div>
                      </div>
                    </div>

                    {/* Our Special "Better than 3Commas" Budget Usage Bar */}
                    <div className="mt-3 px-4">
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="text-slate-400">Budget Used</span>
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

                    {/* Action Buttons Row */}
                    <div className="mt-3 px-4 flex items-center gap-3">
                      <button
                        className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1"
                        onClick={(e) => {
                          e.stopPropagation()
                          setSelectedPosition(null)
                        }}
                      >
                        <span>🚫</span> Cancel
                      </button>
                      <button
                        className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                        onClick={(e) => {
                          e.stopPropagation()
                          setCloseConfirmPositionId(position.id)
                          setShowCloseConfirm(true)
                        }}
                      >
                        <span>💱</span> Close at market
                      </button>
                      <button
                        className="text-xs text-green-400 hover:text-green-300 flex items-center gap-1"
                        onClick={(e) => {
                          e.stopPropagation()
                          setLimitClosePosition(position)
                          setShowLimitCloseModal(true)
                        }}
                      >
                        <span>📊</span> Close at limit
                      </button>
                      <button
                        className="text-xs text-slate-400 hover:text-slate-300 flex items-center gap-1"
                        onClick={(e) => {
                          e.stopPropagation()
                          setShowLogsModal(true)
                          setLogsModalPosition(position)
                        }}
                      >
                        <span>📊</span> AI Reasoning
                      </button>
                      <button
                        className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center gap-1"
                        onClick={(e) => {
                          e.stopPropagation()
                          openAddFundsModal(position.id, position)
                        }}
                      >
                        <span>💰</span> Add funds
                      </button>
                      <button
                        className="text-xs text-slate-400 hover:text-slate-300 flex items-center gap-1"
                        onClick={(e) => {
                          e.stopPropagation()
                          refetchPositions()
                        }}
                      >
                        <span>🔄</span> Refresh
                      </button>
                    </div>

                    {/* Notes Section (like 3Commas) */}
                    <div className="mt-3 px-4 pb-3">
                      <div
                        className="text-xs flex items-center gap-2 cursor-pointer hover:opacity-70 transition-opacity"
                        onClick={(e) => {
                          e.stopPropagation()
                          openNotesModal(position)
                        }}
                      >
                        <span>📝</span>
                        {position.notes ? (
                          <span className="text-slate-300">{position.notes}</span>
                        ) : (
                          <span className="text-slate-500 italic">You can place a note here</span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Expandable Details Section (keep existing chart/details) */}
                  {selectedPosition === position.id && (
                    <div className="border-t border-slate-700 bg-slate-900/50 p-6">
                      <DealChart
                        position={position}
                        productId={position.product_id || "ETH-BTC"}
                        currentPrice={currentPrice}
                        trades={trades}
                      />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Close Position Confirmation Modal */}
      {showCloseConfirm && closeConfirmPositionId && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg w-full max-w-md p-6">
            <h2 className="text-xl font-bold mb-4 text-red-400 flex items-center gap-2">
              <span>⚠️</span> Close Position at Market Price
            </h2>

            <p className="text-slate-300 mb-4">
              This will immediately sell the entire position at the current market price.
            </p>

            <p className="text-slate-400 text-sm mb-6">
              <strong>Warning:</strong> This action cannot be undone. The position will be closed and profits/losses will be realized.
            </p>

            <div className="flex gap-3">
              <button
                onClick={() => {
                  setShowCloseConfirm(false)
                  setCloseConfirmPositionId(null)
                }}
                className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
                disabled={isProcessing}
              >
                Cancel
              </button>
              <button
                onClick={handleClosePosition}
                className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg font-semibold transition-colors"
                disabled={isProcessing}
              >
                {isProcessing ? 'Closing...' : 'Close Position'}
              </button>
            </div>
          </div>
        </div>
      )}

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
                  className="flex-1 bg-slate-700 hover:bg-slate-600 text-white px-2 sm:px-4 py-2 sm:py-3 rounded-lg font-medium transition-colors"
                  disabled={isProcessing}
                >
                  Cancel
                </button>
                <button
                  onClick={handleAddFunds}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 text-white px-2 sm:px-4 py-2 sm:py-3 rounded-lg font-medium transition-colors disabled:opacity-50"
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

      {/* TradingView Chart Modal */}
      <TradingViewChartModal
        isOpen={showChartModal}
        onClose={() => setShowChartModal(false)}
        symbol={chartModalSymbol}
        position={chartModalPosition}
      />

      {/* Lightweight Chart Modal */}
      <LightweightChartModal
        isOpen={showLightweightChart}
        onClose={() => setShowLightweightChart(false)}
        symbol={lightweightChartSymbol}
        position={lightweightChartPosition}
      />

      {/* Notes Modal (like 3Commas) */}
      {showNotesModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-lg w-full max-w-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-bold text-white">Edit Note</h3>
              <button
                onClick={() => setShowNotesModal(false)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X size={24} />
              </button>
            </div>

            <div className="mb-4">
              <textarea
                value={notesText}
                onChange={(e) => setNotesText(e.target.value)}
                onKeyDown={(e) => {
                  // Save on Cmd+Enter or Ctrl+Enter
                  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                    handleSaveNotes()
                  }
                }}
                className="w-full bg-slate-700 border border-slate-600 rounded px-2 sm:px-4 py-2 sm:py-3 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 min-h-[120px] resize-y"
                placeholder="Add a note for this position..."
                autoFocus
                disabled={isProcessing}
              />
              <p className="text-xs text-slate-400 mt-2">Cmd + Enter to save</p>
            </div>

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowNotesModal(false)}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg font-medium transition-colors"
                disabled={isProcessing}
              >
                Cancel
              </button>
              <button
                onClick={handleSaveNotes}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2 disabled:opacity-50"
                disabled={isProcessing}
              >
                <span>✓</span> Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Limit Close Modal */}
      {showLimitCloseModal && limitClosePosition && (
        <LimitCloseModal
          positionId={limitClosePosition.id}
          productId={limitClosePosition.product_id || 'ETH-BTC'}
          totalAmount={limitClosePosition.total_base_acquired}
          quoteCurrency={limitClosePosition.product_id?.split('-')[1] || 'BTC'}
          onClose={() => {
            setShowLimitCloseModal(false)
            setLimitClosePosition(null)
          }}
          onSuccess={() => {
            refetchPositions()
          }}
        />
      )}
    </div>
  )
}
