/**
 * Crypto News Page
 *
 * Displays aggregated crypto news from multiple sources with 24-hour caching.
 * Sources include Reddit, CoinDesk, CoinTelegraph, Decrypt, The Block, and CryptoSlate.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Newspaper, ExternalLink, RefreshCw, Clock, Filter } from 'lucide-react'
import { LoadingSpinner } from '../components/LoadingSpinner'

interface NewsItem {
  title: string
  url: string
  source: string
  source_name: string
  published: string | null
  summary: string | null
  thumbnail: string | null
}

interface NewsSource {
  id: string
  name: string
  website: string
}

interface NewsResponse {
  news: NewsItem[]
  sources: NewsSource[]
  cached_at: string
  cache_expires_at: string
  total_items: number
}

// Format relative time (e.g., "2 hours ago")
function formatRelativeTime(isoString: string | null): string {
  if (!isoString) return ''

  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`

  return date.toLocaleDateString()
}

// Source colors for visual distinction
const sourceColors: Record<string, string> = {
  reddit_crypto: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  reddit_bitcoin: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  coindesk: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  cointelegraph: 'bg-green-500/20 text-green-400 border-green-500/30',
  decrypt: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  theblock: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
  cryptoslate: 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30',
}

export default function News() {
  const [selectedSource, setSelectedSource] = useState<string>('all')

  const {
    data: newsData,
    isLoading,
    error,
    refetch,
    isFetching,
  } = useQuery<NewsResponse>({
    queryKey: ['crypto-news'],
    queryFn: async () => {
      const response = await fetch('/api/news/')
      if (!response.ok) throw new Error('Failed to fetch news')
      return response.json()
    },
    staleTime: 1000 * 60 * 60, // Consider fresh for 1 hour
    refetchOnWindowFocus: false,
  })

  const handleForceRefresh = async () => {
    const response = await fetch('/api/news/?force_refresh=true')
    if (!response.ok) throw new Error('Failed to refresh news')
    refetch()
  }

  // Filter news by selected source
  const filteredNews =
    selectedSource === 'all'
      ? newsData?.news || []
      : newsData?.news.filter((item) => item.source === selectedSource) || []

  // Get unique sources from actual news items
  const availableSources = newsData?.sources || []

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <LoadingSpinner size="lg" text="Loading crypto news..." />
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-6 text-center">
        <p className="text-red-400">Failed to load news. Please try again later.</p>
        <button
          onClick={() => refetch()}
          className="mt-4 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 rounded-lg text-red-400 transition-colors"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="flex items-center space-x-3">
          <Newspaper className="w-8 h-8 text-blue-400" />
          <div>
            <h1 className="text-2xl font-bold">Crypto News</h1>
            <p className="text-sm text-slate-400">
              Aggregated from {availableSources.length} trusted sources
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          {/* Cache info */}
          {newsData && (
            <div className="flex items-center space-x-2 text-xs text-slate-500">
              <Clock className="w-3 h-3" />
              <span>
                Cached {formatRelativeTime(newsData.cached_at)}
              </span>
            </div>
          )}

          {/* Refresh button */}
          <button
            onClick={handleForceRefresh}
            disabled={isFetching}
            className="flex items-center space-x-2 px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
            <span className="text-sm">Refresh</span>
          </button>
        </div>
      </div>

      {/* Source filter */}
      <div className="flex flex-wrap items-center gap-2">
        <Filter className="w-4 h-4 text-slate-400" />
        <button
          onClick={() => setSelectedSource('all')}
          className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
            selectedSource === 'all'
              ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
              : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700'
          }`}
        >
          All ({newsData?.total_items || 0})
        </button>
        {availableSources.map((source) => {
          const count = newsData?.news.filter((n) => n.source === source.id).length || 0
          return (
            <button
              key={source.id}
              onClick={() => setSelectedSource(source.id)}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                selectedSource === source.id
                  ? sourceColors[source.id] || 'bg-slate-600 text-white'
                  : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700'
              }`}
            >
              {source.name.replace('Reddit ', 'r/')} ({count})
            </button>
          )
        })}
      </div>

      {/* News grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredNews.map((item, index) => (
          <a
            key={`${item.source}-${index}`}
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="group bg-slate-800 border border-slate-700 rounded-lg overflow-hidden hover:border-slate-600 transition-all hover:shadow-lg hover:shadow-slate-900/50"
          >
            {/* Thumbnail */}
            {item.thumbnail && (
              <div className="aspect-video w-full overflow-hidden bg-slate-900">
                <img
                  src={item.thumbnail}
                  alt=""
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  onError={(e) => {
                    // Hide broken images
                    (e.target as HTMLImageElement).style.display = 'none'
                  }}
                />
              </div>
            )}

            <div className="p-4 space-y-3">
              {/* Source badge and time */}
              <div className="flex items-center justify-between">
                <span
                  className={`px-2 py-0.5 rounded text-xs font-medium border ${
                    sourceColors[item.source] || 'bg-slate-600 text-slate-300'
                  }`}
                >
                  {item.source_name}
                </span>
                {item.published && (
                  <span className="text-xs text-slate-500">
                    {formatRelativeTime(item.published)}
                  </span>
                )}
              </div>

              {/* Title */}
              <h3 className="font-medium text-white group-hover:text-blue-400 transition-colors line-clamp-3">
                {item.title}
              </h3>

              {/* Summary */}
              {item.summary && (
                <p className="text-sm text-slate-400 line-clamp-2">{item.summary}</p>
              )}

              {/* External link indicator */}
              <div className="flex items-center space-x-1 text-xs text-slate-500 group-hover:text-blue-400 transition-colors">
                <ExternalLink className="w-3 h-3" />
                <span>Read more</span>
              </div>
            </div>
          </a>
        ))}
      </div>

      {/* Empty state */}
      {filteredNews.length === 0 && (
        <div className="text-center py-12">
          <Newspaper className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <p className="text-slate-400">No news articles found</p>
          {selectedSource !== 'all' && (
            <button
              onClick={() => setSelectedSource('all')}
              className="mt-2 text-blue-400 hover:text-blue-300"
            >
              Show all sources
            </button>
          )}
        </div>
      )}

      {/* Sources footer */}
      <div className="border-t border-slate-700 pt-6">
        <h3 className="text-sm font-medium text-slate-400 mb-3">News Sources</h3>
        <div className="flex flex-wrap gap-3">
          {availableSources.map((source) => (
            <a
              key={source.id}
              href={source.website}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-slate-500 hover:text-blue-400 transition-colors"
            >
              {source.name} ↗
            </a>
          ))}
        </div>
        <p className="mt-3 text-xs text-slate-600">
          News is cached for 24 hours. Click refresh to fetch the latest articles.
        </p>
      </div>
    </div>
  )
}
