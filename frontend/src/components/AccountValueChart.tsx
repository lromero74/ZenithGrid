import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { createChart, ColorType, IChartApi, Time, LineData } from 'lightweight-charts'
import { TrendingUp, DollarSign } from 'lucide-react'
import { LoadingSpinner } from './LoadingSpinner'
import { useAccount } from '../contexts/AccountContext'
import { accountValueApi } from '../services/api'

interface AccountValueSnapshot {
  date: string
  timestamp: string
  total_value_btc: number
  total_value_usd: number
}

export type TimeRange = '7d' | '14d' | '30d' | '3m' | '6m' | '1y' | 'all'

interface AccountValueChartProps {
  className?: string
}

export function AccountValueChart({ className = '' }: AccountValueChartProps) {
  const [timeRange, setTimeRange] = useState<TimeRange>('30d')
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const btcSeriesRef = useRef<any>(null)
  const usdSeriesRef = useRef<any>(null)
  const { selectedAccount } = useAccount()

  // Determine if we should include paper trading accounts
  const includePaperTrading = selectedAccount?.is_paper_trading || false

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
    queryKey: ['account-value-history', timeRange, includePaperTrading],
    queryFn: async () => {
      const days = getDaysForTimeRange(timeRange)
      return accountValueApi.getHistory(days, includePaperTrading)
    },
    refetchInterval: 300000, // Refresh every 5 minutes
  })

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
      },
      leftPriceScale: {
        visible: true,
        borderColor: '#334155',
      },
      timeScale: {
        borderColor: '#334155',
        timeVisible: true,
        secondsVisible: false,
      },
    })

    chartRef.current = chart

    // Add BTC line series (left scale - orange)
    const btcSeries = chart.addLineSeries({
      color: '#fb923c',
      lineWidth: 2,
      priceScaleId: 'left',
      title: 'BTC',
    })
    btcSeriesRef.current = btcSeries

    // Add USD line series (right scale - green)
    const usdSeries = chart.addLineSeries({
      color: '#4ade80',
      lineWidth: 2,
      priceScaleId: 'right',
      title: 'USD',
    })
    usdSeriesRef.current = usdSeries

    // Prepare data
    const btcData: LineData<Time>[] = history.map(snapshot => ({
      time: snapshot.date as Time,
      value: snapshot.total_value_btc,
    }))

    const usdData: LineData<Time>[] = history.map(snapshot => ({
      time: snapshot.date as Time,
      value: snapshot.total_value_usd,
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
  }, [history])

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

  // Calculate stats
  const latestValue = history && history.length > 0 ? history[history.length - 1] : null
  const earliestValue = history && history.length > 0 ? history[0] : null
  const btcChange = latestValue && earliestValue
    ? ((latestValue.total_value_btc - earliestValue.total_value_btc) / earliestValue.total_value_btc) * 100
    : 0
  const usdChange = latestValue && earliestValue
    ? ((latestValue.total_value_usd - earliestValue.total_value_usd) / earliestValue.total_value_usd) * 100
    : 0

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
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <TrendingUp className="w-5 h-5 text-blue-400" />
          <h2 className="text-xl font-semibold text-white">Account Value Over Time</h2>
        </div>

        {/* Time range selector */}
        <div className="flex space-x-2">
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

      {/* Stats Cards */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-slate-400 mb-1">Current Value (BTC)</p>
              <p className="text-2xl font-bold text-orange-400">
                {latestValue?.total_value_btc.toFixed(8) || '0.00000000'}
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
              <p className="text-xs text-slate-400 mb-1">Current Value (USD)</p>
              <p className="text-2xl font-bold text-green-400">
                ${latestValue?.total_value_usd.toLocaleString(undefined, { maximumFractionDigits: 2 }) || '0.00'}
              </p>
              <p className={`text-sm ${usdChange >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {usdChange >= 0 ? '+' : ''}{usdChange.toFixed(2)}% ({timeRange})
              </p>
            </div>
            <DollarSign className="w-8 h-8 text-green-400 opacity-50" />
          </div>
        </div>
      </div>

      {/* Chart Legend */}
      <div className="flex items-center justify-center space-x-6 mb-2 text-sm">
        <div className="flex items-center space-x-2">
          <div className="w-4 h-0.5 bg-orange-400"></div>
          <span className="text-slate-300">BTC Value (Left Axis)</span>
        </div>
        <div className="flex items-center space-x-2">
          <div className="w-4 h-0.5 bg-green-400"></div>
          <span className="text-slate-300">USD Value (Right Axis)</span>
        </div>
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
