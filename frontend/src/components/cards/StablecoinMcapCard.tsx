import { memo } from 'react'
import { Coins } from 'lucide-react'
import { Sparkline } from '../Sparkline'
import { InfoTooltip } from './InfoTooltip'
import { CardLoading, CardError } from './CardStates'
import type { StablecoinMcapResponse } from '../../types'

interface StablecoinMcapCardProps {
  data: StablecoinMcapResponse | undefined
  isError?: boolean
  spark: number[]
  sparkTimeLabel?: string
}

function StablecoinMcapCardInner({ data, isError, spark, sparkTimeLabel }: StablecoinMcapCardProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full flex flex-col">
      <div className="flex items-center space-x-2 mb-4">
        <Coins className="w-5 h-5 text-green-500" />
        <h3 className="font-medium text-white">Stablecoin Supply</h3>
        <InfoTooltip text="Total stablecoins in circulation - 'dry powder' waiting to deploy. Rising supply often precedes market rallies as capital is ready to buy the dip." />
      </div>

      {isError ? <CardError /> : data ? (
        <div className="flex-1 flex flex-col items-center">
          <div className="text-3xl font-bold text-green-400 mb-1">
            ${(data.total_stablecoin_mcap / 1_000_000_000).toFixed(1)}B
          </div>
          <div className="text-xs text-slate-400 mb-4">"Dry powder" in stablecoins</div>

          <div className="w-full space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">USDT</span>
              <span className="text-xs text-green-400">${(data.usdt_mcap / 1_000_000_000).toFixed(1)}B</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">USDC</span>
              <span className="text-xs text-blue-400">${(data.usdc_mcap / 1_000_000_000).toFixed(1)}B</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">DAI</span>
              <span className="text-xs text-yellow-400">${(data.dai_mcap / 1_000_000_000).toFixed(1)}B</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-400">Others</span>
              <span className="text-xs text-slate-300">${(data.others_mcap / 1_000_000_000).toFixed(1)}B</span>
            </div>
          </div>

          <div className="mt-auto w-full pt-2">
            <Sparkline data={spark} color="#22c55e" height={54} timeLabel={sparkTimeLabel} />
            <div className="text-[10px] text-slate-600 text-center">
              High supply = capital ready to deploy
            </div>
          </div>
        </div>
      ) : <CardLoading />}
    </div>
  )
}

export const StablecoinMcapCard = memo(StablecoinMcapCardInner)
