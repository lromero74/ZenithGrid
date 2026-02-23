/**
 * Tests for pages/news/helpers.ts
 *
 * Tests pure data filtering, pagination, markdown-to-text conversion,
 * and DOM-based highlight/scroll functions.
 */

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  filterNewsBySource,
  filterNewsByCategory,
  filterVideosBySource,
  filterVideosByCategory,
  paginateItems,
  calculateTotalPages,
  shouldResetPage,
  getUniqueSources,
  getUniqueVideoSources,
  countItemsBySource,
  filterBySeen,
  markdownToPlainText,
  filterByFullArticle,
  cleanupHoverHighlights,
  scrollToVideo,
  highlightVideo,
  unhighlightVideo,
  cleanupArticleHoverHighlights,
  highlightArticle,
  unhighlightArticle,
  scrollToArticle,
} from './helpers'

// Minimal news item
const news = (
  source: string,
  category: string,
  opts?: { is_seen?: boolean; has_issue?: boolean; content_scrape_allowed?: boolean }
) =>
  ({
    source, category, is_seen: opts?.is_seen, has_issue: opts?.has_issue,
    content_scrape_allowed: opts?.content_scrape_allowed,
  }) as any

const video = (source: string, category: string) =>
  ({ source, category }) as any

describe('filterNewsBySource', () => {
  test('returns all when sources set is empty', () => {
    const items = [news('a', 'crypto'), news('b', 'tech')]
    expect(filterNewsBySource(items, new Set())).toHaveLength(2)
  })

  test('filters by source set', () => {
    const items = [news('a', 'crypto'), news('b', 'tech'), news('a', 'markets')]
    const result = filterNewsBySource(items, new Set(['a']))
    expect(result).toHaveLength(2)
    expect(result.every((i: any) => i.source === 'a')).toBe(true)
  })

  test('returns empty when no sources match', () => {
    const items = [news('a', 'crypto'), news('b', 'tech')]
    expect(filterNewsBySource(items, new Set(['z']))).toHaveLength(0)
  })

  test('handles multiple sources in set', () => {
    const items = [news('a', 'crypto'), news('b', 'tech'), news('c', 'fin')]
    const result = filterNewsBySource(items, new Set(['a', 'c']))
    expect(result).toHaveLength(2)
  })
})

describe('filterNewsByCategory', () => {
  test('returns all for "all" string', () => {
    const items = [news('a', 'crypto'), news('b', 'tech')]
    expect(filterNewsByCategory(items, 'all')).toHaveLength(2)
  })

  test('returns all for "All" string', () => {
    expect(filterNewsByCategory([news('a', 'crypto')], 'All')).toHaveLength(1)
  })

  test('filters by specific category string', () => {
    const items = [news('a', 'crypto'), news('b', 'tech')]
    const result = filterNewsByCategory(items, 'crypto')
    expect(result).toHaveLength(1)
    expect(result[0].category).toBe('crypto')
  })

  test('filters by category Set', () => {
    const items = [news('a', 'crypto'), news('b', 'tech'), news('c', 'markets')]
    const result = filterNewsByCategory(items, new Set(['crypto', 'markets']))
    expect(result).toHaveLength(2)
  })

  test('returns empty for empty Set', () => {
    expect(filterNewsByCategory([news('a', 'crypto')], new Set())).toHaveLength(0)
  })

  test('returns empty for non-matching category string', () => {
    const items = [news('a', 'crypto')]
    expect(filterNewsByCategory(items, 'nonexistent')).toHaveLength(0)
  })
})

describe('filterVideosBySource', () => {
  test('returns all when sources set is empty', () => {
    expect(filterVideosBySource([video('a', 'x')], new Set())).toHaveLength(1)
  })

  test('filters by source', () => {
    const items = [video('a', 'x'), video('b', 'y')]
    expect(filterVideosBySource(items, new Set(['b']))).toHaveLength(1)
  })
})

describe('filterVideosByCategory', () => {
  test('filters by string category', () => {
    const items = [video('a', 'crypto'), video('b', 'tech')]
    expect(filterVideosByCategory(items, 'crypto')).toHaveLength(1)
  })

  test('filters by category Set', () => {
    const items = [video('a', 'crypto'), video('b', 'tech')]
    expect(filterVideosByCategory(items, new Set(['crypto']))).toHaveLength(1)
  })

  test('returns all for "all" string', () => {
    const items = [video('a', 'crypto'), video('b', 'tech')]
    expect(filterVideosByCategory(items, 'all')).toHaveLength(2)
  })

  test('returns all for "All" string', () => {
    const items = [video('a', 'crypto')]
    expect(filterVideosByCategory(items, 'All')).toHaveLength(1)
  })

  test('returns empty for empty Set', () => {
    expect(filterVideosByCategory([video('a', 'crypto')], new Set())).toHaveLength(0)
  })
})

