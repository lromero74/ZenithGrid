import { useQuery } from '@tanstack/react-query'
import { positionsApi, botsApi } from '../services/api'
import { format } from 'date-fns'
import { useState, useEffect, useRef } from 'react'
import {
  TrendingUp,
  TrendingDown,
  ChevronDown,
  ChevronUp,
  X,
  Plus,
  AlertCircle,
  Clock,
  Target,
  DollarSign,
  BarChart3,
  Brain
} from 'lucide-react'
import { createChart, ColorType, IChartApi, ISeriesApi, Time } from 'lightweight-charts'
import axios from 'axios'
import type { Position, Trade } from '../types'
import PositionLogsModal from '../components/PositionLogsModal'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface CandleData {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

// Deal Chart Component
function DealChart({ position, productId, currentPrice }: { position: Position, productId: string, currentPrice?: number }) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const [timeframe, setTimeframe] = useState('FIFTEEN_MINUTE')
  const [chartData, setChartData] = useState<CandleData[]>([])

  const timeframes = [
    { value: 'FIVE_MINUTE', label: '5m' },
    { value: 'FIFTEEN_MINUTE', label: '15m' },
    { value: 'THIRTY_MINUTE', label: '30m' },
    { value: 'ONE_HOUR', label: '1h' },
    { value: 'FOUR_HOUR', label: '4h' },
    { value: 'ONE_DAY', label: '1d' },
  ]

  // Fetch bot configuration
  const { data: bot } = useQuery({
    queryKey: ['bot', position.bot_id],
    queryFn: () => position.bot_id ? botsApi.getById(position.bot_id) : null,
    enabled: !!position.bot_id,
  })

  // Fetch candle data
  useEffect(() => {
    const fetchCandles = async () => {
      try {
        const response = await axios.get(`${API_BASE}/api/candles`, {
          params: {
            product_id: productId,
            granularity: timeframe,
            limit: 100,
          },
        })
        setChartData(response.data.candles || [])
      } catch (err) {
        console.error('Error fetching candles:', err)
      }
    }
    fetchCandles()
  }, [productId, timeframe])

  // Initialize and update chart
  useEffect(() => {
    if (!chartContainerRef.current || chartData.length === 0) return

    // Create chart if it doesn't exist
    if (!chartRef.current) {
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
        height: 300,
        timeScale: {
          timeVisible: true,
          secondsVisible: false,
        },
        rightPriceScale: {
          borderColor: '#334155',
          scaleMargins: {
            top: 0.1,
            bottom: 0.1,
          },
        },
      })

      chartRef.current = chart
    }

    const chart = chartRef.current

    // Clear existing series
    const allSeries = (chart as any)._private__seriesMap
    if (allSeries) {
      allSeries.forEach((series: any) => {
        try {
          chart.removeSeries(series)
        } catch (e) {
          // Ignore
        }
      })
    }

    // Determine price format
    const isBTCPair = productId.endsWith('-BTC')
    const priceFormat = isBTCPair
      ? { type: 'price' as const, precision: 8, minMove: 0.00000001 }
      : { type: 'price' as const, precision: 2, minMove: 0.01 }

    // Add candlestick series
    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
      priceFormat: priceFormat,
    })

    const priceData = chartData.map((c) => ({
      time: c.time as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }))

    candleSeries.setData(priceData)

    // Add price markers
    const markers: any[] = []

    // Add average entry price line
    const entryLineSeries = chart.addLineSeries({
      color: '#3b82f6',
      lineWidth: 2,
      lineStyle: 2, // Dashed
      priceLineVisible: false,
      lastValueVisible: true,
      title: 'Avg Entry',
      priceFormat: priceFormat,
    })

    const entryLineData = chartData.map((c) => ({
      time: c.time as Time,
      value: position.average_buy_price,
    }))

    entryLineSeries.setData(entryLineData)

    // Add Take Profit line (2% above entry as default)
    const takeProfitPrice = position.average_buy_price * 1.02
    const takeProfitSeries = chart.addLineSeries({
      color: '#10b981', // Green
      lineWidth: 2,
      lineStyle: 2, // Dashed
      priceLineVisible: false,
      lastValueVisible: true,
      title: 'Take Profit',
      priceFormat: priceFormat,
    })

    const takeProfitData = chartData.map((c) => ({
      time: c.time as Time,
      value: takeProfitPrice,
    }))

    takeProfitSeries.setData(takeProfitData)

    // Add Stop Loss line (2% below entry as default - only if position is open)
    if (position.status === 'open') {
      const stopLossPrice = position.average_buy_price * 0.98
      const stopLossSeries = chart.addLineSeries({
        color: '#ef4444', // Red
        lineWidth: 2,
        lineStyle: 2, // Dashed
        priceLineVisible: false,
        lastValueVisible: true,
        title: 'Stop Loss',
        priceFormat: priceFormat,
      })

      const stopLossData = chartData.map((c) => ({
        time: c.time as Time,
        value: stopLossPrice,
      }))

      stopLossSeries.setData(stopLossData)
    }

    // Add Safety Order price levels (gray dashed lines)
    if (bot && position.status === 'open') {
      const config = bot.strategy_config
      const priceDeviation = config.price_deviation || 2.0
      const stepScale = config.safety_order_step_scale || 1.0
      const maxSafetyOrders = config.max_safety_orders || 5

      // Calculate safety order price levels
      let cumulativeDeviation = priceDeviation
      for (let i = 0; i < maxSafetyOrders; i++) {
        const soPrice = position.average_buy_price * (1 - cumulativeDeviation / 100)

        const soSeries = chart.addLineSeries({
          color: '#64748b', // Gray
          lineWidth: 1,
          lineStyle: 2, // Dashed
          priceLineVisible: false,
          lastValueVisible: false,
          title: `SO${i + 1}`,
          priceFormat: priceFormat,
        })

        const soData = chartData.map((c) => ({
          time: c.time as Time,
          value: soPrice,
        }))

        soSeries.setData(soData)

        // Calculate next safety order deviation
        cumulativeDeviation += priceDeviation * Math.pow(stepScale, i)
      }
    }

    // Add current price marker
    if (chartData.length > 0) {
      const lastCandle = chartData[chartData.length - 1]
      markers.push({
        time: lastCandle.time as Time,
        position: 'inBar',
        color: '#3b82f6',
        shape: 'circle',
        text: 'Current',
      })
    }

    // Add position opened marker
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

    candleSeries.setMarkers(markers)

    chart.timeScale().fitContent()

    return () => {
      if (chartRef.current) {
        chartRef.current.remove()
        chartRef.current = null
      }
    }
  }, [chartData, position, productId, bot, currentPrice])

  return (
    <div className="space-y-3">
      {/* Timeframe Selector */}
      <div className="flex items-center justify-between">
        <h4 className="font-semibold text-white flex items-center gap-2">
          <BarChart3 size={18} />
          Price Chart
        </h4>
        <div className="flex gap-1">
          {timeframes.map((tf) => (
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
      </div>

      {/* Chart Container */}
      <div className="bg-slate-900 rounded-lg border border-slate-700 p-2">
        <div ref={chartContainerRef} />
      </div>

      {/* Price Legend */}
      <div className="space-y-2">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
          <div className="flex items-center gap-2">
            <div className="w-8 h-0.5 bg-blue-500" style={{ borderTop: '2px dashed' }} />
            <span className="text-slate-400">Entry: {position.average_buy_price.toFixed(8)}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-0.5 bg-green-500" style={{ borderTop: '2px dashed' }} />
            <span className="text-green-400">TP: {(position.average_buy_price * 1.02).toFixed(8)}</span>
          </div>
          {position.status === 'open' && (
            <div className="flex items-center gap-2">
              <div className="w-8 h-0.5 bg-red-500" style={{ borderTop: '2px dashed' }} />
              <span className="text-red-400">SL: {(position.average_buy_price * 0.98).toFixed(8)}</span>
            </div>
          )}
          {(currentPrice || chartData.length > 0) && (
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-blue-500" />
              <span className="text-slate-400">
                Current: {(currentPrice || chartData[chartData.length - 1]?.close || 0).toFixed(8)}
              </span>
            </div>
          )}
        </div>
        {/* Safety Order Levels */}
        {bot && position.status === 'open' && (() => {
          const config = bot.strategy_config
          const priceDeviation = config.price_deviation || 2.0
          const stepScale = config.safety_order_step_scale || 1.0
          const maxSafetyOrders = config.max_safety_orders || 5
          const soLevels = []

          let cumulativeDeviation = priceDeviation
          for (let i = 0; i < Math.min(maxSafetyOrders, 3); i++) {
            const soPrice = position.average_buy_price * (1 - cumulativeDeviation / 100)
            soLevels.push({ level: i + 1, price: soPrice })
            cumulativeDeviation += priceDeviation * Math.pow(stepScale, i)
          }

          return (
            <div className="flex items-center gap-3 text-xs flex-wrap">
              <div className="flex items-center gap-1">
                <div className="w-6 h-0.5 bg-slate-500" style={{ borderTop: '1px dashed' }} />
                <span className="text-slate-500">Safety Orders:</span>
              </div>
              {soLevels.map(({ level, price }) => (
                <span key={level} className="text-slate-400">
                  SO{level}: {price.toFixed(8)}
                </span>
              ))}
              {maxSafetyOrders > 3 && (
                <span className="text-slate-500">+{maxSafetyOrders - 3} more</span>
              )}
            </div>
          )
        })()}
      </div>
    </div>
  )
}

export default function Positions() {
  const [selectedPosition, setSelectedPosition] = useState<number | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [showAddFundsModal, setShowAddFundsModal] = useState(false)
  const [addFundsAmount, setAddFundsAmount] = useState('')
  const [addFundsPositionId, setAddFundsPositionId] = useState<number | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [currentPrices, setCurrentPrices] = useState<Record<string, number>>({})
  const [showLogsModal, setShowLogsModal] = useState(false)
  const [logsModalPosition, setLogsModalPosition] = useState<Position | null>(null)

  const { data: allPositions } = useQuery({
    queryKey: ['positions'],
    queryFn: () => positionsApi.getAll(undefined, 100),
    refetchInterval: 5000, // Update every 5 seconds for active deals
  })

  // Fetch real-time prices for all open positions
  useEffect(() => {
    const fetchPrices = async () => {
      if (!allPositions) return

      const openPositions = allPositions.filter(p => p.status === 'open')
      const pricePromises = openPositions.map(async (position) => {
        try {
          const response = await axios.get(`${API_BASE}/api/ticker/${position.product_id || 'ETH-BTC'}`)
          return { product_id: position.product_id || 'ETH-BTC', price: response.data.price }
        } catch (err) {
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

    return () => clearInterval(interval)
  }, [allPositions])

  const { data: trades } = useQuery({
    queryKey: ['position-trades', selectedPosition],
    queryFn: () => positionsApi.getTrades(selectedPosition!),
    enabled: selectedPosition !== null,
  })

  const openPositions = allPositions?.filter(p => p.status === 'open') || []
  const closedPositions = allPositions?.filter(p => p.status === 'closed') || []

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
    const remaining = position.max_btc_allowed - position.total_btc_spent
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

  const formatPrice = (price: number) => price.toFixed(8)

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
      btcAmount: trade.btc_amount,
      ethAmount: trade.eth_amount,
      price: trade.price,
      timestamp: trade.timestamp,
      filled: true
    }))
  }

  // Calculate unrealized P&L for open position
  const calculateUnrealizedPnL = (position: Position, currentPrice?: number) => {
    if (position.status !== 'open') return null

    // Use real-time price if available, otherwise fall back to average buy price
    const price = currentPrice || position.average_buy_price
    const currentValue = position.total_eth_acquired * price
    const costBasis = position.total_btc_spent
    const unrealizedPnL = currentValue - costBasis
    const unrealizedPnLPercent = (unrealizedPnL / costBasis) * 100

    return {
      btc: unrealizedPnL,
      percent: unrealizedPnLPercent,
      usd: unrealizedPnL * (position.btc_usd_price_at_open || 0),
      currentPrice: price
    }
  }

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
              const fundsUsedPercent = (position.total_btc_spent / position.max_btc_allowed) * 100

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
                                  {pnl.btc >= 0 ? '+' : ''}{formatCrypto(pnl.btc, 8)} BTC
                                </p>
                              </div>
                            )}
                          </div>

                          {/* Current Price */}
                          <div>
                            <p className="text-slate-400 text-xs mb-1">Current Price</p>
                            {pnl && (
                              <div>
                                <p className="text-white font-semibold">{formatPrice(pnl.currentPrice)}</p>
                                <p className={`text-xs ${pnl.btc >= 0 ? 'text-green-400/70' : 'text-red-400/70'}`}>
                                  {pnl.btc >= 0 ? '▲' : '▼'} {Math.abs(pnl.percent).toFixed(2)}%
                                </p>
                              </div>
                            )}
                          </div>

                          {/* Invested */}
                          <div>
                            <p className="text-slate-400 text-xs mb-1">Invested</p>
                            <p className="text-white font-semibold">{formatCrypto(position.total_btc_spent, 8)} BTC</p>
                            <p className="text-slate-400 text-xs">{position.trade_count} orders filled</p>
                          </div>

                          {/* Average Price */}
                          <div>
                            <p className="text-slate-400 text-xs mb-1">Avg Entry Price</p>
                            <p className="text-white font-semibold">{formatPrice(position.average_buy_price)}</p>
                          </div>

                          {/* Opened */}
                          <div>
                            <p className="text-slate-400 text-xs mb-1">Opened</p>
                            <p className="text-white font-semibold">
                              {format(new Date(position.opened_at), 'MMM dd, HH:mm')}
                            </p>
                          </div>
                        </div>

                        {/* Funds Usage Bar */}
                        <div className="mt-4">
                          <div className="flex items-center justify-between text-xs mb-1">
                            <span className="text-slate-400">Funds Used</span>
                            <span className="text-slate-300">
                              {formatCrypto(position.total_btc_spent, 8)} / {formatCrypto(position.max_btc_allowed, 8)} BTC
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
                                        {format(new Date(order.timestamp), 'MMM dd, HH:mm:ss')}
                                      </p>
                                    </div>
                                  </div>
                                  <div className="text-right">
                                    <p className="text-sm text-white font-mono">{formatCrypto(order.btcAmount, 8)} BTC</p>
                                    <p className="text-xs text-slate-400">@ {formatPrice(order.price)}</p>
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
                              {formatCrypto(position.total_eth_acquired, 6)} {(position.product_id || 'ETH-BTC').split('-')[0]}
                            </p>
                          </div>
                          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
                            <p className="text-slate-400 text-xs mb-1">Max Funds</p>
                            <p className="text-white font-semibold">
                              {formatCrypto(position.max_btc_allowed, 8)} {(position.product_id || 'ETH-BTC').split('-')[1]}
                            </p>
                          </div>
                          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
                            <p className="text-slate-400 text-xs mb-1">Remaining</p>
                            <p className="text-white font-semibold">
                              {formatCrypto(position.max_btc_allowed - position.total_btc_spent, 8)} {(position.product_id || 'ETH-BTC').split('-')[1]}
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

      {/* Closed Position History */}
      <div>
        <div
          className="flex items-center justify-between cursor-pointer hover:bg-slate-800/50 rounded-lg p-4 transition-colors"
          onClick={() => setShowHistory(!showHistory)}
        >
          <h2 className="text-2xl font-bold text-white">Position History</h2>
          <div className="flex items-center gap-3">
            <span className="text-slate-400">{closedPositions.length} closed</span>
            {showHistory ? (
              <ChevronUp className="w-5 h-5 text-slate-400" />
            ) : (
              <ChevronDown className="w-5 h-5 text-slate-400" />
            )}
          </div>
        </div>

        {showHistory && closedPositions.length > 0 && (
          <div className="mt-4 space-y-3">
            {closedPositions.map((position) => (
              <div key={position.id} className="bg-slate-800 rounded-lg border border-slate-700 p-4">
                <div className="grid grid-cols-1 md:grid-cols-6 gap-4">
                  <div>
                    <p className="text-slate-400 text-xs mb-1">Deal</p>
                    <div className="flex items-center gap-2">
                      <p className="font-semibold text-white">#{position.id}</p>
                      <span className="bg-purple-500/20 text-purple-400 px-1.5 py-0.5 rounded text-xs font-medium">
                        {position.product_id || 'ETH-BTC'}
                      </span>
                    </div>
                  </div>
                  <div>
                    <p className="text-slate-400 text-xs mb-1">Opened</p>
                    <p className="font-semibold text-white">
                      {format(new Date(position.opened_at), 'MMM dd, HH:mm')}
                    </p>
                  </div>
                  <div>
                    <p className="text-slate-400 text-xs mb-1">Closed</p>
                    <p className="font-semibold text-white">
                      {position.closed_at ? format(new Date(position.closed_at), 'MMM dd, HH:mm') : '-'}
                    </p>
                  </div>
                  <div>
                    <p className="text-slate-400 text-xs mb-1">Invested</p>
                    <p className="font-semibold text-white">{formatCrypto(position.total_btc_spent, 8)} BTC</p>
                  </div>
                  <div>
                    <p className="text-slate-400 text-xs mb-1">Orders</p>
                    <p className="font-semibold text-white">{position.trade_count}</p>
                  </div>
                  <div>
                    <p className="text-slate-400 text-xs mb-1">Profit</p>
                    {position.profit_btc !== null ? (
                      <div>
                        <div className="flex items-center gap-1">
                          {position.profit_btc >= 0 ? (
                            <TrendingUp className="w-3 h-3 text-green-500" />
                          ) : (
                            <TrendingDown className="w-3 h-3 text-red-500" />
                          )}
                          <span className={`font-semibold ${position.profit_btc >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {position.profit_percentage?.toFixed(2)}%
                          </span>
                        </div>
                        <p className={`text-xs ${position.profit_btc >= 0 ? 'text-green-400/70' : 'text-red-400/70'}`}>
                          {formatCrypto(position.profit_btc, 8)} BTC
                        </p>
                      </div>
                    ) : (
                      <p className="font-semibold text-slate-400">-</p>
                    )}
                  </div>
                </div>
              </div>
            ))}
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
