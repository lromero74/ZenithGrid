/**
 * BTC Halving Countdown Card
 *
 * S1 fix: Timer state (liveCountdown) is managed internally,
 * preventing parent carousel re-renders every second.
 */

import { memo, useState, useEffect, useRef } from 'react'
import { Timer, ToggleLeft, ToggleRight } from 'lucide-react'
import { InfoTooltip } from './InfoTooltip'
import { CardLoading, CardError } from './CardStates'
import {
  NEXT_HALVING_BLOCK,
  AVG_BLOCK_TIME_MINUTES,
  formatExtendedCountdown,
  calculateHalvingCountdown,
} from '../../utils/marketSentiment'
import type { BlockHeightResponse } from '../../types'

interface HalvingCardProps {
  blockHeight: BlockHeightResponse | undefined
  isError?: boolean
}

function HalvingCardInner({ blockHeight, isError }: HalvingCardProps) {
  const [showExtendedCountdown, setShowExtendedCountdown] = useState(false)
  const [liveCountdown, setLiveCountdown] = useState('')
  const targetTimeRef = useRef(0)

  const halvingCountdown = blockHeight ? calculateHalvingCountdown(blockHeight.height) : null

  // Calculate target time once when block height changes
  useEffect(() => {
    if (!blockHeight?.height) return
    const blocksRemaining = NEXT_HALVING_BLOCK - blockHeight.height
    const minutesRemaining = blocksRemaining * AVG_BLOCK_TIME_MINUTES
    targetTimeRef.current = Date.now() + minutesRemaining * 60 * 1000
  }, [blockHeight?.height])

  // Update countdown display every second (contained to this card only)
  useEffect(() => {
    if (!blockHeight?.height) return

    const updateCountdown = () => {
      const now = Date.now()
      const diff = targetTimeRef.current - now
      if (diff <= 0) {
        setLiveCountdown('Halving imminent!')
        return
      }

      if (showExtendedCountdown) {
        setLiveCountdown(formatExtendedCountdown(diff))
      } else {
        const days = Math.floor(diff / (1000 * 60 * 60 * 24))
        const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
        const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
        const secs = Math.floor((diff % (1000 * 60)) / 1000)
        setLiveCountdown(`${days}d ${hours}h ${mins}m ${secs}s`)
      }
    }

    updateCountdown()
    const interval = setInterval(updateCountdown, 1000)
    return () => clearInterval(interval)
  }, [blockHeight?.height, showExtendedCountdown])

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <Timer className="w-5 h-5 text-orange-400" />
          <h3 className="font-medium text-white">Next BTC Halving</h3>
          <InfoTooltip text="Bitcoin's block reward halves every ~4 years. Historically, halvings reduce new supply and often precede bull runs. Next halving cuts reward from 3.125 to 1.5625 BTC." />
        </div>
        <button
          onClick={() => setShowExtendedCountdown(!showExtendedCountdown)}
          className="flex items-center space-x-1 px-2 py-1 text-xs bg-slate-700/50 hover:bg-slate-700 rounded transition-colors"
        >
          {showExtendedCountdown ? <ToggleRight className="w-4 h-4 text-orange-400" /> : <ToggleLeft className="w-4 h-4 text-slate-400" />}
          <span className="text-slate-400">{showExtendedCountdown ? 'Y/M/D' : 'Days'}</span>
        </button>
      </div>

      {isError ? <CardError /> : halvingCountdown && blockHeight ? (
        <div className="flex flex-col items-center">
          <div className="text-2xl sm:text-3xl font-mono font-bold text-orange-400 mb-2 whitespace-nowrap">{liveCountdown || 'Calculating...'}</div>
          <div className="text-sm text-slate-400 mb-4">
            {halvingCountdown.estimatedDate.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
          </div>
          <div className="w-full mb-2">
            <div className="flex justify-between text-xs text-slate-500 mb-1">
              <span>Epoch Progress</span>
              <span>{halvingCountdown.percentComplete.toFixed(1)}%</span>
            </div>
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div className="h-full bg-gradient-to-r from-orange-600 to-yellow-500 transition-all duration-500" style={{ width: `${halvingCountdown.percentComplete}%` }} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4 w-full mt-3 text-center">
            <div className="bg-slate-900/50 rounded-lg p-2">
              <div className="text-xs text-slate-500">Current Block</div>
              <div className="text-sm font-mono text-slate-300">{blockHeight.height.toLocaleString()}</div>
            </div>
            <div className="bg-slate-900/50 rounded-lg p-2">
              <div className="text-xs text-slate-500">Blocks Remaining</div>
              <div className="text-sm font-mono text-orange-400">{halvingCountdown.blocksRemaining.toLocaleString()}</div>
            </div>
          </div>
        </div>
      ) : <CardLoading />}
    </div>
  )
}

export const HalvingCard = memo(HalvingCardInner)
