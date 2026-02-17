/**
 * US National Debt Card
 *
 * S1 fix: Timer state (liveDebt, 100ms interval) is managed internally,
 * preventing parent carousel re-renders 10x/sec.
 */

import { memo, useState, useEffect, useRef } from 'react'
import { DollarSign, Info } from 'lucide-react'
import { InfoTooltip } from './InfoTooltip'
import { CardLoading, CardError } from './CardStates'
import { formatDebt, calculateDebtMilestone, formatDebtCountdown } from '../../utils/marketSentiment'
import type { USDebtResponse } from '../../types'

interface USDebtCardProps {
  usDebtData: USDebtResponse | undefined
  isError?: boolean
  onShowHistory: () => void
}

function USDebtCardInner({ usDebtData, isError, onShowHistory }: USDebtCardProps) {
  const [liveDebt, setLiveDebt] = useState(0)
  const debtStartTimeRef = useRef(0)
  const debtBaseValueRef = useRef(0)

  useEffect(() => {
    if (!usDebtData) return

    debtBaseValueRef.current = usDebtData.total_debt
    debtStartTimeRef.current = Date.now()
    setLiveDebt(usDebtData.total_debt)

    const updateDebt = () => {
      const elapsedSeconds = (Date.now() - debtStartTimeRef.current) / 1000
      const newDebt = debtBaseValueRef.current + (elapsedSeconds * usDebtData.debt_per_second)
      setLiveDebt(newDebt)
    }

    const interval = setInterval(updateDebt, 100)
    return () => clearInterval(interval)
  }, [usDebtData])

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <DollarSign className="w-5 h-5 text-green-400" />
        <h3 className="font-medium text-white">US National Debt</h3>
        <InfoTooltip text="Massive debt expansion often leads to currency debasement. Bitcoin is seen as a hedge against this. Watch debt-to-GDP ratio and ceiling debates for macro signals." />
      </div>

      {isError ? <CardError /> : usDebtData ? (
        <div className="flex flex-col items-center">
          <div className="flex items-center gap-2 mb-2">
            <div className="text-xl sm:text-2xl font-mono font-bold text-red-400 tracking-tighter whitespace-nowrap">${formatDebt(liveDebt)}</div>
            <button onClick={onShowHistory} className="w-5 h-5 rounded-full bg-slate-700 hover:bg-slate-600 flex items-center justify-center transition-colors" title="View debt ceiling history">
              <Info className="w-3 h-3 text-slate-400" />
            </button>
          </div>
          <div className="text-xs text-slate-400 mb-3">
            {usDebtData.debt_per_second > 0 ? '+' : ''}${formatDebt(usDebtData.debt_per_second)}/sec
          </div>

          {/* Debt Ceiling Info */}
          <div className="w-full bg-slate-900/50 rounded-lg p-2 mb-2">
            <div className="flex justify-between items-center">
              <span className="text-xs text-slate-500">Debt Ceiling</span>
              {usDebtData.debt_ceiling_suspended ? (
                <span className="text-xs font-medium text-yellow-400">SUSPENDED</span>
              ) : usDebtData.debt_ceiling ? (
                <span className="text-xs font-mono text-slate-300">${(usDebtData.debt_ceiling / 1_000_000_000_000).toFixed(2)}T</span>
              ) : (
                <span className="text-xs text-slate-500">Unknown</span>
              )}
            </div>
            {!usDebtData.debt_ceiling_suspended && usDebtData.headroom != null && (
              <div className="flex justify-between items-center mt-1">
                <span className="text-[10px] text-slate-600">Headroom</span>
                <span className={`text-[10px] font-mono ${usDebtData.headroom > 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {usDebtData.headroom > 0 ? '+' : ''}${(usDebtData.headroom / 1_000_000_000_000).toFixed(3)}T
                </span>
              </div>
            )}
            {!usDebtData.debt_ceiling_suspended && usDebtData.debt_ceiling && usDebtData.debt_per_second > 0 && (() => {
              const remaining = usDebtData.debt_ceiling - liveDebt
              const exceeded = remaining <= 0
              const seconds = Math.abs(remaining / usDebtData.debt_per_second)
              return (
                <div className="flex justify-between items-center mt-1">
                  <span className="text-[10px] text-slate-600">{exceeded ? 'Exceeded by' : 'Hits ceiling in'}</span>
                  <span className={`text-[10px] font-mono ${exceeded ? 'text-red-400' : 'text-orange-400'}`}>
                    {exceeded
                      ? formatDebtCountdown(seconds) + ' ago'
                      : formatDebtCountdown(seconds)}
                  </span>
                </div>
              )
            })()}
          </div>

          <div className="w-full bg-slate-900/50 rounded-lg p-2">
            <div className="flex justify-between items-center mb-1">
              <span className="text-xs text-slate-500">Debt-to-GDP</span>
              <span className={`text-sm font-bold ${usDebtData.debt_to_gdp_ratio > 100 ? 'text-red-400' : 'text-yellow-400'}`}>
                {usDebtData.debt_to_gdp_ratio.toFixed(1)}%
              </span>
            </div>
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div className={`h-full transition-all duration-500 ${usDebtData.debt_to_gdp_ratio > 100 ? 'bg-gradient-to-r from-red-600 to-red-400' : 'bg-gradient-to-r from-yellow-600 to-yellow-400'}`} style={{ width: `${Math.min(150, usDebtData.debt_to_gdp_ratio)}%` }} />
            </div>
          </div>

          {/* Projected Milestones */}
          {(() => {
            const m1T = calculateDebtMilestone(liveDebt, usDebtData.debt_per_second, 1)
            const m5T = calculateDebtMilestone(liveDebt, usDebtData.debt_per_second, 5)
            return (
              <div className="w-full bg-slate-900/50 rounded-lg p-2 mt-2">
                <div className="text-[10px] text-slate-500 mb-1.5 font-medium">Projected Milestones</div>
                <div className="space-y-1.5">
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-slate-400">
                      ${(m1T.milestone / 1_000_000_000_000).toFixed(0)}T
                    </span>
                    <div className="text-right">
                      <span className="text-xs font-mono text-orange-400">
                        {formatDebtCountdown(m1T.secondsUntil)}
                      </span>
                      <span className="text-[10px] text-slate-500 ml-2">
                        {m1T.estimatedDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                      </span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-slate-400">
                      ${(m5T.milestone / 1_000_000_000_000).toFixed(0)}T
                    </span>
                    <div className="text-right">
                      <span className="text-xs font-mono text-orange-400">
                        {formatDebtCountdown(m5T.secondsUntil)}
                      </span>
                      <span className="text-[10px] text-slate-500 ml-2">
                        {m5T.estimatedDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )
          })()}
        </div>
      ) : <CardLoading />}
    </div>
  )
}

export const USDebtCard = memo(USDebtCardInner)
