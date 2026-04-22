/**
 * SpeculativeSignalBreakdown — renders the catalyst scorer output.
 *
 * See PRP high-risk-doubling-preset §Task D4. Surfaces the LLM-reported
 * doubling_probability_score plus the per-component breakdown from the
 * pre-AI quantitative scorer.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'

import { SpeculativeSignalBreakdown } from './SpeculativeSignalBreakdown'

describe('SpeculativeSignalBreakdown', () => {
  it('renders nothing when both doubling score and components are absent', () => {
    const { container } = render(
      <SpeculativeSignalBreakdown
        doublingProbabilityScore={null}
        speculativeScore={null}
        components={null}
      />
    )
    expect(container.textContent).toBe('')
  })

  it('shows the doubling_probability_score when present', () => {
    render(
      <SpeculativeSignalBreakdown
        doublingProbabilityScore={42}
        speculativeScore={65}
        components={null}
      />
    )
    expect(screen.getByText(/42/)).toBeInTheDocument()
    expect(screen.getByText(/Doubling probability/i)).toBeInTheDocument()
  })

  it('lists each component with its weight and fired status', () => {
    render(
      <SpeculativeSignalBreakdown
        doublingProbabilityScore={null}
        speculativeScore={45}
        components={{
          volume_surge: { fired: true, weight: 25, contribution: 25 },
          compression_breakout: { fired: true, weight: 20, contribution: 20 },
          momentum_accelerating: { fired: false, weight: 20, contribution: 0 },
        }}
      />
    )
    expect(screen.getByText(/volume_surge/)).toBeInTheDocument()
    expect(screen.getByText(/compression_breakout/)).toBeInTheDocument()
    expect(screen.getByText(/momentum_accelerating/)).toBeInTheDocument()
    // Speculative score headline.
    expect(screen.getByText(/45/)).toBeInTheDocument()
  })

  it('visually differentiates fired vs unfired components', () => {
    const { container } = render(
      <SpeculativeSignalBreakdown
        doublingProbabilityScore={null}
        speculativeScore={25}
        components={{
          volume_surge: { fired: true, weight: 25, contribution: 25 },
          correlation_break: { fired: false, weight: 10, contribution: 0 },
        }}
      />
    )
    const fired = container.querySelector('[data-component-fired="true"]')
    const notFired = container.querySelector('[data-component-fired="false"]')
    expect(fired).toBeTruthy()
    expect(notFired).toBeTruthy()
  })
})
