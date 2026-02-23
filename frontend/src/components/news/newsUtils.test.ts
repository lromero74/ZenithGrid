/**
 * Tests for newsUtils.tsx
 *
 * Tests pure helper functions: formatRelativeTime, sortSourcesByCategory.
 * Tests renderMarkdown for markdown-to-React conversion.
 */

import { describe, test, expect, vi, afterEach } from 'vitest'
import { formatRelativeTime, sortSourcesByCategory, renderMarkdown } from './newsUtils'

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

  test('returns "1m ago" for exactly 1 minute', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2025-06-15T12:01:00Z'))
    expect(formatRelativeTime('2025-06-15T12:00:00Z')).toBe('1m ago')
    vi.useRealTimers()
  })

  test('returns "59m ago" at 59 minutes boundary', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2025-06-15T12:59:00Z'))
    expect(formatRelativeTime('2025-06-15T12:00:00Z')).toBe('59m ago')
    vi.useRealTimers()
  })

  test('returns "1h ago" at exactly 1 hour', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2025-06-15T13:00:00Z'))
    expect(formatRelativeTime('2025-06-15T12:00:00Z')).toBe('1h ago')
    vi.useRealTimers()
  })

  test('returns "6d ago" at 6 days (still less than 7)', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2025-06-21T12:00:00Z'))
    expect(formatRelativeTime('2025-06-15T12:00:00Z')).toBe('6d ago')
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

  test('handles missing category as unknown', () => {
    const sources = [
      { id: 'no-cat' },
      { id: 'has-cat', category: 'Finance' },
    ]
    const sorted = sortSourcesByCategory(sources)
    expect(sorted[0].id).toBe('has-cat')
    expect(sorted[1].id).toBe('no-cat')
  })

  test('handles empty array', () => {
    expect(sortSourcesByCategory([])).toEqual([])
  })
})

describe('renderMarkdown', () => {
  test('renders plain paragraph text', () => {
    const elements = renderMarkdown('Hello world')
    expect(elements).toHaveLength(1)
  })

  test('renders h1 heading', () => {
    const elements = renderMarkdown('# Main Title')
    expect(elements).toHaveLength(1)
  })

  test('renders h2 heading', () => {
    const elements = renderMarkdown('## Sub Title')
    expect(elements).toHaveLength(1)
  })

  test('renders h3 heading', () => {
    const elements = renderMarkdown('### Section')
    expect(elements).toHaveLength(1)
  })

  test('renders h4 heading', () => {
    const elements = renderMarkdown('#### Detail')
    expect(elements).toHaveLength(1)
  })

  test('renders horizontal rule', () => {
    const elements = renderMarkdown('---')
    expect(elements).toHaveLength(1)
  })

  test('renders horizontal rule with asterisks', () => {
    const elements = renderMarkdown('***')
    expect(elements).toHaveLength(1)
  })

  test('renders unordered list', () => {
    const elements = renderMarkdown('- item one\n- item two\n- item three')
    // Should produce a single <ul> element
    expect(elements).toHaveLength(1)
  })

  test('renders ordered list', () => {
    const elements = renderMarkdown('1. first\n2. second')
    expect(elements).toHaveLength(1)
  })

  test('skips empty lines without adding elements', () => {
    const elements = renderMarkdown('para one\n\npara two')
    expect(elements).toHaveLength(2)
  })

  test('flushes pending list before new heading', () => {
    const md = '- item\n## Heading'
    const elements = renderMarkdown(md)
    // list + heading
    expect(elements).toHaveLength(2)
  })

  test('switches from ul to ol when list type changes', () => {
    const md = '- bullet\n\n1. numbered'
    const elements = renderMarkdown(md)
    expect(elements).toHaveLength(2)
  })

  test('skips h1 that matches titleToSkip (fuzzy match)', () => {
    const md = '# Bitcoin Price Surges\n\nSome content here.'
    const elements = renderMarkdown(md, 'Bitcoin Price Surges')
    // h1 should be skipped, only paragraph remains
    expect(elements).toHaveLength(1)
  })

  test('does not skip h1 when titleToSkip does not match', () => {
    const md = '# Completely Different Title\n\nContent.'
    const elements = renderMarkdown(md, 'Bitcoin Price')
    // Both h1 and paragraph should be present
    expect(elements).toHaveLength(2)
  })

  test('only skips the first matching h1', () => {
    const md = '# Repeated Title\n\n# Repeated Title'
    const elements = renderMarkdown(md, 'Repeated Title')
    // First is skipped, second is kept
    expect(elements).toHaveLength(1)
  })

  test('renders without titleToSkip', () => {
    const md = '# Title\n\nBody text'
    const elements = renderMarkdown(md)
    expect(elements).toHaveLength(2)
  })

  test('handles mixed content types', () => {
    const md = '# Title\n\nParagraph\n\n- bullet 1\n- bullet 2\n\n---\n\n## Sub'
    const elements = renderMarkdown(md)
    // h1, p, ul, hr, h2
    expect(elements).toHaveLength(5)
  })

  test('flushes remaining list at end of input', () => {
    const md = '- item 1\n- item 2'
    const elements = renderMarkdown(md)
    // Should produce one ul element (flushed at end)
    expect(elements).toHaveLength(1)
  })

  test('handles empty string', () => {
    const elements = renderMarkdown('')
    expect(elements).toHaveLength(0)
  })

  test('titleToSkip with special characters still matches via normalization', () => {
    const md = '# Bitcoin\'s Price: $100k!\n\nContent.'
    const elements = renderMarkdown(md, 'Bitcoin\'s Price: $100k!')
    // h1 should be skipped
    expect(elements).toHaveLength(1)
  })
})
