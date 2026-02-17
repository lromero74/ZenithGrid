/**
 * Article Reader Context for persistent TTS playback
 * Manages article playlist with voice cycling and caching
 */

import { createContext, useContext, useState, useCallback, useRef, useEffect, useMemo, ReactNode } from 'react'
import { authFetch } from '../services/api'
import { useTTSSync, WordTiming } from '../pages/news/hooks/useTTSSync'
import { markdownToPlainText } from '../pages/news/helpers'
import { registerArticleReader, stopVideoPlayer } from './mediaCoordinator'
import { VOICE_CYCLE_IDS, CHILD_VOICE_IDS, containsAdultContent } from '../constants/voices'

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
  seekToTime: (time: number) => void
  skipWords: (count: number) => void
  setVoice: (voice: string) => void
  setRate: (rate: number) => void

  // Direct audio access (for smooth progress bar animation)
  getPlaybackState: () => { currentTime: number; duration: number }

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
const TTS_SESSION_KEY = 'article-reader-session'

interface TTSSession {
  playlist: ArticleItem[]
  currentIndex: number
  timestamp: number
}

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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const wakeLockRef = useRef<any>(null)
  const keepaliveAudioRef = useRef<HTMLAudioElement | null>(null)
  const autoResumeTriggeredRef = useRef(false)

  // Use TTS hook
  const tts = useTTSSync()

  // Keep playlist ref in sync
  useEffect(() => {
    playlistRef.current = playlist
  }, [playlist])

  // Keep a ref to the latest loadAndPlayArticle (for use in timeout callbacks)
  const loadAndPlayRef = useRef<typeof loadAndPlayArticle | null>(null)

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
      const response = await authFetch(`/api/news/article-content?url=${encodeURIComponent(url)}`)
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
      voiceToUse = VOICE_CYCLE_IDS[articleIndex % VOICE_CYCLE_IDS.length]
    }
    // If voice cycling is disabled, voiceToUse is undefined and TTS will use current voice

    // Fetch content if not already present
    let content = article.content
    if (!content) {
      content = await fetchArticleContent(article.url) || undefined
    }

    // Child voice content filter: if a child voice would read adult content,
    // skip to the next non-child voice in the cycle
    const textToCheck = content || article.summary || article.title || ''
    const currentVoiceId = voiceToUse || tts.currentVoice
    if (CHILD_VOICE_IDS.has(currentVoiceId) && containsAdultContent(textToCheck)) {
      if (voiceCycleEnabled) {
        // Find the next non-child voice in the cycle after this index
        for (let offset = 1; offset < VOICE_CYCLE_IDS.length; offset++) {
          const candidate = VOICE_CYCLE_IDS[(articleIndex + offset) % VOICE_CYCLE_IDS.length]
          if (!CHILD_VOICE_IDS.has(candidate)) {
            voiceToUse = candidate
            break
          }
        }
      } else {
        // Manual voice selection — pick the default adult voice
        voiceToUse = 'aria'
      }
      console.log(`[TTS] Child voice skipped for adult content, using ${voiceToUse} instead`)
    }

    // Cache voice for display purposes
    if (voiceCycleEnabled && voiceToUse) {
      const newCache = { ...voiceCache, [article.url]: voiceToUse }
      saveVoiceCache(newCache)
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

  // Keep loadAndPlayRef in sync so timeout callbacks always get the latest version
  useEffect(() => {
    loadAndPlayRef.current = loadAndPlayArticle
  }, [loadAndPlayArticle])

  // ===========================================================================
  // Playback Keep-Alive: Wake Lock + Silent Audio + Auto-Resume
  // Prevents iPad/mobile browsers from discarding the tab during TTS playback.
  // ===========================================================================

  // Acquire screen wake lock to signal active media use
  const acquireWakeLock = useCallback(async () => {
    try {
      if ('wakeLock' in navigator && !wakeLockRef.current) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        wakeLockRef.current = await (navigator as any).wakeLock.request('screen')
        wakeLockRef.current?.addEventListener('release', () => {
          wakeLockRef.current = null
        })
      }
    } catch {
      // Wake lock request can fail (low battery, unsupported, etc.)
    }
  }, [])

  const releaseWakeLock = useCallback(() => {
    try {
      wakeLockRef.current?.release()
    } catch { /* ignore */ }
    wakeLockRef.current = null
  }, [])

  // Acquire wake lock when playing, release when stopped
  useEffect(() => {
    if (isPlaying) {
      acquireWakeLock()
    } else {
      releaseWakeLock()
    }
    return () => releaseWakeLock()
  }, [isPlaying, acquireWakeLock, releaseWakeLock])

  // Re-acquire wake lock when tab becomes visible (auto-released on visibility:hidden)
  useEffect(() => {
    const handleVisibility = () => {
      if (!document.hidden && isPlaying) {
        acquireWakeLock()
      }
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [isPlaying, acquireWakeLock])

  // Create keepalive audio element (silent, looped) to prevent tab discard.
  // Browsers avoid killing tabs with active audio playback.
  useEffect(() => {
    // Generate a tiny silent WAV (0.5s, 8kHz, 8-bit mono)
    const sampleRate = 8000
    const numSamples = sampleRate * 0.5
    const buffer = new ArrayBuffer(44 + numSamples)
    const view = new DataView(buffer)
    const writeStr = (offset: number, str: string) => {
      for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i))
    }
    writeStr(0, 'RIFF')
    view.setUint32(4, 36 + numSamples, true)
    writeStr(8, 'WAVE')
    writeStr(12, 'fmt ')
    view.setUint32(16, 16, true)
    view.setUint16(20, 1, true)
    view.setUint16(22, 1, true)
    view.setUint32(24, sampleRate, true)
    view.setUint32(28, sampleRate, true)
    view.setUint16(32, 1, true)
    view.setUint16(34, 8, true)
    writeStr(36, 'data')
    view.setUint32(40, numSamples, true)
    for (let i = 0; i < numSamples; i++) view.setUint8(44 + i, 128) // 128 = silence for 8-bit WAV
    const blob = new Blob([buffer], { type: 'audio/wav' })
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audio.loop = true
    audio.volume = 0.01 // Near-silent (some browsers optimize away volume=0)
    keepaliveAudioRef.current = audio
    return () => {
      audio.pause()
      audio.src = ''
      URL.revokeObjectURL(url)
      keepaliveAudioRef.current = null
    }
  }, [])

  // Play keepalive audio during gaps between articles (no active TTS audio)
  useEffect(() => {
    const keepalive = keepaliveAudioRef.current
    if (!keepalive) return
    if (isPlaying && (tts.isLoading || (!tts.isPlaying && !tts.isPaused))) {
      // Gap between articles — play silence to maintain audio session
      keepalive.play().catch(() => {})
    } else {
      keepalive.pause()
    }
  }, [isPlaying, tts.isLoading, tts.isPlaying, tts.isPaused])

  // Persist TTS session to localStorage for auto-resume after tab kill
  useEffect(() => {
    if (isPlaying && playlist.length > 0) {
      try {
        const session: TTSSession = {
          playlist: playlist.map(({ title, url, source, source_name, published, thumbnail, summary }) =>
            ({ title, url, source, source_name, published, thumbnail, summary })),
          currentIndex,
          timestamp: Date.now(),
        }
        localStorage.setItem(TTS_SESSION_KEY, JSON.stringify(session))
      } catch { /* ignore */ }
    }
  }, [isPlaying, playlist, currentIndex])

  // Auto-resume TTS session after page reload (tab was killed by browser)
  useEffect(() => {
    if (autoResumeTriggeredRef.current) return
    autoResumeTriggeredRef.current = true

    try {
      const saved = localStorage.getItem(TTS_SESSION_KEY)
      if (!saved) return

      // Clear session BEFORE attempting resume to prevent crash loops
      localStorage.removeItem(TTS_SESSION_KEY)

      const session: TTSSession = JSON.parse(saved)
      // Only resume if saved within last 10 minutes and has content
      if (Date.now() - session.timestamp > 10 * 60 * 1000 || session.playlist.length === 0) {
        return
      }

      console.log('[TTS] Auto-resuming session:', session.playlist.length, 'articles, index', session.currentIndex)

      // Delay to let voice cache and other mount effects settle
      const timer = setTimeout(() => {
        try {
          stopVideoPlayer()
          tts.stop()
          const idx = Math.min(session.currentIndex, session.playlist.length - 1)
          setPlaylist(session.playlist)
          setCurrentIndex(idx)
          setIsPlaying(true)
          setShowMiniPlayer(true)
          if (loadAndPlayRef.current) {
            loadAndPlayRef.current(session.playlist[idx], idx)
          }
        } catch (err) {
          console.error('[TTS] Auto-resume failed:', err)
          setIsPlaying(false)
          setShowMiniPlayer(false)
        }
      }, 1000)

      return () => clearTimeout(timer)
    } catch { /* ignore parse errors */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // Mount only — intentionally omit deps

  // ===========================================================================

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
    // Clear saved session so auto-resume doesn't trigger after intentional stop
    try { localStorage.removeItem(TTS_SESSION_KEY) } catch { /* ignore */ }
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

  const value: ArticleReaderContextType = useMemo(() => ({
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
    seekToTime: tts.seekToTime,
    skipWords: tts.skipWords,
    setVoice: tts.setVoice,
    setRate: tts.setRate,

    // Direct audio access
    getPlaybackState: tts.getPlaybackState,

    // Voice cache
    getVoiceForArticle,
  }), [
    playlist, currentIndex, isPlaying, showMiniPlayer, isExpanded, currentArticle,
    tts.isLoading, tts.isPaused, tts.isReady, tts.error, tts.words,
    tts.currentWordIndex, tts.currentTime, tts.duration, tts.currentVoice, tts.playbackRate,
    articleContent, articleContentLoading, voiceCycleEnabled, toggleVoiceCycle,
    openArticle, startPlaylist, stopPlaylist, playArticle, nextArticle, previousArticle,
    toggleExpanded, closeMiniPlayer,
    tts.play, tts.pause, tts.resume, tts.stop, tts.replay,
    tts.seekToWord, tts.seekToTime, tts.skipWords, tts.setVoice, tts.setRate,
    tts.getPlaybackState, getVoiceForArticle,
  ])

  return (
    <ArticleReaderContext.Provider value={value}>
      {children}
    </ArticleReaderContext.Provider>
  )
}
