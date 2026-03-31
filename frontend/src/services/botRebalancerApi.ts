import axios from 'axios'

export interface RebalancerBot {
  id: number
  name: string
  is_active: boolean
  budget_percentage: number
  bot_rebalancer_enabled: boolean
  bot_rebalancer_target_pct: number
  rebalancer_bot_overweight: boolean
  quote_currency: string
  open_positions_count: number
}

export interface RebalancerCurrencyGroup {
  base_currency: string
  max_total_pct: number
  overweight_tolerance_pct: number
  enabled: boolean
  bots: RebalancerBot[]
}

export interface RebalancerSavePayload {
  account_id: number
  base_currency: string
  max_total_pct: number
  overweight_tolerance_pct: number
  bots: Array<{ bot_id: number; enabled: boolean; target_pct: number }>
}

export const getRebalancerState = (accountId: number) =>
  axios.get<RebalancerCurrencyGroup[]>(`/api/bots/rebalancer?account_id=${accountId}`)

export const saveRebalancerGroup = (payload: RebalancerSavePayload) =>
  axios.put('/api/bots/rebalancer', payload)
