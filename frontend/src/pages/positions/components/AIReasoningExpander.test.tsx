import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AIReasoningExpander } from './AIReasoningExpander'
import { positionsApi } from '../../../services/api'
import type { AIOpinionLog } from '../../../types'

vi.mock('../../../services/api', () => ({
  positionsApi: {
    getAIOpinion: vi.fn(),
  },
}))

const mockGetAIOpinion = positionsApi.getAIOpinion as ReturnType<typeof vi.fn>

const buildOpinion = (overrides: Partial<AIOpinionLog> = {}): AIOpinionLog => ({
  id: 1,
  position_id: 42,
  bot_id: 7,
  product_id: 'ETH-BTC',
  is_sell_check: false,
  signal: 'BUY',
  confidence: 72,
  reasoning: 'Strong upward momentum across 4h candles.',
  ai_model: 'claude-sonnet-4-6',
  tool_calls: [
    {
      name: 'get_portfolio_context',
      input: { quote: 'BTC' },
      output_summary: 'Account has 0.45 BTC free.',
    },
  ],
  created_at: '2026-04-21T12:00:00Z',
  outcome: null,
  realized_pnl_pct: null,
  closed_at: null,
  ...overrides,
})

describe('AIReasoningExpander', () => {
  beforeEach(() => {
    mockGetAIOpinion.mockReset()
  })

  it('renders nothing while the fetch is in flight', () => {
    // Never-resolving promise keeps fetched=false
    mockGetAIOpinion.mockReturnValue(new Promise(() => {}))
    const { container } = render(<AIReasoningExpander positionId={42} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when the opinion has no tool calls (single-shot fallback)', async () => {
    mockGetAIOpinion.mockResolvedValue(buildOpinion({ tool_calls: [] }))
    const { container } = render(<AIReasoningExpander positionId={42} />)
    await waitFor(() => expect(mockGetAIOpinion).toHaveBeenCalledWith(42))
    await waitFor(() => expect(container.firstChild).toBeNull())
  })

  it('renders nothing when tool_calls is null', async () => {
    mockGetAIOpinion.mockResolvedValue(buildOpinion({ tool_calls: null }))
    const { container } = render(<AIReasoningExpander positionId={42} />)
    await waitFor(() => expect(mockGetAIOpinion).toHaveBeenCalled())
    await waitFor(() => expect(container.firstChild).toBeNull())
  })

  it('renders nothing when the endpoint returns null (no opinion logged yet)', async () => {
    mockGetAIOpinion.mockResolvedValue(null)
    const { container } = render(<AIReasoningExpander positionId={42} />)
    await waitFor(() => expect(mockGetAIOpinion).toHaveBeenCalled())
    await waitFor(() => expect(container.firstChild).toBeNull())
  })

  it('renders nothing when the fetch rejects (network error, etc.)', async () => {
    mockGetAIOpinion.mockRejectedValue(new Error('network down'))
    const { container } = render(<AIReasoningExpander positionId={42} />)
    await waitFor(() => expect(mockGetAIOpinion).toHaveBeenCalled())
    await waitFor(() => expect(container.firstChild).toBeNull())
  })

  it('shows the collapsed "AI reasoning" button when tool calls exist', async () => {
    mockGetAIOpinion.mockResolvedValue(buildOpinion())
    render(<AIReasoningExpander positionId={42} />)
    const btn = await screen.findByRole('button', { name: /toggle ai reasoning detail/i })
    expect(btn).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText(/tools called/i)).not.toBeInTheDocument()
  })

  it('expands to show signal, confidence, reasoning and tool-call names', async () => {
    mockGetAIOpinion.mockResolvedValue(buildOpinion())
    render(<AIReasoningExpander positionId={42} />)
    const btn = await screen.findByRole('button', { name: /toggle ai reasoning detail/i })

    await act(async () => {
      await userEvent.click(btn)
    })

    expect(btn).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('BUY')).toBeInTheDocument()
    expect(screen.getByText(/72%/)).toBeInTheDocument()
    expect(screen.getByText(/strong upward momentum/i)).toBeInTheDocument()
    expect(screen.getByText(/tools called \(1\)/i)).toBeInTheDocument()
    expect(screen.getByText('get_portfolio_context')).toBeInTheDocument()
  })

  it('reveals the tool output_summary when a tool row is clicked', async () => {
    mockGetAIOpinion.mockResolvedValue(buildOpinion())
    render(<AIReasoningExpander positionId={42} />)
    const toggleBtn = await screen.findByRole('button', { name: /toggle ai reasoning detail/i })

    await act(async () => {
      await userEvent.click(toggleBtn)
    })

    expect(screen.queryByText(/account has 0.45 btc free/i)).not.toBeInTheDocument()

    const toolBtn = screen.getByRole('button', { name: /get_portfolio_context/i })
    await act(async () => {
      await userEvent.click(toolBtn)
    })

    expect(screen.getByText(/account has 0.45 btc free/i)).toBeInTheDocument()
  })
})
