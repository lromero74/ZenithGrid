import type { ISeriesApi } from 'lightweight-charts'
import type { Position } from '../../types'

// Fee adjustment for profit targets
// Coinbase Advanced Trade taker fee is ~0.6% (0.006)
// To achieve X% NET profit after sell fees: gross_target = (1 + X%) / (1 - sell_fee)
export const SELL_FEE_RATE = 0.006 // 0.6% Coinbase taker fee

// Helper to calculate fee-adjusted profit target multiplier
export const getFeeAdjustedProfitMultiplier = (desiredNetProfitPercent: number): number => {
  const netMultiplier = 1 + (desiredNetProfitPercent / 100)
  return netMultiplier / (1 - SELL_FEE_RATE)
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
