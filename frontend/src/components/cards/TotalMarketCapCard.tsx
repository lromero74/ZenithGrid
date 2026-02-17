import { memo } from 'react'
import { Globe } from 'lucide-react'
import { Sparkline } from '../Sparkline'
import { InfoTooltip } from './InfoTooltip'
import { CardLoading, CardError } from './CardStates'
import type { TotalMarketCapResponse } from '../../types'

interface TotalMarketCapCardProps {
  data: TotalMarketCapResponse | undefined
  isError?: boolean
  spark: number[]
  sparkTimeLabel?: string
}

function TotalMarketCapCardInner({ data, isError, spark, sparkTimeLabel }: TotalMarketCapCardProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <Globe className="w-5 h-5 text-blue-400" />
        <h3 className="font-medium text-white">Total Crypto Market</h3>
        <InfoTooltip text="Combined market cap of all cryptocurrencies. Compare to gold (~$14T) and stocks (~$45T) to gauge crypto's overall adoption and growth potential." />
      </div>

      {isError ? <CardError /> : data ? (
        <div className="flex flex-col items-center">
          <div className="text-4xl font-bold text-blue-400 mb-2">
            ${(data.total_market_cap / 1_000_000_000_000).toFixed(2)}T
          </div>
          <div className="text-xs text-slate-400 mb-4">Total crypto market capitalization</div>

          <div className="w-full bg-slate-900/50 rounded-lg p-3">
            <div className="text-xs text-slate-500 mb-1 text-center">For reference</div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="text-slate-400">Gold:</div>
              <div className="text-yellow-400 text-right">~$14T</div>
              <div className="text-slate-400">S&P 500:</div>
              <div className="text-green-400 text-right">~$45T</div>
            </div>
          </div>

          <Sparkline data={spark} color="#60a5fa" height={36} timeLabel={sparkTimeLabel} />
          <div className="text-[10px] text-slate-600 text-center">
            All cryptocurrencies combined
          </div>
        </div>
      ) : <CardLoading />}
    </div>
  )
}

export const TotalMarketCapCard = memo(TotalMarketCapCardInner)
