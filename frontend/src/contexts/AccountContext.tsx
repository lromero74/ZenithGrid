/**
 * Account Context
 *
 * Provides global state management for multi-account trading.
 * Allows switching between CEX (Coinbase) and DEX (MetaMask) accounts,
 * with all pages filtering data by the selected account.
 */

import { createContext, useContext, useState, useEffect, useCallback, useMemo, ReactNode } from 'react'
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

interface AccountContextType {
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
      const detail = typeof error.detail === 'string'
        ? error.detail
        : Array.isArray(error.detail)
          ? error.detail.map((e: { msg?: string }) => e.msg || String(e)).join(', ')
          : 'Failed to create account'
      throw new Error(detail)
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

const invitationsApi = {
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

export { invitationsApi }

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

  // Find selected account from the list (memoized to avoid new reference on every render)
  const selectedAccount = useMemo(
    () => accounts.find((a) => a.id === selectedAccountId) || null,
    [accounts, selectedAccountId]
  )

  // Auto-select default account if none selected or stale ID from another user
  useEffect(() => {
    if (accounts.length > 0) {
      const isValid = selectedAccountId != null && accounts.some((a) => a.id === selectedAccountId)
      if (!isValid) {
        const defaultAccount = accounts.find((a) => a.is_default) || accounts[0]
        if (defaultAccount) {
          setSelectedAccountId(defaultAccount.id)
          localStorage.setItem('selectedAccountId', defaultAccount.id.toString())
        }
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

  // Pending invitations — the WebSocket push below is the primary delivery
  // path; this is only a slow safety-net poll for when the socket is down.
  // (Was a 60s poll + focus refetch, app-wide, 24/7 — needless API load.)
  const {
    data: pendingInvitations = [],
    refetch: refetchInvitations,
  } = useQuery({
    queryKey: ['invitations', 'pending'],
    queryFn: invitationsApi.getPending,
    staleTime: 30000,
    refetchInterval: 300000, // 5 minutes (fallback only)
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
  })

  // Listen for real-time invitation push from WebSocket (via custom DOM event)
  useEffect(() => {
    const handler = () => {
      queryClient.invalidateQueries({ queryKey: ['invitations', 'pending'] })
    }
    window.addEventListener('account:invitation_received', handler)
    return () => window.removeEventListener('account:invitation_received', handler)
  }, [queryClient])

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

  const refreshInvitations = useCallback(async (): Promise<void> => {
    await refetchInvitations()
  }, [refetchInvitations])

  const acceptInvitation = useCallback(async (token: string): Promise<void> => {
    await invitationsApi.accept(token)
    queryClient.invalidateQueries({ queryKey: ['invitations', 'pending'] })
    queryClient.invalidateQueries({ queryKey: ['accounts'] })
  }, [queryClient])

  const declineInvitation = useCallback(async (token: string): Promise<void> => {
    await invitationsApi.decline(token)
    queryClient.invalidateQueries({ queryKey: ['invitations', 'pending'] })
  }, [queryClient])

  const leaveSharedAccount = useCallback(async (accountId: number, userId: number): Promise<void> => {
    const response = await authFetch(
      `/api/accounts/${accountId}/sharing/members/${userId}`,
      { method: 'DELETE' }
    )
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to leave account')
    }
    queryClient.invalidateQueries({ queryKey: ['accounts'] })
    if (selectedAccountId === accountId) {
      setSelectedAccountId(null)
      localStorage.removeItem('selectedAccountId')
    }
  }, [queryClient, selectedAccountId])

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

  const isOwner = useCallback((account: Account): boolean => {
    return !account.membership_role
  }, [])

  const getOwnedAccounts = useCallback((): Account[] => {
    return accounts.filter((a) => !a.membership_role)
  }, [accounts])

  const getSharedAccounts = useCallback((): Account[] => {
    return accounts.filter((a) => !!a.membership_role)
  }, [accounts])

  const value: AccountContextType = useMemo(() => ({
    accounts,
    selectedAccount,
    selectedAccountId,
    isLoading,
    error: fetchError ? (fetchError as Error).message : null,
    pendingInvitations,
    pendingInvitationCount: pendingInvitations.length,
    refreshInvitations,
    acceptInvitation,
    declineInvitation,
    selectAccount,
    addAccount,
    updateAccount,
    deleteAccount,
    setDefaultAccount,
    refreshAccounts,
    leaveSharedAccount,
    getAccountById,
    getCexAccounts,
    getDexAccounts,
    isOwner,
    getOwnedAccounts,
    getSharedAccounts,
  }), [
    accounts, selectedAccount, selectedAccountId, isLoading, fetchError,
    pendingInvitations, refreshInvitations, acceptInvitation, declineInvitation,
    selectAccount, addAccount, updateAccount, deleteAccount,
    setDefaultAccount, refreshAccounts, leaveSharedAccount,
    getAccountById, getCexAccounts, getDexAccounts,
    isOwner, getOwnedAccounts, getSharedAccounts,
  ])

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
