/**
 * SpeculativeBucketCard — Dashboard card that surfaces the cost-basis bucket.
 *
 * PRP: high-risk-doubling-preset §Task D3.
 * - Hidden when the account's configured bucket_pct is 0.
 * - Shows deployed/bucket progress bar and available headroom.
 * - Shows a separate speculative PnL (closed position profit_usd for
 *   positions on speculative-tagged bots) so damage is isolated visually.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

const mockGetBucket = vi.fn()
const mockGetClosed = vi.fn()

vi.mock('../../services/api', () => ({
  speculativeBucketApi: {
    get: (...args: unknown[]) => mockGetBucket(...args),
  },
  positionsApi: {
    getAll: (...args: unknown[]) => mockGetClosed(...args),
  },
}))

import { SpeculativeBucketCard } from './SpeculativeBucketCard'

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe('SpeculativeBucketCard', () => {
  beforeEach(() => {
    mockGetBucket.mockReset()
    mockGetClosed.mockReset()
    mockGetClosed.mockResolvedValue([])
  })

  it('renders nothing when bucket_pct is 0 (bucket not configured)', async () => {
    mockGetBucket.mockResolvedValue({
      bucket_pct: 0, bucket_usd: 0,
      deployed_cost_basis_usd: 0, available_usd: 0,
      active_bot_count: 0, open_position_count: 0,
      max_concurrent_slots: 0, per_slot_budget_usd: 0,
    })
    const { container } = renderWithQuery(<SpeculativeBucketCard accountId={1} />)
    // Give the query time to resolve — the component should render null.
    await waitFor(() => {
      expect(mockGetBucket).toHaveBeenCalledWith(1)
    })
    expect(container.textContent).toBe('')
  })

  it('shows deployed/bucket numbers and available when configured', async () => {
    mockGetBucket.mockResolvedValue({
      bucket_pct: 5, bucket_usd: 500,
      deployed_cost_basis_usd: 200, available_usd: 300,
      active_bot_count: 2, open_position_count: 3,
      max_concurrent_slots: 10, per_slot_budget_usd: 30,
    })
    renderWithQuery(<SpeculativeBucketCard accountId={1} />)
    expect(await screen.findByText(/Speculative Bucket/i)).toBeInTheDocument()
    expect(screen.getByText(/\$200\.00/)).toBeInTheDocument()
    expect(screen.getByText(/\$500\.00/)).toBeInTheDocument()
    expect(screen.getByText(/\$300\.00/)).toBeInTheDocument()
  })

  it('computes realized speculative PnL from closed speculative-bot positions', async () => {
    mockGetBucket.mockResolvedValue({
      bucket_pct: 5, bucket_usd: 500,
      deployed_cost_basis_usd: 100, available_usd: 400,
      active_bot_count: 1, open_position_count: 1,
      max_concurrent_slots: 5, per_slot_budget_usd: 80,
    })
    mockGetClosed.mockResolvedValue([
      { id: 1, status: 'closed', strategy_config_snapshot: { is_speculative: 'true' }, profit_usd: 45 },
      { id: 2, status: 'closed', strategy_config_snapshot: { is_speculative: 'true' }, profit_usd: -12 },
      { id: 3, status: 'closed', strategy_config_snapshot: {}, profit_usd: 800 },
    ])
    renderWithQuery(<SpeculativeBucketCard accountId={1} />)
    // Only speculative closed positions are counted: 45 - 12 = 33
    expect(await screen.findByText(/\+\$33\.00/)).toBeInTheDocument()
  })

  it('renders a progress bar reflecting deployed share of bucket', async () => {
    mockGetBucket.mockResolvedValue({
      bucket_pct: 5, bucket_usd: 400,
      deployed_cost_basis_usd: 100, available_usd: 300,
      active_bot_count: 1, open_position_count: 1,
      max_concurrent_slots: 5, per_slot_budget_usd: 75,
    })
    renderWithQuery(<SpeculativeBucketCard accountId={1} />)
    const bar = await screen.findByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '25')
  })
})
