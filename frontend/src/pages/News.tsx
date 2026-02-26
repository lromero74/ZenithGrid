/**
 * Crypto News Page
 *
 * Displays aggregated crypto news from multiple sources with 24-hour caching.
 * Sources include Reddit, CoinDesk, CoinTelegraph, Decrypt, The Block, and CryptoSlate.
 * Also includes video news from reputable crypto YouTube channels.
 *
 * UI sections are extracted into subcomponents under pages/news/components/:
 *   - NewsFilterBar: seen/unseen filter pills and bulk actions
 *   - ArticleSection: articles tab (filters, grid, pagination)
 *   - VideoSection: videos tab (filters, grid, pagination)
 *   - ArticlePreviewModal: article reader modal with TTS
 */

import { useState, useEffect, useCallback } from 'react'
import { Newspaper, RefreshCw, Clock, Video, TrendingUp, Settings } from 'lucide-react'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { MarketSentimentCards } from '../components/MarketSentimentCards'
import { useVideoPlayer } from '../contexts/VideoPlayerContext'
import { useArticleReader } from '../contexts/ArticleReaderContext'
import { SourceSubscriptionsModal } from '../components/news/SourceSubscriptionsModal'
import { formatRelativeTime } from '../components/news'
import { NewsItem, TabType, NEWS_CATEGORIES } from '../types/newsTypes'
import { useNewsData, useArticleContent, useNewsFilters, useSeenStatus, useTTSSync } from './news/hooks'
import { cleanupArticleHoverHighlights, scrollToArticle, highlightArticle, unhighlightArticle, scrollToVideo } from './news/helpers'
import { NewsFilterBar, ArticleSection, VideoSection, ArticlePreviewModal } from './news/components'
import { markdownToPlainText } from './news/helpers'

