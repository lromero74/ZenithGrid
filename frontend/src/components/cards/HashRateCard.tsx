import { memo } from 'react'
import { Cpu } from 'lucide-react'
import { Sparkline } from '../Sparkline'
import { InfoTooltip } from './InfoTooltip'
import { CardLoading, CardError } from './CardStates'
import type { HashRateResponse } from '../../types'

interface HashRateCardProps {
  data: HashRateResponse | undefined
  isError?: boolean
  spark: number[]
  sparkTimeLabel?: string
}

function HashRateCardInner({ data, isError, spark, sparkTimeLabel }: HashRateCardProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <Cpu className="w-5 h-5 text-cyan-400" />
        <h3 className="font-medium text-white">Network Hash Rate</h3>
        <InfoTooltip text="Total mining power securing Bitcoin. Higher hash rate = stronger security and miner confidence. Dropping hash rate can signal miner capitulation." />
      </div>

      {isError ? <CardError /> : data ? (
        <div className="flex flex-col items-center">
          <div className="text-3xl font-bold text-cyan-400 mb-1">
            {data.hash_rate_eh.toFixed(0)} EH/s
          </div>
          <div className="text-xs text-slate-400 mb-4">exahashes per second</div>

          <div className="w-full bg-slate-900/50 rounded-lg p-3 mb-3">
            <div className="flex justify-between items-center">
              <span className="text-xs text-slate-500">Next Difficulty</span>
              <span className={`text-xs font-mono ${data.difficulty_t >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {data.difficulty_t >= 0 ? '+' : ''}{data.difficulty_t.toFixed(1)}%
              </span>
            </div>
          </div>

          <div className="w-full h-2 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-cyan-600 to-blue-500"
              style={{ width: `${Math.min(100, (data.hash_rate_eh / 1000) * 100)}%` }}
            />
          </div>

          <Sparkline data={spark} color="#22d3ee" height={36} timeLabel={sparkTimeLabel} />
          <div className="text-[10px] text-slate-600 text-center">
            Higher = more secure network
          </div>
        </div>
      ) : <CardLoading />}
    </div>
  )
}

export const HashRateCard = memo(HashRateCardInner)
