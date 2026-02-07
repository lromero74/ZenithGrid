/**
 * useNewsFilters Hook
 *
 * Manages filtering and pagination state for news articles and videos.
 * Handles multi-select category filtering, source filtering, client-side pagination, and page reset logic.
 */

import { useState, useEffect, useMemo, useCallback } from 'react'
import { NewsItem, VideoItem, NewsResponse, VideoResponse, NEWS_CATEGORIES } from '../types'
import {
  filterNewsBySource,
  filterNewsByCategory,
  filterVideosBySource,
  filterVideosByCategory,
  paginateItems,
  calculateTotalPages,
  shouldResetPage,
} from '../helpers'

export interface UseNewsFiltersReturn {
  selectedSource: string
  setSelectedSource: (source: string) => void
  selectedCategories: Set<string>
  toggleCategory: (category: string) => void
  toggleAllCategories: () => void
  allCategoriesSelected: boolean
  selectedVideoSource: string
  setSelectedVideoSource: (source: string) => void
  selectedVideoCategories: Set<string>
  toggleVideoCategory: (category: string) => void
  toggleAllVideoCategories: () => void
  allVideoCategoriesSelected: boolean
  currentPage: number
  setCurrentPage: (page: number | ((prev: number) => number)) => void
  filteredNews: NewsItem[]
  filteredVideos: VideoItem[]
  paginatedNews: NewsItem[]
  totalPages: number
  totalFilteredItems: number
}

interface UseNewsFiltersProps {
  newsData: NewsResponse | undefined
  videoData: VideoResponse | undefined
  pageSize: number
}

/**
 * Hook to manage news/video filtering and pagination
 */
export const useNewsFilters = ({
  newsData,
  videoData,
  pageSize,
}: UseNewsFiltersProps): UseNewsFiltersReturn => {
  const [selectedSource, setSelectedSource] = useState<string>('all')
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(() => new Set(['CryptoCurrency']))
  const [selectedVideoSource, setSelectedVideoSource] = useState<string>('all')
  const [selectedVideoCategories, setSelectedVideoCategories] = useState<Set<string>>(() => new Set(['CryptoCurrency']))
  const [currentPage, setCurrentPage] = useState(1)

  const allCategoriesSelected = selectedCategories.size === NEWS_CATEGORIES.length
  const allVideoCategoriesSelected = selectedVideoCategories.size === NEWS_CATEGORIES.length

  const toggleCategory = useCallback((category: string) => {
    setSelectedCategories(prev => {
      const next = new Set(prev)
      if (next.has(category)) {
        // Don't allow deselecting the last category
        if (next.size > 1) next.delete(category)
      } else {
        next.add(category)
      }
      return next
    })
    setSelectedSource('all')
    setCurrentPage(1)
  }, [])

  const toggleAllCategories = useCallback(() => {
    setSelectedCategories(prev => {
      if (prev.size === NEWS_CATEGORIES.length) {
        // All selected -> select only CryptoCurrency
        return new Set(['CryptoCurrency'])
      } else {
        // Not all selected -> select all
        return new Set(NEWS_CATEGORIES)
      }
    })
    setSelectedSource('all')
    setCurrentPage(1)
  }, [])

  const toggleVideoCategory = useCallback((category: string) => {
    setSelectedVideoCategories(prev => {
      const next = new Set(prev)
      if (next.has(category)) {
        if (next.size > 1) next.delete(category)
      } else {
        next.add(category)
      }
      return next
    })
    setSelectedVideoSource('all')
  }, [])

  const toggleAllVideoCategories = useCallback(() => {
    setSelectedVideoCategories(prev => {
      if (prev.size === NEWS_CATEGORIES.length) {
        return new Set(['CryptoCurrency'])
      } else {
        return new Set(NEWS_CATEGORIES)
      }
    })
    setSelectedVideoSource('all')
  }, [])

  // Filter news by selected categories first, then by source
  const filteredNews = useMemo(() => {
    const byCategory = filterNewsByCategory(newsData?.news || [], selectedCategories)
    return filterNewsBySource(byCategory, selectedSource)
  }, [newsData?.news, selectedCategories, selectedSource])

  // Filter videos by selected categories first, then by source
  const filteredVideos = useMemo(() => {
    const byCategory = filterVideosByCategory(videoData?.videos || [], selectedVideoCategories)
    return filterVideosBySource(byCategory, selectedVideoSource)
  }, [videoData?.videos, selectedVideoCategories, selectedVideoSource])

  // Client-side pagination - slice filtered news for current page (instant page changes)
  const totalFilteredItems = filteredNews.length
  const totalPages = useMemo(
    () => calculateTotalPages(totalFilteredItems, pageSize),
    [totalFilteredItems, pageSize]
  )

  const paginatedNews = useMemo(
    () => paginateItems(filteredNews, currentPage, pageSize),
    [filteredNews, currentPage, pageSize]
  )

  // Reset to page 1 if current page is out of bounds (e.g., after filtering)
  useEffect(() => {
    if (shouldResetPage(currentPage, totalPages)) {
      setCurrentPage(1)
    }
  }, [currentPage, totalPages])

  return {
    selectedSource,
    setSelectedSource,
    selectedCategories,
    toggleCategory,
    toggleAllCategories,
    allCategoriesSelected,
    selectedVideoSource,
    setSelectedVideoSource,
    selectedVideoCategories,
    toggleVideoCategory,
    toggleAllVideoCategories,
    allVideoCategoriesSelected,
    currentPage,
    setCurrentPage,
    filteredNews,
    filteredVideos,
    paginatedNews,
    totalPages,
    totalFilteredItems,
  }
}
