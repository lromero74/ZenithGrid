/**
 * Market Sentiment Cards Carousel
 *
 * Displays market metrics in a rotating carousel:
 * - Fear & Greed Index
 * - BTC Halving Countdown
 * - US National Debt
 * - Bitcoin Dominance
 * - Altcoin Season Index
 * - Stablecoin Market Cap
 *
 * Shows 3 cards at a time, auto-cycles every 30 seconds with pause/manual controls.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Gauge, Timer, DollarSign, ToggleLeft, ToggleRight, Info, X, ExternalLink,
  ChevronLeft, ChevronRight, Pause, Play, TrendingUp, Coins, PieChart
} from 'lucide-react'
import { LoadingSpinner } from './LoadingSpinner'
import type {
  FearGreedResponse,
  BlockHeightResponse,
  USDebtResponse,
  DebtCeilingHistoryResponse,
  BTCDominanceResponse,
  AltseasonIndexResponse,
  StablecoinMcapResponse,
} from '../types'
import {
  NEXT_HALVING_BLOCK,
  AVG_BLOCK_TIME_MINUTES,
  getFearGreedColor,
  formatDebt,
  calculateDebtMilestone,
  formatDebtCountdown,
  formatExtendedCountdown,
  calculateHalvingCountdown,
} from '../utils/marketSentiment'

// Carousel configuration
const CARDS_VISIBLE = 3
const AUTO_CYCLE_INTERVAL = 30000 // 30 seconds

// Spring animation: anticipation -> follow-through -> overshoot -> settle
// Using CSS custom property for dynamic transform
const springKeyframes = `
@keyframes slideSpringLeft {
  0% { transform: translateX(var(--from-x)); }
  15% { transform: translateX(calc(var(--from-x) + 2%)); }
  50% { transform: translateX(calc(var(--to-x) - 1.5%)); }
  75% { transform: translateX(calc(var(--to-x) + 0.5%)); }
  100% { transform: translateX(var(--to-x)); }
}
@keyframes slideSpringRight {
  0% { transform: translateX(var(--from-x)); }
  15% { transform: translateX(calc(var(--from-x) - 2%)); }
  50% { transform: translateX(calc(var(--to-x) + 1.5%)); }
  75% { transform: translateX(calc(var(--to-x) - 0.5%)); }
  100% { transform: translateX(var(--to-x)); }
}
`

export function MarketSentimentCards() {
  // Carousel state
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isPaused, setIsPaused] = useState(false)
  const [isAnimating, setIsAnimating] = useState(false)
  const [slideDirection, setSlideDirection] = useState<'left' | 'right' | null>(null)
  const autoPlayRef = useRef<NodeJS.Timeout | null>(null)
  const carouselRef = useRef<HTMLDivElement>(null)

  // Track debt ceiling history modal
  const [showDebtCeilingModal, setShowDebtCeilingModal] = useState(false)

  // Fetch Fear & Greed Index
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

  // Fetch BTC Dominance
  const { data: btcDominanceData } = useQuery<BTCDominanceResponse>({
    queryKey: ['btc-dominance'],
    queryFn: async () => {
      const response = await fetch('/api/news/btc-dominance')
      if (!response.ok) throw new Error('Failed to fetch BTC dominance')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  // Fetch Altseason Index
  const { data: altseasonData } = useQuery<AltseasonIndexResponse>({
    queryKey: ['altseason-index'],
    queryFn: async () => {
      const response = await fetch('/api/news/altseason-index')
      if (!response.ok) throw new Error('Failed to fetch altseason index')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  // Fetch Stablecoin Market Cap
  const { data: stablecoinData } = useQuery<StablecoinMcapResponse>({
    queryKey: ['stablecoin-mcap'],
    queryFn: async () => {
      const response = await fetch('/api/news/stablecoin-mcap')
      if (!response.ok) throw new Error('Failed to fetch stablecoin mcap')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: 1000 * 60 * 15,
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

  // Define all cards (funding rates removed - requires API key)
  const allCards = [
    { id: 'fear-greed', component: <FearGreedCard data={fearGreedData} /> },
    { id: 'halving', component: <HalvingCard blockHeight={blockHeight} halvingCountdown={halvingCountdown} liveCountdown={liveCountdown} showExtendedCountdown={showExtendedCountdown} setShowExtendedCountdown={setShowExtendedCountdown} /> },
    { id: 'us-debt', component: <USDebtCard usDebtData={usDebtData} liveDebt={liveDebt} onShowHistory={() => setShowDebtCeilingModal(true)} /> },
    { id: 'btc-dominance', component: <BTCDominanceCard data={btcDominanceData} /> },
    { id: 'altseason', component: <AltseasonCard data={altseasonData} /> },
    { id: 'stablecoin-mcap', component: <StablecoinMcapCard data={stablecoinData} /> },
  ]

  const totalCards = allCards.length
  const maxIndex = totalCards - CARDS_VISIBLE

  // Inject keyframes into document (only once)
  useEffect(() => {
    const styleId = 'carousel-spring-keyframes'
    if (!document.getElementById(styleId)) {
      const style = document.createElement('style')
      style.id = styleId
      style.textContent = springKeyframes
      document.head.appendChild(style)
    }
  }, [])

  // Animation duration
  const ANIMATION_DURATION = 500 // ms

  // Auto-cycle logic with animation
  const nextSlide = useCallback(() => {
    if (isAnimating) return
    setSlideDirection('left')
    setIsAnimating(true)
    setTimeout(() => {
      setCurrentIndex(prev => (prev >= maxIndex ? 0 : prev + 1))
      setIsAnimating(false)
      setSlideDirection(null)
    }, ANIMATION_DURATION)
  }, [maxIndex, isAnimating])

  const prevSlide = useCallback(() => {
    if (isAnimating) return
    setSlideDirection('right')
    setIsAnimating(true)
    setTimeout(() => {
      setCurrentIndex(prev => (prev <= 0 ? maxIndex : prev - 1))
      setIsAnimating(false)
      setSlideDirection(null)
    }, ANIMATION_DURATION)
  }, [maxIndex, isAnimating])

  // Jump to specific index
  const goToIndex = useCallback((targetIndex: number) => {
    if (isAnimating || targetIndex === currentIndex) return
    const direction = targetIndex > currentIndex ? 'left' : 'right'
    setSlideDirection(direction)
    setIsAnimating(true)
    setTimeout(() => {
      setCurrentIndex(targetIndex)
      setIsAnimating(false)
      setSlideDirection(null)
    }, ANIMATION_DURATION)
  }, [currentIndex, isAnimating])

  // Auto-play effect
  useEffect(() => {
    if (isPaused) {
      if (autoPlayRef.current) {
        clearInterval(autoPlayRef.current)
        autoPlayRef.current = null
      }
      return
    }

    autoPlayRef.current = setInterval(nextSlide, AUTO_CYCLE_INTERVAL)
    return () => {
      if (autoPlayRef.current) {
        clearInterval(autoPlayRef.current)
      }
    }
  }, [isPaused, nextSlide])

  // Calculate card width percentage (each card is 1/3 of visible area)
  const cardWidthPercent = 100 / CARDS_VISIBLE
  // Calculate the transform for the current position
  const baseTransform = -(currentIndex * cardWidthPercent)

  // Get animation style
  const getAnimationStyle = (): React.CSSProperties => {
    if (!isAnimating || !slideDirection) {
      return { transform: `translateX(${baseTransform}%)` }
    }

    const fromX = `${baseTransform}%`
    const toX = slideDirection === 'left'
      ? `${baseTransform - cardWidthPercent}%`
      : `${baseTransform + cardWidthPercent}%`

    return {
      '--from-x': fromX,
      '--to-x': toX,
      animation: `slideSpring${slideDirection === 'left' ? 'Left' : 'Right'} ${ANIMATION_DURATION}ms cubic-bezier(0.34, 1.56, 0.64, 1) forwards`,
    } as React.CSSProperties
  }

  return (
    <>
      <div className="relative">
        {/* Carousel Controls */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <button
              onClick={prevSlide}
              disabled={isAnimating}
              className="p-1.5 rounded-full bg-slate-700 hover:bg-slate-600 text-slate-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Previous"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={nextSlide}
              disabled={isAnimating}
              className="p-1.5 rounded-full bg-slate-700 hover:bg-slate-600 text-slate-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Next"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
            <button
              onClick={() => setIsPaused(!isPaused)}
              className={`p-1.5 rounded-full transition-colors ${isPaused ? 'bg-green-600 hover:bg-green-500 text-white' : 'bg-slate-700 hover:bg-slate-600 text-slate-300'}`}
              title={isPaused ? 'Resume auto-cycle' : 'Pause auto-cycle'}
            >
              {isPaused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
            </button>
          </div>
          <div className="flex items-center gap-1">
            {Array.from({ length: maxIndex + 1 }).map((_, idx) => (
              <button
                key={idx}
                onClick={() => goToIndex(idx)}
                disabled={isAnimating}
                className={`w-2 h-2 rounded-full transition-colors disabled:cursor-not-allowed ${
                  currentIndex === idx ? 'bg-blue-500' : 'bg-slate-600 hover:bg-slate-500'
                }`}
              />
            ))}
          </div>
        </div>

        {/* Cards Carousel - overflow hidden container */}
        <div className="overflow-hidden">
          {/* Sliding track containing all cards */}
          <div
            ref={carouselRef}
            className="flex gap-4"
            style={{
              width: `${(totalCards / CARDS_VISIBLE) * 100}%`,
              ...getAnimationStyle(),
            }}
          >
            {allCards.map(card => (
              <div
                key={card.id}
                className="flex-shrink-0"
                style={{ width: `calc(${100 / totalCards}% - ${(totalCards - 1) * 16 / totalCards}px)` }}
              >
                {card.component}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Debt Ceiling History Modal */}
      {showDebtCeilingModal && (
        <DebtCeilingModal
          debtCeilingHistory={debtCeilingHistory}
          onClose={() => setShowDebtCeilingModal(false)}
        />
      )}
    </>
  )
}

// ============================================================================
// Individual Card Components
// ============================================================================

function FearGreedCard({ data }: { data: FearGreedResponse | undefined }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <Gauge className="w-5 h-5 text-slate-400" />
        <h3 className="font-medium text-white">Fear & Greed Index</h3>
      </div>

      {data ? (
        <div className="flex flex-col items-center">
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
              <path d="M 20 95 A 80 80 0 0 1 180 95" fill="none" stroke="#334155" strokeWidth="12" strokeLinecap="round" />
              <path d="M 20 95 A 80 80 0 0 1 180 95" fill="none" stroke="url(#fearGreedGradient)" strokeWidth="12" strokeLinecap="round" />
              <g transform={`rotate(${-90 + (data.data.value / 100) * 180}, 100, 95)`}>
                <line x1="100" y1="95" x2="100" y2="30" stroke="white" strokeWidth="3" strokeLinecap="round" />
                <circle cx="100" cy="95" r="6" fill="white" />
              </g>
            </svg>
          </div>
          <div className={`text-4xl font-bold ${getFearGreedColor(data.data.value).text}`}>{data.data.value}</div>
          <div className={`px-3 py-1 rounded-full text-sm font-medium mt-1 ${getFearGreedColor(data.data.value).bg} ${getFearGreedColor(data.data.value).text} border ${getFearGreedColor(data.data.value).border}`}>
            {data.data.value_classification}
          </div>
          <div className="flex justify-between w-full mt-3 text-xs text-slate-500">
            <span>Extreme Fear</span>
            <span>Neutral</span>
            <span>Extreme Greed</span>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-center h-32">
          <LoadingSpinner size="sm" text="Loading..." />
        </div>
      )}
    </div>
  )
}

