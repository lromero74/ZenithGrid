/**
 * Sample Bots inventory tests.
 *
 * The user-facing "Sample Bots" section on /bots reads from this array. Each
 * entry flows through Bots.tsx::handleSampleCopy → setFormData, then into the
 * Create Bot modal form — from there the user clicks Save and the backend's
 * preset-merger fills in anything the sample left unset.
 *
 * Tests below focus on the speculative sample shipped with the
 * high-risk-doubling preset feature, since the sample is users' primary
 * entry point into that flow.
 */

import { describe, it, expect } from 'vitest'
import { SAMPLE_BOTS } from './sampleBots'

describe('SAMPLE_BOTS — speculative catalyst hunter', () => {
  const spec = SAMPLE_BOTS.find(b => b.id === 'speculative-catalyst-usd')

  it('exists', () => {
    expect(spec).toBeDefined()
  })

  it('is wired for the indicator_based strategy on the USD market', () => {
    expect(spec?.market).toBe('USD')
    expect(spec?.strategy_type).toBe('indicator_based')
    // Speculative hunts live across all USD pairs — the copy flow resolves
    // product_ids at copy time via selectAllMarket.
    expect(spec?.selectAllMarket).toBe('USD')
  })

  it('carries ai_risk_preset=speculative so backend preset-merger fills defaults on save', () => {
    const cfg = spec?.formData.strategy_config as Record<string, unknown>
    expect(cfg?.ai_risk_preset).toBe('speculative')
  })

  it('tags the bot into the shared account bucket at preview time', () => {
    // is_speculative must be the string "true" — PG-vs-SQLite JSON bool extraction
    // difference. See speculative_bucket_service._speculative_bot_filter docstring.
    const cfg = spec?.formData.strategy_config as Record<string, unknown>
    expect(cfg?.is_speculative).toBe('true')
  })

  it('includes at least one ai_opinion buy condition so catalyst-mode AI runs', () => {
    const cfg = spec?.formData.strategy_config as Record<string, unknown>
    const boc = cfg?.base_order_conditions as { groups: Array<{ conditions: Array<{ type: string }> }> }
    const allConditions = boc?.groups?.flatMap(g => g.conditions) ?? []
    const hasAiOpinion = allConditions.some(c => c.type === 'ai_opinion')
    expect(hasAiOpinion).toBe(true)
  })

  it('shows the speculative bracket discipline at preview time', () => {
    const cfg = spec?.formData.strategy_config as Record<string, unknown>
    expect(cfg?.stop_loss_enabled).toBe(true)
    expect(cfg?.stop_loss_percentage).toBe(-12)
    expect(cfg?.take_profit_percentage).toBe(25)
    expect(cfg?.trailing_take_profit).toBe(true)
    expect(cfg?.max_safety_orders).toBe(0)
    expect(cfg?.speculative_max_hold_hours).toBe(24)
  })

  it('does NOT get picked up as just another sample — the HIGH RISK tag in description must be preserved', () => {
    // The description is the user's only warning before they click Copy.
    expect(spec?.description).toMatch(/HIGH RISK/)
    expect(spec?.description).toMatch(/under 20%/)
  })
})
