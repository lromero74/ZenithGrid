/**
 * Crypto News Page
 *
 * Displays aggregated crypto news from multiple sources with 24-hour caching.
 * Sources include Reddit, CoinDesk, CoinTelegraph, Decrypt, The Block, and CryptoSlate.
 * Also includes video news from reputable crypto YouTube channels.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Newspaper, ExternalLink, RefreshCw, Clock, Filter, Video, Play, X, BookOpen, AlertCircle, TrendingUp, Pause, SkipForward, ListVideo, ChevronDown } from 'lucide-react'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { MarketSentimentCards } from '../components/MarketSentimentCards'
import {
  renderMarkdown,
  formatRelativeTime,
  sourceColors,
  videoSourceColors,
} from '../components/news'

interface NewsItem {
  title: string
  url: string
  source: string
  source_name: string
  published: string | null
  summary: string | null
  thumbnail: string | null
}

interface VideoItem {
  title: string
  url: string
  video_id: string
  source: string
  source_name: string
  channel_name: string
  published: string | null
  thumbnail: string | null
  description: string | null
}

interface NewsSource {
  id: string
  name: string
  website: string
}

interface VideoSource {
  id: string
  name: string
  website: string
  description: string
}

interface NewsResponse {
  news: NewsItem[]
  sources: NewsSource[]
  cached_at: string
  cache_expires_at: string
  total_items: number
}

interface VideoResponse {
  videos: VideoItem[]
  sources: VideoSource[]
  cached_at: string
  cache_expires_at: string
  total_items: number
}

interface ArticleContentResponse {
  url: string
  title: string | null
  content: string | null
  author: string | null
  date: string | null
  success: boolean
  error: string | null
}

type TabType = 'articles' | 'videos'

export default function News() {
  const [selectedSource, setSelectedSource] = useState<string>('all')
  const [selectedVideoSource, setSelectedVideoSource] = useState<string>('all')
  const [activeTab, setActiveTab] = useState<TabType>('articles')
  // Track which video is playing inline (null means none)
  const [playingVideoId, setPlayingVideoId] = useState<string | null>(null)
  // Track which article is being previewed (null means none)
  const [previewArticle, setPreviewArticle] = useState<NewsItem | null>(null)

  // Auto-play playlist state
  const [autoPlayActive, setAutoPlayActive] = useState(false)
  const [autoPlayIndex, setAutoPlayIndex] = useState<number>(0)
  const [showPlaylistDropdown, setShowPlaylistDropdown] = useState(false)
  const [showVideoModal, setShowVideoModal] = useState(false)
  const playerRef = useRef<HTMLIFrameElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const modalDropdownRef = useRef<HTMLDivElement>(null)
  const [showModalPlaylistDropdown, setShowModalPlaylistDropdown] = useState(false)
  // Track article reader mode content
  const [articleContent, setArticleContent] = useState<ArticleContentResponse | null>(null)
  const [articleContentLoading, setArticleContentLoading] = useState(false)
  const [readerModeEnabled, setReaderModeEnabled] = useState(false)

  // Storage key for persisting playlist position
  const PLAYLIST_STORAGE_KEY = 'crypto-news-video-playlist-position'

  // Load saved playlist position on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(PLAYLIST_STORAGE_KEY)
      if (saved) {
        const position = parseInt(saved, 10)
        if (!isNaN(position) && position >= 0) {
          setAutoPlayIndex(position)
        }
      }
    } catch {
      // Ignore localStorage errors
    }
  }, [])

  // Save playlist position when it changes
  useEffect(() => {
    try {
      localStorage.setItem(PLAYLIST_STORAGE_KEY, autoPlayIndex.toString())
    } catch {
      // Ignore localStorage errors
    }
  }, [autoPlayIndex])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowPlaylistDropdown(false)
      }
      if (modalDropdownRef.current && !modalDropdownRef.current.contains(e.target as Node)) {
        setShowModalPlaylistDropdown(false)
      }
    }
    if (showPlaylistDropdown || showModalPlaylistDropdown) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showPlaylistDropdown, showModalPlaylistDropdown])

  // Start auto-play from a specific index (opens modal)
  const startAutoPlay = useCallback((startIndex: number = 0, videos: VideoItem[], openModal: boolean = true) => {
    if (videos.length === 0) return
    const clampedIndex = Math.min(Math.max(0, startIndex), videos.length - 1)
    setAutoPlayIndex(clampedIndex)
    setAutoPlayActive(true)
    if (openModal) {
      setShowVideoModal(true)
    } else {
      const video = videos[clampedIndex]
      const uniqueKey = `${video.source}-${video.video_id}`
      setPlayingVideoId(uniqueKey)
    }
  }, [])

  // Stop auto-play and close modal
  const stopAutoPlay = useCallback(() => {
    setAutoPlayActive(false)
    setPlayingVideoId(null)
    setShowVideoModal(false)
    setShowModalPlaylistDropdown(false)
  }, [])

  // Advance to next video in playlist
  const advanceToNextVideo = useCallback((videos: VideoItem[]) => {
    if (!autoPlayActive || videos.length === 0) return

    const nextIndex = autoPlayIndex + 1
    if (nextIndex >= videos.length) {
      // End of playlist - close modal
      setAutoPlayActive(false)
      setPlayingVideoId(null)
      setShowVideoModal(false)
      return
    }

    setAutoPlayIndex(nextIndex)
    // Only update playingVideoId if not in modal mode (for inline playback)
    if (!showVideoModal) {
      const video = videos[nextIndex]
      const uniqueKey = `${video.source}-${video.video_id}`
      setPlayingVideoId(uniqueKey)
    }
  }, [autoPlayActive, autoPlayIndex, showVideoModal])

  // Skip to next video manually
  const skipToNextVideo = useCallback((videos: VideoItem[]) => {
    if (videos.length === 0) return
    advanceToNextVideo(videos)
  }, [advanceToNextVideo])

  // Ref to hold current filteredVideos for use in message handler
  // Will be updated by an effect defined after filteredVideos is computed
  const filteredVideosRef = useRef<VideoItem[]>([])

  // Fetch article content when reader mode is enabled
  useEffect(() => {
    if (!previewArticle || !readerModeEnabled) {
      return
    }

    const fetchArticleContent = async () => {
      setArticleContentLoading(true)
      setArticleContent(null)

      try {
        const response = await fetch(`/api/news/article-content?url=${encodeURIComponent(previewArticle.url)}`)
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
          error: 'Failed to connect to article extraction service'
        })
      } finally {
        setArticleContentLoading(false)
      }
    }

    fetchArticleContent()
  }, [previewArticle, readerModeEnabled])

  // Reset reader mode when closing modal
  const handleCloseModal = () => {
    setPreviewArticle(null)
    setReaderModeEnabled(false)
    setArticleContent(null)
  }

  // Close modals on ESC key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showVideoModal) {
          stopAutoPlay()
        } else if (previewArticle) {
          handleCloseModal()
        }
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [previewArticle, showVideoModal, stopAutoPlay])

  // Force re-render every minute to update relative timestamps
  const [, setTimeTick] = useState(0)
  useEffect(() => {
    const interval = setInterval(() => {
      setTimeTick((t) => t + 1)
    }, 60000) // Update every minute
    return () => clearInterval(interval)
  }, [])

  // Fetch news articles
  const {
    data: newsData,
    isLoading: newsLoading,
    error: newsError,
    refetch: refetchNews,
    isFetching: newsFetching,
  } = useQuery<NewsResponse>({
    queryKey: ['crypto-news'],
    queryFn: async () => {
      const response = await fetch('/api/news/')
      if (!response.ok) throw new Error('Failed to fetch news')
      return response.json()
    },
    staleTime: 1000 * 60 * 15, // Consider fresh for 15 minutes
    refetchInterval: 1000 * 60 * 15, // Auto-refresh every 15 minutes
    refetchOnWindowFocus: false,
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
    refetchInterval: 1000 * 60 * 15, // Auto-refresh every 15 minutes
    refetchOnWindowFocus: false,
  })

  const handleForceRefresh = async () => {
    if (activeTab === 'articles') {
      await fetch('/api/news/?force_refresh=true')
      refetchNews()
    } else {
      await fetch('/api/news/videos?force_refresh=true')
      refetchVideos()
    }
  }

  // Filter news by selected source
  const filteredNews =
    selectedSource === 'all'
      ? newsData?.news || []
      : newsData?.news.filter((item) => item.source === selectedSource) || []

  // Filter videos by selected source
  const filteredVideos =
    selectedVideoSource === 'all'
      ? videoData?.videos || []
      : videoData?.videos.filter((item) => item.source === selectedVideoSource) || []

  // Keep filteredVideosRef in sync for use in YouTube message handler
  useEffect(() => {
    filteredVideosRef.current = filteredVideos
  }, [filteredVideos])

  // Handle YouTube iframe API messages for video end detection
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // YouTube sends messages from its domain
      if (event.origin !== 'https://www.youtube.com') return
      if (!autoPlayActive) return

      try {
        const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data

        // YouTube Player API event: state 0 = ended
        // Also check for 'infoDelivery' with playerState 0
        if (data.event === 'onStateChange' && data.info === 0) {
          // Video ended - advance to next
          advanceToNextVideo(filteredVideosRef.current)
        } else if (data.event === 'infoDelivery' && data.info?.playerState === 0) {
          // Alternative format for video end
          advanceToNextVideo(filteredVideosRef.current)
        }
      } catch {
        // Not a JSON message, ignore
      }
    }

    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [autoPlayActive, advanceToNextVideo])

  // Get unique sources from actual news items
  const availableSources = newsData?.sources || []
  const availableVideoSources = videoData?.sources || []

  const isLoading = activeTab === 'articles' ? newsLoading : videosLoading
  const error = activeTab === 'articles' ? newsError : videosError
  const isFetching = activeTab === 'articles' ? newsFetching : videosFetching
  const cacheData = activeTab === 'articles' ? newsData : videoData

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <LoadingSpinner size="lg" text={activeTab === 'articles' ? 'Loading crypto news...' : 'Loading crypto videos...'} />
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-6 text-center">
        <p className="text-red-400">Failed to load {activeTab}. Please try again later.</p>
        <button
          onClick={() => activeTab === 'articles' ? refetchNews() : refetchVideos()}
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
              Aggregated from {availableSources.length + availableVideoSources.length} trusted sources
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          {/* Cache info */}
          {cacheData && (
            <div className="flex items-center space-x-2 text-xs text-slate-500">
              <Clock className="w-3 h-3" />
              <span>
                Cached {formatRelativeTime(cacheData.cached_at)}
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

      {/* Market Sentiment Section */}
      <div className="space-y-4">
        <div className="flex items-center space-x-3">
          <TrendingUp className="w-6 h-6 text-green-400" />
          <h2 className="text-xl font-bold text-white">Market Sentiment</h2>
        </div>
        <MarketSentimentCards />
      </div>

      {/* Crypto News Section */}
      <div className="space-y-4">
        <div className="flex items-center space-x-3">
          <Newspaper className="w-6 h-6 text-blue-400" />
          <h2 className="text-xl font-bold text-white">Crypto News</h2>
        </div>
      </div>

      {/* Tab switcher */}
      <div className="flex space-x-1 bg-slate-800 rounded-lg p-1 w-fit">
        <button
          onClick={() => setActiveTab('articles')}
          className={`flex items-center space-x-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            activeTab === 'articles'
              ? 'bg-blue-500/20 text-blue-400'
              : 'text-slate-400 hover:text-white hover:bg-slate-700'
          }`}
        >
          <Newspaper className="w-4 h-4" />
          <span>Articles</span>
          <span className="bg-slate-700 px-1.5 py-0.5 rounded text-xs">
            {newsData?.total_items || 0}
          </span>
        </button>
        <button
          onClick={() => setActiveTab('videos')}
          className={`flex items-center space-x-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            activeTab === 'videos'
              ? 'bg-red-500/20 text-red-400'
              : 'text-slate-400 hover:text-white hover:bg-slate-700'
          }`}
        >
          <Video className="w-4 h-4" />
          <span>Videos</span>
          <span className="bg-slate-700 px-1.5 py-0.5 rounded text-xs">
            {videoData?.total_items || 0}
          </span>
        </button>
      </div>

      {/* Articles Tab */}
      {activeTab === 'articles' && (
        <>
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
              <div
                key={`${item.source}-${index}`}
                className="group bg-slate-800 border border-slate-700 rounded-lg overflow-hidden hover:border-slate-600 transition-all hover:shadow-lg hover:shadow-slate-900/50"
              >
                {/* Thumbnail with preview/external link buttons */}
                <div className="aspect-video w-full overflow-hidden bg-slate-900 relative">
                  {item.thumbnail && (
                    <img
                      src={item.thumbnail}
                      alt=""
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = 'none'
                      }}
                    />
                  )}
                  {/* Click overlay to open preview in reader mode */}
                  <button
                    onClick={() => { setPreviewArticle(item); setReaderModeEnabled(true) }}
                    className="absolute inset-0 flex items-center justify-center bg-black/0 hover:bg-black/30 transition-colors cursor-pointer"
                  />
                  {/* Open in new tab button */}
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="absolute top-2 right-2 w-8 h-8 bg-black/70 hover:bg-black/90 rounded-full flex items-center justify-center transition-colors z-10"
                    title="Open on website"
                  >
                    <ExternalLink className="w-4 h-4 text-white" />
                  </a>
                </div>

                <button
                  onClick={() => { setPreviewArticle(item); setReaderModeEnabled(true) }}
                  className="p-4 space-y-3 text-left w-full cursor-pointer hover:bg-slate-700/30 transition-colors"
                >
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

                  {/* Click to preview indicator */}
                  <div className="flex items-center space-x-1 text-xs text-slate-500 group-hover:text-blue-400 transition-colors">
                    <Newspaper className="w-3 h-3" />
                    <span>Click to preview</span>
                  </div>
                </button>
              </div>
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
        </>
      )}

      {/* Videos Tab */}
      {activeTab === 'videos' && (
        <>
          {/* Video source filter */}
          <div className="flex flex-wrap items-center gap-2">
            <Filter className="w-4 h-4 text-slate-400" />
            <button
              onClick={() => setSelectedVideoSource('all')}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                selectedVideoSource === 'all'
                  ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                  : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700'
              }`}
            >
              All ({videoData?.total_items || 0})
            </button>
            {availableVideoSources.map((source) => {
              const count = videoData?.videos.filter((v) => v.source === source.id).length || 0
              return (
                <button
                  key={source.id}
                  onClick={() => setSelectedVideoSource(source.id)}
                  className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    selectedVideoSource === source.id
                      ? videoSourceColors[source.id] || 'bg-slate-600 text-white'
                      : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700'
                  }`}
                >
                  {source.name} ({count})
                </button>
              )
            })}
          </div>

          {/* Auto-play controls */}
          <div className="flex flex-wrap items-center gap-3 bg-slate-800/50 rounded-lg p-3 border border-slate-700">
            <ListVideo className="w-5 h-5 text-red-400" />

            {!autoPlayActive ? (
              <>
                {/* Play All button */}
                <button
                  onClick={() => startAutoPlay(0, filteredVideos)}
                  disabled={filteredVideos.length === 0}
                  className="flex items-center space-x-2 px-4 py-2 bg-red-600 hover:bg-red-500 disabled:bg-slate-600 disabled:cursor-not-allowed rounded-lg text-white font-medium transition-colors"
                >
                  <Play className="w-4 h-4" fill="white" />
                  <span>Play All</span>
                </button>

                {/* Continue from saved position */}
                {autoPlayIndex > 0 && autoPlayIndex < filteredVideos.length && (
                  <button
                    onClick={() => startAutoPlay(autoPlayIndex, filteredVideos)}
                    className="flex items-center space-x-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-white transition-colors"
                  >
                    <Play className="w-4 h-4" />
                    <span>Continue from #{autoPlayIndex + 1}</span>
                  </button>
                )}
              </>
            ) : (
              <>
                {/* Stop button */}
                <button
                  onClick={stopAutoPlay}
                  className="flex items-center space-x-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-white transition-colors"
                >
                  <Pause className="w-4 h-4" />
                  <span>Stop</span>
                </button>

                {/* Skip to next */}
                <button
                  onClick={() => skipToNextVideo(filteredVideos)}
                  disabled={autoPlayIndex >= filteredVideos.length - 1}
                  className="flex items-center space-x-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-600/50 disabled:cursor-not-allowed rounded-lg text-white transition-colors"
                >
                  <SkipForward className="w-4 h-4" />
                  <span>Skip</span>
                </button>

                {/* Progress indicator */}
                <div className="flex items-center space-x-2 text-sm text-slate-300">
                  <span className="text-red-400 font-medium">Playing:</span>
                  <span>{autoPlayIndex + 1} / {filteredVideos.length}</span>
                </div>
              </>
            )}

            {/* Position selector dropdown */}
            <div className="relative ml-auto" ref={dropdownRef}>
              <button
                onClick={() => setShowPlaylistDropdown(!showPlaylistDropdown)}
                className="flex items-center space-x-2 px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm text-slate-300 transition-colors"
              >
                <span>Start from video...</span>
                <ChevronDown className={`w-4 h-4 transition-transform ${showPlaylistDropdown ? 'rotate-180' : ''}`} />
              </button>

              {showPlaylistDropdown && (
                <div className="absolute right-0 mt-2 w-80 max-h-96 overflow-y-auto bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-20">
                  <div className="p-2 border-b border-slate-700">
                    <p className="text-xs text-slate-400">Select starting video</p>
                  </div>
                  {filteredVideos.map((video, idx) => (
                    <button
                      key={`${video.source}-${video.video_id}`}
                      onClick={() => {
                        setAutoPlayIndex(idx)
                        setShowPlaylistDropdown(false)
                        if (autoPlayActive) {
                          const uniqueKey = `${video.source}-${video.video_id}`
                          setPlayingVideoId(uniqueKey)
                        }
                      }}
                      className={`w-full flex items-start space-x-3 p-3 hover:bg-slate-700 transition-colors text-left ${
                        idx === autoPlayIndex ? 'bg-red-500/10 border-l-2 border-red-500' : ''
                      }`}
                    >
                      <span className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                        idx === autoPlayIndex ? 'bg-red-500 text-white' : 'bg-slate-600 text-slate-300'
                      }`}>
                        {idx + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-white truncate">{video.title}</p>
                        <p className="text-xs text-slate-500">{video.channel_name}</p>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Videos grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredVideos.map((video, index) => {
              // Use unique key combining source and video_id to avoid collisions
              const uniqueKey = `${video.source}-${video.video_id}`
              const isPlaying = playingVideoId === uniqueKey

              return (
                <div
                  key={uniqueKey}
                  className="group bg-slate-800 border border-slate-700 rounded-lg overflow-hidden hover:border-slate-600 transition-all hover:shadow-lg hover:shadow-slate-900/50"
                >
                  {/* Video area - either thumbnail or embedded player */}
                  <div className="aspect-video w-full overflow-hidden bg-slate-900 relative">
                    {isPlaying ? (
                      // Embedded YouTube player with API enabled for end detection
                      <>
                        <iframe
                          ref={index === autoPlayIndex && autoPlayActive ? playerRef : undefined}
                          src={`https://www.youtube.com/embed/${video.video_id}?autoplay=1&rel=0&enablejsapi=1&origin=${window.location.origin}`}
                          title={video.title}
                          className="w-full h-full"
                          id={`youtube-player-${video.video_id}`}
                          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                          allowFullScreen
                          onLoad={() => {
                            // When iframe loads, set up message listener for this specific player
                            if (autoPlayActive && index === autoPlayIndex) {
                              const iframe = document.getElementById(`youtube-player-${video.video_id}`) as HTMLIFrameElement
                              if (iframe?.contentWindow) {
                                // Listen to all YouTube events
                                iframe.contentWindow.postMessage('{"event":"listening","id":"1","channel":"widget"}', '*')
                              }
                            }
                          }}
                        />
                        {/* Auto-play indicator badge */}
                        {autoPlayActive && index === autoPlayIndex && (
                          <div className="absolute top-2 left-2 px-2 py-1 bg-red-600 rounded text-xs text-white font-medium flex items-center space-x-1 z-10">
                            <ListVideo className="w-3 h-3" />
                            <span>{autoPlayIndex + 1}/{filteredVideos.length}</span>
                          </div>
                        )}
                        {/* Close/Stop button */}
                        <button
                          onClick={() => {
                            if (autoPlayActive) {
                              stopAutoPlay()
                            } else {
                              setPlayingVideoId(null)
                            }
                          }}
                          className="absolute top-2 right-2 w-8 h-8 bg-black/70 hover:bg-black/90 rounded-full flex items-center justify-center transition-colors z-10"
                          title={autoPlayActive ? "Stop playlist" : "Close video"}
                        >
                          <X className="w-5 h-5 text-white" />
                        </button>
                        {/* Skip to next button (only in auto-play mode) */}
                        {autoPlayActive && autoPlayIndex < filteredVideos.length - 1 && (
                          <button
                            onClick={() => advanceToNextVideo(filteredVideos)}
                            className="absolute top-2 right-12 w-8 h-8 bg-black/70 hover:bg-black/90 rounded-full flex items-center justify-center transition-colors z-10"
                            title="Skip to next video"
                          >
                            <SkipForward className="w-4 h-4 text-white" />
                          </button>
                        )}
                      </>
                    ) : (
                      // Thumbnail with play button
                      <>
                        {video.thumbnail && (
                          <img
                            src={video.thumbnail}
                            alt=""
                            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                            onError={(e) => {
                              (e.target as HTMLImageElement).style.display = 'none'
                            }}
                          />
                        )}
                        {/* Play button overlay - click to play inline */}
                        <button
                          onClick={() => setPlayingVideoId(uniqueKey)}
                          className="absolute inset-0 flex items-center justify-center bg-black/30 group-hover:bg-black/40 transition-colors cursor-pointer"
                        >
                          <div className="w-14 h-14 bg-red-600 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform">
                            <Play className="w-7 h-7 text-white ml-1" fill="white" />
                          </div>
                        </button>
                        {/* Open in new tab button */}
                        <a
                          href={video.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="absolute top-2 right-2 w-8 h-8 bg-black/70 hover:bg-black/90 rounded-full flex items-center justify-center transition-colors z-10"
                          title="Open on YouTube"
                        >
                          <ExternalLink className="w-4 h-4 text-white" />
                        </a>
                      </>
                    )}
                  </div>

                  <div className="p-4 space-y-3">
                    {/* Channel badge and time */}
                    <div className="flex items-center justify-between">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium border ${
                          videoSourceColors[video.source] || 'bg-slate-600 text-slate-300'
                        }`}
                      >
                        {video.channel_name}
                      </span>
                      {video.published && (
                        <span className="text-xs text-slate-500">
                          {formatRelativeTime(video.published)}
                        </span>
                      )}
                    </div>

                    {/* Title */}
                    <h3 className="font-medium text-white line-clamp-2">
                      {video.title}
                    </h3>

                    {/* Description */}
                    {video.description && (
                      <p className="text-sm text-slate-400 line-clamp-2">{video.description}</p>
                    )}

                    {/* Action link */}
                    <a
                      href={video.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center space-x-1 text-xs text-slate-500 hover:text-red-400 transition-colors"
                    >
                      <ExternalLink className="w-3 h-3" />
                      <span>Open on YouTube</span>
                    </a>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Empty state for videos */}
          {filteredVideos.length === 0 && (
            <div className="text-center py-12">
              <Video className="w-12 h-12 text-slate-600 mx-auto mb-4" />
              <p className="text-slate-400">No videos found</p>
              {selectedVideoSource !== 'all' && (
                <button
                  onClick={() => setSelectedVideoSource('all')}
                  className="mt-2 text-red-400 hover:text-red-300"
                >
                  Show all channels
                </button>
              )}
            </div>
          )}
        </>
      )}

      {/* Sources footer */}
      <div className="border-t border-slate-700 pt-6">
        <h3 className="text-sm font-medium text-slate-400 mb-3">
          {activeTab === 'articles' ? 'News Sources' : 'Video Channels'}
        </h3>
        <div className="flex flex-wrap gap-3">
          {activeTab === 'articles' ? (
            availableSources.map((source) => (
              <a
                key={source.id}
                href={source.website}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-slate-500 hover:text-blue-400 transition-colors"
              >
                {source.name} ↗
              </a>
            ))
          ) : (
            availableVideoSources.map((source) => (
              <a
                key={source.id}
                href={source.website}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-slate-500 hover:text-red-400 transition-colors"
                title={source.description}
              >
                {source.name} ↗
              </a>
            ))
          )}
        </div>
        <p className="mt-3 text-xs text-slate-600">
          Auto-refreshes every 15 minutes. Click refresh to fetch immediately.
        </p>
      </div>

      {/* Article Preview Modal */}
      {previewArticle && (
        <div
          className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4"
          onClick={handleCloseModal}
        >
          <div
            className={`bg-slate-800 rounded-lg w-full max-h-[90vh] overflow-hidden shadow-2xl transition-all duration-300 ${
              readerModeEnabled ? 'max-w-4xl' : 'max-w-2xl'
            }`}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal header with reader mode toggle */}
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <div className="flex items-center space-x-2">
                <span
                  className={`px-2 py-0.5 rounded text-xs font-medium border ${
                    sourceColors[previewArticle.source] || 'bg-slate-600 text-slate-300'
                  }`}
                >
                  {previewArticle.source_name}
                </span>
                {previewArticle.published && (
                  <span className="text-xs text-slate-500">
                    {formatRelativeTime(previewArticle.published)}
                  </span>
                )}
              </div>
              <div className="flex items-center space-x-2">
                {/* Reader Mode Toggle */}
                <button
                  onClick={() => setReaderModeEnabled(!readerModeEnabled)}
                  className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    readerModeEnabled
                      ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                      : 'bg-slate-700 text-slate-400 hover:text-white hover:bg-slate-600'
                  }`}
                  title="Toggle reader mode to fetch and display full article content"
                >
                  <BookOpen className="w-4 h-4" />
                  <span className="hidden sm:inline">Reader Mode</span>
                </button>
                <button
                  onClick={handleCloseModal}
                  className="w-8 h-8 bg-slate-700 hover:bg-slate-600 rounded-full flex items-center justify-center transition-colors"
                >
                  <X className="w-5 h-5 text-slate-400" />
                </button>
              </div>
            </div>

            {/* Modal content */}
            <div className="overflow-y-auto max-h-[calc(90vh-140px)]">
              {/* Full-size thumbnail - always show if available */}
              {previewArticle.thumbnail && (
                <div className="w-full aspect-video bg-slate-900">
                  <img
                    src={previewArticle.thumbnail}
                    alt=""
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = 'none'
                    }}
                  />
                </div>
              )}

              <div className="p-6 space-y-4">
                {/* Title - use extracted title in reader mode if available */}
                <h2 className="text-xl font-bold text-white leading-tight">
                  {readerModeEnabled && articleContent?.title ? articleContent.title : previewArticle.title}
                </h2>

                {/* Author and date in reader mode */}
                {readerModeEnabled && articleContent?.success && (articleContent.author || articleContent.date) && (
                  <div className="flex items-center space-x-3 text-sm text-slate-400">
                    {articleContent.author && <span>By {articleContent.author}</span>}
                    {articleContent.author && articleContent.date && <span>•</span>}
                    {articleContent.date && <span>{articleContent.date}</span>}
                  </div>
                )}

                {/* Reader Mode Content */}
                {readerModeEnabled ? (
                  <>
                    {/* Loading state */}
                    {articleContentLoading && (
                      <div className="flex flex-col items-center justify-center py-12 space-y-4">
                        <LoadingSpinner size="md" text="Fetching article content..." />
                        <p className="text-sm text-slate-500">
                          Extracting readable content from the source
                        </p>
                      </div>
                    )}

                    {/* Error state */}
                    {articleContent && !articleContent.success && (
                      <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
                        <div className="flex items-start space-x-3">
                          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                          <div>
                            <p className="text-red-400 font-medium">Unable to extract article content</p>
                            <p className="text-sm text-red-400/70 mt-1">{articleContent.error}</p>
                            <p className="text-sm text-slate-400 mt-3">
                              Try opening the full article on the source website instead.
                            </p>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Success - Full article content */}
                    {articleContent?.success && articleContent.content && (
                      <div className="prose prose-invert prose-slate max-w-none">
                        {/* Render markdown content with headings, lists, and formatting */}
                        {/* Pass title to skip duplicate h1 that matches the article title */}
                        {renderMarkdown(articleContent.content, articleContent.title)}
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    {/* Default preview mode - summary only */}
                    {previewArticle.summary && (
                      <p className="text-slate-300 leading-relaxed">
                        {previewArticle.summary}
                      </p>
                    )}

                    {/* No summary message */}
                    {!previewArticle.summary && (
                      <p className="text-slate-500 italic">
                        No summary available. Enable Reader Mode or click below to read the full article.
                      </p>
                    )}

                    {/* Hint to enable reader mode */}
                    <div className="bg-slate-700/50 rounded-lg p-4 mt-4">
                      <div className="flex items-start space-x-3">
                        <BookOpen className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
                        <div>
                          <p className="text-slate-300 font-medium">Want to read the full article here?</p>
                          <p className="text-sm text-slate-400 mt-1">
                            Enable <span className="text-blue-400">Reader Mode</span> above to extract and display the full article content in a clean, readable format.
                          </p>
                        </div>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Modal footer with action button */}
            <div className="p-4 border-t border-slate-700 flex justify-between items-center">
              <button
                onClick={handleCloseModal}
                className="px-4 py-2 text-slate-400 hover:text-white transition-colors"
              >
                Close
              </button>
              <a
                href={previewArticle.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center space-x-2 px-6 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-white font-medium transition-colors"
              >
                <ExternalLink className="w-4 h-4" />
                <span>Read on Website</span>
              </a>
            </div>
          </div>
        </div>
      )}

      {/* Video Player Modal for Play All */}
      {showVideoModal && autoPlayActive && filteredVideos.length > 0 && (
        <div
          className="fixed inset-0 bg-black/90 flex items-center justify-center z-50 p-4"
          onClick={stopAutoPlay}
        >
          <div
            className="bg-slate-800 rounded-lg w-full max-w-5xl max-h-[95vh] overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal header */}
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <div className="flex items-center space-x-3">
                <div className="flex items-center space-x-2 px-3 py-1.5 bg-red-600 rounded-lg">
                  <ListVideo className="w-4 h-4 text-white" />
                  <span className="text-white font-medium text-sm">
                    {autoPlayIndex + 1} / {filteredVideos.length}
                  </span>
                </div>
                <span
                  className={`px-2 py-0.5 rounded text-xs font-medium border ${
                    videoSourceColors[filteredVideos[autoPlayIndex]?.source] || 'bg-slate-600 text-slate-300'
                  }`}
                >
                  {filteredVideos[autoPlayIndex]?.channel_name}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                {/* Skip to next */}
                <button
                  onClick={() => skipToNextVideo(filteredVideos)}
                  disabled={autoPlayIndex >= filteredVideos.length - 1}
                  className="flex items-center space-x-2 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-700/50 disabled:cursor-not-allowed rounded-lg text-white text-sm transition-colors"
                >
                  <SkipForward className="w-4 h-4" />
                  <span className="hidden sm:inline">Skip</span>
                </button>
                {/* Close button */}
                <button
                  onClick={stopAutoPlay}
                  className="w-8 h-8 bg-slate-700 hover:bg-slate-600 rounded-full flex items-center justify-center transition-colors"
                >
                  <X className="w-5 h-5 text-slate-400" />
                </button>
              </div>
            </div>

            {/* Video player area */}
            <div className="aspect-video w-full bg-black">
              <iframe
                key={`modal-player-${filteredVideos[autoPlayIndex]?.video_id}`}
                src={`https://www.youtube.com/embed/${filteredVideos[autoPlayIndex]?.video_id}?autoplay=1&rel=0&enablejsapi=1&origin=${window.location.origin}`}
                title={filteredVideos[autoPlayIndex]?.title}
                className="w-full h-full"
                id={`modal-youtube-player-${filteredVideos[autoPlayIndex]?.video_id}`}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                onLoad={() => {
                  const iframe = document.getElementById(`modal-youtube-player-${filteredVideos[autoPlayIndex]?.video_id}`) as HTMLIFrameElement
                  if (iframe?.contentWindow) {
                    iframe.contentWindow.postMessage('{"event":"listening","id":"1","channel":"widget"}', '*')
                  }
                }}
              />
            </div>

            {/* Video info and controls */}
            <div className="p-4 space-y-3 border-t border-slate-700">
              {/* Title */}
              <h3 className="font-medium text-white text-lg line-clamp-2">
                {filteredVideos[autoPlayIndex]?.title}
              </h3>

              {/* Time and external link */}
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3 text-sm text-slate-400">
                  {filteredVideos[autoPlayIndex]?.published && (
                    <span>{formatRelativeTime(filteredVideos[autoPlayIndex].published!)}</span>
                  )}
                </div>
                <a
                  href={filteredVideos[autoPlayIndex]?.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center space-x-1 text-sm text-slate-400 hover:text-red-400 transition-colors"
                >
                  <ExternalLink className="w-4 h-4" />
                  <span>Open on YouTube</span>
                </a>
              </div>

              {/* Playlist selector */}
              <div className="relative" ref={modalDropdownRef}>
                <button
                  onClick={() => setShowModalPlaylistDropdown(!showModalPlaylistDropdown)}
                  className="flex items-center space-x-2 px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm text-slate-300 transition-colors w-full justify-between"
                >
                  <span>Jump to video...</span>
                  <ChevronDown className={`w-4 h-4 transition-transform ${showModalPlaylistDropdown ? 'rotate-180' : ''}`} />
                </button>

                {showModalPlaylistDropdown && (
                  <div className="absolute bottom-full left-0 right-0 mb-2 max-h-64 overflow-y-auto bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-20">
                    {filteredVideos.map((video, idx) => (
                      <button
                        key={`modal-${video.source}-${video.video_id}`}
                        onClick={() => {
                          setAutoPlayIndex(idx)
                          setShowModalPlaylistDropdown(false)
                        }}
                        className={`w-full flex items-start space-x-3 p-3 hover:bg-slate-700 transition-colors text-left ${
                          idx === autoPlayIndex ? 'bg-red-500/10 border-l-2 border-red-500' : ''
                        }`}
                      >
                        <span className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                          idx === autoPlayIndex ? 'bg-red-500 text-white' : 'bg-slate-600 text-slate-300'
                        }`}>
                          {idx + 1}
                        </span>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-white truncate">{video.title}</p>
                          <p className="text-xs text-slate-500">{video.channel_name}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