function HalvingCard({
  blockHeight,
  halvingCountdown,
  liveCountdown,
  showExtendedCountdown,
  setShowExtendedCountdown
}: {
  blockHeight: BlockHeightResponse | undefined
  halvingCountdown: ReturnType<typeof calculateHalvingCountdown> | null
  liveCountdown: string
  showExtendedCountdown: boolean
  setShowExtendedCountdown: (v: boolean) => void
}) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <Timer className="w-5 h-5 text-orange-400" />
          <h3 className="font-medium text-white">Next BTC Halving</h3>
        </div>
        <button
          onClick={() => setShowExtendedCountdown(!showExtendedCountdown)}
          className="flex items-center space-x-1 px-2 py-1 text-xs bg-slate-700/50 hover:bg-slate-700 rounded transition-colors"
        >
          {showExtendedCountdown ? <ToggleRight className="w-4 h-4 text-orange-400" /> : <ToggleLeft className="w-4 h-4 text-slate-400" />}
          <span className="text-slate-400">{showExtendedCountdown ? 'Y/M/D' : 'Days'}</span>
        </button>
      </div>

      {halvingCountdown && blockHeight ? (
        <div className="flex flex-col items-center">
          <div className="text-3xl font-mono font-bold text-orange-400 mb-2">{liveCountdown || 'Calculating...'}</div>
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
      ) : (
        <div className="flex items-center justify-center h-32">
          <LoadingSpinner size="sm" text="Loading..." />
        </div>
      )}
    </div>
  )
}

