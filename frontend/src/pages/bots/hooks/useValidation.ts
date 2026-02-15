import { useCallback } from 'react'
import { api } from '../../../services/api'
import type { BotFormData, ValidationWarning, ValidationError } from '../../../components/bots'

interface UseValidationProps {
  formData: BotFormData
  setValidationWarnings: (warnings: ValidationWarning[]) => void
  setValidationErrors: (errors: ValidationError[]) => void
  portfolio: any
}

export function useValidation({
  formData,
  setValidationWarnings,
  setValidationErrors,
  portfolio
}: UseValidationProps) {
  // Validate bot configuration against Coinbase minimum order sizes
  const validateBotConfig = useCallback(async () => {
    // Only validate if we have products and strategy config
    if (formData.product_ids.length === 0 || !formData.strategy_config) {
      setValidationWarnings([])
      return
    }

    // Skip if no budget percentage configured
    const budgetPct = formData.strategy_config.base_order_percentage ||
                      formData.strategy_config.safety_order_percentage ||
                      formData.strategy_config.initial_budget_percentage
    if (!budgetPct || budgetPct === 0) {
      setValidationWarnings([])
      return
    }

    try {
      const response = await api.post('/bots/validate-config', {
        product_ids: formData.product_ids,
        strategy_config: formData.strategy_config
      })

      if (response.data.warnings) {
        setValidationWarnings(response.data.warnings)
      } else {
        setValidationWarnings([])
      }
    } catch (error) {
      console.error('Validation error:', error)
      setValidationWarnings([])
    }
  }, [formData.product_ids, formData.strategy_config, setValidationWarnings])

  // Validate manual order sizing values against exchange minimums
  const validateManualOrderSizing = useCallback(() => {
    const errors: ValidationError[] = []

    // Only validate if manual sizing mode is enabled
    if (!formData.strategy_config.use_manual_sizing) {
      setValidationErrors([])
      return
    }

    // Get aggregate portfolio value from portfolio data
    // For BTC pairs, use aggregate BTC value; for USD pairs, use aggregate USD value
    const hasBtcPairs = formData.product_ids.some(p => p.endsWith('-BTC'))
    const hasUsdPairs = formData.product_ids.some(p => p.endsWith('-USD') || p.endsWith('-USDC') || p.endsWith('-USDT'))

    // Exchange minimums
    const BTC_MINIMUM = 0.0001  // Coinbase minimum for BTC pairs
    const USD_MINIMUM = 1.0     // Coinbase minimum for USD pairs (roughly)

    if (portfolio) {
      // Use balance_breakdown.btc.total which is the true aggregate (free + in positions)
      const aggregateBtc = portfolio.balance_breakdown?.btc?.total || portfolio.total_btc_value || 0
      const aggregateUsd = portfolio.total_usd_value || 0

      // Validate base_order_value
      const baseOrderPct = formData.strategy_config.base_order_value
      if (baseOrderPct && baseOrderPct > 0) {
        if (hasBtcPairs) {
          const calculatedBtc = aggregateBtc * (baseOrderPct / 100)
          if (calculatedBtc < BTC_MINIMUM) {
            errors.push({
              field: 'base_order_value',
              message: `Base Order Value (${baseOrderPct}%) calculates to ${calculatedBtc.toFixed(8)} BTC, which is below Coinbase's minimum of ${BTC_MINIMUM} BTC`,
              calculated_value: calculatedBtc,
              minimum_required: BTC_MINIMUM
            })
          }
        }
        if (hasUsdPairs) {
          const calculatedUsd = aggregateUsd * (baseOrderPct / 100)
          if (calculatedUsd < USD_MINIMUM) {
            errors.push({
              field: 'base_order_value',
              message: `Base Order Value (${baseOrderPct}%) calculates to $${calculatedUsd.toFixed(2)}, which is below Coinbase's minimum of $${USD_MINIMUM}`,
              calculated_value: calculatedUsd,
              minimum_required: USD_MINIMUM
            })
          }
        }
      }

      // Validate dca_order_value
      const dcaOrderPct = formData.strategy_config.dca_order_value
      if (dcaOrderPct && dcaOrderPct > 0) {
        if (hasBtcPairs) {
          const calculatedBtc = aggregateBtc * (dcaOrderPct / 100)
          if (calculatedBtc < BTC_MINIMUM) {
            errors.push({
              field: 'dca_order_value',
              message: `DCA Order Value (${dcaOrderPct}%) calculates to ${calculatedBtc.toFixed(8)} BTC, which is below Coinbase's minimum of ${BTC_MINIMUM} BTC`,
              calculated_value: calculatedBtc,
              minimum_required: BTC_MINIMUM
            })
          }
        }
        if (hasUsdPairs) {
          const calculatedUsd = aggregateUsd * (dcaOrderPct / 100)
          if (calculatedUsd < USD_MINIMUM) {
            errors.push({
              field: 'dca_order_value',
              message: `DCA Order Value (${dcaOrderPct}%) calculates to $${calculatedUsd.toFixed(2)}, which is below Coinbase's minimum of $${USD_MINIMUM}`,
              calculated_value: calculatedUsd,
              minimum_required: USD_MINIMUM
            })
          }
        }
      }
    }

    setValidationErrors(errors)
  }, [formData.product_ids, formData.strategy_config, portfolio, setValidationErrors])

  return {
    validateBotConfig,
    validateManualOrderSizing
  }
}
