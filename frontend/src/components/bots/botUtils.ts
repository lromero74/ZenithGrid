import { StrategyParameter, AggregateValue } from '../../types'
import { RebalanceStatus } from '../../services/api'

export interface BotFormData {
  name: string
  description: string
  market_type: 'spot' | 'perps'  // Spot or perpetual futures
  strategy_type: string
  product_id: string  // Legacy - kept for backward compatibility
  product_ids: string[]  // Multi-pair support
  split_budget_across_pairs: boolean  // Budget splitting toggle
  reserved_btc_balance: number | undefined  // BTC allocated to this bot (legacy)
  reserved_usd_balance: number | undefined  // USD allocated to this bot (legacy)
  budget_percentage: number | undefined  // % of aggregate portfolio value (preferred)
  check_interval_seconds: number | undefined  // How often bot monitors positions
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  strategy_config: Record<string, any>
  // DEX-specific fields
  exchange_type: 'cex' | 'dex'  // Exchange type
  chain_id?: number  // Blockchain ID (1=Ethereum, 56=BSC, 137=Polygon, 42161=Arbitrum)
  dex_router?: string  // DEX router contract address
  wallet_private_key?: string  // Wallet private key for DEX
  rpc_url?: string  // RPC endpoint URL
  // Bot Budget Rebalancer
  bot_rebalancer_enabled?: boolean  // Participating in the bot budget rebalancer
  bot_rebalancer_target_pct?: number  // Target allocation % set by rebalancer slider
}

export interface ValidationWarning {
  product_id: string
  issue: string
  suggested_minimum_pct: number
  current_pct: number
}

export interface ValidationError {
  field: string
  message: string
  calculated_value: number
  minimum_required: number
}

export interface TradingPair {
  value: string
  label: string
  group: string
  base: string
}

export const getDefaultFormData = (): BotFormData => ({
  name: '',
  description: '',
  market_type: 'spot',
  strategy_type: '',
  product_id: 'ETH-BTC',  // Legacy fallback
  product_ids: [],  // Start with empty array, user will select
  split_budget_across_pairs: false,  // Default to independent budgets (deal-based allocation)
  reserved_btc_balance: 0,  // No reserved balance by default
  reserved_usd_balance: 0,  // No reserved balance by default
  budget_percentage: 0,  // No budget percentage by default
  check_interval_seconds: 300,  // Default: 5 minutes
  strategy_config: {},
  // DEX fields - default to CEX
  exchange_type: 'cex',
  chain_id: undefined,
  dex_router: undefined,
  wallet_private_key: undefined,
  rpc_url: undefined,
})

// Popularity order for sorting trading pairs (by market cap / trading volume)
export const POPULARITY_ORDER = [
  'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA', 'AVAX', 'LINK', 'DOT',
  'MATIC', 'UNI', 'LTC', 'ATOM', 'XLM', 'ALGO', 'AAVE', 'COMP', 'MKR',
  'SNX', 'CRV', 'SUSHI', 'YFI', '1INCH', 'BAT', 'ZRX', 'ENJ', 'MANA',
  'GRT', 'FIL', 'ICP', 'VET', 'FTM', 'SAND', 'AXS', 'GALA', 'CHZ'
]

// Default trading pairs fallback while loading
export const DEFAULT_TRADING_PAIRS: TradingPair[] = [
  { value: 'BTC-USD', label: 'BTC/USD', group: 'USD', base: 'BTC' },
  { value: 'ETH-USD', label: 'ETH/USD', group: 'USD', base: 'ETH' },
  { value: 'ETH-BTC', label: 'ETH/BTC', group: 'BTC', base: 'ETH' },
]

