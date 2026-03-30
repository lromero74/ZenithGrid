import { describe, it, expect } from 'vitest'
import { computeEffectiveAggregateValues } from './StrategyConfigSection'
import type { AggregateValue } from '../../../types'
import type { RebalanceStatus } from '../../../services/api'

// ─── Fixtures ────────────────────────────────────────────────────────────────

const AGGREGATE: AggregateValue = {
  aggregate_usd_value: 10000,
  aggregate_btc_value: 0.2,   // implies BTC price = 10000 / 0.2 = $50,000
  btc_usd_price: 50000,
}

function makeRebalanceStatus(overrides: Partial<RebalanceStatus> = {}): RebalanceStatus {
  return {
    account_id: 1,
    total_value_usd: 10000,
    deployable_value_usd: 9000,   // $1,000 reserved
    reserve_value_usd: 1000,
    rebalance_enabled: false,
    target_usd_pct: 50,
    target_btc_pct: 40,
    target_eth_pct: 5,
    target_usdc_pct: 5,
    current_usd_pct: 50,
    current_btc_pct: 40,
    current_eth_pct: 5,
    current_usdc_pct: 5,
    min_balance_usd: 500,
    min_balance_btc: 0.01,
    min_balance_eth: 0,
    min_balance_usdc: 0,
    reserve_usd_pct: 5,
    reserve_btc_pct: 5,
    reserve_eth_pct: 0,
    reserve_usdc_pct: 0,
    ...overrides,
  }
}

// ─── No rebalance status ──────────────────────────────────────────────────────

describe('computeEffectiveAggregateValues — no rebalanceStatus', () => {
  it('returns raw aggregate values unchanged', () => {
    const result = computeEffectiveAggregateValues('USD', AGGREGATE, undefined)
    expect(result.effectiveUsdValue).toBe(10000)
    expect(result.effectiveBtcValue).toBe(0.2)
  })
})

// ─── Rebalancer disabled, reserves still apply ────────────────────────────────

describe('computeEffectiveAggregateValues — rebalancer disabled, reserves set', () => {
  it('deducts USD reserve from USD-quoted bot', () => {
    const rs = makeRebalanceStatus({ rebalance_enabled: false, min_balance_usd: 500 })
    const result = computeEffectiveAggregateValues('USD', AGGREGATE, rs)
    expect(result.effectiveUsdValue).toBe(9500)  // 10000 - 500
    expect(result.effectiveBtcValue).toBe(0.2)   // unchanged
  })

  it('deducts BTC reserve from BTC-quoted bot', () => {
    const rs = makeRebalanceStatus({ rebalance_enabled: false, min_balance_btc: 0.01 })
    const result = computeEffectiveAggregateValues('BTC', AGGREGATE, rs)
    expect(result.effectiveBtcValue).toBeCloseTo(0.19)  // 0.2 - 0.01
    expect(result.effectiveUsdValue).toBe(10000)        // unchanged
  })

  it('clamps BTC effective value to 0 when reserve > balance', () => {
    const rs = makeRebalanceStatus({ rebalance_enabled: false, min_balance_btc: 0.5 })
    const result = computeEffectiveAggregateValues('BTC', AGGREGATE, rs)
    expect(result.effectiveBtcValue).toBe(0)
  })

  it('clamps USD effective value to 0 when reserve > balance', () => {
    const rs = makeRebalanceStatus({ rebalance_enabled: false, min_balance_usd: 99999 })
    const result = computeEffectiveAggregateValues('USD', AGGREGATE, rs)
    expect(result.effectiveUsdValue).toBe(0)
  })

  it('deducts USDC reserve for USDC-quoted bots', () => {
    const rs = makeRebalanceStatus({ rebalance_enabled: false, min_balance_usdc: 200 })
    const result = computeEffectiveAggregateValues('USDC', AGGREGATE, rs)
    expect(result.effectiveUsdValue).toBe(9800)  // 10000 - 200
  })
})

// ─── Rebalancer enabled — at target ──────────────────────────────────────────

describe('computeEffectiveAggregateValues — rebalancer enabled, at target', () => {
  it('USD bot: uses target % of deployable', () => {
    const rs = makeRebalanceStatus({
      rebalance_enabled: true,
      deployable_value_usd: 9000,
      target_usd_pct: 50,
      current_usd_pct: 50,
      total_value_usd: 10000,
    })
    // target = 9000 * 0.50 = 4500; current = 10000 * 0.50 = 5000 → min = 4500
    const result = computeEffectiveAggregateValues('USD', AGGREGATE, rs)
    expect(result.effectiveUsdValue).toBe(4500)
  })

  it('BTC bot: converts allocated USD to BTC using btc_usd_price', () => {
    const rs = makeRebalanceStatus({
      rebalance_enabled: true,
      deployable_value_usd: 9000,
      target_btc_pct: 40,
      current_btc_pct: 40,
      total_value_usd: 10000,
    })
    // target = 9000 * 0.40 = 3600; current = 10000 * 0.40 = 4000 → min = 3600
    // effectiveBtc = 3600 / 50000 = 0.072
    const result = computeEffectiveAggregateValues('BTC', AGGREGATE, rs)
    expect(result.effectiveBtcValue).toBeCloseTo(0.072)
    expect(result.effectiveUsdValue).toBeCloseTo(3600)
  })
})

