/**
 * Tests for pages/bots/helpers.ts
 *
 * Tests bot indicator detection helpers.
 */

import { describe, test, expect } from 'vitest'
import {
  conditionUsesAI,
  botUsesAIIndicators,
  botUsesBullFlagIndicator,
  botUsesNonAIIndicators,
} from './helpers'

describe('conditionUsesAI', () => {
  test('returns true for ai_buy type', () => {
    expect(conditionUsesAI({ type: 'ai_buy' })).toBe(true)
  })

  test('returns true for ai_sell indicator', () => {
    expect(conditionUsesAI({ indicator: 'ai_sell' })).toBe(true)
  })

  test('returns false for rsi', () => {
    expect(conditionUsesAI({ type: 'rsi' })).toBe(false)
  })

  test('returns false for empty object', () => {
    expect(conditionUsesAI({})).toBe(false)
  })
})

describe('botUsesAIIndicators', () => {
  test('returns true for ai_autonomous strategy', () => {
    const bot = { strategy_type: 'ai_autonomous', strategy_config: {} } as any
    expect(botUsesAIIndicators(bot)).toBe(true)
  })

  test('returns true when base_order_conditions has ai_buy', () => {
    const bot = {
      strategy_type: 'indicator_based',
      strategy_config: {
        base_order_conditions: [{ type: 'ai_buy' }],
      },
    } as any
    expect(botUsesAIIndicators(bot)).toBe(true)
  })

  test('returns true for grouped conditions format', () => {
    const bot = {
      strategy_type: 'indicator_based',
      strategy_config: {
        base_order_conditions: {
          groups: [{ conditions: [{ type: 'ai_buy' }] }],
        },
      },
    } as any
    expect(botUsesAIIndicators(bot)).toBe(true)
  })

  test('returns false for non-AI bot', () => {
    const bot = {
      strategy_type: 'dca',
      strategy_config: {
        base_order_conditions: [{ type: 'rsi' }],
      },
    } as any
    expect(botUsesAIIndicators(bot)).toBe(false)
  })

  test('returns false when no config', () => {
    const bot = { strategy_type: 'dca', strategy_config: null } as any
    expect(botUsesAIIndicators(bot)).toBe(false)
  })
})

describe('botUsesBullFlagIndicator', () => {
  test('returns true for bull_flag strategy type', () => {
    const bot = { strategy_type: 'bull_flag', strategy_config: {} } as any
    expect(botUsesBullFlagIndicator(bot)).toBe(true)
  })

  test('returns true when conditions have bull_flag', () => {
    const bot = {
      strategy_type: 'indicator_based',
      strategy_config: {
        base_order_conditions: [{ type: 'bull_flag' }],
      },
    } as any
    expect(botUsesBullFlagIndicator(bot)).toBe(true)
  })

  test('returns false for non-bull-flag bot', () => {
    const bot = {
      strategy_type: 'dca',
      strategy_config: { base_order_conditions: [{ type: 'rsi' }] },
    } as any
    expect(botUsesBullFlagIndicator(bot)).toBe(false)
  })

  test('returns false when no config', () => {
    const bot = { strategy_type: 'dca', strategy_config: null } as any
    expect(botUsesBullFlagIndicator(bot)).toBe(false)
  })
})

describe('botUsesNonAIIndicators', () => {
  test('returns true for indicator_based with non-AI conditions', () => {
    const bot = {
      strategy_type: 'indicator_based',
      strategy_config: {
        base_order_conditions: [{ type: 'rsi' }],
      },
    } as any
    expect(botUsesNonAIIndicators(bot)).toBe(true)
  })

  test('returns false for AI-based indicator bot', () => {
    const bot = {
      strategy_type: 'indicator_based',
      strategy_config: {
        base_order_conditions: [{ type: 'ai_buy' }],
      },
    } as any
    expect(botUsesNonAIIndicators(bot)).toBe(false)
  })

  test('returns false for non-indicator strategy', () => {
    const bot = {
      strategy_type: 'dca',
      strategy_config: {
        base_order_conditions: [{ type: 'rsi' }],
      },
    } as any
    expect(botUsesNonAIIndicators(bot)).toBe(false)
  })

  test('handles grouped conditions format', () => {
    const bot = {
      strategy_type: 'indicator_based',
      strategy_config: {
        base_order_conditions: {
          groups: [{ conditions: [{ type: 'rsi' }] }],
        },
      },
    } as any
    expect(botUsesNonAIIndicators(bot)).toBe(true)
  })
})
