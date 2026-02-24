import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { createChart, ColorType, IChartApi, Time, LineData, SeriesMarker } from 'lightweight-charts'
import { TrendingUp, DollarSign } from 'lucide-react'
import { LoadingSpinner } from './LoadingSpinner'
import { useAccount } from '../contexts/AccountContext'
import { accountValueApi, type ActivityItem } from '../services/api'

interface AccountValueSnapshot {
  date: string
  timestamp: string
  total_value_btc: number
  total_value_usd: number
  usd_portion_usd?: number | null
  btc_portion_btc?: number | null
}

type ChartMode = 'total' | 'split'

export type TimeRange = '7d' | '14d' | '30d' | '3m' | '6m' | '1y' | 'all'

type MarkerCategory = ActivityItem['category']

interface AccountValueChartProps {
  className?: string
}

// Marker config per activity category
const MARKER_CONFIG: Record<MarkerCategory, {
  shape: 'arrowUp' | 'arrowDown'
  position: 'belowBar' | 'aboveBar'
  color: string
  label: string
  symbol: string
  textClass: string
}> = {
  trade_win:  { shape: 'arrowUp',   position: 'belowBar', color: '#10b981', label: 'Wins',
                symbol: '\u25B2', textClass: 'text-emerald-400' },
  trade_loss: { shape: 'arrowDown', position: 'aboveBar', color: '#ef4444', label: 'Losses',
                symbol: '\u25BC', textClass: 'text-red-400' },
  deposit:    { shape: 'arrowUp',   position: 'belowBar', color: '#3b82f6', label: 'Deposits',
                symbol: '\u25B2', textClass: 'text-blue-400' },
  withdrawal: { shape: 'arrowDown', position: 'aboveBar', color: '#f59e0b', label: 'Withdrawals',
                symbol: '\u25BC', textClass: 'text-amber-400' },
}

const ALL_CATEGORIES: MarkerCategory[] = ['trade_win', 'trade_loss', 'deposit', 'withdrawal']

function formatMarkerText(item: ActivityItem): string {
  const cfg = MARKER_CONFIG[item.category]
  const isBtc = item.line === 'btc'

  if (item.category === 'trade_win' || item.category === 'trade_loss') {
    const sign = item.amount >= 0 ? '+' : ''
    const amt = isBtc ? `${sign}${item.amount.toFixed(8)} BTC` : `${sign}$${Math.abs(item.amount).toLocaleString()}`
    const singular = item.category === 'trade_win' ? 'Win' : 'Loss'
    const plural = item.count > 1 ? `${item.count} ${singular}${item.count > 1 ? (singular === 'Loss' ? 'es' : 's') : ''}` : singular
    return `${plural}: ${amt}`
  }
  // Deposits/withdrawals
  const amt = isBtc ? `${item.amount.toFixed(8)} BTC` : `$${Math.abs(item.amount).toLocaleString()}`
  const singular = cfg.label.replace(/s$/, '')
  const plural = item.count > 1 ? `${item.count} ${cfg.label}` : singular
  return `${plural}: ${amt}`
}