describe('paginateItems', () => {
  const items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

  test('returns first page', () => {
    expect(paginateItems(items, 1, 3)).toEqual([1, 2, 3])
  })

  test('returns middle page', () => {
    expect(paginateItems(items, 2, 3)).toEqual([4, 5, 6])
  })

  test('returns last partial page', () => {
    expect(paginateItems(items, 4, 3)).toEqual([10])
  })

  test('returns empty for out-of-range page', () => {
    expect(paginateItems(items, 100, 3)).toEqual([])
  })

  test('returns all items when pageSize exceeds total', () => {
    expect(paginateItems(items, 1, 100)).toEqual(items)
  })

  test('returns empty for empty array', () => {
    expect(paginateItems([], 1, 10)).toEqual([])
  })
})

describe('calculateTotalPages', () => {
  test('calculates correctly', () => {
    expect(calculateTotalPages(10, 3)).toBe(4)
    expect(calculateTotalPages(9, 3)).toBe(3)
    expect(calculateTotalPages(1, 10)).toBe(1)
  })

  test('returns 1 for zero items', () => {
    expect(calculateTotalPages(0, 10)).toBe(1)
  })

  test('returns 1 for exact division', () => {
    expect(calculateTotalPages(6, 3)).toBe(2)
  })
})

describe('shouldResetPage', () => {
  test('returns true when page exceeds total', () => {
    expect(shouldResetPage(5, 3)).toBe(true)
  })

  test('returns false when page is within range', () => {
    expect(shouldResetPage(2, 3)).toBe(false)
  })

  test('returns false when totalPages is 0', () => {
    expect(shouldResetPage(1, 0)).toBe(false)
  })

  test('returns false when page equals totalPages', () => {
    expect(shouldResetPage(3, 3)).toBe(false)
  })

  test('returns true when page is just over total', () => {
    expect(shouldResetPage(4, 3)).toBe(true)
  })
})

describe('getUniqueSources', () => {
  test('returns unique sources', () => {
    const items = [news('a', 'x'), news('b', 'y'), news('a', 'z')]
    const sources = getUniqueSources(items)
    expect(sources).toHaveLength(2)
    expect(sources).toContain('a')
    expect(sources).toContain('b')
  })

  test('returns empty for no items', () => {
    expect(getUniqueSources([])).toEqual([])
  })
})

describe('getUniqueVideoSources', () => {
  test('returns unique video sources', () => {
    const items = [video('x', 'a'), video('y', 'b'), video('x', 'c')]
    expect(getUniqueVideoSources(items)).toHaveLength(2)
  })

  test('returns empty for no items', () => {
    expect(getUniqueVideoSources([])).toEqual([])
  })
})

describe('countItemsBySource', () => {
  test('counts matching items', () => {
    const items = [news('a', 'x'), news('b', 'y'), news('a', 'z')]
    expect(countItemsBySource(items, 'a')).toBe(2)
    expect(countItemsBySource(items, 'b')).toBe(1)
    expect(countItemsBySource(items, 'c')).toBe(0)
  })

  test('returns 0 for empty items', () => {
    expect(countItemsBySource([], 'a')).toBe(0)
  })
})

describe('filterBySeen', () => {
  const items = [
    news('a', 'x', { is_seen: true }),
    news('b', 'y', { is_seen: false }),
    news('c', 'z', { is_seen: false, has_issue: true }),
  ]

  test('returns all for "all" filter', () => {
    expect(filterBySeen(items, 'all')).toHaveLength(3)
  })

  test('returns unseen items', () => {
    const result = filterBySeen(items, 'unseen')
    expect(result).toHaveLength(2)
  })

  test('returns seen items', () => {
    const result = filterBySeen(items, 'seen')
    expect(result).toHaveLength(1)
    expect(result[0].source).toBe('a')
  })

  test('returns broken items', () => {
    const result = filterBySeen(items, 'broken')
    expect(result).toHaveLength(1)
    expect(result[0].source).toBe('c')
  })

  test('handles items with undefined is_seen as unseen', () => {
    const undefinedItems = [news('d', 'w')]
    expect(filterBySeen(undefinedItems, 'unseen')).toHaveLength(1)
    expect(filterBySeen(undefinedItems, 'seen')).toHaveLength(0)
  })
})

