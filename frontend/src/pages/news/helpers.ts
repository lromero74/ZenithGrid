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

/**
 * Crypto/finance acronyms that should be spelled out letter-by-letter
 * Maps acronym to spaced version for TTS pronunciation
 */
const TTS_ACRONYMS: Record<string, string> = {
  // Crypto terms
  'NFT': 'N F T',
  'BTC': 'B T C',
  'ETH': 'E T H',
  'DAO': 'D A O',
  'DEX': 'D E X',
  'CEX': 'C E X',
  'ICO': 'I C O',
  'IDO': 'I D O',
  'IEO': 'I E O',
  'DCA': 'D C A',
  'ATH': 'A T H',
  'ATL': 'A T L',
  'TVL': 'T V L',
  'APY': 'A P Y',
  'APR': 'A P R',
  'KYC': 'K Y C',
  'AML': 'A M L',
  'FUD': 'F U D',
  'SOL': 'S O L',
  'XRP': 'X R P',
  'LTC': 'L T C',
  'DOT': 'D O T',
  'ADA': 'A D A',
  // Finance/regulatory
  'SEC': 'S E C',
  'ETF': 'E T F',
  'IPO': 'I P O',
  'CEO': 'C E O',
  'CFO': 'C F O',
  'CTO': 'C T O',
  'GDP': 'G D P',
  'USD': 'U S D',
  'EUR': 'E U R',
  'GBP': 'G B P',
  'JPY': 'J P Y',
  'API': 'A P I',
  'AI': 'A I',
  'ML': 'M L',
  'UI': 'U I',
  'UX': 'U X',
}

/**
 * Expand acronyms for consistent TTS pronunciation
 * Handles plurals (NFTs -> "N F T s") and possessives (NFT's -> "N F T's")
 * @param text - Text containing acronyms
 * @returns Text with acronyms expanded for letter-by-letter pronunciation
 */
export const expandAcronymsForTTS = (text: string): string => {
  let result = text

  // Sort by length descending to match longer acronyms first
  const sortedAcronyms = Object.keys(TTS_ACRONYMS).sort((a, b) => b.length - a.length)

  for (const acronym of sortedAcronyms) {
    const expanded = TTS_ACRONYMS[acronym]

    // Match acronym with optional plural 's' or possessive "'s"
    // Word boundary ensures we don't match partial words
    // Case insensitive matching, preserve original case in output
    const regex = new RegExp(`\\b(${acronym})(s|'s)?\\b`, 'gi')

    result = result.replace(regex, (match, base, suffix) => {
      // Use the expanded version, add suffix if present
      const expandedBase = base === base.toUpperCase() ? expanded : expanded.toLowerCase()
      return suffix ? `${expandedBase} ${suffix}` : expandedBase
    })
  }

  return result
}

/**
 * Convert markdown to plain text for TTS
 * Strips all markdown formatting while preserving readable content
 * @param markdown - Markdown formatted text
 * @returns Plain text suitable for text-to-speech
 */
export const markdownToPlainText = (markdown: string): string => {
  let text = markdown

  // Remove code blocks (``` ... ```)
  text = text.replace(/```[\s\S]*?```/g, '')

  // Remove inline code (`code`)
  text = text.replace(/`([^`]+)`/g, '$1')

  // Remove images ![alt](url)
  text = text.replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')

  // Convert links [text](url) to just text
  text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')

  // Remove heading markers (# ## ### etc) but keep the text
  text = text.replace(/^#{1,6}\s+/gm, '')

  // Remove bold/italic markers
  text = text.replace(/\*\*\*([^*]+)\*\*\*/g, '$1')  // ***bold italic***
  text = text.replace(/\*\*([^*]+)\*\*/g, '$1')      // **bold**
  text = text.replace(/\*([^*]+)\*/g, '$1')          // *italic*
  text = text.replace(/___([^_]+)___/g, '$1')        // ___bold italic___
  text = text.replace(/__([^_]+)__/g, '$1')          // __bold__
  text = text.replace(/_([^_]+)_/g, '$1')            // _italic_

  // Remove horizontal rules
  text = text.replace(/^[-*_]{3,}\s*$/gm, '')

  // Remove blockquote markers
  text = text.replace(/^>\s+/gm, '')

  // Remove list markers (-, *, +, 1., 2., etc)
  text = text.replace(/^[\s]*[-*+]\s+/gm, '')
  text = text.replace(/^[\s]*\d+\.\s+/gm, '')

  // Remove HTML tags if any
  text = text.replace(/<[^>]+>/g, '')

  // Collapse multiple newlines into double newline (paragraph break)
  text = text.replace(/\n{3,}/g, '\n\n')

  // Collapse multiple spaces
  text = text.replace(/[ \t]+/g, ' ')

  // Trim each line
  text = text.split('\n').map(line => line.trim()).join('\n')

  // Final trim
  return text.trim()
}
