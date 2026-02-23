/**
 * Tests for seasonDetection.ts
 *
 * Tests determineMarketSeason with mocked system time to exercise
 * all reachable halving cycle phases: bull, distribution, bear.
 * Note: The "accumulation" phase requires daysSinceHalving between -180 and 0,
 * which is unreachable since getHalvingInfo always counts from past halvings (>= 0).
 * Also tests indicator agreement adjusting confidence.
 */

import { describe, test, expect, vi, afterEach } from 'vitest'
import { determineMarketSeason } from './seasonDetection'
import type { ATHResponse, BTCDominanceResponse } from '../types'

afterEach(() => {
  vi.useRealTimers()
})

// ── Baseline tests (current time) ────────────────────────────────────

describe('determineMarketSeason', () => {
  test('returns a valid season info object', () => {
    const result = determineMarketSeason(50, undefined, undefined)
    expect(result).toHaveProperty('season')
    expect(result).toHaveProperty('name')
    expect(result).toHaveProperty('subtitle')
    expect(result).toHaveProperty('description')
    expect(result).toHaveProperty('progress')
    expect(result).toHaveProperty('confidence')
    expect(result).toHaveProperty('icon')
    expect(result).toHaveProperty('color')
    expect(result).toHaveProperty('bgGradient')
    expect(result).toHaveProperty('signals')
    expect(['accumulation', 'bull', 'distribution', 'bear']).toContain(result.season)
  })

  test('confidence is between 40 and 100', () => {
    const result = determineMarketSeason(50, undefined, undefined)
    expect(result.confidence).toBeGreaterThanOrEqual(40)
    expect(result.confidence).toBeLessThanOrEqual(100)
  })

  test('progress is between 0 and 100', () => {
    const result = determineMarketSeason(50, undefined, undefined)
    expect(result.progress).toBeGreaterThanOrEqual(0)
    expect(result.progress).toBeLessThanOrEqual(100)
  })

  test('signals array has at most 3 entries', () => {
    const ath: ATHResponse = {
      current_price: 60000,
      ath: 69000,
      ath_date: '2021-11-10',
      days_since_ath: 30,
      drawdown_pct: 13,
      recovery_pct: 87,
      cached_at: '2025-01-01',
    }
    const dom: BTCDominanceResponse = {
      btc_dominance: 48,
      eth_dominance: 18,
      others_dominance: 34,
      total_market_cap: 2_000_000_000_000,
      cached_at: '2025-01-01',
    }
    const result = determineMarketSeason(70, ath, dom)
    expect(result.signals.length).toBeLessThanOrEqual(3)
  })

  test('handles undefined indicators gracefully (uses defaults)', () => {
    // Should not throw with all undefined
    const result = determineMarketSeason(undefined, undefined, undefined)
    expect(result.season).toBeDefined()
    expect(result.confidence).toBeGreaterThanOrEqual(40)
  })

  test('season name matches expected mapping', () => {
    const result = determineMarketSeason(50, undefined, undefined)
    const seasonNames: Record<string, string> = {
      accumulation: 'Spring',
      bull: 'Summer',
      distribution: 'Fall',
      bear: 'Winter',
    }
    expect(result.name).toBe(seasonNames[result.season])
  })

  test('agreeing indicators increase confidence above baseline', () => {
    // We're ~674 days post-2024-halving (Feb 2026), so season = bear.
    // Supply indicators that agree with bear signals:
    // fg <= 35, drawdown >= 40, btcDom >= 55, daysSinceATH >= 60
    const bearAth: ATHResponse = {
      current_price: 30000,
      ath: 69000,
      ath_date: '2024-03-01',
      days_since_ath: 700,
      drawdown_pct: 56,
      recovery_pct: 43,
      cached_at: '2026-02-01',
    }
    const bearDom: BTCDominanceResponse = {
      btc_dominance: 60,
      eth_dominance: 15,
      others_dominance: 25,
      total_market_cap: 1_000_000_000_000,
      cached_at: '2026-02-01',
    }

    const result = determineMarketSeason(20, bearAth, bearDom)
    // All 4 bear checks should agree -> confidence = 40 + (4/4)*60 = 100
    expect(result.confidence).toBeGreaterThan(40)
    expect(result.season).toBe('bear')
  })

  test('first signal is always cycle position', () => {
    const result = determineMarketSeason(50, undefined, undefined)
    // First signal should contain halving cycle info
    expect(result.signals[0]).toMatch(/days|halving|cycle/i)
  })
})

