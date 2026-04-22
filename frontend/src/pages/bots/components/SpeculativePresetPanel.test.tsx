/**
 * SpeculativePresetPanel — the BotFormModal risk-preset picker with
 * speculative-specific guardrails. See PRP high-risk-doubling-preset §Task D2.
 *
 * - Selecting "speculative" writes ai_risk_preset into strategy_config.
 * - Renders a red/amber warning banner only when speculative is selected.
 * - Requires the "I understand" confirmation checkbox to be checked.
 * - Reports disabled=true upstream while account bucket is 0, with actionable copy.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import '@testing-library/jest-dom'

const mockGetBucket = vi.fn()

vi.mock('../../../services/api', () => ({
  speculativeBucketApi: {
    get: (...args: unknown[]) => mockGetBucket(...args),
  },
}))

import { SpeculativePresetPanel } from './SpeculativePresetPanel'

const makeProps = (overrides: Partial<React.ComponentProps<typeof SpeculativePresetPanel>> = {}) => ({
  strategyConfig: {} as Record<string, unknown>,
  onChange: vi.fn(),
  onBlockingStateChange: vi.fn(),
  accountId: 1,
  accountSpeculativeAllocationPct: 5,
  // Most tests exercise the fully-supported strategy so the panel renders.
  strategyType: 'indicator_based',
  ...overrides,
})

describe('SpeculativePresetPanel', () => {
  beforeEach(() => {
    mockGetBucket.mockReset()
    mockGetBucket.mockResolvedValue({
      bucket_pct: 5,
      bucket_usd: 500,
      deployed_cost_basis_usd: 100,
      available_usd: 400,
      active_bot_count: 1,
      open_position_count: 1,
      max_concurrent_slots: 3,
      per_slot_budget_usd: 200,
    })
  })

  it('renders the four preset options including speculative', () => {
    render(<SpeculativePresetPanel {...makeProps()} />)
    const select = screen.getByLabelText(/Risk Preset/i) as HTMLSelectElement
    const values = Array.from(select.options).map(o => o.value)
    expect(values).toContain('aggressive')
    expect(values).toContain('moderate')
    expect(values).toContain('conservative')
    expect(values).toContain('speculative')
  })

  it('does not render the warning banner for non-speculative presets', () => {
    render(<SpeculativePresetPanel {...makeProps({ strategyConfig: { ai_risk_preset: 'moderate' } })} />)
    expect(screen.queryByText(/under 20%/i)).not.toBeInTheDocument()
  })

  it('renders the warning banner when speculative is selected', () => {
    render(
      <SpeculativePresetPanel
        {...makeProps({ strategyConfig: { ai_risk_preset: 'speculative' } })}
      />
    )
    expect(screen.getByText(/under 20%/i)).toBeInTheDocument()
  })

  it('requires the confirmation checkbox before allowing save', () => {
    const onBlockingStateChange = vi.fn()
    render(
      <SpeculativePresetPanel
        {...makeProps({
          strategyConfig: { ai_risk_preset: 'speculative' },
          onBlockingStateChange,
        })}
      />
    )
    // Confirmation unchecked by default → blocked.
    expect(onBlockingStateChange).toHaveBeenCalledWith(expect.objectContaining({ blocked: true }))
    const checkbox = screen.getByLabelText(/I understand the risk/i)
    act(() => {
      fireEvent.click(checkbox)
    })
    expect(onBlockingStateChange).toHaveBeenCalledWith(expect.objectContaining({ blocked: false }))
  })

  it('blocks save with actionable copy when the account bucket is 0', () => {
    const onBlockingStateChange = vi.fn()
    render(
      <SpeculativePresetPanel
        {...makeProps({
          strategyConfig: { ai_risk_preset: 'speculative' },
          accountSpeculativeAllocationPct: 0,
          onBlockingStateChange,
        })}
      />
    )
    // Actionable copy points the user to the Speculative Bucket settings.
    expect(screen.getByText(/Speculative Bucket/i)).toBeInTheDocument()
    expect(onBlockingStateChange).toHaveBeenCalledWith(
      expect.objectContaining({ blocked: true })
    )
  })

  it('stays non-blocking when the user picks a non-speculative preset', () => {
    const onBlockingStateChange = vi.fn()
    render(
      <SpeculativePresetPanel
        {...makeProps({
          strategyConfig: { ai_risk_preset: 'moderate' },
          accountSpeculativeAllocationPct: 0,
          onBlockingStateChange,
        })}
      />
    )
    expect(onBlockingStateChange).toHaveBeenCalledWith({ blocked: false, reason: null })
  })

  it('invokes onChange with ai_risk_preset when a preset is picked', () => {
    const onChange = vi.fn()
    render(<SpeculativePresetPanel {...makeProps({ onChange })} />)
    const select = screen.getByLabelText(/Risk Preset/i)
    act(() => {
      fireEvent.change(select, { target: { value: 'speculative' } })
    })
    expect(onChange).toHaveBeenCalledWith({ ai_risk_preset: 'speculative' })
  })

  it('renders nothing when strategy_type is not indicator_based', () => {
    const onBlockingStateChange = vi.fn()
    const { container } = render(
      <SpeculativePresetPanel
        {...makeProps({
          strategyType: 'grid_trading',
          onBlockingStateChange,
        })}
      />
    )
    // No controls from this panel at all.
    expect(container.textContent).toBe('')
    // And it must never block the parent form's save button when hidden.
    expect(onBlockingStateChange).toHaveBeenCalledWith({ blocked: false, reason: null })
  })

  it('does not block save on unsupported strategy even if speculative was picked earlier', () => {
    // User picked speculative on indicator_based, then switched strategy to grid_trading.
    // The panel disappears AND must clear any prior blocking state.
    const onBlockingStateChange = vi.fn()
    render(
      <SpeculativePresetPanel
        {...makeProps({
          strategyConfig: { ai_risk_preset: 'speculative' },
          accountSpeculativeAllocationPct: 0,
          strategyType: 'grid_trading',
          onBlockingStateChange,
        })}
      />
    )
    expect(onBlockingStateChange).toHaveBeenCalledWith({ blocked: false, reason: null })
  })

  it('renders the panel when strategy_type is indicator_based', () => {
    render(<SpeculativePresetPanel {...makeProps({ strategyType: 'indicator_based' })} />)
    expect(screen.getByLabelText(/Risk Preset/i)).toBeInTheDocument()
  })
})
