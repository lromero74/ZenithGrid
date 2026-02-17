import { memo } from 'react'
import { Activity } from 'lucide-react'
import { Sparkline } from '../Sparkline'
import { InfoTooltip } from './InfoTooltip'
import { CardLoading, CardError } from './CardStates'
import type { MempoolResponse } from '../../types'

interface MempoolCardProps {
  data: MempoolResponse | undefined
  isError?: boolean
  spark: number[]
  sparkTimeLabel?: string
}

function getCongestionColor(congestion: string) {
  if (congestion === 'High') return { text: 'text-red-400', bg: 'bg-red-500/20', border: 'border-red-500/30' }
  if (congestion === 'Medium') return { text: 'text-yellow-400', bg: 'bg-yellow-500/20', border: 'border-yellow-500/30' }
  return { text: 'text-green-400', bg: 'bg-green-500/20', border: 'border-green-500/30' }
}

function MempoolCardInner({ data, isError, spark, sparkTimeLabel }: MempoolCardProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <Activity className="w-5 h-5 text-purple-400" />
        <h3 className="font-medium text-white">Bitcoin Mempool</h3>
        <InfoTooltip text="Pending Bitcoin transactions awaiting confirmation. High congestion = high demand and fees. Low congestion = cheap transactions, possibly less activity." />
      </div>

      {isError ? <CardError /> : data ? (
        <div className="flex flex-col items-center">
          <div className="text-3xl font-bold text-purple-400 mb-1">
            {data.tx_count.toLocaleString()}
          </div>
          <div className="text-xs text-slate-400 mb-2">pending transactions</div>

          {(() => {
            const colors = getCongestionColor(data.congestion)
            return (
              <div className={`px-3 py-1 rounded-full text-sm font-medium mb-3 ${colors.bg} ${colors.text} border ${colors.border}`}>
                {data.congestion} Congestion
              </div>
            )
          })()}

          <div className="w-full space-y-1 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-500">Fast (~10 min)</span>
              <span className="text-green-400 font-mono">{data.fee_fastest} sat/vB</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Medium (~30 min)</span>
              <span className="text-yellow-400 font-mono">{data.fee_half_hour} sat/vB</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Economy (~1 hr)</span>
              <span className="text-slate-400 font-mono">{data.fee_hour} sat/vB</span>
            </div>
          </div>

          <Sparkline data={spark} color="#a855f7" height={36} timeLabel={sparkTimeLabel} />
          <div className="text-[10px] text-slate-600 text-center">
            Recommended fee rates
          </div>
        </div>
      ) : <CardLoading />}
    </div>
  )
}

export const MempoolCard = memo(MempoolCardInner)