export default function News() {
  const [activeTab, setActiveTab] = useState<TabType>(() => {
    try {
      const saved = localStorage.getItem('zenith-news-active-tab')
      if (saved === 'articles' || saved === 'videos') return saved
    } catch { /* ignore */ }
    return 'articles'
  })
  const [showSourceSettings, setShowSourceSettings] = useState(false)
  const PAGE_SIZE = 50

  // Persist active tab
  useEffect(() => {
    try { localStorage.setItem('zenith-news-active-tab', activeTab) } catch { /* ignore */ }
  }, [activeTab])

  // Track which article is being previewed (null means none)
  const [previewArticle, setPreviewArticle] = useState<NewsItem | null>(null)

  // Global video player context for engagement tracking
  const { isPlaying: isPlaylistPlaying } = useVideoPlayer()

  // Global article reader context for engagement tracking
  const { isPlaying: isArticleReaderPlaying } = useArticleReader()

  // TTS for reading articles aloud
  const tts = useTTSSync()

  // Suppress auto-refetch when user is actively engaged (reading, listening)
  const isUserEngaged = !!previewArticle || tts.isPlaying || isArticleReaderPlaying || isPlaylistPlaying

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
  } = useNewsData({ isUserEngaged })

  // Article content for reader mode
  const {
    articleContent,
    articleContentLoading,
    readerModeEnabled,
    setReaderModeEnabled,
    clearContent,
  } = useArticleContent({ previewArticle })

  // Get plain text for TTS from article content
  const articlePlainText = articleContent?.content ? markdownToPlainText(articleContent.content) : ''

  // Filtering and pagination
  const {
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
    seenFilter,
    setSeenFilter,
    seenVideoFilter,
    setSeenVideoFilter,
    fullArticlesOnly,
    setFullArticlesOnly,
    currentPage,
    setCurrentPage,
    videoPage,
    setVideoPage,
    filteredNews,
    filteredVideos,
    paginatedNews,
    paginatedVideos,
    totalPages,
    videoTotalPages,
    totalFilteredItems,
  } = useNewsFilters({ newsData, videoData, pageSize: PAGE_SIZE })

  // Seen status mutations
  const { markSeen, bulkMarkSeen } = useSeenStatus()

  // Reset reader mode when closing modal and stop TTS
  const handleCloseModal = useCallback(() => {
    tts.stop()
    setPreviewArticle(null)
    clearContent()
  }, [clearContent, tts])

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
  // Paused when user is engaged (reading/listening) to avoid disrupting the view
  const [, setTimeTick] = useState(0)
  useEffect(() => {
    if (isUserEngaged) return
    const interval = setInterval(() => {
      setTimeTick((t) => t + 1)
    }, 60000) // Update every minute
    return () => clearInterval(interval)
  }, [isUserEngaged])

  // Navigate to the page containing an article, then scroll to it
  const findArticle = useCallback((articleUrl: string, addPulse = false) => {
    const idx = filteredNews.findIndex(n => n.url === articleUrl)
    if (idx === -1) return
    const targetPage = Math.floor(idx / PAGE_SIZE) + 1
    if (targetPage !== currentPage) {
      setCurrentPage(targetPage)
      // Wait for re-render then scroll
      setTimeout(() => scrollToArticle(articleUrl, addPulse), 100)
    } else {
      scrollToArticle(articleUrl, addPulse)
    }
  }, [filteredNews, currentPage, setCurrentPage])

  // Listen for playlist hover events from the TTS mini player
  useEffect(() => {
    const handleHover = (e: Event) => {
      const url = (e as CustomEvent).detail?.url
      if (!url || activeTab !== 'articles') return
      cleanupArticleHoverHighlights()
      const idx = filteredNews.findIndex(n => n.url === url)
      if (idx === -1) return
      const targetPage = Math.floor(idx / PAGE_SIZE) + 1
      if (targetPage !== currentPage) {
        setCurrentPage(targetPage)
        setTimeout(() => {
          scrollToArticle(url)
          highlightArticle(url)
        }, 100)
      } else {
        scrollToArticle(url)
        highlightArticle(url)
      }
    }
    const handleLeave = (e: Event) => {
      const url = (e as CustomEvent).detail?.url
      if (url) unhighlightArticle(url)
    }
    const handleCleanup = () => cleanupArticleHoverHighlights()

    window.addEventListener('article-playlist-hover', handleHover)
    window.addEventListener('article-playlist-hover-leave', handleLeave)
    window.addEventListener('article-playlist-hover-cleanup', handleCleanup)
    return () => {
      window.removeEventListener('article-playlist-hover', handleHover)
      window.removeEventListener('article-playlist-hover-leave', handleLeave)
      window.removeEventListener('article-playlist-hover-cleanup', handleCleanup)
    }
  }, [filteredNews, currentPage, setCurrentPage, activeTab])

  // Navigate to the page containing a video, then scroll to it
  const findVideo = useCallback((videoId: string, addPulse = false) => {
    const idx = filteredVideos.findIndex(v => v.video_id === videoId)
    if (idx === -1) return
    const targetPage = Math.floor(idx / PAGE_SIZE) + 1
    if (targetPage !== videoPage) {
      setVideoPage(targetPage)
      setTimeout(() => scrollToVideo(videoId, addPulse), 100)
    } else {
      scrollToVideo(videoId, addPulse)
    }
  }, [filteredVideos, videoPage, setVideoPage])

  // Get derived values
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
            <h1 className="text-2xl font-bold">News</h1>
            <p className="text-sm text-slate-400">
              Browse {NEWS_CATEGORIES.length} categories from {availableSources.length + availableVideoSources.length} trusted sources
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
        <MarketSentimentCards isUserEngaged={isUserEngaged} />
      </div>

      {/* News Section */}
      <div className="space-y-4">
        <div className="flex items-center space-x-3">
          <Newspaper className="w-6 h-6 text-blue-400" />
          <h2 className="text-xl font-bold text-white">
            {allCategoriesSelected
              ? 'All'
              : selectedCategories.size === 1
                ? Array.from(selectedCategories)[0]
                : `${selectedCategories.size} Categories`
            } News
          </h2>
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
            {totalFilteredItems || newsData?.total_items || 0}
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
            {filteredVideos.length || videoData?.total_items || 0}
          </span>
        </button>
      </div>

      {/* Seen filter + bulk actions */}
      <NewsFilterBar
        activeTab={activeTab}
        seenFilter={seenFilter}
        setSeenFilter={setSeenFilter}
        seenVideoFilter={seenVideoFilter}
        setSeenVideoFilter={setSeenVideoFilter}
        setCurrentPage={setCurrentPage}
        setVideoPage={setVideoPage}
        fullArticlesOnly={fullArticlesOnly}
        setFullArticlesOnly={setFullArticlesOnly}
        filteredNews={filteredNews}
        filteredVideos={filteredVideos}
        bulkMarkSeen={bulkMarkSeen}
      />

      {/* Articles Tab */}
      {activeTab === 'articles' && (
        <ArticleSection
          newsData={newsData}
          filteredNews={filteredNews}
          paginatedNews={paginatedNews}
          selectedCategories={selectedCategories}
          toggleCategory={toggleCategory}
          toggleAllCategories={toggleAllCategories}
          allCategoriesSelected={allCategoriesSelected}
          selectedSources={selectedSources}
          toggleSource={toggleSource}
          toggleAllSources={toggleAllSources}
          allSourcesSelected={allSourcesSelected}
          seenFilter={seenFilter}
          currentPage={currentPage}
          setCurrentPage={setCurrentPage}
          totalPages={totalPages}
          totalFilteredItems={totalFilteredItems}
          pageSize={PAGE_SIZE}
          markSeen={markSeen}
          findArticle={findArticle}
        />
      )}

      {/* Videos Tab */}
      {activeTab === 'videos' && (
        <VideoSection
          videoData={videoData}
          filteredVideos={filteredVideos}
          paginatedVideos={paginatedVideos}
          selectedVideoCategories={selectedVideoCategories}
          toggleVideoCategory={toggleVideoCategory}
          toggleAllVideoCategories={toggleAllVideoCategories}
          allVideoCategoriesSelected={allVideoCategoriesSelected}
          selectedVideoSources={selectedVideoSources}
          toggleVideoSource={toggleVideoSource}
          toggleAllVideoSources={toggleAllVideoSources}
          allVideoSourcesSelected={allVideoSourcesSelected}
          videoPage={videoPage}
          setVideoPage={setVideoPage}
          videoTotalPages={videoTotalPages}
          pageSize={PAGE_SIZE}
          markSeen={markSeen}
          findVideo={findVideo}
        />
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
        <ArticlePreviewModal
          previewArticle={previewArticle}
          readerModeEnabled={readerModeEnabled}
          setReaderModeEnabled={setReaderModeEnabled}
          articleContent={articleContent}
          articleContentLoading={articleContentLoading}
          articlePlainText={articlePlainText}
          tts={tts}
          onClose={handleCloseModal}
        />
      )}

      {/* Source Subscriptions Modal */}
      <SourceSubscriptionsModal
        isOpen={showSourceSettings}
        onClose={() => setShowSourceSettings(false)}
      />

    </div>
  )
}