export function AccountValueChart({ className = '' }: AccountValueChartProps) {
  const [timeRange, setTimeRange] = useState<TimeRange>('all')
  const [chartMode, setChartMode] = useState<ChartMode>('total')
  const [showAllAccounts, setShowAllAccounts] = useState(false)
  const [visibleMarkers, setVisibleMarkers] = useState<Set<MarkerCategory>>(
    () => new Set(ALL_CATEGORIES)
  )
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const btcSeriesRef = useRef<any>(null)
  const usdSeriesRef = useRef<any>(null)
  const { selectedAccount } = useAccount()

  // Determine if we should include paper trading accounts
  const includePaperTrading = selectedAccount?.is_paper_trading || false

  // Determine which account(s) to show
  const accountId = showAllAccounts ? undefined : selectedAccount?.id

  // Map time ranges to days
  const getDaysForTimeRange = (range: TimeRange): number => {
    switch (range) {
      case '7d': return 7
      case '14d': return 14
      case '30d': return 30
      case '3m': return 90
      case '6m': return 180
      case '1y': return 365
      case 'all': return 1825 // 5 years max
      default: return 30
    }
  }

  // Fetch account value history
  const { data: history, isLoading } = useQuery<AccountValueSnapshot[]>({
    queryKey: ['account-value-history', timeRange, includePaperTrading, accountId],
    queryFn: async () => {
      const days = getDaysForTimeRange(timeRange)
      return accountValueApi.getHistory(days, includePaperTrading, accountId)
    },
    refetchInterval: 300000, // Refresh every 5 minutes
  })

  // Fetch activity data for chart markers
  const { data: activity } = useQuery<ActivityItem[]>({
    queryKey: ['account-value-activity', timeRange, includePaperTrading, accountId],
    queryFn: async () => {
      const days = getDaysForTimeRange(timeRange)
      return accountValueApi.getActivity(days, includePaperTrading, accountId)
    },
    refetchInterval: 300000,
  })

  const toggleCategory = useCallback((cat: MarkerCategory) => {
    setVisibleMarkers(prev => {
      const next = new Set(prev)
      if (next.has(cat)) {
        next.delete(cat)
      } else {
        next.add(cat)
      }
      return next
    })
  }, [])

  // Apply markers whenever activity data or visibility toggles change
  useEffect(() => {
    const btcSeries = btcSeriesRef.current
    const usdSeries = usdSeriesRef.current
    if (!btcSeries || !usdSeries) return

    if (!activity || activity.length === 0) {
      btcSeries.setMarkers([])
      usdSeries.setMarkers([])
      return
    }

    const btcMarkers: SeriesMarker<Time>[] = []
    const usdMarkers: SeriesMarker<Time>[] = []

    for (const item of activity) {
      if (!visibleMarkers.has(item.category)) continue
      const cfg = MARKER_CONFIG[item.category]
      const marker: SeriesMarker<Time> = {
        time: item.date as Time,
        position: cfg.position,
        color: cfg.color,
        shape: cfg.shape,
        text: formatMarkerText(item),
      }
      if (item.line === 'btc') {
        btcMarkers.push(marker)
      } else {
        usdMarkers.push(marker)
      }
    }

    // Markers must be sorted by time
    btcMarkers.sort((a, b) => (a.time as string).localeCompare(b.time as string))
    usdMarkers.sort((a, b) => (a.time as string).localeCompare(b.time as string))

    btcSeries.setMarkers(btcMarkers)
    usdSeries.setMarkers(usdMarkers)
  }, [activity, visibleMarkers])

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current || !history || history.length === 0) return

    // Clear existing chart
    if (chartRef.current) {
      chartRef.current.remove()
      chartRef.current = null
    }

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
        visible: true,
        borderColor: '#334155',
        scaleMargins: {
          top: 0.1,
          bottom: 0.1,
        },
      },
      leftPriceScale: {
        visible: true,
        borderColor: '#334155',
        mode: 0, // Normal price scale mode
        scaleMargins: {
          top: 0.1,
          bottom: 0.1,
        },
      },
      timeScale: {
        borderColor: '#334155',
        timeVisible: true,
        secondsVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
    })

    chartRef.current = chart

    const isSplit = chartMode === 'split'
    const btcLabel = isSplit ? 'BTC Portion' : 'BTC'
    const usdLabel = isSplit ? 'USD Portion' : 'USD'

    // Add BTC line series (left scale - orange)
    const btcSeries = chart.addLineSeries({
      color: '#ff8800',
      lineWidth: 2,
      lineType: 2, // 2 = curved/smooth line
      priceScaleId: 'left',
      title: btcLabel,
      priceFormat: {
        type: 'custom',
        minMove: 0.00000001,
        formatter: (price: number) => price.toFixed(8),
      },
      lastValueVisible: false,
      priceLineVisible: false,
    })
    btcSeriesRef.current = btcSeries

    // Add USD line series (right scale - green)
    const usdSeries = chart.addLineSeries({
      color: '#4ade80',
      lineWidth: 2,
      lineType: 2, // 2 = curved/smooth line
      priceScaleId: 'right',
      title: usdLabel,
      lastValueVisible: false,
      priceLineVisible: false,
    })
    usdSeriesRef.current = usdSeries

    // Filter data based on chart mode
    const chartData = isSplit
      ? history.filter(s => s.usd_portion_usd != null && s.btc_portion_btc != null)
      : history

    // Prepare data
    const btcData: LineData<Time>[] = chartData.map(snapshot => ({
      time: snapshot.date as Time,
      value: isSplit ? (snapshot.btc_portion_btc ?? 0) : snapshot.total_value_btc,
    }))

    const usdData: LineData<Time>[] = chartData.map(snapshot => ({
      time: snapshot.date as Time,
      value: isSplit ? (snapshot.usd_portion_usd ?? 0) : snapshot.total_value_usd,
    }))

    btcSeries.setData(btcData)
    usdSeries.setData(usdData)

    // Fit content
    chart.timeScale().fitContent()

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        })
      }
    }

    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      if (chartRef.current) {
        chartRef.current.remove()
        chartRef.current = null
      }
    }
  }, [history, chartMode])

  // Calculate which time range buttons should be enabled based on data span
  const getEnabledTimeRanges = (): Set<TimeRange> => {
    const enabled = new Set<TimeRange>(['all'])

    if (!history || history.length === 0) {
      return enabled
    }

    // Find the earliest date in the data
    const dates = history.map(d => new Date(d.date).getTime())
    const earliestDate = new Date(Math.min(...dates))
    const now = new Date()
    const dataSpanDays = Math.ceil((now.getTime() - earliestDate.getTime()) / (1000 * 60 * 60 * 24))

    // Time range thresholds in days
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
    for (const { range, days } of thresholds) {
      if (days <= firstCoveringDays) {
        enabled.add(range)
      }
    }

    return enabled
  }

  const enabledTimeRanges = getEnabledTimeRanges()

  // Check if any snapshot has portion data (for enabling the split toggle)
  const hasPortionData = history?.some(s => s.usd_portion_usd != null) ?? false

  // Calculate stats based on chart mode
  const isSplit = chartMode === 'split'
  const relevantHistory = isSplit
    ? history?.filter(s => s.usd_portion_usd != null && s.btc_portion_btc != null)
    : history
  const latestValue = relevantHistory && relevantHistory.length > 0 ? relevantHistory[relevantHistory.length - 1] : null
  const earliestValue = relevantHistory && relevantHistory.length > 0 ? relevantHistory[0] : null

  const latestBtc = isSplit ? (latestValue?.btc_portion_btc ?? 0) : (latestValue?.total_value_btc ?? 0)
  const earliestBtc = isSplit ? (earliestValue?.btc_portion_btc ?? 0) : (earliestValue?.total_value_btc ?? 0)
  const latestUsd = isSplit ? (latestValue?.usd_portion_usd ?? 0) : (latestValue?.total_value_usd ?? 0)
  const earliestUsd = isSplit ? (earliestValue?.usd_portion_usd ?? 0) : (earliestValue?.total_value_usd ?? 0)

  const btcChange = earliestBtc ? ((latestBtc - earliestBtc) / earliestBtc) * 100 : 0
  const usdChange = earliestUsd ? ((latestUsd - earliestUsd) / earliestUsd) * 100 : 0

  if (isLoading) {
    return (
      <div className={`bg-slate-800 rounded-lg border border-slate-700 p-6 ${className}`}>
        <div className="flex items-center justify-center h-96">
          <LoadingSpinner />
        </div>
      </div>
    )
  }

  if (!history || history.length === 0) {
    return (
      <div className={`bg-slate-800 rounded-lg border border-slate-700 p-6 ${className}`}>
        <div className="flex items-center space-x-2 mb-4">
          <TrendingUp className="w-5 h-5 text-blue-400" />
          <h2 className="text-xl font-semibold text-white">Account Value Over Time</h2>
        </div>
        <div className="flex items-center justify-center h-96 text-slate-400">
          <div className="text-center">
            <DollarSign className="w-16 h-16 mx-auto mb-4 opacity-50" />
            <p>No historical data available yet</p>
            <p className="text-sm mt-2">Account values are captured daily</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={`bg-slate-800 rounded-lg border border-slate-700 p-6 ${className}`}>
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 mb-4">
        <div className="flex items-center space-x-2">
          <TrendingUp className="w-5 h-5 text-blue-400" />
          <h2 className="text-lg sm:text-xl font-semibold text-white">Account Value Over Time</h2>
        </div>

        {/* Time range selector */}
        <div className="flex flex-wrap gap-1.5">
          {(['7d', '14d', '30d', '3m', '6m', '1y', 'all'] as TimeRange[]).map((range) => (
            <button
              key={range}
              onClick={() => setTimeRange(range)}
              disabled={!enabledTimeRanges.has(range)}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                timeRange === range
                  ? 'bg-blue-600 text-white'
                  : enabledTimeRanges.has(range)
                  ? 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  : 'bg-slate-800 text-slate-600 cursor-not-allowed'
              }`}
            >
              {range === 'all' ? 'All' : range.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Account Filter + Chart Mode Toggles */}
      <div className="flex items-center justify-end gap-2 mb-4">
        <button
          onClick={() => setChartMode(m => m === 'total' ? 'split' : 'total')}
          disabled={!hasPortionData && chartMode === 'total'}
          title={!hasPortionData ? 'Portion data will appear after the next daily snapshot' : undefined}
          className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
            chartMode === 'split'
              ? 'bg-blue-600 text-white hover:bg-blue-700'
              : hasPortionData
              ? 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              : 'bg-slate-800 text-slate-500 cursor-not-allowed'
          }`}
        >
          {chartMode === 'total' ? 'Total Value' : 'By Quote Currency'}
        </button>
        <button
          onClick={() => setShowAllAccounts(!showAllAccounts)}
          className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
            showAllAccounts
              ? 'bg-purple-600 text-white hover:bg-purple-700'
              : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
          }`}
        >
          {showAllAccounts ? 'Showing: All Accounts' : `Showing: ${selectedAccount?.name || 'Current Account'}`}
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-slate-400 mb-1">
                {isSplit ? 'BTC Portion (BTC)' : 'Current Value (BTC)'}
              </p>
              <p className="text-2xl font-bold text-orange-400">
                {latestBtc.toFixed(8)}
              </p>
              <p className={`text-sm ${btcChange >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {btcChange >= 0 ? '+' : ''}{btcChange.toFixed(2)}% ({timeRange})
              </p>
            </div>
            <DollarSign className="w-8 h-8 text-orange-400 opacity-50" />
          </div>
        </div>

        <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-slate-400 mb-1">
                {isSplit ? 'USD Portion (USD)' : 'Current Value (USD)'}
              </p>
              <p className="text-2xl font-bold text-green-400">
                ${latestUsd.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </p>
              <p className={`text-sm ${usdChange >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {usdChange >= 0 ? '+' : ''}{usdChange.toFixed(2)}% ({timeRange})
              </p>
            </div>
            <DollarSign className="w-8 h-8 text-green-400 opacity-50" />
          </div>
        </div>
      </div>

      {/* Chart Legend — line indicators (static) + marker toggles (clickable) */}
      <div className="flex items-center justify-center gap-3 flex-wrap mb-2 text-xs">
        <div className="flex items-center space-x-1.5">
          <div className="w-4 h-0.5 bg-orange-400"></div>
          <span className="text-slate-300">{isSplit ? 'BTC Portion (Left)' : 'BTC (Left)'}</span>
        </div>
        <div className="flex items-center space-x-1.5">
          <div className="w-4 h-0.5 bg-green-400"></div>
          <span className="text-slate-300">{isSplit ? 'USD Portion (Right)' : 'USD (Right)'}</span>
        </div>
        <span className="text-slate-600">|</span>
        {ALL_CATEGORIES.map((cat) => {
          const cfg = MARKER_CONFIG[cat]
          const active = visibleMarkers.has(cat)
          return (
            <button
              key={cat}
              onClick={() => toggleCategory(cat)}
              className={`flex items-center space-x-1 px-1.5 py-0.5 rounded transition-colors ${
                active
                  ? 'bg-slate-700/50 hover:bg-slate-600/50'
                  : 'bg-slate-900/50 opacity-40 hover:opacity-60'
              }`}
              title={`${active ? 'Hide' : 'Show'} ${cfg.label.toLowerCase()}`}
            >
              <span className={cfg.textClass}>{cfg.symbol}</span>
              <span className={active ? 'text-slate-300' : 'text-slate-500 line-through'}>
                {cfg.label}
              </span>
            </button>
          )
        })}
      </div>

      {/* Chart */}
      <div ref={chartContainerRef} className="w-full" />

      {/* Note */}
      <p className="text-xs text-slate-500 mt-4 text-center">
        Account values are captured daily and aggregated across all your active accounts
      </p>
    </div>
  )
}
