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
  selectedSources: Set<string>
  toggleSource: (source: string) => void
  toggleAllSources: () => void
  allSourcesSelected: boolean
  selectedCategories: Set<string>
  toggleCategory: (category: string) => void
  toggleAllCategories: () => void
  allCategoriesSelected: boolean
  selectedVideoSources: Set<string>
  toggleVideoSource: (source: string) => void
  toggleAllVideoSources: () => void
  allVideoSourcesSelected: boolean
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
const STORAGE_KEY = 'zenith-news-filters'

function loadSavedFilters() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function saveFilters(state: Record<string, unknown>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch { /* ignore quota errors */ }
}

export const useNewsFilters = ({
  newsData,
  videoData,
  pageSize,
}: UseNewsFiltersProps): UseNewsFiltersReturn => {
  const saved = useMemo(() => loadSavedFilters(), [])

  const [selectedSources, setSelectedSources] = useState<Set<string>>(
    () => new Set(saved?.selectedSources?.length ? saved.selectedSources : [])
  )
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(
    () => new Set(saved?.selectedCategories?.length ? saved.selectedCategories : NEWS_CATEGORIES)
  )
  const [selectedVideoSources, setSelectedVideoSources] = useState<Set<string>>(
    () => new Set(saved?.selectedVideoSources?.length ? saved.selectedVideoSources : [])
  )
  const [selectedVideoCategories, setSelectedVideoCategories] = useState<Set<string>>(
    () => new Set(saved?.selectedVideoCategories?.length ? saved.selectedVideoCategories : NEWS_CATEGORIES)
  )
  const [currentPage, setCurrentPage] = useState(saved?.currentPage ?? 1)

  // Persist filter state to localStorage
  useEffect(() => {
    saveFilters({
      selectedSources: Array.from(selectedSources),
      selectedCategories: Array.from(selectedCategories),
      selectedVideoSources: Array.from(selectedVideoSources),
      selectedVideoCategories: Array.from(selectedVideoCategories),
      currentPage,
    })
  }, [selectedSources, selectedCategories, selectedVideoSources, selectedVideoCategories, currentPage])

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
    setSelectedSources(new Set())
    setCurrentPage(1)
  }, [])

  const toggleAllCategories = useCallback(() => {
    setSelectedCategories(prev => {
      if (prev.size === NEWS_CATEGORIES.length) {
        return new Set(['CryptoCurrency'])
      } else {
        return new Set(NEWS_CATEGORIES)
      }
    })
    setSelectedSources(new Set())
    setCurrentPage(1)
  }, [])

  const allSourcesSelected = selectedSources.size === 0

  const toggleSource = useCallback((sourceId: string) => {
    setSelectedSources(prev => {
      const next = new Set(prev)
      if (next.has(sourceId)) {
        next.delete(sourceId)
      } else {
        next.add(sourceId)
      }
      return next
    })
    setCurrentPage(1)
  }, [])

  const toggleAllSources = useCallback(() => {
    setSelectedSources(new Set())
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
    setSelectedVideoSources(new Set())
  }, [])

  const toggleAllVideoCategories = useCallback(() => {
    setSelectedVideoCategories(prev => {
      if (prev.size === NEWS_CATEGORIES.length) {
        return new Set(['CryptoCurrency'])
      } else {
        return new Set(NEWS_CATEGORIES)
      }
    })
    setSelectedVideoSources(new Set())
  }, [])

  const allVideoSourcesSelected = selectedVideoSources.size === 0

  const toggleVideoSource = useCallback((sourceId: string) => {
    setSelectedVideoSources(prev => {
      const next = new Set(prev)
      if (next.has(sourceId)) {
        next.delete(sourceId)
      } else {
        next.add(sourceId)
      }
      return next
    })
  }, [])

  const toggleAllVideoSources = useCallback(() => {
    setSelectedVideoSources(new Set())
  }, [])

  // Filter news by selected categories first, then by source
  const filteredNews = useMemo(() => {
    const byCategory = filterNewsByCategory(newsData?.news || [], selectedCategories)
    return filterNewsBySource(byCategory, selectedSources)
  }, [newsData?.news, selectedCategories, selectedSources])

  // Filter videos by selected categories first, then by source
  const filteredVideos = useMemo(() => {
    const byCategory = filterVideosByCategory(videoData?.videos || [], selectedVideoCategories)
    return filterVideosBySource(byCategory, selectedVideoSources)
  }, [videoData?.videos, selectedVideoCategories, selectedVideoSources])

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
    selectedSources,
    toggleSource,
    toggleAllSources,
    allSourcesSelected,
    selectedCategories,
    toggleCategory,
    toggleAllCategories,
    allCategoriesSelected,
    selectedVideoSources,
    toggleVideoSource,
    toggleAllVideoSources,
    allVideoSourcesSelected,
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
