import { StrategyParameter } from '../../types'

export interface BotFormData {
  name: string
  description: string
  strategy_type: string
  product_id: string  // Legacy - kept for backward compatibility
  product_ids: string[]  // Multi-pair support
  split_budget_across_pairs: boolean  // Budget splitting toggle
  reserved_btc_balance: number  // BTC allocated to this bot (legacy)
  reserved_usd_balance: number  // USD allocated to this bot (legacy)
  budget_percentage: number  // % of aggregate portfolio value (preferred)
  check_interval_seconds: number  // How often bot monitors positions
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  strategy_config: Record<string, any>
  // DEX-specific fields
  exchange_type: 'cex' | 'dex'  // Exchange type
  chain_id?: number  // Blockchain ID (1=Ethereum, 56=BSC, 137=Polygon, 42161=Arbitrum)
  dex_router?: string  // DEX router contract address
  wallet_private_key?: string  // Wallet private key for DEX
  rpc_url?: string  // RPC endpoint URL
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
  strategy_type: '',
  product_id: 'ETH-BTC',  // Legacy fallback
  product_ids: [],  // Start with empty array, user will select
  split_budget_across_pairs: false,  // Default to independent budgets (3Commas style)
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
export const isParameterVisible = (
  param: StrategyParameter,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  strategyConfig: Record<string, any>
): boolean => {
  if (!param.visible_when) return true

  // Check each condition in visible_when
  return Object.entries(param.visible_when).every(([key, value]) => {
    const currentValue = strategyConfig[key]
    return currentValue === value
  })
}
