/**
 * useArticleContent Hook
 *
 * Manages fetching and caching full article content for reader mode.
 * Fetches content on-demand when reader mode is enabled.
 */

import { useState, useEffect } from 'react'
import { authFetch } from '../../../services/api'
import { ArticleContentResponse, NewsItem } from '../types'

export interface UseArticleContentReturn {
  articleContent: ArticleContentResponse | null
  articleContentLoading: boolean
  readerModeEnabled: boolean
  setReaderModeEnabled: (enabled: boolean) => void
  clearContent: () => void
}

interface UseArticleContentProps {
  previewArticle: NewsItem | null
}

/**
 * Hook to fetch article content for reader mode
 */
export const useArticleContent = ({
  previewArticle,
}: UseArticleContentProps): UseArticleContentReturn => {
  const [articleContent, setArticleContent] =
    useState<ArticleContentResponse | null>(null)
  const [articleContentLoading, setArticleContentLoading] = useState(false)
  const [readerModeEnabled, setReaderModeEnabled] = useState(false)

  /**
   * Fetch article content when reader mode is enabled
   */
  useEffect(() => {
    if (!previewArticle || !readerModeEnabled) {
      return
    }

    const fetchArticleContent = async () => {
      setArticleContentLoading(true)
      setArticleContent(null)

      try {
        const response = await authFetch(
          `/api/news/article-content?url=${encodeURIComponent(
            previewArticle.url
          )}`
        )
        if (!response.ok) {
          throw new Error('Failed to fetch article content')
        }
        const data: ArticleContentResponse = await response.json()
        setArticleContent(data)
      } catch {
        setArticleContent({
          url: previewArticle.url,
          title: null,
          content: null,
          author: null,
          date: null,
          success: false,
          error: 'Failed to connect to article extraction service',
        })
      } finally {
        setArticleContentLoading(false)
      }
    }

    fetchArticleContent()
  }, [previewArticle, readerModeEnabled])

  /**
   * Clear article content and reset reader mode
   */
  const clearContent = () => {
    setArticleContent(null)
    setReaderModeEnabled(false)
  }

  return {
    articleContent,
    articleContentLoading,
    readerModeEnabled,
    setReaderModeEnabled,
    clearContent,
  }
}