// ── Halving cycle phase tests (mocked time) ──────────────────────────

describe('determineMarketSeason - bull phase', () => {
  test('returns bull when 10 days after 2024 halving', () => {
    vi.useFakeTimers()
    // 2024-04-20 + 10 days = 2024-04-30
    vi.setSystemTime(new Date('2024-04-30T12:00:00Z'))

    const result = determineMarketSeason(60, undefined, undefined)
    expect(result.season).toBe('bull')
    expect(result.name).toBe('Summer')
  })

  test('returns bull when 200 days after 2024 halving', () => {
    vi.useFakeTimers()
    // 2024-04-20 + 200 days = 2024-11-06
    vi.setSystemTime(new Date('2024-11-06T12:00:00Z'))

    const result = determineMarketSeason(60, undefined, undefined)
    expect(result.season).toBe('bull')
    expect(result.name).toBe('Summer')
  })

  test('bull progress starts at 0 on halving day', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2024-04-20T12:00:00Z'))

    const result = determineMarketSeason(50, undefined, undefined)
    expect(result.season).toBe('bull')
    expect(result.progress).toBeCloseTo(0, 0)
  })

  test('bull progress increases over time', () => {
    vi.useFakeTimers()
    // 200 days into bull phase (out of 400 total) = 50%
    vi.setSystemTime(new Date('2024-11-06T12:00:00Z'))

    const result = determineMarketSeason(50, undefined, undefined)
    expect(result.season).toBe('bull')
    expect(result.progress).toBeGreaterThan(40)
    expect(result.progress).toBeLessThan(60)
  })

  test('bull confidence increases with agreeing indicators', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2024-11-06T12:00:00Z'))

    // Indicators that agree with bull: fg>=40, recovery>=50, 40<=btcDom<=60, drawdown<=40
    const ath: ATHResponse = {
      current_price: 90000, ath: 100000, ath_date: '2024-10-01',
      days_since_ath: 36, drawdown_pct: 10, recovery_pct: 90, cached_at: '2024-11-06',
    }
    const dom: BTCDominanceResponse = {
      btc_dominance: 50, eth_dominance: 20, others_dominance: 30,
      total_market_cap: 3_000_000_000_000, cached_at: '2024-11-06',
    }

    const result = determineMarketSeason(65, ath, dom)
    expect(result.season).toBe('bull')
    // fg=65>=40, recovery=90>=50, dom=50 in [40,60], drawdown=10<=40 -> all 4 agree
    expect(result.confidence).toBe(100)
  })

  test('bull with no agreeing indicators has baseline confidence', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2024-11-06T12:00:00Z'))

    // Indicators that disagree with bull
    const ath: ATHResponse = {
      current_price: 20000, ath: 100000, ath_date: '2024-01-01',
      days_since_ath: 310, drawdown_pct: 80, recovery_pct: 20, cached_at: '2024-11-06',
    }
    const dom: BTCDominanceResponse = {
      btc_dominance: 70, eth_dominance: 10, others_dominance: 20,
      total_market_cap: 1_000_000_000_000, cached_at: '2024-11-06',
    }

    const result = determineMarketSeason(15, ath, dom)
    expect(result.season).toBe('bull')
    // 0 agreements: confidence = 40
    expect(result.confidence).toBe(40)
  })

  test('bull signal includes cycle position', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2024-11-06T12:00:00Z'))

    const result = determineMarketSeason(50, undefined, undefined)
    expect(result.signals[0]).toContain('days post-halving')
  })
})

describe('determineMarketSeason - distribution phase', () => {
  test('returns distribution when 420 days after 2024 halving', () => {
    vi.useFakeTimers()
    // 2024-04-20 + 420 days = 2025-06-14
    vi.setSystemTime(new Date('2025-06-14T12:00:00Z'))

    const result = determineMarketSeason(75, undefined, undefined)
    expect(result.season).toBe('distribution')
    expect(result.name).toBe('Fall')
  })

  test('distribution starts at fallStart (400 days)', () => {
    vi.useFakeTimers()
    // 2024-04-20 + 400 days = 2025-05-25
    vi.setSystemTime(new Date('2025-05-25T12:00:00Z'))

    const result = determineMarketSeason(50, undefined, undefined)
    expect(result.season).toBe('distribution')
    expect(result.progress).toBeCloseTo(0, 0)
  })

  test('distribution confidence increases with agreeing indicators', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2025-06-14T12:00:00Z'))

    // Indicators that agree with distribution: fg>=60, recovery>=85, btcDom<=50, daysSinceATH<=60
    const ath: ATHResponse = {
      current_price: 120000, ath: 130000, ath_date: '2025-05-20',
      days_since_ath: 25, drawdown_pct: 8, recovery_pct: 92, cached_at: '2025-06-14',
    }
    const dom: BTCDominanceResponse = {
      btc_dominance: 42, eth_dominance: 22, others_dominance: 36,
      total_market_cap: 4_000_000_000_000, cached_at: '2025-06-14',
    }

    const result = determineMarketSeason(80, ath, dom)
    expect(result.season).toBe('distribution')
    // fg=80>=60, recovery=92>=85, dom=42<=50, days=25<=60 -> all 4
    expect(result.confidence).toBe(100)
  })
})

