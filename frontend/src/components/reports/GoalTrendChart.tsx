import { useState, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer, ComposedChart, Area, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, ReferenceArea,
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

/** Compute the chart's visible end date based on horizon setting. */
function computeHorizonDate(
  points: GoalTrendPoint[],
  targetDate: string,
  horizon: string,
): string {
  if (!points.length) return targetDate

  const realDates = points
    .filter(p => p.current_value != null)
    .map(p => new Date(p.date + 'T00:00:00').getTime())

  if (!realDates.length) return targetDate

  const firstDataTs = Math.min(...realDates)
  const lastDataTs = Math.max(...realDates)
  const targetTs = new Date(targetDate + 'T00:00:00').getTime()
  const DAY_MS = 86400000

  if (horizon === 'full') return targetDate

  if (horizon === 'elapsed') {
    // Look-ahead = fraction of elapsed days (default 0.33 for frontend fallback)
    const elapsedDays = Math.max(Math.round((lastDataTs - firstDataTs) / DAY_MS), 1)
    const lookAhead = Math.max(Math.round(elapsedDays * 0.33), 1)
    const h = lastDataTs + lookAhead * DAY_MS
    return new Date(Math.min(h, targetTs)).toISOString().split('T')[0]
  }

  if (horizon !== 'auto') {
    const days = parseInt(horizon)
    if (!isNaN(days)) {
      const h = lastDataTs + days * DAY_MS
      return new Date(Math.min(h, targetTs)).toISOString().split('T')[0]
    }
  }

  // Auto: 30-day look-ahead from last data point (no schedule context)
  const h = lastDataTs + 30 * DAY_MS
  return new Date(Math.min(h, targetTs)).toISOString().split('T')[0]
}

/** Clip data points to horizon date with a synthetic ideal endpoint at the horizon. */
function clipPoints(
  points: GoalTrendPoint[],
  horizonDate: string,
  goalStartDate: string,
  goalTargetDate: string,
  idealStart: number,
  idealEnd: number,
): GoalTrendPoint[] {
  const horizonTs = new Date(horizonDate + 'T00:00:00').getTime()
  const clipped: GoalTrendPoint[] = []

  for (const p of points) {
    const pTs = new Date(p.date + 'T00:00:00').getTime()
    if (pTs <= horizonTs) {
      clipped.push(p)
    }
  }

  if (!clipped.length) return clipped

  // If last point is already ideal-only at the horizon, no need for synthetic endpoint
  const last = clipped[clipped.length - 1]
  if (last.current_value == null) return clipped

  // Interpolate ideal value at the horizon date
  const startTs = new Date(goalStartDate + 'T00:00:00').getTime()
  const targetTs = new Date(goalTargetDate + 'T00:00:00').getTime()
  const totalDays = targetTs - startTs
  let idealAtHorizon = idealEnd
  if (totalDays > 0) {
    const elapsed = horizonTs - startTs
    const progress = Math.min(Math.max(elapsed / totalDays, 0), 1)
    idealAtHorizon = idealStart + (idealEnd - idealStart) * progress
  }

  clipped.push({
    date: horizonDate,
    current_value: null as unknown as number,
    ideal_value: idealAtHorizon,
    progress_pct: null as unknown as number,
    on_track: null as unknown as boolean,
  })

  return clipped
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
        {point.current_value != null && (
          <div className="flex items-center gap-2">
            <div className="w-3 h-0.5 bg-blue-400" />
            <span className="text-sm text-slate-300">Actual: </span>
            <span className={`text-sm font-semibold ${point.on_track ? 'text-emerald-400' : 'text-amber-400'}`}>
              {format(point.current_value)}
            </span>
          </div>
        )}
        <div className="flex items-center gap-2">
          <div className="w-3 h-0.5 bg-slate-500" />
          <span className="text-sm text-slate-300">Ideal: </span>
          <span className="text-sm text-slate-400">{format(point.ideal_value)}</span>
        </div>
        {point.progress_pct != null && (
          <div className="text-xs text-slate-500 mt-1">
            Progress: {point.progress_pct.toFixed(1)}%
            {point.on_track ? ' — On track' : ' — Behind target'}
          </div>
        )}
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

  // Compute horizon and clipped points
  const { clippedPoints, fullPoints, horizonDate, showMinimap } = useMemo(() => {
    if (!data || data.data_points.length < 2) {
      return { clippedPoints: [], fullPoints: [], horizonDate: '', showMinimap: false }
    }

    const settings = data.chart_settings
    const horizon = settings?.chart_horizon || 'auto'
    const targetDate = data.goal.target_date
    const allPoints = data.data_points

    const hDate = computeHorizonDate(allPoints, targetDate, horizon)
    const clipped = clipPoints(
      allPoints, hDate,
      data.goal.start_date, targetDate,
      data.ideal_start_value, data.ideal_end_value,
    )

    // Minimap: show when chart doesn't reach target date
    const showMm = hDate < targetDate

    return {
      clippedPoints: clipped,
      fullPoints: allPoints,
      horizonDate: hDate,
      showMinimap: showMm,
    }
  }, [data])

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

  // Use the last real data point (skip projected endpoint where on_track is null)
  const realPoints = clippedPoints.filter(p => p.on_track != null)
  const lastPoint = realPoints.length > 0 ? realPoints[realPoints.length - 1] : clippedPoints[0]
  const isOnTrack = lastPoint?.on_track

  // Minimap viewport boundaries (date strings)
  const minimapFirstDate = fullPoints.length > 0 ? fullPoints[0].date : ''

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

      {/* Main chart — clipped to horizon */}
      <div className="h-[280px] sm:h-[320px]">
        {mounted && (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={clippedPoints} margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
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
              {/* Ideal trend line (dashed, no fill) — connectNulls so it extends to target */}
              <Line
                type="linear"
                dataKey="ideal_value"
                name="Ideal Path"
                stroke="#64748b"
                strokeWidth={1.5}
                strokeDasharray="6 3"
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Minimap — full timeline with viewport indicator */}
      {showMinimap && mounted && fullPoints.length >= 2 && (
        <div className="mt-2">
          <div className="text-[10px] text-slate-500 mb-1">Full Timeline</div>
          <div className="h-[50px]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={fullPoints} margin={{ top: 2, right: 5, left: 5, bottom: 2 }}>
                {/* Viewport highlight */}
                <ReferenceArea
                  x1={minimapFirstDate}
                  x2={horizonDate}
                  fill="#3b82f6"
                  fillOpacity={0.08}
                  stroke="#3b82f6"
                  strokeOpacity={0.3}
                />
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#475569', fontSize: 8 }}
                  tickFormatter={formatDate}
                  interval="preserveStartEnd"
                  axisLine={{ stroke: '#334155' }}
                  tickLine={false}
                />
                <YAxis hide />
                {/* Full ideal line */}
                <Line
                  type="linear"
                  dataKey="ideal_value"
                  stroke="#64748b"
                  strokeWidth={1}
                  strokeDasharray="4 3"
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
                {/* Full actual line */}
                <Area
                  type="monotone"
                  dataKey="current_value"
                  stroke="#10b981"
                  strokeWidth={1.5}
                  fill="transparent"
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  )
}
