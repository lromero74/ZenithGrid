/**
 * Article Reader Context for persistent TTS playback
 * Manages article playlist with voice cycling and caching
 */

import { createContext, useContext, useState, useCallback, useRef, useEffect, ReactNode } from 'react'
import { useTTSSync, WordTiming } from '../pages/news/hooks/useTTSSync'
import { markdownToPlainText } from '../pages/news/helpers'

// Available TTS voices for cycling
const VOICE_CYCLE = ['aria', 'guy', 'jenny', 'brian', 'emma', 'andrew']

export interface ArticleItem {
  title: string
  url: string
  source: string
  source_name: string
  published: string | null
  thumbnail: string | null
  summary: string | null
  content?: string  // Full article content (markdown)
}

interface ArticleVoiceCache {
  [articleUrl: string]: string  // Maps article URL to voice ID
}

interface ArticleReaderContextType {
  // Playlist state
  playlist: ArticleItem[]
  currentIndex: number
  isPlaying: boolean
  showMiniPlayer: boolean
  isExpanded: boolean
  currentArticle: ArticleItem | null

  // TTS state (proxied from useTTSSync)
  isLoading: boolean
  isPaused: boolean
  isReady: boolean
  error: string | null
  words: WordTiming[]
  currentWordIndex: number
  currentTime: number
  duration: number
  currentVoice: string
  playbackRate: number

  // Content state
  articleContent: string | null
  articleContentLoading: boolean

  // Actions
  openArticle: (article: ArticleItem, allArticles?: ArticleItem[]) => void
  startPlaylist: (articles: ArticleItem[], startIndex?: number, startExpanded?: boolean) => void
  stopPlaylist: () => void
  playArticle: (index: number) => void
  nextArticle: () => void
  previousArticle: () => void
  toggleExpanded: () => void
  closeMiniPlayer: () => void
  setExpanded: (expanded: boolean) => void

  // TTS actions (proxied)
  play: () => void
  pause: () => void
  resume: () => void
  stop: () => void
  replay: () => void
  seekToWord: (index: number) => void
  skipWords: (count: number) => void
  setVoice: (voice: string) => void
  setRate: (rate: number) => void

  // Voice cache
  getVoiceForArticle: (articleUrl: string) => string | null
}

const ArticleReaderContext = createContext<ArticleReaderContextType | null>(null)

// eslint-disable-next-line react-refresh/only-export-components
export function useArticleReader() {
  const context = useContext(ArticleReaderContext)
  if (!context) {
    throw new Error('useArticleReader must be used within ArticleReaderProvider')
  }
  return context
}

interface ArticleReaderProviderProps {
  children: ReactNode
}

// Storage key for voice cache
const VOICE_CACHE_KEY = 'article-reader-voice-cache'

