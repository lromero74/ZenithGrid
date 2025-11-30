/**
 * Market Sentiment Cards
 *
 * Displays Fear & Greed Index, BTC Halving Countdown, and US National Debt.
 * Can be used on Dashboard or News page.
 */

import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Gauge, Timer, DollarSign, ToggleLeft, ToggleRight, Info, X, ExternalLink } from 'lucide-react'
import { LoadingSpinner } from './LoadingSpinner'

// BTC Halving constants
const NEXT_HALVING_BLOCK = 1050000 // Block 1,050,000 is the next halving
const BLOCKS_PER_HALVING = 210000
const AVG_BLOCK_TIME_MINUTES = 10 // Average Bitcoin block time

interface FearGreedData {
  value: number
  value_classification: string
  timestamp: string
  time_until_update: string | null
}

interface FearGreedResponse {
  data: FearGreedData
  cached_at: string
  cache_expires_at: string
}

interface BlockHeightResponse {
  height: number
  timestamp: string
}

interface USDebtResponse {
  total_debt: number
  debt_per_second: number
  gdp: number
  debt_to_gdp_ratio: number
  record_date: string
  cached_at: string
  cache_expires_at: string
}

interface HalvingCountdown {
  blocksRemaining: number
  estimatedDate: Date
  daysRemaining: number
  hoursRemaining: number
  minutesRemaining: number
  percentComplete: number
}

interface DebtCeilingEvent {
  date: string
  amount_trillion: number | null
  suspended: boolean
  suspension_end: string | null
  note: string
  legislation: string | null
  political_context: string | null
  source_url: string | null
}

interface DebtCeilingHistoryResponse {
  events: DebtCeilingEvent[]
  total_events: number
  last_updated: string
}

// Get color for Fear/Greed meter based on value
function getFearGreedColor(value: number): { bg: string; text: string; border: string; gradient: string } {
  if (value <= 25) {
    return {
      bg: 'bg-red-500/20',
      text: 'text-red-400',
      border: 'border-red-500/30',
      gradient: 'from-red-600 to-red-400',
    }
  } else if (value <= 45) {
    return {
      bg: 'bg-orange-500/20',
      text: 'text-orange-400',
      border: 'border-orange-500/30',
      gradient: 'from-orange-600 to-orange-400',
    }
  } else if (value <= 55) {
    return {
      bg: 'bg-yellow-500/20',
      text: 'text-yellow-400',
      border: 'border-yellow-500/30',
      gradient: 'from-yellow-600 to-yellow-400',
    }
  } else if (value <= 75) {
    return {
      bg: 'bg-lime-500/20',
      text: 'text-lime-400',
      border: 'border-lime-500/30',
      gradient: 'from-lime-600 to-lime-400',
    }
  } else {
    return {
      bg: 'bg-green-500/20',
      text: 'text-green-400',
      border: 'border-green-500/30',
      gradient: 'from-green-600 to-green-400',
    }
  }
}

// Format large numbers with commas and optional prefix
function formatDebt(value: number): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

// Calculate next debt milestone and countdown
function calculateDebtMilestone(currentDebt: number, debtPerSecond: number, milestoneSize: number): {
  milestone: number
  secondsUntil: number
  estimatedDate: Date
  isIncreasing: boolean
} {
  const TRILLION = 1_000_000_000_000
  const milestone = milestoneSize * TRILLION
  const isIncreasing = debtPerSecond > 0

  // Find the next milestone based on direction
  let nextMilestone: number
  if (isIncreasing) {
    nextMilestone = Math.ceil(currentDebt / milestone) * milestone
  } else {
    nextMilestone = Math.floor(currentDebt / milestone) * milestone
  }

  // If we're exactly on a milestone, go to the next one
  if (nextMilestone === currentDebt) {
    nextMilestone = isIncreasing ? nextMilestone + milestone : nextMilestone - milestone
  }

  const debtDifference = isIncreasing
    ? nextMilestone - currentDebt
    : currentDebt - nextMilestone
  const secondsUntil = Math.abs(debtDifference / debtPerSecond)
  const estimatedDate = new Date(Date.now() + secondsUntil * 1000)

  return {
    milestone: nextMilestone,
    secondsUntil,
    estimatedDate,
    isIncreasing
  }
}

