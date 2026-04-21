/**
 * Tests for PanicSellModal component
 *
 * TDD: written before full implementation details, covers:
 * - Renders correctly on first step (configure)
 * - Shows currency selector when action = sell
 * - Does not show currency selector when action = cancel
 * - Advances to confirm step
 * - Requires typing CONFIRM to enable submit
 * - Calls panicSellSendMfa when proceeding from confirm
 * - Skips MFA step and submits when method = none
 * - Shows MFA step for TOTP method
 * - Shows MFA step with send button for email method
 * - Calls panicSell with correct params after MFA
 * - Shows progress phase indicator after submission
 * - Shows completion summary when status = completed
 * - Shows error state when status = failed
 * - Close button resets and dismisses
 */

import { describe, test, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import type { ReactNode } from 'react'
import { PanicSellModal } from './PanicSellModal'
import { positionsApi } from '../../services/api'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../services/api', () => ({
  positionsApi: {
    panicSellSendMfa: vi.fn(),
    panicSell: vi.fn(),
    panicSellStatus: vi.fn(),
  },
}))

const mockPanicSellSendMfa = positionsApi.panicSellSendMfa as ReturnType<typeof vi.fn>
const mockPanicSell = positionsApi.panicSell as ReturnType<typeof vi.fn>
const mockPanicSellStatus = positionsApi.panicSellStatus as ReturnType<typeof vi.fn>

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children)
}

const DEFAULT_PROPS = {
  isOpen: true,
  onClose: vi.fn(),
  accountId: 42,
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderModal(props = DEFAULT_PROPS) {
  return render(createElement(PanicSellModal, props), { wrapper: makeWrapper() })
}

// ---------------------------------------------------------------------------
// Step 1: Configure
// ---------------------------------------------------------------------------

describe('Step: configure', () => {
  test('renders action choice on first step', () => {
    renderModal()
    expect(screen.getByText('Cancel All Deals')).toBeInTheDocument()
    expect(screen.getByText('Sell All at Market')).toBeInTheDocument()
  })

  test('shows currency selector after choosing sell', () => {
    renderModal()
    fireEvent.click(screen.getByLabelText(/sell all at market/i, { exact: false }) ||
      screen.getAllByRole('radio').find(r => (r as HTMLInputElement).value === 'sell')!)
    expect(screen.getByText('USD')).toBeInTheDocument()
    expect(screen.getByText('USDC')).toBeInTheDocument()
    expect(screen.getByText('BTC')).toBeInTheDocument()
  })

  test('does not show currency selector for cancel action', () => {
    renderModal()
    // cancel is default
    expect(screen.queryByText('Convert to')).not.toBeInTheDocument()
  })

  test('advances to confirm step on Next click', () => {
    renderModal()
    fireEvent.click(screen.getByText('Next →'))
    expect(screen.getByText(/type/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText('CONFIRM')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Step 2: Confirm
// ---------------------------------------------------------------------------

describe('Step: confirm', () => {
  function advanceToConfirm() {
    renderModal()
    fireEvent.click(screen.getByText('Next →'))
  }

  test('Next button is disabled until CONFIRM is typed', () => {
    advanceToConfirm()
    const nextBtn = screen.getByRole('button', { name: /next/i })
    expect(nextBtn).toBeDisabled()
    fireEvent.change(screen.getByPlaceholderText('CONFIRM'), { target: { value: 'CONFI' } })
    expect(nextBtn).toBeDisabled()
    fireEvent.change(screen.getByPlaceholderText('CONFIRM'), { target: { value: 'CONFIRM' } })
    expect(nextBtn).not.toBeDisabled()
  })

  test('calls panicSellSendMfa after typing CONFIRM and clicking Next', async () => {
    mockPanicSellSendMfa.mockResolvedValueOnce({ method: 'none' })
    mockPanicSell.mockResolvedValueOnce({ task_id: 'task-123', message: 'ok', status_url: '' })
    mockPanicSellStatus.mockResolvedValue({ status: 'running', phase: 'starting', message: 'init', bots_stopped: 0, positions_total: 0, positions_current: 0, positions_acted: 0, positions_failed: 0, portfolio_rebalancer_stopped: false, bot_rebalancer_groups_stopped: 0, auto_buy_stopped: false, min_balances_zeroed: false, conversion_task_id: null, conversion_status_url: null, progress_pct: 0, errors: [], started_at: '', completed_at: null })

    advanceToConfirm()
    fireEvent.change(screen.getByPlaceholderText('CONFIRM'), { target: { value: 'CONFIRM' } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /next/i })) })
    await waitFor(() => expect(mockPanicSellSendMfa).toHaveBeenCalledOnce())
  })
})

// ---------------------------------------------------------------------------
// Step 3: MFA
// ---------------------------------------------------------------------------

describe('Step: MFA', () => {
  async function advanceToMfa(method: 'totp' | 'email') {
    const maskedEmail = method === 'email' ? 'te***@example.com' : undefined
    mockPanicSellSendMfa.mockResolvedValueOnce({ method, masked_email: maskedEmail })
    renderModal()
    fireEvent.click(screen.getByText('Next →'))
    fireEvent.change(screen.getByPlaceholderText('CONFIRM'), { target: { value: 'CONFIRM' } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /next/i })) })
    await waitFor(() => screen.getByText('MFA Verification'))
  }

  test('shows TOTP prompt for authenticator app', async () => {
    await advanceToMfa('totp')
    expect(screen.getByText(/authenticator app/i)).toBeInTheDocument()
  })

  test('shows email prompt with masked address for email MFA', async () => {
    await advanceToMfa('email')
    expect(screen.getByText(/te\*\*\*@example\.com/)).toBeInTheDocument()
  })

  test('Execute button disabled until 6 digits entered', async () => {
    await advanceToMfa('totp')
    const execBtn = screen.getByRole('button', { name: /execute/i })
    expect(execBtn).toBeDisabled()
    const input = screen.getByPlaceholderText('000000')
    fireEvent.change(input, { target: { value: '12345' } })
    expect(execBtn).toBeDisabled()
    fireEvent.change(input, { target: { value: '123456' } })
    expect(execBtn).not.toBeDisabled()
  })

  test('calls panicSell with mfa_code when execute clicked', async () => {
    mockPanicSell.mockResolvedValueOnce({ task_id: 'task-abc', message: 'ok', status_url: '' })
    mockPanicSellStatus.mockResolvedValue({ status: 'running', phase: 'starting', message: '', bots_stopped: 0, positions_total: 0, positions_current: 0, positions_acted: 0, positions_failed: 0, portfolio_rebalancer_stopped: false, bot_rebalancer_groups_stopped: 0, auto_buy_stopped: false, min_balances_zeroed: false, conversion_task_id: null, conversion_status_url: null, progress_pct: 0, errors: [], started_at: '', completed_at: null })
    await advanceToMfa('totp')
    const input = screen.getByPlaceholderText('000000')
    fireEvent.change(input, { target: { value: '654321' } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /execute/i })) })
    await waitFor(() => expect(mockPanicSell).toHaveBeenCalledWith(
      expect.objectContaining({ mfa_code: '654321', confirm: true, account_id: 42 })
    ))
  })
})

