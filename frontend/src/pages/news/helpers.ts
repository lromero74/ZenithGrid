/**
 * Helper utilities for News page
 *
 * Includes functions for:
 * - Cleaning up hover highlights
 * - Filtering news/videos by source
 * - Pagination helpers
 * - Source extraction
 */

import { NewsItem, VideoItem } from './types'

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
  source: string
): NewsItem[] => {
  if (source === 'all') return news
  return news.filter((item) => item.source === source)
}

/**
 * Filter videos by selected source
 * @param videos - Array of video items
 * @param source - Source ID to filter by ('all' shows all sources)
 * @returns Filtered videos array
 */
export const filterVideosBySource = (
  videos: VideoItem[],
  source: string
): VideoItem[] => {
  if (source === 'all') return videos
  return videos.filter((item) => item.source === source)
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