// Format time in days/hours/mins format (compact)
function formatDebtCountdown(seconds: number): string {
  const days = Math.floor(seconds / (24 * 60 * 60))
  const hours = Math.floor((seconds % (24 * 60 * 60)) / (60 * 60))
  const mins = Math.floor((seconds % (60 * 60)) / 60)

  if (days > 365) {
    const years = Math.floor(days / 365)
    const remainingDays = days % 365
    const months = Math.floor(remainingDays / 30)
    return `${years}y ${months}mo`
  } else if (days > 30) {
    const months = Math.floor(days / 30)
    const remainingDays = days % 30
    return `${months}mo ${remainingDays}d`
  } else if (days > 0) {
    return `${days}d ${hours}h`
  } else {
    return `${hours}h ${mins}m`
  }
}

// Format the countdown in extended format (years, months, days, hours, minutes, seconds)
function formatExtendedCountdown(diffMs: number): string {
  if (diffMs <= 0) return 'Halving imminent!'

  const totalDays = diffMs / (1000 * 60 * 60 * 24)
  const years = Math.floor(totalDays / 365.25)
  const remainingAfterYears = totalDays - (years * 365.25)
  const months = Math.floor(remainingAfterYears / 30.44)
  const remainingAfterMonths = remainingAfterYears - (months * 30.44)
  const days = Math.floor(remainingAfterMonths)

  const remainingMs = diffMs - (Math.floor(totalDays) * 24 * 60 * 60 * 1000)
  const hours = Math.floor(remainingMs / (1000 * 60 * 60))
  const mins = Math.floor((remainingMs % (1000 * 60 * 60)) / (1000 * 60))
  const secs = Math.floor((remainingMs % (1000 * 60)) / 1000)

  const parts: string[] = []
  if (years > 0) parts.push(`${years}y`)
  if (months > 0) parts.push(`${months}mo`)
  if (days > 0) parts.push(`${days}d`)
  parts.push(`${hours}h ${mins}m ${secs}s`)

  return parts.join(' ')
}

// Calculate halving countdown from current block height
function calculateHalvingCountdown(currentHeight: number): HalvingCountdown {
  const blocksRemaining = NEXT_HALVING_BLOCK - currentHeight
  const minutesRemaining = blocksRemaining * AVG_BLOCK_TIME_MINUTES
  const estimatedDate = new Date(Date.now() + minutesRemaining * 60 * 1000)

  const totalMinutes = minutesRemaining
  const days = Math.floor(totalMinutes / (24 * 60))
  const hours = Math.floor((totalMinutes % (24 * 60)) / 60)
  const minutes = Math.floor(totalMinutes % 60)

  const currentEpochStart = NEXT_HALVING_BLOCK - BLOCKS_PER_HALVING
  const blocksIntoEpoch = currentHeight - currentEpochStart
  const percentComplete = (blocksIntoEpoch / BLOCKS_PER_HALVING) * 100

  return {
    blocksRemaining,
    estimatedDate,
    daysRemaining: days,
    hoursRemaining: hours,
    minutesRemaining: minutes,
    percentComplete: Math.min(100, Math.max(0, percentComplete)),
  }
}

