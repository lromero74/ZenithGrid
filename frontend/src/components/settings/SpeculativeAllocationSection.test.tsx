/**
 * SpeculativeAllocationSection — Account Settings speculative bucket field
 *
 * PRP: high-risk-doubling-preset §Task D1.
 * Lets the user configure the account-level cap for speculative bots.
 * 0 means no bucket (speculative bots blocked from opening new positions).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'

const mockUpdateAccount = vi.fn()

vi.mock('../../contexts/AccountContext', () => ({
  useAccount: () => ({
    updateAccount: mockUpdateAccount,
  }),
}))

let __canWrite = true
vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => __canWrite,
}))

import { SpeculativeAllocationSection } from './SpeculativeAllocationSection'

const makeAccount = (pct = 0) => ({
  id: 42,
  name: 'Main',
  type: 'cex' as const,
  is_default: true,
  is_active: true,
  bot_count: 0,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  speculative_allocation_pct: pct,
})

describe('SpeculativeAllocationSection', () => {
  beforeEach(() => {
    mockUpdateAccount.mockReset()
    mockUpdateAccount.mockResolvedValue(makeAccount(5))
    __canWrite = true
  })

  it('renders the current speculative_allocation_pct value', () => {
    render(<SpeculativeAllocationSection account={makeAccount(3.5)} />)
    const input = screen.getByLabelText(/Speculative Allocation/i) as HTMLInputElement
    expect(input).toBeInTheDocument()
    expect(input.value).toBe('3.5')
  })

  it('submits the updated value to updateAccount', async () => {
    render(<SpeculativeAllocationSection account={makeAccount(0)} />)
    const input = screen.getByLabelText(/Speculative Allocation/i)
    fireEvent.change(input, { target: { value: '7' } })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))
    await waitFor(() => {
      expect(mockUpdateAccount).toHaveBeenCalledWith(42, { speculative_allocation_pct: 7 })
    })
  })

  it('clamps values above 100 before submit', async () => {
    render(<SpeculativeAllocationSection account={makeAccount(0)} />)
    const input = screen.getByLabelText(/Speculative Allocation/i)
    fireEvent.change(input, { target: { value: '250' } })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))
    await waitFor(() => {
      expect(mockUpdateAccount).toHaveBeenCalledWith(42, { speculative_allocation_pct: 100 })
    })
  })

  it('clamps negative values to 0 before submit', async () => {
    render(<SpeculativeAllocationSection account={makeAccount(5)} />)
    const input = screen.getByLabelText(/Speculative Allocation/i)
    fireEvent.change(input, { target: { value: '-4' } })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))
    await waitFor(() => {
      expect(mockUpdateAccount).toHaveBeenCalledWith(42, { speculative_allocation_pct: 0 })
    })
  })

  it('shows a warning note explaining cost-basis semantics', () => {
    render(<SpeculativeAllocationSection account={makeAccount(0)} />)
    expect(screen.getByText(/cost basis/i)).toBeInTheDocument()
  })

  it('disables the save button when the user lacks accounts:write permission', () => {
    __canWrite = false
    render(<SpeculativeAllocationSection account={makeAccount(0)} />)
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled()
  })
})