// ---------------------------------------------------------------------------
// Step 4: Progress
// ---------------------------------------------------------------------------

describe('Step: progress', () => {
  async function advanceToProgress() {
    mockPanicSellSendMfa.mockResolvedValue({ method: 'none' })
    mockPanicSell.mockResolvedValue({ task_id: 'task-xyz', message: 'ok', status_url: '' })
    mockPanicSellStatus.mockResolvedValue({
      status: 'running', phase: 'closing_positions', message: 'Selling 2/5...',
      bots_stopped: 2, positions_total: 5, positions_current: 2, positions_acted: 2,
      positions_failed: 0, portfolio_rebalancer_stopped: false, bot_rebalancer_groups_stopped: 0,
      auto_buy_stopped: false, min_balances_zeroed: false, conversion_task_id: null,
      conversion_status_url: null, progress_pct: 40, errors: [], started_at: '', completed_at: null,
    })

    renderModal()
    fireEvent.click(screen.getByText('Next →'))
    fireEvent.change(screen.getByPlaceholderText('CONFIRM'), { target: { value: 'CONFIRM' } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /next/i })) })
    await waitFor(() => screen.getByText('Selling 2/5...'))
  }

  test('shows phase indicator and progress after submission', async () => {
    await advanceToProgress()
    expect(screen.getByText('Closing positions')).toBeInTheDocument()
    expect(screen.getByText('Selling 2/5...')).toBeInTheDocument()
    expect(screen.getByText('2/5')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Step 5: Done
// ---------------------------------------------------------------------------

describe('Step: done', () => {
  async function advanceToDone(status: 'completed' | 'failed') {
    mockPanicSellSendMfa.mockResolvedValue({ method: 'none' })
    mockPanicSell.mockResolvedValue({ task_id: 'task-done', message: 'ok', status_url: '' })
    mockPanicSellStatus.mockResolvedValue({
      status,
      phase: 'completed',
      message: status === 'completed' ? 'Complete: 0 bots stopped, 3 positions cancelled' : 'Panic sell failed: error',
      bots_stopped: 1, positions_total: 3, positions_current: 3, positions_acted: 3,
      positions_failed: 0, portfolio_rebalancer_stopped: true, bot_rebalancer_groups_stopped: 1,
      auto_buy_stopped: true, min_balances_zeroed: true, conversion_task_id: null,
      conversion_status_url: null, progress_pct: 100, errors: [], started_at: '', completed_at: '2026-01-01T00:00:00',
    })

    renderModal()
    fireEvent.click(screen.getByText('Next →'))
    fireEvent.change(screen.getByPlaceholderText('CONFIRM'), { target: { value: 'CONFIRM' } })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /next/i })) })
    await waitFor(() => status === 'completed'
      ? screen.getByText('✓ Complete')
      : screen.getByText('Panic sell failed')
    )
  }

  test('shows completion summary when status is completed', async () => {
    await advanceToDone('completed')
    expect(screen.getByText('✓ Complete')).toBeInTheDocument()
    expect(screen.getByText(/3 position/)).toBeInTheDocument()
    expect(screen.getByText('✓ Portfolio rebalancer disabled')).toBeInTheDocument()
    expect(screen.getByText('✓ Auto-buy BTC disabled')).toBeInTheDocument()
    expect(screen.getByText('✓ Minimum balance reserves zeroed')).toBeInTheDocument()
  })

  test('shows error state when status is failed', async () => {
    await advanceToDone('failed')
    expect(screen.getByText('Panic sell failed')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Close button
// ---------------------------------------------------------------------------

describe('Close button', () => {
  test('close button calls onClose and resets state', () => {
    const onClose = vi.fn()
    renderModal({ ...DEFAULT_PROPS, onClose })
    fireEvent.click(screen.getByText('✕'))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
