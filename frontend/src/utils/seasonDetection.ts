/**
 * Market Season Detection
 *
 * Determines the current market season based on the Bitcoin halving cycle
 * and market indicators. Used by the carousel SeasonCard and the header
 * gradient hook (useMarketSeason).
 *
 * Extracted from MarketSentimentCards.tsx for modularity (S3/S4).
 * Removed unused altseason parameter (S14).
 */

import { Sun, Snowflake, Leaf, Sprout } from 'lucide-react'
import type { ATHResponse, BTCDominanceResponse } from '../types'

export type MarketSeason = 'accumulation' | 'bull' | 'distribution' | 'bear'

export interface SeasonInfo {
  season: MarketSeason
  name: string
  subtitle: string
  description: string
  progress: number
  confidence: number
  icon: typeof Sprout
  color: string
  bgGradient: string
  signals: string[]
}

// Bitcoin halving dates
const HALVING_DATES = [
  new Date('2012-11-28T00:00:00Z'),
  new Date('2016-07-09T00:00:00Z'),
  new Date('2020-05-11T00:00:00Z'),
  new Date('2024-04-20T00:00:00Z'),
  new Date('2028-04-17T00:00:00Z'), // Estimated
]

// Cycle timing in days from halving
const CYCLE_TIMING = {
  springStart: -180,
  summerStart: 0,
  fallStart: 400,
  winterStart: 550,
  cycleLength: 1260,
}

function getHalvingInfo(): { daysSinceHalving: number } {
  const now = new Date()
  let lastHalving = HALVING_DATES[0]

  for (const halvingDate of HALVING_DATES) {
    if (halvingDate <= now) {
      lastHalving = halvingDate
    } else {
      break
    }
  }

  const daysSinceHalving = Math.floor((now.getTime() - lastHalving.getTime()) / (1000 * 60 * 60 * 24))
  return { daysSinceHalving }
}

function getSeasonFromHalving(daysSinceHalving: number): { season: MarketSeason; progress: number; cyclePosition: string } {
  const t = CYCLE_TIMING

  if (daysSinceHalving < t.springStart) {
    return { season: 'bear', progress: 50, cyclePosition: 'Late previous cycle' }
  } else if (daysSinceHalving < t.summerStart) {
    const seasonLength = t.summerStart - t.springStart
    const daysInto = daysSinceHalving - t.springStart
    return { season: 'accumulation', progress: (daysInto / seasonLength) * 100, cyclePosition: `${-daysSinceHalving} days to halving` }
  } else if (daysSinceHalving < t.fallStart) {
    const seasonLength = t.fallStart - t.summerStart
    const daysInto = daysSinceHalving - t.summerStart
    return { season: 'bull', progress: (daysInto / seasonLength) * 100, cyclePosition: `${daysSinceHalving} days post-halving` }
  } else if (daysSinceHalving < t.winterStart) {
    const seasonLength = t.winterStart - t.fallStart
    const daysInto = daysSinceHalving - t.fallStart
    return { season: 'distribution', progress: (daysInto / seasonLength) * 100, cyclePosition: `${daysSinceHalving} days post-halving` }
  } else {
    const winterEnd = t.cycleLength + t.springStart
    const seasonLength = winterEnd - t.winterStart
    const daysInto = daysSinceHalving - t.winterStart
    return { season: 'bear', progress: Math.min((daysInto / seasonLength) * 100, 100), cyclePosition: `${daysSinceHalving} days post-halving` }
  }
}

/**
 * Determine the current market season based on halving cycle (primary) and indicators (secondary).
 *
 * HALVING-ANCHORED: Season is primarily determined by position in the ~4-year halving cycle.
 * Indicators (Fear/Greed, drawdown, dominance) only adjust CONFIDENCE, not the season itself.
 */