// ─── Rebalancer enabled — target NOT yet reached (current < target) ───────────

describe('computeEffectiveAggregateValues — rebalancer enabled, target not reached', () => {
  it('USD bot: caps at current allocation when target > current', () => {
    const rs = makeRebalanceStatus({
      rebalance_enabled: true,
      deployable_value_usd: 9000,
      total_value_usd: 10000,
      target_usd_pct: 70,    // wants 70% in USD
      current_usd_pct: 50,   // only has 50% right now
    })
    // target = 9000 * 0.70 = 6300; current = 10000 * 0.50 = 5000 → min = 5000
    const result = computeEffectiveAggregateValues('USD', AGGREGATE, rs)
    expect(result.effectiveUsdValue).toBe(5000)
  })

  it('BTC bot: caps at current when target > current', () => {
    const rs = makeRebalanceStatus({
      rebalance_enabled: true,
      deployable_value_usd: 9000,
      total_value_usd: 10000,
      target_btc_pct: 60,    // wants 60%
      current_btc_pct: 30,   // only has 30%
    })
    // target = 9000 * 0.60 = 5400; current = 10000 * 0.30 = 3000 → min = 3000
    // effectiveBtc = 3000 / 50000 = 0.06
    const result = computeEffectiveAggregateValues('BTC', AGGREGATE, rs)
    expect(result.effectiveBtcValue).toBeCloseTo(0.06)
  })
})

// ─── Rebalancer enabled — overweight (current > target) ──────────────────────

describe('computeEffectiveAggregateValues — rebalancer enabled, overweight', () => {
  it('USD bot: uses target when current > target (constrains bot to help rebalance)', () => {
    const rs = makeRebalanceStatus({
      rebalance_enabled: true,
      deployable_value_usd: 9000,
      total_value_usd: 10000,
      target_usd_pct: 30,    // wants only 30%
      current_usd_pct: 60,   // currently has 60% (overweight)
    })
    // target = 9000 * 0.30 = 2700; current = 10000 * 0.60 = 6000 → min = 2700
    const result = computeEffectiveAggregateValues('USD', AGGREGATE, rs)
    expect(result.effectiveUsdValue).toBe(2700)
  })

  it('BTC bot: uses target when overweight', () => {
    const rs = makeRebalanceStatus({
      rebalance_enabled: true,
      deployable_value_usd: 9000,
      total_value_usd: 10000,
      target_btc_pct: 20,
      current_btc_pct: 50,
    })
    // target = 9000 * 0.20 = 1800; current = 10000 * 0.50 = 5000 → min = 1800
    const result = computeEffectiveAggregateValues('BTC', AGGREGATE, rs)
    expect(result.effectiveBtcValue).toBeCloseTo(1800 / 50000)
  })
})

// ─── Edge cases ───────────────────────────────────────────────────────────────

describe('computeEffectiveAggregateValues — edge cases', () => {
  it('returns zeros when aggregateData is undefined', () => {
    const result = computeEffectiveAggregateValues('USD', undefined, undefined)
    expect(result.effectiveUsdValue).toBe(0)
    expect(result.effectiveBtcValue).toBe(0)
  })

  it('does not divide by zero when btc_usd_price is 0', () => {
    const aggregate = { ...AGGREGATE, btc_usd_price: 0 }
    const rs = makeRebalanceStatus({ rebalance_enabled: true, target_btc_pct: 40, current_btc_pct: 40 })
    const result = computeEffectiveAggregateValues('BTC', aggregate, rs)
    expect(result.effectiveBtcValue).toBe(0)  // safe fallback
  })

  it('unknown quote currency falls back to USD target', () => {
    const rs = makeRebalanceStatus({
      rebalance_enabled: true,
      deployable_value_usd: 9000,
      total_value_usd: 10000,
      target_usd_pct: 50,
      current_usd_pct: 50,
    })
    const result = computeEffectiveAggregateValues('UNKNOWN', AGGREGATE, rs)
    // Falls back to USD target: 9000*0.50=4500 vs current 10000*0.50=5000 → 4500
    expect(result.effectiveUsdValue).toBe(4500)
  })
})
