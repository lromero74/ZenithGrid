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
  ChevronLeft, ChevronRight, Pause, Play, TrendingUp, Coins, PieChart,
  Cpu, Zap, Activity, TrendingDown, Database, Globe, Sun, Snowflake, Leaf, Sprout
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
  TotalMarketCapResponse,
  BTCSupplyResponse,
  MempoolResponse,
  HashRateResponse,
  LightningResponse,
  ATHResponse,
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

// Info tooltip component for explaining each metric
// Positioned below the icon to avoid carousel overflow clipping
function InfoTooltip({ text }: { text: string }) {
  return (
    <div className="group relative ml-auto">
      <Info className="w-4 h-4 text-slate-500 hover:text-slate-300 cursor-help transition-colors" />
      <div className="absolute top-full right-0 mt-2 w-48 p-2 bg-slate-900 border border-slate-600 rounded-lg shadow-xl text-xs text-slate-300 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-50">
        <div className="absolute top-0 right-2 transform -translate-y-1/2 rotate-45 w-2 h-2 bg-slate-900 border-l border-t border-slate-600" />
        {text}
      </div>
    </div>
  )
}

// ============================================================================
// Market Season Detection
// ============================================================================

type MarketSeason = 'accumulation' | 'bull' | 'distribution' | 'bear'

interface SeasonInfo {
  season: MarketSeason
  name: string
  description: string
  progress: number // 0-100, how far into this season
  confidence: number // 0-100, how confident we are in this classification
  icon: typeof Sprout
  color: string
  bgGradient: string
  signals: string[]
}

/**
 * Determine the current market season based on multiple indicators.
 * Uses a weighted scoring system to classify into one of four phases:
 * - Accumulation (Spring): Bottom forming, smart money buying
 * - Bull (Summer): Prices rising, optimism growing
 * - Distribution (Autumn): Peak euphoria, smart money selling
 * - Bear (Winter): Prices falling, capitulation
 */