export function determineMarketSeason(
  fearGreed: number | undefined,
  athData: ATHResponse | undefined,
  btcDominance: BTCDominanceResponse | undefined
): SeasonInfo {
  const { daysSinceHalving } = getHalvingInfo()
  const { season, progress, cyclePosition } = getSeasonFromHalving(daysSinceHalving)

  const fg = fearGreed ?? 50
  const drawdown = athData?.drawdown_pct ?? 0
  const recovery = athData?.recovery_pct ?? 100
  const daysSinceATH = athData?.days_since_ath ?? 0
  const btcDom = btcDominance?.btc_dominance ?? 50

  const signals: string[] = [cyclePosition]
  let agreements = 0
  const totalChecks = 4

  if (season === 'accumulation') {
    if (fg <= 40) { agreements++; signals.push(`Fear & Greed at ${fg}`) }
    if (drawdown >= 30) { agreements++; signals.push(`${drawdown.toFixed(0)}% drawdown`) }
    if (btcDom >= 50) { agreements++; signals.push(`BTC dom ${btcDom.toFixed(0)}%`) }
    if (daysSinceATH >= 300) { agreements++; signals.push(`${daysSinceATH} days since ATH`) }
  } else if (season === 'bull') {
    if (fg >= 40) { agreements++; signals.push(`Fear & Greed at ${fg}`) }
    if (recovery >= 50) { agreements++; signals.push(`${recovery.toFixed(0)}% recovery`) }
    if (btcDom >= 40 && btcDom <= 60) { agreements++; signals.push(`BTC dom ${btcDom.toFixed(0)}%`) }
    if (drawdown <= 40) { agreements++; signals.push(`${drawdown.toFixed(0)}% drawdown`) }
  } else if (season === 'distribution') {
    if (fg >= 60) { agreements++; signals.push(`Fear & Greed at ${fg}`) }
    if (recovery >= 85) { agreements++; signals.push(`${recovery.toFixed(0)}% of ATH`) }
    if (btcDom <= 50) { agreements++; signals.push(`BTC dom ${btcDom.toFixed(0)}%`) }
    if (daysSinceATH <= 60) { agreements++; signals.push(`${daysSinceATH} days since ATH`) }
  } else if (season === 'bear') {
    if (fg <= 35) { agreements++; signals.push(`Fear & Greed at ${fg}`) }
    if (drawdown >= 40) { agreements++; signals.push(`${drawdown.toFixed(0)}% drawdown`) }
    if (btcDom >= 55) { agreements++; signals.push(`BTC dom ${btcDom.toFixed(0)}%`) }
    if (daysSinceATH >= 60) { agreements++; signals.push(`${daysSinceATH} days since ATH`) }
  }

  const confidence = 40 + (agreements / totalChecks) * 60

  const seasonInfo: Record<MarketSeason, Omit<SeasonInfo, 'progress' | 'confidence' | 'signals'>> = {
    accumulation: {
      season: 'accumulation', name: 'Spring', subtitle: 'Accumulation Phase',
      description: 'Smart money quietly buying. Fear dominates headlines.',
      icon: Sprout, color: 'text-pink-400', bgGradient: 'from-pink-900/30 to-rose-900/20'
    },
    bull: {
      season: 'bull', name: 'Summer', subtitle: 'Bull Market',
      description: 'Prices rising, optimism growing. Momentum building.',
      icon: Sun, color: 'text-green-400', bgGradient: 'from-green-900/30 to-emerald-900/20'
    },
    distribution: {
      season: 'distribution', name: 'Fall', subtitle: 'Distribution Phase',
      description: 'Peak euphoria. Smart money taking profits.',
      icon: Leaf, color: 'text-orange-400', bgGradient: 'from-orange-900/30 to-red-900/20'
    },
    bear: {
      season: 'bear', name: 'Winter', subtitle: 'Bear Market',
      description: 'Prices falling, fear spreading. Patience required.',
      icon: Snowflake, color: 'text-blue-400', bgGradient: 'from-blue-900/30 to-slate-900/20'
    }
  }

  return {
    ...seasonInfo[season],
    progress,
    confidence,
    signals: signals.slice(0, 3)
  }
}
