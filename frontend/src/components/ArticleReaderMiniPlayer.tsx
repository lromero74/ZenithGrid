/**
 * Article Reader Mini Player Component
 * Persistent player that morphs between mini-bar and full modal
 * Shows word-highlighted text in expanded mode
 */

import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { Play, Pause, SkipBack, SkipForward, X, Maximize2, Minimize2, ListVideo, ExternalLink, RotateCcw, Volume2, Volume1, VolumeX, RefreshCw, Repeat, AlertCircle } from 'lucide-react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useArticleReader } from '../contexts/ArticleReaderContext'
import { sourceColors } from './news'
import { markdownToPlainText, scrollToArticle } from '../pages/news/helpers'
import { TTS_VOICES, TTS_VOICES_BY_ID } from '../constants/voices'

// Format seconds to MM:SS
function formatTime(seconds: number): string {
  if (!seconds || isNaN(seconds)) return '0:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

// Number-related words that TTS uses when reading numbers/currency
const NUMBER_WORDS = new Set([
  'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
  'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen',
  'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety',
  'hundred', 'thousand', 'million', 'billion', 'trillion',
  'dollar', 'dollars', 'cent', 'cents', 'percent', 'point',
  'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth'
])

// Check if a string contains digits
const hasDigits = (s: string) => /\d/.test(s)

export function ArticleReaderMiniPlayer() {
  const {
    playlist,
    currentIndex,
    isPlaying,
    showMiniPlayer,
    isExpanded,
    setExpanded,
    currentArticle,
    isLoading,
    isPaused,
    isReady,
    error,
    words,
    currentWordIndex,
    currentTime,
    duration,
    currentVoice,
    playbackRate,
    articleContent,
    articleContentLoading,
    isSummaryOnly,
    voiceCycleEnabled,
    toggleVoiceCycle,
    continuousPlay,
    setContinuousPlay,
    pendingResume,
    resumeSession,
    dismissResume,
    nextArticle,
    previousArticle,
    closeMiniPlayer,
    playArticle,
    play,
    pause,
    resume,
    replay,
    seekToWord,
    seekToTime,
    getPlaybackState,
    setVoice,
    setRate,
    volume,
    setVolume,
  } = useArticleReader()

  const navigate = useNavigate()
  const location = useLocation()

  const [showPlaylistDropdown, setShowPlaylistDropdown] = useState(false)
  const [showSettingsDropdown, setShowSettingsDropdown] = useState(false)
  const [hoveredPlaylistIndex, setHoveredPlaylistIndex] = useState<number | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const settingsRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const wordRefs = useRef<(HTMLSpanElement | null)[]>([])
  const prevHighlightRef = useRef<number>(-1)
  const progressBarRef = useRef<HTMLDivElement>(null)
  const progressRafRef = useRef<number | null>(null)
  const getPlaybackStateRef = useRef(getPlaybackState)

  // Keep ref in sync (avoids restarting rAF on context value changes)
  useEffect(() => {
    getPlaybackStateRef.current = getPlaybackState
  }, [getPlaybackState])

  // Smooth progress bar via direct DOM updates (bypasses React state for 60fps)
  useEffect(() => {
    if (!isPlaying && !isPaused) {
      // Not active — reset bar
      if (progressBarRef.current) progressBarRef.current.style.width = '0%'
      return
    }

    const updateBar = () => {
      if (progressBarRef.current) {
        const state = getPlaybackStateRef.current()
        const pct = state.duration > 0 ? (state.currentTime / state.duration) * 100 : 0
        progressBarRef.current.style.width = `${pct}%`
      }
      progressRafRef.current = requestAnimationFrame(updateBar)
    }

    progressRafRef.current = requestAnimationFrame(updateBar)
    return () => {
      if (progressRafRef.current) cancelAnimationFrame(progressRafRef.current)
    }
  }, [isPlaying, isPaused])

  // Convert article content to plain text for word matching
  const plainText = useMemo(() => {
    return articleContent ? markdownToPlainText(articleContent) : ''
  }, [articleContent])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowPlaylistDropdown(false)
        setHoveredPlaylistIndex(null)
        window.dispatchEvent(new CustomEvent('article-playlist-hover-cleanup'))
      }
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) {
        setShowSettingsDropdown(false)
      }
    }
    if (showPlaylistDropdown || showSettingsDropdown) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showPlaylistDropdown, showSettingsDropdown])

  // Auto-scroll to keep current word visible in expanded mode
  useEffect(() => {
    if (isExpanded && currentWordIndex >= 0 && wordRefs.current[currentWordIndex] && contentRef.current) {
      const wordEl = wordRefs.current[currentWordIndex]
      const container = contentRef.current

      if (wordEl) {
        const wordRect = wordEl.getBoundingClientRect()
        const containerRect = container.getBoundingClientRect()

        const isAbove = wordRect.top < containerRect.top + 50
        const isBelow = wordRect.bottom > containerRect.bottom - 50

        if (isAbove || isBelow) {
          wordEl.scrollIntoView({
            behavior: 'smooth',
            block: 'center',
          })
        }
      }
    }
  }, [currentWordIndex, isExpanded])

  // O(1) word highlighting via direct DOM manipulation (P1)
  useEffect(() => {
    const prev = prevHighlightRef.current
    if (prev >= 0 && wordRefs.current[prev]) {
      const el = wordRefs.current[prev]!
      el.classList.remove('bg-yellow-500/40', 'text-white', 'font-medium')
      el.classList.add('text-slate-300')
    }
    if (currentWordIndex >= 0 && wordRefs.current[currentWordIndex]) {
      const el = wordRefs.current[currentWordIndex]!
      el.classList.remove('text-slate-300')
      el.classList.add('bg-yellow-500/40', 'text-white', 'font-medium')
    }
    prevHighlightRef.current = currentWordIndex
  }, [currentWordIndex])

  // Toggle play/pause - also handles retry on error and stopped state
  const togglePlayPause = useCallback(() => {
    if (error) {
      // On error, retry the current article
      playArticle(currentIndex)
    } else if (isPaused) {
      resume()
    } else if (isReady) {
      play()
    } else if (isPlaying) {
      pause()
    } else if (!isPlaying && !isPaused && !isReady && !isLoading) {
      // Stopped state (continuous play off, article finished) — replay current article
      playArticle(currentIndex)
    }
  }, [error, isPaused, isReady, isPlaying, isLoading, play, pause, resume, playArticle, currentIndex])

  // Find current article - navigate to news page if needed, then scroll
  const findCurrentArticle = useCallback(() => {
    if (!currentArticle) return

    const isOnNewsPage = location.pathname === '/news'

    if (isOnNewsPage) {
      scrollToArticle(currentArticle.url, true)
    } else {
      // Navigate to news page, then scroll after it renders
      navigate('/news')
      setTimeout(() => {
        scrollToArticle(currentArticle.url, true)
      }, 300)
    }
  }, [currentArticle, location.pathname, navigate])

  // Progress bar click handler - time-based to match the time-driven progress bar
  const handleProgressClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (duration <= 0) return

    const rect = e.currentTarget.getBoundingClientRect()
    const clickX = e.clientX - rect.left
    const percentage = Math.max(0, Math.min(1, clickX / rect.width))

    // Convert click position to a target time, then seek to the nearest word
    const targetTime = percentage * duration
    seekToTime(targetTime)
  }, [duration, seekToTime])

  // P2: Event delegation for word clicks — single handler on container
  const handleWordClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement
    const ttsIdx = target.dataset?.ttsIdx
    if (ttsIdx !== undefined) {
      seekToWord(parseInt(ttsIdx, 10))
    }
  }, [seekToWord])

  // Build word-highlighted content by matching TTS words to text words sequentially
  const renderedContent = useMemo(() => {
    // M7: Reset stale DOM refs when content changes
    wordRefs.current = []

    // Show placeholder if no content yet
    if (!plainText) {
      return (
        <p className="text-slate-400 italic">
          Click the play button to load and read this article aloud.
        </p>
      )
    }

    // Show plain text if TTS hasn't loaded words yet
    if (words.length === 0) {
      return <p className="text-slate-300 leading-relaxed whitespace-pre-wrap">{plainText}</p>
    }

    // Extract all words from plain text with their positions
    // Include hyphens and apostrophes as part of words (e.g., "anti-union", "don't")
    // Also capture $numbers, numbers%, and acronyms with periods (U.S., U.K.)
    // Note: en-dashes (–) and em-dashes (—) are treated as separators since TTS reads them as separate words
    const textWords: Array<{ start: number; end: number; text: string; lower: string; clean: string; isNumeric: boolean }> = []
    // Regex patterns: $numbers | numbers% | acronyms (A.B.C.) | regular words (with various apostrophe chars)
    const wordRegex = /\$[\d,\.]+|\d[\d,\.]*%|(?:[A-Z]\.)+[A-Z]?|[a-zA-Z0-9]+(?:[-'''`ʼ][a-zA-Z0-9]+)*/g
    let match
    while ((match = wordRegex.exec(plainText)) !== null) {
      const text = match[0]
      const lower = text.toLowerCase()
      textWords.push({
        start: match.index,
        end: match.index + text.length,
        text: text,
        lower: lower,
        clean: lower.replace(/[^a-z0-9]/g, ''), // alphanumeric only for matching
        isNumeric: hasDigits(text),
      })
    }

    // Match TTS words to text words sequentially
    // Simple strategy: find matches, and if no match found, inherit from previous TTS word
    // This handles possessives ("Trump's" -> "Trump" + "s") and numbers ("$500" -> "five hundred dollars")
    const ttsToTextMap = new Map<number, number>() // TTS index -> text word index
    let textWordPtr = 0
    let lastMatchIdx: number | null = null

    words.forEach((word, ttsIndex) => {
      const ttsClean = word.text.toLowerCase().replace(/[^a-z0-9]/g, '')
      if (ttsClean.length === 0) {
        // Empty after cleaning - inherit previous match
        if (lastMatchIdx !== null) ttsToTextMap.set(ttsIndex, lastMatchIdx)
        return
      }

      const isNumberWord = NUMBER_WORDS.has(ttsClean)
      let matchIdx: number | null = null

      // First pass: look for exact match (prioritize over partial/number matches)
      for (let i = textWordPtr; i < textWords.length && i < textWordPtr + 10; i++) {
        if (textWords[i].clean === ttsClean) {
          matchIdx = i
          textWordPtr = i + 1
          break
        }
      }

      // Second pass: if no exact match, look for partial/number matches
      if (matchIdx === null) {
        for (let i = textWordPtr; i < textWords.length && i < textWordPtr + 10; i++) {
          const tw = textWords[i]

          // Text contains TTS word (e.g., "trumps" contains "trump")
          if (tw.clean.includes(ttsClean) && ttsClean.length > 1) {
            matchIdx = i
            // Don't advance - suffix may also match this word
            break
          }

          // TTS contains text (abbreviation expansion)
          if (ttsClean.includes(tw.clean) && tw.clean.length > 1) {
            matchIdx = i
            textWordPtr = i + 1
            break
          }

          // Number word matches numeric text
          if (isNumberWord && tw.isNumeric) {
            matchIdx = i
            // Don't advance - more number words may match
            break
          }
        }
      }

      // If no match found, inherit from previous TTS word
      // This handles: possessive suffixes, number word continuations, etc.
      if (matchIdx === null && lastMatchIdx !== null) {
        matchIdx = lastMatchIdx
      }

      if (matchIdx !== null) {
        ttsToTextMap.set(ttsIndex, matchIdx)
        lastMatchIdx = matchIdx
      }
    })

    // Build the rendered content
    const elements: React.ReactElement[] = []
    let lastEnd = 0

    // Create reverse map: text word index -> Set of TTS indices
    // Multiple TTS words can map to the same text word (e.g., "President" and "s" both map to "President's")
    const textToTTSMap = new Map<number, Set<number>>()
    ttsToTextMap.forEach((textIdx, ttsIdx) => {
      if (!textToTTSMap.has(textIdx)) {
        textToTTSMap.set(textIdx, new Set())
      }
      textToTTSMap.get(textIdx)!.add(ttsIdx)
    })

    textWords.forEach((tw, twIndex) => {
      // Add any text before this word (punctuation, spaces, etc.)
      if (tw.start > lastEnd) {
        elements.push(
          <span key={`between-${twIndex}`} className="text-slate-300">
            {plainText.slice(lastEnd, tw.start)}
          </span>
        )
      }

      const ttsIndices = textToTTSMap.get(twIndex)
      // Use the first TTS index for seeking/refs
      const firstTTSIndex = ttsIndices ? Math.min(...ttsIndices) : undefined

      elements.push(
        <span
          key={`word-${twIndex}`}
          ref={(el) => {
            if (firstTTSIndex !== undefined) {
              wordRefs.current[firstTTSIndex] = el
            }
          }}
          data-tts-idx={firstTTSIndex}
          className="text-slate-300 transition-all duration-150 rounded px-0.5 cursor-pointer hover:bg-slate-600/50"
        >
          {tw.text}
        </span>
      )

      lastEnd = tw.end
    })

    // Add any remaining text after the last word
    if (lastEnd < plainText.length) {
      elements.push(
        <span key="remaining" className="text-slate-300">
          {plainText.slice(lastEnd)}
        </span>
      )
    }

    return <p className="leading-relaxed whitespace-pre-wrap">{elements}</p>
  }, [words, plainText])

  // Resume prompt banner — shown when there's a pending session and player isn't active
  if (pendingResume && !showMiniPlayer) {
    const resumeArticle = pendingResume.playlist[Math.min(pendingResume.currentIndex, pendingResume.playlist.length - 1)]
    return (
      <>
        <div className="fixed bottom-0 left-0 right-0 z-50 bg-slate-800 border-t border-slate-700 shadow-2xl">
          <div className="flex items-center gap-3 px-4 py-3">
            <div className="flex-1 min-w-0">
              <p className="text-sm text-slate-300">Continue where you left off?</p>
              <p className="text-xs text-slate-500 truncate">
                {resumeArticle?.title} ({pendingResume.currentIndex + 1}/{pendingResume.playlist.length})
              </p>
            </div>
            <button
              onClick={resumeSession}
              className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white text-sm font-medium rounded-lg transition-colors flex-shrink-0"
            >
              Resume
            </button>
            <button
              onClick={dismissResume}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 text-sm font-medium rounded-lg transition-colors flex-shrink-0"
            >
              Dismiss
            </button>
          </div>
        </div>
        <div className="h-16" />
      </>
    )
  }

  // Don't render if not showing
  if (!showMiniPlayer || !currentArticle) {
    return null
  }

  const voiceInfo = TTS_VOICES_BY_ID[currentVoice] || { name: currentVoice, gender: '' }
  const isAudioActive = !isLoading && (isPaused || words.length > 0)

  return (
    <>
      {/* Dark overlay when expanded */}
      {isExpanded && (
        <div
          className="fixed inset-0 bg-black/80 z-40 transition-opacity"
          onClick={() => setExpanded(false)}
        />
      )}

      {/* Player container - morphs between mini-bar and modal */}
      <div
        className={`fixed z-50 transition-all duration-300 ease-in-out ${
          isExpanded
            ? 'inset-0 sm:inset-8 md:inset-12 lg:inset-x-[10%] lg:inset-y-8'
            : 'bottom-0 left-0 right-0 sm:h-20'
        }`}
      >
        <div className={`h-full bg-slate-800 shadow-2xl flex transition-all duration-300 overflow-hidden ${
          isExpanded
            ? 'flex-col rounded-lg border border-slate-700'
            : 'flex-row border-t border-slate-700'
        }`}>

          {/* Expanded: Pinned thumbnail with blurred background fill */}
          {isExpanded && currentArticle.thumbnail && (
            <div className="relative w-full flex-shrink-0 overflow-hidden max-h-[150px] sm:max-h-[250px] bg-slate-900">
              {/* Blurred version fills empty space on sides */}
              <img
                src={currentArticle.thumbnail}
                alt=""
                aria-hidden="true"
                className="absolute inset-0 w-full h-full object-cover blur-2xl scale-110 opacity-90"
              />
              {/* Actual image centered on top */}
              <img
                src={currentArticle.thumbnail}
                alt=""
                className="relative w-full h-auto max-h-[150px] sm:max-h-[250px] object-contain mx-auto"
                onError={(e) => {
                  // Hide the whole container (both images) on error
                  (e.target as HTMLImageElement).parentElement!.style.display = 'none'
                }}
              />
            </div>
          )}
          {/* Expanded: Pinned article info */}
          {isExpanded && (
            <div className="flex-shrink-0 px-3 sm:px-6 pt-3 sm:pt-4 pb-2">
              {/* Header with source, time, voice */}
              <div className="flex flex-wrap items-center gap-3 mb-2">
                <span className={`px-2 py-1 rounded text-sm font-medium border ${
                  sourceColors[currentArticle.source] || 'bg-slate-600 text-slate-300'
                }`}>
                  {currentArticle.source_name}
                </span>
                {isSummaryOnly && (
                  <span className="px-2 py-1 rounded text-sm font-medium bg-amber-600/20 text-amber-400 border border-amber-500/30">
                    Summary only
                  </span>
                )}
                {currentArticle.published && (
                  <span className="text-sm text-slate-400">
                    {new Date(currentArticle.published).toLocaleDateString(undefined, {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </span>
                )}
                <span className="text-sm text-green-400">
                  Voice: {voiceInfo.name} ({voiceInfo.gender})
                </span>
                <span className="text-sm text-slate-500">
                  Article {currentIndex + 1} of {playlist.length}
                </span>
              </div>

              {/* Title */}
              <h1 className="text-xl sm:text-2xl font-bold text-white leading-tight">
                {currentArticle.title}
              </h1>
              <div className="mt-3 h-px bg-gradient-to-r from-transparent via-slate-600 to-transparent" />
            </div>
          )}

          {/* Expanded: Scrollable article body */}
          {isExpanded && (
            <div
              ref={contentRef}
              className="flex-1 overflow-y-auto relative [mask-image:linear-gradient(to_bottom,transparent,black_24px,black_calc(100%-24px),transparent)]"
            >
              <div className="px-3 sm:px-6 py-2">
                {/* Article content with word highlighting */}
                <div className="prose prose-invert prose-slate max-w-none" onClick={handleWordClick}>
                  {articleContentLoading ? (
                    <div className="flex items-center justify-center py-12">
                      <div className="animate-spin w-8 h-8 border-2 border-green-500 border-t-transparent rounded-full" />
                      <span className="ml-3 text-slate-400">Loading article content...</span>
                    </div>
                  ) : (
                    renderedContent
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Mini mode: Thumbnail (click to find article in news list) */}
          {!isExpanded && currentArticle.thumbnail && (
            <div
              className="w-20 h-12 sm:w-28 sm:h-16 my-auto ml-2 sm:ml-4 rounded overflow-hidden flex-shrink-0 bg-slate-900 cursor-pointer hover:ring-2 hover:ring-green-500 transition-all"
              onClick={findCurrentArticle}
              title="Find article in news list"
            >
              <img
                src={currentArticle.thumbnail}
                alt=""
                className="w-full h-full object-cover"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = 'none'
                }}
              />
            </div>
          )}

          {/* Controls bar */}
          <div className={`flex transition-all duration-300 ${
            isExpanded
              ? 'flex-col sm:flex-row items-center gap-2 sm:gap-4 p-2 sm:p-4 border-t border-slate-700'
              : 'flex-col flex-1 min-w-0 px-2 sm:px-4 py-2 justify-center gap-0.5 sm:gap-1'
          }`}>
            {/* Article info — only in mini mode (pinned header shows it in expanded) */}
            {!isExpanded && (
              <div className="flex items-center gap-2 min-w-0">
                <span className={`px-1.5 py-0.5 rounded text-xs font-medium border flex-shrink-0 ${
                  sourceColors[currentArticle.source] || 'bg-slate-600 text-slate-300'
                }`}>
                  {currentArticle.source_name}
                </span>
                {isSummaryOnly && (
                  <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-amber-600/20 text-amber-400 border border-amber-500/30 flex-shrink-0">
                    Summary
                  </span>
                )}
                <h4 className="text-sm font-medium text-white truncate flex-1">
                  {currentArticle.title}
                </h4>
                <div className="flex items-center gap-2 text-xs text-slate-500 flex-shrink-0">
                  <span>{voiceInfo.name}</span>
                  <span>{currentIndex + 1}/{playlist.length}</span>
                </div>
              </div>
            )}

            {/* Progress and controls */}
            <div className={`flex gap-1 sm:gap-2 w-full sm:w-auto ${isExpanded ? 'flex-col sm:flex-row items-center flex-1' : 'flex-col sm:flex-row items-center'}`}>
              {/* Progress bar and time */}
              <div className={`flex items-center gap-1 sm:gap-2 min-w-0 w-full ${isExpanded ? 'sm:w-auto sm:flex-1' : 'sm:flex-1'}`}>
                <span className="text-xs text-slate-400 w-8 sm:w-10 text-right flex-shrink-0 font-mono">
                  {formatTime(currentTime)}
                </span>

                <div
                  className="flex-1 h-2 bg-slate-700 rounded-full cursor-pointer group relative"
                  onClick={handleProgressClick}
                >
                  <div
                    ref={progressBarRef}
                    className="h-full bg-green-500 rounded-full relative"
                    style={{ width: '0%' }}
                  >
                    <div className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-1/2 w-3 h-3 bg-white rounded-full shadow-md opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </div>

                <span className="text-xs text-slate-400 w-12 flex-shrink-0 font-mono">
                  -{formatTime(Math.max(0, duration - currentTime))}
                </span>
              </div>

              {/* Playback controls */}
              <div className={`flex items-center gap-1 ${isExpanded ? 'flex-wrap justify-center sm:justify-start' : 'flex-wrap justify-center sm:justify-start'}`}>
                {/* Voice settings dropdown */}
                <div className="relative" ref={settingsRef}>
                  <button
                    onClick={() => setShowSettingsDropdown(!showSettingsDropdown)}
                    className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                    title="Voice settings"
                  >
                    <Volume2 className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                  </button>

                  {showSettingsDropdown && (
                    <div className="fixed bottom-24 right-4 sm:right-20 w-60 sm:w-64 bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-[60] p-4">
                      <div className="space-y-4">
                        {/* Voice cycling toggle */}
                        <div>
                          <button
                            onClick={toggleVoiceCycle}
                            className={`w-full flex items-center justify-between px-3 py-2 rounded-lg transition-colors ${
                              voiceCycleEnabled
                                ? 'bg-green-500/20 border border-green-500/30 text-green-400'
                                : 'bg-slate-700 border border-slate-600 text-slate-400'
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <RefreshCw className={`w-4 h-4 ${voiceCycleEnabled ? 'animate-spin' : ''}`} style={{ animationDuration: '3s' }} />
                              <span className="text-sm font-medium">Voice Cycling</span>
                            </div>
                            <span className="text-xs">{voiceCycleEnabled ? 'ON' : 'OFF'}</span>
                          </button>
                          <p className="text-xs text-slate-500 mt-1">
                            {voiceCycleEnabled
                              ? 'Different voice for each article'
                              : 'Same voice for all articles'}
                          </p>
                        </div>

                        {/* Voice selector */}
                        <div>
                          <label className="text-xs text-slate-400 block mb-1">Voice</label>
                          <select
                            value={currentVoice}
                            onChange={(e) => setVoice(e.target.value)}
                            disabled={voiceCycleEnabled || (!isPaused && !isReady)}
                            className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-sm text-white disabled:opacity-50"
                          >
                            {TTS_VOICES.map((v) => (
                              <option key={v.id} value={v.id}>
                                {v.name} ({v.gender}{v.locale ? `, ${v.locale}` : ''})
                              </option>
                            ))}
                          </select>
                          <p className="text-xs text-slate-500 mt-1">
                            {voiceCycleEnabled
                              ? 'Disable cycling to choose voice'
                              : 'Change voice while paused'}
                          </p>
                        </div>

                        {/* Speed selector */}
                        <div>
                          <label className="text-xs text-slate-400 block mb-1">Speed</label>
                          <select
                            value={playbackRate}
                            onChange={(e) => setRate(parseFloat(e.target.value))}
                            className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-sm text-white"
                          >
                            <option value="0.75">0.75x</option>
                            <option value="1">1x</option>
                            <option value="1.25">1.25x</option>
                            <option value="1.5">1.5x</option>
                            <option value="2">2x</option>
                          </select>
                        </div>

                        {/* Volume slider */}
                        <div>
                          <label className="text-xs text-slate-400 block mb-1">Volume</label>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => setVolume(volume > 0 ? 0 : 1)}
                              className="text-slate-400 hover:text-white transition-colors flex-shrink-0"
                              title={volume > 0 ? 'Mute' : 'Unmute'}
                            >
                              {volume === 0 ? <VolumeX className="w-4 h-4" /> :
                               volume < 0.5 ? <Volume1 className="w-4 h-4" /> :
                               <Volume2 className="w-4 h-4" />}
                            </button>
                            <input
                              type="range"
                              min="0"
                              max="1"
                              step="0.05"
                              value={volume}
                              onChange={(e) => setVolume(parseFloat(e.target.value))}
                              className="flex-1 h-1.5 bg-slate-600 rounded-full appearance-none cursor-pointer accent-green-500 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-green-500 [&::-webkit-slider-thumb]:hover:bg-green-400 [&::-moz-range-thumb]:w-3.5 [&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-green-500 [&::-moz-range-thumb]:border-0"
                            />
                            <span className="text-xs text-slate-400 w-8 text-right flex-shrink-0">
                              {Math.round(volume * 100)}%
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Replay */}
                <button
                  onClick={replay}
                  disabled={!isAudioActive}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title="Restart article"
                >
                  <RotateCcw className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                </button>

                {/* Previous article */}
                <button
                  onClick={previousArticle}
                  disabled={currentIndex === 0}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title="Previous article"
                >
                  <SkipBack className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                </button>

                {/* Play/Pause/Retry */}
                {(() => {
                  // Show spinner during content fetch OR TTS generation
                  const showSpinner = isLoading || articleContentLoading
                  return (
                    <button
                      onClick={togglePlayPause}
                      disabled={showSpinner}
                      className={`flex items-center justify-center rounded-full ${
                        showSpinner
                          ? 'bg-slate-600'  // Grey while loading
                          : error
                            ? 'bg-red-600 hover:bg-red-500'  // Red only when showing retry
                            : 'bg-green-600 hover:bg-green-500'  // Green for play/pause
                      } text-white transition-colors ${isExpanded ? 'w-12 h-12' : 'w-9 h-9'}`}
                      title={showSpinner ? "Loading..." : error ? "Retry" : isPaused || isReady ? "Play" : "Pause"}
                    >
                      {showSpinner ? (
                        <div className={`animate-spin border-2 border-white border-t-transparent rounded-full ${isExpanded ? 'w-6 h-6' : 'w-4 h-4'}`} />
                      ) : error ? (
                        <RefreshCw className={isExpanded ? 'w-6 h-6' : 'w-4 h-4'} />
                      ) : isPaused || isReady ? (
                        <Play className={`${isExpanded ? 'w-6 h-6' : 'w-4 h-4'} ml-0.5`} fill="white" />
                      ) : isPlaying ? (
                        <Pause className={isExpanded ? 'w-6 h-6' : 'w-4 h-4'} />
                      ) : (
                        <Play className={`${isExpanded ? 'w-6 h-6' : 'w-4 h-4'} ml-0.5`} fill="white" />
                      )}
                    </button>
                  )
                })()}

                {/* Next article */}
                <button
                  onClick={nextArticle}
                  disabled={currentIndex >= playlist.length - 1}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title="Next article"
                >
                  <SkipForward className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                </button>

                {/* Speed toggle */}
                <button
                  onClick={() => {
                    const speeds = [1, 1.25, 1.5, 1.75, 2]
                    const currentIdx = speeds.indexOf(playbackRate)
                    const nextIdx = (currentIdx + 1) % speeds.length
                    setRate(speeds[nextIdx])
                  }}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title="Toggle speed"
                >
                  <span className={`font-medium ${isExpanded ? 'text-sm' : 'text-xs'}`}>
                    {playbackRate}x
                  </span>
                </button>

                {/* Continuous play toggle */}
                <button
                  onClick={() => setContinuousPlay(!continuousPlay)}
                  className={`flex items-center justify-center rounded-full transition-colors ${
                    continuousPlay
                      ? 'bg-green-600/30 text-green-400 hover:bg-green-600/40'
                      : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                  } ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title={continuousPlay ? 'Continuous play: ON' : 'Continuous play: OFF'}
                >
                  <Repeat className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                </button>
              </div>

              {/* Secondary controls */}
              <div className="flex items-center gap-1 flex-shrink-0">
                {/* Open article in new tab */}
                {isExpanded && (
                  <a
                    href={currentArticle.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="w-10 h-10 flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors"
                    title="Open on website"
                  >
                    <ExternalLink className="w-5 h-5" />
                  </a>
                )}

                {/* Expand/Minimize */}
                <button
                  onClick={() => setExpanded(!isExpanded)}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title={isExpanded ? "Minimize" : "Expand"}
                >
                  {isExpanded ? <Minimize2 className="w-5 h-5" /> : <Maximize2 className="w-4 h-4" />}
                </button>

                {/* Playlist dropdown (reading queue) */}
                <div className="relative" ref={dropdownRef}>
                  <button
                    onClick={() => {
                      if (showPlaylistDropdown) {
                        window.dispatchEvent(new CustomEvent('article-playlist-hover-cleanup'))
                      }
                      setShowPlaylistDropdown(!showPlaylistDropdown)
                    }}
                    className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-slate-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                    title="Reading queue"
                  >
                    <ListVideo className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                  </button>

                  {showPlaylistDropdown && (
                    <div className="fixed bottom-24 right-4 w-80 max-h-96 overflow-y-auto bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-[60]">
                      <div className="p-2 border-b border-slate-700 sticky top-0 bg-slate-800 z-10">
                        <p className="text-xs text-slate-400">Reading queue ({playlist.length} articles) - Hover to scroll</p>
                      </div>
                      {playlist.map((article, idx) => (
                        <button
                          key={`playlist-${article.url}`}
                          onClick={() => {
                            playArticle(idx)
                            setShowPlaylistDropdown(false)
                            window.dispatchEvent(new CustomEvent('article-playlist-hover-cleanup'))
                          }}
                          onMouseEnter={() => {
                            setHoveredPlaylistIndex(idx)
                            window.dispatchEvent(new CustomEvent('article-playlist-hover', { detail: { url: article.url } }))
                          }}
                          onMouseLeave={() => {
                            setHoveredPlaylistIndex(null)
                            window.dispatchEvent(new CustomEvent('article-playlist-hover-leave', { detail: { url: article.url } }))
                          }}
                          className={`w-full flex items-start gap-3 p-3 hover:bg-slate-700 transition-colors text-left ${
                            idx === currentIndex ? 'bg-green-500/10 border-l-2 border-green-500' : ''
                          } ${hoveredPlaylistIndex === idx ? 'bg-blue-500/10' : ''}`}
                        >
                          <span className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                            idx === currentIndex ? 'bg-green-500 text-white' : hoveredPlaylistIndex === idx ? 'bg-blue-500 text-white' : 'bg-slate-600 text-slate-300'
                          }`}>
                            {idx + 1}
                          </span>
                          {article.has_issue && (
                            <span title="Playback issue" className="flex-shrink-0">
                              <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
                            </span>
                          )}
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-white truncate">{article.title}</p>
                            <p className="text-xs text-slate-500">{article.source_name}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {/* Close */}
                <button
                  onClick={closeMiniPlayer}
                  className={`flex items-center justify-center rounded-full bg-slate-700 hover:bg-red-600 text-white transition-colors ${isExpanded ? 'w-10 h-10' : 'w-8 h-8'}`}
                  title="Close"
                >
                  <X className={isExpanded ? 'w-5 h-5' : 'w-4 h-4'} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Spacer to prevent content from being hidden behind mini-player */}
      {!isExpanded && <div className="h-24 sm:h-20" />}
    </>
  )
}
