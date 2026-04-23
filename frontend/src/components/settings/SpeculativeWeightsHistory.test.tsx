/**
 * SpeculativeWeightsHistory — read-only proposal log.
 * Hidden when empty. Shows status badge + summary per row.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'

const mockList = vi.fn()

vi.mock('../../services/api', () => ({
  speculativeBucketApi: {
    listWeightsProposals: (...args: unknown[]) => mockList(...args),
  },
}))

import { SpeculativeWeightsHistory } from './SpeculativeWeightsHistory'

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const DEFAULTS = {
  volume_surge: 25, compression_breakout: 20,
  momentum_accelerating: 20, micro_mid_cap: 10,
  correlation_break: 10, volume_vs_mcap: 15,
}

describe('SpeculativeWeightsHistory', () => {
  beforeEach(() => {
    mockList.mockReset()
  })

  it('renders nothing when no proposals exist', async () => {
    mockList.mockResolvedValue([])
    const { container } = renderWithQuery(<SpeculativeWeightsHistory accountId={1} />)
    await waitFor(() => {
      expect(mockList).toHaveBeenCalledWith(1)
    })
    expect(container.textContent).toBe('')
  })

  it('renders a row per proposal with its status badge', async () => {
    mockList.mockResolvedValue([
      {
        id: 7, status: 'applied',
        algorithm: 'proportional-alpha-v1',
        sample_size: 600, overall_win_rate_pct: 16.0, divergence_pp: 22.0,
        baseline_weights: { ...DEFAULTS },
        proposed_weights: { ...DEFAULTS, volume_surge: 28, correlation_break: 7 },
        created_at: '2026-01-01T00:00:00Z',
        decided_at: '2026-01-02T00:00:00Z',
        reason: null,
      },
      {
        id: 8, status: 'pending',
        algorithm: 'proportional-alpha-v1',
        sample_size: 700, overall_win_rate_pct: 17.0, divergence_pp: 18.0,
        baseline_weights: { ...DEFAULTS, volume_surge: 28, correlation_break: 7 },
        proposed_weights: { ...DEFAULTS, volume_surge: 30, correlation_break: 5 },
        created_at: '2026-02-01T00:00:00Z',
        decided_at: null,
        reason: null,
      },
    ])
    renderWithQuery(<SpeculativeWeightsHistory accountId={1} />)
    // Wait for the async query to resolve.
    await screen.findByTestId('proposal-7')
    expect(screen.getByTestId('proposal-8')).toBeInTheDocument()
    // Status badges present (case-insensitive match — CSS uppercase).
    expect(screen.getByText(/applied/i)).toBeInTheDocument()
    expect(screen.getByText(/pending/i)).toBeInTheDocument()
  })

  it('highlights gainers and losers by sign', async () => {
    mockList.mockResolvedValue([
      {
        id: 7, status: 'applied',
        algorithm: 'proportional-alpha-v1',
        sample_size: 600, overall_win_rate_pct: 16.0, divergence_pp: 22.0,
        baseline_weights: { ...DEFAULTS },
        proposed_weights: { ...DEFAULTS, volume_surge: 28, correlation_break: 7 },
        created_at: '2026-01-01T00:00:00Z',
        decided_at: '2026-01-02T00:00:00Z',
        reason: null,
      },
    ])
    renderWithQuery(<SpeculativeWeightsHistory accountId={1} />)
    const row = await screen.findByTestId('proposal-7')
    // Gainer: volume_surge +3; loser: correlation_break -3.
    expect(row.textContent).toContain('+3')
    expect(row.textContent).toContain('-3')
  })

  it('shows a fallback label when no weights changed', async () => {
    // A 'superseded' row that was never applied can legitimately have
    // baseline == proposed in edge cases.
    mockList.mockResolvedValue([
      {
        id: 9, status: 'superseded',
        algorithm: 'proportional-alpha-v1',
        sample_size: 500, overall_win_rate_pct: 15.0, divergence_pp: 21.0,
        baseline_weights: { ...DEFAULTS },
        proposed_weights: { ...DEFAULTS },
        created_at: '2026-03-01T00:00:00Z',
        decided_at: '2026-03-02T00:00:00Z',
        reason: null,
      },
    ])
    renderWithQuery(<SpeculativeWeightsHistory accountId={1} />)
    await screen.findByTestId('proposal-9')
    expect(screen.getByText(/no weight changes/i)).toBeInTheDocument()
  })
})
