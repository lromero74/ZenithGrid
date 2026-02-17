import { memo } from 'react'
import { TrendingDown } from 'lucide-react'
import { InfoTooltip } from './InfoTooltip'
import { CardLoading, CardError } from './CardStates'
import type { ATHResponse } from '../../types'

interface ATHCardProps {
  data: ATHResponse | undefined
  isError?: boolean
}

function ATHCardInner({ data, isError }: ATHCardProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <TrendingDown className="w-5 h-5 text-red-400" />
        <h3 className="font-medium text-white">Days Since ATH</h3>
        <InfoTooltip text="Days since Bitcoin's all-time high. Long periods below ATH often mark accumulation zones. Breaking ATH typically triggers FOMO and price discovery." />
      </div>

      {isError ? <CardError /> : data ? (
        <div className="flex flex-col items-center">
          <div className="text-4xl font-bold text-red-400 mb-1">
            {data.days_since_ath}
          </div>
          <div className="text-xs text-slate-400 mb-3">days since all-time high</div>

          <div className="w-full bg-slate-900/50 rounded-lg p-3 mb-2">
            <div className="flex justify-between items-center mb-1">
              <span className="text-xs text-slate-500">ATH</span>
              <span className="text-xs font-mono text-green-400">${data.ath.toLocaleString()}</span>
            </div>
            <div className="flex justify-between items-center mb-1">
              <span className="text-xs text-slate-500">Current</span>
              <span className="text-xs font-mono text-slate-300">${data.current_price.toLocaleString()}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs text-slate-500">Drawdown</span>
              <span className="text-xs font-mono text-red-400">{data.drawdown_pct.toFixed(1)}%</span>
            </div>
          </div>

          <div className="w-full">
            <div className="flex justify-between text-[10px] text-slate-500 mb-1">
              <span>Recovery</span>
              <span>{data.recovery_pct.toFixed(0)}%</span>
            </div>
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-red-600 to-green-500"
                style={{ width: `${data.recovery_pct}%` }}
              />
            </div>
          </div>
        </div>
      ) : <CardLoading />}
    </div>
  )
}

export const ATHCard = memo(ATHCardInner)
