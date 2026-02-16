/**
 * useNewsData Hook
 *
 * Manages data fetching for news articles and videos.
 * Uses React Query for caching and automatic refetching.
 */

import { useQuery } from '@tanstack/react-query'
import { NewsResponse, VideoResponse } from '../types'

interface UseNewsDataOptions {
  /** When true, suppresses auto-refetch to avoid disrupting the user */
  isUserEngaged?: boolean
}

export interface UseNewsDataReturn {
  newsData: NewsResponse | undefined
  videoData: VideoResponse | undefined
  newsLoading: boolean
  videosLoading: boolean
  newsError: Error | null
  videosError: Error | null
  newsFetching: boolean
  videosFetching: boolean
  refetchNews: () => void
  refetchVideos: () => void
  handleForceRefresh: (activeTab: 'articles' | 'videos') => Promise<void>
}

const REFETCH_INTERVAL = 1000 * 60 * 15 // 15 minutes

/**
 * Hook to fetch news articles and videos with caching.
 * Auto-refetch is suppressed when user is engaged (reading/listening).
 */
export const useNewsData = (options?: UseNewsDataOptions): UseNewsDataReturn => {
  const isUserEngaged = options?.isUserEngaged ?? false

  // Fetch recent news articles (limited to reduce memory on mobile devices)
  const {
    data: newsData,
    isLoading: newsLoading,
    error: newsError,
    refetch: refetchNews,
    isFetching: newsFetching,
  } = useQuery<NewsResponse>({
    queryKey: ['crypto-news'],
    queryFn: async () => {
      const response = await fetch('/api/news/?page=1&page_size=500')
      if (!response.ok) throw new Error('Failed to fetch news')
      return response.json()
    },
    staleTime: 1000 * 60 * 15, // Consider fresh for 15 minutes
    gcTime: 1000 * 60 * 5, // Garbage collect 5 min after unmount (default is 5 min, explicit for clarity)
    refetchInterval: isUserEngaged ? false : REFETCH_INTERVAL,
    refetchOnWindowFocus: false,
    refetchOnReconnect: !isUserEngaged,
  })

  // Fetch video news
  const {
    data: videoData,
    isLoading: videosLoading,
    error: videosError,
    refetch: refetchVideos,
    isFetching: videosFetching,
  } = useQuery<VideoResponse>({
    queryKey: ['crypto-videos'],
    queryFn: async () => {
      const response = await fetch('/api/news/videos')
      if (!response.ok) throw new Error('Failed to fetch videos')
      return response.json()
    },
    staleTime: 1000 * 60 * 15, // Consider fresh for 15 minutes
    refetchInterval: isUserEngaged ? false : REFETCH_INTERVAL,
    refetchOnWindowFocus: false,
    refetchOnReconnect: !isUserEngaged,
  })

  /**
   * Force refresh data by hitting the API with force_refresh flag
   */
  const handleForceRefresh = async (activeTab: 'articles' | 'videos') => {
    if (activeTab === 'articles') {
      await fetch('/api/news/?force_refresh=true')
      refetchNews()
    } else {
      await fetch('/api/news/videos?force_refresh=true')
      refetchVideos()
    }
  }

  return {
    newsData,
    videoData,
    newsLoading,
    videosLoading,
    newsError: newsError as Error | null,
    videosError: videosError as Error | null,
    newsFetching,
    videosFetching,
    refetchNews,
    refetchVideos,
    handleForceRefresh,
  }
}
