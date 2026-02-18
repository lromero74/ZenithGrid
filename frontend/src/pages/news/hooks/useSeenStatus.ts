/**
 * useSeenStatus Hook
 *
 * Provides functions to mark news articles and videos as seen/unseen
 * and invalidate React Query cache so the UI updates.
 */

import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { authFetch } from '../../../services/api'

export interface UseSeenStatusReturn {
  markSeen: (contentType: 'article' | 'video', contentId: number, seen?: boolean) => Promise<void>
  bulkMarkSeen: (contentType: 'article' | 'video', contentIds: number[], seen?: boolean) => Promise<void>
}

export const useSeenStatus = (): UseSeenStatusReturn => {
  const queryClient = useQueryClient()

  const invalidateCache = useCallback((contentType: 'article' | 'video') => {
    const key = contentType === 'article' ? 'crypto-news' : 'crypto-videos'
    queryClient.invalidateQueries({ queryKey: [key] })
  }, [queryClient])

  const markSeen = useCallback(async (
    contentType: 'article' | 'video',
    contentId: number,
    seen = true,
  ) => {
    await authFetch('/api/news/seen', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content_type: contentType, content_id: contentId, seen }),
    })
    invalidateCache(contentType)
  }, [invalidateCache])

  const bulkMarkSeen = useCallback(async (
    contentType: 'article' | 'video',
    contentIds: number[],
    seen = true,
  ) => {
    if (contentIds.length === 0) return
    await authFetch('/api/news/seen/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content_type: contentType, content_ids: contentIds, seen }),
    })
    invalidateCache(contentType)
  }, [invalidateCache])

  return { markSeen, bulkMarkSeen }
}
