/**
 * useNewsFilters Hook
 *
 * Manages filtering and pagination state for news articles and videos.
 * Handles source filtering, client-side pagination, and page reset logic.
 */

import { useState, useEffect, useMemo } from 'react'
import { NewsItem, VideoItem, NewsResponse, VideoResponse } from '../types'
import {
  filterNewsBySource,
  filterVideosBySource,
  paginateItems,
  calculateTotalPages,
  shouldResetPage,
} from '../helpers'

export interface UseNewsFiltersReturn {
  selectedSource: string
  setSelectedSource: (source: string) => void
  selectedVideoSource: string
  setSelectedVideoSource: (source: string) => void
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
  const [selectedVideoSource, setSelectedVideoSource] = useState<string>('all')
  const [currentPage, setCurrentPage] = useState(1)

  // Filter news by selected source
  const filteredNews = useMemo(
    () => filterNewsBySource(newsData?.news || [], selectedSource),
    [newsData?.news, selectedSource]
  )

  // Filter videos by selected source
  const filteredVideos = useMemo(
    () => filterVideosBySource(videoData?.videos || [], selectedVideoSource),
    [videoData?.videos, selectedVideoSource]
  )

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
    selectedVideoSource,
    setSelectedVideoSource,
    currentPage,
    setCurrentPage,
    filteredNews,
    filteredVideos,
    paginatedNews,
    totalPages,
    totalFilteredItems,
  }
}
