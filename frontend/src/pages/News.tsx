/**
 * Crypto News Page
 *
 * Displays aggregated crypto news from multiple sources with 24-hour caching.
 * Sources include Reddit, CoinDesk, CoinTelegraph, Decrypt, The Block, and CryptoSlate.
 * Also includes video news from reputable crypto YouTube channels.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { Newspaper, ExternalLink, RefreshCw, Clock, Filter, Video, Play, X, BookOpen, AlertCircle, TrendingUp, ListVideo, ChevronDown, Settings, Crosshair } from 'lucide-react'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { MarketSentimentCards } from '../components/MarketSentimentCards'
import { useVideoPlayer, VideoItem as ContextVideoItem } from '../contexts/VideoPlayerContext'
import { SourceSubscriptionsModal } from '../components/news/SourceSubscriptionsModal'
import {
  renderMarkdown,
  formatRelativeTime,
  sourceColors,
  videoSourceColors,
} from '../components/news'
import { NewsItem, TabType } from './news/types'
import { useNewsData, useArticleContent, useNewsFilters } from './news/hooks'
import { cleanupHoverHighlights, scrollToVideo, highlightVideo, unhighlightVideo, countItemsBySource } from './news/helpers'

export default function News() {
  const [activeTab, setActiveTab] = useState<TabType>('articles')
  const [showSourceSettings, setShowSourceSettings] = useState(false)
  const PAGE_SIZE = 50

  // Track which article is being previewed (null means none)
  const [previewArticle, setPreviewArticle] = useState<NewsItem | null>(null)

  // Global video player context for "Play All" feature
  const { startPlaylist, isPlaying: isPlaylistPlaying, currentIndex: playlistIndex, playlist, currentVideo } = useVideoPlayer()

  // Playlist dropdown state (for starting from specific video)
  const [showPlaylistDropdown, setShowPlaylistDropdown] = useState(false)
  const [hoveredPlaylistIndex, setHoveredPlaylistIndex] = useState<number | null>(null)
  const [dropdownPosition, setDropdownPosition] = useState<{ top: number; right: number } | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const dropdownButtonRef = useRef<HTMLButtonElement>(null)

  // Fetch news and video data
  const {
    newsData,
    videoData,
    newsLoading,
    videosLoading,
    newsError,
    videosError,
    newsFetching,
    videosFetching,
    refetchNews,
    refetchVideos,
    handleForceRefresh,
  } = useNewsData()

  // Article content for reader mode
  const {
    articleContent,
    articleContentLoading,
    readerModeEnabled,
    setReaderModeEnabled,
    clearContent,
  } = useArticleContent({ previewArticle })

  // Filtering and pagination
  const {
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
  } = useNewsFilters({ newsData, videoData, pageSize: PAGE_SIZE })

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowPlaylistDropdown(false)
        cleanupHoverHighlights()
      }
    }
    if (showPlaylistDropdown) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showPlaylistDropdown])

  // Reset reader mode when closing modal
  const handleCloseModal = useCallback(() => {
    setPreviewArticle(null)
    clearContent()
  }, [clearContent])

  // Close article modal on ESC key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && previewArticle) {
        handleCloseModal()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [previewArticle, handleCloseModal])

  // Force re-render every minute to update relative timestamps
  const [, setTimeTick] = useState(0)
  useEffect(() => {
    const interval = setInterval(() => {
      setTimeTick((t) => t + 1)
    }, 60000) // Update every minute
    return () => clearInterval(interval)
  }, [])

  // Scroll to currently playing video (centered in viewport) with pulse effect
  const scrollToPlayingVideo = () => {
    if (!currentVideo) return
    scrollToVideo(currentVideo.video_id, true)
  }

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

          {/* Settings button */}
          <button
            onClick={() => setShowSourceSettings(true)}
            className="flex items-center space-x-2 px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
            title="Manage news sources"
          >
            <Settings className="w-4 h-4" />
            <span className="text-sm hidden sm:inline">Sources</span>
          </button>

          {/* Refresh button */}
          <button
            onClick={() => handleForceRefresh(activeTab)}
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
              onClick={() => { setSelectedSource('all'); setCurrentPage(1) }}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                selectedSource === 'all'
                  ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                  : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700'
              }`}
            >
              All ({newsData?.total_items || 0})
            </button>
            {availableSources.map((source) => {
              const count = countItemsBySource(newsData?.news || [], source.id)
              return (
                <button
                  key={source.id}
                  onClick={() => { setSelectedSource(source.id); setCurrentPage(1) }}
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
            {paginatedNews.map((item, index) => (
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

          {/* Pagination controls (client-side - instant page changes) */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center space-x-4 py-6">
              <button
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 disabled:cursor-not-allowed rounded-lg transition-colors"
              >
                Previous
              </button>
              <div className="flex items-center space-x-2">
                {/* Show page numbers with ellipsis for large page counts */}
                {Array.from({ length: totalPages }, (_, i) => i + 1)
                  .filter(pageNum => {
                    // Always show first, last, current, and neighbors
                    if (pageNum === 1 || pageNum === totalPages) return true
                    if (Math.abs(pageNum - currentPage) <= 1) return true
                    return false
                  })
                  .map((pageNum, idx, arr) => (
                    <span key={pageNum} className="flex items-center">
                      {/* Add ellipsis if there's a gap */}
                      {idx > 0 && arr[idx - 1] !== pageNum - 1 && (
                        <span className="px-2 text-slate-500">...</span>
                      )}
                      <button
                        onClick={() => setCurrentPage(pageNum)}
                        className={`w-10 h-10 rounded-lg transition-colors ${
                          currentPage === pageNum
                            ? 'bg-blue-600 text-white'
                            : 'bg-slate-700 hover:bg-slate-600 text-slate-300'
                        }`}
                      >
                        {pageNum}
                      </button>
                    </span>
                  ))}
              </div>
              <button
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 disabled:cursor-not-allowed rounded-lg transition-colors"
              >
                Next
              </button>
            </div>
          )}

          {/* Page info */}
          {totalFilteredItems > 0 && (
            <div className="text-center text-sm text-slate-500">
              Showing {((currentPage - 1) * PAGE_SIZE) + 1}-{Math.min(currentPage * PAGE_SIZE, totalFilteredItems)} of {totalFilteredItems} articles
            </div>
          )}

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
              const count = countItemsBySource(videoData?.videos || [], source.id)
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

            {/* Play All button - opens mini-player */}
            <button
              onClick={() => startPlaylist(filteredVideos as ContextVideoItem[], 0)}
              disabled={filteredVideos.length === 0}
              className="flex items-center space-x-2 px-4 py-2 bg-red-600 hover:bg-red-500 disabled:bg-slate-600 disabled:cursor-not-allowed rounded-lg text-white font-medium transition-colors"
            >
              <Play className="w-4 h-4" fill="white" />
              <span>Play All</span>
            </button>

            {/* Now playing indicator and scroll button */}
            {isPlaylistPlaying && (
              <div className="flex items-center space-x-3">
                <div className="flex items-center space-x-2 text-sm text-slate-300">
                  <span className="text-green-400 font-medium">Now playing:</span>
                  <span>{playlistIndex + 1} / {playlist.length}</span>
                </div>
                <button
                  onClick={scrollToPlayingVideo}
                  className="flex items-center space-x-1.5 px-3 py-1.5 bg-red-600/20 hover:bg-red-600/30 border border-red-500/30 rounded-lg text-red-400 text-sm transition-colors"
                  title="Scroll to currently playing video"
                >
                  <Crosshair className="w-4 h-4" />
                  <span className="hidden sm:inline">Find Playing</span>
                </button>
              </div>
            )}

            {/* Position selector dropdown - start from specific video */}
            <div className="relative ml-auto" ref={dropdownRef}>
              <button
                ref={dropdownButtonRef}
                onClick={() => {
                  if (showPlaylistDropdown) {
                    cleanupHoverHighlights()
                    setShowPlaylistDropdown(false)
                  } else {
                    // Calculate position based on button location
                    if (dropdownButtonRef.current) {
                      const rect = dropdownButtonRef.current.getBoundingClientRect()
                      setDropdownPosition({
                        top: rect.bottom + 8, // 8px gap below button
                        right: window.innerWidth - rect.right, // Align right edges
                      })
                    }
                    setShowPlaylistDropdown(true)
                  }
                }}
                className="flex items-center space-x-2 px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm text-slate-300 transition-colors"
              >
                <span>Start from video...</span>
                <ChevronDown className={`w-4 h-4 transition-transform ${showPlaylistDropdown ? 'rotate-180' : ''}`} />
              </button>

              {showPlaylistDropdown && dropdownPosition && (
                <div
                  className="fixed w-80 max-h-[60vh] overflow-y-auto bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-50"
                  style={{ top: dropdownPosition.top, right: dropdownPosition.right }}
                >
                  <div className="p-2 border-b border-slate-700 sticky top-0 bg-slate-800 z-10">
                    <p className="text-xs text-slate-400">Hover to preview - Click to play</p>
                  </div>
                  {filteredVideos.map((video, idx) => (
                    <button
                      key={`${video.source}-${video.video_id}`}
                      onClick={() => {
                        startPlaylist(filteredVideos as ContextVideoItem[], idx, true) // Start expanded
                        setShowPlaylistDropdown(false)
                        cleanupHoverHighlights()
                      }}
                      onMouseEnter={() => {
                        setHoveredPlaylistIndex(idx)
                        // Scroll to and highlight the video in the grid
                        highlightVideo(video.video_id)
                        scrollToVideo(video.video_id, false)
                      }}
                      onMouseLeave={() => {
                        setHoveredPlaylistIndex(null)
                        // Remove blue halo effect
                        unhighlightVideo(video.video_id)
                      }}
                      className={`w-full flex items-start space-x-3 p-3 hover:bg-slate-700 transition-colors text-left ${
                        hoveredPlaylistIndex === idx ? 'bg-blue-500/10' : ''
                      }`}
                    >
                      <span className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                        hoveredPlaylistIndex === idx ? 'bg-blue-500 text-white' : 'bg-slate-600 text-slate-300'
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
            {filteredVideos.map((video, idx) => {
              // Use unique key combining source and video_id to avoid collisions
              const uniqueKey = `${video.source}-${video.video_id}`

              // Check if this video is currently playing in the mini player
              const isCurrentlyPlaying = isPlaylistPlaying && currentVideo?.video_id === video.video_id

              // Handler to play this specific video in expanded modal
              const handlePlayVideo = () => {
                startPlaylist(filteredVideos as ContextVideoItem[], idx, true) // true = start expanded
              }

              return (
                <div
                  key={uniqueKey}
                  data-video-id={video.video_id}
                  className={`group bg-slate-800 rounded-lg overflow-hidden transition-all hover:shadow-lg ${
                    isCurrentlyPlaying
                      ? 'border-2 border-red-500 ring-4 ring-red-500/30 shadow-lg shadow-red-500/20'
                      : 'border border-slate-700 hover:border-slate-600 hover:shadow-slate-900/50'
                  }`}
                >
                  {/* Video thumbnail with play button */}
                  <div className="aspect-video w-full overflow-hidden bg-slate-900 relative">
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
                    {/* Now Playing badge */}
                    {isCurrentlyPlaying && (
                      <div className="absolute top-2 left-2 flex items-center space-x-1.5 px-2 py-1 bg-red-600 rounded-full z-10 animate-pulse">
                        <div className="w-2 h-2 bg-white rounded-full" />
                        <span className="text-xs font-medium text-white">Playing</span>
                      </div>
                    )}
                    {/* Play button overlay - click to open in expanded modal */}
                    <button
                      onClick={handlePlayVideo}
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

      {/* Source Subscriptions Modal */}
      <SourceSubscriptionsModal
        isOpen={showSourceSettings}
        onClose={() => setShowSourceSettings(false)}
      />

    </div>
  )
}
