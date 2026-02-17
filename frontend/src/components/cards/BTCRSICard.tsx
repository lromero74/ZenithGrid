import { memo } from 'react'
import { Activity } from 'lucide-react'
import { Sparkline } from '../Sparkline'
import { InfoTooltip } from './InfoTooltip'
import { CardLoading, CardError } from './CardStates'
import type { BTCRSIResponse } from '../../types'

interface BTCRSICardProps {
  data: BTCRSIResponse | undefined
  isError?: boolean
  spark: number[]
  sparkTimeLabel?: string
}

function getZoneColor(zone: string) {
  if (zone === 'oversold') return 'text-green-400'
  if (zone === 'overbought') return 'text-red-400'
  return 'text-slate-300'
}

function getZoneLabel(zone: string) {
  if (zone === 'oversold') return 'Oversold'
  if (zone === 'overbought') return 'Overbought'
  return 'Neutral'
}

function getSparkColor(zone: string) {
  if (zone === 'oversold') return '#4ade80'
  if (zone === 'overbought') return '#f87171'
  return '#94a3b8'
}

function BTCRSICardInner({ data, isError, spark, sparkTimeLabel }: BTCRSICardProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <Activity className="w-5 h-5 text-yellow-500" />
        <h3 className="font-medium text-white">BTC RSI (14)</h3>
        <InfoTooltip text="Relative Strength Index measures momentum on daily candles. RSI below 30 suggests BTC is oversold (potential buying opportunity); above 70 suggests overbought (potential correction ahead)." />
      </div>

      {isError ? <CardError /> : data ? (
        <div className="flex flex-col items-center">
          <div className={`text-4xl font-bold mb-1 ${getZoneColor(data.zone)}`}>
            {data.rsi.toFixed(1)}
          </div>
          <div className={`text-xs mb-3 px-2 py-0.5 rounded ${
            data.zone === 'oversold' ? 'bg-green-500/20 text-green-400' :
            data.zone === 'overbought' ? 'bg-red-500/20 text-red-400' :
            'bg-slate-500/20 text-slate-400'
          }`}>
            {getZoneLabel(data.zone)}
          </div>

          <div className="w-full mb-3">
            <div className="flex justify-between text-[10px] text-slate-500 mb-1">
              <span>Oversold</span>
              <span>Overbought</span>
            </div>
            <div className="relative h-2 bg-slate-700 rounded-full overflow-hidden">
              <div className="absolute inset-0 flex">
                <div className="w-[30%] bg-green-900/40" />
                <div className="w-[40%] bg-slate-700" />
                <div className="w-[30%] bg-red-900/40" />
              </div>
              <div
                className="absolute top-0 w-1.5 h-full bg-white rounded-full shadow-lg"
                style={{ left: `calc(${Math.min(Math.max(data.rsi, 0), 100)}% - 3px)` }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-slate-600 mt-0.5">
              <span>0</span>
              <span>30</span>
              <span>70</span>
              <span>100</span>
            </div>
          </div>

          <Sparkline data={spark} color={getSparkColor(data.zone)} height={36} timeLabel={sparkTimeLabel} />
        </div>
      ) : <CardLoading />}
    </div>
  )
}

export const BTCRSICard = memo(BTCRSICardInner)
