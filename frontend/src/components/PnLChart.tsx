import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { createChart, ColorType, IChartApi, ISeriesApi, Time, LineStyle } from 'lightweight-charts'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { TrendingUp, TrendingDown, Calendar } from 'lucide-react'
import { LoadingSpinner } from './LoadingSpinner'

interface PnLDataPoint {
  timestamp: string
  date: string
  cumulative_pnl: number
  profit: number
}

interface DailyPnL {
  date: string
  daily_pnl: number
  cumulative_pnl: number
}

interface PairPnL {
  pair: string
  total_pnl: number
}

interface MostProfitableBot {
  bot_id: number
  bot_name: string
  total_pnl: number
}

interface PnLTimeSeriesData {
  summary: PnLDataPoint[]
  by_day: DailyPnL[]
  by_pair: PairPnL[]
  active_trades: number
  most_profitable_bot: MostProfitableBot | null
}

type TimeRange = '7d' | '30d' | '3m' | '6m' | 'all'
type TabType = 'summary' | 'by_day' | 'by_pair'

// Custom tooltip component for 3Commas-style tooltips
const CustomTooltip = ({ active, payload, label, labelFormatter }: any) => {
  if (!active || !payload || !payload.length) return null

  const value = payload[0].value
  const isProfit = value >= 0

  // Convert USD to BTC (using approximate current BTC price)
  const btcValue = value / 100000 // Approximate conversion

  return (
    <div className="bg-slate-800 border-2 border-slate-600 rounded-lg p-3 shadow-lg">
      <div className="text-slate-300 text-sm mb-2">
        {labelFormatter ? labelFormatter(label) : label}
      </div>
      <div className={`text-base font-semibold ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
        Profit ${value.toFixed(2)} / {btcValue.toFixed(8)} BTC
      </div>
    </div>
  )
}

export function PnLChart() {
  const [activeTab, setActiveTab] = useState<TabType>('summary')
  const [timeRange, setTimeRange] = useState<TimeRange>('30d')
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const areaSeriesRef = useRef<ISeriesApi<'Area'> | null>(null)

  // Fetch P&L data
  const { data, isLoading } = useQuery<PnLTimeSeriesData>({
    queryKey: ['pnl-timeseries'],
    queryFn: async () => {
      const response = await fetch('/api/positions/pnl-timeseries')
      if (!response.ok) throw new Error('Failed to fetch P&L data')
      return response.json()
    },
    refetchInterval: 60000, // Refresh every minute
  })

  // Filter data by time range
  const getFilteredData = () => {
    if (!data) return []

    const now = new Date()
    const cutoffDate = new Date()

    switch (timeRange) {
      case '7d':
        cutoffDate.setDate(now.getDate() - 7)
        break
      case '30d':
        cutoffDate.setDate(now.getDate() - 30)
        break
      case '3m':
        cutoffDate.setMonth(now.getMonth() - 3)
        break
      case '6m':
        cutoffDate.setMonth(now.getMonth() - 6)
        break
      case 'all':
        return activeTab === 'summary' ? data.summary : activeTab === 'by_day' ? data.by_day : []
    }

    const filterByDate = (item: PnLDataPoint | DailyPnL) => {
      const itemDate = new Date(item.date)
      return itemDate >= cutoffDate
    }

    if (activeTab === 'summary') {
      return data.summary.filter(filterByDate)
    } else if (activeTab === 'by_day') {
      return data.by_day.filter(filterByDate)
    }

    return []
  }

  // Calculate stats
  const calculateStats = () => {
    if (!data || data.summary.length === 0) {
      return {
        totalPnL: 0,
        closedTrades: 0,
        bestPair: null as PairPnL | null,
        worstPair: null as PairPnL | null
      }
    }

    const filteredData = getFilteredData()
    const totalPnL = filteredData.length > 0
      ? filteredData[filteredData.length - 1].cumulative_pnl
      : 0

    const closedTrades = filteredData.length

    const bestPair = data.by_pair.length > 0 ? data.by_pair[0] : null
    const worstPair = data.by_pair.length > 0 ? data.by_pair[data.by_pair.length - 1] : null

    return { totalPnL, closedTrades, bestPair, worstPair }
  }

  // Initialize chart - recreate when switching to summary tab
  useEffect(() => {
    if (!chartContainerRef.current || !data || activeTab !== 'summary') return

    // Clean up existing chart if any
    if (chartRef.current) {
      try {
        chartRef.current.remove()
      } catch (e) {
        // Chart already disposed, ignore
      }
      chartRef.current = null
      areaSeriesRef.current = null
    }

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: '#0f172a' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      crosshair: {
        mode: 1,
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: '#1e293b',
      },
      rightPriceScale: {
        borderColor: '#1e293b',
      },
    })

    const areaSeries = chart.addAreaSeries({
      topColor: 'rgba(34, 197, 94, 0.4)',
      bottomColor: 'rgba(34, 197, 94, 0.0)',
      lineColor: 'rgba(34, 197, 94, 1)',
      lineWidth: 2,
    })

    chartRef.current = chart
    areaSeriesRef.current = areaSeries

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chart) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        })
      }
    }

    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      try {
        if (chart) {
          chart.remove()
        }
      } catch (e) {
        // Chart already disposed, ignore
      }
    }
  }, [data, activeTab])

  // Update chart data
  useEffect(() => {
    if (!areaSeriesRef.current || !data || activeTab !== 'summary') return

    const filteredData = getFilteredData()
    if (filteredData.length === 0) return

    // Convert to chart format
    const chartData = filteredData.map((point) => {
      const timestamp = Math.floor(new Date(point.date).getTime() / 1000) as Time
      return {
        time: timestamp,
        value: point.cumulative_pnl
      }
    })

    // Determine if we have profits or losses
    const latestValue = chartData[chartData.length - 1]?.value || 0
    const isProfit = latestValue >= 0

    // Update series colors based on profit/loss
    areaSeriesRef.current.applyOptions({
      topColor: isProfit ? 'rgba(34, 197, 94, 0.4)' : 'rgba(239, 68, 68, 0.4)',
      bottomColor: isProfit ? 'rgba(34, 197, 94, 0.0)' : 'rgba(239, 68, 68, 0.0)',
      lineColor: isProfit ? 'rgba(34, 197, 94, 1)' : 'rgba(239, 68, 68, 1)',
    })

    areaSeriesRef.current.setData(chartData)

    if (chartRef.current) {
      chartRef.current.timeScale().fitContent()
    }
  }, [data, activeTab, timeRange])

  const stats = calculateStats()

  if (isLoading) {
    return (
      <div className="bg-slate-900 rounded-lg p-6">
        <LoadingSpinner size="lg" text="Loading P&L data..." />
      </div>
    )
  }

  if (!data || data.summary.length === 0) {
    return (
      <div className="bg-slate-900 rounded-lg p-6">
        <div className="text-center text-slate-400 py-12">
          <TrendingUp className="w-12 h-12 mx-auto mb-3 text-slate-600" />
          <p>No closed positions yet</p>
          <p className="text-sm mt-2">P&L chart will appear after your first closed trade</p>
        </div>
      </div>
    )
  }

  const isProfit = stats.totalPnL >= 0

  return (
    <div className="bg-slate-900 rounded-lg overflow-hidden">
      {/* Time Range Pills - 3Commas style */}
      <div className="p-4 sm:p-6 border-b border-slate-800">
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => setTimeRange('all')}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
              timeRange === 'all'
                ? 'bg-emerald-500 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            All
          </button>
          <button
            onClick={() => setTimeRange('7d')}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
              timeRange === '7d'
                ? 'bg-emerald-500 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            7 days
          </button>
          <button
            onClick={() => setTimeRange('30d')}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
              timeRange === '30d'
                ? 'bg-emerald-500 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            30 days
          </button>
          <button
            onClick={() => setTimeRange('3m')}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
              timeRange === '3m'
                ? 'bg-emerald-500 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            3 months
          </button>
          <button
            onClick={() => setTimeRange('6m')}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
              timeRange === '6m'
                ? 'bg-emerald-500 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            6 months
          </button>
        </div>
      </div>

      {/* Stats Cards + Chart */}
      <div className="p-4 sm:p-6 flex gap-6">
        {/* Left sidebar - Stats Cards */}
        <div className="flex flex-col gap-3 w-72 flex-shrink-0">
          {/* Total P&L Card */}
          <div className="bg-slate-800/50 rounded-lg p-4">
            <div className="text-sm text-slate-400 mb-1">PnL</div>
            <div className={`text-2xl font-bold mb-2 ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
              {isProfit ? '' : '-'}${Math.abs(stats.totalPnL).toFixed(2)}
            </div>
          </div>

          {/* Closed Trades Card */}
          <div className="bg-slate-800/50 rounded-lg p-4">
            <div className="text-sm text-slate-400 mb-1">Closed trades</div>
            <div className="text-3xl font-bold text-white mb-1">{stats.closedTrades}</div>
            <div className="text-xs text-slate-500">Active trades: {data.active_trades}</div>
          </div>

          {/* Best Pairs Card */}
          <div className="bg-slate-800/50 rounded-lg p-4">
            <div className="text-sm text-slate-400 mb-3">Best pairs</div>
            <div className="space-y-2">
              {data.by_pair.slice(0, 3).map((pair, index) => (
                <div key={pair.pair} className="flex items-center gap-2">
                  <span className="text-xs text-slate-500">#{index + 1}</span>
                  <span className="text-sm text-white flex-1">{pair.pair}</span>
                  <span className={`text-sm font-semibold ${pair.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {pair.total_pnl >= 0 ? '+' : ''}${pair.total_pnl.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Most Profitable Bot Card */}
          <div className="bg-slate-800/50 rounded-lg p-4">
            <div className="text-sm text-slate-400 mb-1">Most profitable bot</div>
            {data.most_profitable_bot ? (
              <>
                <div className={`text-2xl font-bold mb-1 ${data.most_profitable_bot.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {data.most_profitable_bot.total_pnl >= 0 ? '+' : ''}${data.most_profitable_bot.total_pnl.toFixed(2)}
                </div>
                <div className="text-xs text-blue-400 truncate">{data.most_profitable_bot.bot_name}</div>
              </>
            ) : (
              <div className="text-sm text-slate-500">No data</div>
            )}
          </div>
        </div>

        {/* Right side - Chart Type Tabs + Chart */}
        <div className="flex-1 min-h-0 flex flex-col">
          {/* Chart Type Tabs */}
          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setActiveTab('summary')}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === 'summary'
                  ? 'bg-slate-700 text-white border-b-2 border-blue-500'
                  : 'text-slate-400 hover:text-slate-300'
              }`}
            >
              Summary PnL
            </button>
            <button
              onClick={() => setActiveTab('by_day')}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === 'by_day'
                  ? 'bg-slate-700 text-white border-b-2 border-blue-500'
                  : 'text-slate-400 hover:text-slate-300'
              }`}
            >
              PnL by day
            </button>
            <button
              onClick={() => setActiveTab('by_pair')}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === 'by_pair'
                  ? 'bg-slate-700 text-white border-b-2 border-blue-500'
                  : 'text-slate-400 hover:text-slate-300'
              }`}
            >
              PnL by pair
            </button>
          </div>

          {/* Chart Container */}
          <div className="flex-1 min-h-0">
        {activeTab === 'by_day' ? (
          // Daily P&L bar chart
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={getFilteredData()} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis
                dataKey="date"
                tick={{ fill: '#94a3b8', fontSize: 12 }}
                tickFormatter={(date) => {
                  const d = new Date(date)
                  return `${d.getMonth() + 1}/${d.getDate()}`
                }}
              />
              <YAxis
                tick={{ fill: '#94a3b8', fontSize: 12 }}
                tickFormatter={(value) => `$${value}`}
              />
              <Tooltip
                content={<CustomTooltip labelFormatter={(date: string) => new Date(date).toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric' })} />}
                cursor={false}
              />
              <Bar dataKey="daily_pnl" radius={[4, 4, 0, 0]}>
                {getFilteredData().map((entry: any, index: number) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={entry.daily_pnl >= 0 ? '#22c55e' : '#ef4444'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : activeTab === 'by_pair' ? (
          // Pair P&L bar chart
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.by_pair} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis
                dataKey="pair"
                angle={-45}
                textAnchor="end"
                height={80}
                tick={{ fill: '#94a3b8', fontSize: 12 }}
              />
              <YAxis
                tick={{ fill: '#94a3b8', fontSize: 12 }}
                tickFormatter={(value) => `$${value}`}
              />
              <Tooltip
                content={<CustomTooltip labelFormatter={(pair: string) => pair} />}
                cursor={false}
              />
              <Bar dataKey="total_pnl" radius={[4, 4, 0, 0]}>
                {data.by_pair.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={entry.total_pnl >= 0 ? '#22c55e' : '#ef4444'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          // Area chart for summary (cumulative P&L)
          <div ref={chartContainerRef} className="w-full h-full" />
        )}
          </div>
        </div>
      </div>
    </div>
  )
}
