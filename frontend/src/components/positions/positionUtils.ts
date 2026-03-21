import type { ISeriesApi } from 'lightweight-charts'
import type { Position } from '../../types'

// Fee adjustment for profit targets
// Default taker fee rate — varies by exchange:
//   Coinbase: ~0.6%, ByBit: ~0.1%, MT5: commission-based
// To achieve X% NET profit after sell fees: gross_target = (1 + X%) / (1 - sell_fee)
export const SELL_FEE_RATE = 0.006 // Default (Coinbase) taker fee

// Exchange-specific fee rates
export const EXCHANGE_FEE_RATES: Record<string, number> = {
  coinbase: 0.006,
  bybit: 0.001,
  mt5_bridge: 0.0005,
}

export const getSellFeeRate = (exchange?: string): number =>
  EXCHANGE_FEE_RATES[exchange || 'coinbase'] ?? SELL_FEE_RATE

// Helper to calculate fee-adjusted profit target multiplier
export const getFeeAdjustedProfitMultiplier = (
  desiredNetProfitPercent: number,
  exchange?: string
): number => {
  const feeRate = getSellFeeRate(exchange)
  const netMultiplier = 1 + (desiredNetProfitPercent / 100)
  return netMultiplier / (1 - feeRate)
}

// Get take profit percentage from position config (frozen at position open) or bot config
export const getTakeProfitPercent = (
  position: Position,
  bot: { strategy_config?: Record<string, unknown> } | null | undefined
): number => {
  return position.strategy_config_snapshot?.take_profit_percentage
    ?? position.strategy_config_snapshot?.min_profit_percentage
    ?? bot?.strategy_config?.take_profit_percentage
    ?? bot?.strategy_config?.min_profit_percentage
    ?? 2.0 // Default 2% if not configured
}

export interface IndicatorConfig {
  id: string
  name: string
  type: string
  enabled: boolean
  settings: Record<string, unknown>
  color?: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  series?: ISeriesApi<any>[]
}

// Utility functions for price formatting
export const getQuoteCurrency = (productId: string) => {
  const quote = productId?.split('-')[1] || 'BTC'
  return {
    symbol: quote,
    decimals: quote === 'USD' ? 2 : 8
  }
}

export const getBaseCurrency = (productId: string) => {
  const base = productId?.split('-')[0] || 'ETH'
  return {
    symbol: base,
    decimals: 6  // Most altcoins use 6 decimals for display
  }
}

export const formatPrice = (price: number, productId: string = 'ETH-BTC') => {
  const { symbol, decimals } = getQuoteCurrency(productId)
  if (symbol === 'USD') {
    return `$${price.toFixed(decimals)}`
  }
  return `${price.toFixed(decimals)} ${symbol}`
}

export const formatBaseAmount = (amount: number, productId: string = 'ETH-BTC') => {
  const { symbol, decimals } = getBaseCurrency(productId)
  return `${amount.toFixed(decimals)} ${symbol}`
}

export const formatQuoteAmount = (amount: number, productId: string) => {
  const { symbol, decimals } = getQuoteCurrency(productId)
  return `${amount.toFixed(decimals)} ${symbol}`
}

// ─── Safety Order Level Calculation ──────────────────────────────────────────
// Mirrors backend: indicator_based.py _get_dca_reference_price() +
// calculate_safety_order_price(). Used by chart to draw accurate SO lines.

export interface SOLevel {
  soNumber: number      // Absolute SO number (1-based, from start of deal)
  triggerPrice: number
}

/**
 * Calculate remaining unfilled safety order trigger prices for a position.
 *
 * Uses strategy_config_snapshot so lines match the FROZEN config at deal open,
 * not the current bot settings. Respects dca_target_reference, step_scale
 * (geometric spacing), and skips SOs already filled (trade_count - 1).
 */
export function calculateSOLevels(position: Position): SOLevel[] {
  const cfg = position.strategy_config_snapshot
  if (!cfg) return []

  const priceDeviation: number = cfg.price_deviation
  const maxSafetyOrders: number = cfg.max_safety_orders
  if (!priceDeviation || !maxSafetyOrders) return []

  const stepScale: number = cfg.safety_order_step_scale ?? 1.0
  const dcaReference: string = cfg.dca_target_reference ?? 'average_price'
  const direction: string = position.direction ?? 'long'

  // Pick reference price per dca_target_reference config
  let referencePrice: number
  if (dcaReference === 'base_order') {
    referencePrice = position.first_buy_price ?? position.average_buy_price
  } else if (dcaReference === 'last_buy') {
    referencePrice = position.last_buy_price ?? position.average_buy_price
  } else {
    referencePrice = position.average_buy_price
  }
  if (!referencePrice) return []

  // trade_count includes base order; remaining are SO fills
  const safetyOrdersFilled = Math.max(0, (position.trade_count ?? 1) - 1)

  const levels: SOLevel[] = []
  for (let soNum = safetyOrdersFilled + 1; soNum <= maxSafetyOrders; soNum++) {
    let totalDeviation: number
    if (stepScale === 1.0) {
      totalDeviation = priceDeviation * soNum
    } else {
      totalDeviation = priceDeviation * (Math.pow(stepScale, soNum) - 1) / (stepScale - 1)
    }

    const triggerPrice = direction === 'long'
      ? referencePrice * (1 - totalDeviation / 100)
      : referencePrice * (1 + totalDeviation / 100)

    levels.push({ soNumber: soNum, triggerPrice })
  }
  return levels
}
