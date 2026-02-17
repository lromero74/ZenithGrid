import { memo } from 'react'
import { PieChart } from 'lucide-react'
import { Sparkline } from '../Sparkline'
import { InfoTooltip } from './InfoTooltip'
import { CardLoading, CardError } from './CardStates'
import type { BTCDominanceResponse } from '../../types'

interface BTCDominanceCardProps {
  data: BTCDominanceResponse | undefined
  isError?: boolean
  spark: number[]
  sparkTimeLabel?: string
}

function BTCDominanceCardInner({ data, isError, spark, sparkTimeLabel }: BTCDominanceCardProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <PieChart className="w-5 h-5 text-orange-500" />
        <h3 className="font-medium text-white">BTC Dominance</h3>
        <InfoTooltip text="Bitcoin's share of total crypto market cap. High dominance suggests BTC strength; falling dominance often signals altcoin season or risk-on sentiment." />
      </div>

      {isError ? <CardError /> : data ? (
        <div className="flex flex-col items-center">
          <div className="text-4xl font-bold text-orange-500 mb-2">{data.btc_dominance.toFixed(1)}%</div>
          <div className="text-xs text-slate-400 mb-4">of total crypto market cap</div>

          <div className="w-full space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">BTC</span>
              <div className="flex-1 mx-2 h-2 bg-slate-700 rounded-full overflow-hidden">
                <div className="h-full bg-orange-500" style={{ width: `${data.btc_dominance}%` }} />
              </div>
              <span className="text-xs text-orange-500 w-12 text-right">{data.btc_dominance.toFixed(1)}%</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">ETH</span>
              <div className="flex-1 mx-2 h-2 bg-slate-700 rounded-full overflow-hidden">
                <div className="h-full bg-blue-500" style={{ width: `${data.eth_dominance}%` }} />
              </div>
              <span className="text-xs text-blue-500 w-12 text-right">{data.eth_dominance.toFixed(1)}%</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">Others</span>
              <div className="flex-1 mx-2 h-2 bg-slate-700 rounded-full overflow-hidden">
                <div className="h-full bg-purple-500" style={{ width: `${data.others_dominance}%` }} />
              </div>
              <span className="text-xs text-purple-500 w-12 text-right">{data.others_dominance.toFixed(1)}%</span>
            </div>
          </div>

          <Sparkline data={spark} color="#f97316" height={36} timeLabel={sparkTimeLabel} />
          <div className="text-[10px] text-slate-600">
            Total MCap: ${(data.total_market_cap / 1_000_000_000_000).toFixed(2)}T
          </div>
        </div>
      ) : <CardLoading />}
    </div>
  )
}

export const BTCDominanceCard = memo(BTCDominanceCardInner)
