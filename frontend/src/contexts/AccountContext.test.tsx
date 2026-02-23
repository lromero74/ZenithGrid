/**
 * Tests for AccountContext
 *
 * Tests pure helper functions (getChainById, getChainName, SUPPORTED_CHAINS)
 * and the AccountProvider/useAccount hook behavior with mocked API calls.
 */

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  getChainById,
  getChainName,
  SUPPORTED_CHAINS,
  AccountProvider,
  useAccount,
} from './AccountContext'
import type { Account } from './AccountContext'

// Mock authFetch
vi.mock('../services/api', () => ({
  authFetch: vi.fn(),
}))

import { authFetch } from '../services/api'

// Helper to create a test wrapper with QueryClient + AccountProvider
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <AccountProvider>{children}</AccountProvider>
      </QueryClientProvider>
    )
  }
}

// Test consumer component that exposes context values
function TestConsumer() {
  const ctx = useAccount()
  return (
    <div>
      <span data-testid="loading">{String(ctx.isLoading)}</span>
      <span data-testid="error">{ctx.error || 'null'}</span>
      <span data-testid="accounts-count">{ctx.accounts.length}</span>
      <span data-testid="selected-id">{ctx.selectedAccount?.id ?? 'none'}</span>
      <span data-testid="selected-name">{ctx.selectedAccount?.name ?? 'none'}</span>
      <span data-testid="cex-count">{ctx.getCexAccounts().length}</span>
      <span data-testid="dex-count">{ctx.getDexAccounts().length}</span>
      <button data-testid="select-btn" onClick={() => ctx.selectAccount(2)}>Select 2</button>
      <button data-testid="refresh-btn" onClick={() => ctx.refreshAccounts()}>Refresh</button>
    </div>
  )
}

// Sample account data
const mockAccounts: Account[] = [
  {
    id: 1,
    name: 'Coinbase Main',
    type: 'cex',
    is_default: true,
    is_active: true,
    exchange: 'coinbase',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    bot_count: 3,
  },
  {
    id: 2,
    name: 'MetaMask Wallet',
    type: 'dex',
    is_default: false,
    is_active: true,
    chain_id: 1,
    wallet_address: '0x123',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    bot_count: 0,
  },
  {
    id: 3,
    name: 'Coinbase Paper',
    type: 'cex',
    is_default: false,
    is_active: true,
    is_paper_trading: true,
    exchange: 'coinbase',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    bot_count: 1,
  },
]

describe('SUPPORTED_CHAINS', () => {
  test('contains Ethereum', () => {
    const eth = SUPPORTED_CHAINS.find((c) => c.id === 1)
    expect(eth).toBeDefined()
    expect(eth!.name).toBe('Ethereum Mainnet')
    expect(eth!.symbol).toBe('ETH')
  })

  test('contains BSC', () => {
    const bsc = SUPPORTED_CHAINS.find((c) => c.id === 56)
    expect(bsc).toBeDefined()
    expect(bsc!.shortName).toBe('BSC')
  })

  test('contains Polygon', () => {
    const polygon = SUPPORTED_CHAINS.find((c) => c.id === 137)
    expect(polygon).toBeDefined()
    expect(polygon!.symbol).toBe('MATIC')
  })

  test('contains Arbitrum', () => {
    const arb = SUPPORTED_CHAINS.find((c) => c.id === 42161)
    expect(arb).toBeDefined()
    expect(arb!.shortName).toBe('Arbitrum')
  })

  test('all chains have required fields', () => {
    for (const chain of SUPPORTED_CHAINS) {
      expect(chain.id).toBeDefined()
      expect(chain.name).toBeDefined()
      expect(chain.shortName).toBeDefined()
      expect(chain.symbol).toBeDefined()
      expect(chain.rpcUrl).toBeDefined()
      expect(chain.blockExplorer).toBeDefined()
    }
  })
})

describe('getChainById', () => {
  test('returns Ethereum for id 1', () => {
    const chain = getChainById(1)
    expect(chain).toBeDefined()
    expect(chain!.name).toBe('Ethereum Mainnet')
  })

  test('returns undefined for unknown chain', () => {
    expect(getChainById(999999)).toBeUndefined()
  })

  test('returns Arbitrum for id 42161', () => {
    const chain = getChainById(42161)
    expect(chain).toBeDefined()
    expect(chain!.shortName).toBe('Arbitrum')
  })
})