export function MarketSentimentCards() {
  // Track debt ceiling history modal
  const [showDebtCeilingModal, setShowDebtCeilingModal] = useState(false)

  // Fetch Fear & Greed Index (15 minute refresh)
  const { data: fearGreedData } = useQuery<FearGreedResponse>({
    queryKey: ['fear-greed'],
    queryFn: async () => {
      const response = await fetch('/api/news/fear-greed')
      if (!response.ok) throw new Error('Failed to fetch fear/greed index')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  // Fetch BTC block height for halving countdown
  const { data: blockHeight } = useQuery<BlockHeightResponse>({
    queryKey: ['btc-block-height'],
    queryFn: async () => {
      const response = await fetch('/api/news/btc-block-height')
      if (!response.ok) throw new Error('Failed to fetch block height')
      return response.json()
    },
    staleTime: 1000 * 60 * 10,
    refetchInterval: 1000 * 60 * 10,
    refetchOnWindowFocus: false,
  })

  // Fetch US National Debt
  const { data: usDebtData } = useQuery<USDebtResponse>({
    queryKey: ['us-debt'],
    queryFn: async () => {
      const response = await fetch('/api/news/us-debt')
      if (!response.ok) throw new Error('Failed to fetch US debt')
      return response.json()
    },
    staleTime: 1000 * 60 * 60 * 24,
    refetchInterval: 1000 * 60 * 60 * 24,
    refetchOnWindowFocus: false,
  })

  // Fetch Debt Ceiling History
  const { data: debtCeilingHistory } = useQuery<DebtCeilingHistoryResponse>({
    queryKey: ['debt-ceiling-history'],
    queryFn: async () => {
      const response = await fetch('/api/news/debt-ceiling-history')
      if (!response.ok) throw new Error('Failed to fetch debt ceiling history')
      return response.json()
    },
    staleTime: 1000 * 60 * 60 * 24 * 7,
    refetchOnWindowFocus: false,
  })

  // Calculate halving countdown
  const halvingCountdown = blockHeight ? calculateHalvingCountdown(blockHeight.height) : null

  // Toggle for extended countdown format (years/months)
  const [showExtendedCountdown, setShowExtendedCountdown] = useState(false)

  // Live countdown timer
  const [liveCountdown, setLiveCountdown] = useState<string>('')
  const targetTimeRef = useRef<number>(0)

  // Calculate target time once when block height changes
  useEffect(() => {
    if (!blockHeight?.height) return
    const blocksRemaining = NEXT_HALVING_BLOCK - blockHeight.height
    const minutesRemaining = blocksRemaining * AVG_BLOCK_TIME_MINUTES
    targetTimeRef.current = Date.now() + minutesRemaining * 60 * 1000
  }, [blockHeight?.height])

  // Update countdown display every second
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

  // Animated US debt counter
  const [liveDebt, setLiveDebt] = useState<number>(0)
  const debtStartTimeRef = useRef<number>(0)
  const debtBaseValueRef = useRef<number>(0)

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
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Fear & Greed Index */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <div className="flex items-center space-x-2 mb-4">
            <Gauge className="w-5 h-5 text-slate-400" />
            <h3 className="font-medium text-white">Fear & Greed Index</h3>
          </div>

          {fearGreedData ? (
            <div className="flex flex-col items-center">
              {/* Semicircular gauge */}
              <div className="relative w-48 h-24 mb-2">
                <svg viewBox="0 0 200 100" className="w-full h-full">
                  <defs>
                    <linearGradient id="fearGreedGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="#ef4444" />
                      <stop offset="25%" stopColor="#f97316" />
                      <stop offset="50%" stopColor="#eab308" />
                      <stop offset="75%" stopColor="#84cc16" />
                      <stop offset="100%" stopColor="#22c55e" />
                    </linearGradient>
                  </defs>
                  <path
                    d="M 20 95 A 80 80 0 0 1 180 95"
                    fill="none"
                    stroke="#334155"
                    strokeWidth="12"
                    strokeLinecap="round"
                  />
                  <path
                    d="M 20 95 A 80 80 0 0 1 180 95"
                    fill="none"
                    stroke="url(#fearGreedGradient)"
                    strokeWidth="12"
                    strokeLinecap="round"
                  />
                  <g transform={`rotate(${-90 + (fearGreedData.data.value / 100) * 180}, 100, 95)`}>
                    <line
                      x1="100"
                      y1="95"
                      x2="100"
                      y2="30"
                      stroke="white"
                      strokeWidth="3"
                      strokeLinecap="round"
                    />
                    <circle cx="100" cy="95" r="6" fill="white" />
                  </g>
                </svg>
              </div>

              <div className={`text-4xl font-bold ${getFearGreedColor(fearGreedData.data.value).text}`}>
                {fearGreedData.data.value}
              </div>
              <div
                className={`px-3 py-1 rounded-full text-sm font-medium mt-1 ${getFearGreedColor(fearGreedData.data.value).bg} ${getFearGreedColor(fearGreedData.data.value).text} border ${getFearGreedColor(fearGreedData.data.value).border}`}
              >
                {fearGreedData.data.value_classification}
              </div>

              <div className="flex justify-between w-full mt-3 text-xs text-slate-500">
                <span>Extreme Fear</span>
                <span>Neutral</span>
                <span>Extreme Greed</span>
              </div>

              <div className="mt-3 text-xs text-slate-600">
                Updates every 15 minutes
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-32">
              <LoadingSpinner size="sm" text="Loading..." />
            </div>
          )}
        </div>

        {/* BTC Halving Countdown */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-2">
              <Timer className="w-5 h-5 text-orange-400" />
              <h3 className="font-medium text-white">Next BTC Halving</h3>
            </div>
            <button
              onClick={() => setShowExtendedCountdown(!showExtendedCountdown)}
              className="flex items-center space-x-1 px-2 py-1 text-xs bg-slate-700/50 hover:bg-slate-700 rounded transition-colors"
              title={showExtendedCountdown ? 'Show short format (days)' : 'Show extended format (years/months)'}
            >
              {showExtendedCountdown ? (
                <ToggleRight className="w-4 h-4 text-orange-400" />
              ) : (
                <ToggleLeft className="w-4 h-4 text-slate-400" />
              )}
              <span className="text-slate-400">{showExtendedCountdown ? 'Y/M/D' : 'Days'}</span>
            </button>
          </div>

          {halvingCountdown && blockHeight ? (
            <div className="flex flex-col items-center">
              <div className="text-3xl font-mono font-bold text-orange-400 mb-2">
                {liveCountdown || 'Calculating...'}
              </div>

              <div className="text-sm text-slate-400 mb-4">
                {halvingCountdown.estimatedDate.toLocaleDateString('en-US', {
                  month: 'long',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </div>

              <div className="w-full mb-2">
                <div className="flex justify-between text-xs text-slate-500 mb-1">
                  <span>Epoch Progress</span>
                  <span>{halvingCountdown.percentComplete.toFixed(1)}%</span>
                </div>
                <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-orange-600 to-yellow-500 transition-all duration-500"
                    style={{ width: `${halvingCountdown.percentComplete}%` }}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 w-full mt-3 text-center">
                <div className="bg-slate-900/50 rounded-lg p-2">
                  <div className="text-xs text-slate-500">Current Block</div>
                  <div className="text-sm font-mono text-slate-300">
                    {blockHeight.height.toLocaleString()}
                  </div>
                </div>
                <div className="bg-slate-900/50 rounded-lg p-2">
                  <div className="text-xs text-slate-500">Blocks Remaining</div>
                  <div className="text-sm font-mono text-orange-400">
                    {halvingCountdown.blocksRemaining.toLocaleString()}
                  </div>
                </div>
              </div>

              <div className="mt-3 text-xs text-slate-600 text-center">
                Block reward will drop from 3.125 to 1.5625 BTC
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-32">
              <LoadingSpinner size="sm" text="Loading..." />
            </div>
          )}
        </div>

        {/* US National Debt */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <div className="flex items-center space-x-2 mb-4">
            <DollarSign className="w-5 h-5 text-green-400" />
            <h3 className="font-medium text-white">US National Debt</h3>
          </div>

          {usDebtData ? (
            <div className="flex flex-col items-center">
              <div className="flex items-center gap-2 mb-2">
                <div className="text-2xl font-mono font-bold text-red-400 tracking-tight">
                  ${formatDebt(liveDebt)}
                </div>
                <button
                  onClick={() => setShowDebtCeilingModal(true)}
                  className="w-5 h-5 rounded-full bg-slate-700 hover:bg-slate-600 flex items-center justify-center transition-colors"
                  title="View debt ceiling history"
                >
                  <Info className="w-3 h-3 text-slate-400" />
                </button>
              </div>

              <div className="text-xs text-slate-400 mb-3">
                {usDebtData.debt_per_second > 0 ? '+' : ''}
                ${formatDebt(usDebtData.debt_per_second)}/sec
              </div>

              <div className="w-full bg-slate-900/50 rounded-lg p-3 mb-3">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs text-slate-500">Debt-to-GDP Ratio</span>
                  <span className={`text-sm font-bold ${usDebtData.debt_to_gdp_ratio > 100 ? 'text-red-400' : 'text-yellow-400'}`}>
                    {usDebtData.debt_to_gdp_ratio.toFixed(1)}%
                  </span>
                </div>
                <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 ${
                      usDebtData.debt_to_gdp_ratio > 100
                        ? 'bg-gradient-to-r from-red-600 to-red-400'
                        : 'bg-gradient-to-r from-yellow-600 to-yellow-400'
                    }`}
                    style={{ width: `${Math.min(150, usDebtData.debt_to_gdp_ratio)}%` }}
                  />
                </div>
                <div className="flex justify-between text-[10px] text-slate-600 mt-1">
                  <span>0%</span>
                  <span>100%</span>
                  <span>150%</span>
                </div>
              </div>

              <div className="text-xs text-slate-500">
                GDP: ${(usDebtData.gdp / 1_000_000_000_000).toFixed(2)}T
              </div>

              {(() => {
                const m1T = calculateDebtMilestone(liveDebt, usDebtData.debt_per_second, 1)
                const m5T = calculateDebtMilestone(liveDebt, usDebtData.debt_per_second, 5)
                return (
                  <div className="w-full bg-slate-900/50 rounded-lg p-3 mt-3">
                    <div className="text-[10px] text-slate-500 mb-2 font-medium">Projected Milestones</div>
                    <div className="space-y-2">
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

              <div className="mt-2 text-[10px] text-slate-600">
                Source: Treasury Fiscal Data • FRED
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-32">
              <LoadingSpinner size="sm" text="Loading..." />
            </div>
          )}
        </div>
      </div>

      {/* Debt Ceiling History Modal */}
      {showDebtCeilingModal && (
        <div
          className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4"
          onClick={() => setShowDebtCeilingModal(false)}
        >
          <div
            className="bg-slate-800 rounded-lg w-full max-w-2xl max-h-[90vh] overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <div className="flex items-center space-x-2">
                <DollarSign className="w-5 h-5 text-green-400" />
                <div>
                  <h3 className="font-medium text-white">US Debt Ceiling History</h3>
                  {debtCeilingHistory && (
                    <p className="text-xs text-slate-500">
                      {debtCeilingHistory.total_events} events from 1939 to present
                    </p>
                  )}
                </div>
              </div>
              <button
                onClick={() => setShowDebtCeilingModal(false)}
                className="w-8 h-8 bg-slate-700 hover:bg-slate-600 rounded-full flex items-center justify-center transition-colors"
              >
                <X className="w-5 h-5 text-slate-400" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto max-h-[calc(90vh-140px)]">
              {debtCeilingHistory ? (
                <div className="space-y-3">
                  <p className="text-sm text-slate-400 mb-4">
                    Complete history of US debt ceiling changes since the first statutory limit was established in 1939.
                    The debt ceiling has been raised or suspended {debtCeilingHistory.total_events} times.
                  </p>
                  {debtCeilingHistory.events.map((event, idx) => (
                    <div
                      key={idx}
                      className="bg-slate-900/50 rounded-lg p-3 border border-slate-700"
                    >
                      <div className="flex justify-between items-start mb-2">
                        <span className="text-sm font-medium text-slate-300">
                          {new Date(event.date).toLocaleDateString('en-US', {
                            month: 'long',
                            day: 'numeric',
                            year: 'numeric'
                          })}
                        </span>
                        {event.suspended ? (
                          <span className="px-2 py-0.5 bg-yellow-500/20 text-yellow-400 text-xs rounded border border-yellow-500/30">
                            SUSPENDED
                          </span>
                        ) : (
                          <span className="text-lg font-mono font-bold text-green-400">
                            {event.amount_trillion && event.amount_trillion >= 1
                              ? `$${event.amount_trillion}T`
                              : `$${((event.amount_trillion || 0) * 1000).toFixed(0)}B`}
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-slate-400">{event.note}</p>
                      {event.legislation && (
                        <p className="text-xs text-slate-500 mt-1 italic">
                          {event.legislation}
                        </p>
                      )}
                      {event.suspended && event.suspension_end && (
                        <p className="text-xs text-yellow-500/70 mt-1">
                          Suspension ended: {new Date(event.suspension_end).toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric'
                          })}
                        </p>
                      )}
                      {event.political_context && (
                        <p className="text-xs text-slate-400 mt-2 border-t border-slate-700 pt-2">
                          {event.political_context}
                        </p>
                      )}
                      {event.source_url && (
                        <a
                          href={event.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 mt-2 transition-colors"
                        >
                          <ExternalLink className="w-3 h-3" />
                          View on Congress.gov
                        </a>
                      )}
                    </div>
                  ))}
                  <div className="text-xs text-slate-600 pt-2 border-t border-slate-700">
                    Last updated: {debtCeilingHistory.last_updated}
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center py-8">
                  <LoadingSpinner size="sm" text="Loading..." />
                </div>
              )}
            </div>

            <div className="p-4 border-t border-slate-700">
              <button
                onClick={() => setShowDebtCeilingModal(false)}
                className="w-full px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-slate-300 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
