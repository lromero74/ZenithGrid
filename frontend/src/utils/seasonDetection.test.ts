import { determineMarketSeason } from './seasonDetection'
import type { ATHResponse, BTCDominanceResponse } from '../types'

// ── determineMarketSeason ────────────────────────────────────────────

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
    // All 4 bear checks should agree → confidence = 40 + (4/4)*60 = 100
    expect(result.confidence).toBeGreaterThan(40)
    expect(result.season).toBe('bear')
  })

  test('first signal is always cycle position', () => {
    const result = determineMarketSeason(50, undefined, undefined)
    // First signal should contain halving cycle info
    expect(result.signals[0]).toMatch(/days|halving|cycle/i)
  })
})