describe('getChainName', () => {
  test('returns shortName for known chain', () => {
    expect(getChainName(1)).toBe('Ethereum')
    expect(getChainName(56)).toBe('BSC')
    expect(getChainName(137)).toBe('Polygon')
  })

  test('returns fallback for unknown chain', () => {
    expect(getChainName(12345)).toBe('Chain 12345')
  })
})

describe('AccountProvider', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(authFetch).mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('fetches accounts on mount and displays them', async () => {
    vi.mocked(authFetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockAccounts),
    } as Response)

    render(<TestConsumer />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    expect(screen.getByTestId('accounts-count').textContent).toBe('3')
  })

  test('auto-selects default account when none is selected', async () => {
    vi.mocked(authFetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockAccounts),
    } as Response)

    render(<TestConsumer />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByTestId('selected-id').textContent).toBe('1')
    })

    expect(screen.getByTestId('selected-name').textContent).toBe('Coinbase Main')
  })

  test('restores selected account from localStorage', async () => {
    localStorage.setItem('selectedAccountId', '2')

    vi.mocked(authFetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockAccounts),
    } as Response)

    render(<TestConsumer />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    expect(screen.getByTestId('selected-id').textContent).toBe('2')
    expect(screen.getByTestId('selected-name').textContent).toBe('MetaMask Wallet')
  })

  test('selectAccount updates selection and persists to localStorage', async () => {
    vi.mocked(authFetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockAccounts),
    } as Response)

    render(<TestConsumer />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByTestId('selected-id').textContent).toBe('1')
    })

    // Click to select account 2
    act(() => {
      screen.getByTestId('select-btn').click()
    })

    expect(screen.getByTestId('selected-id').textContent).toBe('2')
    expect(localStorage.getItem('selectedAccountId')).toBe('2')
  })

  test('getCexAccounts filters correctly', async () => {
    vi.mocked(authFetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockAccounts),
    } as Response)

    render(<TestConsumer />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    // 2 CEX accounts (Coinbase Main + Coinbase Paper)
    expect(screen.getByTestId('cex-count').textContent).toBe('2')
  })

  test('getDexAccounts filters correctly', async () => {
    vi.mocked(authFetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockAccounts),
    } as Response)

    render(<TestConsumer />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    // 1 DEX account (MetaMask)
    expect(screen.getByTestId('dex-count').textContent).toBe('1')
  })

  test('handles fetch failure with error state', async () => {
    vi.mocked(authFetch).mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ detail: 'Unauthorized' }),
    } as unknown as Response)

    render(<TestConsumer />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    expect(screen.getByTestId('error').textContent).not.toBe('null')
    expect(screen.getByTestId('accounts-count').textContent).toBe('0')
  })

  test('auto-selects first account when no default exists', async () => {
    const noDefaultAccounts = mockAccounts.map(a => ({ ...a, is_default: false }))

    vi.mocked(authFetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(noDefaultAccounts),
    } as Response)

    render(<TestConsumer />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    // Should auto-select the first account
    expect(screen.getByTestId('selected-id').textContent).toBe('1')
  })

  test('shows loading state initially', () => {
    vi.mocked(authFetch).mockReturnValue(new Promise(() => {})) // Never resolves

    render(<TestConsumer />, { wrapper: createWrapper() })

    expect(screen.getByTestId('loading').textContent).toBe('true')
  })

  test('empty accounts list shows no selection', async () => {
    vi.mocked(authFetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    } as Response)

    render(<TestConsumer />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    expect(screen.getByTestId('accounts-count').textContent).toBe('0')
    expect(screen.getByTestId('selected-id').textContent).toBe('none')
  })
})

describe('useAccount outside provider', () => {
  test('throws error when used outside AccountProvider', () => {
    function BadConsumer() {
      useAccount()
      return <div />
    }

    // Suppress console.error for expected throw
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

    expect(() => {
      render(<BadConsumer />)
    }).toThrow('useAccount must be used within an AccountProvider')

    spy.mockRestore()
  })
})