// Exchange minimum order sizes
export const EXCHANGE_MINIMUMS = {
  BTC: 0.0001, // 0.0001 BTC minimum for BTC pairs
  USD: 1.0, // $1 minimum for USD pairs
  USDC: 1.0, // $1 minimum for USDC pairs
  USDT: 1.0, // $1 minimum for USDT pairs
  EUR: 1.0, // 1 EUR minimum for EUR pairs
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const convertProductsToTradingPairs = (products: any[]): TradingPair[] => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const pairs = products.map((product: any) => {
    const base = product.base_currency
    const quote = product.quote_currency
    // Group by quote currency type
    const group = quote === 'USD' ? 'USD' : quote === 'USDT' ? 'USDT' : quote === 'USDC' ? 'USDC' : 'BTC'

    return {
      value: product.product_id,
      label: `${base}/${quote}`,
      group,
      base
    }
  })

  // Sort by: 1) group, 2) popularity order
  return pairs.sort((a: TradingPair, b: TradingPair) => {
    // Group priority: BTC > USD > USDC > USDT > others
    const groupOrder: Record<string, number> = { 'BTC': 1, 'USD': 2, 'USDC': 3, 'USDT': 4 }
    const aGroupPriority = groupOrder[a.group] || 99
    const bGroupPriority = groupOrder[b.group] || 99

    if (aGroupPriority !== bGroupPriority) {
      return aGroupPriority - bGroupPriority
    }

    // Within same group, sort by popularity
    const aPopularity = POPULARITY_ORDER.indexOf(a.base)
    const bPopularity = POPULARITY_ORDER.indexOf(b.base)
    const aRank = aPopularity === -1 ? 999 : aPopularity
    const bRank = bPopularity === -1 ? 999 : bPopularity

    if (aRank !== bRank) {
      return aRank - bRank
    }

    // If both unlisted, sort alphabetically
    return a.label.localeCompare(b.label)
  })
}

// Check if parameter should be visible based on visible_when condition
// and paper_trading_only flag
export const isParameterVisible = (
  param: StrategyParameter,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  strategyConfig: Record<string, any>,
  isPaperTrading?: boolean,
): boolean => {
  // Hide paper-trading-only params on live accounts
  if (param.paper_trading_only && !isPaperTrading) return false

  if (!param.visible_when) return true

  // Check each condition in visible_when
  return Object.entries(param.visible_when).every(([key, value]) => {
    const currentValue = strategyConfig[key]
    return currentValue === value
  })
}

/**
 * Compute the effective aggregate values for DCA budget calculations,
 * accounting for configured reserves and rebalancer target allocations.
 */