function determineMarketSeason(
  fearGreed: number | undefined,
  athData: ATHResponse | undefined,
  altseason: AltseasonIndexResponse | undefined,
  btcDominance: BTCDominanceResponse | undefined
): SeasonInfo {
  const signals: string[] = []

  // Default values if data not available
  const fg = fearGreed ?? 50
  const drawdown = athData?.drawdown_pct ?? 0
  const daysSinceATH = athData?.days_since_ath ?? 0
  const recovery = athData?.recovery_pct ?? 100
  const altseasonIdx = altseason?.altseason_index ?? 50
  const btcDom = btcDominance?.btc_dominance ?? 50

  // Score each season (0-100)
  let accumulationScore = 0
  let bullScore = 0
  let distributionScore = 0
  let bearScore = 0

  // Fear & Greed signals
  if (fg <= 20) {
    accumulationScore += 30
    signals.push('Extreme fear (buying opportunity)')
  } else if (fg <= 35) {
    accumulationScore += 20
    bearScore += 10
    signals.push('Fear in market')
  } else if (fg >= 80) {
    distributionScore += 30
    signals.push('Extreme greed (caution)')
  } else if (fg >= 65) {
    distributionScore += 15
    bullScore += 15
    signals.push('Greed rising')
  } else if (fg >= 45 && fg <= 55) {
    // Neutral - could be transitioning
    bullScore += 10
    bearScore += 10
  } else if (fg > 55) {
    bullScore += 20
    signals.push('Optimism building')
  } else {
    bearScore += 15
  }

  // ATH/Drawdown signals
  if (drawdown <= 5) {
    distributionScore += 25
    signals.push('At/near all-time high')
  } else if (drawdown <= 15) {
    bullScore += 25
    distributionScore += 10
    signals.push('Close to ATH')
  } else if (drawdown >= 60) {
    accumulationScore += 30
    signals.push('Deep drawdown (accumulation zone)')
  } else if (drawdown >= 40) {
    accumulationScore += 15
    bearScore += 15
    signals.push('Significant drawdown')
  } else if (drawdown >= 20) {
    bearScore += 20
    signals.push('Correction territory')
  } else {
    bullScore += 15
  }

  // Days since ATH signals
  if (daysSinceATH <= 30 && drawdown <= 10) {
    distributionScore += 20
    signals.push('Recent ATH')
  } else if (daysSinceATH >= 365) {
    accumulationScore += 20
    signals.push('Extended time below ATH')
  } else if (daysSinceATH >= 180) {
    accumulationScore += 10
    bearScore += 10
  }

  // Recovery signals
  if (recovery >= 90) {
    bullScore += 15
    distributionScore += 10
  } else if (recovery >= 70) {
    bullScore += 20
    signals.push('Strong recovery underway')
  } else if (recovery <= 30) {
    bearScore += 15
    accumulationScore += 10
  }

  // Altseason signals (risk appetite)
  if (altseasonIdx >= 75) {
    distributionScore += 15
    bullScore += 10
    signals.push('Alt season (late cycle)')
  } else if (altseasonIdx <= 25) {
    accumulationScore += 10
    bearScore += 10
    signals.push('BTC dominance (early/late cycle)')
  }

  // BTC Dominance signals
  if (btcDom >= 60) {
    accumulationScore += 10
    bearScore += 5
    signals.push('High BTC dominance')
  } else if (btcDom <= 40) {
    distributionScore += 10
    signals.push('Low BTC dominance (risk-on)')
  }

  // Determine winning season
  const scores = {
    accumulation: accumulationScore,
    bull: bullScore,
    distribution: distributionScore,
    bear: bearScore
  }

  const maxScore = Math.max(...Object.values(scores))
  const totalScore = Object.values(scores).reduce((a, b) => a + b, 0)

  let season: MarketSeason = 'bull'
  if (accumulationScore === maxScore) season = 'accumulation'
  else if (bullScore === maxScore) season = 'bull'
  else if (distributionScore === maxScore) season = 'distribution'
  else if (bearScore === maxScore) season = 'bear'

  // Calculate confidence (how dominant is the winning score)
  const confidence = totalScore > 0 ? Math.round((maxScore / totalScore) * 100) : 50

  // Calculate progress within the season (simplified heuristic)
  let progress = 50
  if (season === 'accumulation') {
    // Progress based on fear level (lower fear = later in accumulation)
    progress = Math.max(0, Math.min(100, 100 - fg))
  } else if (season === 'bull') {
    // Progress based on recovery to ATH
    progress = Math.max(0, Math.min(100, recovery))
  } else if (season === 'distribution') {
    // Progress based on greed level
    progress = Math.max(0, Math.min(100, fg))
  } else if (season === 'bear') {
    // Progress based on drawdown depth
    progress = Math.max(0, Math.min(100, drawdown * 1.5))
  }

  const seasonInfo: Record<MarketSeason, Omit<SeasonInfo, 'progress' | 'confidence' | 'signals'>> = {
    accumulation: {
      season: 'accumulation',
      name: 'Accumulation',
      description: 'Smart money quietly buying. Fear dominates headlines.',
      icon: Sprout,
      color: 'text-emerald-400',
      bgGradient: 'from-emerald-900/30 to-green-900/20'
    },
    bull: {
      season: 'bull',
      name: 'Bull Market',
      description: 'Prices rising, optimism growing. Momentum building.',
      icon: Sun,
      color: 'text-amber-400',
      bgGradient: 'from-amber-900/30 to-orange-900/20'
    },
    distribution: {
      season: 'distribution',
      name: 'Distribution',
      description: 'Peak euphoria. Smart money taking profits.',
      icon: Leaf,
      color: 'text-orange-400',
      bgGradient: 'from-orange-900/30 to-red-900/20'
    },
    bear: {
      season: 'bear',
      name: 'Bear Market',
      description: 'Prices falling, fear spreading. Patience required.',
      icon: Snowflake,
      color: 'text-blue-400',
      bgGradient: 'from-blue-900/30 to-slate-900/20'
    }
  }

  return {
    ...seasonInfo[season],
    progress,
    confidence,
    signals: signals.slice(0, 3) // Top 3 signals
  }
}

// Export season for header background (will be used by parent component)
export { determineMarketSeason }
export type { MarketSeason, SeasonInfo }

