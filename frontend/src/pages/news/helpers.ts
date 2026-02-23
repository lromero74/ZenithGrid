/**
 * Helper utilities for News page
 *
 * Includes functions for:
 * - Cleaning up hover highlights
 * - Filtering news/videos by source
 * - Pagination helpers
 * - Source extraction
 */

import { NewsItem, VideoItem, SeenFilter } from '../../types/newsTypes'
export { markdownToPlainText, scrollToArticle } from '../../utils/newsHelpers'

/**
 * Clean up hover highlights from dropdown interactions
 * Removes visual effects from video elements when dropdown closes
 */
export const cleanupHoverHighlights = (): void => {
  document.querySelectorAll('[data-video-id]').forEach((el) => {
    el.classList.remove('ring-4', 'ring-blue-500/50', 'border-blue-500')
  })
}

/**
 * Filter news items by selected source
 * @param news - Array of news items
 * @param source - Source ID to filter by ('all' shows all sources)
 * @returns Filtered news array
 */
export const filterNewsBySource = (
  news: NewsItem[],
  sources: Set<string>
): NewsItem[] => {
  if (sources.size === 0) return news
  return news.filter((item) => sources.has(item.source))
}

/**
 * Filter news items by selected category
 * @param news - Array of news items
 * @param category - Category to filter by ('all' shows all categories)
 * @returns Filtered news array
 */
export const filterNewsByCategory = (
  news: NewsItem[],
  category: string | Set<string>
): NewsItem[] => {
  if (category instanceof Set) {
    if (category.size === 0) return []
    return news.filter((item) => category.has(item.category))
  }
  if (category === 'all' || category === 'All') return news
  return news.filter((item) => item.category === category)
}

/**
 * Filter videos by selected source
 * @param videos - Array of video items
 * @param source - Source ID to filter by ('all' shows all sources)
 * @returns Filtered videos array
 */
export const filterVideosBySource = (
  videos: VideoItem[],
  sources: Set<string>
): VideoItem[] => {
  if (sources.size === 0) return videos
  return videos.filter((item) => sources.has(item.source))
}

/**
 * Filter videos by selected category
 * @param videos - Array of video items
 * @param category - Category to filter by ('all' shows all categories)
 * @returns Filtered videos array
 */
export const filterVideosByCategory = (
  videos: VideoItem[],
  category: string | Set<string>
): VideoItem[] => {
  if (category instanceof Set) {
    if (category.size === 0) return []
    return videos.filter((item) => category.has(item.category))
  }
  if (category === 'all' || category === 'All') return videos
  return videos.filter((item) => item.category === category)
}

/**
 * Paginate an array of items
 * @param items - Items to paginate
 * @param page - Current page (1-indexed)
 * @param pageSize - Number of items per page
 * @returns Sliced array for current page
 */
export const paginateItems = <T>(
  items: T[],
  page: number,
  pageSize: number
): T[] => {
  const startIndex = (page - 1) * pageSize
  const endIndex = startIndex + pageSize
  return items.slice(startIndex, endIndex)
}

/**
 * Calculate total number of pages
 * @param totalItems - Total number of items
 * @param pageSize - Number of items per page
 * @returns Total pages (minimum 1)
 */
export const calculateTotalPages = (
  totalItems: number,
  pageSize: number
): number => {
  return Math.ceil(totalItems / pageSize) || 1
}

/**
 * Check if current page is out of bounds and should reset
 * @param currentPage - Current page number
 * @param totalPages - Total number of pages
 * @returns True if page should reset to 1
 */
export const shouldResetPage = (
  currentPage: number,
  totalPages: number
): boolean => {
  return currentPage > totalPages && totalPages > 0
}

/**
 * Extract unique sources from news items
 * @param items - News items
 * @returns Array of unique source IDs
 */
export const getUniqueSources = (items: NewsItem[]): string[] => {
  const sources = new Set<string>()
  items.forEach((item) => sources.add(item.source))
  return Array.from(sources)
}

