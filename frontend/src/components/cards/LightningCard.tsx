import { memo } from 'react'
import { Zap } from 'lucide-react'
import { Sparkline } from '../Sparkline'
import { InfoTooltip } from './InfoTooltip'
import { CardLoading, CardError } from './CardStates'
import type { LightningResponse } from '../../types'

interface LightningCardProps {
  data: LightningResponse | undefined
  isError?: boolean
  spark: number[]
  sparkTimeLabel?: string
}

function LightningCardInner({ data, isError, spark, sparkTimeLabel }: LightningCardProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <Zap className="w-5 h-5 text-yellow-400" />
        <h3 className="font-medium text-white">Lightning Network</h3>
        <InfoTooltip text="Bitcoin's Layer 2 for instant, low-fee payments. Growing capacity shows real-world adoption and scaling progress. Key infrastructure for BTC as money." />
      </div>

      {isError ? <CardError /> : data ? (
        <div className="flex flex-col items-center">
          <div className="text-3xl font-bold text-yellow-400 mb-1">
            {data.total_capacity_btc.toLocaleString()} BTC
          </div>
          <div className="text-xs text-slate-400 mb-4">total capacity</div>

          <div className="w-full grid grid-cols-2 gap-2 text-xs mb-3">
            <div className="bg-slate-900/50 rounded p-2 text-center">
              <div className="text-slate-500">Nodes</div>
              <div className="text-yellow-400 font-mono">{data.node_count.toLocaleString()}</div>
            </div>
            <div className="bg-slate-900/50 rounded p-2 text-center">
              <div className="text-slate-500">Channels</div>
              <div className="text-yellow-400 font-mono">{data.channel_count.toLocaleString()}</div>
            </div>
          </div>

          <Sparkline data={spark} color="#eab308" height={36} timeLabel={sparkTimeLabel} />
          <div className="text-[10px] text-slate-600 text-center">
            Bitcoin's Layer 2 scaling solution
          </div>
        </div>
      ) : <CardLoading />}
    </div>
  )
}

export const LightningCard = memo(LightningCardInner)