describe('filterByFullArticle', () => {
  test('filters out scrape-blocked items', () => {
    const items = [
      news('a', 'x', { content_scrape_allowed: true }),
      news('b', 'y', { content_scrape_allowed: false }),
      news('c', 'z'), // undefined = allowed
    ]
    const result = filterByFullArticle(items)
    expect(result).toHaveLength(2)
  })

  test('returns all when all are allowed', () => {
    const items = [
      news('a', 'x', { content_scrape_allowed: true }),
      news('b', 'y'),
    ]
    expect(filterByFullArticle(items)).toHaveLength(2)
  })

  test('returns empty when all blocked', () => {
    const items = [
      news('a', 'x', { content_scrape_allowed: false }),
    ]
    expect(filterByFullArticle(items)).toHaveLength(0)
  })
})

describe('markdownToPlainText', () => {
  test('strips heading markers', () => {
    expect(markdownToPlainText('# Hello World')).toBe('Hello World')
    expect(markdownToPlainText('## Sub heading')).toBe('Sub heading')
  })

  test('strips bold markers', () => {
    expect(markdownToPlainText('This is **bold** text')).toBe('This is bold text')
    expect(markdownToPlainText('This is __bold__ text')).toBe('This is bold text')
  })

  test('strips italic markers', () => {
    expect(markdownToPlainText('This is *italic* text')).toBe('This is italic text')
  })

  test('converts links to text', () => {
    expect(markdownToPlainText('[click here](https://example.com)')).toBe('click here')
  })

  test('removes images', () => {
    expect(markdownToPlainText('![alt text](image.png)')).toBe('alt text')
  })

  test('removes code blocks', () => {
    expect(markdownToPlainText('before\n```\ncode\n```\nafter')).toBe('before\n\nafter')
  })

  test('removes inline code', () => {
    expect(markdownToPlainText('use `console.log`')).toBe('use console.log')
  })

  test('removes HTML tags', () => {
    expect(markdownToPlainText('Hello <b>world</b>')).toBe('Hello world')
  })

  test('removes list markers', () => {
    expect(markdownToPlainText('- item one\n- item two')).toBe('item one\nitem two')
  })

  test('removes horizontal rules', () => {
    expect(markdownToPlainText('above\n---\nbelow')).toBe('above\n\nbelow')
  })

  test('removes ad artifacts', () => {
    expect(markdownToPlainText('SponsoredCustomers love it')).toBe('Customers love it')
  })

  test('handles empty string', () => {
    expect(markdownToPlainText('')).toBe('')
  })

  test('removes numbered list markers', () => {
    expect(markdownToPlainText('1. first\n2. second')).toBe('first\nsecond')
  })

  test('removes blockquote markers', () => {
    expect(markdownToPlainText('> quoted text')).toBe('quoted text')
  })

  test('strips bold italic markers', () => {
    expect(markdownToPlainText('***bold italic***')).toBe('bold italic')
  })

  test('strips underscore bold italic markers', () => {
    expect(markdownToPlainText('___bold italic___')).toBe('bold italic')
  })

  test('collapses multiple newlines', () => {
    expect(markdownToPlainText('a\n\n\n\nb')).toBe('a\n\nb')
  })

  test('collapses multiple spaces', () => {
    expect(markdownToPlainText('a   b   c')).toBe('a b c')
  })

  test('removes Advertisement artifacts', () => {
    expect(markdownToPlainText('AdvertisementGreat product')).toBe('Great product')
  })

  test('removes Promoted artifacts', () => {
    expect(markdownToPlainText('PromotedNew launch')).toBe('New launch')
  })

  test('removes standalone ad words', () => {
    expect(markdownToPlainText('Content here\nSponsored')).toBe('Content here')
  })

  test('removes stray ## artifacts', () => {
    expect(markdownToPlainText('Sponsored##More text')).toBe('More text')
  })

  test('trims whitespace from each line', () => {
    expect(markdownToPlainText('  hello  \n  world  ')).toBe('hello\nworld')
  })
})

// ── DOM-based functions ──────────────────────────────────────────────

describe('cleanupHoverHighlights', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  test('removes highlight classes from video elements', () => {
    const el = document.createElement('div')
    el.setAttribute('data-video-id', 'vid-1')
    el.classList.add('ring-4', 'ring-blue-500/50', 'border-blue-500')
    document.body.appendChild(el)

    cleanupHoverHighlights()

    expect(el.classList.contains('ring-4')).toBe(false)
    expect(el.classList.contains('ring-blue-500/50')).toBe(false)
    expect(el.classList.contains('border-blue-500')).toBe(false)
  })

  test('does nothing when no video elements exist', () => {
    // Should not throw
    cleanupHoverHighlights()
  })
})

