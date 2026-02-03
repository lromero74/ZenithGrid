/**
 * Article Reader Context for persistent TTS playback
 * Manages article playlist with voice cycling and caching
 */

import { createContext, useContext, useState, useCallback, useRef, useEffect, ReactNode } from 'react'
import { useTTSSync, WordTiming } from '../pages/news/hooks/useTTSSync'
import { markdownToPlainText } from '../pages/news/helpers'
import { registerArticleReader, stopVideoPlayer } from './mediaCoordinator'

// Available TTS voices for cycling (curated mix of accents and genders)
const VOICE_CYCLE = [
  // US voices
  'aria', 'guy', 'jenny', 'brian', 'emma', 'andrew',
  'ava', 'christopher', 'michelle', 'roger',
  // British voices
  'libby', 'ryan', 'sonia', 'thomas',
  // Australian voices
  'natasha', 'william',
  // Canadian voices
  'clara', 'liam',
  // Irish voices
  'emily', 'connor',
  // Other English locales
  'neerja', 'prabhat',    // Indian
  'molly', 'mitchell',    // New Zealand
  'leah', 'luke',         // South African
]

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

  // Voice cycling
  voiceCycleEnabled: boolean
  toggleVoiceCycle: () => void

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

// Storage keys
const VOICE_CACHE_KEY = 'article-reader-voice-cache'
const VOICE_CYCLE_ENABLED_KEY = 'article-reader-voice-cycle-enabled'

export function ArticleReaderProvider({ children }: ArticleReaderProviderProps) {
  const [playlist, setPlaylist] = useState<ArticleItem[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [showMiniPlayer, setShowMiniPlayer] = useState(false)
  const [isExpanded, setIsExpanded] = useState(false)
  const [articleContent, setArticleContent] = useState<string | null>(null)
  const [articleContentLoading, setArticleContentLoading] = useState(false)
  const [voiceCache, setVoiceCache] = useState<ArticleVoiceCache>({})
  const [voiceCycleEnabled, setVoiceCycleEnabled] = useState(true)

  const playlistRef = useRef<ArticleItem[]>([])
  const hasPlaybackStartedRef = useRef(false)  // Track if audio ever started for current article

  // Use TTS hook
  const tts = useTTSSync()

  // Keep playlist ref in sync
  useEffect(() => {
    playlistRef.current = playlist
  }, [playlist])

  // Load voice cache and cycle preference from localStorage
  useEffect(() => {
    try {
      const savedCache = localStorage.getItem(VOICE_CACHE_KEY)
      if (savedCache) {
        setVoiceCache(JSON.parse(savedCache))
      }
      // Check if we've migrated the voice cycling setting (v1.20.6 fix)
      const migrated = localStorage.getItem('voice-cycle-migrated-v1206')
      if (!migrated) {
        // One-time migration: reset to true to fix stale 'false' values
        localStorage.setItem(VOICE_CYCLE_ENABLED_KEY, 'true')
        localStorage.setItem('voice-cycle-migrated-v1206', 'true')
        setVoiceCycleEnabled(true)
      } else {
        // Normal behavior: load from localStorage
        const savedCycleEnabled = localStorage.getItem(VOICE_CYCLE_ENABLED_KEY)
        if (savedCycleEnabled !== null) {
          setVoiceCycleEnabled(savedCycleEnabled === 'true')
        }
      }
    } catch {
      // Ignore localStorage errors
    }
  }, [])

  // Toggle voice cycling on/off
  const toggleVoiceCycle = useCallback(() => {
    setVoiceCycleEnabled(prev => {
      const newValue = !prev
      try {
        localStorage.setItem(VOICE_CYCLE_ENABLED_KEY, String(newValue))
      } catch {
        // Ignore localStorage errors
      }
      return newValue
    })
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

  // Get voice for an article (from cache for display purposes)
  const getVoiceForArticle = useCallback((articleUrl: string): string | null => {
    return voiceCache[articleUrl] || null
  }, [voiceCache])

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
  // articleIndex is the position in the playlist (used for voice cycling)
  const loadAndPlayArticle = useCallback(async (article: ArticleItem, articleIndex: number) => {
    // Reset playback tracking for new article
    hasPlaybackStartedRef.current = false

    // Determine voice based on cycling preference
    let voiceToUse: string | undefined
    if (voiceCycleEnabled) {
      // Use position-based voice cycling: article 0 = voice 0, article 1 = voice 1, etc.
      voiceToUse = VOICE_CYCLE[articleIndex % VOICE_CYCLE.length]

      // Cache this voice for the article (for display purposes)
      const newCache = { ...voiceCache, [article.url]: voiceToUse }
      saveVoiceCache(newCache)
    }
    // If voice cycling is disabled, voiceToUse is undefined and TTS will use current voice

    // Fetch content if not already present
    let content = article.content
    if (!content) {
      content = await fetchArticleContent(article.url) || undefined
    }

    if (content) {
      setArticleContent(content)
      const plainText = markdownToPlainText(content)
      // Pass voice directly to avoid async state race condition
      await tts.loadAndPlay(plainText, voiceToUse)
    } else {
      // No content available, try to read summary
      if (article.summary) {
        setArticleContent(article.summary)
        await tts.loadAndPlay(article.summary, voiceToUse)
      }
    }
  }, [voiceCycleEnabled, voiceCache, saveVoiceCache, fetchArticleContent, tts])

  // Start a new playlist
  const startPlaylist = useCallback((articles: ArticleItem[], startIndex: number = 0, startExpanded: boolean = false) => {
    if (articles.length === 0) return
    // Stop video player if playing (mutually exclusive)
    stopVideoPlayer()
    // Clear any previous TTS state (error, loading, etc.) before showing mini player
    tts.stop()

    const clampedIndex = Math.min(Math.max(0, startIndex), articles.length - 1)
    setPlaylist(articles)
    setCurrentIndex(clampedIndex)
    setIsPlaying(true)
    setShowMiniPlayer(true)
    setIsExpanded(startExpanded)

    // Load and play the first article (pass index for voice cycling)
    loadAndPlayArticle(articles[clampedIndex], clampedIndex)
  }, [loadAndPlayArticle, tts])

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

  // Register with media coordinator for mutual exclusion with video player
  useEffect(() => {
    registerArticleReader(stopPlaylist)
  }, [stopPlaylist])

  // Play specific article in playlist
  const playArticle = useCallback((index: number) => {
    if (index >= 0 && index < playlistRef.current.length) {
      tts.stop()
      setCurrentIndex(index)
      loadAndPlayArticle(playlistRef.current[index], index)
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

    // Voice cycling
    voiceCycleEnabled,
    toggleVoiceCycle,

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