export function computeEffectiveAggregateValues(
  quoteCurrency: string,
  aggregateData: AggregateValue | undefined,
  rebalanceStatus: RebalanceStatus | undefined
): { effectiveUsdValue: number; effectiveBtcValue: number } {
  const rawUsd = aggregateData?.aggregate_usd_value ?? 0
  const rawBtc = aggregateData?.aggregate_btc_value ?? 0
  const btcPrice = aggregateData?.btc_usd_price ?? 0

  if (!rebalanceStatus) {
    return { effectiveUsdValue: rawUsd, effectiveBtcValue: rawBtc }
  }

  const quote = quoteCurrency.toUpperCase()

  if (rebalanceStatus.rebalance_enabled) {
    // Deployable value already has ALL reserves deducted
    const deployable = rebalanceStatus.deployable_value_usd
    const total = rebalanceStatus.total_value_usd

    // Pick target and current allocation % for this currency
    let targetPct = 0
    let currentPct = 0
    if (quote === 'USD') {
      targetPct = rebalanceStatus.target_usd_pct
      currentPct = rebalanceStatus.current_usd_pct
    } else if (quote === 'BTC') {
      targetPct = rebalanceStatus.target_btc_pct
      currentPct = rebalanceStatus.current_btc_pct
    } else if (quote === 'ETH') {
      targetPct = rebalanceStatus.target_eth_pct
      currentPct = rebalanceStatus.current_eth_pct
    } else if (quote === 'USDC') {
      targetPct = rebalanceStatus.target_usdc_pct
      currentPct = rebalanceStatus.current_usdc_pct
    } else if (quote === 'USDT') {
      targetPct = rebalanceStatus.target_usdt_pct
      currentPct = rebalanceStatus.current_usdt_pct
    } else {
      targetPct = rebalanceStatus.target_usd_pct
      currentPct = rebalanceStatus.current_usd_pct
    }

    // Cap at the lesser of target and current allocation:
    // if the rebalance target hasn't been reached yet, use current
    // (can't deploy capital that isn't in this currency yet)
    const targetUsd = (deployable * targetPct) / 100
    const currentUsd = (total * currentPct) / 100
    const allocatedUsd = Math.min(targetUsd, currentUsd)

    if (quote === 'BTC') {
      return {
        effectiveUsdValue: allocatedUsd,
        effectiveBtcValue: btcPrice > 0 ? allocatedUsd / btcPrice : 0,
      }
    }
    return { effectiveUsdValue: allocatedUsd, effectiveBtcValue: rawBtc }
  }

  // Rebalancer disabled — subtract only the relevant reserve
  if (quote === 'BTC') {
    const reserve = rebalanceStatus.min_balance_btc ?? 0
    return {
      effectiveUsdValue: rawUsd,
      effectiveBtcValue: Math.max(0, rawBtc - reserve),
    }
  }

  // USD / USDC / USDT / default
  let reserveUsd = 0
  if (quote === 'USDC') {
    reserveUsd = rebalanceStatus.min_balance_usdc ?? 0
  } else if (quote === 'USDT') {
    reserveUsd = rebalanceStatus.min_balance_usdt ?? 0
  } else {
    reserveUsd = rebalanceStatus.min_balance_usd ?? 0
  }

  return {
    effectiveUsdValue: Math.max(0, rawUsd - reserveUsd),
    effectiveBtcValue: rawBtc,
  }
}

/**
 * Helper to calculate total capital multiplier for one full DCA cycle.
 */
export function getDCAMultiplier(config: Record<string, any>): number {
  const maxSafetyOrders = config.max_safety_orders || 0
  if (maxSafetyOrders <= 0) return 1.0

  const volumeScale = config.safety_order_volume_scale || 1.0
  const safetyOrderType = config.safety_order_type || 'percentage_of_base'

  if (safetyOrderType === 'percentage_of_base') {
    const soPercentage = (config.safety_order_percentage || 50.0) / 100.0
    if (volumeScale === 1.0) {
      return 1.0 + soPercentage * maxSafetyOrders
    } else {
      return (
        1.0 +
        (soPercentage * (Math.pow(volumeScale, maxSafetyOrders) - 1)) /
          (volumeScale - 1)
      )
    }
  } else if (safetyOrderType === 'fixed' || safetyOrderType === 'fixed_btc') {
    // Base (1.0) + SO1 (1.0) + SO2..SOn (geometric)
    let total = 2.0
    const n = maxSafetyOrders
    if (n > 1) {
      if (volumeScale === 1.0) {
        total += n - 1
      } else {
        total +=
          (volumeScale * (Math.pow(volumeScale, n - 1) - 1)) / (volumeScale - 1)
      }
    }
    return total
  }
  return 1.0 + maxSafetyOrders * 0.5
}

/**
 * Calculate the soft ceiling for concurrent deals based on budget and exchange minimums.
 */
export function calculateSoftCeiling(
  config: Record<string, any>,
  aggregateValue: number,
  budgetPercentage: number,
  worstCaseMin: number,
  maxConcurrentDeals: number
): number {
  const multiplier = getDCAMultiplier(config)
  const totalBudget = ((aggregateValue || 0) * (budgetPercentage || 0)) / 100
  const softCeiling = Math.floor(totalBudget / (worstCaseMin * multiplier))
  return Math.max(1, Math.min(softCeiling, maxConcurrentDeals || 1000))
}