describe('highlightVideo / unhighlightVideo', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  test('highlightVideo adds highlight classes', () => {
    const el = document.createElement('div')
    el.setAttribute('data-video-id', 'vid-2')
    document.body.appendChild(el)

    highlightVideo('vid-2')

    expect(el.classList.contains('ring-4')).toBe(true)
    expect(el.classList.contains('ring-blue-500/50')).toBe(true)
    expect(el.classList.contains('border-blue-500')).toBe(true)
  })

  test('highlightVideo does nothing for missing element', () => {
    // Should not throw
    highlightVideo('nonexistent')
  })

  test('unhighlightVideo removes highlight classes', () => {
    const el = document.createElement('div')
    el.setAttribute('data-video-id', 'vid-3')
    el.classList.add('ring-4', 'ring-blue-500/50', 'border-blue-500')
    document.body.appendChild(el)

    unhighlightVideo('vid-3')

    expect(el.classList.contains('ring-4')).toBe(false)
    expect(el.classList.contains('ring-blue-500/50')).toBe(false)
  })

  test('unhighlightVideo does nothing for missing element', () => {
    // Should not throw
    unhighlightVideo('nonexistent')
  })
})

describe('scrollToVideo', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  test('calls scrollIntoView on matching element', () => {
    const el = document.createElement('div')
    el.setAttribute('data-video-id', 'vid-scroll')
    el.scrollIntoView = vi.fn()
    document.body.appendChild(el)

    scrollToVideo('vid-scroll')

    expect(el.scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' })
  })

  test('adds pulse animation when addPulse is true', () => {
    vi.useFakeTimers()
    const el = document.createElement('div')
    el.setAttribute('data-video-id', 'vid-pulse')
    el.scrollIntoView = vi.fn()
    document.body.appendChild(el)

    scrollToVideo('vid-pulse', true)

    expect(el.classList.contains('animate-pulse-ring')).toBe(true)

    vi.advanceTimersByTime(3000)
    expect(el.classList.contains('animate-pulse-ring')).toBe(false)
    vi.useRealTimers()
  })

  test('does nothing for missing element', () => {
    // Should not throw
    scrollToVideo('nonexistent')
  })
})

describe('cleanupArticleHoverHighlights', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  test('removes highlight classes from article elements', () => {
    const el = document.createElement('div')
    el.setAttribute('data-article-url', 'https://example.com')
    el.classList.add('ring-4', 'ring-green-500/50', 'border-green-500')
    document.body.appendChild(el)

    cleanupArticleHoverHighlights()

    expect(el.classList.contains('ring-4')).toBe(false)
    expect(el.classList.contains('ring-green-500/50')).toBe(false)
    expect(el.classList.contains('border-green-500')).toBe(false)
  })
})

describe('highlightArticle / unhighlightArticle', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  test('highlightArticle adds green highlight classes', () => {
    const el = document.createElement('div')
    el.setAttribute('data-article-url', 'https://example.com/article')
    document.body.appendChild(el)

    highlightArticle('https://example.com/article')

    expect(el.classList.contains('ring-4')).toBe(true)
    expect(el.classList.contains('ring-green-500/50')).toBe(true)
    expect(el.classList.contains('border-green-500')).toBe(true)
  })

  test('highlightArticle does nothing for missing element', () => {
    highlightArticle('https://nonexistent.com')
  })

  test('unhighlightArticle removes green highlight classes', () => {
    const el = document.createElement('div')
    el.setAttribute('data-article-url', 'https://example.com/art')
    el.classList.add('ring-4', 'ring-green-500/50', 'border-green-500')
    document.body.appendChild(el)

    unhighlightArticle('https://example.com/art')

    expect(el.classList.contains('ring-4')).toBe(false)
  })
})

describe('scrollToArticle', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  test('calls scrollIntoView on matching element', () => {
    const el = document.createElement('div')
    el.setAttribute('data-article-url', 'https://example.com/scroll')
    el.scrollIntoView = vi.fn()
    document.body.appendChild(el)

    scrollToArticle('https://example.com/scroll')

    expect(el.scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' })
  })

  test('adds pulse animation when addPulse is true', () => {
    vi.useFakeTimers()
    const el = document.createElement('div')
    el.setAttribute('data-article-url', 'https://example.com/pulse')
    el.scrollIntoView = vi.fn()
    document.body.appendChild(el)

    scrollToArticle('https://example.com/pulse', true)

    expect(el.classList.contains('animate-pulse-ring')).toBe(true)

    vi.advanceTimersByTime(3000)
    expect(el.classList.contains('animate-pulse-ring')).toBe(false)
  })

  test('does nothing for missing element', () => {
    scrollToArticle('https://nonexistent.com')
  })
})