// Carousel configuration
const CARDS_VISIBLE = 3
const AUTO_CYCLE_INTERVAL = 30000 // 30 seconds
const ANIMATION_DURATION = 625 // ms (25% slower for smoother feel)
const SWIPE_THRESHOLD = 50 // px minimum swipe distance

// Spring animations with CSS custom properties
// Button/auto: anticipation -> follow-through -> overshoot -> settle
// Swipe: follow-through -> overshoot -> settle (no anticipation)
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
@keyframes slideSwipeLeft {
  0% { transform: translateX(var(--from-x)); }
  60% { transform: translateX(calc(var(--to-x) - 1.5%)); }
  80% { transform: translateX(calc(var(--to-x) + 0.5%)); }
  100% { transform: translateX(var(--to-x)); }
}
@keyframes slideSwipeRight {
  0% { transform: translateX(var(--from-x)); }
  60% { transform: translateX(calc(var(--to-x) + 1.5%)); }
  80% { transform: translateX(calc(var(--to-x) - 0.5%)); }
  100% { transform: translateX(var(--to-x)); }
}
`

export function MarketSentimentCards() {
  // Carousel state - for infinite scroll, we track position in extended array
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isPaused, setIsPaused] = useState(false)
  const [isAnimating, setIsAnimating] = useState(false)
  const [animationType, setAnimationType] = useState<'button' | 'swipe'>('button')
  const [slideDirection, setSlideDirection] = useState<'left' | 'right' | null>(null)
  const autoPlayRef = useRef<NodeJS.Timeout | null>(null)
  const carouselRef = useRef<HTMLDivElement>(null)

  // Swipe tracking
  const touchStartX = useRef<number>(0)
  const touchStartY = useRef<number>(0)
  const isDragging = useRef<boolean>(false)

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

  // Fetch Total Market Cap
  const { data: totalMarketCapData } = useQuery<TotalMarketCapResponse>({
    queryKey: ['total-market-cap'],
    queryFn: async () => {
      const response = await fetch('/api/news/total-market-cap')
      if (!response.ok) throw new Error('Failed to fetch total market cap')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  // Fetch BTC Supply
  const { data: btcSupplyData } = useQuery<BTCSupplyResponse>({
    queryKey: ['btc-supply'],
    queryFn: async () => {
      const response = await fetch('/api/news/btc-supply')
      if (!response.ok) throw new Error('Failed to fetch BTC supply')
      return response.json()
    },
    staleTime: 1000 * 60 * 10,
    refetchInterval: 1000 * 60 * 10,
    refetchOnWindowFocus: false,
  })

  // Fetch Mempool Stats
  const { data: mempoolData } = useQuery<MempoolResponse>({
    queryKey: ['mempool'],
    queryFn: async () => {
      const response = await fetch('/api/news/mempool')
      if (!response.ok) throw new Error('Failed to fetch mempool')
      return response.json()
    },
    staleTime: 1000 * 60 * 5,
    refetchInterval: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
  })

  // Fetch Hash Rate
  const { data: hashRateData } = useQuery<HashRateResponse>({
    queryKey: ['hash-rate'],
    queryFn: async () => {
      const response = await fetch('/api/news/hash-rate')
      if (!response.ok) throw new Error('Failed to fetch hash rate')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  // Fetch Lightning Stats
  const { data: lightningData } = useQuery<LightningResponse>({
    queryKey: ['lightning'],
    queryFn: async () => {
      const response = await fetch('/api/news/lightning')
      if (!response.ok) throw new Error('Failed to fetch lightning stats')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  // Fetch ATH Data
  const { data: athData } = useQuery<ATHResponse>({
    queryKey: ['ath'],
    queryFn: async () => {
      const response = await fetch('/api/news/ath')
      if (!response.ok) throw new Error('Failed to fetch ATH data')
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

  // Calculate market season based on available metrics
  const seasonInfo = fearGreedData || athData || altseasonData || btcDominanceData
    ? determineMarketSeason(
        fearGreedData?.data?.value,
        athData,
        altseasonData,
        btcDominanceData
      )
    : null

  // Define all cards (funding rates removed - requires API key)
  const baseCards = [
    { id: 'season', component: <SeasonCard seasonInfo={seasonInfo} /> },
    { id: 'fear-greed', component: <FearGreedCard data={fearGreedData} /> },
    { id: 'halving', component: <HalvingCard blockHeight={blockHeight} halvingCountdown={halvingCountdown} liveCountdown={liveCountdown} showExtendedCountdown={showExtendedCountdown} setShowExtendedCountdown={setShowExtendedCountdown} /> },
    { id: 'us-debt', component: <USDebtCard usDebtData={usDebtData} liveDebt={liveDebt} onShowHistory={() => setShowDebtCeilingModal(true)} /> },
    { id: 'btc-dominance', component: <BTCDominanceCard data={btcDominanceData} /> },
    { id: 'altseason', component: <AltseasonCard data={altseasonData} /> },
    { id: 'stablecoin-mcap', component: <StablecoinMcapCard data={stablecoinData} /> },
    { id: 'total-mcap', component: <TotalMarketCapCard data={totalMarketCapData} /> },
    { id: 'btc-supply', component: <BTCSupplyCard data={btcSupplyData} /> },
    { id: 'mempool', component: <MempoolCard data={mempoolData} /> },
    { id: 'hash-rate', component: <HashRateCard data={hashRateData} /> },
    { id: 'lightning', component: <LightningCard data={lightningData} /> },
    { id: 'ath', component: <ATHCard data={athData} /> },
  ]

  const totalCards = baseCards.length

  // For infinite scroll: create extended array with clones at both ends
  // [clone of last 3] + [all cards] + [clone of first 3]
  const extendedCards = [
    ...baseCards.slice(-CARDS_VISIBLE).map((card, i) => ({ ...card, id: `clone-end-${i}` })),
    ...baseCards,
    ...baseCards.slice(0, CARDS_VISIBLE).map((card, i) => ({ ...card, id: `clone-start-${i}` })),
  ]
  const extendedTotal = extendedCards.length

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

  // Slide functions for infinite carousel
  const nextSlide = useCallback((isSwipe = false) => {
    if (isAnimating) return
    setAnimationType(isSwipe ? 'swipe' : 'button')
    setSlideDirection('left')
    setIsAnimating(true)
    setTimeout(() => {
      setCurrentIndex(prev => prev + 1)
      setIsAnimating(false)
      setSlideDirection(null)
    }, ANIMATION_DURATION)
  }, [isAnimating])

  const prevSlide = useCallback((isSwipe = false) => {
    if (isAnimating) return
    setAnimationType(isSwipe ? 'swipe' : 'button')
    setSlideDirection('right')
    setIsAnimating(true)
    setTimeout(() => {
      setCurrentIndex(prev => prev - 1)
      setIsAnimating(false)
      setSlideDirection(null)
    }, ANIMATION_DURATION)
  }, [isAnimating])

  // Jump to specific logical index (0 to totalCards-1)
  const goToIndex = useCallback((targetLogicalIndex: number) => {
    const currentLogicalIndex = ((currentIndex % totalCards) + totalCards) % totalCards
    if (isAnimating || targetLogicalIndex === currentLogicalIndex) return

    // Calculate shortest path direction
    let diff = targetLogicalIndex - currentLogicalIndex
    if (Math.abs(diff) > totalCards / 2) {
      diff = diff > 0 ? diff - totalCards : diff + totalCards
    }

    setAnimationType('button')
    setSlideDirection(diff > 0 ? 'left' : 'right')
    setIsAnimating(true)
    setTimeout(() => {
      setCurrentIndex(targetLogicalIndex)
      setIsAnimating(false)
      setSlideDirection(null)
    }, ANIMATION_DURATION)
  }, [currentIndex, totalCards, isAnimating])

  // Normalize index after animation (for infinite loop)
  useEffect(() => {
    if (isAnimating) return

    // If we've scrolled into the clone zones, instantly jump to the real position
    if (currentIndex < 0) {
      setCurrentIndex(totalCards + currentIndex)
    } else if (currentIndex >= totalCards) {
      setCurrentIndex(currentIndex % totalCards)
    }
  }, [currentIndex, isAnimating, totalCards])

  // Reset auto-play timer (called on manual interaction)
  const resetAutoPlay = useCallback(() => {
    if (autoPlayRef.current) {
      clearInterval(autoPlayRef.current)
    }
    if (!isPaused) {
      autoPlayRef.current = setInterval(() => nextSlide(false), AUTO_CYCLE_INTERVAL)
    }
  }, [isPaused, nextSlide])

  // Auto-play effect
  useEffect(() => {
    if (isPaused) {
      if (autoPlayRef.current) {
        clearInterval(autoPlayRef.current)
        autoPlayRef.current = null
      }
      return
    }

    autoPlayRef.current = setInterval(() => nextSlide(false), AUTO_CYCLE_INTERVAL)
    return () => {
      if (autoPlayRef.current) {
        clearInterval(autoPlayRef.current)
      }
    }
  }, [isPaused, nextSlide])

  // Swipe handlers
  const handleTouchStart = useCallback((e: React.TouchEvent | React.MouseEvent) => {
    if (isAnimating) return
    const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX
    const clientY = 'touches' in e ? e.touches[0].clientY : e.clientY
    touchStartX.current = clientX
    touchStartY.current = clientY
    isDragging.current = true
  }, [isAnimating])

  const handleTouchEnd = useCallback((e: React.TouchEvent | React.MouseEvent) => {
    if (!isDragging.current) return
    isDragging.current = false

    const clientX = 'changedTouches' in e ? e.changedTouches[0].clientX : e.clientX
    const clientY = 'changedTouches' in e ? e.changedTouches[0].clientY : e.clientY
    const diffX = touchStartX.current - clientX
    const diffY = touchStartY.current - clientY

    // Only trigger if horizontal swipe is dominant and exceeds threshold
    if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > SWIPE_THRESHOLD) {
      if (diffX > 0) {
        nextSlide(true) // Swipe left = next
      } else {
        prevSlide(true) // Swipe right = prev
      }
      resetAutoPlay() // Reset timer on manual swipe
    }
  }, [nextSlide, prevSlide, resetAutoPlay])

  // Calculate card width as percentage of the TRACK (not viewport)
  // Track contains extendedTotal cards, so each card is 100/extendedTotal % of track
  const cardWidthInTrack = 100 / extendedTotal

  // Calculate the transform for the current position
  // Account for the prepended clones (offset by CARDS_VISIBLE)
  // currentIndex 0 should show real cards starting at position CARDS_VISIBLE in extended array
  const getTransformPercent = (index: number) => {
    return -((index + CARDS_VISIBLE) * cardWidthInTrack)
  }
  const baseTransform = getTransformPercent(currentIndex)

  // Get animation style
  const getAnimationStyle = (): React.CSSProperties => {
    if (!isAnimating || !slideDirection) {
      return { transform: `translateX(${baseTransform}%)` }
    }

    const fromX = `${baseTransform}%`
    const toX = slideDirection === 'left'
      ? `${baseTransform - cardWidthInTrack}%`
      : `${baseTransform + cardWidthInTrack}%`

    // Use different animation for swipe vs button
    const animName = animationType === 'swipe'
      ? `slideSwipe${slideDirection === 'left' ? 'Left' : 'Right'}`
      : `slideSpring${slideDirection === 'left' ? 'Left' : 'Right'}`

    return {
      '--from-x': fromX,
      '--to-x': toX,
      animation: `${animName} ${ANIMATION_DURATION}ms cubic-bezier(0.34, 1.56, 0.64, 1) forwards`,
    } as React.CSSProperties
  }

  // Current logical index for dot indicators (0 to totalCards-1)
  const logicalIndex = ((currentIndex % totalCards) + totalCards) % totalCards

  return (
    <>
      <div className="relative">
        {/* Carousel Controls */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <button
              onClick={() => { prevSlide(); resetAutoPlay() }}
              disabled={isAnimating}
              className="p-1.5 rounded-full bg-slate-700 hover:bg-slate-600 text-slate-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Previous"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => { nextSlide(); resetAutoPlay() }}
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
            {Array.from({ length: totalCards }).map((_, idx) => (
              <button
                key={idx}
                onClick={() => { goToIndex(idx); resetAutoPlay() }}
                disabled={isAnimating}
                className={`w-2 h-2 rounded-full transition-colors disabled:cursor-not-allowed ${
                  logicalIndex === idx ? 'bg-blue-500' : 'bg-slate-600 hover:bg-slate-500'
                }`}
              />
            ))}
          </div>
        </div>

        {/* Cards Carousel - overflow hidden container with touch/mouse support */}
        <div
          className="overflow-hidden cursor-grab active:cursor-grabbing select-none"
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
          onMouseDown={handleTouchStart}
          onMouseUp={handleTouchEnd}
          onMouseLeave={() => { isDragging.current = false }}
        >
          {/* Sliding track containing extended cards (clones + originals + clones) */}
          <div
            ref={carouselRef}
            className="flex gap-4"
            style={{
              width: `${(extendedTotal / CARDS_VISIBLE) * 100}%`,
              ...getAnimationStyle(),
            }}
          >
            {extendedCards.map(card => (
              <div
                key={card.id}
                className="flex-shrink-0"
                style={{ width: `calc(${100 / extendedTotal}% - ${(extendedTotal - 1) * 16 / extendedTotal}px)` }}
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
        <InfoTooltip text="Measures market sentiment from 0 (extreme fear) to 100 (extreme greed). Extreme fear often signals buying opportunities; extreme greed may indicate overheated markets." />
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
        <InfoTooltip text="Massive debt expansion often leads to currency debasement. Bitcoin is seen as a hedge against this. Watch debt-to-GDP ratio and ceiling debates for macro signals." />
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
        <InfoTooltip text="Bitcoin's share of total crypto market cap. High dominance suggests BTC strength; falling dominance often signals altcoin season or risk-on sentiment." />
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
        <InfoTooltip text="Measures if altcoins are outperforming Bitcoin. Above 75 = Alt Season (consider taking altcoin profits). Below 25 = BTC Season (rotate to BTC or accumulate alts)." />
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
        <InfoTooltip text="Total stablecoins in circulation - 'dry powder' waiting to deploy. Rising supply often precedes market rallies as capital is ready to buy the dip." />
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

function TotalMarketCapCard({ data }: { data: TotalMarketCapResponse | undefined }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <Globe className="w-5 h-5 text-blue-400" />
        <h3 className="font-medium text-white">Total Crypto Market</h3>
        <InfoTooltip text="Combined market cap of all cryptocurrencies. Compare to gold (~$14T) and stocks (~$45T) to gauge crypto's overall adoption and growth potential." />
      </div>

      {data ? (
        <div className="flex flex-col items-center">
          <div className="text-4xl font-bold text-blue-400 mb-2">
            ${(data.total_market_cap / 1_000_000_000_000).toFixed(2)}T
          </div>
          <div className="text-xs text-slate-400 mb-4">Total crypto market capitalization</div>

          <div className="w-full bg-slate-900/50 rounded-lg p-3">
            <div className="text-xs text-slate-500 mb-1 text-center">For reference</div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="text-slate-400">Gold:</div>
              <div className="text-yellow-400 text-right">~$14T</div>
              <div className="text-slate-400">S&P 500:</div>
              <div className="text-green-400 text-right">~$45T</div>
            </div>
          </div>

          <div className="text-[10px] text-slate-600 mt-3 text-center">
            All cryptocurrencies combined
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

function BTCSupplyCard({ data }: { data: BTCSupplyResponse | undefined }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <Database className="w-5 h-5 text-orange-400" />
        <h3 className="font-medium text-white">BTC Supply Progress</h3>
        <InfoTooltip text="Bitcoin's fixed 21M supply creates scarcity. Over 93% already mined. As remaining supply shrinks, each halving has greater supply shock potential." />
      </div>

      {data ? (
        <div className="flex flex-col items-center">
          <div className="text-3xl font-bold text-orange-400 mb-1">
            {data.percent_mined.toFixed(2)}%
          </div>
          <div className="text-xs text-slate-400 mb-3">of 21M mined</div>

          <div className="w-full mb-3">
            <div className="h-3 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-orange-600 to-yellow-500 transition-all duration-500"
                style={{ width: `${data.percent_mined}%` }}
              />
            </div>
          </div>

          <div className="w-full grid grid-cols-2 gap-2 text-xs">
            <div className="bg-slate-900/50 rounded p-2 text-center">
              <div className="text-slate-500">Circulating</div>
              <div className="text-orange-400 font-mono">{(data.circulating / 1_000_000).toFixed(2)}M</div>
            </div>
            <div className="bg-slate-900/50 rounded p-2 text-center">
              <div className="text-slate-500">Remaining</div>
              <div className="text-slate-300 font-mono">{(data.remaining / 1_000_000).toFixed(2)}M</div>
            </div>
          </div>

          <div className="text-[10px] text-slate-600 mt-3 text-center">
            Max supply: 21,000,000 BTC
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

function MempoolCard({ data }: { data: MempoolResponse | undefined }) {
  const getCongestionColor = (congestion: string) => {
    if (congestion === 'High') return { text: 'text-red-400', bg: 'bg-red-500/20', border: 'border-red-500/30' }
    if (congestion === 'Medium') return { text: 'text-yellow-400', bg: 'bg-yellow-500/20', border: 'border-yellow-500/30' }
    return { text: 'text-green-400', bg: 'bg-green-500/20', border: 'border-green-500/30' }
  }

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <Activity className="w-5 h-5 text-purple-400" />
        <h3 className="font-medium text-white">Bitcoin Mempool</h3>
        <InfoTooltip text="Pending Bitcoin transactions awaiting confirmation. High congestion = high demand and fees. Low congestion = cheap transactions, possibly less activity." />
      </div>

      {data ? (
        <div className="flex flex-col items-center">
          <div className="text-3xl font-bold text-purple-400 mb-1">
            {data.tx_count.toLocaleString()}
          </div>
          <div className="text-xs text-slate-400 mb-2">pending transactions</div>

          <div className={`px-3 py-1 rounded-full text-sm font-medium mb-3 ${getCongestionColor(data.congestion).bg} ${getCongestionColor(data.congestion).text} border ${getCongestionColor(data.congestion).border}`}>
            {data.congestion} Congestion
          </div>

          <div className="w-full space-y-1 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-500">Fast (~10 min)</span>
              <span className="text-green-400 font-mono">{data.fee_fastest} sat/vB</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Medium (~30 min)</span>
              <span className="text-yellow-400 font-mono">{data.fee_half_hour} sat/vB</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Economy (~1 hr)</span>
              <span className="text-slate-400 font-mono">{data.fee_hour} sat/vB</span>
            </div>
          </div>

          <div className="text-[10px] text-slate-600 mt-3 text-center">
            Recommended fee rates
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

function HashRateCard({ data }: { data: HashRateResponse | undefined }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <Cpu className="w-5 h-5 text-cyan-400" />
        <h3 className="font-medium text-white">Network Hash Rate</h3>
        <InfoTooltip text="Total mining power securing Bitcoin. Higher hash rate = stronger security and miner confidence. Dropping hash rate can signal miner capitulation." />
      </div>

      {data ? (
        <div className="flex flex-col items-center">
          <div className="text-3xl font-bold text-cyan-400 mb-1">
            {data.hash_rate_eh.toFixed(0)} EH/s
          </div>
          <div className="text-xs text-slate-400 mb-4">exahashes per second</div>

          <div className="w-full bg-slate-900/50 rounded-lg p-3 mb-3">
            <div className="flex justify-between items-center">
              <span className="text-xs text-slate-500">Next Difficulty</span>
              <span className={`text-xs font-mono ${data.difficulty_t >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {data.difficulty_t >= 0 ? '+' : ''}{data.difficulty_t.toFixed(1)}%
              </span>
            </div>
          </div>

          <div className="w-full h-2 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-cyan-600 to-blue-500"
              style={{ width: `${Math.min(100, (data.hash_rate_eh / 1000) * 100)}%` }}
            />
          </div>

          <div className="text-[10px] text-slate-600 mt-3 text-center">
            Higher = more secure network
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

function LightningCard({ data }: { data: LightningResponse | undefined }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <Zap className="w-5 h-5 text-yellow-400" />
        <h3 className="font-medium text-white">Lightning Network</h3>
        <InfoTooltip text="Bitcoin's Layer 2 for instant, low-fee payments. Growing capacity shows real-world adoption and scaling progress. Key infrastructure for BTC as money." />
      </div>

      {data ? (
        <div className="flex flex-col items-center">
          <div className="text-3xl font-bold text-yellow-400 mb-1">
            {data.total_capacity_btc.toLocaleString()} BTC
          </div>
          <div className="text-xs text-slate-400 mb-4">total capacity</div>

          <div className="w-full grid grid-cols-2 gap-2 text-xs mb-3">
            <div className="bg-slate-900/50 rounded p-2 text-center">
              <div className="text-slate-500">Nodes</div>
              <div className="text-yellow-400 font-mono">{data.node_count.toLocaleString()}</div>
            </div>
            <div className="bg-slate-900/50 rounded p-2 text-center">
              <div className="text-slate-500">Channels</div>
              <div className="text-yellow-400 font-mono">{data.channel_count.toLocaleString()}</div>
            </div>
          </div>

          <div className="text-[10px] text-slate-600 mt-1 text-center">
            Bitcoin's Layer 2 scaling solution
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

function ATHCard({ data }: { data: ATHResponse | undefined }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
      <div className="flex items-center space-x-2 mb-4">
        <TrendingDown className="w-5 h-5 text-red-400" />
        <h3 className="font-medium text-white">Days Since ATH</h3>
        <InfoTooltip text="Days since Bitcoin's all-time high. Long periods below ATH often mark accumulation zones. Breaking ATH typically triggers FOMO and price discovery." />
      </div>

      {data ? (
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
      ) : (
        <div className="flex items-center justify-center h-32">
          <LoadingSpinner size="sm" text="Loading..." />
        </div>
      )}
    </div>
  )
}

function SeasonCard({ seasonInfo }: { seasonInfo: SeasonInfo | null }) {
  if (!seasonInfo) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 h-full">
        <div className="flex items-center space-x-2 mb-4">
          <Sun className="w-5 h-5 text-slate-400" />
          <h3 className="font-medium text-white">Market Season</h3>
        </div>
        <div className="flex items-center justify-center h-32">
          <LoadingSpinner size="sm" text="Analyzing..." />
        </div>
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

  const currentAngle = seasonPositions[seasonInfo.season] + (seasonInfo.progress * 0.9) // 90° per season

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
            <path d="M 50 10 A 40 40 0 0 1 90 50" fill="none" stroke="#10b981" strokeWidth="8" opacity="0.3" />
            <path d="M 90 50 A 40 40 0 0 1 50 90" fill="none" stroke="#f59e0b" strokeWidth="8" opacity="0.3" />
            <path d="M 50 90 A 40 40 0 0 1 10 50" fill="none" stroke="#f97316" strokeWidth="8" opacity="0.3" />
            <path d="M 10 50 A 40 40 0 0 1 50 10" fill="none" stroke="#3b82f6" strokeWidth="8" opacity="0.3" />

            {/* Active segment highlight */}
            {seasonInfo.season === 'accumulation' && (
              <path d="M 50 10 A 40 40 0 0 1 90 50" fill="none" stroke="#10b981" strokeWidth="8" />
            )}
            {seasonInfo.season === 'bull' && (
              <path d="M 90 50 A 40 40 0 0 1 50 90" fill="none" stroke="#f59e0b" strokeWidth="8" />
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
            <text x="70" y="25" fontSize="6" fill="#10b981" textAnchor="middle">🌱</text>
            <text x="85" y="55" fontSize="6" fill="#f59e0b" textAnchor="middle">☀️</text>
            <text x="70" y="85" fontSize="6" fill="#f97316" textAnchor="middle">🍂</text>
            <text x="30" y="85" fontSize="6" fill="#3b82f6" textAnchor="middle">❄️</text>

            {/* Center icon */}
            <foreignObject x="35" y="35" width="30" height="30">
              <div className="flex items-center justify-center w-full h-full">
                <IconComponent className={`w-6 h-6 ${seasonInfo.color}`} />
              </div>
            </foreignObject>
          </svg>
        </div>

        {/* Season name and description */}
        <div className={`text-xl font-bold ${seasonInfo.color} mb-1`}>
          {seasonInfo.name}
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
                seasonInfo.season === 'accumulation' ? 'bg-emerald-500' :
                seasonInfo.season === 'bull' ? 'bg-amber-500' :
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
                <span className={seasonInfo.color}>•</span>
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