export function ArticleReaderProvider({ children }: ArticleReaderProviderProps) {
  const [playlist, setPlaylist] = useState<ArticleItem[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [showMiniPlayer, setShowMiniPlayer] = useState(false)
  const [isExpanded, setIsExpanded] = useState(false)
  const [articleContent, setArticleContent] = useState<string | null>(null)
  const [articleContentLoading, setArticleContentLoading] = useState(false)
  const [voiceCache, setVoiceCache] = useState<ArticleVoiceCache>({})

  // Track which voice index to use for cycling
  const voiceCycleIndexRef = useRef(0)
  const playlistRef = useRef<ArticleItem[]>([])
  const hasPlaybackStartedRef = useRef(false)  // Track if audio ever started for current article

  // Use TTS hook
  const tts = useTTSSync()

  // Keep playlist ref in sync
  useEffect(() => {
    playlistRef.current = playlist
  }, [playlist])

  // Load voice cache from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem(VOICE_CACHE_KEY)
      if (saved) {
        setVoiceCache(JSON.parse(saved))
      }
    } catch {
      // Ignore localStorage errors
    }
  }, [])

  // Save voice cache to localStorage
  const saveVoiceCache = useCallback((cache: ArticleVoiceCache) => {
    setVoiceCache(cache)
    try {
      localStorage.setItem(VOICE_CACHE_KEY, JSON.stringify(cache))
    } catch {
      // Ignore localStorage errors
    }
  }, [])

  // Get voice for an article (from cache or assign new)
  const getVoiceForArticle = useCallback((articleUrl: string): string | null => {
    return voiceCache[articleUrl] || null
  }, [voiceCache])

  // Get or assign voice for current article
  const getOrAssignVoice = useCallback((articleUrl: string): string => {
    // If cached, use cached voice
    if (voiceCache[articleUrl]) {
      return voiceCache[articleUrl]
    }

    // Otherwise, cycle to next voice and cache it
    const voice = VOICE_CYCLE[voiceCycleIndexRef.current % VOICE_CYCLE.length]
    voiceCycleIndexRef.current++

    // Cache this voice for the article
    const newCache = { ...voiceCache, [articleUrl]: voice }
    saveVoiceCache(newCache)

    return voice
  }, [voiceCache, saveVoiceCache])

  // Get current article
  const currentArticle = playlist.length > 0 && currentIndex < playlist.length
    ? playlist[currentIndex]
    : null

  // Fetch article content
  const fetchArticleContent = useCallback(async (url: string): Promise<string | null> => {
    setArticleContentLoading(true)
    try {
      const response = await fetch(`/api/news/article-content?url=${encodeURIComponent(url)}`)
      if (!response.ok) {
        throw new Error('Failed to fetch article')
      }
      const data = await response.json()
      if (data.success && data.content) {
        return data.content
      }
      return null
    } catch (err) {
      console.error('Failed to fetch article content:', err)
      return null
    } finally {
      setArticleContentLoading(false)
    }
  }, [])

  // Load and play an article
  const loadAndPlayArticle = useCallback(async (article: ArticleItem) => {
    // Reset playback tracking for new article
    hasPlaybackStartedRef.current = false

    // Get or assign voice for this article
    const voice = getOrAssignVoice(article.url)
    tts.setVoice(voice)

    // Fetch content if not already present
    let content = article.content
    if (!content) {
      content = await fetchArticleContent(article.url) || undefined
    }

    if (content) {
      setArticleContent(content)
      const plainText = markdownToPlainText(content)
      await tts.loadAndPlay(plainText)
    } else {
      // No content available, try to read summary
      if (article.summary) {
        setArticleContent(article.summary)
        await tts.loadAndPlay(article.summary)
      }
    }
  }, [getOrAssignVoice, fetchArticleContent, tts])

  // Start a new playlist
  const startPlaylist = useCallback((articles: ArticleItem[], startIndex: number = 0, startExpanded: boolean = false) => {
    if (articles.length === 0) return

    const clampedIndex = Math.min(Math.max(0, startIndex), articles.length - 1)
    setPlaylist(articles)
    setCurrentIndex(clampedIndex)
    setIsPlaying(true)
    setShowMiniPlayer(true)
    setIsExpanded(startExpanded)

    // Reset voice cycle index when starting new playlist
    voiceCycleIndexRef.current = 0

    // Load and play the first article
    loadAndPlayArticle(articles[clampedIndex])
  }, [loadAndPlayArticle])

  // Open a single article (expanded view) - optionally with surrounding articles for navigation
  const openArticle = useCallback((article: ArticleItem, allArticles?: ArticleItem[]) => {
    if (allArticles && allArticles.length > 0) {
      // Find the index of the clicked article in the full list
      const index = allArticles.findIndex(a => a.url === article.url)
      if (index >= 0) {
        startPlaylist(allArticles, index, true)
        return
      }
    }
    // Single article, create a one-item playlist
    startPlaylist([article], 0, true)
  }, [startPlaylist])

  // Stop playlist
  const stopPlaylist = useCallback(() => {
    tts.stop()
    setIsPlaying(false)
    setShowMiniPlayer(false)
    setArticleContent(null)
  }, [tts])

  // Play specific article in playlist
  const playArticle = useCallback((index: number) => {
    if (index >= 0 && index < playlistRef.current.length) {
      tts.stop()
      setCurrentIndex(index)
      loadAndPlayArticle(playlistRef.current[index])
    }
  }, [tts, loadAndPlayArticle])

  // Go to next article
  const nextArticle = useCallback(() => {
    if (currentIndex < playlistRef.current.length - 1) {
      playArticle(currentIndex + 1)
    } else {
      // End of playlist
      stopPlaylist()
    }
  }, [currentIndex, playArticle, stopPlaylist])

  // Go to previous article
  const previousArticle = useCallback(() => {
    if (currentIndex > 0) {
      playArticle(currentIndex - 1)
    }
  }, [currentIndex, playArticle])

  // Toggle expanded view
  const toggleExpanded = useCallback(() => {
    setIsExpanded(prev => !prev)
  }, [])

  // Close mini player
  const closeMiniPlayer = useCallback(() => {
    stopPlaylist()
  }, [stopPlaylist])

  // Track when TTS playback actually starts
  useEffect(() => {
    if (tts.isPlaying) {
      hasPlaybackStartedRef.current = true
    }
  }, [tts.isPlaying])

  // Handle TTS ended - auto-advance to next article
  useEffect(() => {
    // Only auto-advance if:
    // 1. Context thinks we're playing
    // 2. Playback actually started at some point (prevents premature advance)
    // 3. TTS is now idle (not playing, paused, loading, or ready)
    // 4. Words were loaded (proves content was fetched)
    if (isPlaying && hasPlaybackStartedRef.current && !tts.isPlaying && !tts.isPaused && !tts.isLoading && !tts.isReady && tts.words.length > 0) {
      // Small delay before advancing to next article
      const timer = setTimeout(() => {
        nextArticle()
      }, 1500)
      return () => clearTimeout(timer)
    }
  }, [isPlaying, tts.isPlaying, tts.isPaused, tts.isLoading, tts.isReady, tts.words.length, nextArticle])

  // ESC to collapse
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isExpanded) {
        setIsExpanded(false)
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isExpanded])

  const value: ArticleReaderContextType = {
    // Playlist state
    playlist,
    currentIndex,
    isPlaying,
    showMiniPlayer,
    isExpanded,
    currentArticle,

    // TTS state
    isLoading: tts.isLoading,
    isPaused: tts.isPaused,
    isReady: tts.isReady,
    error: tts.error,
    words: tts.words,
    currentWordIndex: tts.currentWordIndex,
    currentTime: tts.currentTime,
    duration: tts.duration,
    currentVoice: tts.currentVoice,
    playbackRate: tts.playbackRate,

    // Content state
    articleContent,
    articleContentLoading,

    // Actions
    openArticle,
    startPlaylist,
    stopPlaylist,
    playArticle,
    nextArticle,
    previousArticle,
    toggleExpanded,
    closeMiniPlayer,
    setExpanded: setIsExpanded,

    // TTS actions
    play: tts.play,
    pause: tts.pause,
    resume: tts.resume,
    stop: tts.stop,
    replay: tts.replay,
    seekToWord: tts.seekToWord,
    skipWords: tts.skipWords,
    setVoice: tts.setVoice,
    setRate: tts.setRate,

    // Voice cache
    getVoiceForArticle,
  }

  return (
    <ArticleReaderContext.Provider value={value}>
      {children}
    </ArticleReaderContext.Provider>
  )
}
