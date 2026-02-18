/**
 * useSeenStatus Hook
 *
 * Provides functions to mark news articles and videos as seen/unseen.
 * Uses optimistic updates for instant UI feedback — mutates the React Query
 * cache directly, then sends the API call in the background.
 */

import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { authFetch } from '../../../services/api'
import { NewsResponse, VideoResponse } from '../types'

export interface UseSeenStatusReturn {
  markSeen: (contentType: 'article' | 'video', contentId: number, seen?: boolean) => Promise<void>
  bulkMarkSeen: (contentType: 'article' | 'video', contentIds: number[], seen?: boolean) => Promise<void>
}

function getCacheKey(contentType: 'article' | 'video'): string[] {
  return contentType === 'article' ? ['crypto-news'] : ['crypto-videos']
}

export const useSeenStatus = (): UseSeenStatusReturn => {
  const queryClient = useQueryClient()

  // Optimistically update a single item's is_seen in the cache
  const optimisticUpdate = useCallback((
    contentType: 'article' | 'video',
    contentId: number,
    seen: boolean,
  ) => {
    const key = getCacheKey(contentType)

    if (contentType === 'article') {
      queryClient.setQueryData<NewsResponse>(key, (old) => {
        if (!old) return old
        return {
          ...old,
          news: old.news.map(item =>
            item.id === contentId ? { ...item, is_seen: seen } : item
          ),
        }
      })
    } else {
      queryClient.setQueryData<VideoResponse>(key, (old) => {
        if (!old) return old
        return {
          ...old,
          videos: old.videos.map(item =>
            item.id === contentId ? { ...item, is_seen: seen } : item
          ),
        }
      })
    }
  }, [queryClient])

  // Optimistically update multiple items' is_seen in the cache
  const optimisticBulkUpdate = useCallback((
    contentType: 'article' | 'video',
    contentIds: number[],
    seen: boolean,
  ) => {
    const idSet = new Set(contentIds)
    const key = getCacheKey(contentType)

    if (contentType === 'article') {
      queryClient.setQueryData<NewsResponse>(key, (old) => {
        if (!old) return old
        return {
          ...old,
          news: old.news.map(item =>
            item.id != null && idSet.has(item.id) ? { ...item, is_seen: seen } : item
          ),
        }
      })
    } else {
      queryClient.setQueryData<VideoResponse>(key, (old) => {
        if (!old) return old
        return {
          ...old,
          videos: old.videos.map(item =>
            item.id != null && idSet.has(item.id) ? { ...item, is_seen: seen } : item
          ),
        }
      })
    }
  }, [queryClient])

  const markSeen = useCallback(async (
    contentType: 'article' | 'video',
    contentId: number,
    seen = true,
  ) => {
    // Instant UI update
    optimisticUpdate(contentType, contentId, seen)

    // Background API call — revert on failure
    try {
      await authFetch('/api/news/seen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content_type: contentType, content_id: contentId, seen }),
      })
    } catch {
      // Revert optimistic update
      optimisticUpdate(contentType, contentId, !seen)
    }
  }, [optimisticUpdate])

  const bulkMarkSeen = useCallback(async (
    contentType: 'article' | 'video',
    contentIds: number[],
    seen = true,
  ) => {
    if (contentIds.length === 0) return

    // Instant UI update
    optimisticBulkUpdate(contentType, contentIds, seen)

    // Background API call — revert on failure
    try {
      await authFetch('/api/news/seen/bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content_type: contentType, content_ids: contentIds, seen }),
      })
    } catch {
      // Revert optimistic update
      optimisticBulkUpdate(contentType, contentIds, !seen)
    }
  }, [optimisticBulkUpdate])

  return { markSeen, bulkMarkSeen }
}