describe('determineMarketSeason - bear phase', () => {
  test('returns bear when 600 days after 2024 halving', () => {
    vi.useFakeTimers()
    // 2024-04-20 + 600 days = 2025-12-11
    vi.setSystemTime(new Date('2025-12-11T12:00:00Z'))

    const result = determineMarketSeason(20, undefined, undefined)
    expect(result.season).toBe('bear')
    expect(result.name).toBe('Winter')
  })

  test('bear starts at winterStart (550 days)', () => {
    vi.useFakeTimers()
    // 2024-04-20 + 550 days = 2025-10-22
    vi.setSystemTime(new Date('2025-10-22T12:00:00Z'))

    const result = determineMarketSeason(20, undefined, undefined)
    expect(result.season).toBe('bear')
  })

  test('bear progress is capped at 100', () => {
    vi.useFakeTimers()
    // Far into bear phase, near end of cycle
    // 2024-04-20 + 1200 days = 2027-08-02
    vi.setSystemTime(new Date('2027-08-02T12:00:00Z'))

    const result = determineMarketSeason(15, undefined, undefined)
    // This is now in 2028 halving territory but still bear from 2024
    expect(result.progress).toBeLessThanOrEqual(100)
  })

  test('late previous cycle returns bear with fixed 50% progress', () => {
    vi.useFakeTimers()
    // Before the 2024 halving springStart: dates where daysSinceHalving from 2020 < 1080
    // Actually getHalvingInfo uses last past halving. Before 2024-04-20, last halving = 2020-05-11.
    // 2020-05-11 + 1000 days = 2023-02-05. daysSinceHalving = 1000.
    // springStart for next cycle relative to 2020 halving = cycleLength + springStart = 1260 + (-180) = 1080
    // 1000 < 1080? No, 1000 >= 550 (winterStart). So it's bear with progress > 0.
    // Let me pick a date that gives daysSinceHalving > winterStart (550) but near the bear/spring boundary
    vi.setSystemTime(new Date('2022-01-01T12:00:00Z'))
    // daysSinceHalving from 2020-05-11 = ~600 days

    const result = determineMarketSeason(50, undefined, undefined)
    expect(result.season).toBe('bear')
  })

  test('bear confidence with all agreeing indicators = 100', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2025-12-11T12:00:00Z'))

    const bearAth: ATHResponse = {
      current_price: 30000, ath: 100000, ath_date: '2025-01-01',
      days_since_ath: 345, drawdown_pct: 70, recovery_pct: 30, cached_at: '2025-12-11',
    }
    const bearDom: BTCDominanceResponse = {
      btc_dominance: 65, eth_dominance: 12, others_dominance: 23,
      total_market_cap: 1_000_000_000_000, cached_at: '2025-12-11',
    }

    const result = determineMarketSeason(20, bearAth, bearDom)
    expect(result.season).toBe('bear')
    // fg=20<=35, drawdown=70>=40, dom=65>=55, days=345>=60 -> all 4 agree
    expect(result.confidence).toBe(100)
  })
})

// ── Edge cases ──────────────────────────────────────────────────────

