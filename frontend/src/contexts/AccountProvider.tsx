/**
 * AccountProvider — global state for multi-account trading. Fetches accounts
 * and invitations, manages the selected account, and supplies actions/helpers
 * via AccountContext.
 */

import { useState, useEffect, useCallback, useMemo, ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authFetch } from '../services/api'
import { markStartupMilestone } from '../utils/startupPerformance'
import {
  AccountContext,
  AccountContextType,
  Account,
  CreateAccountDto,
  UpdateAccountDto,
  invitationsApi,
} from './AccountContext'

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

  useEffect(() => {
    if (selectedAccount) markStartupMilestone('account-ready')
  }, [selectedAccount])

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
