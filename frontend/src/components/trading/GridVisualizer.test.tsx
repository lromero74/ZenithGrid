/**
 * Tests for GridVisualizer — A (sweep #4): a degenerate grid range (upper === lower)
 * must not divide by zero and push Infinity/NaN into inline `bottom:` styles.
 */
import { describe, test, expect } from 'vitest'
import { render } from '@testing-library/react'
import { GridVisualizer } from './GridVisualizer'

const level = (over: Record<string, unknown> = {}) => ({
  level_index: 0,
  price: 100,
  order_type: 'buy' as const,
  status: 'pending' as const,
  ...over,
})

describe('GridVisualizer', () => {
  test('degenerate range (upper === lower) emits no NaN/Infinity styles', () => {
    const gridState = {
      initialized_at: '2026-01-01T00:00:00Z',
      current_range_upper: 100,
      current_range_lower: 100, // priceRange would be 0 without the guard
      grid_levels: [level(), level({ level_index: 1, order_type: 'sell' as const })],
    }
    const { container } = render(
      <GridVisualizer gridState={gridState} currentPrice={100} productId="BTC-USD" />
    )
    expect(container.innerHTML).not.toContain('NaN')
    expect(container.innerHTML).not.toContain('Infinity')
  })

  test('normal range renders finite percentages', () => {
    const gridState = {
      initialized_at: '2026-01-01T00:00:00Z',
      current_range_upper: 110,
      current_range_lower: 90,
      grid_levels: [level({ price: 100 })],
    }
    const { container } = render(
      <GridVisualizer gridState={gridState} currentPrice={100} productId="BTC-USD" />
    )
    expect(container.innerHTML).not.toContain('NaN')
    expect(container.innerHTML).not.toContain('Infinity')
  })
})
