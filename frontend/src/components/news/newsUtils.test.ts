/**
 * Tests for newsUtils.tsx
 *
 * Tests pure helper functions: formatRelativeTime, sortSourcesByCategory.
 * renderMarkdown is a React component — tested separately if needed.
 */

import { describe, test, expect, vi, afterEach } from 'vitest'
import { formatRelativeTime, sortSourcesByCategory } from './newsUtils'

describe('formatRelativeTime', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  test('returns empty string for null', () => {
    expect(formatRelativeTime(null)).toBe('')
  })

  test('returns "Just now" for very recent time', () => {
    const now = new Date().toISOString()
    expect(formatRelativeTime(now)).toBe('Just now')
  })

  test('returns minutes ago', () => {
    vi.useFakeTimers()
    const baseTime = new Date('2025-06-15T12:00:00Z')
    vi.setSystemTime(baseTime)

    const fiveMinAgo = new Date('2025-06-15T11:55:00Z').toISOString()
    expect(formatRelativeTime(fiveMinAgo)).toBe('5m ago')
    vi.useRealTimers()
  })

  test('returns hours ago', () => {
    vi.useFakeTimers()
    const baseTime = new Date('2025-06-15T12:00:00Z')
    vi.setSystemTime(baseTime)

    const threeHoursAgo = new Date('2025-06-15T09:00:00Z').toISOString()
    expect(formatRelativeTime(threeHoursAgo)).toBe('3h ago')
    vi.useRealTimers()
  })

  test('returns days ago', () => {
    vi.useFakeTimers()
    const baseTime = new Date('2025-06-15T12:00:00Z')
    vi.setSystemTime(baseTime)

    const twoDaysAgo = new Date('2025-06-13T12:00:00Z').toISOString()
    expect(formatRelativeTime(twoDaysAgo)).toBe('2d ago')
    vi.useRealTimers()
  })

  test('returns formatted date for old items', () => {
    vi.useFakeTimers()
    const baseTime = new Date('2025-06-15T12:00:00Z')
    vi.setSystemTime(baseTime)

    const twoWeeksAgo = new Date('2025-06-01T12:00:00Z').toISOString()
    const result = formatRelativeTime(twoWeeksAgo)
    // Should be a date string, not relative
    expect(result).not.toContain('ago')
    vi.useRealTimers()
  })
})

describe('sortSourcesByCategory', () => {
  test('sorts by category order', () => {
    const sources = [
      { id: 'tech-source', category: 'Technology' },
      { id: 'crypto-source', category: 'CryptoCurrency' },
      { id: 'finance-source', category: 'Finance' },
    ]
    const sorted = sortSourcesByCategory(sources)
    // CryptoCurrency < Finance < Technology in NEWS_CATEGORIES
    expect(sorted[0].id).toBe('crypto-source')
    expect(sorted[1].id).toBe('finance-source')
    expect(sorted[2].id).toBe('tech-source')
  })

  test('sorts alphabetically within same category', () => {
    const sources = [
      { id: 'zz-source', category: 'CryptoCurrency' },
      { id: 'aa-source', category: 'CryptoCurrency' },
    ]
    const sorted = sortSourcesByCategory(sources)
    expect(sorted[0].id).toBe('aa-source')
    expect(sorted[1].id).toBe('zz-source')
  })

  test('unknown categories sort last', () => {
    const sources = [
      { id: 'unknown', category: 'Unknown' },
      { id: 'crypto', category: 'CryptoCurrency' },
    ]
    const sorted = sortSourcesByCategory(sources)
    expect(sorted[0].id).toBe('crypto')
    expect(sorted[1].id).toBe('unknown')
  })

  test('does not mutate original array', () => {
    const sources = [
      { id: 'b', category: 'Technology' },
      { id: 'a', category: 'CryptoCurrency' },
    ]
    const original = [...sources]
    sortSourcesByCategory(sources)
    expect(sources).toEqual(original)
  })
})
