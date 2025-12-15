import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { createChart, ColorType, IChartApi, ISeriesApi, Time } from 'lightweight-charts'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { TrendingUp } from 'lucide-react'
import { LoadingSpinner } from './LoadingSpinner'

interface PnLDataPoint {
  timestamp: string
  date: string
  cumulative_pnl: number
  profit: number
  product_id?: string
  bot_id?: number
  bot_name?: string
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

type TimeRange = '7d' | '14d' | '30d' | '3m' | '6m' | '1y' | 'all'
type TabType = 'summary' | 'by_day' | 'by_pair'

interface PnLChartProps {
  accountId?: number
}

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

export function PnLChart({ accountId }: PnLChartProps) {
  const [activeTab, setActiveTab] = useState<TabType>('summary')
  const [timeRange, setTimeRange] = useState<TimeRange>('30d')
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const areaSeriesRef = useRef<ISeriesApi<'Area'> | null>(null)

  // Fetch P&L data (filtered by account)
  const { data, isLoading } = useQuery<PnLTimeSeriesData>({
    queryKey: ['pnl-timeseries', accountId],
    queryFn: async () => {
      const url = accountId
        ? `/api/positions/pnl-timeseries?account_id=${accountId}`
        : '/api/positions/pnl-timeseries'
      const response = await fetch(url)
      if (!response.ok) throw new Error('Failed to fetch P&L data')
      return response.json()
    },
    refetchInterval: 60000, // Refresh every minute
  })

  // Calculate which time range buttons should be enabled based on data span
  const getEnabledTimeRanges = (): Set<TimeRange> => {
    const enabled = new Set<TimeRange>(['all']) // 'all' is always enabled

    if (!data || data.summary.length === 0) {
      return enabled
    }

    // Find the earliest date in the data
    const dates = data.summary.map(d => new Date(d.date).getTime())
    const earliestDate = new Date(Math.min(...dates))
    const now = new Date()
    const dataSpanDays = Math.ceil((now.getTime() - earliestDate.getTime()) / (1000 * 60 * 60 * 24))

    // Time range thresholds in days (ordered smallest to largest)
    const thresholds: { range: TimeRange; days: number }[] = [
      { range: '7d', days: 7 },
      { range: '14d', days: 14 },
      { range: '30d', days: 30 },
      { range: '3m', days: 90 },
      { range: '6m', days: 180 },
      { range: '1y', days: 365 },
    ]

    // Find the first threshold that covers all data
    let firstCoveringDays = Infinity
    for (const { days } of thresholds) {
      if (days >= dataSpanDays) {
        firstCoveringDays = days
        break
      }
    }

    // Enable all buttons up to and including the first one that shows all data
    // Disable buttons beyond that (they'd show the same as the covering one)
    for (const { range, days } of thresholds) {
      if (days <= firstCoveringDays) {
        enabled.add(range)
      }
    }

    return enabled
  }

  const enabledTimeRanges = getEnabledTimeRanges()

  // Filter data by time range
  const getFilteredData = () => {
    if (!data) return []

    const now = new Date()
    const cutoffDate = new Date()

    switch (timeRange) {
      case '7d':
        cutoffDate.setDate(now.getDate() - 7)
        break
      case '14d':
        cutoffDate.setDate(now.getDate() - 14)
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
      case '1y':
        cutoffDate.setFullYear(now.getFullYear() - 1)
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

  // Get by_day data with all dates filled in (no gaps)
  const getFilledByDayData = (): DailyPnL[] => {
    if (!data || data.by_day.length === 0) return []

    // First apply time range filter
    const now = new Date()
    const cutoffDate = new Date()
    switch (timeRange) {
      case '7d':
        cutoffDate.setDate(now.getDate() - 7)
        break
      case '14d':
        cutoffDate.setDate(now.getDate() - 14)
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
      case '1y':
        cutoffDate.setFullYear(now.getFullYear() - 1)
        break
      case 'all':
        cutoffDate.setTime(0)
        break
    }

    // Build a map of existing daily data
    const dailyMap = new Map<string, DailyPnL>()
    data.by_day.forEach((day) => {
      dailyMap.set(day.date, day)
    })

    // Get date range - from first trade (or cutoff) to today
    const sortedDates = data.by_day.map(d => d.date).sort()
    if (sortedDates.length === 0) return []

    const firstDataDate = new Date(sortedDates[0])
    const firstDate = new Date(Math.max(firstDataDate.getTime(), cutoffDate.getTime()))
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const lastDate = new Date(Math.max(new Date(sortedDates[sortedDates.length - 1]).getTime(), today.getTime()))

    // Fill in all dates from first to last
    const filledData: DailyPnL[] = []
    const currentDate = new Date(firstDate)
    let runningCumulativePnL = 0

    // Find cumulative PnL up to cutoff if not starting from beginning
    if (timeRange !== 'all') {
      for (const day of data.by_day) {
        if (new Date(day.date) < cutoffDate) {
          runningCumulativePnL = day.cumulative_pnl
        }
      }
    }

    while (currentDate <= lastDate) {
      const dateStr = currentDate.toISOString().split('T')[0]
      const existingData = dailyMap.get(dateStr)

      if (existingData && new Date(existingData.date) >= cutoffDate) {
        runningCumulativePnL = existingData.cumulative_pnl
        filledData.push(existingData)
      } else {
        // No trade on this day - show 0 daily PnL, maintain cumulative
        filledData.push({
          date: dateStr,
          daily_pnl: 0,
          cumulative_pnl: runningCumulativePnL
        })
      }
      currentDate.setDate(currentDate.getDate() + 1)
    }

    return filledData
  }

  // Calculate stats - always use summary data for stats cards (tab-independent)
  const calculateStats = () => {
    if (!data || data.summary.length === 0) {
      return {
        totalPnL: 0,
        closedTrades: 0,
        bestPair: null as PairPnL | null,
        worstPair: null as PairPnL | null,
        filteredByPair: [] as PairPnL[],
        filteredMostProfitableBot: null as MostProfitableBot | null
      }
    }

    // Calculate cutoff date based on time range
    const now = new Date()
    const cutoffDate = new Date()
    switch (timeRange) {
      case '7d':
        cutoffDate.setDate(now.getDate() - 7)
        break
      case '14d':
        cutoffDate.setDate(now.getDate() - 14)
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
        cutoffDate.setTime(0) // Include all
        break
    }

    // Always use summary data for stats (one entry per position, not per day/pair)
    // This ensures stats are consistent regardless of which tab is active
    const filteredSummary = data.summary.filter((item) => new Date(item.date) >= cutoffDate)

    // Sum up profits for positions within the selected time range (not cumulative_pnl which is all-time running total)
    const totalPnL = filteredSummary.reduce((sum, item) => sum + item.profit, 0)
    const closedTrades = filteredSummary.length

    // Calculate by_pair from filtered summary data (respects time range)
    const pairPnLMap = new Map<string, number>()
    filteredSummary.forEach((item) => {
      if (item.product_id) {
        const current = pairPnLMap.get(item.product_id) || 0
        pairPnLMap.set(item.product_id, current + item.profit)
      }
    })
    const filteredByPair: PairPnL[] = Array.from(pairPnLMap.entries())
      .map(([pair, total_pnl]) => ({ pair, total_pnl: Math.round(total_pnl * 100) / 100 }))
      .sort((a, b) => b.total_pnl - a.total_pnl)

    const bestPair = filteredByPair.length > 0 ? filteredByPair[0] : null
    const worstPair = filteredByPair.length > 0 ? filteredByPair[filteredByPair.length - 1] : null

    // Calculate most profitable bot from filtered summary (respects time range)
    const botPnLMap = new Map<number, { total_pnl: number; bot_name: string }>()
    filteredSummary.forEach((item) => {
      if (item.bot_id) {
        const current = botPnLMap.get(item.bot_id) || { total_pnl: 0, bot_name: item.bot_name || 'Unknown' }
        current.total_pnl += item.profit
        botPnLMap.set(item.bot_id, current)
      }
    })
    const sortedBots = Array.from(botPnLMap.entries())
      .map(([bot_id, { total_pnl, bot_name }]) => ({ bot_id, bot_name, total_pnl: Math.round(total_pnl * 100) / 100 }))
      .sort((a, b) => b.total_pnl - a.total_pnl)
    const filteredMostProfitableBot = sortedBots.length > 0 ? sortedBots[0] : null

    return { totalPnL, closedTrades, bestPair, worstPair, filteredByPair, filteredMostProfitableBot }
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
        fixLeftEdge: true,
        fixRightEdge: true,
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

    const filteredData = getFilteredData() as PnLDataPoint[]
    if (filteredData.length === 0) return

    // First, aggregate profits by day (multiple positions can close on same day)
    const dailyProfits = new Map<string, number>()
    filteredData.forEach((point) => {
      const current = dailyProfits.get(point.date) || 0
      dailyProfits.set(point.date, current + point.profit)
    })

    // Get date range - from first trade to today (or last trade if in the future somehow)
    const sortedDates = Array.from(dailyProfits.keys()).sort()
    if (sortedDates.length === 0) return

    const firstDate = new Date(sortedDates[0])
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const lastDate = new Date(Math.max(new Date(sortedDates[sortedDates.length - 1]).getTime(), today.getTime()))

    // Fill in all dates from first to last (including days with no trades)
    const allDates: string[] = []
    const currentDate = new Date(firstDate)
    while (currentDate <= lastDate) {
      allDates.push(currentDate.toISOString().split('T')[0])
      currentDate.setDate(currentDate.getDate() + 1)
    }

    // Build chart data with all dates, using 0 profit for missing days
    let cumulativePnL = 0
    const chartData = allDates.map((date) => {
      const dailyProfit = dailyProfits.get(date) || 0
      cumulativePnL += dailyProfit
      const timestamp = Math.floor(new Date(date).getTime() / 1000) as Time
      return { time: timestamp, value: Math.round(cumulativePnL * 100) / 100 }
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
            disabled={!enabledTimeRanges.has('7d')}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
              !enabledTimeRanges.has('7d')
                ? 'bg-slate-800 text-slate-600 cursor-not-allowed'
                : timeRange === '7d'
                  ? 'bg-emerald-500 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            7 days
          </button>
          <button
            onClick={() => setTimeRange('14d')}
            disabled={!enabledTimeRanges.has('14d')}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
              !enabledTimeRanges.has('14d')
                ? 'bg-slate-800 text-slate-600 cursor-not-allowed'
                : timeRange === '14d'
                  ? 'bg-emerald-500 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            14 days
          </button>
          <button
            onClick={() => setTimeRange('30d')}
            disabled={!enabledTimeRanges.has('30d')}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
              !enabledTimeRanges.has('30d')
                ? 'bg-slate-800 text-slate-600 cursor-not-allowed'
                : timeRange === '30d'
                  ? 'bg-emerald-500 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            30 days
          </button>
          <button
            onClick={() => setTimeRange('3m')}
            disabled={!enabledTimeRanges.has('3m')}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
              !enabledTimeRanges.has('3m')
                ? 'bg-slate-800 text-slate-600 cursor-not-allowed'
                : timeRange === '3m'
                  ? 'bg-emerald-500 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            3 months
          </button>
          <button
            onClick={() => setTimeRange('6m')}
            disabled={!enabledTimeRanges.has('6m')}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
              !enabledTimeRanges.has('6m')
                ? 'bg-slate-800 text-slate-600 cursor-not-allowed'
                : timeRange === '6m'
                  ? 'bg-emerald-500 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            6 months
          </button>
          <button
            onClick={() => setTimeRange('1y')}
            disabled={!enabledTimeRanges.has('1y')}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
              !enabledTimeRanges.has('1y')
                ? 'bg-slate-800 text-slate-600 cursor-not-allowed'
                : timeRange === '1y'
                  ? 'bg-emerald-500 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            1 year
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

          {/* Best Pairs Card (filtered by time range) */}
          <div className="bg-slate-800/50 rounded-lg p-4">
            <div className="text-sm text-slate-400 mb-3">Best pairs</div>
            <div className="space-y-2">
              {stats.filteredByPair.slice(0, 3).map((pair, index) => (
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

          {/* Most Profitable Bot Card (filtered by time range) */}
          <div className="bg-slate-800/50 rounded-lg p-4">
            <div className="text-sm text-slate-400 mb-1">Most profitable bot</div>
            {stats.filteredMostProfitableBot ? (
              <>
                <div className={`text-2xl font-bold mb-1 ${stats.filteredMostProfitableBot.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {stats.filteredMostProfitableBot.total_pnl >= 0 ? '+' : ''}${stats.filteredMostProfitableBot.total_pnl.toFixed(2)}
                </div>
                <div className="text-xs text-blue-400 truncate">{stats.filteredMostProfitableBot.bot_name}</div>
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
          <div className="flex-1 min-h-[300px]">
        {activeTab === 'by_day' ? (
          // Daily P&L bar chart - uses filled data to show all dates including days with no trades
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={getFilledByDayData()} margin={{ top: 5, right: 30, left: 20, bottom: 40 }}>
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
                {getFilledByDayData().map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={entry.daily_pnl >= 0 ? '#22c55e' : '#ef4444'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : activeTab === 'by_pair' ? (
          // Pair P&L bar chart (filtered by time range)
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={stats.filteredByPair} margin={{ top: 5, right: 30, left: 20, bottom: 80 }}>
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
                {stats.filteredByPair.map((entry, index) => (
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