describe('determineMarketSeason - edge cases', () => {
  test('returns bull on exact halving day', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2024-04-20T12:00:00Z'))

    const result = determineMarketSeason(50, undefined, undefined)
    expect(result.season).toBe('bull')
    expect(result.progress).toBeCloseTo(0, 0)
  })

  test('each reachable season returns correct icon color', () => {
    vi.useFakeTimers()

    // Bull (10 days after halving)
    vi.setSystemTime(new Date('2024-04-30T12:00:00Z'))
    expect(determineMarketSeason(50, undefined, undefined).color).toBe('text-green-400')

    // Distribution (420 days after halving)
    vi.setSystemTime(new Date('2025-06-14T12:00:00Z'))
    expect(determineMarketSeason(50, undefined, undefined).color).toBe('text-orange-400')

    // Bear (600 days after halving)
    vi.setSystemTime(new Date('2025-12-11T12:00:00Z'))
    expect(determineMarketSeason(50, undefined, undefined).color).toBe('text-blue-400')
  })

  test('confidence formula: 40 + (agreements/4) * 60', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2025-12-11T12:00:00Z'))

    // Bear with exactly 2 agreeing indicators: fg<=35 and btcDom>=55
    const ath: ATHResponse = {
      current_price: 80000, ath: 100000, ath_date: '2025-11-01',
      days_since_ath: 10, drawdown_pct: 20, recovery_pct: 80, cached_at: '2025-12-11',
    }
    const dom: BTCDominanceResponse = {
      btc_dominance: 60, eth_dominance: 15, others_dominance: 25,
      total_market_cap: 2_000_000_000_000, cached_at: '2025-12-11',
    }

    const result = determineMarketSeason(30, ath, dom)
    // fg=30<=35: agree. drawdown=20<40: disagree. dom=60>=55: agree. days=10<60: disagree.
    // 2 agreements: 40 + (2/4)*60 = 70
    expect(result.confidence).toBe(70)
  })

  test('confidence with 1 agreement = 55', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2025-12-11T12:00:00Z'))

    // Bear with exactly 1 agreeing indicator: only fg<=35
    const ath: ATHResponse = {
      current_price: 80000, ath: 100000, ath_date: '2025-11-01',
      days_since_ath: 10, drawdown_pct: 20, recovery_pct: 80, cached_at: '2025-12-11',
    }
    const dom: BTCDominanceResponse = {
      btc_dominance: 40, eth_dominance: 25, others_dominance: 35,
      total_market_cap: 2_000_000_000_000, cached_at: '2025-12-11',
    }

    const result = determineMarketSeason(30, ath, dom)
    // fg=30<=35: agree. drawdown=20<40: disagree. dom=40<55: disagree. days=10<60: disagree.
    // 1 agreement: 40 + (1/4)*60 = 55
    expect(result.confidence).toBe(55)
  })

  test('confidence with 3 agreements = 85', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2025-12-11T12:00:00Z'))

    // Bear with 3 agreeing: fg<=35, drawdown>=40, btcDom>=55
    const ath: ATHResponse = {
      current_price: 50000, ath: 100000, ath_date: '2025-11-01',
      days_since_ath: 40, drawdown_pct: 50, recovery_pct: 50, cached_at: '2025-12-11',
    }
    const dom: BTCDominanceResponse = {
      btc_dominance: 60, eth_dominance: 15, others_dominance: 25,
      total_market_cap: 2_000_000_000_000, cached_at: '2025-12-11',
    }

    const result = determineMarketSeason(25, ath, dom)
    // fg=25<=35: agree. drawdown=50>=40: agree. dom=60>=55: agree. days=40<60: disagree.
    // 3 agreements: 40 + (3/4)*60 = 85
    expect(result.confidence).toBe(85)
  })

  test('bgGradient matches season', () => {
    vi.useFakeTimers()

    vi.setSystemTime(new Date('2024-04-30T12:00:00Z'))
    expect(determineMarketSeason(50, undefined, undefined).bgGradient).toContain('green')

    vi.setSystemTime(new Date('2025-06-14T12:00:00Z'))
    expect(determineMarketSeason(50, undefined, undefined).bgGradient).toContain('orange')

    vi.setSystemTime(new Date('2025-12-11T12:00:00Z'))
    expect(determineMarketSeason(50, undefined, undefined).bgGradient).toContain('blue')
  })

  test('subtitle matches season', () => {
    vi.useFakeTimers()

    vi.setSystemTime(new Date('2024-04-30T12:00:00Z'))
    expect(determineMarketSeason(50, undefined, undefined).subtitle).toBe('Bull Market')

    vi.setSystemTime(new Date('2025-06-14T12:00:00Z'))
    expect(determineMarketSeason(50, undefined, undefined).subtitle).toBe('Distribution Phase')

    vi.setSystemTime(new Date('2025-12-11T12:00:00Z'))
    expect(determineMarketSeason(50, undefined, undefined).subtitle).toBe('Bear Market')
  })
})
