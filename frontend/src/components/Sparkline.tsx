import { useRef, useState, useEffect } from 'react'
import { ResponsiveContainer, AreaChart, Area, YAxis } from 'recharts'

interface SparklineProps {
  data: number[]
  color: string
  height?: number
  timeLabel?: string
}

export function Sparkline({ data, color, height = 40, timeLabel }: SparklineProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [hasSize, setHasSize] = useState(false)

  // Defer chart render until container has real dimensions
  useEffect(() => {
    if (!containerRef.current) return
    const observer = new ResizeObserver((entries) => {
      const { width, height: h } = entries[0].contentRect
      if (width > 0 && h > 0) setHasSize(true)
    })
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  if (!data || data.length < 2) return null

  const chartData = data.map((value, i) => ({ v: value, i }))

  return (
    <div className="w-full">
      <div ref={containerRef} className="w-full opacity-60 hover:opacity-100 transition-opacity" style={{ height }}>
        {hasSize && (
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
