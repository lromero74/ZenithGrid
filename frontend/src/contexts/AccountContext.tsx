/**
 * Account Context
 *
 * Provides global state management for multi-account trading.
 * Allows switching between CEX (Coinbase) and DEX (MetaMask) accounts,
 * with all pages filtering data by the selected account.
 */

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
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

  // Metadata
  created_at: string
  updated_at: string
  last_used_at?: string

  // Computed
  display_name?: string
  short_address?: string
  bot_count: number
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
}

interface AccountContextType {
  // State
  accounts: Account[]
  selectedAccount: Account | null
  isLoading: boolean
  error: string | null

  // Actions
  selectAccount: (accountId: number) => void
  addAccount: (account: CreateAccountDto) => Promise<Account>
  updateAccount: (id: number, data: UpdateAccountDto) => Promise<Account>
  deleteAccount: (id: number) => Promise<void>
  setDefaultAccount: (id: number) => Promise<void>
  refreshAccounts: () => Promise<void>

  // Helpers
  getAccountById: (id: number) => Account | undefined
  getCexAccounts: () => Account[]
  getDexAccounts: () => Account[]
}

// =============================================================================
// API Functions
// =============================================================================

const accountsApi = {
  getAll: async (): Promise<Account[]> => {
    const response = await authFetch('/api/accounts')
    if (!response.ok) throw new Error('Failed to fetch accounts')
    return response.json()
  },

  getDefault: async (): Promise<Account> => {
    const response = await authFetch('/api/accounts/default')
    if (!response.ok) throw new Error('Failed to fetch default account')
    return response.json()
  },

  create: async (data: CreateAccountDto): Promise<Account> => {
    const response = await authFetch('/api/accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to create account')
    }
    return response.json()
  },

  update: async (id: number, data: UpdateAccountDto): Promise<Account> => {
    const response = await authFetch(`/api/accounts/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to update account')
    }
    return response.json()
  },

  delete: async (id: number): Promise<void> => {
    const response = await authFetch(`/api/accounts/${id}`, {
      method: 'DELETE',
    })
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to delete account')
    }
  },

  setDefault: async (id: number): Promise<void> => {
    const response = await authFetch(`/api/accounts/${id}/set-default`, {
      method: 'POST',
    })
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to set default account')
    }
  },
}

// =============================================================================
// Context
// =============================================================================

const AccountContext = createContext<AccountContextType | undefined>(undefined)

// =============================================================================
// Provider
// =============================================================================

interface AccountProviderProps {
  children: ReactNode
}

export function AccountProvider({ children }: AccountProviderProps) {
  const queryClient = useQueryClient()
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(() => {
    // Try to restore from localStorage
    const saved = localStorage.getItem('selectedAccountId')
    return saved ? parseInt(saved, 10) : null
  })

  // Fetch all accounts
  const {
    data: accounts = [],
    isLoading,
    error: fetchError,
    refetch: refetchAccounts,
  } = useQuery({
    queryKey: ['accounts'],
    queryFn: accountsApi.getAll,
    staleTime: 60000, // 1 minute
    refetchOnWindowFocus: false,
  })

  // Find selected account from the list
  const selectedAccount = accounts.find((a) => a.id === selectedAccountId) || null

  // Auto-select default account if none selected
  useEffect(() => {
    if (!selectedAccountId && accounts.length > 0) {
      const defaultAccount = accounts.find((a) => a.is_default) || accounts[0]
      if (defaultAccount) {
        setSelectedAccountId(defaultAccount.id)
        localStorage.setItem('selectedAccountId', defaultAccount.id.toString())
      }
    }
  }, [accounts, selectedAccountId])

  // Create account mutation
  const createMutation = useMutation({
    mutationFn: accountsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
    },
  })

  // Update account mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateAccountDto }) =>
      accountsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
    },
  })

  // Delete account mutation
  const deleteMutation = useMutation({
    mutationFn: accountsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
    },
  })

  // Set default mutation
  const setDefaultMutation = useMutation({
    mutationFn: accountsApi.setDefault,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
    },
  })

  // Actions
  const selectAccount = useCallback((accountId: number) => {
    setSelectedAccountId(accountId)
    localStorage.setItem('selectedAccountId', accountId.toString())
  }, [])

  const addAccount = useCallback(
    async (data: CreateAccountDto): Promise<Account> => {
      return createMutation.mutateAsync(data)
    },
    [createMutation]
  )

  const updateAccount = useCallback(
    async (id: number, data: UpdateAccountDto): Promise<Account> => {
      return updateMutation.mutateAsync({ id, data })
    },
    [updateMutation]
  )

  const deleteAccount = useCallback(
    async (id: number): Promise<void> => {
      await deleteMutation.mutateAsync(id)
      // If we deleted the selected account, clear selection
      if (selectedAccountId === id) {
        setSelectedAccountId(null)
        localStorage.removeItem('selectedAccountId')
      }
    },
    [deleteMutation, selectedAccountId]
  )

  const setDefaultAccount = useCallback(
    async (id: number): Promise<void> => {
      await setDefaultMutation.mutateAsync(id)
    },
    [setDefaultMutation]
  )

  const refreshAccounts = useCallback(async (): Promise<void> => {
    await refetchAccounts()
  }, [refetchAccounts])

  // Helpers
  const getAccountById = useCallback(
    (id: number): Account | undefined => {
      return accounts.find((a) => a.id === id)
    },
    [accounts]
  )

  const getCexAccounts = useCallback((): Account[] => {
    return accounts.filter((a) => a.type === 'cex')
  }, [accounts])

  const getDexAccounts = useCallback((): Account[] => {
    return accounts.filter((a) => a.type === 'dex')
  }, [accounts])

  const value: AccountContextType = {
    accounts,
    selectedAccount,
    isLoading,
    error: fetchError ? (fetchError as Error).message : null,
    selectAccount,
    addAccount,
    updateAccount,
    deleteAccount,
    setDefaultAccount,
    refreshAccounts,
    getAccountById,
    getCexAccounts,
    getDexAccounts,
  }

  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>
}

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
