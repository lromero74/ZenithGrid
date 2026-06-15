import { describe, test, expect } from 'vitest'
import { buildVisualRows, type PositionRow } from './visualRows'

type P = { id: number }

const row = (id: number, groupKey: string | null = null, showHeader = false): PositionRow<P> => ({
  position: { id },
  groupKey,
  showHeader,
})

describe('buildVisualRows', () => {
  test('happy path: tiles ungrouped cards into rows of `columns`', () => {
    const rows = [row(1), row(2), row(3), row(4)]
    const result = buildVisualRows(rows, 2)

    expect(result).toHaveLength(2)
    expect(result.every(r => r.kind === 'cards')).toBe(true)
    expect(result[0]).toMatchObject({ kind: 'cards', items: [{ position: { id: 1 } }, { position: { id: 2 } }] })
    expect(result[1]).toMatchObject({ kind: 'cards', items: [{ position: { id: 3 } }, { position: { id: 4 } }] })
  })

  test('edge: ragged last row holds the remainder', () => {
    const result = buildVisualRows([row(1), row(2), row(3)], 2)
    expect(result).toHaveLength(2)
    expect((result[1] as { items: unknown[] }).items).toHaveLength(1)
  })

  test('columns=1 yields one card per visual row', () => {
    const result = buildVisualRows([row(1), row(2), row(3)], 1)
    expect(result).toHaveLength(3)
    expect(result.every(r => r.kind === 'cards' && r.items.length === 1)).toBe(true)
  })

  test('group headers get their own row and reset the tiling chunk', () => {
    // Two groups of 3, columns=2. Each group must start a fresh chunk so cards
    // from different groups never share a row.
    const rows = [
      row(1, 'A', true), row(2, 'A'), row(3, 'A'),
      row(4, 'B', true), row(5, 'B'),
    ]
    const result = buildVisualRows(rows, 2)

    expect(result.map(r => r.kind)).toEqual(['header', 'cards', 'cards', 'header', 'cards'])
    // Group A: [1,2] then [3] (not [3,4] — B must not bleed in)
    expect((result[1] as { items: { position: P }[] }).items.map(i => i.position.id)).toEqual([1, 2])
    expect((result[2] as { items: { position: P }[] }).items.map(i => i.position.id)).toEqual([3])
    expect((result[4] as { items: { position: P }[] }).items.map(i => i.position.id)).toEqual([4, 5])
  })

  test('failure/edge: empty input and clamped column counts', () => {
    expect(buildVisualRows([], 2)).toEqual([])
    // columns < 1 is clamped to 1 (never produces an empty/zero-width row)
    expect(buildVisualRows([row(1), row(2)], 0)).toHaveLength(2)
    expect(buildVisualRows([row(1), row(2)], -3)).toHaveLength(2)
  })

  test('keys are stable and unique per row', () => {
    const result = buildVisualRows([row(1, 'A', true), row(2, 'A')], 2)
    const keys = result.map(r => r.key)
    expect(new Set(keys).size).toBe(keys.length)
    expect(keys[0]).toBe('header-A')
  })
})
