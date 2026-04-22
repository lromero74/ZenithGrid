import type {
  AutoBuySettings, RebalanceSettings, DustSweepSettings,
} from '../../services/api'
import type { Bot } from '../../types'

export interface CurrencySlider {
  key: 'target_usd_pct' | 'target_btc_pct' | 'target_eth_pct' | 'target_usdc_pct' | 'target_usdt_pct'
  label: string
  color: string
  bgColor: string
}

export const CURRENCIES: CurrencySlider[] = [
  { key: 'target_usd_pct', label: 'USD', color: 'text-green-400', bgColor: 'bg-green-500' },
  { key: 'target_btc_pct', label: 'BTC', color: 'text-orange-400', bgColor: 'bg-orange-500' },
  { key: 'target_eth_pct', label: 'ETH', color: 'text-blue-400', bgColor: 'bg-blue-500' },
  { key: 'target_usdc_pct', label: 'USDC', color: 'text-cyan-400', bgColor: 'bg-cyan-500' },
  { key: 'target_usdt_pct', label: 'USDT', color: 'text-teal-400', bgColor: 'bg-teal-500' },
]

export const CURRENCY_HEX: Record<string, string> = {
  USD: '#22c55e', BTC: '#f97316', ETH: '#3b82f6', USDC: '#06b6d4', USDT: '#14b8a6',
}

export const MIN_BALANCE_CONFIG: Record<string, { key: keyof RebalanceSettings; step: string; placeholder: string }> = {
  USD: { key: 'min_balance_usd', step: '1', placeholder: '0.00' },
  BTC: { key: 'min_balance_btc', step: '0.001', placeholder: '0.000' },
  ETH: { key: 'min_balance_eth', step: '0.01', placeholder: '0.00' },
  USDC: { key: 'min_balance_usdc', step: '1', placeholder: '0.00' },
  USDT: { key: 'min_balance_usdt', step: '1', placeholder: '0.00' },
}

export const INTERVAL_OPTIONS = [
  { value: 15, label: '15 min' },
  { value: 30, label: '30 min' },
  { value: 60, label: '1 hour' },
  { value: 120, label: '2 hours' },
  { value: 240, label: '4 hours' },
]

export type PortfolioMode = 'off' | 'autobuy' | 'rebalance'

export const MODE_OPTIONS: { value: PortfolioMode; label: string; description: string }[] = [
  { value: 'off', label: 'Off', description: 'No automatic portfolio management' },
  { value: 'autobuy', label: 'Auto-Buy BTC', description: 'Convert idle stablecoins to BTC' },
  { value: 'rebalance', label: 'Rebalancing', description: 'Maintain target allocations' },
]

// Cache (survives unmount/remount AND page reloads via sessionStorage)

export interface PortfolioCache {
  autoBuy: Record<number, AutoBuySettings>
  rebalance: Record<number, RebalanceSettings>
  dust: Record<number, DustSweepSettings>
  bots: Bot[]
  timestamp: number
}

export const CACHE_KEY = 'portfolioMgmtCache'
export const CACHE_STALE_MS = 5 * 60 * 1000  // refresh in background after 5 min

export function loadCache(): PortfolioCache | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY)
    if (!raw) return null
    return JSON.parse(raw) as PortfolioCache
  } catch { return null }
}

export function saveCache(cache: PortfolioCache) {
  try { sessionStorage.setItem(CACHE_KEY, JSON.stringify(cache)) } catch { /* ignored */ }
}
