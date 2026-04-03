import { useState, useEffect, useRef } from 'react'
import { ResponsiveContainer, AreaChart, Area, YAxis } from 'recharts'

interface SparklineProps {
  data: number[]
  color: string
  height?: number
  timeLabel?: string
}

export function Sparkline({ data, color, height = 54, timeLabel }: SparklineProps) {
  // Defer chart render by two frames after data first becomes available.
  // The previous approach deferred on mount, but data often arrives later (React Query),
  // at which point some carousel cards are off-screen and measure as 0/-1 dimensions.
  // We defer from when data first arrives instead, and only once (subsequent updates render immediately).
  const [ready, setReady] = useState(false)
  const triggered = useRef(false)
  const hasData = data != null && data.length >= 2

  useEffect(() => {
    if (!hasData || triggered.current) return
    triggered.current = true
    let cancelled = false
    requestAnimationFrame(() => {
      requestAnimationFrame(() => { if (!cancelled) setReady(true) })
    })
    return () => { cancelled = true }
  }, [hasData])

  if (!hasData) return null

  const chartData = data.map((value, i) => ({ v: value, i }))

  return (
    <div className="w-full">
      <div className="w-full opacity-60 hover:opacity-100 transition-opacity" style={{ height }}>
        {ready && (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
              <defs>
                <linearGradient id={`spark-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={color} stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <YAxis domain={['dataMin', 'dataMax']} hide />
              <Area
                type="monotone"
                dataKey="v"
                stroke={color}
                strokeWidth={1.5}
                fill={`url(#spark-${color.replace('#', '')})`}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
      {timeLabel && <div className="text-[10px] text-slate-600 text-center mt-0.5">{timeLabel}</div>}
    </div>
  )
}