function USDebtCard({
  usDebtData,
  liveDebt,
  onShowHistory
}: {
  usDebtData: USDebtResponse | undefined
  liveDebt: number
  onShowHistory: () => void
}) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <DollarSign className="w-5 h-5 text-green-400" />
        <h3 className="font-medium text-white">US National Debt</h3>
      </div>

      {usDebtData ? (
        <div className="flex flex-col items-center">
          <div className="flex items-center gap-2 mb-2">
            <div className="text-2xl font-mono font-bold text-red-400 tracking-tight">${formatDebt(liveDebt)}</div>
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
            {!usDebtData.debt_ceiling_suspended && usDebtData.headroom !== null && (
              <div className="flex justify-between items-center mt-1">
                <span className="text-[10px] text-slate-600">Headroom</span>
                <span className={`text-[10px] font-mono ${usDebtData.headroom > 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {usDebtData.headroom > 0 ? '+' : ''}${(usDebtData.headroom / 1_000_000_000_000).toFixed(3)}T
                </span>
              </div>
            )}
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
        </div>
      ) : (
        <div className="flex items-center justify-center h-32">
          <LoadingSpinner size="sm" text="Loading..." />
        </div>
      )}
    </div>
  )
}

function BTCDominanceCard({ data }: { data: BTCDominanceResponse | undefined }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <PieChart className="w-5 h-5 text-orange-500" />
        <h3 className="font-medium text-white">BTC Dominance</h3>
      </div>

      {data ? (
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

          <div className="text-[10px] text-slate-600 mt-3">
            Total MCap: ${(data.total_market_cap / 1_000_000_000_000).toFixed(2)}T
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-center h-32">
          <LoadingSpinner size="sm" text="Loading..." />
        </div>
      )}
    </div>
  )
}

function AltseasonCard({ data }: { data: AltseasonIndexResponse | undefined }) {
  const getSeasonColor = (season: string) => {
    if (season === 'Altcoin Season') return { text: 'text-purple-400', bg: 'bg-purple-500/20', border: 'border-purple-500/30' }
    if (season === 'Bitcoin Season') return { text: 'text-orange-400', bg: 'bg-orange-500/20', border: 'border-orange-500/30' }
    return { text: 'text-slate-400', bg: 'bg-slate-500/20', border: 'border-slate-500/30' }
  }

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <TrendingUp className="w-5 h-5 text-purple-400" />
        <h3 className="font-medium text-white">Altcoin Season Index</h3>
      </div>

      {data ? (
        <div className="flex flex-col items-center">
          <div className={`text-4xl font-bold mb-2 ${data.season === 'Altcoin Season' ? 'text-purple-400' : data.season === 'Bitcoin Season' ? 'text-orange-400' : 'text-slate-300'}`}>
            {data.altseason_index}
          </div>
          <div className={`px-3 py-1 rounded-full text-sm font-medium ${getSeasonColor(data.season).bg} ${getSeasonColor(data.season).text} border ${getSeasonColor(data.season).border}`}>
            {data.season}
          </div>

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

          <div className="text-xs text-slate-500 mt-3">
            {data.outperformers}/{data.total_altcoins} alts beat BTC (30d)
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-center h-32">
          <LoadingSpinner size="sm" text="Loading..." />
        </div>
      )}
    </div>
  )
}

function StablecoinMcapCard({ data }: { data: StablecoinMcapResponse | undefined }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <Coins className="w-5 h-5 text-green-500" />
        <h3 className="font-medium text-white">Stablecoin Supply</h3>
      </div>

      {data ? (
        <div className="flex flex-col items-center">
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

          <div className="text-[10px] text-slate-600 mt-3 text-center">
            High supply = capital ready to deploy
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-center h-32">
          <LoadingSpinner size="sm" text="Loading..." />
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Debt Ceiling History Modal
// ============================================================================

function DebtCeilingModal({
  debtCeilingHistory,
  onClose
}: {
  debtCeilingHistory: DebtCeilingHistoryResponse | undefined
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-slate-800 rounded-lg w-full max-w-2xl max-h-[90vh] overflow-hidden shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div className="flex items-center space-x-2">
            <DollarSign className="w-5 h-5 text-green-400" />
            <div>
              <h3 className="font-medium text-white">US Debt Ceiling History</h3>
              {debtCeilingHistory && (
                <p className="text-xs text-slate-500">{debtCeilingHistory.total_events} events from 1939 to present</p>
              )}
            </div>
          </div>
          <button onClick={onClose} className="w-8 h-8 bg-slate-700 hover:bg-slate-600 rounded-full flex items-center justify-center transition-colors">
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>

        <div className="p-4 overflow-y-auto max-h-[calc(90vh-140px)]">
          {debtCeilingHistory ? (
            <div className="space-y-3">
              <p className="text-sm text-slate-400 mb-4">
                Complete history of US debt ceiling changes since the first statutory limit was established in 1939.
              </p>
              {debtCeilingHistory.events.map((event, idx) => (
                <div key={idx} className="bg-slate-900/50 rounded-lg p-3 border border-slate-700">
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-sm font-medium text-slate-300">
                      {new Date(event.date).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
                    </span>
                    {event.suspended ? (
                      <span className="px-2 py-0.5 bg-yellow-500/20 text-yellow-400 text-xs rounded border border-yellow-500/30">SUSPENDED</span>
                    ) : (
                      <span className="text-lg font-mono font-bold text-green-400">
                        {event.amount_trillion && event.amount_trillion >= 1 ? `$${event.amount_trillion}T` : `$${((event.amount_trillion || 0) * 1000).toFixed(0)}B`}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-slate-400">{event.note}</p>
                  {event.legislation && <p className="text-xs text-slate-500 mt-1 italic">{event.legislation}</p>}
                  {event.suspended && event.suspension_end && (
                    <p className="text-xs text-yellow-500/70 mt-1">
                      Suspension ended: {new Date(event.suspension_end).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                    </p>
                  )}
                  {event.political_context && (
                    <p className="text-xs text-slate-400 mt-2 border-t border-slate-700 pt-2">{event.political_context}</p>
                  )}
                  {event.source_url && (
                    <a href={event.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 mt-2 transition-colors">
                      <ExternalLink className="w-3 h-3" />
                      View on Congress.gov
                    </a>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center justify-center py-8">
              <LoadingSpinner size="sm" text="Loading..." />
            </div>
          )}
        </div>

        <div className="p-4 border-t border-slate-700">
          <button onClick={onClose} className="w-full px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-slate-300 transition-colors">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
