/**
 * Market Sentiment Cards Carousel
 *
 * Orchestrator component: manages data fetching, carousel mechanics, and card composition.
 * Individual cards are in ./cards/, season detection in ../utils/seasonDetection.ts.
 *
 * Performance fixes applied:
 * - S1: Timer state moved into HalvingCard/USDebtCard (prevents ~11 re-renders/sec)
 * - S2: Card components are React.memo'd (prevents re-renders during carousel animation)
 * - S5: Error states passed to cards via isError prop
 * - S11: Resize handler debounced
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { authFetch } from '../services/api'
import { ChevronLeft, ChevronRight, Pause, Play } from 'lucide-react'
import { determineMarketSeason } from '../utils/seasonDetection'
import { DebtCeilingModal } from './DebtCeilingModal'
import {
  FearGreedCard, HalvingCard, USDebtCard, BTCDominanceCard,
  AltseasonCard, StablecoinMcapCard, TotalMarketCapCard,
  BTCSupplyCard, MempoolCard, HashRateCard, LightningCard,
  ATHCard, BTCRSICard, SeasonCard,
} from './cards'
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
  BTCRSIResponse,
  MetricHistoryResponse,
} from '../types'

// Re-export for backward compatibility
export { determineMarketSeason } from '../utils/seasonDetection'
export type { MarketSeason, SeasonInfo } from '../utils/seasonDetection'

// Carousel configuration
const AUTO_CYCLE_INTERVAL = 30000 // 30 seconds
const ANIMATION_DURATION = 1200 // ms - bowstring feel
const SWIPE_THRESHOLD = 50 // px minimum swipe distance

const springKeyframes = `
@keyframes slideSpringLeft {
  0% { transform: translateX(var(--from-x)); }
  15% { transform: translateX(calc(var(--from-x) + 1.5%)); }
  40% { transform: translateX(calc(var(--from-x) + 3.5%)); }
  52% { transform: translateX(calc(var(--from-x) + 3.5%)); }
  72% { transform: translateX(calc(var(--to-x) - 2%)); }
  86% { transform: translateX(calc(var(--to-x) + 0.5%)); }
  100% { transform: translateX(var(--to-x)); }
}
@keyframes slideSpringRight {
  0% { transform: translateX(var(--from-x)); }
  15% { transform: translateX(calc(var(--from-x) - 1.5%)); }
  40% { transform: translateX(calc(var(--from-x) - 3.5%)); }
  52% { transform: translateX(calc(var(--from-x) - 3.5%)); }
  72% { transform: translateX(calc(var(--to-x) + 2%)); }
  86% { transform: translateX(calc(var(--to-x) - 0.5%)); }
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

export function MarketSentimentCards({ isUserEngaged = false }: { isUserEngaged?: boolean }) {
  // S11: Responsive cards visible count with debounced resize
  const [cardsVisible, setCardsVisible] = useState(() => {
    if (typeof window !== 'undefined') {
      if (window.innerWidth < 640) return 1
      if (window.innerWidth < 1024) return 2
      return 3
    }
    return 3
  })

  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout>
    const handleResize = () => {
      clearTimeout(timeoutId)
      timeoutId = setTimeout(() => {
        const width = window.innerWidth
        setCardsVisible(prev => {
          const next = width < 640 ? 1 : width < 1024 ? 2 : 3
          if (next !== prev) return next
          return prev
        })
      }, 150)
    }
    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      clearTimeout(timeoutId)
    }
  }, [])

  // Carousel state
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isPaused, setIsPaused] = useState(false)
  const [isAnimating, setIsAnimating] = useState(false)
  const [animationType, setAnimationType] = useState<'button' | 'swipe'>('button')
  const [slideDirection, setSlideDirection] = useState<'left' | 'right' | null>(null)
  const autoPlayRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const carouselRef = useRef<HTMLDivElement>(null)

  // Reset carousel position when cards visible count changes
  useEffect(() => {
    setCurrentIndex(0)
    setIsAnimating(false)
    setSlideDirection(null)
  }, [cardsVisible])

  // Swipe tracking
  const touchStartX = useRef<number>(0)
  const touchStartY = useRef<number>(0)
  const isDragging = useRef<boolean>(false)

  // Track debt ceiling history modal
  const [showDebtCeilingModal, setShowDebtCeilingModal] = useState(false)

  // =========================================================================
  // Data Fetching (S5: destructure isError for each query)
  // =========================================================================

  const { data: fearGreedData, isError: fgError } = useQuery<FearGreedResponse>({
    queryKey: ['fear-greed'],
    queryFn: async () => {
      const response = await authFetch('/api/news/fear-greed')
      if (!response.ok) throw new Error('Failed to fetch fear/greed index')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: isUserEngaged ? false : 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  const { data: blockHeight, isError: blockError } = useQuery<BlockHeightResponse>({
    queryKey: ['btc-block-height'],
    queryFn: async () => {
      const response = await authFetch('/api/news/btc-block-height')
      if (!response.ok) throw new Error('Failed to fetch block height')
      return response.json()
    },
    staleTime: 1000 * 60 * 10,
    refetchInterval: isUserEngaged ? false : 1000 * 60 * 10,
    refetchOnWindowFocus: false,
  })

  const { data: usDebtData, isError: debtError } = useQuery<USDebtResponse>({
    queryKey: ['us-debt'],
    queryFn: async () => {
      const response = await authFetch('/api/news/us-debt')
      if (!response.ok) throw new Error('Failed to fetch US debt')
      return response.json()
    },
    staleTime: 1000 * 60 * 60 * 24,
    refetchInterval: isUserEngaged ? false : 1000 * 60 * 60 * 24,
    refetchOnWindowFocus: false,
  })

  const { data: debtCeilingHistory } = useQuery<DebtCeilingHistoryResponse>({
    queryKey: ['debt-ceiling-history'],
    queryFn: async () => {
      const response = await authFetch('/api/news/debt-ceiling-history')
      if (!response.ok) throw new Error('Failed to fetch debt ceiling history')
      return response.json()
    },
    staleTime: 1000 * 60 * 60 * 24 * 7,
    refetchOnWindowFocus: false,
  })

  const { data: btcDominanceData, isError: domError } = useQuery<BTCDominanceResponse>({
    queryKey: ['btc-dominance'],
    queryFn: async () => {
      const response = await authFetch('/api/news/btc-dominance')
      if (!response.ok) throw new Error('Failed to fetch BTC dominance')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: isUserEngaged ? false : 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  const { data: altseasonData, isError: altError } = useQuery<AltseasonIndexResponse>({
    queryKey: ['altseason-index'],
    queryFn: async () => {
      const response = await authFetch('/api/news/altseason-index')
      if (!response.ok) throw new Error('Failed to fetch altseason index')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: isUserEngaged ? false : 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  const { data: stablecoinData, isError: stableError } = useQuery<StablecoinMcapResponse>({
    queryKey: ['stablecoin-mcap'],
    queryFn: async () => {
      const response = await authFetch('/api/news/stablecoin-mcap')
      if (!response.ok) throw new Error('Failed to fetch stablecoin mcap')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: isUserEngaged ? false : 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  const { data: totalMarketCapData, isError: tmcError } = useQuery<TotalMarketCapResponse>({
    queryKey: ['total-market-cap'],
    queryFn: async () => {
      const response = await authFetch('/api/news/total-market-cap')
      if (!response.ok) throw new Error('Failed to fetch total market cap')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: isUserEngaged ? false : 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  const { data: btcSupplyData, isError: supplyError } = useQuery<BTCSupplyResponse>({
    queryKey: ['btc-supply'],
    queryFn: async () => {
      const response = await authFetch('/api/news/btc-supply')
      if (!response.ok) throw new Error('Failed to fetch BTC supply')
      return response.json()
    },
    staleTime: 1000 * 60 * 10,
    refetchInterval: isUserEngaged ? false : 1000 * 60 * 10,
    refetchOnWindowFocus: false,
  })

  const { data: mempoolData, isError: mempoolError } = useQuery<MempoolResponse>({
    queryKey: ['mempool'],
    queryFn: async () => {
      const response = await authFetch('/api/news/mempool')
      if (!response.ok) throw new Error('Failed to fetch mempool')
      return response.json()
    },
    staleTime: 1000 * 60 * 5,
    refetchInterval: isUserEngaged ? false : 1000 * 60 * 5,
    refetchOnWindowFocus: false,
  })

  const { data: hashRateData, isError: hashError } = useQuery<HashRateResponse>({
    queryKey: ['hash-rate'],
    queryFn: async () => {
      const response = await authFetch('/api/news/hash-rate')
      if (!response.ok) throw new Error('Failed to fetch hash rate')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: isUserEngaged ? false : 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  const { data: lightningData, isError: lnError } = useQuery<LightningResponse>({
    queryKey: ['lightning'],
    queryFn: async () => {
      const response = await authFetch('/api/news/lightning')
      if (!response.ok) throw new Error('Failed to fetch lightning stats')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: isUserEngaged ? false : 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  const { data: athData, isError: athError } = useQuery<ATHResponse>({
    queryKey: ['ath'],
    queryFn: async () => {
      const response = await authFetch('/api/news/ath')
      if (!response.ok) throw new Error('Failed to fetch ATH data')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: isUserEngaged ? false : 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  const { data: btcRsiData, isError: rsiError } = useQuery<BTCRSIResponse>({
    queryKey: ['btc-rsi'],
    queryFn: async () => {
      const response = await authFetch('/api/news/btc-rsi')
      if (!response.ok) throw new Error('Failed to fetch BTC RSI')
      return response.json()
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: isUserEngaged ? false : 1000 * 60 * 15,
    refetchOnWindowFocus: false,
  })

  // Fetch metric histories for sparklines
  const metricHistoryQuery = (name: string) => ({
    queryKey: ['metric-history', name],
    queryFn: async () => {
      const response = await authFetch(`/api/news/metric-history/${name}?days=30&max_points=30`)
      if (!response.ok) return { metric_name: name, data: [] }
      return response.json() as Promise<MetricHistoryResponse>
    },
    staleTime: 1000 * 60 * 15,
    refetchInterval: (isUserEngaged ? false : 1000 * 60 * 15) as number | false,
    refetchOnWindowFocus: false,
  })

  const { data: fearGreedHistory } = useQuery(metricHistoryQuery('fear_greed'))
  const { data: btcDomHistory } = useQuery(metricHistoryQuery('btc_dominance'))
  const { data: altseasonHistory } = useQuery(metricHistoryQuery('altseason_index'))
  const { data: stablecoinHistory } = useQuery(metricHistoryQuery('stablecoin_mcap'))
  const { data: totalMcapHistory } = useQuery(metricHistoryQuery('total_market_cap'))
  const { data: hashRateHistory } = useQuery(metricHistoryQuery('hash_rate'))
  const { data: lightningHistory } = useQuery(metricHistoryQuery('lightning_capacity'))
  const { data: mempoolHistory } = useQuery(metricHistoryQuery('mempool_tx_count'))
  const { data: btcRsiHistory } = useQuery(metricHistoryQuery('btc_rsi'))

  const sparkData = useMemo(() => ({
    fear_greed: fearGreedHistory?.data?.map(d => d.value) || [],
    btc_dominance: btcDomHistory?.data?.map(d => d.value) || [],
    altseason_index: altseasonHistory?.data?.map(d => d.value) || [],
    stablecoin_mcap: stablecoinHistory?.data?.map(d => d.value) || [],
    total_market_cap: totalMcapHistory?.data?.map(d => d.value) || [],
    hash_rate: hashRateHistory?.data?.map(d => d.value) || [],
    lightning_capacity: lightningHistory?.data?.map(d => d.value) || [],
    mempool_tx_count: mempoolHistory?.data?.map(d => d.value) || [],
    btc_rsi: btcRsiHistory?.data?.map(d => d.value) || [],
  }), [fearGreedHistory, btcDomHistory, altseasonHistory, stablecoinHistory, totalMcapHistory, hashRateHistory, lightningHistory, mempoolHistory, btcRsiHistory])

  const sparkTimeLabels = useMemo(() => {
    const formatTimeSpan = (data: { recorded_at: string }[] | undefined): string => {
      if (!data || data.length < 2) return ''
      const startMs = new Date(data[0].recorded_at).getTime()
      const endMs = new Date(data[data.length - 1].recorded_at).getTime()
      const diffSec = (endMs - startMs) / 1000
      if (diffSec < 3600) {
        const mins = Math.round(diffSec / 60)
        return `last ${mins} min`
      }
      if (diffSec < 86400) {
        const hrs = diffSec / 3600
        const label = hrs % 1 === 0 ? `${Math.round(hrs)}` : `${hrs.toFixed(1)}`
        return `last ${label} hrs`
      }
      if (diffSec < 604800) {
        const days = diffSec / 86400
        const label = days % 1 === 0 ? `${Math.round(days)}` : `${days.toFixed(1)}`
        return `last ${label} days`
      }
      if (diffSec < 2592000) {
        const weeks = diffSec / 604800
        const label = weeks % 1 === 0 ? `${Math.round(weeks)}` : `${weeks.toFixed(1)}`
        return `last ${label} weeks`
      }
      if (diffSec < 31536000) {
        const months = diffSec / 2592000
        const label = months % 1 === 0 ? `${Math.round(months)}` : `${months.toFixed(1)}`
        return `last ${label} months`
      }
      const years = diffSec / 31536000
      const label = years % 1 === 0 ? `${Math.round(years)}` : `${years.toFixed(1)}`
      return `last ${label} years`
    }
    return {
      fear_greed: formatTimeSpan(fearGreedHistory?.data),
      btc_dominance: formatTimeSpan(btcDomHistory?.data),
      altseason_index: formatTimeSpan(altseasonHistory?.data),
      stablecoin_mcap: formatTimeSpan(stablecoinHistory?.data),
      total_market_cap: formatTimeSpan(totalMcapHistory?.data),
      hash_rate: formatTimeSpan(hashRateHistory?.data),
      lightning_capacity: formatTimeSpan(lightningHistory?.data),
      mempool_tx_count: formatTimeSpan(mempoolHistory?.data),
      btc_rsi: formatTimeSpan(btcRsiHistory?.data),
    }
  }, [fearGreedHistory, btcDomHistory, altseasonHistory, stablecoinHistory, totalMcapHistory, hashRateHistory, lightningHistory, mempoolHistory, btcRsiHistory])

  // Calculate market season (S14: removed altseason param)
  const seasonInfo = fearGreedData || athData || btcDominanceData
    ? determineMarketSeason(
        fearGreedData?.data?.value,
        athData,
        btcDominanceData
      )
    : null

  // S1: Timer state removed from parent - now managed inside HalvingCard and USDebtCard

  // Build card list (cards handle their own timers internally)
  const baseCards = [
    { id: 'season', component: <SeasonCard seasonInfo={seasonInfo} /> },
    { id: 'fear-greed', component: <FearGreedCard data={fearGreedData} isError={fgError} spark={sparkData.fear_greed} sparkTimeLabel={sparkTimeLabels.fear_greed} /> },
    { id: 'halving', component: <HalvingCard blockHeight={blockHeight} isError={blockError} /> },
    { id: 'us-debt', component: <USDebtCard usDebtData={usDebtData} isError={debtError} onShowHistory={() => setShowDebtCeilingModal(true)} /> },
    { id: 'btc-dominance', component: <BTCDominanceCard data={btcDominanceData} isError={domError} spark={sparkData.btc_dominance} sparkTimeLabel={sparkTimeLabels.btc_dominance} /> },
    { id: 'altseason', component: <AltseasonCard data={altseasonData} isError={altError} spark={sparkData.altseason_index} sparkTimeLabel={sparkTimeLabels.altseason_index} /> },
    { id: 'stablecoin-mcap', component: <StablecoinMcapCard data={stablecoinData} isError={stableError} spark={sparkData.stablecoin_mcap} sparkTimeLabel={sparkTimeLabels.stablecoin_mcap} /> },
    { id: 'total-mcap', component: <TotalMarketCapCard data={totalMarketCapData} isError={tmcError} spark={sparkData.total_market_cap} sparkTimeLabel={sparkTimeLabels.total_market_cap} /> },
    { id: 'btc-supply', component: <BTCSupplyCard data={btcSupplyData} isError={supplyError} /> },
    { id: 'mempool', component: <MempoolCard data={mempoolData} isError={mempoolError} spark={sparkData.mempool_tx_count} sparkTimeLabel={sparkTimeLabels.mempool_tx_count} /> },
    { id: 'hash-rate', component: <HashRateCard data={hashRateData} isError={hashError} spark={sparkData.hash_rate} sparkTimeLabel={sparkTimeLabels.hash_rate} /> },
    { id: 'lightning', component: <LightningCard data={lightningData} isError={lnError} spark={sparkData.lightning_capacity} sparkTimeLabel={sparkTimeLabels.lightning_capacity} /> },
    { id: 'ath', component: <ATHCard data={athData} isError={athError} /> },
    { id: 'btc-rsi', component: <BTCRSICard data={btcRsiData} isError={rsiError} spark={sparkData.btc_rsi} sparkTimeLabel={sparkTimeLabels.btc_rsi} /> },
  ]

  const totalCards = baseCards.length

  // For infinite scroll: create extended array with clones at both ends
  const extendedCards = [
    ...baseCards.slice(-cardsVisible).map((card, i) => ({ ...card, id: `clone-end-${i}` })),
    ...baseCards,
    ...baseCards.slice(0, cardsVisible).map((card, i) => ({ ...card, id: `clone-start-${i}` })),
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

  // =========================================================================
  // Carousel Navigation
  // =========================================================================

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

  const goToIndex = useCallback((targetLogicalIndex: number) => {
    const currentLogicalIndex = ((currentIndex % totalCards) + totalCards) % totalCards
    if (isAnimating || targetLogicalIndex === currentLogicalIndex) return

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
    if (currentIndex < 0) {
      setCurrentIndex(totalCards + currentIndex)
    } else if (currentIndex >= totalCards) {
      setCurrentIndex(currentIndex % totalCards)
    }
  }, [currentIndex, isAnimating, totalCards])

  // Reset auto-play timer
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

    if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > SWIPE_THRESHOLD) {
      if (diffX > 0) {
        nextSlide(true)
      } else {
        prevSlide(true)
      }
      resetAutoPlay()
    }
  }, [nextSlide, prevSlide, resetAutoPlay])

  // =========================================================================
  // Rendering
  // =========================================================================

  const cardWidthInTrack = 100 / extendedTotal

  const getTransformPercent = (index: number) => {
    return -((index + cardsVisible) * cardWidthInTrack)
  }
  const baseTransform = getTransformPercent(currentIndex)

  const getAnimationStyle = (): React.CSSProperties => {
    if (!isAnimating || !slideDirection) {
      return { transform: `translateX(${baseTransform}%)` }
    }

    const fromX = `${baseTransform}%`
    const toX = slideDirection === 'left'
      ? `${baseTransform - cardWidthInTrack}%`
      : `${baseTransform + cardWidthInTrack}%`

    const animName = animationType === 'swipe'
      ? `slideSwipe${slideDirection === 'left' ? 'Left' : 'Right'}`
      : `slideSpring${slideDirection === 'left' ? 'Left' : 'Right'}`

    return {
      '--from-x': fromX,
      '--to-x': toX,
      animation: `${animName} ${ANIMATION_DURATION}ms cubic-bezier(0.25, 0.1, 0.25, 1) forwards`,
    } as React.CSSProperties
  }

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

        {/* Cards Carousel */}
        <div
          className="overflow-hidden cursor-grab active:cursor-grabbing select-none"
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
          onMouseDown={handleTouchStart}
          onMouseUp={handleTouchEnd}
          onMouseLeave={() => { isDragging.current = false }}
        >
          <div
            ref={carouselRef}
            className="flex gap-4"
            style={{
              width: `${(extendedTotal / cardsVisible) * 100}%`,
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
