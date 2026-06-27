import { describe, expect, it } from 'vitest'

import { isPaceOnTrack } from './goalTrendStatus'

describe('isPaceOnTrack', () => {
  it('treats actual above the ideal line as on track even when another metric is underfunded', () => {
    expect(isPaceOnTrack({ current_value: 0.75, ideal_value: 0.25 })).toBe(true)
  })

  it('treats actual below the ideal line as behind pace', () => {
    expect(isPaceOnTrack({ current_value: 0.10, ideal_value: 0.25 })).toBe(false)
  })

  it('allows tiny rounding noise at the ideal line', () => {
    expect(isPaceOnTrack({ current_value: 99.999999999, ideal_value: 100 })).toBe(true)
  })
})
