/**
 * Tests for useNewsFilters hook
 *
 * Verifies client-side filter state management, localStorage persistence,
 * category/source toggling, pagination, and filter reset behavior.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useNewsFilters } from './useNewsFilters'
import { NEWS_CATEGORIES } from '../../../types/newsTypes'
import type { NewsResponse, VideoResponse } from '../../../types/newsTypes'

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

const makeNewsData = (count: number): NewsResponse => ({
  news: Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    title: `Article ${i + 1}`,
    url: `https://example.com/${i + 1}`,
    source: i % 2 === 0 ? 'src-a' : 'src-b',
    source_name: i % 2 === 0 ? 'Source A' : 'Source B',
    published: '2026-01-01',
    summary: `Summary ${i + 1}`,
    thumbnail: null,
    category: NEWS_CATEGORIES[i % NEWS_CATEGORIES.length],
    is_seen: i % 3 === 0,
    content_scrape_allowed: i % 4 !== 0,
  })),
  sources: [
    { id: 'src-a', name: 'Source A', website: 'https://a.com' },
    { id: 'src-b', name: 'Source B', website: 'https://b.com' },
  ],
  cached_at: '2026-01-01T00:00:00Z',
  cache_expires_at: '2026-01-01T01:00:00Z',
  total_items: count,
  page: 1,
  page_size: 0,
  total_pages: 1,
})

const makeVideoData = (count: number): VideoResponse => ({
  videos: Array.from({ length: count }, (_, i) => ({
    id: i + 100,
    title: `Video ${i + 1}`,
    url: `https://youtube.com/${i + 1}`,
    video_id: `vid-${i}`,
    source: i % 2 === 0 ? 'yt-a' : 'yt-b',
    source_name: i % 2 === 0 ? 'Channel A' : 'Channel B',
    channel_name: i % 2 === 0 ? 'Channel A' : 'Channel B',
    published: '2026-01-01',
    thumbnail: null,
    description: `Desc ${i + 1}`,
    category: NEWS_CATEGORIES[i % NEWS_CATEGORIES.length],
    is_seen: i % 2 === 0,
  })),
  sources: [
    { id: 'yt-a', name: 'Channel A', website: 'https://youtube.com/a', description: 'A' },
    { id: 'yt-b', name: 'Channel B', website: 'https://youtube.com/b', description: 'B' },
  ],
  cached_at: '2026-01-01T00:00:00Z',
  cache_expires_at: '2026-01-01T01:00:00Z',
  total_items: count,
})

const defaultProps = {
  newsData: makeNewsData(24),
  videoData: makeVideoData(10),
  pageSize: 10,
}

describe('useNewsFilters initial state', () => {
  test('starts with all categories selected', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    expect(result.current.allCategoriesSelected).toBe(true)
    expect(result.current.selectedCategories.size).toBe(NEWS_CATEGORIES.length)
  })

  test('starts with all sources selected (selectAll mode)', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    expect(result.current.allSourcesSelected).toBe(true)
  })

  test('starts on page 1 with seenFilter "all"', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    expect(result.current.currentPage).toBe(1)
    expect(result.current.seenFilter).toBe('all')
    expect(result.current.fullArticlesOnly).toBe(false)
  })
})

describe('useNewsFilters category toggling', () => {
  test('toggleCategory removes a category from selection', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    act(() => {
      result.current.toggleCategory('CryptoCurrency')
    })

    expect(result.current.selectedCategories.has('CryptoCurrency')).toBe(false)
    expect(result.current.allCategoriesSelected).toBe(false)
  })

  test('toggleCategory adds a previously removed category', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    act(() => {
      result.current.toggleCategory('CryptoCurrency')
    })
    expect(result.current.selectedCategories.has('CryptoCurrency')).toBe(false)

    act(() => {
      result.current.toggleCategory('CryptoCurrency')
    })
    expect(result.current.selectedCategories.has('CryptoCurrency')).toBe(true)
  })

  test('toggleAllCategories deselects all when all are selected', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    act(() => {
      result.current.toggleAllCategories()
    })

    expect(result.current.selectedCategories.size).toBe(0)
    expect(result.current.allCategoriesSelected).toBe(false)
  })

  test('toggleAllCategories selects all when none are selected', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    // First deselect all
    act(() => { result.current.toggleAllCategories() })
    expect(result.current.selectedCategories.size).toBe(0)

    // Then select all
    act(() => { result.current.toggleAllCategories() })
    expect(result.current.selectedCategories.size).toBe(NEWS_CATEGORIES.length)
    expect(result.current.allCategoriesSelected).toBe(true)
  })

  test('toggleCategory resets current page to 1', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    act(() => { result.current.setCurrentPage(3) })

    act(() => { result.current.toggleCategory('Finance') })
    expect(result.current.currentPage).toBe(1)
  })
})

describe('useNewsFilters source toggling', () => {
  test('toggleSource in selectAll mode switches to individual selection', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    expect(result.current.allSourcesSelected).toBe(true)

    act(() => { result.current.toggleSource('src-a') })

    // Should now be in individual mode with all EXCEPT the toggled one
    expect(result.current.allSourcesSelected).toBe(false)
    expect(result.current.selectedSources.has('src-a')).toBe(false)
    expect(result.current.selectedSources.has('src-b')).toBe(true)
  })

  test('toggleAllSources switches from all to none', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    act(() => { result.current.toggleAllSources() })

    expect(result.current.allSourcesSelected).toBe(false)
    expect(result.current.selectedSources.size).toBe(0)
  })

  test('toggleAllSources switches from none to all', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    // Go to none
    act(() => { result.current.toggleAllSources() })
    expect(result.current.allSourcesSelected).toBe(false)

    // Back to all
    act(() => { result.current.toggleAllSources() })
    expect(result.current.allSourcesSelected).toBe(true)
  })
})

describe('useNewsFilters video toggles', () => {
  test('toggleVideoCategory removes a video category', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    act(() => { result.current.toggleVideoCategory('Technology') })

    expect(result.current.selectedVideoCategories.has('Technology')).toBe(false)
  })

  test('toggleAllVideoCategories toggles all video categories', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    act(() => { result.current.toggleAllVideoCategories() })
    expect(result.current.allVideoCategoriesSelected).toBe(false)
    expect(result.current.selectedVideoCategories.size).toBe(0)

    act(() => { result.current.toggleAllVideoCategories() })
    expect(result.current.allVideoCategoriesSelected).toBe(true)
  })

  test('toggleVideoSource in selectAll mode deselects one source', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    expect(result.current.allVideoSourcesSelected).toBe(true)

    act(() => { result.current.toggleVideoSource('yt-a') })

    expect(result.current.allVideoSourcesSelected).toBe(false)
    expect(result.current.selectedVideoSources.has('yt-a')).toBe(false)
    expect(result.current.selectedVideoSources.has('yt-b')).toBe(true)
  })

  test('toggleAllVideoSources toggles between all and none', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    act(() => { result.current.toggleAllVideoSources() })
    expect(result.current.allVideoSourcesSelected).toBe(false)

    act(() => { result.current.toggleAllVideoSources() })
    expect(result.current.allVideoSourcesSelected).toBe(true)
  })
})

describe('useNewsFilters seen filter', () => {
  test('setSeenFilter changes filter value', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    act(() => { result.current.setSeenFilter('unseen') })
    expect(result.current.seenFilter).toBe('unseen')

    act(() => { result.current.setSeenFilter('seen') })
    expect(result.current.seenFilter).toBe('seen')
  })

  test('setSeenVideoFilter changes video filter value', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    act(() => { result.current.setSeenVideoFilter('unseen') })
    expect(result.current.seenVideoFilter).toBe('unseen')
  })
})

describe('useNewsFilters filtering', () => {
  test('filteredNews returns all news when all filters are default', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    expect(result.current.filteredNews.length).toBe(defaultProps.newsData!.news.length)
  })

  test('filtering by category narrows results', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    // Deselect all, then select only CryptoCurrency
    act(() => { result.current.toggleAllCategories() })
    act(() => { result.current.toggleCategory('CryptoCurrency') })

    expect(result.current.filteredNews.length).toBeGreaterThan(0)
    result.current.filteredNews.forEach(item => {
      expect(item.category).toBe('CryptoCurrency')
    })
  })

  test('empty source selection with selectAll off returns empty', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    // Toggle all sources off
    act(() => { result.current.toggleAllSources() })

    expect(result.current.filteredNews.length).toBe(0)
  })

  test('fullArticlesOnly filters to only scrape-allowed articles', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    const totalBefore = result.current.filteredNews.length

    act(() => { result.current.setFullArticlesOnly(true) })

    expect(result.current.filteredNews.length).toBeLessThanOrEqual(totalBefore)
    result.current.filteredNews.forEach(item => {
      expect(item.content_scrape_allowed).not.toBe(false)
    })
  })

  test('returns empty filteredNews when newsData is undefined', () => {
    const { result } = renderHook(() => useNewsFilters({
      newsData: undefined,
      videoData: undefined,
      pageSize: 10,
    }))

    expect(result.current.filteredNews).toEqual([])
    expect(result.current.filteredVideos).toEqual([])
  })
})

describe('useNewsFilters pagination', () => {
  test('paginatedNews returns correct page size', () => {
    const { result } = renderHook(() => useNewsFilters({
      ...defaultProps,
      newsData: makeNewsData(25),
      pageSize: 10,
    }))

    expect(result.current.paginatedNews.length).toBe(10)
    expect(result.current.totalPages).toBe(3)
  })

  test('totalFilteredItems reflects filtered count', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    expect(result.current.totalFilteredItems).toBe(defaultProps.newsData!.news.length)
  })

  test('videoTotalPages calculates correctly', () => {
    const { result } = renderHook(() => useNewsFilters({
      ...defaultProps,
      videoData: makeVideoData(25),
      pageSize: 10,
    }))

    expect(result.current.videoTotalPages).toBe(3)
  })
})

describe('useNewsFilters localStorage persistence', () => {
  test('saves filter state to localStorage', () => {
    const { result } = renderHook(() => useNewsFilters(defaultProps))

    act(() => { result.current.setSeenFilter('unseen') })

    const saved = JSON.parse(localStorage.getItem('zenith-news-filters') || '{}')
    expect(saved.seenFilter).toBe('unseen')
  })

  test('restores filter state from localStorage', () => {
    localStorage.setItem('zenith-news-filters', JSON.stringify({
      selectedCategories: ['CryptoCurrency', 'Finance'],
      seenFilter: 'seen',
      currentPage: 2,
      fullArticlesOnly: true,
      sourceSelectAll: true,
      selectedSources: [],
      selectedVideoSources: [],
      videoSourceSelectAll: true,
      selectedVideoCategories: NEWS_CATEGORIES,
      videoPage: 1,
      seenVideoFilter: 'all',
    }))

    const { result } = renderHook(() => useNewsFilters(defaultProps))

    expect(result.current.seenFilter).toBe('seen')
    expect(result.current.selectedCategories.size).toBe(2)
    expect(result.current.selectedCategories.has('CryptoCurrency')).toBe(true)
    expect(result.current.fullArticlesOnly).toBe(true)
  })

  test('handles corrupted localStorage gracefully', () => {
    localStorage.setItem('zenith-news-filters', '{invalid json')

    const { result } = renderHook(() => useNewsFilters(defaultProps))

    // Should fall back to defaults without throwing
    expect(result.current.allCategoriesSelected).toBe(true)
    expect(result.current.seenFilter).toBe('all')
  })
})
