/**
 * Account Context
 *
 * Provides global state management for multi-account trading.
 * Allows switching between CEX (Coinbase) and DEX (MetaMask) accounts,
 * with all pages filtering data by the selected account.
 *
 * Types, hooks, the invitations API, and chain configs live here; the
 * AccountProvider component lives in AccountProvider.tsx.
 */

import { createContext, useContext } from 'react'
import { authFetch } from '../services/api'

// =============================================================================
// Types
// =============================================================================

export type AccountType = 'cex' | 'dex'

export interface Account {
  id: number
  name: string
  type: AccountType
  is_default: boolean
  is_active: boolean
  is_paper_trading?: boolean  // Paper trading account flag

  // CEX fields
  exchange?: string
  api_key_name?: string

  // DEX fields
  chain_id?: number
  wallet_address?: string
  wallet_type?: string
  rpc_url?: string

  // Perpetual Futures
  perps_portfolio_uuid?: string | null
  default_leverage?: number
  margin_type?: string

  // Prop firm
  prop_firm?: string | null
  prop_daily_drawdown_pct?: number | null
  prop_total_drawdown_pct?: number | null
  prop_initial_deposit?: number | null

  // Speculative bucket (see PRP: high-risk-doubling-preset)
  // 0 means no bucket configured — speculative bots are blocked from entries.
  speculative_allocation_pct?: number

  // Metadata
  created_at: string
  updated_at: string
  last_used_at?: string

  // Computed
  display_name?: string
  short_address?: string
  bot_count: number

  // Sharing fields — absent/null means the current user owns this account
  membership_role?: 'manager' | 'shadow' | null
  shared_by?: string | null        // Display name of owner (non-owners only)
  member_count?: number            // Active non-owner members
}

export interface PendingInvitation {
  token: string
  account_name: string
  invited_by: string
  role: 'manager' | 'shadow'
  expires_at: string
}

export interface CreateAccountDto {
  name: string
  type: AccountType
  is_default?: boolean

  // CEX fields
  exchange?: string
  api_key_name?: string
  api_private_key?: string

  // DEX fields
  chain_id?: number
  wallet_address?: string
  wallet_private_key?: string
  rpc_url?: string
  wallet_type?: string

  // Prop firm fields
  prop_firm?: string
  prop_firm_config?: Record<string, unknown>
  prop_daily_drawdown_pct?: number
  prop_total_drawdown_pct?: number
  prop_initial_deposit?: number
}

export interface UpdateAccountDto {
  name?: string
  is_active?: boolean

  // CEX fields
  exchange?: string
  api_key_name?: string
  api_private_key?: string

  // DEX fields
  chain_id?: number
  wallet_address?: string
  wallet_private_key?: string
  rpc_url?: string
  wallet_type?: string

  // Speculative bucket (0.0 – 100.0; 0 disables the bucket)
  speculative_allocation_pct?: number
}

export interface AccountContextType {
  // State
  accounts: Account[]
  selectedAccount: Account | null
  selectedAccountId: number | null
  isLoading: boolean
  error: string | null

  // Sharing state
  pendingInvitations: PendingInvitation[]
  pendingInvitationCount: number
  refreshInvitations: () => Promise<void>
  acceptInvitation: (token: string) => Promise<void>
  declineInvitation: (token: string) => Promise<void>

  // Actions
  selectAccount: (accountId: number) => void
  addAccount: (account: CreateAccountDto) => Promise<Account>
  updateAccount: (id: number, data: UpdateAccountDto) => Promise<Account>
  deleteAccount: (id: number) => Promise<void>
  setDefaultAccount: (id: number) => Promise<void>
  refreshAccounts: () => Promise<void>
  leaveSharedAccount: (accountId: number, userId: number) => Promise<void>

  // Helpers
  getAccountById: (id: number) => Account | undefined
  getCexAccounts: () => Account[]
  getDexAccounts: () => Account[]
  isOwner: (account: Account) => boolean
  getOwnedAccounts: () => Account[]
  getSharedAccounts: () => Account[]
}

// =============================================================================
// API Functions
// =============================================================================

export const invitationsApi = {
  getPending: async (): Promise<PendingInvitation[]> => {
    const response = await authFetch('/api/invitations/pending')
    if (!response.ok) return []
    return response.json()
  },

  accept: async (token: string): Promise<void> => {
    const response = await authFetch(`/api/invitations/${token}/accept`, { method: 'POST' })
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to accept invitation')
    }
  },

  decline: async (token: string): Promise<void> => {
    const response = await authFetch(`/api/invitations/${token}/decline`, { method: 'POST' })
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to decline invitation')
    }
  },

  preview: async (token: string) => {
    const response = await authFetch(`/api/invitations/preview/${token}`)
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Invalid invitation')
    }
    return response.json()
  },
}

// =============================================================================
// Context
// =============================================================================

export const AccountContext = createContext<AccountContextType | undefined>(undefined)

// =============================================================================
// Hook
// =============================================================================

export function useAccount(): AccountContextType {
  const context = useContext(AccountContext)
  if (context === undefined) {
    throw new Error('useAccount must be used within an AccountProvider')
  }
  return context
}

// Non-throwing variant — returns null outside an AccountProvider. For components
// (e.g. cross-context bridges) whose misplacement must not crash the app.
export function useAccountOptional(): AccountContextType | null {
  return useContext(AccountContext) ?? null
}

// =============================================================================
// Chain Configurations (for DEX accounts)
// =============================================================================

export const SUPPORTED_CHAINS = [
  {
    id: 1,
    name: 'Ethereum Mainnet',
    shortName: 'Ethereum',
    symbol: 'ETH',
    rpcUrl: 'https://mainnet.infura.io/v3/YOUR_INFURA_KEY',
    blockExplorer: 'https://etherscan.io',
    icon: 'ethereum',
  },
  {
    id: 56,
    name: 'Binance Smart Chain',
    shortName: 'BSC',
    symbol: 'BNB',
    rpcUrl: 'https://bsc-dataseed.binance.org/',
    blockExplorer: 'https://bscscan.com',
    icon: 'bnb',
  },
  {
    id: 137,
    name: 'Polygon Mainnet',
    shortName: 'Polygon',
    symbol: 'MATIC',
    rpcUrl: 'https://polygon-rpc.com',
    blockExplorer: 'https://polygonscan.com',
    icon: 'polygon',
  },
  {
    id: 42161,
    name: 'Arbitrum One',
    shortName: 'Arbitrum',
    symbol: 'ETH',
    rpcUrl: 'https://arb1.arbitrum.io/rpc',
    blockExplorer: 'https://arbiscan.io',
    icon: 'arbitrum',
  },
]

export function getChainById(chainId: number) {
  return SUPPORTED_CHAINS.find((c) => c.id === chainId)
}

export function getChainName(chainId: number): string {
  const chain = getChainById(chainId)
  return chain?.shortName || `Chain ${chainId}`
}
