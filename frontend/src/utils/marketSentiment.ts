/**
 * Market Sentiment Utility Functions
 *
 * Helper functions for Fear & Greed Index, BTC Halving Countdown,
 * and US National Debt calculations.
 */

import type { HalvingCountdown } from '../types'

// BTC Halving constants
export const NEXT_HALVING_BLOCK = 1050000 // Block 1,050,000 is the next halving
export const BLOCKS_PER_HALVING = 210000
export const AVG_BLOCK_TIME_MINUTES = 10 // Average Bitcoin block time

// Get color for Fear/Greed meter based on value
export function getFearGreedColor(value: number): { bg: string; text: string; border: string; gradient: string } {
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
export function formatDebt(value: number): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })
}

// Calculate next debt milestone and countdown
export function calculateDebtMilestone(currentDebt: number, debtPerSecond: number, milestoneSize: number): {
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
export function formatDebtCountdown(seconds: number): string {
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
export function formatExtendedCountdown(diffMs: number): string {
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
export function calculateHalvingCountdown(currentHeight: number): HalvingCountdown {
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
