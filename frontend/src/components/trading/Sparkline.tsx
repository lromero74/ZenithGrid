import { useState, useEffect, useRef } from 'react'
import { AreaChart, Area, YAxis } from 'recharts'

interface SparklineProps {
  data: number[]
  color: string
  height?: number
  timeLabel?: string
}

export function Sparkline({ data, color, height = 54, timeLabel }: SparklineProps) {
  // Measure the container's pixel width ourselves before rendering Recharts.
  // ResponsiveContainer initializes its internal state to -1 and only updates after
  // its own ResizeObserver fires, causing the "width(-1)/height(-1)" warning on every
  // first render. By measuring the wrapper div directly and passing explicit pixel
  // dimensions to AreaChart, we skip ResponsiveContainer entirely and eliminate the warning.
  const containerRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  const hasData = data != null && data.length >= 2

  useEffect(() => {
    if (!hasData) return
    const el = containerRef.current
    if (!el) return
    const measure = () => {
      const w = el.clientWidth
      if (w > 0) setWidth(w)
    }
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    measure()
    return () => ro.disconnect()
  }, [hasData])

  if (!hasData) return null

  const chartData = data.map((value, i) => ({ v: value, i }))

  return (
    <div className="w-full">
      <div ref={containerRef} className="w-full opacity-60 hover:opacity-100 transition-opacity" style={{ height }}>
        {width > 0 && (
          <AreaChart width={width} height={height} data={chartData} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
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
        )}
      </div>
      {timeLabel && <div className="text-[10px] text-slate-600 text-center mt-0.5">{timeLabel}</div>}
    </div>
  )
}