/**
 * Extract unique video sources from video items
 * @param items - Video items
 * @returns Array of unique source IDs
 */
export const getUniqueVideoSources = (items: VideoItem[]): string[] => {
  const sources = new Set<string>()
  items.forEach((item) => sources.add(item.source))
  return Array.from(sources)
}

/**
 * Count items by source
 * @param items - News or video items
 * @param sourceId - Source ID to count
 * @returns Number of items from that source
 */
export const countItemsBySource = <T extends { source: string }>(
  items: T[],
  sourceId: string
): number => {
  return items.filter((item) => item.source === sourceId).length
}

/**
 * Scroll to an element by data attribute with smooth animation
 * @param videoId - Video ID to scroll to
 * @param addPulse - Whether to add pulse animation
 */
export const scrollToVideo = (videoId: string, addPulse = false): void => {
  const element = document.querySelector(`[data-video-id="${videoId}"]`)
  if (!element) return

  element.scrollIntoView({ behavior: 'smooth', block: 'center' })

  if (addPulse) {
    element.classList.add('animate-pulse-ring')
    setTimeout(() => {
      element.classList.remove('animate-pulse-ring')
    }, 3000)
  }
}

/**
 * Add blue highlight halo to video element
 * @param videoId - Video ID to highlight
 */
export const highlightVideo = (videoId: string): void => {
  const element = document.querySelector(`[data-video-id="${videoId}"]`)
  if (!element) return
  element.classList.add('ring-4', 'ring-blue-500/50', 'border-blue-500')
}

/**
 * Remove blue highlight halo from video element
 * @param videoId - Video ID to unhighlight
 */
export const unhighlightVideo = (videoId: string): void => {
  const element = document.querySelector(`[data-video-id="${videoId}"]`)
  if (!element) return
  element.classList.remove('ring-4', 'ring-blue-500/50', 'border-blue-500')
}

/**
 * Clean up hover highlights from article dropdown interactions
 * Removes visual effects from article elements when dropdown closes
 */
export const cleanupArticleHoverHighlights = (): void => {
  document.querySelectorAll('[data-article-url]').forEach((el) => {
    el.classList.remove('ring-4', 'ring-green-500/50', 'border-green-500')
  })
}

/**
 * Add green highlight halo to article element
 * @param articleUrl - Article URL to highlight
 */
export const highlightArticle = (articleUrl: string): void => {
  const element = document.querySelector(`[data-article-url="${CSS.escape(articleUrl)}"]`)
  if (!element) return
  element.classList.add('ring-4', 'ring-green-500/50', 'border-green-500')
}

/**
 * Remove green highlight halo from article element
 * @param articleUrl - Article URL to unhighlight
 */
export const unhighlightArticle = (articleUrl: string): void => {
  const element = document.querySelector(`[data-article-url="${CSS.escape(articleUrl)}"]`)
  if (!element) return
  element.classList.remove('ring-4', 'ring-green-500/50', 'border-green-500')
}

/**
 * Filter items by seen/unseen/broken status
 * @param items - News or video items with is_seen and has_issue fields
 * @param filter - 'all' | 'unseen' | 'seen' | 'broken'
 * @returns Filtered items
 */
export const filterBySeen = <T extends { is_seen?: boolean; has_issue?: boolean }>(
  items: T[],
  filter: SeenFilter,
): T[] => {
  if (filter === 'all') return items
  if (filter === 'unseen') return items.filter(item => !item.is_seen)
  if (filter === 'broken') return items.filter(item => item.has_issue)
  return items.filter(item => item.is_seen)
}

/**
 * Filter to only full-article sources (exclude summary-only sources that block scraping)
 */
export const filterByFullArticle = (items: NewsItem[]): NewsItem[] =>
  items.filter(item => item.content_scrape_allowed !== false)
