import { memo } from 'react'
import { Database } from 'lucide-react'
import { InfoTooltip } from './InfoTooltip'
import { CardLoading, CardError } from './CardStates'
import type { BTCSupplyResponse } from '../../types'

interface BTCSupplyCardProps {
  data: BTCSupplyResponse | undefined
  isError?: boolean
}

function BTCSupplyCardInner({ data, isError }: BTCSupplyCardProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <Database className="w-5 h-5 text-orange-400" />
        <h3 className="font-medium text-white">BTC Supply Progress</h3>
        <InfoTooltip text="Bitcoin's fixed 21M supply creates scarcity. Over 93% already mined. As remaining supply shrinks, each halving has greater supply shock potential." />
      </div>

      {isError ? <CardError /> : data ? (
        <div className="flex flex-col items-center">
          <div className="text-3xl font-bold text-orange-400 mb-1">
            {data.percent_mined.toFixed(2)}%
          </div>
          <div className="text-xs text-slate-400 mb-3">of 21M mined</div>

          <div className="w-full mb-3">
            <div className="h-3 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-orange-600 to-yellow-500 transition-all duration-500"
                style={{ width: `${data.percent_mined}%` }}
              />
            </div>
          </div>

          <div className="w-full grid grid-cols-2 gap-2 text-xs">
            <div className="bg-slate-900/50 rounded p-2 text-center">
              <div className="text-slate-500">Circulating</div>
              <div className="text-orange-400 font-mono">{(data.circulating / 1_000_000).toFixed(2)}M</div>
            </div>
            <div className="bg-slate-900/50 rounded p-2 text-center">
              <div className="text-slate-500">Remaining</div>
              <div className="text-slate-300 font-mono">{(data.remaining / 1_000_000).toFixed(2)}M</div>
            </div>
          </div>

          <div className="text-[10px] text-slate-600 mt-3 text-center">
            Max supply: 21,000,000 BTC
          </div>
        </div>
      ) : <CardLoading />}
    </div>
  )
}

export const BTCSupplyCard = memo(BTCSupplyCardInner)
