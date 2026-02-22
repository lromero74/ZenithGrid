import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer, ComposedChart, Area, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend,
} from 'recharts'
import { TrendingUp, X } from 'lucide-react'
import { reportsApi } from '../../services/api'
import type { GoalTrendData, GoalTrendPoint } from '../../types'

interface GoalTrendChartProps {
  goalId: number
  goalName: string
  targetCurrency: 'USD' | 'BTC'
  onClose: () => void
}

function CustomTooltip({ active, payload, label, targetCurrency }: {
  active?: boolean
  payload?: Array<{ payload: GoalTrendPoint }>
  label?: string
  targetCurrency: string
}) {
  if (!active || !payload || !payload.length) return null

  const point = payload[0]?.payload as GoalTrendPoint
  if (!point) return null

  const isBtc = targetCurrency === 'BTC'
  const format = (v: number) =>
    isBtc
      ? `${v.toFixed(8)} BTC`
      : `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

  return (
    <div className="bg-slate-800 border border-slate-600 rounded-lg p-3 shadow-lg">
      <div className="text-slate-300 text-sm mb-2">
        {new Date(label + 'T00:00:00').toLocaleDateString('en-US', {
          month: 'short', day: 'numeric', year: 'numeric'
        })}
      </div>
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <div className="w-3 h-0.5 bg-blue-400" />
          <span className="text-sm text-slate-300">Actual: </span>
          <span className={`text-sm font-semibold ${point.on_track ? 'text-emerald-400' : 'text-amber-400'}`}>
            {format(point.current_value)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-0.5 bg-slate-500" />
          <span className="text-sm text-slate-300">Ideal: </span>
          <span className="text-sm text-slate-400">{format(point.ideal_value)}</span>
        </div>
        <div className="text-xs text-slate-500 mt-1">
          Progress: {point.progress_pct.toFixed(1)}%
          {point.on_track ? ' — On track' : ' — Behind target'}
        </div>
      </div>
    </div>
  )
}

export function GoalTrendChart({ goalId, goalName, targetCurrency, onClose }: GoalTrendChartProps) {
  // Defer chart mount for ResponsiveContainer sizing
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true))
    return () => cancelAnimationFrame(id)
  }, [])

  const { data, isLoading, error } = useQuery<GoalTrendData>({
    queryKey: ['goal-trend', goalId],
    queryFn: () => reportsApi.getGoalTrend(goalId),
  })

  const isBtc = targetCurrency === 'BTC'

  const formatValue = (value: number) => {
    if (isBtc) return value.toFixed(4)
    if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
    if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`
    return `$${value.toFixed(0)}`
  }

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  if (isLoading) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h4 className="text-white font-medium">{goalName} — Trend</h4>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="text-center py-12 text-slate-400">Loading trend data...</div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h4 className="text-white font-medium">{goalName} — Trend</h4>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="text-center py-12 text-slate-400">
          <TrendingUp className="w-8 h-8 mx-auto mb-2 text-slate-600" />
          <p>No trend data available yet.</p>
          <p className="text-xs mt-1">Data will appear after daily snapshots are captured.</p>
        </div>
      </div>
    )
  }

  const points = data.data_points
  if (points.length < 2) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h4 className="text-white font-medium">{goalName} — Trend</h4>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="text-center py-12 text-slate-400">
          <TrendingUp className="w-8 h-8 mx-auto mb-2 text-slate-600" />
          <p>Need at least 2 data points to show a trend.</p>
          <p className="text-xs mt-1">Check back after a few days of snapshots.</p>
        </div>
      </div>
    )
  }

  const lastPoint = points[points.length - 1]
  const isOnTrack = lastPoint.on_track

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 sm:p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h4 className="text-white font-medium flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-blue-400" />
            {goalName} — Progress Trend
          </h4>
          <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
            <span>
              Target: {isBtc ? `${data.goal.target_value} BTC` : `$${data.goal.target_value.toLocaleString()}`}
            </span>
            <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded ${
              isOnTrack
                ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-800/50'
                : 'bg-amber-900/40 text-amber-400 border border-amber-800/50'
            }`}>
              {isOnTrack ? 'On Track' : 'Behind Target'}
            </span>
          </div>
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="h-[280px] sm:h-[320px]">
        {mounted && (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={points} margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
              <defs>
                <linearGradient id={`goalActual-${goalId}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.15} />
                  <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis
                dataKey="date"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                tickFormatter={formatDate}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                tickFormatter={formatValue}
                width={65}
              />
              <Tooltip content={<CustomTooltip targetCurrency={targetCurrency} />} />
              <Legend
                wrapperStyle={{ paddingTop: '8px' }}
                iconType="line"
                formatter={(value: string) => (
                  <span style={{ color: '#94a3b8', fontSize: '12px' }}>{value}</span>
                )}
              />
              {/* Actual progress area (filled) */}
              <Area
                type="monotone"
                dataKey="current_value"
                name="Actual"
                stroke="#3b82f6"
                strokeWidth={2}
                fill={`url(#goalActual-${goalId})`}
                isAnimationActive={false}
              />
              {/* Ideal trend line (dashed, no fill) */}
              <Line
                type="linear"
                dataKey="ideal_value"
                name="Ideal Path"
                stroke="#64748b"
                strokeWidth={1.5}
                strokeDasharray="6 3"
                dot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
