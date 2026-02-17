import { memo } from 'react'
import { Sun } from 'lucide-react'
import { InfoTooltip } from './InfoTooltip'
import { CardLoading } from './CardStates'
import type { MarketSeason, SeasonInfo } from '../../utils/seasonDetection'

interface SeasonCardProps {
  seasonInfo: SeasonInfo | null
}

function SeasonCardInner({ seasonInfo }: SeasonCardProps) {
  if (!seasonInfo) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
        <div className="flex items-center space-x-2 mb-4">
          <Sun className="w-5 h-5 text-slate-400" />
          <h3 className="font-medium text-white">Market Season</h3>
        </div>
        <CardLoading />
      </div>
    )
  }

  const IconComponent = seasonInfo.icon

  // Season cycle visualization positions (clockwise: accumulation, bull, distribution, bear)
  const seasonPositions: Record<MarketSeason, number> = {
    accumulation: 0,
    bull: 90,
    distribution: 180,
    bear: 270
  }

  const currentAngle = seasonPositions[seasonInfo.season] + (seasonInfo.progress * 0.9)

  return (
    <div className={`bg-gradient-to-br ${seasonInfo.bgGradient} border border-slate-700 rounded-lg p-4 h-full`}>
      <div className="flex items-center space-x-2 mb-4">
        <IconComponent className={`w-5 h-5 ${seasonInfo.color}`} />
        <h3 className="font-medium text-white">Market Season</h3>
        <InfoTooltip text="Crypto markets move in cycles: Accumulation (bottom), Bull (rising), Distribution (top), Bear (falling). Understanding the current phase helps inform strategy." />
      </div>

      <div className="flex flex-col items-center">
        {/* Season cycle wheel */}
        <div className="relative w-32 h-32 mb-3">
          <svg viewBox="0 0 100 100" className="w-full h-full">
            {/* Background circle segments */}
            <circle cx="50" cy="50" r="40" fill="none" stroke="#334155" strokeWidth="8" />

            {/* Season segments */}
            <path d="M 50 10 A 40 40 0 0 1 90 50" fill="none" stroke="#ec4899" strokeWidth="8" opacity="0.3" />
            <path d="M 90 50 A 40 40 0 0 1 50 90" fill="none" stroke="#22c55e" strokeWidth="8" opacity="0.3" />
            <path d="M 50 90 A 40 40 0 0 1 10 50" fill="none" stroke="#f97316" strokeWidth="8" opacity="0.3" />
            <path d="M 10 50 A 40 40 0 0 1 50 10" fill="none" stroke="#3b82f6" strokeWidth="8" opacity="0.3" />

            {/* Active segment highlight */}
            {seasonInfo.season === 'accumulation' && (
              <path d="M 50 10 A 40 40 0 0 1 90 50" fill="none" stroke="#ec4899" strokeWidth="8" />
            )}
            {seasonInfo.season === 'bull' && (
              <path d="M 90 50 A 40 40 0 0 1 50 90" fill="none" stroke="#22c55e" strokeWidth="8" />
            )}
            {seasonInfo.season === 'distribution' && (
              <path d="M 50 90 A 40 40 0 0 1 10 50" fill="none" stroke="#f97316" strokeWidth="8" />
            )}
            {seasonInfo.season === 'bear' && (
              <path d="M 10 50 A 40 40 0 0 1 50 10" fill="none" stroke="#3b82f6" strokeWidth="8" />
            )}

            {/* Position indicator */}
            <g transform={`rotate(${currentAngle}, 50, 50)`}>
              <circle cx="50" cy="14" r="5" fill="white" />
              <circle cx="50" cy="14" r="3" className={seasonInfo.color.replace('text-', 'fill-')} />
            </g>

            {/* Season labels */}
            <text x="78" y="24" fontSize="8" fill="#ec4899" textAnchor="middle" dominantBaseline="middle">&#x1F331;</text>
            <text x="78" y="78" fontSize="8" fill="#22c55e" textAnchor="middle" dominantBaseline="middle">&#x2600;&#xFE0F;</text>
            <text x="22" y="78" fontSize="8" fill="#f97316" textAnchor="middle" dominantBaseline="middle">&#x1F342;</text>
            <text x="22" y="24" fontSize="8" fill="#3b82f6" textAnchor="middle" dominantBaseline="middle">&#x2744;&#xFE0F;</text>

            {/* Center icon */}
            <foreignObject x="35" y="35" width="30" height="30">
              <div className="flex items-center justify-center w-full h-full">
                <IconComponent className={`w-6 h-6 ${seasonInfo.color}`} />
              </div>
            </foreignObject>
          </svg>
        </div>

        {/* Season name and description */}
        <div className={`text-2xl font-bold ${seasonInfo.color}`}>
          {seasonInfo.name}
        </div>
        <div className="text-xs text-slate-500 mb-1">
          {seasonInfo.subtitle}
        </div>
        <div className="text-xs text-slate-400 text-center mb-3 px-2">
          {seasonInfo.description}
        </div>

        {/* Progress and confidence */}
        <div className="w-full space-y-2">
          <div className="flex justify-between text-[10px] text-slate-500">
            <span>Cycle Progress</span>
            <span>{seasonInfo.progress.toFixed(0)}%</span>
          </div>
          <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${
                seasonInfo.season === 'accumulation' ? 'bg-pink-500' :
                seasonInfo.season === 'bull' ? 'bg-green-500' :
                seasonInfo.season === 'distribution' ? 'bg-orange-500' :
                'bg-blue-500'
              }`}
              style={{ width: `${seasonInfo.progress}%` }}
            />
          </div>
        </div>

        {/* Key signals */}
        {seasonInfo.signals.length > 0 && (
          <div className="w-full mt-3 space-y-1">
            {seasonInfo.signals.map((signal, idx) => (
              <div key={idx} className="text-[10px] text-slate-500 flex items-center gap-1">
                <span className={seasonInfo.color}>&#x2022;</span>
                {signal}
              </div>
            ))}
          </div>
        )}

        {/* Confidence indicator */}
        <div className="text-[10px] text-slate-600 mt-2">
          {seasonInfo.confidence}% confidence
        </div>
      </div>
    </div>
  )
}

export const SeasonCard = memo(SeasonCardInner)
