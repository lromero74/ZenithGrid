import { describe, test, expect } from 'vitest'
import { formatUsd } from './numberFormat'

describe('formatUsd', () => {
  test('formats a whole-dollar value with grouping and 2 decimals', () => {
    expect(formatUsd(50000)).toBe('$50,000.00')
  })

  test('rounds to 2 decimals', () => {
    expect(formatUsd(1234.5)).toBe('$1,234.50')
    expect(formatUsd(0.005)).toBe('$0.01')
  })

  test('formats negatives with a leading minus before the symbol', () => {
    expect(formatUsd(-42.5)).toBe('-$42.50')
  })

  test('formats zero', () => {
    expect(formatUsd(0)).toBe('$0.00')
  })
})
