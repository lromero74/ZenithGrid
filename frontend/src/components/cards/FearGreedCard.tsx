import { memo } from 'react'
import { Gauge } from 'lucide-react'
import { Sparkline } from '../Sparkline'
import { getFearGreedColor } from '../../utils/marketSentiment'
import { InfoTooltip } from './InfoTooltip'
import { CardLoading, CardError } from './CardStates'
import type { FearGreedResponse } from '../../types'

interface FearGreedCardProps {
  data: FearGreedResponse | undefined
  isError?: boolean
  spark: number[]
  sparkTimeLabel?: string
}

function FearGreedCardInner({ data, isError, spark, sparkTimeLabel }: FearGreedCardProps) {
  // S8: cache color result instead of calling 3 times
  const colors = data ? getFearGreedColor(data.data.value) : null

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full flex flex-col">
      <div className="flex items-center space-x-2 mb-4">
        <Gauge className="w-5 h-5 text-slate-400" />
        <h3 className="font-medium text-white">Fear & Greed Index</h3>
        <InfoTooltip text="Measures market sentiment from 0 (extreme fear) to 100 (extreme greed). Extreme fear often signals buying opportunities; extreme greed may indicate overheated markets." />
      </div>

      {isError ? <CardError /> : data && colors ? (
        <div className="flex-1 flex flex-col items-center">
          <div className="relative w-48 h-24 mb-2">
            <svg viewBox="0 0 200 100" className="w-full h-full">
              <defs>
                <linearGradient id="fearGreedGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#ef4444" />
                  <stop offset="25%" stopColor="#f97316" />
                  <stop offset="50%" stopColor="#eab308" />
                  <stop offset="75%" stopColor="#84cc16" />
                  <stop offset="100%" stopColor="#22c55e" />
                </linearGradient>
              </defs>
              <path d="M 20 95 A 80 80 0 0 1 180 95" fill="none" stroke="#334155" strokeWidth="12" strokeLinecap="round" />
              <path d="M 20 95 A 80 80 0 0 1 180 95" fill="none" stroke="url(#fearGreedGradient)" strokeWidth="12" strokeLinecap="round" />
              <g transform={`rotate(${-90 + (data.data.value / 100) * 180}, 100, 95)`}>
                <line x1="100" y1="95" x2="100" y2="30" stroke="white" strokeWidth="3" strokeLinecap="round" />
                <circle cx="100" cy="95" r="6" fill="white" />
              </g>
            </svg>
          </div>
          <div className={`text-4xl font-bold ${colors.text}`}>{data.data.value}</div>
          <div className={`px-3 py-1 rounded-full text-sm font-medium mt-1 ${colors.bg} ${colors.text} border ${colors.border}`}>
            {data.data.value_classification}
          </div>
          <div className="flex justify-between w-full mt-3 text-xs text-slate-500">
            <span>Extreme Fear</span>
            <span>Neutral</span>
            <span>Extreme Greed</span>
          </div>
          <div className="mt-auto w-full pt-2">
            <Sparkline data={spark} color="#eab308" height={54} timeLabel={sparkTimeLabel} />
          </div>
        </div>
      ) : <CardLoading />}
    </div>
  )
}

export const FearGreedCard = memo(FearGreedCardInner)
