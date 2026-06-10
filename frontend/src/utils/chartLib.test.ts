/**
 * Tests for the lazy lightweight-charts loader.
 *
 * loadChartLib() must dynamically import the library exactly once and
 * return the same promise on every call so all consumers share one load.
 */

import { describe, test, expect, vi } from 'vitest'

vi.mock('lightweight-charts', () => ({
  createChart: vi.fn(),
  ColorType: { Solid: 'Solid' },
}))

import { loadChartLib } from './chartLib'

describe('loadChartLib', () => {
  test('resolves to the lightweight-charts module', async () => {
    const lib = await loadChartLib()
    expect(typeof lib.createChart).toBe('function')
    expect(lib.ColorType).toBeDefined()
  })

  test('returns the same promise on repeated calls (single shared load)', () => {
    const first = loadChartLib()
    const second = loadChartLib()
    expect(first).toBe(second)
  })
})
