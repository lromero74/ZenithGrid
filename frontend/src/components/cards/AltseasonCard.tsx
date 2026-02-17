import { memo } from 'react'
import { TrendingUp } from 'lucide-react'
import { Sparkline } from '../Sparkline'
import { InfoTooltip } from './InfoTooltip'
import { CardLoading, CardError } from './CardStates'
import type { AltseasonIndexResponse } from '../../types'

interface AltseasonCardProps {
  data: AltseasonIndexResponse | undefined
  isError?: boolean
  spark: number[]
  sparkTimeLabel?: string
}

function getSeasonColor(season: string) {
  if (season === 'Altcoin Season') return { text: 'text-purple-400', bg: 'bg-purple-500/20', border: 'border-purple-500/30' }
  if (season === 'Bitcoin Season') return { text: 'text-orange-400', bg: 'bg-orange-500/20', border: 'border-orange-500/30' }
  return { text: 'text-slate-400', bg: 'bg-slate-500/20', border: 'border-slate-500/30' }
}

function AltseasonCardInner({ data, isError, spark, sparkTimeLabel }: AltseasonCardProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <TrendingUp className="w-5 h-5 text-purple-400" />
        <h3 className="font-medium text-white">Altcoin Season Index</h3>
        <InfoTooltip text="Measures if altcoins are outperforming Bitcoin. Above 75 = Alt Season (consider taking altcoin profits). Below 25 = BTC Season (rotate to BTC or accumulate alts)." />
      </div>

      {isError ? <CardError /> : data ? (
        <div className="flex flex-col items-center">
          <div className={`text-4xl font-bold mb-2 ${data.season === 'Altcoin Season' ? 'text-purple-400' : data.season === 'Bitcoin Season' ? 'text-orange-400' : 'text-slate-300'}`}>
            {data.altseason_index}
          </div>
          {(() => {
            const colors = getSeasonColor(data.season)
            return (
              <div className={`px-3 py-1 rounded-full text-sm font-medium ${colors.bg} ${colors.text} border ${colors.border}`}>
                {data.season}
              </div>
            )
          })()}

          <div className="w-full mt-4">
            <div className="h-3 bg-slate-700 rounded-full overflow-hidden relative">
              <div className="absolute inset-0 flex">
                <div className="w-1/4 bg-orange-500/30" />
                <div className="w-1/2 bg-slate-600/30" />
                <div className="w-1/4 bg-purple-500/30" />
              </div>
              <div
                className="absolute top-0 bottom-0 w-1 bg-white rounded-full shadow-lg transition-all duration-300"
                style={{ left: `${data.altseason_index}%` }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-slate-500 mt-1">
              <span>BTC Season</span>
              <span>Neutral</span>
              <span>Alt Season</span>
            </div>
          </div>

          <Sparkline data={spark} color="#a855f7" height={36} timeLabel={sparkTimeLabel} />
          <div className="text-xs text-slate-500">
            {data.outperformers}/{data.total_altcoins} alts beat BTC (30d)
          </div>
        </div>
      ) : <CardLoading />}
    </div>
  )
}

export const AltseasonCard = memo(AltseasonCardInner)
