/**
 * Tests for useValidation hook.
 *
 * Verifies API call to validate-config, early exits (no product_ids, no budget),
 * and manual order sizing validation against exchange minimums.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useValidation } from './useValidation'
import type { BotFormData, ValidationWarning, ValidationError } from '../../../components/bots'

// ---------- Mocks ----------

vi.mock('../../../services/api', () => ({
  api: {
    post: vi.fn(),
  },
}))

import { api } from '../../../services/api'

// ---------- Helpers ----------

function createFormData(overrides: Partial<BotFormData> = {}): BotFormData {
  return {
    name: 'Test Bot',
    description: '',
    market_type: 'spot',
    strategy_type: 'dca_bot_v2',
    product_id: 'ETH-BTC',
    product_ids: ['ETH-BTC'],
    split_budget_across_pairs: false,
    reserved_btc_balance: 0,
    reserved_usd_balance: 0,
    budget_percentage: 0,
    check_interval_seconds: 300,
    strategy_config: {
      base_order_percentage: 5,
      safety_order_percentage: 3,
    },
    exchange_type: 'cex',
    ...overrides,
  }
}

// ---------- Suite ----------

describe('useValidation', () => {
  let setValidationWarnings: any
  let setValidationErrors: any

  beforeEach(() => {
    vi.restoreAllMocks()
    vi.mocked(api.post).mockReset()
    setValidationWarnings = vi.fn()
    setValidationErrors = vi.fn()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ---- validateBotConfig ----

  describe('validateBotConfig', () => {
    test('calls API with product_ids and strategy_config', async () => {
      const formData = createFormData()
      vi.mocked(api.post).mockResolvedValue({ data: { warnings: [] } })

      const { result } = renderHook(() =>
        useValidation({
          formData,
          setValidationWarnings,
          setValidationErrors,
          portfolio: null,
        }),
      )

      await act(async () => {
        await result.current.validateBotConfig()
      })

      expect(api.post).toHaveBeenCalledWith('/bots/validate-config', {
        product_ids: ['ETH-BTC'],
        strategy_config: formData.strategy_config,
      })
    })

    test('sets warnings from API response', async () => {
      const formData = createFormData()
      const warnings: ValidationWarning[] = [
        { product_id: 'ETH-BTC', issue: 'Budget too low', suggested_minimum_pct: 2.0, current_pct: 0.5 },
      ]
      vi.mocked(api.post).mockResolvedValue({ data: { warnings } })

      const { result } = renderHook(() =>
        useValidation({
          formData,
          setValidationWarnings,
          setValidationErrors,
          portfolio: null,
        }),
      )

      await act(async () => {
        await result.current.validateBotConfig()
      })

      expect(setValidationWarnings).toHaveBeenCalledWith(warnings)
    })

    test('clears warnings when API returns no warnings', async () => {
      const formData = createFormData()
      vi.mocked(api.post).mockResolvedValue({ data: {} })

      const { result } = renderHook(() =>
        useValidation({
          formData,
          setValidationWarnings,
          setValidationErrors,
          portfolio: null,
        }),
      )

      await act(async () => {
        await result.current.validateBotConfig()
      })

      expect(setValidationWarnings).toHaveBeenCalledWith([])
    })

    test('early exits and clears warnings when product_ids is empty', async () => {
      const formData = createFormData({ product_ids: [] })

      const { result } = renderHook(() =>
        useValidation({
          formData,
          setValidationWarnings,
          setValidationErrors,
          portfolio: null,
        }),
      )

      await act(async () => {
        await result.current.validateBotConfig()
      })

      expect(api.post).not.toHaveBeenCalled()
      expect(setValidationWarnings).toHaveBeenCalledWith([])
    })

    test('early exits when no budget percentage is configured', async () => {
      const formData = createFormData({
        strategy_config: {},
      })

      const { result } = renderHook(() =>
        useValidation({
          formData,
          setValidationWarnings,
          setValidationErrors,
          portfolio: null,
        }),
      )

      await act(async () => {
        await result.current.validateBotConfig()
      })

      expect(api.post).not.toHaveBeenCalled()
      expect(setValidationWarnings).toHaveBeenCalledWith([])
    })

    test('early exits when budget percentage is zero', async () => {
      const formData = createFormData({
        strategy_config: {
          base_order_percentage: 0,
          safety_order_percentage: 0,
          initial_budget_percentage: 0,
        },
      })

      const { result } = renderHook(() =>
        useValidation({
          formData,
          setValidationWarnings,
          setValidationErrors,
          portfolio: null,
        }),
      )

      await act(async () => {
        await result.current.validateBotConfig()
      })

      expect(api.post).not.toHaveBeenCalled()
    })

    test('clears warnings and logs error on API failure', async () => {
      const formData = createFormData()
      vi.mocked(api.post).mockRejectedValue(new Error('Network error'))
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

      const { result } = renderHook(() =>
        useValidation({
          formData,
          setValidationWarnings,
          setValidationErrors,
          portfolio: null,
        }),
      )

      await act(async () => {
        await result.current.validateBotConfig()
      })

      expect(setValidationWarnings).toHaveBeenCalledWith([])
      expect(consoleSpy).toHaveBeenCalled()
    })
  })

  // ---- validateManualOrderSizing ----

  describe('validateManualOrderSizing', () => {
    test('clears errors when use_manual_sizing is not enabled', () => {
      const formData = createFormData({
        strategy_config: { use_manual_sizing: false },
      })

      const { result } = renderHook(() =>
        useValidation({
          formData,
          setValidationWarnings,
          setValidationErrors,
          portfolio: null,
        }),
      )

      act(() => {
        result.current.validateManualOrderSizing()
      })

      expect(setValidationErrors).toHaveBeenCalledWith([])
    })

    test('reports error when BTC base_order_value is below minimum', () => {
      const formData = createFormData({
        product_ids: ['ETH-BTC'],
        strategy_config: {
          use_manual_sizing: true,
          base_order_value: 0.001, // 0.001% of 1 BTC = 0.00001 BTC
        },
      })

      const portfolio = {
        balance_breakdown: { btc: { total: 1.0 } },
        total_usd_value: 50000,
      }

      const { result } = renderHook(() =>
        useValidation({
          formData,
          setValidationWarnings,
          setValidationErrors,
          portfolio,
        }),
      )

      act(() => {
        result.current.validateManualOrderSizing()
      })

      expect(setValidationErrors).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({
            field: 'base_order_value',
            minimum_required: 0.0001,
          }),
        ]),
      )
    })

    test('reports error when USD base_order_value is below minimum', () => {
      const formData = createFormData({
        product_ids: ['ETH-USD'],
        strategy_config: {
          use_manual_sizing: true,
          base_order_value: 0.0001, // 0.0001% of $50k = $0.05
        },
      })

      const portfolio = {
        total_usd_value: 50000,
      }

      const { result } = renderHook(() =>
        useValidation({
          formData,
          setValidationWarnings,
          setValidationErrors,
          portfolio,
        }),
      )

      act(() => {
        result.current.validateManualOrderSizing()
      })

      expect(setValidationErrors).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({
            field: 'base_order_value',
            minimum_required: 1.0,
          }),
        ]),
      )
    })

    test('reports error when DCA order value is below BTC minimum', () => {
      const formData = createFormData({
        product_ids: ['ETH-BTC'],
        strategy_config: {
          use_manual_sizing: true,
          dca_order_value: 0.001, // 0.001% of 0.5 BTC = 0.000005 BTC
        },
      })

      const portfolio = {
        balance_breakdown: { btc: { total: 0.5 } },
        total_usd_value: 25000,
      }

      const { result } = renderHook(() =>
        useValidation({
          formData,
          setValidationWarnings,
          setValidationErrors,
          portfolio,
        }),
      )

      act(() => {
        result.current.validateManualOrderSizing()
      })

      expect(setValidationErrors).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({
            field: 'dca_order_value',
          }),
        ]),
      )
    })

    test('no errors when order values are above minimums', () => {
      const formData = createFormData({
        product_ids: ['ETH-BTC'],
        strategy_config: {
          use_manual_sizing: true,
          base_order_value: 5, // 5% of 2 BTC = 0.1 BTC > 0.0001
          dca_order_value: 3,  // 3% of 2 BTC = 0.06 BTC > 0.0001
        },
      })

      const portfolio = {
        balance_breakdown: { btc: { total: 2.0 } },
        total_usd_value: 100000,
      }

      const { result } = renderHook(() =>
        useValidation({
          formData,
          setValidationWarnings,
          setValidationErrors,
          portfolio,
        }),
      )

      act(() => {
        result.current.validateManualOrderSizing()
      })

      expect(setValidationErrors).toHaveBeenCalledWith([])
    })

    test('validates both BTC and USD pairs simultaneously', () => {
      const formData = createFormData({
        product_ids: ['ETH-BTC', 'SOL-USD'],
        strategy_config: {
          use_manual_sizing: true,
          base_order_value: 0.0005, // Very small — will fail for both
        },
      })

      const portfolio = {
        balance_breakdown: { btc: { total: 0.01 } },
        total_usd_value: 100,
      }

      const { result } = renderHook(() =>
        useValidation({
          formData,
          setValidationWarnings,
          setValidationErrors,
          portfolio,
        }),
      )

      act(() => {
        result.current.validateManualOrderSizing()
      })

      // Should get two errors: one for BTC pairs, one for USD pairs
      const errors: ValidationError[] = setValidationErrors.mock.calls[0][0]
      expect(errors.length).toBe(2)
      expect(errors.some(e => e.message.includes('BTC'))).toBe(true)
      expect(errors.some(e => e.message.includes('$'))).toBe(true)
    })

    test('uses total_btc_value fallback when balance_breakdown is missing', () => {
      const formData = createFormData({
        product_ids: ['ETH-BTC'],
        strategy_config: {
          use_manual_sizing: true,
          base_order_value: 50, // 50% of 0.5 BTC = 0.25 BTC > 0.0001
        },
      })

      const portfolio = {
        total_btc_value: 0.5,
        total_usd_value: 25000,
      }

      const { result } = renderHook(() =>
        useValidation({
          formData,
          setValidationWarnings,
          setValidationErrors,
          portfolio,
        }),
      )

      act(() => {
        result.current.validateManualOrderSizing()
      })

      // Should be fine — 50% of 0.5 = 0.25 > 0.0001
      expect(setValidationErrors).toHaveBeenCalledWith([])
    })

    test('recognizes USDC and USDT as USD pairs', () => {
      const formData = createFormData({
        product_ids: ['ETH-USDC', 'SOL-USDT'],
        strategy_config: {
          use_manual_sizing: true,
          base_order_value: 0.0001, // Very small
        },
      })

      const portfolio = { total_usd_value: 100 }

      const { result } = renderHook(() =>
        useValidation({
          formData,
          setValidationWarnings,
          setValidationErrors,
          portfolio,
        }),
      )

      act(() => {
        result.current.validateManualOrderSizing()
      })

      // 0.0001% of $100 = $0.0001 — below $1 minimum
      const errors: ValidationError[] = setValidationErrors.mock.calls[0][0]
      expect(errors.length).toBeGreaterThan(0)
      expect(errors[0].minimum_required).toBe(1.0)
    })
  })
})
