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

interface PnLTimeSeriesData {
  summary: PnLDataPoint[]
  by_day: DailyPnL[]
  by_pair: PairPnL[]
}

type TimeRange = '7d' | '30d' | '3m' | '6m' | 'all'
type TabType = 'summary' | 'by_day' | 'by_pair'

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
      chartRef.current.remove()
      chartRef.current = null
      areaSeriesRef.current = null
    }

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 350,
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
        })
      }
    }

    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
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
      {/* Header with Stats */}
      <div className="p-4 sm:p-6 border-b border-slate-800">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          {/* Total P&L */}
          <div className="bg-slate-800/50 rounded-lg p-4">
            <div className="text-xs text-slate-400 mb-1">Total P&L</div>
            <div className={`text-2xl font-bold ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
              {isProfit ? '+' : ''}${stats.totalPnL.toFixed(2)}
            </div>
          </div>

          {/* Closed Trades */}
          <div className="bg-slate-800/50 rounded-lg p-4">
            <div className="text-xs text-slate-400 mb-1">Closed Trades</div>
            <div className="text-2xl font-bold text-white">{stats.closedTrades}</div>
          </div>

          {/* Best Pair */}
          <div className="bg-slate-800/50 rounded-lg p-4">
            <div className="text-xs text-slate-400 mb-1">Best Pair</div>
            <div className="text-sm font-semibold text-white">{stats.bestPair?.pair || 'N/A'}</div>
            {stats.bestPair && (
              <div className="text-xs text-green-400">
                +${stats.bestPair.total_pnl.toFixed(2)}
              </div>
            )}
          </div>

          {/* Worst Pair */}
          <div className="bg-slate-800/50 rounded-lg p-4">
            <div className="text-xs text-slate-400 mb-1">Worst Pair</div>
            <div className="text-sm font-semibold text-white">{stats.worstPair?.pair || 'N/A'}</div>
            {stats.worstPair && (
              <div className={`text-xs ${stats.worstPair.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {stats.worstPair.total_pnl >= 0 ? '+' : ''}${stats.worstPair.total_pnl.toFixed(2)}
              </div>
            )}
          </div>
        </div>

        {/* Tabs and Time Range */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          {/* Tabs */}
          <div className="flex gap-2">
            <button
              onClick={() => setActiveTab('summary')}
              className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                activeTab === 'summary'
                  ? 'bg-blue-500 text-white'
                  : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
              }`}
            >
              Summary PnL
            </button>
            <button
              onClick={() => setActiveTab('by_day')}
              className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                activeTab === 'by_day'
                  ? 'bg-blue-500 text-white'
                  : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
              }`}
            >
              PnL by Day
            </button>
            <button
              onClick={() => setActiveTab('by_pair')}
              className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
                activeTab === 'by_pair'
                  ? 'bg-blue-500 text-white'
                  : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
              }`}
            >
              PnL by Pair
            </button>
          </div>

          {/* Time Range */}
          <div className="flex gap-2 items-center">
            <Calendar className="w-4 h-4 text-slate-400" />
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value as TimeRange)}
              className="bg-slate-800 text-white px-3 py-1.5 rounded text-sm border border-slate-700 focus:border-blue-500 focus:outline-none"
            >
              <option value="7d">Last 7 days</option>
              <option value="30d">Last 30 days</option>
              <option value="3m">Last 3 months</option>
              <option value="6m">Last 6 months</option>
              <option value="all">All time</option>
            </select>
          </div>
        </div>
      </div>

      {/* Chart or Table */}
      <div className="p-4 sm:p-6">
        {activeTab === 'by_day' ? (
          // Daily P&L bar chart
          <ResponsiveContainer width="100%" height={350}>
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
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '6px',
                  color: '#f1f5f9'
                }}
                labelFormatter={(date) => new Date(date).toLocaleDateString()}
                formatter={(value: number) => [`$${value.toFixed(2)}`, 'Daily P&L']}
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
          <ResponsiveContainer width="100%" height={350}>
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
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '6px',
                  color: '#f1f5f9'
                }}
                formatter={(value: number) => [`$${value.toFixed(2)}`, 'Total P&L']}
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
          <div ref={chartContainerRef} className="w-full h-[350px]" />
        )}
      </div>
    </div>
  )
}
